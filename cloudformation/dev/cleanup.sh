#!/bin/bash
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}========================================${NC}"
echo -e "${YELLOW}Bedrock Cost Keeper - Cleanup AWS Stack${NC}"
echo -e "${YELLOW}========================================${NC}\n"

# Configuration
STACK_NAME="bedrock-cost-keeper-dev-minimal"
REGION="${AWS_REGION:-us-east-1}"

# Check if AWS CLI is installed
if ! command -v aws &> /dev/null; then
    echo -e "${RED}Error: AWS CLI is not installed${NC}"
    exit 1
fi

# Check AWS credentials
echo -e "${YELLOW}Checking AWS credentials...${NC}"
if ! aws sts get-caller-identity &> /dev/null; then
    echo -e "${RED}Error: AWS credentials not configured${NC}"
    exit 1
fi

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
echo -e "${GREEN}✓ AWS Account ID: $ACCOUNT_ID${NC}\n"

# Check if stack exists
echo -e "${YELLOW}Checking if stack exists...${NC}"
if ! aws cloudformation describe-stacks --stack-name "$STACK_NAME" --region "$REGION" &> /dev/null; then
    echo -e "${YELLOW}Stack $STACK_NAME does not exist. Nothing to clean up.${NC}"
    exit 0
fi

echo -e "${GREEN}✓ Stack found${NC}\n"

# Show stack resources before deletion
echo -e "${YELLOW}Stack resources that will be deleted:${NC}"
aws cloudformation list-stack-resources \
  --stack-name "$STACK_NAME" \
  --region "$REGION" \
  --query 'StackResourceSummaries[].{Type:ResourceType,LogicalId:LogicalResourceId,Status:ResourceStatus}' \
  --output table

echo ""

# Confirm deletion
read -p "$(echo -e ${RED}Are you sure you want to delete the stack? This cannot be undone. [y/N]: ${NC})" -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo -e "${YELLOW}Cleanup cancelled${NC}"
    exit 0
fi

# Delete stack
echo -e "\n${YELLOW}Deleting CloudFormation stack...${NC}"
aws cloudformation delete-stack \
  --stack-name "$STACK_NAME" \
  --region "$REGION"

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Stack deletion initiated${NC}\n"
else
    echo -e "${RED}✗ Failed to initiate stack deletion${NC}"
    exit 1
fi

# Wait for deletion
echo -e "${YELLOW}Waiting for stack deletion to complete...${NC}"
echo -e "${YELLOW}This may take a few minutes...${NC}\n"

aws cloudformation wait stack-delete-complete \
  --stack-name "$STACK_NAME" \
  --region "$REGION"

if [ $? -eq 0 ]; then
    echo -e "\n${GREEN}✓ Stack deleted successfully!${NC}\n"
else
    echo -e "\n${RED}✗ Stack deletion failed or timed out${NC}"
    echo -e "${YELLOW}Check CloudFormation console for details:${NC}"
    echo "https://console.aws.amazon.com/cloudformation/home?region=$REGION#/stacks"
    exit 1
fi

# Clean up local files
echo -e "${YELLOW}Cleaning up local configuration files...${NC}"

if [ -f ".env.cloudformation" ]; then
    rm .env.cloudformation
    echo -e "${GREEN}✓ Removed .env.cloudformation${NC}"
fi

echo -e "\n${GREEN}========================================${NC}"
echo -e "${GREEN}Cleanup Complete!${NC}"
echo -e "${GREEN}========================================${NC}\n"

echo -e "${YELLOW}Note: Your local .env file was not modified.${NC}"
echo -e "${YELLOW}You may want to update it manually to remove AWS resource ARNs.${NC}\n"
