from datetime import datetime
from bs4 import BeautifulSoup
import glob
import os


# Function to parse datetime
def parse_datetime(time_string):
    try:
        return datetime.strptime(time_string, '%b %d, %Y %I:%M %p')
    except ValueError:
        return None  # Return None if the time format is incorrect
    


def read_html_file(saved_collections_file_path):
    try:
        # Attempt to open and read the file
        with open(saved_collections_file_path, "r", encoding="utf-8") as file:
            soup = BeautifulSoup(file, "html.parser")
        return soup

    except FileNotFoundError:
        # Handle file not found error
        print(f"Error: The file at path '{saved_collections_file_path}' was not found.")
        return None  # Return None or you can handle it in another way (e.g., logging)

    except Exception as e:
        # Handle any other errors
        print(f"An error occurred while reading the file: {e}")
        return None

# saved_target="your_instagram_activity/saved/saved_locations.html"
# saved_target="your_instagram_activity/saved/saved_posts.html"
# saved_target="your_instagram_activity/saved/saved_collections.html"


def get_soup_from_file_path(target_profile, saved_target="your_instagram_activity/saved/saved_collections.html"):
    """
    This function processes the file path to locate the target profile's saved collections HTML file,
    reads it, and returns the BeautifulSoup object.

    Parameters:
    - file_path (str): The directory where downloaded profiles are located.
    - target_profile (str): The profile you are looking for.
    - saved_target (str): The path to the saved collections HTML file relative to the profile.

    Returns:
    - BeautifulSoup: Parsed HTML content from the saved collections HTML file.
    """
    # Get the list of profiles from the folder path
    # Get the current script's directory
    script_dir = os.path.dirname(os.path.abspath(__file__))

    file_path = os.path.join(script_dir, 'downloaded')
    print(file_path)
    list_profiles = [x.replace(file_path, "") for x in glob.glob(f"{file_path}/*")]
    
    # Find the target profile
    num = 0
    for p in list_profiles:
        if target_profile in p:
            break
        else:
            num += 1
    target_profile_file = list_profiles[num]
    
    # Set the path for the saved collections file
    saved_collections_file_path = f"{file_path}/{target_profile_file}/{saved_target}"

    # Read the HTML file

    return read_html_file(saved_collections_file_path=saved_collections_file_path)
