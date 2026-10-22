"""
Import a new Instagram "Download your information" export into the rawstd download tables.

1. Request the export in Instagram (Accounts Center > Your information and permissions >
   Download your information > Saved, format HTML) and download it when the email arrives.
2. Run:
       python -m src.data_scraper_downloads.import_export

The script looks in ~/Downloads for instagram-<profile>-<date>-<id>.zip (or the folder
Safari unzips it to), copies its saved/ folder into DATA_DIR/raw/instagram/exports/<account>/
(with a manifest.json listing every file and its checksum), and loads the
newest export for each profile. Posts already in the database are skipped, so re-running is safe.

Options:
    --source PATH   a specific .zip/folder, or a folder to search (default: ~/Downloads)
    --dry-run       show what would be imported without touching anything
    --verbose       show every row the loaders insert
    --profile NAME  re-import the newest export already copied for NAME
"""
import argparse
import contextlib
import hashlib
import io
import json
import logging
import os
import re
import shutil
import zipfile
from datetime import datetime

from sqlalchemy import text

from src.helper import paths
from src.helper.model import engine
from src.data_scraper_downloads.utils import get_soup_from_file_path
from src.data_scraper_downloads import parse_export_v2, scrape_saved_collections, scrape_saved_posts

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


def export_dir(name):
    """DATA_DIR/raw/instagram/exports/<account>/<export folder name>"""
    return str(paths.INSTAGRAM_EXPORTS / EXPORT_NAME.match(name)["profile"] / name)


def write_manifest(destination, source):
    """manifest.json next to the export: where it came from, when, and a checksum of every file."""
    files = []
    for root, _, names in os.walk(destination):
        for file_name in sorted(names):
            if file_name == "manifest.json":
                continue
            full = os.path.join(root, file_name)
            with open(full, "rb") as file:
                digest = hashlib.sha256(file.read()).hexdigest()
            files.append({"path": os.path.relpath(full, destination), "bytes": os.path.getsize(full), "sha256": digest})
    manifest = {"source": os.path.basename(source), "imported_at": datetime.now().isoformat(timespec="seconds"),
                "files": files}
    with open(os.path.join(destination, "manifest.json"), "w") as file:
        json.dump(manifest, file, indent=2)


def copy_export(name, path):
    """Copy or unzip the saved-posts part of an export into DATA_DIR/raw/instagram/exports/<account>/<name>.

    A full account export also holds messages, login history and media, so only
    your_instagram_activity/saved/ is copied.
    """
    destination = export_dir(name)
    if os.path.isdir(path):
        shutil.copytree(os.path.join(path, SAVED_DIR), os.path.join(destination, SAVED_DIR))
        write_manifest(destination, path)
        return destination

    with zipfile.ZipFile(path) as archive:
        members = archive.namelist()
        # Some zips wrap everything in a top-level folder named like the export; drop it
        prefix = f"{name}/" if all(m.startswith(f"{name}/") for m in members) else ""
        for member in members:
            relative = member[len(prefix):]
            if not relative.startswith(SAVED_DIR + "/"):
                continue
            target = os.path.realpath(os.path.join(destination, relative))
            if not target.startswith(os.path.realpath(destination) + os.sep):
                continue  # skip anything that would land outside the destination
            if member.endswith("/"):
                os.makedirs(target, exist_ok=True)
                continue
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with archive.open(member) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)
    write_manifest(destination, path)
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
        captions = connection.execute(
            text("SELECT count(*) FROM rawstd.insta_download_saved_reels_details WHERE insta_account = :p AND caption_text IS NOT NULL"),
            {"p": profile},
        ).scalar()
    return reels, collections, latest, captions


def import_profile(profile, verbose):
    before = saved_counts(profile)
    output = contextlib.nullcontext() if verbose else contextlib.redirect_stdout(io.StringIO())
    with output:
        soups = [get_soup_from_file_path(target_profile=profile, saved_target=target) for _, target in LOADERS]
        if any(soup is not None and parse_export_v2.is_v2_layout(soup) for soup in soups):
            # Newer layout: includes captions, hashtags and owners
            parse_export_v2.load_export(posts_soup=soups[1], collections_soup=soups[0], target_profile=profile)
        else:
            for (module, _), soup in zip(LOADERS, soups):
                if soup:
                    module.process_collections_and_reels(soup=soup, target_profile=profile)
    after = saved_counts(profile)
    lines = [f"  {os.path.basename(target)} not in this export, skipped"
             for (_, target), soup in zip(LOADERS, soups) if soup is None]
    lines += [
        f"  saved posts: {before[0]} -> {after[0]} (+{after[0] - before[0]})",
        f"  collections: {before[1]} -> {after[1]} (+{after[1] - before[1]})",
        f"  newest save: {before[2]} -> {after[2]}",
        f"  captions:    {before[3]} -> {after[3]} (+{after[3] - before[3]})",
    ]
    if after[0] == before[0] and after[2] == before[2]:
        lines.append("  nothing new; if you expected new saves, Instagram may have changed the export's HTML layout")
    summary = (f"{profile}: +{after[0] - before[0]} saves, +{after[1] - before[1]} collections, "
               f"+{after[3] - before[3]} captions")
    return lines, summary


def run(source="~/Downloads"):
    """Copy and import new exports found in source; returns a one-line summary."""
    logging.getLogger("src.helper.utils_model").setLevel(logging.ERROR)
    exports = find_exports(os.path.expanduser(source))
    new_exports = {n: p for n, p in exports.items() if not os.path.exists(export_dir(n))}
    if not new_exports:
        return f"no new Instagram exports in {source}"
    profiles = set()
    for name, path in sorted(new_exports.items()):
        copy_export(name, path)
        profiles.add(EXPORT_NAME.match(name)["profile"])
    return "; ".join(import_profile(profile, verbose=False)[1] for profile in sorted(profiles))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", default=os.path.expanduser("~/Downloads"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--profile", help="re-import the newest export already in the data folder for this profile")
    args = parser.parse_args()

    if not args.verbose:
        # insert_record_with_conflict warns on every already-loaded row
        logging.getLogger("src.helper.utils_model").setLevel(logging.ERROR)

    if args.profile:
        print(f"Importing {args.profile}")
        print("\n".join(import_profile(args.profile, args.verbose)[0]))
        return

    exports = find_exports(os.path.expanduser(args.source))
    new_exports = {n: p for n, p in exports.items() if not os.path.exists(export_dir(n))}
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
        print(f"Copying {os.path.basename(path)} -> {export_dir(name)}")
        copy_export(name, path)

    if args.dry_run:
        return
    for profile in sorted(profiles):
        print(f"Importing {profile}")
        print("\n".join(import_profile(profile, args.verbose)[0]))


if __name__ == "__main__":
    main()
