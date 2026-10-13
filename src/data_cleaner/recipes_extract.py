"""
Extract recipes from the captions of posts in recipe collections into clean.recipes.

    python -m src.data_cleaner.recipes_extract              # all posts in the recipes tab
    python -m src.data_cleaner.recipes_extract --no-labels  # skip the slower zero-shot labels

Everything runs locally: rules for ingredients/steps, the cached facebook/bart-large-mnli
zero-shot model for meal type and cuisine, keywords for diet tags.
Rows edited by hand (user_edited = true) are never overwritten.
"""
import argparse
import re
import unicodedata
from collections import Counter
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert

from src.helper.model import engine, CleanRecipe

EXTRACTOR_VERSION = "1.0"

FRACTIONS = "½⅓⅔¼¾⅕⅖⅗⅘⅙⅚⅛⅜⅝⅞"
UNITS = (
    r"cups?|c\.|tbsps?|tbs|tsps?|tablespoons?|teaspoons?|g|grams?|kg|ml|l|liters?|litres?|oz|ounces?|"
    r"lbs?|pounds?|cloves?|sticks?|cans?|pinch(?:es)?|slices?|large|small|medium|whole|handfuls?|bunch(?:es)?|"
    r"packets?|scoops?|pieces?|heads?|stalks?|sprigs?|dash(?:es)?|eggs?"
)
QUANTITY = re.compile(
    rf"^(?:\d+(?:[.,/]\d+)?(?:\s*[-–]\s*\d+)?\s*[{FRACTIONS}]?|[{FRACTIONS}]|(?:a|one|two|three|half)\s+(?:{UNITS}))",
    re.IGNORECASE,
)
HAS_UNIT = re.compile(rf"\b(?:{UNITS})\b|\d(?:g|ml|kg|oz)\b", re.IGNORECASE)
STEP_NUMBER = re.compile(r"^(?:step\s*)?\d{1,2}\s*[.)]\s+\S", re.IGNORECASE)
INGREDIENTS_HEADER = re.compile(
    r"^(?:ingredients?|what you(?:'|’)?ll need|what you need|you(?:'|’)?ll need|here(?:'|’)?s what (?:i|you) used|shopping list)\b",
    re.IGNORECASE,
)
STEPS_HEADER = re.compile(r"^(?:instructions?|directions?|method|steps?|how to make(?: it)?|preparation|recipe)\b", re.IGNORECASE)
COOKING_VERB = re.compile(
    r"^(?:add|bake|blend|boil|combine|cook|cool|fold|fry|grill|heat|knead|let|melt|mix|place|pour|preheat|"
    r"refrigerate|roast|saut[eé]|season|serve|simmer|spread|sprinkle|stir|top|transfer|whisk)\b",
    re.IGNORECASE,
)
SERVINGS = re.compile(r"\b(?:serves|servings?|makes|yield)\s*:?\s*(\d+[^\n.,;]{0,25})", re.IGNORECASE)
URL = re.compile(r"https?://[^\s)]+")
NAME_PREFIX = re.compile(r"^.*?\b(?:ep(?:isode)?\.?\s*\d+|series|part\s*\d+)\s*[:\-–]\s*", re.IGNORECASE)
NOT_A_NAME = re.compile(r"^(?:recipe|details below|ingredients?|new|repost|here|comment|check out|all recipes)\b", re.IGNORECASE)
INVISIBLE = re.compile("[\u200b-\u200f\u2060-\u2064\ufeff]")
# 'comment "BUN"', 'comment OATS', 'Comment the word ‘salmon’', 'Comment coconut and I'll send...'
COMMENT_CODE = re.compile(
    r"(?i:\bcomment)\s+(?:(?i:the word)\s+)?(?:[\"“'‘]([A-Za-z]{2,20})[\"”'’]|([A-Z]{2,20})\b|([a-z]{2,20})(?=\s+(?:and|to|for|below)\b))"
)
EXTERNAL_CUE = re.compile(r"(?i:\bcomment)\s+[\"“'‘]?[A-Za-z]+|link (?:is )?in (?:my |our |the )?bio|\bDM\b", re.IGNORECASE)

MEAL_TYPES = {
    "breakfast": "breakfast", "main dish": "main", "soup": "soup", "salad": "salad",
    "dessert or baked sweets": "dessert", "snack": "snack", "drink": "drink", "bread": "bread",
}
CUISINES = {
    "Italian": "Italian", "Spanish": "Spanish", "Mexican": "Mexican", "French": "French",
    "Greek or Mediterranean": "Mediterranean", "Middle Eastern": "Middle Eastern", "Turkish": "Turkish",
    "North African": "North African", "Indian": "Indian", "Chinese": "Chinese", "Japanese": "Japanese",
    "Korean": "Korean", "Thai": "Thai", "Vietnamese": "Vietnamese",
    "Polish or Eastern European": "Eastern European", "American": "American", "no particular": None,
}
CUISINE_MIN_SCORE = 0.25
RECIPE_KIND = ["a recipe to cook at home", "a restaurant, food market or food travel destination", "a full day of eating or meal plan"]
DIET_TAGS = {
    "vegan": r"\bvegan|plant[- ]?based|\bwfpb\b",
    "vegetarian": r"\bvegetarian\b",
    "high-protein": r"\bprotein\b",
    "gluten-free": r"gluten[- ]?free|\bgf\b",
    "dairy-free": r"dairy[- ]?free",
    "low-sugar": r"sugar[- ]?free|low[- ]?sugar|no added sugar",
    "low-carb": r"\bketo\b|low[- ]?carb",
}


