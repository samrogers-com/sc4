#!/bin/bash

# Configuration
CLUSTER_NAME="sams-collectibles-ecs-cluster"
SERVICE_NAME="sams-collectibles-service"
REGION="us-west-2"

echo "Fetching ECS task ID for service: $SERVICE_NAME..."

# Fetch Task ID (check for RUNNING tasks first, fallback to STOPPED tasks)
TASK_ARN=$(aws ecs list-tasks \
  --cluster $CLUSTER_NAME \
  --service-name $SERVICE_NAME \
  --desired-status RUNNING \
  --region $REGION \
  --output json --no-cli-pager | jq -r '.taskArns[0]')

if [ -z "$TASK_ARN" ]; then
  echo "No RUNNING tasks found. Checking STOPPED tasks..."
  TASK_ARN=$(aws ecs list-tasks \
    --cluster $CLUSTER_NAME \
    --desired-status STOPPED \
    --region $REGION \
    --output json --no-cli-pager | jq -r '.taskArns[0]')
fi

if [ -z "$TASK_ARN" ]; then
  echo "Error: No tasks found for the service $SERVICE_NAME."
  exit 1
fi

TASK_ID=$(echo "$TASK_ARN" | awk -F '/' '{print $NF}')
echo "Task ID: $TASK_ID"

echo "Fetching IAM Role used by ECS Task..."
ROLE_NAME=$(aws ecs describe-tasks \
  --cluster $CLUSTER_NAME \
  --tasks $TASK_ID \
  --region $REGION \
  --output json --no-cli-pager | jq -r '.tasks[0].overrides.taskRoleArn' | awk -F '/' '{print $NF}')

if [ -z "$ROLE_NAME" ]; then
  echo "Error: Could not determine the IAM Role for the ECS Task."
  exit 1
fi
echo "Role Name: $ROLE_NAME"

echo "Fetching policies attached to the role..."
ATTACHED_POLICIES=$(aws iam list-attached-role-policies \
  --role-name $ROLE_NAME \
  --region $REGION \
  --output json --no-cli-pager | jq -r '.AttachedPolicies[]')

if [ -z "$ATTACHED_POLICIES" ]; then
  echo "Error: No policies attached to the role."
  exit 1
fi

echo "Attached Policies:"
echo "$ATTACHED_POLICIES"

# Fetch the policy document for a specific policy
POLICY_ARN=$(echo "$ATTACHED_POLICIES" | jq -r '.PolicyArn' | head -n 1)
echo "Fetching policy document for: $POLICY_ARN"
aws iam get-policy \
  --policy-arn $POLICY_ARN \
  --region $REGION \
  --output json --no-cli-pager | jq '.Policy'