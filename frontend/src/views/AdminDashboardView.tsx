import React, { useState, useEffect, useCallback } from 'react';
import {
  Users,
  Database,
  Search,
  Coins,
  Activity,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  RefreshCw,
  ShieldCheck,
  Eye,
  Clock,
  ArrowUpRight,
  ArrowDownRight,
  X,
  Copy,
  Check,
  Filter,
  Layers,
  ArrowLeft,
  ChevronDown,
  ChevronUp,
  ArrowUpDown,
  Calendar,
  TrendingUp,
  ExternalLink,
  Info,
} from 'lucide-react';
import {
  UserAccount,
  PageRoute,
  AdminOverview,
  AdminAnalyticsResponse,
  AdminUserItem,
  AdminDatasetItem,
  AdminQueryItem,
  AdminTransactionItem,
  AdminAuditLogItem,
  AdminTimelineItem,
} from '../types';
import { api, ApiError } from '../services/api';
import { UserHistoryExplorer } from '../components/UserHistoryExplorer';
import {
  AreaTrendChart,
  MultiBarChart,
  HorizontalRankChart,
  DeltaBadge,
  KpiSkeletonGrid,
  TableSkeletonRows,
  ErrorRetryBanner,
  PaginationFooter,
} from '../components/admin/AdminCharts';
import { DatasetInspectionDrawer } from '../components/admin/DatasetInspectionDrawer';
import { ActivityDetailDrawer } from '../components/admin/ActivityDetailDrawer';

interface AdminDashboardViewProps {
  currentUser: UserAccount;
  onNavigate: (route: PageRoute) => void;
  addToast?: (
    title: string,
    message: string,
    tone?: 'cyan' | 'rose' | 'amber' | 'emerald' | 'violet'
  ) => void;
}

type AdminTab = 'overview' | 'users' | 'datasets' | 'queries' | 'transactions' | 'activity' | 'audit';
type DateRangePreset = '7d' | '30d' | '90d' | 'all' | 'custom';
type Granularity = 'daily' | 'weekly' | 'monthly';

