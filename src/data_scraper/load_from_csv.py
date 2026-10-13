"""
Load the CSV backups (all_posts*.csv, all_collections_2.csv) into the rawstd tables.

Use this to rebuild the database without logging in to Instagram:
    python -m src.data_scraper.load_from_csv

Rows that already exist (same id) are skipped, so it is safe to re-run.
"""
import os
from datetime import datetime

import numpy as np
import pandas as pd
from psycopg2.extras import execute_values

from src.helper.mapping import reels_column_dtype, reels_column_transformations, transform_dtypes
from src.helper.utils_db import connect_to_db

DATA_DIR = os.path.dirname(__file__)
POST_FILES = ["all_posts_2.csv", "all_posts.csv"]
COLLECTION_FILE = "all_collections_2.csv"

REEL_COLUMNS = [
    "pk", "id", "code", "taken_at", "media_type", "image_versions2", "product_type",
    "thumbnail_url", "location", "user", "comment_count", "comments_disabled",
    "commenting_disabled_for_viewer", "like_count", "play_count", "has_liked",
    "caption_text", "accessibility_caption", "usertags", "sponsor_tags",
    "video_url", "view_count", "video_duration", "title", "resources", "clips_metadata",
]


def to_db_value(value):
    # psycopg2 can't insert NaN/NaT into integer or timestamp columns
    if value is None or (isinstance(value, float) and np.isnan(value)) or value is pd.NaT:
        return None
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime().replace(tzinfo=None)
    if isinstance(value, np.generic):
        return value.item()
    return value


def load_reels(cursor, last_updated):
    for file_name in POST_FILES:
        df = pd.read_csv(os.path.join(DATA_DIR, file_name), dtype={"pk": str, "id": str})
        # accessibility_caption is text in the table; skip the float cast in the mapping
        transformations = {k: v for k, v in reels_column_transformations.items() if k != "accessibility_caption"}
        df = transform_dtypes(df=df, column_transformations=transformations, column_dtypes=reels_column_dtype)

        rows = [
            tuple(to_db_value(row[col]) for col in REEL_COLUMNS) + (last_updated,)
            for row in df.to_dict("records")
        ]
        columns = ", ".join(f'"{c}"' for c in REEL_COLUMNS + ["last_updated"])
        execute_values(
            cursor,
            f"INSERT INTO rawstd.insta_saved_reels ({columns}) VALUES %s ON CONFLICT (id) DO NOTHING",
            rows,
            page_size=len(rows),
        )
        print(f"{file_name}: {len(rows)} rows read, {cursor.rowcount} new rows inserted")


def load_collections(cursor, last_updated):
    df = pd.read_csv(os.path.join(DATA_DIR, COLLECTION_FILE), dtype={"id": str})
    rows = [(r["id"], r["name"].strip(), to_db_value(r["media_count"]), last_updated) for r in df.to_dict("records")]
    execute_values(
        cursor,
        "INSERT INTO rawstd.insta_saved_collections (id, name, media_count, last_updated) VALUES %s ON CONFLICT (id) DO NOTHING",
        rows,
    )
    print(f"{COLLECTION_FILE}: {len(rows)} rows read, {cursor.rowcount} new rows inserted")


if __name__ == "__main__":
    connection = connect_to_db()
    last_updated = datetime.now()
    with connection, connection.cursor() as cursor:
        load_collections(cursor, last_updated)
        load_reels(cursor, last_updated)
    connection.close()
