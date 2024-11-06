import json
import codecs
import datetime
import os.path
import argparse
import csv
from instagrapi import Client

def create_map_link(coordinates):
    if len(str(coordinates[0])) > 0 and len(str(coordinates[1])) > 0:
        return 'https://www.google.com/maps?q=' + str(coordinates[0]) + ',' + str(coordinates[1])
    else:
        return ''

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

def onlogin_callback(api, new_settings_file):
    cache_settings = api.get_settings()
    with open(new_settings_file, "w") as outfile:
        json.dump(cache_settings, outfile, default=to_json)
        print("SAVED: {0!s}".format(new_settings_file))

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Login callback and save settings"
    )
    parser.add_argument("-u", "--username", dest="username", type=str, required=True)
    parser.add_argument("-p", "--password", dest="password", type=str, required=True)
    parser.add_argument("-c", "--collection", dest="collection", type=str, required=True)
    parser.add_argument("-o", "--output", dest="output", type=str, required=True)

    args = parser.parse_args()

    settings_file = "credentials.json"
    api = Client()

    if os.path.isfile(settings_file):
        with open(settings_file) as file_data:
            cached_settings = json.load(file_data, object_hook=from_json)
        print("Reusing settings: {0!s}".format(settings_file))
        api.set_settings(cached_settings)
        api.login(args.username, args.password)
    else:
        # Login and save session
        api.login(args.username, args.password)
        onlogin_callback(api, settings_file)

    # Display cookie expiry
    cookie_expiry = datetime.datetime.fromtimestamp(api.cookie_dict.get('auth_expires', 0))
    print("Cookie Expiry: {0!s}".format(cookie_expiry.strftime("%Y-%m-%dT%H:%M:%SZ")))

    print("==== Starting to fetch saved posts data ====")

    saved_collection = []
    
    for media in api.saved_medias():
        saved_collection.append(media.dict())

    field_names = [
        "#",
        "link",
        "location_short_name",
        "facebook_places_id",
        "location_name",
        "address",
        "city",
        "location_lng",
        "location_lat",
        "location_map_link",
        "lng",
        "lat",
        "map_link",
        "full_name_op",
        "username_op",
        "caption",
    ]

    count = 0
    res = []

    print("==== Saving data to file ====")

    for media in saved_collection:
        if args.collection in media.get("saved_collection_ids", []):
            count += 1
            location = media.get("location", {})
            res.append({
                "#": count,
                "link": "https://www.instagram.com/p/" + media.get("code"),
                "location_short_name": location.get("short_name", ""),
                "facebook_places_id": location.get("facebook_places_id", ""),
                "location_name": location.get("name", ""),
                "address": location.get("address", ""),
                "city": location.get("city", ""),
                "location_lng": location.get("lng", ""),
                "location_lat": location.get("lat", ""),
                "location_map_link": create_map_link([location.get("lat", ""), location.get("lng", "")]),
                "lng": media.get("lng", ""),
                "lat": media.get("lat", ""),
                "map_link": create_map_link([media.get("lat", ""), media.get("lng", "")]),
                "full_name_op": media.get("user", {}).get("full_name", ""),
                "username_op": media.get("user", {}).get("username", ""),
                "caption": media.get("caption_text", ""),
            })

    with open(args.output, "w", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=field_names)
        writer.writeheader()
        writer.writerows(res)
