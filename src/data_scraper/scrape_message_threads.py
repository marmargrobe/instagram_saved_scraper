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


threads = insta_client.api.direct_threads()
print(threads)

# Print the messages in the threads
# for thread in threads:
#     print(f"Thread ID: {thread.id}")
#     print(f"Thread with {thread.users[0].username}:")
#     for message in thread.messages:
#         print(f"Message from {message.user.username}: {message.text}")