export type PageRoute =
  | 'landing'
  | 'login'
  | 'dashboard'
  | 'marketplace'
  | 'dataset-detail'
  | 'upload'
  | 'query'
  | 'query-history'
  | 'my-datasets'
  | 'versions-improve'
  | 'wallet'
  | 'profile'
  | 'admin'
  | '404';

export interface UserAccount {
  id: string;
  name: string;
  email: string;
  role: 'Contributor' | 'Data Analyst' | 'Admin';
  credits: number;
  reputationScore: number; // 0 - 100
  contributedDatasetIds: string[];
  unlockedDatasetIds: string[];
  joinedDate: string;
  isAdmin?: boolean;
}

export interface BackendUserResponse {
  id: string;
  email: string;
  full_name: string;
  credits: number;
  reputation_score?: number;
  is_admin?: boolean;
  created_at: string;
}

export interface AuthTokenResponse {
  access_token: string;
  token_type: string;
  user: BackendUserResponse;
}

export interface BackendDatasetDetail {
  id: string;
  user_id: string;
  name: string;
  filename: string;
  domain: string;
  rows_count: number;
  columns_count: number;
  schema_metadata?: Record<string, string>;
  schema_json?: Record<string, string>;
  content_summary: string;
  unlock_price?: number;
  unlocked_by?: string[];
  storage_available?: boolean;
  availability?: string;
  created_at: string;
  quality_score?: number;
  domain_relevance_score?: number;
  overall_score?: number;
  credits_awarded?: number;
  is_curated?: boolean;
  dataset_type?: 'curated' | 'community' | string;
  visibility?: 'public' | 'private' | string;
  source_name?: string | null;
  source_url?: string | null;
  license?: string | null;
  license_url?: string | null;
  retrieved_at?: string | null;
  ingestion_status?: string | null;
  sha256_checksum?: string | null;
  source_version?: string | null;
}


export interface BackendEvaluationResponse {
  id: string;
  dataset_id: string;
  status: string;
  progress: number;
  quality_score: number;
  schema_fidelity_score: number;
  completeness_score: number;
  domain_relevance_score: number;
  overall_score: number;
  credits_awarded: number;
  error_message?: string | null;
  updated_at: string;
  created_at: string;
}

export interface UserRegisterRequest {
  email: string;
  password: string;
  full_name: string;
}

export interface UserLoginRequest {
  email: string;
  password: string;
}

export interface SearchRequest {
  query: string;
  domain?: string;
  limit?: number;
}

export interface SearchItem {
  dataset_id: string;
  user_id?: string | null;
  name: string;
  filename?: string | null;
  domain: string;
  score: number;
  summary: string;
  rows_count: number;
  columns_count?: number | null;
  unlock_price?: number;
  unlocked_by?: string[];
  quality_score?: number | null;
  domain_relevance_score?: number | null;
  overall_score?: number | null;
  storage_available?: boolean | null;
  availability?: string | null;
  is_curated?: boolean;
  dataset_type?: 'curated' | 'community' | string;
  visibility?: 'public' | 'private' | string;
  license?: string | null;
  source_name?: string | null;
  created_at?: string | null;
}

export interface SearchResponse {
  query: string;
  results: SearchItem[];
  total: number;
  method: string;
}

export interface DatasetListResponse {
  datasets: BackendDatasetDetail[];
  total: number;
}

export interface QueryRequest {
  query: string;
  dataset_id?: string;
}

export interface QueryResponse {
  query: string;
  answer: string;
  matching_datasets: string[];
  records_analyzed: number;
  relevance_score: number;
  method: string;
  sql_query?: string | null;
  columns?: string[] | null;
  results?: Record<string, any>[] | null;
  credits_charged?: number | null;
  dataset_id?: string | null;
  dataset_name?: string | null;
}

export interface TransactionItem {
  id: string;
  user_id: string;
  amount: number;
  transaction_type: string;
  description: string;
  status: string;
  created_at: string;
}

export interface RedeemRequest {
  amount: number;
  payout_method: string;
  destination: string;
}

export interface RedeemResponse {
  success: boolean;
  redeemed_credits: number;
  cash_value_usd: number;
  remaining_balance: number;
  transaction_id: string;
  message: string;
}

export interface UserStatsResponse {
  user_id: string;
  email: string;
  credits_balance: number;
  reputation_score?: number;
  datasets_uploaded: number;
  total_evaluations_completed: number;
  average_quality_score: number;
  recent_transactions: TransactionItem[];
}

export interface DatasetUnlockResponse {
  dataset_id: string;
  unlocked: boolean;
  already_unlocked: boolean;
  credits_charged: number;
  remaining_balance: number;
  message: string;
}

