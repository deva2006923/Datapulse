/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { useState, useEffect } from 'react';
import { Navbar } from './components/Navbar';
import { ToastContainer } from './components/ToastContainer';
import { LandingView } from './views/LandingView';
import { LoginRegisterView } from './views/LoginRegisterView';
import { DashboardView } from './views/DashboardView';
import { MarketplaceView } from './views/MarketplaceView';
import { DatasetDetailView } from './views/DatasetDetailView';
import { UploadWizardView } from './views/UploadWizardView';
import { QueryWorkspaceView } from './views/QueryWorkspaceView';
import { QueryHistoryView } from './views/QueryHistoryView';
import { MyDatasetsView } from './views/MyDatasetsView';
import { VersionsImproveView } from './views/VersionsImproveView';
import { WalletView } from './views/WalletView';
import { ProfileView } from './views/ProfileView';
import { NotFoundView } from './views/NotFoundView';

import {
  PageRoute,
  UserAccount,
  AppDataset,
  WalletTransaction,
  QueryHistoryItem,
  ToastMessage,
  BackendUserResponse,
} from './types';

import { api } from './services/api';
import {
  backendDatasetToAppDataset,
  transactionItemToWalletTransaction,
} from './services/datasetAdapter';

import {
  INITIAL_DATASETS,
  INITIAL_TRANSACTIONS,
  INITIAL_QUERY_HISTORY,
  MOCK_DATA_VERSION,
} from './data/mockData';

const MOCK_STORAGE_KEY = `datapulse_state_${MOCK_DATA_VERSION}`;

const PROTECTED_ROUTES: PageRoute[] = [
  'dashboard',
  'marketplace',
  'dataset-detail',
  'upload',
  'query',
  'query-history',
  'my-datasets',
  'versions-improve',
  'wallet',
  'profile',
];

