"""
Find the places in travel posts and put them on the map (clean.travel_places).

    python -m src.data_cleaner.travel_extract              # all posts in the travel tab
    python -m src.data_cleaner.travel_extract --limit 50   # try it on a few posts first

For each post, every place found becomes a candidate:
  pin      text after 📍 in the caption (usually the exact spot)
  geotag   the post's own location (from the 2024 API scrape)
  caption  place names spaCy finds in the caption (FAC/LOC, then GPE)
Names are looked up in OpenStreetMap (Nominatim, free; max 1 lookup/second) and cached in
clean.geocode_cache, so re-runs are fast. Lookups are steered toward the countries named in
the caption and the post's collection (Japan, Taipei, ...). The most trusted candidate with
coordinates becomes the post's primary place.
"""
import argparse
import json
import re
import time
import unicodedata
from collections import Counter
from datetime import datetime

import spacy
from geopy.exc import GeopyError
from geopy.geocoders import Nominatim
from sqlalchemy import text

from src.helper.model import engine

EXTRACTOR_VERSION = "1.0"
USER_AGENT = "saved-instagram-places (personal, non-commercial project)"

# Collection -> ISO country codes to steer lookups ('' = no hint)
COLLECTION_COUNTRIES = {
    "Japan": "jp", "Korea": "kr", "Taipei": "tw", "Poland": "pl", "Pieniny": "pl",
    "Norway Trip": "no", "California": "us", "Sf places": "us",
}
COUNTRY_CODES = {  # names often written in captions
    "usa": "us", "united states": "us", "california": "us", "japan": "jp", "korea": "kr", "south korea": "kr",
    "taiwan": "tw", "poland": "pl", "norway": "no", "iceland": "is", "switzerland": "ch", "swiss": "ch",
    "italy": "it", "france": "fr", "spain": "es", "portugal": "pt", "greece": "gr", "germany": "de",
    "austria": "at", "croatia": "hr", "mexico": "mx", "canada": "ca", "uk": "gb", "england": "gb",
    "scotland": "gb", "ireland": "ie", "netherlands": "nl", "turkey": "tr", "thailand": "th",
    "vietnam": "vn", "indonesia": "id", "bali": "id", "peru": "pe", "chile": "cl", "argentina": "ar",
    "brazil": "br", "new zealand": "nz", "australia": "au", "morocco": "ma", "egypt": "eg",
    "czech": "cz", "prague": "cz", "hungary": "hu", "slovenia": "si", "montenegro": "me",
    "philippines": "ph", "china": "cn", "hong kong": "hk", "singapore": "sg", "india": "in",
    "colombia": "co", "costa rica": "cr", "denmark": "dk", "sweden": "se", "finland": "fi",
}

PIN = re.compile(r"📍\s*[:\-–]?\s*([^\n]*)")
PIN_NOISE = re.compile(
    r"\b(?:comment|location (?:is )?(?:mentioned|in)|tip|spots?|save|follow|link|dm|below|here|guide|"
    r"list|places|things to|where to|itinerary)\b",
    re.IGNORECASE,
)
SPLIT_PARTS = re.compile(r"\s+(?:at|in|near|on|by)\s+|,|\(|\)|\s[-–|]\s|/")
SENTENCE_END = re.compile(r"\s[-–—|]\s|[.!?]\s|\s(?:is|was|has|with|where|which|that)\s")
ABBREVIATIONS = {
    "NP": "National Park", "SP": "State Park", "SNR": "State Natural Reserve", "NRA": "National Recreation Area",
    "NM": "National Monument", "MSP": "Memorial State Park", "RP": "Regional Park", "SB": "State Beach",
    "Mt.": "Mount", "Mt": "Mount", "St.": "Saint",
}
GENERIC_WORDS = {
    "national", "park", "state", "lake", "mount", "beach", "trail", "point", "falls", "river", "island",
    "islands", "canyon", "valley", "north", "south", "east", "west", "city", "county", "the", "and",
    "forest", "reserve", "monument", "recreation", "area", "regional", "natural", "memorial", "saint",
    "highway", "road", "street", "northern", "southern", "eastern", "western", "coast", "bay", "next", "parking", "modern",
}
NAME_TYPES = [  # words in the place's own name beat OpenStreetMap's type ("Lovers Point Beach" is a beach)
    (r"\bbeach\b|\bplaya\b|\bpraia\b", "beach"),
    (r"\btrail\b|\bhike\b|\bloop\b", "hike/trail"),
    (r"\bfalls\b|\bwaterfall\b|\bfoss\b|\bfoss$", "waterfall"),
    (r"\bcaf[eé]\b|\bcoffee\b|\bbakery\b", "café"),
    (r"\brestaurant\b|\bbistro\b|\btrattoria\b|\bramen\b", "restaurant"),
    (r"\bviewpoint\b|\boverlook\b|\bvista\b|\blookout\b", "viewpoint"),
    (r"\bmuseum\b|\bgallery\b", "museum"),
    (r"\bnational park\b|\bstate park\b|\bpark\b|\breserve\b|\bforest\b", "park"),
    (r"\bpeak\b|\bmount\b|\bmountain\b|\bmt\.?\s", "mountain"),
    (r"\blake\b|\bsee$|\blagoon\b", "lake/water"),
    (r"\btemple\b|\bshrine\b|\bcastle\b|\bcathedral\b|\bpalace\b|\bbridge\b|\bbunker\b", "landmark"),
]

