"""
Pull exercises, body areas and workout types out of posts in the workouts tab (clean.workouts).

    python -m src.data_cleaner.workouts_extract

Keyword rules only (fast, easy to adjust): BODY_AREAS and WORKOUT_TYPES below decide the labels.
The workouts tab covers the Workouts, Massages and Face yoga collections.
Rows edited by hand (user_edited = true) are never overwritten.
"""
import re
from collections import Counter
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert

from src.helper.model import engine, CleanWorkout

EXTRACTOR_VERSION = "1.0"

# Body area -> words that point to it. These groups are what a clickable muscle map would use.
BODY_AREAS = {
    "neck": r"neck|traps?|trapezius|scm|cervical",
    "shoulders": r"shoulders?|delts?|deltoids?|rotator cuff|face pulls?|lateral raises?|overhead press",
    "back": r"(?:upper|lower|mid)[- ]?back|back (?:pain|muscles?|workout|day|exercises?|stretch(?:es)?|\+)|"
            r"lats?|rhomboids?|rows?|pull ?downs?|pull[- ]?ups?|spine|spinal|posture|deadlifts?",
    "chest": r"chest|pecs?|push[- ]?ups?|bench press|chest press|flys?|flyes",
    "arms": r"arms?|biceps?|triceps?|forearms?|curls?|dips|wrists?",
    "core": r"core|abs|abdominals?|obliques?|belly|waist|planks?|crunch(?:es)?|sit[- ]?ups?|hollow|l[- ]?sit|dead ?bugs?",
    "glutes": r"glutes?|butt|booty|hip thrusts?|glute bridges?|kickbacks?",
    "hips": r"hips?|hip flexors?|pelvi[cs]|psoas",
    "legs": r"legs?|quads?|hamstrings?|calf|calves|thighs?|squats?|lunges?|knees?|ankles?|feet|foot",
    "face": r"face|facial|cheeks?|jaw(?:line)?|chin|forehead|eyes?|lymphatic|puffy|puffiness|gua ?sha|wrinkles?",
    "full body": r"full[- ]body|total body|whole body",
}
# Checked in order; the first match wins (collections are checked first, in main()).
WORKOUT_TYPES = [
    ("pilates", r"pilates|reformer"),
    ("yoga", r"\byoga\b|asana|vinyasa"),
    ("calisthenics", r"calisthenics|l[- ]?sit|handstand|pull[- ]?ups?|muscle[- ]?ups?"),
    ("mobility", r"mobility|stretch(?:es|ing)?|flexibility|range of motion|tension"),
    ("cardio", r"cardio|hiit|running|run\b|jump(?:ing)? rope|sprints?"),
    ("massage", r"massage|lymphatic|nerve floss|trigger point|foam roll"),
    ("strength", r"\d+\s*x\s*\d+|sets?\b|reps?\b|dumbbells?|barbell|kettlebell|weights?|lift|gym|pull day|push day|leg day"),
]
COLLECTION_TYPES = {"Massages": "massage", "Face yoga": "face"}
EQUIPMENT = {
    "dumbbell": r"dumbbells?|db\b", "barbell": r"barbell", "kettlebell": r"kettlebells?|\bkb\b",
    "cable": r"cable", "resistance band": r"bands?\b|resistance band", "mat": r"\bmat\b",
    "bench": r"bench", "chair": r"chair", "foam roller": r"foam roll", "massage gun": r"massage gun",
    "gua sha": r"gua ?sha", "ball": r"\bball\b", "pull-up bar": r"pull[- ]?up bar", "wall": r"\bwall\b",
}
EXERCISE_WORDS = re.compile(
    r"squat|lunge|deadlift|row|press|curl|plank|pull|push|bridge|thrust|raise|extension|crunch|twist|kick|"
    r"walk|stretch|pose|hold|fly|dip|step|jump|burpee|sit|rotation|circle|massage|tap|glide|slide|lift|"
    r"swing|reach|roll|bend|march|clam|hinge|sweep|pinch|stroke",
    re.IGNORECASE,
)
SETS_REPS = re.compile(
    r"\d+\s*(?:sets?|rounds?)\s*(?:of|[x×])\s*\d+(?:\s*-\s*\d+)?\s*(?:reps?|seconds?|secs?|minutes?|mins?)?"
    r"|\d+\s*reps?\s*x\s*\d+\s*times?(?: a day)?"
    r"|\d+\s*[x×]\s*\d+(?:\s*-\s*\d+)?(?!\d)",
    re.IGNORECASE,
)
KEYCAP_NUMBER = re.compile(r"^\s*(?:\d️?⃣)+\s*")   # 1️⃣ 2️⃣ ... 🔟 handled below
NUMBERED = re.compile(r"^\s*\(?\d{1,2}(?:[.)]\s*|\s+)(?=[A-Za-z])")  # "1. Squat", "(1 Press", "2 Single arm row"
LIST_MARKER = re.compile(r"^\s*(?:\d{1,2}[.)]\s+|[-•*·▪◾✔✅‼❗➡👉🔹🔸⚡]+️?\s*|🔟\s*)")
NOT_EXERCISE = re.compile(r"comment|follow|link|code|save|trial|discount|%|#|@|http", re.IGNORECASE)


