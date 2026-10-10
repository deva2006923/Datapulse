import { describe, it, expect, beforeEach } from 'bun:test';
import { api, ApiError, API_BASE_URL, getStoredToken, setStoredToken, clearStoredToken, DEMO_ACCOUNTS } from './api';

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

  it('supports instant demo login against real backend for all defined demo accounts', async () => {
    for (const [key, expected] of Object.entries(DEMO_ACCOUNTS)) {
      const demoRes = await api.auth.demoLogin(key);
      expect(demoRes).toBeDefined();
      expect(demoRes.access_token).toBeDefined();
      expect(demoRes.user.email).toBe(expected.email);
      expect(demoRes.user.full_name).toBe(expected.full_name);
      expect(getStoredToken()).toBe(demoRes.access_token);

      // Verify authenticated user from authoritative /auth/me
      const me = await api.auth.getMe();
      expect(me.email).toBe(expected.email);
      expect(me.full_name).toBe(expected.full_name);
      expect(typeof me.credits).toBe('number');
    }
  });

  it('rejects demo login with arbitrary or generated user IDs to prevent session corruption', async () => {
    const invalidKeys = ['usr_4cf1c696e1ba', 'user_1728591234', 'fake_account', ''];
    for (const key of invalidKeys) {
      try {
        await api.auth.demoLogin(key);
        expect(true).toBe(false); // Should throw ApiError
      } catch (err: any) {
        expect(err).toBeInstanceOf(ApiError);
        expect(err.status).toBe(400);
        expect(err.message).toContain('Invalid demo account key');
      }
    }
  });

  it('ensures /auth/me is the authoritative single source of truth for credit balance', async () => {
    const demoRes = await api.auth.demoLogin('demo-user');
    const me = await api.auth.getMe();
    expect(me.id).toBe(demoRes.user.id);
    expect(me.credits).toBe(demoRes.user.credits);
    expect(me.credits).toBeGreaterThanOrEqual(0);
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

describe('Phase 3: Dataset Search and Discovery Integration', () => {
  let authToken: string;
  let testDatasetId: string;

  beforeEach(async () => {
    const res = await api.auth.demoLogin('demo-user');
    authToken = res.access_token;
    setStoredToken(authToken);

    // Ensure at least one dataset exists
    const unique = Date.now();
    const csvContent = 'sensor_id,temperature,humidity,status\nS-1,22.4,55.1,OK\nS-2,28.9,65.3,WARN\nS-3,19.2,48.0,OK';
    const file = new File([csvContent], `iot_sensors_${unique}.csv`, { type: 'text/csv' });
    const uploaded = await api.datasets.upload(file, 'technology', `IoT Grid Sensor Network ${unique}`);
    testDatasetId = uploaded.id;
  });

  it('retrieves dataset catalog via GET /datasets', async () => {
    const listRes = await api.datasets.list();
    expect(listRes).toBeDefined();
    expect(listRes.total).toBeGreaterThanOrEqual(1);
    expect(Array.isArray(listRes.datasets)).toBe(true);
    expect(listRes.datasets.some((d) => d.id === testDatasetId)).toBe(true);
  });

  it('filters dataset catalog by domain via GET /datasets?domain=technology', async () => {
    const listRes = await api.datasets.list('technology');
    expect(listRes).toBeDefined();
    expect(Array.isArray(listRes.datasets)).toBe(true);
    expect(listRes.datasets.every((d) => d.domain.toLowerCase() === 'technology')).toBe(true);
  });

  it('performs semantic search via POST /datasets/search with matches', async () => {
    const searchRes = await api.datasets.search('Sensor Network', 'technology', 50);
    expect(searchRes).toBeDefined();
    expect(searchRes.total).toBeGreaterThanOrEqual(1);
    expect(Array.isArray(searchRes.results)).toBe(true);
    const match = searchRes.results.find((r) => r.dataset_id === testDatasetId);
    expect(match).toBeDefined();
    expect(match?.name).toContain('IoT Grid Sensor Network');
    expect(match?.score).toBeGreaterThan(0);
  });

  it('returns empty results list when no datasets match domain or query', async () => {
    const searchRes = await api.datasets.search('temperature', 'nonexistent_domain_xyz');
    expect(searchRes).toBeDefined();
    expect(searchRes.total).toBe(0);
    expect(searchRes.results.length).toBe(0);
  });

  it('fetches full dataset details via GET /datasets/:id', async () => {
    const detail = await api.datasets.getDataset(testDatasetId);
    expect(detail).toBeDefined();
    expect(detail.id).toBe(testDatasetId);
    expect(detail.name).toContain('IoT Grid Sensor Network');
    expect(detail.rows_count).toBe(3);
    expect(detail.columns_count).toBe(4);
    expect(detail.schema_metadata).toBeDefined();
    expect(detail.content_summary).toBeDefined();
  });

  it('fetches automated quality evaluation via GET /datasets/:id/evaluation', async () => {
    const evalData = await api.datasets.getEvaluation(testDatasetId);
    expect(evalData).toBeDefined();
    expect(evalData.dataset_id).toBe(testDatasetId);
    expect(evalData.status).toBe('completed');
    expect(evalData.quality_score).toBeGreaterThan(0);
    expect(evalData.overall_score).toBeGreaterThan(0);
  });

  it('handles non-existent dataset ID with 404 Not Found', async () => {
    try {
      await api.datasets.getDataset('ds_non_existent_999999');
      expect(true).toBe(false);
    } catch (err: any) {
      expect(err).toBeInstanceOf(ApiError);
      expect(err.status).toBe(404);
      expect(err.message).toContain('not found');
    }
  });
});

describe('Phase 4: Natural-Language Query and Actual DuckDB Results', () => {
  let testDatasetId: string;

  beforeEach(async () => {
    const res = await api.auth.demoLogin('demo-user');
    setStoredToken(res.access_token);

    const csvContent = 'device,metric,value\nD-10,cpu,45\nD-20,ram,78\nD-30,disk,23\nD-40,cpu,89';
    const file = new File([csvContent], `metrics_${Date.now()}.csv`, { type: 'text/csv' });
    const uploaded = await api.datasets.upload(file, 'technology', 'System Performance Metrics');
    testDatasetId = uploaded.id;
  });

  it('executes a natural-language query and returns real DuckDB results and SQL', async () => {
    // Query contains count/how many keywords supported by SQL fallback
    const queryRes = await api.query.execute('how many devices are in the dataset?', testDatasetId);

    expect(queryRes).toBeDefined();
    expect(queryRes.query).toBe('how many devices are in the dataset?');
    expect(queryRes.answer).toBeDefined();
    expect(queryRes.sql_query).toBeDefined();
    expect(queryRes.sql_query?.toUpperCase()).toContain('SELECT');
    expect(queryRes.columns).toBeDefined();
    expect(Array.isArray(queryRes.columns)).toBe(true);
    expect(queryRes.results).toBeDefined();
    expect(Array.isArray(queryRes.results)).toBe(true);
    expect(queryRes.records_analyzed).toBe(4);
    // Since demo-user owns this dataset, credits_charged must be 0
    expect(queryRes.credits_charged).toBe(0);
  });

  it('returns 0 credits charged when querying own dataset (own-dataset exemption)', async () => {
    const queryRes = await api.query.execute('show items in the catalog', testDatasetId);
    expect(queryRes).toBeDefined();
    expect(queryRes.credits_charged).toBe(0);
  });

  it('rejects unauthenticated query with 401 Unauthorized', async () => {
    clearStoredToken();
    try {
      await api.query.execute('count rows', testDatasetId);
      expect(true).toBe(false);
    } catch (err: any) {
      expect(err).toBeInstanceOf(ApiError);
      expect(err.status).toBe(401);
    }
  });

  it('rejects query targeting non-existent dataset with 404 Not Found', async () => {
    try {
      await api.query.execute('how many rows?', 'ds_missing_000000');
      expect(true).toBe(false);
    } catch (err: any) {
      expect(err).toBeInstanceOf(ApiError);
      expect(err.status).toBe(404);
      expect(err.message).toContain('not found');
    }
  });

  it('handles AI provider error with 503 without false credit deductions', async () => {
    const meBefore = await api.auth.getMe();
    try {
      // Query that does not match fallback rules triggers AI provider attempt (503 when key unset)
      await api.query.execute('complex non-fallback mathematical inference question', testDatasetId);
      expect(true).toBe(false);
    } catch (err: any) {
      expect(err).toBeInstanceOf(ApiError);
      expect(err.status).toBe(503);
    }

    // Credits must remain untouched
    const meAfter = await api.auth.getMe();
    expect(meAfter.credits).toBe(meBefore.credits);
  });

  it('rejects query when user has 0 credits and queries another user dataset with 402 Payment Required', async () => {
    // 1. Create a user with 0 credits by registering and redeeming all 100 credits
    const unique = Math.random().toString(36).substring(2, 8);
    const brokeUser = await api.auth.register({
      email: `broke_${unique}@datapulse.io`,
      password: 'Password123!',
      full_name: 'Broke User',
    });
    setStoredToken(brokeUser.access_token);

    // Redeem all 100 credits
    await api.credits.redeem({
      amount: 100,
      payout_method: 'bank_transfer',
      destination: 'ACC123456789',
    });

    // Verify balance is now 0
    const me = await api.auth.getMe();
    expect(me.credits).toBe(0);

    // 2. Attempt to query testDatasetId (owned by demo-user)
    try {
      await api.query.execute('how many devices?', testDatasetId);
      expect(true).toBe(false); // Should not succeed
    } catch (err: any) {
      expect(err).toBeInstanceOf(ApiError);
      expect(err.status).toBe(402);
      expect(err.message).toContain('Insufficient credit balance');
    }

    // Verify balance was NOT negatively altered
    const meAfter = await api.auth.getMe();
    expect(meAfter.credits).toBe(0);
  });
});

describe('Phase 5: Credit Balance and Transactions Integration', () => {
  let userToken: string;
  let testEmail: string;

  beforeEach(async () => {
    const unique = Math.random().toString(36).substring(2, 8);
    testEmail = `credits_test_${unique}@datapulse.io`;
    const regRes = await api.auth.register({
      email: testEmail,
      password: 'Password123!',
      full_name: 'Credits Tester',
    });
    userToken = regRes.access_token;
    setStoredToken(userToken);
  });

  it('retrieves authoritative initial credit balance of 100 via GET /auth/me and GET /me/stats', async () => {
    const me = await api.auth.getMe();
    expect(me.credits).toBe(100);

    const stats = await api.user.getStats();
    expect(stats.credits_balance).toBe(100);
    expect(stats.datasets_uploaded).toBe(0);
  });

  it('refreshes credit balance after dataset upload', async () => {
    const initialMe = await api.auth.getMe();
    const initialCredits = initialMe.credits;

    const csvData = 'id,name,role\n1,Alex,Analyst\n2,Jordan,Engineer';
    const file = new File([csvData], `staff_${Date.now()}.csv`, { type: 'text/csv' });
    const uploadRes = await api.datasets.upload(file, 'general', 'Staff Directory');

    expect(uploadRes.credits_awarded).toBeGreaterThanOrEqual(50);

    // Re-fetch balance from backend
    const updatedMe = await api.auth.getMe();
    expect(updatedMe.credits).toBe(initialCredits + uploadRes.credits_awarded!);
  });

  it('retrieves real transaction history via GET /credits/transactions', async () => {
    // Fresh user has signup bonus or initial transaction
    const txList = await api.credits.getTransactions();
    expect(Array.isArray(txList)).toBe(true);

    // Perform a redemption to create a known transaction
    const redeemRes = await api.credits.redeem({
      amount: 25,
      payout_method: 'bank_transfer',
      destination: 'ACC-VERIFY-123',
    });
    expect(redeemRes.success).toBe(true);
    expect(redeemRes.redeemed_credits).toBe(25);
    expect(redeemRes.remaining_balance).toBe(75);

    // Fetch transactions again
    const updatedTx = await api.credits.getTransactions();
    expect(updatedTx.length).toBeGreaterThan(0);
    const redeemTx = updatedTx.find((t) => t.id === redeemRes.transaction_id);
    expect(redeemTx).toBeDefined();
    expect(redeemTx?.amount).toBe(-25);
    expect(redeemTx?.transaction_type).toBe('redeem');
    expect(redeemTx?.status).toBe('completed');
  });

  it('rejects redemption exceeding balance with 400 Bad Request', async () => {
    try {
      await api.credits.redeem({
        amount: 500, // User only has 100 credits
        payout_method: 'crypto',
        destination: '0xABCDEF',
      });
      expect(true).toBe(false);
    } catch (err: any) {
      expect(err).toBeInstanceOf(ApiError);
      expect(err.status).toBe(400);
      expect(err.message).toContain('Insufficient credit balance');
    }
  });

  it('rejects redemption of 0 or negative credits with 422 Unprocessable Entity', async () => {
    try {
      await api.credits.redeem({
        amount: 0,
        payout_method: 'bank_transfer',
        destination: 'ACC-ZERO',
      });
      expect(true).toBe(false);
    } catch (err: any) {
      expect(err).toBeInstanceOf(ApiError);
      expect(err.status).toBe(422);
      expect(err.message).toContain('greater than 0');
    }
  });
});

describe('Dataset & Transaction Adapters', () => {
  it('correctly maps backend dataset response to AppDataset', async () => {
    const { backendDatasetToAppDataset } = await import('./datasetAdapter');

    const backendData = {
      id: 'ds_test_adapter_1',
      user_id: 'user_xyz',
      name: 'E-Commerce Transactions',
      filename: 'ecommerce.csv',
      domain: 'retail',
      rows_count: 1000,
      columns_count: 5,
      quality_score: 92,
      domain_relevance_score: 88,
      overall_score: 90,
      content_summary: 'E-commerce order history dataset',
      schema_metadata: { order_id: 'string', total: 'float', items: 'int' },
      created_at: '2026-10-10T12:00:00Z',
    };

    const appDataset = backendDatasetToAppDataset(backendData, 'user_xyz');
    expect(appDataset.id).toBe('ds_test_adapter_1');
    expect(appDataset.title).toBe('E-Commerce Transactions');
    expect(appDataset.domain).toBe('Retail');
    expect(appDataset.rowCount).toBe(1000);
    expect(appDataset.columnCount).toBe(5);
    expect(appDataset.columns.length).toBe(3);
    expect(appDataset.columns[0].name).toBe('order_id');
    expect(appDataset.authorName).toBe('You'); // Because currentUserId matches user_id
    expect(appDataset.cost).toBe(0); // Own dataset cost is 0
  });

  it('correctly maps search results to AppDataset with matchScore', async () => {
    const { searchItemToAppDataset } = await import('./datasetAdapter');

    const searchItem = {
      dataset_id: 'ds_search_1',
      name: 'Telecom Churn',
      filename: 'telecom.csv',
      domain: 'telecom',
      rows_count: 500,
      columns_count: 6,
      quality_score: 88,
      match_score: 0.94,
      score: 0.94,
      summary: 'Customer churn telemetry',
    };

    const appDataset = searchItemToAppDataset(searchItem);
    expect(appDataset.id).toBe('ds_search_1');
    expect(appDataset.title).toBe('Telecom Churn');
    expect(appDataset.matchScore).toBe(94);
    expect(appDataset.domain).toBe('Telecom');
  });

  it('correctly maps transaction items to WalletTransaction types', async () => {
    const { transactionItemToWalletTransaction } = await import('./datasetAdapter');

    const bonusTx = transactionItemToWalletTransaction({
      id: 'tx_1',
      user_id: 'u1',
      amount: 100,
      transaction_type: 'bonus',
      description: 'Signup bonus',
      status: 'completed',
      created_at: '2026-10-10T10:00:00Z',
    });
    expect(bonusTx.type).toBe('SIGNUP_BONUS');
    expect(bonusTx.amount).toBe(100);

    const feeTx = transactionItemToWalletTransaction({
      id: 'tx_2',
      user_id: 'u1',
      amount: -1,
      transaction_type: 'query_fee',
      description: 'Query deduction',
      status: 'completed',
      created_at: '2026-10-10T10:05:00Z',
    });
    expect(feeTx.type).toBe('QUERY_CHARGE');
    expect(feeTx.amount).toBe(-1);

    const rewardTx = transactionItemToWalletTransaction({
      id: 'tx_3',
      user_id: 'u1',
      amount: 1,
      transaction_type: 'query_reward',
      description: 'Query royalty',
      status: 'completed',
      created_at: '2026-10-10T10:10:00Z',
    });
    expect(rewardTx.type).toBe('CONTRIBUTOR_ROYALTY');
    expect(rewardTx.amount).toBe(1);

    const redeemTx = transactionItemToWalletTransaction({
      id: 'tx_4',
      user_id: 'u1',
      amount: -50,
      transaction_type: 'redeem',
      description: 'Redeemed payout',
      status: 'completed',
      created_at: '2026-10-10T10:15:00Z',
    });
    expect(redeemTx.type).toBe('REDEMPTION');
    expect(redeemTx.amount).toBe(-50);
  });
});

