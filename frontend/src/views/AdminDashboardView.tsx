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
  ChevronLeft,
  ChevronRight,
  RefreshCw,
  FileText,
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
} from 'lucide-react';
import {
  UserAccount,
  PageRoute,
  AdminOverview,
  AdminUserItem,
  AdminUserDetail,
  AdminDatasetItem,
  AdminQueryItem,
  AdminTransactionItem,
  AdminAuditLogItem,
} from '../types';
import { api, ApiError } from '../services/api';

interface AdminDashboardViewProps {
  currentUser: UserAccount;
  onNavigate: (route: PageRoute) => void;
  addToast?: (
    title: string,
    message: string,
    tone?: 'cyan' | 'rose' | 'amber' | 'emerald' | 'violet'
  ) => void;
}

type AdminTab = 'overview' | 'users' | 'datasets' | 'queries' | 'transactions' | 'audit';

export const AdminDashboardView: React.FC<AdminDashboardViewProps> = ({
  currentUser,
  onNavigate,
  addToast,
}) => {
  const [activeTab, setActiveTab] = useState<AdminTab>('overview');

  // Overview Data
  const [overview, setOverview] = useState<AdminOverview | null>(null);
  const [isOverviewLoading, setIsOverviewLoading] = useState<boolean>(true);

  // Users Tab State
  const [users, setUsers] = useState<AdminUserItem[]>([]);
  const [usersTotal, setUsersTotal] = useState<number>(0);
  const [usersPage, setUsersPage] = useState<number>(1);
  const [usersSearch, setUsersSearch] = useState<string>('');
  const [usersRoleFilter, setUsersRoleFilter] = useState<string>('all');
  const [isUsersLoading, setIsUsersLoading] = useState<boolean>(false);
  const [selectedUserDetail, setSelectedUserDetail] = useState<AdminUserDetail | null>(null);
  const [isDetailLoading, setIsDetailLoading] = useState<boolean>(false);

  // Datasets Tab State
  const [datasets, setDatasets] = useState<AdminDatasetItem[]>([]);
  const [datasetsTotal, setDatasetsTotal] = useState<number>(0);
  const [datasetsPage, setDatasetsPage] = useState<number>(1);
  const [datasetsSearch, setDatasetsSearch] = useState<string>('');
  const [datasetsDomainFilter, setDatasetsDomainFilter] = useState<string>('all');
  const [isDatasetsLoading, setIsDatasetsLoading] = useState<boolean>(false);

  // Global Queries Tab State
  const [queries, setQueries] = useState<AdminQueryItem[]>([]);
  const [queriesTotal, setQueriesTotal] = useState<number>(0);
  const [queriesPage, setQueriesPage] = useState<number>(1);
  const [queriesSearch, setQueriesSearch] = useState<string>('');
  const [queriesStatusFilter, setQueriesStatusFilter] = useState<string>('All');
  const [isQueriesLoading, setIsQueriesLoading] = useState<boolean>(false);
  const [copiedSqlId, setCopiedSqlId] = useState<string | null>(null);

  // Transactions Tab State
  const [transactions, setTransactions] = useState<AdminTransactionItem[]>([]);
  const [transactionsTotal, setTransactionsTotal] = useState<number>(0);
  const [transactionsPage, setTransactionsPage] = useState<number>(1);
  const [transactionsSearch, setTransactionsSearch] = useState<string>('');
  const [transactionsTypeFilter, setTransactionsTypeFilter] = useState<string>('all');
  const [isTransactionsLoading, setIsTransactionsLoading] = useState<boolean>(false);

  // Audit Logs Tab State
  const [auditLogs, setAuditLogs] = useState<AdminAuditLogItem[]>([]);
  const [auditTotal, setAuditTotal] = useState<number>(0);
  const [auditPage, setAuditPage] = useState<number>(1);
  const [isAuditLoading, setIsAuditLoading] = useState<boolean>(false);

  // General Error State (e.g. 403 Forbidden)
  const [accessDenied, setAccessDenied] = useState<boolean>(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // 1. Fetch Overview
  const fetchOverview = useCallback(async () => {
    setIsOverviewLoading(true);
    setErrorMessage(null);
    try {
      const data = await api.admin.getOverview();
      setOverview(data);
      setAccessDenied(false);
    } catch (err: any) {
      if (err instanceof ApiError && err.status === 403) {
        setAccessDenied(true);
      } else {
        setErrorMessage(err.message || 'Failed to load platform overview.');
      }
    } finally {
      setIsOverviewLoading(false);
    }
  }, []);

  // 2. Fetch Users
  const fetchUsers = useCallback(async () => {
    setIsUsersLoading(true);
    try {
      const res = await api.admin.getUsers({
        page: usersPage,
        limit: 15,
        search: usersSearch,
        role: usersRoleFilter,
      });
      setUsers(res.items || []);
      setUsersTotal(res.total || 0);
    } catch (err: any) {
      if (err instanceof ApiError && err.status === 403) setAccessDenied(true);
    } finally {
      setIsUsersLoading(false);
    }
  }, [usersPage, usersSearch, usersRoleFilter]);

  // 3. Fetch User Detail
  const handleOpenUserDetail = async (userId: string) => {
    setIsDetailLoading(true);
    try {
      const detail = await api.admin.getUserDetail(userId);
      setSelectedUserDetail(detail);
    } catch (err: any) {
      if (addToast) addToast('Error', err.message || 'Could not load user details.', 'rose');
    } finally {
      setIsDetailLoading(false);
    }
  };

  // 4. Fetch Datasets
  const fetchDatasets = useCallback(async () => {
    setIsDatasetsLoading(true);
    try {
      const res = await api.admin.getDatasets({
        page: datasetsPage,
        limit: 15,
        search: datasetsSearch,
        domain: datasetsDomainFilter,
      });
      setDatasets(res.items || []);
      setDatasetsTotal(res.total || 0);
    } catch (err: any) {
      if (err instanceof ApiError && err.status === 403) setAccessDenied(true);
    } finally {
      setIsDatasetsLoading(false);
    }
  }, [datasetsPage, datasetsSearch, datasetsDomainFilter]);

  // 5. Fetch Queries
  const fetchQueries = useCallback(async () => {
    setIsQueriesLoading(true);
    try {
      const res = await api.admin.getQueries({
        page: queriesPage,
        limit: 15,
        search: queriesSearch,
        status: queriesStatusFilter,
      });
      setQueries(res.items || []);
      setQueriesTotal(res.total || 0);
    } catch (err: any) {
      if (err instanceof ApiError && err.status === 403) setAccessDenied(true);
    } finally {
      setIsQueriesLoading(false);
    }
  }, [queriesPage, queriesSearch, queriesStatusFilter]);

  // 6. Fetch Transactions
  const fetchTransactions = useCallback(async () => {
    setIsTransactionsLoading(true);
    try {
      const res = await api.admin.getTransactions({
        page: transactionsPage,
        limit: 15,
        search: transactionsSearch,
        transaction_type: transactionsTypeFilter,
      });
      setTransactions(res.items || []);
      setTransactionsTotal(res.total || 0);
    } catch (err: any) {
      if (err instanceof ApiError && err.status === 403) setAccessDenied(true);
    } finally {
      setIsTransactionsLoading(false);
    }
  }, [transactionsPage, transactionsSearch, transactionsTypeFilter]);

  // 7. Fetch Audit Logs
  const fetchAuditLogs = useCallback(async () => {
    setIsAuditLoading(true);
    try {
      const res = await api.admin.getAuditLogs({
        page: auditPage,
        limit: 20,
      });
      setAuditLogs(res.items || []);
      setAuditTotal(res.total || 0);
    } catch (err: any) {
      if (err instanceof ApiError && err.status === 403) setAccessDenied(true);
    } finally {
      setIsAuditLoading(false);
    }
  }, [auditPage]);

  // Tab change triggers
  useEffect(() => {
    if (activeTab === 'overview') fetchOverview();
    else if (activeTab === 'users') fetchUsers();
    else if (activeTab === 'datasets') fetchDatasets();
    else if (activeTab === 'queries') fetchQueries();
    else if (activeTab === 'transactions') fetchTransactions();
    else if (activeTab === 'audit') fetchAuditLogs();
  }, [activeTab, fetchOverview, fetchUsers, fetchDatasets, fetchQueries, fetchTransactions, fetchAuditLogs]);

  const copyToClipboard = (text: string, id: string) => {
    navigator.clipboard.writeText(text);
    setCopiedSqlId(id);
    setTimeout(() => setCopiedSqlId(null), 2000);
  };

  // 403 Access Denied View
  if (accessDenied) {
    return (
      <div className="max-w-3xl mx-auto py-16 px-4 text-center">
        <div className="w-16 h-16 rounded-2xl bg-rose-50 border border-rose-200 text-rose-600 flex items-center justify-center mx-auto mb-6 shadow-sm">
          <AlertTriangle className="w-8 h-8" />
        </div>
        <h1 className="text-2xl font-black text-slate-900 mb-2">Access Denied (HTTP 403)</h1>
        <p className="text-sm text-slate-600 max-w-md mx-auto mb-6 leading-relaxed">
          Administrative authorization required. Your authenticated account (
          <span className="font-mono text-slate-800">{currentUser.email}</span>) does not possess
          verified platform administrator privileges.
        </p>
        <div className="flex items-center justify-center gap-3">
          <button
            onClick={() => onNavigate('dashboard')}
            className="px-4 py-2 rounded-xl bg-slate-900 text-white text-xs font-semibold hover:bg-slate-800 transition-colors cursor-pointer flex items-center gap-2"
          >
            <ArrowLeft className="w-4 h-4" />
            <span>Return to Dashboard</span>
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-[1600px] mx-auto pb-16">
      {/* Header Bar */}
      <div className="bg-white border border-slate-200 rounded-2xl p-6 sm:p-8 shadow-xs flex flex-col md:flex-row md:items-center justify-between gap-6">
        <div>
          <div className="flex items-center gap-2.5 mb-2">
            <span className="px-2.5 py-1 rounded-md bg-amber-50 border border-amber-200 text-amber-700 text-xs font-bold flex items-center gap-1.5 uppercase tracking-wider">
              <ShieldCheck className="w-3.5 h-3.5 text-amber-600" />
              Verified Administrator Portal
            </span>
            <span className="text-xs text-slate-400 font-mono hidden sm:inline">
              Backend-Enforced Role Security
            </span>
          </div>
          <h1 className="text-2xl sm:text-3xl font-extrabold text-slate-900 tracking-tight">
            Platform Administration & Telemetry
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            Global governance monitor for registered accounts, dataset registry, analytical SQL executions, and credit liabilities.
          </p>
        </div>

        <div className="flex items-center gap-3 shrink-0">
          <button
            onClick={() => {
              if (activeTab === 'overview') fetchOverview();
              else if (activeTab === 'users') fetchUsers();
              else if (activeTab === 'datasets') fetchDatasets();
              else if (activeTab === 'queries') fetchQueries();
              else if (activeTab === 'transactions') fetchTransactions();
              else if (activeTab === 'audit') fetchAuditLogs();
            }}
            className="px-3.5 py-2 rounded-xl border border-slate-200 hover:bg-slate-50 text-slate-700 text-xs font-semibold transition-colors cursor-pointer flex items-center gap-2 shadow-2xs"
            title="Refresh current view"
          >
            <RefreshCw
              className={`w-3.5 h-3.5 text-slate-500 ${
                isOverviewLoading || isUsersLoading || isDatasetsLoading || isQueriesLoading || isTransactionsLoading
                  ? 'animate-spin'
                  : ''
              }`}
            />
            <span>Refresh</span>
          </button>
        </div>
      </div>

      {/* Navigation Tabs */}
      <div className="flex items-center gap-1.5 border-b border-slate-200 pb-2 overflow-x-auto text-xs font-semibold">
        {[
          { id: 'overview', label: 'Platform Overview', icon: <Layers className="w-4 h-4" /> },
          { id: 'users', label: 'Registered Users', icon: <Users className="w-4 h-4" />, count: overview?.total_users },
          { id: 'datasets', label: 'Dataset Registry', icon: <Database className="w-4 h-4" />, count: overview?.total_datasets },
          { id: 'queries', label: 'Global Query History', icon: <Search className="w-4 h-4" />, count: overview?.total_queries },
          { id: 'transactions', label: 'Credit Ledger', icon: <Coins className="w-4 h-4" /> },
          { id: 'audit', label: 'Audit Logs', icon: <Activity className="w-4 h-4" /> },
        ].map((tab) => {
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id as AdminTab)}
              className={`px-4 py-2.5 rounded-xl transition-all cursor-pointer flex items-center gap-2 whitespace-nowrap ${
                isActive
                  ? 'bg-slate-900 text-white font-bold shadow-xs'
                  : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
              }`}
            >
              {tab.icon}
              <span>{tab.label}</span>
              {typeof tab.count === 'number' && (
                <span
                  className={`text-[10px] px-1.5 py-0.5 rounded-full font-mono ${
                    isActive ? 'bg-slate-800 text-slate-200' : 'bg-slate-200 text-slate-700'
                  }`}
                >
                  {tab.count}
                </span>
              )}
            </button>
          );
        })}
      </div>

      {/* TAB 1: OVERVIEW */}
      {activeTab === 'overview' && (
        <div className="space-y-6">
          {/* Summary Metric Cards */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {/* 1. Total Registered Users */}
            <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-xs">
              <div className="flex items-center justify-between text-slate-500 mb-3">
                <span className="text-xs font-bold uppercase tracking-wider text-slate-400">
                  Registered Users
                </span>
                <div className="w-8 h-8 rounded-lg bg-indigo-50 text-indigo-600 flex items-center justify-center">
                  <Users className="w-4 h-4" />
                </div>
              </div>
              <div className="text-2xl font-black text-slate-900 font-mono">
                {isOverviewLoading ? '...' : (overview?.total_users ?? 0).toLocaleString()}
              </div>
              <p className="text-xs text-slate-500 mt-1 flex items-center gap-1">
                <span className="text-emerald-600 font-semibold">Active accounts</span> across DataPulse
              </p>
            </div>

            {/* 2. Total Uploaded Datasets */}
            <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-xs">
              <div className="flex items-center justify-between text-slate-500 mb-3">
                <span className="text-xs font-bold uppercase tracking-wider text-slate-400">
                  Uploaded Datasets
                </span>
                <div className="w-8 h-8 rounded-lg bg-emerald-50 text-emerald-600 flex items-center justify-center">
                  <Database className="w-4 h-4" />
                </div>
              </div>
              <div className="text-2xl font-black text-slate-900 font-mono">
                {isOverviewLoading ? '...' : (overview?.total_datasets ?? 0).toLocaleString()}
              </div>
              <p className="text-xs text-slate-500 mt-1">
                Indexed in DuckDB analytical storage
              </p>
            </div>

            {/* 3. Query Executions (Successful vs Failed) */}
            <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-xs">
              <div className="flex items-center justify-between text-slate-500 mb-3">
                <span className="text-xs font-bold uppercase tracking-wider text-slate-400">
                  Query Executions
                </span>
                <div className="w-8 h-8 rounded-lg bg-cyan-50 text-cyan-600 flex items-center justify-center">
                  <Search className="w-4 h-4" />
                </div>
              </div>
              <div className="text-2xl font-black text-slate-900 font-mono">
                {isOverviewLoading ? '...' : (overview?.total_queries ?? 0).toLocaleString()}
              </div>
              <div className="flex items-center gap-2 mt-1 text-xs">
                <span className="text-emerald-600 font-semibold flex items-center gap-0.5">
                  <CheckCircle2 className="w-3 h-3" />
                  {overview?.total_queries_successful ?? 0} ok
                </span>
                <span className="text-slate-300">•</span>
                <span className="text-rose-600 font-semibold flex items-center gap-0.5">
                  <XCircle className="w-3 h-3" />
                  {overview?.total_queries_failed ?? 0} rejected
                </span>
              </div>
            </div>

            {/* 4. Total Credits Issued & Spent */}
            <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-xs">
              <div className="flex items-center justify-between text-slate-500 mb-3">
                <span className="text-xs font-bold uppercase tracking-wider text-slate-400">
                  Credits Issued / Spent
                </span>
                <div className="w-8 h-8 rounded-lg bg-amber-50 text-amber-600 flex items-center justify-center">
                  <Coins className="w-4 h-4" />
                </div>
              </div>
              <div className="text-2xl font-black text-slate-900 font-mono">
                {isOverviewLoading
                  ? '...'
                  : `${(overview?.total_credits_issued ?? 0).toLocaleString()} / ${(overview?.total_credits_spent ?? 0).toLocaleString()}`}
              </div>
              <p className="text-xs text-slate-500 mt-1 font-mono">
                Net liability: <span className="font-semibold text-slate-800">{(overview?.net_credit_liability ?? 0).toLocaleString()} cr</span>
              </p>
            </div>
          </div>

          {/* Recent Platform Activity Feed */}
          <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-xs">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2">
                <Activity className="w-5 h-5 text-indigo-600" />
                <h2 className="text-base font-bold text-slate-900">Recent Platform Activity</h2>
              </div>
              <span className="text-xs text-slate-400 font-mono">Real-time Telemetry</span>
            </div>

            {isOverviewLoading ? (
              <div className="py-8 text-center text-xs text-slate-400 animate-pulse">
                Loading administrative events...
              </div>
            ) : !overview?.recent_activity?.length ? (
              <div className="py-8 text-center text-xs text-slate-400">
                No platform activity recorded yet.
              </div>
            ) : (
              <div className="divide-y divide-slate-100">
                {overview.recent_activity.map((act) => {
                  let badge = (
                    <span className="px-2 py-0.5 rounded text-[10px] font-bold uppercase bg-slate-100 text-slate-600">
                      Activity
                    </span>
                  );
                  if (act.type === 'USER_REGISTER') {
                    badge = (
                      <span className="px-2 py-0.5 rounded text-[10px] font-bold uppercase bg-indigo-50 text-indigo-700 border border-indigo-100">
                        Registration
                      </span>
                    );
                  } else if (act.type === 'DATASET_UPLOAD') {
                    badge = (
                      <span className="px-2 py-0.5 rounded text-[10px] font-bold uppercase bg-emerald-50 text-emerald-700 border border-emerald-100">
                        Dataset Upload
                      </span>
                    );
                  } else if (act.type === 'QUERY_EXECUTION') {
                    badge = (
                      <span className="px-2 py-0.5 rounded text-[10px] font-bold uppercase bg-cyan-50 text-cyan-700 border border-cyan-100">
                        Query Run
                      </span>
                    );
                  } else if (act.type === 'CREDIT_TRANSACTION') {
                    badge = (
                      <span className="px-2 py-0.5 rounded text-[10px] font-bold uppercase bg-amber-50 text-amber-700 border border-amber-100">
                        Credit Transaction
                      </span>
                    );
                  }

                  return (
                    <div key={act.id} className="py-3 flex items-center justify-between gap-4 text-xs">
                      <div className="flex items-center gap-3 min-w-0">
                        {badge}
                        <div className="min-w-0">
                          <p className="font-semibold text-slate-800 truncate">{act.description}</p>
                          {act.user_email && (
                            <p className="text-[11px] text-slate-400 font-mono truncate">{act.user_email}</p>
                          )}
                        </div>
                      </div>
                      <div className="text-[11px] text-slate-400 font-mono shrink-0 flex items-center gap-1">
                        <Clock className="w-3 h-3 text-slate-300" />
                        {new Date(act.timestamp).toLocaleString()}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      )}

      {/* TAB 2: REGISTERED USERS */}
      {activeTab === 'users' && (
        <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-xs space-y-4">
          <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3">
            <div className="flex items-center gap-2 flex-1 max-w-md">
              <div className="relative w-full">
                <Search className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" />
                <input
                  type="text"
                  placeholder="Search user by name or email..."
                  value={usersSearch}
                  onChange={(e) => {
                    setUsersSearch(e.target.value);
                    setUsersPage(1);
                  }}
                  className="w-full pl-9 pr-3 py-2 text-xs rounded-xl border border-slate-200 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500"
                />
                {usersSearch && (
                  <button
                    onClick={() => setUsersSearch('')}
                    className="absolute right-2.5 top-2.5 text-slate-400 hover:text-slate-600 cursor-pointer"
                  >
                    <X className="w-3.5 h-3.5" />
                  </button>
                )}
              </div>
            </div>

            <div className="flex items-center gap-2 text-xs">
              <Filter className="w-3.5 h-3.5 text-slate-400" />
              <select
                value={usersRoleFilter}
                onChange={(e) => {
                  setUsersRoleFilter(e.target.value);
                  setUsersPage(1);
                }}
                className="px-3 py-2 rounded-xl border border-slate-200 text-xs text-slate-700 bg-white focus:outline-none"
              >
                <option value="all">All Roles</option>
                <option value="admin">Administrators Only</option>
                <option value="user">Standard Users Only</option>
              </select>
            </div>
          </div>

          {/* Table */}
          <div className="border border-slate-100 rounded-xl overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-50/80 text-slate-500 font-semibold border-b border-slate-100">
                <tr>
                  <th className="py-3 px-4">User ID</th>
                  <th className="py-3 px-4">Name / Email</th>
                  <th className="py-3 px-4">Role / Status</th>
                  <th className="py-3 px-4">Credits</th>
                  <th className="py-3 px-4">Reputation</th>
                  <th className="py-3 px-4">Activity</th>
                  <th className="py-3 px-4">Registered Date</th>
                  <th className="py-3 px-4 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 text-slate-700">
                {isUsersLoading ? (
                  <tr>
                    <td colSpan={8} className="py-8 text-center text-slate-400 animate-pulse">
                      Loading user records...
                    </td>
                  </tr>
                ) : !users.length ? (
                  <tr>
                    <td colSpan={8} className="py-8 text-center text-slate-400">
                      No user accounts match your search filter.
                    </td>
                  </tr>
                ) : (
                  users.map((u) => (
                    <tr key={u.id} className="hover:bg-slate-50/60 transition-colors">
                      <td className="py-3 px-4 font-mono text-[11px] text-slate-500">{u.id}</td>
                      <td className="py-3 px-4">
                        <div className="font-bold text-slate-900">{u.full_name}</div>
                        <div className="text-[11px] text-slate-400 font-mono">{u.email}</div>
                      </td>
                      <td className="py-3 px-4">
                        {u.is_admin ? (
                          <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-50 text-amber-700 border border-amber-200">
                            Administrator
                          </span>
                        ) : (
                          <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-slate-100 text-slate-600">
                            Active User
                          </span>
                        )}
                      </td>
                      <td className="py-3 px-4 font-mono font-bold text-emerald-600">
                        {u.credits.toLocaleString()} cr
                      </td>
                      <td className="py-3 px-4 font-mono">{u.reputation_score}/100</td>
                      <td className="py-3 px-4 text-[11px] text-slate-500">
                        {u.datasets_count} datasets • {u.queries_count} queries
                      </td>
                      <td className="py-3 px-4 text-[11px] text-slate-400 font-mono">
                        {new Date(u.created_at).toLocaleDateString()}
                      </td>
                      <td className="py-3 px-4 text-right">
                        <button
                          onClick={() => handleOpenUserDetail(u.id)}
                          className="px-2.5 py-1 rounded-lg border border-slate-200 hover:bg-indigo-50 hover:text-indigo-600 hover:border-indigo-200 transition-colors text-[11px] font-semibold cursor-pointer inline-flex items-center gap-1"
                        >
                          <Eye className="w-3 h-3" />
                          <span>Inspect</span>
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          <div className="flex items-center justify-between text-xs text-slate-500 pt-2">
            <span>
              Showing {users.length > 0 ? (usersPage - 1) * 15 + 1 : 0} to{' '}
              {Math.min(usersPage * 15, usersTotal)} of {usersTotal} users
            </span>
            <div className="flex items-center gap-2">
              <button
                disabled={usersPage <= 1}
                onClick={() => setUsersPage((p) => p - 1)}
                className="px-2.5 py-1 rounded-lg border border-slate-200 disabled:opacity-40 disabled:cursor-not-allowed hover:bg-slate-50 transition-colors cursor-pointer"
              >
                <ChevronLeft className="w-3.5 h-3.5" />
              </button>
              <span className="font-mono text-xs">Page {usersPage}</span>
              <button
                disabled={usersPage * 15 >= usersTotal}
                onClick={() => setUsersPage((p) => p + 1)}
                className="px-2.5 py-1 rounded-lg border border-slate-200 disabled:opacity-40 disabled:cursor-not-allowed hover:bg-slate-50 transition-colors cursor-pointer"
              >
                <ChevronRight className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        </div>
      )}

      {/* TAB 3: DATASET REGISTRY */}
      {activeTab === 'datasets' && (
        <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-xs space-y-4">
          <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3">
            <div className="relative w-full sm:max-w-md">
              <Search className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" />
              <input
                type="text"
                placeholder="Search datasets by title, filename, domain, owner..."
                value={datasetsSearch}
                onChange={(e) => {
                  setDatasetsSearch(e.target.value);
                  setDatasetsPage(1);
                }}
                className="w-full pl-9 pr-3 py-2 text-xs rounded-xl border border-slate-200 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500"
              />
              {datasetsSearch && (
                <button
                  onClick={() => setDatasetsSearch('')}
                  className="absolute right-2.5 top-2.5 text-slate-400 hover:text-slate-600 cursor-pointer"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              )}
            </div>

            <div className="flex items-center gap-2 text-xs">
              <Filter className="w-3.5 h-3.5 text-slate-400" />
              <select
                value={datasetsDomainFilter}
                onChange={(e) => {
                  setDatasetsDomainFilter(e.target.value);
                  setDatasetsPage(1);
                }}
                className="px-3 py-2 rounded-xl border border-slate-200 text-xs text-slate-700 bg-white focus:outline-none"
              >
                <option value="all">All Domains</option>
                <option value="technology">Technology</option>
                <option value="finance">Finance</option>
                <option value="healthcare">Healthcare</option>
                <option value="retail">Retail</option>
                <option value="general">General</option>
              </select>
            </div>
          </div>

          {/* Table */}
          <div className="border border-slate-100 rounded-xl overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-50/80 text-slate-500 font-semibold border-b border-slate-100">
                <tr>
                  <th className="py-3 px-4">Dataset ID</th>
                  <th className="py-3 px-4">Title / Filename</th>
                  <th className="py-3 px-4">Owner</th>
                  <th className="py-3 px-4">Domain</th>
                  <th className="py-3 px-4">Dimensions</th>
                  <th className="py-3 px-4">Quality Score</th>
                  <th className="py-3 px-4">Status / Storage</th>
                  <th className="py-3 px-4">Upload Date</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 text-slate-700">
                {isDatasetsLoading ? (
                  <tr>
                    <td colSpan={8} className="py-8 text-center text-slate-400 animate-pulse">
                      Loading dataset records...
                    </td>
                  </tr>
                ) : !datasets.length ? (
                  <tr>
                    <td colSpan={8} className="py-8 text-center text-slate-400">
                      No datasets found matching current criteria.
                    </td>
                  </tr>
                ) : (
                  datasets.map((d) => (
                    <tr key={d.id} className="hover:bg-slate-50/60 transition-colors">
                      <td className="py-3 px-4 font-mono text-[11px] text-slate-500">{d.id}</td>
                      <td className="py-3 px-4">
                        <div className="font-bold text-slate-900">{d.title}</div>
                        <div className="text-[11px] text-slate-400 font-mono">{d.filename}</div>
                      </td>
                      <td className="py-3 px-4">
                        <div className="font-semibold text-slate-800">{d.owner_name}</div>
                        <div className="text-[11px] text-slate-400 font-mono">{d.owner_email}</div>
                      </td>
                      <td className="py-3 px-4">
                        <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-slate-100 text-slate-700 uppercase">
                          {d.domain}
                        </span>
                      </td>
                      <td className="py-3 px-4 font-mono text-[11px]">
                        {d.rows_count.toLocaleString()}r × {d.columns_count}c
                      </td>
                      <td className="py-3 px-4">
                        {typeof d.overall_score === 'number' ? (
                          <span
                            className={`px-2 py-0.5 rounded text-[11px] font-bold font-mono ${
                              d.overall_score >= 80
                                ? 'bg-emerald-50 text-emerald-700'
                                : d.overall_score >= 60
                                ? 'bg-amber-50 text-amber-700'
                                : 'bg-rose-50 text-rose-700'
                            }`}
                          >
                            {d.overall_score.toFixed(1)}/100
                          </span>
                        ) : (
                          <span className="text-slate-400">Pending</span>
                        )}
                      </td>
                      <td className="py-3 px-4">
                        <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-50 text-emerald-700 border border-emerald-200 flex items-center gap-1 w-max">
                          <CheckCircle2 className="w-2.5 h-2.5" />
                          {d.availability}
                        </span>
                      </td>
                      <td className="py-3 px-4 text-[11px] text-slate-400 font-mono">
                        {new Date(d.created_at).toLocaleDateString()}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          <div className="flex items-center justify-between text-xs text-slate-500 pt-2">
            <span>
              Showing {datasets.length > 0 ? (datasetsPage - 1) * 15 + 1 : 0} to{' '}
              {Math.min(datasetsPage * 15, datasetsTotal)} of {datasetsTotal} datasets
            </span>
            <div className="flex items-center gap-2">
              <button
                disabled={datasetsPage <= 1}
                onClick={() => setDatasetsPage((p) => p - 1)}
                className="px-2.5 py-1 rounded-lg border border-slate-200 disabled:opacity-40 disabled:cursor-not-allowed hover:bg-slate-50 transition-colors cursor-pointer"
              >
                <ChevronLeft className="w-3.5 h-3.5" />
              </button>
              <span className="font-mono text-xs">Page {datasetsPage}</span>
              <button
                disabled={datasetsPage * 15 >= datasetsTotal}
                onClick={() => setDatasetsPage((p) => p + 1)}
                className="px-2.5 py-1 rounded-lg border border-slate-200 disabled:opacity-40 disabled:cursor-not-allowed hover:bg-slate-50 transition-colors cursor-pointer"
              >
                <ChevronRight className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        </div>
      )}

      {/* TAB 4: GLOBAL QUERY HISTORY */}
      {activeTab === 'queries' && (
        <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-xs space-y-4">
          <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3">
            <div className="relative w-full sm:max-w-md">
              <Search className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" />
              <input
                type="text"
                placeholder="Search prompt, generated SQL, user email..."
                value={queriesSearch}
                onChange={(e) => {
                  setQueriesSearch(e.target.value);
                  setQueriesPage(1);
                }}
                className="w-full pl-9 pr-3 py-2 text-xs rounded-xl border border-slate-200 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500"
              />
              {queriesSearch && (
                <button
                  onClick={() => setQueriesSearch('')}
                  className="absolute right-2.5 top-2.5 text-slate-400 hover:text-slate-600 cursor-pointer"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              )}
            </div>

            <div className="flex items-center gap-2 text-xs">
              <Filter className="w-3.5 h-3.5 text-slate-400" />
              <select
                value={queriesStatusFilter}
                onChange={(e) => {
                  setQueriesStatusFilter(e.target.value);
                  setQueriesPage(1);
                }}
                className="px-3 py-2 rounded-xl border border-slate-200 text-xs text-slate-700 bg-white focus:outline-none"
              >
                <option value="All">All Statuses</option>
                <option value="SUCCESS">Success</option>
                <option value="SQL_REJECTED">SQL Rejected</option>
                <option value="INSUFFICIENT_CREDITS">Insufficient Credits</option>
              </select>
            </div>
          </div>

          {/* Table */}
          <div className="border border-slate-100 rounded-xl overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-50/80 text-slate-500 font-semibold border-b border-slate-100">
                <tr>
                  <th className="py-3 px-4">User</th>
                  <th className="py-3 px-4">Natural Prompt</th>
                  <th className="py-3 px-4">Target Dataset</th>
                  <th className="py-3 px-4">Generated SQL</th>
                  <th className="py-3 px-4">Status</th>
                  <th className="py-3 px-4">Execution</th>
                  <th className="py-3 px-4">Charged</th>
                  <th className="py-3 px-4">Timestamp</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 text-slate-700">
                {isQueriesLoading ? (
                  <tr>
                    <td colSpan={8} className="py-8 text-center text-slate-400 animate-pulse">
                      Loading global queries...
                    </td>
                  </tr>
                ) : !queries.length ? (
                  <tr>
                    <td colSpan={8} className="py-8 text-center text-slate-400">
                      No query executions recorded.
                    </td>
                  </tr>
                ) : (
                  queries.map((q) => (
                    <tr key={q.id} className="hover:bg-slate-50/60 transition-colors">
                      <td className="py-3 px-4">
                        <div className="font-semibold text-slate-800">{q.user_name}</div>
                        <div className="text-[11px] text-slate-400 font-mono">{q.user_email}</div>
                      </td>
                      <td className="py-3 px-4 max-w-xs">
                        <p className="font-medium text-slate-900 truncate" title={q.natural_prompt}>
                          {q.natural_prompt}
                        </p>
                        {q.error_message && (
                          <p className="text-[10px] text-rose-500 truncate" title={q.error_message}>
                            Error: {q.error_message}
                          </p>
                        )}
                      </td>
                      <td className="py-3 px-4">
                        <span className="px-2 py-0.5 rounded text-[11px] bg-slate-100 text-slate-700 font-semibold truncate block max-w-[120px]">
                          {q.dataset_name || 'Cross-Catalog'}
                        </span>
                      </td>
                      <td className="py-3 px-4 max-w-xs">
                        <div className="flex items-center gap-1.5 bg-slate-50 border border-slate-200/80 rounded px-2 py-1 font-mono text-[11px] text-slate-700">
                          <span className="truncate flex-1" title={q.generated_sql || ''}>
                            {q.generated_sql || '-- No SQL generated'}
                          </span>
                          {q.generated_sql && (
                            <button
                              onClick={() => copyToClipboard(q.generated_sql!, q.id)}
                              className="text-slate-400 hover:text-slate-600 cursor-pointer shrink-0"
                              title="Copy SQL"
                            >
                              {copiedSqlId === q.id ? (
                                <Check className="w-3 h-3 text-emerald-600" />
                              ) : (
                                <Copy className="w-3 h-3" />
                              )}
                            </button>
                          )}
                        </div>
                      </td>
                      <td className="py-3 px-4">
                        {q.execution_status === 'SUCCESS' ? (
                          <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-50 text-emerald-700 border border-emerald-200">
                            SUCCESS
                          </span>
                        ) : (
                          <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-rose-50 text-rose-700 border border-rose-200">
                            {q.execution_status}
                          </span>
                        )}
                      </td>
                      <td className="py-3 px-4 font-mono text-[11px] text-slate-500 whitespace-nowrap">
                        {q.execution_time_ms}ms • {q.rows_returned} rows
                      </td>
                      <td className="py-3 px-4 font-mono font-bold text-slate-800 whitespace-nowrap">
                        {q.credits_charged} cr
                      </td>
                      <td className="py-3 px-4 text-[11px] text-slate-400 font-mono whitespace-nowrap">
                        {new Date(q.timestamp).toLocaleString()}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          <div className="flex items-center justify-between text-xs text-slate-500 pt-2">
            <span>
              Showing {queries.length > 0 ? (queriesPage - 1) * 15 + 1 : 0} to{' '}
              {Math.min(queriesPage * 15, queriesTotal)} of {queriesTotal} queries
            </span>
            <div className="flex items-center gap-2">
              <button
                disabled={queriesPage <= 1}
                onClick={() => setQueriesPage((p) => p - 1)}
                className="px-2.5 py-1 rounded-lg border border-slate-200 disabled:opacity-40 disabled:cursor-not-allowed hover:bg-slate-50 transition-colors cursor-pointer"
              >
                <ChevronLeft className="w-3.5 h-3.5" />
              </button>
              <span className="font-mono text-xs">Page {queriesPage}</span>
              <button
                disabled={queriesPage * 15 >= queriesTotal}
                onClick={() => setQueriesPage((p) => p + 1)}
                className="px-2.5 py-1 rounded-lg border border-slate-200 disabled:opacity-40 disabled:cursor-not-allowed hover:bg-slate-50 transition-colors cursor-pointer"
              >
                <ChevronRight className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        </div>
      )}

      {/* TAB 5: CREDIT LEDGER */}
      {activeTab === 'transactions' && (
        <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-xs space-y-4">
          <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3">
            <div className="relative w-full sm:max-w-md">
              <Search className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" />
              <input
                type="text"
                placeholder="Search description, user email..."
                value={transactionsSearch}
                onChange={(e) => {
                  setTransactionsSearch(e.target.value);
                  setTransactionsPage(1);
                }}
                className="w-full pl-9 pr-3 py-2 text-xs rounded-xl border border-slate-200 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500"
              />
              {transactionsSearch && (
                <button
                  onClick={() => setTransactionsSearch('')}
                  className="absolute right-2.5 top-2.5 text-slate-400 hover:text-slate-600 cursor-pointer"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              )}
            </div>

            <div className="flex items-center gap-2 text-xs">
              <Filter className="w-3.5 h-3.5 text-slate-400" />
              <select
                value={transactionsTypeFilter}
                onChange={(e) => {
                  setTransactionsTypeFilter(e.target.value);
                  setTransactionsPage(1);
                }}
                className="px-3 py-2 rounded-xl border border-slate-200 text-xs text-slate-700 bg-white focus:outline-none"
              >
                <option value="all">All Types</option>
                <option value="bonus">Signup / Welcome Bonus</option>
                <option value="reward">Dataset Upload Reward</option>
                <option value="query">Query Charge</option>
                <option value="redeem">Cash Payout / Redemption</option>
                <option value="royalty">Dataset Contributor Royalty</option>
              </select>
            </div>
          </div>

          {/* Table */}
          <div className="border border-slate-100 rounded-xl overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-50/80 text-slate-500 font-semibold border-b border-slate-100">
                <tr>
                  <th className="py-3 px-4">Tx ID</th>
                  <th className="py-3 px-4">User</th>
                  <th className="py-3 px-4">Type</th>
                  <th className="py-3 px-4">Amount / Balance Impact</th>
                  <th className="py-3 px-4">Description</th>
                  <th className="py-3 px-4">Status</th>
                  <th className="py-3 px-4">Timestamp</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 text-slate-700">
                {isTransactionsLoading ? (
                  <tr>
                    <td colSpan={7} className="py-8 text-center text-slate-400 animate-pulse">
                      Loading credit ledger...
                    </td>
                  </tr>
                ) : !transactions.length ? (
                  <tr>
                    <td colSpan={7} className="py-8 text-center text-slate-400">
                      No credit transactions recorded.
                    </td>
                  </tr>
                ) : (
                  transactions.map((t) => {
                    const isCredit = t.amount > 0;
                    return (
                      <tr key={t.id} className="hover:bg-slate-50/60 transition-colors">
                        <td className="py-3 px-4 font-mono text-[11px] text-slate-500">{t.id}</td>
                        <td className="py-3 px-4">
                          <div className="font-semibold text-slate-800">{t.user_name}</div>
                          <div className="text-[11px] text-slate-400 font-mono">{t.user_email}</div>
                        </td>
                        <td className="py-3 px-4">
                          <span className="px-2 py-0.5 rounded text-[10px] font-bold uppercase bg-slate-100 text-slate-600">
                            {t.transaction_type}
                          </span>
                        </td>
                        <td className="py-3 px-4">
                          <span
                            className={`inline-flex items-center gap-1 font-mono font-bold text-xs px-2 py-0.5 rounded-full ${
                              isCredit
                                ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                                : 'bg-rose-50 text-rose-700 border border-rose-200'
                            }`}
                          >
                            {isCredit ? (
                              <ArrowUpRight className="w-3 h-3 text-emerald-600" />
                            ) : (
                              <ArrowDownRight className="w-3 h-3 text-rose-600" />
                            )}
                            {t.balance_impact} cr
                          </span>
                        </td>
                        <td className="py-3 px-4 text-slate-700 max-w-sm truncate" title={t.description}>
                          {t.description}
                        </td>
                        <td className="py-3 px-4">
                          <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-slate-100 text-slate-700">
                            {t.status}
                          </span>
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

          {/* Pagination */}
          <div className="flex items-center justify-between text-xs text-slate-500 pt-2">
            <span>
              Showing {transactions.length > 0 ? (transactionsPage - 1) * 15 + 1 : 0} to{' '}
              {Math.min(transactionsPage * 15, transactionsTotal)} of {transactionsTotal} transactions
            </span>
            <div className="flex items-center gap-2">
              <button
                disabled={transactionsPage <= 1}
                onClick={() => setTransactionsPage((p) => p - 1)}
                className="px-2.5 py-1 rounded-lg border border-slate-200 disabled:opacity-40 disabled:cursor-not-allowed hover:bg-slate-50 transition-colors cursor-pointer"
              >
                <ChevronLeft className="w-3.5 h-3.5" />
              </button>
              <span className="font-mono text-xs">Page {transactionsPage}</span>
              <button
                disabled={transactionsPage * 15 >= transactionsTotal}
                onClick={() => setTransactionsPage((p) => p + 1)}
                className="px-2.5 py-1 rounded-lg border border-slate-200 disabled:opacity-40 disabled:cursor-not-allowed hover:bg-slate-50 transition-colors cursor-pointer"
              >
                <ChevronRight className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        </div>
      )}

      {/* TAB 6: AUDIT LOGS */}
      {activeTab === 'audit' && (
        <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-xs space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-base font-bold text-slate-900">Administrative Governance & Audit Trail</h2>
            <span className="text-xs text-slate-400 font-mono">Immutable Compliance Log</span>
          </div>

          <div className="border border-slate-100 rounded-xl overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-50/80 text-slate-500 font-semibold border-b border-slate-100">
                <tr>
                  <th className="py-3 px-4">Log ID</th>
                  <th className="py-3 px-4">Admin Email</th>
                  <th className="py-3 px-4">Action</th>
                  <th className="py-3 px-4">Target Resource</th>
                  <th className="py-3 px-4">Details</th>
                  <th className="py-3 px-4">Client IP</th>
                  <th className="py-3 px-4">Timestamp</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 text-slate-700">
                {isAuditLoading ? (
                  <tr>
                    <td colSpan={7} className="py-8 text-center text-slate-400 animate-pulse">
                      Loading audit logs...
                    </td>
                  </tr>
                ) : !auditLogs.length ? (
                  <tr>
                    <td colSpan={7} className="py-8 text-center text-slate-400">
                      No administrative actions logged yet.
                    </td>
                  </tr>
                ) : (
                  auditLogs.map((log) => (
                    <tr key={log.id} className="hover:bg-slate-50/60 transition-colors">
                      <td className="py-3 px-4 font-mono text-[11px] text-slate-500">{log.id}</td>
                      <td className="py-3 px-4 font-mono font-semibold text-slate-800">{log.admin_email}</td>
                      <td className="py-3 px-4">
                        <span className="px-2 py-0.5 rounded text-[10px] font-bold uppercase bg-amber-50 text-amber-700 border border-amber-200">
                          {log.action}
                        </span>
                      </td>
                      <td className="py-3 px-4 font-mono text-[11px] text-slate-600">
                        {log.target_resource || '—'}
                      </td>
                      <td className="py-3 px-4 text-slate-600">{log.details || '—'}</td>
                      <td className="py-3 px-4 font-mono text-[11px] text-slate-400">{log.ip_address || '—'}</td>
                      <td className="py-3 px-4 text-[11px] text-slate-400 font-mono whitespace-nowrap">
                        {new Date(log.timestamp).toLocaleString()}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          <div className="flex items-center justify-between text-xs text-slate-500 pt-2">
            <span>
              Showing {auditLogs.length > 0 ? (auditPage - 1) * 20 + 1 : 0} to{' '}
              {Math.min(auditPage * 20, auditTotal)} of {auditTotal} audit events
            </span>
            <div className="flex items-center gap-2">
              <button
                disabled={auditPage <= 1}
                onClick={() => setAuditPage((p) => p - 1)}
                className="px-2.5 py-1 rounded-lg border border-slate-200 disabled:opacity-40 disabled:cursor-not-allowed hover:bg-slate-50 transition-colors cursor-pointer"
              >
                <ChevronLeft className="w-3.5 h-3.5" />
              </button>
              <span className="font-mono text-xs">Page {auditPage}</span>
              <button
                disabled={auditPage * 20 >= auditTotal}
                onClick={() => setAuditPage((p) => p + 1)}
                className="px-2.5 py-1 rounded-lg border border-slate-200 disabled:opacity-40 disabled:cursor-not-allowed hover:bg-slate-50 transition-colors cursor-pointer"
              >
                <ChevronRight className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        </div>
      )}

      {/* USER DETAIL MODAL / SLIDE-OVER */}
      {selectedUserDetail && (
        <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-xs flex items-center justify-center p-4 animate-in fade-in duration-150">
          <div className="bg-white rounded-2xl max-w-3xl w-full max-h-[90vh] overflow-y-auto shadow-2xl border border-slate-200 p-6 space-y-6">
            <div className="flex items-start justify-between border-b border-slate-100 pb-4">
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="text-lg font-extrabold text-slate-900">
                    {selectedUserDetail.full_name}
                  </h3>
                  {selectedUserDetail.is_admin ? (
                    <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-amber-50 text-amber-700 border border-amber-200">
                      Administrator
                    </span>
                  ) : (
                    <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-slate-100 text-slate-700">
                      Standard User
                    </span>
                  )}
                </div>
                <p className="text-xs text-slate-500 font-mono mt-0.5">
                  ID: {selectedUserDetail.id} • {selectedUserDetail.email}
                </p>
              </div>
              <button
                onClick={() => setSelectedUserDetail(null)}
                className="p-1 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-colors cursor-pointer"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Quick Metrics */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-center">
              <div className="p-3 rounded-xl bg-slate-50 border border-slate-100">
                <span className="text-[10px] uppercase font-bold text-slate-400 block">Balance</span>
                <span className="text-base font-black font-mono text-emerald-600">
                  {selectedUserDetail.credits.toLocaleString()} cr
                </span>
              </div>
              <div className="p-3 rounded-xl bg-slate-50 border border-slate-100">
                <span className="text-[10px] uppercase font-bold text-slate-400 block">Reputation</span>
                <span className="text-base font-black font-mono text-slate-900">
                  {selectedUserDetail.reputation_score}/100
                </span>
              </div>
              <div className="p-3 rounded-xl bg-slate-50 border border-slate-100">
                <span className="text-[10px] uppercase font-bold text-slate-400 block">Datasets</span>
                <span className="text-base font-black font-mono text-slate-900">
                  {selectedUserDetail.total_datasets}
                </span>
              </div>
              <div className="p-3 rounded-xl bg-slate-50 border border-slate-100">
                <span className="text-[10px] uppercase font-bold text-slate-400 block">Queries</span>
                <span className="text-base font-black font-mono text-slate-900">
                  {selectedUserDetail.total_queries}
                </span>
              </div>
            </div>

            {/* Uploaded Datasets Section */}
            <div className="space-y-2">
              <h4 className="text-xs font-bold uppercase tracking-wider text-slate-400">
                Uploaded Datasets ({selectedUserDetail.datasets.length})
              </h4>
              {!selectedUserDetail.datasets.length ? (
                <p className="text-xs text-slate-400 italic">No datasets uploaded yet.</p>
              ) : (
                <div className="divide-y divide-slate-100 border border-slate-100 rounded-xl overflow-hidden text-xs">
                  {selectedUserDetail.datasets.map((ds) => (
                    <div key={ds.id} className="p-3 flex items-center justify-between gap-4">
                      <div>
                        <div className="font-bold text-slate-900">{ds.name}</div>
                        <div className="text-[11px] text-slate-400 font-mono">
                          {ds.filename} • {ds.rows_count} rows × {ds.columns_count} columns
                        </div>
                      </div>
                      <div className="text-right">
                        {typeof ds.quality_score === 'number' && (
                          <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-50 text-emerald-700">
                            {ds.quality_score}/100
                          </span>
                        )}
                        <span className="text-[10px] text-slate-400 block mt-0.5">
                          {new Date(ds.created_at).toLocaleDateString()}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Recent Queries Section */}
            <div className="space-y-2">
              <h4 className="text-xs font-bold uppercase tracking-wider text-slate-400">
                Recent Queries ({selectedUserDetail.recent_queries.length})
              </h4>
              {!selectedUserDetail.recent_queries.length ? (
                <p className="text-xs text-slate-400 italic">No query history recorded.</p>
              ) : (
                <div className="divide-y divide-slate-100 border border-slate-100 rounded-xl overflow-hidden text-xs max-h-48 overflow-y-auto">
                  {selectedUserDetail.recent_queries.map((q) => (
                    <div key={q.id} className="p-3 flex items-center justify-between gap-4">
                      <div className="min-w-0">
                        <p className="font-semibold text-slate-800 truncate">{q.natural_prompt}</p>
                        <p className="text-[10px] font-mono text-slate-400 truncate">{q.generated_sql}</p>
                      </div>
                      <div className="text-right shrink-0">
                        <span
                          className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                            q.status === 'SUCCESS'
                              ? 'bg-emerald-50 text-emerald-700'
                              : 'bg-rose-50 text-rose-700'
                          }`}
                        >
                          {q.status}
                        </span>
                        <span className="text-[10px] text-slate-400 block mt-0.5">
                          {new Date(q.timestamp).toLocaleDateString()}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Close Button */}
            <div className="text-right pt-2 border-t border-slate-100">
              <button
                onClick={() => setSelectedUserDetail(null)}
                className="px-4 py-2 rounded-xl bg-slate-900 text-white text-xs font-semibold hover:bg-slate-800 transition-colors cursor-pointer"
              >
                Close Inspector
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default AdminDashboardView;
