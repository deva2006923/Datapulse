# DataPulse API Contract

This document outlines the API contract for the **DataPulse** backend, designed to interface seamlessly with the external Lovable frontend.

## General Information
- **API Title**: DataPulse Backend API
- **Version**: 1.0.0
- **Authentication**: Bearer Token (`Authorization: Bearer <token>`)
- **Trailing Slash Handling**: All endpoints work identically with and without trailing slash (`redirect_slashes=False`)
- **CORS**: Supports exact origin list and regex (`https://.*\.(lovable\.app|lovableproject\.com|lovable\.dev)$`)

---

## Endpoints Summary

| Method | Endpoint | Summary | Auth Required |
|---|---|---|---|
| `GET` | `/admin/audit-logs` | Get Admin Audit Logs | Optional / No |
| `GET` | `/admin/datasets` | Get Admin Datasets | Optional / No |
| `GET` | `/admin/overview` | Get Admin Overview | Optional / No |
| `GET` | `/admin/queries` | Get Admin Queries | Optional / No |
| `GET` | `/admin/transactions` | Get Admin Transactions | Optional / No |
| `GET` | `/admin/users` | Get Admin Users | Optional / No |
| `GET` | `/admin/users/{user_id}` | Get Admin User Detail | Optional / No |
| `POST` | `/auth/login` | Login | No |
| `GET` | `/auth/me` | Get Me | Optional / No |
| `POST` | `/auth/register` | Register | No |
| `POST` | `/credits/redeem` | Redeem Credits | Optional / No |
| `GET` | `/credits/transactions` | Get User Transactions | Optional / No |
| `GET` | `/datasets` | List Datasets | Optional / No |
| `POST` | `/datasets/search` | Search Datasets | Optional / No |
| `GET` | `/datasets/search` | Search Datasets Get | Optional / No |
| `POST` | `/datasets/upload` | Upload Dataset | Optional / No |
| `GET` | `/datasets/{dataset_id}` | Get Dataset | Optional / No |
| `GET` | `/datasets/{dataset_id}/evaluation` | Get Dataset Evaluation | Optional / No |
| `POST` | `/datasets/{dataset_id}/improve` | Improve Dataset | Optional / No |
| `POST` | `/datasets/{dataset_id}/unlock` | Unlock Dataset | Optional / No |
| `GET` | `/health` | Health Check | No |
| `GET` | `/me` | Get Me | Optional / No |
| `GET` | `/me/stats` | Get User Stats | Optional / No |
| `POST` | `/query` | Execute Query | Optional / No |
| `GET` | `/query/history` | Get Query History | Optional / No |
| `POST` | `/redeem` | Redeem Credits | Optional / No |
| `POST` | `/search` | Search Datasets | Optional / No |

---

## Detailed Endpoint Specifications

### `GET /admin/audit-logs`
**Tags**: Admin Dashboard
**Description**: Get Admin Audit Logs

#### Parameters
| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `page` | query | No | `integer` | Page number, 1-indexed |
| `limit` | query | No | `integer` | Items per page |
| `action` | query | No | `string` | Filter by action name |
| `authorization` | header | No | `string` |  |

#### Responses & Error Codes
| Code | Meaning | Schema / Content |
|---|---|---|
| `200` | Successful Response | `AdminAuditLogListResponse` (application/json) |
| `422` | Validation Error | `HTTPValidationError` (application/json) |

---

### `GET /admin/datasets`
**Tags**: Admin Dashboard
**Description**: Get Admin Datasets

#### Parameters
| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `page` | query | No | `integer` | Page number, 1-indexed |
| `limit` | query | No | `integer` | Items per page |
| `search` | query | No | `string` | Search by dataset title, filename, domain, or owner |
| `domain` | query | No | `string` | Filter by domain |
| `owner_id` | query | No | `string` | Filter by owner user ID |
| `sort_by` | query | No | `string` | Sort by: created_at, rows_count, quality_score, name |
| `sort_order` | query | No | `string` | Sort order: asc, desc |
| `authorization` | header | No | `string` |  |

#### Responses & Error Codes
| Code | Meaning | Schema / Content |
|---|---|---|
| `200` | Successful Response | `AdminDatasetListResponse` (application/json) |
| `422` | Validation Error | `HTTPValidationError` (application/json) |

---

### `GET /admin/overview`
**Tags**: Admin Dashboard
**Description**: Get Admin Overview

#### Parameters
| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `authorization` | header | No | `string` |  |

