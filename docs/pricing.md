# Amazon Bedrock Nova Models Pricing

## Overview

This document provides pricing information for Amazon Nova models available through Amazon Bedrock. Pricing is based on token usage and varies by model tier and capability.

## Pricing Table

### Standard Tier Models
**Input Modalities:** Text, Image, Video

| Amazon Nova Model | Price per 1,000 Input Tokens | Price per 1,000 Output Tokens | Price per 1M Input Tokens | Price per 1M Output Tokens |
|-------------------|------------------------------|-------------------------------|---------------------------|----------------------------|
| Amazon Nova 2 Lite | $0.00033 | $0.00275 | $0.33 | $2.75 |
| Amazon Nova Micro | $0.000035 | $0.00014 | $0.035 | $0.14 |
| Amazon Nova Pro | $0.0008 | $0.0032 | $0.80 | $3.20 |


## Pricing in Micro-USD Format

For use in configuration files and cost calculations, prices are expressed in micro-USD per 1 million tokens:

| Model | Input Price (micro-USD/1M) | Output Price (micro-USD/1M) | Model ID |
|-------|---------------------------|----------------------------|----------|
| **Nova 2 Lite** (Standard) | 330,000 | 2,750,000 | `amazon.nova-2-lite-v1:0` |
| **Nova Micro** (Economy) | 35,000 | 140,000 | `amazon.nova-micro-v1:0` |
| **Nova Pro** (Premium) | 800,000 | 3,200,000 | `amazon.nova-pro-v1:0` |



## Cost Calculation Formula

Cost in micro-USD is calculated as:

```
cost_usd_micros = (input_tokens × input_price_per_1m / 1,000,000) +
                  (output_tokens × output_price_per_1m / 1,000,000)
```

Where:
- `input_tokens`: Number of input tokens consumed
- `output_tokens`: Number of output tokens generated
- `input_price_per_1m`: Input price in micro-USD per 1 million tokens
- `output_price_per_1m`: Output price in micro-USD per 1 million tokens

## Example Cost Calculations

### Example 1: Nova Pro (Premium Tier)
**Usage:** 1,500 input tokens, 800 output tokens

```
Input cost  = (1,500 × 800,000) / 1,000,000 = 1,200 micro-USD
Output cost = (800 × 3,200,000) / 1,000,000 = 2,560 micro-USD
Total cost  = 3,760 micro-USD ($0.00376)
```

### Example 2: Nova 2 Lite (Standard Tier)
**Usage:** 10,000 input tokens, 2,000 output tokens

```
Input cost  = (10,000 × 330,000) / 1,000,000 = 3,300 micro-USD
Output cost = (2,000 × 2,750,000) / 1,000,000 = 5,500 micro-USD
Total cost  = 8,800 micro-USD ($0.00880)
```

### Example 3: Nova Micro (Economy Tier)
**Usage:** 5,000 input tokens, 1,000 output tokens

```
Input cost  = (5,000 × 35,000) / 1,000,000 = 175 micro-USD
Output cost = (1,000 × 140,000) / 1,000,000 = 140 micro-USD
Total cost  = 315 micro-USD ($0.000315)
```

## Pricing Updates

Pricing information is fetched from the AWS Pricing API at runtime. The prices in `config.yaml` serve as **fallback values** only, used when:

1. The Pricing API is unreachable or down, AND
2. No cached pricing data exists in memory or DynamoDB

In normal operation, the AWS Pricing API is the single source of truth for all pricing data.

## Regional Pricing

All prices shown are for the **us-east-1** region. Pricing may vary by AWS region. The service automatically fetches region-specific pricing for inference profiles that support multi-region routing.

## Additional Notes

- Prices are subject to change by AWS. Always verify current pricing through the [AWS Bedrock Pricing page](https://aws.amazon.com/bedrock/pricing/).
- The service calculates costs server-side based on token counts provided by clients.
- Costs are tracked and aggregated in micro-USD (1 USD = 1,000,000 micro-USD) for precision.


---
