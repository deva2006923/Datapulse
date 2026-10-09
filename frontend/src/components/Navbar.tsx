import React, { useState, useRef, useEffect } from 'react';
import {
  Activity,
  Layers,
  Database,
  Search,
  Upload,
  Wallet,
  Coins,
  History,
  User,
  ChevronDown,
  LogOut,
  FolderKanban,
  Sparkles,
} from 'lucide-react';
import { PageRoute, UserAccount } from '../types';

interface NavbarProps {
  currentRoute: PageRoute;
  onNavigate: (route: PageRoute) => void;
  currentUser: UserAccount;
  allUsers: Record<string, UserAccount>;
  onSwitchUser: (userId: string) => void;
  isAuthenticated?: boolean;
  onLogout?: () => void;
}

export const Navbar: React.FC<NavbarProps> = ({
  currentRoute,
  onNavigate,
  currentUser,
  allUsers,
  onSwitchUser,
  isAuthenticated = false,
  onLogout,
}) => {
  const [showUserDropdown, setShowUserDropdown] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleOutside = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setShowUserDropdown(false);
      }
    };
    document.addEventListener('mousedown', handleOutside);
    return () => document.removeEventListener('mousedown', handleOutside);
  }, []);

  const navItems: { route: PageRoute; label: string; icon: React.ReactNode }[] = [
    { route: 'dashboard', label: 'Dashboard', icon: <Layers className="w-4 h-4" /> },
    { route: 'marketplace', label: 'Marketplace', icon: <Database className="w-4 h-4" /> },
    { route: 'upload', label: 'Upload', icon: <Upload className="w-4 h-4" /> },
    { route: 'query', label: 'Query', icon: <Search className="w-4 h-4" /> },
    { route: 'my-datasets', label: 'My Datasets', icon: <FolderKanban className="w-4 h-4" /> },
    { route: 'query-history', label: 'History', icon: <History className="w-4 h-4" /> },
    { route: 'wallet', label: 'Wallet', icon: <Wallet className="w-4 h-4" /> },
  ];

  return (
    <header className="sticky top-0 z-40 w-full border-b border-slate-200 bg-white shadow-xs">
      <div className="max-w-[1600px] mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between gap-4">
        {/* Left: Brand Logo & Main Nav Links */}
        <div className="flex items-center gap-6 lg:gap-8">
          {/* Logo is just the text "DataPulse" with a small simple heartbeat-line icon */}
          <button
            onClick={() => onNavigate('landing')}
            className="flex items-center gap-2 group text-left cursor-pointer"
          >
            <Activity className="w-5 h-5 text-indigo-600" />
            <span className="font-extrabold text-lg tracking-tight text-slate-900 group-hover:text-indigo-600 transition-colors">
              DataPulse
            </span>
          </button>

          {/* Desktop Navigation Links */}
          <nav className="hidden md:flex items-center space-x-1 text-xs font-semibold">
            {navItems.map((item) => {
              const isActive = currentRoute === item.route;
              return (
                <button
                  key={item.route}
                  onClick={() => onNavigate(item.route)}
                  className={`px-3 py-2 rounded-lg transition-colors cursor-pointer flex items-center gap-1.5 ${
                    isActive
                      ? 'bg-indigo-50 text-indigo-700 font-bold'
                      : 'text-slate-600 hover:text-slate-900 hover:bg-slate-50'
                  }`}
                >
                  {item.icon}
                  <span>{item.label}</span>
                </button>
              );
            })}
          </nav>
        </div>

        {/* Right: Credit Balance Pill & Active User Switcher */}
        <div className="flex items-center gap-3">
          {/* Real-time Compute Balance Pill */}
          <button
            onClick={() => onNavigate('wallet')}
            className="flex items-center gap-2 px-3 py-1.5 rounded-xl bg-emerald-50 hover:bg-emerald-100/80 border border-emerald-200 text-emerald-800 transition-colors shadow-xs cursor-pointer group"
            title="Click to view Wallet & Redemptions"
          >
            <Coins className="w-4 h-4 text-emerald-600 shrink-0" />
            <div className="flex items-baseline gap-1">
              <span className="text-xs font-black font-mono text-emerald-700">
                {currentUser.credits.toLocaleString()}
              </span>
              <span className="text-[10px] font-semibold text-emerald-600 uppercase">
                cr
              </span>
            </div>
          </button>

          {/* User Account Switcher Dropdown */}
          <div className="relative" ref={dropdownRef}>
            <button
              onClick={() => setShowUserDropdown(!showUserDropdown)}
              className="flex items-center gap-2 px-3 py-1.5 rounded-xl bg-slate-50 hover:bg-slate-100 border border-slate-200 text-slate-800 transition-colors cursor-pointer text-xs"
            >
              <div className="w-5 h-5 rounded-full bg-indigo-600 text-white font-bold text-[10px] flex items-center justify-center">
                {currentUser.name.charAt(0)}
              </div>
              <span className="font-semibold hidden sm:inline max-w-[110px] truncate">
                {currentUser.name}
              </span>
              <ChevronDown className="w-3.5 h-3.5 text-slate-400" />
            </button>

            {showUserDropdown && (
              <div className="absolute right-0 mt-2 w-64 rounded-xl bg-white border border-slate-200 shadow-lg p-2 z-50 text-xs animate-in fade-in slide-in-from-top-2 duration-150">
                <div className="p-2 border-b border-slate-100 mb-1">
                  <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block">
                    Signed in as
                  </span>
                  <div className="font-bold text-slate-900 truncate">{currentUser.name}</div>
                  <div className="text-[11px] font-mono text-slate-500 truncate">{currentUser.email}</div>
                  <div className="text-[10px] font-semibold text-indigo-600 mt-1">
                    {currentUser.role} • {currentUser.credits} credits
                  </div>
                </div>

                <div className="py-1">
                  <span className="px-2 text-[10px] font-semibold text-slate-400 uppercase tracking-wider block mb-1">
                    Quick Switch Account
                  </span>
                  {Object.values(allUsers).map((u) => (
                    <button
                      key={u.id}
                      onClick={() => {
                        onSwitchUser(u.id);
                        setShowUserDropdown(false);
                      }}
                      className={`w-full text-left px-2 py-1.5 rounded-lg flex items-center justify-between transition-colors cursor-pointer ${
                        u.id === currentUser.id
                          ? 'bg-indigo-50 font-bold text-indigo-700'
                          : 'text-slate-700 hover:bg-slate-50'
                      }`}
                    >
                      <span className="truncate">{u.name}</span>
                      <span className="font-mono text-[11px] text-emerald-600 shrink-0 font-semibold">
                        {u.credits} cr
                      </span>
                    </button>
                  ))}
                </div>

                <div className="pt-1 mt-1 border-t border-slate-100 space-y-0.5">
                  <button
                    onClick={() => {
                      onNavigate('profile');
                      setShowUserDropdown(false);
                    }}
                    className="w-full text-left px-2 py-1.5 rounded-lg text-slate-700 hover:bg-slate-50 transition-colors cursor-pointer flex items-center gap-2"
                  >
                    <User className="w-3.5 h-3.5 text-slate-400" />
                    <span>View Profile</span>
                  </button>
                  {isAuthenticated ? (
                    <button
                      onClick={() => {
                        setShowUserDropdown(false);
                        if (onLogout) onLogout();
                        else onNavigate('login');
                      }}
                      className="w-full text-left px-2 py-1.5 rounded-lg text-rose-600 hover:bg-rose-50 transition-colors cursor-pointer flex items-center gap-2 font-medium"
                    >
                      <LogOut className="w-3.5 h-3.5 text-rose-500" />
                      <span>Sign Out</span>
                    </button>
                  ) : (
                    <button
                      onClick={() => {
                        setShowUserDropdown(false);
                        onNavigate('login');
                      }}
                      className="w-full text-left px-2 py-1.5 rounded-lg text-indigo-600 hover:bg-indigo-50 transition-colors cursor-pointer flex items-center gap-2 font-medium"
                    >
                      <LogOut className="w-3.5 h-3.5 text-indigo-500" />
                      <span>Sign In / Register</span>
                    </button>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Mobile Sub-Nav */}
      <div className="md:hidden border-t border-slate-100 bg-white px-4 py-2 overflow-x-auto flex items-center space-x-1 text-xs">
        {navItems.map((item) => {
          const isActive = currentRoute === item.route;
          return (
            <button
              key={item.route}
              onClick={() => onNavigate(item.route)}
              className={`px-2.5 py-1 rounded-md whitespace-nowrap transition-colors cursor-pointer flex items-center gap-1 ${
                isActive
                  ? 'bg-indigo-50 text-indigo-700 font-bold'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              {item.icon}
              <span>{item.label}</span>
            </button>
          );
        })}
      </div>
    </header>
  );
};
