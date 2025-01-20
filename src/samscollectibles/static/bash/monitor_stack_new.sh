#!/bin/bash

STACK_NAME="sams-collectibles-FargateStack"
REGION="us-west-2"
TIMEOUT=1200 # 20 minutes in seconds
INTERVAL=10 # Check every 10 seconds
ELAPSED=0

echo "Monitoring CloudFormation stack creation for $STACK_NAME in $REGION"
echo "Script will exit after 20 minutes if no result is found."

while [ $ELAPSED -lt $TIMEOUT ]; do
    STATUS=$(aws cloudformation describe-stacks \
        --stack-name "$STACK_NAME" \
        --region "$REGION" \
        --output json \
        --no-cli-pager | jq -r '.Stacks[].StackStatus')

    TIMESTAMP=$(date +"%Y-%m-%d %H:%M:%S")

    if [[ "$STATUS" == "CREATE_COMPLETE" || "$STATUS" == "ROLLBACK_COMPLETE" ]]; then
        echo "[$TIMESTAMP] Stack $STACK_NAME status: $STATUS"
        exit 0
    else
        echo "[$TIMESTAMP] Stack $STACK_NAME status: $STATUS"
    fi

    sleep $INTERVAL
    ELAPSED=$((ELAPSED + INTERVAL))
done

echo "[$(date +"%Y-%m-%d %H:%M:%S")] Timeout reached after 20 minutes. Fetching stack events for $STACK_NAME..."
aws cloudformation describe-stack-events \
    --stack-name "$STACK_NAME" \
    --region "$REGION" \
    --output json \
    --no-cli-pager | jq '.StackEvents[] | {LogicalResourceId, ResourceStatus, Timestamp, ResourceStatusReason}'
    