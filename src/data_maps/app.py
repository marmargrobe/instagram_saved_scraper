"""
Local Streamlit app for browsing saved Instagram posts.

Run from the project root (so .env is found):
    source .venv_data_maps/bin/activate
    streamlit run src/data_maps/app.py
"""
import json
import os
import random
import subprocess
import sys

# Streamlit puts this file's folder on sys.path, not the project root
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import altair as alt
import folium
import pandas as pd
from PIL import Image
import streamlit as st
from folium.plugins import MarkerCluster
from sqlalchemy import text
from streamlit_folium import st_folium

from src.helper.model import engine

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
THUMBNAIL_DIR = os.path.join(PROJECT_ROOT, "media", "thumbnails")
# The refresh needs the libraries in the cleaner venv (spaCy, transformers, selenium, ...)
CLEANER_PYTHON = os.path.join(PROJECT_ROOT, ".venv_data_cleaner", "bin", "python")
REFRESH_LOG = os.path.join(PROJECT_ROOT, "logs", "refresh.log")
DOWNLOAD_YOUR_INFORMATION = "https://accountscenter.instagram.com/info_and_permissions/dyi/"
STEP_ICONS = {"running": "⏳", "done": "✅", "skipped": "⏭️", "failed": "❌"}
POST_CODE = r"instagram\.com/(?:reel|p|tv)/([^/?#]+)"

st.set_page_config(page_title="Saved Instagram", page_icon="📍", layout="wide")


@st.cache_data(ttl=600)
def load_posts():
    posts = pd.read_sql(
        text("""
            SELECT r.id, r.code, r.product_type, r.taken_at, r.caption_text, r.hashtags,
                   r.lat, r.lng, r.city, r.location_name, r.locations_from_caption,
                   r.like_count, r.play_count, u.username, u.full_name
            FROM clean.insta_saved_reels r
            LEFT JOIN clean.insta_user u ON u.id = r.user_pk
        """),
        engine,
    )
    kind = posts["product_type"].eq("clips").map({True: "reel", False: "p"})
    posts["url"] = "https://www.instagram.com/" + kind + "/" + posts["code"] + "/"
    posts["hashtags"] = posts["hashtags"].apply(lambda tags: tags or [])
    posts["locations_from_caption"] = posts["locations_from_caption"].apply(lambda places: places or [])
    posts["caption_text"] = posts["caption_text"].fillna("").replace("None", "")

    # Collection names come from the Instagram export; match them to posts by shortcode
    saves = load_saves()
    in_collections = saves.dropna(subset=["collection_name"]).groupby("code")["collection_name"].agg(
        lambda names: sorted(set(names))
    )
    posts["collections"] = posts["code"].map(in_collections).apply(lambda names: names if isinstance(names, list) else [])
    return posts


@st.cache_data(ttl=600)
def load_saves():
    saves = pd.read_sql(
        text("SELECT reel_url, collection_name, user_name, added_time, insta_account FROM rawstd.insta_download_saved_reels"),
        engine,
    )
    saves["code"] = saves["reel_url"].str.extract(POST_CODE, expand=False)
    return saves


RECIPE_STATUS = {
    "full": "Full recipe",
    "ingredients_only": "Ingredients",
    "external": "Recipe elsewhere",
    "description_only": "Name only",
    "not_a_recipe": "Not a recipe",
    "no_caption": "No caption",
}


@st.cache_data(ttl=600)
def load_recipes():
    recipes = pd.read_sql(
        text("""
            SELECT r.*, p.url, p.owner_username, p.caption, p.first_saved_at
            FROM clean.recipes r
            JOIN clean.saved_posts p USING (code)
            ORDER BY p.first_saved_at DESC NULLS LAST
        """),
        engine,
    )
    recipes = recipes.astype(object).where(recipes.notna(), None)  # NaN -> None so blanks stay blank
    for column in ("ingredients", "steps", "diet_tags"):
        recipes[column] = recipes[column].apply(lambda values: values or [])
    return recipes


@st.cache_data
def thumbnail(code, ratio=4 / 5):
    """Cached cover image cropped to width/height = ratio, or None."""
    path = os.path.join(THUMBNAIL_DIR, f"{code}.jpg")
    if not os.path.exists(path):
        return None
    image = Image.open(path)
    width, height = image.size
    if width / height < ratio:  # too tall: keep the middle
        new_height = int(width / ratio)
        top = (height - new_height) // 2
        image = image.crop((0, top, width, top + new_height))
    image.thumbnail((600, 750))
    return image


def removed_from_instagram(code):
    return os.path.exists(os.path.join(THUMBNAIL_DIR, f"{code}.removed"))


def show_recipe(recipe):
    with st.container(border=True):
        picture = thumbnail(recipe.code)
        if picture is not None:
            st.image(picture, width="stretch")
        elif removed_from_instagram(recipe.code):
            st.caption("🚫 No picture: removed from Instagram, or embedding turned off")
        st.markdown(f"**{recipe.recipe_name or 'Untitled'}**")
        badges = [RECIPE_STATUS[recipe.status], recipe.meal_type, recipe.cuisine, *recipe.diet_tags]
        st.caption(" · ".join(b for b in badges if b) + (f"  \n@{recipe.owner_username}" if recipe.owner_username else ""))
        if recipe.servings:
            st.write(f"Serves {recipe.servings}")
        if recipe.ingredients or recipe.steps:
            with st.expander(f"{len([i for i in recipe.ingredients if not i.endswith(':')])} ingredients · {len(recipe.steps)} steps"):
                if recipe.ingredients:
                    st.markdown("\n".join(f"**{i}**" if i.endswith(":") else f"- {i}" for i in recipe.ingredients))
                if recipe.steps:
                    st.markdown("**Steps**")
                    number = 0
                    lines = []
                    for step in recipe.steps:
                        if step.endswith(":"):
                            lines.append(f"\n**{step}**\n")
                        else:
                            number += 1
                            lines.append(f"{number}. {step}")
                    st.markdown("\n".join(lines))
        if recipe.how_to_get:
            st.write(f"To get it: {recipe.how_to_get}")
        links = [f"[Instagram post]({recipe.url})"] + ([f"[Recipe link]({recipe.recipe_link})"] if recipe.recipe_link else [])
        st.markdown(" · ".join(links))
        with st.expander("Caption"):
            st.text(recipe.caption or "")


