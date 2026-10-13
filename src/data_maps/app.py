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

import folium
import pandas as pd
import streamlit as st
from folium.plugins import MarkerCluster
from sqlalchemy import text
from streamlit_folium import st_folium

from src.helper.model import engine

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


def show_recipe(recipe):
    with st.container(border=True):
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
    st.header("Filter")
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

recipes_tab, map_tab, browse_tab, export_tab = st.tabs(["Recipes", "Map", "Browse", "Instagram export"])

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

with map_tab:
    located = filtered.dropna(subset=["lat", "lng"])
    st.write(f"{len(located):,} of {len(filtered):,} matching posts have a location")
    if located.empty:
        st.info("No matching posts have a location.")
    else:
        fmap = folium.Map(location=[located["lat"].mean(), located["lng"].mean()], zoom_start=3, tiles="OpenStreetMap")
        cluster = MarkerCluster().add_to(fmap)
        for post in located.itertuples():
            caption = post.caption_text[:160] + ("…" if len(post.caption_text) > 160 else "")
            popup = (
                f"<b>{post.location_name or ''}</b><br>@{post.username or ''}<br>"
                f"<small>{caption}</small><br><a href='{post.url}' target='_blank'>Open on Instagram</a>"
            )
            folium.Marker(
                [post.lat, post.lng],
                popup=folium.Popup(popup, max_width=280),
                tooltip=post.location_name,
            ).add_to(cluster)
        fmap.fit_bounds([[located["lat"].min(), located["lng"].min()], [located["lat"].max(), located["lng"].max()]])
        st_folium(fmap, height=600, use_container_width=True, returned_objects=[])

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
