import os
from dotenv import load_dotenv
from src.data_scraper.utils_insta import InstaClient, fetch_all_saved_medias
from src.helper.utils_db import connect_to_db
from datetime import datetime
from src.helper.mapping import reels_column_transformations, transform_dtypes, reels_column_dtype


# Load environment variables from the .env file in the "insta-processing" root folder
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))


"""
This script will read the Instagram data, either from an API, and write it to the raw data table in the database.
It could periodically check for new data or use a Kafka consumer to trigger updates.


Kafka producer:
-After ingesting new data into the raw table, the producer sends a Kafka message to trigger processing.
Include the smallest last_updated timestamp or an identifier to inform the consumers of the new data that needs to be processed.

"""

use_instagrapi = True
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
    # Ingest ccode
    saved_collection = []


    user_id = insta_client.api.user_id

    all_collections = insta_client.api.collections()

    total_medias = all_collections[0].media_count

    all_posts_pk = insta_client.api.collection_pk_by_name("All posts")

    all_saved_medias = fetch_all_saved_medias(insta_client, all_posts_pk, total_medias, batch_size=200)


    for media in all_saved_medias:
        saved_collection.append(media.dict())

else:
    import pandas as pd

    file_name = 'all_posts_2.csv'
    file_path = os.path.join(os.path.dirname(__file__), file_name)


    # Read CSV into a pandas DataFrame
    df = pd.read_csv(file_path)


# ---------------------------------
# Connect to your PostgreSQL database
connection = connect_to_db()  # Assuming you have a function for connecting to DB
display_message = "connected to db"
print(display_message)

cursor = connection.cursor()

# Get the current timestamp for 'last_updated'
last_updated_time = datetime.now()
print(last_updated_time)

cursor.execute("SELECT count(id) FROM rawstd.insta_saved_reels")
table_record_count = cursor.fetchone()[0]
print(len(df))
if table_record_count < len(df):
    # Transform dtypes to match data table
    transformed_df = transform_dtypes(df=df, column_transformations=reels_column_transformations, column_dtypes=reels_column_dtype)
    print(len(transformed_df))

# Iterate through the DataFrame and check for each 'id' in the table
for index, row in transformed_df.iterrows():
    print(index)
    reel_id = row['id']
    
    # Check if the collection id already exists in the rawstd.insta_saved_reels table
    if table_record_count == 0:
        print("No records in table")
        result = None
    else:
        cursor.execute("SELECT id,pk,code FROM rawstd.insta_saved_reels WHERE id = %s and pk = %s and code = %s", (reel_id, row["pk"], row["code"]))
        print(reel_id)
        print(row["pk"])
        print(row["code"])
        result = cursor.fetchone()
        print(result)

    if result is None:
        # If the id doesn't exist, insert the new collection data into the table
        # Prepare the data for insertion, assuming you have all the required columns in the DataFrame

    
        data = (
            row['pk'],  # collection ID (VARCHAR)
            reel_id,  # reel ID (VARCHAR)
            row['code'],  # code (VARCHAR)
            row['taken_at'],  # taken_at (TIMESTAMP)
            row['media_type'],  # media_type (VARCHAR)
            row['image_versions2'],  # image_versions2 (JSONB)
            row['product_type'],  # product_type (VARCHAR)
            row['thumbnail_url'],  # thumbnail_url (VARCHAR)
            row['location'],  # location (JSONB)
            row['user'],  # user (JSONB)
            row['comment_count'],  # comment_count (INTEGER)
            row['comments_disabled'],  # comments_disabled (BOOLEAN)
            row['commenting_disabled_for_viewer'],  # commenting_disabled_for_viewer (BOOLEAN)
            row['like_count'],  # like_count (INTEGER)
            row['play_count'],  # play_count (INTEGER)
            row['has_liked'],  # has_liked (BOOLEAN)
            row['caption_text'],  # caption_text (VARCHAR)
            row['accessibility_caption'],  # accessibility_caption (VARCHAR)
            row['usertags'],  # usertags (JSONB)
            row['sponsor_tags'],  # sponsor_tags (JSONB)
            row['video_url'],  # video_url (VARCHAR)
            row['view_count'],  # view_count (INTEGER)
            row['video_duration'],  # video_duration (FLOAT)
            row['title'],  # title (VARCHAR)
            row['resources'],  # resources (JSONB)
            row['clips_metadata'],  # clips_metadata (JSONB)
            last_updated_time  # last_updated (TIMESTAMP)
        )

        
        insert_query = """
            INSERT INTO rawstd.insta_saved_reels (
                pk, id, code, taken_at, media_type, image_versions2, product_type, 
                thumbnail_url, "location", "user", comment_count, comments_disabled, 
                commenting_disabled_for_viewer, like_count, play_count, has_liked, 
                caption_text, accessibility_caption, usertags, sponsor_tags, 
                video_url, view_count, video_duration, title, resources, clips_metadata, 
                last_updated
            )
            VALUES (
                %s, %s, %s, %s::timestamp, %s, %s::jsonb, %s, 
                %s, %s, %s, %s::int, %s::boolean, 
                %s::boolean, %s::int, %s::int, %s::boolean, 
                %s, %s, %s, %s, 
                %s, %s::int, %s::float, %s, %s::jsonb, %s::jsonb, 
                %s::timestamp
            )
            ON CONFLICT (id) DO UPDATE 
            SET 
                pk = EXCLUDED.pk,
                code = EXCLUDED.code,
                taken_at = EXCLUDED.taken_at,
                media_type = EXCLUDED.media_type,
                image_versions2 = EXCLUDED.image_versions2,
                product_type = EXCLUDED.product_type,
                thumbnail_url = EXCLUDED.thumbnail_url,
                location = EXCLUDED.location,
                "user" = EXCLUDED."user",
                comment_count = EXCLUDED.comment_count,
                comments_disabled = EXCLUDED.comments_disabled,
                commenting_disabled_for_viewer = EXCLUDED.commenting_disabled_for_viewer,
                like_count = EXCLUDED.like_count,
                play_count = EXCLUDED.play_count,
                has_liked = EXCLUDED.has_liked,
                caption_text = EXCLUDED.caption_text,
                accessibility_caption = EXCLUDED.accessibility_caption,
                usertags = EXCLUDED.usertags,
                sponsor_tags = EXCLUDED.sponsor_tags,
                video_url = EXCLUDED.video_url,
                view_count = EXCLUDED.view_count,
                video_duration = EXCLUDED.video_duration,
                title = EXCLUDED.title,
                resources = EXCLUDED.resources,
                clips_metadata = EXCLUDED.clips_metadata,
                last_updated = EXCLUDED.last_updated;
        """
        cursor.execute(insert_query, data)
        
        print(f"Inserted new reel with ID: {reel_id}")
    # else:
    #     print(f"Record with ID {reel_id} already exists.")

# Commit the changes to the database

connection.commit()
cursor.close()
connection.close()


