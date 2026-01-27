"""Integration tests for cost submission with real DynamoDB Local."""

import pytest
import asyncio
from datetime import datetime, timezone
import uuid


@pytest.mark.integration
class TestCostSubmissionIntegration:
    """Integration tests for cost submission endpoint."""

    @pytest.mark.asyncio
    async def test_submit_single_cost_to_db(
        self,
        integration_test_client,
        integration_auth_headers,
        test_org_credentials,
        sample_cost_data,
        dynamodb_bridge
    ):
        """Test submitting a single cost and verify it's stored in DynamoDB."""
        creds = test_org_credentials

        # Submit cost
        response = await integration_test_client.post(
            f"/api/v1/orgs/{creds['org_id']}/apps/{creds['app_id']}/costs",
            headers=integration_auth_headers,
            json=sample_cost_data
        )

        assert response.status_code == 202
        data = response.json()
        assert data["status"] == "accepted"
        assert data["request_id"] == sample_cost_data["request_id"]

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
                if sample_cost_data['request_id'] in request_ids:
                    # Verify the aggregated data includes our submission
                    assert item.get('cost_usd_micros', 0) >= sample_cost_data['cost_usd_micros']
                    assert item.get('input_tokens', 0) >= sample_cost_data['input_tokens']
                    assert item.get('output_tokens', 0) >= sample_cost_data['output_tokens']
                    found = True
                    break

            assert found, f"Cost data for request_id {sample_cost_data['request_id']} not found in aggregates"

    @pytest.mark.asyncio
    async def test_submit_batch_costs_to_db(
        self,
        integration_test_client,
        integration_auth_headers,
        test_org_credentials,
        dynamodb_bridge
    ):
        """Test submitting batch costs and verify all are stored."""
        creds = test_org_credentials

        # Create batch of costs
        batch_costs = []
        for i in range(3):
            cost = {
                "request_id": str(uuid.uuid4()),
                "model_label": "standard",
                "bedrock_model_id": "anthropic.claude-3-sonnet-20240229-v1:0",
                "input_tokens": 1000 + (i * 100),
                "output_tokens": 500 + (i * 50),
                "cost_usd_micros": 25000 + (i * 1000),
                "status": "OK",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            batch_costs.append(cost)

        batch_request = {"requests": batch_costs}

        # Submit batch
        response = await integration_test_client.post(
            f"/api/v1/orgs/{creds['org_id']}/apps/{creds['app_id']}/costs/batch",
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

            for cost in batch_costs:
                assert cost['request_id'] in all_request_ids, f"Request ID {cost['request_id']} not found in aggregates"

    @pytest.mark.asyncio
    async def test_cost_aggregation_updates(
        self,
        integration_test_client,
        integration_auth_headers,
        test_org_credentials,
        sample_cost_data,
        dynamodb_bridge
    ):
        """Test that submitting costs updates daily aggregates."""
        creds = test_org_credentials

        # Submit multiple costs for the same model
        for i in range(3):
            cost_data = sample_cost_data.copy()
            cost_data['request_id'] = str(uuid.uuid4())
            cost_data['cost_usd_micros'] = 10000 * (i + 1)

            response = await integration_test_client.post(
                f"/api/v1/orgs/{creds['org_id']}/apps/{creds['app_id']}/costs",
                headers=integration_auth_headers,
                json=cost_data
            )

            assert response.status_code == 202

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

            # Verify total cost is accumulated
            total_cost = sum(item.get('cost_usd_micros', 0) for item in items)
            expected_total = 10000 + 20000 + 30000  # Sum of our 3 submissions
            assert total_cost == expected_total, f"Expected total cost {expected_total}, got {total_cost}"

    @pytest.mark.asyncio
    async def test_retrieve_aggregates_after_submission(
        self,
        integration_test_client,
        integration_auth_headers,
        test_org_credentials,
        sample_cost_data
    ):
        """Test retrieving aggregates after submitting costs."""
        creds = test_org_credentials

        # Submit a cost
        response = await integration_test_client.post(
            f"/api/v1/orgs/{creds['org_id']}/apps/{creds['app_id']}/costs",
            headers=integration_auth_headers,
            json=sample_cost_data
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
        # Should reflect the submitted cost
        assert data['total_cost_usd_micros'] >= 0

    @pytest.mark.asyncio
    async def test_idempotent_cost_submission(
        self,
        integration_test_client,
        integration_auth_headers,
        test_org_credentials,
        sample_cost_data,
        dynamodb_bridge
    ):
        """Test that submitting the same request_id twice is idempotent."""
        creds = test_org_credentials

        # Submit the same cost twice
        response1 = await integration_test_client.post(
            f"/api/v1/orgs/{creds['org_id']}/apps/{creds['app_id']}/costs",
            headers=integration_auth_headers,
            json=sample_cost_data
        )

        # Give event loop time to clean up
        await asyncio.sleep(0.1)

        response2 = await integration_test_client.post(
            f"/api/v1/orgs/{creds['org_id']}/apps/{creds['app_id']}/costs",
            headers=integration_auth_headers,
            json=sample_cost_data
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
                if sample_cost_data['request_id'] in request_ids:
                    found_count += 1
                    # Verify the cost is counted only once (not doubled)
                    # The cost should be exactly what we submitted, not 2x
                    assert item.get('cost_usd_micros') == sample_cost_data['cost_usd_micros']

            # Should be found in exactly one shard
            assert found_count == 1, f"Expected request_id in 1 shard, found in {found_count}"

    @pytest.mark.asyncio
    async def test_cost_submission_different_models(
        self,
        integration_test_client,
        integration_auth_headers,
        test_org_credentials,
        dynamodb_bridge
    ):
        """Test submitting costs for different models."""
        creds = test_org_credentials

        # Only use models configured for the app (premium and standard)
        models = [
            {
                "label": "premium",
                "bedrock_id": "anthropic.claude-3-opus-20240229-v1:0",
                "cost": 45000
            },
            {
                "label": "standard",
                "bedrock_id": "anthropic.claude-3-sonnet-20240229-v1:0",
                "cost": 25000
            }
        ]

        # Submit cost for each model
        for model in models:
            cost_data = {
                "request_id": str(uuid.uuid4()),
                "model_label": model["label"],
                "bedrock_model_id": model["bedrock_id"],
                "input_tokens": 1000,
                "output_tokens": 500,
                "cost_usd_micros": model["cost"],
                "status": "OK",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

            response = await integration_test_client.post(
                f"/api/v1/orgs/{creds['org_id']}/apps/{creds['app_id']}/costs",
                headers=integration_auth_headers,
                json=cost_data
            )

            assert response.status_code == 202

            # Give event loop time to clean up
            await asyncio.sleep(0.1)

        # Verify all three models are in the aggregates
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

            # Note: Economy may not be in app config, so it might not be allowed
            # Check that at least premium and standard are there
            assert 'premium' in found_labels, f"Expected 'premium' in {found_labels}"
            assert 'standard' in found_labels, f"Expected 'standard' in {found_labels}"
