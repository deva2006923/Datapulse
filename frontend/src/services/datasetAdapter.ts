import {
  AppDataset,
  BackendDatasetDetail,
  BackendEvaluationResponse,
  ColumnDefinition,
  SearchItem,
  TransactionItem,
  WalletTransaction,
  QueryHistoryItem,
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
  const isCurated = Boolean(backend.is_curated || backend.dataset_type === 'curated');
  const datasetType: 'curated' | 'community' = isCurated ? 'curated' : 'community';
  const visibility: 'public' | 'private' =
    !isCurated && String(backend.visibility || 'public').toLowerCase() === 'private'
      ? 'private'
      : 'public';
  const formattedDomain = backend.domain
    ? backend.domain.charAt(0).toUpperCase() + backend.domain.slice(1)
    : 'General';

  const unlockPrice = isCurated ? 0 : (backend.unlock_price ?? 10);
  const unlockedList = Array.from(
    new Set([
      ...(backend.unlocked_by || []),
      ...(isOwner ? [backend.user_id] : []),
      ...(isCurated && currentUserId ? [currentUserId] : []),
    ])
  );
  const storageAvailable = backend.storage_available ?? true;
  const availability = backend.availability || (storageAvailable ? 'Available' : 'Unavailable');

  const displayTitle = backend.name || backend.filename || 'Structured Dataset';
  const numericCol = columns.find((c) =>
    ['integer', 'int', 'float', 'double', 'decimal', 'numeric', 'bigint'].some((t) =>
      c.type.toLowerCase().includes(t)
    )
  );
  const dynamicSampleQueries = [
    `How many rows are in ${displayTitle}?`,
    `Show the first 10 rows of ${displayTitle}`,
    ...(numericCol ? [`What is the average ${numericCol.name} in ${displayTitle}?`] : []),
  ];

  return {
    id: backend.id,
    name: backend.filename || `${backend.id}.csv`,
    title: displayTitle,
    description:
      backend.content_summary ||
      `Dataset in the ${backend.domain || 'general'} domain with ${backend.rows_count} rows across ${backend.columns_count} columns.`,
    domain: formattedDomain,
    format: 'csv',
    authorId: backend.user_id,
    authorName: isCurated ? 'DataPulse Curated Library' : isOwner ? 'You' : 'Dataset Contributor',
    cost: isCurated || isOwner ? 0 : unlockPrice,
    unlockPrice,
    qualityScore,
    relevanceScore,
    overallScore,
    status: 'APPROVED',
    tags: [
      ...(isCurated ? ['curated'] : ['community']),
      backend.domain ? backend.domain.toLowerCase() : 'data',
      'csv',
    ],
    license: backend.license || 'MIT',
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
    currentVersion: backend.source_version || 'v1.0',
    versionHistory: [
      {
        version: backend.source_version || 'v1.0',
        date: backend.created_at?.split('T')[0] || new Date().toISOString().split('T')[0],
        author: isCurated ? 'DataPulse Curated Library' : isOwner ? 'You' : 'Contributor',
        quality: qualityScore,
        relevance: relevanceScore,
        changesSummary: backend.content_summary || 'Initial dataset ingestion and automated evaluation.',
      },
    ],
    unlockedBy: unlockedList,
    storageAvailable,
    availability,
    sampleQueries: dynamicSampleQueries,
    isCurated,
    datasetType,
    visibility,
    sourceName: backend.source_name ?? undefined,
    sourceUrl: backend.source_url ?? undefined,
    licenseUrl: backend.license_url ?? undefined,
    retrievedAt: backend.retrieved_at ?? undefined,
    ingestionStatus: backend.ingestion_status ?? undefined,
    sha256Checksum: backend.sha256_checksum ?? undefined,
    sourceVersion: backend.source_version ?? undefined,
  };
}

/**
 * Transforms a backend SearchItem (from POST /datasets/search) into AppDataset.
 * Preserves authoritative backend evaluation scores, unlock price, domain, ownership,
 * and visibility — never overwriting dataset quality/overall scores with search matchScore.
 */
