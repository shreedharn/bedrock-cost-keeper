# DynamoDB Schema Specification - Bedrock Price Keeper

## Overview

This database design supports the Bedrock Price Keeper REST service with the following characteristics:

- **N models** with label-based configuration 
- **Org and App scoping** 
- **Sticky fallback** through ordered model chains
- **Post-response metering** with eventual consistency

---

## Design Principles

### Anti-Hot-Partition Techniques

1. **Distributed writes**: Cost data distributed across N sharded counters
2. **Aggregated reads**: Single consolidated item for quota checks
3. **Controlled cadence**: Background aggregator updates totals every 60s (configurable)


### Cost Optimization

- Read 1 item for quota checks (not N shards)
- Atomic DynamoDB ADD operations
- TTL-based automatic cleanup
- Minimal index overhead

**Target cost**: ~$1.74/month for 10 req/s workload*

*_Cost estimates are illustrative only. Verify with current AWS pricing and validate accuracy based on your usage patterns._

---

## Table Summary

| Table | Purpose | Write Pattern | Notes |
|-------|---------|---------------|-------------------|
| **Config** | Org/app settings + credentials | Low (admin updates) |  None |
| **StickyState** | Fallback tracking | Once per day per scope/model | None |
| **UsageAggSharded** | Distributed counters | Per-request (8-64 shards) | Sharded |
| **DailyTotal** | Aggregated totals | Every 60s (by aggregator) |  Controlled cadence |
| **PricingCache** | Bedrock pricing | Once per day |  None |
| **RevokedTokens** | Token revocation list | Rare (on revoke) |  None |
| **SecretRetrievalTokens** | DEPRECATED - No longer used | N/A |  None |

---

## Table Schemas

### 1. Config Table

**Purpose**: Store organization and application configuration

**Hierarchy**:
- Org-level: Default settings for all apps
- App-level: Overrides for specific applications

#### Primary Key

- **org_key** (string): `ORG#{org_id}` - Organization partition, may include app for inference profiles
- **resource_key** (string): `"#"` (root config marker) for org config, or `APP#{app_id}` for app config, or `PROFILE#{profile_label}` for inference profiles

#### Access Patterns

1. Get org config: `GetItem(org_key="ORG#{org_id}", resource_key="#")`
2. Get app config: `GetItem(org_key="ORG#{org_id}", resource_key="APP#{app_id}")`
3. List all apps for org: `Query(org_key="ORG#{org_id}", resource_key begins_with "APP#")`
4. Get inference profile: `GetItem(org_key="ORG#{org_id}#APP#{app_id}", resource_key="PROFILE#{profile_label}")`

#### Org Config Item

**Key:**
```
org_key: "ORG#550e8400-e29b-41d4-a716-446655440000"
resource_key: "#"   # Root config marker (not empty string)
```

**Attributes:**
- `org_name` (string)
- `timezone` (string, IANA format, e.g., `America/New_York`)
- `quota_scope` (string: `"ORG"` | `"APP"`)
- `model_ordering` (list of strings: `["premium", "standard", "economy"]`)
- `quotas` (map: `{premium: 10000000, standard: 5000000}`)
- `sticky_fallback_enabled` (boolean, default: `true`)
- `agg_shard_count` (number, default: `8`)
- `tight_mode_threshold_pct` (number, default: `95`)
- `refresh_interval_normal_secs` (number, default: `300`)
- `refresh_interval_tight_secs` (number, default: `60`)
- `client_id` (string, e.g., `"org-550e8400-e29b-41d4-a716-446655440000"`)
- `client_secret_hash` (string, bcrypt hash of client secret)
- `client_secret_created_at_epoch` (number)
- `client_secret_rotation_grace_expires_at_epoch` (number, optional - during rotation)
- `provisioning_api_key_hash` (string, optional - for admin access)
- `created_at_epoch` (number)
- `updated_at_epoch` (number)

**Example:**
```json
{
  "org_key": "ORG#550e8400-e29b-41d4-a716-446655440000",
  "resource_key": "#",
  "org_name": "sample_corp",
  "timezone": "America/New_York",
  "quota_scope": "APP",
  "model_ordering": ["premium", "standard", "economy"],
  "quotas": {
    "premium": 10000000,
    "standard": 5000000,
    "economy": 2000000
  },
  "sticky_fallback_enabled": true,
  "agg_shard_count": 8,
  "tight_mode_threshold_pct": 95,
  "refresh_interval_normal_secs": 300,
  "refresh_interval_tight_secs": 60,
  "client_id": "org-550e8400-e29b-41d4-a716-446655440000",
  "client_secret_hash": "$2b$12$KIXhI8K7EXAMPLE_BCRYPT_HASH",
  "client_secret_created_at_epoch": 1737590400,
  "provisioning_api_key_hash": "$2b$12$EXAMPLE_API_KEY_HASH",
  "created_at_epoch": 1737590400,
  "updated_at_epoch": 1737590400
}
```