# OpenStreetMap class/type -> place type shown in the app
OSM_TYPES = [
    (("amenity", {"cafe", "ice_cream"}), "café"),
    (("amenity", {"restaurant", "fast_food", "food_court"}), "restaurant"),
    (("amenity", {"bar", "pub", "biergarten", "nightclub"}), "bar"),
    (("amenity", {"place_of_worship"}), "landmark"),
    (("tourism", {"viewpoint"}), "viewpoint"),
    (("tourism", {"museum", "gallery"}), "museum"),
    (("tourism", {"hotel", "guest_house", "hostel", "alpine_hut", "camp_site", "chalet", "apartment"}), "stay"),
    (("tourism", None), "attraction"),
    (("historic", None), "landmark"),
    (("natural", {"beach"}), "beach"),
    (("natural", {"peak", "volcano", "ridge", "cliff", "saddle", "arete"}), "mountain"),
    (("natural", {"water", "bay", "spring", "glacier", "hot_spring"}), "lake/water"),
    (("waterway", {"waterfall"}), "waterfall"),
    (("waterway", None), "lake/water"),
    (("water", None), "lake/water"),
    (("natural", None), "nature"),
    (("leisure", {"park", "nature_reserve", "garden"}), "park"),
    (("boundary", {"national_park", "protected_area"}), "park"),
    (("highway", {"path", "footway", "track", "bridleway"}), "hike/trail"),
    (("route", {"hiking", "foot"}), "hike/trail"),
    (("shop", None), "shop"),
    (("place", {"city", "town", "village", "hamlet", "suburb", "neighbourhood", "quarter", "borough"}), "city/town"),
    (("place", {"island", "islet", "archipelago"}), "island"),
    (("place", None), "region"),
    (("boundary", {"administrative"}), "region"),
]
BROAD_TYPES = {"city/town", "region", None}
KEYWORD_TYPES = [  # fallback when OpenStreetMap only says "a city"
    (r"\bhik(?:e|ing)\b|\btrail\b|\btrek", "hike/trail"),
    (r"\bcaf[eé]\b|\bcoffee\b|\bbakery\b", "café"),
    (r"\brestaurant\b|\bdinner\b|\blunch\b|\bbrunch\b|\bfood\b", "restaurant"),
    (r"\bbeach\b", "beach"),
    (r"\bwaterfall\b", "waterfall"),
    (r"\bviewpoint\b|\boverlook\b", "viewpoint"),
    (r"\bmuseum\b", "museum"),
    (r"\bhotel\b|\bresort\b|\bcabin\b|\bairbnb\b", "stay"),
]


def place_type(osm_class, osm_type):
    for (cls, types), label in OSM_TYPES:
        if osm_class == cls and (types is None or osm_type in types):
            return label
    return None


def keyword_type(caption):
    for pattern, label in KEYWORD_TYPES:
        if re.search(pattern, caption or "", re.IGNORECASE):
            return label
    return None


def _normalize(value):
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9 ]", " ", value)


def expand_abbreviations(name):
    return " ".join(ABBREVIATIONS.get(word, word) for word in name.split())


def looks_like_place(name):
    """Place names are mostly capitalized: 'Lovers Point Beach', not 'All under 3 miles'."""
    words = [w for w in re.findall(r"[^\W\d_][\w'’.-]*", name) if len(w) > 3]
    return bool(words) and sum(w[0].isupper() for w in words) / len(words) >= 0.5


def distinctive_words(name):
    return [w for w in _normalize(name).split() if len(w) >= 4 and w not in GENERIC_WORDS]