PLACE_STYLE = {  # place type -> (marker color, Font Awesome 4 icon)
    "café": ("beige", "coffee"), "restaurant": ("red", "cutlery"), "bar": ("darkred", "glass"),
    "hike/trail": ("darkgreen", "tree"), "park": ("green", "leaf"), "mountain": ("gray", "area-chart"),
    "beach": ("orange", "sun-o"), "waterfall": ("blue", "tint"), "lake/water": ("lightblue", "tint"),
    "nature": ("lightgreen", "leaf"), "viewpoint": ("purple", "binoculars"), "landmark": ("darkpurple", "university"),
    "museum": ("cadetblue", "university"), "attraction": ("pink", "star"), "shop": ("lightred", "shopping-bag"),
    "stay": ("darkblue", "bed"), "island": ("orange", "life-ring"), "city/town": ("lightgray", "building"),
    "region": ("lightgray", "globe"), "other": ("lightgray", "map-marker"),
}
BROAD_PLACES = {"city/town", "region"}


@st.cache_data(ttl=600)
def load_places():
    """All located place candidates, with my corrections (clean.travel_place_choices) applied.
    Returns (places on the map, every located candidate)."""
    candidates = pd.read_sql(
        text("""
            SELECT t.id, t.code, t.name, t.source, t.rank, t.lat, t.lng, t.matched_name, t.city, t.region,
                   t.country, t.place_type, t.is_primary, t.on_map, p.url, p.owner_username, p.caption,
                   p.collections, c.chosen_name, c.chosen_source, c.place_type AS chosen_type,
                   coalesce(c.hidden, false) AS hidden
            FROM clean.travel_places t
            JOIN clean.saved_posts p USING (code)
            LEFT JOIN clean.travel_place_choices c USING (code)
            WHERE t.lat IS NOT NULL
        """),
        engine,
    )
    candidates = candidates.astype(object).where(candidates.notna(), None)
    candidates["lat"] = candidates["lat"].astype(float)
    candidates["lng"] = candidates["lng"].astype(float)
    candidates["place_type"] = candidates.apply(lambda c: c.chosen_type or c.place_type or "other", axis=1)
    # OpenStreetMap's name merges spellings ("Sequoia NP" / "Sequoia National Park")
    candidates["label"] = candidates.apply(lambda c: (c.matched_name or c["name"]).split(",")[0].strip(), axis=1)
    candidates["area"] = candidates.apply(lambda c: ", ".join(x for x in (c.city, c.region, c.country) if x), axis=1)

    chosen = candidates["chosen_name"].notna()
    is_choice = (candidates["name"] == candidates["chosen_name"]) & (candidates["source"] == candidates["chosen_source"])
    on_map = (chosen & is_choice) | (~chosen & candidates["on_map"].astype(bool))
    places = candidates[on_map & ~candidates["hidden"].astype(bool)]
    return places, candidates


def save_choice(code, chosen_name, chosen_source, place_type, hidden):
    with engine.begin() as connection:
        connection.execute(
            text("""
                INSERT INTO clean.travel_place_choices (code, chosen_name, chosen_source, place_type, hidden, updated_at)
                VALUES (:code, :name, :source, :type, :hidden, now())
                ON CONFLICT (code) DO UPDATE SET chosen_name = :name, chosen_source = :source,
                    place_type = :type, hidden = :hidden, updated_at = now()
            """),
            {"code": code, "name": chosen_name, "source": chosen_source, "type": place_type, "hidden": hidden},
        )
    load_places.clear()


def fix_place_form(place, options):
    """Pick another candidate, change the type, or hide the post."""
    with st.expander("✏️ Fix this place"):
        with st.form(f"fix_{place.code}", border=False):
            labels = [f"{o.label} ({o.source}) · {o.area}" for o in options.itertuples()]
            current = next((i for i, o in enumerate(options.itertuples()) if o.id == place.id), 0)
            picked = st.selectbox("Place", range(len(labels)), index=current, format_func=labels.__getitem__)
            types = [t for t in PLACE_STYLE if t != "other"]
            new_type = st.selectbox("Type", types, index=types.index(place.place_type) if place.place_type in types else 0)
            hidden = st.checkbox("Not a place — hide from the map")
            if st.form_submit_button("Save"):
                option = options.iloc[picked]
                save_choice(place.code, option["name"], option["source"], new_type, hidden)
                st.rerun()


def show_place(place, options):
    with st.container(border=True):
        picture = thumbnail(place.code)
        if picture is not None:
            st.image(picture, width="stretch")
        elif removed_from_instagram(place.code):
            st.caption("🚫 No picture: removed from Instagram, or embedding turned off")
        st.markdown(f"**{place.label}**")
        st.caption(" · ".join(x for x in (place.place_type, place.area) if x)
                   + (f"  \n@{place.owner_username}" if place.owner_username else ""))
        st.markdown(f"[Instagram post]({place.url})")
        with st.expander("Caption"):
            st.text(place.caption or "")
        fix_place_form(place, options)


def bar_chart(counts, label):
    data = counts.rename_axis(label).reset_index(name="posts")
    chart = alt.Chart(data).mark_bar().encode(
        x=alt.X("posts:Q", title="Posts"), y=alt.Y(f"{label}:N", sort="-x", title=None), tooltip=[label, "posts"]
    )
    st.altair_chart(chart, width="stretch")


@st.cache_data(ttl=600)
def load_watch_read():
    """Titles found in Watch / read posts (with my watched/hidden choices), and posts with no title."""
    titles = pd.read_sql(
        text("""
            SELECT w.*, p.url, p.owner_username, p.caption, p.collections,
                   coalesce(w.imdb_id, 'book:' || coalesce(w.openlibrary_key, w.matched_title)) AS item_key,
                   coalesce(c.watched, false) AS watched, coalesce(c.hidden, false) AS hidden
            FROM clean.watch_read_titles w
            JOIN clean.saved_posts p USING (code)
            LEFT JOIN clean.watch_read_choices c
                   ON c.item_key = coalesce(w.imdb_id, 'book:' || coalesce(w.openlibrary_key, w.matched_title))
            ORDER BY w.is_primary DESC, w.votes DESC NULLS LAST
        """),
        engine,
    )
    titles = titles.astype(object).where(titles.notna(), None)
    titles["genres"] = titles["genres"].apply(lambda g: g or [])
    titles = titles.drop_duplicates("item_key")  # the same film saved twice shows once
    no_title = pd.read_sql(
        text("""
            SELECT p.code, p.url, p.owner_username, p.caption, p.collections
            FROM clean.saved_posts p
            WHERE 'watch_read' = ANY (p.tabs)
              AND NOT EXISTS (SELECT 1 FROM clean.watch_read_titles w WHERE w.code = p.code)
        """),
        engine,
    )
    no_title = no_title.astype(object).where(no_title.notna(), None)
    return titles, no_title


