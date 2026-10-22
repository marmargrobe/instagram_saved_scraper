#!/bin/bash
# Back up the local `mars` database to DATA_DIR/backups/postgres/mars-YYYY-MM-DD.dump
# (includes the personal schema: journal entries and everything you corrected in the app).
#
#   scripts/backup_database.sh
#
# Restore into an empty database:   createdb mars_restore && pg_restore -d mars_restore <file>.dump
# The reference schema (IMDb, exercises) is skipped: it can be downloaded again.
# Keeps the newest 8 backups.
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DATA_DIR="$(grep -E '^DATA_DIR=' "$PROJECT_ROOT/.env" 2>/dev/null | cut -d= -f2- | tr -d '"')"
DATA_DIR="${DATA_DIR:-$HOME/Data/saved-instagram}"
DATA_DIR="${DATA_DIR/#\~/$HOME}"
BACKUPS="$DATA_DIR/backups/postgres"
FILE="$BACKUPS/mars-$(date +%F).dump"

mkdir -p "$BACKUPS"
chmod 700 "$BACKUPS"
pg_dump --format=custom --exclude-schema=reference -d mars -f "$FILE"
chmod 600 "$FILE"
echo "Backed up to $FILE ($(du -h "$FILE" | cut -f1))"

# keep the newest 8
ls -1t "$BACKUPS"/mars-*.dump | tail -n +9 | while read -r old; do rm -f "$old"; echo "Removed old backup $(basename "$old")"; done
