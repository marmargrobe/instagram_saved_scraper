## Instagram saved posts

I save a lot of posts on Instagram (recipes, travel spots, movies, workouts, journal prompts)
and never go back to them. This project pulls my saved posts into a Postgres database, cleans
and organizes them, and shows them in a local Streamlit app.

  - [How it works](#how-it-works)
  - [Setup](#setup)
  - [Importing a new Instagram export](#importing-a-new-instagram-export)
  - [Cleaning the data](#cleaning-the-data)
  - [Reference data (IMDb)](#reference-data-imdb)
  - [Thumbnails](#thumbnails)
  - [Refresh pipeline](#refresh-pipeline)
  - [The app](#the-app)
  - [Docker (old AWS setup)](#docker-old-aws-setup)
  - [Credits](#credits)

### How it works

```
Instagram ──► src/data_scraper/            (2024: API scrape with instagrapi)      ─┐
          └─► src/data_scraper_downloads/  ("Download your information" exports)  ─┴─► rawstd.* tables
                                                                                         │
                       src/data_cleaner/  (parse locations, users, hashtags; categorize) ◄┘ ─► clean.* tables
                                                                                         │
                       src/data_maps/app.py  (Streamlit app)                            ◄┘
```

- `rawstd.*` tables hold the data as it came in; `clean.*` tables hold parsed, app-ready data.
- The table definitions live in the separate [sqitch_mars](https://github.com/marmargrobe/sqitch_mars) repo.

### Setup

1. **Postgres (local).** Postgres 16 runs on this laptop. Create the database and tables:
   ```
   createdb mars
   cd ../sqitch_mars && sqitch deploy db:pg:///mars
   ```
2. **`.env`** in the project root (not committed):
   ```
   DB_HOST=localhost
   DB_PORT=5432
   DB_NAME=mars
   DB_USER=<your mac username>
   DB_PASSWORD=
   ```
3. **Virtual environments**, one per part of the project:
   | venv | For | Install |
   |---|---|---|
   | `.venv` | scrapers, imports | `pip install -r src/data_scraper/requirements.txt -r src/data_scraper_downloads/requirements.txt` |
   | `.venv_data_cleaner` | cleaning, categorizing | `pip install -r src/data_cleaner/requirements.txt` |
   | `.venv_data_maps` | the app | `pip install -r src/data_maps/requirements.txt` |

   Run scripts from the project root as modules, e.g. `python -m src.data_scraper.load_from_csv`.

4. **Old data.** `src/data_scraper/all_posts_2.csv` (1,000 posts with full details from the 2024
   API scrape) can be reloaded with `python -m src.data_scraper.load_from_csv`.

### Importing a new Instagram export

1. Instagram → Accounts Center → Your information and permissions → Download your information.
   Pick **Saved**, format **HTML**.
2. Leave the downloaded `instagram-<account>-<date>-<id>.zip` in `~/Downloads` and run:
   ```
   python -m src.data_scraper_downloads.import_export
   ```
   Only the `saved/` folder is copied into `src/data_scraper_downloads/downloaded/` (gitignored);
   a full account export also contains messages and login history. Posts already loaded are
   skipped. `--dry-run` shows what would happen; `--profile <account>` re-imports an export
   that was already copied.

Both Instagram export layouts are supported: the 2024 one (links and save dates only) and the
newer one (adds captions, hashtags and the post owner).

### Cleaning the data

```
python -m src.data_cleaner.reels_scraped_transform      # rawstd.insta_saved_reels → clean tables
python -m src.data_cleaner.reels_scraped_categorize --lookup_col caption_text --top_n 3
```

### Reference data (IMDb)

The Watch / read tab checks titles against IMDb's free non-commercial datasets
(https://datasets.imdbws.com): movies, TV movies, series and mini-series with a rating (~540k titles).
```
python -m src.data_cleaner.imdb_load               # downloads to data/imdb/ (gitignored) if missing, then loads
python -m src.data_cleaner.imdb_load --download    # refresh with the latest files (~230 MB)
python -m src.data_cleaner.watch_read_extract      # find titles in Watch / read posts
```

### Thumbnails

Instagram's image links expire, so the app shows pictures saved on this laptop:
```
python -m src.data_scraper_downloads.fetch_thumbnails --tab recipes   # or travel, all, ...
```
It opens each post's public embed page (no login) in headless Chrome and saves the cover image
to `media/thumbnails/<code>.jpg` (gitignored). Posts removed from Instagram get a `.removed`
marker. Already-fetched posts are skipped, so run it again after each import.

### Refresh pipeline

One command runs every step in order; each step skips itself when there is nothing new:
```
.venv_data_cleaner/bin/python -m src.pipeline.refresh                 # import → imdb → exercises → recipes → travel → watch_read → workouts → journal → thumbnails
.venv_data_cleaner/bin/python -m src.pipeline.refresh --only travel   # one or more steps
```
- Each step is logged in `ops.pipeline_runs`; a failed step is logged and the rest still run; only one refresh runs at a time.
- In the app: sidebar **Data** → "Last updated", **🔄 Update now** (runs in the background with live step progress)
  and **📥 Request a new Instagram export** (date range per account + link to Instagram's download page).
- Weekly (optional): `scripts/install_weekly_refresh.sh` adds a macOS launchd job for Sundays 9:00
  (`--uninstall` removes it). Output goes to `logs/refresh.log` (gitignored).

### The app

```
source .venv_data_maps/bin/activate
streamlit run src/data_maps/app.py
```
The Workouts tab's clickable body map uses muscle shapes from
[react-body-highlighter](https://github.com/giavinh79/react-body-highlighter) (MIT), turned into
`src/data_maps/assets/` by `python -m src.data_maps.build_muscle_map` (only needed to rebuild them).
"💪 Load more exercises" shows exercises from [free-exercise-db](https://github.com/yuhonas/free-exercise-db)
(public domain), loaded into `reference.exercises` by `python -m src.data_cleaner.exercises_load`.

Opens at http://localhost:8501 with a map, a searchable table and stats per Instagram export.

The app is growing into one tab per kind of saved post (Travel, Recipes, Watch/read, Workouts,
Journal prompts, Hobbies & projects, Business). Which collections feed which tab, how each tab
extracts its data, and the ideas backlog are in **[docs/app_plan.md](docs/app_plan.md)**.

### Docker (old AWS setup)

The Dockerfiles and GitHub Actions workflows were used to run the categorizer on AWS (GPU)
against an RDS database that no longer exists. They still reference the old
`src.data_cleaner.data_categorization` module and need updating before they are used again.

Build base image: `docker build -f Dockerfile.base -t data-cleaner .`

Build and run a categorizer image, e.g.:
```
docker build -f Dockerfile.city -t city_category .
docker run --gpus all -it city_category
```
Other images: `Dockerfile.lng_lat`, `Dockerfile.location_list`, `Dockerfile.hashtags`,
`Dockerfile.location_name`, `Dockerfile.usertags`.

### Credits
Started from [skd1993/instagram-saved-scraper](https://github.com/skd1993/instagram-saved-scraper).
The 2024 API scraper uses [instagrapi](https://github.com/subzeroid/instagrapi).
