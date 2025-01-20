#!/bin/bash

# Monitor stack status with local timestamp
STACK_NAME="sams-collectibles-FargateStack"
REGION="us-west-2"
INTERVAL=10

while true; do
    echo "Checking stack status at $(date):"
    
    aws cloudformation describe-stack-events \
        --stack-name "$STACK_NAME" \
        --region "$REGION" \
        --output json \
        --no-cli-pager | jq -r '.StackEvents[] | {
            LogicalResourceId, 
            ResourceStatus, 
            CloudFormationTimestamp: .Timestamp,
            LocalTimestamp: "'$(date '+%Y-%m-%dT%H:%M:%S%z')'"
        }' | tee /tmp/stack_status.log

    # Check if a terminal state is reached
    if egrep -q 'CREATE_COMPLETE|ROLLBACK_COMPLETE' /tmp/stack_status.log; then
        echo "Stack reached a terminal state. Exiting."
        exit 0
    fi

    sleep "$INTERVAL"
done
