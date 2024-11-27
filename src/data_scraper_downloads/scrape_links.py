from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm import aliased
from src.helper.model import engine, RawstdInstaDownloadSavedReels, RawstdInstaDownloadSavedReelsDetails
from datetime import datetime
import re
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
from src.helper.utils_model import insert_reel_detail
import os
import time
import random



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
proxies = [
    "192.168.1.123:8080",
    "192.168.1.124:9090",
    "192.168.1.125:3128"
]

# Select a random proxy
selected_proxy = random.choice(proxies)



# Configure ChromeOptions for headless scraping
chrome_options = Options()
chrome_options.add_argument("--headless")  # Run in headless mode
chrome_options.add_argument("--disable-gpu")  # Disable GPU usage
chrome_options.add_argument("--no-sandbox")  # For Linux compatibility
# Configure ChromeOptions with the selected proxy
chrome_options.add_argument(f"--proxy-server=http://{selected_proxy}")

# Initialize WebDriver (Selenium Manager will handle chromedriver download)
service = Service()
driver = webdriver.Chrome(service=service, options=chrome_options)

# WebDriverWait setup to wait for elements to load
wait = WebDriverWait(driver, 20)  # Wait for up to 10 seconds for elements to be available

# Process each result from RawstdInstaDownloadSavedReels
total_results = len(results)
print(f"Total records to process: {str(total_results)}")
cnt = 1
issue_urls = []
for result in results:
    reel_id = result.id
    url = result.reel_url
    target_profile = result.insta_account
    
    # Open the URL
    print("Fetching data")
    try:
        # Open the URL
        driver.get(url)

        # Wait for the page to load by ensuring a key element (like the caption) is available
        wait.until(EC.presence_of_element_located((By.XPATH, "//meta[@property='og:description']")))

        # Extract the rendered HTML
        rendered_html = driver.page_source

        # Parse the rendered HTML with BeautifulSoup
        soup = BeautifulSoup(rendered_html, "html.parser")

        # Extract Caption
        caption = None
        caption_tag = soup.find("meta", property="og:description")
        if caption_tag:
            caption = caption_tag["content"]
        else:
            # If the <meta> tag is not found, try looking for a <div> with class C4VMK (Instagram caption class)
            caption_element = soup.find("div", class_="C4VMK")
            if caption_element:
                caption = caption_element.get_text(strip=True)

        # Extract Hashtags
        hashtags = []
        caption_hashtags = re.findall(r'#(\w+)', caption) if caption else []
        hashtags.extend(caption_hashtags)

        # Extract Location (if available)
        location_tag = soup.find("meta", property="og:location")
        location = location_tag["content"] if location_tag else None

        # Extract user Name
        user_name_tag = soup.find("meta", property="og:title")
        user_name = user_name_tag["content"].split(" on Instagram")[0] if user_name_tag else None

        # Prepare data for insertion
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

        # Insert the data into the database
        print("Inserting data into table")
        records_remaining = total_results - cnt
        print("Records remaining: " + str(records_remaining))
        insert_reel_detail(session=session, data_dict=reel_details_data)
        cnt+=1
        # Add a random delay between requests to avoid rate limiting
        if cnt % 500 == 0:  # Restart every 500 records
            driver.quit()
            driver = webdriver.Chrome(service=service, options=chrome_options)
        time.sleep(random.uniform(1, 3))

    except Exception as e:
        print(f"Error processing URL {url}: {e}")
        issue_urls.append(url)
        # if too many issues
        if len(issue_urls) > 100:
            driver.quit()
            driver = webdriver.Chrome(service=service, options=chrome_options)

        continue  # Skip this URL and move to the next one


# Close the driver and session
driver.quit()
session.close()