export default function App() {
  const [currentRoute, setCurrentRoute] = useState<PageRoute>('landing');
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(() => !!api.auth.getToken());
  const [isAuthRestoring, setIsAuthRestoring] = useState<boolean>(true);

  // Active authenticated user account from backend
  const [currentUser, setCurrentUser] = useState<UserAccount | null>(null);

  const [datasets, setDatasets] = useState<AppDataset[]>(() => {
    try {
      const storedVer = localStorage.getItem('datapulse_version_key');
      if (storedVer === MOCK_DATA_VERSION) {
        const saved = localStorage.getItem(`${MOCK_STORAGE_KEY}_datasets`);
        if (saved) return JSON.parse(saved);
      }
    } catch (e) {
      // fallback
    }
    return INITIAL_DATASETS;
  });

  const [transactions, setTransactions] = useState<WalletTransaction[]>(() => {
    try {
      const storedVer = localStorage.getItem('datapulse_version_key');
      if (storedVer === MOCK_DATA_VERSION) {
        const saved = localStorage.getItem(`${MOCK_STORAGE_KEY}_transactions`);
        if (saved) return JSON.parse(saved);
      }
    } catch (e) {
      // fallback
    }
    return INITIAL_TRANSACTIONS;
  });

  const [queryHistory, setQueryHistory] = useState<QueryHistoryItem[]>(() => {
    try {
      const storedVer = localStorage.getItem('datapulse_version_key');
      if (storedVer === MOCK_DATA_VERSION) {
        const saved = localStorage.getItem(`${MOCK_STORAGE_KEY}_history`);
        if (saved) return JSON.parse(saved);
      }
    } catch (e) {
      // fallback
    }
    return INITIAL_QUERY_HISTORY;
  });

  const [selectedDatasetId, setSelectedDatasetId] = useState<string>('ds-heart');
  const [workspaceInitialPrompt, setWorkspaceInitialPrompt] = useState<string>('');
  const [toasts, setToasts] = useState<ToastMessage[]>([]);

  // Persist local UI caches & set version key (no mock users stored)
  useEffect(() => {
    try {
      localStorage.setItem('datapulse_version_key', MOCK_DATA_VERSION);
      localStorage.setItem(`${MOCK_STORAGE_KEY}_datasets`, JSON.stringify(datasets));
      localStorage.setItem(`${MOCK_STORAGE_KEY}_transactions`, JSON.stringify(transactions));
      localStorage.setItem(`${MOCK_STORAGE_KEY}_history`, JSON.stringify(queryHistory));
    } catch (e) {
      // ignore
    }
  }, [datasets, transactions, queryHistory]);

  // Safe fallback for views requiring a UserAccount while rendering unauthenticated landing
  const effectiveUser: UserAccount = currentUser || {
    id: 'unauthenticated',
    name: 'Guest User',
    email: 'guest@datapulse.io',
    role: 'Contributor',
    credits: 0,
    reputationScore: 0,
    contributedDatasetIds: [],
    unlockedDatasetIds: [],
    joinedDate: new Date().toISOString().split('T')[0],
  };

  // Toast dispatcher helper
  const addToast = (
    title: string,
    message: string,
    tone: 'cyan' | 'rose' | 'amber' | 'emerald' | 'violet' = 'cyan'
  ) => {
    const id = Math.random().toString(36).substring(2, 9);
    const newToast: ToastMessage = {
      id,
      title,
      message,
      tone,
      timestamp: new Date(),
    };
    setToasts((prev) => [...prev, newToast]);
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 6000);
  };

  const removeToast = (id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  };

  // Restore authenticated session from backend on mount
  useEffect(() => {
    let isMounted = true;
    const restoreSession = async () => {
      const token = api.auth.getToken();
      if (!token) {
        if (isMounted) {
          setIsAuthenticated(false);
          setCurrentUser(null);
          setIsAuthRestoring(false);
        }
        return;
      }

      try {
        const me = await api.auth.getMe();
        if (!isMounted) return;

        const restoredAccount: UserAccount = {
          id: me.id,
          name: me.full_name,
          email: me.email,
          role: 'Contributor',
          credits: me.credits,
          reputationScore: 85,
          contributedDatasetIds: [],
          unlockedDatasetIds: [],
          joinedDate: me.created_at
            ? me.created_at.split('T')[0]
            : new Date().toISOString().split('T')[0],
        };

        setCurrentUser(restoredAccount);
        setIsAuthenticated(true);

        // Fetch real datasets from backend catalog
        try {
          const dsList = await api.datasets.list();
          if (dsList?.datasets && dsList.datasets.length > 0 && isMounted) {
            const mappedDs = dsList.datasets.map((d) =>
              backendDatasetToAppDataset(d, me.id)
            );
            setDatasets(mappedDs);
            setSelectedDatasetId((prev) =>
              mappedDs.some((d) => d.id === prev) ? prev : mappedDs[0].id
            );
          }
        } catch {}

        // Fetch real credit ledger transactions from backend
        try {
          const txList = await api.credits.getTransactions();
          if (txList && isMounted) {
            setTransactions(txList.map(transactionItemToWalletTransaction));
          }
        } catch {}
      } catch {
        if (!isMounted) return;
        api.auth.logout();
        setCurrentUser(null);
        setIsAuthenticated(false);
        setCurrentRoute((curr) =>
          PROTECTED_ROUTES.includes(curr) ? 'login' : curr
        );
      } finally {
        if (isMounted) {
          setIsAuthRestoring(false);
        }
      }
    };

    restoreSession();
    return () => {
      isMounted = false;
    };
  }, []);

  // Protected route guard
  const handleNavigate = (route: PageRoute) => {
    if (PROTECTED_ROUTES.includes(route) && !isAuthenticated) {
      addToast(
        'AUTHENTICATION_REQUIRED',
        'Please sign in or create an account to access that page.',
        'amber'
      );
      setCurrentRoute('login');
      return;
    }
    setCurrentRoute(route);
  };

  const handleAuthSuccess = (
    user: BackendUserResponse,
    _token: string,
    role: 'Contributor' | 'Data Analyst' = 'Contributor'
  ) => {
    const userAccount: UserAccount = {
      id: user.id,
      name: user.full_name,
      email: user.email,
      role: role,
      credits: user.credits,
      reputationScore: 85,
      contributedDatasetIds: [],
      unlockedDatasetIds: [],
      joinedDate: user.created_at
        ? user.created_at.split('T')[0]
        : new Date().toISOString().split('T')[0],
    };

    setCurrentUser(userAccount);
    setIsAuthenticated(true);
    setCurrentRoute('dashboard');
    addToast(
      'SESSION_ACTIVE',
      `Welcome, ${user.full_name}! Active session verified.`,
      'emerald'
    );

    // Refresh datasets & transactions for logged in user
    api.datasets
      .list()
      .then((dsList) => {
        if (dsList?.datasets && dsList.datasets.length > 0) {
          const mapped = dsList.datasets.map((d) =>
            backendDatasetToAppDataset(d, user.id)
          );
          setDatasets(mapped);
          setSelectedDatasetId((prev) =>
            mapped.some((d) => d.id === prev) ? prev : mapped[0].id
          );
        }
      })
      .catch(() => {});

    api.credits
      .getTransactions()
      .then((txList) => {
        if (txList) {
          setTransactions(txList.map(transactionItemToWalletTransaction));
        }
      })
      .catch(() => {});
  };

  const handleLogout = () => {
    api.auth.logout();
    setCurrentUser(null);
    setIsAuthenticated(false);
    setCurrentRoute('login');
    addToast('SESSION_ENDED', 'You have been successfully signed out.', 'emerald');
  };

  // Switch Active User (with backend demo authentication)
  const handleSwitchUser = async (demoKey: string) => {
    try {
      const res = await api.auth.demoLogin(demoKey);
      handleAuthSuccess(res.user, res.access_token);
    } catch (err: any) {
      addToast(
        'SWITCH_FAILED',
        err?.message || 'Failed to switch demo account. Active session preserved.',
        'rose'
      );
    }
  };

  // Upload Wizard Final Publish
  // upload credits = 50 + floor(quality x 0.30) + floor(relevance / 6)
  const handlePublishDataset = (newDataset: AppDataset, earnedCredits: number) => {
    setDatasets((prev) => [newDataset, ...prev]);

    // Record wallet ledger transaction
    const tx: WalletTransaction = {
      id: `tx_up_${Date.now()}`,
      userId: effectiveUser.id,
      type: 'UPLOAD_REWARD',
      amount: earnedCredits,
      description: `Dataset Ingestion Reward for ${newDataset.title} (+${earnedCredits} credits)`,
      timestamp: new Date().toISOString().replace('T', ' ').substring(0, 19),
    };
    const nextTransactions = [tx, ...transactions];
    setTransactions(nextTransactions);

    // Optimistically update credit balance and append dataset
    setCurrentUser((prev) => {
      if (!prev) return null;
      return {
        ...prev,
        credits: prev.credits + earnedCredits,
        contributedDatasetIds: [...prev.contributedDatasetIds, newDataset.id],
        unlockedDatasetIds: [...prev.unlockedDatasetIds, newDataset.id],
      };
    });

    setSelectedDatasetId(newDataset.id);
    addToast(
      'DATASET_PUBLISHED',
      `Dataset approved! You earned +${earnedCredits} credits.`,
      'emerald'
    );

    if (isAuthenticated) {
      api.auth
        .getMe()
        .then((me) => {
          setCurrentUser((prev) => (prev ? { ...prev, credits: me.credits } : null));
        })
        .catch(() => {});

      api.datasets
        .list()
        .then((dsList) => {
          if (dsList?.datasets && dsList.datasets.length > 0) {
            const mapped = dsList.datasets.map((d) =>
              backendDatasetToAppDataset(d, effectiveUser.id)
            );
            setDatasets(mapped);
          }
        })
        .catch(() => {});

      api.credits
        .getTransactions()
        .then((txList) => {
          if (txList) {
            setTransactions(txList.map(transactionItemToWalletTransaction));
          }
        })
        .catch(() => {});
    }
  };

  // Real Backend Natural Language Query Execution
  const handleExecuteQuery = async (
    dataset: AppDataset,
    prompt: string,
    onSuccess: (result: {
      generatedSql: string;
      rows: Record<string, any>[];
      executionMs: number;
      chargedCredits: number;
      explanation: string;
      recordsAnalyzed?: number;
      matchingDatasets?: string[];
      columns?: string[];
    }) => void,
    onError: (err: {
      type: string;
      message: string;
      shortfall?: number;
    }) => void
  ) => {
    const startTime = performance.now();
    try {
      // 1. Submit natural language question to backend POST /query with dataset ID
      const res = await api.query.execute(prompt, dataset.id);
      const execTime = Math.round(performance.now() - startTime);

      const charged = res.credits_charged ?? 0;
      const rows = res.results || [];
      const cols = res.columns || (rows.length > 0 ? Object.keys(rows[0]) : []);

      // 2. Record query in local session history
      const historyItem: QueryHistoryItem = {
        id: `qh_${Date.now()}`,
        userId: effectiveUser.id,
        datasetId: dataset.id,
        datasetName: dataset.title || dataset.name,
        naturalPrompt: prompt,
        generatedSql: res.sql_query || '-- No SQL returned',
        rowsReturned: rows.length,
        status: 'SUCCESS',
        creditsCharged: charged,
        timestamp: new Date().toISOString().replace('T', ' ').substring(0, 19),
        executionTimeMs: execTime,
      };
      setQueryHistory((prev) => [historyItem, ...prev]);

      // 3. Refresh authoritative user credit balance from GET /auth/me
      try {
        const me = await api.auth.getMe();
        setCurrentUser((prev) => (prev ? { ...prev, credits: me.credits } : null));
      } catch {
        // ignore
      }

      // 4. Refresh live transactions from GET /credits/transactions if credits were charged
      if (charged > 0) {
        api.credits
          .getTransactions()
          .then((txList) => {
            if (txList) {
              setTransactions(txList.map(transactionItemToWalletTransaction));
            }
          })
          .catch(() => {});
      }

      onSuccess({
        generatedSql: res.sql_query || '',
        rows,
        executionMs: execTime,
        chargedCredits: charged,
        explanation: res.answer,
        recordsAnalyzed: res.records_analyzed,
        matchingDatasets: res.matching_datasets,
        columns: cols,
      });

      if (charged === 0) {
        addToast(
          'QUERY_EXECUTED',
          `Query executed in ${execTime}ms. (0 credits - Free own-dataset access)`,
          'emerald'
        );
      } else {
        addToast(
          'QUERY_EXECUTED',
          `Query executed in ${execTime}ms. (-${charged} credits charged)`,
          'emerald'
        );
      }
    } catch (error: any) {
      const execTime = Math.round(performance.now() - startTime);
      let errorType = 'QUERY_ERROR';
      let errorMessage = error.message || 'Query execution failed.';

      if (error.status === 402) {
        errorType = 'INSUFFICIENT_CREDITS';
        errorMessage = error.message || 'Insufficient credit balance to execute query.';
      } else if (error.status === 422) {
        errorType = error.message?.includes('Security')
          ? 'SQL_SECURITY_ERROR'
          : 'SQL_VALIDATION_ERROR';
      } else if (error.status === 400) {
        errorType = 'INVALID_QUERY';
      } else if (error.status === 404) {
        errorType = 'DATASET_NOT_FOUND';
      } else if (error.status === 503) {
        errorType = 'AI_PROVIDER_ERROR';
      } else if (error.status === 401) {
        errorType = 'UNAUTHORIZED';
        errorMessage = 'Authentication expired. Please sign in again.';
      }

      // Record failed query in queryHistory
      const historyItem: QueryHistoryItem = {
        id: `qh_${Date.now()}`,
        userId: effectiveUser.id,
        datasetId: dataset.id,
        datasetName: dataset.title || dataset.name,
        naturalPrompt: prompt,
        generatedSql: `-- FAILED (${errorType}): ${errorMessage}`,
        rowsReturned: 0,
        status:
          errorType === 'INSUFFICIENT_CREDITS'
            ? 'INSUFFICIENT_CREDITS'
            : 'SQL_REJECTED',
        creditsCharged: 0,
        timestamp: new Date().toISOString().replace('T', ' ').substring(0, 19),
        executionTimeMs: execTime,
      };
      setQueryHistory((prev) => [historyItem, ...prev]);

      onError({
        type: errorType,
        message: errorMessage,
      });

      addToast(
        errorType,
        errorMessage,
        errorType === 'INSUFFICIENT_CREDITS' ? 'amber' : 'rose'
      );
    }
  };

  // Submit Dataset Improvement
  // improvement credits = floor(delta x 0.75) if delta >= 5
  const handleSubmitImprovement = (
    datasetId: string,
    newQuality: number,
    newRelevance: number,
    changesSummary: string,
    creditsAwarded: number
  ) => {
    setDatasets((prev) =>
      prev.map((d) => {
        if (d.id !== datasetId) return d;
        const currentVerNum = parseInt(d.currentVersion.replace('v', '')) || 1;
        const nextVer = `v${currentVerNum + 1}.0`;
        const newOverall = (newQuality + newRelevance) / 2;

        return {
          ...d,
          qualityScore: newQuality,
          relevanceScore: newRelevance,
          overallScore: newOverall,
          currentVersion: nextVer,
          versionHistory: [
            {
              version: nextVer,
              date: new Date().toISOString().split('T')[0],
              author: effectiveUser.name,
              quality: newQuality,
              relevance: newRelevance,
              changesSummary,
            },
            ...d.versionHistory,
          ],
        };
      })
    );

    if (creditsAwarded > 0) {
      const tx: WalletTransaction = {
        id: `tx_imp_${Date.now()}`,
        userId: effectiveUser.id,
        type: 'IMPROVEMENT_REWARD',
        amount: creditsAwarded,
        description: `Version Improvement Reward (+${creditsAwarded} credits)`,
        timestamp: new Date().toISOString().replace('T', ' ').substring(0, 19),
      };
      const nextTransactions = [tx, ...transactions];
      setTransactions(nextTransactions);

      setCurrentUser((prev) =>
        prev ? { ...prev, credits: prev.credits + creditsAwarded } : null
      );

      addToast(
        'VERSION_IMPROVED',
        `Version upgrade published! You earned +${creditsAwarded} credits.`,
        'emerald'
      );
    } else {
      addToast(
        'VERSION_IMPROVED',
        'Version upgrade published without credit reward (delta < 5 pts).',
        'cyan'
      );
    }

    setCurrentRoute('dataset-detail');
  };

  // Wallet Redemption Handler (Min 500 cr, Multiples of 100, 100 cr = Rs 10)
  const handleRedeemCredits = (amount: number, rupeeValue: number) => {
    if (effectiveUser.credits < amount || amount < 500 || amount % 100 !== 0) return;

    const tx: WalletTransaction = {
      id: `tx_red_${Date.now()}`,
      userId: effectiveUser.id,
      type: 'REDEMPTION',
      amount: -amount,
      description: `Simulated Cash Payout: Redeemed ${amount} credits for ₹${rupeeValue.toFixed(2)}`,
      timestamp: new Date().toISOString().replace('T', ' ').substring(0, 19),
      rupeeValue,
    };
    const nextTransactions = [tx, ...transactions];
    setTransactions(nextTransactions);

    setCurrentUser((prev) =>
      prev ? { ...prev, credits: Math.max(0, prev.credits - amount) } : null
    );

    addToast(
      'REDEMPTION_PROCESSED',
      `Redeemed ${amount} credits for ₹${rupeeValue.toFixed(2)} (Simulated Payout).`,
      'emerald'
    );
  };

  // Top Up Credits Handler
  const handleTopUpCredits = (amount: number) => {
    const tx: WalletTransaction = {
      id: `tx_top_${Date.now()}`,
      userId: effectiveUser.id,
      type: 'MANUAL_RELOAD',
      amount: amount,
      description: `Credits Pool Top-Up (+${amount} credits)`,
      timestamp: new Date().toISOString().replace('T', ' ').substring(0, 19),
    };
    const nextTransactions = [tx, ...transactions];
    setTransactions(nextTransactions);

    setCurrentUser((prev) =>
      prev ? { ...prev, credits: prev.credits + amount } : null
    );

    addToast('WALLET_TOPPED_UP', `Added +${amount} credits.`, 'emerald');
  };

  // Detail View & Query Navigation Helpers
  const handleOpenDetail = (datasetId: string) => {
    setSelectedDatasetId(datasetId);
    setCurrentRoute('dataset-detail');
  };

  const handleOpenQueryWorkspace = (datasetId: string, prompt?: string) => {
    setSelectedDatasetId(datasetId);
    if (prompt) setWorkspaceInitialPrompt(prompt);
    setCurrentRoute('query');
  };

  const handleOpenImprove = (datasetId: string) => {
    setSelectedDatasetId(datasetId);
    setCurrentRoute('versions-improve');
  };

  const activeDataset =
    datasets.find((d) => d.id === selectedDatasetId) || datasets[0] || INITIAL_DATASETS[0];

  if (isAuthRestoring && api.auth.getToken()) {
    return (
      <div className="bg-[#F8FAFC] text-slate-900 font-sans min-h-screen flex items-center justify-center">
        <div className="text-center space-y-3">
          <div className="w-8 h-8 border-2 border-indigo-600 border-t-transparent rounded-full animate-spin mx-auto" />
          <p className="text-xs font-semibold text-slate-500">Restoring session...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-[#F8FAFC] text-slate-900 font-sans min-h-screen selection:bg-indigo-100 selection:text-indigo-900">
      {/* Toast Container Stack */}
      <ToastContainer toasts={toasts} onDismiss={removeToast} />

      {/* Navigation Header */}
      <Navbar
        currentRoute={currentRoute}
        onNavigate={handleNavigate}
        currentUser={currentUser}
        onSwitchUser={handleSwitchUser}
        isAuthenticated={isAuthenticated}
        onLogout={handleLogout}
      />

      {/* Main Container */}
      <main className="max-w-[1600px] mx-auto px-4 sm:px-6 lg:px-8 py-8 min-h-[calc(100vh-140px)]">
        {currentRoute === 'landing' && (
          <LandingView onNavigate={handleNavigate} />
        )}

        {currentRoute === 'login' && (
          <LoginRegisterView
            onLoginSuccess={handleAuthSuccess}
            onNavigate={handleNavigate}
          />
        )}

        {currentRoute === 'dashboard' && (
          <DashboardView
            currentUser={effectiveUser}
            datasets={datasets}
            queryHistory={queryHistory}
            transactions={transactions}
            onNavigate={handleNavigate}
            onSelectDatasetForDetail={handleOpenDetail}
          />
        )}

        {currentRoute === 'marketplace' && (
          <MarketplaceView
            datasets={datasets}
            currentUser={effectiveUser}
            onSelectDatasetForDetail={handleOpenDetail}
            onNavigate={handleNavigate}
            onDatasetsLoaded={(fresh) => {
              if (fresh.length > 0) {
                setDatasets((prev) => {
                  const map = new Map<string, AppDataset>();
                  prev.forEach((d) => map.set(d.id, d));
                  fresh.forEach((d) => map.set(d.id, d));
                  return Array.from(map.values());
                });
              }
            }}
          />
        )}

        {currentRoute === 'dataset-detail' && (
          <DatasetDetailView
            dataset={activeDataset}
            currentUser={effectiveUser}
            onNavigate={handleNavigate}
            onOpenQueryWithPrompt={handleOpenQueryWorkspace}
            onImproveDataset={handleOpenImprove}
          />
        )}

        {currentRoute === 'upload' && (
          <UploadWizardView
            currentUser={effectiveUser}
            onPublishDataset={handlePublishDataset}
            onNavigate={handleNavigate}
          />
        )}

        {currentRoute === 'query' && (
          <QueryWorkspaceView
            currentUser={effectiveUser}
            datasets={datasets}
            selectedDatasetId={selectedDatasetId}
            onSelectDataset={setSelectedDatasetId}
            initialPrompt={workspaceInitialPrompt}
            onExecuteQuery={handleExecuteQuery}
            sessionHistory={queryHistory.filter((q) => q.userId === effectiveUser.id)}
          />
        )}

        {currentRoute === 'query-history' && (
          <QueryHistoryView
            history={queryHistory}
            currentUserId={effectiveUser.id}
          />
        )}

        {currentRoute === 'my-datasets' && (
          <MyDatasetsView
            currentUser={effectiveUser}
            datasets={datasets}
            onNavigate={handleNavigate}
            onSelectDatasetForDetail={handleOpenDetail}
            onOpenQuery={handleOpenQueryWorkspace}
            onImproveDataset={handleOpenImprove}
          />
        )}

        {currentRoute === 'versions-improve' && (
          <VersionsImproveView
            currentUser={effectiveUser}
            datasets={datasets}
            selectedDatasetId={selectedDatasetId}
            onSelectDataset={setSelectedDatasetId}
            onSubmitImprovement={handleSubmitImprovement}
          />
        )}

        {currentRoute === 'wallet' && (
          <WalletView
            currentUser={effectiveUser}
            transactions={transactions}
            onRedeemCredits={handleRedeemCredits}
            onTopUpCredits={handleTopUpCredits}
            onBalanceUpdated={(newBal) => {
              setCurrentUser((prev) => (prev ? { ...prev, credits: newBal } : null));
            }}
          />
        )}

        {currentRoute === 'profile' && (
          <ProfileView
            currentUser={effectiveUser}
            onSwitchUser={handleSwitchUser}
            datasets={datasets}
            queryHistory={queryHistory}
          />
        )}

        {currentRoute === '404' && (
          <NotFoundView onNavigate={handleNavigate} />
        )}
      </main>

      {/* Footer (Required exact string: "DataPulse • Mock mode • 100 credits = Rs 10 (simulated redemption)") */}
      <footer className="border-t border-slate-200 bg-white py-6 text-xs text-slate-500">
        <div className="max-w-[1600px] mx-auto px-4 sm:px-6 lg:px-8 text-center sm:text-left">
          <span>DataPulse • Mock mode • 100 credits = Rs 10 (simulated redemption)</span>
        </div>
      </footer>
    </div>
  );
}
