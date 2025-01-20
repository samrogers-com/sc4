# Django CSV Loader for Non-Sports Cards

This Django management command allows you to load and update Non-Sports Cards data from a CSV file into the database. 
It provides flexibility to either create new records or update existing records based on the card title.

## Features

- Load data from a CSV file into the `NonSportsCards` model. 
- Create new records or update existing records based on the title field. 
- Flexible to update any field(s) based on the CSV input. 
- Logs success and error 
messages to both stdout and a log file. 
- Handles validation for the `key_features` JSON field.

## Usage

### Basic Command to Load Data

### 1. To load data from a CSV file (create new records):

```bash 
python manage.py load_non_sports_cards <csv_file_path> 
```

class Command(BaseCommand): help = "Load non-sports cards data from a CSV file and update any field."

 def add_arguments(self, parser): parser.add_argument('csv_file', type=str, help='The CSV file to load data from') parser.add_argument('--update', action='store_true', help='If set, it will update existing records') BaseCommand: This is the base class for custom
Django management commands. add_arguments: This method defines the arguments you can pass to the command: csv_file: A required argument, this is the path to the CSV file that contains the data to be loaded. --update: This is an optional flag. If set, the command will
update existing records instead of just creating new ones. Without this flag, it will only create new records. 

### 2. File Path Setup (Relative to the commands Directory)

### Determine the commands directory path (the location of this script)
```python
commands_dir = os.path.dirname(__file__) 
```

### Input CSV file path (ensure it's relative to the commands directory)

```python 
csv_file_path = os.path.join(commands_dir, csv_file) 
```

### Output log file path (relative to the commands directory) 

```python 
log_file_path = os.path.join(commands_dir, 'load_non_sports_cards.log'): 
```

* `commands_dir = os.path.dirname(__file__)`: This gets the directory path where the 
current script (management command) is located. This ensures that the script will look 
for the CSV file and write the log file within the same directory. 
* `csv_file_path = os.path.join(commands_dir, csv_file)`: The CSV file path is constructed  
relative to the commands directory using the filename provided in the argument. 
* `log_file_path = os.path.join(commands_dir, 'load_non_sports_cards.log')`: 
This defines the output path for the log file, which will also be saved in the commands directory. 

### 3. Reading the CSV and Processing Rows 

```python 
with open(csv_file_path, newline='', encoding='utf-8') as file, open(log_file_path, 'w') as log_file:
    reader = csv.DictReader(file)

    for row in reader:
        title = row.get('title')
 ```

* The `csv.DictReader(file)` reads the CSV file into a dictionary format. 
Each row becomes a dictionary where the column names (headers) serve as keys. 
* The command first checks for a `title` for each row, which acts as the identifier for the card. 

### 4. Handling Missing Titles

```python 
if not title:
    log_file.write(f"Missing title for row: {row}\n")
    self.stdout.write(self.style.ERROR(f"Missing title for row: {row}"))
    continue
```

* If the title is missing from the row, the command logs this error both to the console and to the 
log file, then moves on to the next row.

### 5. Inserting or Updating Records

```python 
if update_mode:
    card, created = NonSportsCards.objects.update_or_create(
        title=title,
        defaults={**row}
    )
    action = "Updated" if not created else "Created"
else:
    card = NonSportsCards.objects.create(**row)
    action = "Created"
```
* ### Update Mode (`--update`):
    * If the `--update` flag is set, the update_or_create method is used. This method tries to find an 
    existing record by the title: 
        * If found, it updates the record with the fields provided in the CSV row. 
        * If not found, it creates a new record. 
    * `defaults={**row}`: The row dictionary (with the field names and their values from the CSV) is 
    passed to update the corresponding fields. 
    * The `created` flag determines whether the record was newly created or updated, and logs the appropriate action. 
* ### Create Mode (default): 
    * If the `--update` flag is not set, the command uses `NonSportsCards.objects.create(**row)` 
to create a new record using all the fields in the row. 

### 6. Logging Success Messages

```python 
success_message = f"{action} Non-Sports Card: {title}"
log_file.write(success_message + "\n")
self.stdout.write(self.style.SUCCESS(success_message))
```

* For each successful insert or update, the command logs the action (created/updated) 
to both the console and the log file. 

### 7. Error Handling (Integrity Errors)

```python 
except IntegrityError as e:
    error_message = f"Error processing card '{title}': {e}"
    log_file.write(error_message + "\n")
    self.stdout.write(self.style.ERROR(error_message))
```

* If there's a database-related error (such as a validation or constraint failure), 
the command catches it and logs the error, continuing with the next row. 

### 8. FileNotFoundError and Generic Error Handling 

```python  
except FileNotFoundError: raise
CommandError(f"File '{csv_file_path}' does not exist") except Exception as e: raise CommandError(f"An error occurred: {e}") 
```

* The command ensures that the CSV file exists. If it doesn't, it raises a CommandError. 
* It also catches any other exceptions and raises them as CommandError, which will terminate the command execution.

## Key Features:
- Flexibility: The command can either create new records or update existing ones using the --update flag.
- Logging: Success and error messages are written both to the console and a log file (load_non_sports_cards.log).
- Field Flexibility: You can update any field from the CSV (not limited to specific fields), as it uses Django's 
update_or_create method for updates. 
- Error Handling: The command logs errors (missing titles, database issues) and handles them gracefully without 
terminating the entire process.

## Usage:
### To load data (create new records):

```bash 
python manage.py load_non_sports_cards non_sports_cards_data.csv 
``` 

This will read the CSV and create new records for each row.

To update existing records:

```bash 
python manage.py load_non_sports_cards non_sports_cards_data.csv --update 
``` 

This will update existing records based on the title, but can update any fields from the CSV.

The command is now set up for flexibility, allowing you to update specific fields, handle errors 
gracefully, and log everything for future reference!
