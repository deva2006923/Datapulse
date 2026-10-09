import React from 'react';
import {
  ArrowLeft,
  Database,
  Search,
  Lock,
  Unlock,
  Sparkles,
  TrendingUp,
  Table,
  CheckCircle2,
  FileCode,
  Tag,
  Coins,
  History,
  ShieldCheck,
  ExternalLink,
} from 'lucide-react';
import { AppDataset, UserAccount, PageRoute } from '../types';

interface DatasetDetailViewProps {
  dataset: AppDataset;
  currentUser: UserAccount;
  onNavigate: (route: PageRoute) => void;
  onOpenQueryWithPrompt?: (datasetId: string, prompt?: string) => void;
  onImproveDataset: (datasetId: string) => void;
}

export const DatasetDetailView: React.FC<DatasetDetailViewProps> = ({
  dataset,
  currentUser,
  onNavigate,
  onOpenQueryWithPrompt,
  onImproveDataset,
}) => {
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

      {/* Main Header Card */}
      <div className="bg-white border border-slate-200 rounded-xl p-6 shadow-sm space-y-4">
        <div className="flex flex-col md:flex-row md:items-start justify-between gap-4">
          <div className="space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              <span className="px-2.5 py-0.5 rounded text-xs font-semibold bg-slate-100 text-slate-700 border border-slate-200">
                {dataset.domain}
              </span>
              <span className="px-2.5 py-0.5 rounded text-xs font-mono uppercase bg-slate-100 text-slate-700 border border-slate-200">
                {dataset.format}
              </span>
              <span className="px-2 py-0.5 rounded text-xs font-mono text-slate-500 bg-slate-50 border border-slate-200">
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
                  <Lock className="w-3 h-3" /> Locked ({dataset.cost || 20} cr)
                </span>
              )}
            </div>

            <h1 className="text-2xl sm:text-3xl font-extrabold text-slate-900 tracking-tight">
              {dataset.title}
            </h1>
            <p className="text-xs font-mono text-slate-400">{dataset.name}</p>
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
            Formula: Overall Score is computed as the average of Schema Quality and Semantic Domain Relevance.
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
              {isOwner ? 'Dataset Contributor Access' : isUnlocked ? 'Dataset Already Unlocked' : 'Unlock Policy: 20 Compute Credits'}
            </h3>
            <p className="text-xs text-slate-500 mt-0.5">
              {isOwner
                ? 'As the author, you have permanent unrestricted query access at 0 credits.'
                : isUnlocked
                ? 'You have already unlocked this dataset. Future queries in the workspace cost 0 credits.'
                : 'Unlock fee is 20 credits once, charged ONLY after your first successful query. Contributor receives +20 credits.'}
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

      {/* Sample Queries Carousel */}
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

      {/* Columns Table with Synonym Chips */}
      <div className="bg-white border border-slate-200 rounded-xl overflow-hidden shadow-sm">
        <div className="p-5 border-b border-slate-200 flex items-center justify-between">
          <div>
            <h3 className="text-sm font-bold text-slate-900">
              Columns & Synonym Resolution ({dataset.columns.length})
            </h3>
            <p className="text-xs text-slate-500 mt-0.5">
              Natural language queries resolve these synonym mappings automatically.
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
                <th className="py-2.5 px-4 font-semibold">Distinct</th>
                <th className="py-2.5 px-4 font-semibold">Recognized Synonyms</th>
                <th className="py-2.5 px-4 font-semibold">Description</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-slate-700">
              {dataset.columns.map((col, idx) => (
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
                  <td className="py-2.5 px-4 font-mono text-slate-600">
                    {col.distinctCount.toLocaleString()}
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
                  <td className="py-2.5 px-4 text-slate-500 max-w-xs truncate">
                    {col.description || '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* 5-Row Preview Table */}
      <div className="bg-white border border-slate-200 rounded-xl overflow-hidden shadow-sm">
        <div className="p-5 border-b border-slate-200 flex items-center justify-between">
          <div>
            <h3 className="text-sm font-bold text-slate-900">
              5-Row Data Preview
            </h3>
            <p className="text-xs text-slate-500 mt-0.5">
              Live sample slice extracted from {dataset.name}
            </p>
          </div>
          <span className="text-[11px] font-semibold text-emerald-600 bg-emerald-50 border border-emerald-200 px-2.5 py-1 rounded">
            Verified Clean
          </span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs font-mono">
            <thead className="bg-slate-50 text-slate-500 border-b border-slate-200 text-[11px] font-sans">
              <tr>
                {dataset.columns.map((col, idx) => (
                  <th key={idx} className="py-2.5 px-4 font-semibold">
                    {col.name}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-slate-700">
              {dataset.previewRows.slice(0, 5).map((row, rIdx) => (
                <tr key={rIdx} className="hover:bg-slate-50/50">
                  {dataset.columns.map((col, cIdx) => (
                    <td key={cIdx} className="py-2.5 px-4">
                      {row[col.name] !== undefined ? String(row[col.name]) : '—'}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
