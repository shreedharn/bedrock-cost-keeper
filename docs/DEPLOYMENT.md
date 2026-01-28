# Bedrock Cost Keeper - Deployment Guide

This guide provides step-by-step instructions for deploying the Bedrock Cost Keeper service to AWS ECS Fargate with complete infrastructure as code.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Initial Setup](#initial-setup)
3. [Deploy Infrastructure](#deploy-infrastructure)
4. [Build and Push Docker Image](#build-and-push-docker-image)
5. [Initialize Data](#initialize-data)
6. [Verify Deployment](#verify-deployment)
7. [Set Up CI/CD](#set-up-cicd)
8. [Configure DNS (Optional)](#configure-dns-optional)
9. [Test End-to-End](#test-end-to-end)
10. [Production Readiness Checklist](#production-readiness-checklist)
11. [Cost Estimation](#cost-estimation)
12. [Troubleshooting](#troubleshooting)

---

## Prerequisites

### Required Software

- **AWS CLI v2**: [Installation Guide](https://docs.aws.amazon.com/cli/latest/userguide/install-cliv2.html)
- **Docker**: [Installation Guide](https://docs.docker.com/get-docker/)
- **Python 3.9+**: For running seed scripts
- **jq**: JSON processor (optional but recommended)

```bash
# Verify installations
aws --version          # Should be >= 2.0
docker --version       # Should be >= 20.0
python --version       # Should be >= 3.9
jq --version           # Optional
```

### AWS Requirements

1. **AWS Account** with appropriate permissions:
   - CloudFormation (full access)
   - IAM (create roles and policies)
   - ECS/Fargate (full access)
   - DynamoDB (full access)
   - ECR (full access)
   - Secrets Manager (full access)
   - ALB/ELB (full access)
   - CodePipeline/CodeBuild (full access)
   - VPC (read access)
   - ACM (read access)

2. **Existing VPC Infrastructure**:
   - VPC ID
   - 2+ public subnets (for ALB, in different AZs)
   - 2+ private subnets (for ECS tasks, in different AZs)
   - NAT Gateway or VPC endpoints for private subnet internet access

3. **ACM Certificate** for HTTPS:
   - Request certificate in ACM
   - Validate via DNS or email
   - Note the certificate ARN

4. **GitHub Access**:
   - GitHub repository
   - AWS CodeStar Connection to GitHub (for CodePipeline)

### Configure AWS CLI

```bash
aws configure
# AWS Access Key ID: YOUR_ACCESS_KEY
# AWS Secret Access Key: YOUR_SECRET_KEY
# Default region name: us-east-1
# Default output format: json
```

---

## Initial Setup

### Step 1: Identify Network Resources

Gather information about your existing VPC and subnets:

```bash
# List VPCs
aws ec2 describe-vpcs --query 'Vpcs[*].[VpcId,Tags[?Key==`Name`].Value|[0]]' --output table

# List public subnets (with internet gateway route)
aws ec2 describe-subnets \
  --filters "Name=vpc-id,Values=vpc-XXXXX" \
  --query 'Subnets[*].[SubnetId,AvailabilityZone,CidrBlock,Tags[?Key==`Name`].Value|[0]]' \
  --output table

# List private subnets (with NAT gateway route)
aws ec2 describe-route-tables \
  --filters "Name=vpc-id,Values=vpc-XXXXX" \
  --query 'RouteTables[*].Routes[?NatGatewayId!=`null`]' \
  --output table
```

**Requirements**:
- **Public subnets**: Must be in different Availability Zones
- **Private subnets**: Must be in different Availability Zones
- **Private subnets**: Must have route to NAT Gateway or VPC endpoints for AWS services

### Step 2: Request ACM Certificate

If you don't have an ACM certificate:

```bash
# Request certificate for your domain
aws acm request-certificate \
  --domain-name bedrock-cost-keeper.example.com \
  --validation-method DNS \
  --region us-east-1

# Get certificate ARN
aws acm list-certificates --region us-east-1
```

Validate the certificate via DNS (add CNAME records to your domain).

### Step 3: Create AWS CodeStar Connection

Create a connection to GitHub for CodePipeline:

```bash
# Create connection (this will be in PENDING state)
aws codestar-connections create-connection \
  --provider-type GitHub \
  --connection-name bedrock-cost-keeper-github \
  --region us-east-1

# Complete the connection in AWS Console
# Go to: Developer Tools > Settings > Connections
# Click on the connection and complete the OAuth flow
```

Note the connection ARN for later use.

### Step 4: Generate Secrets

Run the secrets generation script:

```bash
cd deployment/scripts
./create-secrets.sh dev

# Save the output values:
# JWT_SECRET_KEY=<base64-encoded-value>
# PROVISIONING_API_KEY=<base64-encoded-value>
```

### Step 5: Update Parameter Files

Edit the parameter file for your environment:

```bash
cd cloudformation/parameters
vi dev.json  # or staging.json, prod.json
```

Update the following values:

```json
{
  "ParameterKey": "VpcId",
  "ParameterValue": "vpc-0123456789abcdef0"  // Your VPC ID
},
{
  "ParameterKey": "PublicSubnetIds",
  "ParameterValue": "subnet-abc123,subnet-def456"  // Your public subnet IDs
},
{
  "ParameterKey": "PrivateSubnetIds",
  "ParameterValue": "subnet-ghi789,subnet-jkl012"  // Your private subnet IDs
},
{
  "ParameterKey": "CertificateArn",
  "ParameterValue": "arn:aws:acm:us-east-1:123456789012:certificate/..."  // Your ACM cert
},
{
  "ParameterKey": "GitHubConnectionArn",
  "ParameterValue": "arn:aws:codestar-connections:us-east-1:123456789012:connection/..."
},
{
  "ParameterKey": "JWTSecretKey",
  "ParameterValue": "<from-create-secrets-script>"
},
{
  "ParameterKey": "ProvisioningAPIKey",
  "ParameterValue": "<from-create-secrets-script>"
}
```

---

## Deploy Infrastructure

### Option 1: Using Deployment Script (Recommended)

The deployment script handles validation, template upload, and stack creation:

```bash
cd deployment/scripts
./deploy.sh dev

# For staging or production:
# ./deploy.sh staging
# ./deploy.sh prod
```

The script will:
1. Validate all CloudFormation templates
2. Check AWS credentials and permissions
3. Upload nested templates to S3 (if configured)
4. Create or update the CloudFormation stack
5. Wait for completion (10-15 minutes)
6. Display stack outputs

### Option 2: Manual Deployment

If you prefer manual control:

```bash
cd cloudformation

# Validate master template
aws cloudformation validate-template \
  --template-body file://master-stack.yaml

# Create stack
aws cloudformation create-stack \
  --stack-name bedrock-cost-keeper-dev \
  --template-body file://master-stack.yaml \
  --parameters file://parameters/dev.json \
  --capabilities CAPABILITY_NAMED_IAM \
  --region us-east-1

# Monitor progress
aws cloudformation wait stack-create-complete \
  --stack-name bedrock-cost-keeper-dev \
  --region us-east-1

# Get outputs
aws cloudformation describe-stacks \
  --stack-name bedrock-cost-keeper-dev \
  --query 'Stacks[0].Outputs' \
  --region us-east-1
```

### Verify Stack Creation

Check that all nested stacks were created:

```bash
aws cloudformation list-stacks \
  --stack-status-filter CREATE_COMPLETE \
  --query 'StackSummaries[?contains(StackName, `bedrock-cost-keeper`)].StackName' \
  --region us-east-1
```

You should see 9 stacks:
- bedrock-cost-keeper-dev (master)
- bedrock-cost-keeper-dev-DynamoDBStack-*
- bedrock-cost-keeper-dev-SecretsStack-*
- bedrock-cost-keeper-dev-ECRStack-*
- bedrock-cost-keeper-dev-IAMStack-*
- bedrock-cost-keeper-dev-SecurityGroupsStack-*
- bedrock-cost-keeper-dev-ALBStack-*
- bedrock-cost-keeper-dev-ECSStack-*
- bedrock-cost-keeper-dev-CodePipelineStack-*

---

## Build and Push Docker Image

### Get ECR Repository URI

```bash
ECR_REPO=$(aws cloudformation describe-stacks \
  --stack-name bedrock-cost-keeper-dev \
  --query 'Stacks[0].Outputs[?OutputKey==`ECRRepositoryUri`].OutputValue' \
  --output text \
  --region us-east-1)

echo $ECR_REPO
# Output: 123456789012.dkr.ecr.us-east-1.amazonaws.com/bedrock-cost-keeper-dev
```

### Build and Push

```bash
cd /path/to/bedrock_metering

# Authenticate to ECR
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin $ECR_REPO

# Build Docker image
docker build -t bedrock-cost-keeper:latest -f deployment/Dockerfile .

# Tag image
docker tag bedrock-cost-keeper:latest $ECR_REPO:latest

# Push to ECR
docker push $ECR_REPO:latest

# Verify image
aws ecr describe-images \
  --repository-name bedrock-cost-keeper-dev \
  --region us-east-1
```

### Update ECS Service

After pushing the first image, update the ECS service to deploy:

```bash
# Force new deployment
aws ecs update-service \
  --cluster bedrock-cost-keeper-dev \
  --service bedrock-cost-keeper-dev \
  --force-new-deployment \
  --region us-east-1

# Monitor deployment
aws ecs describe-services \
  --cluster bedrock-cost-keeper-dev \
  --services bedrock-cost-keeper-dev \
  --query 'services[0].events[0:5]' \
  --region us-east-1
```

---

## Initialize Data

### Seed DynamoDB with Test Data

```bash
cd deployment/scripts

# Install Python dependencies
pip install boto3 bcrypt

# Run seed script
python seed-dynamodb.py dev

# Save the output:
# Organization ID: 550e8400-e29b-41d4-a716-446655440000
# Client ID: org-550e8400-e29b-41d4-a716-446655440000-app-test-app
# Client Secret: AbCdEfGhIjKlMnOpQrStUvWxYz0123456789
```

**Important**: Save the Client ID and Client Secret - you'll need these for the test client.

### Verify Data in DynamoDB

```bash
# Check that organization was created
aws dynamodb get-item \
  --table-name bedrock-cost-keeper-config-dev \
  --key '{"pk":{"S":"ORG#550e8400-e29b-41d4-a716-446655440000"},"sk":{"S":"CONFIG"}}' \
  --region us-east-1

# Check that application was created
aws dynamodb get-item \
  --table-name bedrock-cost-keeper-config-dev \
  --key '{"pk":{"S":"ORG#550e8400-e29b-41d4-a716-446655440000"},"sk":{"S":"APP#test-app"}}' \
  --region us-east-1
```

---

## Verify Deployment

### Get ALB DNS Name

```bash
ALB_DNS=$(aws cloudformation describe-stacks \
  --stack-name bedrock-cost-keeper-dev \
  --query 'Stacks[0].Outputs[?OutputKey==`ALBDnsName`].OutputValue' \
  --output text \
  --region us-east-1)

echo "Service URL: https://$ALB_DNS"
```

### Test Health Endpoint

```bash
curl -v https://$ALB_DNS/health

# Expected response:
# HTTP/1.1 200 OK
# {"status": "healthy", "timestamp": "2024-01-15T10:30:00Z"}
```

### Check ECS Service Status

```bash
# Verify 2 tasks are running
aws ecs describe-services \
  --cluster bedrock-cost-keeper-dev \
  --services bedrock-cost-keeper-dev \
  --query 'services[0].{DesiredCount:desiredCount,RunningCount:runningCount}' \
  --region us-east-1

# Check task health
aws ecs list-tasks \
  --cluster bedrock-cost-keeper-dev \
  --service-name bedrock-cost-keeper-dev \
  --region us-east-1
```

### Check ALB Target Health

```bash
TARGET_GROUP=$(aws cloudformation describe-stacks \
  --stack-name bedrock-cost-keeper-dev \
  --query 'Stacks[0].Outputs[?contains(OutputKey, `TargetGroup`)].OutputValue' \
  --output text \
  --region us-east-1)

aws elbv2 describe-target-health \
  --target-group-arn $TARGET_GROUP \
  --region us-east-1
```

All targets should be `healthy`.

### View CloudWatch Logs

```bash
# Get recent logs
aws logs tail /ecs/bedrock-cost-keeper-dev \
  --follow \
  --region us-east-1
```

---

## Set Up CI/CD

### Verify CodePipeline

```bash
# Get pipeline name
aws codepipeline list-pipelines \
  --query 'pipelines[?contains(name, `bedrock-cost-keeper`)].name' \
  --region us-east-1

# Get pipeline details
aws codepipeline get-pipeline \
  --name bedrock-cost-keeper-dev \
  --region us-east-1
```

### Test Pipeline

Make a change to your code and push to GitHub:

```bash
# Make a small change
echo "# Test change" >> README.md

# Commit and push
git add README.md
git commit -m "Test CI/CD pipeline"
git push origin develop  # or main, depending on your branch

# Monitor pipeline execution
aws codepipeline get-pipeline-state \
  --name bedrock-cost-keeper-dev \
  --region us-east-1
```

### View Pipeline in Console

Get the pipeline URL:

```bash
aws cloudformation describe-stacks \
  --stack-name bedrock-cost-keeper-dev \
  --query 'Stacks[0].Outputs[?OutputKey==`PipelineUrl`].OutputValue' \
  --output text \
  --region us-east-1
```

Open the URL in your browser to see pipeline execution.

---

## Configure DNS (Optional)

### Create Route 53 A Record

```bash
# Get hosted zone ID
HOSTED_ZONE_ID=$(aws route53 list-hosted-zones \
  --query 'HostedZones[?Name==`example.com.`].Id' \
  --output text)

# Get ALB hosted zone ID
ALB_ZONE_ID=$(aws elbv2 describe-load-balancers \
  --query 'LoadBalancers[?contains(DNSName, `bedrock-cost-keeper`)].CanonicalHostedZoneId' \
  --output text \
  --region us-east-1)

# Create A record (alias to ALB)
cat > change-batch.json <<EOF
{
  "Changes": [{
    "Action": "CREATE",
    "ResourceRecordSet": {
      "Name": "bedrock-cost-keeper-dev.example.com",
      "Type": "A",
      "AliasTarget": {
        "HostedZoneId": "$ALB_ZONE_ID",
        "DNSName": "$ALB_DNS",
        "EvaluateTargetHealth": true
      }
    }
  }]
}
EOF

aws route53 change-resource-record-sets \
  --hosted-zone-id $HOSTED_ZONE_ID \
  --change-batch file://change-batch.json

# Verify DNS propagation
dig bedrock-cost-keeper-dev.example.com
```

---

## Test End-to-End

### Configure Test Client

```bash
cd test-client

# Install dependencies
pip install -r requirements.txt

# Update config.json with credentials from seed script
vi config.json
```

```json
{
  "service_url": "https://bedrock-cost-keeper-dev.example.com",
  "client_id": "org-550e8400-e29b-41d4-a716-446655440000-app-test-app",
  "client_secret": "YOUR_CLIENT_SECRET_FROM_SEED_SCRIPT",
  "org_id": "550e8400-e29b-41d4-a716-446655440000",
  "app_id": "test-app",
  "aws_region": "us-east-1",
  "test_prompt": "What is the capital of France?"
}
```

### Run Test Client

```bash
python bedrock_client.py
```

Expected output:

```
============================================================
Running 5 inference requests
============================================================

--- Request 1/5 ---
[INFO] Authenticating with Bedrock Cost Keeper...
[INFO] Authenticated successfully. Token expires in 3600 seconds
[INFO] Getting model selection recommendation...
[INFO] Recommended model: claude-3-5-sonnet-20241022-v2
[INFO] Invoking Bedrock model: anthropic.claude-3-5-sonnet-20241022-v2:0
[INFO] Bedrock invocation successful
[INFO] Cost: $0.000345 (345 USD micros)
[INFO] Cost submitted successfully

============================================================
Final Summary
============================================================
Successful requests: 5/5
Total cost (calculated): $0.001725

[INFO] Test completed successfully!
```

### Verify in DynamoDB

```bash
# Check daily totals
aws dynamodb scan \
  --table-name bedrock-cost-keeper-daily-total-dev \
  --region us-east-1 \
  --limit 5

# Check usage aggregation
aws dynamodb scan \
  --table-name bedrock-cost-keeper-usage-agg-sharded-dev \
  --region us-east-1 \
  --limit 5
```

---

## Production Readiness Checklist

Before going to production, complete these steps:

### Security

- [ ] Rotate JWT_SECRET_KEY and PROVISIONING_API_KEY
- [ ] Restrict CORS allowed origins (update application config)
- [ ] Enable AWS WAF for DDoS protection
- [ ] Review IAM policies for least privilege
- [ ] Enable MFA for AWS account root user
- [ ] Set up AWS CloudTrail for audit logging

### High Availability

- [ ] Deploy to 3+ availability zones
- [ ] Increase ECS task count (minimum 3)
- [ ] Enable DynamoDB point-in-time recovery
- [ ] Set up cross-region replication (optional)
- [ ] Configure Route 53 health checks

### Monitoring and Alerts

- [ ] Create CloudWatch Dashboard
- [ ] Set up CloudWatch Alarms:
  - ECS task failures
  - ALB 5xx errors > threshold
  - CPU utilization > 80%
  - Memory utilization > 85%
  - DynamoDB throttling events
- [ ] Configure SNS topics for alerts
- [ ] Set up PagerDuty/Opsgenie integration
- [ ] Enable Container Insights
- [ ] Set up X-Ray tracing (optional)

### Backup and Recovery

- [ ] Enable DynamoDB point-in-time recovery
- [ ] Set up AWS Backup for DynamoDB
- [ ] Document recovery procedures
- [ ] Test disaster recovery process
- [ ] Set up S3 versioning for logs

### Logging

- [ ] Enable ALB access logs to S3
- [ ] Set up log aggregation (e.g., CloudWatch Logs Insights)
- [ ] Configure log retention policies
- [ ] Set up log analysis (optional: ELK, Splunk)

### Cost Optimization

- [ ] Review DynamoDB capacity settings
- [ ] Enable S3 lifecycle policies
- [ ] Set up AWS Budgets and alerts
- [ ] Review reserved capacity options (ECS, DynamoDB)

### Documentation

- [ ] Document runbooks for common issues
- [ ] Create architecture diagrams
- [ ] Document API endpoints and usage
- [ ] Update team wiki/confluence

---

## Cost Estimation

> **⚠️ COST DISCLAIMER**
>
> All cost estimates provided below are for **illustrative purposes only** and must be verified against current AWS pricing. Actual costs may vary significantly based on:
> - Usage patterns, traffic volume, and data transfer
> - AWS region (estimates below are for US East 1)
> - Current AWS pricing (subject to change without notice)
> - Resource configuration and optimization strategies
> - Free tier eligibility
> **Always:**
> - Validate calculations with the [AWS Pricing Calculator](https://calculator.aws/)
> - Monitor actual costs using AWS Cost Explorer
> - Set up billing alerts before deployment
> - Conduct your own detailed cost analysis for your specific use case

### Monthly Cost Breakdown (US East 1)

**ECS Fargate** (2 tasks @ 0.5 vCPU, 1 GB memory):
- 2 tasks × 730 hours × $0.04048/vCPU/hour = $59.10
- 2 tasks × 730 hours × $0.004445/GB/hour = $6.49
- **Subtotal**: ~$65.59/month

**Application Load Balancer**:
- ALB hours: 730 × $0.0225 = $16.43
- LCU hours (estimated 5 LCU): 730 × 5 × $0.008 = $29.20
- **Subtotal**: ~$45.63/month

**DynamoDB** (PAY_PER_REQUEST):
- Assuming 1M requests/month: $1.25
- Storage (1 GB): $0.25
- **Subtotal**: ~$1.50/month (variable based on traffic)

**ECR** (Image storage):
- 1 GB × $0.10 = $0.10/month
- **Subtotal**: ~$0.10/month

**Secrets Manager**:
- 2 secrets × $0.40 = $0.80/month
- **Subtotal**: ~$0.80/month

**CloudWatch**:
- Logs (5 GB): $2.50
- Metrics: $0.30
- Container Insights: $0.50
- **Subtotal**: ~$3.30/month

**S3** (Artifacts, logs):
- 10 GB × $0.023 = $0.23/month
- **Subtotal**: ~$0.25/month

**Data Transfer**:
- First 10 TB/month out: $0.09/GB
- Estimated 100 GB: $9.00/month
- **Subtotal**: ~$9.00/month

### Total Estimated Monthly Cost

**Base Infrastructure**: ~$126.17/month

**Variable Costs**:
- DynamoDB (high traffic): +$10-100/month
- Data transfer (high traffic): +$50-200/month
- **Total Range**: $126-426/month

### Cost Optimization Tips

1. Use Compute Savings Plans for ECS (up to 50% off)
2. Use DynamoDB reserved capacity for predictable workloads
3. Reduce CloudWatch log retention for non-production
4. Use S3 Intelligent-Tiering for logs
5. Right-size ECS tasks after monitoring actual usage

---

## Troubleshooting

### ECS Tasks Failing Health Checks

**Symptoms**: Tasks start but quickly fail health checks

**Diagnosis**:
```bash
# Check task logs
aws logs tail /ecs/bedrock-cost-keeper-dev --follow --region us-east-1

# Check task status
aws ecs describe-tasks \
  --cluster bedrock-cost-keeper-dev \
  --tasks $(aws ecs list-tasks --cluster bedrock-cost-keeper-dev --query 'taskArns[0]' --output text) \
  --region us-east-1
```

**Common Causes**:
- Application failing to start (check logs)
- Secrets not accessible (check IAM permissions)
- DynamoDB connection issues (check VPC endpoints)
- Health check path incorrect

**Solutions**:
- Verify environment variables in task definition
- Check IAM task role permissions
- Ensure private subnets have NAT Gateway
- Test /health endpoint manually

### DynamoDB Permission Errors

**Symptoms**: Application logs show `AccessDeniedException` for DynamoDB

**Diagnosis**:
```bash
# Check IAM task role
aws iam get-role-policy \
  --role-name bedrock-cost-keeper-ecs-task-dev \
  --policy-name DynamoDBAccess \
  --region us-east-1
```

**Solution**:
- Verify table ARNs in IAM policy
- Check table names in environment variables
- Ensure tables exist in the same region

### Secrets Manager Access Denied

**Symptoms**: Application fails to retrieve JWT/API keys

**Diagnosis**:
```bash
# Test secret access
aws secretsmanager get-secret-value \
  --secret-id bedrock-cost-keeper/jwt-secret-dev \
  --region us-east-1
```

**Solution**:
- Verify IAM execution role has `secretsmanager:GetSecretValue` permission
- Check secret ARNs in task definition
- Ensure KMS key policy allows ECS task role

### CodePipeline Build Failures

**Symptoms**: Build stage fails in CodePipeline

**Diagnosis**:
```bash
# Get build logs
BUILD_ID=$(aws codebuild list-builds-for-project \
  --project-name bedrock-cost-keeper-dev \
  --query 'ids[0]' \
  --output text \
  --region us-east-1)

aws codebuild batch-get-builds \
  --ids $BUILD_ID \
  --query 'builds[0].logs.deepLink' \
  --output text \
  --region us-east-1
```

**Common Causes**:
- Test failures (check test output)
- Docker build errors (check Dockerfile)
- ECR push failures (check IAM permissions)

**Solutions**:
- Fix failing tests
- Verify Dockerfile syntax
- Check CodeBuild service role has ECR permissions

### ALB Target Group Unhealthy

**Symptoms**: All targets showing unhealthy status

**Diagnosis**:
```bash
# Check target health
aws elbv2 describe-target-health \
  --target-group-arn $TARGET_GROUP_ARN \
  --query 'TargetHealthDescriptions[*].{Target:Target.Id,Health:TargetHealth.State,Reason:TargetHealth.Reason}' \
  --region us-east-1
```

**Common Causes**:
- Health check path incorrect (should be /health)
- Tasks not listening on port 8000
- Security group not allowing ALB → ECS traffic

**Solutions**:
- Verify health check configuration
- Check application is binding to 0.0.0.0:8000
- Review security group rules

### High DynamoDB Costs

**Symptoms**: DynamoDB bill higher than expected

**Diagnosis**:
```bash
# Check table metrics
aws cloudwatch get-metric-statistics \
  --namespace AWS/DynamoDB \
  --metric-name ConsumedReadCapacityUnits \
  --dimensions Name=TableName,Value=bedrock-cost-keeper-config-dev \
  --start-time 2024-01-01T00:00:00Z \
  --end-time 2024-01-31T23:59:59Z \
  --period 86400 \
  --statistics Sum \
  --region us-east-1
```

**Solutions**:
- Review access patterns for inefficiencies
- Add caching layer (Redis/ElastiCache)
- Consider provisioned capacity for predictable workloads
- Implement pagination for large scans

---

## Support and Resources

- **CloudFormation Documentation**: https://docs.aws.amazon.com/cloudformation/
- **ECS Documentation**: https://docs.aws.amazon.com/ecs/
- **DynamoDB Documentation**: https://docs.aws.amazon.com/dynamodb/
- **AWS Support**: https://console.aws.amazon.com/support/

For issues specific to this deployment, check:
- CloudWatch Logs: `/ecs/bedrock-cost-keeper-{environment}`
- ECS Service Events
- CloudFormation Stack Events
