from datetime import datetime
from src.helper.mapping import reels_column_dtype, reels_column_transformations, transform_dtypes
import logging
from sqlalchemy.dialects.postgresql import insert
from src.helper.model import RawstdInstaDownloadSavedReelsDetails
from sqlalchemy.exc import SQLAlchemyError


# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def upsert_insta_saved_reels(all_data, cursor,):
    # Get the current timestamp for 'last_updated'
    last_updated_time = datetime.now()
    print(last_updated_time)

    cursor.execute("SELECT count(id) FROM clean.insta_saved_reels")
    table_record_count = cursor.fetchone()[0]
    # Iterate through the DataFrame and check for each 'id' in the table
    if table_record_count < len(all_data):
        # Transform dtypes to match data table
        transformed_df = all_data
        # transformed_df = transform_dtypes(df=all_data, column_transformations=reels_column_transformations, column_dtypes=reels_column_dtype)
    for index, row in all_data.iterrows():
        print(index)
        reel_id = row['id']
        
        # Check if the collection id already exists in the clean.insta_saved_reels table
        if table_record_count == 0:
            print("No records in table")
            result = None
        else:
            cursor.execute("SELECT id, pk, code FROM clean.insta_saved_reels WHERE id = %s and pk = %s and code = %s", (reel_id, row["pk"], row["code"]))
            print(reel_id)
            print(row["pk"])
            print(row["code"])
            result = cursor.fetchone()
            print(result)

        if result is None:
            # Prepare the data for insertion, assuming all required columns are in the DataFrame
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
                # row['commenting_disabled_for_viewer'],  # commenting_disabled_for_viewer (BOOLEAN)
                row['like_count'],  # like_count (INTEGER)
                row['play_count'],  # play_count (INTEGER)
                row['has_liked'],  # has_liked (BOOLEAN)
                row['caption_text'],  # caption_text (VARCHAR)
                # row['accessibility_caption'],  # accessibility_caption (VARCHAR)
                row['usertags'],  # usertags (JSONB)
                row['sponsor_tags'],  # sponsor_tags (JSONB)
                row['video_url'],  # video_url (VARCHAR)
                row['view_count'],  # view_count (INTEGER)
                row['video_duration'],  # video_duration (FLOAT)
                # row['title'],  # title (VARCHAR)
                row['resources'],  # resources (JSONB)
                row['clips_metadata'],  # clips_metadata (JSONB)
                last_updated_time,  # last_updated (TIMESTAMP)
                row['hashtags'],  # hashtags (VARCHAR[])
                row['lng'],  # lng (FLOAT)
                row['lat'],  # lat (FLOAT)
                row['city'],  # city (VARCHAR)
                row['location_name'],  # location_name (VARCHAR)
                row['user_pk']  # user_pk (VARCHAR(50))
            )
            
            # Insert query with the new columns
            insert_query = """
                INSERT INTO clean.insta_saved_reels (
                    pk, id, code, taken_at, media_type, image_versions2, product_type, 
                    thumbnail_url, "location", "user", comment_count, comments_disabled, 
                    like_count, play_count, has_liked, 
                    caption_text, usertags, sponsor_tags, 
                    video_url, view_count, video_duration, resources, clips_metadata, 
                    last_updated, hashtags, lng, lat, city, location_name, user_pk
                )
                VALUES (
                    %s, %s, %s, %s::timestamp, %s, %s::jsonb, %s, 
                    %s, %s, %s, %s::int, %s::boolean, 
                    %s::int, %s::int, %s::boolean, 
                    %s, %s, %s, 
                    %s, %s::int, %s::float, %s::jsonb, %s::jsonb, 
                    %s::timestamp, %s::varchar[], %s::float, %s::float, %s, %s, %s
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
                    like_count = EXCLUDED.like_count,
                    play_count = EXCLUDED.play_count,
                    has_liked = EXCLUDED.has_liked,
                    caption_text = EXCLUDED.caption_text,
                    usertags = EXCLUDED.usertags,
                    sponsor_tags = EXCLUDED.sponsor_tags,
                    video_url = EXCLUDED.video_url,
                    view_count = EXCLUDED.view_count,
                    video_duration = EXCLUDED.video_duration,
                    resources = EXCLUDED.resources,
                    clips_metadata = EXCLUDED.clips_metadata,
                    last_updated = EXCLUDED.last_updated,
                    hashtags = EXCLUDED.hashtags,
                    lng = EXCLUDED.lng,
                    lat = EXCLUDED.lat,
                    city = EXCLUDED.city,
                    location_name = EXCLUDED.location_name,
                    user_pk = EXCLUDED.user_pk;
            """
            print(insert_query,data)
            cursor.execute(insert_query, data)
            
            print(f"Inserted new reel with ID: {reel_id}")


