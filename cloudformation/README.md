# CloudFormation Deployment Guide

This directory contains CloudFormation templates for deploying the Bedrock Metering System infrastructure.

## Templates

### 1. dynamodb-table.yaml
Deploys only the DynamoDB table with optional configuration.

**Parameters:**
- `TableName`: Name of the DynamoDB table (default: `bedrock-metering`)
- `BillingMode`: PAY_PER_REQUEST or PROVISIONED (default: `PAY_PER_REQUEST`)
- `ReadCapacityUnits`: Read capacity (only for PROVISIONED mode)
- `WriteCapacityUnits`: Write capacity (only for PROVISIONED mode)

**Deploy:**
```bash
aws cloudformation deploy \
  --template-file dynamodb-table.yaml \
  --stack-name bedrock-metering-db \
  --parameter-overrides TableName=bedrock-metering \
  --capabilities CAPABILITY_IAM
```

### 2. complete-stack.yaml
Deploys the complete system including:
- DynamoDB table
- Lambda function for usage aggregator
- Lambda function for pricing refresh
- EventBridge schedulers
- IAM roles and policies
- CloudWatch alarms

**Parameters:**
- `TableName`: Name of the DynamoDB table (default: `bedrock-metering`)
- `AggregatorIntervalMinutes`: Aggregator run frequency (default: `1` minute)
- `ShardCount`: Number of usage shards (default: `8`)

**Deploy:**
```bash
# First, build the Lambda functions (if using Lambda-based aggregator)
cargo lambda build --release --arm64

# Then deploy the stack
aws cloudformation deploy \
  --template-file complete-stack.yaml \
  --stack-name bedrock-metering \
  --parameter-overrides \
      TableName=bedrock-metering \
      AggregatorIntervalMinutes=1 \
      ShardCount=8 \
  --capabilities CAPABILITY_IAM CAPABILITY_AUTO_EXPAND
```

## DynamoDB Table Schema

### Single-Table Design

The table uses a single-table design with composite keys:
- **Primary Key**: `pk` (partition key) + `sk` (sort key)
- **TTL Attribute**: `ttl_epoch` (automatic cleanup)

### Entity Types

#### 1. Config (Org Configuration)
```
PK: ORG#{org_id}
SK: "" (empty string for org config)
Attributes:
  - timezone: string
  - quota_scope: "ORG" | "USER"
  - modelA_id: string
  - modelB_id: string
  - modelA_daily_quota_usd_micros: number
  - modelB_daily_quota_usd_micros: number
  - fallback_enabled: boolean
  - agg_shard_count: number
  - tight_mode_threshold_pct: number
  - updated_at_epoch: number
```

#### 2. UserOverride
```
PK: ORG#{org_id}
SK: USER#{user_id}
Attributes:
  - modelA_daily_quota_usd_micros_override: number (optional)
  - modelB_daily_quota_usd_micros_override: number (optional)
  - updated_at_epoch: number
```

#### 3. StickyState
```
PK: {ORG|USER}#{scope_id}#DAY#{org_day}
Attributes:
  - active_model: "A" | "B"
  - reason: string
  - activated_at_epoch: number
  - expires_at_epoch: number (TTL)
```

#### 4. RequestLedger
```
PK: {request_id}
Attributes:
  - org_id: string
  - user_id: string (optional)
  - scope_type: "ORG" | "USER"
  - scope_id: string
  - org_day: string (YYYYMMDD)
  - model_used: "A" | "B"
  - bedrock_model_id: string
  - status: string
  - input_tokens: number
  - output_tokens: number
  - cost_usd_micros: number
  - price_version: string
  - created_at_epoch: number
  - ttl_epoch: number (TTL)
```

#### 5. UsageAggSharded
```
PK: {ORG|USER}#{scope_id}#DAY#{org_day}#MODEL#{A|B}#SH#{shard_id}
Attributes:
  - cost_usd_micros: number
  - input_tokens: number
  - output_tokens: number
  - requests: number
  - updated_at_epoch: number
```

#### 6. DailyTotal
```
PK: {ORG|USER}#{scope_id}#DAY#{org_day}#MODEL#{A|B}
Attributes:
  - cost_usd_micros: number
  - input_tokens: number
  - output_tokens: number
  - requests: number
  - updated_at_epoch: number
```

#### 7. PricingCache
```
PK: {bedrock_model_id}
SK: {YYYY-MM-DD}
Attributes:
  - input_token_price_usd_micros: number
  - output_token_price_usd_micros: number
  - fetched_at_epoch: number
  - expires_at_epoch: number (optional)
```

## Access Patterns

### Read Patterns
1. **Get org config**: `GetItem(PK=ORG#{org_id}, SK="")`
2. **Get user override**: `GetItem(PK=ORG#{org_id}, SK=USER#{user_id})`
3. **Get sticky state**: `GetItem(PK={scope}#DAY#{day})`
4. **Get daily total**: `GetItem(PK={scope}#DAY#{day}#MODEL#{model})`
5. **Get pricing**: `GetItem(PK={model_id}, SK={date})`

### Write Patterns
1. **Put request ledger**: `PutItem` (immutable)
2. **Update usage shard**: `UpdateItem` with ADD operations (atomic)
3. **Flip sticky state**: `UpdateItem` with conditional check (first-writer-wins)
4. **Aggregate to daily total**: `PutItem` (overwrite, idempotent)

## Cost Estimation

### For 10 req/s workload (~26M requests/month):

**DynamoDB:**
- Writes: ~25.9M/month → ~$0.32
- Reads: ~4.3M/month → ~$1.08
- Storage: < 1 GB → ~$0.25
- **Total DynamoDB: ~$1.65/month**

**Lambda (if using serverless aggregator):**
- Aggregator: 43,200 invocations/month × 500ms → ~$0.50
- **Total Lambda: ~$0.50/month**

**Total infrastructure: ~$2.15/month** (excludes Bedrock inference costs)

## Monitoring

The stack creates CloudWatch alarms for:
- Aggregator function errors
- DynamoDB throttling

View metrics in CloudWatch console or CLI:
```bash
# View aggregator metrics
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Duration \
  --dimensions Name=FunctionName,Value=bedrock-metering-aggregator \
  --start-time 2026-01-22T00:00:00Z \
  --end-time 2026-01-22T23:59:59Z \
  --period 3600 \
  --statistics Average
```

## Cleanup

To delete all resources:
```bash
aws cloudformation delete-stack --stack-name bedrock-metering
```

**Note:** This will permanently delete all data. Export data before deletion if needed.
