import json
import codecs
import datetime
from instagrapi import Client
import time


def to_json(python_object):
    if isinstance(python_object, bytes):
        return {
            "__class__": "bytes",
            "__value__": codecs.encode(python_object, "base64").decode(),
        }
    raise TypeError(repr(python_object) + " is not JSON serializable")


def from_json(json_object):
    if "__class__" in json_object and json_object["__class__"] == "bytes":
        return codecs.decode(json_object["__value__"].encode(), "base64")
    return json_object


class InstaClient:
    def __init__(self, username, password, stored_session=None):
        self.username = username
        self.password = password
        self.api = Client()
        self.stored_session = stored_session

    def login(self):
        if self.stored_session:
            cached_settings = json.loads(self.stored_session, object_hook=from_json)
            self.api.set_settings(cached_settings)
            self.api.login(self.username, self.password)
            print("Reusing stored session data.")
        else:
            self.api.login(self.username, self.password)
            self.stored_session = json.dumps(self.api.get_settings(), default=to_json)
            print("New session created and stored in memory.")

    def get_cookie_expiry(self):
        cookie_expiry = datetime.datetime.fromtimestamp(self.api.cookie_dict.get('auth_expires', 0))
        return cookie_expiry.strftime("%Y-%m-%dT%H:%M:%SZ")

def fetch_all_saved_medias(insta_client, collection_pk, total_medias, batch_size=100):
    all_medias = []
    last_media_pk = 0

    while len(all_medias) < total_medias:
        # Fetch the media for the current batch
        medias = insta_client.api.collection_medias(collection_pk, amount=batch_size, last_media_pk=last_media_pk)

        if not medias:
            print("No more media to fetch.")
            break  # Exit the loop if no more media is returned

        all_medias.extend(medias)
        
        # Update the last media pk for pagination
        last_media_pk = medias[-1].pk  # Assuming Media object has 'pk' attribute

        print(f"Fetched {len(medias)} media items. Total collected: {len(all_medias)}")

        # Optional: Add a delay to avoid hitting rate limits
        time.sleep(1)  # Sleep for 1 second

    return all_medias