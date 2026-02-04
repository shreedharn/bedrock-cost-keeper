#!/usr/bin/env python3
"""Initialize local DynamoDB tables for testing."""
import sys
import argparse
import asyncio
from pathlib import Path
import aioboto3
from botocore.exceptions import ClientError

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

async def create_tables():
    """Create all required DynamoDB tables in local instance."""

    # Connect to local DynamoDB
    session = aioboto3.Session()

    async with session.resource(
        'dynamodb',
        endpoint_url='http://localhost:8000',
        region_name='us-east-1',
        aws_access_key_id='fake',
        aws_secret_access_key='fake'
    ) as dynamodb:

        tables_to_create = [
            {
                'name': 'bedrock-cost-keeper-config',
                'key_schema': [
                    {'AttributeName': 'org_key', 'KeyType': 'HASH'},
                    {'AttributeName': 'resource_key', 'KeyType': 'RANGE'}
                ],
                'attribute_definitions': [
                    {'AttributeName': 'org_key', 'AttributeType': 'S'},
                    {'AttributeName': 'resource_key', 'AttributeType': 'S'}
                ]
            },
            {
                'name': 'bedrock-cost-keeper-usage',
                'key_schema': [
                    {'AttributeName': 'shard_key', 'KeyType': 'HASH'},
                    {'AttributeName': 'date_key', 'KeyType': 'RANGE'}
                ],
                'attribute_definitions': [
                    {'AttributeName': 'shard_key', 'AttributeType': 'S'},
                    {'AttributeName': 'date_key', 'AttributeType': 'S'}
                ]
            },
            {
                'name': 'bedrock-cost-keeper-aggregates',
                'key_schema': [
                    {'AttributeName': 'usage_key', 'KeyType': 'HASH'},
                    {'AttributeName': 'date_key', 'KeyType': 'RANGE'}
                ],
                'attribute_definitions': [
                    {'AttributeName': 'usage_key', 'AttributeType': 'S'},
                    {'AttributeName': 'date_key', 'AttributeType': 'S'}
                ]
            },
            {
                'name': 'bedrock-cost-keeper-tokens',
                'key_schema': [
                    {'AttributeName': 'token_jti', 'KeyType': 'HASH'}
                ],
                'attribute_definitions': [
                    {'AttributeName': 'token_jti', 'AttributeType': 'S'}
                ],
                'ttl': 'ttl'
            },
            {
                'name': 'bedrock-cost-keeper-secrets',
                'key_schema': [
                    {'AttributeName': 'token', 'KeyType': 'HASH'}
                ],
                'attribute_definitions': [
                    {'AttributeName': 'token', 'AttributeType': 'S'}
                ],
                'ttl': 'ttl'
            }
        ]

        for table_spec in tables_to_create:
            table_name = table_spec['name']

            try:
                # Check if table exists
                table = await dynamodb.Table(table_name)
                await table.load()
                print(f"✅ Table '{table_name}' already exists")

            except ClientError as e:
                if e.response['Error']['Code'] == 'ResourceNotFoundException':
                    # Create table
                    print(f"Creating table '{table_name}'...")

                    create_params = {
                        'TableName': table_name,
                        'KeySchema': table_spec['key_schema'],
                        'AttributeDefinitions': table_spec['attribute_definitions'],
                        'BillingMode': 'PAY_PER_REQUEST'
                    }

                    table = await dynamodb.create_table(**create_params)

                    # Wait for table to be created
                    await table.wait_until_exists()

                    # Enable TTL if specified
                    if 'ttl' in table_spec:
                        session_client = aioboto3.Session()
                        async with session_client.client(
                            'dynamodb',
                            endpoint_url='http://localhost:8000',
                            region_name='us-east-1',
                            aws_access_key_id='fake',
                            aws_secret_access_key='fake'
                        ) as client:
                            await client.update_time_to_live(
                                TableName=table_name,
                                TimeToLiveSpecification={
                                    'Enabled': True,
                                    'AttributeName': table_spec['ttl']
                                }
                            )

                    print(f"✅ Table '{table_name}' created successfully")
                else:
                    raise


