"""
Import a new Instagram "Download your information" export into the rawstd download tables.

1. Request the export in Instagram (Accounts Center > Your information and permissions >
   Download your information > Saved, format HTML) and download it when the email arrives.
2. Run:
       python -m src.data_scraper_downloads.import_export

The script looks in ~/Downloads for instagram-<profile>-<date>-<id>.zip (or the folder
Safari unzips it to), copies it into src/data_scraper_downloads/downloaded/, and loads the
newest export for each profile. Posts already in the database are skipped, so re-running is safe.

Options:
    --source PATH   a specific .zip/folder, or a folder to search (default: ~/Downloads)
    --dry-run       show what would be imported without touching anything
    --verbose       show every row the loaders insert
"""
import argparse
import contextlib
import io
import logging
import os
import re
import shutil
import zipfile

from sqlalchemy import text

from src.helper.model import engine
from src.data_scraper_downloads.utils import get_soup_from_file_path
from src.data_scraper_downloads import scrape_saved_collections, scrape_saved_posts

DOWNLOADED_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "downloaded")
EXPORT_NAME = re.compile(r"^instagram-(?P<profile>.+)-(?P<date>\d{4}-\d{2}-\d{2})-[^.]+$")
SAVED_DIR = os.path.join("your_instagram_activity", "saved")
LOADERS = [
    (scrape_saved_collections, os.path.join(SAVED_DIR, "saved_collections.html")),
    (scrape_saved_posts, os.path.join(SAVED_DIR, "saved_posts.html")),
]


def find_exports(source):
    """Return {export_name: path} for every export zip/folder at or directly inside source."""
    candidates = [source] if EXPORT_NAME.match(_export_name(source)) else [
        os.path.join(source, name) for name in os.listdir(source)
    ]
    exports = {}
    for path in candidates:
        name = _export_name(path)
        if not EXPORT_NAME.match(name):
            continue
        if zipfile.is_zipfile(path) or os.path.isdir(os.path.join(path, SAVED_DIR)):
            exports[name] = path
    return exports


def _export_name(path):
    name = os.path.basename(os.path.normpath(path))
    return name[:-4] if name.endswith(".zip") else name


def copy_export(name, path):
    """Copy or unzip an export into downloaded/<name>. Returns the destination folder."""
    destination = os.path.join(DOWNLOADED_DIR, name)
    if os.path.isdir(path):
        shutil.copytree(path, destination)
        return destination

    with zipfile.ZipFile(path) as archive:
        members = archive.namelist()
        # Some zips wrap everything in a top-level folder named like the export; drop it
        prefix = f"{name}/" if all(m.startswith(f"{name}/") for m in members) else ""
        for member in members:
            relative = member[len(prefix):]
            target = os.path.realpath(os.path.join(destination, relative))
            if not target.startswith(os.path.realpath(destination) + os.sep):
                continue  # skip anything that would land outside the destination
            if member.endswith("/"):
                os.makedirs(target, exist_ok=True)
                continue
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with archive.open(member) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)
    return destination


def saved_counts(profile):
    with engine.connect() as connection:
        reels, latest = connection.execute(
            text("SELECT count(*), max(added_time) FROM rawstd.insta_download_saved_reels WHERE insta_account = :p"),
            {"p": profile},
        ).one()
        collections = connection.execute(
            text("SELECT count(*) FROM rawstd.insta_download_saved_collections WHERE insta_account = :p"),
            {"p": profile},
        ).scalar()
    return reels, collections, latest


def import_profile(profile, verbose):
    before = saved_counts(profile)
    for module, saved_target in LOADERS:
        output = contextlib.nullcontext() if verbose else contextlib.redirect_stdout(io.StringIO())
        with output:
            soup = get_soup_from_file_path(target_profile=profile, saved_target=saved_target)
            if soup:
                module.process_collections_and_reels(soup=soup, target_profile=profile)
        if soup is None:
            print(f"  {os.path.basename(saved_target)} not in this export, skipped")
    after = saved_counts(profile)

    print(f"  saved posts: {before[0]} -> {after[0]} (+{after[0] - before[0]})")
    print(f"  collections: {before[1]} -> {after[1]} (+{after[1] - before[1]})")
    print(f"  newest save: {before[2]} -> {after[2]}")
    if after[0] == before[0] and after[2] == before[2]:
        print("  nothing new; if you expected new saves, Instagram may have changed the export's HTML layout")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", default=os.path.expanduser("~/Downloads"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    if not args.verbose:
        # insert_record_with_conflict warns on every already-loaded row
        logging.getLogger("src.helper.utils_model").setLevel(logging.ERROR)

    exports = find_exports(os.path.expanduser(args.source))
    new_exports = {n: p for n, p in exports.items() if not os.path.exists(os.path.join(DOWNLOADED_DIR, n))}
    if not new_exports:
        print(f"No new Instagram exports found in {args.source}")
        if exports:
            print("Already copied: " + ", ".join(sorted(exports)))
        return

    profiles = set()
    for name, path in sorted(new_exports.items()):
        profile = EXPORT_NAME.match(name)["profile"]
        profiles.add(profile)
        if args.dry_run:
            print(f"Would import {path} ({profile})")
            continue
        print(f"Copying {os.path.basename(path)} -> downloaded/{name}")
        copy_export(name, path)

    if args.dry_run:
        return
    for profile in sorted(profiles):
        print(f"Importing {profile}")
        import_profile(profile, args.verbose)


if __name__ == "__main__":
    main()
