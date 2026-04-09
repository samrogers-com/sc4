# src/Dockerfile

# Dockerfile.dev (development)
# Dockerfile (production)
FROM python:3.12-slim-bookworm

# Install dependencies including curl
RUN apt-get update && apt-get install -y bash curl && apt-get clean

# Set environment variables for optimal Docker performance
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Create and set working directory
WORKDIR /usr/src/app

# Install dependencies
COPY requirements.txt /usr/src/app/
RUN pip install --no-cache-dir -r requirements.txt

# Create the staticfiles directory before running collectstatic
RUN mkdir -p /usr/src/app/staticfiles

# Copy application code
COPY . /usr/src/app/

# Collect static files (for Django)
RUN python manage.py collectstatic --noinput

# Expose port (overridden by docker-compose)
EXPOSE 8000

# Use Gunicorn for production
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "samscollectibles.wsgi:application"]
