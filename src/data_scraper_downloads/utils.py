from datetime import datetime
from bs4 import BeautifulSoup
import glob
import os
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options


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

    # Export folders are named instagram-<profile>-<YYYY-MM-DD>-<id>, so sorting by name
    # puts the newest export for the profile last
    profile_dirs = sorted(glob.glob(f"{file_path}/instagram-{target_profile}-*"))
    if not profile_dirs:
        print(f"Error: no export folder found for '{target_profile}' in '{file_path}'.")
        return None
    target_profile_file = profile_dirs[-1]
    print(f"Using export: {os.path.basename(target_profile_file)}")

    # Set the path for the saved collections file
    saved_collections_file_path = f"{target_profile_file}/{saved_target}"

    # Read the HTML file

    return read_html_file(saved_collections_file_path=saved_collections_file_path)


def get_proxies():
    # Define the path to the proxy file relative to the script's directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    proxy_file_path = os.path.join(script_dir, "proxy/proxies_us.txt")
    
    try:
        # Read proxies from the file, ensuring no blank or invalid lines are included
        with open(proxy_file_path, "r") as proxy_file:
            proxies = [line.strip() for line in proxy_file if line.strip() and ":" in line]
        
        # Ensure the file contains at least one valid proxy
        if not proxies:
            raise ValueError("No valid proxies found in the file.")
    except FileNotFoundError:
        print(f"Proxy file not found at {proxy_file_path}.")
        proxies = []
    except Exception as e:
        print(f"Error reading proxy file: {e}")
        proxies = []

    return proxies 

# Function to get WebDriver with proxy
def get_driver_with_proxy(proxies):
    selected_proxy = random.choice(proxies)
    chrome_options = Options()
    chrome_options.add_argument("--headless")  # Run in headless mode
    chrome_options.add_argument("--disable-gpu")  # Disable GPU usage
    chrome_options.add_argument("--no-sandbox")  # For Linux compatibility
    chrome_options.add_argument(f"--proxy-server=http://{selected_proxy}")  # Configure proxy
    service = Service()
    return webdriver.Chrome(service=service, options=chrome_options), selected_proxy

