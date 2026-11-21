import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  X,
  Database,
  CheckCircle2,
  AlertTriangle,
  User,
  GitCommit,
  Search,
  Coins,
  Layers,
  RefreshCw,
  Copy,
  Check,
  Clock,
  ExternalLink,
} from 'lucide-react';
import { AdminDatasetDetail } from '../../types';
import { api } from '../../services/api';
import { ErrorRetryBanner } from './AdminCharts';

interface DatasetInspectionDrawerProps {
  datasetId: string;
  onClose: () => void;
  onInspectUser?: (userId: string) => void;
}

export const DatasetInspectionDrawer: React.FC<DatasetInspectionDrawerProps> = ({
  datasetId,
  onClose,
  onInspectUser,
}) => {
  const [detail, setDetail] = useState<AdminDatasetDetail | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [copiedId, setCopiedId] = useState<boolean>(false);
  const requestSeqRef = useRef<number>(0);

  const loadDetail = useCallback(async () => {
    const seq = ++requestSeqRef.current;
    setLoading(true);
    setError(null);
    setDetail(null);
    try {
      const data = await api.admin.getDatasetDetail(datasetId);
      if (seq === requestSeqRef.current) {
        setDetail(data);
      }
    } catch (err: any) {
      if (seq === requestSeqRef.current) {
        setError(err.message || 'Failed to load dataset inspection details.');
      }
    } finally {
      if (seq === requestSeqRef.current) {
        setLoading(false);
      }
    }
  }, [datasetId]);

  useEffect(() => {
    loadDetail();
  }, [loadDetail]);

  const copyDatasetId = () => {
    navigator.clipboard.writeText(datasetId);
    setCopiedId(true);
    setTimeout(() => setCopiedId(false), 1800);
  };

  return (
    <div
      className="fixed inset-0 z-50 bg-slate-900/50 backdrop-blur-xs flex justify-end"
      onClick={onClose}
    >
      <div
        className="bg-white w-full max-w-2xl h-full shadow-2xl border-l border-slate-200 flex flex-col overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="px-6 py-5 bg-slate-900 text-white shrink-0 flex items-start justify-between gap-4">
          <div className="flex items-start gap-3.5 min-w-0">
            <div className="w-10 h-10 rounded-xl bg-emerald-500/20 border border-emerald-400/30 text-emerald-300 flex items-center justify-center shrink-0">
              <Database className="w-5 h-5" />
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <h2 className="text-lg font-bold text-white truncate">
                  {detail?.name || 'Dataset Inspection'}
                </h2>
                {detail?.domain && (
                  <span className="px-2 py-0.5 rounded text-[10px] font-bold uppercase bg-white/10 text-slate-200">
                    {detail.domain}
                  </span>
                )}
              </div>
              <div className="flex items-center gap-2 text-xs text-slate-300 font-mono mt-1 flex-wrap">
                <span>{datasetId}</span>
                <button
                  type="button"
                  onClick={copyDatasetId}
                  className="text-slate-400 hover:text-white cursor-pointer"
                  title="Copy Dataset ID"
                >
                  {copiedId ? (
                    <Check className="w-3 h-3 text-emerald-400" />
                  ) : (
                    <Copy className="w-3 h-3" />
                  )}
                </button>
                {detail?.filename && (
                  <>
                    <span className="text-slate-600">•</span>
                    <span className="truncate max-w-[220px]">{detail.filename}</span>
                  </>
                )}
              </div>
            </div>
          </div>

          <div className="flex items-center gap-1.5 shrink-0">
            <button
              type="button"
              onClick={loadDetail}
              className="p-2 rounded-lg bg-white/10 hover:bg-white/20 text-slate-200 cursor-pointer transition-colors"
              title="Refresh"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            </button>
            <button
              type="button"
              onClick={onClose}
              className="p-2 rounded-lg bg-white/10 hover:bg-rose-500/80 text-slate-200 hover:text-white cursor-pointer transition-colors"
              title="Close"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6 bg-slate-50/50 space-y-5">
          {error && <ErrorRetryBanner message={error} onRetry={loadDetail} />}

          {loading ? (
            <div className="space-y-4">
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                {[1, 2, 3, 4].map((n) => (
                  <div key={n} className="h-20 bg-white border border-slate-200 rounded-xl animate-pulse" />
                ))}
              </div>
              <div className="h-36 bg-white border border-slate-200 rounded-xl animate-pulse" />
              <div className="h-44 bg-white border border-slate-200 rounded-xl animate-pulse" />
            </div>
          ) : detail ? (
            <>
              {/* Owner & Storage Strip */}
              <div className="bg-white border border-slate-200 rounded-xl p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <div className="flex items-center gap-3 min-w-0">
                  <div className="w-9 h-9 rounded-full bg-indigo-50 text-indigo-600 flex items-center justify-center shrink-0">
                    <User className="w-4 h-4" />
                  </div>
                  <div className="min-w-0">
                    <div className="text-[11px] uppercase font-bold text-slate-400">Dataset Owner</div>
                    <div className="text-xs font-bold text-slate-900 truncate">{detail.owner_name}</div>
                    <div className="text-[11px] font-mono text-slate-500 truncate">{detail.owner_email}</div>
                  </div>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <span
                    className={`px-2.5 py-1 rounded-full text-[11px] font-semibold inline-flex items-center gap-1 ${
                      detail.availability === 'Available'
                        ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                        : 'bg-amber-50 text-amber-700 border border-amber-200'
                    }`}
                  >
                    {detail.availability === 'Available' ? (
                      <CheckCircle2 className="w-3 h-3" />
                    ) : (
                      <AlertTriangle className="w-3 h-3" />
                    )}
                    {detail.availability === 'Available' ? 'DuckDB Ready' : detail.availability}
                  </span>
                  {onInspectUser && (
                    <button
                      type="button"
                      onClick={() => onInspectUser(detail.owner_id)}
                      className="px-2.5 py-1 rounded-lg border border-slate-200 hover:bg-indigo-50 hover:text-indigo-700 hover:border-indigo-200 text-xs font-semibold text-slate-700 inline-flex items-center gap-1 cursor-pointer transition-colors"
                    >
                      <span>View Owner</span>
                      <ExternalLink className="w-3 h-3" />
                    </button>
                  )}
                </div>
              </div>

              {/* KPI Strip */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <div className="bg-white border border-slate-200 rounded-xl p-3.5">
                  <span className="text-[10px] uppercase font-bold text-slate-400">Dimensions</span>
                  <div className="text-base font-black font-mono text-slate-900 mt-1">
                    {detail.rows_count.toLocaleString()} × {detail.columns_count}
                  </div>
                  <span className="text-[10px] text-slate-400">rows × columns</span>
                </div>
                <div className="bg-white border border-slate-200 rounded-xl p-3.5">
                  <span className="text-[10px] uppercase font-bold text-slate-400">Overall Score</span>
                  <div className="text-base font-black font-mono text-emerald-600 mt-1">
                    {detail.evaluation ? `${detail.evaluation.overall_score.toFixed(1)}/100` : 'Pending'}
                  </div>
                  <span className="text-[10px] text-slate-400 capitalize">
                    {detail.evaluation?.status || 'unrated'}
                  </span>
                </div>
                <div className="bg-white border border-slate-200 rounded-xl p-3.5">
                  <span className="text-[10px] uppercase font-bold text-slate-400">Query Usage</span>
                  <div className="text-base font-black font-mono text-slate-900 mt-1">
                    {detail.query_count.toLocaleString()}
                  </div>
                  <span className="text-[10px] text-slate-400">
                    {detail.successful_queries} ok • {detail.unique_queriers} users
                  </span>
                </div>
                <div className="bg-white border border-slate-200 rounded-xl p-3.5">
                  <span className="text-[10px] uppercase font-bold text-slate-400">Unlock Pricing</span>
                  <div className="text-base font-black font-mono text-amber-600 mt-1">
                    {detail.unlock_price} cr
                  </div>
                  <span className="text-[10px] text-slate-400">{detail.unlock_count} unlocks</span>
                </div>
              </div>

              {/* Evaluation & Rewards */}
              <div className="bg-white border border-slate-200 rounded-xl p-4 space-y-4">
                <div className="flex items-center justify-between">
                  <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500 flex items-center gap-1.5">
                    <Coins className="w-3.5 h-3.5 text-amber-500" />
                    Evaluation Breakdown & Contributor Rewards
                  </h3>
                  <span className="text-xs font-mono font-bold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded">
                    Total Earned: +{detail.total_rewards} cr
                  </span>
                </div>

                {detail.evaluation && (
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
                    {[
                      { label: 'Schema Fidelity', val: detail.evaluation.schema_fidelity_score },
                      { label: 'Completeness', val: detail.evaluation.completeness_score },
                      { label: 'Domain Relevance', val: detail.evaluation.domain_relevance_score },
                    ].map((m) => (
                      <div key={m.label} className="p-3 rounded-lg bg-slate-50 border border-slate-100">
                        <div className="flex items-center justify-between mb-1.5">
                          <span className="text-slate-600 font-medium">{m.label}</span>
                          <span className="font-mono font-bold text-slate-900">{m.val.toFixed(1)}%</span>
                        </div>
                        <div className="h-1.5 bg-slate-200 rounded-full overflow-hidden">
                          <div
                            className="h-full bg-indigo-500 rounded-full"
                            style={{ width: `${Math.min(100, Math.max(0, m.val))}%` }}
                          />
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                <div className="grid grid-cols-3 gap-2 pt-2 border-t border-slate-100 text-xs">
                  <div className="p-2.5 rounded-lg bg-slate-50 text-center">
                    <div className="text-[10px] uppercase text-slate-400 font-semibold">Basic Upload</div>
                    <div className="font-mono font-bold text-slate-900 mt-0.5">+{detail.basic_upload_reward} cr</div>
                  </div>
                  <div className="p-2.5 rounded-lg bg-slate-50 text-center">
                    <div className="text-[10px] uppercase text-slate-400 font-semibold">Quality Reward</div>
                    <div className="font-mono font-bold text-emerald-700 mt-0.5">+{detail.quality_reward} cr</div>
                  </div>
                  <div className="p-2.5 rounded-lg bg-slate-50 text-center">
                    <div className="text-[10px] uppercase text-slate-400 font-semibold">Improvements</div>
                    <div className="font-mono font-bold text-indigo-700 mt-0.5">+{detail.improvement_rewards} cr</div>
                  </div>
                </div>
              </div>

              {/* Version History */}
              <div className="bg-white border border-slate-200 rounded-xl p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500 flex items-center gap-1.5">
                    <GitCommit className="w-3.5 h-3.5 text-indigo-500" />
                    Version History ({detail.version_count})
                  </h3>
                  <span className="text-[11px] font-mono text-slate-400">
                    Uploaded {new Date(detail.created_at).toLocaleDateString()}
                  </span>
                </div>
                <div className="space-y-2 text-xs">
                  {detail.versions.map((v, i) => (
                    <div
                      key={`${v.version}-${i}`}
                      className="p-3 rounded-lg bg-slate-50 border border-slate-100 flex items-start justify-between gap-3"
                    >
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="px-1.5 py-0.5 rounded bg-indigo-50 text-indigo-700 font-mono font-bold text-[10px]">
                            {v.version}
                          </span>
                          <span className="font-semibold text-slate-800">
                            Score {Number(v.overall_score).toFixed(1)} ({v.delta_score >= 0 ? '+' : ''}
                            {Number(v.delta_score).toFixed(1)} pts)
                          </span>
                          {v.credits_awarded > 0 && (
                            <span className="text-[10px] font-mono font-bold text-emerald-700">
                              +{v.credits_awarded} cr
                            </span>
                          )}
                        </div>
                        <p className="text-slate-600 mt-1">{v.changes_summary}</p>
                      </div>
                      <span className="text-[10px] font-mono text-slate-400 shrink-0">
                        {new Date(v.created_at).toLocaleDateString()}
                      </span>
                    </div>
                  ))}
                  <div className="p-3 rounded-lg bg-slate-50/70 border border-slate-100 flex items-center justify-between gap-3">
                    <div className="flex items-center gap-2">
                      <span className="px-1.5 py-0.5 rounded bg-slate-200 text-slate-700 font-mono font-bold text-[10px]">
                        v1.0
                      </span>
                      <span className="text-slate-700 font-medium">Initial dataset upload & automated evaluation</span>
                    </div>
                    <span className="text-[10px] font-mono text-slate-400 shrink-0">
                      {new Date(detail.created_at).toLocaleDateString()}
                    </span>
                  </div>
                </div>
              </div>

              {/* Schema Columns (metadata only — no raw data) */}
              {detail.schema_columns.length > 0 && (
                <div className="bg-white border border-slate-200 rounded-xl p-4 space-y-2.5">
                  <div className="flex items-center justify-between">
                    <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500 flex items-center gap-1.5">
                      <Layers className="w-3.5 h-3.5 text-slate-500" />
                      Schema Structure ({detail.schema_columns.length} columns)
                    </h3>
                    <span className="text-[10px] font-mono text-slate-400">Raw rows redacted</span>
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {detail.schema_columns.map((c) => (
                      <span
                        key={c.name}
                        className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-slate-50 border border-slate-200 text-[11px] font-mono"
                      >
                        <span className="text-slate-800 font-semibold">{c.name}</span>
                        <span className="text-slate-400">{c.type}</span>
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Recent Query Usage Metadata */}
              <div className="bg-white border border-slate-200 rounded-xl p-4 space-y-3">
                <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500 flex items-center gap-1.5">
                  <Search className="w-3.5 h-3.5 text-cyan-600" />
                  Recent Query Usage ({detail.recent_queries.length})
                </h3>
                {detail.recent_queries.length === 0 ? (
                  <p className="text-xs text-slate-400 py-2">No queries have targeted this dataset yet.</p>
                ) : (
                  <div className="divide-y divide-slate-100 text-xs">
                    {detail.recent_queries.map((q) => (
                      <div key={q.id} className="py-2.5 flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <p className="font-medium text-slate-800 truncate">{q.natural_prompt}</p>
                          <div className="flex items-center gap-2 text-[11px] text-slate-400 mt-0.5">
                            <span className="font-mono">{q.user_email}</span>
                            <span>•</span>
                            <span className="font-mono">{q.execution_time_ms}ms</span>
                            <span>•</span>
                            <span className="font-mono">{q.rows_returned} rows</span>
                          </div>
                        </div>
                        <div className="text-right shrink-0">
                          <span
                            className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
                              q.status === 'SUCCESS'
                                ? 'bg-emerald-50 text-emerald-700'
                                : 'bg-rose-50 text-rose-700'
                            }`}
                          >
                            {q.status}
                          </span>
                          <div className="text-[10px] text-slate-400 font-mono mt-1 flex items-center justify-end gap-1">
                            <Clock className="w-2.5 h-2.5" />
                            {new Date(q.timestamp).toLocaleDateString()}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </>
          ) : null}
        </div>
      </div>
    </div>
  );
};