#### App Config Item

**Key:**
```
org_key: "ORG#550e8400-e29b-41d4-a716-446655440000"
resource_key: "APP#app-production-api"
```

**Attributes:**
- `app_name` (string)
- `model_ordering` (list of strings, optional - overrides org)
- `quotas` (map, optional - overrides org)
- `tight_mode_threshold_pct` (number, optional - overrides org)
- `refresh_interval_normal_secs` (number, optional - overrides org)
- `refresh_interval_tight_secs` (number, optional - overrides org)
- `client_id` (string, e.g., `"org-550e8400-e29b-41d4-a716-446655440000-app-app-production-api"`)
- `client_secret_hash` (string, bcrypt hash of client secret)
- `client_secret_created_at_epoch` (number)
- `client_secret_rotation_grace_expires_at_epoch` (number, optional - during rotation)
- `created_at_epoch` (number)
- `updated_at_epoch` (number)

**Inheritance Rules:**
- If attribute not present in app config, inherit from org config
- If app config doesn't exist, use org config entirely
- `quota_scope`, `timezone`, `agg_shard_count` always from org (not overridable)

**Example:**
```json
{
  "org_key": "ORG#550e8400-e29b-41d4-a716-446655440000",
  "resource_key": "APP#app-production-api",
  "app_name": "Production API",
  "model_ordering": ["premium", "standard"],
  "quotas": {
    "premium": 50000000,
    "standard": 20000000
  },
  "tight_mode_threshold_pct": 90,
  "client_id": "org-550e8400-e29b-41d4-a716-446655440000-app-app-production-api",
  "client_secret_hash": "$2b$12$EXAMPLE_APP_SECRET_HASH",
  "client_secret_created_at_epoch": 1737590400,
  "created_at_epoch": 1737590400,
  "updated_at_epoch": 1737590400
}
```

#### Inference Profile Item

**Purpose**: Register AWS Bedrock inference profiles for multi-tenant cost tracking

**Key:**
```
org_key: "ORG#{org_id}#APP#{app_id}"
resource_key: "PROFILE#{profile_label}"
```

**Attributes:**
- `profile_label` (string) - Label to use in usage submissions
- `inference_profile_arn` (string) - AWS Bedrock inference profile ARN
- `description` (string, optional) - Human-readable description
- `created_at` (string, ISO 8601) - When profile was registered
- `updated_at_epoch` (number) - Last update timestamp

**Example:**
```json
{
  "org_key": "ORG#550e8400-e29b-41d4-a716-446655440000#APP#app-production-api",
  "resource_key": "PROFILE#tenant-a-premium",
  "profile_label": "tenant-a-premium",
  "inference_profile_arn": "arn:aws:bedrock:us-east-1:123456789012:inference-profile/tenant-a",
  "description": "Premium profile for Tenant A",
  "created_at": "2026-01-23T15:30:45Z",
  "updated_at_epoch": 1737640245
}
```

**Label Resolution Priority:**
When a `model_label` is submitted in a usage request:
1. Check for registered inference profile (this table)
2. If not found, check config.yaml `model_labels`
3. If neither exists, reject request

**Usage Flow with Inference Profiles:**
1. Client registers profile: `POST /inference-profiles` → validates ARN format → stores in Config table
2. Client submits usage with `model_label` and `calling_region`
3. Service resolves label → finds inference profile
4. Service calls AWS GetInferenceProfile API to get model details (on first use, then memoized in memory)
5. Service extracts model for `calling_region` from AWS response
6. Service calculates cost using region-specific model pricing from Pricing API (or config.yaml fallback)
7. Quota tracking uses `model_label` (same as traditional models)

**Multi-Region Support:**
- Single profile can route to different models per region
- AWS GetInferenceProfile API called on-demand (first use) and memoized in memory
- Service requires `calling_region` in usage submission for profiles
- Traditional models (config.yaml) don't require `calling_region`

