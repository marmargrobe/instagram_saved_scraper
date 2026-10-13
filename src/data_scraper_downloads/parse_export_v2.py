"""
Parser for the newer Instagram export layout (seen in exports from 2026).

Unlike the 2024 layout, each saved post includes its caption, hashtags and owner, so the
caption also goes into rawstd.insta_download_saved_reels_details.

saved_posts.html:       one block per post: URL, Caption, Hashtags, Owner, then the saved time
saved_collections.html: one block per collection: Name, Type, Privacy, Update time, then Media
                        (same per-post fields, no saved time)
"""
import os
import re
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from src.data_scraper_downloads.utils import parse_datetime
from src.helper.model import (
    engine,
    RawstdInstaDownloadSavedCollections,
    RawstdInstaDownloadSavedReels,
    RawstdInstaDownloadSavedReelsDetails,
)
from src.helper.utils_model import insert_record_with_conflict

Session = sessionmaker(bind=engine)
POST_URL = re.compile(r"https://www\.instagram\.com/(?:reel|p)/[^/?#]+/?")


def _top_blocks(soup):
    """One block per post/collection; the same CSS class is reused on nested elements."""
    main = soup.find("main") or soup.body
    return main.find_all("div", recursive=False)


def is_v2_layout(soup):
    return any(h2.get_text(strip=True) in ("Owner", "Media") for h2 in soup.find_all("h2"))


def _label_value(scope, label):
    """Value cell next to a <td>label</td>, searching scope (first match)."""
    for td in scope.find_all("td"):
        if td.get_text(strip=True) == label:
            value = td.find_next_sibling("td")
            if value:
                return value.get_text(" ", strip=True) or None
    return None


def _section(scope, heading):
    for h2 in scope.find_all("h2"):
        if h2.get_text(strip=True) == heading:
            return h2.find_next_sibling("div")
    return None


def _post_tables(scope):
    """Tables that describe one post: their first row is a URL cell linking to the post."""
    tables = []
    for td in scope.find_all("td", colspan="2"):
        link = td.find("a", href=POST_URL)
        if link and td.find(string=True, recursive=False) and td.find(string=True, recursive=False).strip() == "URL":
            tables.append(td.find_parent("table"))
    return tables


def _parse_post(table):
    link = table.find("a", href=POST_URL)
    hashtags_div = _section(table, "Hashtags")
    hashtags = []
    if hashtags_div:
        for div in hashtags_div.find_all("div"):
            if not div.find("div"):
                text = div.get_text(strip=True)
                if text and text != "Name":
                    hashtags.append(text)
    owner = _section(table, "Owner")
    return {
        "reel_url": POST_URL.match(link["href"]).group(0),
        "caption_text": _label_value(table, "Caption"),
        "hashtags": list(dict.fromkeys(hashtags)),
        "user_name": _label_value(owner, "Username") if owner else None,
    }


def parse_saved_posts(soup):
    posts = []
    for block in _top_blocks(soup):
        tables = _post_tables(block)
        if not tables:
            continue
        post = _parse_post(tables[0])
        # The saved time is the block's last direct child div
        children = block.find_all("div", recursive=False)
        post["added_time"] = parse_datetime(children[-1].get_text(strip=True)) if len(children) > 1 else None
        posts.append(post)
    return posts


def parse_saved_collections(soup):
    collections = []
    for block in _top_blocks(soup):
        first_row = block.find("tr")
        cells = first_row.find_all("td", recursive=False) if first_row else []
        if len(cells) != 2 or cells[0].get_text(strip=True) != "Name":
            continue
        media = _section(block, "Media")
        collections.append({
            "collection_name": cells[1].get_text(strip=True),
            "update_time": parse_datetime(_label_value(block, "Update time") or ""),
            "posts": [_parse_post(table) for table in _post_tables(media)] if media else [],
        })
    return collections


def load_export(posts_soup, collections_soup, target_profile):
    """Insert saves, collections and post details. Existing rows are left alone."""
    session = Session()
    script_name = os.path.basename(__file__)
    runtime = datetime.now()
    reel_unique = ["collection_name", "reel_url", "insta_account"]
    details = {}

    def add_reel(post, collection_name, added_time):
        insert_record_with_conflict(session=session, target_table=RawstdInstaDownloadSavedReels, unique_columns=reel_unique, data={
            "collection_name": collection_name,
            "user_name": post["user_name"],
            "reel_url": post["reel_url"],
            "added_time": added_time,
            "insta_account": target_profile,
            "python_script": script_name,
            "python_runtime": runtime,
        })
        details.setdefault(post["reel_url"], post)

    if posts_soup is not None:
        for post in parse_saved_posts(posts_soup):
            add_reel(post, None, post["added_time"])

    if collections_soup is not None:
        for collection in parse_saved_collections(collections_soup):
            insert_record_with_conflict(
                session=session,
                target_table=RawstdInstaDownloadSavedCollections,
                unique_columns=["collection_name", "insta_account"],
                data={
                    "collection_name": collection["collection_name"],
                    "creation_time": None,
                    "update_time": collection["update_time"],
                    "insta_account": target_profile,
                    "python_script": script_name,
                    "python_runtime": runtime,
                },
            )
            for post in collection["posts"]:
                add_reel(post, collection["collection_name"], None)
    session.commit()

    # One details row per post URL, linked to one of its saved_reels rows
    reels = RawstdInstaDownloadSavedReels
    already = set(session.scalars(
        select(RawstdInstaDownloadSavedReelsDetails.reel_url)
        .where(RawstdInstaDownloadSavedReelsDetails.insta_account == target_profile)
    ))
    for url, post in details.items():
        if url in already:
            continue
        reel_id = session.scalars(
            select(reels.id).where(reels.reel_url == url, reels.insta_account == target_profile)
            .order_by(reels.collection_name.is_not(None))  # prefer the "All posts" row
        ).first()
        session.add(RawstdInstaDownloadSavedReelsDetails(
            reel_id=reel_id,
            user_name=post["user_name"],
            reel_url=url,
            caption_text=post["caption_text"],
            hashtags=post["hashtags"],
            insta_account=target_profile,
            python_script=script_name,
            python_runtime=runtime,
        ))
    session.commit()
    session.close()