def save_watch_choice(item_key, watched, hidden):
    with engine.begin() as connection:
        connection.execute(
            text("""
                INSERT INTO clean.watch_read_choices (item_key, watched, hidden, updated_at)
                VALUES (:key, :watched, :hidden, now())
                ON CONFLICT (item_key) DO UPDATE SET watched = :watched, hidden = :hidden, updated_at = now()
            """),
            {"key": item_key, "watched": watched, "hidden": hidden},
        )
    load_watch_read.clear()


def show_title(item, key_prefix=""):
    with st.container(border=True):
        picture = thumbnail(item.code)
        if picture is not None:
            st.image(picture, width="stretch")
        year = f" ({item.year})" if item.year else ""
        st.markdown(f"**{item.matched_title}{year}**" + (" ✅" if item.watched else ""))
        details = [item.kind, ", ".join(item.genres)]
        if item.rating:
            details.append(f"⭐ {item.rating}")
        if item.runtime_minutes:
            details.append(f"{item.runtime_minutes} min")
        if item.author:
            details.append(f"by {item.author}")
        st.caption(" · ".join(d for d in details if d))
        links = [f"[Instagram post]({item.url})"]
        if item.imdb_id:
            links.append(f"[IMDb](https://www.imdb.com/title/{item.imdb_id}/)")
        if item.openlibrary_key:
            links.append(f"[Open Library](https://openlibrary.org{item.openlibrary_key})")
        st.markdown(" · ".join(links))
        left, right = st.columns(2)
        if left.button("↩️ Not watched" if item.watched else "✅ Watched", key=f"{key_prefix}watched_{item.item_key}"):
            save_watch_choice(item.item_key, not item.watched, item.hidden)
            st.rerun()
        if right.button("🙈 Not interested", key=f"{key_prefix}hide_{item.item_key}"):
            save_watch_choice(item.item_key, item.watched, True)
            st.rerun()


BODY_AREA_ORDER = ["neck", "shoulders", "back", "chest", "arms", "core", "glutes", "hips", "legs", "face", "full body"]
# Areas the body drawing can't show -> (body areas in clean.workouts, muscles in reference.exercises)
OFF_MAP = {
    "neck": (["neck"], ["neck"]),
    "face": (["face"], []),
    "forearms": (["arms"], ["forearms"]),
    "lower back": (["back"], ["lower back"]),
    "inner thighs": (["legs", "hips"], ["adductors"]),
    "outer thighs": (["legs", "hips"], ["abductors"]),
    "hips": (["hips"], ["adductors", "abductors"]),
    "full body": (["full body"], []),
}
EXERCISE_IMAGE_BASE = "https://raw.githubusercontent.com/yuhonas/free-exercise-db/f00c92c7dcf1216a928a52c3706c7ce8e2f71ed5/exercises/"
EXERCISES_PER_PAGE = 12

# Clickable body map (assets built by src/data_maps/build_muscle_map.py from wger.de drawings, AGPL-3.0)
ASSETS_DIR = os.path.join(os.path.dirname(__file__), "assets")
with open(os.path.join(ASSETS_DIR, "muscle_map.json")) as _file:
    MUSCLES = json.load(_file)  # muscle id -> {"label", "areas" (post body areas), "exercise_muscles"}
with open(os.path.join(ASSETS_DIR, "muscle_map_front.svg"), encoding="utf-8") as _front, \
        open(os.path.join(ASSETS_DIR, "muscle_map_back.svg"), encoding="utf-8") as _back:
    BODY_MAP_HTML = (
        f'<div class="bodymap"><figure>{_front.read()}<figcaption>Front</figcaption></figure>'
        f'<figure>{_back.read()}<figcaption>Back</figcaption></figure></div>'
    )
BODY_MAP_CSS = """
.bodymap { display: flex; gap: 12px; justify-content: center; }
.bodymap figure { margin: 0; text-align: center; }
.bodymap svg { height: 340px; width: auto; }
.bodymap figcaption { font: 12px sans-serif; color: #888; }
.muscle path { fill: var(--shade, #eadbd6); opacity: 0.9 !important; cursor: pointer; transition: fill 0.15s; }
.muscle:hover path { fill: #f4a261; }
.muscle.selected path { fill: #e4572e; }
"""
BODY_MAP_JS = """
function shade(count, max) {
    if (!count) return "#eadbd6";
    const t = Math.min(1, count / Math.max(1, max));   // more saved workouts = darker
    const mix = (a, b) => Math.round(a + (b - a) * t);
    return `rgb(${mix(242, 168)}, ${mix(206, 92)}, ${mix(196, 80)})`;
}
export default function (component) {
    const { setStateValue, parentElement, data } = component;
    // The drawing owns the selection: keep it on the component so redraws don't reset it
    const host = parentElement.host || parentElement;
    if (!host.__selected) host.__selected = new Set(data.selected || []);
    const selected = host.__selected;
    parentElement.querySelectorAll(".muscle").forEach((muscle) => {
        const key = muscle.dataset.muscle;
        const count = data.counts[key] || 0;
        muscle.style.setProperty("--shade", shade(count, data.max));
        muscle.querySelector("title").textContent = `${data.labels[key]} · ${count} saved`;
        muscle.classList.toggle("selected", selected.has(key));
        muscle.onclick = () => {
            selected.has(key) ? selected.delete(key) : selected.add(key);
            muscle.classList.toggle("selected", selected.has(key));
            setStateValue("selected", [...selected]);
        };
    });
}
"""
body_map_component = st.components.v2.component("body_map", html=BODY_MAP_HTML, css=BODY_MAP_CSS, js=BODY_MAP_JS)


