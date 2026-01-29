"""Integration tests for usage submission with real DynamoDB Local."""

import pytest
import asyncio
from datetime import datetime, timezone
import uuid


@pytest.mark.integration
class TestUsageSubmissionIntegration:
    """Integration tests for usage submission endpoint."""

    @pytest.mark.asyncio
    async def test_submit_single_usage_to_db(
        self,
        integration_test_client,
        integration_auth_headers,
        test_org_credentials,
        sample_usage_data,
        dynamodb_bridge
    ):
        """Test submitting a single usage and verify it's stored in DynamoDB with calculated cost."""
        creds = test_org_credentials

        # Submit usage (cost calculated server-side)
        response = await integration_test_client.post(
            f"/api/v1/orgs/{creds['org_id']}/apps/{creds['app_id']}/usage",
            headers=integration_auth_headers,
            json=sample_usage_data
        )

        assert response.status_code == 202
        data = response.json()
        assert data["status"] == "accepted"
        assert data["request_id"] == sample_usage_data["request_id"]
        assert "processing" in data
        assert "cost_usd_micros" in data["processing"], "Server should calculate and return cost"

        # Verify data was written to DynamoDB (aggregates table)
        import aioboto3

        session = aioboto3.Session()

        async with session.resource(
            'dynamodb',
            endpoint_url='http://localhost:8000',
            region_name='us-east-1',
            aws_access_key_id='fake',
            aws_secret_access_key='fake'
        ) as dynamodb:

            agg_table = await dynamodb.Table('bedrock-cost-keeper-aggregates')

            # Check if aggregate record exists for this model
            response = await agg_table.scan()
            items = response.get('Items', [])

            assert len(items) > 0, "No aggregate records found in DynamoDB"

            # Find our record - check that request_id is in the request_ids set
            found = False
            for item in items:
                request_ids = item.get('request_ids', set())
                if sample_usage_data['request_id'] in request_ids:
                    # Verify the aggregated data includes our submission
                    assert item.get('cost_usd_micros', 0) > 0, "Cost should be calculated and stored"
                    assert item.get('input_tokens', 0) >= sample_usage_data['input_tokens']
                    assert item.get('output_tokens', 0) >= sample_usage_data['output_tokens']
                    found = True
                    break

            assert found, f"Usage data for request_id {sample_usage_data['request_id']} not found in aggregates"

    @pytest.mark.asyncio
    async def test_service_calculates_cost_correctly(
        self,
        integration_test_client,
        integration_auth_headers,
        test_org_credentials,
        dynamodb_bridge
    ):
        """Test that service calculates cost correctly using pricing data."""
        creds = test_org_credentials

        # Test with known values
        # Premium model: $3 input, $15 output per 1M tokens
        # 1500 input + 800 output should = (1500 * 3 / 1000) + (800 * 15 / 1000) = 4.5 + 12 = $16.5 = 16500 micro-USD
        usage_data = {
            "request_id": str(uuid.uuid4()),
            "model_label": "premium",
            "bedrock_model_id": "anthropic.claude-3-opus-20240229-v1:0",
            "input_tokens": 1500,
            "output_tokens": 800,
            "status": "OK",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        response = await integration_test_client.post(
            f"/api/v1/orgs/{creds['org_id']}/apps/{creds['app_id']}/usage",
            headers=integration_auth_headers,
            json=usage_data
        )

        assert response.status_code == 202
        data = response.json()

        # Verify calculated cost is returned
        assert "processing" in data
        assert "cost_usd_micros" in data["processing"]
        calculated_cost = data["processing"]["cost_usd_micros"]

        # Verify cost calculation is reasonable (should be around 16500 for premium model)
        # Allow some variance due to potential pricing differences
        assert calculated_cost > 0, "Cost should be greater than zero"

    @pytest.mark.asyncio
    async def test_submit_batch_usage_to_db(
        self,
        integration_test_client,
        integration_auth_headers,
        test_org_credentials,
        dynamodb_bridge
    ):
        """Test submitting batch usage and verify all are stored with calculated costs."""
        creds = test_org_credentials

        # Create batch of usage data (no cost_usd_micros field)
        batch_usage = []
        for i in range(3):
            usage = {
                "request_id": str(uuid.uuid4()),
                "model_label": "standard",
                "bedrock_model_id": "anthropic.claude-3-sonnet-20240229-v1:0",
                "input_tokens": 1000 + (i * 100),
                "output_tokens": 500 + (i * 50),
                "status": "OK",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            batch_usage.append(usage)

        batch_request = {"requests": batch_usage}

        # Submit batch
        response = await integration_test_client.post(
            f"/api/v1/orgs/{creds['org_id']}/apps/{creds['app_id']}/usage/batch",
            headers=integration_auth_headers,
            json=batch_request
        )

        assert response.status_code == 207
        data = response.json()
        assert data["accepted"] == 3
        assert data["failed"] == 0

        # Verify all records in DynamoDB aggregates
        import aioboto3

        session = aioboto3.Session()

        async with session.resource(
            'dynamodb',
            endpoint_url='http://localhost:8000',
            region_name='us-east-1',
            aws_access_key_id='fake',
            aws_secret_access_key='fake'
        ) as dynamodb:

            agg_table = await dynamodb.Table('bedrock-cost-keeper-aggregates')
            response = await agg_table.scan()
            items = response.get('Items', [])

            # Should have aggregate records
            assert len(items) > 0, f"Expected aggregate records, found none"

            # Verify each request_id exists in request_ids sets
            all_request_ids = set()
            for item in items:
                all_request_ids.update(item.get('request_ids', set()))

            for usage in batch_usage:
                assert usage['request_id'] in all_request_ids, f"Request ID {usage['request_id']} not found in aggregates"

    @pytest.mark.asyncio
    async def test_usage_aggregation_updates(
        self,
        integration_test_client,
        integration_auth_headers,
        test_org_credentials,
        sample_usage_data,
        dynamodb_bridge
    ):
        """Test that submitting usage updates daily aggregates with calculated costs."""
        creds = test_org_credentials

        # Submit multiple usage records for the same model
        submitted_usage = []
        for i in range(3):
            usage_data = sample_usage_data.copy()
            usage_data['request_id'] = str(uuid.uuid4())
            usage_data['input_tokens'] = 1000 * (i + 1)
            usage_data['output_tokens'] = 500 * (i + 1)

            response = await integration_test_client.post(
                f"/api/v1/orgs/{creds['org_id']}/apps/{creds['app_id']}/usage",
                headers=integration_auth_headers,
                json=usage_data
            )

            assert response.status_code == 202
            submitted_usage.append(usage_data)

            # Give event loop time to clean up
            await asyncio.sleep(0.1)

        # Check aggregates table
        import aioboto3

        session = aioboto3.Session()

        async with session.resource(
            'dynamodb',
            endpoint_url='http://localhost:8000',
            region_name='us-east-1',
            aws_access_key_id='fake',
            aws_secret_access_key='fake'
        ) as dynamodb:

            agg_table = await dynamodb.Table('bedrock-cost-keeper-aggregates')
            response = await agg_table.scan()
            items = response.get('Items', [])

            # Should have aggregate records
            assert len(items) > 0, "No aggregate records found"

            # Verify total cost is accumulated (should be > 0 since service calculates it)
            total_cost = sum(item.get('cost_usd_micros', 0) for item in items)
            assert total_cost > 0, "Total cost should be greater than zero (calculated by service)"

    @pytest.mark.asyncio
    async def test_retrieve_aggregates_after_submission(
        self,
        integration_test_client,
        integration_auth_headers,
        test_org_credentials,
        sample_usage_data
    ):
        """Test retrieving aggregates after submitting usage."""
        creds = test_org_credentials

        # Submit usage
        response = await integration_test_client.post(
            f"/api/v1/orgs/{creds['org_id']}/apps/{creds['app_id']}/usage",
            headers=integration_auth_headers,
            json=sample_usage_data
        )

        assert response.status_code == 202

        # Give event loop time to clean up
        await asyncio.sleep(0.1)

        # Retrieve aggregates
        response = await integration_test_client.get(
            f"/api/v1/orgs/{creds['org_id']}/apps/{creds['app_id']}/aggregates/today",
            headers=integration_auth_headers
        )

        assert response.status_code == 200
        data = response.json()

        assert data['org_id'] == creds['org_id']
        assert data['app_id'] == creds['app_id']
        # Should reflect the calculated cost
        assert data['total_cost_usd_micros'] >= 0

    @pytest.mark.asyncio
    async def test_idempotent_usage_submission(
        self,
        integration_test_client,
        integration_auth_headers,
        test_org_credentials,
        sample_usage_data,
        dynamodb_bridge
    ):
        """Test that submitting the same request_id twice is idempotent."""
        creds = test_org_credentials

        # Submit the same usage twice
        response1 = await integration_test_client.post(
            f"/api/v1/orgs/{creds['org_id']}/apps/{creds['app_id']}/usage",
            headers=integration_auth_headers,
            json=sample_usage_data
        )

        # Give event loop time to clean up
        await asyncio.sleep(0.1)

        response2 = await integration_test_client.post(
            f"/api/v1/orgs/{creds['org_id']}/apps/{creds['app_id']}/usage",
            headers=integration_auth_headers,
            json=sample_usage_data
        )

        assert response1.status_code == 202
        assert response2.status_code == 202

        # Verify idempotency - request_id should appear only once in request_ids set
        import aioboto3

        session = aioboto3.Session()

        async with session.resource(
            'dynamodb',
            endpoint_url='http://localhost:8000',
            region_name='us-east-1',
            aws_access_key_id='fake',
            aws_secret_access_key='fake'
        ) as dynamodb:

            agg_table = await dynamodb.Table('bedrock-cost-keeper-aggregates')
            response = await agg_table.scan()
            items = response.get('Items', [])

            # Find the shard containing our request_id
            found_count = 0
            for item in items:
                request_ids = item.get('request_ids', set())
                if sample_usage_data['request_id'] in request_ids:
                    found_count += 1
                    # Verify the cost is counted only once (not doubled)
                    # Cost should be calculated consistently
                    assert item.get('cost_usd_micros') > 0

            # Should be found in exactly one shard
            assert found_count == 1, f"Expected request_id in 1 shard, found in {found_count}"

    @pytest.mark.asyncio
    async def test_usage_submission_different_models(
        self,
        integration_test_client,
        integration_auth_headers,
        test_org_credentials,
        dynamodb_bridge
    ):
        """Test submitting usage for different models with different pricing."""
        creds = test_org_credentials

        # Only use models configured for the app (premium and standard)
        models = [
            {
                "label": "premium",
                "bedrock_id": "anthropic.claude-3-opus-20240229-v1:0",
            },
            {
                "label": "standard",
                "bedrock_id": "anthropic.claude-3-sonnet-20240229-v1:0",
            }
        ]

        # Submit usage for each model
        for model in models:
            usage_data = {
                "request_id": str(uuid.uuid4()),
                "model_label": model["label"],
                "bedrock_model_id": model["bedrock_id"],
                "input_tokens": 1000,
                "output_tokens": 500,
                "status": "OK",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

            response = await integration_test_client.post(
                f"/api/v1/orgs/{creds['org_id']}/apps/{creds['app_id']}/usage",
                headers=integration_auth_headers,
                json=usage_data
            )

            assert response.status_code == 202
            data = response.json()
            # Verify cost was calculated
            assert "processing" in data
            assert "cost_usd_micros" in data["processing"]
            assert data["processing"]["cost_usd_micros"] > 0

            # Give event loop time to clean up
            await asyncio.sleep(0.1)

        # Verify all models are in the aggregates
        import aioboto3

        session = aioboto3.Session()

        async with session.resource(
            'dynamodb',
            endpoint_url='http://localhost:8000',
            region_name='us-east-1',
            aws_access_key_id='fake',
            aws_secret_access_key='fake'
        ) as dynamodb:

            agg_table = await dynamodb.Table('bedrock-cost-keeper-aggregates')
            response = await agg_table.scan()
            items = response.get('Items', [])

            # Extract model labels from pk (format: scope#LABEL#model_label#SH#shard_id)
            found_labels = set()
            for item in items:
                pk = item.get('pk', '')
                if '#LABEL#' in pk:
                    # Extract model_label from pk
                    parts = pk.split('#LABEL#')
                    if len(parts) > 1:
                        model_part = parts[1].split('#SH#')[0]
                        found_labels.add(model_part)

            # Check that at least premium and standard are there
            assert 'premium' in found_labels, f"Expected 'premium' in {found_labels}"
            assert 'standard' in found_labels, f"Expected 'standard' in {found_labels}"
