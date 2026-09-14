import React, { useState } from 'react';
import {
  Lock, Eye, EyeOff, ArrowRight, ShieldCheck, Sun, Moon, AlertCircle, RefreshCw, KeyRound, Sparkles
} from 'lucide-react';
import nimCubeLogo from '../../icons/nim-cube.svg';

export function LoginPage({ onLoginSuccess, theme, onToggleTheme }) {
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [shake, setShake] = useState(false);

  const handleSubmit = async (e) => {
    if (e) e.preventDefault();
    if (!password.trim()) {
      setError('Please enter your access password');
      triggerShake();
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const res = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password: password.trim() })
      });

      const data = await res.json();

      if (res.ok && data.success) {
        if (data.token) {
          localStorage.setItem('nim_auth_token', data.token);
        }
        if (onLoginSuccess) {
          onLoginSuccess(data.token);
        }
      } else {
        setError(data.detail || 'Incorrect access password');
        triggerShake();
      }
    } catch (err) {
      console.error('Login error:', err);
      setError('Failed to connect to gateway server');
      triggerShake();
    } finally {
      setLoading(false);
    }
  };

  const triggerShake = () => {
    setShake(true);
    setTimeout(() => setShake(false), 500);
  };

  const handleUseDefaultPassword = () => {
    setPassword('nimrouter');
    setError(null);
  };

  return (
    <div className="relative min-h-screen w-full flex flex-col justify-between items-center p-4 sm:p-8 bg-[#eef2f7] dark:bg-[#0f1117] text-slate-800 dark:text-slate-100 transition-colors duration-300 overflow-hidden select-none">

      {/* Ambient background glow accents */}
      <div className="absolute -top-32 -left-32 w-96 h-96 rounded-full bg-[#da7756]/10 dark:bg-[#da7756]/15 blur-3xl pointer-events-none" />
      <div className="absolute -bottom-32 -right-32 w-96 h-96 rounded-full bg-[#00d2ff]/10 dark:bg-[#00d2ff]/15 blur-3xl pointer-events-none" />

      {/* Top Bar with Gateway Status & Theme Toggle */}
      <header className="w-full max-w-5xl mx-auto flex items-center justify-between z-10">
        <div className="flex items-center gap-2 px-3 py-1.5 rounded-2xl bg-white/70 dark:bg-white/5 backdrop-blur-md border border-black/5 dark:border-white/5 text-[11px] font-mono shadow-sm">
          <span className="relative flex h-2 w-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
            <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
          </span>
          <span className="text-slate-600 dark:text-slate-400 font-semibold">Gateway Online</span>
          <span className="text-slate-300 dark:text-white/20">|</span>
          <span className="text-[#da7756] font-semibold">Port 11435</span>
        </div>

        <button
          type="button"
          onClick={onToggleTheme}
          className="p-2 rounded-2xl bg-white/80 dark:bg-white/5 backdrop-blur-md text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-white/10 transition neu-button border border-black/5 dark:border-white/5 shadow-sm"
          title="Toggle Light / Dark Theme"
        >
          {theme === 'dark' ? (
            <Sun className="w-4 h-4 text-amber-400" />
          ) : (
            <Moon className="w-4 h-4 text-indigo-600" />
          )}
        </button>
      </header>

      {/* Main Login Card */}
      <div className="w-full max-w-md my-auto z-10">
        <div
          className={`w-full p-6 sm:p-8 rounded-3xl sm:rounded-4xl bg-white dark:bg-[#171b24] border border-black/5 dark:border-white/10 shadow-neu-light dark:shadow-neu-dark transition-all duration-300 ${shake ? 'animate-bounce border-rose-500/50' : ''
            }`}
        >
          {/* Brand Identity */}
          <div className="flex flex-col items-center text-center mb-6">
            <div className="relative mb-3.5">
              <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-[#da7756]/25 to-[#da7756]/10 border border-[#da7756]/40 shadow-[0_0_24px_rgba(218,119,86,0.35)] flex items-center justify-center p-2.5">
                <img
                  src={nimCubeLogo}
                  alt="NIM Router"
                  className="w-10 h-10 object-contain drop-shadow-md"
                />
              </div>
              <div className="absolute -bottom-1 -right-1 p-1 rounded-lg bg-emerald-500 text-white shadow-sm">
                <ShieldCheck className="w-3 h-3" />
              </div>
            </div>

            <h1 className="text-xl sm:text-2xl font-black tracking-tight text-slate-900 dark:text-white">
              NIM ROUTER
            </h1>
            <p className="text-xs text-slate-500 dark:text-slate-400 mt-1 font-medium">
              Universal Multi-Provider Gateway
            </p>

            <div className="mt-2.5 inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-slate-100 dark:bg-white/5 border border-black/5 dark:border-white/10 text-[10px] font-mono text-slate-600 dark:text-slate-300">
              <KeyRound className="w-3 h-3 text-[#00d2ff]" />
              <span>Dashboard Access Protection</span>
            </div>
          </div>

          {/* Error Banner */}
          {error && (
            <div className="mb-5 p-3 rounded-2xl bg-rose-500/10 border border-rose-500/20 text-rose-600 dark:text-rose-400 text-xs flex items-center gap-2 animate-fadeIn">
              <AlertCircle className="w-4 h-4 shrink-0 text-rose-500" />
              <span className="font-medium">{error}</span>
            </div>
          )}

          {/* Login Form */}
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-1.5">
              <div className="flex items-center justify-between px-1">
                <label
                  htmlFor="dashboard-password"
                  className="text-[10px] uppercase font-bold tracking-wider text-slate-500 dark:text-slate-400"
                >
                  Gateway Password
                </label>

              </div>

              <div className="relative group">
                <div className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400 group-focus-within:text-[#00d2ff] transition-colors">
                  <Lock className="w-4 h-4" />
                </div>

                <input
                  id="dashboard-password"
                  type={showPassword ? 'text' : 'password'}
                  placeholder="Enter dashboard password..."
                  value={password}
                  onChange={(e) => {
                    setPassword(e.target.value);
                    if (error) setError(null);
                  }}
                  autoFocus
                  disabled={loading}
                  className="w-full pl-10 pr-11 py-2.5 sm:py-3 text-xs sm:text-sm font-mono rounded-2xl bg-slate-50 dark:bg-[#0f1117] border border-black/10 dark:border-white/10 text-slate-900 dark:text-white placeholder-slate-400 focus:outline-none focus:border-[#00d2ff] focus:ring-2 focus:ring-[#00d2ff]/20 transition-all shadow-inner"
                />

                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 p-1 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 transition"
                  title={showPassword ? 'Hide password' : 'Show password'}
                >
                  {showPassword ? (
                    <EyeOff className="w-4 h-4" />
                  ) : (
                    <Eye className="w-4 h-4" />
                  )}
                </button>
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full py-2.5 sm:py-3 px-4 rounded-2xl bg-gradient-to-r from-[#da7756] to-[#ff8c42] hover:from-[#e08362] hover:to-[#ffa05c] text-white font-bold text-xs sm:text-sm transition-all neu-button shadow-md flex items-center justify-center gap-2 group disabled:opacity-50"
            >
              {loading ? (
                <>
                  <RefreshCw className="w-4 h-4 animate-spin text-white" />
                  <span>Verifying Credentials...</span>
                </>
              ) : (
                <>
                  <span>Unlock Dashboard</span>
                  <ArrowRight className="w-4 h-4 group-hover:translate-x-1 transition-transform" />
                </>
              )}
            </button>
          </form>

          {/* Default Password Quick-Fill Pill */}
          <div className="mt-5 pt-4 border-t border-black/5 dark:border-white/5 flex flex-col items-center gap-2 text-center">
            <button
              type="button"
              onClick={handleUseDefaultPassword}
              className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-xl bg-slate-100 hover:bg-slate-200 dark:bg-white/5 dark:hover:bg-white/10 text-[10px] font-mono text-slate-600 dark:text-slate-300 transition-colors border border-black/5 dark:border-white/5"
              title="Click to autofill default password"
            >
              <KeyRound className="w-3 h-3 text-amber-400" />
              <span>Default password:</span>
              <code className="text-[#da7756] dark:text-[#ff8c42] font-bold">nimrouter</code>
            </button>
            <p className="text-[10px] text-slate-400 dark:text-slate-500">
              You can update or change this password anytime in <span className="font-semibold text-slate-600 dark:text-slate-400">Config</span>.
            </p>
          </div>
        </div>
      </div>

      {/* Footer */}
      <footer className="w-full max-w-5xl mx-auto flex items-center justify-between text-[10px] text-slate-400 dark:text-slate-500 py-2 z-10">
        <div className="flex items-center gap-1.5 font-mono">
          <span>NIM Router v2.4</span>
          <span>•</span>
          <span className="text-emerald-500">OpenAI & Ollama Compatible</span>
        </div>
        <div className="flex items-center gap-1">
          <span>Icons by</span>
          <a
            href="https://svgl.app/"
            target="_blank"
            rel="noreferrer"
            className="text-slate-400 hover:text-[#00d2ff] transition underline decoration-slate-500/40"
          >
            svgl.app
          </a>
        </div>
      </footer>
    </div>
  );
}
