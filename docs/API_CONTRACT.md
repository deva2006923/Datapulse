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
| `GET` | `/health` | Health Check | No |
| `GET` | `/me` | Get Me | Optional / No |
| `GET` | `/me/stats` | Get User Stats | Optional / No |
| `POST` | `/query` | Execute Query | Optional / No |
| `POST` | `/redeem` | Redeem Credits | Optional / No |
| `POST` | `/search` | Search Datasets | Optional / No |

---

## Detailed Endpoint Specifications

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