export interface DatasetImproveRequest {
  new_quality_score: number;
  new_relevance_score: number;
  changes_summary: string;
}

export interface DatasetImproveResponse {
  dataset_id: string;
  version: string;
  previous_overall_score: number;
  new_overall_score: number;
  delta_score: number;
  improvement_credits_awarded: number;
  new_reputation_score: number;
  changes_summary: string;
  created_at: string;
}

export interface ColumnDefinition {
  name: string;
  type: string;
  nullCount: number;
  nullPct: number;
  distinctCount: number;
  synonyms: string[];
  description?: string;
}

export interface DatasetVersionEntry {
  version: string;
  date: string;
  author: string;
  quality: number;
  relevance: number;
  changesSummary: string;
}

export interface AppDataset {
  id: string;
  name: string;
  title: string;
  description: string;
  domain: string; // 'Healthcare' | 'Telecom' | 'Retail' | 'Finance' | 'Education' | 'Technology' | 'General'
  format: 'csv' | 'xlsx' | 'parquet' | 'json';
  authorId: string;
  authorName: string;
  cost: number; // typically 20 credits
  unlockPrice?: number;
  qualityScore: number; // 0 - 100
  relevanceScore: number; // 0 - 100
  overallScore: number; // (qualityScore + relevanceScore) / 2
  status: 'APPROVED' | 'REJECTED';
  rejectionReasons?: string;
  tags: string[];
  license: string; // 'MIT' | 'Open Data Commons' | 'CC-BY-4.0' | 'Apache 2.0'
  usageCount: number;
  qualityBreakdown: {
    completeness: number;
    validity: number;
    uniqueness: number;
    consistency: number;
  };
  rowCount: number;
  columnCount: number;
  columns: ColumnDefinition[];
  previewRows: Record<string, any>[];
  createdAt: string;
  currentVersion: string;
  versionHistory: DatasetVersionEntry[];
  unlockedBy: string[]; // List of userIds who unlocked this dataset
  storageAvailable?: boolean;
  availability?: string;
  sampleQueries: string[];
  matchScore?: number;
  isCurated?: boolean;
  datasetType?: 'curated' | 'community';
  visibility?: 'public' | 'private';
  sourceName?: string;
  sourceUrl?: string;
  licenseUrl?: string;
  retrievedAt?: string;
  ingestionStatus?: string;
  sha256Checksum?: string;
  sourceVersion?: string;
}


export interface WalletTransaction {
  id: string;
  userId: string;
  type:
    | 'SIGNUP_BONUS'
    | 'UPLOAD_REWARD'
    | 'QUERY_CHARGE'
    | 'CONTRIBUTOR_ROYALTY'
    | 'IMPROVEMENT_REWARD'
    | 'REDEMPTION'
    | 'MANUAL_RELOAD';
  amount: number; // positive for earned (+), negative for spent (-)
  description: string;
  timestamp: string; // YYYY-MM-DD or formatted
  rupeeValue?: number;
}

export interface QueryHistoryItem {
  id: string;
  userId: string;
  datasetId: string;
  datasetName: string;
  naturalPrompt: string;
  generatedSql: string;
  rowsReturned: number;
  status: 'SUCCESS' | 'SQL_REJECTED' | 'INSUFFICIENT_CREDITS';
  creditsCharged: number;
  timestamp: string;
  executionTimeMs: number;
}

export interface QueryHistoryResponse {
  items: QueryHistoryItem[];
  total: number;
  page: number;
  limit: number;
  has_more: boolean;
}

export interface ToastMessage {
  id: string;
  title: string;
  message: string;
  tone: 'cyan' | 'rose' | 'amber' | 'emerald' | 'violet';
  timestamp: Date;
  action?: {
    label: string;
    onClick: () => void;
  };
}

// Admin Dashboard Types
export interface AdminActivityItem {
  id: string;
  type:
    | 'USER_REGISTER'
    | 'USER_LOGIN'
    | 'DATASET_UPLOAD'
    | 'QUERY_EXECUTION'
    | 'CREDIT_TRANSACTION'
    | 'DATASET_IMPROVE'
    | 'DATASET_UNLOCK';
  description: string;
  user_id?: string;
  user_email?: string;
  dataset_id?: string;
  status?: string;
  timestamp: string;
}

export interface AdminOverview {
  total_users: number;
  active_users?: number;
  total_datasets: number;
  total_queries: number;
  total_queries_successful: number;
  total_queries_failed: number;
  query_success_rate?: number;
  total_credits_issued: number;
  total_credits_spent: number;
  total_credits_refunded?: number;
  net_credit_movement?: number;
  net_credit_liability: number;
  total_credits_in_circulation?: number;
  recent_activity: AdminActivityItem[];
}

