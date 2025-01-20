
# Deployment Guide for Sam's Collectibles Django Application

This guide provides step-by-step instructions to deploy the Sam's Collectibles Django application using AWS Fargate, AWS ECS, Docker, and PostgreSQL in a containerized environment.

## Prerequisites
1. **AWS CLI Installed**: Ensure the AWS CLI is installed and configured.
2. **Docker Installed**: Docker is needed to build and push images to ECR.
3. **AWS Account**: You must have an AWS account with sufficient permissions.
4. **Django Project Setup**: Make sure the Django project is working locally with PostgreSQL.

## Creating & Storing Secrets in AWS Secrets Manager with the AWS CLI
## Store Secrets in AWS Secrets Manager from the console
  ### 1. Install and Configure AWS CLI
  Ensure that your AWS CLI is installed and configured with the necessary IAM permissions:
  ``` bash
  aws configure
  ```

  ### 2. Create Secrets in AWS Secrets Manager Using AWS CLI
  ### Example 1: Create a Secret for PostgreSQL Credentials
  ```bash
  aws secretsmanager create-secret \
    --name sams-collectibles-db-secret \
    --description "PostgreSQL credentials for Sam's Collectibles" \
    --secret-string '{"username":"postgres","password":"your_password","dbname":"samscollectibles","host":"db","port":"5432"}'
  ```

  ### Example 2: Create a Secret for Django Settings

  ```bash
  aws secretsmanager create-secret \
    --name sams-collectibles-django-secret \
    --description "Django application secrets for Sam's Collectibles" \
    --secret-string '{"DJANGO_SECRET_KEY":"your_django_secret_key","ALLOWED_HOSTS":"samscollectibles.net,localhost"}'
  ```

  ### 3. Additional Parameters Explained:
  * '--name': The name of your secret.
  * '--description': Optional description of the secret.
  * '--secret-string': A JSON string containing your secret key-value pairs.

  Replace the values ('your_password', your_django_secret_key', etc.) with your actual secrets.

  ### 4. Viewing Secrets from AWS CLI
  You can view your created secrets using:
  ```bash
  aws secretsmanager get-secret-value --secret-id sams-collectibles-db-secret
  ```
  'Note': This command reveals the secret, so be cautious about using it.

  ### 5. Deleting a Secret Using AWS CLI
  If you need to delete a secret, you can use:

  ```bash
  aws secretsmanager delete-secret --secret-id sams-collectibles-db-secret --recovery-window-in-days 7
  ```
  The '--recovery-window-in-days' specifies how many days AWS will retain the secret before permanently deleting it.

###1.1 Create Secrets from the console for PostgreSQL Database
  1. Open the AWS Secrets Manager console.
  2. Click Store a new secret.
  3. Choose Other type of secrets.
  4. Enter the key-value pairs for your PostgreSQL credentials:

      * username: admin (replace with your DB username)
      * password: your_password (replace with your DB password)
      * host: your-db-endpoint.rds.amazonaws.com
      * port: 5432
      * dbname: sams_collectibles
  5. Click Next and provide a name for the secret, e.g., sams-collectibles-db-secret.
  6. Click through the remaining steps and store the secret.

###1.2 Create Secrets from the console for Django Settings
  1. Click Store a new secret again.
  2. Choose Other type of secrets.

  3. Enter key-value pairs for sensitive Django settings:

      * DJANGO_SECRET_KEY: <your-django-secret-key> (replace this with your actual secret key)
      * ALLOWED_HOSTS: * or your domain name, e.g., sams-collectibles.com
  4. Click Next and provide a name for the secret, e.g., sams-collectibles-django-secret.
  5. Click through the remaining steps and store the secret.

##Step 2: Grant ECS Task Role Access to Secrets
  1. Open the IAM Console.
  2. Find or create the ECS task execution role (e.g., ecsTaskExecutionRole).
  3. Attach a new policy to allow access to Secrets Manager:
      * Click on the role and then Add permissions > Attach policies > Create policy.
      * Use the following JSON policy (replace your-region and your-account-id with your actual values):

```json
json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "secretsmanager:GetSecretValue"
      ],
      "Resource": [
        "arn:aws:secretsmanager:your-region:your-account-id:secret:sams-collectibles-db-secret-*",
        "arn:aws:secretsmanager:your-region:your-account-id:secret:sams-collectibles-django-secret-*"
      ]
    }
  ]
}
```
  4. Click `Review policy`, give it a name (e.g., ecs-secrets-access-policy), and attach it to the ECS task execution role.

## Step 1: Dockerize the Django Application

### 1.1 Create a Dockerfile
Create a `Dockerfile` for your Django application at the root of the project.

**Production Dockerfile (`Dockerfile`):**
```
Dockerfile
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
#### 2.2.1 First retrieve your AWS account ID using the following AWS CLI command:
```bash
aws sts get-caller-identity --query Account --output text
```
This command will return the AWS account ID associated with the credentials currently configured for the AWS CLI.
This will disappear after you quit it.

#### 2.2.2 authenticate Docker with Amazon Elastic Container Registry (ECR) in the us-west-2 region for the repository named sams-collectibles, you can use the following awscli command:
```bash
The comment below is an example and then the real command is below that.
# aws ecr get-login-password --region us-west-2 | docker login --username \
# samrogers --password-stdin <aws_account_id>.dkr.ecr.us-west-2.amazonaws.com/sams-collectibles

# Real command 
aws ecr get-login-password --region us-west-2 | docker login --username \
samrogers --password-stdin 315414901942.dkr.ecr.us-west-2.amazonaws.com/sams-collectibles
```
#### 2.2.3 You can validate if your Docker client is authenticated with Amazon ECR by running a simple command that interacts with the ECR repository.
```bash
aws ecr list-images --repository-name sams-collectibles --region us-west-2
```
If your authentication is successful, this command will list all the images stored in the sams-collectibles ECR repository. If you encounter authentication or permission issues, it indicates a problem with your login or credentials.

### 2.3 Build and Push the Docker Image
```bash
docker build -t sams-collectibles .

# docker tag sams-collectibles:latest <your_account_id>.dkr.ecr.<region>.amazonaws.com/sams-collectibles:latest
docker tag sams-collectibles:latest 315414901942.dkr.ecr.us-west-2.amazonaws.com/sams-collectibles:latest

# docker push <your_account_id>.dkr.ecr.<region>.amazonaws.com/sams-collectibles:latest
docker push 315414901942.dkr.ecr.us-west-2.amazonaws.com/sams-collectibles:latest
```

## Step 3: Set Up PostgreSQL in a Container

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
aws ecs create-cluster --cluster-name sams-collectibles-ecs-cluster
```

### Step A: Setting Up Networking and Security Groups
You can create a VPC and subnets using the CLI→:

- Create a new VPC.
- Create at least two subnets within different availability zones for redundancy.

#### A.1 Create a VPC
```bash
# Create a VPC with a specified CIDR block (10.0.0.0/16)
aws ec2 create-vpc --cidr-block 10.0.0.0/16 --tag-specifications 'ResourceType=vpc,Tags=[{Key=Name,Value=sams-collectibles-vpc}]'
```
Take note of the VpcId returned from the output, as you will need it for subsequent commands. \
For this example, let’s assume VpcId is vpc-xxxxxx.

#### A.1.1 Create a VPC
To list your existing VPCs and find the VpcId for the VPC you just created, use the following AWS CLI command:

```bash
aws ec2 describe-vpcs --query "Vpcs[*].{ID:VpcId, CIDR: CidrBlock, Name:Tags[?Key=='Name']|[0].Value}" --output table
```

Explanation:

	•	--query: Filters the output to show only the VpcId, CidrBlock, and Name tag for each VPC.
	•	--output table: Formats the output in a readable table format.

The output will look like this:

```
---------------------------------------------------------------------
|                           DescribeVpcs                            |
+---------------+-------------------------+-------------------------+
|     CIDR      |           ID            |          Name           |
+---------------+-------------------------+-------------------------+
|  172.31.0.0/16|  vpc-0731d262           |  None                   |
|  10.0.0.0/16  |  vpc-078dc2a6c620f0c70  |  sams-collectibles-vpc  |
+---------------+-------------------------+-------------------------+
```

This command will help you locate the VpcId for your newly created VPC. Replace vpc-xxxxxx with your actual VpcId in subsequent commands.
#### A.2 Create Subnets in Different Availability Zones
```bash
# Create the first subnet in Availability Zone us-west-2a with the real vpc-id
aws ec2 create-subnet --vpc-id vpc-078dc2a6c620f0c70 --cidr-block 10.0.1.0/24 --availability-zone us-west-2a --tag-specifications 'ResourceType=subnet,Tags=[{Key=Name,Value=sams-collectibles-subnet-1}]'

# Create the second subnet in Availability Zone us-west-2b with the real vpc-id
aws ec2 create-subnet --vpc-id vpc-078dc2a6c620f0c70 --cidr-block 10.0.2.0/24 --availability-zone us-west-2b --tag-specifications 'ResourceType=subnet,Tags=[{Key=Name,Value=sams-collectibles-subnet-2}]'
```
These commands create two subnets within the specified VPC, each in a different availability zone for redundancy.

To list your subnets in the us-west-2 region and filter the output to show only those with a 10.x.x.x CIDR block, you can use the following AWS CLI command with a --query filter:

```bash
aws ec2 describe-subnets --region us-west-2 \
    --query "Subnets[?starts_with(CidrBlock, '10.')].{ID:SubnetId, CIDR:CidrBlock, VPC:VpcId, AZ:AvailabilityZone, Name:Tags[?Key=='Name']|[0].Value}" \
    --output table
```

Explanation:

	+	--region us-west-2: Specifies the us-west-2 region.
	+	--query: Uses a filter to restrict results to subnets with a CIDR block that starts with 10..
	  -   The filter starts_with(CidrBlock, '10.') checks if the CidrBlock begins with 10..
	  _	  {ID:SubnetId, CIDR:CidrBlock, VPC:VpcId, AZ:AvailabilityZone, Name:Tags[?Key=='Name']|[0].Value} specifies which fields to include in the output.
	+	--output table: Formats the output in a table for readability.

Sample Output:

This will display a table of subnets in us-west-2 with 10.x.x.x CIDR blocks:

```
------------------------------------------------------------------------------------------------------------------
|                                                 DescribeSubnets                                                |
+------------+--------------+---------------------------+------------------------------+-------------------------+
|     AZ     |    CIDR      |            ID             |            Name              |           VPC           |
+------------+--------------+---------------------------+------------------------------+-------------------------+
|  us-west-2a|  10.0.1.0/24 |  subnet-005c50966587f9b98 |  sams-collectibles-subnet-1  |  vpc-078dc2a6c620f0c70  |
|  us-west-2b|  10.0.2.0/24 |  subnet-0dfe8dcf83c0842d4 |  sams-collectibles-subnet-2  |  vpc-078dc2a6c620f0c70  |
+------------+--------------+---------------------------+------------------------------+-------------------------+
```

This command helps you quickly identify subnets with CIDR blocks in the 10.x.x.x range in us-west-2.



#### A.3 Create the Web Security Group (sams-collectibles-web-sg)
```bash
# Create Web Security Group with tag name sams-collectibles-web-sg
aws ec2 create-security-group --group-name sams-collectibles-web-sg \
    --description "Web security group for Django Fargate app" \
    --vpc-id vpc-078dc2a6c620f0c70 \
    --tag-specifications 'ResourceType=security-group,Tags=[{Key=Name,Value=sams-collectibles-web-sg}]'
```

#### A.3.1 List the Web Security Group (sams-collectibles-web-sg)
```bash
aws ec2 describe-security-groups --region us-west-2 \
    --filters "Name=tag:Name,Values=sams-collectibles-web-sg,sams-collectibles-db-sg" \
    --query "SecurityGroups[*].{ID:GroupId, Name:GroupName, Description:Description, VPC:VpcId}" \
    --output table
```
Which returns:
```
----------------------------------------------------------------------------------------------------------------------------
|                                                  DescribeSecurityGroups                                                  |
+--------------------------------------------+-----------------------+---------------------------+-------------------------+
|                 Description                |          ID           |           Name            |           VPC           |
+--------------------------------------------+-----------------------+---------------------------+-------------------------+
|  Web security group for Django Fargate app |  sg-029eb602389458954 |  sams-collectibles-web-sg |  vpc-078dc2a6c620f0c70  |
+--------------------------------------------+-----------------------+---------------------------+-------------------------+
|                                                                                                                          |
----------------------------------------------------------------------------------------------------------------------------
```

Assume the GroupId returned is sg-web-xxxxxx, sg-029eb602389458954 . You’ll use this GroupId to set inbound and outbound rules.

4. Create the PostgreSQL Security Group (sams-collectibles-db-sg)

4.1 Create the Security Group for PostgreSQL
```bash
# Create PostgreSQL Security Group
aws ec2 create-security-group --group-name sams-collectibles-db-sg \
    --description "PostgreSQL Database security group for Django Fargate app" \
    --vpc-id vpc-078dc2a6c620f0c70 \
    --tag-specifications 'ResourceType=security-group,Tags=[{Key=Name,Value=sams-collectibles-db-sg}]'
```
Using the above sg list command the output for both should look like:
```
--------------------------------------------------------------------------------------------------------------------------------------------
|                                                          DescribeSecurityGroups                                                          |
+------------------------------------------------------------+-----------------------+---------------------------+-------------------------+
|                         Description                        |          ID           |           Name            |           VPC           |
+------------------------------------------------------------+-----------------------+---------------------------+-------------------------+
|  PostgreSQL Database security group for Django Fargate app |  sg-00242036d9be9884a |  sams-collectibles-db-sg  |  vpc-078dc2a6c620f0c70  |
|  Web security group for Django Fargate app                 |  sg-029eb602389458954 |  sams-collectibles-web-sg |  vpc-078dc2a6c620f0c70  |
+------------------------------------------------------------+-----------------------+---------------------------+-------------------------+
```
With that add the below Inbound rules

3.2 Add Inbound Rules to Web Security Group

```bash
# Allow HTTP (port 80) on the web security group
aws ec2 authorize-security-group-ingress --group-id sg-029eb602389458954 --protocol tcp --port 80 --cidr 0.0.0.0/0

# Allow HTTPS (port 443) on the web security group
aws ec2 authorize-security-group-ingress --group-id sg-029eb602389458954 --protocol tcp --port 443 --cidr 0.0.0.0/0

# Allow the web security group to access the database on port 5432
aws ec2 authorize-security-group-ingress --group-id sg-029eb602389458954 --protocol tcp --port 5432 --source-group sg-00242036d9be9884a
```
It should return an output of:
```
----------------------------------------------------------------------------------------------------------------------------------
|                                                  AuthorizeSecurityGroupIngress                                                 |
+----------------------------------------------------------------------+---------------------------------------------------------+
|  Return                                                              |  True                                                   |
+----------------------------------------------------------------------+---------------------------------------------------------+
||                                                      SecurityGroupRules                                                      ||
|+-----------+-----------+-----------------------+---------------+-------------+-----------+-------------------------+----------+|
|| CidrIpv4  | FromPort  |        GroupId        | GroupOwnerId  | IpProtocol  | IsEgress  |   SecurityGroupRuleId   | ToPort   ||
|+-----------+-----------+-----------------------+---------------+-------------+-----------+-------------------------+----------+|
||  0.0.0.0/0|  80       |  sg-029eb602389458954 |  315414901942 |  tcp        |  False    |  sgr-02918aafb28d98b31  |  80      ||
|+-----------+-----------+-----------------------+---------------+-------------+-----------+-------------------------+----------+|
```

Add Outbound Rule to Web Security Group

By default, security groups in AWS allow all outbound traffic. If for some reason this is not the case in your configuration, you can explicitly set it:
```bash
# Add Outbound Rule to Web Security Group
aws ec2 authorize-security-group-egress --group-id sg-029eb602389458954 --protocol -1 --port all --cidr 0.0.0.0/0
```

Add Inbound Rule to Database Security Group
```bash
# Allow access on port 5432 from the web security group only
aws ec2 authorize-security-group-ingress --group-id sg-00242036d9be9884a --protocol tcp --port 5432 --source-group sg-029eb602389458954
```

Add Outbound Rule to Database Security Group
Again, by default, all outbound traffic is allowed in AWS security groups, but if you need to set it explicitly:
```bash
aws ec2 authorize-security-group-egress --group-id sg-00242036d9be9884a   --protocol -1 --port all --cidr 0.0.0.0/0
```


#### A.2 
```bash
aws ec2 describe-security-groups --region us-west-2 \
    --filters "Name=tag:Name,Values=sams-collectibles-web-sg,sams-collectibles-db-sg" \
    --query "SecurityGroups[*].{ID:GroupId, Name:GroupName, Description:Description, VPC:VpcId, Ingress:IpPermissions, Egress:IpPermissionsEgress}" \
    --output table \
    --no-cli-pager
```
Output of above command:
```plaintext
-------------------------------------------------------------------------------------------------------------------------------------------
|                                                         DescribeSecurityGroups                                                          |
+-------------------------------------------------+--------------------------+-------------------------------+----------------------------+
|                   Description                   |           ID             |             Name              |            VPC             |
+-------------------------------------------------+--------------------------+-------------------------------+----------------------------+
|  Web security group for Django Fargate app      |  sg-029eb602389458954    |  sams-collectibles-web-sg     |  vpc-078dc2a6c620f0c70     |
+-------------------------------------------------+--------------------------+-------------------------------+----------------------------+
||                                                                Egress                                                                 ||
|+---------------------------------------------------------------------------------------------------------------------------------------+|
||                                                              IpProtocol                                                               ||
|+---------------------------------------------------------------------------------------------------------------------------------------+|
||  -1                                                                                                                                   ||
|+---------------------------------------------------------------------------------------------------------------------------------------+|
|||                                                              IpRanges                                                               |||
||+-------------------------------------------------------------------------------------------------------------------------------------+||
|||                                                               CidrIp                                                                |||
||+-------------------------------------------------------------------------------------------------------------------------------------+||
|||  0.0.0.0/0                                                                                                                          |||
||+-------------------------------------------------------------------------------------------------------------------------------------+||
||                                                                Ingress                                                                ||
|+--------------------------------------------+----------------------------------------------------+-------------------------------------+|
||                  FromPort                  |                    IpProtocol                      |               ToPort                ||
|+--------------------------------------------+----------------------------------------------------+-------------------------------------+|
||  80                                        |  tcp                                               |  80                                 ||
|+--------------------------------------------+----------------------------------------------------+-------------------------------------+|
|||                                                              IpRanges                                                               |||
||+-------------------------------------------------------------------------------------------------------------------------------------+||
|||                                                               CidrIp                                                                |||
||+-------------------------------------------------------------------------------------------------------------------------------------+||
|||  0.0.0.0/0                                                                                                                          |||
||+-------------------------------------------------------------------------------------------------------------------------------------+||
||                                                                Ingress                                                                ||
|+--------------------------------------------+----------------------------------------------------+-------------------------------------+|
||                  FromPort                  |                    IpProtocol                      |               ToPort                ||
|+--------------------------------------------+----------------------------------------------------+-------------------------------------+|
||  5432                                      |  tcp                                               |  5432                               ||
|+--------------------------------------------+----------------------------------------------------+-------------------------------------+|
|||                                                          UserIdGroupPairs                                                           |||
||+-------------------------------------------------------------------------------+-----------------------------------------------------+||
|||                                    GroupId                                    |                       UserId                        |||
||+-------------------------------------------------------------------------------+-----------------------------------------------------+||
|||  sg-00242036d9be9884a                                                         |  315414901942                                       |||
||+-------------------------------------------------------------------------------+-----------------------------------------------------+||
||                                                                Ingress                                                                ||
|+--------------------------------------------+----------------------------------------------------+-------------------------------------+|
||                  FromPort                  |                    IpProtocol                      |               ToPort                ||
|+--------------------------------------------+----------------------------------------------------+-------------------------------------+|
||  443                                       |  tcp                                               |  443                                ||
|+--------------------------------------------+----------------------------------------------------+-------------------------------------+|
|||                                                              IpRanges                                                               |||
||+-------------------------------------------------------------------------------------------------------------------------------------+||
|||                                                               CidrIp                                                                |||
||+-------------------------------------------------------------------------------------------------------------------------------------+||
|||  0.0.0.0/0                                                                                                                          |||
||+-------------------------------------------------------------------------------------------------------------------------------------+||
|                                                         DescribeSecurityGroups                                                          |
+------------------------------------------------------------+-----------------------+--------------------------+-------------------------+
|                         Description                        |          ID           |          Name            |           VPC           |
+------------------------------------------------------------+-----------------------+--------------------------+-------------------------+
|  PostgreSQL Database security group for Django Fargate app |  sg-00242036d9be9884a |  sams-collectibles-db-sg |  vpc-078dc2a6c620f0c70  |
+------------------------------------------------------------+-----------------------+--------------------------+-------------------------+
||                                                                Egress                                                                 ||
|+---------------------------------------------------------------------------------------------------------------------------------------+|
||                                                              IpProtocol                                                               ||
|+---------------------------------------------------------------------------------------------------------------------------------------+|
||  -1                                                                                                                                   ||
|+---------------------------------------------------------------------------------------------------------------------------------------+|
|||                                                              IpRanges                                                               |||
||+-------------------------------------------------------------------------------------------------------------------------------------+||
|||                                                               CidrIp                                                                |||
||+-------------------------------------------------------------------------------------------------------------------------------------+||
|||  0.0.0.0/0                                                                                                                          |||
||+-------------------------------------------------------------------------------------------------------------------------------------+||
||                                                                Ingress                                                                ||
|+--------------------------------------------+----------------------------------------------------+-------------------------------------+|
||                  FromPort                  |                    IpProtocol                      |               ToPort                ||
|+--------------------------------------------+----------------------------------------------------+-------------------------------------+|
||  5432                                      |  tcp                                               |  5432                               ||
|+--------------------------------------------+----------------------------------------------------+-------------------------------------+|
|||                                                          UserIdGroupPairs                                                           |||
||+-------------------------------------------------------------------------------+-----------------------------------------------------+||
|||                                    GroupId                                    |                       UserId                        |||
||+-------------------------------------------------------------------------------+-----------------------------------------------------+||
|||  sg-029eb602389458954                                                         |  315414901942                                       |||
||+-------------------------------------------------------------------------------+-----------------------------------------------------+||
```

#### A.3 Explanation of Security Groups:
The configuration for both security groups (sams-collectibles-web-sg and sams-collectibles-db-sg). Here’s a breakdown of each section and what to look for:

Security Group for Web (sams-collectibles-web-sg)

	•	Description: Clearly indicates it’s the web security group.
	•	Egress Rule:
	    •	Allows all outbound traffic (IpProtocol: '-1' with CidrIp: 0.0.0.0/0), which is standard for web security groups to enable internet communication.
	•	Ingress Rules:
      -	Port 80 (HTTP): Allows inbound HTTP traffic from any IPv4 address (CidrIp: 0.0.0.0/0).
      -	Port 443 (HTTPS): Allows inbound HTTPS traffic from any IPv4 address (CidrIp: 0.0.0.0/0).
      -	Port 5432:
        •	Allows inbound traffic on port 5432 (PostgreSQL) specifically from the database security group (sg-00242036d9be9884a), identified under UserIdGroupPairs.
        •	This configuration restricts PostgreSQL access to only the security group sams-collectibles-db-sg, as intended.

Security Group for Database (sams-collectibles-db-sg)

	•	Description: Indicates it’s the database security group.
	•	Egress Rule:
	  -   Allows all outbound traffic (IpProtocol: '-1' with CidrIp: 0.0.0.0/0), which is typical for internal resources.
	•	Ingress Rule:
	  -	  Port 5432:
	  -	  Allows inbound traffic on port 5432 from sg-029eb602389458954 (sams-collectibles-web-sg), enabling internal communication with the web application only.


Summary

Your configuration looks correct:

	•	Web Security Group (sams-collectibles-web-sg): Allows HTTP, HTTPS from anywhere, and PostgreSQL access only from the database security group.
	•	Database Security Group (sams-collectibles-db-sg): Restricts access to port 5432 to only the web security group.

This configuration aligns with security best practices for AWS setups, where database access is restricted to only necessary internal resources.
#### A.3 Assign Security Groups to the Fargate Task

Ensure that both security groups are assigned to your Fargate task definition when deploying the service.

### Step B: Deploying the ECS Task Definition

#### B.1 Deploy Using AWS CLI

##### B.1.1 Register the ECS Task Definition

Assuming your task definition JSON is ready (`sams-collectibles-task.json`):

```bash
aws ecs register-task-definition --cli-input-json file://sams-collectibles-task.json
```

##### B.1.2 Create the ECS Fargate Service
Step 1: Register Task Definition (if not already done)

Make sure your task definition includes any container configurations you need. Here’s an example task definition file, sams-collectibles-task.json, which you can modify as necessary:
Create the Fargate service and launch your task:
```json
{
  "family": "sams-collectibles-task",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "256",
  "memory": "512",
  "containerDefinitions": [
    {
      "name": "web",
      "image": "<your_ecr_repository_url>:latest",
      "portMappings": [
        {
          "containerPort": 80,
          "protocol": "tcp"
        }
      ],
      "essential": true
    }
  ]
}
```
Register the task definition:

```bash
aws ecs register-task-definition --cli-input-json file://samscollectibles/static/json/sams-collectibles-task.json
```
Output:
```
--------------------------------------------------------------------------------------------------------
|                                        RegisterTaskDefinition                                        |
+------------------------------------------------------------------------------------------------------+
||                                           taskDefinition                                           ||
|+-------------------+--------------------------------------------------------------------------------+|
||  cpu              |  256                                                                           ||
||  family           |  sams-collectibles-task                                                        ||
||  memory           |  512                                                                           ||
||  networkMode      |  awsvpc                                                                        ||
||  registeredAt     |  2024-11-09T20:12:31.949000-08:00                                              ||
||  registeredBy     |  arn:aws:iam::315414901942:root                                                ||
||  revision         |  1                                                                             ||
||  status           |  ACTIVE                                                                        ||
||  taskDefinitionArn|  arn:aws:ecs:us-west-2:315414901942:task-definition/sams-collectibles-task:1   ||
|+-------------------+--------------------------------------------------------------------------------+|
|||                                          compatibilities                                         |||
||+--------------------------------------------------------------------------------------------------+||
|||  EC2                                                                                             |||
|||  FARGATE                                                                                         |||
||+--------------------------------------------------------------------------------------------------+||
|||                                       containerDefinitions                                       |||
||+-----------------------+--------------------------------------------------------------------------+||
|||  cpu                  |  0                                                                       |||
|||  essential            |  True                                                                    |||
|||  image                |  sams-collectibles:latest                                                |||
|||  name                 |  sams-collectibles-web-container-defs                                    |||
||+-----------------------+--------------------------------------------------------------------------+||
||||                                          portMappings                                          ||||
|||+-------------------------------------------------------------------+----------------------------+|||
||||  containerPort                                                    |  80                        ||||
||||  hostPort                                                         |  80                        ||||
||||  protocol                                                         |  tcp                       ||||
|||+-------------------------------------------------------------------+----------------------------+|||
|||                                        requiresAttributes                                        |||
||+--------------------------------------------------------------------------------------------------+||
|||                                               name                                               |||
||+--------------------------------------------------------------------------------------------------+||
|||  com.amazonaws.ecs.capability.docker-remote-api.1.18                                             |||
|||  ecs.capability.task-eni                                                                         |||
||+--------------------------------------------------------------------------------------------------+||
|||                                      requiresCompatibilities                                     |||
||+--------------------------------------------------------------------------------------------------+||
|||  FARGATE                                                                                         |||
||+--------------------------------------------------------------------------------------------------+||
```


Step 2: Create ECS Service with Security Groups and Subnets

When creating or updating the ECS service, specify both security groups and subnets in the networkConfiguration parameter.

Command to Create the Service
```bash
aws ecs create-service \
    --cluster sams-collectibles-ecs-cluster \
    --service-name sams-collectibles-service \
    --task-definition sams-collectibles-task \
    --desired-count 1 \
    --launch-type FARGATE \
    --network-configuration "awsvpcConfiguration={subnets=[subnet-005c50966587f9b98,subnet-0dfe8dcf83c0842d4],securityGroups=[sg-029eb602389458954,sg-00242036d9be9884a],assignPublicIp=ENABLED}"
```

Output:
```
-------------------------------------------------------------------------------------------------------------------------------------------
|                                                              CreateService                                                              |
+-----------------------------------------------------------------------------------------------------------------------------------------+
||                                                                service                                                                ||
|+-------------------------------+-------------------------------------------------------------------------------------------------------+|
||  clusterArn                   |  arn:aws:ecs:us-west-2:315414901942:cluster/sams-collectibles-ecs-cluster                             ||
||  createdAt                    |  2024-11-09T20:17:42.190000-08:00                                                                     ||
||  createdBy                    |  arn:aws:iam::315414901942:root                                                                       ||
||  desiredCount                 |  1                                                                                                    ||
||  enableECSManagedTags         |  False                                                                                                ||
||  enableExecuteCommand         |  False                                                                                                ||
||  healthCheckGracePeriodSeconds|  0                                                                                                    ||
||  launchType                   |  FARGATE                                                                                              ||
||  pendingCount                 |  0                                                                                                    ||
||  platformFamily               |  Linux                                                                                                ||
||  platformVersion              |  LATEST                                                                                               ||
||  propagateTags                |  NONE                                                                                                 ||
||  roleArn                      |  arn:aws:iam::315414901942:role/aws-service-role/ecs.amazonaws.com/AWSServiceRoleForECS               ||
||  runningCount                 |  0                                                                                                    ||
||  schedulingStrategy           |  REPLICA                                                                                              ||
||  serviceArn                   |  arn:aws:ecs:us-west-2:315414901942:service/sams-collectibles-ecs-cluster/sams-collectibles-service   ||
||  serviceName                  |  sams-collectibles-service                                                                            ||
||  status                       |  ACTIVE                                                                                               ||
||  taskDefinition               |  arn:aws:ecs:us-west-2:315414901942:task-definition/sams-collectibles-task:1                          ||
|+-------------------------------+-------------------------------------------------------------------------------------------------------+|
|||                                                       deploymentConfiguration                                                       |||
||+-------------------------------------------------------------------------------------------------------+-----------------------------+||
|||  maximumPercent                                                                                       |  200                        |||
|||  minimumHealthyPercent                                                                                |  100                        |||
||+-------------------------------------------------------------------------------------------------------+-----------------------------+||
||||                                                     deploymentCircuitBreaker                                                      ||||
|||+--------------------------------------------------------------------------+--------------------------------------------------------+|||
||||  enable                                                                  |  False                                                 ||||
||||  rollback                                                                |  False                                                 ||||
|||+--------------------------------------------------------------------------+--------------------------------------------------------+|||
|||                                                        deploymentController                                                         |||
||+----------------------------------------------------------------------+--------------------------------------------------------------+||
|||  type                                                                |  ECS                                                         |||
||+----------------------------------------------------------------------+--------------------------------------------------------------+||
|||                                                             deployments                                                             |||
||+---------------------------+---------------------------------------------------------------------------------------------------------+||
|||  createdAt                |  2024-11-09T20:17:42.190000-08:00                                                                       |||
|||  desiredCount             |  0                                                                                                      |||
|||  failedTasks              |  0                                                                                                      |||
|||  id                       |  ecs-svc/9860234021000529940                                                                            |||
|||  launchType               |  FARGATE                                                                                                |||
|||  pendingCount             |  0                                                                                                      |||
|||  platformFamily           |  Linux                                                                                                  |||
|||  platformVersion          |  1.4.0                                                                                                  |||
|||  rolloutState             |  IN_PROGRESS                                                                                            |||
|||  rolloutStateReason       |  ECS deployment ecs-svc/9860234021000529940 in progress.                                                |||
|||  runningCount             |  0                                                                                                      |||
|||  status                   |  PRIMARY                                                                                                |||
|||  taskDefinition           |  arn:aws:ecs:us-west-2:315414901942:task-definition/sams-collectibles-task:1                            |||
|||  updatedAt                |  2024-11-09T20:17:42.190000-08:00                                                                       |||
||+---------------------------+---------------------------------------------------------------------------------------------------------+||
||||                                                       networkConfiguration                                                        ||||
|||+-----------------------------------------------------------------------------------------------------------------------------------+|||
|||||                                                       awsvpcConfiguration                                                       |||||
||||+-------------------------------------------------------------------------------+-------------------------------------------------+||||
|||||  assignPublicIp                                                               |  ENABLED                                        |||||
||||+-------------------------------------------------------------------------------+-------------------------------------------------+||||
||||||                                                        securityGroups                                                         ||||||
|||||+-------------------------------------------------------------------------------------------------------------------------------+|||||
||||||  sg-029eb602389458954                                                                                                         ||||||
||||||  sg-00242036d9be9884a                                                                                                         ||||||
|||||+-------------------------------------------------------------------------------------------------------------------------------+|||||
||||||                                                            subnets                                                            ||||||
|||||+-------------------------------------------------------------------------------------------------------------------------------+|||||
||||||  subnet-005c50966587f9b98                                                                                                     ||||||
||||||  subnet-0dfe8dcf83c0842d4                                                                                                     ||||||
|||||+-------------------------------------------------------------------------------------------------------------------------------+|||||
|||                                                        networkConfiguration                                                         |||
||+-------------------------------------------------------------------------------------------------------------------------------------+||
||||                                                        awsvpcConfiguration                                                        ||||
||||+-------------------------------------------------------------------------------+-------------------------------------------------+||||
|||||  assignPublicIp                                                               |  ENABLED                                        |||||
||||+-------------------------------------------------------------------------------+-------------------------------------------------+||||
||||||                                                        securityGroups                                                         ||||||
|||||+-------------------------------------------------------------------------------------------------------------------------------+|||||
||||||  sg-029eb602389458954                                                                                                         ||||||
||||||  sg-00242036d9be9884a                                                                                                         ||||||
|||||+-------------------------------------------------------------------------------------------------------------------------------+|||||
||||||                                                            subnets                                                            ||||||
|||||+-------------------------------------------------------------------------------------------------------------------------------+|||||
||||||  subnet-005c50966587f9b98                                                                                                     ||||||
||||||  subnet-0dfe8dcf83c0842d4                                                                                                     ||||||
|||||+-------------------------------------------------------------------------------------------------------------------------------+|||||
|||                                                        networkConfiguration                                                         |||
||+-------------------------------------------------------------------------------------------------------------------------------------+||
||||                                                        awsvpcConfiguration                                                        ||||
|||+---------------------------------------------------------------------------------+-------------------------------------------------+|||
||||  assignPublicIp                                                                 |  ENABLED                                        ||||
|||+---------------------------------------------------------------------------------+-------------------------------------------------+|||
|||||                                                         securityGroups                                                          |||||
||||+---------------------------------------------------------------------------------------------------------------------------------+||||
|||||  sg-029eb602389458954                                                                                                           |||||
|||||  sg-00242036d9be9884a                                                                                                           |||||
||||+---------------------------------------------------------------------------------------------------------------------------------+||||
|||||                                                             subnets                                                             |||||
||||+---------------------------------------------------------------------------------------------------------------------------------+||||
|||||  subnet-005c50966587f9b98                                                                                                       |||||
|||||  subnet-0dfe8dcf83c0842d4                                                                                                       |||||
||||+---------------------------------------------------------------------------------------------------------------------------------+||||
```


Command to Update the Service (if the service already exists)

If the ECS service is already created, you can update it to assign the security groups:
```bash
aws ecs update-service \
    --cluster sams-collectibles-cluster \
    --service sams-collectibles-service \
    --network-configuration "awsvpcConfiguration={subnets=[subnet-005c50966587f9b98,subnet-0dfe8dcf83c0842d4],securityGroups=[sg-029eb602389458954,sg-00242036d9be9884a],assignPublicIp=ENABLED}"
```

AWS Fargate service to write logs to CloudWatch. To resolve this, you’ll need to:
	1.	Create an ECS task execution role (if you don’t have one already).
	2.	Attach the necessary policy to the role to enable logging.
	3.	Specify the execution role in your task definition.

Step 1: Create an ECS Task Execution Role (If Not Already Created)

If you don’t have an ECS execution role, create one using the following command:
```bash
aws iam create-role \
    --role-name ecsTaskExecutionRole \
    --assume-role-policy-document file://<(echo '{
      "Version": "2012-10-17",
      "Statement": [
        {
          "Effect": "Allow",
          "Principal": {
            "Service": "ecs-tasks.amazonaws.com"
          },
          "Action": "sts:AssumeRole"
        }
      ]
    }')
```

Output:
```
-------------------------------------------------------------------------------------------------------------------------------------------------
|                                                                  CreateRole                                                                   |
+-----------------------------------------------------------------------------------------------------------------------------------------------+
||                                                                    Role                                                                     ||
|+------------------------------------------------------+----------------------------+-------+------------------------+------------------------+|
||                          Arn                         |        CreateDate          | Path  |        RoleId          |       RoleName         ||
|+------------------------------------------------------+----------------------------+-------+------------------------+------------------------+|
||  arn:aws:iam::315414901942:role/ecsTaskExecutionRole |  2024-11-10T04:51:40+00:00 |  /    |  AROAUS4BROS3BCQ3BQ7Y7 |  ecsTaskExecutionRole  ||
|+------------------------------------------------------+----------------------------+-------+------------------------+------------------------+|
|||                                                         AssumeRolePolicyDocument                                                          |||
||+------------------------------------------------------------+------------------------------------------------------------------------------+||
|||  Version                                                   |  2012-10-17                                                                  |||
||+------------------------------------------------------------+------------------------------------------------------------------------------+||
||||                                                                Statement                                                                ||||
|||+---------------------------------------------------------------------------------------+-------------------------------------------------+|||
||||                                        Action                                         |                     Effect                      ||||
|||+---------------------------------------------------------------------------------------+-------------------------------------------------+|||
||||  sts:AssumeRole                                                                       |  Allow                                          ||||
|||+---------------------------------------------------------------------------------------+-------------------------------------------------+|||
|||||                                                               Principal                                                               |||||
||||+--------------------------------------+------------------------------------------------------------------------------------------------+||||
|||||  Service                             |  ecs-tasks.amazonaws.com                                                                       |||||
||||+--------------------------------------+------------------------------------------------------------------------------------------------+||||
```

Step 2: Attach the Required Policy to the Execution Role

Attach the AmazonECSTaskExecutionRolePolicy managed policy to this role, which grants permissions to write logs to CloudWatch and pull images from Amazon ECR:

```bash
aws iam attach-role-policy \
    --role-name ecsTaskExecutionRole \
    --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy
```
Now, modify your task definition JSON (sams-collectibles-task.json) to include the executionRoleArn field. Here’s the updated JSON:

```json
{
  "family": "sams-collectibles-task",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "256",
  "memory": "512",
  "executionRoleArn": "arn:aws:iam::315414901942:role/ecsTaskExecutionRole",
  "containerDefinitions": [
    {
      "name": "sams-collectibles-web-container-defs",
      "image": "sams-collectibles:latest",
      "portMappings": [
        {
          "containerPort": 80,
          "protocol": "tcp"
        }
      ],
      "essential": true,
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/sams-collectibles",
          "awslogs-region": "us-west-2",
          "awslogs-stream-prefix": "ecs"
        }
      }
    }
  ]
}
```

Step 4: Register the Task Definition

With the updated task definition, register it again:

```bash
aws ecs register-task-definition --cli-input-json file://samscollectibles/static/json/sams-collectibles-task.json
```


#### B.2 Deploy Using AWS Management Console

##### B.2.1 Register the Task Definition

1. Log in to the AWS Console.
2. Navigate to the **ECS Dashboard** → **Task Definitions**.
3. Click **Create new Task Definition** and select **Fargate** as the launch type.
4. Fill out the task definition details and add container definitions for both Django and PostgreSQL.

##### B.2.2 Create the ECS Service

1. In the ECS Dashboard, go to **Clusters** and select your cluster (`sams-collectibles-cluster`).
2. Click on **Create** under the **Services** tab.
3. Use your task definition and set the service details, such as the number of tasks, VPC, subnets, and security groups.

### Additional Configuration

- Ensure both the Django and PostgreSQL containers are in the same VPC/Subnet for communication.

## Additional Resources
- Use AWS Secrets Manager for managing sensitive credentials.
- Integrate CloudWatch for logging and monitoring your services.
