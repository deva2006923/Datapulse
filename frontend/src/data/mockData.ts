import { UserAccount, AppDataset, WalletTransaction, QueryHistoryItem } from '../types';

export const MOCK_DATA_VERSION = 'datapulse_v3_2026';

export const INITIAL_USERS: Record<string, UserAccount> = {
  'demo-user': {
    id: 'demo-user',
    name: 'Demo User',
    email: 'demo@datapulse.io',
    role: 'Contributor',
    credits: 340, // Exactly equals sum of wallet ledger
    reputationScore: 94,
    contributedDatasetIds: ['ds-retail-a', 'ds-student-raw', 'ds-noise-rejected'],
    unlockedDatasetIds: ['ds-heart', 'ds-telecom-churn'], // Exactly 2 unlocked external datasets
    joinedDate: '2026-09-08',
  },
  'alice': {
    id: 'alice',
    name: 'Alice Smith',
    email: 'alice@datapulse.io',
    role: 'Contributor',
    credits: 240,
    reputationScore: 98,
    contributedDatasetIds: ['ds-heart', 'ds-customer-retention'],
    unlockedDatasetIds: ['ds-retail-a', 'ds-student-raw'],
    joinedDate: '2026-08-01',
  },
  'bob': {
    id: 'bob',
    name: 'Bob Miller',
    email: 'bob@datapulse.io',
    role: 'Data Analyst',
    credits: 100, // Starts at 100 credits
    reputationScore: 89,
    contributedDatasetIds: ['ds-telecom-churn', 'ds-bank-churn', 'ds-retail-b'],
    unlockedDatasetIds: ['ds-retail-b'],
    joinedDate: '2026-09-28',
  },
};

