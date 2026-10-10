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
}

export interface BackendUserResponse {
  id: string;
  email: string;
  full_name: string;
  credits: number;
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
  created_at: string;
  quality_score?: number;
  domain_relevance_score?: number;
  overall_score?: number;
  credits_awarded?: number;
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
  name: string;
  domain: string;
  score: number;
  summary: string;
  rows_count: number;
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
  datasets_uploaded: number;
  total_evaluations_completed: number;
  average_quality_score: number;
  recent_transactions: TransactionItem[];
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
  sampleQueries: string[];
  matchScore?: number;
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
