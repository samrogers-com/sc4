import csv
import json
import os
import sys
from django.core.management.base import BaseCommand, CommandError
from non_sports_cards.models import NonSportsCards
from django.db import IntegrityError

class Command(BaseCommand):
    help = "Load non-sports cards data from a CSV or JSON file and update any field."

    def add_arguments(self, parser):
        parser.add_argument('file', type=str, help='The CSV or JSON file to load data from')
        parser.add_argument('--update', action='store_true', help='If set, it will update existing records')
        parser.add_argument('--format', type=str, choices=['csv', 'json'], default='csv', help='Specify the format of the input file (csv or json)')

    def handle(self, *args, **options):
        file_path = options['file']
        update_mode = options['update']
        file_format = options['format']

        # Determine the commands directory path (the location of this script)
        commands_dir = os.path.dirname(__file__)

        # Input file path (ensure it's relative to the commands directory)
        file_path = os.path.join(commands_dir, file_path)

        # Output log file path (relative to the commands directory)
        log_file_path = os.path.join(commands_dir, 'load_non_sports_cards.log')

        total_records = 0  # Counter to track successfully processed records

        try:
            if file_format == 'csv':
                with open(file_path, newline='', encoding='utf-8') as file, open(log_file_path, 'w') as log_file:
                    reader = csv.DictReader(file)
                    total_records = self.process_records(reader, log_file, update_mode)
            elif file_format == 'json':
                with open(file_path, encoding='utf-8') as file, open(log_file_path, 'w') as log_file:
                    data = json.load(file)
                    total_records = self.process_records(data, log_file, update_mode)

            # Print the total number of records loaded or updated
            self.stdout.write(self.style.SUCCESS(f"Total records processed: {total_records}"))

        except FileNotFoundError:
            raise CommandError(f"File '{file_path}' does not exist")
        except Exception as e:
            raise CommandError(f"An error occurred: {e}")

    def process_records(self, records, log_file, update_mode):
        total_records = 0  # Counter to track processed records

        for row in records:
            title = row.get('title')

            if not title:
                log_file.write(f"Missing title for row: {row}\n")
                self.stdout.write(self.style.ERROR(f"Missing title for row: {row}"))
                continue

            try:
                if update_mode:
                    card, created = NonSportsCards.objects.update_or_create(
                        title=title,
                        defaults={**row}
                    )
                    action = "Updated" if not created else "Created"
                else:
                    # Prevent duplicates by checking if the card already exists
                    if NonSportsCards.objects.filter(title=title).exists():
                        error_message = f"Duplicate title '{title}' skipped."
                        log_file.write(error_message + "\n")
                        self.stdout.write(self.style.WARNING(error_message))
                        continue
                    
                    card = NonSportsCards.objects.create(**row)
                    action = "Created"

                total_records += 1  # Increment counter for each successful record

                success_message = f"{action} Non-Sports Card: {title}"
                log_file.write(success_message + "\n")
                self.stdout.write(self.style.SUCCESS(success_message))

            except IntegrityError as e:
                error_message = f"Error processing card '{title}': {e}"
                log_file.write(error_message + "\n")
                self.stdout.write(self.style.ERROR(error_message))

        return total_records  # Return the total number of records processed
