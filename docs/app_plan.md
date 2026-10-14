# Saved Instagram app — plan

A local Streamlit app that turns saved Instagram posts into something usable: a recipe box,
a travel map, a watch/read list, workout ideas, journal prompts, hobby and business ideas.

Constraints:
- **Free and local.** No paid APIs or hosted AI; Python libraries that run on this laptop.
- **Local first.** Postgres on this laptop; the app runs at `localhost`. Hosting can come later.

## Tabs and the collections that feed them

Each Instagram collection maps to one tab. This mapping lives in the database table
`clean.collection_tabs`, so it can change without code changes.

| Tab | Collections | What matters for these posts |
|---|---|---|
| **Travel** | Travel, Mars & Ags, Travel Ags and Mars, Sf places, Norway Trip, California, Japan, Korea, Taipei, Poland, Eurotrip 2025, Pieniny, New Travel (szyk_designs) | Place, type of place, coordinates |
| **Recipes** | Recipes | Caption (ingredients, steps) |
| **Watch / read** | Movies, Watch later, Books | Title and genre |
| **Workouts** | Workouts, Massages, Face yoga | Exercises, body area |
| **Journal prompts** | Journals | The prompts in the caption |
| **Hobbies & projects** | Projects, Ideas, Guitar, Art, Photography, Dance, Clothes, Interior design, Tattoos, Make up, Templates, Wedding inspo (szyk_designs) | A short "what is this" and tags |
| **Business** | Bithnes (business ideas) | Caption; expected to grow |
| *(not shown)* | Agnes (one client interior-design post), Europe purchases | — |

Posts not in any collection (most saves from 2021–2024) stay out of the tabs for now.
Once each tab's posts have clear traits, those traits can be used to sort uncategorized
posts automatically (see backlog).

## Data foundation

All tabs read from one table, **`clean.saved_posts`**: one row per post, combining the
three sources:

| Source | Covers | Has captions? | Has coordinates? |
|---|---|---|---|
| 2024 API scrape (`rawstd.insta_saved_reels` → `clean.insta_saved_reels`) | 1,000 posts | Yes | Yes (geotag) |
| 2024 export (`rawstd.insta_download_saved_reels`, Nov 2021 – Nov 2024) | ~5,900 posts | No | No |
| 2026 export (same table + `rawstd.insta_download_saved_reels_details`, Nov 2024 – Oct 2026) | ~2,600 posts | Yes | No |

Each tab then gets its own results table (for example `clean.recipes`) with a **status**:
`found`, `not_found` (for example a Movies post whose caption has no title) or `no_caption`.
The `not_found` and `no_caption` counts show how many posts would need media analysis.

## How each tab gets its data

### Travel
A post can point to a place in several ways, and they don't always agree:

| Source | Example | Notes |
|---|---|---|
| 📍 in the caption | "This is 📍Lovers Point Beach in Pacific Grove" | Usually the exact spot |
| Post geotag | "Los Angeles, California" | Accurate but often just a city |
| Place names spaCy finds in the caption | "Japan", "Kyoto" | Broad; fallback |
| The collection | Japan, Taipei, Poland | Context for looking places up |

Approach: save every place found as a **candidate** with its source, show the most
specific one by default, and let me correct it in the app; corrections are saved and win
from then on. A post listing several spots ("5 cafés in Kyoto") produces several places.
Place names become coordinates with Nominatim (OpenStreetMap, free), cached.

Each place also gets a **type**: café, restaurant, bar, hike/trail, beach, viewpoint,
monument/landmark, museum, shop, hotel, other.

Map features: pins clustered by area; when zoomed in, a chart of the places (and place
types) in view and how often they were saved.

### Recipes
Rules over the caption: find an "Ingredients" section and quantity lines ("2 cups flour"),
and "Instructions/Steps/Method". Flag "recipe in bio / in comments / link" posts.
Labels (meal type, cuisine, diet) with the local zero-shot classifier already in the project.

### Watch / read
Titles from captions: quoted titles, "Title (2019)", numbered lists, spaCy WORK_OF_ART.
Check them against the free IMDb title dataset (also gives genres) and Open Library for
books. Posts with no title found are flagged for media analysis.
App: "Today I want to watch/read…" → pick a genre → suggestions.

### Workouts
Exercises from the caption; label each post with body areas (zero-shot).

### Journal prompts
Split captions into prompts (questions, numbered lines). Label prompts by theme
(gratitude, relationships, goals, …); themes can be edited later.

### Hobbies & projects, Business
A short "what is this" plus tags. To be refined later; the content is varied.

## Build order
1. ✅ `clean.saved_posts` (foundation) and `clean.collection_tabs`
2. ✅ Recipes tab (v1): `python -m src.data_cleaner.recipes_extract` fills `clean.recipes`;
   pictures from `python -m src.data_scraper_downloads.fetch_thumbnails` (cached in `media/thumbnails/`)
3. ✅ Travel tab (v1): `python -m src.data_cleaner.travel_extract` fills `clean.travel_places`
   (OpenStreetMap lookups cached in `clean.geocode_cache`); fixes made in the app are stored in
   `clean.travel_place_choices` and survive re-extraction
4. ✅ Watch / read tab (v1): `python -m src.data_cleaner.imdb_load` loads IMDb movies/series into
   `reference.imdb_titles`; `python -m src.data_cleaner.watch_read_extract` fills `clean.watch_read_titles`;
   watched / not interested saved in `clean.watch_read_choices`
