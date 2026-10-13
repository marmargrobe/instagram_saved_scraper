"""
Any additional transformation scripts will go here. For instance, you could have one that aggregates the data or another that normalizes or filters it.
"""
from src.data_cleaner.utils_transformation import parse_dict_object, extract_key, extract_hashtags, extract_location_from_caption
from sqlalchemy.orm import sessionmaker
from src.helper.model import engine, CleanInstaSavedReel, RawstdInstaSavedReel, CleanInstaUser, CleanInstaUserTag
from src.helper.utils_model import upsert_record, insert_record_with_conflict
import spacy
import json

Session = sessionmaker(bind=engine)
session = Session()

try:
    # Fetch all records
    rawstd_insta_saved_reels = session.query(RawstdInstaSavedReel).all()

finally:
    # Close the session
    session.close()

compute_transformations = True
# switch on which transformations to do
compute_extract_hashtags = False
compute_extract_locations = False
compute_extract_user = False
compute_extract_usertagged = False
compute_extract_locations_from_caption = False

compute_extract_hashtags = True
compute_extract_locations = True
compute_extract_user = True
# compute_extract_usertagged = True
compute_extract_locations_from_caption = True

if len(rawstd_insta_saved_reels) > 0:
    compute_transformations = True
if compute_transformations:
    if compute_extract_user:
        # id VARCHAR(50) PRIMARY KEY,
        # username VARCHAR(50),
        # full_name VARCHAR(100),
        # profile_pic_url VARCHAR,
        # Manipulate the `all_reels` objects to add parsed fields
        for reel in rawstd_insta_saved_reels:
            # Parse the user dictionary
            parsed_user = parse_dict_object(reel.user)

            # Add attributes based on the parsed user data
            reel.user_id = extract_key(parsed_user, 'pk') if parsed_user is not None else None
            reel.user_pk = reel.user_id  # Duplicate user_id as user_pk if needed
            reel.user_username = extract_key(parsed_user, 'username') if parsed_user is not None else None
            reel.user_full_name = extract_key(parsed_user, 'full_name') if parsed_user is not None else None
            reel.user_profile_pic_url = extract_key(parsed_user, 'profile_pic_url') if parsed_user is not None else None
    if compute_extract_usertagged:
        # id VARCHAR(50) PRIMARY KEY,
        # username VARCHAR(50),
        # full_name VARCHAR(100),
        # profile_pic_url VARCHAR,
        # tagged_by_insta_user_id VARCHAR(50),
        # insta_saved_reels_id 
        for reel in rawstd_insta_saved_reels:
            # Parse the usertagged dictionary if available
            parsed_usertagged = parse_dict_object(reel.usertagged) if hasattr(reel, 'usertagged') else None

            # Check for 'user' within the parsed usertagged data and extract fields if present
            if parsed_usertagged and 'user' in parsed_usertagged:
                usertagged_user = parsed_usertagged['user']
                reel.usertagged_id = extract_key(usertagged_user, 'pk')
                reel.usertagged_username = extract_key(usertagged_user, 'username')
                reel.usertagged_full_name = extract_key(usertagged_user, 'full_name')
                reel.usertagged_profile_pic_url = extract_key(usertagged_user, 'profile_pic_url')
            else:
                # If `usertagged` or `user` key is missing, assign None to new attributes
                reel.usertagged_id = None
                reel.usertagged_username = None
                reel.usertagged_full_name = None
                reel.usertagged_profile_pic_url = None
    if compute_extract_hashtags:
        # Apply the function to the 'caption_text' column
        # Function to extract hashtags from a caption text

        # Manipulate the `all_reels` objects to add hashtags
        for reel in rawstd_insta_saved_reels:
            # Ensure caption_text exists, then extract hashtags
            if hasattr(reel, 'caption_text'):
                reel.hashtags = extract_hashtags(reel.caption_text)
            else:
                reel.hashtags = []
    if compute_extract_locations_from_caption:
        nlp = spacy.load('en_core_web_sm')
        for reel in rawstd_insta_saved_reels:
            # Ensure caption_text exists, then extract hashtags
            if hasattr(reel, 'caption_text'):
                reel.locations_from_caption = extract_location_from_caption(reel.caption_text, nlp)
            else:
                reel.locations_from_caption = []

    # function to extract location data
    if compute_extract_locations:

        # Apply parsing and extraction functions to the location column
        for reel in rawstd_insta_saved_reels:
            # Parse the location if it exists
            reel.parsed_location = parse_dict_object(reel.location)
            
            # Extract city, name, longitude, and latitude from the parsed location
            reel.city = extract_key(reel.parsed_location, 'city') if reel.parsed_location else None
            reel.location_name = extract_key(reel.parsed_location, 'name') if reel.parsed_location else None
            reel.lng = extract_key(reel.parsed_location, 'lng') if reel.parsed_location else None
            reel.lat = extract_key(reel.parsed_location, 'lat') if reel.parsed_location else None


