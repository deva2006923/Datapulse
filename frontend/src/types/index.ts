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

export interface UserRegisterRequest {
  email: string;
  password: string;
  full_name: string;
}

export interface UserLoginRequest {
  email: string;
  password: string;
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
