from bs4 import BeautifulSoup
from src.helper.model import engine, RawstdInstaDownloadSavedCollections, RawstdInstaDownloadSavedReels
from sqlalchemy.orm import sessionmaker
from src.data_scraper_downloads.utils import parse_datetime, get_soup_from_file_path


Session = sessionmaker(bind=engine)


def process_collections_and_reels(soup):
    session = Session()

    # Extract all collections
    collections = soup.find_all("div", class_="pam _3-95 _2ph- _a6-g uiBoxWhite noborder")

    # Parse data and insert into the database
    for collection in collections:
        collection_name = None
        creation_time = None
        update_time = None
        added_time = None

        # Extract the collection name (from the first 'td' element where 'Name' is listed)
        name_tag = collection.find("td", class_="_2pin _a6_q", colspan="2")
        collection_name = name_tag.find("div").text.strip() if name_tag else None

        # Extract creation time, update time, and added time
        table_rows = collection.find_all("tr")
        for row in table_rows:
            if "Creation Time" in row.text:
                creation_time_string = row.find_all("td")[1].text.strip() if row.find_all("td") else None
                creation_time = parse_datetime(creation_time_string) if creation_time_string else None
            if "Update Time" in row.text:
                update_time_string = row.find_all("td")[1].text.strip() if row.find_all("td") else None
                update_time = parse_datetime(update_time_string) if update_time_string else None
            if "Added Time" in row.text:
                added_time_string = row.find_all("td")[1].text.strip() if row.find_all("td") else None
                added_time = parse_datetime(added_time_string) if added_time_string else None

        # Insert collection into 'insta_download_saved_collections' table
        collection_entry = RawstdInstaDownloadSavedCollections(
            collection_name=collection_name,
            creation_time=creation_time,
            update_time=update_time,
            insta_account=target_profile
        )
        session.add(collection_entry)

        # Extract the individual reels in this collection (links to the reels)
        reels = collection.find_all("a", href=True)
        for reel in reels:
            link = reel["href"].strip()  # Reel link
            user_name = reel.text.strip() if reel.text else "No user name found"

            # Insert reel into 'insta_download_saved_reels' table
            reel_entry = RawstdInstaDownloadSavedReels(
                collection_name=collection_name,
                user_name=user_name,
                reel_url=link,
                added_time=added_time,
                insta_account=target_profile
            )
            session.add(reel_entry)

    # Commit the changes to the database
    session.commit()
    session.close()

    print("Data has been successfully inserted into the database.")





target_profile_list = ["marmargrobe","szyk_designs","marmargrub"]
target_profile = target_profile_list[2]


soup_obj = get_soup_from_file_path(target_profile=target_profile)


process_collections_and_reels(soup_obj)