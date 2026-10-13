"""
Find the movies, series and books in Watch / read posts (clean.watch_read_titles).

    python -m src.data_cleaner.watch_read_extract

Candidate titles come from caption patterns:
  title_year  "Phantom Thread (2017) is ..."     quoted   “Detachment”, ‘Barefoot’
  emoji       "📽️ The Empty man"                 caps     "Tarkovsky's MIRROR"
  reading     "reading A Little Life on a train"  spacy    spaCy WORK_OF_ART entities
Movies and series are checked against reference.imdb_titles (python -m src.data_cleaner.imdb_load),
which also gives year, genres, rating and runtime. Books are looked up on Open Library (free).
Posts where nothing matches have no rows; the app counts them as "no title found".
"""
import json
import re
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime

import spacy
from sqlalchemy import text

from src.data_cleaner.imdb_load import title_key
from src.helper.model import engine

EXTRACTOR_VERSION = "1.0"
USER_AGENT = "saved-instagram-watch-read (personal, non-commercial project)"

# Most trusted first; also the order used to pick a post's primary title
FOUND_BY_PRIORITY = ["title_year", "quoted", "emoji", "reading", "caps", "spacy"]
# Weak guesses must match a well-known title so random words don't become obscure films
MIN_VOTES = {"title_year": 0, "quoted": 200, "emoji": 200, "reading": 0, "caps": 5000, "spacy": 5000}

SMALL_WORDS = {"of", "the", "a", "an", "and", "in", "on", "to", "for", "at", "with", "from", "is"}
CAPS_STOPWORDS = {
    "OMG", "LOL", "FOLLOW", "COMMENT", "SAVE", "SHARE", "NEW", "WATCH", "MOVIE", "MOVIES", "FILM",
    "LINK", "BIO", "FYP", "THIS", "THAT", "WHAT", "WHEN", "THE", "AND", "YOU", "YOUR", "RIGHT", "NOW",
    "COURSE", "FREE", "MUST", "BEST", "TOP", "POV", "NETFLIX", "HBO", "PART", "EPISODE",
}

TITLE_YEAR = re.compile(r"([^\n()]{1,70}?)\s*\(((?:19|20)\d{2})\)")
QUOTED = re.compile(r"[“\"‘]([A-Z0-9][^“”\"‘’\n]{1,60}?)[”\"’]")
EMOJI = re.compile(r"(?:🎬|📽️?|🎥|🍿|📺)\s*[:\-–]?\s*([A-Z0-9][^\n#@]{1,60})")
CAPS = re.compile(r"\b([A-Z][A-Z0-9'’&]{2,}(?:\s+[A-Z][A-Z0-9'’&]+){0,4})\b")
READING = re.compile(r"\breading\s+((?:[A-Z][\w'’]*)(?:\s+(?:[A-Z][\w'’]*|of|the|a|an|and|in|on|to))*)")


def title_before(chunk):
    """The capitalized run of words right before '(2017)': 'Phantom Thread' from '...ok. Phantom Thread'."""
    chunk = re.split(r"[.!?:🎬📽🎥\n]|\s[-–|]\s", chunk)[-1]
    chunk = chunk.strip(" ‘’'\"“”*_")
    words = chunk.split()
    title = []
    for word in reversed(words):
        bare = word.strip("‘’'\"“”,")
        if bare[:1].isupper() or bare[:1].isdigit() or (bare.lower() in SMALL_WORDS and title):
            title.insert(0, bare)
        else:
            break
    while title and title[0].lower() in SMALL_WORDS - {"the", "a", "an"}:
        title.pop(0)
    return " ".join(title) or None


def find_candidates(caption, nlp):
    """[(title, found_by, year or None)] in the order found."""
    found = []

    def add(title, found_by, year=None):
        title = (title or "").strip(" ‘’'\"“”,.!?*_-–")
        if len(title) >= 2 and title_key(title) and title_key(title) not in [title_key(t) for t, _, _ in found]:
            found.append((title, found_by, int(year) if year else None))

    for match in TITLE_YEAR.finditer(caption):
        add(title_before(match.group(1)), "title_year", match.group(2))
    for match in QUOTED.finditer(caption):
        add(match.group(1), "quoted")
    for match in EMOJI.finditer(caption):
        add(match.group(1), "emoji")
    for match in READING.finditer(caption):
        add(match.group(1), "reading")
    for match in CAPS.finditer(caption):
        words = match.group(1).split()
        if not set(words) & CAPS_STOPWORDS and sum(len(w) for w in words) >= 4:
            add(match.group(1), "caps")
    for ent in nlp(caption[:3000]).ents:
        if ent.label_ == "WORK_OF_ART":
            add(ent.text, "spacy")
    return found