def upsert_user(all_data, cursor,):

    # Prepare the SQL statements
    check_query = """
        SELECT * FROM clean.insta_user WHERE id = %s;
    """

    insert_query = """
        INSERT INTO clean.insta_user (id, username, full_name, profile_pic_url)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (id) DO UPDATE 
        SET username = EXCLUDED.username, 
            full_name = EXCLUDED.full_name, 
            profile_pic_url = EXCLUDED.profile_pic_url;
    """

    update_query = """
        UPDATE clean.insta_user
        SET username = %s, full_name = %s, profile_pic_url = %s
        WHERE id = %s;
    """


    # Iterate over each row in all_data
    for index, row in all_data.iterrows():
        if row["user_id"]:
            print(row)

            # Check if the row ID already exists in the database
            cursor.execute(check_query, (row["user_id"],))
            existing_data = cursor.fetchone()

            # If no data is found for the ID, insert it
            if existing_data is None:
                display_message = "No record exists, inserting the row data"
                print(display_message)
                # No record exists, so insert the row
                cursor.execute(insert_query, (row["user_id"], row["user_username"], row["user_full_name"], row["user_profile_pic_url"]))
            else:
                display_message = "Record exists, checking if there are changes"
                print(display_message)

                existing_username, existing_full_name, existing_profile_pic_url = existing_data

                if (existing_username != row["user_username"] or 
                    existing_full_name != row["user_full_name"]):
                    display_message = "Change found, updating the record"
                    print(display_message)
                    # row["user_last_updated = row["user_last_updated.strftime('%Y-%m-%d %H:%M:%S')

                    cursor.execute(update_query, (row["user_username"], row["user_full_name"], row["user_profile_pic_url"], row["user_id"]))
                else:
                    display_message = "No changed found"
                    print(display_message)



# Function to insert collection with conflict handling

def insert_record_with_conflict(session, target_table, unique_columns, data):
    try:


        # Create the insert statement using the provided dictionary
        insert_stmt = insert(target_table).values(data).on_conflict_do_nothing(
            index_elements=unique_columns  # Replace with your unique constraint columns
        )

        # Execute the insert statement
        result = session.execute(insert_stmt)

        # If no rows were inserted (i.e., conflict occurred), log it
        if result.rowcount == 0:
            logger.warn(f"Conflict found for collection '{data[unique_columns[0]]}' and account '{data[unique_columns[1]]}'. No new data inserted.")

    except Exception as e:
        # Log any unexpected errors
        logger.error(f"Error inserting collection '{data[unique_columns[0]]}': {e}")
        session.rollback()

def upsert_record(session, target_table, unique_columns, data, new_values):
    try:
        # Create the insert statement using the provided dictionary
        insert_stmt = insert(target_table).values(data).on_conflict_do_update(
            index_elements=unique_columns,  # Replace with your unique constraint columns
            set_={key: data[key] for key in data if key in new_values}  # Update all fields except the key
            )

        # Execute the insert statement
        result = session.execute(insert_stmt)

        # If no rows were inserted (i.e., conflict occurred), log it
        if result.rowcount == 0:
            print(f"No records found for '{unique_columns[0]}': '{data[unique_columns[0]]}'.")


    except Exception as e:
        # Log any unexpected errors
        print(f"Error inserting record '{unique_columns[0]}':'{data[unique_columns[0]]}': {e}")
        logger.error(f"Error inserting record '{unique_columns[0]}':'{data[unique_columns[0]]}': {e}")
        session.rollback()



# Function to insert data into RawstdInstaDownloadSavedReelsDetails table
def insert_reel_detail(data_dict, session):
    try:
        # Create an instance of RawstdInstaDownloadSavedReelsDetails using the dictionary
        reel_detail_entry = RawstdInstaDownloadSavedReelsDetails(**data_dict)

        # Add the entry to the session
        session.add(reel_detail_entry)

        # Commit the session to insert the data into the database
        session.commit()

        print("Data inserted successfully into RawstdInstaDownloadSavedReelsDetails table.")

    except SQLAlchemyError as e:
        # Handle any database errors (e.g., integrity constraints violation, etc.)
        print(f"Error inserting data: {e}")
        session.rollback() 