# Pricing Simulation Tests

Comprehensive end-to-end tests that simulate real usage scenarios to verify:
- ✅ Cost calculations are mathematically correct
- ✅ Multiple submissions aggregate properly
- ✅ Different model tiers calculate correctly
- ✅ Edge cases are handled properly

## Prerequisites

1. **DynamoDB Local** must be running:
   ```bash
   finch run -d -p 8000:8000 amazon/dynamodb-local
   ```

2. **Initialize tables and seed test data**:
   ```bash
   python scripts/init_local_dynamodb.py create
   python scripts/init_local_dynamodb.py seed
   ```

## Running the Simulation

### Run all simulation tests:
```bash
pytest tests/simulation/test_pricing_simulation.py -v -s
```

### Run specific test:
```bash
# Test single premium submission
pytest tests/simulation/test_pricing_simulation.py::TestPricingSimulation::test_single_submission_premium -v -s

# Test aggregation
pytest tests/simulation/test_pricing_simulation.py::TestPricingSimulation::test_multiple_submissions_aggregation -v -s

# Test quota tracking
pytest tests/simulation/test_pricing_simulation.py::TestQuotaTracking::test_quota_aggregation -v -s
```

## Test Coverage

### Test 1: Single Premium Submission ✅
- **Model**: Nova Pro (amazon.nova-pro-v1:0)
- **Scenario**: 1,500 input / 800 output tokens
- **Verifies**: Cost calculation for premium tier
- **Expected**: 3,760 micro-USD ($0.00376)

### Test 2: Single Standard Submission ✅
- **Model**: Nova 2 Lite (amazon.nova-2-lite-v1:0)
- **Scenario**: 10,000 input / 2,000 output tokens
- **Verifies**: Cost calculation for standard tier
- **Expected**: 8,800 micro-USD ($0.00880)

### Test 3: Single Economy Submission ✅
- **Model**: Nova Micro (amazon.nova-micro-v1:0)
- **Scenario**: 5,000 input / 1,000 output tokens
- **Verifies**: Cost calculation for economy tier
- **Expected**: 315 micro-USD ($0.000315)

### Test 4: Multiple Submissions Aggregation ✅
- **Scenario**: 5 premium requests with varying token counts
- **Verifies**: Individual costs calculate correctly AND sum matches expected total
- **Expected**: Each request cost accurate, total aggregates correctly

### Test 5: Mixed Model Submissions ✅
- **Scenario**: Mix of premium, standard, and economy requests
- **Verifies**: Different model tiers calculate correctly in same session
- **Expected**: Per-tier totals and grand total accurate

### Test 6: Edge Cases ✅
- **Scenarios**:
  - Minimum tokens (1 input / 1 output)
  - Zero input tokens
  - Zero output tokens
  - Very large token counts (1M+ tokens)
- **Verifies**: Integer division handles edge cases correctly

### Test 7: Daily Quota Aggregation ✅
- **Scenario**: 10 identical premium requests
- **Verifies**: Costs aggregate toward daily quota tracking
- **Expected**: Consistent cost per request, proper aggregation

## Example Output

```
======================================================================
TEST 1: Single Premium Submission
======================================================================
Model: Nova Pro (Premium)
Input tokens: 1,500
Output tokens: 800
Expected cost: 3,760 micro-USD ($0.003760)
Actual cost: 3,760 micro-USD ($0.003760)
Match: ✅ PASS

======================================================================
TEST 4: Multiple Submissions Aggregation
======================================================================

Submitting 5 requests:
#    Input      Output     Expected Cost        Actual Cost
----------------------------------------------------------------------
1    1,000      500        2,400                2,400
2    2,000      1,000      4,800                4,800
3    1,500      800        3,760                3,760
4    3,000      1,500      7,200                7,200
5    2,500      1,200      5,840                5,840
----------------------------------------------------------------------
TOTAL                      24,000               24,000

Expected total: $0.024000
Actual total: $0.024000
Match: ✅ PASS
```

## Pricing Reference

All calculations use verified AWS Bedrock pricing (us-east-1):

| Model | Input (micro-USD/1M) | Output (micro-USD/1M) |
|-------|----------------------|-----------------------|
| Nova Pro (Premium) | 800,000 | 3,200,000 |
| Nova 2 Lite (Standard) | 330,000 | 2,750,000 |
| Nova Micro (Economy) | 35,000 | 140,000 |

## Cost Calculation Formula

```python
input_cost = (input_tokens × input_price_per_1m) ÷ 1,000,000
output_cost = (output_tokens × output_price_per_1m) ÷ 1,000,000
total_cost = input_cost + output_cost  # All in micro-USD
```

Uses integer division (`//`) to prevent floating-point errors.

## Troubleshooting

### DynamoDB Connection Error
```
Error: Could not connect to DynamoDB Local
```
**Solution**: Ensure DynamoDB Local is running on port 8000

### Tables Not Found
```
Error: Table 'bedrock-cost-keeper-config' not found
```
**Solution**: Run table creation and seeding:
```bash
python scripts/init_local_dynamodb.py create
python scripts/init_local_dynamodb.py seed
```

### Authentication Error
```
Error: Invalid credentials
```
**Solution**: Ensure test data is seeded with org and app credentials

## Related Documentation

- [Pricing Documentation](../../docs/pricing.md) - Pricing tables and examples
- [Pricing Verification](../../docs/PRICING_VERIFICATION.md) - Complete audit trail
- [API Specification](../../docs/api_spec.md) - Usage submission endpoints
- [Application Specification](../../docs/app_spec.md) - Cost calculation details