export const INITIAL_DATASETS: AppDataset[] = [
  // 1. Heart Disease Dataset (Healthcare, 50,000 rows, quality 91, relevance 94, cost 20, by Alice)
  {
    id: 'ds-heart',
    name: 'heart_disease_clinical_records.csv',
    title: 'Heart Disease Dataset',
    description: 'Comprehensive clinical biomarker records, cardiovascular parameters, serum cholesterol, blood pressure, and diagnostic outcomes.',
    domain: 'Healthcare',
    format: 'csv',
    authorId: 'alice',
    authorName: 'Alice Smith',
    cost: 20,
    qualityScore: 91,
    relevanceScore: 94,
    overallScore: (91 + 94) / 2, // 92.5
    status: 'APPROVED',
    tags: ['healthcare', 'cardiology', 'cholesterol', 'clinical'],
    license: 'Open Data Commons',
    usageCount: 142,
    qualityBreakdown: {
      completeness: 96,
      validity: 93,
      uniqueness: 90,
      consistency: 85,
    },
    rowCount: 50000,
    columnCount: 6,
    columns: [
      { name: 'patient_id', type: 'UUID', nullCount: 0, nullPct: 0, distinctCount: 50000, synonyms: ['id', 'patient_code'], description: 'Unique hospital identifier' },
      { name: 'age', type: 'Int32', nullCount: 0, nullPct: 0, distinctCount: 65, synonyms: ['years', 'patient_age'], description: 'Age in completed years' },
      { name: 'cholesterol', type: 'Float64 (mg/dL)', nullCount: 15, nullPct: 0.03, distinctCount: 420, synonyms: ['serum_chol', 'lipid', 'cholesterol_level'], description: 'Serum cholesterol concentration' },
      { name: 'resting_bp', type: 'Int32 (mmHg)', nullCount: 0, nullPct: 0, distinctCount: 110, synonyms: ['blood_pressure', 'bp', 'systolic'], description: 'Resting systolic blood pressure' },
      { name: 'fasting_glucose', type: 'Float64', nullCount: 8, nullPct: 0.016, distinctCount: 195, synonyms: ['blood_sugar', 'glucose'], description: 'Fasting glucose level in mg/dL' },
      { name: 'heart_disease_risk', type: 'Categorical', nullCount: 0, nullPct: 0, distinctCount: 3, synonyms: ['risk_tier', 'diagnosis', 'cardiac_risk'], description: 'Low, Moderate, High risk' },
    ],
    previewRows: [
      { patient_id: 'P-10842', age: 62, cholesterol: 312.0, resting_bp: 145, fasting_glucose: 124.5, heart_disease_risk: 'High' },
      { patient_id: 'P-10491', age: 58, cholesterol: 298.5, resting_bp: 138, fasting_glucose: 108.0, heart_disease_risk: 'High' },
      { patient_id: 'P-11204', age: 71, cholesterol: 284.0, resting_bp: 152, fasting_glucose: 142.0, heart_disease_risk: 'Moderate' },
      { patient_id: 'P-10332', age: 49, cholesterol: 276.5, resting_bp: 126, fasting_glucose: 94.0, heart_disease_risk: 'Moderate' },
      { patient_id: 'P-11899', age: 64, cholesterol: 268.0, resting_bp: 134, fasting_glucose: 115.0, heart_disease_risk: 'High' },
    ],
    createdAt: '2026-08-15',
    currentVersion: 'v1.0',
    versionHistory: [
      {
        version: 'v1.0',
        date: '2026-08-15',
        author: 'Alice Smith',
        quality: 91,
        relevance: 94,
        changesSummary: 'Initial clinical data extraction and de-identification.',
      },
    ],
    unlockedBy: ['alice', 'demo-user'],
    sampleQueries: [
      'Show top 10 patients by cholesterol',
      'Average cholesterol level grouped by heart disease risk',
      'Patients older than 60 with resting bp over 140',
      'Count of patients in each risk tier'
    ],
  },

  // 2. Telecom Customer Churn (Telecom, quality 88, relevance 96, cost 20, by Bob)
  {
    id: 'ds-telecom-churn',
    name: 'telecom_customer_churn_q3.csv',
    title: 'Telecom Customer Churn',
    description: 'Subscriber telemetry, contract length, fiber service, monthly recurring charges, support incidents, and churn status.',
    domain: 'Telecom',
    format: 'csv',
    authorId: 'bob',
    authorName: 'Bob Miller',
    cost: 20,
    qualityScore: 88,
    relevanceScore: 96,
    overallScore: (88 + 96) / 2, // 92
    status: 'APPROVED',
    tags: ['churn', 'telecom', 'subscribers', 'retention'],
    license: 'MIT',
    usageCount: 230,
    qualityBreakdown: {
      completeness: 92,
      validity: 90,
      uniqueness: 88,
      consistency: 82,
    },
    rowCount: 28400,
    columnCount: 6,
    columns: [
      { name: 'customer_id', type: 'UUID', nullCount: 0, nullPct: 0, distinctCount: 28400, synonyms: ['id', 'user_id', 'subscriber_id'], description: 'Unique customer identifier' },
      { name: 'tenure_months', type: 'Int32', nullCount: 0, nullPct: 0, distinctCount: 72, synonyms: ['tenure', 'months_active', 'account_age'], description: 'Duration of subscription' },
      { name: 'monthly_charges', type: 'Float64 ($)', nullCount: 0, nullPct: 0, distinctCount: 1620, synonyms: ['monthly_spend', 'bill_amount', 'mrr'], description: 'Monthly fee' },
      { name: 'contract_type', type: 'Categorical', nullCount: 0, nullPct: 0, distinctCount: 3, synonyms: ['contract', 'subscription_plan'], description: 'Month-to-month, 1-yr, 2-yr' },
      { name: 'total_charges', type: 'Float64 ($)', nullCount: 12, nullPct: 0.04, distinctCount: 21400, synonyms: ['lifetime_spend', 'total_billed'], description: 'Cumulative charges' },
      { name: 'churn_status', type: 'Boolean', nullCount: 0, nullPct: 0, distinctCount: 2, synonyms: ['churn', 'cancelled', 'attrition'], description: 'Yes or No' },
    ],
    previewRows: [
      { customer_id: 'C-7590-VH', tenure_months: 1, monthly_charges: 29.85, contract_type: 'Month-to-month', total_charges: 29.85, churn_status: 'No' },
      { customer_id: 'C-5575-GN', tenure_months: 34, monthly_charges: 56.95, contract_type: 'One year', total_charges: 1889.50, churn_status: 'No' },
      { customer_id: 'C-3668-QP', tenure_months: 2, monthly_charges: 53.85, contract_type: 'Month-to-month', total_charges: 108.15, churn_status: 'Yes' },
      { customer_id: 'C-7795-CF', tenure_months: 45, monthly_charges: 42.30, contract_type: 'One year', total_charges: 1840.75, churn_status: 'No' },
      { customer_id: 'C-9237-HQ', tenure_months: 2, monthly_charges: 70.70, contract_type: 'Month-to-month', total_charges: 151.65, churn_status: 'Yes' },
    ],
    createdAt: '2026-09-02',
    currentVersion: 'v1.0',
    versionHistory: [
      {
        version: 'v1.0',
        date: '2026-09-02',
        author: 'Bob Miller',
        quality: 88,
        relevance: 96,
        changesSummary: 'Extracted subscriber billing and churn telemetry.',
      },
    ],
    unlockedBy: ['bob', 'demo-user'],
    sampleQueries: [
      'Show high churn customers with monthly spend over 60',
      'Average tenure of churned customers vs retained',
      'Count of customers grouped by contract type',
      'Top 10 customers by total charges on month-to-month plan'
    ],
  },

  // 3. Customer Retention Dataset (Retail, relevance to churn 91, quality 86, cost 20, by Alice)
  {
    id: 'ds-customer-retention',
    name: 'retail_customer_retention.xlsx',
    title: 'Customer Retention Dataset',
    description: 'Omnichannel retail loyalty program metrics, purchase cadence, coupon usage, and likelihood to churn.',
    domain: 'Retail',
    format: 'xlsx',
    authorId: 'alice',
    authorName: 'Alice Smith',
    cost: 20,
    qualityScore: 86,
    relevanceScore: 91,
    overallScore: (86 + 91) / 2, // 88.5
    status: 'APPROVED',
    tags: ['retail', 'retention', 'churn', 'loyalty'],
    license: 'CC-BY-4.0',
    usageCount: 95,
    qualityBreakdown: {
      completeness: 89,
      validity: 88,
      uniqueness: 84,
      consistency: 83,
    },
    rowCount: 32000,
    columnCount: 5,
    columns: [
      { name: 'member_id', type: 'String', nullCount: 0, nullPct: 0, distinctCount: 32000, synonyms: ['id', 'user_id', 'customer_id'], description: 'Loyalty member code' },
      { name: 'visit_frequency', type: 'Int32', nullCount: 0, nullPct: 0, distinctCount: 45, synonyms: ['visits', 'frequency'], description: 'Visits per quarter' },
      { name: 'basket_size_avg', type: 'Float64 ($)', nullCount: 0, nullPct: 0, distinctCount: 2200, synonyms: ['order_value', 'spend'], description: 'Average cart size' },
      { name: 'days_since_last_order', type: 'Int32', nullCount: 5, nullPct: 0.015, distinctCount: 180, synonyms: ['recency', 'inactivity'], description: 'Days since previous transaction' },
      { name: 'retention_status', type: 'Categorical', nullCount: 0, nullPct: 0, distinctCount: 2, synonyms: ['churn', 'retained', 'attrition'], description: 'Active or At-Risk' },
    ],
    previewRows: [
      { member_id: 'MEM-8801', visit_frequency: 14, basket_size_avg: 78.50, days_since_last_order: 4, retention_status: 'Active' },
      { member_id: 'MEM-8802', visit_frequency: 3, basket_size_avg: 124.00, days_since_last_order: 62, retention_status: 'At-Risk' },
      { member_id: 'MEM-8803', visit_frequency: 22, basket_size_avg: 45.20, days_since_last_order: 2, retention_status: 'Active' },
      { member_id: 'MEM-8804', visit_frequency: 1, basket_size_avg: 34.00, days_since_last_order: 110, retention_status: 'At-Risk' },
      { member_id: 'MEM-8805', visit_frequency: 8, basket_size_avg: 92.10, days_since_last_order: 18, retention_status: 'Active' },
    ],
    createdAt: '2026-08-25',
    currentVersion: 'v1.0',
    versionHistory: [
      {
        version: 'v1.0',
        date: '2026-08-25',
        author: 'Alice Smith',
        quality: 86,
        relevance: 91,
        changesSummary: 'Compiled retail loyalty transaction cohort retention.',
      },
    ],
    unlockedBy: ['alice'],
    sampleQueries: [
      'Show at-risk members with days since last order over 60',
      'Average basket size of retained vs at-risk customers',
      'Top 10 members by quarterly visit frequency'
    ],
  },

  // 4. Bank Customer Churn (Finance, relevance 87, quality 89, cost 20, by Bob)
  {
    id: 'ds-bank-churn',
    name: 'bank_customer_churn_records.csv',
    title: 'Bank Customer Churn',
    description: 'Commercial banking customer portfolio, credit score, account balances, product count, active credit card flag, and account closure churn.',
    domain: 'Finance',
    format: 'csv',
    authorId: 'bob',
    authorName: 'Bob Miller',
    cost: 20,
    qualityScore: 89,
    relevanceScore: 87,
    overallScore: (89 + 87) / 2, // 88
    status: 'APPROVED',
    tags: ['banking', 'finance', 'churn', 'credit-score'],
    license: 'Open Data Commons',
    usageCount: 165,
    qualityBreakdown: {
      completeness: 94,
      validity: 91,
      uniqueness: 88,
      consistency: 83,
    },
    rowCount: 20000,
    columnCount: 6,
    columns: [
      { name: 'account_number', type: 'String', nullCount: 0, nullPct: 0, distinctCount: 20000, synonyms: ['id', 'acct_num', 'customer_id'], description: 'Bank account number' },
      { name: 'credit_score', type: 'Int32', nullCount: 0, nullPct: 0, distinctCount: 450, synonyms: ['fico', 'score'], description: 'FICO credit score' },
      { name: 'balance', type: 'Float64 ($)', nullCount: 0, nullPct: 0, distinctCount: 11400, synonyms: ['account_balance', 'savings'], description: 'Total deposit balance' },
      { name: 'products_count', type: 'Int32', nullCount: 0, nullPct: 0, distinctCount: 4, synonyms: ['products', 'services_count'], description: 'Number of active bank products' },
      { name: 'is_active_member', type: 'Boolean', nullCount: 0, nullPct: 0, distinctCount: 2, synonyms: ['active', 'engagement'], description: '1 if active, 0 otherwise' },
      { name: 'churned', type: 'Boolean', nullCount: 0, nullPct: 0, distinctCount: 2, synonyms: ['churn', 'exited', 'cancelled'], description: '1 if account closed' },
    ],
    previewRows: [
      { account_number: 'ACCT-9011', credit_score: 619, balance: 0.00, products_count: 1, is_active_member: true, churned: true },
      { account_number: 'ACCT-9012', credit_score: 608, balance: 83807.86, products_count: 1, is_active_member: false, churned: false },
      { account_number: 'ACCT-9013', credit_score: 502, balance: 159660.80, products_count: 3, is_active_member: false, churned: true },
      { account_number: 'ACCT-9014', credit_score: 699, balance: 0.00, products_count: 2, is_active_member: false, churned: false },
      { account_number: 'ACCT-9015', credit_score: 850, balance: 125510.82, products_count: 1, is_active_member: true, churned: false },
    ],
    createdAt: '2026-08-30',
    currentVersion: 'v1.0',
    versionHistory: [
      {
        version: 'v1.0',
        date: '2026-08-30',
        author: 'Bob Miller',
        quality: 89,
        relevance: 87,
        changesSummary: 'Financial accounts ledger extraction with privacy sanitization.',
      },
    ],
    unlockedBy: ['bob'],
    sampleQueries: [
      'Show accounts with balance over 100000 that churned',
      'Average credit score of churned accounts vs active accounts',
      'Count of customers grouped by products count'
    ],
  },

  // 5. Retail Customers A (columns: customer_name, purchase_amount, city, quality 84, relevance 82, cost 20, by Demo User)
  {
    id: 'ds-retail-a',
    name: 'retail_customers_a.csv',
    title: 'Retail Customers A',
    description: 'Demographic and transactional consumer log including individual customer names, total purchase value, and geographic city.',
    domain: 'Retail',
    format: 'csv',
    authorId: 'demo-user',
    authorName: 'Demo User',
    cost: 20,
    qualityScore: 84,
    relevanceScore: 82,
    overallScore: (84 + 82) / 2, // 83
    status: 'APPROVED',
    tags: ['retail', 'customers', 'demographics', 'sales'],
    license: 'MIT',
    usageCount: 110,
    qualityBreakdown: {
      completeness: 88,
      validity: 86,
      uniqueness: 82,
      consistency: 80,
    },
    rowCount: 18000,
    columnCount: 3,
    columns: [
      { name: 'customer_name', type: 'String', nullCount: 0, nullPct: 0, distinctCount: 14200, synonyms: ['name', 'client', 'buyer'], description: 'Customer full name' },
      { name: 'purchase_amount', type: 'Float64 ($)', nullCount: 0, nullPct: 0, distinctCount: 3100, synonyms: ['amount_spent', 'spend', 'total_sales'], description: 'Total purchase amount' },
      { name: 'city', type: 'String', nullCount: 0, nullPct: 0, distinctCount: 48, synonyms: ['location', 'town', 'metro'], description: 'Metro residence city' },
    ],
    previewRows: [
      { customer_name: 'Arthur Morgan', purchase_amount: 1420.50, city: 'Chicago' },
      { customer_name: 'Sadie Adler', purchase_amount: 890.00, city: 'Denver' },
      { customer_name: 'John Marston', purchase_amount: 450.25, city: 'Dallas' },
      { customer_name: 'Charles Smith', purchase_amount: 120.00, city: 'Seattle' },
      { customer_name: 'Abigail Roberts', purchase_amount: 760.80, city: 'Boston' },
    ],
    createdAt: '2026-09-12',
    currentVersion: 'v1.0',
    versionHistory: [
      {
        version: 'v1.0',
        date: '2026-09-12',
        author: 'Demo User',
        quality: 84,
        relevance: 82,
        changesSummary: 'Initial schema ingestion and city standardization.',
      },
    ],
    unlockedBy: ['demo-user', 'alice', 'bob'],
    sampleQueries: [
      'Show top 5 customers by purchase amount',
      'Average purchase amount grouped by city',
      'Customers located in Chicago with spend over 500'
    ],
  },

  // 6. Retail Customers B (columns: client_name, amount_spent, location, quality 85, relevance 83, cost 20, by Bob)
  {
    id: 'ds-retail-b',
    name: 'retail_customers_b.xlsx',
    title: 'Retail Customers B',
    description: 'Parallel retail consumer extract utilizing synonym column variants (client_name, amount_spent, location).',
    domain: 'Retail',
    format: 'xlsx',
    authorId: 'bob',
    authorName: 'Bob Miller',
    cost: 20,
    qualityScore: 85,
    relevanceScore: 83,
    overallScore: (85 + 83) / 2, // 84
    status: 'APPROVED',
    tags: ['retail', 'consumers', 'synonyms', 'sales'],
    license: 'Apache 2.0',
    usageCount: 88,
    qualityBreakdown: {
      completeness: 89,
      validity: 87,
      uniqueness: 83,
      consistency: 81,
    },
    rowCount: 19500,
    columnCount: 3,
    columns: [
      { name: 'client_name', type: 'String', nullCount: 0, nullPct: 0, distinctCount: 15100, synonyms: ['customer_name', 'client', 'buyer'], description: 'Client full name' },
      { name: 'amount_spent', type: 'Float64 ($)', nullCount: 0, nullPct: 0, distinctCount: 3400, synonyms: ['purchase_amount', 'spend', 'total_price'], description: 'Total revenue spent' },
      { name: 'location', type: 'String', nullCount: 0, nullPct: 0, distinctCount: 52, synonyms: ['city', 'region', 'area'], description: 'City/regional jurisdiction' },
    ],
    previewRows: [
      { client_name: 'Elena Rostova', amount_spent: 1850.00, location: 'San Francisco' },
      { client_name: 'Marcus Vance', amount_spent: 640.20, location: 'Austin' },
      { client_name: 'Chloe Frazer', amount_spent: 980.50, location: 'New York' },
      { client_name: 'Nathan Drake', amount_spent: 420.00, location: 'Miami' },
      { client_name: 'Victor Sullivan', amount_spent: 1250.75, location: 'Chicago' },
    ],
    createdAt: '2026-09-14',
    currentVersion: 'v1.0',
    versionHistory: [
      {
        version: 'v1.0',
        date: '2026-09-14',
        author: 'Bob Miller',
        quality: 85,
        relevance: 83,
        changesSummary: 'Exported warehouse client purchases with alternate synonym headers.',
      },
    ],
    unlockedBy: ['bob'],
    sampleQueries: [
      'Show clients with amount spent over 1000 dollars',
      'Average amount spent by location',
      'Top 5 clients in San Francisco'
    ],
  },

  // 7. Student Performance (Raw) (Education, two versions: v1 quality 70 by Bob, v2 quality 91 by Demo User, +21, 15 credits awarded)
  {
    id: 'ds-student-raw',
    name: 'student_performance_benchmark.csv',
    title: 'Student Performance (Raw)',
    description: 'Academic exam scores in mathematics, reading and writing alongside parental education, study hours, and lunch assistance.',
    domain: 'Education',
    format: 'csv',
    authorId: 'demo-user', // Currently maintained by Demo User (v2 author)
    authorName: 'Demo User',
    cost: 20,
    qualityScore: 91,
    relevanceScore: 92,
    overallScore: (91 + 92) / 2, // 91.5
    status: 'APPROVED',
    tags: ['education', 'students', 'test-scores', 'benchmark'],
    license: 'MIT',
    usageCount: 175,
    qualityBreakdown: {
      completeness: 95,
      validity: 92,
      uniqueness: 90,
      consistency: 87,
    },
    rowCount: 12000,
    columnCount: 5,
    columns: [
      { name: 'student_id', type: 'String', nullCount: 0, nullPct: 0, distinctCount: 12000, synonyms: ['id', 'pupil_id'], description: 'Student identifier' },
      { name: 'math_score', type: 'Int32', nullCount: 0, nullPct: 0, distinctCount: 100, synonyms: ['math', 'mathematics'], description: 'Score out of 100' },
      { name: 'reading_score', type: 'Int32', nullCount: 0, nullPct: 0, distinctCount: 100, synonyms: ['reading', 'verbal'], description: 'Score out of 100' },
      { name: 'writing_score', type: 'Int32', nullCount: 0, nullPct: 0, distinctCount: 100, synonyms: ['writing', 'essay'], description: 'Score out of 100' },
      { name: 'study_hours_weekly', type: 'Float64', nullCount: 0, nullPct: 0, distinctCount: 50, synonyms: ['study_time', 'hours'], description: 'Weekly self-study hours' },
    ],
    previewRows: [
      { student_id: 'STU-101', math_score: 88, reading_score: 92, writing_score: 90, study_hours_weekly: 16.5 },
      { student_id: 'STU-102', math_score: 72, reading_score: 75, writing_score: 70, study_hours_weekly: 8.0 },
      { student_id: 'STU-103', math_score: 95, reading_score: 98, writing_score: 94, study_hours_weekly: 22.0 },
      { student_id: 'STU-104', math_score: 64, reading_score: 68, writing_score: 62, study_hours_weekly: 6.5 },
      { student_id: 'STU-105', math_score: 81, reading_score: 84, writing_score: 83, study_hours_weekly: 12.0 },
    ],
    createdAt: '2026-08-10',
    currentVersion: 'v2.0',
    versionHistory: [
      {
        version: 'v2.0',
        date: '2026-09-20',
        author: 'Demo User',
        quality: 91,
        relevance: 92,
        changesSummary: 'Imputed missing reading scores, deduplicated student IDs, and normalized weekly hours (+21 quality boost, 15 credits awarded).',
      },
      {
        version: 'v1.0',
        date: '2026-08-10',
        author: 'Bob Miller',
        quality: 70,
        relevance: 78,
        changesSummary: 'Raw ingestion with missing test records and inconsistent formatting.',
      },
    ],
    unlockedBy: ['demo-user', 'alice', 'bob'],
    sampleQueries: [
      'Show students with math score over 90',
      'Average reading score vs writing score by study hours',
      'Top 5 students by aggregate academic performance'
    ],
  },

  // 8. Random Noise Sample (Technology, owned by Demo User, REJECTED)
  {
    id: 'ds-noise-rejected',
    name: 'random_noise_sample_v0.csv',
    title: 'Random Noise Sample',
    description: 'Synthetic sensor telemetry packet stream with uncalibrated signal noise and corrupted timestamps.',
    domain: 'Technology',
    format: 'csv',
    authorId: 'demo-user',
    authorName: 'Demo User',
    cost: 20,
    qualityScore: 32.5,
    relevanceScore: 28,
    overallScore: (32.5 + 28) / 2, // 30.25
    status: 'REJECTED',
    rejectionReasons: 'Quality score 32.5 is below the minimum of 40. Main problems: 41% missing values; 18% duplicate rows.',
    tags: ['technology', 'sensors', 'noise', 'rejected'],
    license: 'MIT',
    usageCount: 0,
    qualityBreakdown: {
      completeness: 35,
      validity: 38,
      uniqueness: 30,
      consistency: 27,
    },
    rowCount: 5400,
    columnCount: 3,
    columns: [
      { name: 'sensor_uid', type: 'String', nullCount: 2200, nullPct: 40.7, distinctCount: 140, synonyms: ['id'], description: 'Corrupted hardware ID' },
      { name: 'signal_mv', type: 'Float64', nullCount: 1800, nullPct: 33.3, distinctCount: 890, synonyms: ['voltage'], description: 'Noisy millivolt reading' },
      { name: 'err_code', type: 'Int32', nullCount: 950, nullPct: 17.6, distinctCount: 12, synonyms: ['error'], description: 'Hardware fault code' },
    ],
    previewRows: [
      { sensor_uid: 'SN-001', signal_mv: null, err_code: 99 },
      { sensor_uid: null, signal_mv: 42.1, err_code: null },
      { sensor_uid: 'SN-001', signal_mv: null, err_code: 99 },
      { sensor_uid: 'SN-004', signal_mv: -999.0, err_code: 404 },
      { sensor_uid: null, signal_mv: null, err_code: 500 },
    ],
    createdAt: '2026-09-22',
    currentVersion: 'v1.0',
    versionHistory: [
      {
        version: 'v1.0',
        date: '2026-09-22',
        author: 'Demo User',
        quality: 32.5,
        relevance: 28,
        changesSummary: 'Initial upload rejected: Quality score 32.5 is below the minimum of 40.',
      },
    ],
    unlockedBy: ['demo-user'],
    sampleQueries: [
      'Show error code frequency distribution'
    ],
  },
];

