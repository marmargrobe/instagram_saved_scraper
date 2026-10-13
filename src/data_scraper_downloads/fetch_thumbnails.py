"""
Save a thumbnail for each saved post so the app can show pictures offline.

    python -m src.data_scraper_downloads.fetch_thumbnails                # posts in the recipes tab
    python -m src.data_scraper_downloads.fetch_thumbnails --tab travel
    python -m src.data_scraper_downloads.fetch_thumbnails --tab all --limit 50

Opens each post's public embed page (instagram.com/p/<code>/embed/, the page websites use to
embed posts; no login) in headless Chrome, reads the cover image and saves it as
media/thumbnails/<code>.jpg. Posts that already have a thumbnail are skipped, so it can be
re-run after each import. Instagram's image links expire, which is why the file is saved.

Posts Instagram reports as removed get an empty media/thumbnails/<code>.removed marker so
they are not retried (use --retry-removed to try them again) and the app can say so.
"""
import argparse
import os
import random
import time

import requests
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from sqlalchemy import text

from src.helper.model import engine

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
THUMBNAIL_DIR = os.path.join(PROJECT_ROOT, "media", "thumbnails")
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36"


def thumbnail_path(code):
    return os.path.join(THUMBNAIL_DIR, f"{code}.jpg")


def removed_marker(code):
    return os.path.join(THUMBNAIL_DIR, f"{code}.removed")


def posts_without_thumbnail(tab, limit, retry_removed=False):
    query = "SELECT code, url FROM clean.saved_posts"
    params = {}
    if tab != "all":
        query += " WHERE :tab = ANY (tabs)"
        params["tab"] = tab
    query += " ORDER BY first_saved_at DESC NULLS LAST"
    with engine.connect() as connection:
        posts = connection.execute(text(query), params).all()
    missing = [
        (code, url) for code, url in posts
        if not os.path.exists(thumbnail_path(code)) and (retry_removed or not os.path.exists(removed_marker(code)))
    ]
    return missing[:limit] if limit else missing


def headless_chrome():
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--window-size=800,1000")
    options.add_argument(f"--user-agent={USER_AGENT}")
    return webdriver.Chrome(options=options)


def image_url(driver, post_url):
    driver.get(post_url.rstrip("/") + "/embed/")
    try:
        image = WebDriverWait(driver, 12).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "img.EmbeddedMediaImage"))
        )
    except TimeoutException:
        if "may have been removed" in driver.find_element(By.TAG_NAME, "body").text:
            return "removed"
        return None  # private, slow, or Instagram changed the embed page
    return image.get_property("currentSrc") or image.get_dom_attribute("src")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tab", default="recipes", help="app tab to fetch for (recipes, travel, ...) or 'all'")
    parser.add_argument("--limit", type=int, default=0, help="stop after this many posts (0 = no limit)")
    parser.add_argument("--retry-removed", action="store_true", help="also retry posts marked as removed")
    args = parser.parse_args()

    posts = posts_without_thumbnail(args.tab, args.limit, args.retry_removed)
    if not posts:
        print("Every post already has a thumbnail.")
        return
    os.makedirs(THUMBNAIL_DIR, exist_ok=True)
    print(f"Fetching {len(posts)} thumbnails into {os.path.relpath(THUMBNAIL_DIR, PROJECT_ROOT)}/")

    saved, missing, removed = 0, [], []
    driver = headless_chrome()
    try:
        for code, url in posts:
            src = image_url(driver, url)
            if src == "removed":
                open(removed_marker(code), "w").close()
                removed.append(code)
            elif src:
                response = requests.get(src, headers={"User-Agent": USER_AGENT}, timeout=30)
                if response.ok and response.headers.get("content-type", "").startswith("image/"):
                    with open(thumbnail_path(code), "wb") as file:
                        file.write(response.content)
                    saved += 1
                else:
                    missing.append(code)
            else:
                missing.append(code)
            time.sleep(random.uniform(1.0, 2.5))  # go easy on Instagram
    finally:
        driver.quit()

    print(f"Saved {saved}, removed from Instagram {len(removed)}, no image for {len(missing)}")
    if removed:
        print("  Removed: " + ", ".join(removed))
    if missing:
        print("  No image: " + ", ".join(missing))


if __name__ == "__main__":
    main()