def body_map(workouts, key="body_map"):
    """Clickable front/back body; returns the selected muscle ids."""
    counts = {
        muscle: int(workouts["body_areas"].apply(lambda areas: bool(set(areas) & set(info["areas"]))).sum())
        for muscle, info in MUSCLES.items()
    }
    selected = (st.session_state.get(key) or {}).get("selected", [])  # only used when the drawing first appears
    data = {"counts": counts, "max": max(counts.values()), "selected": selected,
            "labels": {m: info["label"] for m, info in MUSCLES.items()}}
    result = body_map_component(data=data, default={"selected": []}, key=key, on_selected_change=lambda: None)
    return sorted(getattr(result, "selected", None) or [])
WORKOUT_STATUS = {
    "exercises": "Exercise list",
    "routine": "Routine / tip",
    "how_to": "How-to",
    "no_details": "No details in caption",
    "no_caption": "No caption",
}


@st.cache_data(ttl=600)
def load_workouts():
    workouts = pd.read_sql(
        text("""
            SELECT w.*, p.url, p.owner_username, p.caption, p.collections, p.first_saved_at
            FROM clean.workouts w
            JOIN clean.saved_posts p USING (code)
            ORDER BY cardinality(w.exercises) DESC, p.first_saved_at DESC NULLS LAST
        """),
        engine,
    )
    workouts = workouts.astype(object).where(workouts.notna(), None)
    for column in ("body_areas", "exercises", "equipment", "collections"):
        workouts[column] = workouts[column].apply(lambda values: values or [])
    return workouts


@st.cache_data(ttl=3600)
def load_exercises(exercise_muscles):
    """Exercises from reference.exercises whose primary muscles overlap the given ones, easiest first."""
    exercises = pd.read_sql(
        text("""
            SELECT id, name, level, category, equipment, force, mechanic,
                   primary_muscles, secondary_muscles, instructions, images
            FROM reference.exercises
            WHERE primary_muscles && CAST(:muscles AS TEXT[])
            ORDER BY array_position(ARRAY['beginner', 'intermediate', 'expert'], level), name
        """),
        engine,
        params={"muscles": list(exercise_muscles)},
    )
    return exercises.astype(object).where(exercises.notna(), None)


def show_exercise(exercise):
    with st.container(border=True):
        if exercise.images:
            st.image(EXERCISE_IMAGE_BASE + exercise.images[0], width="stretch")  # start position
        st.markdown(f"**{exercise.name}**")
        st.caption(" · ".join(x for x in (exercise.level, exercise.equipment, exercise.category) if x))
        muscles = ", ".join(exercise.primary_muscles)
        if exercise.secondary_muscles:
            muscles += f" (also {', '.join(exercise.secondary_muscles)})"
        st.caption(f"Muscles: {muscles}")
        with st.expander("How to do it"):
            if len(exercise.images) > 1:
                st.image(EXERCISE_IMAGE_BASE + exercise.images[1], caption="End position", width="stretch")
            st.markdown("\n".join(f"{i}. {step}" for i, step in enumerate(exercise.instructions, 1)))


def more_exercises(selection, exercise_muscles):
    """'Load more exercises' for the selected muscles and areas (free-exercise-db, public domain)."""
    exercise_muscles = sorted(set(exercise_muscles))
    if not exercise_muscles:
        return
    selection = ",".join(sorted(selection))
    if st.session_state.get("exercises_for") != selection:  # new selection: start collapsed again
        st.session_state["exercises_for"] = selection
        st.session_state["exercise_count"] = 0
    if st.session_state["exercise_count"] == 0:
        if st.button("💪 Load more exercises", type="primary"):
            st.session_state["exercise_count"] = EXERCISES_PER_PAGE
            st.rerun()
        return

    st.subheader("More exercises")
    st.caption(f"From the free exercise database for: {', '.join(exercise_muscles)}")
    exercises = load_exercises(tuple(exercise_muscles))
    filters = st.columns(3)
    levels = filters[0].multiselect("Level", ["beginner", "intermediate", "expert"])
    equipment = filters[1].multiselect("Equipment", sorted(exercises["equipment"].dropna().unique()))
    categories = filters[2].multiselect("Type", sorted(exercises["category"].dropna().unique()))
    if levels:
        exercises = exercises[exercises["level"].isin(levels)]
    if equipment:
        exercises = exercises[exercises["equipment"].isin(equipment)]
    if categories:
        exercises = exercises[exercises["category"].isin(categories)]

    count = st.session_state["exercise_count"]
    st.write(f"Showing {min(count, len(exercises))} of {len(exercises)} exercises")
    columns = st.columns(3)
    for i, exercise in enumerate(exercises.head(count).itertuples()):
        with columns[i % 3]:
            show_exercise(exercise)
    if count < len(exercises) and st.button("Load more"):
        st.session_state["exercise_count"] = count + EXERCISES_PER_PAGE
        st.rerun()


def show_workout(workout):
    with st.container(border=True):
        picture = thumbnail(workout.code)
        if picture is not None:
            st.image(picture, width="stretch")
        elif removed_from_instagram(workout.code):
            st.caption("🚫 No picture: removed from Instagram, or embedding turned off")
        st.markdown(f"**{workout.title or 'Untitled'}**")
        st.caption(" · ".join(x for x in [workout.workout_type, ", ".join(workout.body_areas)] if x)
                   + (f"  \n@{workout.owner_username}" if workout.owner_username else ""))
        if workout.exercises:
            with st.expander(f"{len(workout.exercises)} exercises"):
                st.markdown("\n".join(f"{i}. {e}" for i, e in enumerate(workout.exercises, 1)))
        elif workout.sets_reps:
            st.write(workout.sets_reps)
        if workout.equipment:
            st.caption("Equipment: " + ", ".join(workout.equipment))
        st.markdown(f"[Instagram post]({workout.url})")
        with st.expander("Caption"):
            st.text(workout.caption or "")