export function searchItemToAppDataset(
  item: SearchItem,
  currentUserId?: string,
  existing?: AppDataset
): AppDataset {
  const matchPct = Math.round(item.score * 100);
  const formattedDomain = item.domain
    ? item.domain.charAt(0).toUpperCase() + item.domain.slice(1)
    : existing?.domain || 'General';
  const isCurated = Boolean(
    item.is_curated ??
      (item.dataset_type !== undefined
        ? item.dataset_type === 'curated'
        : existing?.isCurated) ??
      false
  );
  const datasetType: 'curated' | 'community' = isCurated ? 'curated' : 'community';
  const authorId = item.user_id ?? existing?.authorId ?? '';
  const isOwner = Boolean(currentUserId && authorId && authorId === currentUserId);
  const unlockPrice = isCurated
    ? 0
    : (item.unlock_price ?? existing?.unlockPrice ?? 10);
  const visibility: 'public' | 'private' =
    !isCurated && String(item.visibility ?? existing?.visibility ?? 'public').toLowerCase() === 'private'
      ? 'private'
      : 'public';

  const qualityScore = item.quality_score ?? existing?.qualityScore ?? 0;
  const relevanceScore = item.domain_relevance_score ?? existing?.relevanceScore ?? 0;
  const overallScore =
    item.overall_score ??
    existing?.overallScore ??
    (qualityScore > 0 && relevanceScore > 0
      ? Math.round(((qualityScore + relevanceScore) / 2) * 100) / 100
      : qualityScore || relevanceScore || 0);

  const unlockedList = Array.from(
    new Set([
      ...(existing?.unlockedBy || []),
      ...(item.unlocked_by || []),
      ...(isOwner && authorId ? [authorId] : []),
      ...(isCurated && currentUserId ? [currentUserId] : []),
    ])
  );

  const storageAvailable =
    item.storage_available ?? existing?.storageAvailable ?? true;
  const availability =
    item.availability ?? existing?.availability ?? (storageAvailable ? 'Available' : 'Unavailable');

  return {
    id: item.dataset_id,
    name: item.filename || existing?.name || `${item.dataset_id}.csv`,
    title: item.name,
    description: item.summary,
    domain: formattedDomain,
    format: existing?.format || 'csv',
    authorId,
    authorName: isCurated
      ? 'DataPulse Curated Library'
      : isOwner
      ? 'You'
      : existing?.authorName || 'Dataset Contributor',
    cost: isCurated || isOwner ? 0 : unlockPrice,
    unlockPrice,
    qualityScore,
    relevanceScore,
    overallScore,
    status: existing?.status || 'APPROVED',
    tags: existing?.tags?.length
      ? existing.tags
      : [
          ...(isCurated ? ['curated'] : ['community']),
          item.domain ? item.domain.toLowerCase() : 'data',
          'csv',
        ],
    license: item.license || existing?.license || 'MIT',
    usageCount: existing?.usageCount ?? 0,
    qualityBreakdown: existing?.qualityBreakdown || {
      completeness: qualityScore,
      validity: qualityScore,
      uniqueness: qualityScore,
      consistency: qualityScore,
    },
    rowCount: item.rows_count,
    columnCount: item.columns_count ?? existing?.columnCount ?? 0,
    columns: existing?.columns || [],
    previewRows: existing?.previewRows || [],
    createdAt: item.created_at
      ? item.created_at.split('T')[0]
      : existing?.createdAt || new Date().toISOString().split('T')[0],
    currentVersion: existing?.currentVersion || 'v1.0',
    versionHistory: existing?.versionHistory || [],
    unlockedBy: unlockedList,
    storageAvailable,
    availability,
    sampleQueries: existing?.sampleQueries || [`How many records are in ${item.name}?`],
    matchScore: matchPct,
    isCurated,
    datasetType,
    visibility,
    sourceName: item.source_name ?? existing?.sourceName,
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
    case 'upload_reward':
    case 'quality_reward':
      mappedType = 'UPLOAD_REWARD';
      break;
    case 'query_fee':
    case 'dataset_unlock':
      mappedType = 'QUERY_CHARGE';
      break;
    case 'query_reward':
    case 'unlock_royalty':
      mappedType = 'CONTRIBUTOR_ROYALTY';
      break;
    case 'improvement_reward':
      mappedType = 'IMPROVEMENT_REWARD';
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

/**
 * Transforms a backend query history record into the frontend QueryHistoryItem model.
 */
export function backendQueryHistoryItemToQueryHistoryItem(item: any): QueryHistoryItem {
  return {
    id: item.id,
    userId: item.user_id || item.userId || '',
    datasetId: item.dataset_id || item.datasetId || '',
    datasetName: item.dataset_name || item.datasetName || 'Cross-Catalog',
    naturalPrompt: item.natural_prompt || item.naturalPrompt || item.query_text || '',
    generatedSql: item.generated_sql || item.generatedSql || '-- No SQL generated',
    rowsReturned: item.rows_returned ?? item.rowsReturned ?? item.result_count ?? 0,
    status: (item.status as any) || 'SUCCESS',
    creditsCharged: item.credits_charged ?? item.creditsCharged ?? 0,
    timestamp: item.timestamp
      ? item.timestamp.replace('T', ' ').substring(0, 19)
      : item.created_at
      ? item.created_at.replace('T', ' ').substring(0, 19)
      : new Date().toISOString().replace('T', ' ').substring(0, 19),
    executionTimeMs: item.execution_time_ms ?? item.executionTimeMs ?? 0,
  };
}
