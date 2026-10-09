import { describe, it, expect, beforeEach } from 'bun:test';
import { api, ApiError, API_BASE_URL, getStoredToken, setStoredToken, clearStoredToken } from './api';

// Polyfill localStorage if necessary in test environment
if (typeof globalThis.localStorage === 'undefined') {
  const store = new Map<string, string>();
  globalThis.localStorage = {
    getItem: (key: string) => store.get(key) ?? null,
    setItem: (key: string, value: string) => {
      store.set(key, String(value));
    },
    removeItem: (key: string) => {
      store.delete(key);
    },
    clear: () => {
      store.clear();
    },
    key: (index: number) => Array.from(store.keys())[index] ?? null,
    get length() {
      return store.size;
    },
  } as Storage;
}

describe('API Client Configuration & Token Storage', () => {
  beforeEach(() => {
    clearStoredToken();
  });

  it('resolves API_BASE_URL with default localhost:8000', () => {
    expect(API_BASE_URL).toBeDefined();
    expect(API_BASE_URL.startsWith('http')).toBe(true);
  });

  it('stores, retrieves, and clears authentication tokens', () => {
    expect(getStoredToken()).toBeNull();
    setStoredToken('test_token_123');
    expect(getStoredToken()).toBe('test_token_123');
    clearStoredToken();
    expect(getStoredToken()).toBeNull();
  });
});

describe('Live Backend Authentication Integration', () => {
  const uniqueId = Math.random().toString(36).substring(2, 8);
  const testEmail = `frontend_test_${uniqueId}@datapulse.io`;
  const testPassword = 'Password123!';
  const testName = `Frontend Tester ${uniqueId}`;

  beforeEach(() => {
    clearStoredToken();
  });

  it('registers a new user successfully via POST /auth/register', async () => {
    const res = await api.auth.register({
      email: testEmail,
      password: testPassword,
      full_name: testName,
    });

    expect(res).toBeDefined();
    expect(res.access_token).toBeDefined();
    expect(res.token_type.toLowerCase()).toBe('bearer');
    expect(res.user.email).toBe(testEmail);
    expect(res.user.full_name).toBe(testName);
    expect(res.user.credits).toBe(100);
    expect(getStoredToken()).toBe(res.access_token);
  });

  it('fails duplicate registration with 400 Bad Request', async () => {
    try {
      await api.auth.register({
        email: testEmail,
        password: testPassword,
        full_name: testName,
      });
      expect(true).toBe(false); // Should not reach
    } catch (err: any) {
      expect(err).toBeInstanceOf(ApiError);
      expect(err.status).toBe(400);
      expect(err.message).toContain('already exists');
    }
  });

  it('rejects short passwords (< 6 chars) with 422 validation error', async () => {
    try {
      await api.auth.register({
        email: `short_pw_${uniqueId}@datapulse.io`,
        password: '123',
        full_name: 'Short Password User',
      });
      expect(true).toBe(false);
    } catch (err: any) {
      expect(err).toBeInstanceOf(ApiError);
      expect(err.status).toBe(422);
    }
  });

  it('logs in successfully via POST /auth/login', async () => {
    const res = await api.auth.login({
      email: testEmail,
      password: testPassword,
    });

    expect(res).toBeDefined();
    expect(res.access_token).toBeDefined();
    expect(res.user.email).toBe(testEmail);
    expect(getStoredToken()).toBe(res.access_token);
  });

  it('rejects invalid password with 401 Unauthorized', async () => {
    try {
      await api.auth.login({
        email: testEmail,
        password: 'WrongPassword!',
      });
      expect(true).toBe(false);
    } catch (err: any) {
      expect(err).toBeInstanceOf(ApiError);
      expect(err.status).toBe(401);
      expect(err.message).toContain('Incorrect email or password');
    }
  });

  it('restores authenticated user via GET /auth/me with Bearer token', async () => {
    // Log in to set token
    const loginRes = await api.auth.login({
      email: testEmail,
      password: testPassword,
    });
    expect(getStoredToken()).toBe(loginRes.access_token);

    // Call getMe
    const me = await api.auth.getMe();
    expect(me).toBeDefined();
    expect(me.id).toBe(loginRes.user.id);
    expect(me.email).toBe(testEmail);
    expect(me.full_name).toBe(testName);
    expect(me.credits).toBe(100);
  });

  it('handles expired/invalid token on GET /auth/me by clearing stored token', async () => {
    setStoredToken('invalid_or_expired_token_abc');
    try {
      await api.auth.getMe();
      expect(true).toBe(false);
    } catch (err: any) {
      expect(err).toBeInstanceOf(ApiError);
      expect(err.status).toBe(401);
      // Stored token must be cleared on 401
      expect(getStoredToken()).toBeNull();
    }
  });

  it('logs out and clears stored credentials', () => {
    setStoredToken('active_token');
    expect(getStoredToken()).toBe('active_token');
    api.auth.logout();
    expect(getStoredToken()).toBeNull();
  });

  it('supports instant demo login against real backend', async () => {
    const demoRes = await api.auth.demoLogin('demo-user');
    expect(demoRes).toBeDefined();
    expect(demoRes.access_token).toBeDefined();
    expect(demoRes.user.email).toBe('demo@datapulse.io');
    expect(getStoredToken()).toBe(demoRes.access_token);

    // Verify authenticated user
    const me = await api.auth.getMe();
    expect(me.email).toBe('demo@datapulse.io');
  });
});

