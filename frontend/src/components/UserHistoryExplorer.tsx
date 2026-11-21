import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  User,
  Database,
  Search,
  Coins,
  Activity,
  CheckCircle2,
  AlertTriangle,
  ChevronDown,
  ChevronUp,
  RefreshCw,
  ShieldCheck,
  Clock,
  ArrowUpRight,
  ArrowDownRight,
  X,
  Copy,
  Check,
  Filter,
  Layers,
  GitCommit,
  Unlock,
  Shield,
  LogIn,
  ArrowUpDown,
  ExternalLink,
  Info,
} from 'lucide-react';
import {
  AdminUserDetail,
  AdminQueryItem,
  AdminDatasetItem,
  AdminTransactionItem,
  AdminTimelineItem,
} from '../types';
import { api } from '../services/api';
import {
  ErrorRetryBanner,
  PaginationFooter,
  TableSkeletonRows,
} from './admin/AdminCharts';

interface UserHistoryExplorerProps {
  userId: string;
  initialUserDetail?: AdminUserDetail | null;
  onClose: () => void;
  onInspectDataset?: (datasetId: string) => void;
  addToast?: (
    title: string,
    message: string,
    tone?: 'cyan' | 'rose' | 'amber' | 'emerald' | 'violet'
  ) => void;
}

type UserDetailTab = 'overview' | 'queries' | 'datasets' | 'transactions' | 'timeline';

const TX_TYPE_OPTIONS = [
  { value: 'all', label: 'All Types' },
  { value: 'bonus', label: 'Welcome Bonus' },
  { value: 'upload_reward', label: 'Basic Upload Reward' },
  { value: 'quality_reward', label: 'Quality Reward' },
  { value: 'improvement_reward', label: 'Improvement Reward' },
  { value: 'reward', label: 'Legacy Upload Reward' },
  { value: 'query_reward', label: 'Owner Query Reward' },
  { value: 'unlock_royalty', label: 'Unlock Royalty' },
  { value: 'query_fee', label: 'Query Fee' },
  { value: 'dataset_unlock', label: 'Dataset Unlock' },
  { value: 'redeem', label: 'Cash Redemption' },
  { value: 'refund', label: 'Refund' },
];

