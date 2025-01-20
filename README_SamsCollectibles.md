
# Deployment Guide for Sam's Collectibles Django Application

This guide provides step-by-step instructions to deploy the Sam's Collectibles Django application using AWS Fargate, AWS ECS, Docker, and PostgreSQL in a containerized environment.

## Prerequisites
1. **AWS CLI Installed**: Ensure the AWS CLI is installed and configured.
2. **Docker Installed**: Docker is needed to build and push images to ECR.
3. **AWS Account**: You must have an AWS account with sufficient permissions.
4. **Django Project Setup**: Make sure the Django project is working locally with PostgreSQL.

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

## Step 2: Build and Push Docker Image to ECR

### 2.1 Create an ECR Repository
```bash
aws ecr create-repository --repository-name sams-collectibles
```

### 2.2 Authenticate Docker with ECR
```bash
$(aws ecr get-login --no-include-email --region your-region)
```

### 2.3 Build and Push the Docker Image
```bash
docker build -t sams-collectibles .
docker tag sams-collectibles:latest <your_account_id>.dkr.ecr.<region>.amazonaws.com/sams-collectibles:latest
docker push <your_account_id>.dkr.ecr.<region>.amazonaws.com/sams-collectibles:latest
```

## Step 3: Set Up PostgreSQL in a Container

Instead of using AWS RDS, we'll configure PostgreSQL as a separate container.

### 3.1 Update your `docker-compose.yml` file

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

## Step 4: Create AWS Fargate Cluster

### 4.1 Create a new ECS Cluster
```bash
aws ecs create-cluster --cluster-name sams-collectibles-cluster
```

### 4.2 Define a task definition `sams-collectibles-task.json`
Update the `taskDefinition` to include both Django and PostgreSQL containers:
```json
{
  "family": "sams-collectibles",
  "networkMode": "awsvpc",
  "containerDefinitions": [
    {
      "name": "sams-collectibles",
      "image": "<your_account_id>.dkr.ecr.<region>.amazonaws.com/sams-collectibles:latest",
      "memoryReservation": 512,
      "cpu": 256,
      "essential": true,
      "portMappings": [
        {
          "containerPort": 8000,
          "hostPort": 8000,
          "protocol": "tcp"
        }
      ],
      "environment": [
        {"name": "DB_NAME", "value": "samscollectibles"},
        {"name": "DB_USER", "value": "postgres"},
        {"name": "DB_PASSWORD", "value": "your_password"},
        {"name": "DB_HOST", "value": "db"},
        {"name": "DB_PORT", "value": "5432"}
      ]
    },
    {
      "name": "db",
      "image": "postgres:13",
      "memoryReservation": 256,
      "cpu": 256,
      "essential": true,
      "environment": [
        {"name": "POSTGRES_DB", "value": "samscollectibles"},
        {"name": "POSTGRES_USER", "value": "postgres"},
        {"name": "POSTGRES_PASSWORD", "value": "your_password"}
      ],
      "portMappings": [
        {
          "containerPort": 5432,
          "hostPort": 5432,
          "protocol": "tcp"
        }
      ]
    }
  ],
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "512",
  "memory": "1024",
  "executionRoleArn": "arn:aws:iam::your_account_id:role/ecsTaskExecutionRole"
}
```

### 4.3 Register and Deploy the Task
* Register
```bash
aws ecs register-task-definition \
  --cli-input-json file://sams-collectibles-task.json
```

* Deploy the Task
```bash
aws ecs create-service \
  --cluster sams-collectibles-cluster \
  --service-name sams-collectibles-service \
  --task-definition sams-collectibles \
  --desired-count 1 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[subnet-xxxxxx],securityGroups=[sg-xxxxxx],assignPublicIp=ENABLED}"
```

## Additional Configuration
- For the database communication, ensure both Django and PostgreSQL containers are in the same task and AWS VPC/Subnet.

## Additional Resources
- Use AWS Secrets Manager for managing secrets securely.
- Integrate AWS CloudWatch for logging.

