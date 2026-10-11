import { describe, it, expect } from 'bun:test';
import {
  profileDatasetColumns,
  recommendVisualization,
} from './visualizationAnalyzer';

describe('Visualization Analyzer & Recommendation Engine', () => {
  describe('Rule 1: Empty results', () => {
    it('recommends Table when rows are empty', () => {
      const columns = ['id', 'name', 'value'];
      const rows: Record<string, any>[] = [];
      const rec = recommendVisualization(columns, rows);

      expect(rec.recommendedType).toBe('table');
      expect(rec.isActionableChart).toBe(false);
      expect(rec.title).toBe('Data Table');
      expect(rec.availableMeasures).toHaveLength(0);
      expect(rec.reason).toContain('Empty query result set');
    });

    it('handles undefined or null rows safely', () => {
      const rec = recommendVisualization(['col1'], null as any);
      expect(rec.recommendedType).toBe('table');
      expect(rec.isActionableChart).toBe(false);
    });
  });

  describe('Rule 2 & 6: Identifier Exclusion & Staff Record Directory', () => {
    it('excludes record IDs, primary keys, and UUIDs from available measures', () => {
      const columns = ['id', 'uuid', 'staff_id', 'employee_key', 'name', 'role'];
      const rows = [
        { id: 1, uuid: '550e8400-e29b-41d4-a716-446655440000', staff_id: 'STF-01', employee_key: 101, name: 'Alice', role: 'Engineer' },
        { id: 2, uuid: '550e8400-e29b-41d4-a716-446655440001', staff_id: 'STF-02', employee_key: 102, name: 'Bob', role: 'Designer' },
      ];

      const profiles = profileDatasetColumns(columns, rows);
      expect(profiles['id'].isIdentifier).toBe(true);
      expect(profiles['uuid'].isIdentifier).toBe(true);
      expect(profiles['staff_id'].isIdentifier).toBe(true);
      expect(profiles['employee_key'].isIdentifier).toBe(true);

      const rec = recommendVisualization(columns, rows, 'select staff records');
      expect(rec.availableMeasures).not.toContain('id');
      expect(rec.availableMeasures).not.toContain('uuid');
      expect(rec.availableMeasures).not.toContain('staff_id');
      expect(rec.availableMeasures).not.toContain('employee_key');
      expect(rec.availableMeasures).toHaveLength(0);
    });

    it('recommends Table and provides aggregation guidance for staff roster without metrics', () => {
      const columns = ['id', 'name', 'role', 'department', 'email'];
      const rows = [
        { id: 1, name: 'Alice Smith', role: 'Lead Engineer', department: 'Engineering', email: 'alice@corp.io' },
        { id: 2, name: 'Bob Johnson', role: 'Product Designer', department: 'Design', email: 'bob@corp.io' },
        { id: 3, name: 'Carol Williams', role: 'Staff Engineer', department: 'Engineering', email: 'carol@corp.io' },
      ];

      const rec = recommendVisualization(columns, rows, 'list of staff records');
      expect(rec.recommendedType).toBe('table');
      expect(rec.isActionableChart).toBe(false);
      expect(rec.requiresAggregationWarning).toBeDefined();
      expect(rec.requiresAggregationWarning).toContain('unaggregated individual entity records');
      expect(rec.explanation).toContain('unaggregated individual entity records');
    });

    it('identifies sequential 1-based IDs as identifiers even if named col_a', () => {
      const columns = ['row_idx', 'name'];
      const rows = [
        { row_idx: 1, name: 'One' },
        { row_idx: 2, name: 'Two' },
        { row_idx: 3, name: 'Three' },
        { row_idx: 4, name: 'Four' },
      ];

      const profiles = profileDatasetColumns(columns, rows);
      expect(profiles['row_idx'].isIdentifier).toBe(true);

      const rec = recommendVisualization(columns, rows);
      expect(rec.availableMeasures).not.toContain('row_idx');
    });
  });

  describe('Rule 3: Single Value or Summary Metrics (KPI Cards)', () => {
    it('recommends KPI cards for 1-row summary results', () => {
      const columns = ['total_revenue', 'order_count'];
      const rows = [{ total_revenue: 4500000, order_count: 1250 }];

      const rec = recommendVisualization(columns, rows, 'summary total revenue and orders');
      expect(rec.recommendedType).toBe('kpi');
      expect(rec.isActionableChart).toBe(true);
      expect(rec.availableMeasures).toContain('total_revenue');
      expect(rec.availableMeasures).toContain('order_count');
      expect(rec.title).toBe('Key Performance Indicator');
    });

    it('recommends KPI for single aggregated count', () => {
      const columns = ['staff_count'];
      const rows = [{ staff_count: 42 }];

      const rec = recommendVisualization(columns, rows);
      expect(rec.recommendedType).toBe('kpi');
      expect(rec.measureColumn).toBe('staff_count');
    });
  });

  describe('Rule 4: Time Series Trends (Line Chart)', () => {
    it('recommends Line Chart when a date/time column is present with numeric measure', () => {
      const columns = ['order_date', 'daily_revenue'];
      const rows = [
        { order_date: '2024-01-01', daily_revenue: 1200 },
        { order_date: '2024-01-02', daily_revenue: 1500 },
        { order_date: '2024-01-03', daily_revenue: 900 },
        { order_date: '2024-01-04', daily_revenue: 1800 },
        { order_date: '2024-01-05', daily_revenue: 2200 },
      ];

      const rec = recommendVisualization(columns, rows, 'revenue trend over time');
      expect(rec.recommendedType).toBe('line');
      expect(rec.dimensionColumn).toBe('order_date');
      expect(rec.measureColumn).toBe('daily_revenue');
      expect(rec.isActionableChart).toBe(true);
    });

    it('identifies 4-digit year columns as date dimensions', () => {
      const columns = ['year', 'active_users'];
      const rows = [
        { year: 2021, active_users: 10000 },
        { year: 2022, active_users: 18000 },
        { year: 2023, active_users: 25000 },
        { year: 2024, active_users: 32000 },
      ];

      const rec = recommendVisualization(columns, rows);
      expect(rec.recommendedType).toBe('line');
      expect(rec.dimensionColumn).toBe('year');
      expect(rec.measureColumn).toBe('active_users');
    });
  });

  describe('Rule 5: Proportions with Limited Categories (Donut Chart)', () => {
    it('recommends Donut Chart for 2 to 8 distinct categories with non-negative measure', () => {
      const columns = ['status', 'count'];
      const rows = [
        { status: 'Completed', count: 850 },
        { status: 'Pending', count: 120 },
        { status: 'Failed', count: 30 },
      ];

      const rec = recommendVisualization(columns, rows, 'order share by status');
      expect(rec.recommendedType).toBe('donut');
      expect(rec.dimensionColumn).toBe('status');
      expect(rec.measureColumn).toBe('count');
      expect(rec.isActionableChart).toBe(true);
      expect(rec.title).toBe('Donut / Pie Chart');
    });

    it('does not recommend Donut chart when category count exceeds 8', () => {
      const columns = ['category', 'sales'];
      const rows = Array.from({ length: 12 }, (_, i) => ({
        category: `Category ${i + 1}`,
        sales: (i + 1) * 100,
      }));

      const rec = recommendVisualization(columns, rows);
      // More than 8 categories should recommend bar chart instead of donut
      expect(rec.recommendedType).toBe('bar');
    });
  });

  describe('Rule 6: Categorical Comparison (Bar Chart)', () => {
    it('recommends Bar Chart for comparing metrics across categories', () => {
      const columns = ['department', 'average_salary'];
      const rows = [
        { department: 'Engineering', average_salary: 135000 },
        { department: 'Product', average_salary: 120000 },
        { department: 'Design', average_salary: 110000 },
        { department: 'Marketing', average_salary: 95000 },
        { department: 'Sales', average_salary: 105000 },
        { department: 'Support', average_salary: 75000 },
        { department: 'Operations', average_salary: 85000 },
        { department: 'Finance', average_salary: 115000 },
        { department: 'HR', average_salary: 80000 },
      ];

      const rec = recommendVisualization(columns, rows, 'average salary by department');
      expect(rec.recommendedType).toBe('bar');
      expect(rec.dimensionColumn).toBe('department');
      expect(rec.measureColumn).toBe('average_salary');
      expect(rec.isActionableChart).toBe(true);
    });
  });

  describe('Rule 7: Correlation between Numeric Metrics (Scatter Plot)', () => {
    it('recommends Scatter Plot when prompt indicates correlation with multiple numeric columns', () => {
      const columns = ['ad_spend', 'conversion_rate', 'customer_acquisition_cost'];
      const rows = [
        { ad_spend: 1000, conversion_rate: 0.04, customer_acquisition_cost: 25 },
        { ad_spend: 2000, conversion_rate: 0.05, customer_acquisition_cost: 22 },
        { ad_spend: 3000, conversion_rate: 0.03, customer_acquisition_cost: 29 },
        { ad_spend: 4000, conversion_rate: 0.06, customer_acquisition_cost: 20 },
      ];

      const rec = recommendVisualization(columns, rows, 'correlation between ad spend and conversion rate');
      expect(rec.recommendedType).toBe('scatter');
      expect(rec.availableMeasures.length).toBeGreaterThanOrEqual(2);
      expect(rec.isActionableChart).toBe(true);
    });
  });

  describe('Rule 8: Table Default for Entity Details & Free Text', () => {
    it('recommends Table when all columns are textual or description fields', () => {
      const columns = ['title', 'notes', 'tags'];
      const rows = [
        { title: 'Project A', notes: 'First kick-off meeting completed', tags: 'core' },
        { title: 'Project B', notes: 'Waiting for stakeholder approval', tags: 'review' },
      ];

      const rec = recommendVisualization(columns, rows);
      expect(rec.recommendedType).toBe('table');
      expect(rec.isActionableChart).toBe(false);
      expect(rec.reason).toContain('No quantitative measures');
    });
  });

  describe('Robustness: Nulls, Mixed Types, and Extremes', () => {
    it('gracefully handles nulls and non-numeric values in numeric columns', () => {
      const columns = ['product', 'rating'];
      const rows = [
        { product: 'Prod A', rating: 4.5 },
        { product: 'Prod B', rating: null },
        { product: 'Prod C', rating: 'N/A' },
        { product: 'Prod D', rating: 3.8 },
      ];

      const profiles = profileDatasetColumns(columns, rows);
      expect(profiles['rating'].nullCount).toBe(1);
      expect(profiles['product'].isCategorical).toBe(true);

      const rec = recommendVisualization(columns, rows);
      expect(rec).toBeDefined();
      expect(rec.availableDimensions).toContain('product');
    });

    it('safely handles missing columns in some rows', () => {
      const columns = ['dept', 'headcount'];
      const rows = [
        { dept: 'Tech' }, // headcount missing
        { dept: 'Sales', headcount: 20 },
      ];

      const rec = recommendVisualization(columns, rows);
      expect(rec).toBeDefined();
      expect(rec.dimensionColumn).toBe('dept');
    });
  });
});
