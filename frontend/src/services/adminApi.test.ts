import { describe, it, expect, beforeEach } from 'bun:test';
import { api, ApiError, clearStoredToken, setStoredToken } from './api';

// Polyfill localStorage if necessary in test environment
if (typeof globalThis.localStorage === 'undefined') {
  const store = new Map<string, string>();
  globalThis.localStorage = {
    getItem: (key: string) => store.get(key) ?? null,
    setItem: (key: string, value: string) => store.set(key, String(value)),
    removeItem: (key: string) => store.delete(key),
    clear: () => store.clear(),
    key: (index: number) => Array.from(store.keys())[index] ?? null,
    get length() {
      return store.size;
    },
  } as Storage;
}

describe('Admin API Authorization & Endpoints (Integration)', () => {
  beforeEach(() => {
    clearStoredToken();
  });

  it('rejects unauthenticated requests to admin endpoints with 401', async () => {
    try {
      await api.admin.getOverview();
      expect(true).toBe(false); // Should not reach here
    } catch (err: any) {
      expect(err).toBeInstanceOf(ApiError);
      expect(err.status).toBe(401);
    }
  });

  it('rejects regular non-admin user with 403 Forbidden on all admin endpoints', async () => {
    // 1. Register a fresh non-admin user
    const unique = Math.random().toString(36).substring(2, 8);
    const regRes = await api.auth.register({
      email: `regular_${unique}@datapulse.io`,
      password: 'Password123!',
      full_name: `Regular Tester ${unique}`,
    });

    expect(regRes.access_token).toBeDefined();
    expect(regRes.user.is_admin).toBe(false);

    // 2. Overview -> 403
    try {
      await api.admin.getOverview();
      expect(true).toBe(false);
    } catch (err: any) {
      expect(err).toBeInstanceOf(ApiError);
      expect(err.status).toBe(403);
    }

    // 3. Users -> 403
    try {
      await api.admin.getUsers();
      expect(true).toBe(false);
    } catch (err: any) {
      expect(err).toBeInstanceOf(ApiError);
      expect(err.status).toBe(403);
    }

    // 4. Datasets -> 403
    try {
      await api.admin.getDatasets();
      expect(true).toBe(false);
    } catch (err: any) {
      expect(err).toBeInstanceOf(ApiError);
      expect(err.status).toBe(403);
    }

    // 5. Queries -> 403
    try {
      await api.admin.getQueries();
      expect(true).toBe(false);
    } catch (err: any) {
      expect(err).toBeInstanceOf(ApiError);
      expect(err.status).toBe(403);
    }

    // 6. Transactions -> 403
    try {
      await api.admin.getTransactions();
      expect(true).toBe(false);
    } catch (err: any) {
      expect(err).toBeInstanceOf(ApiError);
      expect(err.status).toBe(403);
    }
  });

  it('normal user querying history remains isolated', async () => {
    const unique = Math.random().toString(36).substring(2, 8);
    await api.auth.register({
      email: `isolated_${unique}@datapulse.io`,
      password: 'Password123!',
      full_name: `Isolated User ${unique}`,
    });

    const history = await api.query.getHistory({ page: 1, limit: 10 });
    expect(history.items).toBeDefined();
    expect(history.items.length).toBe(0);
  });
});
