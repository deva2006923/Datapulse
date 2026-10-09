import React from 'react';
import {
  AlertCircle,
  AlertTriangle,
  CheckCircle2,
  Lock,
  Info,
  X,
  PlusCircle,
} from 'lucide-react';
import { ToastMessage } from '../types';

interface ToastContainerProps {
  toasts: ToastMessage[];
  onDismiss: (id: string) => void;
}

export const ToastContainer: React.FC<ToastContainerProps> = ({ toasts, onDismiss }) => {
  return (
    <div className="fixed top-20 right-6 z-50 flex flex-col gap-2.5 max-w-sm pointer-events-none w-full">
      {toasts.map((toast) => {
        const borderStyle =
          toast.tone === 'rose'
            ? 'border-red-200 bg-red-50/90 text-red-900'
            : toast.tone === 'amber'
            ? 'border-amber-200 bg-amber-50/90 text-amber-900'
            : toast.tone === 'emerald'
            ? 'border-emerald-200 bg-emerald-50/90 text-emerald-900'
            : 'border-slate-200 bg-white text-slate-900';

        const iconColor =
          toast.tone === 'rose'
            ? 'text-red-600'
            : toast.tone === 'amber'
            ? 'text-amber-600'
            : toast.tone === 'emerald'
            ? 'text-emerald-600'
            : 'text-indigo-600';

        return (
          <div
            key={toast.id}
            className={`pointer-events-auto p-4 rounded-xl border shadow-md flex items-start gap-3 w-full transition-all ${borderStyle}`}
          >
            <div className="shrink-0 mt-0.5">
              {toast.tone === 'rose' ? (
                <AlertCircle className={`w-4 h-4 ${iconColor}`} />
              ) : toast.tone === 'amber' ? (
                <AlertTriangle className={`w-4 h-4 ${iconColor}`} />
              ) : toast.tone === 'emerald' ? (
                <CheckCircle2 className={`w-4 h-4 ${iconColor}`} />
              ) : toast.tone === 'violet' ? (
                <Lock className={`w-4 h-4 ${iconColor}`} />
              ) : (
                <Info className={`w-4 h-4 ${iconColor}`} />
              )}
            </div>

            <div className="flex-1 min-w-0">
              <div className="font-semibold text-xs tracking-wide font-mono">
                {toast.title}
              </div>
              <div className="text-xs text-slate-600 mt-0.5 leading-relaxed break-words">
                {toast.message}
              </div>

              {toast.action && (
                <button
                  onClick={() => {
                    toast.action?.onClick();
                    onDismiss(toast.id);
                  }}
                  className="mt-2 px-2.5 py-1 rounded bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-medium flex items-center gap-1.5 transition-colors cursor-pointer"
                >
                  <PlusCircle className="w-3 h-3" />
                  {toast.action.label}
                </button>
              )}
            </div>

            <button
              onClick={() => onDismiss(toast.id)}
              className="text-slate-400 hover:text-slate-600 text-xs shrink-0 cursor-pointer"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        );
      })}
    </div>
  );
};
