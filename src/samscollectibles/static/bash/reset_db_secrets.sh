#!/bin/bash
SECRET_NAME="sams-collectibles-db-secret"
REGION="us-west-2"

SECRET_VALUES=$(aws secretsmanager get-secret-value \
    --secret-id $SECRET_NAME \
    --region $REGION \
    --output json --no-cli-pager | jq -r '.SecretString | fromjson')

export DB_USER=$(echo $SECRET_VALUES | jq -r '.DB_USER')
export DB_PASSWORD=$(echo $SECRET_VALUES | jq -r '.DB_PASSWORD')
export DB_NAME=$(echo $SECRET_VALUES | jq -r '.DB_NAME')
export DB_HOST=$(echo $SECRET_VALUES | jq -r '.DB_HOST')
export DB_PORT=$(echo $SECRET_VALUES | jq -r '.DB_PORT')

echo "Secrets loaded into environment variables."