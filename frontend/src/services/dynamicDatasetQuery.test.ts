import { describe, it, expect, beforeEach } from 'bun:test';
import { api, ApiError, clearStoredToken } from './api';
import { backendDatasetToAppDataset } from './datasetAdapter';

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

describe('Dynamic Dataset Selection & Multi-Schema Querying', () => {
  beforeEach(() => {
    clearStoredToken();
  });

  it('lists and queries 3 distinct datasets dynamically and never deducts credits on missing dataset', async () => {
    const suffix = Math.random().toString(36).substring(2, 8);

    // 1. Register owner and analyst accounts
    const owner = await api.auth.register({
      email: `dyn_owner_${suffix}@datapulse.io`,
      password: 'Password123!',
      full_name: `Dynamic Owner ${suffix}`,
    });

    const ds1 = await api.datasets.upload(
      new File(
        ['clinic_id,patients,avg_wait_min\nCL-1,42,12.5\nCL-2,67,18.0\n'],
        'clinics.csv',
        { type: 'text/csv' }
      ),
      'healthcare',
      `Clinic Metrics ${suffix}`
    );

    const ds2 = await api.datasets.upload(
      new File(
        ['sensor_code,voltage,temperature_c\nSN-A,220.4,34.1\nSN-B,218.9,36.8\nSN-C,221.0,32.5\n'],
        'sensors.csv',
        { type: 'text/csv' }
      ),
      'technology',
      `Sensor Telemetry ${suffix}`
    );

    const ds3 = await api.datasets.upload(
      new File(
        ['course_code,enrolled,pass_rate\nCS101,120,91.5\nDS202,85,88.0\n'],
        'courses.csv',
        { type: 'text/csv' }
      ),
      'education',
      `Course Enrollment ${suffix}`
    );

    // 2. Verify all 3 appear in GET /datasets with real availability and schema-aware mapping
    const catalog = await api.datasets.list();
    const mapped = catalog.datasets.map((d) => backendDatasetToAppDataset(d, owner.user.id));

    for (const created of [ds1, ds2, ds3]) {
      const found = mapped.find((m) => m.id === created.id);
      expect(found).toBeDefined();
      expect(found?.storageAvailable).toBe(true);
      expect(found?.availability).toBe('Available');
      expect(found?.rowCount).toBe(created.rows_count);
      expect(found?.format).toBe('csv');
    }

    // 3. Query each dataset sequentially (switching target dataset_id)
    const r1 = await api.query.execute('how many rows are in this dataset', ds1.id);
    expect(r1.dataset_id).toBe(ds1.id);
    expect(r1.sql_query).toContain(`dataset_${ds1.id}`);
    expect(r1.records_analyzed).toBe(2);

    const r2 = await api.query.execute('how many rows are in this dataset', ds2.id);
    expect(r2.dataset_id).toBe(ds2.id);
    expect(r2.sql_query).toContain(`dataset_${ds2.id}`);
    expect(r2.records_analyzed).toBe(3);

    const r3 = await api.query.execute('how many rows are in this dataset', ds3.id);
    expect(r3.dataset_id).toBe(ds3.id);
    expect(r3.sql_query).toContain(`dataset_${ds3.id}`);
    expect(r3.records_analyzed).toBe(2);

    // 4. Register analyst and confirm missing/legacy dataset ID returns 404 and deducts 0 credits
    const analyst = await api.auth.register({
      email: `dyn_analyst_${suffix}@datapulse.io`,
      password: 'Password123!',
      full_name: `Dynamic Analyst ${suffix}`,
    });
    const balanceBefore = analyst.user.credits;

    try {
      await api.query.execute('how many rows', 'ds-retail-b');
      expect(true).toBe(false);
    } catch (err: any) {
      expect(err).toBeInstanceOf(ApiError);
      expect(err.status).toBe(404);
    }

    const meAfter = await api.auth.getMe();
    expect(meAfter.credits).toBe(balanceBefore);
  });
});
