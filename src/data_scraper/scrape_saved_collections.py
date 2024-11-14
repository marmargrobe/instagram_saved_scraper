import os
from dotenv import load_dotenv
from src.data_scraper.utils_insta import InstaClient
from src.helper.utils_db import connect_to_db
from datetime import datetime

# Load environment variables from the .env file in the "insta-processing" root folder
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))


"""
This script will read the Instagram data, either from an API, and write it to the raw data table in the database.
It could periodically check for new data or use a Kafka consumer to trigger updates.


Kafka producer:
-After ingesting new data into the raw table, the producer sends a Kafka message to trigger processing.
Include the smallest last_updated timestamp or an identifier to inform the consumers of the new data that needs to be processed.

"""

use_instagrapi = False
if use_instagrapi:

    # Load credentials from environment variables
    username = os.getenv('INSTAGRAM_USERNAME')
    password = os.getenv('INSTAGRAM_PASSWORD')
    collection_id = os.getenv('INSTAGRAM_COLLECTION_ID')

    # Create an instance of InstaClient
    insta_client = InstaClient(username=username, password=password)

    # Login and start fetching data
    insta_client.login()
    print("Cookie Expiry:", insta_client.get_cookie_expiry())
    print("==== Starting to fetch saved posts data ====")


    # ---------------------------------
    # Ingest code

    all_collections = insta_client.api.collections()
else:
    import pandas as pd

    file_name = 'all_collections_2.csv'
    file_path = os.path.join(os.path.dirname(__file__), file_name)


    # Read CSV into a pandas DataFrame
    df = pd.read_csv(file_path)
    all_collections = []
    class Collection:
        # id,name,type,media_count
        def __init__(self, id, name, type, media_count):
            self.id = id  # Initialize the username attribute
            self.name = name
            self.type = type
            self.media_count = media_count
    
    for i in range(0,len(df)-1):

        # print(i)
        row = df.iloc[i]
        # print(row)
        new_col = Collection(id = row["id"],name = row["name"],type = row["type"],media_count = int(row["media_count"]))
        all_collections.append(new_col)




# Get current timestamp for last_updated
last_updated_time = datetime.now()

# ---------------------------------
# Connect to your PostgreSQL database
connection = connect_to_db()  # Assuming you have a function for connecting to DB
display_message = "connected to db"
print(display_message)

cursor = connection.cursor()


# Prepare the SQL statements
check_query = """
    SELECT name, media_count, last_updated FROM rawstd.insta_saved_collections WHERE id = %s;
"""

insert_query = """
    INSERT INTO rawstd.insta_saved_collections (id, name, media_count, last_updated)
    VALUES (%s, %s, %s, %s)
    ON CONFLICT (id) DO UPDATE 
    SET name = EXCLUDED.name, 
        media_count = EXCLUDED.media_count, 
        last_updated = EXCLUDED.last_updated;
"""

update_query = """
    UPDATE rawstd.insta_saved_collections
    SET name = %s, media_count = %s, last_updated = %s
    WHERE id = %s;
"""

# Get the current timestamp for 'last_updated'
last_updated_time = datetime.now()
print(last_updated_time)

# Iterate over each collection in all_collections
for collection in all_collections:
    # Check if the collection ID already exists in the database
    cursor.execute(check_query, (collection.id,))
    existing_data = cursor.fetchone()

    # If no data is found for the ID, insert it
    if existing_data is None:
        display_message = "No record exists, inserting the collection data"
        print(display_message)
        # No record exists, so insert the collection
        cursor.execute(insert_query, (collection.id, collection.name, collection.media_count, last_updated_time))
    else:
        display_message = "Record exists, checking if there are changes"
        print(display_message)
        print(collection.name) 
        print(type(collection.media_count))
        print(last_updated_time)
        print(collection.id)
        existing_name, existing_media_count, existing_last_updated = existing_data

        if (existing_name != collection.name or 
            existing_media_count != collection.media_count):
            display_message = "Change found, updating the record"
            print(display_message)
            # collection.last_updated = collection.last_updated.strftime('%Y-%m-%d %H:%M:%S')

            print(update_query, (collection.name, collection.media_count, last_updated_time, collection.id))
            cursor.execute(update_query, (collection.name, collection.media_count, last_updated_time, collection.id))
        else:
            display_message = "No changed found"
            print(display_message)

# Commit the changes to the database
connection.commit()