// 30-day back-dated transaction history across 12 days for Demo User: exactly sums to 340 credits
export const INITIAL_TRANSACTIONS: WalletTransaction[] = [
  // Day -28 (2026-09-08)
  {
    id: 'tx_d01',
    userId: 'demo-user',
    type: 'SIGNUP_BONUS',
    amount: 100,
    description: 'Welcome Sign-up Credit Allocation (+100 credits)',
    timestamp: '2026-09-08 10:00:00',
  },
  // Day -25 (2026-09-11)
  {
    id: 'tx_d02',
    userId: 'demo-user',
    type: 'UPLOAD_REWARD',
    amount: 90,
    description: 'Dataset Ingestion Reward for Retail Customers A (+90 credits)',
    timestamp: '2026-09-11 14:15:00',
  },
  // Day -22 (2026-09-14)
  {
    id: 'tx_d03',
    userId: 'demo-user',
    type: 'QUERY_CHARGE',
    amount: -20,
    description: 'Unlock & Query Charge for Telecom Customer Churn (-20 credits)',
    timestamp: '2026-09-14 11:30:00',
  },
  // Day -20 (2026-09-16)
  {
    id: 'tx_d04',
    userId: 'demo-user',
    type: 'CONTRIBUTOR_ROYALTY',
    amount: 20,
    description: 'Unlock Royalty from Alice Smith on Retail Customers A (+20 credits)',
    timestamp: '2026-09-16 09:45:00',
  },
  // Day -17 (2026-09-19)
  {
    id: 'tx_d05',
    userId: 'demo-user',
    type: 'QUERY_CHARGE',
    amount: -20,
    description: 'Unlock & Query Charge for Heart Disease Dataset (-20 credits)',
    timestamp: '2026-09-19 16:20:00',
  },
  // Day -16 (2026-09-20)
  {
    id: 'tx_d06',
    userId: 'demo-user',
    type: 'IMPROVEMENT_REWARD',
    amount: 15,
    description: 'Version Improvement Reward for Student Performance (Raw) v2.0 (+15 credits)',
    timestamp: '2026-09-20 17:10:00',
  },
  // Day -14 (2026-09-22)
  {
    id: 'tx_d07',
    userId: 'demo-user',
    type: 'CONTRIBUTOR_ROYALTY',
    amount: 20,
    description: 'Unlock Royalty from Bob Miller on Retail Customers A (+20 credits)',
    timestamp: '2026-09-22 13:05:00',
  },
  // Day -12 (2026-09-24)
  {
    id: 'tx_d08',
    userId: 'demo-user',
    type: 'CONTRIBUTOR_ROYALTY',
    amount: 20,
    description: 'Unlock Royalty from Alice Smith on Student Performance (Raw) (+20 credits)',
    timestamp: '2026-09-24 10:40:00',
  },
  // Day -10 (2026-09-26)
  {
    id: 'tx_d09',
    userId: 'demo-user',
    type: 'UPLOAD_REWARD',
    amount: 90,
    description: 'Dataset Ingestion Reward for Student Performance (Raw) (+90 credits)',
    timestamp: '2026-09-26 15:30:00',
  },
  // Day -7 (2026-09-29)
  {
    id: 'tx_d10',
    userId: 'demo-user',
    type: 'QUERY_CHARGE',
    amount: -20,
    description: 'Query Execution Fee on Retail Benchmark Shard (-20 credits)',
    timestamp: '2026-09-29 11:15:00',
  },
  // Day -4 (2026-10-02)
  {
    id: 'tx_d11',
    userId: 'demo-user',
    type: 'CONTRIBUTOR_ROYALTY',
    amount: 25,
    description: 'Quality Bounty Bonus on Curated Student Cohort (+25 credits)',
    timestamp: '2026-10-02 14:00:00',
  },
  // Day -1 (2026-10-05)
  {
    id: 'tx_d12',
    userId: 'demo-user',
    type: 'CONTRIBUTOR_ROYALTY',
    amount: 20,
    description: 'Unlock Royalty from Bob Miller on Student Performance (Raw) (+20 credits)',
    timestamp: '2026-10-05 16:50:00',
  },

  // Transactions for Alice (Total = 240)
  {
    id: 'tx_a01',
    userId: 'alice',
    type: 'SIGNUP_BONUS',
    amount: 100,
    description: 'Welcome Sign-up Credit Allocation (+100 credits)',
    timestamp: '2026-08-01 09:00:00',
  },
  {
    id: 'tx_a02',
    userId: 'alice',
    type: 'UPLOAD_REWARD',
    amount: 120,
    description: 'Dataset Ingestion Reward for Heart Disease Dataset (+120 credits)',
    timestamp: '2026-08-15 14:22:00',
  },
  {
    id: 'tx_a03',
    userId: 'alice',
    type: 'CONTRIBUTOR_ROYALTY',
    amount: 20,
    description: 'Unlock Royalty on Heart Disease Dataset (+20 credits)',
    timestamp: '2026-09-19 16:20:00',
  },

  // Transactions for Bob (Total = 100)
  {
    id: 'tx_b01',
    userId: 'bob',
    type: 'SIGNUP_BONUS',
    amount: 100,
    description: 'Welcome Sign-up Credit Allocation (+100 credits)',
    timestamp: '2026-09-28 11:30:00',
  },
];

