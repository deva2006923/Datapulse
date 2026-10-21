import React, { useState, useEffect } from 'react';
import {
  History,
  Search,
  Filter,
  Copy,
  Check,
  CheckCircle2,
  AlertTriangle,
  Clock,
  Terminal,
  RefreshCw,
  ArrowRight,
} from 'lucide-react';
import { QueryHistoryItem } from '../types';
import { api } from '../services/api';

interface QueryHistoryViewProps {
  currentUserId: string;
  history?: QueryHistoryItem[];
  onRefreshHistory?: () => Promise<void> | void;
  onNavigateToQuery?: () => void;
}

export const QueryHistoryView: React.FC<QueryHistoryViewProps> = ({
  currentUserId,
  history,
  onRefreshHistory,
  onNavigateToQuery,
}) => {
  const [historyItems, setHistoryItems] = useState<QueryHistoryItem[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('All');
  const [copiedId, setCopiedId] = useState<string | null>(null);

  // Pagination state
  const [page, setPage] = useState<number>(1);
  const pageSize = 20;
  const [totalCount, setTotalCount] = useState<number>(0);
  const [hasMore, setHasMore] = useState<boolean>(false);

  const fetchHistory = async (targetPage = 1) => {
    if (!currentUserId) {
      setHistoryItems([]);
      setTotalCount(0);
      setIsLoading(false);
      return;
    }

    setIsLoading(true);
    setError(null);

    try {
      const response = await api.query.getHistory({
        page: targetPage,
        limit: pageSize,
      });

      // Ensure every item is restricted to the authenticated user ID
      const userItems = (response.items || []).filter(
        (it) => !it.userId || it.userId === currentUserId
      );

      setHistoryItems(userItems);
      setTotalCount(response.total ?? userItems.length);
      setHasMore(response.has_more ?? false);
      setPage(targetPage);

      if (onRefreshHistory) {
        try {
          await onRefreshHistory();
        } catch {
          // ignore
        }
      }
    } catch (err: any) {
      // If props history was provided and network request failed, fallback gracefully
      if (history && history.length > 0) {
        const userItems = history.filter((it) => it.userId === currentUserId);
        setHistoryItems(userItems);
        setTotalCount(userItems.length);
      } else {
        setError(err?.message || 'Failed to fetch query history from server.');
      }
    } finally {
      setIsLoading(false);
    }
  };

  // Fetch when user ID changes (or on initial mount)
  useEffect(() => {
    setPage(1);
    fetchHistory(1);
  }, [currentUserId]);

  // Sync if parent updates history prop
  useEffect(() => {
    if (history && history.length > 0) {
      const filteredForUser = history.filter((it) => it.userId === currentUserId);
      setHistoryItems((prev) => {
        // Only update if different
        if (prev.length === 0 && filteredForUser.length > 0) {
          return filteredForUser;
        }
        return prev;
      });
    }
  }, [history, currentUserId]);

  const handleCopySql = (id: string, sql: string) => {
    navigator.clipboard.writeText(sql);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const filtered = historyItems.filter((item) => {
    const matchesSearch =
      (item.naturalPrompt || '').toLowerCase().includes(searchTerm.toLowerCase()) ||
      (item.datasetName || '').toLowerCase().includes(searchTerm.toLowerCase()) ||
      (item.generatedSql || '').toLowerCase().includes(searchTerm.toLowerCase());

    const matchesStatus =
      statusFilter === 'All' || item.status === statusFilter;

    return matchesSearch && matchesStatus;
  });

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="bg-white border border-slate-200 rounded-xl p-6 shadow-sm">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <span className="text-xs font-semibold text-indigo-600 uppercase tracking-wide">
              Your query history
            </span>
            <h1 className="text-2xl font-extrabold text-slate-900 tracking-tight">
              Query History
            </h1>
            <p className="text-xs text-slate-500 mt-0.5">
              Comprehensive ledger of analytical prompts, compiled SQL queries, and credit debits.
            </p>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => fetchHistory(page)}
              disabled={isLoading}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-slate-700 bg-slate-50 border border-slate-200 rounded-lg hover:bg-slate-100 disabled:opacity-50 transition cursor-pointer"
              title="Refresh History from Backend"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin text-indigo-600' : 'text-slate-500'}`} />
              <span>Refresh</span>
            </button>

            <div className="text-xs font-mono text-slate-500 bg-slate-50 border border-slate-200 px-3 py-1.5 rounded-lg">
              {totalCount > 0 ? `${totalCount} logged queries` : `${historyItems.length} logged queries`}
            </div>
          </div>
        </div>

        {/* Filter Toolbar */}
        <div className="mt-4 pt-4 border-t border-slate-100 flex flex-col md:flex-row items-center justify-between gap-3">
          <div className="relative w-full md:w-80">
            <Search className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" />
            <input
              type="text"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              placeholder="Search prompts or SQL statements..."
              className="w-full bg-slate-50 border border-slate-200 rounded-lg pl-9 pr-3 py-1.5 text-xs text-slate-900 placeholder-slate-400 focus:outline-none focus:border-indigo-500"
            />
          </div>

          <div className="flex items-center gap-2 w-full md:w-auto">
            <span className="text-xs text-slate-500">Status:</span>
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="bg-slate-50 border border-slate-200 rounded-md px-2 py-1 text-xs text-slate-700 outline-none"
            >
              <option value="All">All Statuses</option>
              <option value="SUCCESS">SUCCESS</option>
              <option value="SQL_REJECTED">SQL_REJECTED</option>
              <option value="INSUFFICIENT_CREDITS">INSUFFICIENT_CREDITS</option>
            </select>
          </div>
        </div>
      </div>

      {/* History Table */}
      <div className="bg-white border border-slate-200 rounded-xl overflow-hidden shadow-sm">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-50 text-slate-500 border-b border-slate-200 text-[11px]">
              <tr>
                <th className="py-2.5 px-4 font-semibold">Timestamp</th>
                <th className="py-2.5 px-4 font-semibold">Dataset</th>
                <th className="py-2.5 px-4 font-semibold">Natural Language Prompt</th>
                <th className="py-2.5 px-4 font-semibold">Generated SQL</th>
                <th className="py-2.5 px-4 font-semibold">Rows</th>
                <th className="py-2.5 px-4 font-semibold">Time</th>
                <th className="py-2.5 px-4 font-semibold">Status</th>
                <th className="py-2.5 px-4 font-semibold text-right">Charge</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-slate-700">
              {isLoading ? (
                <tr>
                  <td colSpan={8} className="py-12 text-center text-slate-400">
                    <div className="flex flex-col items-center justify-center gap-2">
                      <RefreshCw className="w-5 h-5 text-indigo-500 animate-spin" />
                      <span className="text-xs text-slate-500 font-medium">Loading query history...</span>
                    </div>
                  </td>
                </tr>
              ) : error ? (
                <tr>
                  <td colSpan={8} className="py-10 text-center">
                    <div className="flex flex-col items-center justify-center gap-2 text-rose-600">
                      <AlertTriangle className="w-5 h-5" />
                      <p className="text-xs font-semibold">{error}</p>
                      <button
                        onClick={() => fetchHistory(page)}
                        className="px-3 py-1 mt-1 text-xs font-medium text-slate-700 bg-white border border-slate-300 rounded hover:bg-slate-50 cursor-pointer"
                      >
                        Retry
                      </button>
                    </div>
                  </td>
                </tr>
              ) : filtered.length === 0 ? (
                <tr>
                  <td colSpan={8} className="py-12 text-center text-slate-400">
                    {historyItems.length === 0 ? (
                      <div className="flex flex-col items-center justify-center max-w-sm mx-auto space-y-3 py-4">
                        <div className="w-12 h-12 rounded-full bg-indigo-50 border border-indigo-100 flex items-center justify-center text-indigo-600">
                          <Terminal className="w-6 h-6" />
                        </div>
                        <div>
                          <h3 className="text-sm font-bold text-slate-800">No Queries Run Yet</h3>
                          <p className="text-xs text-slate-500 mt-1 leading-relaxed">
                            You haven't executed any natural language queries yet. Select an uploaded or marketplace dataset in the Query Workspace to start compiling SQL queries.
                          </p>
                        </div>
                        {onNavigateToQuery && (
                          <button
                            onClick={onNavigateToQuery}
                            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-white bg-indigo-600 hover:bg-indigo-700 rounded-lg shadow-sm transition cursor-pointer"
                          >
                            <Terminal className="w-3.5 h-3.5" />
                            <span>Open Query Workspace</span>
                            <ArrowRight className="w-3 h-3 ml-0.5" />
                          </button>
                        )}
                      </div>
                    ) : (
                      <div className="py-6">
                        <p className="text-xs text-slate-500">No query history records match your search filter.</p>
                        <button
                          onClick={() => {
                            setSearchTerm('');
                            setStatusFilter('All');
                          }}
                          className="mt-2 text-xs font-medium text-indigo-600 hover:text-indigo-800 underline cursor-pointer"
                        >
                          Clear filters
                        </button>
                      </div>
                    )}
                  </td>
                </tr>
              ) : (
                filtered.map((item) => (
                  <tr key={item.id} className="hover:bg-slate-50/50">
                    <td className="py-3 px-4 font-mono text-[11px] text-slate-500 whitespace-nowrap">
                      {item.timestamp}
                    </td>
                    <td className="py-3 px-4 font-semibold text-slate-800 whitespace-nowrap">
                      {item.datasetName}
                    </td>
                    <td className="py-3 px-4 text-slate-800 font-medium max-w-xs truncate" title={item.naturalPrompt}>
                      "{item.naturalPrompt}"
                    </td>
                    <td className="py-3 px-4 font-mono text-[11px] text-slate-600 max-w-sm truncate">
                      <div className="flex items-center gap-1.5">
                        <span className="truncate">{item.generatedSql}</span>
                        <button
                          onClick={() => handleCopySql(item.id, item.generatedSql)}
                          className="text-slate-400 hover:text-indigo-600 cursor-pointer p-0.5"
                          title="Copy SQL"
                        >
                          {copiedId === item.id ? (
                            <Check className="w-3.5 h-3.5 text-emerald-600" />
                          ) : (
                            <Copy className="w-3.5 h-3.5" />
                          )}
                        </button>
                      </div>
                    </td>
                    <td className="py-3 px-4 font-mono text-slate-600">
                      {item.rowsReturned}
                    </td>
                    <td className="py-3 px-4 font-mono text-[11px] text-slate-500">
                      {item.executionTimeMs}ms
                    </td>
                    <td className="py-3 px-4 whitespace-nowrap">
                      <span
                        className={`px-2 py-0.5 rounded text-[10px] font-semibold ${
                          item.status === 'SUCCESS'
                            ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                            : item.status === 'SQL_REJECTED'
                            ? 'bg-red-50 text-red-700 border border-red-200'
                            : 'bg-amber-50 text-amber-700 border border-amber-200'
                        }`}
                      >
                        {item.status}
                      </span>
                    </td>
                    <td className="py-3 px-4 text-right font-mono font-bold whitespace-nowrap">
                      {item.creditsCharged > 0 ? (
                        <span className="text-red-600">-{item.creditsCharged} cr</span>
                      ) : (
                        <span className="text-slate-400">0 cr</span>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination Controls */}
        {totalCount > pageSize && (
          <div className="flex items-center justify-between px-4 py-3 border-t border-slate-200 bg-slate-50">
            <div className="text-xs text-slate-500">
              Showing <span className="font-medium">{(page - 1) * pageSize + 1}</span> to{' '}
              <span className="font-medium">{Math.min(page * pageSize, totalCount)}</span> of{' '}
              <span className="font-medium">{totalCount}</span> queries
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => fetchHistory(page - 1)}
                disabled={page <= 1 || isLoading}
                className="px-2.5 py-1 text-xs border border-slate-200 rounded-md bg-white hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
              >
                Previous
              </button>
              <span className="text-xs text-slate-600 font-medium">
                Page {page} of {Math.ceil(totalCount / pageSize) || 1}
              </span>
              <button
                onClick={() => fetchHistory(page + 1)}
                disabled={!hasMore || page >= Math.ceil(totalCount / pageSize) || isLoading}
                className="px-2.5 py-1 text-xs border border-slate-200 rounded-md bg-white hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
              >
                Next
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
