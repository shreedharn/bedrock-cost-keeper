# DynamoDB Schema Specification - Bedrock Price Keeper

## Overview

This database design supports the Bedrock Price Keeper REST service with the following characteristics:

- **N models** with label-based configuration (not limited to 2 models)
- **Org and App scoping** (not user-based)
- **Sticky fallback** through ordered model chains
- **Post-response metering** with eventual consistency
- **No hot partitions** through sharding and careful access patterns

---

## Design Principles

### Anti-Hot-Partition Techniques

1. **Distributed writes**: Cost data distributed across N sharded counters
2. **Aggregated reads**: Single consolidated item for quota checks
3. **Controlled cadence**: Background aggregator updates totals every 60s
4. **Request-centric partitions**: Random UUIDs prevent write concentration

### Cost Optimization

- Read 1 item for quota checks (not N shards)
- Atomic DynamoDB ADD operations
- TTL-based automatic cleanup
- Minimal index overhead

**Target cost**: ~$1.74/month for 10 req/s workload

---

## Table Summary

| Table | Purpose | Write Pattern | Hot Partition Risk |
|-------|---------|---------------|-------------------|
| **Config** | Org/app settings + credentials | Low (admin updates) | ✅ None |
| **StickyState** | Fallback tracking | Once per day per scope/model | ✅ None |
| **UsageAggSharded** | Distributed counters | Per-request (8-64 shards) | ✅ None (sharded) |
| **DailyTotal** | Aggregated totals | Every 60s (by aggregator) | ✅ None (controlled cadence) |
| **PricingCache** | Bedrock pricing | Once per day | ✅ None |
| **RevokedTokens** | Token revocation list | Rare (on revoke) | ✅ None |
| **SecretRetrievalTokens** | One-time secret tokens | Rare (on registration/rotation) | ✅ None |

---

## Table Schemas

### 1. Config Table

**Purpose**: Store organization and application configuration

**Hierarchy**:
- Org-level: Default settings for all apps
- App-level: Overrides for specific applications

#### Primary Key

- **PK** (string): `ORG#{org_id}`
- **SK** (string): `""` (empty) for org config, or `APP#{app_id}` for app config

#### Access Patterns

1. Get org config: `GetItem(PK="ORG#{org_id}", SK="")`
2. Get app config: `GetItem(PK="ORG#{org_id}", SK="APP#{app_id}")`
3. List all apps for org: `Query(PK="ORG#{org_id}", SK begins_with "APP#")`

#### Org Config Item

**Key:**
```
PK: "ORG#550e8400-e29b-41d4-a716-446655440000"
SK: ""
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
  "PK": "ORG#550e8400-e29b-41d4-a716-446655440000",
  "SK": "",
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
PK: "ORG#550e8400-e29b-41d4-a716-446655440000"
SK: "APP#app-production-api"
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
  "PK": "ORG#550e8400-e29b-41d4-a716-446655440000",
  "SK": "APP#app-production-api",
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

---

### 2. StickyState Table

**Purpose**: Track sticky fallback decisions for each scope/day/model

**Note**: Only required if `sticky_fallback_enabled: true`

#### Primary Key

- **PK** (string): Scope identifier (org or org+app)
- **SK** (string): `DAY#{day}` for time-series organization

#### Key Patterns

**Org-scoped:**
```
PK: "ORG#550e8400-e29b-41d4-a716-446655440000"
SK: "DAY#20260123"
```

**App-scoped:**
```
PK: "ORG#550e8400-e29b-41d4-a716-446655440000#APP#app-production-api"
SK: "DAY#20260123"
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
  "PK": "ORG#550e8400-e29b-41d4-a716-446655440000",
  "SK": "DAY#20260123",
  "active_model_label": "standard",
  "active_model_index": 1,
  "reason": "QUOTA_EXCEEDED",
  "previous_model_label": "premium",
  "activated_at_epoch": 1737640800,
  "expires_at_epoch": 1737676800
}
```

#### Access Pattern

- **Check sticky state**: `GetItem(PK={scope}, SK="DAY#{day}")`
- **Set sticky state**: `PutItem(PK={scope}, SK="DAY#{day}", ...)` with conditional expression:
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

- **PK** (string): Scope + model label + shard identifier
- **SK** (string): `DAY#{day}` for time-series organization

#### Key Patterns

**Org-scoped, Model "premium", Shard 0:**
```
PK: "ORG#550e8400-e29b-41d4-a716-446655440000#LABEL#premium#SH#0"
SK: "DAY#20260123"
```

