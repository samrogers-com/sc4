#!/bin/bash

# Define variables
NAT_GATEWAY_ID="nat-0dfc6ef31daf8cf33"
REGION="us-west-2"

# Get the Network Interface ID of the NAT Gateway
echo "Fetching Network Interface ID for NAT Gateway..."
ENI_ID=$(aws ec2 describe-nat-gateways \
  --nat-gateway-ids $NAT_GATEWAY_ID \
  --region $REGION \
  --output json --no-cli-pager | jq -r '.NatGateways[0].NatGatewayAddresses[0].NetworkInterfaceId')

if [ -z "$ENI_ID" ]; then
  echo "Error: Could not retrieve Network Interface ID. Check NAT Gateway ID."
  exit 1
fi
echo "Network Interface ID: $ENI_ID"

# Get the Security Group IDs associated with the ENI
echo "Fetching Security Groups for the Network Interface..."
SECURITY_GROUP_IDS=$(aws ec2 describe-network-interfaces \
  --network-interface-ids $ENI_ID \
  --region $REGION \
  --output json --no-cli-pager | jq -r '.NetworkInterfaces[0].Groups[].GroupId')

if [ -z "$SECURITY_GROUP_IDS" ]; then
  echo "Error: Could not retrieve Security Group IDs for the Network Interface. Check ENI."
  exit 1
fi
echo "Security Group IDs: $SECURITY_GROUP_IDS"

# Describe the Security Groups for verification
echo "Describing Security Groups..."
for SG_ID in $SECURITY_GROUP_IDS; do
  aws ec2 describe-security-groups \
    --group-ids $SG_ID \
    --region $REGION \
    --output json --no-cli-pager | jq '.SecurityGroups[0]'
done

echo "Script completed successfully."