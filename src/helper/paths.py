"""
Where data lives. Data is kept outside the code repository, under DATA_DIR (set in .env; default
~/Data/saved-instagram), so it can never be committed by accident:

    DATA_DIR/
      raw/                                  as received; never edited
        instagram/exports/<account>/<export folder>/   Instagram "Download your information" exports
        instagram/csv_backups_2024/                    CSVs from the 2024 API scrape
        reference/imdb/                                IMDb non-commercial datasets
        reference/free-exercise-db/                    exercise database JSON
      derived/                              can be rebuilt from raw/ (or re-fetched)
        thumbnails/                                    post cover images
      config/                               local settings that aren't code (proxy lists)
      backups/postgres/                     pg_dump files (scripts/backup_database.sh)
      logs/                                 refresh pipeline log
      archive/                              things kept for reference (e.g. files removed from git)
"""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

DATA_DIR = Path(os.getenv("DATA_DIR", "~/Data/saved-instagram")).expanduser()

RAW = DATA_DIR / "raw"
INSTAGRAM_EXPORTS = RAW / "instagram" / "exports"
CSV_BACKUPS = RAW / "instagram" / "csv_backups_2024"
IMDB_DIR = RAW / "reference" / "imdb"
EXERCISES_DIR = RAW / "reference" / "free-exercise-db"

DERIVED = DATA_DIR / "derived"
THUMBNAILS = DERIVED / "thumbnails"

CONFIG = DATA_DIR / "config"
PROXIES = CONFIG / "proxies"

BACKUPS = DATA_DIR / "backups" / "postgres"
LOGS = DATA_DIR / "logs"
ARCHIVE = DATA_DIR / "archive"
