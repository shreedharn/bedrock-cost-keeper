# Bedrock Cost Keeper - AI Context Guide

## Project Overview
A REST service for managing Amazon Bedrock costs through quota-aware model selection and usage tracking. Client-driven, eventually consistent architecture that recommends fallback models when daily quotas are exceeded.

## Core Concepts
- **Label-based models**: Models referenced by labels (premium/standard/economy) not IDs
- **Fallback chains**: Ordered model sequences with sticky fallback behavior
- **Quota scoping**: ORG-level (shared) or APP-level (independent) quotas
- **Eventual consistency**: Accepts <5% quota overruns for horizontal scalability
- **Server-side cost calculation**: Service calculates costs from tokens, not client

## Technology Stack
- **Runtime**: Python 3.12+, FastAPI
- **Database**: DynamoDB (sharded counters pattern)
- **Deployment**: AWS ECS Fargate, ALB, CloudFormation
- **Auth**: OAuth2 JWT (access + refresh tokens)
- **Testing**: pytest, DynamoDB Local

## Directory Structure
```
bedrock_metering/
├── src/                    # Application code
│   ├── api/               # FastAPI endpoints
│   ├── models/            # Data models
│   ├── services/          # Business logic
│   └── utils/             # Utilities
├── tests/                 # Unit/integration/API tests
├── cloudformation/        # IaC templates
├── deployment/            # Dockerfile, scripts
├── test-client/           # E2E test client
├── docs/                  # Specifications
│   ├── app_spec.md       # Architecture & client flows
│   ├── api_spec.md       # REST API reference
│   ├── db_spec.md        # DynamoDB schema
│   └── deployment.md     # Deployment guide
├── config.yaml            # Service config (model labels, defaults)
└── run.py                 # Entry point
```

## Key Specifications

### Application Spec (`docs/app_spec.md`)
- **Purpose**: System architecture, operating modes (NORMAL/TIGHT), client integration flows
- **Key sections**: Configuration hierarchy, quota semantics, sticky fallback, pricing/cost computation
- **Look here for**: How the system works, client behavior, integration patterns

### API Spec (`docs/api_spec.md`)
- **Purpose**: Complete REST API documentation with examples
- **Key sections**: Authentication (JWT), provisioning, model selection, usage submission, inference profiles
- **Look here for**: Endpoint contracts, request/response formats, error codes, rate limits

### Database Spec (`docs/db_spec.md`)
- **Purpose**: DynamoDB schema design and access patterns
- **Key sections**: 7 tables (Config, StickyState, UsageAggSharded, DailyTotal, PricingCache, RevokedTokens, SecretRetrievalTokens)
- **Look here for**: Data model, partition keys, sharding strategy, TTL configuration, cost analysis

### README.md
- **Purpose**: Quick start and overview
- **Look here for**: Setup instructions, usage examples, project context

## Critical Design Patterns

### Anti-Hot-Partition (DynamoDB)
- UsageAggSharded: N shards per scope/model (hash-based distribution)
- DailyTotal: Aggregator consolidates shards every 60s
- Read 1 item for quota checks (not N shards)

### Authentication Flow
1. POST /auth/token (client credentials) → access + refresh tokens
2. Use access token (1hr) in Authorization header
3. POST /auth/refresh before expiry → new access token
4. Revocation check via RevokedTokens table

### Cost Submission Flow
1. Client calls Bedrock, gets token counts
2. POST /usage with tokens only (no cost)
3. Service calculates cost using pricing from config.yaml/PricingCache
4. Updates UsageAggSharded (sharded counter)
5. Returns DailyTotal with quota status

### Model Selection Logic
1. Check StickyState for active fallback
2. Read DailyTotal for all models in ordering
3. Find first model where cost < quota
4. Return recommended model + pricing + mode (NORMAL/TIGHT)

## When Editing Specs

**⚠️ SYNC REQUIREMENT**: These specs are interconnected. When editing:
- **app_spec.md** changes → verify api_spec.md endpoints match, db_spec.md access patterns align
- **api_spec.md** changes → verify app_spec.md flows updated, db_spec.md schema supports new fields
- **db_spec.md** changes → verify app_spec.md describes new behavior, api_spec.md reflects new attributes

## Problem-Solving Guide

| Problem Area | Check First | Then Check |
|--------------|-------------|------------|
| API contract issues | `docs/api_spec.md` | `src/api/` implementation |
| Client integration | `docs/app_spec.md` § Client Integration Flow | `test-client/` examples |
| Database errors | `docs/db_spec.md` § Access Patterns | `src/services/` DB calls |
| Authentication | `docs/api_spec.md` § Authentication | `src/api/auth.py` |
| Quota logic | `docs/app_spec.md` § Operating Modes | `src/services/quota_manager.py` |
| Model selection | `docs/app_spec.md` § Sticky Fallback | `src/services/model_selector.py` |
| Deployment issues | `docs/deployment.md` | `cloudformation/` templates |
| Config questions | `docs/app_spec.md` § Configuration Architecture | `config.yaml` |


## Quick Reference: Key Files
- **Entry point**: `run.py`
- **Main config**: `config.yaml` (model labels, pricing, defaults)
- **API routes**: `src/api/routes.py`
- **Business logic**: `src/services/`
- **DynamoDB operations**: `src/services/dynamodb_service.py`
- **Authentication**: `src/api/auth.py`
- **Test client**: `test-client/bedrock_client.py`

## Environment Variables
See `.env.example` for required configuration:
- AWS credentials/region
- DynamoDB table names
- JWT signing keys
- Service URLs

---
If you don't find the information to solve a given problem, you must use your reasoning to research.

---
Whenever creating or updating config files for development and testing, use following Bedrock models:
- amazon.nova-micro-v1:0 (Nova Micro for economy )
- amazon.nova-2-lite-v1:0 (Nova Lite for standard)
- amazon.nova-pro-v1:0 (Nova Pro for premium)

Use us-east-1 as default region.

---
