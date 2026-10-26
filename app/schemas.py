from typing import List, Dict, Any, Optional
from pydantic import BaseModel, EmailStr, Field, ConfigDict, model_validator


# Health Check Schema
class HealthResponse(BaseModel):
    status: str = Field(default="ok", description="Server health status")
    cors_regex: bool = Field(description="Whether CORS_ORIGIN_REGEX is enabled")
    embeddings: bool = Field(description="Whether EMBEDDINGS_ENABLED is true")
    version: str = Field(default="1.0.0", description="API Version")


# Auth Schemas
class UserRegisterRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255, description="User email address")
    password: str = Field(min_length=6, description="User password")
    full_name: str = Field(min_length=1, description="Full name")

class UserLoginRequest(BaseModel):
    email: str = Field(description="User email address")
    password: str = Field(description="User password")

class UserResponse(BaseModel):
    id: str
    email: str
    full_name: str
    credits: int
    reputation_score: int = Field(default=50, description="Persisted user reputation score (0-100)")
    is_admin: bool = Field(default=False, description="Whether the user is an authorized platform administrator")
    created_at: str

class AuthTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


# Dataset & Evaluation Schemas
class DatasetDetailResponse(BaseModel):
    model_config = {"populate_by_name": True}
    
    id: str
    user_id: str
    name: str
    filename: str
    domain: str
    rows_count: int
    columns_count: int
    schema_metadata: Dict[str, Any] = Field(default_factory=dict, alias="schema_json")
    content_summary: str
    unlock_price: int = Field(default=10, description="Dataset-specific one-time marketplace unlock price")
    unlocked_by: List[str] = Field(default_factory=list, description="User IDs that have unlocked this dataset")
    created_at: str
    quality_score: Optional[float] = None
    domain_relevance_score: Optional[float] = None
    overall_score: Optional[float] = None
    credits_awarded: Optional[int] = None


class DatasetListResponse(BaseModel):
    datasets: List[DatasetDetailResponse]
    total: int

class EvaluationResponse(BaseModel):
    id: str
    dataset_id: str
    status: str = Field(description="Evaluation status: pending, processing, completed, failed")
    progress: int = Field(description="Progress percentage from 0 to 100")
    quality_score: float = Field(description="Overall quality score 0-100")
    schema_fidelity_score: float = Field(description="Schema fidelity score 0-100")
    completeness_score: float = Field(description="Completeness score 0-100")
    domain_relevance_score: float = Field(description="Domain relevance score 0-100")
    overall_score: float = Field(description="Composite score 0-100")
    credits_awarded: int = Field(description="Credits awarded for this dataset")
    error_message: Optional[str] = None
    updated_at: str
    created_at: str


# Search & Query Schemas
class SearchRequest(BaseModel):
    query: str = Field(min_length=1, description="Search query string")
    domain: Optional[str] = Field(default=None, description="Optional domain filter")
    limit: int = Field(default=10, ge=1, le=100, description="Max results")

class SearchItem(BaseModel):
    dataset_id: str
    name: str
    domain: str
    score: float
    summary: str
    rows_count: int
    unlock_price: int = Field(default=10, description="Dataset-specific unlock price in credits")

class SearchResponse(BaseModel):
    query: str
    results: List[SearchItem]
    total: int
    method: str = Field(description="Search algorithm used (embeddings or tfidf_hybrid)")

class QueryRequest(BaseModel):
    query: str = Field(min_length=1, description="Natural language question")
    dataset_id: Optional[str] = Field(default=None, description="Target dataset ID or cross-catalog")

class QueryResponse(BaseModel):
    query: str
    answer: str
    matching_datasets: List[str]
    records_analyzed: int
    relevance_score: float
    method: str
    sql_query: Optional[str] = Field(default=None, description="Generated and executed SQL query")
    columns: Optional[List[str]] = Field(default=None, description="Column names returned by the query")
    results: Optional[List[Dict[str, Any]]] = Field(default=None, description="Actual data rows returned from DuckDB")
    credits_charged: Optional[int] = Field(default=None, description="Credits charged for this query")


class QueryHistoryItem(BaseModel):
    id: str
    user_id: str
    dataset_id: Optional[str] = None
    dataset_name: Optional[str] = "Cross-Catalog"
    natural_prompt: str
    generated_sql: Optional[str] = None
    rows_returned: int = 0
    execution_time_ms: int = 0
    status: str = "SUCCESS"
    credits_charged: int = 0
    timestamp: str
    error_message: Optional[str] = None

    # Frontend-friendly camelCase fields
    userId: Optional[str] = None
    datasetId: Optional[str] = None
    datasetName: Optional[str] = None
    naturalPrompt: Optional[str] = None
    generatedSql: Optional[str] = None
    rowsReturned: Optional[int] = None
    executionTimeMs: Optional[int] = None
    creditsCharged: Optional[int] = None

    model_config = ConfigDict(populate_by_name=True)

    @model_validator(mode="after")
    def populate_camel_case(self):
        if self.userId is None:
            self.userId = self.user_id
        if self.datasetId is None:
            self.datasetId = self.dataset_id
        if self.datasetName is None:
            self.datasetName = self.dataset_name
        if self.naturalPrompt is None:
            self.naturalPrompt = self.natural_prompt
        if self.generatedSql is None:
            self.generatedSql = self.generated_sql
        if self.rowsReturned is None:
            self.rowsReturned = self.rows_returned
        if self.executionTimeMs is None:
            self.executionTimeMs = self.execution_time_ms
        if self.creditsCharged is None:
            self.creditsCharged = self.credits_charged
        return self


class QueryHistoryResponse(BaseModel):
    items: List[QueryHistoryItem]
    total: int
    page: int
    limit: int
    has_more: bool


