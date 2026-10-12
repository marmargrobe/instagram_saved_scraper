from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm import aliased
from src.helper.model import engine, RawstdInstaDownloadSavedReels, RawstdInstaDownloadSavedReelsDetails
from datetime import datetime
import re
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
from src.helper.utils_model import insert_reel_detail
import os
import time
import random
from src.data_scraper_downloads.utils import get_proxies, get_driver_with_proxy


# Assuming your session is created and engine is initialized
Session = sessionmaker(bind=engine)
session = Session()

# Aliasing RawstdInstaDownloadSavedReelsDetails for the subquery
reels_details_alias = aliased(RawstdInstaDownloadSavedReelsDetails)

# Query to select records from RawstdInstaDownloadSavedReels where the id and insta_account do not exist in RawstdInstaDownloadSavedReelsDetails
query = session.query(RawstdInstaDownloadSavedReels).filter(
    ~session.query(reels_details_alias.id, reels_details_alias.insta_account).filter(
        reels_details_alias.reel_id == RawstdInstaDownloadSavedReels.id,
        reels_details_alias.insta_account == RawstdInstaDownloadSavedReels.insta_account
    ).exists()
)

# Execute the query
results = query.all()

# Define the script name and runtime
script_name = os.path.basename(__file__)
last_updated_time = datetime.now()

# List of free proxies
# Read proxies from the file
proxies = get_proxies()
print(proxies)


# Initialize WebDriver with proxy
driver, current_proxy = get_driver_with_proxy(proxies)
print(f"Using proxy: {current_proxy}")

# Process each result from RawstdInstaDownloadSavedReels
total_results = len(results)
print(f"Total records to process: {str(total_results)}")
cnt = 1
issue_urls = []

for result in results:
    reel_id = result.id
    url = result.reel_url
    target_profile = result.insta_account

    print("Fetching data")
    try:
        # Open the URL
        driver.get(url)

        # Wait for the page to load by ensuring a key element (like the caption) is available
        wait = WebDriverWait(driver, 20)
        wait.until(EC.presence_of_element_located((By.XPATH, "//meta[@property='og:description']")))

        # Parse the HTML
        rendered_html = driver.page_source
        soup = BeautifulSoup(rendered_html, "html.parser")

        # Extract data
        caption_tag = soup.find("meta", property="og:description")
        caption = caption_tag["content"] if caption_tag else None
        hashtags = re.findall(r'#(\w+)', caption) if caption else []
        location_tag = soup.find("meta", property="og:location")
        location = location_tag["content"] if location_tag else None
        user_name_tag = soup.find("meta", property="og:title")
        user_name = user_name_tag["content"].split(" on Instagram")[0] if user_name_tag else None

        # Prepare and insert data
        reel_details_data = {
            "caption_text": caption,
            "hashtags": hashtags,
            "location_name": location,
            "user_name": user_name,
            "reel_id": reel_id,
            "reel_url": url,
            "insta_account": target_profile,
            "python_script": script_name,
            "python_runtime": last_updated_time
        }
        insert_reel_detail(session=session, data_dict=reel_details_data)
        cnt += 1

        # Restart driver periodically
        if cnt % 500 == 0:
            print("Restarting driver...")
            driver.quit()
            driver, current_proxy = get_driver_with_proxy(proxies)

        time.sleep(random.uniform(1, 3))

    except Exception as e:
        print(f"Error processing URL {url} with proxy {current_proxy}: {e}")
        issue_urls.append(url)

        # Reinitialize WebDriver with a new proxy after too many issues
        if len(issue_urls) > 10:
            print("Switching proxy...")
            driver.quit()
            driver, current_proxy = get_driver_with_proxy(proxies)
            issue_urls = []  # Reset tracker

        continue

# Close driver and session
driver.quit()
session.close()