def find_labels(patterns, text_):
    return [label for label, pattern in patterns.items() if re.search(rf"\b(?:{pattern})", text_, re.IGNORECASE)]


def workout_type(caption, collections):
    for collection, label in COLLECTION_TYPES.items():
        if collection in collections:
            return label
    for label, pattern in WORKOUT_TYPES:
        if re.search(pattern, caption, re.IGNORECASE):
            return label
    return None


def exercise_lines(caption):
    """List items that name an exercise: '1️⃣ 4x8 single arm bent over row', '‼️Body saw planks'."""
    exercises = []
    for raw in caption.splitlines():
        line = raw.strip()
        item = line.strip(" :-–")
        if SETS_REPS.fullmatch(item) and exercises:  # "4 sets × 12 reps" belongs to the exercise above
            exercises[-1] += f" — {item}"
            continue
        numbered = KEYCAP_NUMBER.match(line) or NUMBERED.match(line)
        marked = numbered or LIST_MARKER.match(line)
        if not marked:
            continue
        item = LIST_MARKER.sub("", NUMBERED.sub("", KEYCAP_NUMBER.sub("", line))).strip(" :-–")
        too_long = len(item) > (90 if numbered else 60)
        if not item or too_long or NOT_EXERCISE.search(item):
            continue
        if numbered or EXERCISE_WORDS.search(item) or SETS_REPS.search(item):
            exercises.append(item)
    return exercises


def title(caption):
    for raw in caption.splitlines()[:3]:
        line = re.sub(r"[#@][\w.]+", "", raw)
        line = re.sub(r"[^\w\s&'’,+\-()/!?.:]", " ", line)  # emoji
        line = re.sub(r"\s+", " ", line).strip(" -–:.,")
        line = re.split(r"(?<=[a-z])[.!?]\s", line)[0]
        if len(line) >= 4:
            return line[:100]
    return None


def extract(code, caption, collections):
    row = {
        "code": code, "title": None, "workout_type": None, "body_areas": [], "exercises": [],
        "sets_reps": None, "equipment": [], "user_edited": False,
        "extractor_version": EXTRACTOR_VERSION, "extracted_at": datetime.now(),
    }
    if not caption:
        row["status"] = "no_caption"
        return row
    sets_reps = SETS_REPS.search(caption)
    row.update({
        "title": title(caption),
        "workout_type": workout_type(caption, collections),
        "body_areas": find_labels(BODY_AREAS, caption),
        "exercises": exercise_lines(caption),
        "sets_reps": sets_reps.group(0).strip() if sets_reps else None,
        "equipment": find_labels(EQUIPMENT, caption),
    })
    if len(row["exercises"]) >= 2:
        row["status"] = "exercises"
    elif not row["body_areas"] and not row["exercises"] and not row["sets_reps"]:
        row["status"] = "no_details"  # the caption doesn't say what the workout is; probably only in the video
    elif row["workout_type"] in ("massage", "face"):
        row["status"] = "how_to"
    else:
        row["status"] = "routine"
    return row


def run():
    """Run the extraction; returns a one-line summary."""
    with engine.connect() as connection:
        posts = connection.execute(text(
            "SELECT code, caption, collections FROM clean.saved_posts WHERE 'workouts' = ANY (tabs)"
        )).all()
    rows = [extract(p.code, p.caption, p.collections) for p in posts]

    statement = insert(CleanWorkout).values(rows)
    statement = statement.on_conflict_do_update(
        index_elements=["code"],
        set_={c: statement.excluded[c] for c in rows[0] if c not in ("code", "user_edited")},
        where=CleanWorkout.user_edited.is_(False),
    )
    with engine.begin() as connection:
        connection.execute(statement)

    return f"{len(rows)} workout posts: " + ", ".join(f"{s} {n}" for s, n in Counter(r["status"] for r in rows).most_common())


def main():
    print(run())


if __name__ == "__main__":
    main()