async def seed_test_data():
    """Seed test data for integration tests."""

    session = aioboto3.Session()

    async with session.resource(
        'dynamodb',
        endpoint_url='http://localhost:8000',
        region_name='us-east-1',
        aws_access_key_id='fake',
        aws_secret_access_key='fake'
    ) as dynamodb:

        # Add test organization
        config_table = await dynamodb.Table('bedrock-cost-keeper-config')

        from datetime import datetime, timezone
        from src.infrastructure.security.jwt_handler import JWTHandler

        jwt_handler = JWTHandler()

        # Test organization config
        test_org_id = '550e8400-e29b-41d4-a716-446655440000'
        client_secret = jwt_handler.generate_secret()
        secret_hash = jwt_handler.hash_secret(client_secret)

        await config_table.put_item(
            Item={
                'org_key': f'ORG#{test_org_id}',
                'resource_key': '#',  # Root config marker (DynamoDB doesn't allow empty strings)
                'org_name': 'Test Organization',
                'client_id': f'org-{test_org_id}',
                'client_secret_hash': secret_hash,
                'timezone': 'America/New_York',
                'quota_scope': 'ORG',
                'model_ordering': ['premium', 'standard', 'economy'],
                'quotas': {
                    'premium': 1000000,
                    'standard': 500000,
                    'economy': 100000
                },
                'created_at_epoch': int(datetime.now(timezone.utc).timestamp()),
                'updated_at_epoch': int(datetime.now(timezone.utc).timestamp())
            }
        )

        # Test application config
        test_app_id = 'test-app'
        app_client_secret = jwt_handler.generate_secret()
        app_secret_hash = jwt_handler.hash_secret(app_client_secret)

        await config_table.put_item(
            Item={
                'org_key': f'ORG#{test_org_id}',
                'resource_key': f'APP#{test_app_id}',
                'app_name': 'Test Application',
                'client_id': f'org-{test_org_id}-app-{test_app_id}',
                'client_secret_hash': app_secret_hash,
                'model_ordering': ['premium', 'standard', 'economy'],
                'quotas': {
                    'premium': 500000,
                    'standard': 250000,
                    'economy': 100000
                },
                'created_at_epoch': int(datetime.now(timezone.utc).timestamp()),
                'updated_at_epoch': int(datetime.now(timezone.utc).timestamp())
            }
        )

        print(f"✅ Seeded test organization: {test_org_id}")
        print(f"   Org Client Secret: {client_secret}")
        print(f"   App Client Secret: {app_client_secret}")


async def clear_tables():
    """Clear all data from tables (for clean test runs)."""

    session = aioboto3.Session()

    async with session.resource(
        'dynamodb',
        endpoint_url='http://localhost:8000',
        region_name='us-east-1',
        aws_access_key_id='fake',
        aws_secret_access_key='fake'
    ) as dynamodb:

        table_names = [
            'bedrock-cost-keeper-config',
            'bedrock-cost-keeper-usage',
            'bedrock-cost-keeper-aggregates',
            'bedrock-cost-keeper-tokens',
            'bedrock-cost-keeper-secrets'
        ]

        for table_name in table_names:
            try:
                table = await dynamodb.Table(table_name)

                # Scan and delete all items
                response = await table.scan()
                items = response.get('Items', [])

                for item in items:
                    # Extract key attributes based on table
                    if table_name == 'bedrock-cost-keeper-tokens':
                        await table.delete_item(Key={'token_jti': item['token_jti']})
                    elif table_name == 'bedrock-cost-keeper-secrets':
                        await table.delete_item(Key={'token': item['token']})
                    elif table_name == 'bedrock-cost-keeper-config':
                        await table.delete_item(Key={'org_key': item['org_key'], 'resource_key': item['resource_key']})
                    elif table_name == 'bedrock-cost-keeper-usage':
                        await table.delete_item(Key={'shard_key': item['shard_key'], 'date_key': item['date_key']})
                    elif table_name == 'bedrock-cost-keeper-aggregates':
                        await table.delete_item(Key={'usage_key': item['usage_key'], 'date_key': item['date_key']})

                print(f"✅ Cleared table '{table_name}' ({len(items)} items)")

            except Exception as e:
                print(f"⚠️  Error clearing table '{table_name}': {e}")


async def main():
    """Main execution."""

    parser = argparse.ArgumentParser(description='Manage local DynamoDB for testing')
    parser.add_argument('action', choices=['init', 'seed', 'clear', 'reset'],
                       help='Action to perform')

    args = parser.parse_args()

    if args.action == 'init':
        print("Initializing DynamoDB tables...")
        await create_tables()
        print("\n✅ All tables initialized!")

    elif args.action == 'seed':
        print("Seeding test data...")
        await seed_test_data()
        print("\n✅ Test data seeded!")

    elif args.action == 'clear':
        print("Clearing all table data...")
        await clear_tables()
        print("\n✅ All tables cleared!")

    elif args.action == 'reset':
        print("Resetting database (clear + seed)...")
        await clear_tables()
        await seed_test_data()
        print("\n✅ Database reset complete!")


if __name__ == '__main__':
    asyncio.run(main())
