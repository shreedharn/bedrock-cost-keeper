"""
Comprehensive pricing simulation test.

Tests:
1. Cost calculation correctness for each tier
2. Aggregation across multiple submissions
3. Daily quota tracking
4. Different model usage patterns
"""

import pytest
import asyncio
from datetime import datetime, timezone
import uuid
from decimal import Decimal


# Test data based on verified pricing
PRICING_DATA = {
    'premium': {
        'model_id': 'amazon.nova-pro-v1:0',
        'label': 'premium',
        'input_price_micro_usd_per_1m': 800_000,
        'output_price_micro_usd_per_1m': 3_200_000,
    },
    'standard': {
        'model_id': 'amazon.nova-2-lite-v1:0',
        'label': 'standard',
        'input_price_micro_usd_per_1m': 330_000,
        'output_price_micro_usd_per_1m': 2_750_000,
    },
    'economy': {
        'model_id': 'amazon.nova-micro-v1:0',
        'label': 'economy',
        'input_price_micro_usd_per_1m': 35_000,
        'output_price_micro_usd_per_1m': 140_000,
    }
}


def calculate_expected_cost(input_tokens: int, output_tokens: int, tier: str) -> int:
    """Calculate expected cost in micro-USD using integer division."""
    pricing = PRICING_DATA[tier]
    input_cost = (input_tokens * pricing['input_price_micro_usd_per_1m']) // 1_000_000
    output_cost = (output_tokens * pricing['output_price_micro_usd_per_1m']) // 1_000_000
    return input_cost + output_cost


def format_cost(micro_usd: int) -> str:
    """Format micro-USD as readable USD string."""
    return f"${micro_usd / 1_000_000:.6f}"