// Initial Query History
export const INITIAL_QUERY_HISTORY: QueryHistoryItem[] = [
  {
    id: 'qh_d01',
    userId: 'demo-user',
    datasetId: 'ds-telecom-churn',
    datasetName: 'telecom_customer_churn_q3.csv',
    naturalPrompt: 'Show high churn customers with monthly spend over 60',
    generatedSql: 'SELECT customer_id, tenure_months, monthly_charges, churn_status \nFROM telecom_customer_churn \nWHERE monthly_charges > 60 AND churn_status = \'Yes\' \nLIMIT 5;',
    rowsReturned: 5,
    status: 'SUCCESS',
    creditsCharged: 20,
    timestamp: '2026-09-14 11:30:00',
    executionTimeMs: 14.8,
  },
  {
    id: 'qh_d02',
    userId: 'demo-user',
    datasetId: 'ds-heart',
    datasetName: 'heart_disease_clinical_records.csv',
    naturalPrompt: 'Show top 10 patients by cholesterol',
    generatedSql: 'SELECT patient_id, age, cholesterol, heart_disease_risk \nFROM heart_disease_clinical_records \nORDER BY cholesterol DESC \nLIMIT 5;',
    rowsReturned: 5,
    status: 'SUCCESS',
    creditsCharged: 20,
    timestamp: '2026-09-19 16:20:00',
    executionTimeMs: 12.3,
  },
];