**App-scoped, Model "standard", Shard 3:**
```
PK: "ORG#550e8400-e29b-41d4-a716-446655440000#APP#app-production-api#LABEL#standard#SH#3"
SK: "DAY#20260123"
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
  "PK": "ORG#550e8400-e29b-41d4-a716-446655440000#LABEL#premium#SH#0",
  "SK": "DAY#20260123",
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
    PK = "{scope}#LABEL#{label}#SH#{shard_id}"
    SK = "DAY#{day}"
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

- **PK** (string): Scope + model label identifier
- **SK** (string): `DAY#{day}` for time-series organization

#### Key Patterns

**Org-scoped, Model "premium":**
```
PK: "ORG#550e8400-e29b-41d4-a716-446655440000#LABEL#premium"
SK: "DAY#20260123"
```

**App-scoped, Model "standard":**
```
PK: "ORG#550e8400-e29b-41d4-a716-446655440000#APP#app-production-api#LABEL#standard"
SK: "DAY#20260123"
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
  "PK": "ORG#550e8400-e29b-41d4-a716-446655440000#LABEL#premium",
  "SK": "DAY#20260123",
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
    PK = "{scope}#LABEL#{label}"
    SK = "DAY#{today}"
  Returns: cost_usd_micros (compare to quota)
```

**Model selection (check all models in ordering):**
```
BatchGetItem:
  Keys: [
    {PK = "{scope}#LABEL#{label1}", SK = "DAY#{today}"},
    {PK = "{scope}#LABEL#{label2}", SK = "DAY#{today}"},
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
       {PK = "{scope}#LABEL#{label}#SH#0", SK = "DAY#{day}"},
       {PK = "{scope}#LABEL#{label}#SH#1", SK = "DAY#{day}"},
       ...
       {PK = "{scope}#LABEL#{label}#SH#N-1", SK = "DAY#{day}"}
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
       PK = "{scope}#LABEL#{label}"
       SK = "DAY#{day}"
     Item: {aggregated totals}
   ```

**Why this prevents hot partitions:**
- `DailyTotal` receives only 1-2 writes/minute (not per-request)
- Even with 100 concurrent service instances, write rate stays low
- Controlled by aggregator schedule, not request volume

**Benefits of time-series design (DAY as sort key):**
- Enables efficient historical queries via Query operations
- All days for a scope logically grouped under one partition key
- Follows DynamoDB time-series best practices
- No performance impact on current operations (GetItem still single-item lookup)
- Future analytics: `Query(PK, SK BETWEEN "DAY#20260101" AND "DAY#20260130")`

---

### 5. PricingCache Table

**Purpose**: Cache Bedrock pricing to avoid repeated API calls

#### Primary Key

- **PK** (string): `{bedrock_model_id}`
- **SK** (string): `{yyyy-mm-dd}`

#### Key Pattern

