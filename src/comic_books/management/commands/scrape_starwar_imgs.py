# src/comic_books/management/commands/scrape_starwar_imgs.py

import requests
from bs4 import BeautifulSoup
import os
import urllib.request
import logging
from urllib.error import URLError, HTTPError
import ssl
import certifi
from PIL import Image
from io import BytesIO

# Set up logging configuration
logging.basicConfig(
    filename='scraper.log', 
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Function to download image using urlopen (supports SSL context) and save as .webp
def download_image(image_url, folder="images", custom_name="StarWarsMarvel", page_number=1, image_index=1, dpi=(300, 300), convert_to_webp=True):
    if not os.path.exists(folder):
        os.makedirs(folder)
    
    # Create custom filename for each image
    image_name = f"{custom_name}-{page_number:03d}"  # E.g., StarWarsMarvel-001 for page 1, image 1
    
    # Modify the extension to .webp if converting to webp
    if convert_to_webp:
        image_name = image_name + ".webp"
    
    image_path = os.path.join(folder, image_name)
    
    try:
        logging.info(f"Attempting to download image from {image_url}")
        
        # Create an unverified SSL context if needed
        ssl_context = ssl._create_unverified_context()
        
        # Open the URL and read the image content
        with urllib.request.urlopen(image_url, context=ssl_context) as response:
            image_data = response.read()
        
        # Open the image with Pillow
        image = Image.open(BytesIO(image_data))
        
        # Convert to RGB mode if needed (for WebP and consistent DPI saving)
        if image.mode != "RGB":
            image = image.convert("RGB")
        
        # Save the image in .webp format and set DPI explicitly
        image.save(image_path, "WEBP", dpi=dpi)
        
        logging.info(f"Successfully downloaded and saved {image_name} as .webp with {dpi[0]} DPI")
    
    except (URLError, HTTPError) as e:
        logging.error(f"Failed to download {image_name} from {image_url}. Error: {e}")
    except Exception as e:
        logging.error(f"An unexpected error occurred while downloading {image_name}. Error: {e}")

# Function to scrape images from a specific page
def scrape_star_wars_images(url, page_number=1):
    try:
        logging.info(f"Fetching webpage: {url}")
        # Use certifi to handle SSL verification
        response = requests.get(url, verify=certifi.where())
        
        if response.status_code != 200:
            logging.error(f"Failed to fetch webpage: {url} with status code {response.status_code}")
            return
        
        logging.info(f"Successfully fetched webpage: {url}")
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Find all <figure> elements with the class "pi-item pi-image"
        figures = soup.find_all('figure', class_='pi-item pi-image')

        if not figures:
            logging.warning(f"No image figures found on page: {url}")
        
        # Iterate over the figures and download each image
        for index, figure in enumerate(figures, start=1):
            # Find the 'a' tag inside the figure and get the 'href'
            anchor = figure.find('a')
            if anchor and 'latest' in anchor['href']:
                # Full image URL from the 'href' attribute
                image_url = anchor['href']
                
                # Download the image and save it as .webp with a custom name
                download_image(image_url, page_number=page_number, image_index=index, dpi=(300, 300), convert_to_webp=True)
    
    except requests.RequestException as e:
        logging.error(f"Error fetching the webpage: {url}. Error: {e}")
    except Exception as e:
        logging.error(f"An unexpected error occurred during scraping. Error: {e}")

# Function to scrape all 107 pages
def scrape_all_star_wars_pages(base_url, start_page=1, end_page=107):
    for page_number in range(start_page, end_page + 1):
        # Generate the URL for each page
        url = f"{base_url}_{page_number}"
        logging.info(f"Scraping page: {url}")
        
        # Scrape the images from the current page
        scrape_star_wars_images(url, page_number=page_number)

# Base URL for the comics
base_url = "https://starwars.fandom.com/wiki/Star_Wars_(1977)"

# Scrape all pages from 1 to 107
# scrape_all_star_wars_pages(base_url, start_page=1, end_page=107)
scrape_all_star_wars_pages(base_url, start_page=3, end_page=107)
