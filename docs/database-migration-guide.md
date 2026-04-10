# Database Migration & Data Sync Guide

## Architecture

- **Local development:** SQLite (`src/db.sqlite3`)
- **Production (VPS):** PostgreSQL 13 in Docker container
- **Schema sync:** Django migrations keep both databases schema-identical
- **Data sync:** Manual — use fixtures (JSON) to move data between environments

## How Schema Migrations Work

### Creating a migration (local)
When you change a Django model:
```bash
# Generate migration file
DJANGO_SETTINGS_MODULE=samscollectibles.settings.local \
  /path/to/venv/bin/python src/manage.py makemigrations app_name

# Apply to local SQLite
DJANGO_SETTINGS_MODULE=samscollectibles.settings.local \
  /path/to/venv/bin/python src/manage.py migrate
```

### Applying to production (VPS)
Migrations run **automatically** on every deploy. The docker-compose command includes:
```
python manage.py migrate --noinput
```
So when you run `ansible-playbook playbooks/deploy.yml --ask-vault-pass`, the new container starts, runs all pending migrations against Postgres, then starts Gunicorn.

### Note on local SQLite sync issues
The local SQLite migration tracking got out of sync (imported from an older Postgres dump). When `manage.py migrate` fails locally with "table already exists", we applied schema changes directly:
```python
import sqlite3
conn = sqlite3.connect('src/db.sqlite3')
conn.execute("ALTER TABLE tablename ADD COLUMN colname varchar(20) DEFAULT 'value'")
conn.commit()
```
This is a workaround — the migration files still exist and work correctly on production Postgres.

## How Data Sync Works (SQLite → Postgres)

### Method 1: Django Fixtures (used for posters)

**Step 1: Export from local SQLite to JSON fixture**
```python
# Option A: Django dumpdata (if migrations are in sync)
python manage.py dumpdata app_name.ModelName --indent 2 --output fixtures/data.json

# Option B: Manual extraction (if migrations are out of sync)
python -c "
import sqlite3, json
conn = sqlite3.connect('src/db.sqlite3')
conn.row_factory = sqlite3.Row
rows = conn.execute('SELECT * FROM table_name').fetchall()
fixture = []
for row in rows:
    r = dict(row)
    fixture.append({
        'model': 'app_name.modelname',
        'pk': r['id'],
        'fields': {k: v for k, v in r.items() if k != 'id'}
    })
with open('fixtures/data.json', 'w') as f:
    json.dump(fixture, f, indent=2)
"
```

**Step 2: Copy fixture to VPS**
```bash
# Via SSH heredoc (works from Claude Code)
ssh sams-collectibles "cat > /tmp/data.json << 'EOF'
$(cat fixtures/data.json)
EOF"

# Or via scp (from your terminal)
scp fixtures/data.json sam@72.62.82.243:/tmp/data.json
```

**Step 3: Load into Postgres via Docker**
```bash
# Copy into container
ssh sams-collectibles "sudo docker cp /tmp/data.json src-web-1:/usr/src/app/data.json"

# Load using Django's loaddata
ssh sams-collectibles "sudo docker exec src-web-1 python manage.py loaddata /usr/src/app/data.json"
```

### Method 2: Django Management Command (for CSV data)
```bash
# The load_non_sports_cards command reads CSV and creates/updates records
ssh sams-collectibles "sudo docker exec src-web-1 python manage.py load_non_sports_cards csv_file.csv --update"
```

### Method 3: Full database dump/restore
```bash
# Export everything from production Postgres
ssh sams-collectibles "sudo docker exec src-db-1 pg_dump -U samscollectibles_user samscollectibles" > backup.sql

# Import into production (destructive — replaces all data)
cat backup.sql | ssh sams-collectibles "sudo docker exec -i src-db-1 psql -U samscollectibles_user samscollectibles"
```

## What Was Done (April 2026 Session)

### Migrations created:
| Migration | App | What it does |
|---|---|---|
| 0011 | non_sports_cards | Add validation_status field |
| 0012 | non_sports_cards | Add ebay_listing_url, ebay_item_id fields |
| 0002 | comic_books | Add condition, ebay_listing_url, ebay_item_id, validation_status |
| 0003 | movie_posters | Full model rewrite: remove release_date, add year, franchise, artist, poster_type, size, dimensions, country_of_origin, condition, linen_backed, rolled_or_folded, ebay_listing_url, ebay_item_id, validation_status. Create MoviePosterImage model |

### Data loaded into production Postgres:
| Data | Method | Records |
|---|---|---|
| 2 movie posters | Fixture JSON → loaddata | Star Wars Style B Teaser (1977), ESB Advance (1980) |

### Data NOT yet loaded into production:
| Data | Source | Next step |
|---|---|---|
| Non-sport trading cards | nstc-core-10-29-22-enriched.csv (315 rows) | Load via management command or fixture |
| Comic books (SW Marvel) | Need to import/photograph | Load via management command |
| Comic books (SW Dark Horse) | Inventory list coming from Sam | Load via management command |

## Fixture Files Location
- `src/movie_posters/fixtures/initial_posters.json` — 2 poster records
- `src/fixtures/all_data.json` — Empty (local DB had no data at export time)

## Important Notes
- **Never push unencrypted secrets** — database passwords are in ansible-vault
- **Postgres data persists** in a Docker volume (`postgres_data`) — survives container rebuilds
- **SQLite is disposable** — it's for local dev only, not the source of truth
- **Always commit migration files** — they're code, not data. They go in git.
- **Fixture files are safe to commit** — they contain no secrets (just titles, years, descriptions)
