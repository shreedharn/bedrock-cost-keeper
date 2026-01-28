#!/usr/bin/env python3
"""
Seed DynamoDB tables with initial test data for Bedrock Cost Keeper
Usage: python seed-dynamodb.py <environment>
"""

import sys
import os
import json
import uuid
import secrets
from datetime import datetime, timezone
from typing import Dict, Any

import boto3
import bcrypt


# Colors for terminal output
class Colors:
    GREEN = '\033[0;32m'
    YELLOW = '\033[1;33m'
    RED = '\033[0;31m'
    NC = '\033[0m'  # No Color


def print_info(msg: str):
    print(f"{Colors.GREEN}[INFO]{Colors.NC} {msg}")


def print_warn(msg: str):
    print(f"{Colors.YELLOW}[WARN]{Colors.NC} {msg}")


def print_error(msg: str):
    print(f"{Colors.RED}[ERROR]{Colors.NC} {msg}")


def generate_client_secret() -> str:
    """Generate a secure client secret"""
    return secrets.token_urlsafe(32)


def hash_secret(secret: str) -> str:
    """Hash a secret using bcrypt"""
    return bcrypt.hashpw(secret.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


def create_test_organization(
    dynamodb_client,
    config_table: str,
    org_id: str = None
) -> Dict[str, Any]:
    """Create a test organization in DynamoDB"""
    if org_id is None:
        org_id = str(uuid.uuid4())

    now = datetime.now(timezone.utc).isoformat()

    org_config = {
        'pk': f'ORG#{org_id}',
        'sk': 'CONFIG',
        'entity_type': 'organization',
        'org_id': org_id,
        'org_name': 'Test Organization',
        'created_at': now,
        'updated_at': now,
        'status': 'active',
        'settings': {
            'default_daily_budget': 10000000,  # $10 in USD micros
            'default_monthly_budget': 300000000,  # $300 in USD micros
            'enable_cost_alerts': True,
            'alert_threshold_percent': 80
        }
    }

    print_info(f"Creating organization: {org_id}")
    dynamodb_client.put_item(
        TableName=config_table,
        Item={k: {'S': v} if isinstance(v, str) else {'M': {
            kk: {'N': str(vv)} if isinstance(vv, (int, float)) else {'BOOL': vv} if isinstance(vv, bool) else {'S': str(vv)}
            for kk, vv in v.items()
        }} for k, v in org_config.items()}
    )

    return org_config


def create_test_application(
    dynamodb_client,
    config_table: str,
    org_id: str,
    app_id: str = None
) -> Dict[str, Any]:
    """Create a test application under an organization"""
    if app_id is None:
        app_id = 'test-app'

    now = datetime.now(timezone.utc).isoformat()
    client_secret = generate_client_secret()
    hashed_secret = hash_secret(client_secret)
    client_id = f'org-{org_id}-app-{app_id}'

    app_config = {
        'pk': f'ORG#{org_id}',
        'sk': f'APP#{app_id}',
        'entity_type': 'application',
        'org_id': org_id,
        'app_id': app_id,
        'app_name': 'Test Application',
        'client_id': client_id,
        'client_secret_hash': hashed_secret,
        'created_at': now,
        'updated_at': now,
        'status': 'active',
        'quota_config': {
            'daily_budget': 5000000,  # $5 in USD micros
            'monthly_budget': 150000000,  # $150 in USD micros
            'enable_quota_enforcement': True,
            'fallback_strategy': 'cheapest'
        },
        'model_preferences': {
            'preferred_models': ['anthropic.claude-3-5-sonnet-20241022-v2:0'],
            'fallback_models': ['anthropic.claude-3-5-haiku-20241022-v1:0'],
            'blocked_models': []
        }
    }

    print_info(f"Creating application: {app_id} under organization: {org_id}")

    # Convert to DynamoDB format
    dynamodb_item = {
        'pk': {'S': app_config['pk']},
        'sk': {'S': app_config['sk']},
        'entity_type': {'S': app_config['entity_type']},
        'org_id': {'S': app_config['org_id']},
        'app_id': {'S': app_config['app_id']},
        'app_name': {'S': app_config['app_name']},
        'client_id': {'S': app_config['client_id']},
        'client_secret_hash': {'S': app_config['client_secret_hash']},
        'created_at': {'S': app_config['created_at']},
        'updated_at': {'S': app_config['updated_at']},
        'status': {'S': app_config['status']},
        'quota_config': {'M': {
            'daily_budget': {'N': str(app_config['quota_config']['daily_budget'])},
            'monthly_budget': {'N': str(app_config['quota_config']['monthly_budget'])},
            'enable_quota_enforcement': {'BOOL': app_config['quota_config']['enable_quota_enforcement']},
            'fallback_strategy': {'S': app_config['quota_config']['fallback_strategy']}
        }},
        'model_preferences': {'M': {
            'preferred_models': {'L': [{'S': m} for m in app_config['model_preferences']['preferred_models']]},
            'fallback_models': {'L': [{'S': m} for m in app_config['model_preferences']['fallback_models']]},
            'blocked_models': {'L': []}
        }}
    }

    dynamodb_client.put_item(
        TableName=config_table,
        Item=dynamodb_item
    )

    return {
        **app_config,
        'client_secret': client_secret  # Return unhashed for output
    }


def main():
    if len(sys.argv) < 2:
        print_error("Environment not specified")
        print("Usage: python seed-dynamodb.py <environment>")
        print("Environments: dev, staging, prod")
        sys.exit(1)

    environment = sys.argv[1]

    if environment not in ['dev', 'staging', 'prod']:
        print_error(f"Invalid environment: {environment}")
        print("Valid environments: dev, staging, prod")
        sys.exit(1)

    aws_region = os.environ.get('AWS_REGION', 'us-east-1')

    print_info(f"Seeding DynamoDB for environment: {environment}")
    print_info(f"AWS Region: {aws_region}")

    # Initialize AWS clients
    dynamodb = boto3.client('dynamodb', region_name=aws_region)

    # Table names
    config_table = f'bedrock-cost-keeper-config-{environment}'

    print_info(f"Using config table: {config_table}")

    # Check if table exists
    try:
        dynamodb.describe_table(TableName=config_table)
    except dynamodb.exceptions.ResourceNotFoundException:
        print_error(f"Table not found: {config_table}")
        print_error("Please deploy the infrastructure first")
        sys.exit(1)

    # Create test organization
    org_id = str(uuid.uuid4())
    org = create_test_organization(dynamodb, config_table, org_id)

    # Create test application
    app = create_test_application(dynamodb, config_table, org_id, 'test-app')

    # Print summary
    print("")
    print_info("=== Seeding Complete ===")
    print(f"Organization ID: {org_id}")
    print(f"Organization Name: {org['org_name']}")
    print(f"Application ID: {app['app_id']}")
    print(f"Application Name: {app['app_name']}")
    print(f"Client ID: {app['client_id']}")
    print(f"Client Secret: {app['client_secret']}")
    print("")

    print_warn("IMPORTANT: Save the Client ID and Client Secret securely!")
    print_info("Update your test-client/config.json with these credentials:")
    print("")
    print(json.dumps({
        'client_id': app['client_id'],
        'client_secret': app['client_secret'],
        'org_id': org_id,
        'app_id': app['app_id']
    }, indent=2))
    print("")
    print_info("Done!")


if __name__ == '__main__':
    main()
