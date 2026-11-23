import {
  AuthTokenResponse,
  BackendDatasetDetail,
  BackendEvaluationResponse,
  BackendUserResponse,
  DatasetListResponse,
  QueryRequest,
  QueryResponse,
  RedeemRequest,
  RedeemResponse,
  SearchRequest,
  SearchResponse,
  TransactionItem,
  UserLoginRequest,
  UserRegisterRequest,
  UserStatsResponse,
  DatasetUnlockResponse,
  DatasetImproveRequest,
  DatasetImproveResponse,
  QueryHistoryItem,
  QueryHistoryResponse,
  AdminOverview,
  AdminAnalyticsResponse,
  AdminUserListResponse,
  AdminUserDetail,
  AdminDatasetListResponse,
  AdminDatasetDetail,
  AdminQueryListResponse,
  AdminTransactionListResponse,
  AdminAuditLogListResponse,
  AdminTimelineResponse,
} from '../types';
import { backendQueryHistoryItemToQueryHistoryItem } from './datasetAdapter';

const TOKEN_STORAGE_KEY = 'datapulse_auth_token';

// Base API URL:
// - In production builds (Vercel), VITE_API_URL MUST be set to the hosted HTTPS backend URL.
// - In local development and tests, falls back cleanly to http://localhost:8000.
function resolveApiBaseUrl(): string {
  const configured = (import.meta.env.VITE_API_URL || '').trim();
  if (configured) {
    return configured.replace(/\/+$/, '');
  }
  if (import.meta.env.PROD) {
    console.error(
      '[DataPulse] VITE_API_URL is not configured for this production build. ' +
        'Set VITE_API_URL in Vercel Environment Variables to your hosted HTTPS backend URL.'
    );
    return '';
  }
  return 'http://localhost:8000';
}

export const API_BASE_URL = resolveApiBaseUrl();

export class ApiError extends Error {
  status: number;
  detail: any;

  constructor(message: string, status: number = 0, detail: any = null) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
  }
}

function parseErrorMessage(status: number, data: any): string {
  if (!data) {
    if (status === 401) return 'Incorrect email or password';
    if (status === 404) return 'Resource not found';
    if (status === 500) return 'Internal server error';
    return `Request failed with status ${status}`;
  }

  // Handle FastAPI string detail
  if (typeof data.detail === 'string') {
    return data.detail;
  }

  // Handle FastAPI / Pydantic 422 validation error array
  if (Array.isArray(data.detail)) {
    const messages = data.detail.map((err: any) => {
      const field = Array.isArray(err.loc) ? err.loc[err.loc.length - 1] : '';
      const fieldPrefix = field ? `${field}: ` : '';
      return `${fieldPrefix}${err.msg || 'Invalid value'}`;
    });
    return messages.join('. ');
  }

  if (data.message && typeof data.message === 'string') {
    return data.message;
  }

  return `Request failed (${status})`;
}

export function getStoredToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_STORAGE_KEY);
  } catch {
    return null;
  }
}

export function setStoredToken(token: string | null): void {
  try {
    if (token) {
      localStorage.setItem(TOKEN_STORAGE_KEY, token);
    } else {
      localStorage.removeItem(TOKEN_STORAGE_KEY);
    }
  } catch {
    // LocalStorage write failed or blocked
  }
}

export function clearStoredToken(): void {
  setStoredToken(null);
}

