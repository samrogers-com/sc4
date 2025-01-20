#!/bin/bash

CLUSTER="sams-collectibles-ecs-cluster"
SERVICE="sams-collectibles-service"
REGION="us-west-2"

echo "Fetching service details..."
aws ecs describe-services \
  --cluster $CLUSTER \
  --services $SERVICE \
  --region $REGION \
  --output json --no-cli-pager

echo "Fetching task definition details..."
TASK_DEF=$(aws ecs describe-services \
  --cluster $CLUSTER \
  --services $SERVICE \
  --region $REGION \
  --output json --no-cli-pager | jq -r '.services[0].taskDefinition')
aws ecs describe-task-definition \
  --task-definition $TASK_DEF \
  --region $REGION \
  --output json --no-cli-pager

echo "Fetching the latest 3 stopped tasks..."
STOPPED_TASKS=$(aws ecs list-tasks \
  --cluster $CLUSTER \
  --desired-status STOPPED \
  --region $REGION \
  --output json --no-cli-pager | jq -r '.taskArns | .[:3] | join(" ")')

if [ -z "$STOPPED_TASKS" ]; then
  echo "No stopped tasks found."
else
  for TASK in $STOPPED_TASKS; do
    echo "Inspecting stopped task: $TASK"
    aws ecs describe-tasks \
      --cluster $CLUSTER \
      --tasks $TASK \
      --region $REGION \
      --output json --no-cli-pager | jq '.tasks[] | {taskArn: .taskArn, stoppedReason: .stoppedReason, containers: .containers}'
  done
fi

echo "Checking subnets and routes..."
aws ec2 describe-route-tables \
  --filters "Name=association.subnet-id,Values=subnet-005c50966587f9b98,subnet-0dfe8dcf83c0842d4" \
  --region $REGION \
  --output json --no-cli-pager | jq '.RouteTables[].Routes[] | select(.NatGatewayId != null)'

echo "Checking security groups..."
aws ec2 describe-security-groups \
  --group-ids sg-029eb602389458954 sg-00242036d9be9884a \
  --region $REGION \
  --output json --no-cli-pager