**Important Notes:**
- **No model_arns stored in database** - AWS is the source of truth, fetched on-demand via boto3
- **In-memory memoization** - Profile details cached in memory after first fetch
- **No List endpoint** - Listing registered profiles is out of scope for the cost tracker

---

### 2. StickyState Table

**Purpose**: Track sticky fallback decisions for each scope/day/model

**Note**: Only required if `sticky_fallback_enabled: true`

#### Primary Key

- **scope_key** (string): Complete scope identifier (org or org+app) - determines where sticky state applies
- **date_key** (string): `DAY#{day}` format for time-series organization

#### Key Patterns

**Org-scoped:**
```
scope_key: "ORG#550e8400-e29b-41d4-a716-446655440000"
date_key: "DAY#20260123"
```

**App-scoped:**
```
scope_key: "ORG#550e8400-e29b-41d4-a716-446655440000#APP#app-production-api"
date_key: "DAY#20260123"
```

**Note**: App-scoped keys MUST include org_id to prevent collisions when different orgs use the same app_id.

#### Attributes

- `active_model_label` (string: model label from ordering, e.g., `"standard"`)
- `active_model_index` (number: index in model_ordering, e.g., `1`)
- `reason` (string: `"QUOTA_EXCEEDED"`, `"MANUAL_OVERRIDE"`)
- `previous_model_label` (string: model that was exceeded)
- `activated_at_epoch` (number)
- `expires_at_epoch` (number, TTL attribute)

**Example:**
```json
{
  "scope_key": "ORG#550e8400-e29b-41d4-a716-446655440000",
  "date_key": "DAY#20260123",
  "active_model_label": "standard",
  "active_model_index": 1,
  "reason": "QUOTA_EXCEEDED",
  "previous_model_label": "premium",
  "activated_at_epoch": 1737640800,
  "expires_at_epoch": 1737676800
}
```

#### Access Pattern

- **Check sticky state**: `GetItem(scope_key={scope}, date_key="DAY#{day}")`
- **Set sticky state**: `PutItem(scope_key={scope}, date_key="DAY#{day}", ...)` with conditional expression:
  ```
  attribute_not_exists(active_model_label) OR active_model_index < :new_index
  ```
  This ensures we only move forward in the fallback chain, never backward

**Conditional Write Logic:**
- First writer wins when transitioning to a model
- Can only advance to later models in ordering (higher index)
- Prevents race conditions when multiple service instances detect quota breach

---

### 3. UsageAggSharded Table

**Purpose**: Distributed counters for per-request cost aggregation

**Design**: N shards per scope/model to prevent hot partitions, with time-series organization by day

#### Primary Key

- **shard_key** (string): Composite key identifying the specific usage shard: `{scope}#LABEL#{model_label}#SH#{shard_id}`
- **date_key** (string): `DAY#{day}` format for time-series organization

#### Key Patterns

**Org-scoped, Model "premium", Shard 0:**
```
shard_key: "ORG#550e8400-e29b-41d4-a716-446655440000#LABEL#premium#SH#0"
date_key: "DAY#20260123"
```

**App-scoped, Model "standard", Shard 3:**
```
shard_key: "ORG#550e8400-e29b-41d4-a716-446655440000#APP#app-production-api#LABEL#standard#SH#3"
date_key: "DAY#20260123"
```

**Note**: App-scoped keys MUST include org_id to prevent collisions when different orgs use the same app_id.

#### Attributes (Atomic Counters)

- `cost_usd_micros` (number)
- `input_tokens` (number)
- `output_tokens` (number)
- `requests` (number)
- `request_ids` (string set, optional - for deduplication, max ~3,000 UUIDs)
- `updated_at_epoch` (number)

**Example:**
```json
{
  "shard_key": "ORG#550e8400-e29b-41d4-a716-446655440000#LABEL#premium#SH#0",
  "date_key": "DAY#20260123",
  "cost_usd_micros": 1250000,
  "input_tokens": 150000,
  "output_tokens": 80000,
  "requests": 42,
  "request_ids": [
    "7c9e6679-7425-40de-944b-e07fc1f90ae7",
    "8d0f7780-8536-51ef-b827-557766551001",
    "..."
  ],
  "updated_at_epoch": 1737640800
}
```

**Note on Deduplication**:
- DynamoDB sets limited to 100KB (~3,000 UUIDs)
- For high-volume (>3,000 req/day/shard), use separate RequestDedup table
- Alternative: Accept small duplicate risk (< 0.1% in practice)

