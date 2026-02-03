# Quick Start: Pricing Simulation

Run these commands to verify pricing calculations and aggregation.

## One-Command Run

```bash
./tests/simulation/run_simulation.sh
```

This will:
1. ✅ Check DynamoDB Local is running
2. ✅ Verify database setup
3. ✅ Run all 7 simulation tests
4. ✅ Display results with color-coded output

## Expected Output

```
╔═══════════════════════════════════════════════════════════════════╗
║         Bedrock Cost Keeper - Pricing Simulation Tests           ║
╚═══════════════════════════════════════════════════════════════════╝

[1/3] Checking prerequisites...
✅ DynamoDB Local is running

[2/3] Verifying database setup...
✅ Database tables exist

[3/3] Running pricing simulation tests...

======================================================================
TEST 1: Single Premium Submission
======================================================================
Model: Nova Pro (Premium)
Input tokens: 1,500
Output tokens: 800
Expected cost: 3,760 micro-USD ($0.003760)
Actual cost: 3,760 micro-USD ($0.003760)
Match: ✅ PASS

... (more tests) ...

╔═══════════════════════════════════════════════════════════════════╗
║                    ✅ ALL TESTS PASSED                            ║
╚═══════════════════════════════════════════════════════════════════╝

✅ Cost calculations verified
✅ Aggregation working correctly
✅ All model tiers accurate
✅ Edge cases handled
```

## Manual Setup (if needed)

### 1. Start DynamoDB Local
```bash
finch run -d -p 8000:8000 amazon/dynamodb-local
```

### 2. Create Tables
```bash
python scripts/init_local_dynamodb.py init
```

### 3. Seed Test Data
```bash
python scripts/init_local_dynamodb.py seed
```

### 4. Run Tests
```bash
pytest tests/simulation/test_pricing_simulation.py -v -s
```

## What Gets Tested

| Test # | Description | Verification |
|--------|-------------|--------------|
| 1 | Single Premium | Nova Pro cost calculation |
| 2 | Single Standard | Nova 2 Lite cost calculation |
| 3 | Single Economy | Nova Micro cost calculation |
| 4 | Multiple Submissions | Aggregation across 5 requests |
| 5 | Mixed Models | Premium + Standard + Economy mix |
| 6 | Edge Cases | Min/max tokens, zero values |
| 7 | Quota Tracking | Daily aggregation (10 requests) |

## Pricing Being Tested

### Nova Pro (Premium)
- Input: 800,000 micro-USD per 1M tokens ($0.80/1M)
- Output: 3,200,000 micro-USD per 1M tokens ($3.20/1M)

### Nova 2 Lite (Standard)
- Input: 330,000 micro-USD per 1M tokens ($0.33/1M)
- Output: 2,750,000 micro-USD per 1M tokens ($2.75/1M)

### Nova Micro (Economy)
- Input: 35,000 micro-USD per 1M tokens ($0.035/1M)
- Output: 140,000 micro-USD per 1M tokens ($0.14/1M)

## Example Calculations Verified

### Premium: 1,500 input / 800 output
```
Input cost:  (1,500 × 800,000) ÷ 1,000,000 = 1,200 micro-USD
Output cost: (800 × 3,200,000) ÷ 1,000,000 = 2,560 micro-USD
Total cost:  3,760 micro-USD = $0.00376
```

### Standard: 10,000 input / 2,000 output
```
Input cost:  (10,000 × 330,000) ÷ 1,000,000 = 3,300 micro-USD
Output cost: (2,000 × 2,750,000) ÷ 1,000,000 = 5,500 micro-USD
Total cost:  8,800 micro-USD = $0.00880
```

### Economy: 5,000 input / 1,000 output
```
Input cost:  (5,000 × 35,000) ÷ 1,000,000 = 175 micro-USD
Output cost: (1,000 × 140,000) ÷ 1,000,000 = 140 micro-USD
Total cost:  315 micro-USD = $0.000315
```

## Troubleshooting

### "Connection refused" error
**Problem**: DynamoDB Local not running
**Solution**: `finch run -d -p 8000:8000 amazon/dynamodb-local`

### "Table not found" error
**Problem**: Tables not created
**Solution**: `python scripts/init_local_dynamodb.py init && python scripts/init_local_dynamodb.py seed`

### Tests fail with wrong costs
**Problem**: Stale pricing data
**Solution**: Check `config.yaml` has correct pricing (see PRICING_VERIFICATION.md)

## Next Steps

After successful simulation:
1. ✅ Pricing calculations are accurate
2. ✅ Ready for production deployment
3. ✅ Can configure real AWS environment

See [deployment.md](../../docs/deployment.md) for production setup.
