from src.helper.model import engine, RawstdInstaDownloadSavedReels
from sqlalchemy.orm import sessionmaker
from src.data_scraper_downloads.utils import parse_datetime, get_soup_from_file_path
from src.helper.utils_model import insert_record_with_conflict
import os
from datetime import datetime


Session = sessionmaker(bind=engine)


def process_collections_and_reels(soup, target_profile):
    session = Session()


    reel_required_fields = ['reel_url', 'collection_name','user_name','added_time','insta_account','python_script','python_runtime']
    reel_table = RawstdInstaDownloadSavedReels
    reel_unique_columns = ['collection_name', 'reel_url', 'insta_account']

    # Get the script name
    script_name = os.path.basename(__file__)
    last_updated_time = datetime.now()

    # Extract all posts
    posts = soup.find_all("div", class_="pam _3-95 _2ph- _a6-g uiBoxWhite noborder")

    # Parse data into a structured format
    collection_name = None
    print("getting data from html")
    for post in posts:
        # Extract user name
        user_name_tag = post.find("div", class_="_3-95 _2pim _a6-h _a6-i")
        user_name = user_name_tag.text.strip() if user_name_tag else "No user name found"
        
        # Extract the reel link
        link_tag = post.find("a", href=True)
        link = link_tag["href"].strip() if link_tag else None

        # Extract the saved time
        added_time = None
        # print(post)
        table_rows = post.find_all("tr")
        for row in table_rows:
            td_elements = row.find_all("td")
            if len(td_elements) == 2 and "Saved on" in td_elements[0].text:
                added_time_string = td_elements[1].text.strip()
                added_time = parse_datetime(added_time_string)
                break  # Exit the loop once we've found the saved time

        # Insert reel into 'insta_download_saved_reels' table
        reel_data = {
                "collection_name": collection_name,
                "user_name": user_name,
                "reel_url": link,
                "added_time": added_time,
                "insta_account": target_profile,
                "python_script": script_name,
                "python_runtime": last_updated_time
            }
        if not all(field in reel_data for field in reel_required_fields):
            raise ValueError("Missing required fields in collection data.")

        print(f"INSERTING REEL: link: '{link}', insta_account: '{target_profile}'")
        insert_record_with_conflict(session=session, target_table=reel_table, unique_columns=reel_unique_columns, data=reel_data)


    # Commit the changes to the database
    session.commit()
    session.close()

    print("Data has been successfully inserted into the database.")


saved_target="your_instagram_activity/saved/saved_posts.html"

target_profile_list = ["marmargrobe","szyk_designs","marmargrub"]

# target_profile = target_profile_list[0]
# print(f"Collecting data for: {target_profile}")
# soup_obj = get_soup_from_file_path(target_profile=target_profile, saved_target=saved_target)
# process_collections_and_reels(soup=soup_obj, target_profile=target_profile)

# target_profile = target_profile_list[1]
# print(f"Collecting data for: {target_profile}")
# soup_obj = get_soup_from_file_path(target_profile=target_profile, saved_target=saved_target)
# process_collections_and_reels(soup=soup_obj, target_profile=target_profile)

# target_profile = target_profile_list[2]
# print(f"Collecting data for: {target_profile}")
# soup_obj = get_soup_from_file_path(target_profile=target_profile, saved_target=saved_target)
# process_collections_and_reels(soup=soup_obj, target_profile=target_profile)