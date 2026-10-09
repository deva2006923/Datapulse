import React, { useState } from 'react';
import {
  History,
  TrendingUp,
  Sparkles,
  ArrowRight,
  CheckCircle2,
  AlertCircle,
  FileCode,
  Coins,
  GitBranch,
} from 'lucide-react';
import { AppDataset, UserAccount, DatasetVersionEntry } from '../types';

interface VersionsImproveViewProps {
  currentUser: UserAccount;
  datasets: AppDataset[];
  selectedDatasetId?: string;
  onSelectDataset: (id: string) => void;
  onSubmitImprovement: (
    datasetId: string,
    newQuality: number,
    newRelevance: number,
    changesSummary: string,
    creditsAwarded: number
  ) => void;
}

export const VersionsImproveView: React.FC<VersionsImproveViewProps> = ({
  currentUser,
  datasets,
  selectedDatasetId,
  onSelectDataset,
  onSubmitImprovement,
}) => {
  const activeDataset =
    datasets.find((d) => d.id === selectedDatasetId) || datasets[0] || null;

  const [proposedQuality, setProposedQuality] = useState<number>(
    activeDataset ? Math.min(100, activeDataset.qualityScore + 12) : 95
  );
  const [proposedRelevance, setProposedRelevance] = useState<number>(
    activeDataset ? Math.min(100, activeDataset.relevanceScore + 6) : 95
  );
  const [changesSummary, setChangesSummary] = useState(
    'Imputed missing values, standardized categorical headers, and expanded natural synonym aliases.'
  );

  if (!activeDataset) {
    return (
      <div className="bg-white border border-slate-200 rounded-xl p-8 text-center text-slate-500">
        No dataset found to inspect.
      </div>
    );
  }

  const currentOverall = activeDataset.overallScore;
  const proposedOverall = (proposedQuality + proposedRelevance) / 2;
  const delta = Math.round(proposedOverall - currentOverall);

  // Formula: improvement credits = floor(delta x 0.75) if delta >= 5
  const eligibleForBounty = delta >= 5;
  const improvementCredits = eligibleForBounty ? Math.floor(delta * 0.75) : 0;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!changesSummary.trim()) return;

    onSubmitImprovement(
      activeDataset.id,
      proposedQuality,
      proposedRelevance,
      changesSummary,
      improvementCredits
    );
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="bg-white border border-slate-200 rounded-xl p-6 shadow-sm">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <span className="text-xs font-semibold text-indigo-600 uppercase tracking-wide">
              Dataset Evolution & Quality Upgrades
            </span>
            <h1 className="text-2xl font-extrabold text-slate-900 tracking-tight">
              Versions & Improve
            </h1>
            <p className="text-xs text-slate-500 mt-0.5">
              Inspect version lineage, submit schema enhancements, and earn improvement credits.
            </p>
          </div>

          <div className="flex items-center gap-2">
            <label className="text-xs font-medium text-slate-500">Target Dataset:</label>
            <select
              value={activeDataset.id}
              onChange={(e) => onSelectDataset(e.target.value)}
              className="bg-slate-50 border border-slate-300 rounded-lg px-3 py-1.5 text-xs font-semibold text-slate-800 outline-none max-w-xs truncate"
            >
              {datasets.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.title} ({d.currentVersion})
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>

      {/* Before / After Comparison Chart */}
      <div className="bg-white border border-slate-200 rounded-xl p-6 shadow-sm space-y-4">
        <h2 className="text-sm font-bold text-slate-900 uppercase tracking-wide">
          Quality & Relevance Comparison (Before vs. Proposed)
        </h2>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {/* Quality Score Bar */}
          <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 space-y-2">
            <span className="text-xs font-semibold text-slate-600 block">Quality Score</span>
            <div className="flex items-baseline justify-between text-xs">
              <span className="text-slate-500">Current: {activeDataset.qualityScore}</span>
              <span className="font-bold text-indigo-600 font-mono">Proposed: {proposedQuality}</span>
            </div>
            <div className="w-full bg-slate-200 rounded-full h-2.5 overflow-hidden">
              <div
                className="bg-indigo-600 h-2.5 rounded-full"
                style={{ width: `${proposedQuality}%` }}
              />
            </div>
          </div>

          {/* Relevance Score Bar */}
          <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 space-y-2">
            <span className="text-xs font-semibold text-slate-600 block">Relevance Score</span>
            <div className="flex items-baseline justify-between text-xs">
              <span className="text-slate-500">Current: {activeDataset.relevanceScore}</span>
              <span className="font-bold text-indigo-600 font-mono">Proposed: {proposedRelevance}</span>
            </div>
            <div className="w-full bg-slate-200 rounded-full h-2.5 overflow-hidden">
              <div
                className="bg-emerald-600 h-2.5 rounded-full"
                style={{ width: `${proposedRelevance}%` }}
              />
            </div>
          </div>

          {/* Overall Delta */}
          <div className="p-4 rounded-xl bg-indigo-50 border border-indigo-200 space-y-2">
            <span className="text-xs font-semibold text-indigo-900 block">Overall Score Delta</span>
            <div className="flex items-baseline justify-between text-xs">
              <span className="text-indigo-700">Baseline: {currentOverall}</span>
              <span className="font-bold text-indigo-700 font-mono">New: {proposedOverall}</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-lg font-black font-mono text-indigo-700">
                {delta >= 0 ? `+${delta}` : delta} pts
              </span>
              <span className="text-[11px] text-slate-500">
                ({eligibleForBounty ? `Eligible: +${improvementCredits} cr` : 'Min 5 pts for bounty'})
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Improvement Form */}
      <div className="bg-white border border-slate-200 rounded-xl p-6 shadow-sm space-y-5">
        <div className="border-b border-slate-100 pb-3">
          <h2 className="text-sm font-bold text-slate-900 uppercase tracking-wide">
            Submit Version Improvement (v{parseInt(activeDataset.currentVersion.replace('v', '')) + 1}.0)
          </h2>
          <p className="text-xs text-slate-500 mt-0.5">
            Rule: Earn <strong className="text-slate-700">floor(delta × 0.75)</strong> credits if score improvement delta is at least 5 points.
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="text-xs font-semibold text-slate-700 block mb-1">
                Proposed Quality Score (0 - 100)
              </label>
              <input
                type="number"
                min={activeDataset.qualityScore}
                max={100}
                value={proposedQuality}
                onChange={(e) => setProposedQuality(Number(e.target.value))}
                className="w-full bg-slate-50 border border-slate-300 rounded-lg px-3 py-2 text-xs font-mono text-slate-900 focus:outline-none focus:border-indigo-500"
              />
              <span className="text-[11px] text-slate-400 mt-1 block">
                Current baseline: {activeDataset.qualityScore}
              </span>
            </div>

            <div>
              <label className="text-xs font-semibold text-slate-700 block mb-1">
                Proposed Relevance Score (0 - 100)
              </label>
              <input
                type="number"
                min={activeDataset.relevanceScore}
                max={100}
                value={proposedRelevance}
                onChange={(e) => setProposedRelevance(Number(e.target.value))}
                className="w-full bg-slate-50 border border-slate-300 rounded-lg px-3 py-2 text-xs font-mono text-slate-900 focus:outline-none focus:border-indigo-500"
              />
              <span className="text-[11px] text-slate-400 mt-1 block">
                Current baseline: {activeDataset.relevanceScore}
              </span>
            </div>

            <div className="sm:col-span-2">
              <label className="text-xs font-semibold text-slate-700 block mb-1">
                Summary of Schema Improvements & Refinements
              </label>
              <textarea
                rows={2}
                value={changesSummary}
                onChange={(e) => setChangesSummary(e.target.value)}
                className="w-full bg-slate-50 border border-slate-300 rounded-lg px-3 py-2 text-xs text-slate-900 focus:outline-none focus:border-indigo-500"
                placeholder="Detail changes like null cleanup, deduplication, synonym expansion..."
              />
            </div>
          </div>

          {/* Reward Preview Banner */}
          <div className="bg-slate-50 border border-slate-200 rounded-xl p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div>
              <span className="text-xs font-bold text-slate-800 block">
                Calculated Improvement Bounty:
              </span>
              <p className="text-[11px] text-slate-500">
                {eligibleForBounty
                  ? `Delta of +${delta} pts gives floor(${delta} × 0.75) = +${improvementCredits} credits.`
                  : 'Score delta is less than 5 points. Minimum 5 point improvement required to earn credits.'}
              </p>
            </div>

            <div className="flex items-center gap-3">
              <span className="text-xl font-black font-mono text-emerald-600">
                +{improvementCredits} cr
              </span>

              <button
                type="submit"
                className="px-5 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white font-semibold text-xs shadow-xs transition-colors cursor-pointer flex items-center gap-1.5"
              >
                <Sparkles className="w-3.5 h-3.5" />
                <span>Submit Improvement</span>
              </button>
            </div>
          </div>
        </form>
      </div>

      {/* Version Timeline */}
      <div className="bg-white border border-slate-200 rounded-xl p-6 shadow-sm space-y-4">
        <h2 className="text-sm font-bold text-slate-900 uppercase tracking-wide">
          Version History Timeline
        </h2>

        <div className="space-y-4">
          {activeDataset.versionHistory.map((ver, idx) => (
            <div key={idx} className="relative pl-6 pb-4 border-l-2 border-indigo-200 last:pb-0">
              <div className="absolute -left-1.5 top-0.5 w-3 h-3 rounded-full bg-indigo-600 border-2 border-white" />
              <div className="bg-slate-50 border border-slate-200 rounded-xl p-4 space-y-2">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-1">
                  <div className="flex items-center gap-2">
                    <span className="font-bold text-xs text-indigo-700 font-mono bg-indigo-50 border border-indigo-200 px-2 py-0.5 rounded">
                      {ver.version}
                    </span>
                    <span className="text-xs font-semibold text-slate-800">{ver.author}</span>
                  </div>
                  <span className="text-[11px] text-slate-400 font-mono">{ver.date}</span>
                </div>

                <p className="text-xs text-slate-600 leading-relaxed">
                  {ver.changesSummary}
                </p>

                <div className="flex items-center gap-3 text-[11px] text-slate-500 pt-1 border-t border-slate-100">
                  <span>Quality: <strong className="font-mono text-slate-700">{ver.quality}</strong></span>
                  <span>Relevance: <strong className="font-mono text-slate-700">{ver.relevance}</strong></span>
                  <span>Overall: <strong className="font-mono text-indigo-600">{(ver.quality + ver.relevance) / 2}</strong></span>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
