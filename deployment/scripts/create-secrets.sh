#!/bin/bash

set -e

# Script to generate and store secrets in AWS Secrets Manager
# Usage: ./create-secrets.sh <environment>

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
    echo "Usage: $0 <environment>"
    echo "Environments: dev, staging, prod"
    exit 1
fi

ENVIRONMENT=$1
AWS_REGION=${AWS_REGION:-us-east-1}

# Validate environment
if [[ ! "$ENVIRONMENT" =~ ^(dev|staging|prod)$ ]]; then
    print_error "Invalid environment: $ENVIRONMENT"
    echo "Valid environments: dev, staging, prod"
    exit 1
fi

# Check prerequisites
if ! command -v aws &> /dev/null; then
    print_error "AWS CLI not found. Please install AWS CLI v2"
    exit 1
fi

if ! command -v openssl &> /dev/null; then
    print_error "OpenSSL not found. Please install OpenSSL"
    exit 1
fi

# Check AWS credentials
if ! aws sts get-caller-identity &> /dev/null; then
    print_error "AWS credentials not configured"
    exit 1
fi

print_info "Generating secrets for environment: $ENVIRONMENT"
print_info "AWS Region: $AWS_REGION"

# Generate JWT secret key (32 bytes, base64 encoded)
print_info "Generating JWT secret key..."
JWT_SECRET=$(openssl rand -base64 32)
print_info "JWT secret generated"

# Generate provisioning API key (32 bytes, base64 encoded)
print_info "Generating provisioning API key..."
PROVISIONING_KEY=$(openssl rand -base64 32)
print_info "Provisioning API key generated"

# Store JWT secret in Secrets Manager
JWT_SECRET_NAME="bedrock-cost-keeper/jwt-secret-${ENVIRONMENT}"
print_info "Storing JWT secret in Secrets Manager: $JWT_SECRET_NAME"

if aws secretsmanager describe-secret --secret-id "$JWT_SECRET_NAME" --region "$AWS_REGION" &> /dev/null; then
    print_warn "Secret already exists. Updating..."
    aws secretsmanager update-secret \
        --secret-id "$JWT_SECRET_NAME" \
        --secret-string "$JWT_SECRET" \
        --region "$AWS_REGION" > /dev/null
    print_info "JWT secret updated"
else
    aws secretsmanager create-secret \
        --name "$JWT_SECRET_NAME" \
        --description "JWT secret key for Bedrock Cost Keeper ${ENVIRONMENT}" \
        --secret-string "$JWT_SECRET" \
        --region "$AWS_REGION" > /dev/null
    print_info "JWT secret created"
fi

JWT_SECRET_ARN=$(aws secretsmanager describe-secret \
    --secret-id "$JWT_SECRET_NAME" \
    --region "$AWS_REGION" \
    --query 'ARN' \
    --output text)

# Store provisioning API key in Secrets Manager
PROVISIONING_SECRET_NAME="bedrock-cost-keeper/provisioning-api-key-${ENVIRONMENT}"
print_info "Storing provisioning API key in Secrets Manager: $PROVISIONING_SECRET_NAME"

if aws secretsmanager describe-secret --secret-id "$PROVISIONING_SECRET_NAME" --region "$AWS_REGION" &> /dev/null; then
    print_warn "Secret already exists. Updating..."
    aws secretsmanager update-secret \
        --secret-id "$PROVISIONING_SECRET_NAME" \
        --secret-string "$PROVISIONING_KEY" \
        --region "$AWS_REGION" > /dev/null
    print_info "Provisioning API key updated"
else
    aws secretsmanager create-secret \
        --name "$PROVISIONING_SECRET_NAME" \
        --description "Provisioning API key for Bedrock Cost Keeper ${ENVIRONMENT}" \
        --secret-string "$PROVISIONING_KEY" \
        --region "$AWS_REGION" > /dev/null
    print_info "Provisioning API key created"
fi

PROVISIONING_SECRET_ARN=$(aws secretsmanager describe-secret \
    --secret-id "$PROVISIONING_SECRET_NAME" \
    --region "$AWS_REGION" \
    --query 'ARN' \
    --output text)

# Print summary
echo ""
print_info "=== Secrets Created Successfully ==="
echo "JWT Secret ARN: $JWT_SECRET_ARN"
echo "Provisioning API Secret ARN: $PROVISIONING_SECRET_ARN"
echo ""

print_info "Secret values (save these securely):"
echo "JWT_SECRET_KEY=$JWT_SECRET"
echo "PROVISIONING_API_KEY=$PROVISIONING_KEY"
echo ""

print_warn "IMPORTANT: Update your CloudFormation parameter file with these values:"
echo "  JWTSecretKey: $JWT_SECRET"
echo "  ProvisioningAPIKey: $PROVISIONING_KEY"
echo ""

print_info "Done!"
