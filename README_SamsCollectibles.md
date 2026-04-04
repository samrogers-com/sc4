
# Deployment Guide for Sam's Collectibles Django Application

This guide provides step-by-step instructions to deploy the Sam's Collectibles Django application using Docker and PostgreSQL in a containerized environment, hosted on Cloudflare or Hostinger.

## Prerequisites
1. **Docker Installed**: Docker is needed to build and run application containers.
2. **Django Project Setup**: Make sure the Django project is working locally with PostgreSQL.
3. **Hosting Account**: A Cloudflare or Hostinger account for production deployment.

## Step 1: Dockerize the Django Application

### 1.1 Create a Dockerfile
Create a `Dockerfile` for your Django application at the root of the project.

**Production Dockerfile (`Dockerfile`):**
```Dockerfile
# Dockerfile (production)
FROM python:3.12-slim-bookworm

# Set environment variables for optimal Docker performance
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Create and set working directory
WORKDIR /usr/src/app

# Install dependencies
COPY requirements.txt /usr/src/app/
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . /usr/src/app/

# Collect static files (for Django)
RUN python manage.py collectstatic --noinput

# Expose port 8000 for the application
EXPOSE 8000

# Use Gunicorn for production
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "sams_collectibles.wsgi:application"]
```

**Development Dockerfile (`Dockerfile.dev`):**
```Dockerfile
# Dockerfile.dev (development)
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

WORKDIR /usr/src/app

COPY requirements.txt /usr/src/app/
RUN pip install --no-cache-dir -r requirements.txt

COPY . /usr/src/app/

RUN apt-get update && apt-get install -y postgresql-client

EXPOSE 8000
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
```

## Step 2: Build the Docker Image

```bash
docker build -t sams-collectibles .
```

## Step 3: Set Up PostgreSQL in a Container

### 3.1 Docker Compose for Local Development

```yaml
version: '3.8'

services:
  web:
    build: .
    command: >
      sh -c "python manage.py migrate &&
             python manage.py runserver 0.0.0.0:8000"
    volumes:
      - .:/usr/src/app
    ports:
      - "8000:8000"
    env_file:
      - ./.env.production
    depends_on:
      - db

  db:
    image: postgres:13
    environment:
      POSTGRES_DB: samscollectibles
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: your_password
    volumes:
      - postgres_data:/var/lib/postgresql/data/
    ports:
      - "5432:5432"

volumes:
  postgres_data:
```

### 3.2 Environment Variables

Ensure your `.env.production` contains:
```env
DB_NAME=samscollectibles
DB_USER=postgres
DB_PASSWORD=your_password
DB_HOST=db
DB_PORT=5432
```

## Step 4: Deploy to Cloudflare or Hostinger

Deployment steps will depend on which hosting provider you choose. Both support Docker containers. Push your built image to a container registry (Docker Hub or the provider's registry) and configure the service to run it.

## Additional Notes
- Use your hosting provider's secrets/environment variable management for sensitive values (DB passwords, Django secret key, etc.).
- Configure logging through your hosting provider's dashboard or via Django's built-in logging settings.
