"""
Load free-exercise-db into reference.exercises (shown under "Load more exercises" in the Workouts tab).

    python -m src.data_cleaner.exercises_load              # download (if needed) and load
    python -m src.data_cleaner.exercises_load --download   # force a fresh download

free-exercise-db: https://github.com/yuhonas/free-exercise-db (Unlicense / public domain), ~870 exercises
with level, equipment, instructions, primary/secondary muscles and two photos each. Pinned to one commit
so photo URLs stay stable; the JSON is saved in DATA_DIR/raw/reference/free-exercise-db/.
"""
import argparse
import json
import os
import time
import urllib.request

from src.helper import paths
from src.helper.model import engine
from sqlalchemy import text

COMMIT = "f00c92c7dcf1216a928a52c3706c7ce8e2f71ed5"
JSON_URL = f"https://raw.githubusercontent.com/yuhonas/free-exercise-db/{COMMIT}/dist/exercises.json"
IMAGE_BASE = f"https://raw.githubusercontent.com/yuhonas/free-exercise-db/{COMMIT}/exercises/"
JSON_PATH = str(paths.EXERCISES_DIR / "exercises.json")  # DATA_DIR/raw/reference/free-exercise-db


def download():
    os.makedirs(os.path.dirname(JSON_PATH), exist_ok=True)
    urllib.request.urlretrieve(JSON_URL, JSON_PATH)


def load():
    """Replace reference.exercises with the downloaded file; returns the number of exercises."""
    with open(JSON_PATH, encoding="utf-8") as file:
        exercises = json.load(file)
    rows = [{
        "id": e["id"], "name": e["name"], "level": e.get("level"), "category": e.get("category"),
        "equipment": e.get("equipment"), "force": e.get("force"), "mechanic": e.get("mechanic"),
        "primary_muscles": e.get("primaryMuscles") or [], "secondary_muscles": e.get("secondaryMuscles") or [],
        "instructions": e.get("instructions") or [], "images": e.get("images") or [],
    } for e in exercises]
    with engine.begin() as connection:  # delete + insert together, or not at all
        connection.execute(text("DELETE FROM reference.exercises"))
        connection.execute(text("""
            INSERT INTO reference.exercises
                (id, name, level, category, equipment, force, mechanic, primary_muscles, secondary_muscles,
                 instructions, images)
            VALUES (:id, :name, :level, :category, :equipment, :force, :mechanic, :primary_muscles,
                    :secondary_muscles, :instructions, :images)
        """), rows)
    return len(rows)


def run(max_age_days=90):
    """Pipeline step: load if the table is empty or the file is older than max_age_days."""
    with engine.connect() as connection:
        loaded = connection.execute(text("SELECT count(*) FROM reference.exercises")).scalar()
    age = (time.time() - os.path.getmtime(JSON_PATH)) / 86400 if os.path.exists(JSON_PATH) else None
    if loaded and age is not None and age < max_age_days:
        return f"exercise data is {age:.0f} days old (refreshes after {max_age_days}), skipped"
    if age is None or age >= max_age_days:
        download()
    return f"{load()} exercises loaded"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--download", action="store_true", help="download a fresh copy first")
    args = parser.parse_args()
    if args.download or not os.path.exists(JSON_PATH):
        download()
    print(f"{load()} exercises loaded into reference.exercises")


if __name__ == "__main__":
    main()
