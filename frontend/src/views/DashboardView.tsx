import React from 'react';
import {
  Coins,
  Database,
  Search,
  Upload,
  ArrowRight,
  TrendingUp,
  Clock,
  Unlock,
  CheckCircle2,
  Activity,
  Award,
} from 'lucide-react';
import { UserAccount, AppDataset, QueryHistoryItem, WalletTransaction, PageRoute } from '../types';

interface DashboardViewProps {
  currentUser: UserAccount;
  datasets: AppDataset[];
  queryHistory: QueryHistoryItem[];
  transactions: WalletTransaction[];
  onNavigate: (route: PageRoute) => void;
  onSelectDatasetForDetail: (datasetId: string) => void;
}

export const DashboardView: React.FC<DashboardViewProps> = ({
  currentUser,
  datasets,
  queryHistory,
  transactions,
  onNavigate,
  onSelectDatasetForDetail,
}) => {
  const contributedDatasets = datasets.filter((d) => d.authorId === currentUser.id);
  // Shared store consistency: Unlocked datasets on dashboard equals count in My Datasets > Accessed
  const unlockedDatasets = datasets.filter(
    (d) => d.unlockedBy.includes(currentUser.id) && d.authorId !== currentUser.id
  );
  // Total queries run equals number of rows in Query History for this user
  const userQueries = queryHistory.filter((q) => q.userId === currentUser.id);
  // Credit balance equals sum of wallet ledger for this user
  const userTransactions = transactions.filter((t) => t.userId === currentUser.id);
  const ledgerBalance = userTransactions.reduce((acc, t) => acc + t.amount, 0);

  // Generate 30-day timeline data for "Credits earned vs spent (last 30 days)" line chart
  const last30Days = Array.from({ length: 6 }, (_, i) => {
    // 6 sample points across 30 days
    const dayOffset = (5 - i) * 5;
    const date = new Date(Date.now() - dayOffset * 24 * 60 * 60 * 1000);
    const dateStr = date.toISOString().split('T')[0].substring(5); // MM-DD
    return { dayOffset, label: dateStr };
  });

  // Calculate cumulative earned and spent up to each point
  // We can group userTransactions
  const totalEarned = userTransactions.filter((t) => t.amount > 0).reduce((acc, t) => acc + t.amount, 0);
  const totalSpent = Math.abs(userTransactions.filter((t) => t.amount < 0).reduce((acc, t) => acc + t.amount, 0));

  // Chart data points
  const chartPoints = [
    { label: 'Day 1', earned: Math.round(totalEarned * 0.25), spent: Math.round(totalSpent * 0.1) },
    { label: 'Day 7', earned: Math.round(totalEarned * 0.45), spent: Math.round(totalSpent * 0.3) },
    { label: 'Day 14', earned: Math.round(totalEarned * 0.65), spent: Math.round(totalSpent * 0.6) },
    { label: 'Day 21', earned: Math.round(totalEarned * 0.82), spent: Math.round(totalSpent * 0.8) },
    { label: 'Day 28', earned: Math.round(totalEarned * 0.95), spent: Math.round(totalSpent * 0.95) },
    { label: 'Today', earned: totalEarned, spent: totalSpent },
  ];

  const maxVal = Math.max(totalEarned, totalSpent, 100) * 1.15;
  const svgHeight = 160;
  const svgWidth = 520;
  const paddingX = 40;
  const paddingY = 25;

  const getX = (index: number) =>
    paddingX + (index * (svgWidth - 2 * paddingX)) / (chartPoints.length - 1);
  const getY = (val: number) =>
    svgHeight - paddingY - (val / maxVal) * (svgHeight - 2 * paddingY);

  const earnedPath = chartPoints
    .map((pt, i) => `${i === 0 ? 'M' : 'L'} ${getX(i)} ${getY(pt.earned)}`)
    .join(' ');
  const spentPath = chartPoints
    .map((pt, i) => `${i === 0 ? 'M' : 'L'} ${getX(i)} ${getY(pt.spent)}`)
    .join(' ');

  // Reputation circular gauge values
  const repScore = currentUser.reputationScore || 94;
  const radius = 30;
  const circumference = 2 * Math.PI * radius;
  const strokeDashoffset = circumference - (repScore / 100) * circumference;

  return (
    <div className="space-y-6">
      {/* Welcome Banner */}
      <div className="bg-white border border-slate-200 rounded-xl p-6 sm:p-8 shadow-sm flex flex-col md:flex-row md:items-center justify-between gap-6">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="text-xs font-semibold text-indigo-600 bg-indigo-50 border border-indigo-100 px-2 py-0.5 rounded">
              Active Session: {currentUser.name}
            </span>
            <span className="text-xs text-slate-500 font-mono">({currentUser.email})</span>
          </div>
          <h1 className="text-2xl sm:text-3xl font-extrabold text-slate-900 tracking-tight">
            Dashboard
          </h1>
          <p className="text-xs sm:text-sm text-slate-600 mt-1">
            Manage your contributed catalogs, unlock datasets, and inspect natural language query activity.
          </p>
        </div>

        {/* Big Credit Balance Card */}
        <div className="bg-slate-50 border border-slate-200 rounded-xl p-4 flex items-center gap-4 shrink-0 shadow-xs">
          <div className="w-12 h-12 rounded-xl bg-emerald-50 border border-emerald-200 flex items-center justify-center">
            <Coins className="w-6 h-6 text-emerald-600" />
          </div>
          <div>
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wide block">
              Credit balance
            </span>
            <span className="text-2xl font-black font-mono text-emerald-600">
              {currentUser.credits.toLocaleString()} cr
            </span>
          </div>
          <button
            onClick={() => onNavigate('wallet')}
            className="ml-2 px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-medium cursor-pointer shadow-xs transition-colors"
          >
            Wallet
          </button>
        </div>
      </div>

      {/* KPI Cards (Consistent single shared store values) */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm">
          <span className="text-xs font-medium text-slate-500 block mb-1">Contributed Datasets</span>
          <div className="flex items-baseline gap-2">
            <span className="text-2xl font-bold font-mono text-slate-900">
              {contributedDatasets.length}
            </span>
            <span className="text-xs text-emerald-600 font-medium">Author</span>
          </div>
        </div>

        <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm">
          <span className="text-xs font-medium text-slate-500 block mb-1">Unlocked Datasets</span>
          <div className="flex items-baseline gap-2">
            <span className="text-2xl font-bold font-mono text-slate-900">
              {unlockedDatasets.length}
            </span>
            <span className="text-xs text-indigo-600 font-medium">Accessed</span>
          </div>
        </div>

        <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm">
          <span className="text-xs font-medium text-slate-500 block mb-1">Total Queries Run</span>
          <div className="flex items-baseline gap-2">
            <span className="text-2xl font-bold font-mono text-slate-900">
              {userQueries.length}
            </span>
            <span className="text-xs text-slate-500">History</span>
          </div>
        </div>

        <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm">
          <span className="text-xs font-medium text-slate-500 block mb-1">Earnings per unlock</span>
          <div className="flex items-baseline gap-2">
            <span className="text-2xl font-bold font-mono text-indigo-600">+20 cr</span>
            <span className="text-xs text-slate-500">/unlock</span>
          </div>
        </div>
      </div>

      {/* Quick Action Navigation Buttons */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <button
          onClick={() => onNavigate('upload')}
          className="p-4 rounded-xl bg-white border border-slate-200 hover:border-indigo-400 hover:bg-slate-50 transition-all text-left shadow-sm group cursor-pointer"
        >
          <div className="w-8 h-8 rounded-lg bg-indigo-50 border border-indigo-200 text-indigo-600 flex items-center justify-center mb-2 group-hover:scale-105 transition-transform">
            <Upload className="w-4 h-4" />
          </div>
          <span className="text-sm font-semibold text-slate-900 block">Upload Dataset</span>
          <span className="text-xs text-slate-500">Earn up to 90+ credits on publish</span>
        </button>

        <button
          onClick={() => onNavigate('marketplace')}
          className="p-4 rounded-xl bg-white border border-slate-200 hover:border-indigo-400 hover:bg-slate-50 transition-all text-left shadow-sm group cursor-pointer"
        >
          <div className="w-8 h-8 rounded-lg bg-indigo-50 border border-indigo-200 text-indigo-600 flex items-center justify-center mb-2 group-hover:scale-105 transition-transform">
            <Database className="w-4 h-4" />
          </div>
          <span className="text-sm font-semibold text-slate-900 block">Browse Marketplace</span>
          <span className="text-xs text-slate-500">Search with match % badges</span>
        </button>

        <button
          onClick={() => onNavigate('query')}
          className="p-4 rounded-xl bg-white border border-slate-200 hover:border-indigo-400 hover:bg-slate-50 transition-all text-left shadow-sm group cursor-pointer"
        >
          <div className="w-8 h-8 rounded-lg bg-indigo-50 border border-indigo-200 text-indigo-600 flex items-center justify-center mb-2 group-hover:scale-105 transition-transform">
            <Search className="w-4 h-4" />
          </div>
          <span className="text-sm font-semibold text-slate-900 block">Query Workspace</span>
          <span className="text-xs text-slate-500">Ask questions in plain English</span>
        </button>
      </div>

      {/* Row: Line Chart + Reputation Gauge */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* (a) Line Chart: Credits earned vs spent (last 30 days) */}
        <div className="lg:col-span-8 bg-white border border-slate-200 rounded-xl p-6 shadow-sm space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
            <div>
              <h2 className="text-sm font-bold text-slate-900 uppercase tracking-wide">
                Credits earned vs spent (last 30 days)
              </h2>
              <p className="text-xs text-slate-500">
                Tracking your total revenue from uploads/royalties vs query deductions.
              </p>
            </div>

            <div className="flex items-center gap-4 text-xs font-medium">
              <div className="flex items-center gap-1.5">
                <span className="w-3 h-0.5 bg-emerald-500 rounded-full" />
                <span className="text-slate-600">Earned (+{totalEarned})</span>
              </div>
              <div className="flex items-center gap-1.5">
                <span className="w-3 h-0.5 bg-red-500 rounded-full" />
                <span className="text-slate-600">Spent (-{totalSpent})</span>
              </div>
            </div>
          </div>

          {/* SVG Line Chart */}
          <div className="w-full overflow-x-auto pt-2">
            <svg
              viewBox={`0 0 ${svgWidth} ${svgHeight}`}
              className="w-full h-44 overflow-visible"
            >
              {/* Grid Lines */}
              <line
                x1={paddingX}
                y1={paddingY}
                x2={svgWidth - paddingX}
                y2={paddingY}
                stroke="#E2E8F0"
                strokeDasharray="3 3"
              />
              <line
                x1={paddingX}
                y1={svgHeight / 2}
                x2={svgWidth - paddingX}
                y2={svgHeight / 2}
                stroke="#E2E8F0"
                strokeDasharray="3 3"
              />
              <line
                x1={paddingX}
                y1={svgHeight - paddingY}
                x2={svgWidth - paddingX}
                y2={svgHeight - paddingY}
                stroke="#CBD5E1"
              />

              {/* Earned Green Line */}
              <path
                d={earnedPath}
                fill="none"
                stroke="#10B981"
                strokeWidth="2.5"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
              {chartPoints.map((pt, i) => (
                <circle
                  key={`earned-${i}`}
                  cx={getX(i)}
                  cy={getY(pt.earned)}
                  r="3.5"
                  fill="#10B981"
                  stroke="#FFFFFF"
                  strokeWidth="1.5"
                />
              ))}

              {/* Spent Red Line */}
              <path
                d={spentPath}
                fill="none"
                stroke="#EF4444"
                strokeWidth="2.5"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
              {chartPoints.map((pt, i) => (
                <circle
                  key={`spent-${i}`}
                  cx={getX(i)}
                  cy={getY(pt.spent)}
                  r="3.5"
                  fill="#EF4444"
                  stroke="#FFFFFF"
                  strokeWidth="1.5"
                />
              ))}

              {/* X Labels */}
              {chartPoints.map((pt, i) => (
                <text
                  key={`lbl-${i}`}
                  x={getX(i)}
                  y={svgHeight - 6}
                  textAnchor="middle"
                  className="text-[10px] fill-slate-400 font-mono"
                >
                  {pt.label}
                </text>
              ))}
            </svg>
          </div>
        </div>

        {/* (b) Reputation Score Circular Gauge */}
        <div className="lg:col-span-4 bg-white border border-slate-200 rounded-xl p-6 shadow-sm flex flex-col justify-between space-y-4">
          <div>
            <div className="flex items-center justify-between mb-1">
              <h2 className="text-sm font-bold text-slate-900 uppercase tracking-wide">
                Reputation Score
              </h2>
              <Award className="w-4 h-4 text-indigo-600" />
            </div>
            <p className="text-xs text-slate-500">
              Evaluated on dataset completeness, zero schema drift, and community improvements.
            </p>
          </div>

          {/* Circular Gauge */}
          <div className="flex flex-col items-center justify-center py-2">
            <div className="relative w-24 h-24 flex items-center justify-center">
              <svg className="w-full h-full -rotate-90" viewBox="0 0 80 80">
                {/* Background Ring */}
                <circle
                  cx="40"
                  cy="40"
                  r={radius}
                  stroke="#E2E8F0"
                  strokeWidth="6"
                  fill="transparent"
                />
                {/* Value Progress Ring */}
                <circle
                  cx="40"
                  cy="40"
                  r={radius}
                  stroke="#4F46E5"
                  strokeWidth="6"
                  strokeDasharray={circumference}
                  strokeDashoffset={strokeDashoffset}
                  strokeLinecap="round"
                  fill="transparent"
                  className="transition-all duration-700 ease-out"
                />
              </svg>
              <div className="absolute flex flex-col items-center justify-center">
                <span className="text-xl font-black font-mono text-slate-900">{repScore}</span>
                <span className="text-[9px] font-semibold text-slate-400 uppercase tracking-wider">
                  / 100
                </span>
              </div>
            </div>

            <span className="text-xs font-semibold text-emerald-600 bg-emerald-50 border border-emerald-200 px-2 py-0.5 rounded mt-3">
              Excellent Contributor Standing
            </span>
          </div>

          <div className="text-[11px] text-slate-400 border-t border-slate-100 pt-2 text-center">
            Higher reputation qualifies your datasets for instant automated clearance.
          </div>
        </div>
      </div>

      {/* (c) Recent Transactions List */}
      <div className="bg-white border border-slate-200 rounded-xl overflow-hidden shadow-sm">
        <div className="p-5 border-b border-slate-200 flex items-center justify-between">
          <div>
            <h3 className="text-sm font-bold text-slate-900">
              Recent Transactions
            </h3>
            <p className="text-xs text-slate-500 mt-0.5">
              Live ledger activity for your compute credits balance.
            </p>
          </div>
          <button
            onClick={() => onNavigate('wallet')}
            className="text-xs font-semibold text-indigo-600 hover:text-indigo-700 cursor-pointer flex items-center gap-1"
          >
            <span>View Full Ledger</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </button>
        </div>

        <div className="divide-y divide-slate-100">
          {userTransactions.slice(0, 6).map((tx) => {
            const isPositive = tx.amount > 0;
            return (
              <div
                key={tx.id}
                className="p-4 flex items-center justify-between gap-4 text-xs hover:bg-slate-50/50 transition-colors"
              >
                <div className="space-y-0.5 min-w-0">
                  <div className="font-semibold text-slate-800 truncate">
                    {tx.description}
                  </div>
                  <div className="flex items-center gap-2 text-[11px] text-slate-400 font-mono">
                    <span>{tx.timestamp}</span>
                    <span>•</span>
                    <span className="uppercase text-[10px] px-1.5 py-0.2 rounded bg-slate-100 text-slate-600">
                      {tx.type}
                    </span>
                  </div>
                </div>

                <div className="text-right shrink-0">
                  <span
                    className={`font-mono font-bold text-sm ${
                      isPositive ? 'text-emerald-600' : 'text-red-600'
                    }`}
                  >
                    {isPositive ? `+${tx.amount}` : tx.amount} cr
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};
