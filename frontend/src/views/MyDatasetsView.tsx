import React, { useState } from 'react';
import {
  Database,
  Upload,
  Search,
  Sparkles,
  Coins,
  Unlock,
  CheckCircle2,
  TrendingUp,
  ArrowRight,
  ShieldCheck,
  FileCode,
} from 'lucide-react';
import { AppDataset, UserAccount, PageRoute } from '../types';

interface MyDatasetsViewProps {
  currentUser: UserAccount;
  datasets: AppDataset[];
  onNavigate: (route: PageRoute) => void;
  onSelectDatasetForDetail: (datasetId: string) => void;
  onOpenQuery: (datasetId: string) => void;
  onImproveDataset: (datasetId: string) => void;
}

export const MyDatasetsView: React.FC<MyDatasetsViewProps> = ({
  currentUser,
  datasets,
  onNavigate,
  onSelectDatasetForDetail,
  onOpenQuery,
  onImproveDataset,
}) => {
  const [activeTab, setActiveTab] = useState<'contributed' | 'accessed'>('contributed');

  const contributed = datasets.filter((d) => d.authorId === currentUser.id);
  const accessed = datasets.filter(
    (d) => d.unlockedBy.includes(currentUser.id) && d.authorId !== currentUser.id
  );

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="bg-white border border-slate-200 rounded-xl p-6 shadow-sm flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <span className="text-xs font-semibold text-indigo-600 uppercase tracking-wide">
            Catalog Management & Portfolios
          </span>
          <h1 className="text-2xl font-extrabold text-slate-900 tracking-tight">
            My Datasets
          </h1>
          <p className="text-xs text-slate-500 mt-0.5">
            Monitor contributed datasets, royalty yields, and catalogs unlocked by your account.
          </p>
        </div>

        <button
          onClick={() => onNavigate('upload')}
          className="px-4 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold cursor-pointer shadow-xs transition-colors self-start sm:self-auto flex items-center gap-2"
        >
          <Upload className="w-3.5 h-3.5" />
          <span>Contribute New Dataset</span>
        </button>
      </div>

      {/* Tabs Switcher */}
      <div className="flex border-b border-slate-200 space-x-6 text-sm font-medium">
        <button
          onClick={() => setActiveTab('contributed')}
          className={`pb-3 font-semibold transition-colors cursor-pointer flex items-center gap-2 border-b-2 ${
            activeTab === 'contributed'
              ? 'border-indigo-600 text-indigo-600'
              : 'border-transparent text-slate-500 hover:text-slate-800'
          }`}
        >
          <span>Contributed by Me</span>
          <span className="px-2 py-0.5 rounded-full text-xs bg-slate-100 text-slate-700">
            {contributed.length}
          </span>
        </button>

        <button
          onClick={() => setActiveTab('accessed')}
          className={`pb-3 font-semibold transition-colors cursor-pointer flex items-center gap-2 border-b-2 ${
            activeTab === 'accessed'
              ? 'border-indigo-600 text-indigo-600'
              : 'border-transparent text-slate-500 hover:text-slate-800'
          }`}
        >
          <span>Accessed & Unlocked</span>
          <span className="px-2 py-0.5 rounded-full text-xs bg-slate-100 text-slate-700">
            {accessed.length}
          </span>
        </button>
      </div>

      {/* Contributed Tab */}
      {activeTab === 'contributed' && (
        <div className="space-y-4">
          {contributed.length === 0 ? (
            <div className="bg-white border border-slate-200 rounded-xl p-12 text-center space-y-3">
              <Database className="w-8 h-8 text-slate-300 mx-auto" />
              <h3 className="text-sm font-bold text-slate-800">
                You haven't contributed any datasets yet
              </h3>
              <p className="text-xs text-slate-500 max-w-sm mx-auto">
                Upload your structured CSV or Parquet files, earn upfront reward credits, and collect +20 credits each time an analyst unlocks your dataset.
              </p>
              <button
                onClick={() => onNavigate('upload')}
                className="mt-2 px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold cursor-pointer shadow-xs"
              >
                Start Upload Wizard
              </button>
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-4">
              {contributed.map((ds) => {
                const totalUnlocks = ds.unlockedBy.filter((uid) => uid !== ds.authorId).length;
                const royaltiesEarned = totalUnlocks * 20;

                return (
                  <div
                    key={ds.id}
                    className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm space-y-4"
                  >
                    <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3">
                      <div>
                        <div className="flex flex-wrap items-center gap-2 mb-1">
                          <span className="px-2 py-0.5 rounded text-[11px] font-semibold bg-slate-100 text-slate-700 border border-slate-200">
                            {ds.domain}
                          </span>
                          <span className="px-2 py-0.5 rounded text-[11px] font-mono uppercase bg-slate-100 text-slate-700 border border-slate-200">
                            {ds.format}
                          </span>
                          <span className="px-2 py-0.5 rounded text-[11px] font-mono text-slate-500 bg-slate-50 border border-slate-200">
                            {ds.currentVersion}
                          </span>
                        </div>
                        <h3 className="text-base font-bold text-slate-900">{ds.title}</h3>
                        <span className="text-xs font-mono text-slate-400 block">{ds.name}</span>
                        <p className="text-xs text-slate-600 mt-1">{ds.description}</p>
                      </div>

                      {/* Royalty Metric Card */}
                      <div className="bg-emerald-50 border border-emerald-200 rounded-xl p-3 text-right shrink-0">
                        <span className="text-[11px] font-semibold text-emerald-800 uppercase tracking-wide block">
                          Earnings from unlocks
                        </span>
                        <div className="text-lg font-mono font-black text-emerald-600">
                          +{royaltiesEarned} cr
                        </div>
                        <span className="text-[10px] text-emerald-700 block">
                          {totalUnlocks} unlocks (+20 cr each)
                        </span>
                      </div>
                    </div>

                    {/* Stats & Actions */}
                    <div className="pt-3 border-t border-slate-100 flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs">
                      <div className="flex flex-wrap items-center gap-4 text-slate-500">
                        <span>Overall: <strong className="font-mono text-indigo-700 font-bold">{ds.overallScore}</strong></span>
                        <span>Quality: <strong className="font-mono text-slate-800">{ds.qualityScore}</strong></span>
                        <span>Relevance: <strong className="font-mono text-slate-800">{ds.relevanceScore}</strong></span>
                        <span>{ds.rowCount.toLocaleString()} rows</span>
                        <span>Published: {ds.createdAt}</span>
                      </div>

                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => onSelectDatasetForDetail(ds.id)}
                          className="px-3 py-1.5 rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-700 font-medium transition-colors cursor-pointer"
                        >
                          View Detail
                        </button>
                        <button
                          onClick={() => onImproveDataset(ds.id)}
                          className="px-3 py-1.5 rounded-lg bg-white border border-slate-300 hover:bg-slate-50 text-slate-700 font-medium transition-colors cursor-pointer"
                        >
                          Improve Version
                        </button>
                        <button
                          onClick={() => onOpenQuery(ds.id)}
                          className="px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white font-medium transition-colors shadow-xs cursor-pointer flex items-center gap-1"
                        >
                          <Search className="w-3 h-3" />
                          <span>Query</span>
                        </button>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* Accessed Tab */}
      {activeTab === 'accessed' && (
        <div className="space-y-4">
          {accessed.length === 0 ? (
            <div className="bg-white border border-slate-200 rounded-xl p-12 text-center space-y-3">
              <Unlock className="w-8 h-8 text-slate-300 mx-auto" />
              <h3 className="text-sm font-bold text-slate-800">
                No external datasets unlocked yet
              </h3>
              <p className="text-xs text-slate-500 max-w-sm mx-auto">
                Explore the marketplace and unlock datasets. Unlocking costs 20 credits once, charged only after your first successful query.
              </p>
              <button
                onClick={() => onNavigate('marketplace')}
                className="mt-2 px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold cursor-pointer shadow-xs"
              >
                Browse Marketplace
              </button>
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-4">
              {accessed.map((ds) => (
                <div
                  key={ds.id}
                  className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm space-y-4"
                >
                  <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3">
                    <div>
                      <div className="flex flex-wrap items-center gap-2 mb-1">
                        <span className="px-2 py-0.5 rounded text-[11px] font-semibold bg-slate-100 text-slate-700 border border-slate-200">
                          {ds.domain}
                        </span>
                        <span className="px-2 py-0.5 rounded text-[11px] font-mono uppercase bg-slate-100 text-slate-700 border border-slate-200">
                          {ds.format}
                        </span>
                        <span className="px-2 py-0.5 rounded text-[11px] font-semibold bg-indigo-50 text-indigo-700 border border-indigo-200 flex items-center gap-1">
                          <Unlock className="w-3 h-3" /> Unlocked
                        </span>
                      </div>
                      <h3 className="text-base font-bold text-slate-900">{ds.title}</h3>
                      <span className="text-xs font-mono text-slate-400 block">{ds.name}</span>
                      <p className="text-xs text-slate-600 mt-1">{ds.description}</p>
                    </div>

                    <div className="text-xs text-slate-500 shrink-0 text-right">
                      <span>Author: <strong>{ds.authorName}</strong></span>
                      <div className="text-slate-400 mt-0.5">Overall: {ds.overallScore}</div>
                    </div>
                  </div>

                  <div className="pt-3 border-t border-slate-100 flex items-center justify-between text-xs">
                    <span className="text-slate-400 font-mono">
                      {ds.rowCount.toLocaleString()} rows • {ds.columnCount} columns
                    </span>

                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => onSelectDatasetForDetail(ds.id)}
                        className="px-3 py-1.5 rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-700 font-medium transition-colors cursor-pointer"
                      >
                        View Detail
                      </button>
                      <button
                        onClick={() => onOpenQuery(ds.id)}
                        className="px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white font-medium transition-colors shadow-xs cursor-pointer flex items-center gap-1"
                      >
                        <Search className="w-3 h-3" />
                        <span>Query Workspace</span>
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
};