# Credit & Redemption Schemas
class RedeemRequest(BaseModel):
    amount: int = Field(gt=0, description="Amount of credits to redeem (must be > 0)")
    payout_method: str = Field(min_length=2, description="Payout method (e.g. upi, paypal, bank_transfer)")
    destination: str = Field(min_length=3, description="Payout destination address/account")

class TransactionItem(BaseModel):
    id: str
    user_id: str
    amount: int
    transaction_type: str
    description: str
    status: str
    created_at: str

class RedeemResponse(BaseModel):
    success: bool
    redeemed_credits: int
    cash_value_usd: float
    remaining_balance: int
    transaction_id: str
    message: str


# User Stats Schema
class UserStatsResponse(BaseModel):
    user_id: str
    email: str
    credits_balance: int
    reputation_score: int
    datasets_uploaded: int
    total_evaluations_completed: int
    average_quality_score: float
    recent_transactions: List[TransactionItem]


# Dataset Unlock & Improvement Schemas
class DatasetUnlockResponse(BaseModel):
    dataset_id: str
    unlocked: bool
    already_unlocked: bool
    credits_charged: int
    remaining_balance: int
    message: str

class DatasetImproveRequest(BaseModel):
    new_quality_score: float = Field(ge=0.0, le=100.0, description="Proposed quality score")
    new_relevance_score: float = Field(ge=0.0, le=100.0, description="Proposed relevance score")
    changes_summary: str = Field(min_length=5, description="Summary of schema or data enhancements")

class DatasetImproveResponse(BaseModel):
    dataset_id: str
    version: str
    previous_overall_score: float
    new_overall_score: float
    delta_score: float
    improvement_credits_awarded: int
    new_reputation_score: int
    changes_summary: str
    created_at: str


# ==============================================================================
# Admin Dashboard & Governance Schemas
# ==============================================================================

class AdminActivityItem(BaseModel):
    id: str
    type: str = Field(description="USER_REGISTER, DATASET_UPLOAD, QUERY_EXECUTION, CREDIT_TRANSACTION")
    description: str
    user_id: Optional[str] = None
    user_email: Optional[str] = None
    status: Optional[str] = "SUCCESS"
    timestamp: str


class AdminOverviewResponse(BaseModel):
    total_users: int
    total_datasets: int
    total_queries: int
    total_queries_successful: int
    total_queries_failed: int
    total_credits_issued: int
    total_credits_spent: int
    net_credit_liability: int
    recent_activity: List[AdminActivityItem]


class AdminUserItem(BaseModel):
    id: str
    email: str
    full_name: str
    credits: int
    reputation_score: int
    is_admin: bool
    account_status: str = "Active"
    datasets_count: int = 0
    queries_count: int = 0
    created_at: str


class AdminUserListResponse(BaseModel):
    items: List[AdminUserItem]
    total: int
    page: int
    limit: int
    has_more: bool


class AdminUserDatasetItem(BaseModel):
    id: str
    name: str
    filename: str
    domain: str
    rows_count: int
    columns_count: int
    quality_score: Optional[float] = None
    unlock_price: int = 10
    created_at: str


class AdminUserDetailResponse(BaseModel):
    id: str
    email: str
    full_name: str
    credits: int
    reputation_score: int
    is_admin: bool
    account_status: str
    created_at: str
    total_datasets: int
    total_queries: int
    total_credits_earned: int
    total_credits_spent: int
    datasets: List[AdminUserDatasetItem]
    recent_queries: List[Dict[str, Any]]
    recent_transactions: List[Dict[str, Any]]


class AdminDatasetItem(BaseModel):
    id: str
    title: str
    name: str
    filename: str
    owner_id: str
    owner_name: str
    owner_email: str
    domain: str
    rows_count: int
    columns_count: int
    quality_score: Optional[float] = None
    domain_relevance_score: Optional[float] = None
    overall_score: Optional[float] = None
    evaluation_status: Optional[str] = None
    credits_awarded: Optional[int] = None
    unlock_price: int = 10
    unlock_count: int = 0
    availability: str = "Available"
    content_summary: str
    created_at: str


class AdminDatasetListResponse(BaseModel):
    items: List[AdminDatasetItem]
    total: int
    page: int
    limit: int
    has_more: bool


class AdminQueryItem(BaseModel):
    id: str
    user_id: str
    user_email: str
    user_name: str
    natural_prompt: str
    dataset_id: Optional[str] = None
    dataset_name: Optional[str] = "Cross-Catalog"
    generated_sql: Optional[str] = None
    execution_status: str = "SUCCESS"
    execution_time_ms: int = 0
    rows_returned: int = 0
    credits_charged: int = 0
    error_message: Optional[str] = None
    timestamp: str


class AdminQueryListResponse(BaseModel):
    items: List[AdminQueryItem]
    total: int
    page: int
    limit: int
    has_more: bool


class AdminTransactionItem(BaseModel):
    id: str
    user_id: str
    user_email: str
    user_name: str
    transaction_type: str
    amount: int
    balance_impact: str
    associated_resource: Optional[str] = None
    description: str
    status: str
    timestamp: str


class AdminTransactionListResponse(BaseModel):
    items: List[AdminTransactionItem]
    total: int
    page: int
    limit: int
    has_more: bool


class AdminAuditLogItem(BaseModel):
    id: str
    admin_user_id: str
    admin_email: str
    action: str
    target_resource: Optional[str] = None
    details: Optional[str] = None
    ip_address: Optional[str] = None
    timestamp: str


class AdminAuditLogListResponse(BaseModel):
    items: List[AdminAuditLogItem]
    total: int
    page: int
    limit: int
    has_more: bool