async function request<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  if (!API_BASE_URL) {
    throw new ApiError(
      'Backend API URL is not configured (VITE_API_URL missing in production environment).',
      0
    );
  }
  const normalizedPath = path.startsWith('/') ? path : `/${path}`;
  const url = `${API_BASE_URL}${normalizedPath}`;

  const headers: Record<string, string> = {
    Accept: 'application/json',
    ...(options.headers as Record<string, string>),
  };

  // Add JSON content type if payload is present and not FormData
  if (options.body && !(options.body instanceof FormData) && !headers['Content-Type']) {
    headers['Content-Type'] = 'application/json';
  }

  // Automatically attach Bearer token if available
  const token = getStoredToken();
  if (token && !headers['Authorization']) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  let response: Response;
  try {
    response = await fetch(url, {
      ...options,
      headers,
    });
  } catch (networkError: any) {
    throw new ApiError(
      `Unable to connect to backend server at ${API_BASE_URL}. Please ensure the backend is running.`,
      0,
      networkError
    );
  }

  let responseData: any = null;
  const contentType = response.headers.get('content-type') || '';
  if (contentType.includes('application/json')) {
    try {
      responseData = await response.json();
    } catch {
      responseData = null;
    }
  } else {
    try {
      responseData = await response.text();
    } catch {
      responseData = null;
    }
  }

  if (!response.ok) {
    // Clear expired/revoked bearer token on any authenticated endpoint returning 401
    const isAuthCredentialEndpoint =
      normalizedPath.startsWith('/auth/login') || normalizedPath.startsWith('/auth/register');
    if (response.status === 401 && !isAuthCredentialEndpoint) {
      const hadToken = !!getStoredToken();
      clearStoredToken();
      if (hadToken && typeof window !== 'undefined') {
        window.dispatchEvent(new CustomEvent('datapulse:session-expired'));
      }
    }

    const message = parseErrorMessage(response.status, responseData);
    throw new ApiError(message, response.status, responseData?.detail ?? responseData);
  }

  return responseData as T;
}

// Restrict dev demo account quick-switcher in production builds unless explicitly opted in
export const DEMO_ACCOUNTS_ENABLED: boolean =
  !import.meta.env.PROD || import.meta.env.VITE_ENABLE_DEMO_ACCOUNTS === 'true';

// Predefined demo credentials for Instant Demo Switcher buttons
export interface DemoAccountDefinition {
  key: 'demo-user' | 'alice' | 'bob';
  email: string;
  password: string;
  full_name: string;
  role: 'Contributor' | 'Data Analyst';
}

export const DEMO_ACCOUNTS: Record<'demo-user' | 'alice' | 'bob', DemoAccountDefinition> = {
  'demo-user': {
    key: 'demo-user',
    email: 'demo@datapulse.io',
    password: 'Password123!',
    full_name: 'Demo User',
    role: 'Contributor',
  },
  alice: {
    key: 'alice',
    email: 'alice@datapulse.io',
    password: 'Password123!',
    full_name: 'Alice Smith',
    role: 'Contributor',
  },
  bob: {
    key: 'bob',
    email: 'bob@datapulse.io',
    password: 'Password123!',
    full_name: 'Bob Miller',
    role: 'Data Analyst',
  },
};

