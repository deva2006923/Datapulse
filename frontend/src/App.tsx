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
  INITIAL_USERS,
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

  // Load from localStorage or initialize from fresh seed data
  const [users, setUsers] = useState<Record<string, UserAccount>>(() => {
    try {
      const storedVer = localStorage.getItem('datapulse_version_key');
      if (storedVer === MOCK_DATA_VERSION) {
        const saved = localStorage.getItem(`${MOCK_STORAGE_KEY}_users`);
        if (saved) return JSON.parse(saved);
      }
    } catch (e) {
      // fallback
    }
    return INITIAL_USERS;
  });

  const [currentUserId, setCurrentUserId] = useState<string>('demo-user');

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

  // Persist state & set version key
  useEffect(() => {
    try {
      localStorage.setItem('datapulse_version_key', MOCK_DATA_VERSION);
      localStorage.setItem(`${MOCK_STORAGE_KEY}_users`, JSON.stringify(users));
      localStorage.setItem(`${MOCK_STORAGE_KEY}_datasets`, JSON.stringify(datasets));
      localStorage.setItem(`${MOCK_STORAGE_KEY}_transactions`, JSON.stringify(transactions));
      localStorage.setItem(`${MOCK_STORAGE_KEY}_history`, JSON.stringify(queryHistory));
    } catch (e) {
      // ignore
    }
  }, [users, datasets, transactions, queryHistory]);

  const currentUser = users[currentUserId] || users['demo-user'];

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
          role: users[me.id]?.role || 'Contributor',
          credits: me.credits,
          reputationScore: users[me.id]?.reputationScore ?? 85,
          contributedDatasetIds: users[me.id]?.contributedDatasetIds || [],
          unlockedDatasetIds: users[me.id]?.unlockedDatasetIds || [],
          joinedDate: me.created_at
            ? me.created_at.split('T')[0]
            : new Date().toISOString().split('T')[0],
        };

        setUsers((prev) => ({ ...prev, [me.id]: restoredAccount }));
        setCurrentUserId(me.id);
        setIsAuthenticated(true);
      } catch {
        if (!isMounted) return;
        api.auth.logout();
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
    token: string,
    role: 'Contributor' | 'Data Analyst' = 'Contributor'
  ) => {
    const userAccount: UserAccount = {
      id: user.id,
      name: user.full_name,
      email: user.email,
      role: users[user.id]?.role || role,
      credits: user.credits,
      reputationScore: users[user.id]?.reputationScore ?? 85,
      contributedDatasetIds: users[user.id]?.contributedDatasetIds || [],
      unlockedDatasetIds: users[user.id]?.unlockedDatasetIds || [],
      joinedDate: user.created_at
        ? user.created_at.split('T')[0]
        : new Date().toISOString().split('T')[0],
    };

    setUsers((prev) => ({ ...prev, [user.id]: userAccount }));
    setCurrentUserId(user.id);
    setIsAuthenticated(true);
    setCurrentRoute('dashboard');
    addToast(
      'SESSION_ACTIVE',
      `Welcome, ${user.full_name}! Active session verified.`,
      'emerald'
    );
  };

  const handleLogout = () => {
    api.auth.logout();
    setIsAuthenticated(false);
    setCurrentRoute('login');
    addToast('SESSION_ENDED', 'You have been successfully signed out.', 'emerald');
  };

  // Switch Active User (with backend demo authentication)
  const handleSwitchUser = async (userId: string) => {
    try {
      const res = await api.auth.demoLogin(userId);
      handleAuthSuccess(res.user, res.access_token);
    } catch {
      if (users[userId]) {
        setCurrentUserId(userId);
        addToast('ACCOUNT_SWITCHED', `Active session switched to ${users[userId].name}.`, 'emerald');
      }
    }
  };

  // Register New User (Starts with 100 credits)
  const handleRegisterUser = (
    name: string,
    email: string,
    role: 'Contributor' | 'Data Analyst'
  ) => {
    const newId = `user_${Date.now()}`;
    const newUser: UserAccount = {
      id: newId,
      name,
      email,
      role,
      credits: 100, // New users get 100 credits
      reputationScore: 85,
      contributedDatasetIds: [],
      unlockedDatasetIds: [],
      joinedDate: new Date().toISOString().split('T')[0],
    };

    const signupTx: WalletTransaction = {
      id: `tx_${Date.now()}`,
      userId: newId,
      type: 'SIGNUP_BONUS',
      amount: 100,
      description: 'Welcome Sign-up Credit Allocation (+100 credits)',
      timestamp: new Date().toISOString().replace('T', ' ').substring(0, 19),
    };

    setUsers((prev) => ({ ...prev, [newId]: newUser }));
    setTransactions((prev) => [signupTx, ...prev]);
    setCurrentUserId(newId);
    setCurrentRoute('dashboard');
    addToast('WELCOME_BONUS', 'Account created! Received +100 welcome credits.', 'emerald');
  };

  // Upload Wizard Final Publish
  // upload credits = 50 + floor(quality x 0.30) + floor(relevance / 6)
  const handlePublishDataset = (newDataset: AppDataset, earnedCredits: number) => {
    setDatasets((prev) => [newDataset, ...prev]);

    // Record wallet ledger transaction
    const tx: WalletTransaction = {
      id: `tx_up_${Date.now()}`,
      userId: currentUser.id,
      type: 'UPLOAD_REWARD',
      amount: earnedCredits,
      description: `Dataset Ingestion Reward for ${newDataset.title} (+${earnedCredits} credits)`,
      timestamp: new Date().toISOString().replace('T', ' ').substring(0, 19),
    };
    const nextTransactions = [tx, ...transactions];
    setTransactions(nextTransactions);

    // Update user credits to strictly equal wallet ledger sum
    const newBalance = nextTransactions
      .filter((t) => t.userId === currentUser.id)
      .reduce((sum, t) => sum + t.amount, 0);

    setUsers((prev) => {
      const u = prev[currentUser.id];
      if (!u) return prev;
      return {
        ...prev,
        [currentUser.id]: {
          ...u,
          credits: newBalance,
          contributedDatasetIds: [...u.contributedDatasetIds, newDataset.id],
          unlockedDatasetIds: [...u.unlockedDatasetIds, newDataset.id],
        },
      };
    });

    setSelectedDatasetId(newDataset.id);
    addToast(
      'DATASET_PUBLISHED',
      `Dataset approved! You earned +${earnedCredits} credits.`,
      'emerald'
    );
  };

  // Query Execution & Unlock Charge Logic
  const handleExecuteQuery = (
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
  ) => {
    // 1. Check for Forbidden SQL mutations (DELETE / DROP / UPDATE / INSERT / ALTER / TRUNCATE)
    const upperPrompt = prompt.toUpperCase();
    const isForbidden =
      upperPrompt.includes('DELETE') ||
      upperPrompt.includes('DROP') ||
      upperPrompt.includes('UPDATE') ||
      upperPrompt.includes('INSERT') ||
      upperPrompt.includes('ALTER') ||
      upperPrompt.includes('TRUNCATE');

    if (isForbidden) {
      setTimeout(() => {
        const historyItem: QueryHistoryItem = {
          id: `qh_${Date.now()}`,
          userId: currentUser.id,
          datasetId: dataset.id,
          datasetName: dataset.name,
          naturalPrompt: prompt,
          generatedSql: `-- SQL_REJECTED: Mutating queries rejected\n-- Input statement: ${prompt}`,
          rowsReturned: 0,
          status: 'SQL_REJECTED',
          creditsCharged: 0,
          timestamp: new Date().toISOString().replace('T', ' ').substring(0, 19),
          executionTimeMs: 4.1,
        };
        setQueryHistory((prev) => [historyItem, ...prev]);

        onError({
          type: 'SQL_REJECTED',
          message:
            'Destructive mutations (DELETE, DROP, UPDATE, INSERT, ALTER) are rejected by read-only query safety policies. No charges applied.',
        });
        addToast(
          'SQL_REJECTED',
          'Forbidden mutation blocked. Read-only policy enforced.',
          'rose'
        );
      }, 300);
      return;
    }

    // 2. Check Unlock Status & Cost
    const isOwner = dataset.authorId === currentUser.id;
    const isAlreadyUnlocked = isOwner || dataset.unlockedBy.includes(currentUser.id);
    const unlockCost = dataset.cost || 20;

    // If locked, unlock cost is 20 credits, charged only after successful query
    if (!isAlreadyUnlocked) {
      if (currentUser.credits < unlockCost) {
        const shortfall = unlockCost - currentUser.credits;
        setTimeout(() => {
          const historyItem: QueryHistoryItem = {
            id: `qh_${Date.now()}`,
            userId: currentUser.id,
            datasetId: dataset.id,
            datasetName: dataset.name,
            naturalPrompt: prompt,
            generatedSql: `-- INSUFFICIENT_CREDITS: Required ${unlockCost} credits, Current ${currentUser.credits} credits`,
            rowsReturned: 0,
            status: 'INSUFFICIENT_CREDITS',
            creditsCharged: 0,
            timestamp: new Date().toISOString().replace('T', ' ').substring(0, 19),
            executionTimeMs: 2.5,
          };
          setQueryHistory((prev) => [historyItem, ...prev]);

          onError({
            type: 'INSUFFICIENT_CREDITS',
            message: `Insufficient credits to unlock dataset. Shortfall: ${shortfall} credits.`,
            shortfall,
          });
          addToast(
            'INSUFFICIENT_CREDITS',
            `Need ${shortfall} more credits to unlock this dataset.`,
            'amber'
          );
        }, 300);
        return;
      }
    }

    // 3. Normal Successful Query Execution
    setTimeout(() => {
      const execTime = +(11 + Math.random() * 8).toFixed(1);
      const tableName = dataset.name.replace(/\.[^/.]+$/, '').toLowerCase();
      const cols = dataset.columns.map((c) => c.name).slice(0, 4).join(', ');
      const sql = `SELECT ${cols} \nFROM ${tableName} \nWHERE 1=1 \nORDER BY 1 DESC \nLIMIT 5;`;

      let charged = 0;
      let nextTransactions = [...transactions];

      // Charge 20 credits once if this was the first unlock
      if (!isAlreadyUnlocked) {
        charged = unlockCost;

        // Record User Query Charge
        const chargeTx: WalletTransaction = {
          id: `tx_ch_${Date.now()}`,
          userId: currentUser.id,
          type: 'QUERY_CHARGE',
          amount: -unlockCost,
          description: `Dataset Unlock & Query Charge for ${dataset.title} (-${unlockCost} credits)`,
          timestamp: new Date().toISOString().replace('T', ' ').substring(0, 19),
        };

        // Record Contributor Royalty (+20)
        const royaltyTx: WalletTransaction = {
          id: `tx_roy_${Date.now()}`,
          userId: dataset.authorId,
          type: 'CONTRIBUTOR_ROYALTY',
          amount: 20,
          description: `Unlock Royalty from ${currentUser.name} on ${dataset.title} (+20 credits)`,
          timestamp: new Date().toISOString().replace('T', ' ').substring(0, 19),
        };

        nextTransactions = [chargeTx, royaltyTx, ...nextTransactions];
        setTransactions(nextTransactions);

        // Deduct 20 from current user and give +20 to contributor
        setUsers((prev) => {
          const u = prev[currentUser.id];
          const author = prev[dataset.authorId];
          const updated = { ...prev };

          if (u) {
            const uBalance = nextTransactions
              .filter((t) => t.userId === currentUser.id)
              .reduce((sum, t) => sum + t.amount, 0);

            updated[currentUser.id] = {
              ...u,
              credits: uBalance,
              unlockedDatasetIds: [...u.unlockedDatasetIds, dataset.id],
            };
          }

          if (author && author.id !== currentUser.id) {
            const authorBalance = nextTransactions
              .filter((t) => t.userId === author.id)
              .reduce((sum, t) => sum + t.amount, 0);

            updated[author.id] = {
              ...author,
              credits: authorBalance,
            };
          }

          return updated;
        });

        // Mark dataset as unlocked
        setDatasets((prev) =>
          prev.map((d) =>
            d.id === dataset.id
              ? { ...d, unlockedBy: [...d.unlockedBy, currentUser.id], usageCount: (d.usageCount || 0) + 1 }
              : d
          )
        );

        addToast(
          'DATASET_UNLOCKED',
          `Dataset unlocked (-${unlockCost} credits). Contributor (${dataset.authorName}) earned +20 credits!`,
          'emerald'
        );
      } else {
        // Increment usage count
        setDatasets((prev) =>
          prev.map((d) =>
            d.id === dataset.id ? { ...d, usageCount: (d.usageCount || 0) + 1 } : d
          )
        );
      }

      // Log successful query history
      const historyItem: QueryHistoryItem = {
        id: `qh_${Date.now()}`,
        userId: currentUser.id,
        datasetId: dataset.id,
        datasetName: dataset.name,
        naturalPrompt: prompt,
        generatedSql: sql,
        rowsReturned: dataset.previewRows.length,
        status: 'SUCCESS',
        creditsCharged: charged,
        timestamp: new Date().toISOString().replace('T', ' ').substring(0, 19),
        executionTimeMs: execTime,
      };
      setQueryHistory((prev) => [historyItem, ...prev]);

      const explanation = `Query matched criteria against ${dataset.title} (${dataset.rowCount.toLocaleString()} rows). Compiled read-only query filtered and returned top ${dataset.previewRows.length} rows in ${execTime}ms.`;

      onSuccess({
        generatedSql: sql,
        rows: dataset.previewRows,
        executionMs: execTime,
        chargedCredits: charged,
        explanation,
      });

      if (charged === 0) {
        addToast('QUERY_EXECUTED', `Query executed in ${execTime}ms. (0 credits - already unlocked)`, 'emerald');
      }
    }, 600);
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
              author: currentUser.name,
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
        userId: currentUser.id,
        type: 'IMPROVEMENT_REWARD',
        amount: creditsAwarded,
        description: `Version Improvement Reward (+${creditsAwarded} credits)`,
        timestamp: new Date().toISOString().replace('T', ' ').substring(0, 19),
      };
      const nextTransactions = [tx, ...transactions];
      setTransactions(nextTransactions);

      const newBalance = nextTransactions
        .filter((t) => t.userId === currentUser.id)
        .reduce((sum, t) => sum + t.amount, 0);

      setUsers((prev) => {
        const u = prev[currentUser.id];
        if (!u) return prev;
        return {
          ...prev,
          [currentUser.id]: {
            ...u,
            credits: newBalance,
          },
        };
      });

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
    if (currentUser.credits < amount || amount < 500 || amount % 100 !== 0) return;

    const tx: WalletTransaction = {
      id: `tx_red_${Date.now()}`,
      userId: currentUser.id,
      type: 'REDEMPTION',
      amount: -amount,
      description: `Simulated Cash Payout: Redeemed ${amount} credits for ₹${rupeeValue.toFixed(2)}`,
      timestamp: new Date().toISOString().replace('T', ' ').substring(0, 19),
      rupeeValue,
    };
    const nextTransactions = [tx, ...transactions];
    setTransactions(nextTransactions);

    const newBalance = nextTransactions
      .filter((t) => t.userId === currentUser.id)
      .reduce((sum, t) => sum + t.amount, 0);

    setUsers((prev) => {
      const u = prev[currentUser.id];
      if (!u) return prev;
      return {
        ...prev,
        [currentUser.id]: {
          ...u,
          credits: newBalance,
        },
      };
    });

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
      userId: currentUser.id,
      type: 'MANUAL_RELOAD',
      amount: amount,
      description: `Credits Pool Top-Up (+${amount} credits)`,
      timestamp: new Date().toISOString().replace('T', ' ').substring(0, 19),
    };
    const nextTransactions = [tx, ...transactions];
    setTransactions(nextTransactions);

    const newBalance = nextTransactions
      .filter((t) => t.userId === currentUser.id)
      .reduce((sum, t) => sum + t.amount, 0);

    setUsers((prev) => {
      const u = prev[currentUser.id];
      if (!u) return prev;
      return {
        ...prev,
        [currentUser.id]: {
          ...u,
          credits: newBalance,
        },
      };
    });

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
        allUsers={users}
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
            onLoginAs={handleSwitchUser}
            onRegisterUser={handleRegisterUser}
            onNavigate={handleNavigate}
          />
        )}

        {currentRoute === 'dashboard' && (
          <DashboardView
            currentUser={currentUser}
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
            currentUser={currentUser}
            onSelectDatasetForDetail={handleOpenDetail}
            onNavigate={handleNavigate}
          />
        )}

        {currentRoute === 'dataset-detail' && (
          <DatasetDetailView
            dataset={activeDataset}
            currentUser={currentUser}
            onNavigate={handleNavigate}
            onOpenQueryWithPrompt={handleOpenQueryWorkspace}
            onImproveDataset={handleOpenImprove}
          />
        )}

        {currentRoute === 'upload' && (
          <UploadWizardView
            currentUser={currentUser}
            onPublishDataset={handlePublishDataset}
            onNavigate={handleNavigate}
          />
        )}

        {currentRoute === 'query' && (
          <QueryWorkspaceView
            currentUser={currentUser}
            datasets={datasets}
            selectedDatasetId={selectedDatasetId}
            onSelectDataset={setSelectedDatasetId}
            initialPrompt={workspaceInitialPrompt}
            onExecuteQuery={handleExecuteQuery}
            sessionHistory={queryHistory.filter((q) => q.userId === currentUser.id)}
          />
        )}

        {currentRoute === 'query-history' && (
          <QueryHistoryView
            history={queryHistory}
            currentUserId={currentUser.id}
          />
        )}

        {currentRoute === 'my-datasets' && (
          <MyDatasetsView
            currentUser={currentUser}
            datasets={datasets}
            onNavigate={handleNavigate}
            onSelectDatasetForDetail={handleOpenDetail}
            onOpenQuery={handleOpenQueryWorkspace}
            onImproveDataset={handleOpenImprove}
          />
        )}

        {currentRoute === 'versions-improve' && (
          <VersionsImproveView
            currentUser={currentUser}
            datasets={datasets}
            selectedDatasetId={selectedDatasetId}
            onSelectDataset={setSelectedDatasetId}
            onSubmitImprovement={handleSubmitImprovement}
          />
        )}

        {currentRoute === 'wallet' && (
          <WalletView
            currentUser={currentUser}
            transactions={transactions}
            onRedeemCredits={handleRedeemCredits}
            onTopUpCredits={handleTopUpCredits}
          />
        )}

        {currentRoute === 'profile' && (
          <ProfileView
            currentUser={currentUser}
            allUsers={users}
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
