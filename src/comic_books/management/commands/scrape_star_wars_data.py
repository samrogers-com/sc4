import requests
from bs4 import BeautifulSoup
import csv
import re
import os
import logging
from datetime import datetime

# Set up logging
logging.basicConfig(
    filename='scraper.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Function to fetch and parse webpage
def fetch_webpage(url):
    try:
        logging.info(f"Fetching webpage: {url}")
        response = requests.get(url)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        logging.info(f"Successfully fetched and parsed webpage: {url}")
        return soup
    except Exception as e:
        logging.error(f"Error fetching webpage: {e}")
        return None

# Function to extract issue number from <h1> tag after (1977)
def extract_issue_number(soup):
    try:
        # Find the <h1> tag with the class "page-header__title"
        h1_tag = soup.find('h1', class_='page-header__title')
        
        if h1_tag:
            # Use regex to find the issue number after "(1977)"
            match = re.search(r'\(1977\)\s*(\d{1,3})', h1_tag.text)
            if match:
                issue_number = match.group(1).strip()  # Extract and strip any extra spaces
                logging.info(f"Extracted Issue Number: {issue_number}")
                return issue_number

        logging.error("Issue number not found in <h1> tag.")
        return "Unknown"
    except Exception as e:
        logging.error(f"Error extracting issue number: {e}")
        return "Unknown"

# Function to extract title after the issue number in the <div class="quote"> section
def extract_title(soup):
    try:
        # Find the <div> tag with class "quote"
        quote_div = soup.find('div', class_='mw-parser-output')
        
        if quote_div:
            # Find the <i><b> tag where the title is expected
            title_element = quote_div.find_next('i').find_next('b')
        else:
            title_element = quote_div.find_next('i').find_next('b')
            if title_element:
                # Extract text and clean it
                title_text = title_element.text.strip()

                # Regex to handle cases like "Star Wars 3: Title" or "Star Wars 3. Title"
                match = re.search(r'Star Wars \d{1,3}[:.]?\s*(.*)', title_text)
                
                if match:
                    title = match.group(1).strip()  # Extract the title part after the issue number
                    logging.info(f"Extracted Title: {title}")
                    return title

        logging.error("Title not found in <div class='quote'>.")
        return "Unknown"
    except Exception as e:
        logging.error(f"Error extracting title: {e}")
        return "Unknown"

# Function to extract the release date
def extract_release_date(soup):
    try:
        release_date_element = soup.find('h3', string='Publication date')
        if release_date_element:
            release_date_value = release_date_element.find_next('div').get_text(strip=True)
            release_date_value = release_date_value.split('[')[0].strip()  # Remove anything after the date, like [1]
            
            # Ensure there's a space after the comma before parsing
            if "," in release_date_value and not release_date_value.endswith(", "):
                release_date_value = release_date_value.replace(",", ", ")

            release_date = datetime.strptime(release_date_value, "%B %d, %Y").strftime("%m/%d/%Y")
            logging.info(f"Extracted Release Date: {release_date}")
            return release_date
        else:
            logging.error("Publication date not found.")
            return "Unknown"
    except Exception as e:
        logging.error(f"Error parsing release date: {e}")
        return "Unknown"

# Function to extract the description
def extract_description(soup):
    try:
        description_header = soup.find('span', {'id': 'Plot_summary'})
        if description_header:
            description = description_header.find_parent('h2').find_next('p').get_text(separator=' ').strip()
            logging.info(f"Extracted Description: {description[:100]}...")  # Log first 100 characters
            return description
        else:
            logging.error("Description not found.")
            return "No description available."
    except Exception as e:
        logging.error(f"Error extracting description: {e}")
        return "No description available."

# Function to save the data to CSV (append mode)
def save_to_csv(data, directory='import', filename='star_wars_comics.csv'):
    if not os.path.exists(directory):
        os.makedirs(directory)  # Create the directory if it doesn't exist
    
    file_path = os.path.join(directory, filename)
    
    try:
        # Write to CSV in append mode
        file_exists = os.path.isfile(file_path)
        with open(file_path, mode='a', newline='', encoding='utf-8') as file:
            writer = csv.DictWriter(file, fieldnames=['issue_number', 'title', 'release_date', 'description'])
            
            # Write header only if the file does not exist
            if not file_exists:
                writer.writeheader()
            
            # Write the data row
            writer.writerow(data)
        logging.info(f"Data successfully saved to {file_path}")
    except Exception as e:
        logging.error(f"Error writing to CSV: {e}")

# Function to scrape data from the webpage
def scrape_star_wars_data(url):
    soup = fetch_webpage(url)
    
    if soup:
        issue_number = extract_issue_number(soup)
        title = extract_title(soup)
        release_date = extract_release_date(soup)
        description = extract_description(soup)
        
        # Return the extracted data
        return {
            'issue_number': issue_number,
            'title': title,
            'release_date': release_date,
            'description': description
        }
    return None

# Function to scrape data from all 107 pages and append to one CSV
def scrape_all_star_wars_data(base_url, start_page=1, end_page=107):
    for page_number in range(start_page, end_page + 1):
        # Generate the URL for each page
        url = f"{base_url}_{page_number}"
        logging.info(f"Scraping page: {url}")
        
        # Scrape the data from the current page
        data = scrape_star_wars_data(url)
        
        if data:
            # Append the data to a single CSV file
            save_to_csv(data, filename='star_wars_comics.csv')

# Main function to run the scraper and save data
def main():
    base_url = "https://starwars.fandom.com/wiki/Star_Wars_(1977)"
    
    # Scrape all pages from 1 to 107 and append to one CSV
    scrape_all_star_wars_data(base_url, start_page=1, end_page=107)

# Run the scraper
if __name__ == '__main__':
    main()
