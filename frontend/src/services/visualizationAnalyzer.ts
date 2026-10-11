/**
 * DataPulse Query Workspace - Visualization Profiler and Recommendation Engine
 * Analyzes query result columns and sample rows to deterministically recommend
 * and configure optimal visual representations.
 */

export type ColumnType = 'numeric' | 'categorical' | 'date' | 'identifier' | 'text' | 'unknown';

export interface ColumnProfile {
  name: string;
  type: ColumnType;
  isIdentifier: boolean;
  isNumeric: boolean;
  isDate: boolean;
  isCategorical: boolean;
  distinctCount: number;
  nullCount: number;
  sampleValues: any[];
  min?: number;
  max?: number;
}

export type SupportedChartType = 'table' | 'kpi' | 'bar' | 'line' | 'donut' | 'scatter';

export interface VisualizationRecommendation {
  recommendedType: SupportedChartType;
  title: string;
  reason: string;
  explanation: string;
  dimensionColumn?: string;
  measureColumn?: string;
  secondaryMeasureColumn?: string;
  availableDimensions: string[];
  availableMeasures: string[];
  requiresAggregationWarning?: string;
  isActionableChart: boolean;
  columnProfiles: Record<string, ColumnProfile>;
}

// Identifier detection patterns
const ID_NAME_REGEX = /^(id|_id|uuid|guid|pk|row_id|row_num|row_idx|idx|index|.*_id|.*_uuid|.*_key|.*_pk|staff_id|emp_id|user_id|customer_id|order_id|product_id|item_id|record_id)$/i;

// Date/time detection patterns
const DATE_NAME_REGEX = /(date|time|timestamp|year|month|day|created_at|updated_at|period|quarter|hour|dt)/i;
const ISO_DATE_REGEX = /^\d{4}[-/](0[1-9]|1[0-2])([-/](0[1-9]|[12]\d|3[01]))?(T|\s|$)/;
const YEAR_ONLY_REGEX = /^(19\d{2}|20\d{2})$/;

/**
 * Check if a string or value is an identifier based on patterns
 */
function isValueLikelyId(val: any): boolean {
  if (val === null || val === undefined) return false;
  const s = String(val).trim();
  // UUID pattern
  if (/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(s)) return true;
  // Prefix ID pattern like ds_123, u_abc, usr_1092
  if (/^[a-z]{1,4}_[0-9a-f]{6,}$/i.test(s)) return true;
  return false;
}

/**
 * Check if a value represents a date or time
 */
function isDateValue(val: any): boolean {
  if (val === null || val === undefined) return false;
  if (typeof val === 'number') {
    // 4-digit years like 2024
    return val >= 1970 && val <= 2099;
  }
  const s = String(val).trim();
  if (YEAR_ONLY_REGEX.test(s)) return true;
  if (ISO_DATE_REGEX.test(s)) return true;
  const timestamp = Date.parse(s);
  return !isNaN(timestamp) && s.length >= 4 && /[0-9]{4}/.test(s);
}

/**
 * Check if a value is purely numeric
 */
function isNumericValue(val: any): boolean {
  if (val === null || val === undefined || val === '') return false;
  if (typeof val === 'number') return !isNaN(val) && isFinite(val);
  if (typeof val === 'boolean') return false;
  const str = String(val).trim();
  if (str === '') return false;
  const num = Number(str);
  return !isNaN(num) && isFinite(num);
}

/**
 * Analyzes columns and values of a tabular dataset
 */
