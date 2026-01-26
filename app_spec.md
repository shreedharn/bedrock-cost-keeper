# Bedrock Price Keeper System - Application Specification

## Overview

The Bedrock Price Keeper is an independent REST service that helps applications manage Amazon Bedrock model costs through intelligent model selection based on daily spend quotas. The system supports multiple models with configurable fallback chains, operates at organization or application scope, and provides eventual consistency guarantees.

**Key Characteristics:**
- REST service deployed on AWS ECS Fargate
- Advisory system (helper, not enforcer)
- Client-driven quota checking
- Supports N models with label-based configuration
- Eventually consistent by design

---

## Core Concepts

### Organization & Application Hierarchy

- **Organization (Org)**: Top-level entity with timezone, model preferences, and quotas
- **Application (App)**: Service or workload within an org that makes Bedrock inference calls
- **Scope**: Quotas can be applied at either:
  - **ORG level**: All apps share organization-wide quota
  - **APP level**: Each app has independent quota

### Model Labels

Models are referenced by **labels** (e.g., `premium`, `standard`, `economy`) rather than specific Bedrock model IDs. This abstraction allows:
- Consistent naming across organizations
- Model upgrades without config changes
- Different model selections per organization

**Example mapping:**
```
premium  → anthropic.claude-opus-4-5-20251101-v1:0
standard → anthropic.claude-sonnet-4-5-20250929-v1:0
economy  → anthropic.claude-haiku-4-5-20251001-v1:0
```

### Fallback Chain

Each org or app defines a **model ordering** that specifies the fallback sequence:
1. Start with first model in ordering (e.g., `premium`)
2. When quota exceeded, fall back to next model (e.g., `standard`)
3. Continue down chain until all quotas exhausted
4. Return quota-exceeded error when no models available

---

## Configuration Architecture

### Two-Tier Configuration System

#### 1. Main Configuration (`config.yaml`)

Global configuration defining:
- Model label to Bedrock ID mappings
- Default pricing (fallback if pricing API unavailable)
- System-wide defaults (shard count, thresholds)
- REST API settings

**Location**: Packaged with service deployment, version-controlled

#### 2. Organization Configuration (`config_<org_name>.yaml`)

Per-organization customization:
- Timezone
- Model ordering (references labels from main config)
- Daily quotas per model label
- App-specific overrides
- Threshold customization

**Loading**: Initially loaded via script, stored in DynamoDB

**Configuration Hierarchy:**
```
config.yaml (global)
  └─ model labels defined
  └─ system defaults

config_<org_name>.yaml (per-org)
  └─ org-level settings
      ├─ model_ordering
      ├─ quotas
      └─ overrides
  └─ app-level overrides (optional)
      ├─ model_ordering
      ├─ quotas
      └─ threshold overrides
```

---

## Quota & Time Semantics

### Daily Quotas

- **Time-based**: Reset at midnight in organization's configured timezone
- **Currency**: Specified in micro-USD (1 USD = 1,000,000 micro-USD)
- **Per model**: Each model label has independent daily quota
- **Scope options**:
  - **ORG scope**: All apps share organization quota
  - **APP scope**: Each app has independent quota
- **Overruns**: Expected and acceptable due to eventual consistency

### Quota Reset Logic

- Daily boundary determined by org timezone
- Quotas reset at midnight local time
- Sticky fallback state cleared at midnight
- New day begins with first model in ordering

---

## Operating Modes

### Normal Mode (< tight_mode threshold)

**When**: Current spend < 95% of quota (configurable)

**Client Behavior:**
- Uses previously determined model
- Load and cache model pricing for cost calculation
- Asynchronous cost submission
- During cost submission get the calculated DailyTotal from the Price Keeper service
- Periodic model selection checks (e.g., every 5 minutes) to detect quota exceeded states


### Tight Mode (≥ tight_mode threshold)

**When**: Current spend ≥ 95% of quota for current model

**Client Behavior:**
- More frequent periodic model selection checks (e.g., every 60 seconds vs ~5 minutes in normal mode)
- Increased quota awareness near limits
- Continues until threshold drops after new model switch or day resets

**Service Behavior:**
- Sticky fallback activation when quota exceeded
- Returns next available model in ordering

**Threshold Configuration:**
- Default: 95%
- Overridable at org level in `config_<org_name>.yaml`
- Overridable per app in app-specific config

---

## Sticky Fallback Behavior

**Purpose**: Prevent oscillation between models when quota boundary reached

**Mechanism:**
1. When model quota exceeded, system activates next model in fallback chain
2. Sticky state recorded in database for current org-local day
3. All subsequent requests use fallback model for remainder of day
4. State clears at midnight (org timezone)

**Example:**
```
Model ordering: [premium, standard, economy]
Daily quotas: {premium: $10, standard: $5, economy: $2}

Time 10:00 AM: Using premium ($9.50 spent)
Time 10:30 AM: Premium quota exceeded → sticky flip to standard
Time 11:00 AM - 11:59 PM: All requests use standard
Time 12:00 AM: Reset to premium
```