const TX_TYPE_OPTIONS = [
  { value: 'all', label: 'All Transaction Types' },
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

export const AdminDashboardView: React.FC<AdminDashboardViewProps> = ({
  currentUser,
  onNavigate,
  addToast,
}) => {
  const [activeTab, setActiveTab] = useState<AdminTab>('overview');

  // Overview & Analytics State
  const [dateRange, setDateRange] = useState<DateRangePreset>('all');
  const [customStartDate, setCustomStartDate] = useState<string>('');
  const [customEndDate, setCustomEndDate] = useState<string>('');
  const [granularity, setGranularity] = useState<Granularity>('daily');
  const [overview, setOverview] = useState<AdminOverview | null>(null);
  const [analytics, setAnalytics] = useState<AdminAnalyticsResponse | null>(null);
  const [isOverviewLoading, setIsOverviewLoading] = useState<boolean>(true);
  const [overviewError, setOverviewError] = useState<string | null>(null);

  // Drawers
  const [selectedUserId, setSelectedUserId] = useState<string | null>(null);
  const [selectedDatasetId, setSelectedDatasetId] = useState<string | null>(null);
  const [selectedActivityItem, setSelectedActivityItem] = useState<AdminTimelineItem | null>(null);

  // Users Tab State
  const [users, setUsers] = useState<AdminUserItem[]>([]);
  const [usersTotal, setUsersTotal] = useState<number>(0);
  const [usersPage, setUsersPage] = useState<number>(1);
  const [usersSearch, setUsersSearch] = useState<string>('');
  const [usersRoleFilter, setUsersRoleFilter] = useState<string>('all');
  const [usersActivityFilter, setUsersActivityFilter] = useState<string>('all');
  const [usersStartDate, setUsersStartDate] = useState<string>('');
  const [usersEndDate, setUsersEndDate] = useState<string>('');
  const [usersSortBy, setUsersSortBy] = useState<string>('created_at');
  const [usersSortOrder, setUsersSortOrder] = useState<'desc' | 'asc'>('desc');
  const [isUsersLoading, setIsUsersLoading] = useState<boolean>(false);
  const [usersError, setUsersError] = useState<string | null>(null);

  // Datasets Tab State
  const [datasets, setDatasets] = useState<AdminDatasetItem[]>([]);
  const [datasetsTotal, setDatasetsTotal] = useState<number>(0);
  const [availableDomains, setAvailableDomains] = useState<string[]>([]);
  const [datasetsPage, setDatasetsPage] = useState<number>(1);
  const [datasetsSearch, setDatasetsSearch] = useState<string>('');
  const [datasetsDomainFilter, setDatasetsDomainFilter] = useState<string>('all');
  const [datasetsAvailabilityFilter, setDatasetsAvailabilityFilter] = useState<string>('all');
  const [datasetsSortBy, setDatasetsSortBy] = useState<string>('created_at');
  const [datasetsSortOrder, setDatasetsSortOrder] = useState<'desc' | 'asc'>('desc');
  const [isDatasetsLoading, setIsDatasetsLoading] = useState<boolean>(false);
  const [datasetsError, setDatasetsError] = useState<string | null>(null);

  // Queries Tab State
  const [queries, setQueries] = useState<AdminQueryItem[]>([]);
  const [queriesTotal, setQueriesTotal] = useState<number>(0);
  const [queriesSummary, setQueriesSummary] = useState<{
    total_queries: number;
    successful_queries: number;
    failed_queries: number;
    success_rate: number;
    avg_execution_time_ms: number;
    total_credits_charged: number;
  } | null>(null);
  const [queriesPage, setQueriesPage] = useState<number>(1);
  const [queriesSearch, setQueriesSearch] = useState<string>('');
  const [queriesStatusFilter, setQueriesStatusFilter] = useState<string>('All');
  const [queriesStartDate, setQueriesStartDate] = useState<string>('');
  const [queriesEndDate, setQueriesEndDate] = useState<string>('');
  const [queriesSortOrder, setQueriesSortOrder] = useState<'desc' | 'asc'>('desc');
  const [expandedQueryId, setExpandedQueryId] = useState<string | null>(null);
  const [isQueriesLoading, setIsQueriesLoading] = useState<boolean>(false);
  const [queriesError, setQueriesError] = useState<string | null>(null);
  const [copiedSqlId, setCopiedSqlId] = useState<string | null>(null);

  // Credit Ledger Tab State
  const [transactions, setTransactions] = useState<AdminTransactionItem[]>([]);
  const [transactionsTotal, setTransactionsTotal] = useState<number>(0);
  const [transactionsSummary, setTransactionsSummary] = useState<{
    total_issued: number;
    total_spent: number;
    net_movement: number;
    earned_by_owners: number;
    query_fees_collected: number;
    refunds_total: number;
  } | null>(null);
  const [transactionsPage, setTransactionsPage] = useState<number>(1);
  const [transactionsSearch, setTransactionsSearch] = useState<string>('');
  const [transactionsTypeFilter, setTransactionsTypeFilter] = useState<string>('all');
  const [transactionsDirectionFilter, setTransactionsDirectionFilter] = useState<string>('all');
  const [transactionsStartDate, setTransactionsStartDate] = useState<string>('');
  const [transactionsEndDate, setTransactionsEndDate] = useState<string>('');
  const [transactionsSortOrder, setTransactionsSortOrder] = useState<'desc' | 'asc'>('desc');
  const [isTransactionsLoading, setIsTransactionsLoading] = useState<boolean>(false);
  const [transactionsError, setTransactionsError] = useState<string | null>(null);

  // Global Activity Explorer State
  const [activityItems, setActivityItems] = useState<AdminTimelineItem[]>([]);
  const [activityTotal, setActivityTotal] = useState<number>(0);
  const [activityPage, setActivityPage] = useState<number>(1);
  const [activitySearch, setActivitySearch] = useState<string>('');
  const [activityTypeFilter, setActivityTypeFilter] = useState<string>('all');
  const [activityStatusFilter, setActivityStatusFilter] = useState<string>('All');
  const [activityStartDate, setActivityStartDate] = useState<string>('');
  const [activityEndDate, setActivityEndDate] = useState<string>('');
  const [activitySortOrder, setActivitySortOrder] = useState<'desc' | 'asc'>('desc');
  const [isActivityLoading, setIsActivityLoading] = useState<boolean>(false);
  const [activityError, setActivityError] = useState<string | null>(null);

  // Audit Logs State
  const [auditLogs, setAuditLogs] = useState<AdminAuditLogItem[]>([]);
  const [auditTotal, setAuditTotal] = useState<number>(0);
  const [auditPage, setAuditPage] = useState<number>(1);
  const [auditActionFilter, setAuditActionFilter] = useState<string>('All');
  const [auditSearch, setAuditSearch] = useState<string>('');
  const [isAuditLoading, setIsAuditLoading] = useState<boolean>(false);
  const [auditError, setAuditError] = useState<string | null>(null);

  // Auth State
  const [accessDenied, setAccessDenied] = useState<boolean>(false);

  // 1. Fetch Overview & Analytics
  const fetchOverviewAndAnalytics = useCallback(async () => {
    setIsOverviewLoading(true);
    setOverviewError(null);
    const rangeParams = {
      range: dateRange,
      start_date: dateRange === 'custom' && customStartDate ? customStartDate : undefined,
      end_date: dateRange === 'custom' && customEndDate ? customEndDate : undefined,
    };
    try {
      const [ov, an] = await Promise.all([
        api.admin.getOverview(rangeParams),
        api.admin.getAnalytics({ ...rangeParams, granularity }),
      ]);
      setOverview(ov);
      setAnalytics(an);
      setAccessDenied(false);
    } catch (err: any) {
      if (err instanceof ApiError && err.status === 403) {
        setAccessDenied(true);
      } else {
        setOverviewError(err.message || 'Failed to load platform analytics.');
      }
    } finally {
      setIsOverviewLoading(false);
    }
  }, [dateRange, customStartDate, customEndDate, granularity]);

  // 2. Fetch Users
  const fetchUsers = useCallback(async () => {
    setIsUsersLoading(true);
    setUsersError(null);
    try {
      const res = await api.admin.getUsers({
        page: usersPage,
        limit: 15,
        search: usersSearch,
        role: usersRoleFilter,
        activity: usersActivityFilter,
        start_date: usersStartDate || undefined,
        end_date: usersEndDate || undefined,
        sort_by: usersSortBy,
        sort_order: usersSortOrder,
      });
      setUsers(res.items || []);
      setUsersTotal(res.total || 0);
    } catch (err: any) {
      if (err instanceof ApiError && err.status === 403) setAccessDenied(true);
      else setUsersError(err.message || 'Failed to load registered users.');
    } finally {
      setIsUsersLoading(false);
    }
  }, [
    usersPage,
    usersSearch,
    usersRoleFilter,
    usersActivityFilter,
    usersStartDate,
    usersEndDate,
    usersSortBy,
    usersSortOrder,
  ]);

  // 3. Fetch Datasets
  const fetchDatasets = useCallback(async () => {
    setIsDatasetsLoading(true);
    setDatasetsError(null);
    try {
      const res = await api.admin.getDatasets({
        page: datasetsPage,
        limit: 15,
        search: datasetsSearch,
        domain: datasetsDomainFilter,
        availability: datasetsAvailabilityFilter,
        sort_by: datasetsSortBy,
        sort_order: datasetsSortOrder,
      });
      setDatasets(res.items || []);
      setDatasetsTotal(res.total || 0);
      if (res.available_domains && res.available_domains.length > 0) {
        setAvailableDomains(res.available_domains);
      }
    } catch (err: any) {
      if (err instanceof ApiError && err.status === 403) setAccessDenied(true);
      else setDatasetsError(err.message || 'Failed to load dataset registry.');
    } finally {
      setIsDatasetsLoading(false);
    }
  }, [
    datasetsPage,
    datasetsSearch,
    datasetsDomainFilter,
    datasetsAvailabilityFilter,
    datasetsSortBy,
    datasetsSortOrder,
  ]);

  // 4. Fetch Queries
  const fetchQueries = useCallback(async () => {
    setIsQueriesLoading(true);
    setQueriesError(null);
    try {
      const res = await api.admin.getQueries({
        page: queriesPage,
        limit: 15,
        search: queriesSearch,
        status: queriesStatusFilter,
        start_date: queriesStartDate || undefined,
        end_date: queriesEndDate || undefined,
        sort_order: queriesSortOrder,
      });
      setQueries(res.items || []);
      setQueriesTotal(res.total || 0);
      setQueriesSummary(res.summary || null);
    } catch (err: any) {
      if (err instanceof ApiError && err.status === 403) setAccessDenied(true);
      else setQueriesError(err.message || 'Failed to load query executions.');
    } finally {
      setIsQueriesLoading(false);
    }
  }, [
    queriesPage,
    queriesSearch,
    queriesStatusFilter,
    queriesStartDate,
    queriesEndDate,
    queriesSortOrder,
  ]);

  // 5. Fetch Transactions
  const fetchTransactions = useCallback(async () => {
    setIsTransactionsLoading(true);
    setTransactionsError(null);
    try {
      const res = await api.admin.getTransactions({
        page: transactionsPage,
        limit: 15,
        search: transactionsSearch,
        transaction_type: transactionsTypeFilter,
        direction: transactionsDirectionFilter,
        start_date: transactionsStartDate || undefined,
        end_date: transactionsEndDate || undefined,
        sort_order: transactionsSortOrder,
      });
      setTransactions(res.items || []);
      setTransactionsTotal(res.total || 0);
      setTransactionsSummary(res.summary || null);
    } catch (err: any) {
      if (err instanceof ApiError && err.status === 403) setAccessDenied(true);
      else setTransactionsError(err.message || 'Failed to load credit ledger.');
    } finally {
      setIsTransactionsLoading(false);
    }
  }, [
    transactionsPage,
    transactionsSearch,
    transactionsTypeFilter,
    transactionsDirectionFilter,
    transactionsStartDate,
    transactionsEndDate,
    transactionsSortOrder,
  ]);

  // 6. Fetch Global Activity
  const fetchGlobalActivity = useCallback(async () => {
    setIsActivityLoading(true);
    setActivityError(null);
    try {
      const res = await api.admin.getGlobalActivity({
        page: activityPage,
        limit: 20,
        search: activitySearch,
        activity_type: activityTypeFilter,
        status: activityStatusFilter,
        start_date: activityStartDate || undefined,
        end_date: activityEndDate || undefined,
        sort_order: activitySortOrder,
      });
      setActivityItems(res.items || []);
      setActivityTotal(res.total || 0);
    } catch (err: any) {
      if (err instanceof ApiError && err.status === 403) setAccessDenied(true);
      else setActivityError(err.message || 'Failed to load global activity stream.');
    } finally {
      setIsActivityLoading(false);
    }
  }, [
    activityPage,
    activitySearch,
    activityTypeFilter,
    activityStatusFilter,
    activityStartDate,
    activityEndDate,
    activitySortOrder,
  ]);

  // 7. Fetch Audit Logs
  const fetchAuditLogs = useCallback(async () => {
    setIsAuditLoading(true);
    setAuditError(null);
    try {
      const res = await api.admin.getAuditLogs({
        page: auditPage,
        limit: 20,
        action: auditActionFilter,
        search: auditSearch,
      });
      setAuditLogs(res.items || []);
      setAuditTotal(res.total || 0);
    } catch (err: any) {
      if (err instanceof ApiError && err.status === 403) setAccessDenied(true);
      else setAuditError(err.message || 'Failed to load audit logs.');
    } finally {
      setIsAuditLoading(false);
    }
  }, [auditPage, auditActionFilter, auditSearch]);

  // Load baseline analytics once on mount (used by Overview, Query Analytics, Credit Analytics)
  useEffect(() => {
    fetchOverviewAndAnalytics();
  }, [fetchOverviewAndAnalytics]);

  // Tab-specific fetches
  useEffect(() => {
    if (activeTab === 'users') fetchUsers();
    else if (activeTab === 'datasets') fetchDatasets();
    else if (activeTab === 'queries') fetchQueries();
    else if (activeTab === 'transactions') fetchTransactions();
    else if (activeTab === 'activity') fetchGlobalActivity();
    else if (activeTab === 'audit') fetchAuditLogs();
  }, [
    activeTab,
    fetchUsers,
    fetchDatasets,
    fetchQueries,
    fetchTransactions,
    fetchGlobalActivity,
    fetchAuditLogs,
  ]);

  const copyToClipboard = (text: string, id: string) => {
    navigator.clipboard.writeText(text);
    setCopiedSqlId(id);
    setTimeout(() => setCopiedSqlId(null), 1800);
  };

  const refreshActiveTab = () => {
    if (activeTab === 'overview') fetchOverviewAndAnalytics();
    else if (activeTab === 'users') fetchUsers();
    else if (activeTab === 'datasets') fetchDatasets();
    else if (activeTab === 'queries') {
      fetchQueries();
      fetchOverviewAndAnalytics();
    } else if (activeTab === 'transactions') {
      fetchTransactions();
      fetchOverviewAndAnalytics();
    } else if (activeTab === 'activity') fetchGlobalActivity();
    else if (activeTab === 'audit') fetchAuditLogs();
  };

  const isCurrentTabLoading =
    isOverviewLoading ||
    isUsersLoading ||
    isDatasetsLoading ||
    isQueriesLoading ||
    isTransactionsLoading ||
    isActivityLoading ||
    isAuditLoading;

  // 403 Access Denied View
  if (accessDenied) {
    return (
      <div className="max-w-3xl mx-auto py-16 px-4 text-center">
        <div className="w-16 h-16 rounded-2xl bg-rose-50 border border-rose-200 text-rose-600 flex items-center justify-center mx-auto mb-6">
          <AlertTriangle className="w-8 h-8" />
        </div>
        <h1 className="text-2xl font-black text-slate-900 mb-2">Access Denied (HTTP 403)</h1>
        <p className="text-sm text-slate-600 max-w-md mx-auto mb-6 leading-relaxed">
          Administrative authorization required. Your authenticated account (
          <span className="font-mono text-slate-800">{currentUser.email}</span>) does not possess
          verified platform administrator privileges.
        </p>
        <button
          type="button"
          onClick={() => onNavigate('dashboard')}
          className="px-4 py-2 rounded-xl bg-slate-900 text-white text-xs font-semibold hover:bg-slate-800 transition-colors cursor-pointer inline-flex items-center gap-2"
        >
          <ArrowLeft className="w-4 h-4" />
          <span>Return to Dashboard</span>
        </button>
      </div>
    );
  }

  const kpis = analytics?.kpis;
  const comparisonLabel = analytics?.comparison_label;

  return (
    <div className="space-y-6 max-w-[1600px] mx-auto pb-16">
      {/* Header Bar */}
      <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-2xs flex flex-col lg:flex-row lg:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2.5 mb-1.5">
            <span className="px-2.5 py-0.5 rounded-md bg-amber-50 border border-amber-200 text-amber-800 text-[11px] font-bold inline-flex items-center gap-1.5 uppercase tracking-wider">
              <ShieldCheck className="w-3.5 h-3.5 text-amber-600" />
              Platform Control Center
            </span>
            <span className="text-xs text-slate-400 font-mono hidden sm:inline">
              {currentUser.email}
            </span>
          </div>
          <h1 className="text-2xl font-extrabold text-slate-900 tracking-tight">
            Platform Administration & Telemetry
          </h1>
          <p className="text-xs sm:text-sm text-slate-500 mt-0.5">
            Unified analytics, account governance, dataset inspection, SQL execution logs, and credit ledger telemetry.
          </p>
        </div>

        <div className="flex items-center gap-2.5 shrink-0">
          <button
            type="button"
            onClick={refreshActiveTab}
            className="px-3.5 py-2 rounded-xl border border-slate-200 hover:bg-slate-50 text-slate-700 text-xs font-semibold transition-colors cursor-pointer inline-flex items-center gap-2"
            title="Refresh active section"
          >
            <RefreshCw className={`w-3.5 h-3.5 text-slate-500 ${isCurrentTabLoading ? 'animate-spin' : ''}`} />
            <span>Refresh</span>
          </button>
        </div>
      </div>

      {/* Navigation Tabs */}
      <div className="flex items-center gap-1.5 border-b border-slate-200 pb-2.5 overflow-x-auto text-xs font-semibold">
        {[
          { id: 'overview', label: 'Platform Overview', icon: <Layers className="w-4 h-4" /> },
          { id: 'users', label: 'Registered Users', icon: <Users className="w-4 h-4" />, count: overview?.total_users },
          { id: 'datasets', label: 'Dataset Registry', icon: <Database className="w-4 h-4" />, count: overview?.total_datasets },
          { id: 'queries', label: 'Global Query History', icon: <Search className="w-4 h-4" />, count: overview?.total_queries },
          { id: 'transactions', label: 'Credit Ledger', icon: <Coins className="w-4 h-4" /> },
          { id: 'activity', label: 'Activity Timeline', icon: <Clock className="w-4 h-4" /> },
          { id: 'audit', label: 'Audit Logs', icon: <Activity className="w-4 h-4" /> },
        ].map((tab) => {
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              type="button"
              onClick={() => setActiveTab(tab.id as AdminTab)}
              className={`px-3.5 py-2 rounded-xl transition-colors cursor-pointer flex items-center gap-2 whitespace-nowrap ${
                isActive
                  ? 'bg-slate-900 text-white font-bold shadow-2xs'
                  : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
              }`}
            >
              {tab.icon}
              <span>{tab.label}</span>
              {typeof tab.count === 'number' && (
                <span
                  className={`text-[10px] px-1.5 py-0.5 rounded-full font-mono ${
                    isActive ? 'bg-slate-800 text-slate-200' : 'bg-slate-200/80 text-slate-700'
                  }`}
                >
                  {tab.count.toLocaleString()}
                </span>
              )}
            </button>
          );
        })}
      </div>

      {/* ===================================================================== */}
      {/* TAB 1: PLATFORM OVERVIEW (PHASE 1)                                    */}
      {/* ===================================================================== */}
      {activeTab === 'overview' && (
        <div className="space-y-6">
          {/* Date Range & Granularity Controls */}
          <div className="bg-white border border-slate-200 rounded-2xl p-4 shadow-2xs flex flex-col lg:flex-row lg:items-center justify-between gap-3">
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="text-xs font-semibold text-slate-500 mr-1.5 inline-flex items-center gap-1">
                <Calendar className="w-3.5 h-3.5 text-slate-400" />
                Range:
              </span>
              {(
                [
                  { id: '7d', label: 'Last 7 days' },
                  { id: '30d', label: 'Last 30 days' },
                  { id: '90d', label: 'Last 90 days' },
                  { id: 'all', label: 'All time' },
                  { id: 'custom', label: 'Custom' },
                ] as Array<{ id: DateRangePreset; label: string }>
              ).map((preset) => (
                <button
                  key={preset.id}
                  type="button"
                  onClick={() => setDateRange(preset.id)}
                  className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors cursor-pointer ${
                    dateRange === preset.id
                      ? 'bg-indigo-600 text-white'
                      : 'bg-slate-50 text-slate-600 hover:bg-slate-100 border border-slate-200/70'
                  }`}
                >
                  {preset.label}
                </button>
              ))}
              {dateRange === 'custom' && (
                <div className="flex items-center gap-1.5 ml-1">
                  <input
                    type="date"
                    value={customStartDate}
                    onChange={(e) => setCustomStartDate(e.target.value)}
                    className="px-2.5 py-1 rounded-lg border border-slate-200 text-xs text-slate-700"
                  />
                  <span className="text-xs text-slate-400">to</span>
                  <input
                    type="date"
                    value={customEndDate}
                    onChange={(e) => setCustomEndDate(e.target.value)}
                    className="px-2.5 py-1 rounded-lg border border-slate-200 text-xs text-slate-700"
                  />
                </div>
              )}
            </div>

            <div className="flex items-center gap-1.5 text-xs">
              <span className="text-slate-500 font-semibold mr-1">Interval:</span>
              {(['daily', 'weekly', 'monthly'] as Granularity[]).map((g) => (
                <button
                  key={g}
                  type="button"
                  onClick={() => setGranularity(g)}
                  className={`px-2.5 py-1 rounded-lg capitalize font-semibold transition-colors cursor-pointer ${
                    granularity === g
                      ? 'bg-slate-900 text-white'
                      : 'bg-slate-50 text-slate-600 hover:bg-slate-100 border border-slate-200/70'
                  }`}
                >
                  {g}
                </button>
              ))}
            </div>
          </div>

          {overviewError && (
            <ErrorRetryBanner message={overviewError} onRetry={fetchOverviewAndAnalytics} />
          )}

          {/* 8 KPI Cards (4x2 responsive grid) */}
          {isOverviewLoading && !analytics ? (
            <KpiSkeletonGrid count={8} />
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
              {/* 1. Total Registered Users */}
              <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-2xs">
                <div className="flex items-center justify-between mb-3">
                  <span className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
                    Registered Users
                  </span>
                  <div className="w-8 h-8 rounded-lg bg-indigo-50 text-indigo-600 flex items-center justify-center">
                    <Users className="w-4 h-4" />
                  </div>
                </div>
                <div className="text-2xl font-black text-slate-900 font-mono">
                  {(kpis?.total_users ?? overview?.total_users ?? 0).toLocaleString()}
                </div>
                <div className="mt-2">
                  <DeltaBadge delta={kpis?.users_delta_pct} label={comparisonLabel} />
                </div>
              </div>

              {/* 2. Active Users */}
              <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-2xs">
                <div className="flex items-center justify-between mb-3">
                  <span className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
                    Active Users
                  </span>
                  <div className="w-8 h-8 rounded-lg bg-emerald-50 text-emerald-600 flex items-center justify-center">
                    <TrendingUp className="w-4 h-4" />
                  </div>
                </div>
                <div className="text-2xl font-black text-slate-900 font-mono">
                  {(kpis?.active_users ?? overview?.active_users ?? 0).toLocaleString()}
                </div>
                <div className="mt-2">
                  <DeltaBadge delta={kpis?.active_users_delta_pct} label={comparisonLabel} />
                </div>
              </div>

              {/* 3. Total Uploaded Datasets */}
              <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-2xs">
                <div className="flex items-center justify-between mb-3">
                  <span className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
                    Uploaded Datasets
                  </span>
                  <div className="w-8 h-8 rounded-lg bg-teal-50 text-teal-600 flex items-center justify-center">
                    <Database className="w-4 h-4" />
                  </div>
                </div>
                <div className="text-2xl font-black text-slate-900 font-mono">
                  {(kpis?.total_datasets ?? overview?.total_datasets ?? 0).toLocaleString()}
                </div>
                <div className="mt-2">
                  <DeltaBadge delta={kpis?.datasets_delta_pct} label={comparisonLabel} />
                </div>
              </div>

              {/* 4. Total Query Executions */}
              <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-2xs">
                <div className="flex items-center justify-between mb-3">
                  <span className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
                    Query Executions
                  </span>
                  <div className="w-8 h-8 rounded-lg bg-cyan-50 text-cyan-600 flex items-center justify-center">
                    <Search className="w-4 h-4" />
                  </div>
                </div>
                <div className="text-2xl font-black text-slate-900 font-mono">
                  {(kpis?.total_queries ?? overview?.total_queries ?? 0).toLocaleString()}
                </div>
                <div className="mt-2">
                  <DeltaBadge delta={kpis?.queries_delta_pct} label={comparisonLabel} />
                </div>
              </div>

              {/* 5. Successful vs Failed Queries */}
              <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-2xs">
                <div className="flex items-center justify-between mb-3">
                  <span className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
                    Success vs Failed Queries
                  </span>
                  <span className="text-xs font-mono font-bold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-md">
                    {(kpis?.query_success_rate ?? overview?.query_success_rate ?? 100).toFixed(1)}%
                  </span>
                </div>
                <div className="flex items-baseline gap-2.5 font-mono">
                  <span className="text-2xl font-black text-emerald-600">
                    {(kpis?.queries_successful ?? overview?.total_queries_successful ?? 0).toLocaleString()}
                  </span>
                  <span className="text-slate-300 text-lg">/</span>
                  <span className="text-xl font-bold text-rose-600">
                    {(kpis?.queries_failed ?? overview?.total_queries_failed ?? 0).toLocaleString()}
                  </span>
                </div>
                <div className="h-1.5 bg-rose-100 rounded-full mt-2.5 overflow-hidden">
                  <div
                    className="h-full bg-emerald-500 rounded-full"
                    style={{
                      width: `${Math.min(
                        100,
                        kpis?.query_success_rate ?? overview?.query_success_rate ?? 100
                      )}%`,
                    }}
                  />
                </div>
              </div>

              {/* 6. Total Credits Issued */}
              <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-2xs">
                <div className="flex items-center justify-between mb-3">
                  <span className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
                    Credits Issued
                  </span>
                  <div className="w-8 h-8 rounded-lg bg-amber-50 text-amber-600 flex items-center justify-center">
                    <ArrowUpRight className="w-4 h-4" />
                  </div>
                </div>
                <div className="text-2xl font-black text-emerald-700 font-mono">
                  +{(kpis?.total_credits_issued ?? overview?.total_credits_issued ?? 0).toLocaleString()} cr
                </div>
                <div className="mt-2">
                  <DeltaBadge delta={kpis?.credits_issued_delta_pct} label={comparisonLabel} />
                </div>
              </div>

              {/* 7. Total Credits Spent */}
              <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-2xs">
                <div className="flex items-center justify-between mb-3">
                  <span className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
                    Credits Spent
                  </span>
                  <div className="w-8 h-8 rounded-lg bg-rose-50 text-rose-600 flex items-center justify-center">
                    <ArrowDownRight className="w-4 h-4" />
                  </div>
                </div>
                <div className="text-2xl font-black text-rose-700 font-mono">
                  -{(kpis?.total_credits_spent ?? overview?.total_credits_spent ?? 0).toLocaleString()} cr
                </div>
                <div className="mt-2">
                  <DeltaBadge delta={kpis?.credits_spent_delta_pct} label={comparisonLabel} />
                </div>
              </div>

              {/* 8. Net Credit Movement */}
              <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-2xs">
                <div className="flex items-center justify-between mb-3">
                  <span className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
                    Net Credit Movement
                  </span>
                  <div className="w-8 h-8 rounded-lg bg-slate-100 text-slate-700 flex items-center justify-center">
                    <Coins className="w-4 h-4" />
                  </div>
                </div>
                <div className="text-2xl font-black text-slate-900 font-mono">
                  {(kpis?.net_credit_movement ?? overview?.net_credit_movement ?? 0) >= 0 ? '+' : ''}
                  {(kpis?.net_credit_movement ?? overview?.net_credit_movement ?? 0).toLocaleString()} cr
                </div>
                <p className="text-[11px] text-slate-500 mt-1.5 font-mono">
                  Liability: {(kpis?.net_credit_liability ?? overview?.net_credit_liability ?? 0).toLocaleString()} cr
                </p>
              </div>
            </div>
          )}

          {/* Time-Series Analytics Grid */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <AreaTrendChart
              title="User Registration Trend"
              subtitle={`New accounts grouped ${granularity}`}
              color="#4f46e5"
              unit="users"
              loading={isOverviewLoading}
              data={(analytics?.user_registration_trend || []).map((p) => ({
                bucket: p.bucket,
                value: p.count,
              }))}
            />
            <AreaTrendChart
              title="Dataset Upload Trend"
              subtitle={`Structured CSV datasets contributed (${granularity})`}
              color="#10b981"
              unit="datasets"
              loading={isOverviewLoading}
              data={(analytics?.dataset_upload_trend || []).map((p) => ({
                bucket: p.bucket,
                value: p.count,
              }))}
            />
            <MultiBarChart
              title="Query Activity"
              subtitle="Successful vs failed SQL executions over time"
              loading={isOverviewLoading}
              legend={[
                { key: 'successful', label: 'Successful', color: '#10b981' },
                { key: 'failed', label: 'Failed', color: '#f43f5e' },
              ]}
              data={(analytics?.query_activity_trend || []).map((p) => ({
                bucket: p.bucket,
                values: [
                  { key: 'successful', label: 'Successful', value: p.successful, color: '#10b981' },
                  { key: 'failed', label: 'Failed', value: p.failed, color: '#f43f5e' },
                ],
              }))}
            />
            <MultiBarChart
              title="Credit Movement"
              subtitle="Credits awarded, spent, and refunded over time"
              loading={isOverviewLoading}
              unit="cr"
              legend={[
                { key: 'awarded', label: 'Awarded', color: '#4f46e5' },
                { key: 'spent', label: 'Spent', color: '#f59e0b' },
                { key: 'refunded', label: 'Refunded', color: '#06b6d4' },
              ]}
              data={(analytics?.credit_movement_trend || []).map((p) => ({
                bucket: p.bucket,
                values: [
                  { key: 'awarded', label: 'Awarded', value: p.awarded, color: '#4f46e5' },
                  { key: 'spent', label: 'Spent', value: p.spent, color: '#f59e0b' },
                  { key: 'refunded', label: 'Refunded', value: p.refunded, color: '#06b6d4' },
                ],
              }))}
            />
          </div>

          {/* Ranked Leaderboards */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            <HorizontalRankChart
              title="Most Active Users"
              subtitle="Ranked by query executions — click to inspect"
              barColorClass="bg-cyan-500"
              loading={isOverviewLoading}
              emptyText="No user query activity in this period."
              onItemClick={(id) => setSelectedUserId(id)}
              items={(analytics?.most_active_users || []).map((u) => ({
                id: u.user_id,
                title: u.full_name,
                subtitle: u.email,
                value: u.query_count,
                valueLabel: `${u.query_count} queries`,
                secondaryLabel: `${u.successful_queries} ok`,
              }))}
            />
            <HorizontalRankChart
              title="Most Contributing Users"
              subtitle="Ranked by dataset uploads — click to inspect"
              barColorClass="bg-emerald-500"
              loading={isOverviewLoading}
              emptyText="No dataset contributions in this period."
              onItemClick={(id) => setSelectedUserId(id)}
              items={(analytics?.most_contributing_users || []).map((u) => ({
                id: u.user_id,
                title: u.full_name,
                subtitle: u.email,
                value: u.dataset_count,
                valueLabel: `${u.dataset_count} ds`,
                secondaryLabel: u.avg_quality_score ? `avg ${u.avg_quality_score}` : undefined,
              }))}
            />
            <HorizontalRankChart
              title="Most Queried Datasets"
              subtitle="Highest analytical usage — click to inspect"
              barColorClass="bg-indigo-500"
              loading={isOverviewLoading}
              emptyText="No dataset queries recorded in this period."
              onItemClick={(id) => setSelectedDatasetId(id)}
              items={(analytics?.most_queried_datasets || []).map((d) => ({
                id: d.dataset_id,
                title: d.dataset_name,
                subtitle: `${d.domain}${d.owner_name ? ` • ${d.owner_name}` : ''}`,
                value: d.query_count,
                valueLabel: `${d.query_count} runs`,
                secondaryLabel: d.quality_score ? `score ${d.quality_score}` : undefined,
              }))}
            />
          </div>

          {/* Compact Recent Platform Activity Feed */}
          <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-2xs">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <Activity className="w-4 h-4 text-indigo-600" />
                <h2 className="text-sm font-bold text-slate-900">Recent Platform Activity</h2>
              </div>
              <button
                type="button"
                onClick={() => setActiveTab('activity')}
                className="text-xs font-semibold text-indigo-600 hover:text-indigo-800 cursor-pointer inline-flex items-center gap-1"
              >
                <span>Open Global Activity Explorer</span>
                <ArrowUpRight className="w-3.5 h-3.5" />
              </button>
            </div>

            {isOverviewLoading && !overview ? (
              <div className="space-y-2.5 py-2">
                {[1, 2, 3, 4].map((n) => (
                  <div key={n} className="h-10 bg-slate-100 rounded-lg animate-pulse" />
                ))}
              </div>
            ) : !overview?.recent_activity?.length ? (
              <div className="py-8 text-center text-xs text-slate-400">
                No platform activity recorded yet.
              </div>
            ) : (
              <div className="divide-y divide-slate-100">
                {overview.recent_activity.slice(0, 8).map((act) => {
                  const tagColors: Record<string, string> = {
                    USER_REGISTER: 'bg-indigo-50 text-indigo-700',
                    DATASET_UPLOAD: 'bg-emerald-50 text-emerald-700',
                    QUERY_EXECUTION: 'bg-cyan-50 text-cyan-700',
                    CREDIT_TRANSACTION: 'bg-amber-50 text-amber-700',
                  };
                  return (
                    <div
                      key={act.id}
                      className="py-2.5 flex items-center justify-between gap-4 text-xs"
                    >
                      <div className="flex items-center gap-3 min-w-0">
                        <span
                          className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase shrink-0 ${
                            tagColors[act.type] || 'bg-slate-100 text-slate-600'
                          }`}
                        >
                          {act.type.replace(/_/g, ' ')}
                        </span>
                        <div className="min-w-0">
                          <p className="font-medium text-slate-800 truncate">{act.description}</p>
                          {act.user_email && (
                            <button
                              type="button"
                              onClick={() => act.user_id && setSelectedUserId(act.user_id)}
                              className="text-[11px] text-slate-400 hover:text-indigo-600 font-mono truncate cursor-pointer"
                            >
                              {act.user_email}
                            </button>
                          )}
                        </div>
                      </div>
                      <span className="text-[11px] text-slate-400 font-mono shrink-0">
                        {new Date(act.timestamp).toLocaleString()}
                      </span>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      )}

      {/* ===================================================================== */}
      {/* TAB 2: REGISTERED USERS (PHASE 2)                                     */}
      {/* ===================================================================== */}
      {activeTab === 'users' && (
        <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-2xs space-y-4">
          {usersError && <ErrorRetryBanner message={usersError} onRetry={fetchUsers} />}

          {/* Toolbar */}
          <div className="flex flex-col xl:flex-row xl:items-center justify-between gap-3">
            <div className="relative flex-1 max-w-md">
              <Search className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" />
              <input
                type="text"
                placeholder="Search by name, email, or user ID..."
                value={usersSearch}
                onChange={(e) => {
                  setUsersSearch(e.target.value);
                  setUsersPage(1);
                }}
                className="w-full pl-9 pr-8 py-2 text-xs rounded-xl border border-slate-200 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500"
              />
              {usersSearch && (
                <button
                  type="button"
                  onClick={() => {
                    setUsersSearch('');
                    setUsersPage(1);
                  }}
                  className="absolute right-2.5 top-2.5 text-slate-400 hover:text-slate-600 cursor-pointer"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              )}
            </div>

            <div className="flex flex-wrap items-center gap-2 text-xs">
              <select
                value={usersRoleFilter}
                onChange={(e) => {
                  setUsersRoleFilter(e.target.value);
                  setUsersPage(1);
                }}
                className="px-2.5 py-2 rounded-xl border border-slate-200 bg-white text-slate-700"
              >
                <option value="all">All Roles</option>
                <option value="admin">Admins</option>
                <option value="user">Standard Users</option>
              </select>

              <select
                value={usersActivityFilter}
                onChange={(e) => {
                  setUsersActivityFilter(e.target.value);
                  setUsersPage(1);
                }}
                className="px-2.5 py-2 rounded-xl border border-slate-200 bg-white text-slate-700"
              >
                <option value="all">All Statuses</option>
                <option value="active">Active</option>
                <option value="inactive">Inactive</option>
                <option value="has_queries">Has Queries</option>
                <option value="has_datasets">Has Datasets</option>
              </select>

              <input
                type="date"
                value={usersStartDate}
                onChange={(e) => {
                  setUsersStartDate(e.target.value);
                  setUsersPage(1);
                }}
                className="px-2.5 py-1.5 rounded-xl border border-slate-200 text-xs text-slate-700"
                title="Registered from"
              />
              <input
                type="date"
                value={usersEndDate}
                onChange={(e) => {
                  setUsersEndDate(e.target.value);
                  setUsersPage(1);
                }}
                className="px-2.5 py-1.5 rounded-xl border border-slate-200 text-xs text-slate-700"
                title="Registered to"
              />

              <select
                value={usersSortBy}
                onChange={(e) => {
                  setUsersSortBy(e.target.value);
                  setUsersPage(1);
                }}
                className="px-2.5 py-2 rounded-xl border border-slate-200 bg-white text-slate-700"
              >
                <option value="created_at">Sort: Registration Date</option>
                <option value="last_activity">Sort: Last Activity</option>
                <option value="queries_count">Sort: Total Queries</option>
                <option value="datasets_count">Sort: Datasets Uploaded</option>
                <option value="credits">Sort: Credit Balance</option>
                <option value="reputation_score">Sort: Reputation</option>
              </select>

              <button
                type="button"
                onClick={() => {
                  setUsersSortOrder((o) => (o === 'desc' ? 'asc' : 'desc'));
                  setUsersPage(1);
                }}
                className="px-2.5 py-2 rounded-xl border border-slate-200 hover:bg-slate-50 text-slate-700 inline-flex items-center gap-1 cursor-pointer"
              >
                <ArrowUpDown className="w-3.5 h-3.5" />
                <span>{usersSortOrder.toUpperCase()}</span>
              </button>
            </div>
          </div>

          {/* Table */}
          <div className="border border-slate-100 rounded-xl overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-50 text-slate-500 font-semibold border-b border-slate-100">
                <tr>
                  <th className="py-3 px-4">User</th>
                  <th className="py-3 px-4">Status</th>
                  <th className="py-3 px-4">Credits</th>
                  <th className="py-3 px-4">Reputation</th>
                  <th className="py-3 px-4">Datasets</th>
                  <th className="py-3 px-4">Queries</th>
                  <th className="py-3 px-4">Last Activity</th>
                  <th className="py-3 px-4">Registered</th>
                  <th className="py-3 px-4 text-right">Profile</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 text-slate-700">
                {isUsersLoading ? (
                  <TableSkeletonRows cols={9} rows={8} />
                ) : users.length === 0 ? (
                  <tr>
                    <td colSpan={9} className="py-10 text-center text-slate-400">
                      No users match your search or filters.
                    </td>
                  </tr>
                ) : (
                  users.map((u) => (
                    <tr
                      key={u.id}
                      onClick={() => setSelectedUserId(u.id)}
                      className="hover:bg-slate-50/70 transition-colors cursor-pointer"
                    >
                      <td className="py-3 px-4">
                        <div className="font-bold text-slate-900">{u.full_name}</div>
                        <div className="text-[11px] text-slate-500 font-mono">{u.email}</div>
                        <div className="text-[10px] text-slate-400 font-mono">{u.id}</div>
                      </td>
                      <td className="py-3 px-4 whitespace-nowrap">
                        {u.is_admin ? (
                          <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-50 text-amber-700 border border-amber-200">
                            Admin
                          </span>
                        ) : u.is_active ? (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-50 text-emerald-700">
                            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                            Active
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-slate-100 text-slate-500">
                            <span className="w-1.5 h-1.5 rounded-full bg-slate-400" />
                            Inactive
                          </span>
                        )}
                      </td>
                      <td className="py-3 px-4 font-mono font-bold text-emerald-700 whitespace-nowrap">
                        {u.credits.toLocaleString()} cr
                      </td>
                      <td className="py-3 px-4 font-mono text-slate-700">{u.reputation_score}/100</td>
                      <td className="py-3 px-4 font-mono font-semibold text-slate-800">{u.datasets_count}</td>
                      <td className="py-3 px-4 font-mono font-semibold text-slate-800">{u.queries_count}</td>
                      <td className="py-3 px-4 text-[11px] text-slate-500 font-mono whitespace-nowrap">
                        {u.last_activity ? new Date(u.last_activity).toLocaleDateString() : '—'}
                      </td>
                      <td className="py-3 px-4 text-[11px] text-slate-400 font-mono whitespace-nowrap">
                        {new Date(u.created_at).toLocaleDateString()}
                      </td>
                      <td className="py-3 px-4 text-right whitespace-nowrap">
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            setSelectedUserId(u.id);
                          }}
                          className="px-2.5 py-1.5 rounded-lg border border-slate-200 hover:bg-indigo-50 hover:text-indigo-700 hover:border-indigo-200 transition-colors text-[11px] font-semibold cursor-pointer inline-flex items-center gap-1"
                        >
                          <Eye className="w-3 h-3" />
                          <span>View Profile</span>
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          <PaginationFooter
            page={usersPage}
            limit={15}
            total={usersTotal}
            itemCount={users.length}
            entityLabel="users"
            onPageChange={setUsersPage}
          />
        </div>
      )}

      {/* ===================================================================== */}
      {/* TAB 3: DATASET REGISTRY & ANALYTICS (PHASE 5)                         */}
      {/* ===================================================================== */}
      {activeTab === 'datasets' && (
        <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-2xs space-y-4">
          {datasetsError && <ErrorRetryBanner message={datasetsError} onRetry={fetchDatasets} />}

          <div className="flex flex-col xl:flex-row xl:items-center justify-between gap-3">
            <div className="relative flex-1 max-w-md">
              <Search className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" />
              <input
                type="text"
                placeholder="Search dataset name, ID, filename, domain, or owner..."
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

            <div className="flex flex-wrap items-center gap-2 text-xs">
              <select
                value={datasetsDomainFilter}
                onChange={(e) => {
                  setDatasetsDomainFilter(e.target.value);
                  setDatasetsPage(1);
                }}
                className="px-2.5 py-2 rounded-xl border border-slate-200 bg-white text-slate-700 capitalize"
              >
                <option value="all">All Domains</option>
                {(availableDomains.length > 0
                  ? availableDomains
                  : ['technology', 'finance', 'healthcare', 'retail', 'telecom', 'education', 'general']
                ).map((dom) => (
                  <option key={dom} value={dom} className="capitalize">
                    {dom}
                  </option>
                ))}
              </select>

              <select
                value={datasetsAvailabilityFilter}
                onChange={(e) => {
                  setDatasetsAvailabilityFilter(e.target.value);
                  setDatasetsPage(1);
                }}
                className="px-2.5 py-2 rounded-xl border border-slate-200 bg-white text-slate-700"
              >
                <option value="all">All Storage States</option>
                <option value="available">DuckDB Available</option>
                <option value="missing">Metadata Only</option>
              </select>

              <select
                value={datasetsSortBy}
                onChange={(e) => {
                  setDatasetsSortBy(e.target.value);
                  setDatasetsPage(1);
                }}
                className="px-2.5 py-2 rounded-xl border border-slate-200 bg-white text-slate-700"
              >
                <option value="created_at">Sort: Upload Date</option>
                <option value="quality_score">Sort: Quality Score</option>
                <option value="query_count">Sort: Query Usage</option>
                <option value="rows_count">Sort: Row Count</option>
                <option value="unlock_price">Sort: Unlock Price</option>
                <option value="name">Sort: Name</option>
              </select>

              <button
                type="button"
                onClick={() => {
                  setDatasetsSortOrder((o) => (o === 'desc' ? 'asc' : 'desc'));
                  setDatasetsPage(1);
                }}
                className="px-2.5 py-2 rounded-xl border border-slate-200 hover:bg-slate-50 text-slate-700 inline-flex items-center gap-1 cursor-pointer"
              >
                <ArrowUpDown className="w-3.5 h-3.5" />
                <span>{datasetsSortOrder.toUpperCase()}</span>
              </button>
            </div>
          </div>

          <div className="border border-slate-100 rounded-xl overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-50 text-slate-500 font-semibold border-b border-slate-100">
                <tr>
                  <th className="py-3 px-4">Dataset</th>
                  <th className="py-3 px-4">Owner</th>
                  <th className="py-3 px-4">Domain</th>
                  <th className="py-3 px-4">Dimensions</th>
                  <th className="py-3 px-4">Quality</th>
                  <th className="py-3 px-4">Unlock</th>
                  <th className="py-3 px-4">Queries</th>
                  <th className="py-3 px-4">Versions</th>
                  <th className="py-3 px-4">Storage</th>
                  <th className="py-3 px-4">Uploaded</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 text-slate-700">
                {isDatasetsLoading ? (
                  <TableSkeletonRows cols={10} rows={8} />
                ) : datasets.length === 0 ? (
                  <tr>
                    <td colSpan={10} className="py-10 text-center text-slate-400">
                      No datasets match your search criteria.
                    </td>
                  </tr>
                ) : (
                  datasets.map((d) => (
                    <tr
                      key={d.id}
                      onClick={() => setSelectedDatasetId(d.id)}
                      className="hover:bg-slate-50/70 transition-colors cursor-pointer"
                    >
                      <td className="py-3 px-4">
                        <div className="font-bold text-slate-900">{d.title}</div>
                        <div className="text-[11px] text-slate-400 font-mono">{d.filename}</div>
                      </td>
                      <td className="py-3 px-4">
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            setSelectedUserId(d.owner_id);
                          }}
                          className="font-semibold text-slate-800 hover:text-indigo-600 text-left cursor-pointer"
                        >
                          {d.owner_name}
                        </button>
                        <div className="text-[11px] text-slate-400 font-mono">{d.owner_email}</div>
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
                          <span className="text-slate-400">Pending</span>
                        )}
                      </td>
                      <td className="py-3 px-4 font-mono text-[11px] whitespace-nowrap">
                        <span className="font-semibold text-slate-800">{d.unlock_price} cr</span>
                        <span className="text-slate-400 ml-1">({d.unlock_count})</span>
                      </td>
                      <td className="py-3 px-4 font-mono font-semibold text-slate-800">
                        {d.query_count ?? 0}
                      </td>
                      <td className="py-3 px-4 font-mono text-[11px] text-slate-600">
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
                  ))
                )}
              </tbody>
            </table>
          </div>

          <PaginationFooter
            page={datasetsPage}
            limit={15}
            total={datasetsTotal}
            itemCount={datasets.length}
            entityLabel="datasets"
            onPageChange={setDatasetsPage}
          />
        </div>
      )}

      {/* ===================================================================== */}
      {/* TAB 4: QUERY ANALYTICS / GLOBAL QUERY HISTORY (PHASE 4)               */}
      {/* ===================================================================== */}
      {activeTab === 'queries' && (
        <div className="space-y-5">
          {/* Query KPI Summary */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <div className="bg-white border border-slate-200 rounded-2xl p-4 shadow-2xs">
              <span className="text-[10px] uppercase font-bold text-slate-400 tracking-wider">
                Total Executions
              </span>
              <div className="text-2xl font-black font-mono text-slate-900 mt-1">
                {(queriesSummary?.total_queries ?? overview?.total_queries ?? 0).toLocaleString()}
              </div>
              <span className="text-[11px] text-slate-400 font-mono">
                Avg {queriesSummary?.avg_execution_time_ms ?? 0}ms duration
              </span>
            </div>
            <div className="bg-white border border-slate-200 rounded-2xl p-4 shadow-2xs">
              <span className="text-[10px] uppercase font-bold text-slate-400 tracking-wider">
                Successful Queries
              </span>
              <div className="text-2xl font-black font-mono text-emerald-600 mt-1">
                {(queriesSummary?.successful_queries ?? overview?.total_queries_successful ?? 0).toLocaleString()}
              </div>
              <span className="text-[11px] text-slate-400">Validated & executed</span>
            </div>
            <div className="bg-white border border-slate-200 rounded-2xl p-4 shadow-2xs">
              <span className="text-[10px] uppercase font-bold text-slate-400 tracking-wider">
                Failed Queries
              </span>
              <div className="text-2xl font-black font-mono text-rose-600 mt-1">
                {(queriesSummary?.failed_queries ?? overview?.total_queries_failed ?? 0).toLocaleString()}
              </div>
              <span className="text-[11px] text-slate-400">Rejected or insufficient credits</span>
            </div>
            <div className="bg-white border border-slate-200 rounded-2xl p-4 shadow-2xs">
              <span className="text-[10px] uppercase font-bold text-slate-400 tracking-wider">
                Query Success Rate
              </span>
              <div className="text-2xl font-black font-mono text-slate-900 mt-1">
                {(queriesSummary?.success_rate ?? overview?.query_success_rate ?? 100).toFixed(1)}%
              </div>
              <span className="text-[11px] text-slate-400 font-mono">
                {(queriesSummary?.total_credits_charged ?? 0).toLocaleString()} cr charged
              </span>
            </div>
          </div>

          {/* Query Volume Trend + Leaderboards */}
          <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
            <div className="xl:col-span-2">
              <MultiBarChart
                title="Query Volume Trend"
                subtitle="Successful vs failed executions over time"
                loading={isOverviewLoading}
                legend={[
                  { key: 'successful', label: 'Successful', color: '#10b981' },
                  { key: 'failed', label: 'Failed', color: '#f43f5e' },
                ]}
                data={(analytics?.query_activity_trend || []).map((p) => ({
                  bucket: p.bucket,
                  values: [
                    { key: 'successful', label: 'Successful', value: p.successful, color: '#10b981' },
                    { key: 'failed', label: 'Failed', value: p.failed, color: '#f43f5e' },
                  ],
                }))}
              />
            </div>
            <HorizontalRankChart
              title="Most Queried Datasets"
              subtitle="Top analytical targets"
              barColorClass="bg-indigo-500"
              loading={isOverviewLoading}
              onItemClick={(id) => setSelectedDatasetId(id)}
              items={(analytics?.most_queried_datasets || []).slice(0, 5).map((d) => ({
                id: d.dataset_id,
                title: d.dataset_name,
                subtitle: d.domain,
                value: d.query_count,
                valueLabel: `${d.query_count}`,
              }))}
            />
          </div>

          {/* Query Audit Table */}
          <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-2xs space-y-4">
            {queriesError && <ErrorRetryBanner message={queriesError} onRetry={fetchQueries} />}

            <div className="flex flex-col xl:flex-row xl:items-center justify-between gap-3">
              <div className="relative flex-1 max-w-md">
                <Search className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" />
                <input
                  type="text"
                  placeholder="Search prompt, SQL, dataset, or user email..."
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
                  value={queriesStatusFilter}
                  onChange={(e) => {
                    setQueriesStatusFilter(e.target.value);
                    setQueriesPage(1);
                  }}
                  className="px-2.5 py-2 rounded-xl border border-slate-200 bg-white text-slate-700"
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
                />
                <input
                  type="date"
                  value={queriesEndDate}
                  onChange={(e) => {
                    setQueriesEndDate(e.target.value);
                    setQueriesPage(1);
                  }}
                  className="px-2.5 py-1.5 rounded-xl border border-slate-200 text-xs text-slate-700"
                />
                <button
                  type="button"
                  onClick={() => {
                    setQueriesSortOrder((o) => (o === 'desc' ? 'asc' : 'desc'));
                    setQueriesPage(1);
                  }}
                  className="px-2.5 py-2 rounded-xl border border-slate-200 hover:bg-slate-50 text-slate-700 inline-flex items-center gap-1 cursor-pointer"
                >
                  <ArrowUpDown className="w-3.5 h-3.5" />
                  <span>{queriesSortOrder === 'desc' ? 'Newest' : 'Oldest'}</span>
                </button>
              </div>
            </div>

            <div className="border border-slate-100 rounded-xl overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-50 text-slate-500 font-semibold border-b border-slate-100">
                  <tr>
                    <th className="py-3 px-4 w-8" />
                    <th className="py-3 px-4">User</th>
                    <th className="py-3 px-4">Prompt Preview</th>
                    <th className="py-3 px-4">Dataset</th>
                    <th className="py-3 px-4">Status</th>
                    <th className="py-3 px-4">Duration</th>
                    <th className="py-3 px-4">Credits</th>
                    <th className="py-3 px-4">Timestamp</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 text-slate-700">
                  {isQueriesLoading ? (
                    <TableSkeletonRows cols={8} rows={8} />
                  ) : queries.length === 0 ? (
                    <tr>
                      <td colSpan={8} className="py-10 text-center text-slate-400">
                        No query executions match your filters.
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
                            <td className="py-3 px-4">
                              <button
                                type="button"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  setSelectedUserId(q.user_id);
                                }}
                                className="font-semibold text-slate-800 hover:text-indigo-600 text-left cursor-pointer"
                              >
                                {q.user_name}
                              </button>
                              <div className="text-[11px] text-slate-400 font-mono">{q.user_email}</div>
                            </td>
                            <td className="py-3 px-4 max-w-sm">
                              <p className="font-medium text-slate-900 truncate" title={q.natural_prompt}>
                                {q.natural_prompt}
                              </p>
                              {q.error_message && (
                                <p className="text-[10px] text-rose-600 truncate mt-0.5">
                                  {q.error_message}
                                </p>
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
                              {q.execution_time_ms}ms
                            </td>
                            <td className="py-3 px-4 font-mono font-bold text-slate-800 whitespace-nowrap">
                              {q.credits_charged} cr
                            </td>
                            <td className="py-3 px-4 text-[11px] text-slate-400 font-mono whitespace-nowrap">
                              {new Date(q.timestamp).toLocaleString()}
                            </td>
                          </tr>
                          {isExpanded && (
                            <tr className="bg-slate-50/80">
                              <td colSpan={8} className="p-4 space-y-3">
                                <div className="flex flex-wrap items-center justify-between gap-2">
                                  <div className="text-xs font-semibold text-slate-800">
                                    Full Prompt: <span className="font-normal">{q.natural_prompt}</span>
                                  </div>
                                  <div className="flex items-center gap-2">
                                    <button
                                      type="button"
                                      onClick={(e) => {
                                        e.stopPropagation();
                                        setSelectedUserId(q.user_id);
                                      }}
                                      className="px-2.5 py-1 rounded-lg bg-white border border-slate-200 hover:bg-slate-100 text-[11px] font-semibold text-slate-700 inline-flex items-center gap-1 cursor-pointer"
                                    >
                                      <span>Inspect User</span>
                                      <ExternalLink className="w-3 h-3" />
                                    </button>
                                    {q.dataset_id && (
                                      <button
                                        type="button"
                                        onClick={(e) => {
                                          e.stopPropagation();
                                          setSelectedDatasetId(q.dataset_id!);
                                        }}
                                        className="px-2.5 py-1 rounded-lg bg-white border border-slate-200 hover:bg-slate-100 text-[11px] font-semibold text-indigo-700 inline-flex items-center gap-1 cursor-pointer"
                                      >
                                        <span>Inspect Dataset</span>
                                        <ExternalLink className="w-3 h-3" />
                                      </button>
                                    )}
                                    <button
                                      type="button"
                                      onClick={(e) => {
                                        e.stopPropagation();
                                        copyToClipboard(q.generated_sql || '', q.id);
                                      }}
                                      className="px-2.5 py-1 rounded-lg bg-white border border-slate-200 hover:bg-slate-100 text-[11px] font-semibold text-slate-700 inline-flex items-center gap-1 cursor-pointer"
                                    >
                                      {copiedSqlId === q.id ? (
                                        <>
                                          <Check className="w-3 h-3 text-emerald-600" />
                                          <span className="text-emerald-700">Copied SQL</span>
                                        </>
                                      ) : (
                                        <>
                                          <Copy className="w-3 h-3" />
                                          <span>Copy SQL</span>
                                        </>
                                      )}
                                    </button>
                                  </div>
                                </div>
                                <pre className="p-3 bg-slate-900 text-emerald-400 rounded-xl font-mono text-[11px] overflow-x-auto whitespace-pre-wrap leading-relaxed">
                                  {q.generated_sql || '-- No SQL generated'}
                                </pre>
                                <div className="flex flex-wrap gap-4 text-[11px] font-mono text-slate-500">
                                  <span>Query ID: {q.id}</span>
                                  <span>Rows Returned: {q.rows_returned}</span>
                                  <span>Execution Time: {q.execution_time_ms}ms</span>
                                  <span>Credits Charged: {q.credits_charged} cr</span>
                                  <span>Raw Dataset Content: Redacted</span>
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
              limit={15}
              total={queriesTotal}
              itemCount={queries.length}
              entityLabel="queries"
              onPageChange={setQueriesPage}
            />
          </div>
        </div>
      )}

      {/* ===================================================================== */}
      {/* TAB 5: CREDIT LEDGER & ANALYTICS (PHASE 6)                            */}
      {/* ===================================================================== */}
      {activeTab === 'transactions' && (
        <div className="space-y-5">
          {/* Credit Analytics Summary Cards */}
          <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
            <div className="bg-white border border-slate-200 rounded-2xl p-4 shadow-2xs">
              <span className="text-[10px] uppercase font-bold text-slate-400 tracking-wider">
                Total Credits Issued
              </span>
              <div className="text-xl font-black font-mono text-emerald-700 mt-1">
                +{(transactionsSummary?.total_issued ?? kpis?.total_credits_issued ?? 0).toLocaleString()} cr
              </div>
              <span className="text-[11px] text-slate-400">Matching ledger filter</span>
            </div>
            <div className="bg-white border border-slate-200 rounded-2xl p-4 shadow-2xs">
              <span className="text-[10px] uppercase font-bold text-slate-400 tracking-wider">
                Total Credits Spent
              </span>
              <div className="text-xl font-black font-mono text-rose-700 mt-1">
                -{(transactionsSummary?.total_spent ?? kpis?.total_credits_spent ?? 0).toLocaleString()} cr
              </div>
              <span className="text-[11px] text-slate-400">Fees, unlocks & payouts</span>
            </div>
            <div className="bg-white border border-slate-200 rounded-2xl p-4 shadow-2xs">
              <span className="text-[10px] uppercase font-bold text-slate-400 tracking-wider">
                Earned by Owners
              </span>
              <div className="text-xl font-black font-mono text-indigo-700 mt-1">
                +{(transactionsSummary?.earned_by_owners ?? kpis?.credits_earned_by_owners ?? 0).toLocaleString()} cr
              </div>
              <span className="text-[11px] text-slate-400">Upload, quality & royalties</span>
            </div>
            <div className="bg-white border border-slate-200 rounded-2xl p-4 shadow-2xs">
              <span className="text-[10px] uppercase font-bold text-slate-400 tracking-wider">
                Query Fees Collected
              </span>
              <div className="text-xl font-black font-mono text-slate-900 mt-1">
                {(transactionsSummary?.query_fees_collected ?? kpis?.query_fees_collected ?? 0).toLocaleString()} cr
              </div>
              <span className="text-[11px] text-slate-400">Cross-user query charges</span>
            </div>
            <div className="bg-white border border-slate-200 rounded-2xl p-4 shadow-2xs">
              <span className="text-[10px] uppercase font-bold text-slate-400 tracking-wider">
                Refunds
              </span>
              <div className="text-xl font-black font-mono text-cyan-700 mt-1">
                {(transactionsSummary?.refunds_total ?? kpis?.total_credits_refunded ?? 0).toLocaleString()} cr
              </div>
              <span className="text-[11px] text-slate-400">Recorded ledger refunds</span>
            </div>
          </div>

          <MultiBarChart
            title="Credit Transaction Trends"
            subtitle="Awarded, spent, and refunded credits across the platform"
            loading={isOverviewLoading}
            unit="cr"
            legend={[
              { key: 'awarded', label: 'Awarded', color: '#4f46e5' },
              { key: 'spent', label: 'Spent', color: '#f59e0b' },
              { key: 'refunded', label: 'Refunded', color: '#06b6d4' },
            ]}
            data={(analytics?.credit_movement_trend || []).map((p) => ({
              bucket: p.bucket,
              values: [
                { key: 'awarded', label: 'Awarded', value: p.awarded, color: '#4f46e5' },
                { key: 'spent', label: 'Spent', value: p.spent, color: '#f59e0b' },
                { key: 'refunded', label: 'Refunded', value: p.refunded, color: '#06b6d4' },
              ],
            }))}
          />

          {/* Ledger Table */}
          <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-2xs space-y-4">
            {transactionsError && (
              <ErrorRetryBanner message={transactionsError} onRetry={fetchTransactions} />
            )}

            <div className="flex flex-col xl:flex-row xl:items-center justify-between gap-3">
              <div className="relative flex-1 max-w-md">
                <Search className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" />
                <input
                  type="text"
                  placeholder="Search user name, email, user ID, or description..."
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
                  value={transactionsTypeFilter}
                  onChange={(e) => {
                    setTransactionsTypeFilter(e.target.value);
                    setTransactionsPage(1);
                  }}
                  className="px-2.5 py-2 rounded-xl border border-slate-200 bg-white text-slate-700"
                >
                  {TX_TYPE_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>

                <select
                  value={transactionsDirectionFilter}
                  onChange={(e) => {
                    setTransactionsDirectionFilter(e.target.value);
                    setTransactionsPage(1);
                  }}
                  className="px-2.5 py-2 rounded-xl border border-slate-200 bg-white text-slate-700"
                >
                  <option value="all">All Directions</option>
                  <option value="positive">Positive (+ Earned)</option>
                  <option value="negative">Negative (- Spent)</option>
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
                    setTransactionsSortOrder((o) => (o === 'desc' ? 'asc' : 'desc'));
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
                    <th className="py-3 px-4">User</th>
                    <th className="py-3 px-4">Type</th>
                    <th className="py-3 px-4">Amount</th>
                    <th className="py-3 px-4">Description</th>
                    <th className="py-3 px-4">Resource</th>
                    <th className="py-3 px-4 text-right">Balance After</th>
                    <th className="py-3 px-4">Timestamp</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 text-slate-700">
                  {isTransactionsLoading ? (
                    <TableSkeletonRows cols={7} rows={8} />
                  ) : transactions.length === 0 ? (
                    <tr>
                      <td colSpan={7} className="py-10 text-center text-slate-400">
                        No credit transactions match your filters.
                      </td>
                    </tr>
                  ) : (
                    transactions.map((t) => {
                      const isCredit = t.amount > 0;
                      return (
                        <tr key={t.id} className="hover:bg-slate-50/60 transition-colors">
                          <td className="py-3 px-4">
                            <button
                              type="button"
                              onClick={() => setSelectedUserId(t.user_id)}
                              className="font-semibold text-slate-800 hover:text-indigo-600 text-left cursor-pointer"
                            >
                              {t.user_name}
                            </button>
                            <div className="text-[11px] text-slate-400 font-mono">{t.user_email}</div>
                          </td>
                          <td className="py-3 px-4 whitespace-nowrap">
                            <span className="px-2 py-0.5 rounded text-[10px] font-bold uppercase bg-slate-100 text-slate-700">
                              {t.transaction_type.replace(/_/g, ' ')}
                            </span>
                          </td>
                          <td className="py-3 px-4 whitespace-nowrap">
                            <span
                              className={`inline-flex items-center gap-1 font-mono font-bold text-xs px-2 py-0.5 rounded-full ${
                                isCredit ? 'bg-emerald-50 text-emerald-700' : 'bg-rose-50 text-rose-700'
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
                          <td className="py-3 px-4 text-slate-700 max-w-sm truncate" title={t.description}>
                            {t.description}
                          </td>
                          <td className="py-3 px-4 text-[11px]">
                            {t.related_dataset_id ? (
                              <button
                                type="button"
                                onClick={() => setSelectedDatasetId(t.related_dataset_id!)}
                                className="text-indigo-600 hover:underline font-medium cursor-pointer truncate block max-w-[150px]"
                              >
                                {t.related_dataset_name || t.related_dataset_id}
                              </button>
                            ) : (
                              <span className="text-slate-400">{t.associated_resource || 'Account Ledger'}</span>
                            )}
                          </td>
                          <td className="py-3 px-4 text-right font-mono font-semibold text-slate-800 whitespace-nowrap">
                            {typeof t.balance_after === 'number'
                              ? `${t.balance_after.toLocaleString()} cr`
                              : '—'}
                          </td>
                          <td className="py-3 px-4 text-[11px] text-slate-400 font-mono whitespace-nowrap">
                            {new Date(t.timestamp).toLocaleString()}
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
              limit={15}
              total={transactionsTotal}
              itemCount={transactions.length}
              entityLabel="transactions"
              onPageChange={setTransactionsPage}
            />
          </div>
        </div>
      )}

      {/* ===================================================================== */}
      {/* TAB 6: GLOBAL ACTIVITY EXPLORER (PHASE 3)                             */}
      {/* ===================================================================== */}
      {activeTab === 'activity' && (
        <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-2xs space-y-4">
          {activityError && <ErrorRetryBanner message={activityError} onRetry={fetchGlobalActivity} />}

          <div className="flex flex-col xl:flex-row xl:items-center justify-between gap-3">
            <div className="relative flex-1 max-w-md">
              <Search className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" />
              <input
                type="text"
                placeholder="Search by user, email, dataset, or description..."
                value={activitySearch}
                onChange={(e) => {
                  setActivitySearch(e.target.value);
                  setActivityPage(1);
                }}
                className="w-full pl-9 pr-8 py-2 text-xs rounded-xl border border-slate-200 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500"
              />
              {activitySearch && (
                <button
                  type="button"
                  onClick={() => {
                    setActivitySearch('');
                    setActivityPage(1);
                  }}
                  className="absolute right-2.5 top-2.5 text-slate-400 hover:text-slate-600 cursor-pointer"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              )}
            </div>

            <div className="flex flex-wrap items-center gap-2 text-xs">
              <select
                value={activityTypeFilter}
                onChange={(e) => {
                  setActivityTypeFilter(e.target.value);
                  setActivityPage(1);
                }}
                className="px-2.5 py-2 rounded-xl border border-slate-200 bg-white text-slate-700"
              >
                <option value="all">All Activity Types</option>
                <option value="USER_REGISTER">Account Registrations</option>
                <option value="USER_LOGIN">Sign-In Sessions</option>
                <option value="DATASET_UPLOAD">Dataset Uploads</option>
                <option value="DATASET_IMPROVE">Dataset Improvements</option>
                <option value="DATASET_UNLOCK">Dataset Unlocks</option>
                <option value="QUERY_EXECUTION">All Queries</option>
                <option value="QUERY_SUCCESS">Successful Queries</option>
                <option value="QUERY_FAILED">Failed Queries</option>
                <option value="CREDIT_TRANSACTION">Credit Transactions</option>
                <option value="ADMIN_AUDIT">Admin Audits</option>
              </select>

              <select
                value={activityStatusFilter}
                onChange={(e) => {
                  setActivityStatusFilter(e.target.value);
                  setActivityPage(1);
                }}
                className="px-2.5 py-2 rounded-xl border border-slate-200 bg-white text-slate-700"
              >
                <option value="All">All Statuses</option>
                <option value="SUCCESS">Success</option>
                <option value="COMPLETED">Completed</option>
                <option value="FAILED">Failed</option>
                <option value="SQL_REJECTED">SQL Rejected</option>
                <option value="INSUFFICIENT_CREDITS">Insufficient Credits</option>
              </select>

              <input
                type="date"
                value={activityStartDate}
                onChange={(e) => {
                  setActivityStartDate(e.target.value);
                  setActivityPage(1);
                }}
                className="px-2.5 py-1.5 rounded-xl border border-slate-200 text-xs text-slate-700"
              />
              <input
                type="date"
                value={activityEndDate}
                onChange={(e) => {
                  setActivityEndDate(e.target.value);
                  setActivityPage(1);
                }}
                className="px-2.5 py-1.5 rounded-xl border border-slate-200 text-xs text-slate-700"
              />

              <button
                type="button"
                onClick={() => {
                  setActivitySortOrder((o) => (o === 'desc' ? 'asc' : 'desc'));
                  setActivityPage(1);
                }}
                className="px-2.5 py-2 rounded-xl border border-slate-200 hover:bg-slate-50 text-slate-700 inline-flex items-center gap-1 cursor-pointer"
              >
                <ArrowUpDown className="w-3.5 h-3.5" />
                <span>{activitySortOrder === 'desc' ? 'Newest first' : 'Oldest first'}</span>
              </button>
            </div>
          </div>

          <div className="border border-slate-100 rounded-xl overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-50 text-slate-500 font-semibold border-b border-slate-100">
                <tr>
                  <th className="py-3 px-4">Type</th>
                  <th className="py-3 px-4">User</th>
                  <th className="py-3 px-4">Description</th>
                  <th className="py-3 px-4">Resource</th>
                  <th className="py-3 px-4">Status</th>
                  <th className="py-3 px-4">Timestamp</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 text-slate-700">
                {isActivityLoading ? (
                  <TableSkeletonRows cols={6} rows={8} />
                ) : activityItems.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="py-10 text-center text-slate-400">
                      No platform events match your filters.
                    </td>
                  </tr>
                ) : (
                  activityItems.map((item) => {
                    const typeBadgeMap: Record<string, { label: string; cls: string }> = {
                      USER_REGISTER: { label: 'Register', cls: 'bg-indigo-50 text-indigo-700' },
                      USER_LOGIN: { label: 'Sign-In', cls: 'bg-sky-50 text-sky-700' },
                      DATASET_UPLOAD: { label: 'Upload', cls: 'bg-emerald-50 text-emerald-700' },
                      QUERY_EXECUTION: { label: 'Query', cls: 'bg-cyan-50 text-cyan-700' },
                      CREDIT_TRANSACTION: { label: 'Credits', cls: 'bg-amber-50 text-amber-700' },
                      DATASET_IMPROVE: { label: 'Improve', cls: 'bg-violet-50 text-violet-700' },
                      DATASET_UNLOCK: { label: 'Unlock', cls: 'bg-blue-50 text-blue-700' },
                      ADMIN_AUDIT: { label: 'Audit', cls: 'bg-rose-50 text-rose-700' },
                    };
                    const badge = typeBadgeMap[item.type] || {
                      label: item.type,
                      cls: 'bg-slate-100 text-slate-600',
                    };
                    const isOk =
                      item.status?.toUpperCase() === 'SUCCESS' ||
                      item.status?.toUpperCase() === 'COMPLETED';

                    return (
                      <tr
                        key={item.id}
                        onClick={() => setSelectedActivityItem(item)}
                        className="hover:bg-slate-50/70 transition-colors cursor-pointer"
                      >
                        <td className="py-3 px-4 whitespace-nowrap">
                          <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase ${badge.cls}`}>
                            {badge.label}
                          </span>
                        </td>
                        <td className="py-3 px-4">
                          {item.user_name || item.user_email ? (
                            <div>
                              <button
                                type="button"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  if (item.user_id) setSelectedUserId(item.user_id);
                                }}
                                className="font-semibold text-slate-800 hover:text-indigo-600 text-left cursor-pointer"
                              >
                                {item.user_name || 'User'}
                              </button>
                              <div className="text-[11px] text-slate-400 font-mono">
                                {item.user_email || item.user_id}
                              </div>
                            </div>
                          ) : (
                            <span className="text-slate-400">—</span>
                          )}
                        </td>
                        <td className="py-3 px-4 max-w-md">
                          <p className="font-medium text-slate-900 truncate" title={item.description}>
                            {item.description}
                          </p>
                        </td>
                        <td className="py-3 px-4 text-[11px] font-mono text-slate-500">
                          {item.dataset_name || item.dataset_id || item.related_query_id || item.related_transaction_id || '—'}
                        </td>
                        <td className="py-3 px-4 whitespace-nowrap">
                          <span
                            className={`px-2 py-0.5 rounded-full text-[10px] font-bold uppercase ${
                              isOk ? 'bg-emerald-50 text-emerald-700' : 'bg-rose-50 text-rose-700'
                            }`}
                          >
                            {item.status}
                          </span>
                        </td>
                        <td className="py-3 px-4 text-[11px] text-slate-400 font-mono whitespace-nowrap">
                          {new Date(item.timestamp).toLocaleString()}
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>

          <PaginationFooter
            page={activityPage}
            limit={20}
            total={activityTotal}
            itemCount={activityItems.length}
            entityLabel="events"
            onPageChange={setActivityPage}
          />
        </div>
      )}

      {/* ===================================================================== */}
      {/* TAB 7: AUDIT LOGS                                                     */}
      {/* ===================================================================== */}
      {activeTab === 'audit' && (
        <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-2xs space-y-4">
          {auditError && <ErrorRetryBanner message={auditError} onRetry={fetchAuditLogs} />}

          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div>
              <h2 className="text-sm font-bold text-slate-900">Administrative Governance & Audit Trail</h2>
              <p className="text-xs text-slate-500">Immutable record of administrative read and inspection events.</p>
            </div>
            <div className="flex items-center gap-2 text-xs">
              <div className="relative">
                <Search className="w-3.5 h-3.5 text-slate-400 absolute left-2.5 top-2.5" />
                <input
                  type="text"
                  placeholder="Search audit details..."
                  value={auditSearch}
                  onChange={(e) => {
                    setAuditSearch(e.target.value);
                    setAuditPage(1);
                  }}
                  className="pl-8 pr-3 py-1.5 rounded-xl border border-slate-200 text-xs focus:outline-none focus:border-indigo-500"
                />
              </div>
              <select
                value={auditActionFilter}
                onChange={(e) => {
                  setAuditActionFilter(e.target.value);
                  setAuditPage(1);
                }}
                className="px-2.5 py-1.5 rounded-xl border border-slate-200 bg-white text-slate-700"
              >
                <option value="All">All Actions</option>
                <option value="VIEW_OVERVIEW">VIEW_OVERVIEW</option>
                <option value="VIEW_ANALYTICS">VIEW_ANALYTICS</option>
                <option value="LIST_USERS">LIST_USERS</option>
                <option value="VIEW_USER_DETAIL">VIEW_USER_DETAIL</option>
                <option value="VIEW_DATASET_DETAIL">VIEW_DATASET_DETAIL</option>
                <option value="LIST_DATASETS">LIST_DATASETS</option>
                <option value="LIST_QUERIES">LIST_QUERIES</option>
                <option value="LIST_TRANSACTIONS">LIST_TRANSACTIONS</option>
                <option value="VIEW_GLOBAL_ACTIVITY">VIEW_GLOBAL_ACTIVITY</option>
              </select>
            </div>
          </div>

          <div className="border border-slate-100 rounded-xl overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-50 text-slate-500 font-semibold border-b border-slate-100">
                <tr>
                  <th className="py-3 px-4">Admin</th>
                  <th className="py-3 px-4">Action</th>
                  <th className="py-3 px-4">Target</th>
                  <th className="py-3 px-4">Details</th>
                  <th className="py-3 px-4">IP</th>
                  <th className="py-3 px-4">Timestamp</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 text-slate-700">
                {isAuditLoading ? (
                  <TableSkeletonRows cols={6} rows={8} />
                ) : auditLogs.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="py-10 text-center text-slate-400">
                      No administrative audit events recorded.
                    </td>
                  </tr>
                ) : (
                  auditLogs.map((log) => (
                    <tr key={log.id} className="hover:bg-slate-50/60 transition-colors">
                      <td className="py-3 px-4 font-mono font-semibold text-slate-800">{log.admin_email}</td>
                      <td className="py-3 px-4">
                        <span className="px-2 py-0.5 rounded text-[10px] font-bold uppercase bg-amber-50 text-amber-700">
                          {log.action}
                        </span>
                      </td>
                      <td className="py-3 px-4 font-mono text-[11px] text-slate-600">
                        {log.target_resource || '—'}
                      </td>
                      <td className="py-3 px-4 text-slate-600">{log.details || '—'}</td>
                      <td className="py-3 px-4 font-mono text-[11px] text-slate-400">
                        {log.ip_address || '—'}
                      </td>
                      <td className="py-3 px-4 text-[11px] text-slate-400 font-mono whitespace-nowrap">
                        {new Date(log.timestamp).toLocaleString()}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          <PaginationFooter
            page={auditPage}
            limit={20}
            total={auditTotal}
            itemCount={auditLogs.length}
            entityLabel="audit events"
            onPageChange={setAuditPage}
          />
        </div>
      )}

      {/* Subtle Data Transparency Note */}
      {analytics?.data_limitations && analytics.data_limitations.length > 0 && activeTab === 'overview' && (
        <div className="bg-slate-50 border border-slate-200/80 rounded-xl px-4 py-3 text-[11px] text-slate-500 flex items-start gap-2.5">
          <Info className="w-4 h-4 text-slate-400 shrink-0 mt-0.5" />
          <div className="space-y-0.5">
            {analytics.data_limitations.map((note, idx) => (
              <p key={idx}>{note}</p>
            ))}
          </div>
        </div>
      )}

      {/* DRAWERS */}
      {selectedUserId && (
        <UserHistoryExplorer
          userId={selectedUserId}
          onClose={() => setSelectedUserId(null)}
          onInspectDataset={(dsId) => setSelectedDatasetId(dsId)}
          addToast={addToast}
        />
      )}

      {selectedDatasetId && (
        <DatasetInspectionDrawer
          datasetId={selectedDatasetId}
          onClose={() => setSelectedDatasetId(null)}
          onInspectUser={(uid) => {
            setSelectedDatasetId(null);
            setSelectedUserId(uid);
          }}
        />
      )}

      {selectedActivityItem && (
        <ActivityDetailDrawer
          item={selectedActivityItem}
          onClose={() => setSelectedActivityItem(null)}
          onInspectUser={(uid) => setSelectedUserId(uid)}
          onInspectDataset={(dsId) => setSelectedDatasetId(dsId)}
        />
      )}
    </div>
  );
};