export function profileDatasetColumns(
  columns: string[],
  rows: Record<string, any>[]
): Record<string, ColumnProfile> {
  const profiles: Record<string, ColumnProfile> = {};

  columns.forEach((col) => {
    let nullCount = 0;
    const valuesSet = new Set<any>();
    const samples: any[] = [];
    let numericCount = 0;
    let dateCount = 0;
    let idValueCount = 0;
    let minVal: number | undefined;
    let maxVal: number | undefined;

    rows.forEach((row) => {
      const v = row[col];
      if (v === null || v === undefined || v === '') {
        nullCount++;
      } else {
        valuesSet.add(v);
        if (samples.length < 5) samples.push(v);

        if (isNumericValue(v)) {
          numericCount++;
          const num = typeof v === 'number' ? v : Number(v);
          minVal = minVal === undefined ? num : Math.min(minVal, num);
          maxVal = maxVal === undefined ? num : Math.max(maxVal, num);
        }

        if (isDateValue(v)) {
          dateCount++;
        }

        if (isValueLikelyId(v)) {
          idValueCount++;
        }
      }
    });

    const validCount = rows.length - nullCount;
    const isNameId = ID_NAME_REGEX.test(col);
    const isNameDate = DATE_NAME_REGEX.test(col);

    const isNumeric = validCount > 0 && numericCount / validCount >= 0.75;
    const isDate = validCount > 0 && (dateCount / validCount >= 0.75 || (isNameDate && dateCount > 0));

    // Check if column is strictly an identifier
    let isIdentifier = isNameId;
    if (!isIdentifier && validCount > 0 && idValueCount / validCount >= 0.8) {
      isIdentifier = true;
    }
    // Sequential integers test (1, 2, 3...) when 100% unique integers
    if (
      !isIdentifier &&
      isNumeric &&
      validCount > 1 &&
      valuesSet.size === validCount &&
      minVal === 1 &&
      maxVal === validCount
    ) {
      isIdentifier = true;
    }

    // Categorical classification
    const distinctRatio = validCount > 0 ? valuesSet.size / validCount : 0;
    const isCategorical =
      !isIdentifier &&
      !isDate &&
      !isNumeric &&
      (valuesSet.size <= 50 || distinctRatio <= 0.6) &&
      validCount > 0;

    let detectedType: ColumnType = 'unknown';
    if (isIdentifier) detectedType = 'identifier';
    else if (isDate) detectedType = 'date';
    else if (isNumeric) detectedType = 'numeric';
    else if (isCategorical) detectedType = 'categorical';
    else detectedType = 'text';

    profiles[col] = {
      name: col,
      type: detectedType,
      isIdentifier,
      isNumeric,
      isDate,
      isCategorical,
      distinctCount: valuesSet.size,
      nullCount,
      sampleValues: samples,
      min: minVal,
      max: maxVal,
    };
  });

  return profiles;
}

/**
 * Recommends the optimal visualization for a query result
 */