#### Write Pattern

**Per cost submission:**
```
UpdateItem:
  Key:
    shard_key = "{scope}#LABEL#{label}#SH#{shard_id}"
    date_key = "DAY#{day}"
  UpdateExpression: "ADD cost_usd_micros :c, input_tokens :i, output_tokens :o, requests :r SET updated_at_epoch = :t"
  ExpressionAttributeValues: computed values
```

**Scope key construction:**
```
if quota_scope == "ORG":
  scope = "ORG#{org_id}"
else:  # quota_scope == "APP"
  scope = "ORG#{org_id}#APP#{app_id}"
```

**Shard selection:**
```
shard_id = hash(request_id) % agg_shard_count
```

**Why this works:**
- Random distribution via hash function
- Each shard receives ~1/N of writes
- Atomic ADD operations ensure no lost updates
- No single partition becomes hot

---

### 4. DailyTotal Table

**Purpose**: Aggregated totals for efficient quota checks

**Critical**: Enables reading 1 item instead of N shards per quota check

#### Primary Key

- **usage_key** (string): Composite key identifying the usage metric: `{scope}#LABEL#{model_label}`
- **date_key** (string): `DAY#{day}` format for time-series organization

#### Key Patterns

**Org-scoped, Model "premium":**
```
usage_key: "ORG#550e8400-e29b-41d4-a716-446655440000#LABEL#premium"
date_key: "DAY#20260123"
```

**App-scoped, Model "standard":**
```
usage_key: "ORG#550e8400-e29b-41d4-a716-446655440000#APP#app-production-api#LABEL#standard"
date_key: "DAY#20260123"
```

**Note**: App-scoped keys MUST include org_id to prevent collisions when different orgs use the same app_id.

#### Attributes

- `cost_usd_micros` (number)
- `input_tokens` (number)
- `output_tokens` (number)
- `requests` (number)
- `updated_at_epoch` (number)

**Example:**
```json
{
  "usage_key": "ORG#550e8400-e29b-41d4-a716-446655440000#LABEL#premium",
  "date_key": "DAY#20260123",
  "cost_usd_micros": 9500000,
  "input_tokens": 1200000,
  "output_tokens": 650000,
  "requests": 342,
  "updated_at_epoch": 1737640800
}
```

#### Read Pattern

**Quota check (get current spend):**
```
GetItem:
  Key:
    usage_key = "{scope}#LABEL#{label}"
    date_key = "DAY#{today}"
  Returns: cost_usd_micros (compare to quota)
```

**Model selection (check all models in ordering):**
```
BatchGetItem:
  Keys: [
    {usage_key = "{scope}#LABEL#{label1}", date_key = "DAY#{today}"},
    {usage_key = "{scope}#LABEL#{label2}", date_key = "DAY#{today}"},
    ...
  ]
  Returns: Spend for each model in fallback chain
```

#### Write Pattern (Aggregator Only)

**Every 60 seconds, aggregator:**

1. **Read all shards:**
   ```
   BatchGetItem:
     Keys: [
       {shard_key = "{scope}#LABEL#{label}#SH#0", date_key = "DAY#{day}"},
       {shard_key = "{scope}#LABEL#{label}#SH#1", date_key = "DAY#{day}"},
       ...
       {shard_key = "{scope}#LABEL#{label}#SH#N-1", date_key = "DAY#{day}"}
     ]
   ```

2. **Sum in-memory:**
   ```
   total_cost = Σ(shard.cost_usd_micros)
   total_input = Σ(shard.input_tokens)
   total_output = Σ(shard.output_tokens)
   total_requests = Σ(shard.requests)
   ```

3. **Overwrite DailyTotal (idempotent):**
   ```
   PutItem:
     Key:
       usage_key = "{scope}#LABEL#{label}"
       date_key = "DAY#{day}"
     Item: {aggregated totals}
   ```

**Why this prevents hot partitions:**
- `DailyTotal` receives only 1-2 writes/minute (not per-request)
- Even with 100 concurrent service instances, write rate stays low
- Controlled by aggregator schedule, not request volume

**Benefits of time-series design (date_key as sort key):**
- Enables efficient historical queries via Query operations
- All days for a scope logically grouped under one partition key
- Follows DynamoDB time-series best practices
- No performance impact on current operations (GetItem still single-item lookup)
- Future analytics: `Query(usage_key, date_key BETWEEN "DAY#20260101" AND "DAY#20260130")`

