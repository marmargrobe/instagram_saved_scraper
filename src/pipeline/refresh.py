"""
Refresh everything: import new exports, update reference data, extract new posts, fetch pictures.

    python -m src.pipeline.refresh                       # all steps
    python -m src.pipeline.refresh --only travel,thumbnails
    python -m src.pipeline.refresh --list                # show the steps

Run it with the .venv_data_cleaner environment (it has every library the steps need).
Each step skips itself when there is nothing new, so a refresh with nothing new takes seconds.
Every step is logged in ops.pipeline_runs (the app's "Last updated" and progress come from there).
A failing step is logged and the remaining steps still run. Only one refresh runs at a time.
"""
import argparse
import os
import sys
import traceback
import uuid

from sqlalchemy import text

from src.helper.model import engine

LOCK_ID = 7_301_2026  # any constant; pg_try_advisory_lock makes sure only one refresh runs


def _import():
    from src.data_scraper_downloads import import_export
    return import_export.run()


def _imdb():
    from src.data_cleaner import imdb_load
    return imdb_load.run(max_age_days=30)


def _recipes():
    from src.data_cleaner import recipes_extract
    return recipes_extract.run(new_only=True)


def _travel():
    from src.data_cleaner import travel_extract
    return travel_extract.run(new_only=True)


def _watch_read():
    from src.data_cleaner import watch_read_extract
    return watch_read_extract.run()


def _workouts():
    from src.data_cleaner import workouts_extract
    return workouts_extract.run()


def _journal():
    from src.data_cleaner import journal_prompts_extract
    return journal_prompts_extract.run()


def _thumbnails():
    from src.data_scraper_downloads import fetch_thumbnails
    return fetch_thumbnails.run(tab="any")


# In order: import first, then reference data, the extractors, and pictures last (the slowest).
# Imports happen inside each step so a missing library only fails that step.
STEPS = [
    ("import", _import),
    ("imdb", _imdb),
    ("recipes", _recipes),
    ("travel", _travel),
    ("watch_read", _watch_read),
    ("workouts", _workouts),
    ("journal", _journal),
    ("thumbnails", _thumbnails),
]
SKIPPED_WORDS = ("no new", "skipped", "already has")


def log_start(connection, run_id, step, triggered_by):
    row_id = connection.execute(
        text("""INSERT INTO ops.pipeline_runs (run_id, step, status, triggered_by)
                VALUES (:run_id, :step, 'running', :by) RETURNING id"""),
        {"run_id": run_id, "step": step, "by": triggered_by},
    ).scalar()
    connection.commit()
    return row_id


def log_end(connection, row_id, status, summary=None, error=None):
    connection.execute(
        text("""UPDATE ops.pipeline_runs SET status = :status, finished_at = now(), summary = :summary, error = :error
                WHERE id = :id"""),
        {"status": status, "summary": summary, "error": error, "id": row_id},
    )
    connection.commit()


def refresh(only=None, triggered_by="cli"):
    """Run the steps (or only the named ones); returns {step: status}."""
    steps = [(name, fn) for name, fn in STEPS if not only or name in only]
    run_id = str(uuid.uuid4())
    results = {}
    with engine.connect() as connection:
        if not connection.execute(text("SELECT pg_try_advisory_lock(:id)"), {"id": LOCK_ID}).scalar():
            print("Another refresh is already running.")
            return {"lock": "busy"}
        connection.commit()
        try:
            for name, step in steps:
                print(f"▶ {name}", flush=True)
                row_id = log_start(connection, run_id, name, triggered_by)
                try:
                    summary = step()
                    status = "skipped" if any(w in summary.lower() for w in SKIPPED_WORDS) else "done"
                    log_end(connection, row_id, status, summary=summary)
                except Exception as error:  # keep going: later steps work on whatever data exists
                    connection.rollback()
                    status = "failed"
                    log_end(connection, row_id, status, error=f"{error}\n\n{traceback.format_exc()}"[:4000])
                    summary = f"FAILED: {error}"
                results[name] = status
                print(f"  {status}: {summary}", flush=True)
        finally:
            connection.execute(text("SELECT pg_advisory_unlock(:id)"), {"id": LOCK_ID})
            connection.commit()
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--only", help="comma-separated steps, e.g. travel,thumbnails")
    parser.add_argument("--triggered-by", default="cli", choices=["cli", "app", "schedule"])
    parser.add_argument("--list", action="store_true", help="list the steps and exit")
    args = parser.parse_args()
    if args.list:
        print("\n".join(name for name, _ in STEPS))
        return 0
    only = {s.strip() for s in args.only.split(",")} if args.only else None
    unknown = (only or set()) - {name for name, _ in STEPS}
    if unknown:
        parser.error(f"unknown step(s): {', '.join(sorted(unknown))}")
    os.chdir(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))  # .env lives here
    results = refresh(only, args.triggered_by)
    return 1 if "failed" in results.values() else 0


if __name__ == "__main__":
    sys.exit(main())