@st.cache_data(ttl=600)
def load_prompts():
    prompts = pd.read_sql(
        text("""
            SELECT j.id, j.code, j.position, j.prompt, j.prompt_key, j.kind, j.heading,
                   coalesce(c.category, j.category) AS category,
                   coalesce(c.favorite, false) AS favorite, coalesce(c.used, false) AS used,
                   coalesce(c.hidden, false) AS hidden, p.url, p.owner_username
            FROM clean.journal_prompts j
            JOIN clean.saved_posts p USING (code)
            LEFT JOIN clean.journal_prompt_choices c USING (prompt_key)
            ORDER BY j.code, j.position
        """),
        engine,
    )
    prompts = prompts.astype(object).where(prompts.notna(), None)
    for column in ("favorite", "used", "hidden"):
        prompts[column] = prompts[column].astype(bool)
    return prompts.drop_duplicates("prompt_key")


def save_prompt_choice(prompt, **changes):
    values = {"category": prompt.category, "favorite": prompt.favorite, "used": prompt.used,
              "hidden": prompt.hidden, **changes, "key": prompt.prompt_key}
    with engine.begin() as connection:
        connection.execute(
            text("""
                INSERT INTO clean.journal_prompt_choices (prompt_key, category, favorite, used, hidden, updated_at)
                VALUES (:key, :category, :favorite, :used, :hidden, now())
                ON CONFLICT (prompt_key) DO UPDATE SET category = :category, favorite = :favorite,
                    used = :used, hidden = :hidden, updated_at = now()
            """),
            values,
        )
    load_prompts.clear()


@st.cache_data(ttl=600)
def load_entries():
    """My journal entries (personal.journal_entries), newest first."""
    entries = pd.read_sql(
        text("""
            SELECT id, prompt_key, prompt_text, body, written_at, updated_at
            FROM personal.journal_entries
            ORDER BY written_at DESC
        """),
        engine,
    )
    return entries.astype(object).where(entries.notna(), None)


def save_entry(prompt, body):
    """Add a reply to a prompt and mark the prompt as used."""
    with engine.begin() as connection:
        connection.execute(
            text("INSERT INTO personal.journal_entries (prompt_key, prompt_text, body) VALUES (:key, :prompt, :body)"),
            {"key": prompt.prompt_key, "prompt": prompt.prompt, "body": body.strip()},
        )
    if not prompt.used:
        save_prompt_choice(prompt, used=True)
    load_entries.clear()


def update_entry(entry_id, body):
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE personal.journal_entries SET body = :body, updated_at = now() WHERE id = :id"),
            {"body": body.strip(), "id": entry_id},
        )
    load_entries.clear()


def show_entry(entry, with_prompt=False):
    edited = f" · edited {entry.updated_at:%b %d}" if entry.updated_at else ""
    st.caption(f"{entry.written_at:%a, %b %d, %Y · %I:%M %p}{edited}")
    if with_prompt:
        st.markdown(f"*{entry.prompt_text}*")
    st.markdown(entry.body.replace("\n", "  \n"))
    with st.popover("Edit", type="tertiary"):
        with st.form(f"edit_entry_{entry.id}", border=False):
            body = st.text_area("Your reply", value=entry.body, height=200, label_visibility="collapsed")
            if st.form_submit_button("Save changes") and body.strip():
                update_entry(entry.id, body)
                st.rerun()


def show_prompt(prompt, categories, replies):
    with st.container(border=True):
        text_col, actions = st.columns([5, 3])
        heading = f"**{prompt.heading}** · " if prompt.heading else ""
        text_col.markdown(heading + prompt.prompt + (" ⭐" if prompt.favorite else "") + (" ☑️" if prompt.used else ""))
        text_col.caption(f"[@{prompt.owner_username or 'post'}]({prompt.url})")
        buttons = actions.columns(3)
        if buttons[0].button("⭐", key=f"fav_{prompt.prompt_key}", help="Favorite"):
            save_prompt_choice(prompt, favorite=not prompt.favorite)
            st.rerun()
        if buttons[1].button("☑️", key=f"used_{prompt.prompt_key}", help="Mark as used / not used"):
            save_prompt_choice(prompt, used=not prompt.used)
            st.rerun()
        if buttons[2].button("🙈", key=f"hide_{prompt.prompt_key}", help="Hide"):
            save_prompt_choice(prompt, hidden=True)
            st.rerun()
        new_category = actions.selectbox(
            "Category", categories, index=categories.index(prompt.category) if prompt.category in categories else None,
            key=f"cat_{prompt.prompt_key}", label_visibility="collapsed", accept_new_options=True,
            placeholder="Category (or type a new one)",
        )
        if new_category and new_category != prompt.category:
            save_prompt_choice(prompt, category=new_category)
            st.rerun()

        write, history = st.columns(2)
        with write.expander("✍️ Write"):
            with st.form(f"write_{prompt.prompt_key}", border=False, clear_on_submit=True):
                body = st.text_area("Your reply", height=180, label_visibility="collapsed",
                                    placeholder="Write your reply…")
                if st.form_submit_button("Save") and body.strip():
                    save_entry(prompt, body)
                    st.toast("Saved to your journal ✍️")
                    st.rerun()
        if len(replies):
            with history.expander(f"📖 {len(replies)} {'reply' if len(replies) == 1 else 'replies'}"):
                for entry in replies.itertuples():
                    show_entry(entry)


def latest_run():
    """Steps of the most recent refresh, and when the last refresh finished."""
    with engine.connect() as connection:
        steps = connection.execute(text("""
            SELECT step, status, summary, error, started_at, finished_at FROM ops.pipeline_runs
            WHERE run_id = (SELECT run_id FROM ops.pipeline_runs ORDER BY started_at DESC LIMIT 1)
            ORDER BY id
        """)).mappings().all()
        last_finished = connection.execute(text("""
            SELECT max(finished_at) FROM ops.pipeline_runs
            WHERE run_id IN (SELECT run_id FROM ops.pipeline_runs GROUP BY run_id
                             HAVING bool_and(status <> 'running'))
        """)).scalar()
    return steps, last_finished


def start_refresh():
    os.makedirs(os.path.dirname(REFRESH_LOG), exist_ok=True)
    with open(REFRESH_LOG, "a") as log:
        subprocess.Popen(
            [CLEANER_PYTHON, "-W", "ignore", "-m", "src.pipeline.refresh", "--triggered-by", "app"],
            cwd=PROJECT_ROOT, stdout=log, stderr=subprocess.STDOUT,
            start_new_session=True,  # keeps running even if the app reloads
        )
    st.session_state["refresh_started"] = True


