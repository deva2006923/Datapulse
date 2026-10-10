import React, { useState } from 'react';
import {
  User,
  Mail,
  Lock,
  ArrowRight,
  ShieldCheck,
  CheckCircle2,
  AlertCircle,
  Loader2,
} from 'lucide-react';
import { PageRoute, BackendUserResponse } from '../types';
import { api, ApiError, DEMO_ACCOUNTS } from '../services/api';

interface LoginRegisterViewProps {
  onLoginSuccess: (
    user: BackendUserResponse,
    token: string,
    role?: 'Contributor' | 'Data Analyst'
  ) => void;
  onNavigate: (route: PageRoute) => void;
}

export const LoginRegisterView: React.FC<LoginRegisterViewProps> = ({
  onLoginSuccess,
  onNavigate,
}) => {
  const [isRegister, setIsRegister] = useState(false);
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [role, setRole] = useState<'Contributor' | 'Data Analyst'>('Contributor');
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const handleDemoClick = async (demoKey: string) => {
    setIsLoading(true);
    setErrorMessage(null);
    try {
      const res = await api.auth.demoLogin(demoKey);
      onLoginSuccess(res.user, res.access_token);
      onNavigate('dashboard');
    } catch (err: any) {
      if (err instanceof ApiError) {
        setErrorMessage(err.message);
      } else {
        setErrorMessage('Failed to sign in with demo account. Please check backend connection.');
      }
    } finally {
      setIsLoading(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMessage(null);

    if (isRegister) {
      if (!name.trim()) {
        setErrorMessage('Please enter your full name.');
        return;
      }
      if (!email.trim() || !email.includes('@')) {
        setErrorMessage('Please enter a valid email address.');
        return;
      }
      if (password.length < 6) {
        setErrorMessage('Password must be at least 6 characters.');
        return;
      }

      setIsLoading(true);
      try {
        const res = await api.auth.register({
          email: email.trim(),
          password,
          full_name: name.trim(),
        });
        onLoginSuccess(res.user, res.access_token, role);
        onNavigate('dashboard');
      } catch (err: any) {
        if (err instanceof ApiError) {
          setErrorMessage(err.message);
        } else {
          setErrorMessage('Registration failed. Please check your network and try again.');
        }
      } finally {
        setIsLoading(false);
      }
    } else {
      if (!email.trim()) {
        setErrorMessage('Please enter your email address.');
        return;
      }
      if (!password) {
        setErrorMessage('Please enter your password.');
        return;
      }

      setIsLoading(true);
      try {
        const res = await api.auth.login({
          email: email.trim(),
          password,
        });
        onLoginSuccess(res.user, res.access_token);
        onNavigate('dashboard');
      } catch (err: any) {
        if (err instanceof ApiError) {
          setErrorMessage(err.message);
        } else {
          setErrorMessage('Login failed. Please check your network and try again.');
        }
      } finally {
        setIsLoading(false);
      }
    }
  };

  return (
    <div className="max-w-md mx-auto my-8 space-y-6">
      {/* Quick Demo Switcher Buttons (Required in checklist) */}
      <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm space-y-3">
        <span className="text-xs font-semibold uppercase tracking-wider text-slate-500 block">
          Instant Demo Access
        </span>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
          {Object.values(DEMO_ACCOUNTS).map((demo) => (
            <button
              key={demo.key}
              type="button"
              disabled={isLoading}
              onClick={() => handleDemoClick(demo.key)}
              className="px-3 py-2 rounded-lg bg-indigo-50/70 hover:bg-indigo-100 disabled:opacity-50 text-indigo-700 text-xs font-semibold border border-indigo-200 transition-colors cursor-pointer text-center"
            >
              {demo.full_name}
              <span className="block text-[10px] font-normal text-indigo-600 font-mono">
                {demo.role}
              </span>
            </button>
          ))}
        </div>
      </div>

      {/* Main Form Card */}
      <div className="bg-white border border-slate-200 rounded-xl p-6 sm:p-8 shadow-sm space-y-6">
        <div className="flex items-center justify-between border-b border-slate-100 pb-4">
          <div>
            <h2 className="text-xl font-bold text-slate-900">
              {isRegister ? 'Create an Account' : 'Welcome Back'}
            </h2>
            <p className="text-xs text-slate-500 mt-0.5">
              {isRegister
                ? 'New accounts receive 100 bonus credits automatically.'
                : 'Sign in to access your datasets and query console.'}
            </p>
          </div>
        </div>

        {errorMessage && (
          <div className="p-3 bg-rose-50 rounded-lg border border-rose-200 text-xs text-rose-800 flex items-start gap-2">
            <AlertCircle className="w-4 h-4 text-rose-600 shrink-0 mt-0.5" />
            <span className="flex-1">{errorMessage}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          {isRegister && (
            <div>
              <label className="block text-xs font-medium text-slate-700 mb-1">Full Name</label>
              <div className="relative">
                <User className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" />
                <input
                  type="text"
                  required
                  disabled={isLoading}
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="e.g. Maya Patel"
                  className="w-full bg-slate-50 border border-slate-200 rounded-lg pl-9 pr-3 py-2 text-xs text-slate-900 focus:outline-none focus:border-indigo-500 disabled:opacity-60"
                />
              </div>
            </div>
          )}

          <div>
            <label className="block text-xs font-medium text-slate-700 mb-1">Email Address</label>
            <div className="relative">
              <Mail className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" />
              <input
                type="email"
                required
                disabled={isLoading}
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="name@organization.com"
                className="w-full bg-slate-50 border border-slate-200 rounded-lg pl-9 pr-3 py-2 text-xs text-slate-900 focus:outline-none focus:border-indigo-500 disabled:opacity-60"
              />
            </div>
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-700 mb-1">Password</label>
            <div className="relative">
              <Lock className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" />
              <input
                type="password"
                required
                disabled={isLoading}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                className="w-full bg-slate-50 border border-slate-200 rounded-lg pl-9 pr-3 py-2 text-xs text-slate-900 focus:outline-none focus:border-indigo-500 disabled:opacity-60"
              />
            </div>
          </div>

          {isRegister && (
            <div>
              <label className="block text-xs font-medium text-slate-700 mb-1">Primary Role</label>
              <select
                value={role}
                disabled={isLoading}
                onChange={(e) => setRole(e.target.value as any)}
                className="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-xs text-slate-900 focus:outline-none focus:border-indigo-500 disabled:opacity-60"
              >
                <option value="Contributor">Dataset Contributor (Upload & Earn)</option>
                <option value="Data Analyst">Data Analyst (Query & Download)</option>
              </select>
            </div>
          )}

          {isRegister && (
            <div className="p-3 bg-emerald-50 rounded-lg border border-emerald-200 text-xs text-emerald-800 flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
              <span><strong>+100 Credits</strong> will be added to your balance upon sign-up.</span>
            </div>
          )}

          <button
            type="submit"
            disabled={isLoading}
            className="w-full py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-700 disabled:opacity-60 text-white font-medium text-xs transition-colors shadow-sm cursor-pointer flex items-center justify-center gap-2 mt-2"
          >
            {isLoading ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                <span>{isRegister ? 'Registering Account...' : 'Signing In...'}</span>
              </>
            ) : (
              <>
                <span>{isRegister ? 'Register & Claim 100 Credits' : 'Sign In'}</span>
                <ArrowRight className="w-4 h-4" />
              </>
            )}
          </button>
        </form>

        <div className="pt-2 text-center text-xs text-slate-500 border-t border-slate-100">
          {isRegister ? (
            <span>
              Already have an account?{' '}
              <button
                type="button"
                onClick={() => {
                  setIsRegister(false);
                  setErrorMessage(null);
                }}
                className="text-indigo-600 font-semibold hover:underline cursor-pointer"
              >
                Sign In
              </button>
            </span>
          ) : (
            <span>
              Don't have an account?{' '}
              <button
                type="button"
                onClick={() => {
                  setIsRegister(true);
                  setErrorMessage(null);
                }}
                className="text-indigo-600 font-semibold hover:underline cursor-pointer"
              >
                Create Account (+100 cr)
              </button>
            </span>
          )}
        </div>
      </div>
    </div>
  );
};
