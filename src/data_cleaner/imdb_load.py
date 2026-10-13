"""
Load IMDb movies and series into reference.imdb_titles, for matching titles in captions.

    python -m src.data_cleaner.imdb_load              # download (if needed) and load
    python -m src.data_cleaner.imdb_load --download   # force a fresh download first

Uses IMDb's non-commercial datasets (https://datasets.imdbws.com, personal/non-commercial use):
title.basics.tsv.gz (titles, years, genres) and title.ratings.tsv.gz (ratings, votes),
saved in data/imdb/ (gitignored). Only movies, TV movies, series and mini-series that have a
rating are kept. The table is replaced in one transaction.
"""
import argparse
import csv
import time
import gzip
import io
import os
import re
import sys
import unicodedata
import urllib.request

from src.helper.model import engine

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
IMDB_DIR = os.path.join(PROJECT_ROOT, "data", "imdb")
DATASET_URL = "https://datasets.imdbws.com/{}"
FILES = ("title.basics.tsv.gz", "title.ratings.tsv.gz")
KEEP_TYPES = {"movie", "tvMovie", "tvSeries", "tvMiniSeries"}
COLUMNS = ("tconst", "title_type", "primary_title", "original_title", "start_year", "runtime_minutes",
           "genres", "average_rating", "num_votes", "title_key", "original_key")


def title_key(title):
    """'The Velvet Queen' / 'MIRROR' / 'Mírror' -> 'velvet queen' / 'mirror' / 'mirror'."""
    text = unicodedata.normalize("NFKD", title or "").encode("ascii", "ignore").decode().lower()
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    text = re.sub(r"^(the|a|an) ", "", text.strip())
    return re.sub(r"\s+", " ", text).strip()


def download():
    os.makedirs(IMDB_DIR, exist_ok=True)
    for name in FILES:
        print(f"Downloading {name}...")
        urllib.request.urlretrieve(DATASET_URL.format(name), os.path.join(IMDB_DIR, name))


def read_tsv(name):
    """Yield rows of a gzipped IMDb TSV as dicts; '\\N' means empty."""
    with gzip.open(os.path.join(IMDB_DIR, name), "rt", encoding="utf-8") as file:
        # IMDb titles contain stray quotes, so turn off CSV quoting
        for row in csv.DictReader(file, delimiter="\t", quoting=csv.QUOTE_NONE):
            yield {k: (None if v == "\\N" else v) for k, v in row.items()}


def copy_value(value):
    """Escape a value for Postgres COPY text format."""
    if value is None:
        return "\\N"
    return str(value).replace("\\", "\\\\").replace("\t", " ").replace("\n", " ").replace("\r", " ")


def files_age_days():
    """Age of the oldest downloaded IMDb file in days, or None if a file is missing."""
    paths = [os.path.join(IMDB_DIR, f) for f in FILES]
    if not all(os.path.exists(p) for p in paths):
        return None
    return (time.time() - min(os.path.getmtime(p) for p in paths)) / 86400


def run(max_age_days=30, force=False):
    """Download and load IMDb data when it is older than max_age_days; returns a one-line summary."""
    age = files_age_days()
    if not force and age is not None and age < max_age_days:
        with engine.connect() as connection:
            loaded = connection.exec_driver_sql("SELECT count(*) FROM reference.imdb_titles").scalar()
        if loaded:
            return f"IMDb data is {age:.0f} days old (refreshes after {max_age_days}), skipped"
    if force or age is None or age >= max_age_days:
        download()
    return f"{load():,} movies and series loaded"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--download", action="store_true", help="download fresh files even if they exist")
    args = parser.parse_args()

    if args.download or files_age_days() is None:
        download()
    print(f"Done: {load():,} movies and series in reference.imdb_titles")


def load():
    """Load the downloaded files into reference.imdb_titles; returns the number of titles."""

    print("Reading ratings...")
    ratings = {r["tconst"]: (r["averageRating"], r["numVotes"]) for r in read_tsv("title.ratings.tsv.gz")}

    print("Reading titles...")
    buffer = io.StringIO()
    kept = 0
    for row in read_tsv("title.basics.tsv.gz"):
        if row["titleType"] not in KEEP_TYPES or row["isAdult"] == "1" or row["tconst"] not in ratings:
            continue
        rating, votes = ratings[row["tconst"]]
        genres = "{" + ",".join(f'"{g}"' for g in (row["genres"] or "").split(",") if g) + "}"
        values = (
            row["tconst"], row["titleType"], row["primaryTitle"], row["originalTitle"], row["startYear"],
            row["runtimeMinutes"], genres, rating, votes,
            title_key(row["primaryTitle"]), title_key(row["originalTitle"]),
        )
        buffer.write("\t".join(copy_value(v) for v in values) + "\n")
        kept += 1
    buffer.seek(0)

    print(f"Loading {kept:,} titles...")
    connection = engine.raw_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("TRUNCATE reference.imdb_titles")
            cursor.copy_expert(f"COPY reference.imdb_titles ({', '.join(COLUMNS)}) FROM STDIN", buffer)
        connection.commit()  # truncate + load happen together, or not at all
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
    return kept


if __name__ == "__main__":
    sys.exit(main())
