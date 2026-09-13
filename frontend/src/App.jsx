import React, { useState, useEffect } from 'react';
import {
  Zap, Sun, Moon, RefreshCw, Key, Server, Sliders, Terminal, Shield, Activity, RotateCcw, CheckCircle2, AlertCircle, GitMerge
} from 'lucide-react';
import { BentoGrid } from './components/BentoGrid';
import {
  ModelSelectorModal,
  KeysManagerModal,
  SettingsModal,
  FullLogsModal,
  ComboEditorModal
} from './components/Modals';

export default function App() {
  const [theme, setTheme] = useState(() => {
    return localStorage.getItem('nim_theme') || 'dark';
  });
  const [stats, setStats] = useState(null);
  const [logs, setLogs] = useState([]);
  const [probing, setProbing] = useState(false);
  const [restarting, setRestarting] = useState(false);
  const [toastMessage, setToastMessage] = useState(null);

  const [activeModal, setActiveModal] = useState(null);
  const [editingCombo, setEditingCombo] = useState(null);

  useEffect(() => {
    localStorage.setItem('nim_theme', theme);
    if (theme === 'dark') {
      document.documentElement.classList.add('dark');
      document.body.classList.add('dark');
      document.body.style.backgroundColor = '#0f1117';
    } else {
      document.documentElement.classList.remove('dark');
      document.body.classList.remove('dark');
      document.body.style.backgroundColor = '#eef2f7';
    }
  }, [theme]);

  const showToast = (msg, type = 'success') => {
    setToastMessage({ text: msg, type });
    setTimeout(() => setToastMessage(null), 3500);
  };

  const fetchStats = async () => {
    try {
      const res = await fetch('/api/dashboard/stats');
      if (res.ok) {
        const data = await res.json();
        setStats(data);
      }
    } catch (e) {
      console.error('Failed to fetch dashboard stats:', e);
    }
  };

  useEffect(() => {
    fetchStats();
    const interval = setInterval(fetchStats, 3500);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    let eventSource;
    try {
      eventSource = new EventSource('/api/logs/stream');
      eventSource.onmessage = (event) => {
        try {
          const entry = JSON.parse(event.data);
          setLogs((prev) => [...prev.slice(-250), entry]);
        } catch (e) {
        }
      };
      eventSource.onerror = () => {
        eventSource.close();
      };
    } catch (e) {
      console.error('SSE initialization error:', e);
    }
    return () => {
      if (eventSource) eventSource.close();
    };
  }, []);

  const handleRunProbe = async () => {
    setProbing(true);
    showToast('Starting multi-provider endpoint probing benchmark...', 'info');
    try {
      const res = await fetch('/api/probe', { method: 'POST' });
      if (res.ok) {
        const data = await res.json();
        const statsRes = await fetch('/api/dashboard/stats');
        let unavailCombos = [];
        let highLatCombos = [];
        if (statsRes.ok) {
          const freshStats = await statsRes.json();
          setStats(freshStats);
          unavailCombos = (freshStats.combos || []).filter(c => c.has_unavailable);
          highLatCombos = (freshStats.combos || []).filter(c => c.has_high_latency && !c.has_unavailable);
        }
        if (unavailCombos.length > 0) {
          const names = unavailCombos.map(c => `'${c.name}'`).join(', ');
          showToast(`Probing complete. ⚠️ Unavailable model(s) in combo ${names}!`, 'error');
        } else if (highLatCombos.length > 0) {
          const names = highLatCombos.map(c => `'${c.name}'`).join(', ');
          showToast(`Probing complete. ⚡ High latency model(s) detected in ${names}.`, 'info');
        } else {
          showToast(`Probing complete! ${data.total_discovered || 0} active models verified.`, 'success');
        }
      } else {
        showToast('Probing failed. Check provider credentials.', 'error');
      }
    } catch (e) {
      showToast('Error during probing scan.', 'error');
    } finally {
      setProbing(false);
    }
  };

  const handleRestartGateway = async () => {
    setRestarting(true);
    showToast('Restarting nim-router gateway process...', 'info');
    try {
      const res = await fetch('/api/server/restart', { method: 'POST' });
      if (res.ok) {
        showToast('Gateway restarted and active pool refreshed!', 'success');
        setTimeout(fetchStats, 1500);
      } else {
        showToast('Restart command failed.', 'error');
      }
    } catch (e) {
      showToast('Gateway restart signal sent.', 'info');
    } finally {
      setTimeout(() => setRestarting(false), 2000);
    }
  };

  const handleSelectModel = async (modelId) => {
    try {
      await fetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ primary_model: modelId })
      });
      showToast(`Primary model set to: ${modelId}`);
      await fetchStats();
    } catch (e) {
      console.error('Failed to update primary model:', e);
    }
  };

  const handleDeleteCombo = async (name) => {
    if (!window.confirm(`Are you sure you want to delete combo "${name}"?`)) return;
    try {
      const res = await fetch(`/api/combos/${name}`, { method: 'DELETE' });
      if (res.ok) {
        showToast(`Combo "${name}" deleted`, 'info');
        fetchStats();
      } else {
        const err = await res.json();
        showToast(err.detail || 'Failed to delete combo', 'error');
      }
    } catch (e) {
      showToast('Failed to delete combo', 'error');
    }
  };

  return (
    <div className="min-h-screen lg:h-screen lg:max-h-screen lg:overflow-hidden flex flex-col justify-between py-2 px-3 sm:px-6 bg-[#eef2f7] dark:bg-[#0f1117] text-slate-800 dark:text-slate-100 transition-colors duration-300">

      {toastMessage && (
        <div className="fixed top-4 right-4 z-50 flex items-center gap-2 px-3.5 py-2 rounded-2xl bg-slate-900 dark:bg-white text-white dark:text-slate-900 text-xs font-semibold shadow-2xl border border-white/10 animate-bounce">
          {toastMessage.type === 'success' && <CheckCircle2 className="w-4 h-4 text-emerald-400" />}
          {toastMessage.type === 'error' && <AlertCircle className="w-4 h-4 text-rose-400" />}
          {toastMessage.type === 'info' && <RefreshCw className="w-4 h-4 text-cyan-400 animate-spin" />}
          <span>{toastMessage.text}</span>
        </div>
      )}

      <header className="w-full max-w-7xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-2 mb-1.5 px-2 shrink-0">
        <div className="flex items-center gap-2.5">
          <div className="p-2 rounded-xl bg-[#ff6b35] text-white shadow-glow-orange flex items-center justify-center">
            <Zap className="w-4 h-4 fill-white" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-sm sm:text-base font-extrabold tracking-tight text-slate-900 dark:text-white">
                NIM ROUTER
              </h1>
            </div>
            <p className="text-[10px] text-slate-500 dark:text-slate-400">Universal Multi-Provider High Availability Proxy</p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-1.5">
          <button
            onClick={handleRunProbe}
            disabled={probing}
            className="px-2.5 py-1 rounded-xl bg-[#ff6b35]/15 text-[#ff6b35] hover:bg-[#ff6b35]/25 text-xs font-semibold transition neu-button flex items-center gap-1.5 disabled:opacity-50"
            title="Probe all active endpoints"
          >
            <RefreshCw className={`w-3 h-3 ${probing ? 'animate-spin' : ''}`} />
            <span>{probing ? 'Probing...' : 'Probe Pool'}</span>
          </button>

          <button
            onClick={handleRestartGateway}
            disabled={restarting}
            className="px-2.5 py-1 rounded-xl bg-slate-200 dark:bg-white/5 text-slate-700 dark:text-slate-300 hover:bg-slate-300 dark:hover:bg-white/10 text-xs font-semibold transition neu-button flex items-center gap-1.5 disabled:opacity-50"
            title="Restart Router Gateway Process"
          >
            <RotateCcw className={`w-3 h-3 ${restarting ? 'animate-spin text-[#00d2ff]' : ''}`} />
            <span>{restarting ? 'Restarting...' : 'Restart Gateway'}</span>
          </button>

          <div className="h-4 w-[1px] bg-slate-300 dark:bg-white/10 mx-0.5" />

          <button
            onClick={() => setActiveModal('models')}
            className="px-2.5 py-1 rounded-xl bg-white dark:bg-white/5 text-slate-700 dark:text-slate-300 text-xs font-semibold hover:bg-slate-50 dark:hover:bg-white/10 transition neu-button flex items-center gap-1 border border-black/5 dark:border-transparent"
          >
            <Server className="w-3 h-3 text-[#ff6b35]" />
            <span>Models</span>
          </button>
          <button
            onClick={() => setActiveModal('keys')}
            className="px-2.5 py-1 rounded-xl bg-white dark:bg-white/5 text-slate-700 dark:text-slate-300 text-xs font-semibold hover:bg-slate-50 dark:hover:bg-white/10 transition neu-button flex items-center gap-1 border border-black/5 dark:border-transparent"
          >
            <Key className="w-3 h-3 text-[#00d2ff]" />
            <span>Keys</span>
          </button>
          <button
            onClick={() => setEditingCombo('new')}
            className="px-2.5 py-1 rounded-xl bg-white dark:bg-white/5 text-slate-700 dark:text-slate-300 text-xs font-semibold hover:bg-slate-50 dark:hover:bg-white/10 transition neu-button flex items-center gap-1 border border-black/5 dark:border-transparent"
            title="Create a new routing combo"
          >
            <GitMerge className="w-3 h-3 text-[#00d2ff]" />
            <span>+ Combo</span>
          </button>
          <button
            onClick={() => setActiveModal('settings')}
            className="px-2.5 py-1 rounded-xl bg-white dark:bg-white/5 text-slate-700 dark:text-slate-300 text-xs font-semibold hover:bg-slate-50 dark:hover:bg-white/10 transition neu-button flex items-center gap-1 border border-black/5 dark:border-transparent"
          >
            <Sliders className="w-3 h-3 text-[#f72585]" />
            <span>Config</span>
          </button>
          <button
            onClick={() => setActiveModal('logs')}
            className="px-2.5 py-1 rounded-xl bg-white dark:bg-white/5 text-slate-700 dark:text-slate-300 text-xs font-semibold hover:bg-slate-50 dark:hover:bg-white/10 transition neu-button flex items-center gap-1 border border-black/5 dark:border-transparent"
          >
            <Terminal className="w-3 h-3 text-[#00a86b] dark:text-[#00f5a0]" />
            <span>Logs</span>
          </button>

          <button
            onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
            className="p-1.5 rounded-xl bg-white dark:bg-white/5 text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-white/10 transition ml-0.5 neu-button border border-black/5 dark:border-transparent"
            title="Toggle Light / Dark Mode"
          >
            {theme === 'dark' ? <Sun className="w-3.5 h-3.5 text-amber-400" /> : <Moon className="w-3.5 h-3.5 text-indigo-600" />}
          </button>
        </div>
      </header>

      <main className="flex-1 min-h-0 flex flex-col justify-center items-center w-full px-2 sm:px-4 lg:px-6 py-2">
        <BentoGrid
          stats={stats}
          logs={logs}
          onOpenModelSelector={() => setActiveModal('models')}
          onOpenKeysManager={() => setActiveModal('keys')}
          onOpenSettings={() => setActiveModal('settings')}
          onOpenLogs={() => setActiveModal('logs')}
          onOpenComboEditor={(comboOrNew) => setEditingCombo(comboOrNew)}
          onDeleteCombo={handleDeleteCombo}
          onRunProbe={handleRunProbe}
          onRestartGateway={handleRestartGateway}
          probing={probing}
          restarting={restarting}
        />
      </main>

      <footer className="w-full max-w-7xl mx-auto px-3 py-1 flex items-center justify-between text-[10px] text-slate-500 border-t border-black/5 dark:border-white/5 shrink-0">
        <div className="flex items-center gap-1">
          <span>Icons & Logos by</span>
          <a
            href="https://svgl.app/"
            target="_blank"
            rel="noreferrer"
            className="text-slate-400 hover:text-[#00d2ff] transition underline decoration-slate-500/40 underline-offset-2"
          >
            svgl.app
          </a>
        </div>
      </footer>

      {activeModal === 'models' && (
        <ModelSelectorModal
          stats={stats}
          onClose={() => setActiveModal(null)}
          onSelectModel={handleSelectModel}
        />
      )}

      {activeModal === 'keys' && (
        <KeysManagerModal
          onClose={() => setActiveModal(null)}
          onKeysUpdated={fetchStats}
        />
      )}

      {activeModal === 'settings' && (
        <SettingsModal
          stats={stats}
          onClose={() => setActiveModal(null)}
          onSettingsUpdated={fetchStats}
        />
      )}

      {activeModal === 'logs' && (
        <FullLogsModal
          logs={logs}
          onClose={() => setActiveModal(null)}
          onClearLogs={() => setLogs([])}
        />
      )}

      {editingCombo && (
        <ComboEditorModal
          combo={editingCombo === 'new' ? null : editingCombo}
          isNew={editingCombo === 'new'}
          stats={stats}
          onClose={() => {
            setEditingCombo(null);
            fetchStats();
          }}
          onCombosUpdated={fetchStats}
        />
      )}

    </div>
  );
}