#### Responses & Error Codes
| Code | Meaning | Schema / Content |
|---|---|---|
| `200` | Successful Response | `AdminOverviewResponse` (application/json) |
| `422` | Validation Error | `HTTPValidationError` (application/json) |

---

### `GET /admin/queries`
**Tags**: Admin Dashboard
**Description**: Get Admin Queries

#### Parameters
| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `page` | query | No | `integer` | Page number, 1-indexed |
| `limit` | query | No | `integer` | Items per page |
| `search` | query | No | `string` | Search prompt, SQL, dataset name, or user email |
| `user_id` | query | No | `string` | Filter by user ID |
| `dataset_id` | query | No | `string` | Filter by dataset ID |
| `status` | query | No | `string` | Filter by status (SUCCESS, SQL_REJECTED, etc.) |
| `start_date` | query | No | `string` | Start date filter YYYY-MM-DD |
| `end_date` | query | No | `string` | End date filter YYYY-MM-DD |
| `authorization` | header | No | `string` |  |

#### Responses & Error Codes
| Code | Meaning | Schema / Content |
|---|---|---|
| `200` | Successful Response | `AdminQueryListResponse` (application/json) |
| `422` | Validation Error | `HTTPValidationError` (application/json) |

---

### `GET /admin/transactions`
**Tags**: Admin Dashboard
**Description**: Get Admin Transactions

#### Parameters
| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `page` | query | No | `integer` | Page number, 1-indexed |
| `limit` | query | No | `integer` | Items per page |
| `search` | query | No | `string` | Search description or user email |
| `user_id` | query | No | `string` | Filter by user ID |
| `transaction_type` | query | No | `string` | Filter by transaction type |
| `start_date` | query | No | `string` | Start date filter YYYY-MM-DD |
| `end_date` | query | No | `string` | End date filter YYYY-MM-DD |
| `authorization` | header | No | `string` |  |

#### Responses & Error Codes
| Code | Meaning | Schema / Content |
|---|---|---|
| `200` | Successful Response | `AdminTransactionListResponse` (application/json) |
| `422` | Validation Error | `HTTPValidationError` (application/json) |

---

### `GET /admin/users`
**Tags**: Admin Dashboard
**Description**: Get Admin Users

#### Parameters
| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `page` | query | No | `integer` | Page number, 1-indexed |
| `limit` | query | No | `integer` | Items per page |
| `search` | query | No | `string` | Search by user name or email |
| `role` | query | No | `string` | Filter by role: admin, user, all |
| `sort_by` | query | No | `string` | Sort by: created_at, credits, reputation_score, full_name |
| `sort_order` | query | No | `string` | Sort order: asc, desc |
| `authorization` | header | No | `string` |  |

#### Responses & Error Codes
| Code | Meaning | Schema / Content |
|---|---|---|
| `200` | Successful Response | `AdminUserListResponse` (application/json) |
| `422` | Validation Error | `HTTPValidationError` (application/json) |

---

### `GET /admin/users/{user_id}`
**Tags**: Admin Dashboard
**Description**: Get Admin User Detail

#### Parameters
| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `user_id` | path | Yes | `string` |  |
| `authorization` | header | No | `string` |  |

#### Responses & Error Codes
| Code | Meaning | Schema / Content |
|---|---|---|
| `200` | Successful Response | `AdminUserDetailResponse` (application/json) |
| `422` | Validation Error | `HTTPValidationError` (application/json) |

---

### `POST /auth/login`
**Tags**: Authentication
**Description**: Login

#### Request Body
- **Content-Type**: `application/json`
- **Schema**: `UserLoginRequest`

#### Responses & Error Codes
| Code | Meaning | Schema / Content |
|---|---|---|
| `200` | Successful Response | `AuthTokenResponse` (application/json) |
| `422` | Validation Error | `HTTPValidationError` (application/json) |

---

### `GET /auth/me`
**Tags**: Authentication
**Description**: Get Me

#### Parameters
| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `authorization` | header | No | `string` |  |

#### Responses & Error Codes
| Code | Meaning | Schema / Content |
|---|---|---|
| `200` | Successful Response | `UserResponse` (application/json) |
| `422` | Validation Error | `HTTPValidationError` (application/json) |

---

### `POST /auth/register`
**Tags**: Authentication
**Description**: Register

#### Request Body
- **Content-Type**: `application/json`
- **Schema**: `UserRegisterRequest`

