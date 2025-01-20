# src/comic_books/management/commands/import_starwars_key_issues.py

import csv
import argparse
import logging
from django.core.management.base import BaseCommand
from comic_books.models import Publisher, StarWarsMarvelComic, StarWarsDarkHorseComic, StarTrekDcComic, KeyIssueFacts
from datetime import datetime
import os

# Configure logging
LOG_FILE_PATH = os.path.join(os.path.dirname(__file__), 'import_starwars_key_issues.log')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE_PATH),
        logging.StreamHandler()  # Logs to console
    ]
)

# Define the comic model mapping for different types of comics
COMIC_MODELS = {
    'starwars_marvel': StarWarsMarvelComic,
    'starwars_dark_horse': StarWarsDarkHorseComic,
    'startrek_dc': StarTrekDcComic,
}

class Command(BaseCommand):
    help = 'Import Star Wars Marvel key issues (and other comics) from a CSV file'

    def add_arguments(self, parser):
        parser.add_argument('csv_file', type=str, help='The CSV file containing key issues')
        parser.add_argument('comic_type', type=str, choices=COMIC_MODELS.keys(), help='Type of comic to import key issues (starwars_marvel, starwars_dark_horse, startrek_dc)')
        parser.add_argument('-update', action='store_true', help='Update existing key issues')

    def handle(self, *args, **options):
        csv_file = options['csv_file']
        comic_type = options['comic_type']
        update = options['update']

        # Get the appropriate comic model
        comic_model = COMIC_MODELS[comic_type]

        # Determine the publisher based on comic type
        publisher_name = 'Marvel' if comic_type == 'starwars_marvel' else 'Dark Horse' if comic_type == 'starwars_dark_horse' else 'DC'
        publisher, _ = Publisher.objects.get_or_create(name=publisher_name)

        with open(csv_file, mode='r') as file:
            reader = csv.DictReader(file)
            for row in reader:
                issue_number = int(row['issue_number'])
                title = row['title']
                release_date = datetime.strptime(row['release_date'], '%m/%d/%Y').date()
                description = row.get('description', '')

                # Check if the issue already exists
                comic, created = comic_model.objects.get_or_create(
                    issue_number=issue_number,
                    title=title,
                    publisher=publisher,
                    defaults={'release_date': release_date, 'description': description}
                )

                if created:
                    logging.info(f"Created new comic: {title} #{issue_number} ({publisher_name})")
                elif update:
                    comic.release_date = release_date
                    comic.description = description
                    comic.save()
                    logging.info(f"Updated comic: {title} #{issue_number} ({publisher_name})")

                # Key Issue Facts
                key_issue_facts, created = KeyIssueFacts.objects.get_or_create(
                    comic=comic,
                    defaults={
                        'is_key_issue': row['is_key_issue'] == 'True',
                        'key_facts': row['key_facts'],
                        'characters_appearing': row['characters_appearing'],
                        'key_reason': row['key_reason']
                    }
                )

                if not created and update:
                    # Update key issue facts if -update flag is passed
                    key_issue_facts.is_key_issue = row['is_key_issue'] == 'True'
                    key_issue_facts.key_facts = row['key_facts']
                    key_issue_facts.characters_appearing = row['characters_appearing']
                    key_issue_facts.key_reason = row['key_reason']
                    key_issue_facts.save()
                    logging.info(f"Updated key issue facts for comic: {title} #{issue_number} ({publisher_name})")

        logging.info("Data import completed successfully.")
        self.stdout.write(self.style.SUCCESS('Data import completed successfully.'))