```
PK: "anthropic.claude-3-5-sonnet-20241022-v2:0"
SK: "2026-01-23"
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
  "PK": "anthropic.claude-3-5-sonnet-20241022-v2:0",
  "SK": "2026-01-23",
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

- **Get today's pricing**: `GetItem(PK={model_id}, SK={today})`
- **Write pricing**: `PutItem` once per day by pricing refresh process

**Fallback**: If pricing not found, use `default_pricing` from config.yaml

---

### 6. RevokedTokens Table

**Purpose**: Track revoked JWT tokens to prevent their use before natural expiry

**Note**: Required for token revocation API endpoint

#### Primary Key

- **PK** (string): `{token_jti}` (JWT ID claim from token)
- No SK (single item per token)

#### Key Pattern

```
PK: "550e8400-e29b-41d4-a716-446655440000-1737640800"
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
  "PK": "550e8400-e29b-41d4-a716-446655440000-1737640800",
  "token_type": "refresh",
  "client_id": "org-550e8400-e29b-41d4-a716-446655440000-app-app-production-api",
  "revoked_at_epoch": 1737640800,
  "original_expiry_epoch": 1740232800,
  "expires_at_epoch": 1740232800
}
```

#### Access Pattern

- **Check if token revoked**: `GetItem(PK={token_jti})`
  - If item exists, token is revoked
  - If item doesn't exist, token is valid (not revoked)
- **Revoke token**: `PutItem(PK, ...)` with TTL matching token expiry

**Performance Note**:
- Check happens on every authenticated request
- DynamoDB GetItem is fast (~5-10ms)
- Consider caching negative results (token NOT revoked) for 30-60 seconds

**TTL Cleanup**: Revoked tokens auto-deleted after original expiry time

---

### 7. SecretRetrievalTokens Table

**Purpose**: Store one-time tokens for secure secret retrieval after registration/rotation

**Security**: Tokens expire after 10 minutes or first use

#### Primary Key

- **PK** (string): `{token_uuid}`
- No SK (single item per token)

#### Key Pattern

```
PK: "7c9e6679-7425-40de-944b-e07fc1f90ae7"
```

#### Attributes

- `org_id` (string)
- `app_id` (string, optional - omitted for org-level tokens)
- `secret_type` (string: `"org"` | `"app"`)
- `client_id` (string: the client_id this secret belongs to)
- `created_at_epoch` (number)
- `expires_at_epoch` (number, TTL attribute - created + 600 seconds)
- `used` (boolean, default: `false`)
- `used_at_epoch` (number, optional - set when retrieved)

**Example:**
```json
{
  "PK": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
  "org_id": "550e8400-e29b-41d4-a716-446655440000",
  "app_id": "app-production-api",
  "secret_type": "app",
  "client_id": "org-550e8400-e29b-41d4-a716-446655440000-app-app-production-api",
  "created_at_epoch": 1737640800,
  "expires_at_epoch": 1737641400,
  "used": false
}
```

#### Access Pattern

- **Check token validity**: `GetItem(PK={token_uuid})`
  - Verify `expires_at_epoch > now`
  - Verify `used == false`
- **Mark token as used**: `UpdateItem` with condition:
  ```
  ConditionExpression: "used = :false AND expires_at_epoch > :now"
  UpdateExpression: "SET used = :true, used_at_epoch = :timestamp"
  ```
  - First use wins (prevents replay)
  - Expired tokens fail condition
- **Cleanup**: DynamoDB TTL deletes after expiry

**Security Notes**:
- Token is cryptographically random UUID
- Single-use prevents replay attacks
- 10-minute expiry window limits exposure
- Returned secret should be transmitted over TLS only

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
   GetItem: StickyState(PK="{scope}", SK="DAY#{day}")
   ```
4. If sticky state exists, use `active_model_label`
5. Otherwise, read totals for all models in ordering:
   ```
   BatchGetItem: [
     DailyTotal(PK="{scope}#LABEL#{label1}", SK="DAY#{day}"),
     DailyTotal(PK="{scope}#LABEL#{label2}", SK="DAY#{day}"),
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
     PK="{scope}#LABEL#{label}#SH#{shard_id}",
     SK="DAY#{day}",
     ADD cost_usd_micros :c, input_tokens :i, output_tokens :o, requests :r
     ADD request_ids (set): :request_id
     SET updated_at_epoch = :t
   )
   ```
5. Read current DailyTotal to return in response:
   ```
   GetItem: DailyTotal(
     PK="{scope}#LABEL#{label}",
     SK="DAY#{day}"
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
     {PK="{scope}#LABEL#{label}#SH#0", SK="DAY#{day}"},
     {PK="{scope}#LABEL#{label}#SH#1", SK="DAY#{day}"},
     ...
   ]
   ```

2. **Sum totals in-memory**

3. **Write consolidated total:**
   ```
   PutItem: DailyTotal(
     PK="{scope}#LABEL#{label}",
     SK="DAY#{day}"
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
     DailyTotal(PK="ORG#{org_id}#LABEL#{label1}", SK="DAY#{today}"),
     DailyTotal(PK="ORG#{org_id}#LABEL#{label2}", SK="DAY#{today}"),
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
   GetItem: RevokedTokens(PK={jti})
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
   GetItem: Config(PK="ORG#{org_id}", SK="") or (SK="APP#{app_id}")
   ```
2. Generate new client_secret and hash with bcrypt
3. Create secret retrieval token (UUID)
4. Update config with new secret and grace period:
   ```
   UpdateItem: Config
     SET client_secret_hash = :new_hash,
         client_secret_created_at_epoch = :now,
         client_secret_rotation_grace_expires_at_epoch = :grace_expiry
   ```
5. Store retrieval token:
   ```
   PutItem: SecretRetrievalTokens(PK={token_uuid}, ...)
   ```
6. Return retrieval token to admin

**Database operations**: 1 GetItem + 1 UpdateItem + 1 PutItem

**Grace period**: Old secret remains valid for configured hours (0-168)

---

### 7. Secret Retrieval (One-Time)

**Frequency**: Once per registration/rotation

**Steps:**
1. Validate retrieval token:
   ```
   GetItem: SecretRetrievalTokens(PK={token_uuid})
   ```