export interface AdminTrendPoint {
  bucket: string;
  count: number;
}

export interface AdminQueryTrendPoint {
  bucket: string;
  total: number;
  successful: number;
  failed: number;
}

export interface AdminCreditTrendPoint {
  bucket: string;
  awarded: number;
  spent: number;
  refunded: number;
  net: number;
}

export interface AdminActiveUserRank {
  user_id: string;
  full_name: string;
  email: string;
  query_count: number;
  successful_queries: number;
  failed_queries: number;
  last_activity?: string | null;
}

export interface AdminContributorRank {
  user_id: string;
  full_name: string;
  email: string;
  dataset_count: number;
  total_rows: number;
  avg_quality_score?: number | null;
}

export interface AdminQueriedDatasetRank {
  dataset_id: string;
  dataset_name: string;
  domain: string;
  owner_id?: string | null;
  owner_name?: string | null;
  query_count: number;
  successful_queries: number;
  unlock_count: number;
  quality_score?: number | null;
}

export interface AdminAnalyticsKpis {
  total_users: number;
  users_in_period: number;
  users_delta_pct?: number | null;
  active_users: number;
  active_users_delta_pct?: number | null;
  total_datasets: number;
  datasets_in_period: number;
  datasets_delta_pct?: number | null;
  total_queries: number;
  queries_successful: number;
  queries_failed: number;
  query_success_rate: number;
  queries_delta_pct?: number | null;
  total_credits_issued: number;
  total_credits_spent: number;
  total_credits_refunded: number;
  net_credit_movement: number;
  net_credit_liability: number;
  total_credits_in_circulation?: number;
  credits_issued_delta_pct?: number | null;
  credits_spent_delta_pct?: number | null;
  credits_earned_by_owners: number;
  query_fees_collected: number;
}

export interface AdminAnalyticsResponse {
  range: string;
  start_date?: string | null;
  end_date?: string | null;
  granularity: 'daily' | 'weekly' | 'monthly';
  comparison_label?: string | null;
  kpis: AdminAnalyticsKpis;
  user_registration_trend: AdminTrendPoint[];
  dataset_upload_trend: AdminTrendPoint[];
  query_activity_trend: AdminQueryTrendPoint[];
  credit_movement_trend: AdminCreditTrendPoint[];
  most_active_users: AdminActiveUserRank[];
  most_contributing_users: AdminContributorRank[];
  most_queried_datasets: AdminQueriedDatasetRank[];
  data_limitations: string[];
}

export interface AdminUserItem {
  id: string;
  email: string;
  full_name: string;
  credits: number;
  reputation_score: number;
  is_admin: boolean;
  account_status: string;
  is_active?: boolean;
  datasets_count: number;
  queries_count: number;
  last_activity?: string | null;
  created_at: string;
}

export interface AdminUserListResponse {
  items: AdminUserItem[];
  total: number;
  page: number;
  limit: number;
  has_more: boolean;
}

export interface AdminUserDatasetItem {
  id: string;
  name: string;
  filename: string;
  domain: string;
  rows_count: number;
  columns_count: number;
  quality_score?: number | null;
  unlock_price: number;
  query_count?: number;
  basic_upload_reward?: number;
  quality_reward?: number;
  improvement_rewards?: number;
  created_at: string;
  version_count?: number;
  availability?: string;
  versions?: Record<string, any>[];
}

export interface AdminUserDetail {
  id: string;
  email: string;
  full_name: string;
  credits: number;
  reputation_score: number;
  is_admin: boolean;
  account_status: string;
  created_at: string;
  last_activity?: string | null;
  total_datasets: number;
  total_queries: number;
  total_queries_successful?: number;
  total_queries_failed?: number;
  query_success_rate?: number;
  total_credits_earned: number;
  total_credits_spent: number;
  total_credits_refunded?: number;
  total_unlocks?: number;
  total_improvements?: number;
  datasets: AdminUserDatasetItem[];
  recent_queries: Record<string, any>[];
  recent_transactions: Record<string, any>[];
}

export interface AdminDatasetItem {
  id: string;
  title: string;
  name: string;
  filename: string;
  owner_id: string;
  owner_name: string;
  owner_email: string;
  domain: string;
  rows_count: number;
  columns_count: number;
  quality_score?: number | null;
  domain_relevance_score?: number | null;
  overall_score?: number | null;
  evaluation_status?: string | null;
  credits_awarded?: number | null;
  basic_upload_reward?: number;
  quality_reward?: number;
  improvement_rewards?: number;
  unlock_price: number;
  unlock_count: number;
  query_count?: number;
  version_count?: number;
  versions?: Record<string, any>[];
  availability: string;
  content_summary: string;
  created_at: string;
}

