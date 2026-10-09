import {
  AuthTokenResponse,
  BackendUserResponse,
  UserLoginRequest,
  UserRegisterRequest,
} from '../types';

const TOKEN_STORAGE_KEY = 'datapulse_auth_token';

// Base API URL with local development fallback to http://localhost:8000
export const API_BASE_URL = (
  import.meta.env.VITE_API_URL || 'http://localhost:8000'
).replace(/\/+$/, '');

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
    // If token expired or unauthorized on authenticated endpoints
    if (response.status === 401 && path.includes('/auth/me')) {
      clearStoredToken();
    }

    const message = parseErrorMessage(response.status, responseData);
    throw new ApiError(message, response.status, responseData?.detail ?? responseData);
  }

  return responseData as T;
}

// Predefined demo credentials for Instant Demo Switcher buttons
const DEMO_ACCOUNTS: Record<
  string,
  { email: string; password: string; full_name: string }
> = {
  'demo-user': {
    email: 'demo@datapulse.io',
    password: 'Password123!',
    full_name: 'Demo User',
  },
  alice: {
    email: 'alice@datapulse.io',
    password: 'Password123!',
    full_name: 'Alice Chen',
  },
  bob: {
    email: 'bob@datapulse.io',
    password: 'Password123!',
    full_name: 'Bob Vance',
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
      clearStoredToken();
    },

    /**
     * Authenticates with real backend credentials for demo buttons.
     * Tries login first; if user doesn't exist, automatically registers.
     */
    async demoLogin(
      accountKey: 'demo-user' | 'alice' | 'bob' | string
    ): Promise<AuthTokenResponse> {
      const creds = DEMO_ACCOUNTS[accountKey] || {
        email: `${accountKey}@datapulse.io`,
        password: 'Password123!',
        full_name: accountKey.charAt(0).toUpperCase() + accountKey.slice(1),
      };

      try {
        return await api.auth.login({
          email: creds.email,
          password: creds.password,
        });
      } catch (err: any) {
        // If not found or wrong credentials, register fresh account
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
};

export default api;