---

### 5. PricingCache Table

**Purpose**: Cache Bedrock pricing to avoid repeated API calls

**Region Support**: Supports optional region-specific pricing for inference profiles

#### Primary Key

- **model_id** (string): The Bedrock model identifier (e.g., `amazon.nova-pro-v1:0`)
- **price_key** (string): Date or date+region composite: `{yyyy-mm-dd}` or `{yyyy-mm-dd}#{region}`

#### Key Patterns

**Traditional pricing (no region):**
```
model_id: "anthropic.claude-3-5-sonnet-20241022-v2:0"
price_key: "2026-01-23"
```

**Region-specific pricing (for inference profiles):**
```
model_id: "anthropic.claude-3-5-sonnet-20241022-v2:0"
price_key: "2026-01-23#us-east-1"
```

#### Attributes

- `model_label` (string: label from config, e.g., `"premium"`)
- `tier` (string: tier from config, e.g., `"premium"`)
- `family` (string: model family, e.g., `"claude-3.5"`)
- `description` (string: human-readable description)
- `input_price_usd_micros_per_1m` (number: price per 1M input tokens)
- `output_price_usd_micros_per_1m` (number: price per 1M output tokens)
- `fetched_at_epoch` (number)
- `expires_at_epoch` (number, TTL attribute - 2-3 days retention)

**Example:**
```json
{
  "model_id": "anthropic.claude-3-5-sonnet-20241022-v2:0",
  "price_key": "2026-01-23",
  "model_label": "premium",
  "tier": "premium",
  "family": "claude-3.5",
  "description": "Claude 3.5 Sonnet v2 - Premium tier, highest performance",
  "input_price_usd_micros_per_1m": 3000000,
  "output_price_usd_micros_per_1m": 15000000,
  "fetched_at_epoch": 1737590400,
  "expires_at_epoch": 1737849600
}
```

#### Access Pattern

- **Get today's pricing (traditional)**: `GetItem(model_id={bedrock_model_id}, price_key={today})`
- **Get today's pricing (region-specific)**: `GetItem(model_id={bedrock_model_id}, price_key="{today}#{region}")`
- **Write pricing**: `PutItem` once per day by pricing refresh process

**Pricing Resolution Order:**
1. Check region-specific pricing: `price_key="{date}#{region}"` (if region provided)
2. Check default pricing: `price_key="{date}"` (no region)
3. Fallback to `default_pricing` from config.yaml

**Note:** Region-specific pricing is used when `model_label` resolves to an inference profile and `calling_region` is provided in the usage submission.

---

### 6. RevokedTokens Table

**Purpose**: Track revoked JWT tokens to prevent their use before natural expiry

**Note**: Required for token revocation API endpoint

#### Primary Key

- **token_jti** (string): JWT ID claim (jti) from the token - unique identifier for each JWT
- No sort key (single-key table, one item per token)

#### Key Pattern

```
token_jti: "550e8400-e29b-41d4-a716-446655440000-1737640800"
```

#### Attributes

- `token_type` (string: `"access"` | `"refresh"`)
- `client_id` (string: identifies which client this token belongs to)
- `revoked_at_epoch` (number)
- `original_expiry_epoch` (number: when token would naturally expire)
- `expires_at_epoch` (number, TTL attribute - matches original token expiry)

**Example:**
```json
{
  "token_jti": "550e8400-e29b-41d4-a716-446655440000-1737640800",
  "token_type": "refresh",
  "client_id": "org-550e8400-e29b-41d4-a716-446655440000-app-app-production-api",
  "revoked_at_epoch": 1737640800,
  "original_expiry_epoch": 1740232800,
  "expires_at_epoch": 1740232800
}
```

#### Access Pattern

- **Check if token revoked**: `GetItem(token_jti={jti_value})`
  - If item exists, token is revoked
  - If item doesn't exist, token is valid (not revoked)
- **Revoke token**: `PutItem(token_jti={jti_value}, ...)` with TTL matching token expiry

**Performance Note**:
- Check happens on every authenticated request
- DynamoDB GetItem is fast (~5-10ms)
- Consider caching negative results (token NOT revoked) for 30-60 seconds

**TTL Cleanup**: Revoked tokens auto-deleted after original expiry time

---

### 7. SecretRetrievalTokens Table (DEPRECATED)

**Status**: DEPRECATED - This table is no longer used.