def refresh_panel():
    steps, last_finished = latest_run()
    running = any(s["status"] == "running" for s in steps) or (
        st.session_state.get("refresh_started") and not steps
    )

    @st.fragment(run_every=3 if running else None)
    def progress():
        steps, last_finished = latest_run()
        still_running = any(s["status"] == "running" for s in steps)
        if st.session_state.get("refresh_started") and steps and not still_running:
            st.session_state["refresh_started"] = False
            st.cache_data.clear()  # show the new data in every tab
            st.rerun()
        st.caption(f"Last updated: {last_finished:%b %d, %I:%M %p}" if last_finished else "Not refreshed yet")
        if st.button("🔄 Update now", disabled=still_running, width="stretch"):
            start_refresh()
            st.rerun()
        if steps and (still_running or st.session_state.get("show_last_run")):
            for s in steps:
                st.caption(f"{STEP_ICONS.get(s['status'], '·')} {s['step']}: {s['summary'] or s['error'] or ''}"[:120])
        elif steps:
            failed = [s["step"] for s in steps if s["status"] == "failed"]
            if failed:
                st.error(f"Last refresh failed at: {', '.join(failed)}")
            if st.button("Show last run", type="tertiary"):
                st.session_state["show_last_run"] = True
                st.rerun()

    progress()


def request_export_panel():
    with engine.connect() as connection:
        newest = connection.execute(text("""
            SELECT insta_account, max(added_time) FROM rawstd.insta_download_saved_reels
            GROUP BY insta_account ORDER BY insta_account
        """)).all()
    with st.expander("📥 Request a new Instagram export"):
        st.markdown("Request these date ranges (since the newest save already loaded):")
        for account, latest in newest:
            st.markdown(f"- **{account}**: {latest:%b %d, %Y} → today" if latest else f"- **{account}**: all time")
        st.link_button("Open Instagram › Download your information", DOWNLOAD_YOUR_INFORMATION, width="stretch")
        st.markdown(
            "1. **Download or transfer information** → choose the account\n"
            "2. **Some of your information** → **Saved** (under Your Instagram activity)\n"
            "3. **Download to device** → date range above, format **HTML**\n"
            "4. When the email arrives, download the zip to **~/Downloads** and press **🔄 Update now**"
        )


def matches(post, query):
    haystack = " ".join(
        [post["caption_text"], post["username"] or "", post["location_name"] or "", post["city"] or ""]
        + post["hashtags"] + post["collections"] + post["locations_from_caption"]
    ).lower()
    return query.lower() in haystack


posts = load_posts()
saves = load_saves()

st.title("📍 Saved Instagram")
st.caption(
    f"{len(posts):,} posts with full details · {posts['lat'].notna().sum():,} with a location · "
    f"{saves['code'].nunique():,} saves in your Instagram exports"
)

with st.sidebar:
    st.header("Data")
    refresh_panel()
    request_export_panel()
    st.divider()
    st.header("Browse filters")
    query = st.text_input("Search", placeholder="caption, @user, place, #tag, collection")
    all_collections = sorted({name for names in posts["collections"] for name in names})
    picked_collections = st.multiselect("Collections", all_collections)
    tag_counts = pd.Series([tag.lower() for tags in posts["hashtags"] for tag in tags]).value_counts()
    picked_tags = st.multiselect("Hashtags", tag_counts.index[:200], format_func=lambda t: f"#{t} ({tag_counts[t]})")
    only_located = st.toggle("Only posts with a location", value=False)

filtered = posts
if query:
    filtered = filtered[filtered.apply(matches, axis=1, query=query)]
if picked_collections:
    filtered = filtered[filtered["collections"].apply(lambda names: bool(set(names) & set(picked_collections)))]
if picked_tags:
    filtered = filtered[filtered["hashtags"].apply(lambda tags: bool({t.lower() for t in tags} & set(picked_tags)))]
if only_located:
    filtered = filtered[filtered["lat"].notna()]

recipes_tab, travel_tab, watch_tab, workouts_tab, journal_tab, browse_tab, export_tab = st.tabs(
    ["Recipes", "Travel", "Watch / read", "Workouts", "Journal prompts", "Browse", "Instagram export"]
)

with recipes_tab:
    recipes = load_recipes()
    filters = st.columns([2, 1, 1, 1])
    recipe_query = filters[0].text_input("Search recipes", placeholder="name, ingredient, @user")
    meal_types = filters[1].multiselect("Meal type", sorted(recipes["meal_type"].dropna().unique()))
    cuisines = filters[2].multiselect("Cuisine", sorted(recipes["cuisine"].dropna().unique()))
    diets = filters[3].multiselect("Diet", sorted({tag for tags in recipes["diet_tags"] for tag in tags}))
    statuses = st.pills(
        "Show", list(RECIPE_STATUS), format_func=RECIPE_STATUS.get, selection_mode="multi",
        default=["full", "ingredients_only", "external", "description_only"],
    )

    shown = recipes[recipes["status"].isin(statuses or list(RECIPE_STATUS))]
    if recipe_query:
        q = recipe_query.lower()
        shown = shown[shown.apply(
            lambda r: q in " ".join([r.recipe_name or "", r.owner_username or "", " ".join(r.ingredients)]).lower(), axis=1
        )]
    if meal_types:
        shown = shown[shown["meal_type"].isin(meal_types)]
    if cuisines:
        shown = shown[shown["cuisine"].isin(cuisines)]
    if diets:
        shown = shown[shown["diet_tags"].apply(lambda tags: bool(set(tags) & set(diets)))]

    st.write(f"{len(shown)} of {len(recipes)} recipe posts")
    columns = st.columns(3)
    for i, recipe in enumerate(shown.itertuples()):
        with columns[i % 3]:
            show_recipe(recipe)

