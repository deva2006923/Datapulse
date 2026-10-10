import React, { useState, useEffect } from 'react';
import {
  ArrowLeft,
  Search,
  Lock,
  Unlock,
  ShieldCheck,
  Loader2,
  AlertCircle,
  RefreshCw,
} from 'lucide-react';
import { AppDataset, UserAccount, PageRoute } from '../types';
import { api, ApiError } from '../services/api';
import { backendDatasetToAppDataset } from '../services/datasetAdapter';

interface DatasetDetailViewProps {
  dataset: AppDataset;
  currentUser: UserAccount;
  onNavigate: (route: PageRoute) => void;
  onOpenQueryWithPrompt?: (datasetId: string, prompt?: string) => void;
  onImproveDataset: (datasetId: string) => void;
}

export const DatasetDetailView: React.FC<DatasetDetailViewProps> = ({
  dataset: initialDataset,
  currentUser,
  onNavigate,
  onOpenQueryWithPrompt,
  onImproveDataset,
}) => {
  const [dataset, setDataset] = useState<AppDataset>(initialDataset);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  const fetchDatasetDetails = async (datasetId: string) => {
    setIsLoading(true);
    setLoadError(null);

    try {
      // 1. Fetch dataset details from GET /datasets/{id}
      const backendDetail = await api.datasets.getDataset(datasetId);

      // 2. Attempt to fetch evaluation metrics from GET /datasets/{id}/evaluation
      let evalData = null;
      try {
        evalData = await api.datasets.getEvaluation(datasetId);
      } catch {
        // Evaluation may not exist or not ready yet; fallback gracefully
      }

      const mergedAppDataset = backendDatasetToAppDataset(
        backendDetail,
        currentUser.id,
        evalData
      );

      // Preserve any client-side unlocked state or versions
      mergedAppDataset.unlockedBy = Array.from(
        new Set([
          ...(initialDataset.unlockedBy || []),
          ...(mergedAppDataset.unlockedBy || []),
        ])
      );

      setDataset(mergedAppDataset);
    } catch (err: any) {
      const message =
        err instanceof ApiError
          ? err.message
          : 'Unable to load dataset details from backend server.';
      setLoadError(message);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    if (initialDataset?.id) {
      fetchDatasetDetails(initialDataset.id);
    }
  }, [initialDataset?.id]);

  const isOwner = dataset.authorId === currentUser.id;
  const isUnlocked = isOwner || dataset.unlockedBy.includes(currentUser.id);

  return (
    <div className="space-y-6">
      {/* Navigation Breadcrumb */}
      <div className="flex items-center justify-between">
        <button
          onClick={() => onNavigate('marketplace')}
          className="inline-flex items-center gap-2 text-xs font-medium text-slate-600 hover:text-indigo-600 transition-colors cursor-pointer"
        >
          <ArrowLeft className="w-4 h-4" />
          <span>Back to Marketplace</span>
        </button>

        <div className="flex items-center gap-2">
          <button
            onClick={() => onImproveDataset(dataset.id)}
            className="px-3 py-1.5 rounded-lg bg-white border border-slate-300 hover:bg-slate-50 text-slate-700 text-xs font-medium transition-colors cursor-pointer"
          >
            Improve Version
          </button>
          <button
            onClick={() => onOpenQueryWithPrompt?.(dataset.id)}
            className="px-3.5 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-medium transition-colors shadow-xs cursor-pointer flex items-center gap-1.5"
          >
            <Search className="w-3.5 h-3.5" />
            <span>Open in Query Workspace</span>
          </button>
        </div>
      </div>

      {/* Error state banner */}
      {loadError && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-4 flex items-center justify-between gap-3 text-xs text-red-800">
          <div className="flex items-center gap-2">
            <AlertCircle className="w-4 h-4 text-red-600 shrink-0" />
            <span>{loadError}</span>
          </div>
          <button
            onClick={() => fetchDatasetDetails(dataset.id)}
            className="px-3 py-1 bg-white border border-red-300 rounded-lg text-red-700 font-semibold hover:bg-red-50 cursor-pointer flex items-center gap-1.5 shrink-0"
          >
            <RefreshCw className="w-3 h-3" />
            <span>Retry</span>
          </button>
        </div>
      )}

      {/* Main Header Card */}
      <div className="bg-white border border-slate-200 rounded-xl p-6 shadow-sm space-y-4 relative">
        {isLoading && (
          <div className="absolute top-4 right-4 flex items-center gap-1.5 text-xs text-indigo-600 font-medium">
            <Loader2 className="w-3.5 h-3.5 animate-spin" />
            <span>Syncing backend metadata...</span>
          </div>
        )}

        <div className="flex flex-col md:flex-row md:items-start justify-between gap-4">
          <div className="space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              <span className="px-2.5 py-0.5 rounded text-xs font-semibold bg-slate-100 text-slate-700 border border-slate-200">
                {dataset.domain}
              </span>
              <span className="px-2.5 py-0.5 rounded text-xs font-mono uppercase bg-slate-100 text-slate-700 border border-slate-200">
                {dataset.format}
              </span>
              <span className="px-2.5 py-0.5 rounded text-xs font-mono text-slate-500 bg-slate-50 border border-slate-200">
                {dataset.currentVersion}
              </span>
              {dataset.status === 'REJECTED' ? (
                <span className="px-2.5 py-0.5 rounded text-xs font-semibold bg-red-50 text-red-700 border border-red-200">
                  REJECTED
                </span>
              ) : isOwner ? (
                <span className="px-2.5 py-0.5 rounded text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
                  You are Author
                </span>
              ) : isUnlocked ? (
                <span className="px-2.5 py-0.5 rounded text-xs font-semibold bg-indigo-50 text-indigo-700 border border-indigo-200 flex items-center gap-1">
                  <Unlock className="w-3 h-3" /> Unlocked
                </span>
              ) : (
                <span className="px-2.5 py-0.5 rounded text-xs font-semibold bg-slate-100 text-slate-600 border border-slate-200 flex items-center gap-1">
                  <Lock className="w-3 h-3" /> Locked ({dataset.cost || 1} cr)
                </span>
              )}
            </div>

            <h1 className="text-2xl sm:text-3xl font-extrabold text-slate-900 tracking-tight">
              {dataset.title}
            </h1>
            <p className="text-xs font-mono text-slate-400">{dataset.name} (ID: {dataset.id})</p>
            <p className="text-sm text-slate-600 max-w-3xl leading-relaxed">
              {dataset.description}
            </p>

            {dataset.status === 'REJECTED' && dataset.rejectionReasons && (
              <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-xs text-red-800 space-y-1">
                <span className="font-bold block">Submission Rejection Reason:</span>
                <p>{dataset.rejectionReasons}</p>
              </div>
            )}
          </div>

          {/* Quick Stats Pill */}
          <div className="flex md:flex-col items-end gap-2 text-right shrink-0">
            <div className="text-xs text-slate-500">
              Contributed by <span className="font-semibold text-slate-700">{dataset.authorName}</span>
            </div>
            <div className="text-xs text-slate-400">
              Published on {dataset.createdAt}
            </div>
            <div className="text-xs font-mono text-slate-500">
              {dataset.rowCount.toLocaleString()} rows • {dataset.columnCount} columns
            </div>
          </div>
        </div>
      </div>

      {/* Score Gauges & Quality Breakdown */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Score Gauges */}
        <div className="lg:col-span-5 bg-white border border-slate-200 rounded-xl p-6 shadow-sm space-y-4">
          <h2 className="text-sm font-semibold text-slate-900 uppercase tracking-wide">
            Automated Evaluation Scores
          </h2>

          <div className="grid grid-cols-3 gap-3 text-center">
            {/* Overall Score */}
            <div className="p-4 rounded-xl bg-indigo-50/50 border border-indigo-100">
              <span className="text-[11px] font-semibold text-indigo-700 uppercase tracking-wider block mb-1">
                Overall Score
              </span>
              <div className="text-2xl font-black font-mono text-indigo-700">
                {dataset.overallScore}
              </div>
              <span className="text-[10px] text-slate-500 block mt-1">(Qual + Rel) / 2</span>
            </div>

            {/* Quality Score */}
            <div className="p-4 rounded-xl bg-slate-50 border border-slate-200">
              <span className="text-[11px] font-semibold text-slate-600 uppercase tracking-wider block mb-1">
                Quality
              </span>
              <div className="text-2xl font-black font-mono text-slate-900">
                {dataset.qualityScore}
              </div>
              <span className="text-[10px] text-slate-500 block mt-1">out of 100</span>
            </div>

            {/* Relevance Score */}
            <div className="p-4 rounded-xl bg-slate-50 border border-slate-200">
              <span className="text-[11px] font-semibold text-slate-600 uppercase tracking-wider block mb-1">
                Relevance
              </span>
              <div className="text-2xl font-black font-mono text-slate-900">
                {dataset.relevanceScore}
              </div>
              <span className="text-[10px] text-slate-500 block mt-1">out of 100</span>
            </div>
          </div>

          <div className="pt-2 text-xs text-slate-500 border-t border-slate-100 leading-relaxed">
            Formula: Overall Score is computed as the composite of Schema Quality and Semantic Domain Relevance.
          </div>
        </div>

        {/* Quality Breakdown Chart */}
        <div className="lg:col-span-7 bg-white border border-slate-200 rounded-xl p-6 shadow-sm space-y-4">
          <h2 className="text-sm font-semibold text-slate-900 uppercase tracking-wide">
            Quality Breakdown Dimension Bars
          </h2>

          <div className="space-y-3.5">
            <div>
              <div className="flex justify-between text-xs mb-1">
                <span className="font-medium text-slate-700">Completeness (Non-null field ratio)</span>
                <span className="font-mono font-semibold text-slate-900">{dataset.qualityBreakdown.completeness}%</span>
              </div>
              <div className="w-full bg-slate-100 rounded-full h-2">
                <div
                  className="bg-indigo-600 h-2 rounded-full"
                  style={{ width: `${dataset.qualityBreakdown.completeness}%` }}
                />
              </div>
            </div>

            <div>
              <div className="flex justify-between text-xs mb-1">
                <span className="font-medium text-slate-700">Validity (Type conformance & constraints)</span>
                <span className="font-mono font-semibold text-slate-900">{dataset.qualityBreakdown.validity}%</span>
              </div>
              <div className="w-full bg-slate-100 rounded-full h-2">
                <div
                  className="bg-emerald-600 h-2 rounded-full"
                  style={{ width: `${dataset.qualityBreakdown.validity}%` }}
                />
              </div>
            </div>

            <div>
              <div className="flex justify-between text-xs mb-1">
                <span className="font-medium text-slate-700">Uniqueness (Primary key & duplicate prevention)</span>
                <span className="font-mono font-semibold text-slate-900">{dataset.qualityBreakdown.uniqueness}%</span>
              </div>
              <div className="w-full bg-slate-100 rounded-full h-2">
                <div
                  className="bg-blue-600 h-2 rounded-full"
                  style={{ width: `${dataset.qualityBreakdown.uniqueness}%` }}
                />
              </div>
            </div>

            <div>
              <div className="flex justify-between text-xs mb-1">
                <span className="font-medium text-slate-700">Consistency (Cross-column integrity)</span>
                <span className="font-mono font-semibold text-slate-900">{dataset.qualityBreakdown.consistency}%</span>
              </div>
              <div className="w-full bg-slate-100 rounded-full h-2">
                <div
                  className="bg-amber-500 h-2 rounded-full"
                  style={{ width: `${dataset.qualityBreakdown.consistency}%` }}
                />
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Unlock Panel Banner */}
      <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div className="flex items-start sm:items-center gap-3">
          <div className={`w-10 h-10 rounded-xl flex items-center justify-center shrink-0 ${
            isOwner ? 'bg-emerald-50 text-emerald-600 border border-emerald-200' :
            isUnlocked ? 'bg-indigo-50 text-indigo-600 border border-indigo-200' :
            'bg-slate-100 text-slate-600 border border-slate-200'
          }`}>
            {isOwner ? <ShieldCheck className="w-5 h-5" /> : isUnlocked ? <Unlock className="w-5 h-5" /> : <Lock className="w-5 h-5" />}
          </div>
          <div>
            <h3 className="text-sm font-bold text-slate-900">
              {isOwner ? 'Dataset Contributor Access' : isUnlocked ? 'Dataset Access Unlocked' : 'Unlock Policy: 1 Compute Credit'}
            </h3>
            <p className="text-xs text-slate-500 mt-0.5">
              {isOwner
                ? 'As the author, you have permanent unrestricted query access at 0 credits.'
                : isUnlocked
                ? 'You have access to this dataset. Standard queries charged per backend policy.'
                : 'Query fee is 1 credit per paid query. The original contributor receives 1 credit royalty reward.'}
            </p>
          </div>
        </div>

        <button
          onClick={() => onOpenQueryWithPrompt?.(dataset.id)}
          className="px-4 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold shadow-xs cursor-pointer transition-colors whitespace-nowrap self-start sm:self-auto flex items-center gap-1.5"
        >
          <Search className="w-3.5 h-3.5" />
          <span>Launch Query Workspace</span>
        </button>
      </div>

      {/* Sample Queries */}
      <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-xs font-semibold text-slate-900 uppercase tracking-wide">
            Sample Natural Language Queries
          </h3>
          <span className="text-[11px] text-slate-400">Click to pre-fill in workspace</span>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
          {dataset.sampleQueries.map((q, idx) => (
            <button
              key={idx}
              onClick={() => onOpenQueryWithPrompt?.(dataset.id, q)}
              className="p-3 rounded-lg bg-slate-50 hover:bg-indigo-50 hover:border-indigo-200 border border-slate-200 text-left transition-colors cursor-pointer group flex items-start justify-between gap-2"
            >
              <div className="flex items-center gap-2 text-xs font-medium text-slate-700 group-hover:text-indigo-700">
                <Search className="w-3.5 h-3.5 text-indigo-600 shrink-0" />
                <span>"{q}"</span>
              </div>
              <ArrowLeft className="w-3.5 h-3.5 text-slate-400 rotate-180 shrink-0 group-hover:text-indigo-600" />
            </button>
          ))}
        </div>
      </div>

      {/* Columns Table */}
      <div className="bg-white border border-slate-200 rounded-xl overflow-hidden shadow-sm">
        <div className="p-5 border-b border-slate-200 flex items-center justify-between">
          <div>
            <h3 className="text-sm font-bold text-slate-900">
              Columns & Schema Metadata ({dataset.columns.length})
            </h3>
            <p className="text-xs text-slate-500 mt-0.5">
              Verified columns and data types from analytical table storage.
            </p>
          </div>
          <span className="text-xs font-mono text-slate-500 bg-slate-100 px-2.5 py-1 rounded">
            {dataset.rowCount.toLocaleString()} total rows
          </span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-50 text-slate-500 border-b border-slate-200 text-[11px]">
              <tr>
                <th className="py-2.5 px-4 font-semibold">Column Name</th>
                <th className="py-2.5 px-4 font-semibold">Data Type</th>
                <th className="py-2.5 px-4 font-semibold">Null Count</th>
                <th className="py-2.5 px-4 font-semibold">Recognized Synonyms</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-slate-700">
              {dataset.columns.length === 0 ? (
                <tr>
                  <td colSpan={4} className="py-6 text-center text-slate-400">
                    No schema columns registered for this dataset.
                  </td>
                </tr>
              ) : (
                dataset.columns.map((col, idx) => (
                  <tr key={idx} className="hover:bg-slate-50/50">
                    <td className="py-2.5 px-4 font-mono font-semibold text-indigo-700">
                      {col.name}
                    </td>
                    <td className="py-2.5 px-4 font-mono text-slate-600">
                      {col.type}
                    </td>
                    <td className="py-2.5 px-4 font-mono text-slate-600">
                      {col.nullCount} ({col.nullPct}%)
                    </td>
                    <td className="py-2.5 px-4">
                      <div className="flex flex-wrap gap-1">
                        {col.synonyms.map((s, sIdx) => (
                          <span
                            key={sIdx}
                            className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-slate-100 text-slate-600 border border-slate-200"
                          >
                            {s}
                          </span>
                        ))}
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