#### Responses & Error Codes
| Code | Meaning | Schema / Content |
|---|---|---|
| `201` | Successful Response | `AuthTokenResponse` (application/json) |
| `422` | Validation Error | `HTTPValidationError` (application/json) |

---

### `POST /credits/redeem`
**Tags**: Credits & Rewards
**Description**: Redeem Credits

#### Request Body
- **Content-Type**: `application/json`
- **Schema**: `RedeemRequest`

#### Parameters
| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `authorization` | header | No | `string` |  |

#### Responses & Error Codes
| Code | Meaning | Schema / Content |
|---|---|---|
| `200` | Successful Response | `RedeemResponse` (application/json) |
| `422` | Validation Error | `HTTPValidationError` (application/json) |

---

### `GET /credits/transactions`
**Tags**: Credits & Rewards
**Description**: Get User Transactions

#### Parameters
| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `authorization` | header | No | `string` |  |

#### Responses & Error Codes
| Code | Meaning | Schema / Content |
|---|---|---|
| `200` | Successful Response | `array` (application/json) |
| `422` | Validation Error | `HTTPValidationError` (application/json) |

---

### `GET /datasets`
**Tags**: Datasets
**Description**: List Datasets

#### Parameters
| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `domain` | query | No | `string` |  |

#### Responses & Error Codes
| Code | Meaning | Schema / Content |
|---|---|---|
| `200` | Successful Response | `DatasetListResponse` (application/json) |
| `422` | Validation Error | `HTTPValidationError` (application/json) |

---

### `POST /datasets/search`
**Tags**: Datasets
**Description**: Search Datasets

#### Request Body
- **Content-Type**: `application/json`
- **Schema**: `SearchRequest`

#### Responses & Error Codes
| Code | Meaning | Schema / Content |
|---|---|---|
| `200` | Successful Response | `SearchResponse` (application/json) |
| `422` | Validation Error | `HTTPValidationError` (application/json) |

---

### `GET /datasets/search`
**Tags**: Datasets
**Description**: Search Datasets Get

#### Parameters
| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `q` | query | Yes | `string` |  |
| `domain` | query | No | `string` |  |
| `limit` | query | No | `integer` |  |

#### Responses & Error Codes
| Code | Meaning | Schema / Content |
|---|---|---|
| `200` | Successful Response | `SearchResponse` (application/json) |
| `422` | Validation Error | `HTTPValidationError` (application/json) |

---

### `POST /datasets/upload`
**Tags**: Datasets
**Description**: Upload Dataset

#### Request Body
- **Content-Type**: `multipart/form-data`
- **Schema**: `Body_upload_dataset_datasets_upload_post`

#### Parameters
| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `authorization` | header | No | `string` |  |

#### Responses & Error Codes
| Code | Meaning | Schema / Content |
|---|---|---|
| `201` | Successful Response | `DatasetDetailResponse` (application/json) |
| `422` | Validation Error | `HTTPValidationError` (application/json) |

---

### `GET /datasets/{dataset_id}`
**Tags**: Datasets
**Description**: Get Dataset

#### Parameters
| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `dataset_id` | path | Yes | `string` |  |

#### Responses & Error Codes
| Code | Meaning | Schema / Content |
|---|---|---|
| `200` | Successful Response | `DatasetDetailResponse` (application/json) |
| `422` | Validation Error | `HTTPValidationError` (application/json) |

---

### `GET /datasets/{dataset_id}/evaluation`
**Tags**: Datasets
**Description**: Get Dataset Evaluation

#### Parameters
| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `dataset_id` | path | Yes | `string` |  |

#### Responses & Error Codes
| Code | Meaning | Schema / Content |
|---|---|---|
| `200` | Successful Response | `EvaluationResponse` (application/json) |
| `422` | Validation Error | `HTTPValidationError` (application/json) |

---

### `POST /datasets/{dataset_id}/improve`
**Tags**: Datasets
**Description**: Improve Dataset

#### Request Body
- **Content-Type**: `application/json`
- **Schema**: `DatasetImproveRequest`

#### Parameters
| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `dataset_id` | path | Yes | `string` |  |
| `authorization` | header | No | `string` |  |

#### Responses & Error Codes
| Code | Meaning | Schema / Content |
|---|---|---|
| `200` | Successful Response | `DatasetImproveResponse` (application/json) |
| `422` | Validation Error | `HTTPValidationError` (application/json) |

---

