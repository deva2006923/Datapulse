import React, { useState, useEffect } from 'react';
import {
  Search,
  Terminal,
  Copy,
  Download,
  BarChart3,
  Table,
  Check,
  AlertTriangle,
  Clock,
  Coins,
  Lock,
  Unlock,
  ChevronDown,
  ChevronUp,
  Info,
  CheckCircle2,
} from 'lucide-react';
import { AppDataset, UserAccount, QueryHistoryItem } from '../types';

interface QueryWorkspaceViewProps {
  currentUser: UserAccount;
  datasets: AppDataset[];
  selectedDatasetId?: string;
  onSelectDataset: (id: string) => void;
  initialPrompt?: string;
  onExecuteQuery: (
    dataset: AppDataset,
    prompt: string,
    onSuccess: (result: {
      generatedSql: string;
      rows: Record<string, any>[];
      executionMs: number;
      chargedCredits: number;
      explanation: string;
    }) => void,
    onError: (err: {
      type: 'SQL_REJECTED' | 'INSUFFICIENT_CREDITS';
      message: string;
      shortfall?: number;
    }) => void
  ) => void;
  sessionHistory: QueryHistoryItem[];
}

export const QueryWorkspaceView: React.FC<QueryWorkspaceViewProps> = ({
  currentUser,
  datasets,
  selectedDatasetId,
  onSelectDataset,
  initialPrompt = '',
  onExecuteQuery,
  sessionHistory,
}) => {
  const activeDataset =
    datasets.find((d) => d.id === selectedDatasetId) || datasets[0] || null;

  const [prompt, setPrompt] = useState(initialPrompt || (activeDataset?.sampleQueries[0] || ''));
  const [generatedSql, setGeneratedSql] = useState<string>('');
  const [results, setResults] = useState<Record<string, any>[] | null>(null);
  const [columns, setColumns] = useState<string[]>([]);
  const [viewMode, setViewMode] = useState<'table' | 'chart'>('table');
  const [isExecuting, setIsExecuting] = useState(false);
  const [executionTime, setExecutionTime] = useState<number | null>(null);
  const [copiedSql, setCopiedSql] = useState(false);
  const [isSqlCollapsed, setIsSqlCollapsed] = useState(true);
  const [queryExplanation, setQueryExplanation] = useState<string>('');
  const [lastChargedCredits, setLastChargedCredits] = useState<number | null>(null);
  const [errorBanner, setErrorBanner] = useState<{
    type: 'SQL_REJECTED' | 'INSUFFICIENT_CREDITS';
    message: string;
    shortfall?: number;
  } | null>(null);

  useEffect(() => {
    if (initialPrompt) {
      setPrompt(initialPrompt);
    } else if (activeDataset?.sampleQueries?.length) {
      setPrompt(activeDataset.sampleQueries[0]);
    }
  }, [selectedDatasetId, initialPrompt]);

  if (!activeDataset) {
    return (
      <div className="bg-white border border-slate-200 rounded-xl p-8 text-center text-slate-500">
        No dataset available. Please upload or select a dataset.
      </div>
    );
  }

  const isOwner = activeDataset.authorId === currentUser.id;
  const isUnlocked = isOwner || activeDataset.unlockedBy.includes(currentUser.id);
  const unlockCost = activeDataset.cost || 20;
  const isShortfall = !isUnlocked && currentUser.credits < unlockCost;
  const shortfallAmount = isShortfall ? unlockCost - currentUser.credits : 0;

  const handleCopySql = () => {
    if (!generatedSql) return;
    navigator.clipboard.writeText(generatedSql);
    setCopiedSql(true);
    setTimeout(() => setCopiedSql(false), 2000);
  };

  const handleRun = () => {
    if (!prompt.trim() || isExecuting || isShortfall) return;
    setIsExecuting(true);
    setErrorBanner(null);

    onExecuteQuery(
      activeDataset,
      prompt,
      (res) => {
        setIsExecuting(false);
        setGeneratedSql(res.generatedSql);
        setResults(res.rows);
        setExecutionTime(res.executionMs);
        setLastChargedCredits(res.chargedCredits);
        setQueryExplanation(res.explanation);
        if (res.rows.length > 0) {
          setColumns(Object.keys(res.rows[0]));
        }
      },
      (err) => {
        setIsExecuting(false);
        setErrorBanner(err);
      }
    );
  };

  const handleExportCsv = () => {
    if (!results || results.length === 0) return;
    const headers = columns.join(',');
    const rows = results.map((r) => columns.map((col) => JSON.stringify(r[col] ?? '')).join(','));
    const csvContent = [headers, ...rows].join('\n');
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', `${activeDataset.name.replace(/\.[^/.]+$/, '')}_query_results.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  return (
    <div className="space-y-6">
      {/* Workspace Header & Dataset Selector */}
      <div className="bg-white border border-slate-200 rounded-xl p-6 shadow-sm">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <span className="text-xs font-semibold text-indigo-600 uppercase tracking-wide">
              Natural Language SQL Workspace
            </span>
            <h1 className="text-2xl font-extrabold text-slate-900 tracking-tight">
              Query Workspace
            </h1>
            <p className="text-xs text-slate-500 mt-0.5">
              Ask questions in plain English. Queries are converted to read-only sandboxed SQL.
            </p>
          </div>

          {/* Dataset Selector Dropdown */}
          <div className="flex items-center gap-3">
            <label className="text-xs font-medium text-slate-500 whitespace-nowrap">
              Active Dataset:
            </label>
            <select
              value={activeDataset.id}
              onChange={(e) => onSelectDataset(e.target.value)}
              className="bg-slate-50 border border-slate-300 rounded-lg px-3 py-1.5 text-xs font-semibold text-slate-800 outline-none focus:border-indigo-500 max-w-xs truncate"
            >
              {datasets.filter((d) => d.status !== 'REJECTED').map((d) => (
                <option key={d.id} value={d.id}>
                  {d.title} ({d.format.toUpperCase()})
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Dataset Status & Credit Summary Bar */}
        <div className="mt-4 pt-4 border-t border-slate-100 flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs">
          <div className="flex items-center gap-2">
            <span className="font-semibold text-slate-700">{activeDataset.title}</span>
            <span className="text-slate-400">•</span>
            <span className="font-mono text-slate-500">{activeDataset.rowCount.toLocaleString()} rows</span>
            <span className="text-slate-400">•</span>
            {isOwner ? (
              <span className="text-emerald-700 bg-emerald-50 border border-emerald-200 px-2 py-0.5 rounded font-semibold">
                Owner Access (Free)
              </span>
            ) : isUnlocked ? (
              <span className="text-indigo-700 bg-indigo-50 border border-indigo-200 px-2 py-0.5 rounded font-semibold flex items-center gap-1">
                <Unlock className="w-3 h-3" /> Unlocked
              </span>
            ) : (
              <span className="text-amber-800 bg-amber-50 border border-amber-200 px-2 py-0.5 rounded font-semibold flex items-center gap-1">
                <Lock className="w-3 h-3" /> {unlockCost} cr unlock
              </span>
            )}
          </div>

          <div className="flex items-center gap-2 text-slate-600">
            <span>Credit balance:</span>
            <span className="font-mono font-bold text-emerald-600">{currentUser.credits} cr</span>
          </div>
        </div>
      </div>

      {/* Notice for Unlocked vs Locked Datasets (Required in Item 9) */}
      {!isUnlocked && (
        <div className="bg-amber-50 border border-amber-300 rounded-xl p-4 shadow-xs flex items-start gap-3">
          <Info className="w-5 h-5 text-amber-700 shrink-0 mt-0.5" />
          <div className="text-xs text-amber-900 space-y-1">
            <span className="font-bold block">
              Running this query will unlock the dataset for {unlockCost} credits. Balance: {currentUser.credits}
            </span>
            <p className="text-amber-800">
              You are charged once only after your query executes successfully. The original contributor will earn +20 credits.
            </p>
            {isShortfall && (
              <p className="text-red-700 font-bold pt-1">
                Shortfall: You need {shortfallAmount} more credits to unlock this dataset (Required: {unlockCost}, Balance: {currentUser.credits}). Run button is disabled.
              </p>
            )}
          </div>
        </div>
      )}

      {/* Query Input Box */}
      <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm space-y-4">
        <div>
          <label className="text-xs font-semibold text-slate-700 block mb-1.5">
            Natural Language Question (Plain English)
          </label>
          <div className="relative">
            <input
              type="text"
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && !isShortfall && handleRun()}
              placeholder='e.g. "Show top 10 patients by cholesterol" or "Show high churn customers with monthly spend over 60"'
              className="w-full bg-slate-50 border border-slate-300 rounded-xl pl-4 pr-32 py-3 text-sm text-slate-900 placeholder-slate-400 focus:outline-none focus:border-indigo-500 shadow-xs"
            />
            <button
              onClick={handleRun}
              disabled={isExecuting || !prompt.trim() || isShortfall}
              className="absolute right-2 top-2 px-5 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-700 disabled:opacity-40 disabled:cursor-not-allowed text-white font-semibold text-xs shadow-xs transition-colors cursor-pointer flex items-center gap-1.5"
            >
              {isExecuting ? (
                <>
                  <Clock className="w-3.5 h-3.5 animate-spin" />
                  <span>Executing...</span>
                </>
              ) : (
                <>
                  <Search className="w-3.5 h-3.5" />
                  <span>Run Query</span>
                </>
              )}
            </button>
          </div>
        </div>

        {/* Suggested Queries */}
        <div className="flex flex-wrap items-center gap-2 pt-1">
          <span className="text-[11px] font-medium text-slate-400">Suggestions:</span>
          {activeDataset.sampleQueries.map((q, idx) => (
            <button
              key={idx}
              onClick={() => setPrompt(q)}
              className="text-[11px] px-2.5 py-1 rounded bg-slate-100 hover:bg-indigo-50 hover:text-indigo-700 text-slate-600 border border-slate-200 transition-colors cursor-pointer"
            >
              "{q}"
            </button>
          ))}
          {/* Test forbidden mutation */}
          <button
            onClick={() => setPrompt('DROP TABLE customers CASCADE;')}
            className="text-[11px] px-2.5 py-1 rounded bg-red-50 hover:bg-red-100 text-red-700 border border-red-200 transition-colors cursor-pointer"
            title="Tests safety policy: SQL_REJECTED"
          >
            "DROP TABLE customers;" (Test Rejection)
          </button>
        </div>
      </div>

      {/* Error Banners */}
      {errorBanner && (
        <div
          className={`border rounded-xl p-4 shadow-xs flex items-start gap-3 ${
            errorBanner.type === 'INSUFFICIENT_CREDITS'
              ? 'bg-amber-50 border-amber-300 text-amber-900'
              : 'bg-red-50 border-red-300 text-red-900'
          }`}
        >
          <AlertTriangle className="w-5 h-5 shrink-0 mt-0.5" />
          <div className="space-y-1">
            <h4 className="text-xs font-bold uppercase tracking-wider">
              {errorBanner.type}
            </h4>
            <p className="text-xs leading-relaxed">{errorBanner.message}</p>
            {errorBanner.shortfall !== undefined && (
              <p className="text-xs font-semibold mt-1">
                Shortfall: You need <span className="font-mono text-red-700">{errorBanner.shortfall} more credits</span> to unlock this dataset.
              </p>
            )}
            <p className="text-[11px] text-slate-500 mt-1">
              No credits have been charged for this request.
            </p>
          </div>
        </div>
      )}

      {/* Post-Query Status: Credits Charged / New Balance Banner (Required in Item 9) */}
      {results && lastChargedCredits !== null && (
        <div className="p-4 rounded-xl bg-indigo-50 border border-indigo-200 flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs text-indigo-900 shadow-xs">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
            <span className="font-semibold">
              Query succeeded. Credits charged: <strong className="font-mono">{lastChargedCredits} credits</strong> • New balance: <strong className="font-mono text-emerald-700">{currentUser.credits} credits</strong>
            </span>
          </div>
          {lastChargedCredits > 0 && (
            <span className="text-emerald-700 bg-emerald-100/70 border border-emerald-300 px-2 py-0.5 rounded font-mono font-bold self-start sm:self-auto">
              Unlocked & Royalty Dispatched (+20 to author)
            </span>
          )}
        </div>
      )}

      {/* Query Explanation (Required in Item 9) */}
      {results && queryExplanation && (
        <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-sm text-xs space-y-1">
          <span className="font-bold text-slate-700 uppercase tracking-wide text-[11px] block">
            Query Explanation
          </span>
          <p className="text-slate-600 leading-relaxed">{queryExplanation}</p>
        </div>
      )}

      {/* Collapsible "View generated SQL" with Copy Button (Required in Item 9) */}
      {generatedSql && (
        <div className="bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden">
          <div
            onClick={() => setIsSqlCollapsed(!isSqlCollapsed)}
            className="p-4 flex items-center justify-between cursor-pointer hover:bg-slate-50 transition-colors select-none"
          >
            <div className="flex items-center gap-2">
              <Terminal className="w-4 h-4 text-indigo-600" />
              <span className="text-xs font-bold text-slate-900">
                View generated SQL
              </span>
            </div>

            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  handleCopySql();
                }}
                className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-medium transition-colors cursor-pointer"
              >
                {copiedSql ? (
                  <>
                    <Check className="w-3.5 h-3.5 text-emerald-600" />
                    <span className="text-emerald-700 font-semibold">Copied!</span>
                  </>
                ) : (
                  <>
                    <Copy className="w-3.5 h-3.5 text-slate-500" />
                    <span>Copy SQL</span>
                  </>
                )}
              </button>
              {isSqlCollapsed ? (
                <ChevronDown className="w-4 h-4 text-slate-400" />
              ) : (
                <ChevronUp className="w-4 h-4 text-slate-400" />
              )}
            </div>
          </div>

          {!isSqlCollapsed && (
            <div className="p-4 pt-0 border-t border-slate-100">
              <pre className="bg-slate-900 text-slate-100 rounded-lg p-3.5 text-xs font-mono overflow-x-auto leading-relaxed border border-slate-800">
                {generatedSql}
              </pre>
            </div>
          )}
        </div>
      )}

      {/* Query Result Workspace (Table / Chart Toggle & CSV Export) */}
      {results && results.length > 0 && (
        <div className="bg-white border border-slate-200 rounded-xl overflow-hidden shadow-sm space-y-0">
          {/* Result Toolbar with row count and execution time */}
          <div className="p-4 border-b border-slate-200 flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-slate-50/50">
            <div className="flex items-center gap-3">
              <span className="text-xs font-bold text-slate-900">
                {results.length} rows returned
              </span>
              {executionTime !== null && (
                <span className="text-[11px] font-mono text-emerald-600 bg-emerald-50 border border-emerald-200 px-2 py-0.5 rounded">
                  {executionTime}ms execution time
                </span>
              )}
            </div>

            <div className="flex items-center gap-2">
              {/* Toggle Table vs Chart */}
              <div className="flex items-center bg-white border border-slate-200 rounded-lg p-0.5">
                <button
                  onClick={() => setViewMode('table')}
                  className={`px-3 py-1 rounded text-xs font-medium cursor-pointer transition-colors flex items-center gap-1.5 ${
                    viewMode === 'table'
                      ? 'bg-indigo-600 text-white shadow-xs'
                      : 'text-slate-600 hover:text-slate-900'
                  }`}
                >
                  <Table className="w-3.5 h-3.5" />
                  <span>Table</span>
                </button>
                <button
                  onClick={() => setViewMode('chart')}
                  className={`px-3 py-1 rounded text-xs font-medium cursor-pointer transition-colors flex items-center gap-1.5 ${
                    viewMode === 'chart'
                      ? 'bg-indigo-600 text-white shadow-xs'
                      : 'text-slate-600 hover:text-slate-900'
                  }`}
                >
                  <BarChart3 className="w-3.5 h-3.5" />
                  <span>Chart</span>
                </button>
              </div>

              {/* Export to CSV */}
              <button
                onClick={handleExportCsv}
                className="px-3 py-1.5 rounded-lg bg-white border border-slate-300 hover:bg-slate-50 text-slate-700 text-xs font-medium transition-colors shadow-xs cursor-pointer flex items-center gap-1.5"
              >
                <Download className="w-3.5 h-3.5 text-slate-500" />
                <span>Export CSV</span>
              </button>
            </div>
          </div>

          {/* Table View */}
          {viewMode === 'table' ? (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs font-mono">
                <thead className="bg-slate-50 text-slate-600 border-b border-slate-200 text-[11px] font-sans">
                  <tr>
                    {columns.map((col, idx) => (
                      <th key={idx} className="py-2.5 px-4 font-semibold">
                        {col}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 text-slate-800">
                  {results.map((row, rIdx) => (
                    <tr key={rIdx} className="hover:bg-slate-50/70">
                      {columns.map((col, cIdx) => (
                        <td key={cIdx} className="py-2.5 px-4">
                          {row[col] !== undefined ? String(row[col]) : '—'}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            /* Bar Chart View */
            <div className="p-6 space-y-4">
              <div className="text-xs text-slate-500 font-medium">
                Distribution breakdown across numeric attributes:
              </div>
              <div className="space-y-3">
                {results.slice(0, 8).map((row, idx) => {
                  const label = String(row[columns[0]] || `Row ${idx + 1}`);
                  const numCol = columns.find((c) => typeof row[c] === 'number') || columns[1];
                  const val = typeof row[numCol] === 'number' ? row[numCol] : 50;
                  const maxVal = Math.max(...results.map((r) => (typeof r[numCol] === 'number' ? r[numCol] : 50))) || 100;
                  const pct = Math.min(100, Math.max(10, Math.round((val / maxVal) * 100)));

                  return (
                    <div key={idx} className="space-y-1">
                      <div className="flex justify-between text-xs">
                        <span className="font-mono text-slate-700">{label}</span>
                        <span className="font-mono font-semibold text-slate-900">{val}</span>
                      </div>
                      <div className="w-full bg-slate-100 rounded-full h-3">
                        <div
                          className="bg-indigo-600 h-3 rounded-full"
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Session History */}
      <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-xs font-bold text-slate-900 uppercase tracking-wider">
            Workspace Session History
          </h3>
          <span className="text-[11px] text-slate-400">
            {sessionHistory.length} queries this session
          </span>
        </div>

        {sessionHistory.length === 0 ? (
          <p className="text-xs text-slate-400 italic">No queries run in this session yet.</p>
        ) : (
          <div className="divide-y divide-slate-100">
            {sessionHistory.slice(0, 5).map((q) => (
              <div key={q.id} className="py-2.5 flex items-center justify-between gap-4 text-xs">
                <div className="space-y-0.5 truncate">
                  <div className="font-medium text-slate-800 truncate">"{q.naturalPrompt}"</div>
                  <div className="text-[11px] text-slate-400 font-mono truncate">
                    {q.datasetName} • {q.timestamp}
                  </div>
                </div>

                <div className="flex items-center gap-2 shrink-0">
                  <span
                    className={`px-2 py-0.5 rounded text-[10px] font-semibold ${
                      q.status === 'SUCCESS'
                        ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                        : q.status === 'SQL_REJECTED'
                        ? 'bg-red-50 text-red-700 border border-red-200'
                        : 'bg-amber-50 text-amber-700 border border-amber-200'
                    }`}
                  >
                    {q.status}
                  </span>
                  <span className="font-mono text-slate-500">
                    {q.creditsCharged > 0 ? `-${q.creditsCharged} cr` : '0 cr'}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
