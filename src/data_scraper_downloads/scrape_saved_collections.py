from src.helper.model import engine, RawstdInstaDownloadSavedCollections, RawstdInstaDownloadSavedReels
from sqlalchemy.orm import sessionmaker
from src.data_scraper_downloads.utils import parse_datetime, get_soup_from_file_path
from src.helper.utils_model import insert_record_with_conflict
import os
from datetime import datetime



Session = sessionmaker(bind=engine)


def process_collections_and_reels(soup, target_profile):
    session = Session()

    # Get the script name
    script_name = os.path.basename(__file__)
    last_updated_time = datetime.now()

    collection_required_fields = ['collection_name', 'creation_time', 'update_time', 'insta_account', 'python_script', 'python_runtime']
    collection_table = RawstdInstaDownloadSavedCollections
    collection_unique_columns = ['collection_name', 'insta_account']

    reel_required_fields = ['reel_url', 'collection_name','user_name','added_time','insta_account','python_script','python_runtime']
    reel_table = RawstdInstaDownloadSavedReels
    reel_unique_columns = ['collection_name', 'reel_url', 'insta_account']
    
    # Extract all collections (we'll iterate over the divs with the class that holds the collection)
    collections = soup.find_all("div", class_="pam _3-95 _2ph- _a6-g uiBoxWhite noborder")

    collection_name = None
    creation_time = None
    update_time = None
    for collection in collections:
    
        # Extract the individual reels in this collection (links to the reels)
        reels = collection.find_all("a", href=True)
        if len(reels) == 0:
            # Extract the collection name (from the first 'td' element where 'Name' is listed)
            name_tag = collection.find("td", class_="_2pin _a6_q", colspan="2")

            collection_name = name_tag.find("div").text.strip() if name_tag else None
            # print(collection_name)
            # Extract the creation time and update time from the 'td' tags
        
        table_rows = collection.find_all("tr")
            
            # Loop through table rows to find 'Creation Time' and 'Update Time'
        for row in table_rows:
            if len(reels) == 0:
                if "Creation Time" in row.text:
                    creation_time_string = row.find_all("td")[1].text.strip() if row.find_all("td") else None
                    creation_time = parse_datetime(creation_time_string) if creation_time_string else None
                if "Update Time" in row.text:
                    update_time_string = row.find_all("td")[1].text.strip() if row.find_all("td") else None
                    update_time = parse_datetime(update_time_string) if update_time_string else None
                # Adding to Collections
                # Ensure the dictionary contains the necessary fields
                collection_data = {
                    'collection_name': collection_name, 
                    'creation_time': creation_time, 
                    'update_time': update_time, 
                    'insta_account': target_profile, 
                    'python_script': script_name, 
                    'python_runtime': last_updated_time

                }
                if not all(field in collection_data for field in collection_required_fields):
                    raise ValueError("Missing required fields in collection data.")

                print(f"INSERTING COLLECTION: {collection_name}")
                if creation_time != None and update_time != None:
                    insert_record_with_conflict(session=session, target_table=collection_table, unique_columns=collection_unique_columns, data=collection_data)

            else:
                if "Added Time" in row.text:
                    added_time_string = row.find_all("td")[1].text.strip() if row.find_all("td") else None
                    added_time = parse_datetime(added_time_string) if added_time_string else None
        # Insert collection into 'insta_download_saved_collections' table


        # Process each reel in the collection
        for reel in reels:
            link = reel["href"].strip()  # Reel link
            user_name = reel.text.strip() if reel.text else "No user name found"

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

            # print(f"INSERTING REEL: link: '{link}', insta_account: '{target_profile}'")
            insert_record_with_conflict(session=session, target_table=reel_table, unique_columns=reel_unique_columns, data=reel_data)

    # Commit the changes to the database
    session.commit()
    session.close()

    print("Data has been successfully inserted into the database.")




saved_target="your_instagram_activity/saved/saved_collections.html"

target_profile_list = ["marmargrobe","szyk_designs","marmargrub"]

# target_profile = target_profile_list[0]
# print(f"Collecting data for: {target_profile}")
# soup_obj = get_soup_from_file_path(target_profile=target_profile, saved_target=saved_target)
# if soup_obj:
#     process_collections_and_reels(soup=soup_obj, target_profile=target_profile)

# target_profile = target_profile_list[1]
# print(f"Collecting data for: {target_profile}")
# soup_obj = get_soup_from_file_path(target_profile=target_profile, saved_target=saved_target)
# if soup_obj:
#     process_collections_and_reels(soup=soup_obj, target_profile=target_profile)

# target_profile = target_profile_list[2]
# print(f"Collecting data for: {target_profile}")
# soup_obj = get_soup_from_file_path(target_profile=target_profile, saved_target=saved_target)
# if soup_obj:
#     process_collections_and_reels(soup=soup_obj, target_profile=target_profile)