#!/bin/bash
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Show usage information
show_usage() {
    cat << EOF
${GREEN}Bedrock Cost Keeper - CloudFormation Deployment (v2)${NC}

${BLUE}Usage:${NC}
    $0 [OPTIONS]

${BLUE}Options:${NC}
    --tag KEY=VALUE         Add a tag to the CloudFormation stack and all resources
                           Can be specified multiple times
                           Example: --tag Environment=dev --tag caylent:owner=user@example.com

    --region REGION        AWS region (default: us-east-1 or \$AWS_REGION)

    --help, -h             Show this help message

${BLUE}Note:${NC}
    This version uses create-stack/update-stack directly instead of 'deploy'
    to avoid tag parsing issues with special characters like colons.

EOF
    exit 0
}

# Initialize variables
TAGS_ARRAY=()

# Parse command-line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --tag)
            if [[ -z "$2" ]] || [[ "$2" == --* ]]; then
                echo -e "${RED}Error: --tag requires a KEY=VALUE argument${NC}"
                exit 1
            fi
            # Validate tag format
            if [[ ! "$2" =~ ^[^=]+=[^=]*$ ]]; then
                echo -e "${RED}Error: Invalid tag format. Use KEY=VALUE${NC}"
                exit 1
            fi
            TAGS_ARRAY+=("$2")
            shift 2
            ;;
        --region)
            if [[ -z "$2" ]] || [[ "$2" == --* ]]; then
                echo -e "${RED}Error: --region requires a value${NC}"
                exit 1
            fi
            AWS_REGION="$2"
            shift 2
            ;;
        --help|-h)
            show_usage
            ;;
        *)
            echo -e "${RED}Error: Unknown option: $1${NC}"
            echo "Use --help to see available options"
            exit 1
            ;;
    esac
done

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Bedrock Cost Keeper - Minimal AWS Setup${NC}"
echo -e "${GREEN}========================================${NC}\n"

# Configuration
STACK_NAME="bedrock-cost-keeper-dev-minimal"
ENVIRONMENT="dev"
REGION="${AWS_REGION:-us-east-1}"
TEMPLATE_FILE="minimal-aws-setup.yaml"

# Check if AWS CLI is installed
if ! command -v aws &> /dev/null; then
    echo -e "${RED}Error: AWS CLI is not installed${NC}"
    exit 1
fi

# Check if template file exists
if [ ! -f "$TEMPLATE_FILE" ]; then
    echo -e "${RED}Error: Template file not found: $TEMPLATE_FILE${NC}"
    exit 1
fi

# Check AWS credentials
echo -e "${YELLOW}Checking AWS credentials...${NC}"
if ! aws sts get-caller-identity &> /dev/null; then
    echo -e "${RED}Error: AWS credentials not configured${NC}"
    echo "Please run: aws configure"
    exit 1
fi

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
echo -e "${GREEN}✓ AWS Account ID: $ACCOUNT_ID${NC}"
echo -e "${GREEN}✓ Region: $REGION${NC}"