def _clean_line(line):
    """Strip leading bullets/emoji and surrounding whitespace."""
    return re.sub(rf"^[^\w{FRACTIONS}(]+", "", line).strip()


def _is_hashtag_line(line):
    words = line.split()
    return bool(words) and sum(w.startswith("#") for w in words) / len(words) > 0.5


def _is_ingredient(line):
    return bool(QUANTITY.match(line)) and not STEP_NUMBER.match(line) and len(line) <= 90


def recipe_name(lines):
    for raw in lines[:3]:
        name = unicodedata.normalize("NFKC", raw)  # fancy letters (𝕊𝕦𝕔𝕔) -> plain
        name = re.sub(r"[#@][\w.]+", "", name)
        name = NAME_PREFIX.sub("", name)
        # emoji and symbols split the line; the first chunk is the title
        name = re.split(r"[^\w\s&'’,+\-()/!.:]+", name)[0] or re.sub(r"[^\w\s&'’,+\-()/!.:]+", " ", name)
        name = re.split(r"(?<=[a-z])[.!?]\s", name)[0].strip(" -–:.!,")  # first sentence
        if len(name) >= 3 and not NOT_A_NAME.match(name):
            return name[:100]
    return None


def _is_group_label(line):
    """Short line naming a part of the recipe: 'Frosting', 'For the dough:', 'for the cookies-'."""
    return (
        len(line) <= 35
        and not line.endswith((".", "!", "?"))
        and not _is_ingredient(line)
        and not SERVINGS.search(line)
        and not INGREDIENTS_HEADER.match(line)
    )


def parse_caption(caption):
    """Return ingredients, steps, servings and name found in a caption."""
    caption = INVISIBLE.sub("", caption)
    lines = [line.rstrip() for line in caption.splitlines()]
    nonblank = [line.strip() for line in lines if line.strip()]
    ingredients, steps = [], []
    section = None  # None | "ingredients" | "steps" | "recipe" (header that can hold either)
    pending_label = None  # short unused line just before an ingredient run

    for raw in lines:
        stripped = raw.strip()
        if not stripped:
            continue
        line = _clean_line(stripped)
        if _is_hashtag_line(stripped):
            section = None
            continue
        if not line or URL.search(line) or EXTERNAL_CUE.search(line) or SERVINGS.match(line):
            pending_label = None
            continue

        if len(line) < 45 and INGREDIENTS_HEADER.match(line):
            section, pending_label = "ingredients", None
            continue
        if len(line) < 45 and STEPS_HEADER.match(line):
            section = "recipe" if line.lower().startswith("recipe") else "steps"
            pending_label = None
            continue

        explicit_label = line.endswith((":", "-")) or line.lower().startswith("for the ")
        label = line.rstrip(":- ") + ":"
        if STEP_NUMBER.match(stripped) or STEP_NUMBER.match(line):
            steps.append(re.sub(r"^(?:step\s*)?\d{1,2}\s*[.)]\s*", "", line, flags=re.IGNORECASE))
            section = "steps" if section == "recipe" else section
            pending_label = None
        elif _is_ingredient(line) and (section in ("ingredients", "recipe") or HAS_UNIT.search(line)):
            if pending_label:
                ingredients.append(pending_label)
            ingredients.append(line)
            pending_label = None
        elif explicit_label and _is_group_label(line) and section in ("steps",):
            steps.append(label)
        elif explicit_label and _is_group_label(line):
            pending_label = label  # added once the ingredients under it appear
        elif section in ("ingredients", "recipe") and len(line) <= 90:
            if COOKING_VERB.match(line):
                steps.append(line)
            elif not re.match(r"^enjoy", line, re.IGNORECASE):
                ingredients.append(line)
            pending_label = None
        elif section == "steps" and len(line) <= 400:
            steps.append(line)
        else:
            if len(line) > 160:
                section = None  # long prose ends a section
            pending_label = label if _is_group_label(line) else None

    servings = SERVINGS.search(caption)
    return {
        "recipe_name": recipe_name(nonblank),
        "ingredients": ingredients,
        "steps": steps,
        "servings": servings.group(1).strip() if servings else None,
    }