**Reason**: Secrets are now returned directly in registration/rotation responses instead of requiring a separate retrieval step. This simplifies the client integration flow (one HTTP call instead of two) and is more efficient while maintaining the same security level (secrets still only shown once, transmitted over TLS).

**Migration**: The table can be safely removed in a future database migration. No data needs to be preserved.

**Previous Purpose**: Stored one-time tokens for secure secret retrieval after registration/rotation

---

## Access Patterns Summary

### 1. Model Selection Decision

**Frequency**:
- Normal mode: Every 300 seconds (5 minutes)
- Tight mode: Every 60 seconds (1 minute)

**Steps:**
1. Compute org_day from org timezone
2. Determine scope (ORG or APP) from config
3. Read sticky state:
   ```
   GetItem: StickyState(scope_key="{scope}", date_key="DAY#{day}")
   ```
4. If sticky state exists, use `active_model_label`
5. Otherwise, read totals for all models in ordering:
   ```
   BatchGetItem: [
     DailyTotal(usage_key="{scope}#LABEL#{label1}", date_key="DAY#{day}"),
     DailyTotal(usage_key="{scope}#LABEL#{label2}", date_key="DAY#{day}"),
     ...
   ]
   ```
6. Find first model where `cost < quota`
7. If all quotas exceeded, check if should flip sticky state

**Database operations**: 1 GetItem + 1 BatchGetItem (2-4 models typically)

---

### 2. Cost Submission Processing

**Frequency**: Per request (async)

**Steps:**
1. Check for duplicate request_id (idempotency)
2. Compute scope and org_day
3. Select shard: `shard_id = hash(request_id) % N`
4. Update shard counter atomically with deduplication:
   ```
   UpdateItem: UsageAggSharded(
     shard_key="{scope}#LABEL#{label}#SH#{shard_id}",
     date_key="DAY#{day}",
     ADD cost_usd_micros :c, input_tokens :i, output_tokens :o, requests :r
     ADD request_ids (set): :request_id
     SET updated_at_epoch = :t
   )
   ```
5. Read current DailyTotal to return in response:
   ```
   GetItem: DailyTotal(
     usage_key="{scope}#LABEL#{label}",
     date_key="DAY#{day}"
   )
   ```
6. Calculate quota percentage and determine mode (NORMAL/TIGHT)
7. Return status with DailyTotal data

**Database operations**: 1 UpdateItem (atomic ADD) + 1 GetItem (read total)

**Response includes**: Current daily total, quota percentage, operating mode

**Idempotency**: `request_ids` set in UsageAggSharded prevents duplicate processing
- DynamoDB set ADD is idempotent (adding same value twice = once)
- Sets have 100KB size limit (~3,000 UUIDs per shard/day/model)
- For higher volume, use separate RequestDedup table with TTL

---

### 3. Aggregator Process

**Frequency**: Every 60 seconds (configurable in config.yaml)

**For each active scope/day/model combination:**

1. **Read all shards:**
   ```
   BatchGetItem: [
     {shard_key="{scope}#LABEL#{label}#SH#0", date_key="DAY#{day}"},
     {shard_key="{scope}#LABEL#{label}#SH#1", date_key="DAY#{day}"},
     ...
   ]
   ```

2. **Sum totals in-memory**

3. **Write consolidated total:**
   ```
   PutItem: DailyTotal(
     usage_key="{scope}#LABEL#{label}",
     date_key="DAY#{day}"
   )
   ```

**Database operations per scope/model**: 1 BatchGetItem + 1 PutItem

**Example**:
- 10 orgs × 3 models = 30 aggregations/minute
- 30 × (1 BatchGetItem + 1 PutItem) = 60 DynamoDB operations/minute
- ~86,400 operations/day = $0.22/month

---

### 4. Daily Aggregate API Query

**Endpoint**: `GET /orgs/{org_id}/aggregates/today`

**Steps:**
1. Load org config to get model_ordering and quotas
2. Read DailyTotal for each model in ordering:
   ```
   BatchGetItem: [
     DailyTotal(usage_key="ORG#{org_id}#LABEL#{label1}", date_key="DAY#{today}"),
     DailyTotal(usage_key="ORG#{org_id}#LABEL#{label2}", date_key="DAY#{today}"),
     ...
   ]
   ```
3. Compute quota percentages
4. Format response

**Database operations**: 1 GetItem (config) + 1 BatchGetItem (totals)

---

### 5. Token Validation (Per Authenticated Request)

