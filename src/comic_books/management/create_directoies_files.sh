#!/bin/bash

# Navigate to the comic_books app directory
cd comic_books/

# Create the required directories for the Django management command
mkdir -p management/commands

# Create an empty __init__.py file in each directory to ensure Python treats them as packages
touch management/__init__.py
touch management/commands/__init__.py

# Create the Python file for the import command
touch management/commands/import_starwars_key_issues.py

#
# docker exec -it <container_name_or_id> python manage.py import_starwars_key_issues path_to_csv_file.csv
# 
# For example:
# docker exec -it web-1 python manage.py import_starwars_key_issues /app/data/starwars_key_issues.csv
# docker exec -it web-1 python manage.py import_starwars_key_issues /app/data/starwars_key_issues.csv -update
