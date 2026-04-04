#!/bin/bash

# Set the project base directory
BASE_DIR="/Volumes/ThunderRaid24t/sc4"
PROJECT_NAME="samscollectibles"

# Create the base directory if it doesn't exist
mkdir -p $BASE_DIR
cd $BASE_DIR

# Check if python3 is installed
if ! command -v python3 &> /dev/null
then
    echo "Python3 could not be found. Please install Python 3."
    exit
fi

# Create a virtual environment
echo "Creating a Python virtual environment..."
python3 -m venv venv
source venv/bin/activate

# Check to see if a new release of pip is available:
pip install --upgrade pip

# Install Django inside the virtual environment
pip install django

# Create the src directory and the Django project inside it
mkdir -p $BASE_DIR/src
cd $BASE_DIR/src

# Create the Django project inside src
django-admin startproject $PROJECT_NAME .

# Create apps: comic_books, non_sports_cards, movie_posters
python3 manage.py startapp comic_books
python3 manage.py startapp non_sports_cards
python3 manage.py startapp movie_posters

# Create necessary directories and files

# Comic Books app
mkdir -p comic_books/migrations
mkdir -p comic_books/templates/comic_books
mkdir -p comic_books/static/css

# Populate Comic Books models.py
cat > comic_books/models.py <<EOL
from django.db import models

class Publisher(models.Model):
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name

class ComicBook(models.Model):
    title = models.CharField(max_length=200)
    publisher = models.ForeignKey(Publisher, on_delete=models.CASCADE)
    issue_number = models.IntegerField()
    release_date = models.DateField()

    def __str__(self):
        return f"\{self.title\} #\{self.issue_number\} (\{self.publisher\})"

class StarWarsMarvelComic(ComicBook):
    description = models.TextField()

    def __str__(self):
        return f"\{self.title\} #\{self.issue_number\} (Star Wars Marvel)"
EOL

# Populate Comic Books views.py
cat > comic_books/views.py <<EOL
from django.shortcuts import render
from .models import StarWarsMarvelComic

def index(request):
    return render(request, 'comic_books/index.html')

def star_wars_marvel_comics(request):
    comics = StarWarsMarvelComic.objects.all()
    return render(request, 'comic_books/starwars_marvel_comics.html', {'comics': comics})
EOL

# Populate Comic Books urls.py
cat > comic_books/urls.py <<EOL
from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='comic_books_index'),
    path('star-wars-marvel/', views.star_wars_marvel_comics, name='star_wars_marvel_comics'),
]
EOL

# Populate Comic Books templates
cat > comic_books/templates/comic_books/index.html <<EOL
{% extends "base.html" %}
{% block content %}
<h1>Comic Books Home</h1>
{% endblock %}
EOL

cat > comic_books/templates/comic_books/starwars_marvel_comics.html <<EOL
{% extends "base.html" %}
{% block content %}
<h1>Star Wars Marvel Comics</h1>
<div>
    <ul>
        {% for comic in comics %}
        <li>{{ comic.title }} - Issue #{{ comic.issue_number }} (Released: {{ comic.release_date }})</li>
        {% endfor %}
    </ul>
</div>
{% endblock %}
EOL

# Non-Sports Cards app
mkdir -p non_sports_cards/migrations
mkdir -p non_sports_cards/templates/non_sports_cards
mkdir -p non_sports_cards/static/css

# Populate Non-Sports Cards models.py
cat > non_sports_cards/models.py <<EOL
from django.db import models
from django.core.exceptions import ValidationError

def validate_key_features(value):
    if not isinstance(value, list):
        raise ValidationError("Key features must be a list.")
    for feature in value:
        if not isinstance(feature, str):
            raise ValidationError("Each feature in key features must be a string.")

class NonSportsCards(models.Model):
    title = models.CharField(max_length=255)
    manufacturer = models.CharField(max_length=255)
    date_manufactured = models.CharField(max_length=4)
    description = models.TextField()
    key_features = models.JSONField(default=list, validators=[validate_key_features])

    def __str__(self):
        return self.title
EOL

# Populate Non-Sports Cards views.py
cat > non_sports_cards/views.py <<EOL
from django.shortcuts import render
from .models import NonSportsCards

def index(request):
    return render(request, 'non_sports_cards/index.html')

def nonsports_chase_cards(request):
    cards = NonSportsCards.objects.filter(CHASE_TYPES='Holographic')
    return render(request, 'non_sports_cards/nonsports_chase_cards.html', {'cards': cards})
EOL