5. ✅ Refresh pipeline (see below): `python -m src.pipeline.refresh`, `ops.pipeline_runs`, sidebar
   "Update now" + "Request a new Instagram export", optional weekly launchd job
6. ✅ Workouts tab (v1): `python -m src.data_cleaner.workouts_extract` fills `clean.workouts` (keyword rules:
   body areas, type, exercises with sets, equipment); body-area buttons in the app
7. ✅ Journal prompts tab (v1): `python -m src.data_cleaner.journal_prompts_extract` fills
   `clean.journal_prompts` (one row per prompt); my categories / favorite / used / hidden in
   `clean.journal_prompt_choices`, keyed by prompt text so they survive re-extraction
8. Remaining tabs: Hobbies & projects, Business

## Refresh pipeline
Everything goes stale at different speeds, so one runner keeps it current:

| Step | Depends on | Runs when |
|---|---|---|
| Import new Instagram export | zip in ~/Downloads | a new zip is there |
| Recipes / Travel / Watch-read extraction | import | there are new posts (new posts only) |
| IMDb reference data | — | older than 30 days |
| Exercise database (free-exercise-db) | — | older than 90 days |
| Thumbnails | import | posts without a picture |

- `python -m src.pipeline.refresh` (or `--only travel`); each step skips itself when there is nothing new
- `ops.pipeline_runs` logs each step (start, end, status, rows, error)
- App sidebar: "Last updated …" + **🔄 Update now** (runs in the background, shows step progress)
- Optional weekly run with macOS launchd (runs at next wake if the Mac was asleep)
- **Request new export helper:** Instagram pages can't be embedded (frame-blocking headers) and there is no
  API for "Download your information", so the app shows the date range to request per account (from the
  newest save in the database), opens Accounts Center → Download your information in a new tab, and lists
  the choices to make (Saved, HTML, that date range). The refresh imports the zip once it is downloaded.

## Ideas backlog
Everything mentioned so far, to come back to:

- **Workouts:** ✅ clickable body map (wger anatomy drawings, 15 muscles, shaded by number of saved workouts;
  neck, face, forearms, lower back, inner/outer thighs, hips and full body as buttons next to it — a
  react-body-highlighter version with all of them on the body was tried and dropped for looks) and
  ✅ "💪 Load more exercises" from free-exercise-db (876 exercises, photos, instructions; level / equipment /
  type filters). Next: extract specific muscles from captions (inner thighs, lower back, rear delts) instead of
  broad body areas; save exercises to a "my routine" list.
- **Recipes:** calorie estimate per recipe (ingredient parsing + USDA FoodData Central); edit a recipe in the
  app (fix name/labels/status; sets `user_edited` so re-extraction keeps the edit); split "what I eat in a day"
  posts into several recipes; speed up labeling (Mac GPU via `device="mps"`, or a smaller zero-shot model,
  which currently takes ~10 min for 32 posts).
- **Journal prompts:** ✅ custom categories and labeling in the app (v1). Next:
  - ✅ **Replies (v1):** "✍️ Write" under each prompt saves a dated entry in `personal.journal_entries`
    (own schema, separate from the Instagram data, never part of any hosted version); the prompt stays and
    shows "📖 2 replies" with the earlier replies (editable); "📖 My journal" reads every entry like a diary.
    Next: "on this day" view; regular backup of the `personal` schema
    (`pg_dump -d mars -n personal -f journal_backup.sql`).
  - Export favorites as a printable list.
- **UI design session (together):** colors, fonts, spacing and layout for each tab — Streamlit theme
  (`.streamlit/config.toml`), custom CSS, maybe a color and icon per tab.
- **Watch / read recommendations:** "more like the films I saved". Free and local: add IMDb's
  `title.principals` + `name.basics` (directors, actors, composers), build a profile per film (genres, decade,
  director, cast, composer) and rank well-rated films by cosine similarity (scikit-learn), with reasons
  ("same director: Paul Thomas Anderson"). Optional second opinion: TMDB's free similar/recommendations API
  (needs a free API key).
- **Movies from my music (separate project):** Spotify API (free developer account) for top artists/genres;
  MusicBrainz / Wikidata to link artists and composers to film soundtracks. Spotify's audio-features and
  recommendations endpoints were closed to new apps in late 2024, so mood matching may not be possible.
- **Watch / read:** ✅ "today I want to watch/read" picker by genre (v1). Next: OCR on cached thumbnails for the
  posts with no title (9 of 19 in v1); "watch later" list order; streaming availability.
- **Travel:** ✅ place types and zoom-linked charts (v1). Next: trip lists (Mars & Ags is a shared trip list
  with a friend); posts that list places without 📍 ("5 cafés in Kyoto: 1. … 2. …"); "visited" checkmarks;
  better types for places OpenStreetMap only knows as a city.
- **Business:** own tab; collection expected to grow.
- **Media analysis** for posts whose title/recipe/place is only in the video or image:
  Whisper (speech to text) and Tesseract/EasyOCR (on-screen text), run locally. Needs the
  media re-downloaded, since stored Instagram media links expire. Decide after seeing the
  `not_found` / `no_caption` counts.
- **Removed posts:** the thumbnail fetcher detects posts removed from Instagram (`.removed` markers);
  keep their saved caption/recipe, and maybe show a "removed" filter or count per tab.
- **Thumbnails for media analysis:** run OCR on cached thumbnails to find movie titles or place
  names shown in the cover image (cheaper than downloading videos).
- **Auto-categorize** uncategorized saves into tabs, using the traits learned from each tab.
- **Hosting:** the app could move online later (Streamlit Community Cloud + Neon/Supabase).
