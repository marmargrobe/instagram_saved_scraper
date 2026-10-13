"""
Pull journal prompts (questions and ChatGPT prompts) out of Journals posts (clean.journal_prompts).

    python -m src.data_cleaner.journal_prompts_extract

One row per prompt. Categories are a first guess from keyword rules (CATEGORIES); my own labels
live in clean.journal_prompt_choices, keyed by the prompt's text, so they survive re-extraction.
"""
import hashlib
import re
from collections import Counter
from datetime import datetime

from sqlalchemy import text

from src.helper.model import engine

EXTRACTOR_VERSION = "1.0"

# Checked in order; the first match wins.
CATEGORIES = [
    ("relationships", r"\bpartner|relationship|dating|\bdate\b|married|marriage|children|kids|love\b|romantic"),
    ("purpose & career", r"\bwork\b|career|\bjob\b|skills?|talents?|passion|purpose|business|money|financ|teach"),
    ("goals & future", r"goals?|future|next year|years? from now|plans?|dreams?|ambitions?|resources"),
    ("healing & emotions", r"hardest|stress|comfort|overcome|challenges?|hurt|fear|heal|pain|peace|anxious"),
    ("gratitude & joy", r"grateful|gratitude|\bjoy\b|happ(?:y|iest)|compliment|alive|enjoy|perfect day"),
    ("self-discovery", r".*"),  # everything else
]
# A post about dating/partners puts its questions under "relationships" even when a single question doesn't say so
RELATIONSHIP_POST = re.compile(
    r"potential partner|dating for|falling for|getting to date|questions to ask (?:your|a) (?:partner|date)", re.IGNORECASE
)

LIST_MARKER = re.compile(r"^\s*(?:\d{1,2}\s*[.)]\s*|[-•*·]\s+|[^\w\s\"“'‘(\[]{1,3}\s*)")
ONLY_NUMBER = re.compile(r"^\s*\d{1,2}\s*[.)]\s*$")
CHATGPT = re.compile(r"chatgpt|chat gpt|\bai\b|act as|help me|can you", re.IGNORECASE)


def prompt_key(prompt):
    normalized = re.sub(r"[^a-z0-9 ]", "", prompt.lower())
    return hashlib.md5(re.sub(r"\s+", " ", normalized).strip().encode()).hexdigest()


def list_items(caption):
    """Text of each list item (marker removed), with its preceding heading line if any."""
    items, pending_number, previous = [], False, None
    for raw in caption.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("*"):  # "*could weave into ..." is a note, not a prompt
            previous = None
            continue
        if ONLY_NUMBER.match(line):  # "11." alone on a line: the item is on the next line
            pending_number = True
            continue
        marked = pending_number or bool(LIST_MARKER.match(line)) and LIST_MARKER.match(line).group(0).strip() != ""
        pending_number = False
        item = LIST_MARKER.sub("", line, count=1).strip() if marked else line
        if item.lower().startswith("prompt:"):  # "Prompt: ..." belongs to the heading above it
            items.append((item[len("prompt:"):].strip(), previous))
        elif marked:
            items.append((item, None))
        previous = item
    return items


def classify(item):
    """('question' | 'chatgpt', cleaned text) or None if the item isn't a prompt."""
    item = item.replace("*", "").strip()  # *typical* -> typical
    quoted = item[:1] in "\"“"
    item = item.strip("\"“”' ")
    if len(item) < 8:
        return None
    if quoted or (CHATGPT.search(item) and not item.endswith("?")):
        return ("chatgpt", item) if quoted or item.lower().startswith(("act as", "help me", "guide me", "provide", "challenge me")) else None
    if "?" in item:
        item = re.sub(r"(\?)\s+[a-z][^?]*$", r"\1", item)  # drop a lowercase note after the question
        return "question", item[0].upper() + item[1:]
    return None


def category_for(prompt, kind, relationship_post):
    if kind == "chatgpt":
        return "ChatGPT"
    if relationship_post:
        return "relationships"
    for label, pattern in CATEGORIES:
        if re.search(pattern, prompt, re.IGNORECASE):
            return label
    return None


def main():
    now = datetime.now()
    rows = []
    with engine.connect() as connection:
        posts = connection.execute(text(
            "SELECT code, caption FROM clean.saved_posts WHERE 'journals' = ANY (tabs) AND caption IS NOT NULL"
        )).all()
        for post in posts:
            relationship_post = bool(RELATIONSHIP_POST.search(post.caption[:400]))
            seen = set()
            for item, heading in list_items(post.caption):
                found = classify(item)
                if not found:
                    continue
                kind, prompt = found
                key = prompt_key(prompt)
                if key in seen:
                    continue
                seen.add(key)
                rows.append({
                    "code": post.code, "position": len(seen), "prompt": prompt, "prompt_key": key, "kind": kind,
                    "heading": heading if kind == "chatgpt" else None,
                    "category": category_for(prompt, kind, relationship_post),
                    "extractor_version": EXTRACTOR_VERSION, "extracted_at": now,
                })

        codes = [p.code for p in posts]
        connection.execute(text("DELETE FROM clean.journal_prompts WHERE code = ANY (:codes)"), {"codes": codes})
        if rows:
            connection.execute(text("""
                INSERT INTO clean.journal_prompts
                    (code, position, prompt, prompt_key, kind, heading, category, extractor_version, extracted_at)
                VALUES (:code, :position, :prompt, :prompt_key, :kind, :heading, :category, :extractor_version, :extracted_at)
            """), rows)
        connection.commit()

    print(f"{len(rows)} prompts from {len({r['code'] for r in rows})} of {len(posts)} Journals posts with a caption")
    print("Categories: " + ", ".join(f"{c} {n}" for c, n in Counter(r["category"] for r in rows).most_common()))


if __name__ == "__main__":
    main()
