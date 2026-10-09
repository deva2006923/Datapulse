import React, { useState } from 'react';
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
} from 'lucide-react';
import { QueryHistoryItem } from '../types';

interface QueryHistoryViewProps {
  history: QueryHistoryItem[];
  currentUserId: string;
}

export const QueryHistoryView: React.FC<QueryHistoryViewProps> = ({
  history,
  currentUserId,
}) => {
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('All');
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const handleCopySql = (id: string, sql: string) => {
    navigator.clipboard.writeText(sql);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const filtered = history.filter((item) => {
    const matchesSearch =
      item.naturalPrompt.toLowerCase().includes(searchTerm.toLowerCase()) ||
      item.datasetName.toLowerCase().includes(searchTerm.toLowerCase()) ||
      item.generatedSql.toLowerCase().includes(searchTerm.toLowerCase());

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

          <div className="text-xs font-mono text-slate-500 bg-slate-50 border border-slate-200 px-3 py-1.5 rounded-lg self-start sm:self-auto">
            {history.length} logged queries
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
              {filtered.length === 0 ? (
                <tr>
                  <td colSpan={8} className="py-8 text-center text-slate-400">
                    No query history records match your search filter.
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
                    <td className="py-3 px-4 text-slate-800 font-medium max-w-xs truncate">
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
      </div>
    </div>
  );
};
