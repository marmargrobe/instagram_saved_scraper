## Instagram saved collections scraper

  - [Motivation](#motivation)
  - [Pre-requisites](#pre-requisites)
  - [How to run?](#how-to-run)
  - [What are collections and how do I know collections ID?](#what-are-collections-and-how-do-i-know-collections-id)
  - [What data is saved?](#what-data-is-saved)
  - [Credits](#credits)

### Motivation
I usually save posts and categorize them in collections on Instagram, so that I can access them later. However, it's not very conveninent to go through them as the list grows big over time. I never really go through these collections. So I created this script to login to my instagram account and scrape all the collections I have.
____________

### Pre-requisites
This script works with Python 3
`pip` is required to download dependencies

`.env` file is created with necessary login information
- `DB_HOST`
- `DB_PORT`
- `DB_NAME`
- `DB_USER`
- `DB_PASSWORD`
- `INSTAGRAM_USERNAME`
- `INSTAGRAM_PASSWORD`
> **Note:** I'm using gcp to encrypt my .env file:
> `gpg -c .env` -> to encrypt
> `gpg -d .env.gpg > .env` -> to decrypt

____________

### How to run?

1. Make sure you have Python 3.12 installed on your machine
2. Clone the repo and then navigate inside the directory
3. Create a venv: `python -m venv .venv`
4. Install the python dependencies: `pip install -r src/data_scraper/requirements.txt`
5. There are some tables that can be created to store your data. I am using postgres and creating my tables in sqitch:
[Sqitch Repo](https://github.com/mgrobeln/sqitch_mars)

> **Note:** This code requires that these tables exist and that the .env file has the login information. I'll can add functionality to just save this info to a csv in the repo if anyone requests.

6. Open terminal/CMD in the directory and run the script in the following manner: 
- `python -m src.data_scraper.scrape_message_threads` (PENDING)
- `python -m src.data_scraper.scrape_saved_collections`
- `python -m src.data_scraper.scrape_saved_reels`


7. If everything works fine, the tables will be loaded.
__________________

### What are collections and how do I know collections ID?

Whenever you save a post in Instagram using the 'save' button, you can go into the "Saved" section and view them. You can also group your saved posts by creating collections.

To get the collection ID, simply go to the collection you want (on desktop or mobile browser, not Instagram app) and the ID should be present in the URL, something like:

`https://www.instagram.com/<username>/saved/<collection_name>/<collection_id>/`
_________________

### What data is saved?
Currently, you will see following headers/columns/attributes in the saved csv file for each saved post:

| Sl. no. | Parameter | Can be blank? | Description |
| ------- | -------- | -------- | -------- | 
| 1.  | **#**                   | no | serial number
| 2.  | **link**                | no | link to instagram post, is generated in script
| 3.  | **location_short_name** | yes | short name of location if present in post
| 4.  | **facebook_places_id**  | yes | location id if location is present
| 5.  | **location_name**       | yes | name of location
| 6.  | **address**             | yes | address of location
| 7.  | **city**                | yes | city of location
| 8.  | **location_lng**        | yes | longitude of location
| 9.  | **location_lat**        | yes | latitude of location
| 10. | **location_map_link**   | yes | google map link created basis latitude and longitude if present
| 11. | **lng**                 | yes | longitude of post (extra)
| 12. | **lat**                 | yes | latitude of post (extra)
| 13. | **map_link**            | yes | google map link created basis latitude and longitude if present
| 14. | **full_name_op**        | no | name on Instagram of person who posted
| 15. | **username_op**         | no | Instagram username of person who posted
| 16. | **caption**             | yes | caption text if present

________________

### Credits
This script heavily relies on https://github.com/dilame/instagram-private-api library for Instagram API functions like logging in, getting posts etc. Thanks to the developer(s)!