describe('Live Backend Dataset Upload Integration', () => {
  let authToken: string;

  beforeEach(async () => {
    // Log in with demo-user to obtain a valid Bearer token for authenticated tests
    const res = await api.auth.demoLogin('demo-user');
    authToken = res.access_token;
    setStoredToken(authToken);
  });

  it('rejects unauthenticated upload requests with 401 Unauthorized', async () => {
    clearStoredToken();

    const sampleCsv = 'id,name,value\n1,alpha,10.5\n2,beta,20.0';
    const file = new File([sampleCsv], 'unauth_test.csv', { type: 'text/csv' });

    try {
      await api.datasets.upload(file, 'general', 'Unauth Test');
      expect(true).toBe(false); // Should not succeed
    } catch (err: any) {
      expect(err).toBeInstanceOf(ApiError);
      expect(err.status).toBe(401);
      expect(err.message).toBeDefined();
    }
  });

  it('rejects non-CSV file extensions with 400 Bad Request', async () => {
    const jsonContent = JSON.stringify([{ id: 1, name: 'invalid' }]);
    const file = new File([jsonContent], 'invalid.json', { type: 'application/json' });

    try {
      await api.datasets.upload(file, 'technology', 'Invalid Ext Test');
      expect(true).toBe(false);
    } catch (err: any) {
      expect(err).toBeInstanceOf(ApiError);
      expect(err.status).toBe(400);
      expect(err.message).toContain('Only CSV files');
    }
  });

  it('rejects empty CSV content with 422 Unprocessable Entity', async () => {
    const file = new File([''], 'empty.csv', { type: 'text/csv' });

    try {
      await api.datasets.upload(file, 'general', 'Empty Test');
      expect(true).toBe(false);
    } catch (err: any) {
      expect(err).toBeInstanceOf(ApiError);
      expect(err.status).toBe(422);
      expect(err.message).toContain('empty');
    }
  });

  it('rejects CSV with header only and zero data rows with 422', async () => {
    const file = new File(['col1,col2,col3\n'], 'header_only.csv', { type: 'text/csv' });

    try {
      await api.datasets.upload(file, 'general', 'Header Only Test');
      expect(true).toBe(false);
    } catch (err: any) {
      expect(err).toBeInstanceOf(ApiError);
      expect(err.status).toBe(422);
      expect(err.message).toContain('at least one data row');
    }
  });

  it('successfully uploads valid CSV, returns real dataset details and awards credits', async () => {
    const csvData = [
      'customer_id,tenure_months,monthly_charges,churn',
      'C-101,12,65.50,No',
      'C-102,24,80.00,No',
      'C-103,3,45.20,Yes',
      'C-104,36,95.10,No',
      'C-105,8,72.40,Yes',
    ].join('\n');

    const fileName = `telecom_churn_${Date.now()}.csv`;
    const datasetTitle = 'Telecom Customer Churn Verified';
    const file = new File([csvData], fileName, { type: 'text/csv' });

    const result = await api.datasets.upload(file, 'telecom', datasetTitle);

    expect(result).toBeDefined();
    expect(result.id).toBeDefined();
    expect(result.id.startsWith('ds_')).toBe(true);
    expect(result.name).toBe(datasetTitle);
    expect(result.filename).toBe(fileName);
    expect(result.domain).toBe('telecom');
    expect(result.rows_count).toBe(5);
    expect(result.columns_count).toBe(4);
    expect(result.schema_metadata).toBeDefined();
    expect(result.schema_metadata['customer_id']).toBe('string');
    expect(result.content_summary).toContain('5 rows');
    expect(result.content_summary).toContain('4 columns');

    // Evaluation scores and credits should be provided
    expect(result.quality_score).toBeDefined();
    expect(result.quality_score).toBeGreaterThan(0);
    expect(result.credits_awarded).toBeDefined();
    expect(result.credits_awarded).toBeGreaterThanOrEqual(50);

    // Verify retrieval via getDataset
    const fetched = await api.datasets.getDataset(result.id);
    expect(fetched.id).toBe(result.id);
    expect(fetched.rows_count).toBe(5);

    // Verify retrieval via getEvaluation
    const evalReport = await api.datasets.getEvaluation(result.id);
    expect(evalReport.dataset_id).toBe(result.id);
    expect(evalReport.status).toBe('completed');
    expect(evalReport.credits_awarded).toBe(result.credits_awarded!);
  });

  it('supports upload using FormData directly with automatic filename fallback for name', async () => {
    const csvContent = 'sku,price,stock\nA101,19.99,100\nB202,29.99,50\nC303,9.99,250';
    const fileName = `inventory_test_${Date.now()}.csv`;
    const file = new File([csvContent], fileName, { type: 'text/csv' });

    const formData = new FormData();
    formData.append('file', file);
    formData.append('domain', 'retail');
    // omit name field so backend derives name from filename

    const result = await api.datasets.upload(formData);

    expect(result).toBeDefined();
    expect(result.id.startsWith('ds_')).toBe(true);
    expect(result.domain).toBe('retail');
    expect(result.filename).toBe(fileName);
    expect(result.name).toBe(fileName.replace('.csv', ''));
    expect(result.rows_count).toBe(3);
    expect(result.columns_count).toBe(3);
  });
});