**Frequency**: Every authenticated API request

**Steps:**
1. Extract JWT token from Authorization header
2. Verify JWT signature and expiry
3. Extract `jti` (JWT ID) from claims
4. Check if token revoked:
   ```
   GetItem: RevokedTokens(token_jti={jti})
   ```
5. If item exists, token is revoked → return 401
6. If item doesn't exist, token is valid → proceed

**Database operations**: 1 GetItem (cached for 30-60s for negative results)

**Performance optimization**:
- Cache "not revoked" results for 60 seconds
- Only uncached or positive results hit DynamoDB
- Reduces read cost by ~600× with caching

---

### 6. Credential Rotation

**Frequency**: Manual (recommended every 90 days) or on-demand

**Steps:**
1. Read existing config:
   ```
   GetItem: Config(org_key="ORG#{org_id}", resource_key="") or (resource_key="APP#{app_id}")
   ```
2. Generate new client_secret and hash with bcrypt
3. Update config with new secret and grace period:
   ```
   UpdateItem: Config
     SET client_secret_hash = :new_hash,
         client_secret_created_at_epoch = :now,
         client_secret_rotation_grace_expires_at_epoch = :grace_expiry
   ```
4. Return client_id and new client_secret directly in response

**Database operations**: 1 GetItem + 1 UpdateItem

**Grace period**: Old secret remains valid for configured hours (0-168)

**Note**: Rotation endpoints are not yet implemented.

---

## Quota Scope Determination

### Org-Level Scope

**Config**: `quota_scope: "ORG"`

**Scope computation:**
```
scope_type = "ORG"
scope_id = org_id
```

**All apps share quota**:
- App A and App B both contribute to org totals
- Quota checks read: `DailyTotal(usage_key="ORG#{org_id}#LABEL#{label}", date_key="DAY#{day}")`

---

### App-Level Scope

**Config**: `quota_scope: "APP"`

**Scope computation:**
```
scope_type = "APP"
scope_key_prefix = "ORG#{org_id}#APP#{app_id}"
```

**Each app has independent quota**:
- App A has separate totals from App B (within same org)
- Different orgs can have apps with same app_id (keys include org_id)
- Quota checks read: `DailyTotal(usage_key="ORG#{org_id}#APP#{app_id}#LABEL#{label}", date_key="DAY#{day}")`

---

## TTL Configuration

### StickyState TTL

**Expiration**: End of org-local day + 1 hour buffer

**Calculation:**
```
expires_at_epoch = midnight_tomorrow(org_timezone) + 3600
```

**Automatic cleanup**: DynamoDB deletes expired items within 48 hours

---

### PricingCache TTL

**Expiration**: 2-3 days after fetch

**Rationale**: Keep recent pricing for troubleshooting, auto-cleanup old data

---

### RevokedTokens TTL

**Expiration**: Matches original token expiry time

**Calculation:**
- Access tokens: `expires_at_epoch = original_expiry_epoch` (1 hour from issuance)
- Refresh tokens: `expires_at_epoch = original_expiry_epoch` (30 days from issuance)

**Rationale**: No need to track revoked tokens after they would naturally expire

**Automatic cleanup**: DynamoDB deletes expired items within 48 hours

---

### SecretRetrievalTokens TTL

**Expiration**: 10 minutes after creation

**Calculation:**
```
expires_at_epoch = created_at_epoch + 600
```

**Rationale**: Short-lived one-time tokens, cleanup quickly after use/expiry

**Automatic cleanup**: DynamoDB deletes expired items within 48 hours

---

## Shard Count Guidelines

Shard count is **immutable per org** - set at creation, cannot change without data migration.

**DynamoDB limits**:
- 3,000 RCU per partition (eventual consistency)
- 1,000 WCU per partition
- With atomic ADD operations, practical limit ~100 WCU/partition/second


---

## Cost Analysis (10 req/s workload)

> **COST DISCLAIMER**
>
> All cost estimates provided in this section are for **illustrative purposes only** and must be verified against current AWS pricing. Actual costs may vary significantly based on:
> - Usage patterns and traffic volume
> - AWS region
> - Current AWS pricing (subject to change)
> - Optimization strategies implemented
>
> **Always validate cost calculations with the latest AWS pricing information and conduct your own cost analysis before deployment.**

### Monthly DynamoDB Costs

