from typing import List, Dict, Any, Optional
from pydantic import BaseModel, EmailStr, Field


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
    created_at: str

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
    datasets_uploaded: int
    total_evaluations_completed: int
    average_quality_score: float
    recent_transactions: List[TransactionItem]