# Populate Non-Sports Cards urls.py
cat > non_sports_cards/urls.py <<EOL
from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='non_sports_cards_index'),
    path('chase-cards/', views.nonsports_chase_cards, name='nonsports_chase_cards'),
]
EOL

# Populate Non-Sports Cards templates
cat > non_sports_cards/templates/non_sports_cards/index.html <<EOL
{% extends "base.html" %}
{% block content %}
<h1>Non-Sports Cards Home</h1>
{% endblock %}
EOL

cat > non_sports_cards/templates/non_sports_cards/nonsports_chase_cards.html <<EOL
{% extends "base.html" %}
{% block content %}
<h1>Non-Sports Chase Cards</h1>
<div>
    <ul>
        {% for card in cards %}
        <li>{{ card.title }} (Released: {{ card.date_manufactured }})</li>
        {% endfor %}
    </ul>
</div>
{% endblock %}
EOL

# Movie Posters app
mkdir -p movie_posters/migrations
mkdir -p movie_posters/templates/movie_posters
mkdir -p movie_posters/static/css

# Populate Movie Posters models.py
cat > movie_posters/models.py <<EOL
from django.db import models

class MoviePosters(models.Model):
    movie_title = models.CharField(max_length=255)
    title = models.CharField(max_length=255)
    description = models.TextField()

    def __str__(self):
        return f"\{self.title\} (\{self.movie_title\})"
EOL

# Populate Movie Posters views.py
cat > movie_posters/views.py <<EOL
from django.shortcuts import render
from .models import MoviePosters

def index(request):
    return render(request, 'movie_posters/index.html')

def star_wars_posters(request):
    posters = MoviePosters.objects.filter(movie_title__icontains='Star Wars')
    return render(request, 'movie_posters/star_wars_posters.html', {'posters': posters})
EOL

# Populate Movie Posters urls.py
cat > movie_posters/urls.py <<EOL
from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='movie_posters_index'),
    path('star-wars/', views.star_wars_posters, name='star_wars_posters'),
]
EOL

# Populate Movie Posters templates
cat > movie_posters/templates/movie_posters/index.html <<EOL
{% extends "base.html" %}
{% block content %}
<h1>Movie Posters Home</h1>
{% endblock %}
EOL

cat > movie_posters/templates/movie_posters/star_wars_posters.html <<EOL
{% extends "base.html" %}
{% block content %}
<h1>Star Wars Movie Posters</h1>
<div>
    <ul>
        {% for poster in posters %}
        <li>{{ poster.title }} ({{ poster.movie_title }})</li>
        {% endfor %}
    </ul>
</div>
{% endblock %}
EOL

# Sams Collectibles base settings and templates
mkdir -p samscollectibles/settings
mkdir -p samscollectibles/templates
mkdir -p samscollectibles/static/images

# Populate base.html
cat > samscollectibles/templates/base.html <<EOL
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Sams Collectibles</title>
    <link rel="stylesheet" href="{% static 'css/base.css' %}">
</head>
<body style="background-image: url('{% static "images/SpaceBackground-1.png" %}'); background-size: cover; background-attachment: fixed;">
    <header>
        <h1>Welcome to Sam's Collectibles</h1>
        <nav>
            <ul>
                <li><a href="{% url 'comic_books_index' %}">Comic Books</a></li>
                <li><a href="{% url 'non_sports_cards_index' %}">Non-Sports Cards</a></li>
                <li><a href="{% url 'movie_posters_index' %}">Movie Posters</a></li>
            </ul>
        </nav>
    </header>
    <main>
        {% block content %}
        {% endblock %}
    </main>
    <footer>
        <p>&copy; 2024 Sam's Collectibles</p>
    </footer>
</body>
</html>
EOL

# Populate settings files
cat > samscollectibles/settings/base.py <<EOL
import os
from decouple import config

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SECRET_KEY = config('SECRET_KEY')

DEBUG = config('DEBUG', default=False, cast=bool)

ALLOWED_HOSTS = config('ALLOWED_HOSTS', default=[], cast=lambda v: [s.strip() for s in v.split(',')])

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'comic_books',
    'non_sports_cards',
    'movie_posters',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'samscollectibles.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'templates')],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'samscollectibles.wsgi.application'

USE_POSTGRES = config('USE_POSTGRES', default=False, cast=bool)