### `POST /datasets/{dataset_id}/unlock`
**Tags**: Datasets
**Description**: Unlock Dataset

#### Parameters
| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `dataset_id` | path | Yes | `string` |  |
| `authorization` | header | No | `string` |  |

#### Responses & Error Codes
| Code | Meaning | Schema / Content |
|---|---|---|
| `200` | Successful Response | `DatasetUnlockResponse` (application/json) |
| `422` | Validation Error | `HTTPValidationError` (application/json) |

---

### `GET /health`
**Tags**: Health
**Description**: Health Check

#### Responses & Error Codes
| Code | Meaning | Schema / Content |
|---|---|---|
| `200` | Successful Response | `HealthResponse` (application/json) |

---

### `GET /me`
**Tags**: Authentication
**Description**: Get Me

#### Parameters
| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `authorization` | header | No | `string` |  |

#### Responses & Error Codes
| Code | Meaning | Schema / Content |
|---|---|---|
| `200` | Successful Response | `UserResponse` (application/json) |
| `422` | Validation Error | `HTTPValidationError` (application/json) |

---

### `GET /me/stats`
**Tags**: User Statistics
**Description**: Get User Stats

#### Parameters
| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `authorization` | header | No | `string` |  |

#### Responses & Error Codes
| Code | Meaning | Schema / Content |
|---|---|---|
| `200` | Successful Response | `UserStatsResponse` (application/json) |
| `422` | Validation Error | `HTTPValidationError` (application/json) |

---

### `POST /query`
**Tags**: Query & Analysis
**Description**: Execute Query

#### Request Body
- **Content-Type**: `application/json`
- **Schema**: `QueryRequest`

#### Parameters
| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `authorization` | header | No | `string` |  |

#### Responses & Error Codes
| Code | Meaning | Schema / Content |
|---|---|---|
| `200` | Successful Response | `QueryResponse` (application/json) |
| `422` | Validation Error | `HTTPValidationError` (application/json) |

---

### `GET /query/history`
**Tags**: Query & Analysis
**Description**: Get Query History

#### Parameters
| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `page` | query | No | `integer` | Page number, 1-indexed |
| `limit` | query | No | `integer` | Items per page |
| `status` | query | No | `string` | Filter by status (SUCCESS, SQL_REJECTED, INSUFFICIENT_CREDITS, All) |
| `search` | query | No | `string` | Search term for prompt, dataset name, or SQL |
| `user_id` | query | No | `string` | Ignored: caller cannot access another user's history |
| `authorization` | header | No | `string` |  |

#### Responses & Error Codes
| Code | Meaning | Schema / Content |
|---|---|---|
| `200` | Successful Response | `QueryHistoryResponse` (application/json) |
| `422` | Validation Error | `HTTPValidationError` (application/json) |

---

### `POST /redeem`
**Tags**: Credits & Rewards
**Description**: Redeem Credits

#### Request Body
- **Content-Type**: `application/json`
- **Schema**: `RedeemRequest`

#### Parameters
| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `authorization` | header | No | `string` |  |

#### Responses & Error Codes
| Code | Meaning | Schema / Content |
|---|---|---|
| `200` | Successful Response | `RedeemResponse` (application/json) |
| `422` | Validation Error | `HTTPValidationError` (application/json) |

---

### `POST /search`
**Tags**: Datasets
**Description**: Search Datasets

#### Request Body
- **Content-Type**: `application/json`
- **Schema**: `SearchRequest`

#### Responses & Error Codes
| Code | Meaning | Schema / Content |
|---|---|---|
| `200` | Successful Response | `SearchResponse` (application/json) |
| `422` | Validation Error | `HTTPValidationError` (application/json) |

---

## Standard Error Codes & Handling

| HTTP Code | Error | Resolution |
|---|---|---|
| `400 Bad Request` | Missing file, duplicate email, or invalid parameters | Check request parameters and payload structure. |
| `401 Unauthorized` | Missing or invalid `Authorization: Bearer <token>` header | Login to obtain a valid access token and include it in request headers. |
| `402 Payment Required / Insufficient Balance` | Insufficient credit balance | Upload more datasets to earn credits or top up. |
| `404 Not Found` | Dataset or evaluation ID not found | Verify resource ID exists in the system. |
| `422 Unprocessable Entity` | Schema validation error (e.g. empty CSV or invalid types) | Inspect validation message and ensure payload matches schema. |
| `500 Internal Server Error` | Unexpected backend failure | Check backend logs and retry. |