| Component | Operations | Monthly Cost |
|-----------|-----------|--------------|
| **Reads** |
| Model selection (normal) | ~4.3M reads (config + daily total) | $1.08 |
| Model selection (tight) | Minimal (spike only) | $0.00 |
| Token revocation checks | 25.9M reads (per request) | $6.48 |
| Cost submission reads | 25.9M reads (DailyTotal for response) | $6.48 |
| Aggregator reads | 8 shards × 1,440/day × 30 = 345,600 | $0.09 |
| **Writes** |
| Cost submissions | 25.9M writes (UsageAggSharded) | $0.32 |
| Aggregator writes | 1,440/day × 30 = 43,200 | $0.00 |
| Token revocations | Minimal (~10/month) | $0.00 |
| **Storage** |
| ~0.5 GB + token tables | < $0.30 |
| **Total** | | **~$14.75** |

**Cost Optimization Note**:
- Token revocation checks can be cached for 30-60 seconds (negative results)
- With 60s cache: Reduces revocation checks by 600× → ~$0.01
- **Optimized Total with caching**: ~$8.27/month

### Lambda Costs (if aggregator runs in Lambda)

- 1,440 invocations/day × 30 = 43,200/month
- 500ms average duration, 128MB memory
- Cost: ~$0.50/month

**Total database infrastructure**:
- Without revocation check caching: ~$15.25/month
- With revocation check caching (recommended): ~$8.77/month

---

## Index Strategy

All access patterns use primary key lookups:
- Config: Direct org_key+resource_key access
- StickyState: Direct scope_key+date_key access
- UsageAggSharded: Direct shard_key+date_key access for writes
- DailyTotal: Direct usage_key+date_key access or BatchGetItem
- PricingCache: Direct model_id+price_key access


### Optional GSIs for Advanced Use Cases

#### UsageAggSharded GSI (Discovery)

**Purpose**: Enable aggregator to discover active scopes dynamically

**Design:**
- GSI partition key: `ACTIVE#{org_day}`
- GSI sort key: `{scope_type}#{scope_id}#LABEL#{label}`

**Use case**: Aggregator queries to find which scopes have data to aggregate

**Alternative**: Maintain in-memory list of active scopes (simpler, recommended)

---

## Data Retention

### Automatic Cleanup (TTL)

- **StickyState**: Deleted at end of org-local day + buffer
- **PricingCache**: Deleted 2-3 days after fetch

### Manual Cleanup (DynamoDB Streams + Lambda)

**For long-term retention:**
1. Enable DynamoDB Streams on UsageAggSharded and DailyTotal
2. Lambda exports to S3 (daily snapshots)
3. TTL deletes from DynamoDB after 30-90 days
4. Historical analysis from S3 via Athena

---

## Multi-Instance Safety

### No Coordination Required

All operations are safe with multiple concurrent service instances:

1. **Cost submissions**: Atomic ADD on sharded counters
2. **Sticky state flips**: Conditional writes (first writer wins)
3. **Aggregator**: Idempotent PutItem overwrites
4. **Model selection**: Read-only operations

### Race Conditions Handled

**Scenario**: Multiple instances detect quota exceeded simultaneously

**Handling**:
```
UpdateItem: StickyState
  ConditionExpression: "attribute_not_exists(active_model_label) OR active_model_index < :new_index"
```

- First writer wins, sets sticky state
- Other instances get `ConditionalCheckFailedException`
- Other instances retry read and see updated sticky state
- System converges on same model within seconds

---

## Migration Considerations

### Adding New Models

1. Add label to main config.yaml
2. Update org configs with new label in model_ordering
3. Set quota for new model label
4. No database schema changes required

### Changing Shard Count

**Not supported** - Shard count is immutable per org

**Workaround**:
1. Create new org with higher shard count
2. Migrate app registrations
3. Historical data remains in old org partition

**Rationale**: Resharding would require rewriting all UsageAggSharded keys

---

## Monitoring & Observability

### DynamoDB Metrics

- **ConsumedReadCapacityUnits**: Track quota check costs
- **ConsumedWriteCapacityUnits**: Track cost submission rate
- **ThrottledRequests**: Should be zero (capacity planning)
- **UserErrors**: Track conditional write failures (sticky state)

### Custom Metrics

- Aggregator lag: Time between cost submission and DailyTotal update (target: < 60s)
- Quota proximity: How close scopes are to thresholds
- Sticky flip rate: How often fallback chains activate
- Token revocation rate: Frequency of token revocations
- Revocation check cache hit rate: Effectiveness of caching strategy

---