if USE_POSTGRES:
    DATABASES = {
        'default': {
            'ENGINE': config('DB_ENGINE'),
            'NAME': config('DB_NAME'),
            'USER': config('DB_USER'),
            'PASSWORD': config('DB_PASSWORD'),
            'HOST': config('DB_HOST'),
            'PORT': config('DB_PORT'),
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': os.path.join(BASE_DIR, 'db.sqlite3'),
        }
    }

LANGUAGE_CODE = 'en-us'

TIME_ZONE = config('TIME_ZONE', default='UTC')

USE_I18N = True

USE_L10N = True

USE_TZ = True

STATIC_URL = '/static/'
STATICFILES_DIRS = [os.path.join(BASE_DIR, 'static')]

MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

# File storage - configure for your hosting provider (Cloudflare R2, Hostinger, etc.)
# DEFAULT_FILE_STORAGE = 'storages.backends.s3boto3.S3Boto3Storage'
EOL

# Populate local.py
cat > samscollectibles/settings/local.py <<EOL
from .base import *

DEBUG = config('DEBUG', default=True, cast=bool)
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default=[], cast=lambda v: [s.strip() for s in v.split(',')])
EOL

# Populate production.py
cat > samscollectibles/settings/production.py <<EOL
from .base import *

DEBUG = False
ALLOWED_HOSTS = config('ALLOWED_HOSTS', cast=lambda v: [s.strip() for s in v.split(',')])
SECURE_SSL_REDIRECT = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_SECURE = True
EOL

# Create .env files
cat > .env.local <<EOL
DJANGO_SETTINGS_MODULE=samscollectibles.settings.local
SECRET_KEY='REDACTED-INSECURE-SECRET-KEY-2'
DEBUG=True
ALLOWED_HOSTS=localhost, 127.0.0.1
USE_POSTGRES=False
TIME_ZONE=America/Los_Angeles
EOL

cat > .env.production <<EOL
DJANGO_SETTINGS_MODULE=samscollectibles.settings.production
SECRET_KEY='Create-New-Secret-Key-for-Production'
DEBUG=False
ALLOWED_HOSTS=samscollectibles.net, www.samscollectibles.net
USE_POSTGRES=True

# PostgreSQL settings for production
DB_ENGINE=django.db.backends.postgresql
DB_NAME=samscollectibles
DB_USER=postgres
DB_PASSWORD=postgres_password
DB_HOST=db
DB_PORT=5432

# File storage settings (configure for your hosting provider)
TIME_ZONE=America/Los_Angeles
EOL

# Populate Dockerfile
cat > Dockerfile <<EOL
FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

WORKDIR /usr/src/app

COPY requirements.txt /usr/src/app/
RUN pip install --no-cache-dir -r requirements.txt

COPY . /usr/src/app/

EXPOSE 8000
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
EOL

# Populate docker-compose.yml
cat > docker-compose.yml <<EOL
version: '3.8'

services:
  web:
    build: .
    command: python manage.py runserver 0.0.0.0:8000
    volumes:
      - .:/usr/src/app
    ports:
      - "8000:8000"
    env_file:
      - .env.local
    depends_on:
      - db

  db:
    image: postgres:13
    environment:
      POSTGRES_DB: samscollectibles
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres_password
    volumes:
      - postgres_data:/var/lib/postgresql/data/
    ports:
      - "5432:5432"

volumes:
  postgres_data:
EOL

# Create static files and directories
mkdir -p samscollectibles/static/css
touch samscollectibles/static/css/base.css

# Create the image background placeholder
touch samscollectibles/static/images/SpaceBackground-1.png

# Create requirements.txt in the root directory
cat > samscollectibles/requirements.txt <<EOL
asgiref==3.6.0
black==23.3.0
certifi==2022.12.7
cffi==1.15.1
charset-normalizer==3.1.0
click==8.1.3
colorama==0.4.6
cryptography==40.0.2
defusedxml==0.7.1
Django==4.2
django-allauth==0.54.0
django-debug-toolbar==4.0.0
django-extensions==3.2.1
django-filter==23.2
django-widget-tweaks==1.4.12
Faker==18.6.0
idna==3.4
mypy-extensions==1.0.0
oauthlib==3.2.2
packaging==23.1
pathspec==0.11.1
platformdirs==3.5.0
pycparser==2.21
PyJWT==2.6.0
python-dateutil==2.8.2
python3-openid==3.
python3-openid==3.2.0
requests==2.29.0
requests-oauthlib==1.3.1
six==1.16.0
sqlparse==0.4.4
tomli==2.0.1
tzdata==2023.3
urllib3==1.26.15
EOL

pip install -r samscollectibles/requirements.txt

echo "Project directory structure and files created successfully!"