with travel_tab:
    places, candidates = load_places()
    if places.empty:
        st.info("No places yet. Run `python -m src.data_cleaner.travel_extract`.")
    else:
        filters = st.columns([2, 2, 2, 1])
        travel_query = filters[0].text_input("Search places", placeholder="place, city, country, @user")
        travel_collections = filters[1].multiselect(
            "Collections", sorted({c for names in places["collections"] for c in names})
        )
        place_types = filters[2].multiselect("Place type", sorted(places["place_type"].unique()))
        specific_only = filters[3].toggle(
            "Specific places only", value=True, help="Hide posts only placed at a city, state or country"
        )

        shown = places
        if specific_only:
            shown = shown[~shown["place_type"].isin(BROAD_PLACES)]
        if travel_query:
            q = travel_query.lower()
            shown = shown[shown.apply(
                lambda p: q in " ".join([p["label"], p["name"], p["area"], p["owner_username"] or ""]).lower(), axis=1
            )]
        if travel_collections:
            shown = shown[shown["collections"].apply(lambda names: bool(set(names) & set(travel_collections)))]
        if place_types:
            shown = shown[shown["place_type"].isin(place_types)]

        st.write(f"{shown['code'].nunique():,} posts · {len(shown):,} places")
        if shown.empty:
            st.info("No places match these filters.")
        else:
            fmap = folium.Map(location=[shown["lat"].mean(), shown["lng"].mean()], zoom_start=3, tiles="OpenStreetMap")
            cluster = MarkerCluster().add_to(fmap)
            for place in shown.itertuples():
                color, icon = PLACE_STYLE.get(place.place_type, PLACE_STYLE["other"])
                popup = (
                    f"<b>{place.label}</b><br>{place.place_type}<br>{place.area}<br>"
                    f"@{place.owner_username or ''}<br><a href='{place.url}' target='_blank'>Open on Instagram</a>"
                )
                folium.Marker(
                    [place.lat, place.lng],
                    popup=folium.Popup(popup, max_width=260),
                    tooltip=f"{place.label} · {place.place_type}",
                    icon=folium.Icon(color=color, icon=icon, prefix="fa"),
                ).add_to(cluster)
            fmap.fit_bounds([[shown["lat"].min(), shown["lng"].min()], [shown["lat"].max(), shown["lng"].max()]])
            view = st_folium(fmap, height=550, use_container_width=True, returned_objects=["bounds"], key="travel_map")

            # Charts and cards follow the part of the map in view
            in_view = shown
            bounds = (view or {}).get("bounds") or {}
            south_west, north_east = bounds.get("_southWest") or {}, bounds.get("_northEast") or {}
            has_area = (
                south_west.get("lat") is not None and north_east.get("lat") is not None
                and north_east["lat"] > south_west["lat"] and north_east["lng"] > south_west["lng"]
            )
            if has_area:  # before the map has drawn, bounds can be a single point
                in_view = shown[
                    shown["lat"].between(south_west["lat"], north_east["lat"])
                    & shown["lng"].between(south_west["lng"], north_east["lng"])
                ]

            st.subheader(f"In view: {in_view['code'].nunique():,} posts")
            left, right = st.columns(2)
            with left:
                st.markdown("**Most-saved places**")
                bar_chart(in_view.groupby("label")["code"].nunique().sort_values(ascending=False).head(15), "place")
            with right:
                st.markdown("**Place types**")
                bar_chart(in_view.groupby("place_type")["code"].nunique(), "type")

            cards = in_view.drop_duplicates("code").head(30)
            if in_view["code"].nunique() > len(cards):
                st.caption(f"Showing {len(cards)} posts; zoom in or filter to see the rest.")
            columns = st.columns(3)
            for i, place in enumerate(cards.itertuples()):
                with columns[i % 3]:
                    show_place(place, candidates[candidates["code"] == place.code])

with watch_tab:
    titles, no_title = load_watch_read()
    available = titles[~titles["hidden"].astype(bool)]

    st.subheader("Today I want to…")
    pick = st.columns([1, 2, 1])
    mode = pick[0].radio("Mode", ["Watch", "Read"], horizontal=True, label_visibility="collapsed")
    kinds = {"Watch": {"movie", "series"}, "Read": {"book"}}[mode]
    pool = available[available["kind"].isin(kinds) & ~available["watched"].astype(bool)]
    genre_options = sorted({g for genres in pool["genres"] for g in genres})
    genre = pick[1].selectbox("Genre", ["Any genre"] + genre_options, label_visibility="collapsed")
    if genre != "Any genre":
        pool = pool[pool["genres"].apply(lambda g: genre in g)]
    if pick[2].button("🎲 Surprise me", disabled=pool.empty):
        st.session_state["suggestion"] = random.choice(list(pool["item_key"]))
    suggestion = pool[pool["item_key"] == st.session_state.get("suggestion")]
    if not suggestion.empty:
        with st.columns(3)[0]:
            show_title(next(suggestion.itertuples()), key_prefix="pick_")
    elif pool.empty:
        st.caption("Nothing left to suggest here; everything is watched or hidden.")

    st.divider()
    show_watched = st.toggle("Show watched", value=True)
    listed = available if show_watched else available[~available["watched"].astype(bool)]
    st.write(f"{len(listed)} titles · {int(available['watched'].astype(bool).sum())} watched")
    columns = st.columns(3)
    for i, item in enumerate(listed.itertuples()):
        with columns[i % 3]:
            show_title(item)

    with st.expander(f"No title found in {len(no_title)} posts (the title may only be in the video)"):
        for post in no_title.itertuples():
            caption = (post.caption or "no caption").strip().splitlines()[0][:100]
            st.markdown(f"- [{post.owner_username or 'post'}]({post.url}) — {caption}")

