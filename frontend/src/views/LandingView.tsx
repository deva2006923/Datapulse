import React from 'react';
import { Search, Database, ArrowRight, Coins, CheckCircle2 } from 'lucide-react';
import { PageRoute } from '../types';

interface LandingViewProps {
  onNavigate: (route: PageRoute) => void;
}

export const LandingView: React.FC<LandingViewProps> = ({ onNavigate }) => {
  return (
    <div className="space-y-10">
      {/* 1. Plain White Landing Hero */}
      <div className="bg-white border border-slate-200 rounded-xl p-8 sm:p-12 shadow-sm">
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-10 items-center">
          {/* Left Column */}
          <div className="lg:col-span-7 space-y-5">
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-md bg-indigo-50 border border-indigo-100 text-indigo-700 text-xs font-semibold">
              <span>Open Data & Analytics Exchange</span>
            </div>
            
            <h1 className="text-4xl sm:text-5xl font-extrabold tracking-tight text-slate-900 leading-[1.15]">
              Contribute data. Earn credits. Query in plain English.
            </h1>
            
            <p className="text-base sm:text-lg text-slate-600 max-w-xl leading-relaxed">
              Upload structured datasets, earn credits through automated evaluation, and query cross-catalog records using natural language.
            </p>
            
            <div className="flex flex-wrap items-center gap-3.5 pt-2">
              <button
                onClick={() => onNavigate('dashboard')}
                className="px-6 py-3 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white font-medium text-sm transition-colors shadow-sm cursor-pointer flex items-center gap-2"
              >
                <span>Get Started</span>
                <ArrowRight className="w-4 h-4" />
              </button>
              <button
                onClick={() => onNavigate('marketplace')}
                className="px-6 py-3 rounded-xl bg-white hover:bg-slate-50 border border-slate-300 text-slate-700 font-medium text-sm transition-colors shadow-xs cursor-pointer flex items-center gap-2"
              >
                <Database className="w-4 h-4 text-slate-500" />
                <span>Browse Datasets</span>
              </button>
            </div>
          </div>

          {/* Right Column: Question Box & Small Result Table */}
          <div className="lg:col-span-5">
            <div className="bg-slate-50 border border-slate-200 rounded-xl p-5 shadow-xs space-y-3.5">
              {/* Question box */}
              <div className="bg-white border border-slate-200 rounded-lg p-3.5 shadow-xs">
                <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider block mb-1">
                  Plain English Question
                </span>
                <div className="flex items-center gap-2.5 text-sm text-slate-900 font-medium">
                  <Search className="w-4 h-4 text-indigo-600 shrink-0" />
                  <span>Show top 10 patients by cholesterol</span>
                </div>
              </div>

              {/* Small result table underneath */}
              <div className="bg-white border border-slate-200 rounded-lg overflow-hidden shadow-xs">
                <div className="px-3.5 py-2.5 bg-slate-50 border-b border-slate-200 flex items-center justify-between text-xs">
                  <span className="font-semibold text-slate-700">Query Output</span>
                  <span className="text-[11px] text-emerald-600 font-medium font-mono">10 rows • 12ms</span>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs font-mono">
                    <thead className="bg-slate-50/60 text-slate-500 border-b border-slate-100 text-[11px] font-sans">
                      <tr>
                        <th className="py-2 px-3 font-semibold">Patient ID</th>
                        <th className="py-2 px-3 font-semibold">Age</th>
                        <th className="py-2 px-3 font-semibold">Cholesterol</th>
                        <th className="py-2 px-3 font-semibold">Risk Tier</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100 text-slate-700">
                      <tr>
                        <td className="py-2 px-3 text-indigo-600 font-medium">P-10842</td>
                        <td className="py-2 px-3 font-sans">62</td>
                        <td className="py-2 px-3 font-semibold text-slate-900">312 mg/dL</td>
                        <td className="py-2 px-3">
                          <span className="px-1.5 py-0.5 rounded text-[10px] font-sans bg-red-50 text-red-700 border border-red-200">High</span>
                        </td>
                      </tr>
                      <tr>
                        <td className="py-2 px-3 text-indigo-600 font-medium">P-10491</td>
                        <td className="py-2 px-3 font-sans">58</td>
                        <td className="py-2 px-3 font-semibold text-slate-900">298 mg/dL</td>
                        <td className="py-2 px-3">
                          <span className="px-1.5 py-0.5 rounded text-[10px] font-sans bg-red-50 text-red-700 border border-red-200">High</span>
                        </td>
                      </tr>
                      <tr>
                        <td className="py-2 px-3 text-indigo-600 font-medium">P-11204</td>
                        <td className="py-2 px-3 font-sans">71</td>
                        <td className="py-2 px-3 font-semibold text-slate-900">284 mg/dL</td>
                        <td className="py-2 px-3">
                          <span className="px-1.5 py-0.5 rounded text-[10px] font-sans bg-amber-50 text-amber-700 border border-amber-200">Moderate</span>
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Credit Math Card (Required in Item 8) */}
      <div className="bg-white border border-slate-200 rounded-xl p-6 shadow-sm">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="space-y-1">
            <span className="text-xs font-semibold uppercase tracking-wider text-indigo-600">
              Credit Reward Formula
            </span>
            <h2 className="text-lg font-bold text-slate-900">
              Clear, automated rewards for every verified upload
            </h2>
            <p className="text-xs text-slate-500">
              Reward formula: 50 base credits + floor(quality × 0.30) + floor(relevance / 6).
            </p>
          </div>

          <div className="bg-emerald-50 border border-emerald-200 rounded-xl p-4 text-center sm:text-right shrink-0">
            <span className="text-xs font-semibold text-emerald-800 uppercase tracking-wide block mb-0.5">
              Standard 85 Quality / 90 Relevance Upload
            </span>
            <div className="text-xl sm:text-2xl font-black font-mono text-emerald-700">
              Base +50, Quality bonus +25, Relevance bonus +15 = 90 credits
            </div>
          </div>
        </div>
      </div>

      {/* 4 Numbered Step Cards (Required in Item 8) */}
      <div className="space-y-3">
        <h2 className="text-xs font-bold uppercase tracking-wider text-slate-400">
          How DataPulse Works
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
          {/* Step 1 */}
          <div className="bg-white border border-slate-200 rounded-xl p-6 shadow-sm space-y-3">
            <div className="w-10 h-10 rounded-lg bg-indigo-50 border border-indigo-200 flex items-center justify-center text-indigo-600 font-extrabold text-base">
              1
            </div>
            <h3 className="text-base font-bold text-slate-900">Upload dataset</h3>
            <p className="text-xs text-slate-600 leading-relaxed">
              Drop your CSV or XLSX file, specify clean metadata, category, and column descriptions in minutes.
            </p>
          </div>

          {/* Step 2 */}
          <div className="bg-white border border-slate-200 rounded-xl p-6 shadow-sm space-y-3">
            <div className="w-10 h-10 rounded-lg bg-indigo-50 border border-indigo-200 flex items-center justify-center text-indigo-600 font-extrabold text-base">
              2
            </div>
            <h3 className="text-base font-bold text-slate-900">Get evaluated and earn credits</h3>
            <p className="text-xs text-slate-600 leading-relaxed">
              Automated pipelines score schema quality and domain relevance, immediately awarding up to 90+ credits on publish.
            </p>
          </div>

          {/* Step 3 */}
          <div className="bg-white border border-slate-200 rounded-xl p-6 shadow-sm space-y-3">
            <div className="w-10 h-10 rounded-lg bg-indigo-50 border border-indigo-200 flex items-center justify-center text-indigo-600 font-extrabold text-base">
              3
            </div>
            <h3 className="text-base font-bold text-slate-900">Others unlock and query it</h3>
            <p className="text-xs text-slate-600 leading-relaxed">
              Analysts unlock your catalog for 20 credits once on first query. You earn 20 credits every time someone unlocks your dataset.
            </p>
          </div>

          {/* Step 4 */}
          <div className="bg-white border border-slate-200 rounded-xl p-6 shadow-sm space-y-3">
            <div className="w-10 h-10 rounded-lg bg-indigo-50 border border-indigo-200 flex items-center justify-center text-indigo-600 font-extrabold text-base">
              4
            </div>
            <h3 className="text-base font-bold text-slate-900">Improve it and earn more</h3>
            <p className="text-xs text-slate-600 leading-relaxed">
              Clean missing rows or add column synonyms. If your score improves by at least 5 points, earn floor(delta × 0.75) bonus credits.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};