def match_imdb(connection, title, found_by, year):
    """Best IMDb movie/series for this title, or None."""
    rows = connection.execute(
        text("""
            SELECT tconst, title_type, primary_title, start_year, genres, average_rating, num_votes, runtime_minutes
            FROM reference.imdb_titles
            WHERE (title_key = :key OR original_key = :key) AND num_votes >= :min_votes
              AND (CAST(:year AS INTEGER) IS NULL OR start_year BETWEEN :year - 1 AND :year + 1)
            ORDER BY num_votes DESC
            LIMIT 1
        """),
        {"key": title_key(title), "min_votes": MIN_VOTES[found_by], "year": year},
    ).mappings().first()
    if not rows:
        return None
    return {
        "kind": "movie" if rows["title_type"] in ("movie", "tvMovie") else "series",
        "matched_title": rows["primary_title"], "year": rows["start_year"], "genres": rows["genres"] or [],
        "rating": rows["average_rating"], "votes": rows["num_votes"], "runtime_minutes": rows["runtime_minutes"],
        "imdb_id": rows["tconst"],
    }


def match_book(title):
    """Best Open Library match for a book title, or None."""
    url = "https://openlibrary.org/search.json?" + urllib.parse.urlencode(
        {"title": title, "limit": 1, "fields": "key,title,author_name,first_publish_year,subject"}
    )
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            docs = json.load(response).get("docs", [])
    except OSError as error:
        print(f"  Open Library lookup failed for {title!r}: {error}")
        return None
    if not docs or title_key(docs[0].get("title")) != title_key(title):
        return None
    book = docs[0]
    return {
        "kind": "book", "matched_title": book.get("title"), "year": book.get("first_publish_year"),
        "genres": [s for s in (book.get("subject") or []) if len(s) < 30][:3],
        "author": ", ".join((book.get("author_name") or [])[:2]) or None, "openlibrary_key": book.get("key"),
    }


def main():
    nlp = spacy.load("en_core_web_sm")
    now = datetime.now()
    rows = []
    with engine.connect() as connection:
        posts = connection.execute(text("""
            SELECT code, caption, collections FROM clean.saved_posts WHERE 'watch_read' = ANY (tabs)
        """)).all()
        for post in posts:
            if not post.caption:
                continue
            is_books_post = "Books" in post.collections
            post_rows = []
            for title, found_by, year in find_candidates(post.caption, nlp):
                match = None
                if found_by == "reading" or is_books_post:
                    match = match_book(title)
                if match is None and found_by != "reading":
                    match = match_imdb(connection, title, found_by, year)
                if match is None:
                    continue  # not a real title
                post_rows.append({
                    "code": post.code, "title": title, "found_by": found_by, "kind": None, "matched_title": None,
                    "year": None, "genres": [], "rating": None, "votes": None, "runtime_minutes": None,
                    "imdb_id": None, "openlibrary_key": None, "author": None, "is_primary": False,
                    "extractor_version": EXTRACTOR_VERSION, "extracted_at": now, **match,
                })
            if post_rows:
                min(post_rows, key=lambda r: FOUND_BY_PRIORITY.index(r["found_by"]))["is_primary"] = True
            rows.extend(post_rows)

        codes = [p.code for p in posts]
        connection.execute(text("DELETE FROM clean.watch_read_titles WHERE code = ANY (:codes)"), {"codes": codes})
        if rows:
            connection.execute(text("""
                INSERT INTO clean.watch_read_titles
                    (code, title, found_by, kind, matched_title, year, genres, rating, votes, runtime_minutes,
                     imdb_id, openlibrary_key, author, is_primary, extractor_version, extracted_at)
                VALUES
                    (:code, :title, :found_by, :kind, :matched_title, :year, :genres, :rating, :votes, :runtime_minutes,
                     :imdb_id, :openlibrary_key, :author, :is_primary, :extractor_version, :extracted_at)
                ON CONFLICT (code, title) DO NOTHING
            """), rows)
        connection.commit()

    with_title = {r["code"] for r in rows}
    no_caption = sum(1 for p in posts if not p.caption)
    print(f"{len(posts)} watch/read posts: {len(with_title)} with a title, "
          f"{len(posts) - len(with_title) - no_caption} with a caption but no title, {no_caption} without a caption")
    print("Found by: " + ", ".join(f"{k} {v}" for k, v in Counter(r["found_by"] for r in rows).most_common()))


if __name__ == "__main__":
    main()