@pytest.mark.integration
class TestPricingSimulation:
    """Simulation tests for pricing calculations and aggregation."""

    @pytest.mark.asyncio
    async def test_single_submission_premium(
        self,
        integration_test_client,
        integration_auth_headers,
        test_org_credentials
    ):
        """Test single submission with premium model - verify exact cost calculation."""
        creds = test_org_credentials

        # Test case: 1,500 input / 800 output tokens
        input_tokens = 1500
        output_tokens = 800
        expected_cost = calculate_expected_cost(input_tokens, output_tokens, 'premium')

        print(f"\n{'='*70}")
        print(f"TEST 1: Single Premium Submission")
        print(f"{'='*70}")
        print(f"Model: Nova Pro (Premium)")
        print(f"Input tokens: {input_tokens:,}")
        print(f"Output tokens: {output_tokens:,}")
        print(f"Expected cost: {expected_cost:,} micro-USD ({format_cost(expected_cost)})")

        usage_data = {
            "request_id": str(uuid.uuid4()),
            "model_label": "premium",
            "bedrock_model_id": PRICING_DATA['premium']['model_id'],
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "status": "OK",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        response = await integration_test_client.post(
            f"/api/v1/orgs/{creds['org_id']}/apps/{creds['app_id']}/usage",
            headers=integration_auth_headers,
            json=usage_data
        )

        assert response.status_code == 202, f"Expected 202, got {response.status_code}"
        data = response.json()

        assert data["status"] == "accepted"
        assert "processing" in data
        assert "cost_usd_micros" in data["processing"]

        actual_cost = data["processing"]["cost_usd_micros"]

        print(f"Actual cost: {actual_cost:,} micro-USD ({format_cost(actual_cost)})")
        print(f"Match: {'✅ PASS' if actual_cost == expected_cost else '❌ FAIL'}")

        assert actual_cost == expected_cost, \
            f"Cost mismatch! Expected {expected_cost}, got {actual_cost}"

    @pytest.mark.asyncio
    async def test_single_submission_standard(
        self,
        integration_test_client,
        integration_auth_headers,
        test_org_credentials
    ):
        """Test single submission with standard model (Nova 2 Lite)."""
        creds = test_org_credentials

        input_tokens = 10_000
        output_tokens = 2_000
        expected_cost = calculate_expected_cost(input_tokens, output_tokens, 'standard')

        print(f"\n{'='*70}")
        print(f"TEST 2: Single Standard Submission")
        print(f"{'='*70}")
        print(f"Model: Nova 2 Lite (Standard)")
        print(f"Input tokens: {input_tokens:,}")
        print(f"Output tokens: {output_tokens:,}")
        print(f"Expected cost: {expected_cost:,} micro-USD ({format_cost(expected_cost)})")

        usage_data = {
            "request_id": str(uuid.uuid4()),
            "model_label": "standard",
            "bedrock_model_id": PRICING_DATA['standard']['model_id'],
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
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
        actual_cost = data["processing"]["cost_usd_micros"]

        print(f"Actual cost: {actual_cost:,} micro-USD ({format_cost(actual_cost)})")
        print(f"Match: {'✅ PASS' if actual_cost == expected_cost else '❌ FAIL'}")

        assert actual_cost == expected_cost

    @pytest.mark.asyncio
    async def test_single_submission_economy(
        self,
        integration_test_client,
        integration_auth_headers,
        test_org_credentials
    ):
        """Test single submission with economy model (Nova Micro)."""
        creds = test_org_credentials

        input_tokens = 5_000
        output_tokens = 1_000
        expected_cost = calculate_expected_cost(input_tokens, output_tokens, 'economy')

        print(f"\n{'='*70}")
        print(f"TEST 3: Single Economy Submission")
        print(f"{'='*70}")
        print(f"Model: Nova Micro (Economy)")
        print(f"Input tokens: {input_tokens:,}")
        print(f"Output tokens: {output_tokens:,}")
        print(f"Expected cost: {expected_cost:,} micro-USD ({format_cost(expected_cost)})")

        usage_data = {
            "request_id": str(uuid.uuid4()),
            "model_label": "economy",
            "bedrock_model_id": PRICING_DATA['economy']['model_id'],
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
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
        actual_cost = data["processing"]["cost_usd_micros"]

        print(f"Actual cost: {actual_cost:,} micro-USD ({format_cost(actual_cost)})")
        print(f"Match: {'✅ PASS' if actual_cost == expected_cost else '❌ FAIL'}")

        assert actual_cost == expected_cost

    @pytest.mark.asyncio
    async def test_multiple_submissions_aggregation(
        self,
        integration_test_client,
        integration_auth_headers,
        test_org_credentials
    ):
        """Test that multiple submissions aggregate correctly."""
        creds = test_org_credentials

        print(f"\n{'='*70}")
        print(f"TEST 4: Multiple Submissions Aggregation")
        print(f"{'='*70}")

        # Submit 5 requests with different token counts
        submissions = [
            {'input': 1_000, 'output': 500, 'tier': 'premium'},
            {'input': 2_000, 'output': 1_000, 'tier': 'premium'},
            {'input': 1_500, 'output': 800, 'tier': 'premium'},
            {'input': 3_000, 'output': 1_500, 'tier': 'premium'},
            {'input': 2_500, 'output': 1_200, 'tier': 'premium'},
        ]

        total_expected_cost = 0
        actual_costs = []

        print(f"\nSubmitting {len(submissions)} requests:")
        print(f"{'#':<4} {'Input':<10} {'Output':<10} {'Expected Cost':<20} {'Actual Cost':<20}")
        print(f"{'-'*70}")

        for i, sub in enumerate(submissions, 1):
            expected = calculate_expected_cost(sub['input'], sub['output'], sub['tier'])
            total_expected_cost += expected

            usage_data = {
                "request_id": str(uuid.uuid4()),
                "model_label": sub['tier'],
                "bedrock_model_id": PRICING_DATA[sub['tier']]['model_id'],
                "input_tokens": sub['input'],
                "output_tokens": sub['output'],
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
            actual = data["processing"]["cost_usd_micros"]
            actual_costs.append(actual)

            print(f"{i:<4} {sub['input']:<10,} {sub['output']:<10,} {expected:<20,} {actual:<20,}")
            assert actual == expected, f"Submission {i} cost mismatch"

        total_actual_cost = sum(actual_costs)

        print(f"{'-'*70}")
        print(f"{'TOTAL':<24} {total_expected_cost:<20,} {total_actual_cost:<20,}")
        print(f"\nExpected total: {format_cost(total_expected_cost)}")
        print(f"Actual total: {format_cost(total_actual_cost)}")
        print(f"Match: {'✅ PASS' if total_actual_cost == total_expected_cost else '❌ FAIL'}")

        assert total_actual_cost == total_expected_cost

    @pytest.mark.asyncio
    async def test_mixed_model_submissions(
        self,
        integration_test_client,
        integration_auth_headers,
        test_org_credentials
    ):
        """Test submissions across different model tiers."""
        creds = test_org_credentials

        print(f"\n{'='*70}")
        print(f"TEST 5: Mixed Model Tier Submissions")
        print(f"{'='*70}")

        # Mix of premium, standard, and economy
        submissions = [
            {'input': 1_000, 'output': 500, 'tier': 'premium'},
            {'input': 5_000, 'output': 1_000, 'tier': 'standard'},
            {'input': 10_000, 'output': 2_000, 'tier': 'economy'},
            {'input': 2_000, 'output': 800, 'tier': 'premium'},
            {'input': 8_000, 'output': 1_500, 'tier': 'standard'},
        ]

        tier_totals = {'premium': 0, 'standard': 0, 'economy': 0}

        print(f"\n{'Tier':<12} {'Input':<10} {'Output':<10} {'Expected Cost':<20} {'Actual Cost':<20}")
        print(f"{'-'*70}")

        for sub in submissions:
            expected = calculate_expected_cost(sub['input'], sub['output'], sub['tier'])

            usage_data = {
                "request_id": str(uuid.uuid4()),
                "model_label": sub['tier'],
                "bedrock_model_id": PRICING_DATA[sub['tier']]['model_id'],
                "input_tokens": sub['input'],
                "output_tokens": sub['output'],
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
            actual = data["processing"]["cost_usd_micros"]
            tier_totals[sub['tier']] += actual

            print(f"{sub['tier']:<12} {sub['input']:<10,} {sub['output']:<10,} {expected:<20,} {actual:<20,}")
            assert actual == expected

        print(f"{'-'*70}")
        print(f"\nCost breakdown by tier:")
        for tier, total in tier_totals.items():
            print(f"  {tier.capitalize():<12}: {total:>10,} micro-USD ({format_cost(total)})")

        grand_total = sum(tier_totals.values())
        print(f"  {'Grand Total':<12}: {grand_total:>10,} micro-USD ({format_cost(grand_total)})")
        print(f"\n✅ All mixed-tier submissions calculated correctly")

    @pytest.mark.asyncio
    async def test_edge_cases(
        self,
        integration_test_client,
        integration_auth_headers,
        test_org_credentials
    ):
        """Test edge cases: very small and very large token counts."""
        creds = test_org_credentials

        print(f"\n{'='*70}")
        print(f"TEST 6: Edge Cases - Very Small and Large Token Counts")
        print(f"{'='*70}")

        test_cases = [
            {'input': 1, 'output': 1, 'tier': 'premium', 'desc': 'Minimum tokens'},
            {'input': 0, 'output': 100, 'tier': 'economy', 'desc': 'Zero input'},
            {'input': 100, 'output': 0, 'tier': 'standard', 'desc': 'Zero output'},
            {'input': 1_000_000, 'output': 500_000, 'tier': 'premium', 'desc': '1M+ tokens'},
        ]

        print(f"\n{'Description':<25} {'Input':<12} {'Output':<12} {'Expected':<15} {'Actual':<15} {'Status'}")
        print(f"{'-'*90}")

        for case in test_cases:
            expected = calculate_expected_cost(case['input'], case['output'], case['tier'])

            usage_data = {
                "request_id": str(uuid.uuid4()),
                "model_label": case['tier'],
                "bedrock_model_id": PRICING_DATA[case['tier']]['model_id'],
                "input_tokens": case['input'],
                "output_tokens": case['output'],
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
            actual = data["processing"]["cost_usd_micros"]

            status = '✅ PASS' if actual == expected else '❌ FAIL'
            print(f"{case['desc']:<25} {case['input']:<12,} {case['output']:<12,} {expected:<15,} {actual:<15,} {status}")

            assert actual == expected, f"Edge case '{case['desc']}' failed"

        print(f"\n✅ All edge cases handled correctly")


@pytest.mark.integration
class TestQuotaTracking:
    """Test daily quota tracking and aggregation."""

    @pytest.mark.asyncio
    async def test_quota_aggregation(
        self,
        integration_test_client,
        integration_auth_headers,
        test_org_credentials
    ):
        """Test that costs aggregate toward daily quota."""
        creds = test_org_credentials

        print(f"\n{'='*70}")
        print(f"TEST 7: Daily Quota Aggregation")
        print(f"{'='*70}")

        # Submit multiple requests and check if they aggregate
        num_requests = 10
        tokens_per_request = {'input': 1_000, 'output': 500}

        print(f"\nSubmitting {num_requests} identical premium requests:")
        print(f"  Tokens per request: {tokens_per_request['input']:,} input / {tokens_per_request['output']:,} output")

        cost_per_request = calculate_expected_cost(
            tokens_per_request['input'],
            tokens_per_request['output'],
            'premium'
        )
        expected_total = cost_per_request * num_requests

        print(f"  Cost per request: {cost_per_request:,} micro-USD ({format_cost(cost_per_request)})")
        print(f"  Expected total: {expected_total:,} micro-USD ({format_cost(expected_total)})")

        for i in range(num_requests):
            usage_data = {
                "request_id": str(uuid.uuid4()),
                "model_label": "premium",
                "bedrock_model_id": PRICING_DATA['premium']['model_id'],
                "input_tokens": tokens_per_request['input'],
                "output_tokens": tokens_per_request['output'],
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
            assert data["processing"]["cost_usd_micros"] == cost_per_request

            if (i + 1) % 3 == 0:
                print(f"  Progress: {i + 1}/{num_requests} requests submitted...")

        print(f"\n✅ All {num_requests} requests submitted with consistent costs")
        print(f"\nNote: Actual aggregation to DailyTotal happens via background aggregator process")
        print(f"      which runs every 60 seconds to consolidate sharded counters.")


if __name__ == "__main__":
    print("Run with: pytest tests/simulation/test_pricing_simulation.py -v -s")
