import React from 'react';
import {
  User,
  Mail,
  ShieldCheck,
  Calendar,
  Coins,
  Database,
  Search,
  CheckCircle2,
  TrendingUp,
} from 'lucide-react';
import { UserAccount, AppDataset, QueryHistoryItem } from '../types';
import { DEMO_ACCOUNTS } from '../services/api';

interface ProfileViewProps {
  currentUser: UserAccount;
  allUsers?: Record<string, UserAccount>;
  onSwitchUser: (demoKey: string) => void;
  datasets: AppDataset[];
  queryHistory: QueryHistoryItem[];
}

export const ProfileView: React.FC<ProfileViewProps> = ({
  currentUser,
  onSwitchUser,
  datasets,
  queryHistory,
}) => {
  const contributedDatasets = datasets.filter((d) => d.authorId === currentUser.id);
  const unlockedDatasets = datasets.filter(
    (d) => d.unlockedBy.includes(currentUser.id) && d.authorId !== currentUser.id
  );
  const userQueries = queryHistory.filter((q) => q.userId === currentUser.id);

  // Compute royalties
  const totalRoyalties = contributedDatasets.reduce((acc, d) => {
    const unlocks = d.unlockedBy.filter((uid) => uid !== d.authorId).length;
    return acc + unlocks * 20;
  }, 0);

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      {/* Header Profile Card */}
      <div className="bg-white border border-slate-200 rounded-xl p-6 sm:p-8 shadow-sm">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-6">
          <div className="flex items-center gap-4">
            <div className="w-16 h-16 rounded-2xl bg-indigo-50 border border-indigo-200 flex items-center justify-center text-indigo-600 font-extrabold text-2xl">
              {currentUser.name.charAt(0)}
            </div>
            <div className="space-y-1">
              <div className="flex items-center gap-2">
                <h1 className="text-xl sm:text-2xl font-extrabold text-slate-900 tracking-tight">
                  {currentUser.name}
                </h1>
                <span className="px-2.5 py-0.5 rounded text-xs font-semibold bg-indigo-50 text-indigo-700 border border-indigo-200">
                  {currentUser.role}
                </span>
              </div>
              <p className="text-xs text-slate-500 font-mono flex items-center gap-1.5">
                <Mail className="w-3.5 h-3.5 text-slate-400" />
                <span>{currentUser.email}</span>
              </p>
              <p className="text-xs text-slate-400 flex items-center gap-1.5">
                <Calendar className="w-3.5 h-3.5 text-slate-400" />
                <span>Member since {currentUser.joinedDate}</span>
              </p>
            </div>
          </div>

          <div className="bg-slate-50 border border-slate-200 rounded-xl p-4 text-right shrink-0">
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wide block">
              Credit balance
            </span>
            <div className="text-2xl sm:text-3xl font-black font-mono text-emerald-600 mt-0.5">
              {currentUser.credits.toLocaleString()} cr
            </div>
            <span className="text-[10px] text-slate-400 font-mono">
              ₹{((currentUser.credits / 100) * 10).toFixed(2)} INR
            </span>
          </div>
        </div>
      </div>

      {/* Account Stats Grid */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm">
          <span className="text-xs text-slate-500 font-medium block mb-1">Contributed</span>
          <div className="text-2xl font-black font-mono text-slate-900">
            {contributedDatasets.length}
          </div>
          <span className="text-[10px] text-slate-400">Published datasets</span>
        </div>

        <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm">
          <span className="text-xs text-slate-500 font-medium block mb-1">Unlocked</span>
          <div className="text-2xl font-black font-mono text-slate-900">
            {unlockedDatasets.length}
          </div>
          <span className="text-[10px] text-slate-400">Available catalogs</span>
        </div>

        <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm">
          <span className="text-xs text-slate-500 font-medium block mb-1">Royalties Earned</span>
          <div className="text-2xl font-black font-mono text-indigo-600">
            +{totalRoyalties} cr
          </div>
          <span className="text-[10px] text-slate-400">+20 per unlock</span>
        </div>

        <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm">
          <span className="text-xs text-slate-500 font-medium block mb-1">Queries Run</span>
          <div className="text-2xl font-black font-mono text-slate-900">
            {userQueries.length}
          </div>
          <span className="text-[10px] text-slate-400">Logged in workspace</span>
        </div>
      </div>

      {/* Switch Active User Profile */}
      <div className="bg-white border border-slate-200 rounded-xl p-6 shadow-sm space-y-4">
        <div>
          <h2 className="text-sm font-bold text-slate-900 uppercase tracking-wide">
            Switch Demo Account
          </h2>
          <p className="text-xs text-slate-500 mt-0.5">
            Switch sessions seamlessly to verify contributor royalties, analyst permissions, and balance updates.
          </p>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          {Object.values(DEMO_ACCOUNTS).map((demo) => {
            const isCurrent =
              currentUser.email.toLowerCase() === demo.email.toLowerCase();
            return (
              <button
                key={demo.key}
                onClick={() => onSwitchUser(demo.key)}
                className={`p-4 rounded-xl border text-left transition-all cursor-pointer ${
                  isCurrent
                    ? 'bg-indigo-50/60 border-indigo-300 ring-2 ring-indigo-500/20'
                    : 'bg-slate-50 border-slate-200 hover:bg-slate-100/60'
                }`}
              >
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs font-bold text-slate-900">{demo.full_name}</span>
                  {isCurrent && (
                    <span className="text-[10px] font-semibold text-indigo-700 bg-indigo-100 px-1.5 py-0.5 rounded">
                      Active
                    </span>
                  )}
                </div>
                <div className="text-[11px] text-slate-500 font-mono">{demo.email}</div>
                <div className="mt-2 pt-2 border-t border-slate-200/60 flex items-center justify-between text-xs font-mono">
                  <span className="text-slate-500">{demo.role}</span>
                  {isCurrent ? (
                    <span className="font-bold text-emerald-600">{currentUser.credits} cr</span>
                  ) : (
                    <span className="text-slate-400 font-medium text-[11px]">Switch session</span>
                  )}
                </div>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
};
