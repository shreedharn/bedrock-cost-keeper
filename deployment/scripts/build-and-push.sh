#!/bin/bash

set -e

# Build and push Docker image to ECR
# Usage: ./build-and-push.sh <environment> [image-tag]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

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
    echo "Usage: $0 <environment> [image-tag]"
    echo "Environments: dev, staging, prod"
    exit 1
fi

ENVIRONMENT=$1
IMAGE_TAG=${2:-latest}
AWS_REGION=${AWS_REGION:-us-east-1}
STACK_NAME="bedrock-cost-keeper-${ENVIRONMENT}"

print_info "Building and pushing Docker image for environment: $ENVIRONMENT"
print_info "Image tag: $IMAGE_TAG"
print_info "AWS Region: $AWS_REGION"

# Check prerequisites
if ! command -v aws &> /dev/null; then
    print_error "AWS CLI not found. Please install AWS CLI v2"
    exit 1
fi

if ! command -v docker &> /dev/null; then
    print_error "Docker not found. Please install Docker"
    exit 1
fi

# Check AWS credentials
if ! aws sts get-caller-identity &> /dev/null; then
    print_error "AWS credentials not configured"
    exit 1
fi

# Get ECR repository URI from CloudFormation stack
print_info "Getting ECR repository URI from CloudFormation..."
ECR_REPO=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --query 'Stacks[0].Outputs[?OutputKey==`ECRRepositoryUri`].OutputValue' \
    --output text \
    --region "$AWS_REGION")

if [ -z "$ECR_REPO" ]; then
    print_error "Failed to get ECR repository URI. Is the stack deployed?"
    exit 1
fi

print_info "ECR Repository: $ECR_REPO"

# Authenticate to ECR
print_info "Authenticating to ECR..."
aws ecr get-login-password --region "$AWS_REGION" | \
    docker login --username AWS --password-stdin "$ECR_REPO"

# Build Docker image
print_info "Building Docker image..."
cd "$PROJECT_ROOT"
docker build -t bedrock-cost-keeper:$IMAGE_TAG -f deployment/Dockerfile .

# Tag image
print_info "Tagging image..."
docker tag bedrock-cost-keeper:$IMAGE_TAG $ECR_REPO:$IMAGE_TAG
docker tag bedrock-cost-keeper:$IMAGE_TAG $ECR_REPO:latest

# Push to ECR
print_info "Pushing image to ECR..."
docker push $ECR_REPO:$IMAGE_TAG
docker push $ECR_REPO:latest

print_info "Image pushed successfully!"
print_info "Image URI: $ECR_REPO:$IMAGE_TAG"

# Update ECS service
print_info "Updating ECS service..."
CLUSTER_NAME="bedrock-cost-keeper-${ENVIRONMENT}"
SERVICE_NAME="bedrock-cost-keeper-${ENVIRONMENT}"

aws ecs update-service \
    --cluster "$CLUSTER_NAME" \
    --service "$SERVICE_NAME" \
    --force-new-deployment \
    --region "$AWS_REGION" \
    > /dev/null

print_info "ECS service update initiated"
print_info "Monitor deployment with: aws ecs describe-services --cluster $CLUSTER_NAME --services $SERVICE_NAME --region $AWS_REGION"

print_info "Done!"
