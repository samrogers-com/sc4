#!/bin/bash

set -e

REGION="us-west-2"
NAT_GATEWAY_ID="nat-0dfc6ef31daf8cf33"

echo "Fetching Network Interface ID for NAT Gateway..."
ENI_ID=$(aws ec2 describe-nat-gateways \
  --nat-gateway-ids $NAT_GATEWAY_ID \
  --region $REGION \
  --output json --no-cli-pager | jq -r '.NatGateways[0].NatGatewayAddresses[0].NetworkInterfaceId')

if [ -z "$ENI_ID" ]; then
  echo "Error: No Network Interface ID found for NAT Gateway $NAT_GATEWAY_ID."
  exit 1
fi

echo "Network Interface ID: $ENI_ID"

# Check Permissions for ModifyNetworkInterfaceAttribute
echo "Validating permissions for ModifyNetworkInterfaceAttribute..."
PERMISSIONS_CHECK=$(aws iam simulate-principal-policy \
  --policy-source-arn arn:aws:iam::<account-id>:role/<role-name> \
  --action-names ec2:ModifyNetworkInterfaceAttribute \
  --output json --no-cli-pager | jq -r '.EvaluationResults[0].EvalDecision')

if [[ "$PERMISSIONS_CHECK" != "allowed" ]]; then
  echo "Error: Insufficient permissions to modify network interface attributes."
  exit 1
fi

echo "Fetching Security Groups for the Network Interface..."
SG_IDS=$(aws ec2 describe-network-interfaces \
  --network-interface-ids $ENI_ID \
  --region $REGION \
  --output json --no-cli-pager | jq -r '.NetworkInterfaces[0].Groups[]?.GroupId')

if [ -z "$SG_IDS" ]; then
  echo "No security groups found on the network interface. Assigning a default security group..."

  # Fetch a default security group from the VPC
  DEFAULT_SG=$(aws ec2 describe-security-groups \
    --filters "Name=vpc-id,Values=vpc-078dc2a6c620f0c70" \
    --region $REGION \
    --output json --no-cli-pager | jq -r '.SecurityGroups[0].GroupId')

  if [ -z "$DEFAULT_SG" ]; then
    echo "Error: No security group found in the VPC. Please create one manually."
    exit 1
  fi

  echo "Assigning Security Group: $DEFAULT_SG to ENI: $ENI_ID..."
  aws ec2 modify-network-interface-attribute \
    --network-interface-id $ENI_ID \
    --groups $DEFAULT_SG \
    --region $REGION
  echo "Security Group $DEFAULT_SG successfully assigned to ENI $ENI_ID."
else
  echo "Security Groups already associated with ENI: $SG_IDS"
fi