def plausible_match(query, raw, exact=False):
    """The matched place's own name should contain the query's distinctive word
    ('Cook Islands' must not match the 'Greek Islands' restaurant in Cook County).
    exact: the names must be the same (used for names spaCy guessed from a caption)."""
    matched_name = _normalize(raw.get("name") or raw.get("display_name", "").split(",")[0]).split()
    if exact:
        return matched_name == _normalize(query).split()
    distinctive = distinctive_words(query)
    return not distinctive or distinctive[0] in matched_name


def clean_place(raw):
    raw = SENTENCE_END.split(raw)[0]  # "Lovers Point Beach in Pacific Grove - a little gem..." -> place only
    name = re.sub(r"[@#][\w.]+", "", raw)
    name = re.sub(r"[^\w\s,'’.&()\-–/|]", " ", name)  # emoji and symbols
    name = re.sub(r"\s+", " ", name).strip(" ,.-–|:")
    name = re.sub(r"^the\s+", "", name, flags=re.IGNORECASE)
    if "(" not in name:
        name = name.rstrip(")").strip()
    if len(name) < 3 or len(name) > 70 or PIN_NOISE.search(name) or not looks_like_place(name) or not distinctive_words(name):
        return None
    return name


def pin_places(caption):
    lines = caption.splitlines()
    places = []
    for i, line in enumerate(lines):
        for match in PIN.finditer(line):
            raw = match.group(1)
            if not raw.strip() and i + 1 < len(lines):  # "📍" alone: the place is on the next line
                raw = lines[i + 1]
            name = clean_place(raw)
            if name and name not in places:
                places.append(name)
    return places


def caption_places(nlp, caption, exclude):
    doc = nlp(caption[:3000])
    found = []
    for ent in doc.ents:
        if ent.label_ not in ("FAC", "LOC", "GPE"):
            continue
        name = clean_place(ent.text)
        if not name or any(e and (name.lower() in e.lower() or e.lower() in name.lower()) for e in exclude):
            continue
        rank = 4 if ent.label_ == "GPE" else 3
        if name not in [n for n, _ in found]:
            found.append((name, rank))
    return found


def hinted_countries(caption, collections):
    codes = {COLLECTION_COUNTRIES[c] for c in collections if c in COLLECTION_COUNTRIES}
    lowered = (caption or "").lower()
    codes |= {code for name, code in COUNTRY_CODES.items() if re.search(rf"\b{re.escape(name)}\b", lowered)}
    return sorted(codes)


class Geocoder:
    """Nominatim with a database cache and the 1-request-per-second limit."""

    def __init__(self, connection):
        self.connection = connection
        self.nominatim = Nominatim(user_agent=USER_AGENT, timeout=15)
        self.last_call = 0.0
        self.calls = 0

    def lookup(self, query, country_codes=()):
        codes = ",".join(country_codes)
        cached = self.connection.execute(
            text("SELECT found, result FROM clean.geocode_cache WHERE query = :q AND country_codes = :c"),
            {"q": query, "c": codes},
        ).first()
        if cached:
            return cached.result if cached.found else None

        time.sleep(max(0.0, 1.1 - (time.time() - self.last_call)))
        try:
            result = self.nominatim.geocode(
                query, addressdetails=True, language="en", country_codes=list(country_codes) or None
            )
        except GeopyError as error:
            print(f"  lookup failed for {query!r}: {error}")
            return None
        finally:
            self.last_call = time.time()
            self.calls += 1
        raw = result.raw if result else None
        self.connection.execute(
            text("""INSERT INTO clean.geocode_cache (query, country_codes, found, result)
                    VALUES (:q, :c, :f, CAST(:r AS JSONB)) ON CONFLICT DO NOTHING"""),
            {"q": query, "c": codes, "f": raw is not None, "r": json.dumps(raw) if raw else None},
        )
        self.connection.commit()
        return raw

    def best_match(self, name, country_codes, exact=False):
        """Try 'A at B' as 'A, B', then the full name, then each part; with the country hint first."""
        name = expand_abbreviations(name)
        parts = [p.strip() for p in SPLIT_PARTS.split(name) if p and len(p.strip()) >= 3]
        variants = [", ".join(parts)] if len(parts) > 1 else []
        variants += [name] + [p for p in parts if p != name]
        variants = list(dict.fromkeys(variants))
        attempts = [(v, country_codes) for v in variants] if country_codes else []
        if not (exact and country_codes):  # guessed caption names stay inside the hinted countries
            attempts += [(v, ()) for v in variants[:2]]
        for query, codes in attempts:
            raw = self.lookup(query, codes)
            if raw and plausible_match(query, raw, exact):
                return raw
        return None


