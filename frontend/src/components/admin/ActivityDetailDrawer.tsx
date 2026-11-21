import React, { useState } from 'react';
import {
  X,
  User,
  Database,
  Search,
  Coins,
  Clock,
  Copy,
  Check,
  ExternalLink,
  Activity,
  GitCommit,
  Unlock,
  Shield,
  LogIn,
} from 'lucide-react';
import { AdminTimelineItem } from '../../types';

interface ActivityDetailDrawerProps {
  item: AdminTimelineItem;
  onClose: () => void;
  onInspectUser: (userId: string) => void;
  onInspectDataset: (datasetId: string) => void;
}

export const ActivityDetailDrawer: React.FC<ActivityDetailDrawerProps> = ({
  item,
  onClose,
  onInspectUser,
  onInspectDataset,
}) => {
  const [copiedSql, setCopiedSql] = useState(false);

  const iconForType = () => {
    switch (item.type) {
      case 'USER_REGISTER':
        return <User className="w-5 h-5 text-indigo-300" />;
      case 'USER_LOGIN':
        return <LogIn className="w-5 h-5 text-sky-300" />;
      case 'DATASET_UPLOAD':
        return <Database className="w-5 h-5 text-emerald-300" />;
      case 'QUERY_EXECUTION':
        return <Search className="w-5 h-5 text-cyan-300" />;
      case 'CREDIT_TRANSACTION':
        return <Coins className="w-5 h-5 text-amber-300" />;
      case 'DATASET_IMPROVE':
        return <GitCommit className="w-5 h-5 text-violet-300" />;
      case 'DATASET_UNLOCK':
        return <Unlock className="w-5 h-5 text-blue-300" />;
      case 'ADMIN_AUDIT':
        return <Shield className="w-5 h-5 text-rose-300" />;
      default:
        return <Activity className="w-5 h-5 text-slate-300" />;
    }
  };

  const isSuccess =
    item.status?.toUpperCase() === 'SUCCESS' || item.status?.toUpperCase() === 'COMPLETED';

  return (
    <div
      className="fixed inset-0 z-50 bg-slate-900/50 backdrop-blur-xs flex justify-end"
      onClick={onClose}
    >
      <div
        className="bg-white w-full max-w-xl h-full shadow-2xl border-l border-slate-200 flex flex-col overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="px-6 py-5 bg-slate-900 text-white shrink-0 flex items-start justify-between gap-4">
          <div className="flex items-start gap-3.5 min-w-0">
            <div className="w-10 h-10 rounded-xl bg-white/10 border border-white/15 flex items-center justify-center shrink-0">
              {iconForType()}
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <h2 className="text-base font-bold text-white">{item.title}</h2>
                <span
                  className={`px-2 py-0.5 rounded-full text-[10px] font-bold uppercase ${
                    isSuccess
                      ? 'bg-emerald-500/20 text-emerald-200 border border-emerald-400/30'
                      : 'bg-rose-500/20 text-rose-200 border border-rose-400/30'
                  }`}
                >
                  {item.status}
                </span>
              </div>
              <div className="text-xs text-slate-400 font-mono mt-1 flex items-center gap-1.5">
                <Clock className="w-3 h-3" />
                <span>{new Date(item.timestamp).toLocaleString()}</span>
              </div>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-2 rounded-lg bg-white/10 hover:bg-rose-500/80 text-slate-200 hover:text-white cursor-pointer transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-6 bg-slate-50/50 space-y-5 text-xs">
          {/* Primary Description */}
          <div className="bg-white border border-slate-200 rounded-xl p-4 space-y-2">
            <div className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
              Event Description
            </div>
            <p className="text-sm text-slate-900 leading-relaxed whitespace-pre-wrap break-words">
              {item.description}
            </p>
            <div className="pt-2 border-t border-slate-100 flex flex-wrap gap-3 text-[11px] font-mono text-slate-500">
              <span>Event ID: {item.id}</span>
              <span>Type: {item.type}</span>
              {item.related_query_id && <span>Query: {item.related_query_id}</span>}
              {item.related_transaction_id && <span>Tx: {item.related_transaction_id}</span>}
            </div>
          </div>

          {/* Actor */}
          {(item.user_id || item.user_email) && (
            <div className="bg-white border border-slate-200 rounded-xl p-4 flex items-center justify-between gap-3">
              <div className="min-w-0">
                <div className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                  Associated User
                </div>
                <div className="font-bold text-slate-900 mt-0.5">{item.user_name || 'User'}</div>
                <div className="text-[11px] font-mono text-slate-500 truncate">
                  {item.user_email || item.user_id}
                </div>
              </div>
              {item.user_id && (
                <button
                  type="button"
                  onClick={() => {
                    onClose();
                    onInspectUser(item.user_id!);
                  }}
                  className="px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white font-semibold inline-flex items-center gap-1.5 shrink-0 cursor-pointer transition-colors"
                >
                  <span>Open User Profile</span>
                  <ExternalLink className="w-3 h-3" />
                </button>
              )}
            </div>
          )}

          {/* Dataset Reference */}
          {(item.dataset_id || item.dataset_name) && (
            <div className="bg-white border border-slate-200 rounded-xl p-4 flex items-center justify-between gap-3">
              <div className="min-w-0">
                <div className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                  Associated Dataset
                </div>
                <div className="font-bold text-slate-900 mt-0.5 truncate">
                  {item.dataset_name || item.dataset_id}
                </div>
                {item.dataset_id && (
                  <div className="text-[11px] font-mono text-slate-500">{item.dataset_id}</div>
                )}
              </div>
              {item.dataset_id && (
                <button
                  type="button"
                  onClick={() => {
                    onClose();
                    onInspectDataset(item.dataset_id!);
                  }}
                  className="px-3 py-1.5 rounded-lg border border-slate-200 hover:bg-slate-50 text-slate-800 font-semibold inline-flex items-center gap-1.5 shrink-0 cursor-pointer transition-colors"
                >
                  <span>Inspect Dataset</span>
                  <ExternalLink className="w-3 h-3" />
                </button>
              )}
            </div>
          )}

          {/* Generated SQL (for query events) */}
          {item.metadata?.generated_sql && (
            <div className="bg-white border border-slate-200 rounded-xl p-4 space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                  Generated SQL
                </span>
                <button
                  type="button"
                  onClick={() => {
                    navigator.clipboard.writeText(item.metadata?.generated_sql || '');
                    setCopiedSql(true);
                    setTimeout(() => setCopiedSql(false), 1800);
                  }}
                  className="px-2 py-1 rounded-md border border-slate-200 hover:bg-slate-50 text-[11px] font-semibold text-slate-600 inline-flex items-center gap-1 cursor-pointer"
                >
                  {copiedSql ? (
                    <>
                      <Check className="w-3 h-3 text-emerald-600" />
                      <span className="text-emerald-700">Copied</span>
                    </>
                  ) : (
                    <>
                      <Copy className="w-3 h-3" />
                      <span>Copy SQL</span>
                    </>
                  )}
                </button>
              </div>
              <pre className="p-3 bg-slate-900 text-emerald-400 rounded-xl font-mono text-[11px] overflow-x-auto whitespace-pre-wrap leading-relaxed">
                {item.metadata.generated_sql}
              </pre>
            </div>
          )}

          {/* Error Details */}
          {item.metadata?.error_message && (
            <div className="p-3.5 rounded-xl bg-rose-50 border border-rose-200 text-rose-800">
              <div className="font-bold text-[11px] uppercase tracking-wider text-rose-700 mb-1">
                Error Details
              </div>
              <p className="font-mono text-xs break-words">{item.metadata.error_message}</p>
            </div>
          )}

          {/* Structured Metadata */}
          {item.metadata && Object.keys(item.metadata).length > 0 && (
            <div className="bg-white border border-slate-200 rounded-xl p-4 space-y-2.5">
              <div className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                Event Metadata
              </div>
              <div className="divide-y divide-slate-100">
                {Object.entries(item.metadata)
                  .filter(([k, v]) => k !== 'generated_sql' && k !== 'error_message' && v !== null && v !== '')
                  .map(([k, v]) => (
                    <div key={k} className="py-2 flex items-center justify-between gap-3">
                      <span className="text-slate-500 capitalize">{k.replace(/_/g, ' ')}</span>
                      <span className="font-mono font-semibold text-slate-800 text-right break-all">
                        {String(v)}
                      </span>
                    </div>
                  ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