2. Verify token not expired and not used
3. Mark token as used (with condition):
   ```
   UpdateItem: SecretRetrievalTokens
     ConditionExpression: "used = :false AND expires_at_epoch > :now"
     UpdateExpression: "SET used = :true, used_at_epoch = :timestamp"
   ```
4. Read config to get client credentials:
   ```
   GetItem: Config(PK="ORG#{org_id}", SK="") or (SK="APP#{app_id}")
   ```
5. Return client_id and client_secret in response

**Database operations**: 1 GetItem + 1 UpdateItem (conditional) + 1 GetItem

**Security**: First use wins (prevents replay), 10-minute expiry window

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
- Quota checks read: `DailyTotal(PK="ORG#{org_id}#LABEL#{label}", SK="DAY#{day}")`

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
- Quota checks read: `DailyTotal(PK="ORG#{org_id}#APP#{app_id}#LABEL#{label}", SK="DAY#{day}")`

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

| Peak Traffic | Recommended Shards | Max Throughput per Shard |
|-------------|-------------------|------------------------|
| < 50 req/s  | 8                 | ~6 req/s               |
| 50-200 req/s | 16                | ~12 req/s              |
| 200-500 req/s | 32               | ~15 req/s              |
| > 500 req/s | 64                | ~8 req/s               |

**DynamoDB limits**:
- 3,000 RCU per partition (eventual consistency)
- 1,000 WCU per partition
- With atomic ADD operations, practical limit ~100 WCU/partition/second

**Safety margin**: Recommend shards that keep per-shard write rate < 50 WCU/second

---

## Cost Analysis (10 req/s workload)

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
| Secret retrievals | Minimal (~20/month) | $0.00 |
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

### No GSIs Required for Core Functionality

All access patterns use primary key lookups:
- Config: Direct PK+SK access
- StickyState: Direct PK access
- UsageAggSharded: Direct PK access for writes
- DailyTotal: Direct PK access or BatchGetItem
- PricingCache: Direct PK+SK access

**Benefit**:
- ✅ Lower write costs (no GSI maintenance)
- ✅ Simpler schema
- ✅ Faster writes

### Optional GSIs for Advanced Use Cases

#### UsageAggSharded GSI (Discovery)

**Purpose**: Enable aggregator to discover active scopes dynamically

**Design:**
- GSI PK: `ACTIVE#{org_day}`
- GSI SK: `{scope_type}#{scope_id}#LABEL#{label}`

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

## Performance Characteristics

### Latency Targets

| Operation | Target Latency | DynamoDB Operations |
|-----------|---------------|-------------------|
| Token validation | < 20ms | 1 GetItem (RevokedTokens check, cacheable) |
| Model selection | < 120ms | 1 GetItem (revoke check) + 1 GetItem (sticky) + 1 BatchGetItem (totals) |
| Cost submission | < 75ms | 1 GetItem (revoke check) + 1 UpdateItem (counter) + 1 GetItem (DailyTotal) |
| Daily aggregate query | < 220ms | 1 GetItem (revoke check) + 1 GetItem (config) + 1 BatchGetItem (totals) |
| Secret retrieval | < 100ms | 1 GetItem (token) + 1 UpdateItem (mark used) + 1 GetItem (config) |

### Throughput Limits

**Per org/app:**
- Cost submissions: ~5,000 req/s (limited by shard count)
- Model selection: ~10,000 req/s (read-heavy, cacheable)

**System-wide:**
- Unlimited (horizontally scalable via ECS tasks)

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
- Secret retrieval token usage: Track token generation and consumption
- Failed secret retrievals: Monitor expired or reused tokens

---

## Summary

This DynamoDB schema provides:

✅ **Scalable writes**: Distributed across N sharded counters
✅ **Efficient reads**: Single item for quota checks via aggregation
✅ **No hot partitions**: Sharding + controlled update cadence
✅ **Multi-instance safe**: Atomic operations, no coordination needed
✅ **Cost efficient**: ~$8.77/month for 10 req/s workload (with caching)
✅ **N-model support**: Label-based keys, unlimited model count
✅ **Org/App scoping**: Flexible hierarchy without user complexity
✅ **Eventual consistency**: Acceptable 60s aggregation lag
✅ **Security**: JWT token revocation, credential rotation, one-time secret retrieval
✅ **Idempotency**: Request deduplication via DynamoDB sets or separate table
✅ **Real-time feedback**: Cost submissions return current DailyTotal for mode detection
