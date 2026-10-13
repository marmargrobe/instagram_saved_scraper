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

map_tab, browse_tab, export_tab = st.tabs(["Map", "Browse", "Instagram export"])

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
        use_container_width=True,
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
