import React from 'react';
import { Database, ArrowLeft, Home } from 'lucide-react';
import { PageRoute } from '../types';

interface NotFoundViewProps {
  onNavigate: (route: PageRoute) => void;
}

export const NotFoundView: React.FC<NotFoundViewProps> = ({ onNavigate }) => {
  return (
    <div className="max-w-md mx-auto my-16 text-center">
      <div className="bg-white border border-slate-200 rounded-xl p-8 shadow-sm space-y-4">
        <div className="w-16 h-16 rounded-2xl bg-indigo-50 border border-indigo-200 text-indigo-600 font-mono font-black text-2xl flex items-center justify-center mx-auto">
          404
        </div>
        <h1 className="text-xl font-bold text-slate-900">
          Page Not Found
        </h1>
        <p className="text-xs text-slate-500 leading-relaxed">
          The requested route does not exist or has been moved. You can return to your dashboard or explore the catalog.
        </p>
        <div className="pt-2 flex flex-col sm:flex-row items-center justify-center gap-2">
          <button
            onClick={() => onNavigate('dashboard')}
            className="w-full sm:w-auto px-4 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold shadow-xs transition-colors cursor-pointer flex items-center justify-center gap-1.5"
          >
            <Home className="w-4 h-4" />
            <span>Go to Dashboard</span>
          </button>
          <button
            onClick={() => onNavigate('marketplace')}
            className="w-full sm:w-auto px-4 py-2.5 rounded-xl bg-slate-50 hover:bg-slate-100 border border-slate-300 text-slate-700 text-xs font-semibold shadow-xs transition-colors cursor-pointer flex items-center justify-center gap-1.5"
          >
            <Database className="w-4 h-4" />
            <span>Browse Datasets</span>
          </button>
        </div>
      </div>
    </div>
  );
};
