# Comic Books Import Program
* import_starwars_base_issues.py
* import_starwars_key_issues.py

This program allows you to import key comic book issues for **Star Wars Marvel**, **Star Wars Dark Horse**, and **Star Trek DC** comic series from a CSV file. The program supports different comic models and ensures that no duplicate issues are created in the database. It also provides an option to update existing issues based on new data from the CSV file.

## Key Features of This Program

- **`comic_type` Argument**: 
   - A new argument `comic_type` determines which comic model to use: `StarWarsMarvelComic`, `StarWarsDarkHorseComic`, or `StarTrekDcComic`.
   
- **Generalized Logic**: 
   - The program can handle imports for any of these models based on the `comic_type` you provide (`starwars_marvel`, `starwars_dark_horse`, or `startrek_dc`).
   
- **Duplicate Prevention**: 
   - It uses `get_or_create()` to avoid duplicate entries, ensuring that if an issue already exists, it won't be added again.
   
- **Update Option**: 
   - The `-update` flag allows you to update existing records with new information from the CSV file.

## To import Base Comics:
### for example:
```bash
docker-compose exec web python manage.py import_starwars_base_issues path/to/starwars_marvel.csv starwars_marvel
```

* To import Star Wars Dark Horse Comics:

```bash
docker-compose exec web python manage.py import_starwars_base_issues path/to/starwars_dark_horse.csv starwars_dark_horse
```

* To import Star Trek DC Comics:

```bash
docker-compose exec web python manage.py import_starwars_base_issues path/to/startrek_dc.csv startrek_dc
```

* To update existing issues with the CSV data:

```bash
docker-compose exec web python manage.py import_comic_books path/to/starwars_marvel.csv starwars_marvel -update
```
* To import Key Comics:

```bash
docker exec -it <container_name_or_id> python manage.py import_starwars_key_issues path_to_csv_file.csv <comic_book_publisher>
```

### for example:

* Import Key Issues for Star Wars Marvel:
```bash
docker-compose exec web python manage.py import_starwars_key_issues starwars_marvel_key_issues.csv starwars_marvel
#or
docker-compose exec web python manage.py import_starwars_key_issues starwars_marvel_key_issues.csv starwars_marvel -update
```

* Import Key Issues for Star Wars Dark Horse:
```bash
docker-compose exec web python manage.py import_starwars_key_issues starwars_dark_horse_key_issues.csv starwars_dark_horse
#or
docker-compose exec web python manage.py import_starwars_key_issues starwars_dark_horse_key_issues.csv starwars_dark_horse -update
```

* Import Key Issues for Star Trek DC:
```bash
docker-compose exec web python manage.py import_starwars_key_issues startrek_dc_key_issues.csv startrek_dc
#or
docker-compose exec web python manage.py import_starwars_key_issues startrek_dc_key_issues.csv startrek_dc -update
```


## Supported Comic Models

This program works for all three comic models:

1. **StarWarsMarvelComic**
2. **StarWarsDarkHorseComic**
3. **StarTrekDcComic**

The program ensures that no duplicate issues are created in the database, even if it is run multiple times. Additionally, the program provides an option to update existing records with new information when necessary.