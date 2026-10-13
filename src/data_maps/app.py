"""
Local Streamlit app for browsing saved Instagram posts.

Run from the project root (so .env is found):
    source .venv_data_maps/bin/activate
    streamlit run src/data_maps/app.py
"""
import os
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

THUMBNAIL_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "media", "thumbnails")
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

recipes_tab, travel_tab, browse_tab, export_tab = st.tabs(["Recipes", "Travel", "Browse", "Instagram export"])

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
