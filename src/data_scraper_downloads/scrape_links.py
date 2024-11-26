from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup
import time
import re
# TODO
# 1. read in data from rawstd.insta_download_saved_reels
# 2. for each link do this code
# 3. insert results into new table with reel id pk
# rawstd.insta_download_saved_reels_details
# caption
# reel_id
# hashtags
# location
# user_name

# Configure ChromeOptions for headless scraping
chrome_options = Options()
chrome_options.add_argument("--headless")  # Run in headless mode
chrome_options.add_argument("--disable-gpu")  # Disable GPU usage
chrome_options.add_argument("--no-sandbox")  # For Linux compatibility

# Initialize WebDriver (Selenium Manager will handle chromedriver download)
service = Service()
driver = webdriver.Chrome(service=service, options=chrome_options)

# Target Instagram reel URL
url = "https://www.instagram.com/reel/C8lh0-hxPK8/"

# Open the URL
driver.get(url)

# Wait for the page to load (adjust timing as needed)
time.sleep(5)

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
caption_hashtags = re.findall(r"#\w+", caption) if caption else []
hashtags.extend(caption_hashtags)

# Extract Location (if available)
location_tag = soup.find("meta", property="og:location")
location = location_tag["content"] if location_tag else "No location available"

# Extract user Name
user_name_tag = soup.find("meta", property="og:title")
user_name = user_name_tag["content"].split(" on Instagram")[0] if user_name_tag else "No user name found"

# Print the results
print("Caption:", caption if caption else "No caption found")
print("Hashtags:", hashtags if hashtags else "No hashtags found")
print("Location:", location)
print("User Name:", user_name)

# Close the driver
driver.quit()