def find_external(caption):
    """Where the full recipe lives when it isn't in the caption."""
    hints = []
    links = [u.rstrip(".,!") for u in URL.findall(caption) if "instagram.com" not in u]
    comment = COMMENT_CODE.search(caption)
    if comment:
        hints.append(f'Comment "{next(g for g in comment.groups() if g).upper()}"')
    if re.search(r"link (?:is )?in (?:my |our |the )?bio", caption, re.IGNORECASE):
        hints.append("Link in bio")
    dot_com = re.search(r"\b([A-Za-z]{3,})\s+DOT\s+COM\b", caption, re.IGNORECASE)
    if dot_com:
        links.append(f"https://{dot_com.group(1).lower()}.com")
    on_account = re.search(r"recipe (?:is )?(?:up )?(?:on|at)\s+(@[\w.]+)", caption, re.IGNORECASE)
    if on_account:
        hints.append(f"Recipe on {on_account.group(1)}")
    if re.search(r"meal plan|exclusive|cookbook", caption, re.IGNORECASE):
        hints.append("In a paid meal plan or cookbook")
    return (links[0] if links else None), ("; ".join(hints) or None)


def diet_tags(caption, hashtags):
    haystack = (caption + " " + " ".join(hashtags or [])).lower()
    tags = [tag for tag, pattern in DIET_TAGS.items() if re.search(pattern, haystack)]
    if "vegan" in tags and "vegetarian" in tags:
        tags.remove("vegetarian")
    return tags


def status_for(parsed, link, how_to_get):
    if len(parsed["ingredients"]) >= 2 and len(parsed["steps"]) >= 2:
        return "full"
    if len(parsed["ingredients"]) >= 3:
        return "ingredients_only"
    if link or how_to_get:
        return "external"
    return "description_only"


def load_classifier():
    from transformers import pipeline

    return pipeline("zero-shot-classification", model="facebook/bart-large-mnli")


def add_labels(classifier, rows, captions):
    for row, caption in zip(rows, captions):
        if row["status"] == "no_caption":
            continue
        sample = f"{row['recipe_name'] or ''}. {caption[:600]}"
        if row["status"] == "description_only":
            kind = classifier(sample, candidate_labels=RECIPE_KIND, hypothesis_template="This post is about {}.")
            if kind["labels"][0] != RECIPE_KIND[0] and kind["scores"][0] > 0.5:
                row["status"] = "not_a_recipe"
                row["notes"] = kind["labels"][0]
                continue
        meal = classifier(sample, candidate_labels=list(MEAL_TYPES), hypothesis_template="This recipe is a {}.")
        row["meal_type"] = MEAL_TYPES[meal["labels"][0]]
        cuisine = classifier(sample, candidate_labels=list(CUISINES), hypothesis_template="This is {} food.")
        if cuisine["scores"][0] >= CUISINE_MIN_SCORE:
            row["cuisine"] = CUISINES[cuisine["labels"][0]]


def run(labels=True, new_only=False):
    """Extract recipes; returns a one-line summary. new_only: only posts not yet in clean.recipes."""
    query = "SELECT code, caption, hashtags FROM clean.saved_posts WHERE 'recipes' = ANY (tabs)"
    if new_only:
        query += " AND code NOT IN (SELECT code FROM clean.recipes)"
    with engine.connect() as connection:
        posts = connection.execute(text(query)).all()
    if not posts:
        return "no new recipe posts"

    now = datetime.now()
    rows, captions = [], []
    for code, caption, hashtags in posts:
        row = {
            "code": code, "recipe_name": None, "servings": None, "ingredients": [], "steps": [],
            "recipe_link": None, "how_to_get": None, "meal_type": None, "cuisine": None, "diet_tags": [],
            "notes": None, "user_edited": False, "extractor_version": EXTRACTOR_VERSION, "extracted_at": now,
        }
        if not caption:
            row["status"] = "no_caption"
        else:
            row.update(parse_caption(caption))
            row["recipe_link"], row["how_to_get"] = find_external(caption)
            row["diet_tags"] = diet_tags(caption, hashtags)
            row["status"] = status_for(row, row["recipe_link"], row["how_to_get"])
        rows.append(row)
        captions.append(caption or "")

    if labels:
        print(f"Labeling {len(rows)} posts with the zero-shot model (takes a few minutes on CPU)...")
        add_labels(load_classifier(), rows, captions)

    statement = insert(CleanRecipe).values(rows)
    updatable = {c: statement.excluded[c] for c in rows[0] if c not in ("code", "user_edited")}
    statement = statement.on_conflict_do_update(
        index_elements=["code"], set_=updatable, where=CleanRecipe.user_edited.is_(False)
    )
    with engine.begin() as connection:
        connection.execute(statement)

    return f"{len(rows)} recipe posts: " + ", ".join(f"{s} {n}" for s, n in Counter(r["status"] for r in rows).most_common())


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--no-labels", action="store_true", help="skip zero-shot meal type / cuisine labels")
    parser.add_argument("--new-only", action="store_true", help="only posts not processed yet")
    args = parser.parse_args()
    print(run(labels=not args.no_labels, new_only=args.new_only))


if __name__ == "__main__":
    main()
