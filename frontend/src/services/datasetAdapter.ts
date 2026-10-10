import {
  AppDataset,
  BackendDatasetDetail,
  BackendEvaluationResponse,
  ColumnDefinition,
  SearchItem,
  TransactionItem,
  WalletTransaction,
} from '../types';

/**
 * Parses backend schema dictionary into ColumnDefinition list.
 */
export function parseSchemaMetadata(
  schemaDict?: Record<string, any> | null
): ColumnDefinition[] {
  if (!schemaDict || typeof schemaDict !== 'object') {
    return [];
  }

  return Object.entries(schemaDict).map(([colName, colType]) => ({
    name: colName,
    type: String(colType || 'string'),
    nullCount: 0,
    nullPct: 0,
    distinctCount: 0,
    synonyms: [colName.toLowerCase()],
  }));
}

/**
 * Transforms a backend DatasetDetailResponse into the frontend AppDataset model.
 */
export function backendDatasetToAppDataset(
  backend: BackendDatasetDetail,
  currentUserId?: string,
  evalData?: BackendEvaluationResponse | null
): AppDataset {
  const schema = backend.schema_metadata || backend.schema_json || {};
  const columns = parseSchemaMetadata(schema);

  const qualityScore =
    evalData?.quality_score ?? backend.quality_score ?? 85;
  const relevanceScore =
    evalData?.domain_relevance_score ?? backend.domain_relevance_score ?? 90;
  const overallScore =
    evalData?.overall_score ?? backend.overall_score ?? Math.round((qualityScore + relevanceScore) / 2);

  const isOwner = Boolean(currentUserId && backend.user_id === currentUserId);
  const formattedDomain = backend.domain
    ? backend.domain.charAt(0).toUpperCase() + backend.domain.slice(1)
    : 'General';

  return {
    id: backend.id,
    name: backend.filename || `${backend.id}.csv`,
    title: backend.name || backend.filename || 'Structured Dataset',
    description:
      backend.content_summary ||
      `Dataset in the ${backend.domain || 'general'} domain with ${backend.rows_count} rows across ${backend.columns_count} columns.`,
    domain: formattedDomain,
    format: 'csv',
    authorId: backend.user_id,
    authorName: isOwner ? 'You' : 'Dataset Contributor',
    cost: isOwner ? 0 : 1, // Backend QUERY_COST is 1, and 0 for own dataset
    qualityScore,
    relevanceScore,
    overallScore,
    status: 'APPROVED',
    tags: [backend.domain ? backend.domain.toLowerCase() : 'data', 'csv'],
    license: 'MIT',
    usageCount: 0,
    qualityBreakdown: {
      completeness: evalData?.completeness_score ?? qualityScore,
      validity: evalData?.schema_fidelity_score ?? qualityScore,
      uniqueness: evalData?.quality_score ?? qualityScore,
      consistency: evalData?.quality_score ?? qualityScore,
    },
    rowCount: backend.rows_count,
    columnCount: backend.columns_count,
    columns,
    previewRows: [],
    createdAt: backend.created_at
      ? backend.created_at.split('T')[0]
      : new Date().toISOString().split('T')[0],
    currentVersion: 'v1.0',
    versionHistory: [
      {
        version: 'v1.0',
        date: backend.created_at?.split('T')[0] || new Date().toISOString().split('T')[0],
        author: isOwner ? 'You' : 'Contributor',
        quality: qualityScore,
        relevance: relevanceScore,
        changesSummary: backend.content_summary || 'Initial dataset ingestion and automated evaluation.',
      },
    ],
    unlockedBy: isOwner ? [backend.user_id] : [],
    sampleQueries: [
      `How many rows are in this dataset?`,
      `Show sample records from ${backend.name || 'this dataset'}`,
    ],
  };
}

/**
 * Transforms a backend SearchItem (from POST /datasets/search) into AppDataset.
 */
export function searchItemToAppDataset(
  item: SearchItem,
  currentUserId?: string
): AppDataset {
  const matchPct = Math.round(item.score * 100);
  const formattedDomain = item.domain
    ? item.domain.charAt(0).toUpperCase() + item.domain.slice(1)
    : 'General';

  return {
    id: item.dataset_id,
    name: `${item.dataset_id}.csv`,
    title: item.name,
    description: item.summary,
    domain: formattedDomain,
    format: 'csv',
    authorId: '',
    authorName: 'Dataset Contributor',
    cost: 1,
    qualityScore: Math.min(100, Math.max(0, matchPct)),
    relevanceScore: Math.min(100, Math.max(0, matchPct)),
    overallScore: Math.min(100, Math.max(0, matchPct)),
    status: 'APPROVED',
    tags: [item.domain ? item.domain.toLowerCase() : 'data'],
    license: 'MIT',
    usageCount: 0,
    qualityBreakdown: {
      completeness: matchPct,
      validity: matchPct,
      uniqueness: matchPct,
      consistency: matchPct,
    },
    rowCount: item.rows_count,
    columnCount: 0,
    columns: [],
    previewRows: [],
    createdAt: new Date().toISOString().split('T')[0],
    currentVersion: 'v1.0',
    versionHistory: [],
    unlockedBy: [],
    sampleQueries: [`How many records are in ${item.name}?`],
    matchScore: matchPct,
  };
}

/**
 * Maps backend transaction type to frontend transaction model.
 */
export function transactionItemToWalletTransaction(
  item: TransactionItem
): WalletTransaction {
  let mappedType: WalletTransaction['type'] = 'MANUAL_RELOAD';

  switch (item.transaction_type) {
    case 'bonus':
      mappedType = 'SIGNUP_BONUS';
      break;
    case 'reward':
      mappedType = 'UPLOAD_REWARD';
      break;
    case 'query_fee':
      mappedType = 'QUERY_CHARGE';
      break;
    case 'query_reward':
      mappedType = 'CONTRIBUTOR_ROYALTY';
      break;
    case 'redeem':
      mappedType = 'REDEMPTION';
      break;
    default:
      mappedType = item.amount >= 0 ? 'UPLOAD_REWARD' : 'QUERY_CHARGE';
  }

  const timestamp = item.created_at
    ? item.created_at.replace('T', ' ').substring(0, 19)
    : new Date().toISOString().replace('T', ' ').substring(0, 19);

  return {
    id: item.id,
    userId: item.user_id,
    type: mappedType,
    amount: item.amount,
    description: item.description,
    timestamp,
    rupeeValue: Math.abs((item.amount / 100) * 10),
  };
}