export interface AdminDatasetListResponse {
  items: AdminDatasetItem[];
  total: number;
  page: number;
  limit: number;
  has_more: boolean;
  available_domains?: string[];
}

export interface AdminDatasetDetail {
  id: string;
  name: string;
  filename: string;
  domain: string;
  owner_id: string;
  owner_name: string;
  owner_email: string;
  rows_count: number;
  columns_count: number;
  schema_columns: Array<{ name: string; type: string }>;
  content_summary: string;
  unlock_price: number;
  unlock_count: number;
  query_count: number;
  successful_queries: number;
  failed_queries: number;
  unique_queriers: number;
  availability: string;
  created_at: string;
  evaluation?: {
    id: string;
    status: string;
    progress: number;
    quality_score: number;
    schema_fidelity_score: number;
    completeness_score: number;
    domain_relevance_score: number;
    overall_score: number;
    credits_awarded: number;
    error_message?: string | null;
    updated_at: string;
    created_at: string;
  } | null;
  basic_upload_reward: number;
  quality_reward: number;
  improvement_rewards: number;
  total_rewards: number;
  version_count: number;
  versions: Array<{
    version: string;
    quality_score: number;
    relevance_score: number;
    overall_score: number;
    delta_score: number;
    credits_awarded: number;
    changes_summary: string;
    created_at: string;
  }>;
  recent_queries: Array<{
    id: string;
    user_id: string;
    user_name: string;
    user_email: string;
    natural_prompt: string;
    status: string;
    execution_time_ms: number;
    rows_returned: number;
    credits_charged: number;
    timestamp: string;
  }>;
}

export interface AdminQueryItem {
  id: string;
  user_id: string;
  user_email: string;
  user_name: string;
  natural_prompt: string;
  dataset_id?: string | null;
  dataset_name?: string | null;
  generated_sql?: string | null;
  execution_status: string;
  execution_time_ms: number;
  rows_returned: number;
  credits_charged: number;
  credits_refunded?: number;
  error_message?: string | null;
  timestamp: string;
}

export interface AdminQueryListResponse {
  items: AdminQueryItem[];
  total: number;
  page: number;
  limit: number;
  has_more: boolean;
  summary?: {
    total_queries: number;
    successful_queries: number;
    failed_queries: number;
    success_rate: number;
    avg_execution_time_ms: number;
    total_credits_charged: number;
  } | null;
}

export interface AdminTransactionItem {
  id: string;
  user_id: string;
  user_email: string;
  user_name: string;
  sender?: string;
  sender_id?: string | null;
  receiver?: string;
  receiver_id?: string | null;
  transaction_type: string;
  amount: number;
  balance_impact: string;
  balance_after?: number | null;
  associated_resource?: string | null;
  related_dataset_id?: string | null;
  related_dataset_name?: string | null;
  related_query_id?: string | null;
  description: string;
  status: string;
  timestamp: string;
}

export interface AdminTransactionListResponse {
  items: AdminTransactionItem[];
  total: number;
  page: number;
  limit: number;
  has_more: boolean;
  summary?: {
    total_issued: number;
    total_spent: number;
    net_movement: number;
    earned_by_owners: number;
    query_fees_collected: number;
    refunds_total: number;
  } | null;
}

export interface AdminAuditLogItem {
  id: string;
  admin_user_id: string;
  admin_email: string;
  action: string;
  target_resource?: string | null;
  details?: string | null;
  ip_address?: string | null;
  timestamp: string;
}

export interface AdminAuditLogListResponse {
  items: AdminAuditLogItem[];
  total: number;
  page: number;
  limit: number;
  has_more: boolean;
}

export interface AdminTimelineItem {
  id: string;
  type:
    | 'USER_REGISTER'
    | 'USER_LOGIN'
    | 'DATASET_UPLOAD'
    | 'QUERY_EXECUTION'
    | 'CREDIT_TRANSACTION'
    | 'DATASET_IMPROVE'
    | 'DATASET_UNLOCK'
    | 'ADMIN_AUDIT';
  title: string;
  description: string;
  timestamp: string;
  status: string;
  user_id?: string;
  user_email?: string;
  user_name?: string;
  dataset_id?: string;
  dataset_name?: string;
  related_query_id?: string | null;
  related_transaction_id?: string | null;
  metadata?: Record<string, any>;
}

export interface AdminTimelineResponse {
  items: AdminTimelineItem[];
  total: number;
  page: number;
  limit: number;
  has_more: boolean;
}
