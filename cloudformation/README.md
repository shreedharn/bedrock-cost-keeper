# CloudFormation Infrastructure

This directory contains all CloudFormation templates for deploying the Bedrock Cost Keeper service to AWS.

## Structure

```
cloudformation/
├── master-stack.yaml           # Main orchestration template
├── parameters/                 # Environment-specific parameters
│   ├── dev.json
│   ├── staging.json
│   └── prod.json
└── stacks/                     # Nested stack templates
    ├── 01-dynamodb.yaml        # DynamoDB tables
    ├── 02-secrets.yaml         # Secrets Manager resources
    ├── 03-ecr.yaml             # ECR repository
    ├── 04-iam.yaml             # IAM roles and policies
    ├── 05-security-groups.yaml # Network security groups
    ├── 06-alb.yaml             # Application Load Balancer
    ├── 07-ecs.yaml             # ECS cluster and service
    └── 08-codepipeline.yaml    # CI/CD pipeline
```

## Quick Start

```bash
# 1. Update parameters for your environment
vi parameters/dev.json

# 2. Deploy using the deployment script
cd ../deployment/scripts
./deploy.sh dev
```

For detailed deployment instructions, see: `docs/DEPLOYMENT.md`
