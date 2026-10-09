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