def to_row(code, name, source, rank, raw, caption):
    row = {
        "code": code, "name": name, "source": source, "rank": rank,
        "lat": None, "lng": None, "matched_name": None, "city": None, "region": None,
        "country": None, "country_code": None, "osm_class": None, "osm_type": None, "place_type": None,
    }
    if raw:
        address = raw.get("address", {})
        row.update({
            "lat": float(raw["lat"]), "lng": float(raw["lon"]), "matched_name": raw.get("display_name"),
            "city": address.get("city") or address.get("town") or address.get("village") or address.get("municipality"),
            "region": address.get("state") or address.get("region") or address.get("province"),
            "country": address.get("country"), "country_code": (address.get("country_code") or "")[:2] or None,
            "osm_class": raw.get("class"), "osm_type": raw.get("type"),
        })
        row["place_type"] = place_type(row["osm_class"], row["osm_type"])
    for pattern, label in NAME_TYPES:
        if re.search(pattern, name, re.IGNORECASE):
            row["place_type"] = label
            break
    if row["place_type"] in BROAD_TYPES and source != "caption":
        row["place_type"] = keyword_type(caption) or row["place_type"]
    return row


def choose_primary(rows):
    located = [r for r in rows if r["lat"] is not None]
    for row in rows:
        row["is_primary"] = False
        row["on_map"] = False
    if not located:
        return
    # most trusted source first; within it, a specific place beats a city/region
    best = min(located, key=lambda r: (r["rank"], r["place_type"] in BROAD_TYPES))
    best["is_primary"] = True
    pins = [r for r in located if r["source"] == "pin"]
    for row in pins if len(pins) > 1 else [best]:
        row["on_map"] = True


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    nlp = spacy.load("en_core_web_sm")
    with engine.connect() as connection:
        posts = connection.execute(text("""
            SELECT code, caption, collections, geotag_name, geotag_lat, geotag_lng
            FROM clean.saved_posts WHERE 'travel' = ANY (tabs)
            ORDER BY first_saved_at DESC NULLS LAST
        """)).all()
        if args.limit:
            posts = posts[: args.limit]
        geocoder = Geocoder(connection)
        now = datetime.now()
        all_rows = []
        for i, post in enumerate(posts, 1):
            caption = post.caption or ""
            countries = hinted_countries(caption, post.collections)
            rows = []
            pins = pin_places(caption)
            for name in pins:
                rows.append(to_row(post.code, name, "pin", 1, geocoder.best_match(name, countries), caption))
            if post.geotag_lat is not None:
                row = to_row(post.code, post.geotag_name or "Post location", "geotag", 2, None, caption)
                row.update({"lat": post.geotag_lat, "lng": post.geotag_lng})
                rows.append(row)
            for name, rank in caption_places(nlp, caption, pins + [post.geotag_name or ""]):
                rows.append(to_row(post.code, name, "caption", rank, geocoder.best_match(name, countries, exact=True), caption))
            choose_primary(rows)
            for row in rows:
                row.update({"extractor_version": EXTRACTOR_VERSION, "extracted_at": now})
            all_rows.extend(rows)
            if i % 25 == 0:
                print(f"  {i}/{len(posts)} posts, {geocoder.calls} new lookups")

        codes = [p.code for p in posts]
        connection.execute(text("DELETE FROM clean.travel_places WHERE code = ANY (:codes)"), {"codes": codes})
        if all_rows:
            connection.execute(text("""
                INSERT INTO clean.travel_places
                    (code, name, source, rank, lat, lng, matched_name, city, region, country, country_code,
                     osm_class, osm_type, place_type, is_primary, on_map, extractor_version, extracted_at)
                VALUES
                    (:code, :name, :source, :rank, :lat, :lng, :matched_name, :city, :region, :country, :country_code,
                     :osm_class, :osm_type, :place_type, :is_primary, :on_map, :extractor_version, :extracted_at)
                ON CONFLICT (code, source, name) DO NOTHING
            """), all_rows)
        connection.commit()

    on_map = {r["code"] for r in all_rows if r["is_primary"]}
    print(f"{len(posts)} travel posts: {len(on_map)} placed on the map, {len(posts) - len(on_map)} without a location")
    print("Primary place from: " + ", ".join(f"{s} {n}" for s, n in Counter(r["source"] for r in all_rows if r["is_primary"]).most_common()))
    print("Place types: " + ", ".join(f"{t} {n}" for t, n in Counter(r["place_type"] for r in all_rows if r["on_map"]).most_common()))


if __name__ == "__main__":
    main()
