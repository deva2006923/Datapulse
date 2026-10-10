import React, { useState, useEffect, useCallback } from 'react';
import {
  Wallet,
  Coins,
  ArrowUpRight,
  Plus,
  CreditCard,
  Clock,
  CheckCircle2,
  AlertTriangle,
  Info,
  Filter,
  Loader2,
  RefreshCw,
  AlertCircle,
} from 'lucide-react';
import { UserAccount, WalletTransaction, TransactionItem } from '../types';
import { api, ApiError } from '../services/api';
import { transactionItemToWalletTransaction } from '../services/datasetAdapter';

interface WalletViewProps {
  currentUser: UserAccount;
  transactions?: WalletTransaction[];
  onRedeemCredits?: (amount: number, rupeeValue: number) => void;
  onTopUpCredits?: (amount: number) => void;
  onBalanceUpdated?: (newBalance: number) => void;
}

export const WalletView: React.FC<WalletViewProps> = ({
  currentUser,
  transactions: initialTransactions = [],
  onRedeemCredits,
  onTopUpCredits,
  onBalanceUpdated,
}) => {
  const [redeemAmount, setRedeemAmount] = useState<number>(500);
  const [redeemSuccess, setRedeemSuccess] = useState<string | null>(null);
  const [redeemError, setRedeemError] = useState<string | null>(null);
  const [isRedeeming, setIsRedeeming] = useState<boolean>(false);
  const [typeFilter, setTypeFilter] = useState<string>('All');

  const [realTransactions, setRealTransactions] = useState<WalletTransaction[]>(
    initialTransactions
  );
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [topUpNotice, setTopUpNotice] = useState<string | null>(null);

  const fetchTransactionsAndBalance = useCallback(async () => {
    setIsLoading(true);
    setLoadError(null);

    try {
      // 1. Fetch live transactions from GET /credits/transactions
      const rawTxList = await api.credits.getTransactions();
      const mapped = rawTxList.map(transactionItemToWalletTransaction);
      setRealTransactions(mapped);

      // 2. Fetch authoritative user balance from GET /auth/me
      const me = await api.auth.getMe();
      if (onBalanceUpdated) {
        onBalanceUpdated(me.credits);
      }
    } catch (err: any) {
      const message =
        err instanceof ApiError
          ? err.message
          : 'Unable to retrieve transactions from backend server.';
      setLoadError(message);
    } finally {
      setIsLoading(false);
    }
  }, [onBalanceUpdated]);

  useEffect(() => {
    fetchTransactionsAndBalance();
  }, [fetchTransactionsAndBalance]);

  // Conversion rate: 100 credits = Rs 10 (1 credit = Rs 0.10)
  const rupeePreview = (redeemAmount / 100) * 10;

  // Authoritative credit balance from authenticated currentUser
  const currentBalance = currentUser.credits;

  const isMinMet = redeemAmount >= 500;
  const isMultipleOf100 = redeemAmount % 100 === 0;
  const hasEnoughCredits = currentBalance >= redeemAmount;
  const canRedeem = isMinMet && isMultipleOf100 && hasEnoughCredits && !isRedeeming;

  const handleRedeem = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!canRedeem) return;

    setIsRedeeming(true);
    setRedeemSuccess(null);
    setRedeemError(null);

    try {
      const res = await api.credits.redeem({
        amount: redeemAmount,
        payout_method: 'upi',
        destination: currentUser.email || 'user@datapulse.io',
      });

      setRedeemSuccess(
        res.message ||
          `Successfully redeemed ${res.redeemed_credits} credits for $${res.cash_value_usd} USD.`
      );

      // Refresh balance and transactions from authoritative backend
      await fetchTransactionsAndBalance();

      if (onRedeemCredits) {
        onRedeemCredits(res.redeemed_credits, rupeePreview);
      }
    } catch (err: any) {
      const message =
        err instanceof ApiError
          ? err.message
          : 'Redemption failed. Please verify your balance and try again.';
      setRedeemError(message);
    } finally {
      setIsRedeeming(false);
    }
  };

  const handleTopUpAttempt = (amount: number) => {
    setTopUpNotice(
      `Credit top-up (+${amount} cr) has no backend endpoint. Accumulate credits by uploading verified datasets or earning contributor query royalties.`
    );
    setTimeout(() => setTopUpNotice(null), 6000);
  };

  const filteredTransactions = realTransactions.filter((tx) => {
    if (typeFilter === 'All') return true;
    if (typeFilter === 'Rewards')
      return tx.type === 'UPLOAD_REWARD' || tx.type === 'SIGNUP_BONUS' || tx.type === 'IMPROVEMENT_REWARD';
    if (typeFilter === 'Royalties') return tx.type === 'CONTRIBUTOR_ROYALTY';
    if (typeFilter === 'Charges') return tx.type === 'QUERY_CHARGE';
    if (typeFilter === 'Redemptions') return tx.type === 'REDEMPTION';
    return true;
  });

  return (
    <div className="space-y-6">
      {/* Required Banner: "Simulated redemption. No real money is transferred." */}
      <div className="bg-amber-50 border border-amber-300 rounded-xl p-4 shadow-xs flex items-center gap-3">
        <Info className="w-5 h-5 text-amber-700 shrink-0" />
        <div className="text-xs text-amber-900">
          <strong className="font-semibold uppercase tracking-wider block">
            Notice
          </strong>
          <span>Simulated redemption. No real money is transferred.</span>
        </div>
      </div>

      {/* TopUp Notice Toast/Banner */}
      {topUpNotice && (
        <div className="bg-indigo-50 border border-indigo-200 rounded-xl p-4 flex items-center gap-3 text-xs text-indigo-900 shadow-xs">
          <Info className="w-4 h-4 text-indigo-600 shrink-0" />
          <span>{topUpNotice}</span>
        </div>
      )}

      {/* Error Banner */}
      {loadError && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-4 flex items-center justify-between gap-3 text-xs text-red-800">
          <div className="flex items-center gap-2">
            <AlertCircle className="w-4 h-4 text-red-600 shrink-0" />
            <span>{loadError}</span>
          </div>
          <button
            onClick={fetchTransactionsAndBalance}
            className="px-3 py-1 bg-white border border-red-300 rounded-lg text-red-700 font-semibold hover:bg-red-50 cursor-pointer flex items-center gap-1.5 shrink-0"
          >
            <RefreshCw className="w-3 h-3" />
            <span>Retry</span>
          </button>
        </div>
      )}

      {/* Balance Card & Quick Top-Ups */}
      <div className="grid grid-cols-1 md:grid-cols-12 gap-6">
        {/* Credit Balance Card */}
        <div className="md:col-span-5 bg-white border border-slate-200 rounded-xl p-6 shadow-sm flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-semibold text-slate-500 uppercase tracking-wide">
                Credit balance
              </span>
              <span className="text-xs font-mono font-medium text-emerald-700 bg-emerald-50 border border-emerald-200 px-2 py-0.5 rounded">
                Authoritative Backend Balance
              </span>
            </div>
            <div className="flex items-baseline gap-2">
              <span className="text-4xl sm:text-5xl font-black font-mono text-emerald-600">
                {currentBalance.toLocaleString()}
              </span>
              <span className="text-lg font-bold text-slate-500">cr</span>
            </div>
            <p className="text-xs text-slate-500 mt-2">
              Equivalent conversion value:{' '}
              <strong className="text-slate-800 font-mono">
                ₹{((currentBalance / 100) * 10).toFixed(2)}
              </strong>{' '}
              (at 100 credits = Rs 10)
            </p>
          </div>

          <div className="pt-6 border-t border-slate-100 flex items-center justify-between">
            <span className="text-xs text-slate-500">Account Owner:</span>
            <span className="text-xs font-semibold text-slate-800">
              {currentUser.name}
            </span>
          </div>
        </div>

        {/* Quick Top-Up Bar */}
        <div className="md:col-span-7 bg-white border border-slate-200 rounded-xl p-6 shadow-sm space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-sm font-bold text-slate-900">
                Credits Accumulation Info
              </h2>
              <p className="text-xs text-slate-500 mt-0.5">
                Earn credits automatically by contributing datasets or through query royalties.
              </p>
            </div>
            <Coins className="w-5 h-5 text-indigo-600" />
          </div>

          <div className="grid grid-cols-3 gap-3">
            <button
              onClick={() => handleTopUpAttempt(100)}
              className="p-3 rounded-xl bg-slate-50 hover:bg-indigo-50 hover:border-indigo-200 border border-slate-200 transition-colors text-center cursor-pointer group"
            >
              <span className="text-xs font-bold text-slate-800 group-hover:text-indigo-600 block">
                +100 cr
              </span>
              <span className="text-[10px] text-slate-400 font-mono mt-0.5 block">
                Welcome Bonus
              </span>
            </button>

            <button
              onClick={() => handleTopUpAttempt(250)}
              className="p-3 rounded-xl bg-slate-50 hover:bg-indigo-50 hover:border-indigo-200 border border-slate-200 transition-colors text-center cursor-pointer group"
            >
              <span className="text-xs font-bold text-slate-800 group-hover:text-indigo-600 block">
                +250 cr
              </span>
              <span className="text-[10px] text-slate-400 font-mono mt-0.5 block">
                Dataset Rewards
              </span>
            </button>

            <button
              onClick={() => handleTopUpAttempt(500)}
              className="p-3 rounded-xl bg-indigo-50/70 hover:bg-indigo-100/70 border border-indigo-200 transition-colors text-center cursor-pointer group"
            >
              <span className="text-xs font-bold text-indigo-700 block">
                +500 cr
              </span>
              <span className="text-[10px] text-indigo-500 font-mono mt-0.5 block">
                Redeem Ready
              </span>
            </button>
          </div>
        </div>
      </div>

      {/* Redeem Credits Section */}
      <div className="bg-white border border-slate-200 rounded-xl p-6 shadow-sm space-y-5">
        <div className="border-b border-slate-100 pb-3 flex flex-col sm:flex-row sm:items-center justify-between gap-2">
          <div>
            <h2 className="text-base font-bold text-slate-900">
              Redeem Credits for Cash (INR ₹)
            </h2>
            <p className="text-xs text-slate-500 mt-0.5">
              Protocol rules: Minimum redemption is 500 credits. Must be in multiples of 100 credits. 100 credits = ₹10 ($1.00 USD).
            </p>
          </div>
          <span className="text-xs font-mono font-bold text-emerald-600 bg-emerald-50 border border-emerald-200 px-3 py-1 rounded-lg self-start sm:self-auto">
            100 Credits = ₹10
          </span>
        </div>

        {redeemSuccess && (
          <div className="p-3 bg-emerald-50 border border-emerald-300 rounded-lg text-emerald-800 text-xs flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 shrink-0" />
            <span>{redeemSuccess}</span>
          </div>
        )}

        {redeemError && (
          <div className="p-3 bg-red-50 border border-red-300 rounded-lg text-red-800 text-xs flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 shrink-0" />
            <span>{redeemError}</span>
          </div>
        )}

        <form onSubmit={handleRedeem} className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="text-xs font-semibold text-slate-700 block mb-1">
                Credits to Redeem
              </label>
              <input
                type="number"
                step="100"
                min="500"
                value={redeemAmount}
                onChange={(e) => setRedeemAmount(Number(e.target.value))}
                className="w-full bg-slate-50 border border-slate-300 rounded-lg px-3 py-2 text-xs font-mono font-bold text-slate-900 focus:outline-none focus:border-indigo-500"
              />
              <span className="text-[11px] text-slate-400 mt-1 block">
                Minimum: 500 credits • Multiples of 100 credits
              </span>
            </div>

            {/* Live Rupee Preview Card */}
            <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 flex flex-col justify-between">
              <span className="text-xs font-semibold text-slate-500 uppercase tracking-wide block">
                Live Rupee Preview
              </span>
              <div className="flex items-baseline gap-1 mt-1">
                <span className="text-2xl font-black font-mono text-emerald-600">
                  ₹{rupeePreview.toFixed(2)}
                </span>
                <span className="text-xs text-slate-500">INR</span>
              </div>
              <span className="text-[11px] text-slate-400">
                Formula: ({redeemAmount} / 100) × ₹10
              </span>
            </div>
          </div>

          {/* Validation Warnings */}
          <div className="space-y-1">
            {!hasEnoughCredits && (
              <p className="text-xs text-red-600 flex items-center gap-1.5">
                <AlertTriangle className="w-3.5 h-3.5" />
                <span>
                  Insufficient balance. You currently have {currentBalance} credits.
                </span>
              </p>
            )}
            {!isMinMet && (
              <p className="text-xs text-amber-700 flex items-center gap-1.5">
                <AlertTriangle className="w-3.5 h-3.5" />
                <span>Redemption requires a minimum of 500 credits.</span>
              </p>
            )}
            {!isMultipleOf100 && (
              <p className="text-xs text-amber-700 flex items-center gap-1.5">
                <AlertTriangle className="w-3.5 h-3.5" />
                <span>Redemption amount must be in multiples of 100 credits.</span>
              </p>
            )}
          </div>

          <div className="pt-2 flex justify-end">
            <button
              type="submit"
              disabled={!canRedeem}
              className="px-6 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-700 disabled:opacity-40 disabled:cursor-not-allowed text-white font-bold text-xs shadow-xs transition-colors cursor-pointer flex items-center gap-2"
            >
              {isRedeeming ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span>Processing Payout...</span>
                </>
              ) : (
                <>
                  <Coins className="w-4 h-4" />
                  <span>
                    Redeem {redeemAmount} Credits for ₹{rupeePreview.toFixed(2)}
                  </span>
                </>
              )}
            </button>
          </div>
        </form>
      </div>

      {/* Wallet Ledger Table with Filter */}
      <div className="bg-white border border-slate-200 rounded-xl overflow-hidden shadow-sm">
        <div className="p-5 border-b border-slate-200 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div>
            <h3 className="text-sm font-bold text-slate-900">Wallet Ledger</h3>
            <p className="text-xs text-slate-500 mt-0.5">
              Live audit history of rewards, query fees, royalties, and redemptions recorded in analytical storage.
            </p>
          </div>

          {/* Ledger Filter */}
          <div className="flex items-center gap-2">
            <Filter className="w-3.5 h-3.5 text-slate-400" />
            <span className="text-xs text-slate-500 font-medium">Filter:</span>
            <select
              value={typeFilter}
              onChange={(e) => setTypeFilter(e.target.value)}
              className="bg-slate-50 border border-slate-200 rounded-md px-2.5 py-1 text-xs text-slate-700 outline-none"
            >
              <option value="All">All Types</option>
              <option value="Rewards">Upload & Quality Rewards</option>
              <option value="Royalties">Royalties</option>
              <option value="Charges">Query Charges</option>
              <option value="Redemptions">Redemptions</option>
            </select>
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-50 text-slate-500 border-b border-slate-200 text-[11px]">
              <tr>
                <th className="py-2.5 px-4 font-semibold">Timestamp</th>
                <th className="py-2.5 px-4 font-semibold">Type</th>
                <th className="py-2.5 px-4 font-semibold">Description</th>
                <th className="py-2.5 px-4 font-semibold text-right">Amount</th>
                <th className="py-2.5 px-4 font-semibold text-right">Rupee Eq.</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-slate-700">
              {isLoading && realTransactions.length === 0 ? (
                <tr>
                  <td colSpan={5} className="py-8 text-center text-slate-400">
                    <Loader2 className="w-5 h-5 text-indigo-600 animate-spin mx-auto mb-2" />
                    <span>Loading ledger records from backend...</span>
                  </td>
                </tr>
              ) : filteredTransactions.length === 0 ? (
                <tr>
                  <td colSpan={5} className="py-8 text-center text-slate-400">
                    No transactions match the selected filter.
                  </td>
                </tr>
              ) : (
                filteredTransactions.map((tx) => {
                  const isEarned = tx.amount > 0;
                  const rupeeVal =
                    tx.rupeeValue !== undefined
                      ? tx.rupeeValue
                      : (Math.abs(tx.amount) / 100) * 10;

                  return (
                    <tr key={tx.id} className="hover:bg-slate-50/50">
                      <td className="py-3 px-4 font-mono text-[11px] text-slate-500 whitespace-nowrap">
                        {tx.timestamp}
                      </td>
                      <td className="py-3 px-4 whitespace-nowrap">
                        <span
                          className={`px-2 py-0.5 rounded text-[10px] font-semibold ${
                            tx.type === 'SIGNUP_BONUS'
                              ? 'bg-blue-50 text-blue-700 border border-blue-200'
                              : tx.type === 'UPLOAD_REWARD'
                              ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                              : tx.type === 'CONTRIBUTOR_ROYALTY'
                              ? 'bg-indigo-50 text-indigo-700 border border-indigo-200'
                              : tx.type === 'IMPROVEMENT_REWARD'
                              ? 'bg-teal-50 text-teal-700 border border-teal-200'
                              : tx.type === 'REDEMPTION'
                              ? 'bg-purple-50 text-purple-700 border border-purple-200'
                              : 'bg-red-50 text-red-700 border border-red-200'
                          }`}
                        >
                          {tx.type}
                        </span>
                      </td>
                      <td className="py-3 px-4 font-medium text-slate-800">
                        {tx.description}
                      </td>
                      <td className="py-3 px-4 text-right font-mono font-bold whitespace-nowrap">
                        <span
                          className={isEarned ? 'text-emerald-600' : 'text-red-600'}
                        >
                          {isEarned ? `+${tx.amount} cr` : `${tx.amount} cr`}
                        </span>
                      </td>
                      <td className="py-3 px-4 text-right font-mono text-slate-500 whitespace-nowrap">
                        ₹{rupeeVal.toFixed(2)}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