compute_extract_user = False
compute_extract_usertagged = False

if compute_extract_user:            
    for reel in rawstd_insta_saved_reels:
        # Extract user data
        user = reel.user
        user_id = user['pk']
        username = user['username']
        full_name = user['full_name']
        profile_pic_url = user['profile_pic_url']

        # Check if user already exists in InstaUser
        existing_user = session.query(CleanInstaUser).filter_by(id=user_id).first()
        
        if not existing_user:
            # Create a new CleanInstaUser object if user doesn't exist
            new_user = CleanInstaUser(
                id=user_id,
                username=username,
                full_name=full_name,
                profile_pic_url=profile_pic_url
            )
            session.add(new_user)

        # Now handle inserting tagged user data into CleanInstaUserTag
        if 'usertags' in reel and reel.usertags:
            for usertag in reel.usertags:
                tagged_user = usertag.get('user', {})
                tagged_user_id = tagged_user.get('pk')
                tagged_username = tagged_user.get('username')
                tagged_full_name = tagged_user.get('full_name')
                tagged_profile_pic_url = tagged_user.get('profile_pic_url')

                # Check if the tagged user already exists in CleanInstaUser
                existing_tagged_user = session.query(CleanInstaUser).filter_by(id=tagged_user_id).first()

                if not existing_tagged_user:
                    # Create a new CleanInstaUser object for the tagged user
                    new_tagged_user = CleanInstaUser(
                        id=tagged_user_id,
                        username=tagged_username,
                        full_name=tagged_full_name,
                        profile_pic_url=tagged_profile_pic_url
                    )
                    session.add(new_tagged_user)

                # Now insert into CleanInstaUserTag
                new_usertagged = CleanInstaUserTag(
                    id=tagged_user_id,
                    username=tagged_username,
                    full_name=tagged_full_name,
                    profile_pic_url=tagged_profile_pic_url,
                    tagged_by_insta_user_id=user_id,  # This would be the user who tagged
                    insta_saved_reels_id=reel.id
                )
                session.add(new_usertagged)

# clean.insta_saved_reels.user_pk references clean.insta_user, so add each reel's poster first
for reel in rawstd_insta_saved_reels:
    if reel.user_pk:
        user_data = {
            "id": reel.user_pk,
            "username": reel.user_username,
            "full_name": reel.user_full_name,
            "profile_pic_url": reel.user_profile_pic_url,
        }
        insert_record_with_conflict(session=session, target_table=CleanInstaUser, unique_columns=["id"], data=user_data)
session.commit()

columns_updated = ["last_updated", "hashtags","lng", "lat","city","location_name", "locations_from_caption"]
if compute_extract_locations or compute_extract_hashtags or compute_extract_locations_from_caption:
    # Iterate through all_reels and insert data into CleanInstaSavedReel table
    for reel in rawstd_insta_saved_reels:
        # user = reel.user
        user_pk = reel.user_pk
        reel_data = {
            "id": reel.id,
            "pk": reel.pk,
            "code": reel.code,
            "taken_at": reel.taken_at,
            "media_type": reel.media_type,
            "image_versions2": json.dumps(reel.image_versions2),
            "product_type": reel.product_type,
            "thumbnail_url": reel.thumbnail_url,
            "location": json.dumps(reel.location),
            "user": json.dumps(reel.user),
            "comment_count": reel.comment_count,
            "comments_disabled": reel.comments_disabled,
            "like_count": reel.like_count,
            "play_count": reel.play_count,
            "has_liked": reel.has_liked,
            "caption_text": reel.caption_text,
            "usertags": json.dumps(reel.usertags),
            "sponsor_tags": json.dumps(reel.sponsor_tags),
            "video_url": reel.video_url,
            "view_count": reel.view_count,
            "video_duration": reel.video_duration,
            "resources": json.dumps(reel.resources),
            "clips_metadata": json.dumps(reel.clips_metadata),
            "last_updated": reel.last_updated,
            "hashtags": reel.hashtags,
            "lng": reel.lng,
            "lat": reel.lat,
            "city": reel.city,
            "location_name": reel.location_name,
            "user_pk": user_pk,
            "locations_from_caption": reel.locations_from_caption
            }
        print(reel_data)
        upsert_record(session=session, target_table=CleanInstaSavedReel, unique_columns=["id"], data=reel_data, new_values=columns_updated)
    # Commit the transaction to insert all records
    session.commit()

    print(f"Inserted {len(rawstd_insta_saved_reels)} reels into the 'insta_saved_reels' table in the 'clean' schema.")