**Configurability**: Can be disabled in main config (`sticky_fallback_enabled: false`)

---

## Pricing & Cost Computation

### Pricing Management

**Source**: Bedrock Pricing API
- Fetched on service startup
- Refreshed once per day
- Fallback to `default_pricing` in config.yaml if API unavailable

**Not checked before inference**: Client makes direct Bedrock calls

**Cost computation timing:**
- After Bedrock response received
- Based on input_tokens and output_tokens returned
- Formula: `cost = (input_tokens × input_price) + (output_tokens × output_price)`

**Pricing updates**: Not retroactive; each request uses pricing version at time of call

---

## REST API Specification

Refer [API Spec](./api_spec.md)
---

## Client Integration Flow

### Initialization

1. Application starts
2. Calls `GET /model-selection` to get initial model
3. Caches model recommendation and pricing
4. Begins making Bedrock inference calls

### Normal Request Flow

**Client learns mode status from DailyTotal in POST /costs response**

```
┌─────────────────────────────────────────────────┐
│ Client Application (NORMAL mode)               │
└──────────┬──────────────────────────────────────┘
           │
           ▼
   ┌───────────────────────────────┐
   │ Use cached model              │
   │ (from initialization)         │
   └────────┬──────────────────────┘
            │
            ▼
   ┌─────────────────────────────────┐
   │ Call Bedrock with cached model  │
   └────────┬────────────────────────┘
            │
            ▼
   ┌──────────────────────────────┐
   │ Calculate cost locally       │
   │ using cached pricing         │
   └────────┬─────────────────────┘
            │
            ▼
   ┌──────────────────────────────────────────┐
   │ POST /costs (async)                      │
   │   - Submits: cost, tokens, model_label   │
   │   - Receives: DailyTotal with mode info  │
   └────────┬─────────────────────────────────┘
            │
            ▼
   ┌──────────────────────────────────────┐
   │ Check mode in response               │
   │ If TIGHT mode reached → adjust flow  │
   └──────────────────────────────────────┘

   Periodic Background Task (every ~5 mins in NORMAL mode):
   ┌────────────────────────────────────────────────┐
   │ GET /model-selection                           │
   │   - Detect quota exceeded after low activity   │
   │   - Update cached model if fallback occurred   │
   │   - Detect TIGHT mode transition               │
   └────────────────────────────────────────────────┘
```

### Tight Mode Flow

**Client detects TIGHT mode from DailyTotal response, then starts periodic model checks**

```
┌─────────────────────────────────────────────────┐
│ TIGHT mode detected (quota ≥ 95%)              │
│ Client begins periodic model selection checks  │
└──────────┬──────────────────────────────────────┘
           │
           ▼
   ┌───────────────────────────────────────┐
   │ Use cached model                      │
   │ (may be fallback model after switch)  │
   └────────┬──────────────────────────────┘
            │
            ▼
   ┌─────────────────────────────────┐
   │ Call Bedrock with cached model  │
   └────────┬────────────────────────┘
            │
            ▼
   ┌──────────────────────────────┐
   │ Calculate cost locally       │
   └────────┬─────────────────────┘
            │
            ▼
   ┌──────────────────────────────────────────┐
   │ POST /costs (async)                      │
   │   - Submits: cost, tokens, model_label   │
   │   - Receives: DailyTotal with mode info  │
   └──────────────────────────────────────────┘

   Periodic Background Task (every 60s in TIGHT mode):
   ┌────────────────────────────────────────────┐
   │ GET /model-selection                       │
   │   - Check for model fallback/switch        │
   │   - Update cached model if changed         │
   │   - Exit TIGHT mode if quota drops < 95%   │
   └────────────────────────────────────────────┘
```

---

## Service Architecture

### Deployment

- **Platform**: AWS ECS Fargate
- **Stateless**: No in-process state beyond caches
- **Horizontal scaling**: Multiple tasks behind load balancer
- **Database**: Amazon DynamoDB (see db_spec.md)

### Background Processes

#### 1. Aggregator Process

**Purpose**: Prevent hot partitions by consolidating distributed counters

**Schedule**: Every 30-60 seconds

**Operation:**
1. Read N sharded usage counters from DynamoDB
2. Sum totals in-memory
3. Write consolidated daily totals (single item per scope/model)

**Critical**: Converts high-frequency distributed writes into low-frequency aggregated updates

---

#### 2. Pricing Refresh Process

**Purpose**: Keep pricing data current

**Schedule**: Once per day (e.g., 8 AM UTC)

**Operation:**
1. Fetch current pricing from Bedrock API
2. Update PricingCache table
3. Invalidate in-memory pricing cache
4. Log pricing changes

**Fallback**: Use `default_pricing` from config.yaml if API unavailable

---

#### 3. Quota Monitor Process

**Purpose**: Track quota proximity and update recommendations

**Schedule**: Continuous (event-driven or polling)

**Operation:**
1. Monitor DailyTotal updates
2. Calculate quota percentages
3. Trigger mode transitions (NORMAL ↔ TIGHT)
4. Update StickyState when quotas exceeded

---

## Error Handling

