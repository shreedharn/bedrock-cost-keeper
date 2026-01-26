# Bedrock Price Keeper - REST API Specification

## Overview

The Bedrock Price Keeper REST API provides endpoints for managing organization and application configurations, retrieving usage aggregates, selecting models based on quotas, and submitting cost data.

**Version:** v1
**Base URL:** `https://price-keeper.{region}.amazonaws.com/api/v1`
**Protocol:** HTTPS only
**Authentication:** JWT Bearer Token (Client ID + Client Secret)

---

## Table of Contents

1. [Authentication](#authentication)
2. [Common Data Types](#common-data-types)
3. [Error Responses](#error-responses)
4. [Rate Limiting](#rate-limiting)
5. [Endpoints](#endpoints)
   - [Authentication Endpoints](#authentication)
     - [Token Issuance](#post-authtoken)
     - [Token Refresh](#post-authrefresh)
     - [Token Revocation](#post-authrevoke)
   - [Provisioning (Admin)](#provisioning-admin)
     - [Register Organization](#put-orgsorg_id)
     - [Register Application](#put-orgsorg_idappsapp_id)
     - [Rotate Credentials](#credential-rotation)
     - [Retrieve Secret](#get-orgsorg_idcredentialssecret)
   - [Daily Aggregates](#daily-aggregates)
   - [Model Selection](#model-selection)
   - [Cost Submission](#cost-submission)
6. [Examples](#examples)

---

## Authentication

All API requests must be authenticated using JWT bearer tokens obtained via Client ID and Client Secret.

**Architecture:**
- Application Load Balancer (ALB) in front of ECS Fargate service
- Client credentials authentication (Client ID + Client Secret)
- JWT access tokens (1 hour) and refresh tokens (30 days) for API requests
- Service validates JWT signature and extracts claims

**Two API Types:**
1. **Provisioning API** - Admin endpoints for org/app registration (uses API key)
2. **Runtime API** - Normal operations for clients (uses JWT tokens)

### Authentication Flow

**Step 1: Obtain JWT Tokens**

Clients authenticate using Client ID and Client Secret (provided during org/app registration):

```http
POST /auth/token HTTP/1.1
Host: price-keeper.{region}.amazonaws.com
Content-Type: application/json

{
  "client_id": "org-550e8400-e29b-41d4-a716-446655440000-app-app-production-api",
  "client_secret": "base64-encoded-secret",
  "grant_type": "client_credentials"
}
```

**Response:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "Bearer",
  "expires_in": 3600,
  "refresh_expires_in": 2592000,
  "scope": "org:550e8400-e29b-41d4-a716-446655440000 app:app-production-api"
}
```

**Step 2: Use JWT Token in API Requests**

Include the access token in the Authorization header:

```http
GET /api/v1/orgs/{org_id}/apps/{app_id}/model-selection HTTP/1.1
Host: price-keeper.{region}.amazonaws.com
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

**Step 3: Refresh Access Token**

Before access token expires, use refresh token to get new access token:

```http
POST /auth/refresh HTTP/1.1
Host: price-keeper.{region}.amazonaws.com
Content-Type: application/json

{
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "grant_type": "refresh_token"
}
```

**Response:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "Bearer",
  "expires_in": 3600
}
```

### JWT Token Claims

**Access Token Claims:**
```json
{
  "sub": "org-550e8400-e29b-41d4-a716-446655440000-app-app-production-api",
  "org_id": "550e8400-e29b-41d4-a716-446655440000",
  "app_id": "app-production-api",
  "scope": ["read:aggregates", "write:costs", "read:model-selection"],
  "token_type": "access",
  "iat": 1737638445,
  "exp": 1737642045,
  "iss": "bedrock-price-keeper"
}
```

**Refresh Token Claims:**
```json
{
  "sub": "org-550e8400-e29b-41d4-a716-446655440000-app-app-production-api",
  "token_type": "refresh",
  "iat": 1737638445,
  "exp": 1740230445,
  "iss": "bedrock-price-keeper"
}
```

### Provisioning API Authentication

**Purpose:** Admin operations for org/app registration and credential management.

**Authentication Method:** Static API Key in header
```
X-API-Key: <provisioning-api-key>
```

**Endpoints:**
- `PUT /orgs/{org_id}`
- `PUT /orgs/{org_id}/apps/{app_id}`
- `POST /orgs/{org_id}/credentials/rotate`
- `POST /orgs/{org_id}/apps/{app_id}/credentials/rotate`
- `GET /orgs/{org_id}/credentials/secret` (one-time retrieval)

### Client Credential Management

**Client ID Format:** `org-{org_id}-app-{app_id}`

**Example:** `org-550e8400-e29b-41d4-a716-446655440000-app-app-production-api`

**Client Secret:**
- Generated during org/app registration/rotation
- 32-byte cryptographically secure random value, base64-encoded
- Stored as bcrypt hash in DynamoDB
- **Never returned in API responses** (see retrieval endpoint below)
- Should be rotated every 90 days (automated alerts recommended)

**Secret Retrieval:**

After registration, retrieve secret using one-time token:

```http
GET /orgs/{org_id}/credentials/secret?token=<one-time-token> HTTP/1.1
X-API-Key: <provisioning-api-key>
```

Response:
```json
{
  "client_id": "org-550e8400-e29b-41d4-a716-446655440000",
  "client_secret": "base64-encoded-secret",
  "expires_at": "2026-01-23T15:40:00Z",
  "note": "This secret will not be shown again. Store securely."
}
```

**Token expires after:** 10 minutes or first use (whichever comes first)

### Authorization Model

- Service validates JWT signature using signing key
- Extracts org_id and app_id from JWT claims
- Validates that token scopes match requested operation
- Rejects requests if org_id/app_id in URL don't match token claims
- Validates token hasn't been revoked (check revocation list)

---

## Common Data Types

### ModelLabel

Model labels reference entries in the main `config.yaml`.

**Type:** String
**Valid values:** `premium`, `standard`, `economy`, `ultra_premium`, or custom labels defined in config

**Examples:**
```
"premium"
"standard"
"economy"
```

### QuotaScope

Determines how quotas are applied within an organization.

**Type:** String
**Enum:**
- `ORG` - All apps share organization-wide quota
- `APP` - Each app has independent quota

### Timestamp

All timestamps use ISO 8601 format with timezone.

**Format:** `YYYY-MM-DDTHH:MM:SSZ`
**Example:** `2026-01-23T15:30:45Z`

### CostAmount

Cost values in micro-USD (1 USD = 1,000,000 micro-USD).

**Type:** Integer (64-bit)
**Unit:** micro-USD
**Example:** `15000000` (represents $15.00)

---

## Error Responses

All error responses follow a consistent format.

### Error Response Schema

```json
{
  "error": "ERROR_CODE",
  "message": "Human-readable error description",
  "details": {
    "field": "additional context"
  },
  "timestamp": "2026-01-23T15:30:45Z",
  "request_id": "7c9e6679-7425-40de-944b-e07fc1f90ae7"
}
```

### Common Error Codes

| HTTP Status | Error Code | Description |
|-------------|------------|-------------|
| 400 | `INVALID_REQUEST` | Malformed request body or parameters |
| 400 | `INVALID_CONFIG` | Configuration validation failed |
| 400 | `INVALID_MODEL_LABEL` | Model label not defined in config |
| 401 | `UNAUTHORIZED` | Missing or invalid authentication |
| 403 | `FORBIDDEN` | Insufficient permissions |
| 404 | `NOT_FOUND` | Organization or application not found |
| 409 | `ALREADY_EXISTS` | Resource already registered |
| 429 | `QUOTA_EXCEEDED` | All model quotas exceeded |
| 429 | `RATE_LIMIT_EXCEEDED` | API rate limit exceeded |
| 500 | `INTERNAL_ERROR` | Server-side error |
| 503 | `SERVICE_UNAVAILABLE` | Temporary service outage |

---

## Rate Limiting

API requests are rate-limited per client_id (extracted from JWT token).

| Endpoint | Rate Limit | Identifier |
|----------|-----------|------------|
| `POST /auth/token` | 10 requests/minute | client_id |
| `POST /auth/refresh` | 30 requests/minute | client_id |
| `PUT /orgs/{org_id}` | 10 requests/hour | API key |
| `PUT /orgs/{org_id}/apps/{app_id}` | 10 requests/hour | API key |
| `POST /credentials/rotate` | 5 requests/hour | API key |
| `GET /aggregates/*` | 60 requests/minute | client_id |
| `GET /model-selection` | 120 requests/minute | client_id |
| `POST /costs` | 1000 requests/minute | client_id |

**Rate Limit Headers:**
```
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 42
X-RateLimit-Reset: 1737640800
X-RateLimit-ClientId: org-550e8400-e29b-41d4-a716-446655440000-app-app-production-api
```

When rate limit exceeded:
```json
{
  "error": "RATE_LIMIT_EXCEEDED",
  "message": "Rate limit of 60 requests/minute exceeded",
  "retry_after": 17,
  "timestamp": "2026-01-23T15:30:45Z"
}
```

---

## Endpoints

## Authentication

### POST /auth/token

Obtain JWT access and refresh tokens using client credentials.

**Request Headers:**
```
Content-Type: application/json
```

**Request Body:**

```json
{
  "client_id": "string",
  "client_secret": "string",
  "grant_type": "client_credentials"
}
```

**Field Descriptions:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `client_id` | string | Yes | Client ID in format `org-{org_id}-app-{app_id}` |
| `client_secret` | string | Yes | Client secret from registration |
| `grant_type` | string | Yes | Must be `client_credentials` |

**Response:** `200 OK`

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "Bearer",
  "expires_in": 3600,
  "refresh_expires_in": 2592000,
  "scope": "org:550e8400-e29b-41d4-a716-446655440000 app:app-production-api"
}
```

**Response Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `access_token` | string | JWT token for API requests (1 hour lifetime) |
| `refresh_token` | string | Token to obtain new access tokens (30 days lifetime) |
| `token_type` | string | Always `Bearer` |
| `expires_in` | integer | Access token lifetime in seconds (3600) |
| `refresh_expires_in` | integer | Refresh token lifetime in seconds (2592000) |
| `scope` | string | Space-separated list of authorized scopes |

**Error Responses:**

- `401 Unauthorized` - Invalid client credentials
- `400 Bad Request` - Invalid request format or missing fields

**Rate Limiting:** 10 requests per minute per client_id

---

### POST /auth/refresh

Obtain a new access token using a refresh token.

**Request Headers:**
```
Content-Type: application/json
```

**Request Body:**

```json
{
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "grant_type": "refresh_token"
}
```

**Field Descriptions:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `refresh_token` | string | Yes | Valid refresh token from /auth/token |
| `grant_type` | string | Yes | Must be `refresh_token` |

**Response:** `200 OK`

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "Bearer",
  "expires_in": 3600
}
```

**Response Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `access_token` | string | New JWT access token (1 hour lifetime) |
| `token_type` | string | Always `Bearer` |
| `expires_in` | integer | Access token lifetime in seconds (3600) |

**Error Responses:**

- `401 Unauthorized` - Invalid or expired refresh token
- `400 Bad Request` - Invalid request format

**Rate Limiting:** 30 requests per minute per client_id

**Notes:**
- Refresh token remains valid and can be reused until it expires (30 days)
- If refresh token is revoked, this endpoint returns 401

---

### POST /auth/revoke

Revoke an access or refresh token immediately.

**Request Headers:**
```
Content-Type: application/json
Authorization: Bearer <access_token>
```

**Request Body:**

```json
{
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type_hint": "refresh_token"
}
```

**Field Descriptions:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `token` | string | Yes | Token to revoke (access or refresh) |
| `token_type_hint` | string | No | `access_token` or `refresh_token` (optimization hint) |

**Response:** `204 No Content`

**Error Responses:**

- `401 Unauthorized` - Invalid authorization header
- `400 Bad Request` - Invalid request format

**Rate Limiting:** 10 requests per minute per client_id

**Notes:**
- Revoking a refresh token invalidates all access tokens issued from it
- Revoking an access token only invalidates that specific token
- Revoked tokens are added to blocklist with TTL matching original expiry

---

## Provisioning (Admin)

These endpoints require provisioning API key authentication and are used for administrative operations.

### PUT /orgs/{org_id}

Create or update an organization configuration.

**Path Parameters:**
- `org_id` (string, required) - Organization UUID

**Request Headers:**
```
Content-Type: application/json
X-API-Key: <provisioning-api-key>
```

**Request Body:**

```json
{
  "org_name": "string",
  "timezone": "string",
  "quota_scope": "ORG" | "APP",
  "model_ordering": ["string"],
  "quotas": {
    "model_label": integer
  },
  "overrides": {
    "tight_mode_threshold_pct": integer,
    "agg_shard_count": integer,
    "sticky_fallback_enabled": boolean,
    "refresh_interval_secs": integer
  }
}
```

**Field Descriptions:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `org_name` | string | Yes | Human-readable organization name |
| `timezone` | string | Yes | IANA timezone (e.g., `America/New_York`) |
| `quota_scope` | string | Yes | `ORG` or `APP` |
| `model_ordering` | array[string] | Yes | Ordered list of model labels for fallback chain |
| `quotas` | object | Yes | Daily quota per model label in micro-USD |
| `overrides.tight_mode_threshold_pct` | integer | No | 0-100, default: 95 |
| `overrides.agg_shard_count` | integer | No | 8, 16, 32, or 64, default: 8 |
| `overrides.sticky_fallback_enabled` | boolean | No | Default: true |
| `overrides.refresh_interval_secs` | integer | No | Default: 60 |

**Validation Rules:**
- `org_id` must be valid UUID format
- `timezone` must be valid IANA timezone
- `model_ordering` must contain at least 1 label
- All labels in `model_ordering` must be defined in main config.yaml
- `quotas` must include entries for all labels in `model_ordering`
- `tight_mode_threshold_pct` must be between 50 and 100
- `agg_shard_count` is immutable after creation

**Response: 201 Created** (New organization)

```json
{
  "org_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "created",
  "created_at": "2026-01-23T15:30:45Z",
  "credentials": {
    "client_id": "org-550e8400-e29b-41d4-a716-446655440000",
    "secret_retrieval": {
      "url": "/orgs/550e8400-e29b-41d4-a716-446655440000/credentials/secret?token=7c9e6679-7425-40de-944b-e07fc1f90ae7",
      "token": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
      "expires_at": "2026-01-23T15:40:45Z"
    }
  },
  "configuration": {
    "timezone": "America/New_York",
    "quota_scope": "APP",
    "model_ordering": ["premium", "standard", "economy"],
    "agg_shard_count": 8
  }
}
```

**Response: 200 OK** (Organization updated)

```json
{
  "org_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "updated",
  "updated_at": "2026-01-23T15:30:45Z",
  "configuration": {
    "timezone": "America/New_York",
    "quota_scope": "APP",
    "model_ordering": ["premium", "standard", "economy"],
    "agg_shard_count": 8
  }
}
```

**Important:**
- Client secret is NOT returned in this response
- Use the one-time retrieval token to get the secret within 10 minutes
- PUT is idempotent - repeated calls update the configuration without creating new credentials

**Error Responses:**

**400 Bad Request - Invalid Configuration**
```json
{
  "error": "INVALID_CONFIG",
  "message": "Model label 'unknown_label' not defined in main config",
  "details": {
    "invalid_labels": ["unknown_label"],
    "valid_labels": ["premium", "standard", "economy", "ultra_premium"]
  },
  "timestamp": "2026-01-23T15:30:45Z"
}
```

**409 Conflict - Already Exists**
```json
{
  "error": "ALREADY_EXISTS",
  "message": "Organization already registered",
  "details": {
    "org_id": "550e8400-e29b-41d4-a716-446655440000",
    "registered_at": "2026-01-20T10:00:00Z"
  },
  "timestamp": "2026-01-23T15:30:45Z"
}
```

**Example Request:**

```bash
curl -X PUT https://price-keeper.us-east-1.amazonaws.com/api/v1/orgs/550e8400-e29b-41d4-a716-446655440000 \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <provisioning-api-key>" \
  --data '{
    "org_name": "sample_corp",
    "timezone": "America/New_York",
    "quota_scope": "APP",
    "model_ordering": ["premium", "standard", "economy"],
    "quotas": {
      "premium": 10000000,
      "standard": 5000000,
      "economy": 2000000
    },
    "overrides": {
      "tight_mode_threshold_pct": 95,
      "agg_shard_count": 8
    }
  }'
```

---

### PUT /orgs/{org_id}/apps/{app_id}

Create or update an application configuration under an organization.

**Path Parameters:**
- `org_id` (string, required) - Organization UUID
- `app_id` (string, required) - Application identifier

**Request Headers:**
```
Content-Type: application/json
X-API-Key: <provisioning-api-key>
```

**Request Body:**

```json
{
  "app_name": "string",
  "model_ordering": ["string"],
  "quotas": {
    "model_label": integer
  },
  "overrides": {
    "tight_mode_threshold_pct": integer,
    "refresh_interval_secs": integer
  }
}
```

**Field Descriptions:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `app_name` | string | Yes | Human-readable application name |
| `model_ordering` | array[string] | No | Overrides org model_ordering |
| `quotas` | object | No | Overrides org quotas (only if quota_scope=APP) |
| `overrides.tight_mode_threshold_pct` | integer | No | Overrides org threshold |
| `overrides.refresh_interval_secs` | integer | No | Overrides org refresh interval |

**Inheritance Rules:**
- If field not specified, inherits from org config
- If app config doesn't exist, uses org config entirely
- `timezone`, `quota_scope`, `agg_shard_count` always inherited from org (not overridable)

**Response: 201 Created** (New application)

```json
{
  "org_id": "550e8400-e29b-41d4-a716-446655440000",
  "app_id": "app-production-api",
  "status": "created",
  "created_at": "2026-01-23T15:30:45Z",
  "credentials": {
    "client_id": "org-550e8400-e29b-41d4-a716-446655440000-app-app-production-api",
    "secret_retrieval": {
      "url": "/orgs/550e8400-e29b-41d4-a716-446655440000/apps/app-production-api/credentials/secret?token=8d0f7680-8536-51ef-b827-557766551001",
      "token": "8d0f7680-8536-51ef-b827-557766551001",
      "expires_at": "2026-01-23T15:40:45Z"
    }
  },
  "configuration": {
    "app_name": "Production API",
    "model_ordering": ["premium", "standard"],
    "inherited_fields": ["timezone", "agg_shard_count"]
  }
}
```

**Response: 200 OK** (Application updated)

```json
{
  "org_id": "550e8400-e29b-41d4-a716-446655440000",
  "app_id": "app-production-api",
  "status": "updated",
  "updated_at": "2026-01-23T15:30:45Z",
  "configuration": {
    "app_name": "Production API",
    "model_ordering": ["premium", "standard"],
    "inherited_fields": ["timezone", "agg_shard_count"]
  }
}
```

**Important:**
- Client secret is NOT returned in this response
- Use the one-time retrieval token to get the secret within 10 minutes
- PUT is idempotent - repeated calls update configuration without creating new credentials

**Error Responses:**

**404 Not Found - Org Not Registered**
```json
{
  "error": "NOT_FOUND",
  "message": "Organization not registered",
  "details": {
    "org_id": "550e8400-e29b-41d4-a716-446655440000"
  },
  "hint": "Call POST /orgs/{org_id}/register first",
  "timestamp": "2026-01-23T15:30:45Z"
}
```

**Example Request:**

```bash
curl -X PUT https://price-keeper.us-east-1.amazonaws.com/api/v1/orgs/550e8400-e29b-41d4-a716-446655440000/apps/app-production-api \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <provisioning-api-key>" \
  --data '{
    "app_name": "Production API",
    "model_ordering": ["premium", "standard"],
    "quotas": {
      "premium": 50000000,
      "standard": 20000000
    },
    "overrides": {
      "tight_mode_threshold_pct": 90
    }
  }'
```

---

### Credential Rotation

#### POST /orgs/{org_id}/credentials/rotate

Rotate client credentials for an organization. Generates new client_secret while keeping client_id.

**Path Parameters:**
- `org_id` (string, required) - Organization UUID

**Request Headers:**
```
Content-Type: application/json
X-API-Key: <provisioning-api-key>
```

**Request Body:**

```json
{
  "grace_period_hours": 24
}
```

**Field Descriptions:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `grace_period_hours` | integer | No | Hours before old secret expires (0-168, default: 24) |

**Response: 200 OK**

```json
{
  "org_id": "550e8400-e29b-41d4-a716-446655440000",
  "client_id": "org-550e8400-e29b-41d4-a716-446655440000",
  "secret_retrieval": {
    "url": "/orgs/550e8400-e29b-41d4-a716-446655440000/credentials/secret?token=9e1f8791-9647-62f0-c938-668877662112",
    "token": "9e1f8791-9647-62f0-c938-668877662112",
    "expires_at": "2026-01-23T15:40:45Z"
  },
  "rotation": {
    "rotated_at": "2026-01-23T15:30:45Z",
    "old_secret_expires_at": "2026-01-24T15:30:45Z",
    "grace_period_hours": 24
  }
}
```

**Notes:**
- Old secret remains valid during grace period for zero-downtime rotation
- After grace period, old secret is permanently invalidated
- Use one-time retrieval token to get new secret

**Example Request:**

```bash
curl -X POST https://price-keeper.us-east-1.amazonaws.com/api/v1/orgs/550e8400-e29b-41d4-a716-446655440000/credentials/rotate \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <provisioning-api-key>" \
  --data '{"grace_period_hours": 24}'
```

---

#### POST /orgs/{org_id}/apps/{app_id}/credentials/rotate

Rotate client credentials for an application.

**Path Parameters:**
- `org_id` (string, required) - Organization UUID
- `app_id` (string, required) - Application identifier

**Request Headers:**
```
Content-Type: application/json
X-API-Key: <provisioning-api-key>
```

**Request Body:**

```json
{
  "grace_period_hours": 24
}
```

**Response: 200 OK**

Same structure as org credential rotation, with additional `app_id` field.

```json
{
  "org_id": "550e8400-e29b-41d4-a716-446655440000",
  "app_id": "app-production-api",
  "client_id": "org-550e8400-e29b-41d4-a716-446655440000-app-app-production-api",
  "secret_retrieval": {
    "url": "/orgs/550e8400-e29b-41d4-a716-446655440000/apps/app-production-api/credentials/secret?token=af209802-a758-73g1-d049-779988773223",
    "token": "af209802-a758-73g1-d049-779988773223",
    "expires_at": "2026-01-23T15:40:45Z"
  },
  "rotation": {
    "rotated_at": "2026-01-23T15:30:45Z",
    "old_secret_expires_at": "2026-01-24T15:30:45Z",
    "grace_period_hours": 24
  }
}
```

---

### GET /orgs/{org_id}/credentials/secret

Retrieve client secret using one-time token (from registration or rotation response).

**Path Parameters:**
- `org_id` (string, required) - Organization UUID

**Query Parameters:**
- `token` (string, required) - One-time retrieval token

**Request Headers:**
```
X-API-Key: <provisioning-api-key>
```

**Response: 200 OK**

```json
{
  "client_id": "org-550e8400-e29b-41d4-a716-446655440000",
  "client_secret": "YnVmZmVyLWlzLWEtYmFzZTY0LWVuY29kZWQtc2VjcmV0LXZhbHVl",
  "retrieved_at": "2026-01-23T15:35:45Z",
  "expires_at": "2026-04-23T15:30:45Z",
  "note": "This secret will not be shown again. Store securely."
}
```

**Error Responses:**

**401 Unauthorized - Invalid or Expired Token**
```json
{
  "error": "UNAUTHORIZED",
  "message": "One-time retrieval token invalid or expired",
  "details": {
    "token_status": "expired",
    "expired_at": "2026-01-23T15:40:45Z"
  },
  "timestamp": "2026-01-23T15:50:45Z"
}
```

**404 Not Found - Token Already Used**
```json
{
  "error": "NOT_FOUND",
  "message": "Token has already been used",
  "details": {
    "retrieved_at": "2026-01-23T15:32:00Z"
  },
  "hint": "If you lost the secret, rotate credentials to generate new one",
  "timestamp": "2026-01-23T15:35:45Z"
}
```

**Example Request:**

```bash
curl -X GET "https://price-keeper.us-east-1.amazonaws.com/api/v1/orgs/550e8400-e29b-41d4-a716-446655440000/credentials/secret?token=7c9e6679-7425-40de-944b-e07fc1f90ae7" \
  -H "X-API-Key: <provisioning-api-key>"
```

**Notes:**
- Token expires after 10 minutes or first use (whichever comes first)
- Token can only be used once
- Response includes full client_secret for secure storage

---

### GET /orgs/{org_id}/apps/{app_id}/credentials/secret

Retrieve application client secret using one-time token.

**Path Parameters:**
- `org_id` (string, required) - Organization UUID
- `app_id` (string, required) - Application identifier

**Query Parameters:**
- `token` (string, required) - One-time retrieval token

**Request Headers:**
```
X-API-Key: <provisioning-api-key>
```

**Response: 200 OK**

Same structure as org secret retrieval, with app-specific client_id.

**Example Request:**

```bash
curl -X GET "https://price-keeper.us-east-1.amazonaws.com/api/v1/orgs/550e8400-e29b-41d4-a716-446655440000/apps/app-production-api/credentials/secret?token=8d0f7680-8536-51ef-b827-557766551001" \
  -H "X-API-Key: <provisioning-api-key>"
```

---

## Daily Aggregates

### GET /orgs/{org_id}/aggregates/today

Retrieve today's usage summary for an organization across all models.

**Path Parameters:**
- `org_id` (string, required) - Organization UUID

**Query Parameters:**
None

**Response: 200 OK**

```json
{
  "org_id": "550e8400-e29b-41d4-a716-446655440000",
  "date": "2026-01-23",
  "timezone": "America/New_York",
  "quota_scope": "APP",
  "models": {
    "premium": {
      "label": "premium",
      "bedrock_model_id": "anthropic.claude-3-5-sonnet-20241022-v2:0",
      "cost_usd_micros": 9500000,
      "quota_usd_micros": 10000000,
      "quota_pct": 95.0,
      "quota_status": "TIGHT",
      "input_tokens": 1200000,
      "output_tokens": 650000,
      "requests": 342,
      "average_cost_per_request": 27784
    },
    "standard": {
      "label": "standard",
      "bedrock_model_id": "anthropic.claude-3-5-haiku-20241022-v1:0",
      "cost_usd_micros": 1200000,
      "quota_usd_micros": 5000000,
      "quota_pct": 24.0,
      "quota_status": "NORMAL",
      "input_tokens": 500000,
      "output_tokens": 250000,
      "requests": 89,
      "average_cost_per_request": 13483
    },
    "economy": {
      "label": "economy",
      "bedrock_model_id": "anthropic.claude-3-haiku-20240307-v1:0",
      "cost_usd_micros": 0,
      "quota_usd_micros": 2000000,
      "quota_pct": 0.0,
      "quota_status": "NORMAL",
      "input_tokens": 0,
      "output_tokens": 0,
      "requests": 0,
      "average_cost_per_request": 0
    }
  },
  "total_cost_usd_micros": 10700000,
  "total_quota_usd_micros": 17000000,
  "total_quota_pct": 62.9,
  "sticky_fallback_active": false,
  "current_active_model": "premium",
  "updated_at": "2026-01-23T15:30:45Z"
}
```

**Field Descriptions:**

| Field | Description |
|-------|-------------|
| `quota_status` | `NORMAL`, `TIGHT`, or `EXCEEDED` |
| `quota_pct` | Percentage of quota consumed (0-100+) |
| `average_cost_per_request` | Average cost per request in micro-USD |
| `sticky_fallback_active` | Whether sticky fallback is currently in effect |
| `current_active_model` | Model label currently in use (if sticky active) |

**Response Headers:**

```
Cache-Control: max-age=30, private
ETag: "550e8400-20260123-v1"
X-Data-Lag-Secs: 15
```

| Header | Description |
|--------|-------------|
| `Cache-Control` | 30-second cache (data updates every 30-60s due to aggregator) |
| `ETag` | Hash for conditional requests (If-None-Match) |
| `X-Data-Lag-Secs` | Seconds since last aggregator run (eventual consistency indicator) |

**Error Responses:**

**404 Not Found**
```json
{
  "error": "NOT_FOUND",
  "message": "Organization not found",
  "timestamp": "2026-01-23T15:30:45Z"
}
```

---

### GET /orgs/{org_id}/apps/{app_id}/aggregates/today

Retrieve today's usage for a specific application.

**Path Parameters:**
- `org_id` (string, required) - Organization UUID
- `app_id` (string, required) - Application identifier

**Response: 200 OK**

Same structure as org aggregates, with additional fields:

```json
{
  "org_id": "550e8400-e29b-41d4-a716-446655440000",
  "app_id": "app-production-api",
  "app_name": "Production API",
  "date": "2026-01-23",
  "timezone": "America/New_York",
  "quota_scope": "APP",
  "models": { ... },
  "total_cost_usd_micros": 75000000,
  "total_quota_usd_micros": 70000000,
  "total_quota_pct": 107.1,
  "sticky_fallback_active": true,
  "current_active_model": "standard",
  "updated_at": "2026-01-23T15:30:45Z"
}
```

**Note:** If `quota_scope` is `ORG`, this endpoint returns the same data as org-level aggregates since all apps share quotas.

---

### GET /orgs/{org_id}/aggregates/{date}

Retrieve historical aggregates for an organization.

**Path Parameters:**
- `org_id` (string, required) - Organization UUID
- `date` (string, required) - Date in `YYYY-MM-DD` format

**Query Parameters:**
None

**Response: 200 OK**

Same structure as today endpoint, but for specified date.

**Validation:**
- `date` must be valid ISO 8601 date format (YYYY-MM-DD)
- `date` cannot be in the future
- Historical data retained based on TTL configuration (typically 30-90 days)

**Error Responses:**

**400 Bad Request - Invalid Date**
```json
{
  "error": "INVALID_REQUEST",
  "message": "Invalid date format",
  "details": {
    "date": "2026-13-45",
    "expected_format": "YYYY-MM-DD"
  },
  "timestamp": "2026-01-23T15:30:45Z"
}
```

**404 Not Found - No Data**
```json
{
  "error": "NOT_FOUND",
  "message": "No data available for specified date",
  "details": {
    "date": "2025-12-15",
    "reason": "Data expired (TTL) or date predates org registration"
  },
  "timestamp": "2026-01-23T15:30:45Z"
}
```

---

### GET /orgs/{org_id}/apps/{app_id}/aggregates/{date}

Retrieve historical aggregates for an application.

**Path Parameters:**
- `org_id` (string, required) - Organization UUID
- `app_id` (string, required) - Application identifier
- `date` (string, required) - Date in `YYYY-MM-DD` format

**Response: 200 OK**

Same structure as app aggregates today endpoint, for specified date.

---

## Model Selection

### GET /orgs/{org_id}/apps/{app_id}/model-selection

Get current recommended model based on quota status and sticky fallback state.

**Path Parameters:**
- `org_id` (string, required) - Organization UUID
- `app_id` (string, required) - Application identifier

**Query Parameters:**
- `force_check` (boolean, optional) - Bypass cache, perform real-time quota check. Default: `false`

**Request Headers:**
```
Authorization: Bearer <access_token>
```

**Response: 200 OK**

```json
{
  "org_id": "550e8400-e29b-41d4-a716-446655440000",
  "app_id": "app-production-api",
  "recommended_model": {
    "label": "standard",
    "bedrock_model_id": "anthropic.claude-3-5-haiku-20241022-v1:0",
    "reason": "QUOTA_EXCEEDED_PREMIUM",
    "description": "Premium quota exceeded, using standard tier"
  },
  "quota_status": {
    "scope": "APP",
    "mode": "TIGHT",
    "current_model": "standard",
    "spend_usd_micros": 18500000,
    "quota_usd_micros": 20000000,
    "quota_pct": 92.5,
    "sticky_fallback_active": true,
    "models_status": {
      "premium": {
        "spend_usd_micros": 50000000,
        "quota_usd_micros": 50000000,
        "quota_pct": 100.0,
        "status": "EXCEEDED"
      },
      "standard": {
        "spend_usd_micros": 18500000,
        "quota_usd_micros": 20000000,
        "quota_pct": 92.5,
        "status": "TIGHT"
      }
    }
  },
  "pricing": {
    "input_price_usd_micros_per_1m": 800000,
    "output_price_usd_micros_per_1m": 4000000,
    "version": "2026-01-23",
    "source": "PRICING_API"
  },
  "client_guidance": {
    "check_frequency": "PERIODIC_60S",
    "cache_duration_secs": 60,
    "explanation": "In TIGHT mode - check every 60 seconds for faster fallback detection"
  },
  "checked_at": "2026-01-23T15:30:45Z",
  "org_day": "20260123",
  "org_local_time": "2026-01-23T10:30:45-05:00"
}
```

**Field Descriptions:**

| Field | Description |
|-------|-------------|
| `recommended_model.reason` | `NORMAL`, `QUOTA_EXCEEDED_<label>`, `STICKY_FALLBACK`, `ALL_QUOTAS_EXCEEDED` |
| `quota_status.mode` | `NORMAL` (< 95% quota) or `TIGHT` (>= 95% quota) |
| `quota_status.status` | `NORMAL`, `TIGHT`, or `EXCEEDED` per model |
| `pricing.source` | `PRICING_API`, `CONFIG_FALLBACK`, or `CACHED` |
| `client_guidance.check_frequency` | `PERIODIC_300S` (normal mode, 5 min) or `PERIODIC_60S` (tight mode, 1 min) |
| `client_guidance.cache_duration_secs` | How long client can cache this response (300 or 60) |

**Response Headers:**

```
Cache-Control: max-age=60, private    # TIGHT mode
Cache-Control: max-age=300, private   # NORMAL mode
ETag: "550e8400-app-production-api-20260123-v1"
```

| Header | Description |
|--------|-------------|
| `Cache-Control` | Variable based on mode (60s TIGHT, 300s NORMAL) |
| `ETag` | Hash for conditional requests (If-None-Match) |

**Response: 429 Too Many Requests - All Quotas Exceeded**

```json
{
  "error": "QUOTA_EXCEEDED",
  "message": "All model quotas exceeded for today",
  "retry_after": "2026-01-24T05:00:00Z",
  "details": {
    "org_id": "550e8400-e29b-41d4-a716-446655440000",
    "app_id": "app-production-api",
    "date": "2026-01-23",
    "models": {
      "premium": {"quota_pct": 102.5, "exceeded": true},
      "standard": {"quota_pct": 108.3, "exceeded": true},
      "economy": {"quota_pct": 101.2, "exceeded": true}
    },
    "total_overage_usd_micros": 2150000
  },
  "timestamp": "2026-01-23T15:30:45Z"
}
```

**Client Usage Pattern:**

```python
# Periodic checking based on mode
while True:
    response = get_model_selection(org_id, app_id)
    model_id = response['recommended_model']['bedrock_model_id']
    pricing = response['pricing']

    # Determine check interval based on mode
    check_freq = response['client_guidance']['check_frequency']
    cache_duration = response['client_guidance']['cache_duration_secs']

    if check_freq == 'PERIODIC_300S':
        # NORMAL mode: Check every 5 minutes
        time.sleep(300)
    elif check_freq == 'PERIODIC_60S':
        # TIGHT mode: Check every 60 seconds
        time.sleep(60)
```

**Example Request:**

```bash
curl -X GET "https://price-keeper.us-east-1.amazonaws.com/api/v1/orgs/550e8400-e29b-41d4-a716-446655440000/apps/app-production-api/model-selection?force_check=true" \
  -H "Authorization: Bearer <access_token>"
```

---

## Cost Submission

### POST /orgs/{org_id}/apps/{app_id}/costs

Submit request cost and usage data for aggregation.

**Path Parameters:**
- `org_id` (string, required) - Organization UUID
- `app_id` (string, required) - Application identifier

**Request Body:**

```json
{
  "request_id": "string",
  "model_label": "string",
  "bedrock_model_id": "string",
  "input_tokens": integer,
  "output_tokens": integer,
  "cost_usd_micros": integer,
  "status": "string",
  "timestamp": "string"
}
```

**Field Descriptions:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `request_id` | string (UUID) | Yes | Unique request identifier (for idempotency) |
| `model_label` | string | Yes | Model label from config (e.g., `premium`) |
| `bedrock_model_id` | string | Yes | Actual Bedrock model ID used |
| `input_tokens` | integer | Yes | Number of input tokens |
| `output_tokens` | integer | Yes | Number of output tokens |
| `cost_usd_micros` | integer | Yes | Total cost in micro-USD |
| `status` | string | Yes | `OK` or `ERROR` |
| `timestamp` | string (ISO 8601) | Yes | When the request occurred |

**Validation Rules:**
- `request_id` must be valid UUID format
- `model_label` must exist in org/app configuration
- `input_tokens` and `output_tokens` must be non-negative
- `cost_usd_micros` must be non-negative
- `timestamp` must not be in the future
- `timestamp` must be within current org-local day (±24 hours tolerance)

**Response: 202 Accepted**

```json
{
  "request_id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
  "status": "accepted",
  "message": "Cost data queued for processing",
  "processing": {
    "shard_id": 3,
    "expected_aggregation_lag_secs": 60
  },
  "timestamp": "2026-01-23T15:30:45Z"
}
```

**Idempotency:**
- Submitting the same `request_id` multiple times is safe
- Subsequent submissions with same `request_id` are no-ops
- Returns 202 Accepted regardless

**Error Responses:**

**400 Bad Request - Invalid Model Label**
```json
{
  "error": "INVALID_CONFIG",
  "message": "Model label not configured for this application",
  "details": {
    "model_label": "ultra_premium",
    "configured_labels": ["premium", "standard"],
    "app_id": "app-production-api"
  },
  "timestamp": "2026-01-23T15:30:45Z"
}
```

**400 Bad Request - Timestamp Out of Range**
```json
{
  "error": "INVALID_REQUEST",
  "message": "Timestamp outside acceptable range",
  "details": {
    "timestamp": "2026-01-22T10:00:00Z",
    "org_day": "20260123",
    "timezone": "America/New_York",
    "acceptable_range": "2026-01-22T05:00:00Z to 2026-01-24T04:59:59Z"
  },
  "timestamp": "2026-01-23T15:30:45Z"
}
```

**Example Request:**

```bash
curl -X POST https://price-keeper.us-east-1.amazonaws.com/api/v1/orgs/550e8400-e29b-41d4-a716-446655440000/apps/app-production-api/costs \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <access_token>" \
  --data '{
    "request_id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
    "model_label": "premium",
    "bedrock_model_id": "anthropic.claude-3-5-sonnet-20241022-v2:0",
    "input_tokens": 1500,
    "output_tokens": 800,
    "cost_usd_micros": 15750,
    "status": "OK",
    "timestamp": "2026-01-23T15:30:45Z"
  }'
```

**Batch Submission:**

For high-throughput applications, batch submission is recommended:

```json
{
  "requests": [
    {
      "request_id": "uuid-1",
      "model_label": "premium",
      ...
    },
    {
      "request_id": "uuid-2",
      "model_label": "standard",
      ...
    }
  ]
}
```

**Batch Response: 207 Multi-Status**

```json
{
  "accepted": 95,
  "failed": 5,
  "results": [
    {
      "request_id": "uuid-1",
      "status": "accepted"
    },
    {
      "request_id": "uuid-2",
      "status": "failed",
      "error": "INVALID_MODEL_LABEL"
    }
  ],
  "timestamp": "2026-01-23T15:30:45Z"
}
```

---

## Examples

### Complete Client Integration Flow

#### 1. Initialization

```python
import requests
import os

base_url = 'https://price-keeper.us-east-1.amazonaws.com'
org_id = '550e8400-e29b-41d4-a716-446655440000'
app_id = 'app-production-api'

# Load client credentials from environment
client_id = os.environ['PRICE_KEEPER_CLIENT_ID']
client_secret = os.environ['PRICE_KEEPER_CLIENT_SECRET']

# Token cache with expiration handling
token_cache = {
    'access_token': None,
    'refresh_token': None,
    'expires_at': 0
}

def authenticate():
    """Initial authentication with client credentials."""
    response = requests.post(
        f'{base_url}/auth/token',
        json={
            'client_id': client_id,
            'client_secret': client_secret,
            'grant_type': 'client_credentials'
        }
    )
    response.raise_for_status()
    data = response.json()

    now = time.time()
    token_cache['access_token'] = data['access_token']
    token_cache['refresh_token'] = data['refresh_token']
    token_cache['expires_at'] = now + data['expires_in'] - 300  # Refresh 5 min early

def refresh_access_token():
    """Refresh access token using refresh token."""
    response = requests.post(
        f'{base_url}/auth/refresh',
        json={
            'refresh_token': token_cache['refresh_token'],
            'grant_type': 'refresh_token'
        }
    )
    response.raise_for_status()
    data = response.json()

    now = time.time()
    token_cache['access_token'] = data['access_token']
    token_cache['expires_at'] = now + data['expires_in'] - 300  # Refresh 5 min early

def get_headers():
    """Get headers with valid JWT token, refreshing if needed."""
    now = time.time()
    if token_cache['access_token'] is None:
        # First time - authenticate with credentials
        authenticate()
    elif now >= token_cache['expires_at']:
        # Access token expired - use refresh token
        refresh_access_token()

    return {
        'Authorization': f'Bearer {token_cache["access_token"]}',
        'Content-Type': 'application/json'
    }

# Get initial model recommendation
response = requests.get(
    f'{base_url}/api/v1/orgs/{org_id}/apps/{app_id}/model-selection',
    headers=get_headers()
)
model_info = response.json()

current_model = model_info['recommended_model']['bedrock_model_id']
pricing = model_info['pricing']
check_frequency = model_info['client_guidance']['check_frequency']
```

#### 2. Making Bedrock Requests (Normal Mode)

```python
import boto3
import time
from datetime import datetime

bedrock = boto3.client('bedrock-runtime', region_name='us-east-1')

# Cache model for 60 seconds in normal mode
model_cache = {
    'model_id': current_model,
    'pricing': pricing,
    'expires_at': time.time() + 60
}

def make_request(prompt):
    # Check if need to refresh model
    if time.time() > model_cache['expires_at']:
        refresh_model_cache()

    # Call Bedrock
    request_id = str(uuid.uuid4())
    response = bedrock.converse(
        modelId=model_cache['model_id'],
        messages=[{'role': 'user', 'content': [{'text': prompt}]}]
    )

    # Calculate cost
    input_tokens = response['usage']['inputTokens']
    output_tokens = response['usage']['outputTokens']
    cost = calculate_cost(input_tokens, output_tokens, model_cache['pricing'])

    # Submit cost asynchronously (fire and forget)
    submit_cost_async(request_id, input_tokens, output_tokens, cost)

    return response

def calculate_cost(input_tokens, output_tokens, pricing):
    input_cost = (input_tokens * pricing['input_price_usd_micros_per_1m']) // 1_000_000
    output_cost = (output_tokens * pricing['output_price_usd_micros_per_1m']) // 1_000_000
    return input_cost + output_cost
```

#### 3. Submitting Costs

```python
import threading

def submit_cost_async(request_id, input_tokens, output_tokens, cost):
    def submit():
        try:
            requests.post(
                f'{base_url}/api/v1/orgs/{org_id}/apps/{app_id}/costs',
                headers=get_headers(),
                json={
                    'request_id': request_id,
                    'model_label': model_cache['label'],
                    'bedrock_model_id': model_cache['model_id'],
                    'input_tokens': input_tokens,
                    'output_tokens': output_tokens,
                    'cost_usd_micros': cost,
                    'status': 'OK',
                    'timestamp': datetime.utcnow().isoformat() + 'Z'
                }
            )
        except Exception as e:
            # Log error but don't block main flow
            logger.error(f'Cost submission failed: {e}')

    # Submit in background thread
    threading.Thread(target=submit, daemon=True).start()
```

#### 4. Background Model Refresh Loop

```python
import threading
import time

def model_refresh_loop():
    """Background thread to periodically refresh model selection."""
    while True:
        try:
            response = requests.get(
                f'{base_url}/api/v1/orgs/{org_id}/apps/{app_id}/model-selection',
                headers=get_headers()
            )

            if response.status_code == 200:
                model_info = response.json()

                # Update cache with new model/pricing
                model_cache['model_id'] = model_info['recommended_model']['bedrock_model_id']
                model_cache['label'] = model_info['recommended_model']['label']
                model_cache['pricing'] = model_info['pricing']

                # Adjust check frequency based on mode
                check_freq = model_info['client_guidance']['check_frequency']
                cache_duration = model_info['client_guidance']['cache_duration_secs']

                # Sleep until next check
                time.sleep(cache_duration)

            elif response.status_code == 429:
                # All quotas exceeded - wait until tomorrow
                error = response.json()
                print(f"All quotas exceeded. Retry after {error['retry_after']}")
                time.sleep(3600)  # Check again in 1 hour

        except Exception as e:
            print(f"Model refresh failed: {e}")
            time.sleep(60)  # Retry after 1 minute on error

# Start background refresh thread
refresh_thread = threading.Thread(target=model_refresh_loop, daemon=True)
refresh_thread.start()
```

#### 5. Checking Daily Usage

```python
def get_daily_usage():
    response = requests.get(
        f'{base_url}/api/v1/orgs/{org_id}/apps/{app_id}/aggregates/today',
        headers=get_headers()
    )

    data = response.json()

    print(f"Total cost today: ${data['total_cost_usd_micros'] / 1_000_000:.2f}")
    print(f"Total quota: ${data['total_quota_usd_micros'] / 1_000_000:.2f}")
    print(f"Quota usage: {data['total_quota_pct']:.1f}%")

    for label, model in data['models'].items():
        print(f"\n{label}:")
        print(f"  Cost: ${model['cost_usd_micros'] / 1_000_000:.2f}")
        print(f"  Requests: {model['requests']}")
        print(f"  Quota: {model['quota_pct']:.1f}%")
```

---

## HTTP Status Code Summary

| Status | Meaning | When Used |
|--------|---------|-----------|
| 200 | OK | Successful GET requests |
| 201 | Created | Successful registration |
| 202 | Accepted | Cost submission accepted |
| 207 | Multi-Status | Batch operations with mixed results |
| 400 | Bad Request | Invalid request format or parameters |
| 401 | Unauthorized | Missing or invalid authentication |
| 403 | Forbidden | Insufficient permissions |
| 404 | Not Found | Resource doesn't exist |
| 409 | Conflict | Resource already exists |
| 429 | Too Many Requests | Rate limit or quota exceeded |
| 500 | Internal Server Error | Unexpected server error |
| 503 | Service Unavailable | Temporary outage |

---

## API Versioning

The API uses URL-based versioning (`/api/v1`).

**Version Policy:**
- Breaking changes require new version (v2, v3, etc.)
- Non-breaking additions can be made to existing versions
- Old versions supported for minimum 12 months after deprecation notice

**Deprecation Process:**
1. New version released with migration guide
2. Old version marked deprecated (header: `X-API-Deprecated: true`)
3. 12-month deprecation period
4. Old version removed

---

## Support & Contact

**Documentation:** https://docs.aws.amazon.com/bedrock-price-keeper/
**API Status:** https://status.aws.amazon.com/
**Support:** Open ticket via AWS Support Center

**SDKs Available:**
- Python: `pip install bedrock-price-keeper-sdk`
- Java: Available via Maven Central
- JavaScript/TypeScript: `npm install @aws/bedrock-price-keeper-client`
- Go: `go get github.com/aws/bedrock-price-keeper-sdk-go`

---

## Changelog

### v1.0.0 (2026-01-23)
- Initial release
- Registration endpoints
- Daily aggregate queries
- Model selection endpoint
- Cost submission endpoint
- Support for N models with label-based configuration
- Org and app-level quota scoping
