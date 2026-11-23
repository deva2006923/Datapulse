import { describe, it, expect } from 'bun:test';
import { backendDatasetToAppDataset, searchItemToAppDataset } from './datasetAdapter';
import type { BackendDatasetDetail, SearchItem } from '../types';

describe('Curated Public Library Adapter & Marketplace Mapping', () => {
  it('maps curated public datasets with free access, provenance, and license', () => {
    const curatedBackend: BackendDatasetDetail = {
      id: 'ds_cur_env_owid_co2',
      user_id: 'usr_system_curated_library',
      name: 'OWID Global CO2 & Greenhouse Gas Emissions',
      filename: 'owid-co2-data.csv',
      domain: 'Environment & Climate',
      rows_count: 48000,
      columns_count: 15,
      schema_metadata: { country: 'string', year: 'integer', co2: 'float' },
      content_summary: 'Global CO2 emissions curated by OWID.',
      unlock_price: 0,
      unlocked_by: ['usr_system_curated_library'],
      storage_available: true,
      availability: 'On-Demand Ready',
      created_at: '2026-11-22T10:00:00',
      quality_score: 96,
      domain_relevance_score: 90,
      overall_score: 95,
      credits_awarded: 0,
      is_curated: true,
      dataset_type: 'curated',
      source_name: 'Our World in Data (OWID)',
      source_url: 'https://github.com/owid/co2-data',
      license: 'CC-BY 4.0',
      license_url: 'https://creativecommons.org/licenses/by/4.0/',
      ingestion_status: 'ingested',
      sha256_checksum: 'a'.repeat(64),
      source_version: 'v1',
    };

    const appDs = backendDatasetToAppDataset(curatedBackend, 'usr_regular_123');
    expect(appDs.isCurated).toBe(true);
    expect(appDs.datasetType).toBe('curated');
    expect(appDs.cost).toBe(0);
    expect(appDs.unlockPrice).toBe(0);
    expect(appDs.license).toBe('CC-BY 4.0');
    expect(appDs.sourceName).toBe('Our World in Data (OWID)');
    expect(appDs.authorName).toBe('DataPulse Curated Library');
    expect(appDs.unlockedBy).toContain('usr_regular_123');
    expect(appDs.availability).toBe('On-Demand Ready');
  });

  it('preserves community dataset pricing, ownership, and separation', () => {
    const communityBackend: BackendDatasetDetail = {
      id: 'ds_90ec661cdf80',
      user_id: 'usr_owner_1',
      name: 'IBM HR Analytics Employee Attrition & Performance',
      filename: 'WA_Fn-UseC_-HR-Employee-Attrition.csv',
      domain: 'education',
      rows_count: 1470,
      columns_count: 35,
      schema_metadata: { Age: 'integer', Department: 'string' },
      content_summary: 'Community uploaded HR dataset.',
      unlock_price: 49,
      unlocked_by: ['usr_owner_1'],
      storage_available: true,
      availability: 'Available',
      created_at: '2026-10-21T06:21:05',
      quality_score: 96.25,
      domain_relevance_score: 85,
      overall_score: 96.25,
      is_curated: false,
      dataset_type: 'community',
    };

    const forBuyer = backendDatasetToAppDataset(communityBackend, 'usr_buyer_2');
    expect(forBuyer.isCurated).toBe(false);
    expect(forBuyer.datasetType).toBe('community');
    expect(forBuyer.cost).toBe(49);
    expect(forBuyer.unlockPrice).toBe(49);
    expect(forBuyer.unlockedBy).not.toContain('usr_buyer_2');

    const forOwner = backendDatasetToAppDataset(communityBackend, 'usr_owner_1');
    expect(forOwner.cost).toBe(0);
    expect(forOwner.unlockedBy).toContain('usr_owner_1');
    expect(forOwner.visibility).toBe('public');
  });

  it('maps private visibility for community datasets and keeps curated datasets public', () => {
    const privateCommunity: BackendDatasetDetail = {
      id: 'ds_private_1',
      user_id: 'usr_owner_1',
      name: 'Private Financial Ledger',
      filename: 'private_ledger.csv',
      domain: 'finance',
      rows_count: 120,
      columns_count: 4,
      schema_metadata: { id: 'integer', amount: 'float' },
      content_summary: 'Internal finance table.',
      unlock_price: 20,
      unlocked_by: ['usr_owner_1'],
      storage_available: true,
      availability: 'Available',
      created_at: '2026-11-22T12:00:00',
      is_curated: false,
      dataset_type: 'community',
      visibility: 'private',
    };

    const mappedPrivate = backendDatasetToAppDataset(privateCommunity, 'usr_owner_1');
    expect(mappedPrivate.visibility).toBe('private');
    expect(mappedPrivate.isCurated).toBe(false);

    const curatedAlwaysPublic = backendDatasetToAppDataset(
      { ...privateCommunity, id: 'ds_cur_1', is_curated: true, dataset_type: 'curated', visibility: 'private' },
      'usr_owner_1'
    );
    expect(curatedAlwaysPublic.isCurated).toBe(true);
    expect(curatedAlwaysPublic.visibility).toBe('public');
    expect(curatedAlwaysPublic.cost).toBe(0);
  });

  it('keeps My Datasets (list) and Marketplace search metadata 100% consistent without overwriting overallScore with matchScore', () => {
    const ownerId = 'usr_admin_d1ad20dc';
    const backendDetail: BackendDatasetDetail = {
      id: 'ds_06d7602e30ec',
      user_id: ownerId,
      name: 'Customer Churn Analysis Q4',
      filename: 'Zomato Restaurant Dataset.csv',
      domain: 'telecom',
      rows_count: 9551,
      columns_count: 21,
      schema_metadata: { Restaurant_ID: 'integer', Rating: 'float' },
      content_summary: 'Structured dataset containing 9551 rows across 21 columns.',
      unlock_price: 48,
      unlocked_by: [ownerId],
      storage_available: true,
      availability: 'Available',
      created_at: '2026-11-22T16:33:16.271761',
      quality_score: 92.92,
      domain_relevance_score: 85,
      overall_score: 92.92,
      is_curated: false,
      dataset_type: 'community',
      visibility: 'public',
    };

    const searchItem: SearchItem = {
      dataset_id: 'ds_06d7602e30ec',
      user_id: ownerId,
      name: 'Customer Churn Analysis Q4',
      filename: 'Zomato Restaurant Dataset.csv',
      domain: 'telecom',
      score: 0.48, // 48% search similarity — MUST NOT overwrite overallScore (92.92)
      summary: 'Structured dataset containing 9551 rows across 21 columns.',
      rows_count: 9551,
      columns_count: 21,
      unlock_price: 48,
      unlocked_by: [ownerId],
      quality_score: 92.92,
      domain_relevance_score: 85,
      overall_score: 92.92,
      storage_available: true,
      availability: 'Available',
      is_curated: false,
      dataset_type: 'community',
      visibility: 'public',
      created_at: '2026-11-22T16:33:16.271761',
    };

    const fromMyDatasets = backendDatasetToAppDataset(backendDetail, ownerId);
    const fromMarketplaceSearch = searchItemToAppDataset(searchItem, ownerId, fromMyDatasets);

    expect(fromMarketplaceSearch.id).toBe(fromMyDatasets.id);
    expect(fromMarketplaceSearch.title).toBe(fromMyDatasets.title);
    expect(fromMarketplaceSearch.name).toBe('Zomato Restaurant Dataset.csv');
    expect(fromMarketplaceSearch.domain).toBe('Telecom');
    expect(fromMarketplaceSearch.unlockPrice).toBe(48);
    expect(fromMarketplaceSearch.qualityScore).toBe(92.92);
    expect(fromMarketplaceSearch.relevanceScore).toBe(85);
    expect(fromMarketplaceSearch.overallScore).toBe(92.92);
    expect(fromMarketplaceSearch.matchScore).toBe(48);
    expect(fromMarketplaceSearch.authorId).toBe(ownerId);
    expect(fromMarketplaceSearch.authorName).toBe('You');
    expect(fromMarketplaceSearch.unlockedBy).toContain(ownerId);
    expect(fromMarketplaceSearch.storageAvailable).toBe(true);
    expect(fromMarketplaceSearch.availability).toBe('Available');
  });
});