export function recommendVisualization(
  columns: string[],
  rows: Record<string, any>[],
  queryPrompt: string = ''
): VisualizationRecommendation {
  if (!columns || columns.length === 0 || !rows || rows.length === 0) {
    return {
      recommendedType: 'table',
      title: 'Data Table',
      reason: 'Empty query result set',
      explanation: 'The query executed successfully but produced an empty result set. Showing standard table view.',
      availableDimensions: [],
      availableMeasures: [],
      isActionableChart: false,
      columnProfiles: {},
    };
  }

  const profiles = profileDatasetColumns(columns, rows);

  // Separate valid candidate dimensions and measures
  // RULE: Never include identifier or date columns in availableMeasures!
  const availableDimensions: string[] = [];
  const availableMeasures: string[] = [];
  const dateColumns: string[] = [];
  const categoricalColumns: string[] = [];

  columns.forEach((col) => {
    const prof = profiles[col];
    if (prof.isNumeric && !prof.isIdentifier && !prof.isDate) {
      availableMeasures.push(col);
    }
    if (prof.isDate) {
      dateColumns.push(col);
      availableDimensions.push(col);
    } else if (prof.isCategorical && !prof.isIdentifier) {
      categoricalColumns.push(col);
      availableDimensions.push(col);
    } else if (!prof.isIdentifier && !prof.isNumeric) {
      availableDimensions.push(col);
    }
  });

  // If no dimension found without identifiers, fallback to any non-measure column for labels
  if (availableDimensions.length === 0) {
    columns.forEach((col) => {
      if (!availableMeasures.includes(col)) availableDimensions.push(col);
    });
  }

  // 1. Single Value / Summary Metric (KPI Card)
  if (rows.length === 1) {
    const firstMeasure = availableMeasures[0] || columns[0];
    return {
      recommendedType: 'kpi',
      title: 'Key Performance Indicator',
      reason: 'Single aggregated value',
      explanation: `The query returned a single summary record for "${firstMeasure}". Ideal for a prominent KPI metric card.`,
      dimensionColumn: undefined,
      measureColumn: firstMeasure,
      availableDimensions,
      availableMeasures,
      isActionableChart: true,
      columnProfiles: profiles,
    };
  }

  // 2. No valid numeric measures (e.g. employee roster: name, role, email, id)
  if (availableMeasures.length === 0) {
    const catCol = categoricalColumns[0] || columns[0];
    return {
      recommendedType: 'table',
      title: 'Detailed Entity Records Table',
      reason: 'No quantitative measures or numeric metrics in result',
      explanation: `This result contains unaggregated individual entity records (such as ${columns.slice(0, 3).join(', ')}) rather than quantitative measures. Displaying tabular view.`,
      availableDimensions,
      availableMeasures: [],
      requiresAggregationWarning: `Query returned unaggregated individual entity records. To visualize this data as a chart without altering records, ask a follow-up query to aggregate it (e.g., "count of ${catCol} by category" or "average by group").`,
      isActionableChart: false,
      columnProfiles: profiles,
    };
  }

  const primaryMeasure = availableMeasures[0];

  // 3. Time Series / Trends Over Time (Line Chart)
  if (dateColumns.length > 0 && availableMeasures.length > 0) {
    const dateCol = dateColumns[0];
    return {
      recommendedType: 'line',
      title: 'Timeline Trend Line Chart',
      reason: `Temporal trend over ${dateCol}`,
      explanation: `Detected chronological dates in "${dateCol}" alongside measure "${primaryMeasure}". Visualizing trajectory over time.`,
      dimensionColumn: dateCol,
      measureColumn: primaryMeasure,
      availableDimensions,
      availableMeasures,
      isActionableChart: true,
      columnProfiles: profiles,
    };
  }

  // 4. Scatter Plot (Relationship between 2 distinct numeric measures)
  // Check if query is explicitly asking for correlation or if there are >=2 measures and no categorical dimension
  const isCorrelationPrompt = /(correlation|scatter|relationship|vs|versus)/i.test(queryPrompt);
  if (availableMeasures.length >= 2 && rows.length >= 3 && (isCorrelationPrompt || categoricalColumns.length === 0)) {
    const measureX = availableMeasures[0];
    const measureY = availableMeasures[1];
    return {
      recommendedType: 'scatter',
      title: 'Numeric Correlation Scatter Plot',
      reason: `Correlation between ${measureX} and ${measureY}`,
      explanation: `Identified two distinct numeric measures ("${measureX}" and "${measureY}"). Visualizing relationships across data points.`,
      dimensionColumn: measureX,
      measureColumn: measureY,
      secondaryMeasureColumn: measureY,
      availableDimensions,
      availableMeasures,
      isActionableChart: true,
      columnProfiles: profiles,
    };
  }

  // 5. Proportions / Part-to-Whole (Donut / Pie Chart)
  // Low distinct categories (2 - 8) and non-negative measures
  const firstCatCol = categoricalColumns[0];
  const distinctCatCount = firstCatCol ? profiles[firstCatCol].distinctCount : rows.length;
  const isPositiveMeasure = rows.every((r) => Number(r[primaryMeasure]) >= 0);

  if (firstCatCol && distinctCatCount >= 2 && distinctCatCount <= 8 && isPositiveMeasure && rows.length <= 15) {
    return {
      recommendedType: 'donut',
      title: 'Donut / Pie Chart',
      reason: `${distinctCatCount} distinct ${firstCatCol} categories`,
      explanation: `Detected ${distinctCatCount} categories in "${firstCatCol}" with positive values for "${primaryMeasure}". Ideal for part-to-whole distribution.`,
      dimensionColumn: firstCatCol,
      measureColumn: primaryMeasure,
      availableDimensions,
      availableMeasures,
      isActionableChart: true,
      columnProfiles: profiles,
    };
  }

  // 6. Categorical Comparisons (Bar Chart)
  if (firstCatCol && availableMeasures.length > 0) {
    return {
      recommendedType: 'bar',
      title: 'Category Comparison Bar Chart',
      reason: `Comparing ${primaryMeasure} across ${firstCatCol}`,
      explanation: `Comparing metric "${primaryMeasure}" across categories of "${firstCatCol}". Best visualized as a comparative bar chart.`,
      dimensionColumn: firstCatCol,
      measureColumn: primaryMeasure,
      availableDimensions,
      availableMeasures,
      isActionableChart: true,
      columnProfiles: profiles,
    };
  }

  // 7. Fallback to Bar chart if any non-measure dimension exists
  if (availableDimensions.length > 0 && availableMeasures.length > 0) {
    const dimCol = availableDimensions[0];
    return {
      recommendedType: 'bar',
      title: 'Data Bar Chart',
      reason: `Comparing ${primaryMeasure} by ${dimCol}`,
      explanation: `Visualizing "${primaryMeasure}" across "${dimCol}" values.`,
      dimensionColumn: dimCol,
      measureColumn: primaryMeasure,
      availableDimensions,
      availableMeasures,
      isActionableChart: true,
      columnProfiles: profiles,
    };
  }

  // Default fallback: Table
  return {
    recommendedType: 'table',
    title: 'Data Grid Table',
    reason: 'Standard tabular layout',
    explanation: 'Detailed table layout is the most effective format for this result set.',
    availableDimensions,
    availableMeasures,
    isActionableChart: false,
    columnProfiles: profiles,
  };
}