with workouts_tab:
    workouts = load_workouts()
    st.markdown("**What do you want to work on?** Click muscles on the body (click again to unselect).")
    map_col, extra_col = st.columns([3, 2])
    with map_col:
        muscles = body_map(workouts)
    with extra_col:
        if muscles:
            st.markdown("**Selected:** " + ", ".join(MUSCLES[m]["label"] for m in muscles))
        extra_areas = st.pills(
            "Also", list(OFF_MAP), selection_mode="multi",
            format_func=lambda a: f"{a} ({sum(bool(set(OFF_MAP[a][0]) & set(b)) for b in workouts['body_areas'])})",
        ) or []
        st.caption("Darker muscles have more saved workouts. Body drawings: [wger](https://wger.de) (AGPL-3.0).")
    areas = sorted({a for m in muscles for a in MUSCLES[m]["areas"]} | {a for e in extra_areas for a in OFF_MAP[e][0]})
    exercise_muscles = [x for m in muscles for x in MUSCLES[m]["exercise_muscles"]] + \
                       [x for e in extra_areas for x in OFF_MAP[e][1]]
    filters = st.columns([2, 2, 1])
    workout_query = filters[0].text_input("Search workouts", placeholder="exercise, @user, word in caption")
    workout_types = filters[1].multiselect("Type", sorted(workouts["workout_type"].dropna().unique()))
    show_unclear = filters[2].toggle("Show posts without details", value=False)

    shown = workouts
    if not show_unclear:
        shown = shown[~shown["status"].isin(["no_details", "no_caption"])]
    if areas:
        shown = shown[shown["body_areas"].apply(lambda b: bool(set(b) & set(areas)))]
    if workout_types:
        shown = shown[shown["workout_type"].isin(workout_types)]
    if workout_query:
        q = workout_query.lower()
        shown = shown[shown.apply(
            lambda w: q in " ".join([w["title"] or "", w["owner_username"] or "", w["caption"] or "", *w["exercises"]]).lower(),
            axis=1,
        )]

    unclear = workouts["status"].isin(["no_details", "no_caption"]).sum()
    st.subheader("From your Instagram saves")
    st.write(f"{len(shown)} of {len(workouts)} posts" + ("" if show_unclear else f" · {unclear} without details hidden"))
    columns = st.columns(3)
    for i, workout in enumerate(shown.itertuples()):
        with columns[i % 3]:
            show_workout(workout)

    if muscles or extra_areas:
        st.divider()
        more_exercises(muscles + extra_areas, exercise_muscles)

with journal_tab:
    prompts = load_prompts()
    entries = load_entries()
    view = st.segmented_control(
        "View", ["Prompts", "My journal"], default="Prompts", label_visibility="collapsed",
        format_func=lambda v: {"Prompts": "💭 Prompts", "My journal": "📖 My journal"}[v],
    )
    if view == "My journal":
        st.caption(f"{len(entries)} {'entry' if len(entries) == 1 else 'entries'}")
        journal_query = st.text_input("Search my journal", placeholder="word in a reply or prompt")
        shown_entries = entries
        if journal_query:
            q = journal_query.lower()
            shown_entries = entries[entries.apply(lambda e: q in (e["body"] + " " + e["prompt_text"]).lower(), axis=1)]
        if shown_entries.empty:
            st.caption("No entries yet — open ✍️ Write under any prompt." if entries.empty else "No entries match.")
        for entry in shown_entries.itertuples():
            with st.container(border=True):
                show_entry(entry, with_prompt=True)
    else:
        visible = prompts[~prompts["hidden"]]
        categories = sorted(visible["category"].dropna().unique())

        st.subheader("✨ A prompt for today")
        today = st.columns([2, 1])
        today_category = today[0].selectbox("From", ["Any category"] + categories, label_visibility="collapsed")
        pool = visible[~visible["used"]]
        if today_category != "Any category":
            pool = pool[pool["category"] == today_category]
        if today[1].button("🔀 Another one", disabled=pool.empty) or st.session_state.get("prompt_of_day") not in set(pool["prompt_key"]):
            st.session_state["prompt_of_day"] = random.choice(list(pool["prompt_key"])) if not pool.empty else None
        todays = pool[pool["prompt_key"] == st.session_state.get("prompt_of_day")]
        if todays.empty:
            st.caption("No unused prompts here.")
        else:
            st.info(next(todays.itertuples()).prompt)

        st.divider()
        picked_categories = st.pills(
            "Categories", categories, selection_mode="multi",
            format_func=lambda c: f"{c} ({(visible['category'] == c).sum()})",
        )
        filters = st.columns([1, 2, 1])
        prompt_kind = filters[0].radio("Kind", ["All", "Questions", "ChatGPT"], horizontal=True, label_visibility="collapsed")
        prompt_query = filters[1].text_input("Search prompts", placeholder="word in a prompt", label_visibility="collapsed")
        favorites_only = filters[2].toggle("Favorites only")

        shown = visible
        if picked_categories:
            shown = shown[shown["category"].isin(picked_categories)]
        if prompt_kind != "All":
            shown = shown[shown["kind"] == {"Questions": "question", "ChatGPT": "chatgpt"}[prompt_kind]]
        if prompt_query:
            shown = shown[shown["prompt"].str.contains(prompt_query, case=False, regex=False)]
        if favorites_only:
            shown = shown[shown["favorite"]]

        st.write(f"{len(shown)} of {len(visible)} prompts · {int(visible['used'].sum())} used · "
                 f"{int(prompts['hidden'].sum())} hidden")
        for prompt in shown.itertuples():
            show_prompt(prompt, categories, entries[entries["prompt_key"] == prompt.prompt_key])

with browse_tab:
    st.write(f"{len(filtered):,} posts")
    table = filtered.assign(
        hashtags=filtered["hashtags"].apply(lambda tags: " ".join(f"#{t}" for t in tags)),
        collections=filtered["collections"].apply(", ".join),
        place=filtered["location_name"].fillna(filtered["locations_from_caption"].apply(lambda places: ", ".join(dict.fromkeys(places)))),
    ).sort_values("taken_at", ascending=False)
    st.dataframe(
        table[["url", "username", "place", "collections", "caption_text", "hashtags", "taken_at", "like_count"]],
        column_config={
            "url": st.column_config.LinkColumn("Post", display_text="Open"),
            "username": "Posted by",
            "place": "Place",
            "collections": "Collections",
            "caption_text": st.column_config.TextColumn("Caption", width="large"),
            "hashtags": "Hashtags",
            "taken_at": st.column_config.DatetimeColumn("Posted", format="MMM D, YYYY"),
            "like_count": st.column_config.NumberColumn("Likes", format="%d"),
        },
        hide_index=True,
        width="stretch",
        height=600,
    )

with export_tab:
    account = st.selectbox("Account", sorted(saves["insta_account"].unique()))
    account_saves = saves[saves["insta_account"] == account]
    left, right = st.columns(2)
    left.metric("Saved posts", f"{account_saves['code'].nunique():,}")
    right.metric("Newest save", f"{account_saves['added_time'].max():%b %d, %Y}")

    st.subheader("Saves per month")
    per_month = account_saves.drop_duplicates("code").set_index("added_time").resample("MS")["code"].count()
    st.bar_chart(per_month, y_label="Posts saved", x_label="")

    st.subheader("Collections")
    st.bar_chart(account_saves["collection_name"].value_counts(), horizontal=True, x_label="Posts", y_label="")