export const UserHistoryExplorer: React.FC<UserHistoryExplorerProps> = ({
  userId,
  initialUserDetail,
  onClose,
  onInspectDataset,
  addToast,
}) => {
  const [activeTab, setActiveTab] = useState<UserDetailTab>('overview');

  // User Profile
  const [userDetail, setUserDetail] = useState<AdminUserDetail | null>(initialUserDetail || null);
  const [isProfileLoading, setIsProfileLoading] = useState<boolean>(true);
  const [profileError, setProfileError] = useState<string | null>(null);

  // Queries Tab
  const [queries, setQueries] = useState<AdminQueryItem[]>([]);
  const [queriesTotal, setQueriesTotal] = useState<number>(0);
  const [queriesPage, setQueriesPage] = useState<number>(1);
  const [queriesLimit, setQueriesLimit] = useState<number>(10);
  const [queriesSearch, setQueriesSearch] = useState<string>('');
  const [queriesStatus, setQueriesStatus] = useState<string>('All');
  const [queriesStartDate, setQueriesStartDate] = useState<string>('');
  const [queriesEndDate, setQueriesEndDate] = useState<string>('');
  const [queriesSortOrder, setQueriesSortOrder] = useState<'desc' | 'asc'>('desc');
  const [isQueriesLoading, setIsQueriesLoading] = useState<boolean>(false);
  const [queriesError, setQueriesError] = useState<string | null>(null);
  const [expandedQueryId, setExpandedQueryId] = useState<string | null>(null);

  // Datasets Tab
  const [datasets, setDatasets] = useState<AdminDatasetItem[]>([]);
  const [datasetsTotal, setDatasetsTotal] = useState<number>(0);
  const [datasetsPage, setDatasetsPage] = useState<number>(1);
  const [datasetsLimit, setDatasetsLimit] = useState<number>(10);
  const [datasetsSearch, setDatasetsSearch] = useState<string>('');
  const [isDatasetsLoading, setIsDatasetsLoading] = useState<boolean>(false);
  const [datasetsError, setDatasetsError] = useState<string | null>(null);
  const [expandedDatasetId, setExpandedDatasetId] = useState<string | null>(null);

  // Transactions Tab
  const [transactions, setTransactions] = useState<AdminTransactionItem[]>([]);
  const [transactionsTotal, setTransactionsTotal] = useState<number>(0);
  const [transactionsPage, setTransactionsPage] = useState<number>(1);
  const [transactionsLimit, setTransactionsLimit] = useState<number>(10);
  const [transactionsSearch, setTransactionsSearch] = useState<string>('');
  const [transactionsType, setTransactionsType] = useState<string>('all');
  const [transactionsDirection, setTransactionsDirection] = useState<string>('all');
  const [transactionsStartDate, setTransactionsStartDate] = useState<string>('');
  const [transactionsEndDate, setTransactionsEndDate] = useState<string>('');
  const [transactionsSortOrder, setTransactionsSortOrder] = useState<'desc' | 'asc'>('desc');
  const [isTransactionsLoading, setIsTransactionsLoading] = useState<boolean>(false);
  const [transactionsError, setTransactionsError] = useState<string | null>(null);

  // Timeline Tab
  const [timelineItems, setTimelineItems] = useState<AdminTimelineItem[]>([]);
  const [timelineTotal, setTimelineTotal] = useState<number>(0);
  const [timelinePage, setTimelinePage] = useState<number>(1);
  const [timelineLimit, setTimelineLimit] = useState<number>(15);
  const [timelineType, setTimelineType] = useState<string>('all');
  const [timelineStatus, setTimelineStatus] = useState<string>('All');
  const [timelineStartDate, setTimelineStartDate] = useState<string>('');
  const [timelineEndDate, setTimelineEndDate] = useState<string>('');
  const [timelineSortOrder, setTimelineSortOrder] = useState<'desc' | 'asc'>('desc');
  const [isTimelineLoading, setIsTimelineLoading] = useState<boolean>(false);
  const [timelineError, setTimelineError] = useState<string | null>(null);

  // Clipboard Feedback
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [copiedSqlId, setCopiedSqlId] = useState<string | null>(null);

  // Sequence guards to prevent stale state when rapidly switching users or filters
  const profileSeqRef = useRef(0);
  const queriesSeqRef = useRef(0);
  const datasetsSeqRef = useRef(0);
  const txSeqRef = useRef(0);
  const timelineSeqRef = useRef(0);

  // Reset all user-scoped state whenever userId changes
  useEffect(() => {
    setActiveTab('overview');
    setUserDetail(null);
    setProfileError(null);
    setQueries([]);
    setQueriesTotal(0);
    setQueriesPage(1);
    setQueriesSearch('');
    setQueriesStatus('All');
    setQueriesStartDate('');
    setQueriesEndDate('');
    setQueriesSortOrder('desc');
    setExpandedQueryId(null);
    setDatasets([]);
    setDatasetsTotal(0);
    setDatasetsPage(1);
    setDatasetsSearch('');
    setExpandedDatasetId(null);
    setTransactions([]);
    setTransactionsTotal(0);
    setTransactionsPage(1);
    setTransactionsSearch('');
    setTransactionsType('all');
    setTransactionsDirection('all');
    setTransactionsStartDate('');
    setTransactionsEndDate('');
    setTransactionsSortOrder('desc');
    setTimelineItems([]);
    setTimelineTotal(0);
    setTimelinePage(1);
    setTimelineType('all');
    setTimelineStatus('All');
    setTimelineStartDate('');
    setTimelineEndDate('');
    setTimelineSortOrder('desc');
  }, [userId]);

  const copyToClipboard = (text: string, identifier: string, isSql = false) => {
    navigator.clipboard.writeText(text);
    if (isSql) {
      setCopiedSqlId(identifier);
      setTimeout(() => setCopiedSqlId(null), 1800);
    } else {
      setCopiedId(identifier);
      setTimeout(() => setCopiedId(null), 1800);
    }
  };

  // 1. Fetch Profile
  const fetchUserProfile = useCallback(async () => {
    const seq = ++profileSeqRef.current;
    setIsProfileLoading(true);
    setProfileError(null);
    try {
      const data = await api.admin.getUserDetail(userId);
      if (seq === profileSeqRef.current) {
        setUserDetail(data);
      }
    } catch (err: any) {
      if (seq === profileSeqRef.current) {
        setProfileError(err.message || 'Failed to load user profile.');
      }
    } finally {
      if (seq === profileSeqRef.current) {
        setIsProfileLoading(false);
      }
    }
  }, [userId]);

  // 2. Fetch User Queries
  const fetchUserQueries = useCallback(async () => {
    const seq = ++queriesSeqRef.current;
    setIsQueriesLoading(true);
    setQueriesError(null);
    try {
      const res = await api.admin.getUserQueries(userId, {
        page: queriesPage,
        limit: queriesLimit,
        search: queriesSearch,
        status: queriesStatus,
        start_date: queriesStartDate || undefined,
        end_date: queriesEndDate || undefined,
        sort_order: queriesSortOrder,
      });
      if (seq === queriesSeqRef.current) {
        setQueries(res.items || []);
        setQueriesTotal(res.total || 0);
      }
    } catch (err: any) {
      if (seq === queriesSeqRef.current) {
        const msg = err.message || 'Failed to load user queries.';
        setQueriesError(msg);
        addToast?.('Error', msg, 'rose');
      }
    } finally {
      if (seq === queriesSeqRef.current) {
        setIsQueriesLoading(false);
      }
    }
  }, [
    userId,
    queriesPage,
    queriesLimit,
    queriesSearch,
    queriesStatus,
    queriesStartDate,
    queriesEndDate,
    queriesSortOrder,
    addToast,
  ]);

  // 3. Fetch User Datasets
  const fetchUserDatasets = useCallback(async () => {
    const seq = ++datasetsSeqRef.current;
    setIsDatasetsLoading(true);
    setDatasetsError(null);
    try {
      const res = await api.admin.getUserDatasets(userId, {
        page: datasetsPage,
        limit: datasetsLimit,
        search: datasetsSearch,
      });
      if (seq === datasetsSeqRef.current) {
        setDatasets(res.items || []);
        setDatasetsTotal(res.total || 0);
      }
    } catch (err: any) {
      if (seq === datasetsSeqRef.current) {
        const msg = err.message || 'Failed to load user datasets.';
        setDatasetsError(msg);
        addToast?.('Error', msg, 'rose');
      }
    } finally {
      if (seq === datasetsSeqRef.current) {
        setIsDatasetsLoading(false);
      }
    }
  }, [userId, datasetsPage, datasetsLimit, datasetsSearch, addToast]);

  // 4. Fetch User Transactions
  const fetchUserTransactions = useCallback(async () => {
    const seq = ++txSeqRef.current;
    setIsTransactionsLoading(true);
    setTransactionsError(null);
    try {
      const res = await api.admin.getUserTransactions(userId, {
        page: transactionsPage,
        limit: transactionsLimit,
        search: transactionsSearch,
        transaction_type: transactionsType,
        direction: transactionsDirection,
        start_date: transactionsStartDate || undefined,
        end_date: transactionsEndDate || undefined,
        sort_order: transactionsSortOrder,
      });
      if (seq === txSeqRef.current) {
        setTransactions(res.items || []);
        setTransactionsTotal(res.total || 0);
      }
    } catch (err: any) {
      if (seq === txSeqRef.current) {
        const msg = err.message || 'Failed to load user transactions.';
        setTransactionsError(msg);
        addToast?.('Error', msg, 'rose');
      }
    } finally {
      if (seq === txSeqRef.current) {
        setIsTransactionsLoading(false);
      }
    }
  }, [
    userId,
    transactionsPage,
    transactionsLimit,
    transactionsSearch,
    transactionsType,
    transactionsDirection,
    transactionsStartDate,
    transactionsEndDate,
    transactionsSortOrder,
    addToast,
  ]);

  // 5. Fetch User Timeline
  const fetchUserTimeline = useCallback(async () => {
    const seq = ++timelineSeqRef.current;
    setIsTimelineLoading(true);
    setTimelineError(null);
    try {
      const res = await api.admin.getUserActivity(userId, {
        page: timelinePage,
        limit: timelineLimit,
        activity_type: timelineType,
        status: timelineStatus,
        start_date: timelineStartDate || undefined,
        end_date: timelineEndDate || undefined,
        sort_order: timelineSortOrder,
      });
      if (seq === timelineSeqRef.current) {
        setTimelineItems(res.items || []);
        setTimelineTotal(res.total || 0);
      }
    } catch (err: any) {
      if (seq === timelineSeqRef.current) {
        const msg = err.message || 'Failed to load user activity timeline.';
        setTimelineError(msg);
        addToast?.('Error', msg, 'rose');
      }
    } finally {
      if (seq === timelineSeqRef.current) {
        setIsTimelineLoading(false);
      }
    }
  }, [
    userId,
    timelinePage,
    timelineLimit,
    timelineType,
    timelineStatus,
    timelineStartDate,
    timelineEndDate,
    timelineSortOrder,
    addToast,
  ]);

  useEffect(() => {
    fetchUserProfile();
  }, [fetchUserProfile]);

  useEffect(() => {
    if (activeTab === 'queries') fetchUserQueries();
    else if (activeTab === 'datasets') fetchUserDatasets();
    else if (activeTab === 'transactions') fetchUserTransactions();
    else if (activeTab === 'timeline') fetchUserTimeline();
  }, [activeTab, fetchUserQueries, fetchUserDatasets, fetchUserTransactions, fetchUserTimeline]);

  const totalQ = userDetail?.total_queries ?? 0;
  const successQ = userDetail?.total_queries_successful ?? 0;
  const failedQ = userDetail?.total_queries_failed ?? 0;
  const successPct =
    userDetail?.query_success_rate !== undefined
      ? userDetail.query_success_rate
      : totalQ > 0
      ? Math.round((successQ / totalQ) * 100)
      : 100;

  const isAnyLoading =
    isProfileLoading ||
    isQueriesLoading ||
    isDatasetsLoading ||
    isTransactionsLoading ||
    isTimelineLoading;

  return (
    <div
      className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-xs flex justify-end overflow-hidden"
      onClick={onClose}
    >
      <div
        className="bg-white w-full max-w-5xl h-full flex flex-col shadow-2xl border-l border-slate-200 overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header Bar */}
        <div className="px-6 py-5 bg-slate-900 text-white shrink-0 flex items-start justify-between gap-4">
          <div className="flex items-center gap-4 min-w-0">
            <div className="w-12 h-12 rounded-2xl bg-indigo-500/20 border border-indigo-400/30 flex items-center justify-center shrink-0 text-indigo-200 font-extrabold text-lg">
              {userDetail?.full_name ? userDetail.full_name.charAt(0).toUpperCase() : 'U'}
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <h2 className="text-lg sm:text-xl font-bold text-white truncate">
                  {userDetail?.full_name || 'Loading User Profile...'}
                </h2>
                {userDetail?.is_admin ? (
                  <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-400/20 text-amber-300 border border-amber-400/30 uppercase tracking-wider inline-flex items-center gap-1">
                    <ShieldCheck className="w-3 h-3" />
                    Administrator
                  </span>
                ) : userDetail ? (
                  <span
                    className={`px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider ${
                      userDetail.account_status === 'Active'
                        ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-400/30'
                        : 'bg-slate-700 text-slate-300 border border-slate-600'
                    }`}
                  >
                    {userDetail.account_status}
                  </span>
                ) : null}
              </div>
              <div className="flex items-center gap-2.5 text-xs text-slate-300 font-mono mt-1 flex-wrap">
                <span className="text-slate-100">{userDetail?.email || '—'}</span>
                <span className="text-slate-600">•</span>
                <span className="inline-flex items-center gap-1 text-indigo-200">
                  {userId}
                  <button
                    type="button"
                    onClick={() => copyToClipboard(userId, 'user_id')}
                    className="hover:text-white cursor-pointer"
                    title="Copy User ID"
                  >
                    {copiedId === 'user_id' ? (
                      <Check className="w-3 h-3 text-emerald-400" />
                    ) : (
                      <Copy className="w-3 h-3 text-slate-400" />
                    )}
                  </button>
                </span>
                {userDetail?.created_at && (
                  <>
                    <span className="text-slate-600">•</span>
                    <span className="text-slate-400">
                      Joined {new Date(userDetail.created_at).toLocaleDateString()}
                    </span>
                  </>
                )}
                {userDetail?.last_activity && (
                  <>
                    <span className="text-slate-600">•</span>
                    <span className="text-slate-400">
                      Last active {new Date(userDetail.last_activity).toLocaleDateString()}
                    </span>
                  </>
                )}
              </div>
            </div>
          </div>

          <div className="flex items-center gap-2 shrink-0">
            <button
              type="button"
              onClick={() => {
                fetchUserProfile();
                if (activeTab === 'queries') fetchUserQueries();
                else if (activeTab === 'datasets') fetchUserDatasets();
                else if (activeTab === 'transactions') fetchUserTransactions();
                else if (activeTab === 'timeline') fetchUserTimeline();
              }}
              className="p-2 rounded-lg bg-white/10 hover:bg-white/20 text-white transition-colors cursor-pointer"
              title="Refresh Profile"
            >
              <RefreshCw className={`w-4 h-4 ${isAnyLoading ? 'animate-spin' : ''}`} />
            </button>
            <button
              type="button"
              onClick={onClose}
              className="p-2 rounded-lg bg-white/10 hover:bg-rose-500/80 text-slate-300 hover:text-white transition-colors cursor-pointer"
              title="Close Profile"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Tab Navigation */}
        <div className="bg-slate-50 border-b border-slate-200 px-6 pt-2 shrink-0 flex items-center gap-1.5 overflow-x-auto text-xs font-semibold">
          {[
            { id: 'overview', label: 'Overview', icon: <Layers className="w-3.5 h-3.5" /> },
            {
              id: 'queries',
              label: 'Query History',
              icon: <Search className="w-3.5 h-3.5" />,
              count: userDetail?.total_queries,
            },
            {
              id: 'datasets',
              label: 'Dataset Contributions',
              icon: <Database className="w-3.5 h-3.5" />,
              count: userDetail?.total_datasets,
            },
            {
              id: 'transactions',
              label: 'Credit History',
              icon: <Coins className="w-3.5 h-3.5" />,
            },
            {
              id: 'timeline',
              label: 'Activity Timeline',
              icon: <Activity className="w-3.5 h-3.5" />,
            },
          ].map((tab) => {
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                type="button"
                onClick={() => setActiveTab(tab.id as UserDetailTab)}
                className={`px-3.5 py-2.5 rounded-t-xl transition-colors cursor-pointer flex items-center gap-2 whitespace-nowrap border-b-2 ${
                  isActive
                    ? 'border-indigo-600 text-indigo-700 bg-white font-bold'
                    : 'border-transparent text-slate-600 hover:text-slate-900 hover:bg-slate-100/70'
                }`}
              >
                {tab.icon}
                <span>{tab.label}</span>
                {typeof tab.count === 'number' && (
                  <span
                    className={`text-[10px] px-1.5 py-0.5 rounded-full font-mono ${
                      isActive ? 'bg-indigo-50 text-indigo-700' : 'bg-slate-200/80 text-slate-600'
                    }`}
                  >
                    {tab.count}
                  </span>
                )}
              </button>
            );
          })}
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-6 bg-slate-50/40">
          {profileError && <ErrorRetryBanner message={profileError} onRetry={fetchUserProfile} />}

          {/* TAB 1: OVERVIEW */}
          {activeTab === 'overview' && (
            <div className="space-y-5">
              {isProfileLoading && !userDetail ? (
                <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
                  {[1, 2, 3, 4, 5, 6].map((n) => (
                    <div key={n} className="h-24 bg-white border border-slate-200 rounded-xl animate-pulse" />
                  ))}
                </div>
              ) : userDetail ? (
                <>
                  {/* Summary Stats */}
                  <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
                    <div className="bg-white border border-slate-200 rounded-xl p-4">
                      <span className="text-[10px] uppercase font-bold text-slate-400 tracking-wider block">
                        Credit Balance
                      </span>
                      <div className="text-xl font-black font-mono text-emerald-600 mt-1">
                        {userDetail.credits.toLocaleString()} cr
                      </div>
                      <span className="text-[10px] text-slate-400 block mt-0.5">Current balance</span>
                    </div>

                    <div className="bg-white border border-slate-200 rounded-xl p-4">
                      <span className="text-[10px] uppercase font-bold text-slate-400 tracking-wider block">
                        Reputation
                      </span>
                      <div className="text-xl font-black font-mono text-indigo-600 mt-1">
                        {userDetail.reputation_score}/100
                      </div>
                      <span className="text-[10px] text-slate-400 block mt-0.5">Contributor score</span>
                    </div>

                    <div className="bg-white border border-slate-200 rounded-xl p-4">
                      <span className="text-[10px] uppercase font-bold text-slate-400 tracking-wider block">
                        Datasets
                      </span>
                      <div className="text-xl font-black font-mono text-slate-900 mt-1">
                        {userDetail.total_datasets}
                      </div>
                      <span className="text-[10px] text-slate-400 block mt-0.5">
                        {userDetail.total_improvements ?? 0} improvements
                      </span>
                    </div>

                    <div className="bg-white border border-slate-200 rounded-xl p-4">
                      <span className="text-[10px] uppercase font-bold text-slate-400 tracking-wider block">
                        Total Queries
                      </span>
                      <div className="text-xl font-black font-mono text-slate-900 mt-1">
                        {totalQ}
                      </div>
                      <div className="flex items-center gap-1.5 text-[10px] font-semibold mt-0.5">
                        <span className="text-emerald-600">{successQ} ok</span>
                        <span className="text-slate-300">•</span>
                        <span className="text-rose-600">{failedQ} failed</span>
                      </div>
                    </div>

                    <div className="bg-white border border-slate-200 rounded-xl p-4">
                      <span className="text-[10px] uppercase font-bold text-slate-400 tracking-wider block">
                        Success Rate
                      </span>
                      <div className="text-xl font-black font-mono text-slate-900 mt-1">
                        {successPct}%
                      </div>
                      <div className="h-1.5 bg-slate-100 rounded-full mt-1.5 overflow-hidden">
                        <div
                          className={`h-full rounded-full ${
                            successPct >= 80 ? 'bg-emerald-500' : successPct >= 50 ? 'bg-amber-500' : 'bg-rose-500'
                          }`}
                          style={{ width: `${Math.min(100, successPct)}%` }}
                        />
                      </div>
                    </div>

                    <div className="bg-white border border-slate-200 rounded-xl p-4">
                      <span className="text-[10px] uppercase font-bold text-slate-400 tracking-wider block">
                        Credit Flow
                      </span>
                      <div className="text-sm font-black font-mono mt-1.5">
                        <span className="text-emerald-600">+{userDetail.total_credits_earned.toLocaleString()}</span>
                        <span className="text-slate-300"> / </span>
                        <span className="text-rose-600">-{userDetail.total_credits_spent.toLocaleString()}</span>
                      </div>
                      <span className="text-[10px] text-slate-400 block mt-0.5">
                        Refunds: {userDetail.total_credits_refunded ?? 0} cr
                      </span>
                    </div>
                  </div>

                  {/* Account Metadata Summary */}
                  <div className="bg-white border border-slate-200 rounded-2xl p-5 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 text-xs">
                    <div>
                      <span className="text-[10px] uppercase font-bold text-slate-400">Account Created</span>
                      <div className="font-mono text-slate-800 mt-1">
                        {new Date(userDetail.created_at).toLocaleString()}
                      </div>
                    </div>
                    <div>
                      <span className="text-[10px] uppercase font-bold text-slate-400">Last Recorded Activity</span>
                      <div className="font-mono text-slate-800 mt-1">
                        {userDetail.last_activity
                          ? new Date(userDetail.last_activity).toLocaleString()
                          : 'No activity yet'}
                      </div>
                    </div>
                    <div>
                      <span className="text-[10px] uppercase font-bold text-slate-400">Marketplace Unlocks</span>
                      <div className="font-mono font-bold text-slate-800 mt-1">
                        {userDetail.total_unlocks ?? 0} dataset(s)
                      </div>
                    </div>
                    <div>
                      <span className="text-[10px] uppercase font-bold text-slate-400">Account Role</span>
                      <div className="font-semibold text-slate-800 mt-1">
                        {userDetail.is_admin ? 'Platform Administrator' : 'Registered User'} ({userDetail.account_status})
                      </div>
                    </div>
                  </div>

                  {/* Quick Snapshots with Drill-Down */}
                  <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                    {/* Recent Datasets */}
                    <div className="bg-white border border-slate-200 rounded-2xl p-5 space-y-3">
                      <div className="flex items-center justify-between">
                        <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500 flex items-center gap-1.5">
                          <Database className="w-3.5 h-3.5 text-emerald-600" />
                          Recent Contributions ({userDetail.total_datasets})
                        </h3>
                        <button
                          type="button"
                          onClick={() => setActiveTab('datasets')}
                          className="text-xs font-semibold text-indigo-600 hover:text-indigo-800 cursor-pointer inline-flex items-center gap-0.5"
                        >
                          <span>All datasets</span>
                          <ArrowUpRight className="w-3.5 h-3.5" />
                        </button>
                      </div>
                      {userDetail.datasets.length === 0 ? (
                        <p className="text-xs text-slate-400 py-4 text-center">No datasets uploaded yet.</p>
                      ) : (
                        <div className="divide-y divide-slate-100 text-xs">
                          {userDetail.datasets.slice(0, 4).map((ds) => (
                            <div
                              key={ds.id}
                              onClick={() => onInspectDataset?.(ds.id)}
                              className={`py-2.5 flex items-center justify-between gap-3 ${
                                onInspectDataset ? 'hover:bg-slate-50 cursor-pointer -mx-2 px-2 rounded-lg' : ''
                              }`}
                            >
                              <div className="min-w-0">
                                <div className="font-semibold text-slate-900 truncate">{ds.name}</div>
                                <div className="text-[11px] text-slate-400 font-mono">
                                  {ds.rows_count.toLocaleString()}r × {ds.columns_count}c • {ds.version_count || 1}v •{' '}
                                  {ds.query_count ?? 0} queries
                                </div>
                              </div>
                              <div className="text-right shrink-0">
                                {typeof ds.quality_score === 'number' && (
                                  <span className="px-2 py-0.5 rounded bg-emerald-50 text-emerald-700 font-mono text-[10px] font-bold">
                                    {ds.quality_score.toFixed(1)}
                                  </span>
                                )}
                                <div className="text-[10px] text-slate-400 font-mono mt-0.5">
                                  {ds.availability || 'Available'}
                                </div>
                              </div>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>

                    {/* Recent Queries */}
                    <div className="bg-white border border-slate-200 rounded-2xl p-5 space-y-3">
                      <div className="flex items-center justify-between">
                        <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500 flex items-center gap-1.5">
                          <Search className="w-3.5 h-3.5 text-cyan-600" />
                          Recent Queries ({userDetail.total_queries})
                        </h3>
                        <button
                          type="button"
                          onClick={() => setActiveTab('queries')}
                          className="text-xs font-semibold text-indigo-600 hover:text-indigo-800 cursor-pointer inline-flex items-center gap-0.5"
                        >
                          <span>All queries</span>
                          <ArrowUpRight className="w-3.5 h-3.5" />
                        </button>
                      </div>
                      {userDetail.recent_queries.length === 0 ? (
                        <p className="text-xs text-slate-400 py-4 text-center">No queries executed yet.</p>
                      ) : (
                        <div className="divide-y divide-slate-100 text-xs">
                          {userDetail.recent_queries.slice(0, 4).map((q: any) => (
                            <div key={q.id} className="py-2.5 flex items-center justify-between gap-3">
                              <div className="min-w-0">
                                <p className="font-medium text-slate-900 truncate">{q.natural_prompt}</p>
                                <p className="text-[11px] text-slate-400 font-mono truncate">
                                  {q.dataset_name || 'Cross-Catalog'} • {q.execution_time_ms}ms
                                </p>
                              </div>
                              <span
                                className={`px-2 py-0.5 rounded-full text-[10px] font-bold shrink-0 ${
                                  q.status === 'SUCCESS'
                                    ? 'bg-emerald-50 text-emerald-700'
                                    : 'bg-rose-50 text-rose-700'
                                }`}
                              >
                                {q.status}
                              </span>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                </>
              ) : null}
            </div>
          )}

          {/* TAB 2: QUERY HISTORY */}
          {activeTab === 'queries' && (
            <div className="bg-white border border-slate-200 rounded-2xl p-5 space-y-4">
              {queriesError && <ErrorRetryBanner message={queriesError} onRetry={fetchUserQueries} />}

              <div className="flex flex-wrap items-center justify-between gap-2.5">
                <div className="relative flex-1 min-w-[220px] max-w-sm">
                  <Search className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" />
                  <input
                    type="text"
                    placeholder="Search prompt, SQL, or dataset..."
                    value={queriesSearch}
                    onChange={(e) => {
                      setQueriesSearch(e.target.value);
                      setQueriesPage(1);
                    }}
                    className="w-full pl-9 pr-8 py-2 text-xs rounded-xl border border-slate-200 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500"
                  />
                  {queriesSearch && (
                    <button
                      type="button"
                      onClick={() => {
                        setQueriesSearch('');
                        setQueriesPage(1);
                      }}
                      className="absolute right-2.5 top-2.5 text-slate-400 hover:text-slate-600 cursor-pointer"
                    >
                      <X className="w-3.5 h-3.5" />
                    </button>
                  )}
                </div>

                <div className="flex flex-wrap items-center gap-2 text-xs">
                  <select
                    value={queriesStatus}
                    onChange={(e) => {
                      setQueriesStatus(e.target.value);
                      setQueriesPage(1);
                    }}
                    className="px-2.5 py-2 rounded-xl border border-slate-200 bg-white text-slate-700 focus:outline-none"
                  >
                    <option value="All">All Statuses</option>
                    <option value="SUCCESS">Success</option>
                    <option value="FAILED">All Failed</option>
                    <option value="SQL_REJECTED">SQL Rejected</option>
                    <option value="INSUFFICIENT_CREDITS">Insufficient Credits</option>
                  </select>
                  <input
                    type="date"
                    value={queriesStartDate}
                    onChange={(e) => {
                      setQueriesStartDate(e.target.value);
                      setQueriesPage(1);
                    }}
                    className="px-2.5 py-1.5 rounded-xl border border-slate-200 text-xs text-slate-700"
                    title="Start Date"
                  />
                  <input
                    type="date"
                    value={queriesEndDate}
                    onChange={(e) => {
                      setQueriesEndDate(e.target.value);
                      setQueriesPage(1);
                    }}
                    className="px-2.5 py-1.5 rounded-xl border border-slate-200 text-xs text-slate-700"
                    title="End Date"
                  />
                  <button
                    type="button"
                    onClick={() => {
                      setQueriesSortOrder((s) => (s === 'desc' ? 'asc' : 'desc'));
                      setQueriesPage(1);
                    }}
                    className="px-2.5 py-2 rounded-xl border border-slate-200 hover:bg-slate-50 text-slate-700 inline-flex items-center gap-1 cursor-pointer"
                  >
                    <ArrowUpDown className="w-3.5 h-3.5" />
                    <span>{queriesSortOrder === 'desc' ? 'Newest' : 'Oldest'}</span>
                  </button>
                  <select
                    value={queriesLimit}
                    onChange={(e) => {
                      setQueriesLimit(Number(e.target.value));
                      setQueriesPage(1);
                    }}
                    className="px-2.5 py-2 rounded-xl border border-slate-200 bg-white text-slate-700 focus:outline-none"
                  >
                    <option value={10}>10 / pg</option>
                    <option value={20}>20 / pg</option>
                    <option value={50}>50 / pg</option>
                  </select>
                </div>
              </div>

              <div className="border border-slate-100 rounded-xl overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead className="bg-slate-50 text-slate-500 font-semibold border-b border-slate-100">
                    <tr>
                      <th className="py-3 px-4 w-8" />
                      <th className="py-3 px-4">Natural Prompt</th>
                      <th className="py-3 px-4">Dataset</th>
                      <th className="py-3 px-4">Status</th>
                      <th className="py-3 px-4">Duration / Rows</th>
                      <th className="py-3 px-4">Credits</th>
                      <th className="py-3 px-4">Timestamp</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 text-slate-700">
                    {isQueriesLoading ? (
                      <TableSkeletonRows cols={7} rows={5} />
                    ) : queries.length === 0 ? (
                      <tr>
                        <td colSpan={7} className="py-10 text-center text-slate-400">
                          No queries match your current filters.
                        </td>
                      </tr>
                    ) : (
                      queries.map((q) => {
                        const isExpanded = expandedQueryId === q.id;
                        return (
                          <React.Fragment key={q.id}>
                            <tr
                              onClick={() => setExpandedQueryId(isExpanded ? null : q.id)}
                              className="hover:bg-slate-50/70 transition-colors cursor-pointer"
                            >
                              <td className="py-3 px-4 text-slate-400">
                                {isExpanded ? (
                                  <ChevronUp className="w-3.5 h-3.5" />
                                ) : (
                                  <ChevronDown className="w-3.5 h-3.5" />
                                )}
                              </td>
                              <td className="py-3 px-4 max-w-xs">
                                <div className="font-semibold text-slate-900 truncate" title={q.natural_prompt}>
                                  {q.natural_prompt}
                                </div>
                                {q.error_message && (
                                  <div className="text-[10px] text-rose-600 truncate mt-0.5">
                                    {q.error_message}
                                  </div>
                                )}
                              </td>
                              <td className="py-3 px-4">
                                <span className="px-2 py-0.5 rounded text-[11px] bg-slate-100 text-slate-700 font-medium truncate block max-w-[140px]">
                                  {q.dataset_name || 'Cross-Catalog'}
                                </span>
                              </td>
                              <td className="py-3 px-4">
                                <span
                                  className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
                                    q.execution_status === 'SUCCESS'
                                      ? 'bg-emerald-50 text-emerald-700'
                                      : 'bg-rose-50 text-rose-700'
                                  }`}
                                >
                                  {q.execution_status}
                                </span>
                              </td>
                              <td className="py-3 px-4 font-mono text-[11px] text-slate-500 whitespace-nowrap">
                                {q.execution_time_ms}ms • {q.rows_returned} rows
                              </td>
                              <td className="py-3 px-4 font-mono text-[11px] whitespace-nowrap">
                                <span className="font-bold text-slate-800">{q.credits_charged} cr</span>
                                {(q.credits_refunded ?? 0) > 0 && (
                                  <span className="text-emerald-600 ml-1">(+{q.credits_refunded} ref)</span>
                                )}
                              </td>
                              <td className="py-3 px-4 text-[11px] text-slate-400 font-mono whitespace-nowrap">
                                {new Date(q.timestamp).toLocaleString()}
                              </td>
                            </tr>
                            {isExpanded && (
                              <tr className="bg-slate-50/80">
                                <td colSpan={7} className="p-4 space-y-3">
                                  <div className="space-y-1">
                                    <div className="text-[10px] uppercase font-bold text-slate-400">Full Prompt</div>
                                    <p className="text-xs text-slate-900 bg-white border border-slate-200 rounded-lg p-3">
                                      {q.natural_prompt}
                                    </p>
                                  </div>
                                  <div className="space-y-1.5">
                                    <div className="flex items-center justify-between">
                                      <span className="text-[10px] uppercase font-bold text-slate-400">
                                        Generated SQL
                                      </span>
                                      <div className="flex items-center gap-2">
                                        {q.dataset_id && onInspectDataset && (
                                          <button
                                            type="button"
                                            onClick={(e) => {
                                              e.stopPropagation();
                                              onInspectDataset(q.dataset_id!);
                                            }}
                                            className="px-2 py-1 rounded bg-white border border-slate-200 hover:bg-slate-100 text-[11px] font-semibold text-indigo-700 inline-flex items-center gap-1 cursor-pointer"
                                          >
                                            <span>Inspect Dataset</span>
                                            <ExternalLink className="w-3 h-3" />
                                          </button>
                                        )}
                                        <button
                                          type="button"
                                          onClick={(e) => {
                                            e.stopPropagation();
                                            copyToClipboard(q.generated_sql || '', `${q.id}_full`, true);
                                          }}
                                          className="px-2 py-1 rounded bg-white border border-slate-200 hover:bg-slate-100 text-[11px] font-semibold text-slate-700 inline-flex items-center gap-1 cursor-pointer"
                                        >
                                          {copiedSqlId === `${q.id}_full` ? (
                                            <>
                                              <Check className="w-3 h-3 text-emerald-600" />
                                              <span className="text-emerald-700">Copied</span>
                                            </>
                                          ) : (
                                            <>
                                              <Copy className="w-3 h-3 text-slate-500" />
                                              <span>Copy SQL</span>
                                            </>
                                          )}
                                        </button>
                                      </div>
                                    </div>
                                    <pre className="p-3 bg-slate-900 text-emerald-400 rounded-xl font-mono text-[11px] overflow-x-auto whitespace-pre-wrap leading-relaxed">
                                      {q.generated_sql || '-- No SQL generated'}
                                    </pre>
                                  </div>
                                  <div className="flex flex-wrap gap-4 text-[11px] font-mono text-slate-500">
                                    <span>Query ID: {q.id}</span>
                                    <span>Duration: {q.execution_time_ms}ms</span>
                                    <span>Rows Returned: {q.rows_returned}</span>
                                    <span>Charged: {q.credits_charged} cr</span>
                                    <span>Refunded: {q.credits_refunded ?? 0} cr</span>
                                  </div>
                                  {q.error_message && (
                                    <div className="p-3 rounded-lg bg-rose-50 border border-rose-200 text-rose-700 text-xs font-mono">
                                      Error: {q.error_message}
                                    </div>
                                  )}
                                </td>
                              </tr>
                            )}
                          </React.Fragment>
                        );
                      })
                    )}
                  </tbody>
                </table>
              </div>

              <PaginationFooter
                page={queriesPage}
                limit={queriesLimit}
                total={queriesTotal}
                itemCount={queries.length}
                entityLabel="queries"
                onPageChange={setQueriesPage}
              />
            </div>
          )}

          {/* TAB 3: DATASET CONTRIBUTIONS */}
          {activeTab === 'datasets' && (
            <div className="bg-white border border-slate-200 rounded-2xl p-5 space-y-4">
              {datasetsError && <ErrorRetryBanner message={datasetsError} onRetry={fetchUserDatasets} />}

              <div className="flex flex-wrap items-center justify-between gap-2.5">
                <div className="relative flex-1 min-w-[220px] max-w-sm">
                  <Search className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" />
                  <input
                    type="text"
                    placeholder="Search dataset name, filename, domain..."
                    value={datasetsSearch}
                    onChange={(e) => {
                      setDatasetsSearch(e.target.value);
                      setDatasetsPage(1);
                    }}
                    className="w-full pl-9 pr-8 py-2 text-xs rounded-xl border border-slate-200 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500"
                  />
                  {datasetsSearch && (
                    <button
                      type="button"
                      onClick={() => {
                        setDatasetsSearch('');
                        setDatasetsPage(1);
                      }}
                      className="absolute right-2.5 top-2.5 text-slate-400 hover:text-slate-600 cursor-pointer"
                    >
                      <X className="w-3.5 h-3.5" />
                    </button>
                  )}
                </div>
                <select
                  value={datasetsLimit}
                  onChange={(e) => {
                    setDatasetsLimit(Number(e.target.value));
                    setDatasetsPage(1);
                  }}
                  className="px-2.5 py-2 rounded-xl border border-slate-200 text-xs text-slate-700 bg-white focus:outline-none"
                >
                  <option value={10}>10 / pg</option>
                  <option value={20}>20 / pg</option>
                </select>
              </div>

              <div className="border border-slate-100 rounded-xl overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead className="bg-slate-50 text-slate-500 font-semibold border-b border-slate-100">
                    <tr>
                      <th className="py-3 px-4 w-8" />
                      <th className="py-3 px-4">Dataset</th>
                      <th className="py-3 px-4">Domain</th>
                      <th className="py-3 px-4">Dimensions</th>
                      <th className="py-3 px-4">Quality</th>
                      <th className="py-3 px-4">Rewards (Basic / Qual / Imp)</th>
                      <th className="py-3 px-4">Versions</th>
                      <th className="py-3 px-4">Storage</th>
                      <th className="py-3 px-4">Uploaded</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 text-slate-700">
                    {isDatasetsLoading ? (
                      <TableSkeletonRows cols={9} rows={5} />
                    ) : datasets.length === 0 ? (
                      <tr>
                        <td colSpan={9} className="py-10 text-center text-slate-400">
                          No dataset contributions recorded for this user.
                        </td>
                      </tr>
                    ) : (
                      datasets.map((d) => {
                        const isExpanded = expandedDatasetId === d.id;
                        return (
                          <React.Fragment key={d.id}>
                            <tr
                              onClick={() => setExpandedDatasetId(isExpanded ? null : d.id)}
                              className="hover:bg-slate-50/70 transition-colors cursor-pointer"
                            >
                              <td className="py-3 px-4 text-slate-400">
                                {isExpanded ? (
                                  <ChevronUp className="w-3.5 h-3.5" />
                                ) : (
                                  <ChevronDown className="w-3.5 h-3.5" />
                                )}
                              </td>
                              <td className="py-3 px-4">
                                <div className="font-bold text-slate-900">{d.name}</div>
                                <div className="text-[11px] text-slate-400 font-mono">{d.filename}</div>
                              </td>
                              <td className="py-3 px-4">
                                <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-slate-100 text-slate-700 uppercase">
                                  {d.domain}
                                </span>
                              </td>
                              <td className="py-3 px-4 font-mono text-[11px] whitespace-nowrap">
                                {d.rows_count.toLocaleString()}r × {d.columns_count}c
                              </td>
                              <td className="py-3 px-4 font-mono">
                                {typeof d.overall_score === 'number' ? (
                                  <span
                                    className={`px-2 py-0.5 rounded text-[11px] font-bold ${
                                      d.overall_score >= 80
                                        ? 'bg-emerald-50 text-emerald-700'
                                        : d.overall_score >= 60
                                        ? 'bg-amber-50 text-amber-700'
                                        : 'bg-rose-50 text-rose-700'
                                    }`}
                                  >
                                    {d.overall_score.toFixed(1)}
                                  </span>
                                ) : (
                                  <span className="text-slate-400">—</span>
                                )}
                              </td>
                              <td className="py-3 px-4 font-mono text-[11px] whitespace-nowrap">
                                <span className="text-slate-700">+{d.basic_upload_reward ?? 0}</span>
                                <span className="text-slate-300"> / </span>
                                <span className="text-emerald-700">+{d.quality_reward ?? 0}</span>
                                <span className="text-slate-300"> / </span>
                                <span className="text-indigo-700">+{d.improvement_rewards ?? 0}</span>
                              </td>
                              <td className="py-3 px-4 font-mono text-[11px]">
                                v{d.version_count ?? 1}.0
                              </td>
                              <td className="py-3 px-4 whitespace-nowrap">
                                <span
                                  className={`px-2 py-0.5 rounded-full text-[10px] font-bold inline-flex items-center gap-1 ${
                                    d.availability === 'Available'
                                      ? 'bg-emerald-50 text-emerald-700'
                                      : 'bg-amber-50 text-amber-700'
                                  }`}
                                >
                                  {d.availability === 'Available' ? (
                                    <CheckCircle2 className="w-2.5 h-2.5" />
                                  ) : (
                                    <AlertTriangle className="w-2.5 h-2.5" />
                                  )}
                                  {d.availability}
                                </span>
                              </td>
                              <td className="py-3 px-4 text-[11px] text-slate-400 font-mono whitespace-nowrap">
                                {new Date(d.created_at).toLocaleDateString()}
                              </td>
                            </tr>
                            {isExpanded && (
                              <tr className="bg-slate-50/80">
                                <td colSpan={9} className="p-4 space-y-3">
                                  <div className="flex flex-wrap items-center justify-between gap-2">
                                    <div className="text-xs text-slate-600">
                                      <span className="font-mono text-slate-400 mr-2">{d.id}</span>
                                      <span>
                                        {d.query_count ?? 0} queries • {d.unlock_count} unlocks • Unlock price:{' '}
                                        <strong>{d.unlock_price} cr</strong>
                                      </span>
                                    </div>
                                    {onInspectDataset && (
                                      <button
                                        type="button"
                                        onClick={(e) => {
                                          e.stopPropagation();
                                          onInspectDataset(d.id);
                                        }}
                                        className="px-3 py-1 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold inline-flex items-center gap-1 cursor-pointer"
                                      >
                                        <span>Open Dataset Inspector</span>
                                        <ExternalLink className="w-3 h-3" />
                                      </button>
                                    )}
                                  </div>
                                  {d.versions && d.versions.length > 0 ? (
                                    <div className="space-y-1.5">
                                      <div className="text-[10px] uppercase font-bold text-slate-400">
                                        Improvement Versions ({d.versions.length})
                                      </div>
                                      {d.versions.map((v: any, idx: number) => (
                                        <div
                                          key={idx}
                                          className="p-2.5 rounded-lg bg-white border border-slate-200 flex items-center justify-between gap-3 text-xs"
                                        >
                                          <div>
                                            <span className="font-mono font-bold text-indigo-700 mr-2">
                                              {v.version}
                                            </span>
                                            <span className="text-slate-700">{v.changes_summary}</span>
                                          </div>
                                          <div className="font-mono text-[11px] shrink-0 text-slate-500">
                                            Score {Number(v.overall_score).toFixed(1)} (+{v.credits_awarded} cr)
                                          </div>
                                        </div>
                                      ))}
                                    </div>
                                  ) : (
                                    <p className="text-[11px] text-slate-400">
                                      Initial v1.0 release — no subsequent version improvements submitted.
                                    </p>
                                  )}
                                </td>
                              </tr>
                            )}
                          </React.Fragment>
                        );
                      })
                    )}
                  </tbody>
                </table>
              </div>

              <PaginationFooter
                page={datasetsPage}
                limit={datasetsLimit}
                total={datasetsTotal}
                itemCount={datasets.length}
                entityLabel="datasets"
                onPageChange={setDatasetsPage}
              />
            </div>
          )}

          {/* TAB 4: CREDIT HISTORY */}
          {activeTab === 'transactions' && (
            <div className="bg-white border border-slate-200 rounded-2xl p-5 space-y-4">
              {transactionsError && (
                <ErrorRetryBanner message={transactionsError} onRetry={fetchUserTransactions} />
              )}

              <div className="flex flex-wrap items-center justify-between gap-2.5">
                <div className="relative flex-1 min-w-[200px] max-w-sm">
                  <Search className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" />
                  <input
                    type="text"
                    placeholder="Search description..."
                    value={transactionsSearch}
                    onChange={(e) => {
                      setTransactionsSearch(e.target.value);
                      setTransactionsPage(1);
                    }}
                    className="w-full pl-9 pr-8 py-2 text-xs rounded-xl border border-slate-200 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500"
                  />
                  {transactionsSearch && (
                    <button
                      type="button"
                      onClick={() => {
                        setTransactionsSearch('');
                        setTransactionsPage(1);
                      }}
                      className="absolute right-2.5 top-2.5 text-slate-400 hover:text-slate-600 cursor-pointer"
                    >
                      <X className="w-3.5 h-3.5" />
                    </button>
                  )}
                </div>

                <div className="flex flex-wrap items-center gap-2 text-xs">
                  <select
                    value={transactionsType}
                    onChange={(e) => {
                      setTransactionsType(e.target.value);
                      setTransactionsPage(1);
                    }}
                    className="px-2.5 py-2 rounded-xl border border-slate-200 bg-white text-slate-700 focus:outline-none"
                  >
                    {TX_TYPE_OPTIONS.map((opt) => (
                      <option key={opt.value} value={opt.value}>
                        {opt.label}
                      </option>
                    ))}
                  </select>

                  <select
                    value={transactionsDirection}
                    onChange={(e) => {
                      setTransactionsDirection(e.target.value);
                      setTransactionsPage(1);
                    }}
                    className="px-2.5 py-2 rounded-xl border border-slate-200 bg-white text-slate-700 focus:outline-none"
                  >
                    <option value="all">All Flows</option>
                    <option value="positive">Earned (+)</option>
                    <option value="negative">Spent (-)</option>
                  </select>

                  <input
                    type="date"
                    value={transactionsStartDate}
                    onChange={(e) => {
                      setTransactionsStartDate(e.target.value);
                      setTransactionsPage(1);
                    }}
                    className="px-2.5 py-1.5 rounded-xl border border-slate-200 text-xs text-slate-700"
                  />
                  <input
                    type="date"
                    value={transactionsEndDate}
                    onChange={(e) => {
                      setTransactionsEndDate(e.target.value);
                      setTransactionsPage(1);
                    }}
                    className="px-2.5 py-1.5 rounded-xl border border-slate-200 text-xs text-slate-700"
                  />

                  <button
                    type="button"
                    onClick={() => {
                      setTransactionsSortOrder((s) => (s === 'desc' ? 'asc' : 'desc'));
                      setTransactionsPage(1);
                    }}
                    className="px-2.5 py-2 rounded-xl border border-slate-200 hover:bg-slate-50 text-slate-700 inline-flex items-center gap-1 cursor-pointer"
                  >
                    <ArrowUpDown className="w-3.5 h-3.5" />
                    <span>{transactionsSortOrder === 'desc' ? 'Newest' : 'Oldest'}</span>
                  </button>
                </div>
              </div>

              <div className="border border-slate-100 rounded-xl overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead className="bg-slate-50 text-slate-500 font-semibold border-b border-slate-100">
                    <tr>
                      <th className="py-3 px-4">Timestamp</th>
                      <th className="py-3 px-4">Type</th>
                      <th className="py-3 px-4">Credits</th>
                      <th className="py-3 px-4">Description</th>
                      <th className="py-3 px-4">Related Resource</th>
                      <th className="py-3 px-4 text-right">Balance After</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 text-slate-700">
                    {isTransactionsLoading ? (
                      <TableSkeletonRows cols={6} rows={5} />
                    ) : transactions.length === 0 ? (
                      <tr>
                        <td colSpan={6} className="py-10 text-center text-slate-400">
                          No credit transactions match your filters.
                        </td>
                      </tr>
                    ) : (
                      transactions.map((t) => {
                        const isCredit = t.amount > 0;
                        return (
                          <tr key={t.id} className="hover:bg-slate-50/60 transition-colors">
                            <td className="py-3 px-4 text-[11px] text-slate-400 font-mono whitespace-nowrap">
                              {new Date(t.timestamp).toLocaleString()}
                            </td>
                            <td className="py-3 px-4">
                              <span className="px-2 py-0.5 rounded text-[10px] font-bold uppercase bg-slate-100 text-slate-700">
                                {t.transaction_type.replace(/_/g, ' ')}
                              </span>
                            </td>
                            <td className="py-3 px-4 whitespace-nowrap">
                              <span
                                className={`inline-flex items-center gap-1 font-mono font-bold text-xs px-2 py-0.5 rounded-full ${
                                  isCredit
                                    ? 'bg-emerald-50 text-emerald-700'
                                    : 'bg-rose-50 text-rose-700'
                                }`}
                              >
                                {isCredit ? (
                                  <ArrowUpRight className="w-3 h-3" />
                                ) : (
                                  <ArrowDownRight className="w-3 h-3" />
                                )}
                                {t.balance_impact} cr
                              </span>
                            </td>
                            <td className="py-3 px-4 text-slate-800 max-w-sm truncate" title={t.description}>
                              {t.description}
                            </td>
                            <td className="py-3 px-4 text-[11px]">
                              {t.related_dataset_id ? (
                                <button
                                  type="button"
                                  onClick={() => onInspectDataset?.(t.related_dataset_id!)}
                                  className="text-indigo-600 hover:underline font-medium cursor-pointer truncate block max-w-[160px]"
                                >
                                  {t.related_dataset_name || t.related_dataset_id}
                                </button>
                              ) : t.related_query_id ? (
                                <span className="font-mono text-slate-500">{t.related_query_id}</span>
                              ) : (
                                <span className="text-slate-400">{t.associated_resource || 'Account Ledger'}</span>
                              )}
                            </td>
                            <td className="py-3 px-4 text-right font-mono font-semibold text-slate-900 whitespace-nowrap">
                              {typeof t.balance_after === 'number'
                                ? `${t.balance_after.toLocaleString()} cr`
                                : '—'}
                            </td>
                          </tr>
                        );
                      })
                    )}
                  </tbody>
                </table>
              </div>

              <PaginationFooter
                page={transactionsPage}
                limit={transactionsLimit}
                total={transactionsTotal}
                itemCount={transactions.length}
                entityLabel="transactions"
                onPageChange={setTransactionsPage}
              />
            </div>
          )}

          {/* TAB 5: ACTIVITY TIMELINE */}
          {activeTab === 'timeline' && (
            <div className="bg-white border border-slate-200 rounded-2xl p-5 space-y-4">
              {timelineError && <ErrorRetryBanner message={timelineError} onRetry={fetchUserTimeline} />}

              <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-3">
                <div>
                  <h3 className="text-sm font-bold text-slate-900">Complete User Activity Timeline</h3>
                  <p className="text-xs text-slate-500">
                    Server-paginated chronological history of all persisted account actions.
                  </p>
                </div>

                <div className="flex flex-wrap items-center gap-2 text-xs">
                  <div className="inline-flex items-center gap-1.5 bg-slate-50 px-2.5 py-1.5 rounded-xl border border-slate-200">
                    <Filter className="w-3.5 h-3.5 text-slate-400" />
                    <select
                      value={timelineType}
                      onChange={(e) => {
                        setTimelineType(e.target.value);
                        setTimelinePage(1);
                      }}
                      className="text-xs text-slate-700 bg-transparent focus:outline-none cursor-pointer"
                    >
                      <option value="all">All Activities</option>
                      <option value="USER_REGISTER">Registration</option>
                      <option value="USER_LOGIN">Sign-In Sessions</option>
                      <option value="DATASET_UPLOAD">Dataset Uploads</option>
                      <option value="DATASET_IMPROVE">Dataset Improvements</option>
                      <option value="DATASET_UNLOCK">Dataset Unlocks</option>
                      <option value="QUERY_SUCCESS">Successful Queries</option>
                      <option value="QUERY_FAILED">Failed Queries</option>
                      <option value="CREDIT_REWARD">Credit Rewards</option>
                      <option value="QUERY_FEE">Query Fees</option>
                      <option value="REFUND">Refunds</option>
                    </select>
                  </div>

                  <input
                    type="date"
                    value={timelineStartDate}
                    onChange={(e) => {
                      setTimelineStartDate(e.target.value);
                      setTimelinePage(1);
                    }}
                    className="px-2.5 py-1.5 rounded-xl border border-slate-200 text-xs text-slate-700"
                  />
                  <input
                    type="date"
                    value={timelineEndDate}
                    onChange={(e) => {
                      setTimelineEndDate(e.target.value);
                      setTimelinePage(1);
                    }}
                    className="px-2.5 py-1.5 rounded-xl border border-slate-200 text-xs text-slate-700"
                  />
                  <button
                    type="button"
                    onClick={() => {
                      setTimelineSortOrder((s) => (s === 'desc' ? 'asc' : 'desc'));
                      setTimelinePage(1);
                    }}
                    className="px-2.5 py-1.5 rounded-xl border border-slate-200 hover:bg-slate-50 text-slate-700 inline-flex items-center gap-1 cursor-pointer"
                  >
                    <ArrowUpDown className="w-3.5 h-3.5" />
                    <span>{timelineSortOrder === 'desc' ? 'Newest first' : 'Oldest first'}</span>
                  </button>
                </div>
              </div>

              {isTimelineLoading ? (
                <div className="space-y-3 py-4">
                  {[1, 2, 3, 4].map((n) => (
                    <div key={n} className="h-20 bg-slate-100 rounded-xl animate-pulse" />
                  ))}
                </div>
              ) : timelineItems.length === 0 ? (
                <div className="py-12 text-center text-xs text-slate-400">
                  No activity events match the selected filters.
                </div>
              ) : (
                <div className="relative pl-6 sm:pl-8 border-l-2 border-slate-100 space-y-4 my-2">
                  {timelineItems.map((item) => {
                    let icon = <Activity className="w-3.5 h-3.5" />;
                    let iconBg = 'bg-slate-100 text-slate-600 border-slate-200';
                    let badgeLabel = 'Activity';
                    let badgeColor = 'bg-slate-100 text-slate-700';

                    if (item.type === 'USER_REGISTER') {
                      icon = <User className="w-3.5 h-3.5" />;
                      iconBg = 'bg-indigo-50 text-indigo-600 border-indigo-200';
                      badgeLabel = 'Registration';
                      badgeColor = 'bg-indigo-50 text-indigo-700';
                    } else if (item.type === 'USER_LOGIN') {
                      icon = <LogIn className="w-3.5 h-3.5" />;
                      iconBg = 'bg-sky-50 text-sky-600 border-sky-200';
                      badgeLabel = 'Sign-In';
                      badgeColor = 'bg-sky-50 text-sky-700';
                    } else if (item.type === 'DATASET_UPLOAD') {
                      icon = <Database className="w-3.5 h-3.5" />;
                      iconBg = 'bg-emerald-50 text-emerald-600 border-emerald-200';
                      badgeLabel = 'Upload';
                      badgeColor = 'bg-emerald-50 text-emerald-700';
                    } else if (item.type === 'QUERY_EXECUTION') {
                      const ok = item.status?.toUpperCase() === 'SUCCESS';
                      icon = <Search className="w-3.5 h-3.5" />;
                      iconBg = ok
                        ? 'bg-cyan-50 text-cyan-600 border-cyan-200'
                        : 'bg-rose-50 text-rose-600 border-rose-200';
                      badgeLabel = ok ? 'Query Success' : 'Query Failed';
                      badgeColor = ok ? 'bg-cyan-50 text-cyan-700' : 'bg-rose-50 text-rose-700';
                    } else if (item.type === 'CREDIT_TRANSACTION') {
                      icon = <Coins className="w-3.5 h-3.5" />;
                      iconBg = 'bg-amber-50 text-amber-600 border-amber-200';
                      badgeLabel = item.metadata?.transaction_type
                        ? String(item.metadata.transaction_type).replace(/_/g, ' ')
                        : 'Credits';
                      badgeColor = 'bg-amber-50 text-amber-700';
                    } else if (item.type === 'DATASET_IMPROVE') {
                      icon = <GitCommit className="w-3.5 h-3.5" />;
                      iconBg = 'bg-violet-50 text-violet-600 border-violet-200';
                      badgeLabel = 'Improvement';
                      badgeColor = 'bg-violet-50 text-violet-700';
                    } else if (item.type === 'DATASET_UNLOCK') {
                      icon = <Unlock className="w-3.5 h-3.5" />;
                      iconBg = 'bg-blue-50 text-blue-600 border-blue-200';
                      badgeLabel = 'Unlock';
                      badgeColor = 'bg-blue-50 text-blue-700';
                    } else if (item.type === 'ADMIN_AUDIT') {
                      icon = <Shield className="w-3.5 h-3.5" />;
                      iconBg = 'bg-purple-50 text-purple-600 border-purple-200';
                      badgeLabel = 'Audit';
                      badgeColor = 'bg-purple-50 text-purple-700';
                    }

                    return (
                      <div key={item.id} className="relative">
                        <div
                          className={`absolute -left-[35px] sm:-left-[43px] top-1.5 w-6 h-6 rounded-full border flex items-center justify-center ${iconBg}`}
                        >
                          {icon}
                        </div>

                        <div className="bg-slate-50/70 border border-slate-200/70 rounded-xl p-3.5">
                          <div className="flex items-center justify-between gap-2 flex-wrap mb-1">
                            <div className="flex items-center gap-2">
                              <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase ${badgeColor}`}>
                                {badgeLabel}
                              </span>
                              <h4 className="text-xs font-bold text-slate-900">{item.title}</h4>
                            </div>
                            <span className="text-[11px] text-slate-400 font-mono flex items-center gap-1">
                              <Clock className="w-3 h-3 text-slate-300" />
                              {new Date(item.timestamp).toLocaleString()}
                            </span>
                          </div>
                          <p className="text-xs text-slate-600 leading-relaxed">{item.description}</p>
                          {(item.dataset_name || item.metadata?.amount || item.metadata?.execution_info) && (
                            <div className="mt-2 pt-2 border-t border-slate-200/60 flex items-center gap-2 flex-wrap text-[11px] font-mono text-slate-500">
                              {item.dataset_name && (
                                <button
                                  type="button"
                                  onClick={() => item.dataset_id && onInspectDataset?.(item.dataset_id)}
                                  className="bg-white px-2 py-0.5 rounded border border-slate-200 hover:border-indigo-300 hover:text-indigo-700 cursor-pointer"
                                >
                                  Dataset: {item.dataset_name}
                                </button>
                              )}
                              {item.metadata?.amount && (
                                <span className="bg-white px-2 py-0.5 rounded border border-slate-200 font-bold text-slate-800">
                                  {Number(item.metadata.amount) > 0
                                    ? `+${item.metadata.amount}`
                                    : item.metadata.amount}{' '}
                                  cr
                                </span>
                              )}
                              {item.metadata?.execution_info && (
                                <span className="bg-white px-2 py-0.5 rounded border border-slate-200">
                                  {item.metadata.execution_info}
                                </span>
                              )}
                            </div>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}

              <div className="flex items-center gap-2 text-[11px] text-slate-400 bg-slate-50 rounded-lg px-3 py-2">
                <Info className="w-3.5 h-3.5 shrink-0" />
                <span>
                  Sign-in events reflect persisted authentication sessions (IP/device headers were not stored historically).
                </span>
              </div>

              <PaginationFooter
                page={timelinePage}
                limit={timelineLimit}
                total={timelineTotal}
                itemCount={timelineItems.length}
                entityLabel="events"
                onPageChange={setTimelinePage}
              />
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default UserHistoryExplorer;