# Display tags if provided
if [ ${#TAGS_ARRAY[@]} -gt 0 ]; then
    echo -e "${GREEN}✓ Tags to apply:${NC}"
    for tag in "${TAGS_ARRAY[@]}"; do
        echo -e "  ${BLUE}• $tag${NC}"
    done
fi
echo ""

# Generate secrets
echo -e "${YELLOW}Generating secrets...${NC}"
JWT_SECRET=$(openssl rand -base64 32)
PROV_API_KEY=$(openssl rand -base64 32)
echo -e "${GREEN}✓ Secrets generated${NC}\n"

# Check if stack already exists
OPERATION="create-stack"
if aws cloudformation describe-stacks --stack-name "$STACK_NAME" --region "$REGION" &> /dev/null; then
    echo -e "${YELLOW}Stack $STACK_NAME already exists. Updating...${NC}"
    OPERATION="update-stack"
else
    echo -e "${YELLOW}Creating new stack $STACK_NAME...${NC}"
fi

# Deploy stack
echo -e "${YELLOW}Deploying CloudFormation stack...${NC}"

# Build tags in JSON format for create-stack/update-stack
TAGS_JSON='['
for i in "${!TAGS_ARRAY[@]}"; do
    tag="${TAGS_ARRAY[$i]}"
    KEY="${tag%%=*}"
    VALUE="${tag#*=}"

    if [ $i -gt 0 ]; then
        TAGS_JSON+=','
    fi
    # Properly escape JSON strings
    KEY_ESCAPED=$(echo -n "$KEY" | jq -Rs .)
    VALUE_ESCAPED=$(echo -n "$VALUE" | jq -Rs .)
    TAGS_JSON+="{\"Key\":$KEY_ESCAPED,\"Value\":$VALUE_ESCAPED}"
done
TAGS_JSON+=']'

# Debug: Show the tags JSON
echo -e "${BLUE}Tags JSON:${NC}"
echo "$TAGS_JSON" | jq .
echo ""

# Build parameters JSON
PARAMS_JSON="[
  {\"ParameterKey\":\"Environment\",\"ParameterValue\":\"$ENVIRONMENT\"},
  {\"ParameterKey\":\"JWTSecretKey\",\"ParameterValue\":\"$JWT_SECRET\"},
  {\"ParameterKey\":\"ProvisioningAPIKey\",\"ParameterValue\":\"$PROV_API_KEY\"}
]"

# Execute deployment
if [ "$OPERATION" = "create-stack" ]; then
    aws cloudformation create-stack \
      --stack-name "$STACK_NAME" \
      --template-body "file://$TEMPLATE_FILE" \
      --parameters "$PARAMS_JSON" \
      --tags "$TAGS_JSON" \
      --capabilities CAPABILITY_IAM \
      --region "$REGION"
else
    aws cloudformation update-stack \
      --stack-name "$STACK_NAME" \
      --template-body "file://$TEMPLATE_FILE" \
      --parameters "$PARAMS_JSON" \
      --tags "$TAGS_JSON" \
      --capabilities CAPABILITY_IAM \
      --region "$REGION" || {
        ERROR_MSG=$(aws cloudformation describe-stacks --stack-name "$STACK_NAME" --region "$REGION" --query 'Stacks[0].StackStatus' --output text 2>&1)
        if [[ "$ERROR_MSG" == *"No updates are to be performed"* ]] || aws cloudformation describe-stacks --stack-name "$STACK_NAME" --region "$REGION" --query 'Stacks[0].StackStatus' --output text 2>&1 | grep -q "UPDATE_COMPLETE"; then
            echo -e "${YELLOW}No updates needed${NC}"
        else
            exit 1
        fi
    }
fi

if [ $? -eq 0 ] || [ "$?" = "0" ]; then
    echo -e "\n${GREEN}✓ Stack operation initiated successfully!${NC}\n"
else
    echo -e "\n${RED}✗ Stack operation failed${NC}"
    exit 1
fi

# Wait for stack to be ready
echo -e "${YELLOW}Waiting for stack to be ready...${NC}"
if [ "$OPERATION" = "create-stack" ]; then
    aws cloudformation wait stack-create-complete \
      --stack-name "$STACK_NAME" \
      --region "$REGION"
else
    aws cloudformation wait stack-update-complete \
      --stack-name "$STACK_NAME" \
      --region "$REGION" 2>/dev/null || true
fi

# Fetch and display outputs
echo -e "\n${GREEN}========================================${NC}"
echo -e "${GREEN}Stack Outputs${NC}"
echo -e "${GREEN}========================================${NC}\n"

OUTPUTS=$(aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --region "$REGION" \
  --query 'Stacks[0].Outputs' \
  --output json)

echo "$OUTPUTS" | jq -r '.[] | "\(.OutputKey): \(.OutputValue)"'

# Extract key values for .env file
INFERENCE_PROFILE_ARN=$(echo "$OUTPUTS" | jq -r '.[] | select(.OutputKey=="InferenceProfileArn") | .OutputValue')
JWT_SECRET_NAME=$(echo "$OUTPUTS" | jq -r '.[] | select(.OutputKey=="JWTSecretName") | .OutputValue')
PROV_API_SECRET_NAME=$(echo "$OUTPUTS" | jq -r '.[] | select(.OutputKey=="ProvisioningAPISecretName") | .OutputValue')

# Create .env file snippet
echo -e "\n${GREEN}========================================${NC}"
echo -e "${GREEN}Environment Configuration${NC}"
echo -e "${GREEN}========================================${NC}\n"

cat > .env.cloudformation << EOF
# Generated by CloudFormation deployment: $(date)
# Stack: $STACK_NAME
# Region: $REGION

# AWS Configuration
AWS_ACCOUNT_ID=$ACCOUNT_ID
AWS_REGION=$REGION

# Inference Profile
SAMPLE_APP_INFERENCE_PROFILE_ARN=$INFERENCE_PROFILE_ARN

# Secrets Manager
JWT_SECRET_NAME=$JWT_SECRET_NAME
PROVISIONING_API_KEY_NAME=$PROV_API_SECRET_NAME
EOF

echo -e "${GREEN}✓ Environment configuration saved to: .env.cloudformation${NC}"
echo -e "${YELLOW}  Copy these values to your .env file in the project root${NC}\n"

cat .env.cloudformation

# Verify resources
echo -e "\n${GREEN}========================================${NC}"
echo -e "${GREEN}Verifying Resources${NC}"
echo -e "${GREEN}========================================${NC}\n"

echo -e "${YELLOW}Checking Inference Profile...${NC}"
PROFILE_ID=$(echo "$OUTPUTS" | jq -r '.[] | select(.OutputKey=="InferenceProfileId") | .OutputValue')
if aws bedrock get-inference-profile \
    --inference-profile-identifier "$PROFILE_ID" \
    --region "$REGION" &> /dev/null; then
    echo -e "${GREEN}✓ Inference Profile accessible${NC}"
else
    echo -e "${RED}✗ Inference Profile not accessible${NC}"
fi

echo -e "\n${YELLOW}Checking Secrets...${NC}"
if aws secretsmanager get-secret-value \
    --secret-id "$JWT_SECRET_NAME" \
    --region "$REGION" &> /dev/null; then
    echo -e "${GREEN}✓ JWT Secret accessible${NC}"
else
    echo -e "${RED}✗ JWT Secret not accessible${NC}"
fi

if aws secretsmanager get-secret-value \
    --secret-id "$PROV_API_SECRET_NAME" \
    --region "$REGION" &> /dev/null; then
    echo -e "${GREEN}✓ Provisioning API Secret accessible${NC}"
else
    echo -e "${RED}✗ Provisioning API Secret not accessible${NC}"
fi

echo -e "\n${GREEN}========================================${NC}"
echo -e "${GREEN}Deployment Complete!${NC}"
echo -e "${GREEN}========================================${NC}\n"

# Show applied tags
if [ ${#TAGS_ARRAY[@]} -gt 0 ]; then
    echo -e "${GREEN}Applied tags to stack and resources:${NC}"
    for tag in "${TAGS_ARRAY[@]}"; do
        echo -e "  ${BLUE}✓ $tag${NC}"
    done
    echo ""
fi

echo -e "${YELLOW}Next steps:${NC}"
echo "1. Copy values from .env.cloudformation to your project .env file"
echo "2. Start local development environment: ./scripts/dynamodb.sh start"
echo "3. Run tests: cd test-client && python manual_test.py"
echo ""