export const api = {
  auth: {
    getToken: getStoredToken,
    setToken: setStoredToken,
    clearToken: clearStoredToken,

    async register(data: UserRegisterRequest): Promise<AuthTokenResponse> {
      const res = await request<AuthTokenResponse>('/auth/register', {
        method: 'POST',
        body: JSON.stringify(data),
      });
      if (res?.access_token) {
        setStoredToken(res.access_token);
      }
      return res;
    },

    async login(data: UserLoginRequest): Promise<AuthTokenResponse> {
      const res = await request<AuthTokenResponse>('/auth/login', {
        method: 'POST',
        body: JSON.stringify(data),
      });
      if (res?.access_token) {
        setStoredToken(res.access_token);
      }
      return res;
    },

    async getMe(): Promise<BackendUserResponse> {
      return request<BackendUserResponse>('/auth/me', {
        method: 'GET',
      });
    },

    logout(): void {
      const token = getStoredToken();
      clearStoredToken();
      if (token && API_BASE_URL) {
        // Best-effort server-side token revocation (non-blocking)
        fetch(`${API_BASE_URL}/auth/logout`, {
          method: 'POST',
          headers: {
            Accept: 'application/json',
            Authorization: `Bearer ${token}`,
          },
        }).catch(() => {});
      }
    },

    /**
     * Authenticates with real backend credentials for predefined demo accounts.
     * Tries login first; if account doesn't exist, automatically registers with backend.
     * Rejects unknown or generated keys to prevent session corruption.
     */
    async demoLogin(
      accountKey: 'demo-user' | 'alice' | 'bob' | string
    ): Promise<AuthTokenResponse> {
      const creds = DEMO_ACCOUNTS[accountKey as 'demo-user' | 'alice' | 'bob'];
      if (!creds) {
        throw new ApiError(
          `Invalid demo account key: '${accountKey}'. Only predefined demo accounts ('demo-user', 'alice', 'bob') are supported.`,
          400
        );
      }

      try {
        return await api.auth.login({
          email: creds.email,
          password: creds.password,
        });
      } catch (err: any) {
        // If not found or wrong credentials, register fresh account with exact credentials
        if (err?.status === 401 || err?.status === 404) {
          try {
            return await api.auth.register({
              email: creds.email,
              password: creds.password,
              full_name: creds.full_name,
            });
          } catch (regErr: any) {
            // If already registered concurrently, retry login once
            return await api.auth.login({
              email: creds.email,
              password: creds.password,
            });
          }
        }
        throw err;
      }
    },
  },

  datasets: {
    /**
     * Uploads a CSV dataset file to POST /datasets/upload using multipart/form-data.
     * Multipart fields expected by backend:
     * - file: File (.csv)
     * - domain: string (optional, defaults to "general")
     * - name: string (optional, defaults to filename without extension)
     * - visibility: 'public' | 'private' (optional, defaults to "public")
     */
    async upload(
      fileOrFormData: File | FormData,
      domain: string = 'general',
      name?: string,
      visibility: 'public' | 'private' = 'public'
    ): Promise<BackendDatasetDetail> {
      let body: FormData;
      if (fileOrFormData instanceof FormData) {
        body = fileOrFormData;
      } else {
        body = new FormData();
        body.append('file', fileOrFormData);
        if (domain) {
          body.append('domain', domain);
        }
        if (name) {
          body.append('name', name);
        }
        if (visibility) {
          body.append('visibility', visibility);
        }
      }

      const rawRes = await request<BackendDatasetDetail>('/datasets/upload', {
        method: 'POST',
        body,
      });

      const schema = rawRes?.schema_metadata || rawRes?.schema_json || {};
      const res: BackendDatasetDetail = {
        ...rawRes,
        schema_metadata: schema,
        schema_json: schema,
      };

      // If the upload response already provides evaluation metrics, return as-is
      if (res && res.id) {
        if (res.quality_score !== undefined && res.credits_awarded !== undefined) {
          return res;
        }

        // Check if evaluation was completed synchronously on backend
        try {
          const evalRes = await api.datasets.getEvaluation(res.id);
          if (evalRes) {
            return {
              ...res,
              quality_score: evalRes.quality_score,
              domain_relevance_score: evalRes.domain_relevance_score,
              overall_score: evalRes.overall_score,
              credits_awarded: evalRes.credits_awarded,
            };
          }
        } catch {
          // If evaluation is not yet ready or failed, return raw upload response
        }
      }

      return res;
    },

    /**
     * Retrieves the evaluation report for a given dataset ID.
     */
    async getEvaluation(datasetId: string): Promise<BackendEvaluationResponse> {
      return request<BackendEvaluationResponse>(`/datasets/${datasetId}/evaluation`, {
        method: 'GET',
      });
    },

    /**
     * Retrieves dataset details by ID.
     */
    async getDataset(datasetId: string): Promise<BackendDatasetDetail> {
      const data = await request<BackendDatasetDetail>(`/datasets/${datasetId}`, {
        method: 'GET',
      });
      const schema = data?.schema_metadata || data?.schema_json || {};
      return {
        ...data,
        schema_metadata: schema,
        schema_json: schema,
      };
    },

    /**
     * Lists datasets from GET /datasets, optionally filtered by domain and library source.
     */
    async list(
      domain?: string,
      source?: 'all' | 'mine' | 'curated' | 'community'
    ): Promise<DatasetListResponse> {
      const params = new URLSearchParams();
      if (domain && domain !== 'All') {
        params.set('domain', domain);
      }
      if (source && source !== 'all') {
        params.set('source', source);
      }
      const qs = params.toString();
      return request<DatasetListResponse>(`/datasets${qs ? `?${qs}` : ''}`, {
        method: 'GET',
      });
    },

    /**
     * Updates visibility ('public' | 'private') for an owner's community dataset.
     */
    async updateVisibility(
      datasetId: string,
      visibility: 'public' | 'private'
    ): Promise<BackendDatasetDetail> {
      return request<BackendDatasetDetail>(`/datasets/${datasetId}/visibility`, {
        method: 'PATCH',
        body: JSON.stringify({ visibility }),
      });
    },

    /**
     * Searches datasets via POST /datasets/search using vector embeddings / TF-IDF hybrid recommender.
     */
    async search(
      query: string,
      domain?: string,
      limit: number = 10
    ): Promise<SearchResponse> {
      const payload: SearchRequest = {
        query,
        domain: domain && domain !== 'All' ? domain.toLowerCase() : undefined,
        limit,
      };
      return request<SearchResponse>('/datasets/search', {
        method: 'POST',
        body: JSON.stringify(payload),
      });
    },

    /**
     * Unlocks a dataset via POST /datasets/:id/unlock (one-time purchase).
     */
    async unlock(datasetId: string): Promise<DatasetUnlockResponse> {
      return request<DatasetUnlockResponse>(`/datasets/${datasetId}/unlock`, {
        method: 'POST',
      });
    },

    /**
     * Submits version improvements via POST /datasets/:id/improve.
     */
    async improve(
      datasetId: string,
      data: DatasetImproveRequest
    ): Promise<DatasetImproveResponse> {
      return request<DatasetImproveResponse>(`/datasets/${datasetId}/improve`, {
        method: 'POST',
        body: JSON.stringify(data),
      });
    },
  },


  query: {
    /**
     * Executes a natural language query against DuckDB via POST /query.
     * Request schema: QueryRequest { query: string, dataset_id?: string }
     * Response schema: QueryResponse
     */
    async execute(
      queryText: string,
      datasetId?: string
    ): Promise<QueryResponse> {
      const payload: QueryRequest = {
        query: queryText,
        dataset_id: datasetId || undefined,
      };
      return request<QueryResponse>('/query', {
        method: 'POST',
        body: JSON.stringify(payload),
      });
    },

    /**
     * Retrieves the authenticated user's isolated query history from GET /query/history.
     * Guaranteed to only return records belonging to the authenticated user.
     */
    async getHistory(params?: {
      page?: number;
      limit?: number;
      status?: string;
      search?: string;
    }): Promise<QueryHistoryResponse> {
      const searchParams = new URLSearchParams();
      if (params?.page) searchParams.set('page', params.page.toString());
      if (params?.limit) searchParams.set('limit', params.limit.toString());
      if (params?.status && params.status !== 'All') searchParams.set('status', params.status);
      if (params?.search && params.search.trim()) searchParams.set('search', params.search.trim());

      const queryStr = searchParams.toString();
      const path = `/query/history${queryStr ? `?${queryStr}` : ''}`;

      const response = await request<{
        items: any[];
        total: number;
        page: number;
        limit: number;
        has_more: boolean;
      }>(path, {
        method: 'GET',
      });

      return {
        ...response,
        items: (response.items || []).map(backendQueryHistoryItemToQueryHistoryItem),
      };
    },
  },

  credits: {
    /**
     * Retrieves user credit transaction history via GET /credits/transactions.
     */
    async getTransactions(): Promise<TransactionItem[]> {
      return request<TransactionItem[]>('/credits/transactions', {
        method: 'GET',
      });
    },

    /**
     * Redeems accumulated credits for cash payout via POST /credits/redeem.
     * Request schema: RedeemRequest { amount, payout_method, destination }
     * Response schema: RedeemResponse
     */
    async redeem(data: RedeemRequest): Promise<RedeemResponse> {
      return request<RedeemResponse>('/credits/redeem', {
        method: 'POST',
        body: JSON.stringify(data),
      });
    },
  },

  user: {
    /**
     * Retrieves aggregated user statistics via GET /me/stats.
     */
    async getStats(): Promise<UserStatsResponse> {
      return request<UserStatsResponse>('/me/stats', {
        method: 'GET',
      });
    },
  },

  admin: {
    /**
     * Retrieves administrative overview and platform KPIs via GET /admin/overview.
     */
    async getOverview(params?: {
      range?: string;
      start_date?: string;
      end_date?: string;
    }): Promise<AdminOverview> {
      const searchParams = new URLSearchParams();
      if (params?.range) searchParams.set('range', params.range);
      if (params?.start_date) searchParams.set('start_date', params.start_date);
      if (params?.end_date) searchParams.set('end_date', params.end_date);
      const queryStr = searchParams.toString();
      return request<AdminOverview>(`/admin/overview${queryStr ? `?${queryStr}` : ''}`, { method: 'GET' });
    },

    /**
     * Retrieves time-series analytics, KPI comparisons, and leaderboards via GET /admin/analytics.
     */
    async getAnalytics(params?: {
      range?: '7d' | '30d' | '90d' | 'all' | 'custom' | string;
      start_date?: string;
      end_date?: string;
      granularity?: 'daily' | 'weekly' | 'monthly';
    }): Promise<AdminAnalyticsResponse> {
      const searchParams = new URLSearchParams();
      if (params?.range) searchParams.set('range', params.range);
      if (params?.start_date) searchParams.set('start_date', params.start_date);
      if (params?.end_date) searchParams.set('end_date', params.end_date);
      if (params?.granularity) searchParams.set('granularity', params.granularity);
      const queryStr = searchParams.toString();
      return request<AdminAnalyticsResponse>(`/admin/analytics${queryStr ? `?${queryStr}` : ''}`, { method: 'GET' });
    },

    /**
     * Retrieves paginated, searchable user registry via GET /admin/users.
     */
    async getUsers(params?: {
      page?: number;
      limit?: number;
      search?: string;
      role?: string;
      activity?: string;
      start_date?: string;
      end_date?: string;
      sort_by?: string;
      sort_order?: string;
    }): Promise<AdminUserListResponse> {
      const searchParams = new URLSearchParams();
      if (params?.page) searchParams.set('page', params.page.toString());
      if (params?.limit) searchParams.set('limit', params.limit.toString());
      if (params?.search && params.search.trim()) searchParams.set('search', params.search.trim());
      if (params?.role && params.role !== 'all') searchParams.set('role', params.role);
      if (params?.activity && params.activity !== 'all') searchParams.set('activity', params.activity);
      if (params?.start_date) searchParams.set('start_date', params.start_date);
      if (params?.end_date) searchParams.set('end_date', params.end_date);
      if (params?.sort_by) searchParams.set('sort_by', params.sort_by);
      if (params?.sort_order) searchParams.set('sort_order', params.sort_order);
      const queryStr = searchParams.toString();
      return request<AdminUserListResponse>(`/admin/users${queryStr ? `?${queryStr}` : ''}`, { method: 'GET' });
    },

    /**
     * Retrieves comprehensive user detail view via GET /admin/users/{userId}.
     */
    async getUserDetail(userId: string): Promise<AdminUserDetail> {
      return request<AdminUserDetail>(`/admin/users/${encodeURIComponent(userId)}`, { method: 'GET' });
    },

    /**
     * Retrieves paginated query history for a specific user via GET /admin/users/{userId}/queries.
     */
    async getUserQueries(
      userId: string,
      params?: {
        page?: number;
        limit?: number;
        search?: string;
        dataset_id?: string;
        status?: string;
        start_date?: string;
        end_date?: string;
        sort_order?: string;
      }
    ): Promise<AdminQueryListResponse> {
      const searchParams = new URLSearchParams();
      if (params?.page) searchParams.set('page', params.page.toString());
      if (params?.limit) searchParams.set('limit', params.limit.toString());
      if (params?.search && params.search.trim()) searchParams.set('search', params.search.trim());
      if (params?.dataset_id) searchParams.set('dataset_id', params.dataset_id);
      if (params?.status && params.status !== 'All') searchParams.set('status', params.status);
      if (params?.start_date) searchParams.set('start_date', params.start_date);
      if (params?.end_date) searchParams.set('end_date', params.end_date);
      if (params?.sort_order) searchParams.set('sort_order', params.sort_order);
      const queryStr = searchParams.toString();
      return request<AdminQueryListResponse>(
        `/admin/users/${encodeURIComponent(userId)}/queries${queryStr ? `?${queryStr}` : ''}`,
        { method: 'GET' }
      );
    },

    /**
     * Retrieves paginated dataset uploads for a specific user via GET /admin/users/{userId}/datasets.
     */
    async getUserDatasets(
      userId: string,
      params?: {
        page?: number;
        limit?: number;
        search?: string;
        domain?: string;
      }
    ): Promise<AdminDatasetListResponse> {
      const searchParams = new URLSearchParams();
      if (params?.page) searchParams.set('page', params.page.toString());
      if (params?.limit) searchParams.set('limit', params.limit.toString());
      if (params?.search && params.search.trim()) searchParams.set('search', params.search.trim());
      if (params?.domain && params.domain !== 'all') searchParams.set('domain', params.domain);
      const queryStr = searchParams.toString();
      return request<AdminDatasetListResponse>(
        `/admin/users/${encodeURIComponent(userId)}/datasets${queryStr ? `?${queryStr}` : ''}`,
        { method: 'GET' }
      );
    },

    /**
     * Retrieves paginated credit ledger transactions for a specific user via GET /admin/users/{userId}/transactions.
     */
    async getUserTransactions(
      userId: string,
      params?: {
        page?: number;
        limit?: number;
        search?: string;
        transaction_type?: string;
        direction?: string;
        start_date?: string;
        end_date?: string;
        sort_order?: string;
      }
    ): Promise<AdminTransactionListResponse> {
      const searchParams = new URLSearchParams();
      if (params?.page) searchParams.set('page', params.page.toString());
      if (params?.limit) searchParams.set('limit', params.limit.toString());
      if (params?.search && params.search.trim()) searchParams.set('search', params.search.trim());
      if (params?.transaction_type && params.transaction_type !== 'all') {
        searchParams.set('transaction_type', params.transaction_type);
      }
      if (params?.direction && params.direction !== 'all') searchParams.set('direction', params.direction);
      if (params?.start_date) searchParams.set('start_date', params.start_date);
      if (params?.end_date) searchParams.set('end_date', params.end_date);
      if (params?.sort_order) searchParams.set('sort_order', params.sort_order);
      const queryStr = searchParams.toString();
      return request<AdminTransactionListResponse>(
        `/admin/users/${encodeURIComponent(userId)}/transactions${queryStr ? `?${queryStr}` : ''}`,
        { method: 'GET' }
      );
    },

    /**
     * Retrieves chronological activity timeline for a specific user via GET /admin/users/{userId}/activity.
     */
    async getUserActivity(
      userId: string,
      params?: {
        page?: number;
        limit?: number;
        activity_type?: string;
        status?: string;
        start_date?: string;
        end_date?: string;
        sort_order?: string;
      }
    ): Promise<AdminTimelineResponse> {
      const searchParams = new URLSearchParams();
      if (params?.page) searchParams.set('page', params.page.toString());
      if (params?.limit) searchParams.set('limit', params.limit.toString());
      if (params?.activity_type && params.activity_type !== 'all') {
        searchParams.set('activity_type', params.activity_type);
      }
      if (params?.status && params.status !== 'All' && params.status !== 'all') {
        searchParams.set('status', params.status);
      }
      if (params?.start_date) searchParams.set('start_date', params.start_date);
      if (params?.end_date) searchParams.set('end_date', params.end_date);
      if (params?.sort_order) searchParams.set('sort_order', params.sort_order);
      const queryStr = searchParams.toString();
      return request<AdminTimelineResponse>(
        `/admin/users/${encodeURIComponent(userId)}/activity${queryStr ? `?${queryStr}` : ''}`,
        { method: 'GET' }
      );
    },

    /**
     * Retrieves global platform activity explorer across all users via GET /admin/activity.
     */
    async getGlobalActivity(params?: {
      page?: number;
      limit?: number;
      search?: string;
      user_id?: string;
      activity_type?: string;
      dataset_id?: string;
      status?: string;
      start_date?: string;
      end_date?: string;
      sort_order?: string;
    }): Promise<AdminTimelineResponse> {
      const searchParams = new URLSearchParams();
      if (params?.page) searchParams.set('page', params.page.toString());
      if (params?.limit) searchParams.set('limit', params.limit.toString());
      if (params?.search && params.search.trim()) searchParams.set('search', params.search.trim());
      if (params?.user_id) searchParams.set('user_id', params.user_id);
      if (params?.activity_type && params.activity_type !== 'all') {
        searchParams.set('activity_type', params.activity_type);
      }
      if (params?.dataset_id) searchParams.set('dataset_id', params.dataset_id);
      if (params?.status && params.status !== 'All' && params.status !== 'all') {
        searchParams.set('status', params.status);
      }
      if (params?.start_date) searchParams.set('start_date', params.start_date);
      if (params?.end_date) searchParams.set('end_date', params.end_date);
      if (params?.sort_order) searchParams.set('sort_order', params.sort_order);
      const queryStr = searchParams.toString();
      return request<AdminTimelineResponse>(`/admin/activity${queryStr ? `?${queryStr}` : ''}`, { method: 'GET' });
    },

    /**
     * Retrieves paginated dataset registry with quality ratings via GET /admin/datasets.
     */
    async getDatasets(params?: {
      page?: number;
      limit?: number;
      search?: string;
      domain?: string;
      owner_id?: string;
      availability?: string;
      start_date?: string;
      end_date?: string;
      sort_by?: string;
      sort_order?: string;
    }): Promise<AdminDatasetListResponse> {
      const searchParams = new URLSearchParams();
      if (params?.page) searchParams.set('page', params.page.toString());
      if (params?.limit) searchParams.set('limit', params.limit.toString());
      if (params?.search && params.search.trim()) searchParams.set('search', params.search.trim());
      if (params?.domain && params.domain !== 'all') searchParams.set('domain', params.domain);
      if (params?.owner_id) searchParams.set('owner_id', params.owner_id);
      if (params?.availability && params.availability !== 'all') searchParams.set('availability', params.availability);
      if (params?.start_date) searchParams.set('start_date', params.start_date);
      if (params?.end_date) searchParams.set('end_date', params.end_date);
      if (params?.sort_by) searchParams.set('sort_by', params.sort_by);
      if (params?.sort_order) searchParams.set('sort_order', params.sort_order);
      const queryStr = searchParams.toString();
      return request<AdminDatasetListResponse>(`/admin/datasets${queryStr ? `?${queryStr}` : ''}`, { method: 'GET' });
    },

    /**
     * Retrieves detailed administrative dataset inspection payload via GET /admin/datasets/{datasetId}.
     */
    async getDatasetDetail(datasetId: string): Promise<AdminDatasetDetail> {
      return request<AdminDatasetDetail>(`/admin/datasets/${encodeURIComponent(datasetId)}`, { method: 'GET' });
    },

    /**
     * Retrieves global query execution log across all users via GET /admin/queries.
     */
    async getQueries(params?: {
      page?: number;
      limit?: number;
      search?: string;
      user_id?: string;
      dataset_id?: string;
      status?: string;
      start_date?: string;
      end_date?: string;
      sort_order?: string;
    }): Promise<AdminQueryListResponse> {
      const searchParams = new URLSearchParams();
      if (params?.page) searchParams.set('page', params.page.toString());
      if (params?.limit) searchParams.set('limit', params.limit.toString());
      if (params?.search && params.search.trim()) searchParams.set('search', params.search.trim());
      if (params?.user_id) searchParams.set('user_id', params.user_id);
      if (params?.dataset_id) searchParams.set('dataset_id', params.dataset_id);
      if (params?.status && params.status !== 'All') searchParams.set('status', params.status);
      if (params?.start_date) searchParams.set('start_date', params.start_date);
      if (params?.end_date) searchParams.set('end_date', params.end_date);
      if (params?.sort_order) searchParams.set('sort_order', params.sort_order);
      const queryStr = searchParams.toString();
      return request<AdminQueryListResponse>(`/admin/queries${queryStr ? `?${queryStr}` : ''}`, { method: 'GET' });
    },

    /**
     * Retrieves global platform credit ledger transactions via GET /admin/transactions.
     */
    async getTransactions(params?: {
      page?: number;
      limit?: number;
      search?: string;
      user_id?: string;
      transaction_type?: string;
      direction?: string;
      start_date?: string;
      end_date?: string;
      sort_order?: string;
    }): Promise<AdminTransactionListResponse> {
      const searchParams = new URLSearchParams();
      if (params?.page) searchParams.set('page', params.page.toString());
      if (params?.limit) searchParams.set('limit', params.limit.toString());
      if (params?.search && params.search.trim()) searchParams.set('search', params.search.trim());
      if (params?.user_id) searchParams.set('user_id', params.user_id);
      if (params?.transaction_type && params.transaction_type !== 'all') searchParams.set('transaction_type', params.transaction_type);
      if (params?.direction && params.direction !== 'all') searchParams.set('direction', params.direction);
      if (params?.start_date) searchParams.set('start_date', params.start_date);
      if (params?.end_date) searchParams.set('end_date', params.end_date);
      if (params?.sort_order) searchParams.set('sort_order', params.sort_order);
      const queryStr = searchParams.toString();
      return request<AdminTransactionListResponse>(`/admin/transactions${queryStr ? `?${queryStr}` : ''}`, { method: 'GET' });
    },

    /**
     * Retrieves administrative governance and audit logs via GET /admin/audit-logs.
     */
    async getAuditLogs(params?: {
      page?: number;
      limit?: number;
      action?: string;
      search?: string;
    }): Promise<AdminAuditLogListResponse> {
      const searchParams = new URLSearchParams();
      if (params?.page) searchParams.set('page', params.page.toString());
      if (params?.limit) searchParams.set('limit', params.limit.toString());
      if (params?.action && params.action !== 'All') searchParams.set('action', params.action);
      if (params?.search && params.search.trim()) searchParams.set('search', params.search.trim());
      const queryStr = searchParams.toString();
      return request<AdminAuditLogListResponse>(`/admin/audit-logs${queryStr ? `?${queryStr}` : ''}`, { method: 'GET' });
    },
  },
};

export default api;