### Quota Exceeded

**Condition**: All models in fallback chain exceeded their quotas

**Response:** `429 Too Many Requests`
```json
{
  "error": "QUOTA_EXCEEDED",
  "message": "All model quotas exceeded for today",
  "retry_after": "2026-01-24T05:00:00Z",
  "models": {
    "premium": {"quota_pct": 102.5, "exceeded": true},
    "standard": {"quota_pct": 108.3, "exceeded": true},
    "economy": {"quota_pct": 101.2, "exceeded": true}
  }
}
```

### Unknown Org or App

**Response:** `404 Not Found`
```json
{
  "error": "NOT_FOUND",
  "message": "Organization or application not registered",
  "hint": "Call POST /orgs/{org_id}/register first"
}
```

### Invalid Configuration

**Response:** `400 Bad Request`
```json
{
  "error": "INVALID_CONFIG",
  "message": "Model label 'unknown_label' not defined in main config",
  "valid_labels": ["premium", "standard", "economy"]
}
```

---

## Observability & Monitoring

### Metrics (Future Dashboard)

Applications and organizations can query:
- **Token usage**: Input/output tokens per model
- **Cost usage**: Current spend vs. quota
- **Remaining quota**: Available spend per model
- **Request counts**: Number of requests per model
- **Fallback events**: When and why fallbacks occurred

### Logging

Service logs:
- Model selection decisions
- Quota threshold crossings
- Fallback activations
- Configuration changes
- Pricing updates
- Error conditions

---

## Consistency Guarantees

### Eventually Consistent by Design

**Aggregation lag**: 30-60 seconds
- Cost submissions are async
- Aggregator runs periodically
- Quota checks read slightly stale data

**Acceptable overruns**: System allows quota overruns due to:
- Aggregation lag
- Multiple concurrent clients
- Network delays
- Client-side caching

**Typical overrun**: < 5% of quota in high-traffic scenarios

**Mitigation**: Set quotas with buffer (e.g., 10% below hard limit)

---

## Configuration Management

### Initial Setup

1. Define model labels in main `config.yaml`
2. Create per-org `config_<org_name>.yaml` files
3. Run loader script to populate DynamoDB:
   ```bash
   ./scripts/load_config.sh config_acme_corp.yaml
   ```
4. Verify via API:
   ```bash
   curl https://price-keeper.us-east-1.amazonaws.com/api/v1/orgs/{org_id}/config
   ```

### Runtime Updates

Configuration changes:
- **Model label mappings**: Requires service redeployment (main config)
- **Org quotas/ordering**: Update via DynamoDB or re-run loader script
- **App overrides**: Update via DynamoDB or management API

**Note**: Config changes take effect within aggregation interval (30-60s)

---

## Scalability Considerations

### Shard Count Configuration

Sharded counters prevent hot partitions. Shard count determined by traffic:

| Peak Traffic    | Recommended Shards | Growth Headroom |
|----------------|--------------------|-----------------|
| < 50 req/s     | 8                  | 40x growth      |
| 50-200 req/s   | 16                 | 20x growth      |
| 200-500 req/s  | 32                 | 10x growth      |
| > 500 req/s    | 64                 | 5x growth       |

**Configuration**: Set in `config_<org_name>.yaml` under `overrides.agg_shard_count`

**Important**: Shard count immutable per org (set at creation)

---

## Cost Estimation

### DynamoDB Costs (10 req/s workload)

| Component          | Operations           | Monthly Cost |
|--------------------|---------------------|--------------|
| Aggregator reads   | 8 shards × 43,200   | $0.09        |
| Quota checks       | ~4.3M reads         | $1.08        |
| Cost submissions   | ~25.9M writes       | $0.32        |
| Storage           | < 1 GB              | < $0.25      |
| **Total DynamoDB** |                     | **~$1.74**   |

### ECS Fargate Costs

- 0.25 vCPU, 0.5 GB memory: ~$8/month per task
- Typical deployment: 2 tasks (HA) = **$16/month**

**Total system cost**: ~$18/month for 10 req/s workload

---

## Security Considerations

### Authentication

- API requires AWS Signature V4 authentication
- Org/App identifiers in path prevent cross-tenant access
- IAM policies restrict access per organization

### Data Privacy

- No prompt/response content stored
- Only metadata: tokens, cost, model used
- TTL-based data retention (configurable)

### Rate Limiting

- Per-client rate limits on all endpoints
- Prevents single client from overwhelming service
- Configured in main config.yaml

---

## Summary

The Bedrock Price Keeper is a **client-driven, eventually consistent, REST-based** metering service that:

✅ Supports N models with label-based configuration
✅ Operates at organization or application scope
✅ Provides intelligent fallback chains
✅ Prevents hot DynamoDB partitions through sharding
✅ Scales horizontally on ECS Fargate
✅ Offers simple REST API for integration
✅ Maintains cost efficiency (~$18/month at 10 req/s)
✅ Provides eventual consistency with acceptable overrun

The service acts as a **helper, not enforcer**, allowing applications to make informed model selection decisions while maintaining quota awareness.
