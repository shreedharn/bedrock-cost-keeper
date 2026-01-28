#!/bin/bash

set -e

# CloudFormation deployment script for Bedrock Cost Keeper
# Usage: ./deploy.sh <environment> [stack-name]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
CFN_DIR="$PROJECT_ROOT/cloudformation"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if environment is provided
if [ -z "$1" ]; then
    print_error "Environment not specified"
    echo "Usage: $0 <environment> [stack-name]"
    echo "Environments: dev, staging, prod"
    exit 1
fi

ENVIRONMENT=$1
STACK_NAME=${2:-"bedrock-cost-keeper-${ENVIRONMENT}"}
PARAMS_FILE="$CFN_DIR/parameters/${ENVIRONMENT}.json"
MASTER_TEMPLATE="$CFN_DIR/master-stack.yaml"

# Validate environment
if [[ ! "$ENVIRONMENT" =~ ^(dev|staging|prod)$ ]]; then
    print_error "Invalid environment: $ENVIRONMENT"
    echo "Valid environments: dev, staging, prod"
    exit 1
fi

# Check if parameters file exists
if [ ! -f "$PARAMS_FILE" ]; then
    print_error "Parameters file not found: $PARAMS_FILE"
    exit 1
fi

# Check if master template exists
if [ ! -f "$MASTER_TEMPLATE" ]; then
    print_error "Master template not found: $MASTER_TEMPLATE"
    exit 1
fi

# Check prerequisites
print_info "Checking prerequisites..."

# Check AWS CLI
if ! command -v aws &> /dev/null; then
    print_error "AWS CLI not found. Please install AWS CLI v2"
    exit 1
fi

# Check jq
if ! command -v jq &> /dev/null; then
    print_warn "jq not found. Install jq for better JSON handling"
fi

# Check AWS credentials
if ! aws sts get-caller-identity &> /dev/null; then
    print_error "AWS credentials not configured"
    exit 1
fi

AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
AWS_REGION=${AWS_REGION:-us-east-1}

print_info "AWS Account: $AWS_ACCOUNT_ID"
print_info "AWS Region: $AWS_REGION"
print_info "Environment: $ENVIRONMENT"
print_info "Stack Name: $STACK_NAME"

# Validate CloudFormation templates
print_info "Validating CloudFormation templates..."

# Validate master template
if aws cloudformation validate-template --template-body file://"$MASTER_TEMPLATE" &> /dev/null; then
    print_info "Master template is valid"
else
    print_error "Master template validation failed"
    exit 1
fi

# Validate nested stacks
for template in "$CFN_DIR"/stacks/*.yaml; do
    template_name=$(basename "$template")
    if aws cloudformation validate-template --template-body file://"$template" &> /dev/null; then
        print_info "Template $template_name is valid"
    else
        print_error "Template $template_name validation failed"
        exit 1
    fi
done

# Check if stack already exists
print_info "Checking if stack exists..."
if aws cloudformation describe-stacks --stack-name "$STACK_NAME" --region "$AWS_REGION" &> /dev/null; then
    STACK_EXISTS=true
    OPERATION="update"
    print_info "Stack exists. Will perform UPDATE operation"
else
    STACK_EXISTS=false
    OPERATION="create"
    print_info "Stack does not exist. Will perform CREATE operation"
fi

# Upload nested templates to S3 if TemplatesBucketName is specified
TEMPLATES_BUCKET=$(jq -r '.[] | select(.ParameterKey=="TemplatesBucketName") | .ParameterValue' "$PARAMS_FILE")

if [ -n "$TEMPLATES_BUCKET" ] && [ "$TEMPLATES_BUCKET" != "" ]; then
    print_info "Uploading nested templates to S3 bucket: $TEMPLATES_BUCKET"

    # Check if bucket exists
    if ! aws s3 ls "s3://$TEMPLATES_BUCKET" &> /dev/null; then
        print_warn "S3 bucket does not exist. Creating bucket..."
        aws s3 mb "s3://$TEMPLATES_BUCKET" --region "$AWS_REGION"
    fi

    # Upload templates
    aws s3 sync "$CFN_DIR/stacks" "s3://$TEMPLATES_BUCKET/cloudformation/stacks" --region "$AWS_REGION"
    print_info "Templates uploaded successfully"
fi

# Deploy the stack
print_info "Deploying CloudFormation stack..."

if [ "$OPERATION" == "create" ]; then
    aws cloudformation create-stack \
        --stack-name "$STACK_NAME" \
        --template-body file://"$MASTER_TEMPLATE" \
        --parameters file://"$PARAMS_FILE" \
        --capabilities CAPABILITY_NAMED_IAM \
        --region "$AWS_REGION" \
        --tags Key=Environment,Value="$ENVIRONMENT" Key=Application,Value=bedrock-cost-keeper

    print_info "Stack creation initiated. Waiting for completion..."
    aws cloudformation wait stack-create-complete \
        --stack-name "$STACK_NAME" \
        --region "$AWS_REGION"
else
    aws cloudformation update-stack \
        --stack-name "$STACK_NAME" \
        --template-body file://"$MASTER_TEMPLATE" \
        --parameters file://"$PARAMS_FILE" \
        --capabilities CAPABILITY_NAMED_IAM \
        --region "$AWS_REGION" \
        --tags Key=Environment,Value="$ENVIRONMENT" Key=Application,Value=bedrock-cost-keeper

    print_info "Stack update initiated. Waiting for completion..."
    aws cloudformation wait stack-update-complete \
        --stack-name "$STACK_NAME" \
        --region "$AWS_REGION"
fi

# Get stack outputs
print_info "Stack deployment completed successfully!"
print_info "Retrieving stack outputs..."

OUTPUTS=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --region "$AWS_REGION" \
    --query 'Stacks[0].Outputs' \
    --output json)

echo ""
print_info "=== Stack Outputs ==="
echo "$OUTPUTS" | jq -r '.[] | "\(.OutputKey): \(.OutputValue)"'
echo ""

# Extract key outputs
ALB_URL=$(echo "$OUTPUTS" | jq -r '.[] | select(.OutputKey=="ALBUrl") | .OutputValue')
PIPELINE_URL=$(echo "$OUTPUTS" | jq -r '.[] | select(.OutputKey=="PipelineUrl") | .OutputValue')
ECR_REPO=$(echo "$OUTPUTS" | jq -r '.[] | select(.OutputKey=="ECRRepositoryUri") | .OutputValue')

print_info "=== Important Links ==="
echo "Service URL: $ALB_URL"
echo "Pipeline URL: $PIPELINE_URL"
echo "ECR Repository: $ECR_REPO"
echo ""

# Test health endpoint
print_info "Testing health endpoint..."
if curl -f -s "${ALB_URL}/health" > /dev/null 2>&1; then
    print_info "Health check passed!"
else
    print_warn "Health check failed. The service might still be starting up."
    print_info "You can manually test with: curl ${ALB_URL}/health"
fi

print_info "Deployment complete!"
print_info "Next steps:"
echo "  1. Build and push Docker image: cd deployment && ./scripts/build-and-push.sh $ENVIRONMENT"
echo "  2. Initialize secrets: cd deployment/scripts && ./create-secrets.sh $ENVIRONMENT"
echo "  3. Seed DynamoDB: cd deployment/scripts && python seed-dynamodb.py $ENVIRONMENT"
echo "  4. Configure test client: cd test-client && vi config.json"
