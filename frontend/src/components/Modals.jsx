import React, { useState, useEffect } from 'react';
import {
  X, Check, Search, Key, Sliders, Terminal, Shield, RefreshCw, Plus, Trash2, Zap, Server, Activity, Copy, CheckCircle, Eye, EyeOff, Edit2, Wrench, Code, Brain, MessageSquare, Layers, Sparkles, Lock, KeyRound, BarChart3, ArrowUpRight, TrendingUp, Clock, AlertCircle, PieChart, GripVertical
} from 'lucide-react';
import { ModelIcon, ProviderIcon, resolveProvider } from './ModelIcon';
import { authFetch } from '../api';

export { ModelIcon, ProviderIcon, resolveProvider };

export function ModalWrapper({ title, icon: Icon, onClose, children, maxWidth = "max-w-2xl" }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-fade-in">
      <div className={`relative w-full ${maxWidth} max-h-[90vh] flex flex-col bg-white dark:bg-[#151922] text-slate-800 dark:text-slate-100 rounded-3xl border border-black/10 dark:border-white/10 shadow-neu-light dark:shadow-neu-dark overflow-hidden transition-colors duration-300`}>
        <div className="flex items-center justify-between px-6 py-4 border-b border-black/5 dark:border-white/5">
          <div className="flex items-center gap-3">
            {Icon && <div className="p-2 rounded-xl bg-black/5 dark:bg-white/5 text-[#ff6b35]"><Icon className="w-5 h-5" /></div>}
            <h2 className="text-lg font-semibold tracking-wide uppercase">{title}</h2>
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-xl text-slate-400 hover:text-slate-800 dark:hover:text-white hover:bg-black/5 dark:hover:bg-white/5 transition"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
        <div className="p-6 overflow-y-auto space-y-4">
          {children}
        </div>
      </div>
    </div>
  );
}

export function ModelSelectorModal({ stats, onClose, onSelectModel }) {
  const [search, setSearch] = useState('');
  const [providerFilter, setProviderFilter] = useState('ALL');

  const models = stats?.models || [];
  const providers = ['ALL', 'NVIDIA', 'Groq', 'Cerebras', 'OpenRouter', 'OpenCode', 'BAI'];

  const filtered = models.filter(m => {
    const matchesSearch = m.id.toLowerCase().includes(search.toLowerCase()) || m.provider.toLowerCase().includes(search.toLowerCase());
    const matchesProv = providerFilter === 'ALL' || m.provider.toUpperCase() === providerFilter.toUpperCase();
    return matchesSearch && matchesProv;
  });

  const categories = [
    { id: 'nim-auto', name: 'nim-auto (Universal Auto-Balancer)', desc: 'Routes automatically to the lowest-latency healthy endpoint.' },
    { id: 'nim-coding', name: 'nim-coding (Coding Specialist)', desc: 'Prioritizes Codestral, DeepSeek Coder, Qwen Coder.' },
    { id: 'nim-reasoning', name: 'nim-reasoning (Reasoning & Math)', desc: 'Prioritizes DeepSeek R1, QwQ, reasoning models.' },
    { id: 'nim-vision', name: 'nim-vision (Multimodal & Vision)', desc: 'Prioritizes image-capable vision models.' },
    { id: 'nim-moe', name: 'nim-moe (Mixture-of-Experts)', desc: 'Prioritizes high-parameter MoE architectures.' },
    { id: 'nim-chat', name: 'nim-chat (Fast Conversational)', desc: 'Prioritizes lightweight conversational chat models.' },
  ];

  return (
    <ModalWrapper title="Model Priority & Selection" icon={Server} onClose={onClose}>
      <div>
        <h3 className="text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-2">Virtual Purpose Categories</h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          {categories.map(cat => (
            <div
              key={cat.id}
              onClick={() => { onSelectModel(cat.id); onClose(); }}
              className={`p-3 rounded-2xl cursor-pointer border transition ${stats?.primary_model === cat.id
                ? 'bg-[#ff6b35]/15 border-[#ff6b35]/50 text-[#ff6b35] dark:text-white font-semibold'
                : 'bg-slate-100 dark:bg-white/5 border-black/5 dark:border-white/5 hover:border-black/20 dark:hover:border-white/20'
                }`}
            >
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs font-semibold">{cat.name}</span>
                {stats?.primary_model === cat.id && <Check className="w-3.5 h-3.5 text-[#ff6b35]" />}
              </div>
              <p className="text-[11px] text-slate-500 dark:text-slate-400 leading-snug">{cat.desc}</p>
            </div>
          ))}
        </div>
      </div>

      <div className="pt-2">
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider">Discovered Provider Models ({filtered.length})</h3>
        </div>

        <div className="flex flex-col sm:flex-row gap-2 mb-3">
          <div className="relative flex-1">
            <Search className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              type="text"
              placeholder="Search models..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full pl-9 pr-3 py-1.5 text-xs rounded-xl bg-slate-100 dark:bg-black/40 border border-black/10 dark:border-white/10 text-slate-900 dark:text-slate-100 focus:outline-none focus:border-[#ff6b35]/50"
            />
          </div>
          <div className="flex gap-1 overflow-x-auto pb-1">
            {providers.map(p => (
              <button
                key={p}
                onClick={() => setProviderFilter(p)}
                title={p === 'ALL' ? 'All Providers' : p}
                className={`px-2.5 py-1 text-[11px] font-medium rounded-lg transition whitespace-nowrap ${providerFilter === p
                  ? 'bg-[#ff6b35] text-white'
                  : 'bg-slate-100 dark:bg-white/5 text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white'
                  }`}
              >
                {p === 'ALL' ? 'All Providers' : <ProviderIcon provider={p} className="h-2.5 w-auto max-w-[28px] max-h-2.5" />}
              </button>
            ))}
          </div>
        </div>

        <div className="space-y-1.5 max-h-60 overflow-y-auto pr-1">
          {filtered.map(m => (
            <div
              key={m.id}
              onClick={() => { onSelectModel(m.id); onClose(); }}
              className={`flex items-center justify-between p-2.5 rounded-xl cursor-pointer border transition ${stats?.primary_model === m.id
                ? 'bg-[#ff6b35]/15 border-[#ff6b35]/50 text-slate-900 dark:text-white'
                : 'bg-slate-50 dark:bg-white/[0.03] border-black/5 dark:border-white/5 hover:border-black/20 dark:hover:border-white/20'
                }`}
            >
              <div className="flex items-center gap-2 overflow-hidden">
                <span className="w-1.5 h-1.5 rounded-full bg-[#00f5a0] shrink-0" />
                <ModelIcon model={m.id} provider={m.provider} className="h-3.5 w-auto max-w-[48px] max-h-3.5 shrink-0" />
                <span className="text-xs font-mono truncate text-slate-800 dark:text-slate-200">{m.id}</span>
                
              </div>
              <div className="flex items-center gap-3 text-[11px] text-slate-500 dark:text-slate-400 shrink-0 ml-2">
                <span>{m.latency}s</span>
                <span className="text-[#00d2ff]">{m.tps} tps</span>
                {stats?.primary_model === m.id && <Check className="w-3.5 h-3.5 text-[#ff6b35]" />}
              </div>
            </div>
          ))}
          {filtered.length === 0 && (
            <div className="text-center py-6 text-xs text-slate-500">No matching models found in active pool.</div>
          )}
        </div>
      </div>
    </ModalWrapper>
  );
}



export function KeysManagerModal({ onClose, onKeysUpdated }) {
  const [keysData, setKeysData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedProvider, setSelectedProvider] = useState('NVIDIA');
  const [keyInput, setKeyInput] = useState('');
  const [showKey, setShowKey] = useState(false);
  const [actionStatus, setActionStatus] = useState('');
  const [editingIndex, setEditingIndex] = useState(null);

  const providerMeta = {
    NVIDIA: { name: 'NVIDIA NIM', short: 'NVIDIA', color: '#76B900', env: 'NVIDIA_API_KEYS', multi: true, placeholder: 'nvapi-...' },
    Groq: { name: 'Groq LPU', short: 'Groq', color: '#F55036', env: 'GROQ_API_KEYS', multi: true, placeholder: 'gsk_...' },
    Cerebras: { name: 'Cerebras Wafer', short: 'Cerebras', color: '#FF6B35', env: 'CEREBRAS_API_KEYS', multi: true, placeholder: 'csk-...' },
    OpenRouter: { name: 'OpenRouter Free', short: 'OpenRouter', color: '#6366F1', env: 'OPENROUTER_API_KEY', multi: false, placeholder: 'sk-or-v1-...' },
    OpenCode: { name: 'OpenCode Zen', short: 'OpenCode', color: '#00D2FF', env: 'OPENCODE_API_KEY', multi: false, placeholder: 'opencode_...' },
    BAI: { name: 'B.AI Free', short: 'B.AI', color: '#A855F7', env: 'BAI_API_KEY', multi: false, placeholder: 'bai_...' }
  };

  const fetchKeys = async () => {
    try {
      const res = await authFetch('/api/keys');
      const data = await res.json();
      setKeysData(data.providers || []);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  React.useEffect(() => {
    fetchKeys();
  }, []);

  const handleUpdate = async (action, value = null, index = null) => {
    setActionStatus('Saving...');
    try {
      const payload = {
        provider: selectedProvider,
        action: action,
        key: value !== null ? value : keyInput.trim()
      };
      if (index !== null) {
        payload.index = index;
      }
      const res = await authFetch('/api/keys', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      if (res.ok) {
        setKeyInput('');
        setEditingIndex(null);
        setActionStatus('Saved successfully!');
        await fetchKeys();
        if (onKeysUpdated) onKeysUpdated();
        setTimeout(() => setActionStatus(''), 2500);
      } else {
        setActionStatus('Failed to save.');
      }
    } catch (e) {
      setActionStatus('Error saving key.');
    }
  };

  const currentProviderInfo = keysData.find(p => p.id === selectedProvider);
  const currentMeta = providerMeta[selectedProvider] || { name: selectedProvider, short: selectedProvider, color: '#ff6b35', env: '', multi: false, placeholder: 'Paste API key...' };
  const configuredKeys = currentProviderInfo?.keys || [];

  return (
    <ModalWrapper title="Multi-Provider Key Manager" icon={Key} onClose={onClose}>
      <p className="text-xs text-slate-500 dark:text-slate-400">
        Configure single or multiple keys per provider. The router rotates requests across multiple keys in round-robin to maximize throughput and avoid rate limits.
      </p>

      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2 pt-1">
        {keysData.map(p => {
          const isSelected = selectedProvider === p.id;
          const meta = providerMeta[p.id] || { name: p.name, short: p.id, color: '#ff6b35' };
          const hasKeys = p.count > 0;
          return (
            <button
              key={p.id}
              onClick={() => {
                setSelectedProvider(p.id);
                setKeyInput('');
                setEditingIndex(null);
              }}
              style={{
                borderColor: isSelected ? meta.color : undefined,
                boxShadow: isSelected ? `0 0 12px ${meta.color}33` : undefined
              }}
              className={`p-2.5 rounded-2xl text-center transition-all flex flex-col items-center justify-center gap-1.5 border neu-button ${isSelected
                ? 'bg-black/5 dark:bg-white/10 text-slate-900 dark:text-white font-semibold'
                : 'bg-slate-100 dark:bg-white/5 border-black/5 dark:border-white/5 text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white'
                }`}
            >
              <div
                className="h-8 w-full max-w-[84px] px-1.5 rounded-xl flex items-center justify-center transition-transform group-hover:scale-105"
                style={{ backgroundColor: `${meta.color}18` }}
              >
                <ProviderIcon provider={p.id} className="h-4 w-auto max-w-[68px] max-h-4" />
              </div>
              <div className="text-[11px] font-semibold tracking-tight">{meta.short}</div>
              <span
                className={`text-[9px] px-1.5 py-0.5 rounded-full font-mono ${hasKeys
                  ? 'bg-black/5 dark:bg-white/10 text-slate-700 dark:text-slate-300 font-semibold'
                  : 'text-slate-400 dark:text-slate-500'
                  }`}
              >
                {hasKeys ? `${p.count} key${p.count > 1 ? 's' : ''}` : 'No key'}
              </span>
            </button>
          );
        })}
      </div>

      {selectedProvider && (
        <div className="p-4 sm:p-5 rounded-3xl bg-slate-100 dark:bg-black/40 border border-black/10 dark:border-white/10 space-y-4 mt-2">
          <div className="flex items-center justify-between gap-2 border-b border-black/5 dark:border-white/5 pb-3">
            <div className="flex items-center gap-2.5">
              <div
                className="h-9 px-3 rounded-xl flex items-center justify-center"
                style={{ backgroundColor: `${currentMeta.color}22` }}
              >
                <ProviderIcon provider={selectedProvider} className="h-5 w-auto max-w-[85px] max-h-5" />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="text-xs font-bold text-slate-900 dark:text-white">{currentMeta.name}</h3>
                  <span className="text-[9px] font-mono px-2 py-0.5 rounded-lg bg-black/5 dark:bg-white/10 text-slate-500 dark:text-slate-400">
                    {currentMeta.env}
                  </span>
                </div>
                <p className="text-[10px] text-slate-500 dark:text-slate-400">
                  {currentMeta.multi ? 'Supports multi-key pool rotation (Round Robin)' : 'Single key provider'}
                </p>
              </div>
            </div>
            {actionStatus && (
              <span className="text-[11px] font-semibold text-[#00f5a0] animate-fade-in">{actionStatus}</span>
            )}
          </div>

          <div>
            <div className="text-[10px] uppercase text-slate-500 dark:text-slate-400 font-bold tracking-wider mb-1.5 flex items-center justify-between">
              <span>Configured Keys ({configuredKeys.length})</span>
            </div>
            {configuredKeys.length > 0 ? (
              <div className="flex flex-wrap gap-2">
                {configuredKeys.map((k, i) => {
                  const isEditingThis = editingIndex === i;
                  return (
                    <div
                      key={i}
                      className={`flex items-center gap-1.5 px-3 py-1.5 rounded-xl border text-xs font-mono shadow-sm transition ${isEditingThis
                        ? 'bg-[#ff6b35]/15 border-[#ff6b35]/60 text-slate-900 dark:text-white font-semibold'
                        : 'bg-white dark:bg-white/5 border-black/5 dark:border-white/10 text-slate-800 dark:text-slate-200'
                        }`}
                    >
                      <Key className={`w-3 h-3 ${isEditingThis ? 'text-[#ff6b35]' : 'text-slate-400'}`} />
                      <span>{k}</span>
                      <button
                        type="button"
                        onClick={() => {
                          setEditingIndex(isEditingThis ? null : i);
                          setKeyInput('');
                        }}
                        className={`ml-1 p-0.5 rounded transition ${isEditingThis ? 'text-[#ff6b35]' : 'text-slate-400 hover:text-slate-700 dark:hover:text-slate-200'
                          }`}
                        title={isEditingThis ? "Cancel update" : "Update this key"}
                      >
                        <Edit2 className="w-3 h-3" />
                      </button>
                      <button
                        type="button"
                        onClick={() => handleUpdate('delete', null, i)}
                        className="p-0.5 rounded text-slate-400 hover:text-rose-500 transition"
                        title="Delete this key"
                      >
                        <X className="w-3 h-3" />
                      </button>
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="text-xs text-slate-400 dark:text-slate-500 italic py-1">
                No keys configured yet. Paste a key below to connect {currentMeta.name}.
              </div>
            )}
          </div>

          <div className="space-y-2 pt-1 border-t border-black/5 dark:border-white/5">
            <div className="flex items-center justify-between">
              <div className="text-[10px] uppercase text-slate-500 dark:text-slate-400 font-bold tracking-wider">
                {editingIndex !== null
                  ? `Updating Key #${editingIndex + 1} (${configuredKeys[editingIndex] || ''})`
                  : (configuredKeys.length > 0 ? 'Add or Update API Key' : 'Enter API Key')}
              </div>
              {editingIndex !== null && (
                <button
                  type="button"
                  onClick={() => {
                    setEditingIndex(null);
                    setKeyInput('');
                  }}
                  className="text-[10px] text-[#ff6b35] hover:underline font-semibold"
                >
                  Cancel
                </button>
              )}
            </div>

            <div className="flex flex-col sm:flex-row gap-2">
              <div className="relative flex-1">
                <input
                  type={showKey ? 'text' : 'password'}
                  placeholder={
                    editingIndex !== null
                      ? `Enter replacement key for key #${editingIndex + 1}...`
                      : `Paste ${currentMeta.short} API key (${currentMeta.placeholder})`
                  }
                  value={keyInput}
                  onChange={(e) => setKeyInput(e.target.value)}
                  className="w-full pl-3.5 pr-10 py-2 text-xs font-mono rounded-xl bg-white dark:bg-black/60 border border-black/10 dark:border-white/10 text-slate-900 dark:text-slate-100 focus:outline-none focus:border-[#ff6b35]/60 transition"
                />
                <button
                  type="button"
                  onClick={() => setShowKey(!showKey)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 transition"
                  title={showKey ? 'Hide key' : 'Show key'}
                >
                  {showKey ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
                </button>
              </div>

              <div className="flex items-center gap-1.5">
                {editingIndex !== null ? (
                  <>
                    <button
                      onClick={() => handleUpdate('update', null, editingIndex)}
                      disabled={!keyInput.trim()}
                      className="flex-1 sm:flex-none px-3.5 py-2 rounded-xl bg-[#ff6b35] hover:bg-[#ff8c42] disabled:opacity-40 text-white text-xs font-semibold transition neu-button flex items-center justify-center gap-1 shadow-sm"
                    >
                      <Check className="w-3.5 h-3.5" />
                      <span>Update Key #{editingIndex + 1}</span>
                    </button>
                    <button
                      onClick={() => {
                        setEditingIndex(null);
                        setKeyInput('');
                      }}
                      className="px-3 py-2 rounded-xl bg-slate-200 dark:bg-white/10 hover:bg-slate-300 dark:hover:bg-white/15 text-slate-700 dark:text-slate-300 text-xs font-semibold transition"
                    >
                      Cancel
                    </button>
                  </>
                ) : (
                  <>
                    <button
                      onClick={() => handleUpdate('set')}
                      disabled={!keyInput.trim()}
                      className="flex-1 sm:flex-none px-3.5 py-2 rounded-xl bg-[#ff6b35] hover:bg-[#ff8c42] disabled:opacity-40 text-white text-xs font-semibold transition neu-button flex items-center justify-center gap-1 shadow-sm"
                      title="Replace / Set as primary key"
                    >
                      <Check className="w-3.5 h-3.5" />
                      <span>Update Key</span>
                    </button>

                    {currentMeta.multi && (
                      <button
                        onClick={() => handleUpdate('add')}
                        disabled={!keyInput.trim()}
                        className="flex-1 sm:flex-none px-3.5 py-2 rounded-xl bg-slate-200 dark:bg-white/10 hover:bg-slate-300 dark:hover:bg-white/15 disabled:opacity-40 text-slate-800 dark:text-slate-200 text-xs font-semibold transition neu-button flex items-center justify-center gap-1"
                        title="Add another key to round-robin rotation pool"
                      >
                        <Plus className="w-3.5 h-3.5" />
                        <span>Add Key</span>
                      </button>
                    )}

                    {configuredKeys.length > 0 && (
                      <button
                        onClick={() => handleUpdate('clear')}
                        className="px-3 py-2 rounded-xl bg-rose-500/15 hover:bg-rose-500/25 text-rose-600 dark:text-rose-400 text-xs font-semibold transition"
                        title="Remove all keys for this provider"
                      >
                        Clear All
                      </button>
                    )}
                  </>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </ModalWrapper>
  );
}

export function SettingsModal({ stats, onClose, onSettingsUpdated }) {
  const [strategy, setStrategy] = useState(stats?.routing_strategy || 'fallback');
  const [maxLatency, setMaxLatency] = useState(stats?.max_latency_threshold || 3.0);
  const [saving, setSaving] = useState(false);
  const [savedMsg, setSavedMsg] = useState('');

  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showPw, setShowPw] = useState(false);
  const [changingPw, setChangingPw] = useState(false);
  const [pwStatus, setPwStatus] = useState(null);

  const handleSave = async () => {
    setSaving(true);
    try {
      const res = await authFetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          routing_strategy: strategy,
          max_latency_threshold: parseFloat(maxLatency)
        })
      });
      if (res.ok) {
        setSavedMsg('Settings saved!');
        if (onSettingsUpdated) onSettingsUpdated();
        setTimeout(() => setSavedMsg(''), 2000);
      }
    } catch (e) {
      console.error(e);
    } finally {
      setSaving(false);
    }
  };

  const handleChangePassword = async (e) => {
    if (e) e.preventDefault();
    if (!currentPassword) {
      setPwStatus({ type: 'error', message: 'Please enter your current password.' });
      return;
    }
    if (!newPassword || newPassword.length < 4) {
      setPwStatus({ type: 'error', message: 'New password must be at least 4 characters long.' });
      return;
    }
    if (newPassword !== confirmPassword) {
      setPwStatus({ type: 'error', message: 'New passwords do not match.' });
      return;
    }

    setChangingPw(true);
    setPwStatus(null);
    try {
      const res = await authFetch('/api/auth/change-password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          current_password: currentPassword,
          new_password: newPassword
        })
      });
      const data = await res.json();
      if (res.ok && data.success) {
        setPwStatus({ type: 'success', message: 'Password updated successfully!' });
        setCurrentPassword('');
        setNewPassword('');
        setConfirmPassword('');
        setTimeout(() => setPwStatus(null), 3500);
      } else {
        setPwStatus({ type: 'error', message: data.detail || 'Failed to update password.' });
      }
    } catch (err) {
      setPwStatus({ type: 'error', message: 'Error communicating with server.' });
    } finally {
      setChangingPw(false);
    }
  };

  return (
    <ModalWrapper title="Routing & Engine Settings" icon={Sliders} onClose={onClose}>
      <div className="space-y-2">
        <label className="text-xs font-semibold text-slate-700 dark:text-slate-300 uppercase tracking-wider">Routing Strategy</label>
        <div className="grid grid-cols-2 gap-3">
          <div
            onClick={() => setStrategy('fallback')}
            className={`p-3.5 rounded-2xl cursor-pointer border transition ${strategy === 'fallback'
              ? 'bg-[#00d2ff]/15 border-[#00d2ff]/50 text-slate-900 dark:text-white font-semibold'
              : 'bg-slate-100 dark:bg-white/5 border-black/5 dark:border-white/5 text-slate-600 dark:text-slate-400 hover:border-black/20 dark:hover:border-white/20'
              }`}
          >
            <div className="text-xs font-semibold mb-1">Fallback Mode (Recommended)</div>
            <p className="text-[11px] text-slate-500 dark:text-slate-400">Strict latency & reliability order. Cascades to next candidate on error.</p>
          </div>
          <div
            onClick={() => setStrategy('round_robin')}
            className={`p-3.5 rounded-2xl cursor-pointer border transition ${strategy === 'round_robin'
              ? 'bg-[#00d2ff]/15 border-[#00d2ff]/50 text-slate-900 dark:text-white font-semibold'
              : 'bg-slate-100 dark:bg-white/5 border-black/5 dark:border-white/5 text-slate-600 dark:text-slate-400 hover:border-black/20 dark:hover:border-white/20'
              }`}
          >
            <div className="text-xs font-semibold mb-1">Round Robin Mode</div>
            <p className="text-[11px] text-slate-500 dark:text-slate-400">Rotates requests evenly across the primary pool of healthy endpoints.</p>
          </div>
        </div>
      </div>

      <div className="space-y-2 pt-2">
        <div className="flex justify-between items-center">
          <label className="text-xs font-semibold text-slate-700 dark:text-slate-300 uppercase tracking-wider">Max Latency Threshold</label>
          <span className="text-xs font-mono font-bold text-[#00d2ff]">{maxLatency}s</span>
        </div>
        <input
          type="range"
          min="1.0"
          max="8.0"
          step="0.5"
          value={maxLatency}
          onChange={(e) => setMaxLatency(e.target.value)}
          className="w-full accent-[#00d2ff]"
        />
        <p className="text-[11px] text-slate-500 dark:text-slate-400">Restricts active pool to endpoints responding in under {maxLatency} seconds.</p>
      </div>

      <div className="flex items-center justify-between pt-3 border-t border-black/10 dark:border-white/10">
        {savedMsg ? <span className="text-xs text-[#00f5a0]">{savedMsg}</span> : <div />}
        <button
          onClick={handleSave}
          disabled={saving}
          className="px-5 py-2 rounded-xl bg-[#00d2ff] hover:bg-[#3a7bd5] text-slate-900 font-bold text-xs transition neu-button"
        >
          {saving ? 'Saving...' : 'Apply Engine Settings'}
        </button>
      </div>

      <div className="space-y-3 pt-4 border-t border-black/10 dark:border-white/10">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Lock className="w-4 h-4 text-[#da7756]" />
            <label className="text-xs font-semibold text-slate-700 dark:text-slate-300 uppercase tracking-wider">
              Dashboard Access Password
            </label>
          </div>
        </div>

        <p className="text-[11px] text-slate-500 dark:text-slate-400">
          Change the password required to access this dashboard and manage routing configurations.
        </p>

        {pwStatus && (
          <div
            className={`p-2.5 rounded-xl text-xs flex items-center gap-2 ${pwStatus.type === 'success'
              ? 'bg-emerald-500/15 border border-emerald-500/30 text-emerald-600 dark:text-emerald-400'
              : 'bg-rose-500/15 border border-rose-500/30 text-rose-600 dark:text-rose-400'
              }`}
          >
            {pwStatus.type === 'success' ? (
              <Check className="w-3.5 h-3.5 shrink-0" />
            ) : (
              <X className="w-3.5 h-3.5 shrink-0" />
            )}
            <span>{pwStatus.message}</span>
          </div>
        )}

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
          <div>
            <label className="text-[10px] text-slate-400 mb-1 block">Current Password</label>
            <input
              type={showPw ? 'text' : 'password'}
              placeholder="Current password..."
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              className="w-full px-3 py-2 text-xs font-mono rounded-xl bg-slate-100 dark:bg-black/50 border border-black/10 dark:border-white/10 text-slate-900 dark:text-slate-100 focus:outline-none focus:border-[#da7756]"
            />
          </div>
          <div>
            <label className="text-[10px] text-slate-400 mb-1 block">New Password</label>
            <input
              type={showPw ? 'text' : 'password'}
              placeholder="New password (min 4 chars)..."
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              className="w-full px-3 py-2 text-xs font-mono rounded-xl bg-slate-100 dark:bg-black/50 border border-black/10 dark:border-white/10 text-slate-900 dark:text-slate-100 focus:outline-none focus:border-[#da7756]"
            />
          </div>
          <div>
            <label className="text-[10px] text-slate-400 mb-1 block">Confirm New</label>
            <input
              type={showPw ? 'text' : 'password'}
              placeholder="Confirm new password..."
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              className="w-full px-3 py-2 text-xs font-mono rounded-xl bg-slate-100 dark:bg-black/50 border border-black/10 dark:border-white/10 text-slate-900 dark:text-slate-100 focus:outline-none focus:border-[#da7756]"
            />
          </div>
        </div>

        <div className="flex items-center justify-between pt-1">
          <button
            type="button"
            onClick={() => setShowPw(!showPw)}
            className="text-[11px] text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 transition flex items-center gap-1"
          >
            {showPw ? <EyeOff className="w-3 h-3" /> : <Eye className="w-3 h-3" />}
            <span>{showPw ? 'Hide passwords' : 'Show passwords'}</span>
          </button>

          <button
            type="button"
            onClick={handleChangePassword}
            disabled={changingPw || !currentPassword || !newPassword}
            className="px-3.5 py-1.5 rounded-xl bg-[#da7756] hover:bg-[#ff8c42] disabled:opacity-40 text-white text-xs font-semibold transition neu-button flex items-center gap-1.5"
          >
            {changingPw ? <RefreshCw className="w-3 h-3 animate-spin" /> : <KeyRound className="w-3 h-3" />}
            <span>Change Password</span>
          </button>
        </div>
      </div>
    </ModalWrapper>
  );
}


export function FullLogsModal({ logs, onClose, onClearLogs }) {
  const [filter, setFilter] = useState('');
  const filtered = logs.filter(l => l.message.toLowerCase().includes(filter.toLowerCase()) || l.level.toLowerCase().includes(filter.toLowerCase()));

  return (
    <ModalWrapper title="Live Server Log Stream" icon={Terminal} onClose={onClose}>
      <div className="flex items-center justify-between gap-2 pb-2">
        <input
          type="text"
          placeholder="Filter logs..."
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          className="px-3 py-1 text-xs rounded-lg bg-black/40 border border-white/10 text-slate-200 focus:outline-none focus:border-[#ff6b35]"
        />
        <button
          onClick={onClearLogs}
          className="text-xs text-slate-400 hover:text-white px-2 py-1 rounded bg-white/5 hover:bg-white/10 transition"
        >
          Clear
        </button>
      </div>
      <div className="h-96 overflow-y-auto p-3 rounded-2xl bg-black/80 font-mono text-[11px] space-y-1 shadow-neu-dark-inset">
        {filtered.map((log, i) => (
          <div key={i} className="flex gap-2 leading-relaxed">
            <span className="text-slate-500">{log.timestamp}</span>
            <span className={`font-semibold ${log.level === 'INFO' ? 'text-[#00d2ff]' :
              log.level === 'SUCCESS' ? 'text-[#00f5a0]' :
                log.level === 'WARNING' ? 'text-[#ffb703]' :
                  log.level === 'ERROR' ? 'text-[#ff4d6d]' : 'text-slate-400'
              }`}>
              [{log.level}]
            </span>
            <span className="text-slate-200">{log.message}</span>
          </div>
        ))}
      </div>
    </ModalWrapper>
  );
}

const STRATEGY_LABELS = {
  round_robin: { label: 'Round Robin', color: 'text-[#00d2ff]', bg: 'bg-[#00d2ff]/15 border-[#00d2ff]/30' },
  fallback: { label: 'Fallback', color: 'text-[#ff6b35]', bg: 'bg-[#ff6b35]/15 border-[#ff6b35]/30' },
};

function ComboEditor({ combo, allModels, onSave, onCancel, isNew, maxLatencyThreshold = 3.0 }) {
  const [name, setName] = useState(combo?.name || '');
  const [strategy, setStrategy] = useState(combo?.strategy || 'fallback');
  const [models, setModels] = useState(combo?.models || []);
  const [draggedIndex, setDraggedIndex] = useState(null);
  const [dragOverIndex, setDragOverIndex] = useState(null);
  const [search, setSearch] = useState('');
  const [focused, setFocused] = useState(false);
  const [taskFilter, setTaskFilter] = useState('ALL');
  const [providerFilter, setProviderFilter] = useState('ALL');
  const [showSortWarning, setShowSortWarning] = useState(false);
  const [previousOrder, setPreviousOrder] = useState(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const slugify = (s) => s.toLowerCase().replace(/[^a-z0-9-]/g, '-').replace(/-+/g, '-').replace(/^-|-$/g, '');

  const matchesTask = (m, task) => {
    if (!task || task === 'ALL') return true;
    if (m.tasks && Array.isArray(m.tasks)) {
      return m.tasks.includes(task);
    }
    if (m.capabilities && typeof m.capabilities === 'object') {
      return !!m.capabilities[task];
    }
    const mid = (m.id || '').toLowerCase();
    if (task === 'tools') {
      return ['llama-3.1', 'llama-3.2', 'llama-3.3', 'llama3.1', 'llama3.2', 'llama3.3', 'qwen-2.5', 'qwen2.5', 'mistral-large', 'mistral-small', 'mixtral-8x7b', 'command-r', 'nemotron-4', 'nemotron-3-super', 'gpt-4', 'claude-3', 'deepseek-v3', 'hermes'].some(k => mid.includes(k));
    }
    if (task === 'coding') {
      return ['code', 'coder', 'codestral', 'starcoder', 'deepseek-coder', 'qwen-coder', 'dev', 'llama-3.3-70b', 'nemotron-3-super-120b', 'qwen-2.5-72b', 'gpt-oss-120b'].some(k => mid.includes(k));
    }
    if (task === 'reasoning') {
      return ['reasoning', 'r1', 'qwq', 'think', 'o1', 'o3', 'reasoner', 'deepseek-r1'].some(k => mid.includes(k));
    }
    if (task === 'vision') {
      return ['vision', '-vl', 'vl-', '_vl', 'omni', 'paligemma', 'pixtral', 'llava'].some(k => mid.includes(k));
    }
    if (task === 'chat') {
      return ['instruct', 'chat', 'gemma', 'llama', 'mistral', 'qwen', 'glm', 'hy3'].some(k => mid.includes(k));
    }
    if (task === 'moe') {
      return ['moe', 'mixtral', 'dbrx', 'a3b', 'a12b', 'a55b', 'deepseek-v3'].some(k => mid.includes(k));
    }
    return true;
  };

  const TASK_FILTERS = [
    { id: 'ALL', label: 'All', icon: Sparkles },
    { id: 'tools', label: 'Tools', icon: Wrench },
    { id: 'coding', label: 'Coding', icon: Code },
    { id: 'reasoning', label: 'Reasoning', icon: Brain },
    { id: 'vision', label: 'Vision', icon: Eye },
    { id: 'chat', label: 'Chat', icon: MessageSquare },
    { id: 'moe', label: 'MoE', icon: Layers },
  ];

  const availableProviders = ['ALL', ...Array.from(new Set(allModels.map(m => m.provider).filter(Boolean)))];

  const getTaskCount = (task) => {
    return allModels.filter(m =>
      matchesTask(m, task) &&
      (providerFilter === 'ALL' || (m.provider || '').toUpperCase() === providerFilter.toUpperCase()) &&
      !models.includes(m.id)
    ).length;
  };

  const getProviderCount = (prov) => {
    return allModels.filter(m =>
      (prov === 'ALL' || (m.provider || '').toUpperCase() === prov.toUpperCase()) &&
      matchesTask(m, taskFilter) &&
      !models.includes(m.id)
    ).length;
  };

  const filtered = allModels.filter(m =>
    matchesTask(m, taskFilter) &&
    (providerFilter === 'ALL' || (m.provider || '').toUpperCase() === providerFilter.toUpperCase()) &&
    m.id.toLowerCase().includes(search.toLowerCase()) &&
    !models.includes(m.id)
  );

  const addModel = (id) => {
    setModels(prev => [...prev, id]);
    setSearch('');
    setPreviousOrder(null);
  };

  const removeModel = (id) => {
    setModels(prev => prev.filter(m => m !== id));
    setPreviousOrder(null);
  };

  const getModelLatency = (id) => {
    const m = allModels.find(x => x.id === id || x.id.toLowerCase() === id.toLowerCase());
    if (!m || !m.healthy) return 999999;
    if (typeof m.latency === 'number' && !isNaN(m.latency)) return m.latency;
    return 99999;
  };

  const handleSortByLatency = () => {
    setPreviousOrder([...models]);
    const sorted = [...models].sort((a, b) => getModelLatency(a) - getModelLatency(b));
    setModels(sorted);
    setShowSortWarning(false);
  };

  const handleUndoSort = () => {
    if (previousOrder) {
      setModels(previousOrder);
      setPreviousOrder(null);
    }
  };

  const handleDragStart = (e, index) => {
    setDraggedIndex(index);
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', String(index));
  };

  const handleDragOver = (e, index) => {
    e.preventDefault();
    if (draggedIndex === null) return;
    e.dataTransfer.dropEffect = 'move';
    if (dragOverIndex !== index) {
      setDragOverIndex(index);
    }
  };

  const handleDrop = (e, dropIndex) => {
    e.preventDefault();
    if (draggedIndex === null || draggedIndex === undefined) return;
    if (
      draggedIndex >= 0 &&
      draggedIndex < models.length &&
      dropIndex >= 0 &&
      dropIndex < models.length &&
      draggedIndex !== dropIndex
    ) {
      const updated = [...models];
      const [movedItem] = updated.splice(draggedIndex, 1);
      updated.splice(dropIndex, 0, movedItem);
      setModels(updated);
      setPreviousOrder(null);
    }
    setDraggedIndex(null);
    setDragOverIndex(null);
  };

  const handleDragEnd = () => {
    setDraggedIndex(null);
    setDragOverIndex(null);
  };

  const handleSave = async () => {
    const finalName = isNew ? slugify(name) : combo.name;
    if (!finalName) { setError('Name is required.'); return; }
    if (models.length === 0) { setError('Add at least one model.'); return; }
    setSaving(true); setError('');
    try {
      const url = isNew ? '/api/combos' : `/api/combos/${combo.name}`;
      const method = isNew ? 'POST' : 'PUT';
      const res = await authFetch(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: finalName, strategy, models }),
      });
      if (!res.ok) {
        const err = await res.json();
        setError(err.detail || 'Failed to save.');
      } else {
        onSave();
      }
    } catch (e) {
      setError('Network error.');
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteCombo = async () => {
    if (!combo?.name) return;
    if (!window.confirm(`Are you sure you want to delete combo "${combo.name}"?`)) return;
    setSaving(true);
    setError('');
    try {
      const res = await authFetch(`/api/combos/${combo.name}`, { method: 'DELETE' });
      if (!res.ok) {
        const err = await res.json();
        setError(err.detail || 'Failed to delete combo.');
      } else {
        onSave();
      }
    } catch (e) {
      setError('Network error while deleting combo.');
    } finally {
      setSaving(false);
    }
  };

  const isOptionsOpen = focused || search.length > 0 || taskFilter !== 'ALL' || providerFilter !== 'ALL';

  return (
    <div className="space-y-4 relative">
      {isOptionsOpen && (
        <div
          className="fixed inset-0 z-20 bg-black/40 backdrop-blur-sm animate-fade-in"
          onMouseDown={(e) => {
            e.preventDefault();
            setFocused(false);
            setSearch('');
            setTaskFilter('ALL');
            setProviderFilter('ALL');
          }}
        />
      )}

      {isNew && (
        <div className={`space-y-1 transition-all duration-200 ${isOptionsOpen ? 'filter blur-[2px] opacity-35 pointer-events-none select-none' : ''}`}>
          <label className="text-[10px] uppercase font-semibold text-slate-500 dark:text-slate-400 tracking-wider">Combo Name <span className="text-slate-400 normal-case">(becomes model ID)</span></label>
          <input
            type="text"
            value={name}
            onChange={e => setName(e.target.value)}
            placeholder="e.g. my-coding-team"
            className="w-full px-3 py-2 text-sm font-mono rounded-xl bg-slate-100 dark:bg-black/40 border border-black/10 dark:border-white/10 text-slate-900 dark:text-slate-100 focus:outline-none focus:border-[#00d2ff]/50"
          />
          {name && <p className="text-[10px] text-slate-400 font-mono">Model ID: <span className="text-[#00d2ff]">{slugify(name)}</span></p>}
        </div>
      )}

      <div className={`space-y-1 transition-all duration-200 ${isOptionsOpen ? 'filter blur-[2px] opacity-35 pointer-events-none select-none' : ''}`}>
        <label className="text-[10px] uppercase font-semibold text-slate-500 dark:text-slate-400 tracking-wider">Strategy</label>
        <div className="grid grid-cols-2 gap-2">
          {['fallback', 'round_robin'].map(s => (
            <button key={s} onClick={() => setStrategy(s)}
              className={`p-3 rounded-2xl text-left border transition ${strategy === s
                ? (s === 'fallback' ? 'bg-[#ff6b35]/15 border-[#ff6b35]/50' : 'bg-[#00d2ff]/15 border-[#00d2ff]/50')
                : 'bg-slate-100 dark:bg-white/5 border-black/5 dark:border-white/5 hover:border-black/20 dark:hover:border-white/20'}`}
            >
              <div className={`text-xs font-semibold mb-0.5 ${strategy === s ? (s === 'fallback' ? 'text-[#ff6b35]' : 'text-[#00d2ff]') : 'text-slate-700 dark:text-slate-300'}`}>
                {s === 'fallback' ? '⬇ Fallback' : '↻ Round Robin'}
              </div>
              <p className="text-[10px] text-slate-500 dark:text-slate-400">
                {s === 'fallback' ? 'Try models in order. First success wins.' : 'Rotate evenly across all models.'}
              </p>
            </button>
          ))}
        </div>
      </div>

      <div className="space-y-2.5">
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <label className="text-[11px] uppercase font-bold text-slate-500 dark:text-slate-400 tracking-wider">
            Models <span className="normal-case text-slate-400">({models.length}){strategy === 'fallback' ? ' — first = primary' : ''}</span>
          </label>

          {models.length > 1 && (
            <div className="flex items-center gap-1.5">
              {showSortWarning ? (
                <div className="flex items-center gap-1.5 px-2 py-0.5 rounded-lg bg-amber-500/10 border border-amber-500/40 text-[10px] animate-fade-in shadow-sm">
                  <AlertCircle className="w-3 h-3 text-amber-500 shrink-0" />
                  <span className="text-amber-500 font-semibold text-[9.5px]">Breaks current order. Proceed?</span>
                  <button
                    type="button"
                    onClick={handleSortByLatency}
                    className="px-2 py-0.5 rounded bg-amber-500 hover:bg-amber-600 text-white font-bold text-[9px] transition ml-1"
                  >
                    Arrange
                  </button>
                  <button
                    type="button"
                    onClick={() => setShowSortWarning(false)}
                    className="px-1.5 py-0.5 rounded text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 text-[9px]"
                  >
                    Cancel
                  </button>
                </div>
              ) : (
                <div className="flex items-center gap-1.5">
                  {previousOrder && (
                    <button
                      type="button"
                      onClick={handleUndoSort}
                      className="px-2 py-0.5 rounded-lg border border-[#00d2ff]/30 bg-[#00d2ff]/10 hover:bg-[#00d2ff]/20 text-[#00d2ff] text-[9.5px] font-semibold transition flex items-center gap-1"
                      title="Revert to previous custom order"
                    >
                      <RefreshCw className="w-2.5 h-2.5" />
                      <span>Undo</span>
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={() => setShowSortWarning(true)}
                    className="flex items-center gap-1 px-2 py-0.5 rounded-lg border border-black/10 dark:border-white/10 hover:border-[#00d2ff]/40 bg-slate-100 dark:bg-white/[0.04] hover:bg-[#00d2ff]/10 text-slate-600 dark:text-slate-400 hover:text-[#00d2ff] text-[10px] font-semibold transition"
                    title="Arrange models by latency (lowest to highest)"
                  >
                    <Clock className="w-3 h-3 text-[#00d2ff]" />
                    <span>Order by Latency</span>
                  </button>
                </div>
              )}
            </div>
          )}
        </div>

        <div className="space-y-1.5 relative z-30">
          <div className="flex items-center gap-1 overflow-x-auto pb-0.5 scrollbar-none">
            <span className="text-[9px] uppercase font-bold text-slate-400 dark:text-slate-500 mr-0.5 shrink-0 tracking-wider">Type:</span>
            {TASK_FILTERS.map(tf => {
              const Icon = tf.icon;
              const count = getTaskCount(tf.id);
              const active = taskFilter === tf.id;
              return (
                <button
                  key={tf.id}
                  type="button"
                  onClick={() => {
                    setTaskFilter(tf.id);
                    setFocused(true);
                  }}
                  className={`flex items-center gap-1 px-2 py-0.5 rounded-lg text-[9.5px] font-semibold border transition whitespace-nowrap shrink-0 ${active
                    ? 'bg-[#00d2ff]/15 border-[#00d2ff]/60 text-[#00d2ff] shadow-[0_0_8px_rgba(0,210,255,0.2)]'
                    : 'bg-slate-100 dark:bg-white/[0.04] border-black/5 dark:border-white/5 text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white hover:border-black/20 dark:hover:border-white/20'
                    }`}
                >
                  {Icon && <Icon className="w-2.5 h-2.5" />}
                  <span>{tf.label}</span>
                  <span className={`text-[8.5px] px-1 py-0.1 rounded-full font-mono ${active ? 'bg-[#00d2ff]/25 text-[#00d2ff]' : 'bg-black/5 dark:bg-white/5 text-slate-400'}`}>
                    {count}
                  </span>
                </button>
              );
            })}
          </div>

          <div className="flex items-center gap-1 overflow-x-auto pb-0.5 scrollbar-none">
            <span className="text-[9px] uppercase font-bold text-slate-400 dark:text-slate-500 mr-0.5 shrink-0 tracking-wider">Provider:</span>
            {availableProviders.map(p => {
              const count = getProviderCount(p);
              const active = providerFilter === p;
              return (
                <button
                  key={p}
                  type="button"
                  onClick={() => {
                    setProviderFilter(p);
                    setFocused(true);
                  }}
                  className={`flex items-center gap-1 px-2 py-0.5 rounded-lg text-[9.5px] font-semibold border transition whitespace-nowrap shrink-0 ${active
                    ? 'bg-[#ff6b35]/15 border-[#ff6b35]/60 text-[#ff6b35] shadow-[0_0_8px_rgba(255,107,53,0.2)]'
                    : 'bg-slate-100 dark:bg-white/[0.04] border-black/5 dark:border-white/5 text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white hover:border-black/20 dark:hover:border-white/20'
                    }`}
                >
                  {p !== 'ALL' && <ProviderIcon provider={p} className="h-2.5 w-auto max-w-[28px] max-h-2.5 shrink-0" />}
                  {p === 'ALL' && <span>All Providers</span>}
                  <span className={`text-[8.5px] px-1 py-0.1 rounded-full font-mono ${active ? 'bg-[#ff6b35]/25 text-[#ff6b35]' : 'bg-black/5 dark:bg-white/5 text-slate-400'}`}>
                    {count}
                  </span>
                </button>
              );
            })}
          </div>
        </div>

        <div className="relative z-30">
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-xl bg-slate-100 dark:bg-black/60 border border-black/10 dark:border-white/10 focus-within:border-[#00d2ff]/60 shadow-sm transition">
            <Search className="w-3.5 h-3.5 text-slate-400 shrink-0" />
            <input
              type="text"
              value={search}
              onChange={e => setSearch(e.target.value)}
              onFocus={() => setFocused(true)}
              onBlur={() => setTimeout(() => setFocused(false), 200)}
              placeholder={
                taskFilter !== 'ALL' && providerFilter !== 'ALL'
                  ? `Filter ${providerFilter} ${taskFilter} models...`
                  : taskFilter !== 'ALL'
                    ? `Filter ${taskFilter} models...`
                    : providerFilter !== 'ALL'
                      ? `Filter ${providerFilter} models...`
                      : 'Search and add a model...'
              }
              className="flex-1 bg-transparent text-xs font-mono text-slate-800 dark:text-slate-200 focus:outline-none placeholder:text-slate-400"
            />
            {(search || taskFilter !== 'ALL' || providerFilter !== 'ALL') && (
              <button
                type="button"
                onMouseDown={(e) => {
                  e.preventDefault();
                  setSearch('');
                  setTaskFilter('ALL');
                  setProviderFilter('ALL');
                }}
                className="text-slate-400 hover:text-slate-600 dark:hover:text-white p-0.5 rounded"
                title="Clear search and filters"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            )}
          </div>

          {isOptionsOpen && (
            <div className="absolute left-0 right-0 z-30 mt-1 rounded-2xl bg-white/95 dark:bg-[#0f1117]/95 backdrop-blur-md border border-black/10 dark:border-white/10 shadow-2xl max-h-60 sm:max-h-72 overflow-y-auto divide-y divide-black/5 dark:divide-white/5">
              {filtered.length === 0 ? (
                <div className="p-3 text-center text-xs text-slate-400 font-mono">
                  No models found matching criteria.
                </div>
              ) : (
                filtered.map(m => (
                  <button key={m.id} onMouseDown={() => addModel(m.id)}
                    className="w-full flex items-center justify-between gap-2 px-2.5 sm:px-3 py-1.5 text-xs font-mono text-slate-700 dark:text-slate-300 hover:bg-[#00d2ff]/10 hover:text-[#00d2ff] transition group text-left overflow-hidden"
                  >
                    <div className="flex items-center gap-1.5 sm:gap-2 truncate min-w-0 flex-1">
                      <ModelIcon model={m.id} provider={m.provider} className="h-3 w-auto max-w-[34px] sm:max-w-[40px] max-h-3 shrink-0" />
                      <span className="truncate min-w-0">{m.id}</span>
                      <div className="hidden sm:flex items-center gap-1 shrink-0 ml-1">
                        {matchesTask(m, 'tools') && (
                          <span className="text-[7.5px] font-bold px-1 py-0.2 rounded bg-sky-500/15 text-sky-400 border border-sky-500/30">TOOLS</span>
                        )}
                        {matchesTask(m, 'coding') && (
                          <span className="text-[7.5px] font-bold px-1 py-0.2 rounded bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">CODE</span>
                        )}
                        {matchesTask(m, 'reasoning') && (
                          <span className="text-[7.5px] font-bold px-1 py-0.2 rounded bg-purple-500/15 text-purple-400 border border-purple-500/30">REASON</span>
                        )}
                        {matchesTask(m, 'vision') && (
                          <span className="text-[7.5px] font-bold px-1 py-0.2 rounded bg-amber-500/15 text-amber-400 border border-amber-500/30">VISION</span>
                        )}
                      </div>
                    </div>
                    <div className="flex items-center gap-1.5 shrink-0 ml-1 sm:ml-2 font-sans">
                      {!m.healthy && (
                        <span className="text-[8.5px] font-mono text-rose-400 font-bold bg-rose-500/15 px-1 py-0.2 rounded">! Unavail</span>
                      )}
                      {m.healthy && m.latency > maxLatencyThreshold && (
                        <span className="text-[8.5px] font-mono text-amber-400 font-bold bg-amber-500/15 px-1 py-0.2 rounded">? {m.latency}s</span>
                      )}
                      {m.healthy && m.latency <= maxLatencyThreshold && (
                        <span className="text-[8.5px] font-mono text-emerald-400/80">{m.latency}s</span>
                      )}

                      <span className="text-[8.5px] font-bold text-[#00d2ff] opacity-0 group-hover:opacity-100 transition ml-1 shrink-0">+ Add</span>
                    </div>
                  </button>
                ))
              )}
            </div>
          )}
        </div>

        {models.length > 0 && (
          <div
            className={`space-y-1 max-h-64 sm:max-h-72 overflow-y-auto pr-1 transition-all duration-200 ${isOptionsOpen ? 'filter blur-[2px] opacity-35 pointer-events-none select-none' : ''
              }`}
            onDragOver={(e) => e.preventDefault()}
            onDragLeave={(e) => {
              if (!e.currentTarget.contains(e.relatedTarget)) {
                setDragOverIndex(null);
              }
            }}
          >
            {models.map((id, i) => {
              const m = allModels.find(x => x.id === id || x.id.toLowerCase() === id.toLowerCase());
              const isUnavailable = !m || !m.healthy;
              const isHighLatency = m && m.healthy && m.latency > maxLatencyThreshold;
              const isDragging = draggedIndex === i;
              const isDragOver = dragOverIndex === i && draggedIndex !== null && draggedIndex !== i;

              return (
                <div
                  key={id}
                  draggable
                  onDragStart={(e) => handleDragStart(e, i)}
                  onDragOver={(e) => handleDragOver(e, i)}
                  onDrop={(e) => handleDrop(e, i)}
                  onDragEnd={handleDragEnd}
                  className={`w-full flex items-center justify-between gap-1.5 sm:gap-2 px-2.5 sm:px-3 py-1.5 sm:py-2 rounded-xl border transition-all select-none cursor-grab active:cursor-grabbing overflow-hidden ${isDragging
                      ? 'opacity-40 border-dashed border-slate-400 dark:border-slate-500 bg-slate-200/50 dark:bg-white/[0.02]'
                      : isDragOver
                        ? 'border-[#00d2ff] bg-[#00d2ff]/15 dark:bg-[#00d2ff]/20 ring-1 ring-[#00d2ff]/50 shadow-[0_0_10px_rgba(0,210,255,0.25)]'
                        : 'bg-slate-100/80 dark:bg-white/[0.04] border-black/5 dark:border-white/5 hover:border-black/20 dark:hover:border-white/20'
                    }`}
                >
                  <div className="flex items-center gap-1.5 sm:gap-2 min-w-0 flex-1">
                    <div className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 shrink-0" title="Drag to reorder">
                      <GripVertical className="w-3.5 h-3.5" />
                    </div>
                    {strategy === 'fallback' && (
                      <span className={`text-[8.5px] sm:text-[9.5px] font-bold shrink-0 w-11 sm:w-13 text-center ${i === 0 ? 'text-[#ff6b35]' : 'text-slate-400'}`}>
                        {i === 0 ? 'PRIMARY' : `FB ${i}`}
                      </span>
                    )}
                    <ModelIcon model={id} provider={m?.provider} className="h-3.5 sm:h-4 w-auto max-w-[34px] sm:max-w-[42px] max-h-3.5 sm:max-h-4 shrink-0" />
                    <span className="text-xs sm:text-sm font-mono font-medium truncate min-w-0 flex-1 text-slate-800 dark:text-slate-200" title={id}>
                      {id}
                    </span>
                  </div>

                  <div className="flex items-center gap-1 sm:gap-2 shrink-0 ml-1 sm:ml-2">
                    {isUnavailable ? (
                      <span
                        className="inline-flex items-center gap-0.5 sm:gap-1 px-1.5 py-0.5 rounded bg-rose-500/20 border border-rose-500/40 text-rose-500 dark:text-rose-400 text-[8px] sm:text-[9px] font-bold font-mono shrink-0 animate-pulse"
                        title="Model unavailable after background probing"
                      >
                        ! <span className="hidden sm:inline">Unavailable</span><span className="sm:hidden">Unavail</span>
                      </span>
                    ) : isHighLatency ? (
                      <span
                        className="inline-flex items-center gap-0.5 sm:gap-1 px-1.5 py-0.5 rounded bg-amber-500/20 border border-amber-500/40 text-amber-500 dark:text-amber-400 text-[8px] sm:text-[9px] font-bold font-mono shrink-0"
                        title={`High latency: ${m.latency}s > ${maxLatencyThreshold}s`}
                      >
                        ? {m.latency}s
                      </span>
                    ) : m ? (
                      <span className="text-[8px] sm:text-[9px] font-mono text-emerald-400/90 shrink-0">
                        {m.latency}s
                      </span>
                    ) : null}

                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        removeModel(id);
                      }}
                      className="text-slate-400 hover:text-rose-400 transition shrink-0 p-0.5 rounded hover:bg-black/5 dark:hover:bg-white/5"
                      title="Remove model"
                    >
                      <X className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {error && <p className="text-xs text-rose-400">{error}</p>}

      <div className={`flex items-center justify-between pt-2 border-t border-black/10 dark:border-white/10 transition-all duration-200 ${isOptionsOpen ? 'filter blur-[2px] opacity-35 pointer-events-none select-none' : ''
        }`}>
        {!isNew ? (
          <button
            type="button"
            onClick={handleDeleteCombo}
            disabled={saving}
            className="px-3 py-1.5 rounded-xl text-xs font-semibold text-rose-500 hover:bg-rose-500/10 transition disabled:opacity-50 flex items-center gap-1.5"
          >
            <Trash2 className="w-3.5 h-3.5" />
            <span>Delete Combo</span>
          </button>
        ) : <div />}
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={onCancel}
            className="px-4 py-1.5 rounded-xl text-xs text-slate-500 hover:text-slate-800 dark:hover:text-white transition"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleSave}
            disabled={saving}
            className="px-5 py-1.5 rounded-xl bg-[#00d2ff] hover:bg-[#3a7bd5] text-slate-900 font-bold text-xs transition disabled:opacity-50 shadow-md"
          >
            {saving ? 'Saving...' : isNew ? 'Create Combo' : 'Save Changes'}
          </button>
        </div>
      </div>
    </div>
  );
}

export function ComboEditorModal({ combo, isNew, stats, onClose, onCombosUpdated }) {
  const allModels = stats?.models || [];
  const maxLatencyThreshold = stats?.max_latency_threshold || 3.0;

  return (
    <ModalWrapper
      title={isNew ? "Create Routing Combo" : `Combo Settings: ${combo?.name || ''}`}
      icon={isNew ? Plus : Sliders}
      onClose={onClose}
      maxWidth="max-w-4xl sm:max-w-[940px]"
    >
      <ComboEditor
        combo={combo}
        isNew={isNew}
        allModels={allModels}
        maxLatencyThreshold={maxLatencyThreshold}
        onSave={() => {
          if (onCombosUpdated) onCombosUpdated();
          onClose();
        }}
        onCancel={onClose}
      />
    </ModalWrapper>
  );
}

export function CombosModal({ stats, onClose, onCombosUpdated }) {
  const [combos, setCombos] = useState(stats?.combos || []);
  const [editing, setEditing] = useState(null);
  const [deleting, setDeleting] = useState(null);

  const allModels = stats?.models || [];
  const maxLatencyThreshold = stats?.max_latency_threshold || 3.0;

  const refresh = async () => {
    try {
      const res = await authFetch('/api/combos');
      const data = await res.json();
      setCombos(data.combos || []);
      if (onCombosUpdated) onCombosUpdated();
    } catch (e) {
      console.error('Failed to refresh combos:', e);
    }
  };

  const handleDelete = async (name) => {
    try {
      await authFetch(`/api/combos/${name}`, { method: 'DELETE' });
      setDeleting(null);
      await refresh();
    } catch (e) {
      console.error('Failed to delete combo:', e);
    }
  };

  if (editing === 'new') {
    return (
      <ModalWrapper title="Create Combo" icon={Plus} onClose={onClose} maxWidth="max-w-4xl sm:max-w-[940px]">
        <ComboEditor isNew allModels={allModels} maxLatencyThreshold={maxLatencyThreshold} onSave={async () => { await refresh(); setEditing(null); }} onCancel={() => setEditing(null)} />
      </ModalWrapper>
    );
  }

  if (editing) {
    return (
      <ModalWrapper title={`Edit: ${editing.name}`} icon={Sliders} onClose={onClose} maxWidth="max-w-4xl sm:max-w-[940px]">
        <ComboEditor combo={editing} allModels={allModels} maxLatencyThreshold={maxLatencyThreshold} onSave={async () => { await refresh(); setEditing(null); }} onCancel={() => setEditing(null)} />
      </ModalWrapper>
    );
  }

  return (
    <ModalWrapper title="Routing Combos" icon={Activity} onClose={onClose} maxWidth="max-w-4xl sm:max-w-[940px]">
      <p className="text-xs text-slate-500 dark:text-slate-400">
        Create named routing groups. Use the combo name as the <code className="text-[#00d2ff]">model</code> field in your API calls. All combos fall back to <span className="text-[#00f5a0] font-semibold">nim-auto</span> if all models fail.
      </p>

      <div className="space-y-2">
        {combos.length === 0 && (
          <div className="text-center py-8 text-xs text-slate-400">No combos yet. Create one below.</div>
        )}
        {combos.map(c => {
          const strat = STRATEGY_LABELS[c.strategy] || STRATEGY_LABELS.fallback;
          return (
            <div key={c.name} className="flex items-center gap-3 p-3 rounded-2xl bg-slate-100 dark:bg-white/[0.03] border border-black/5 dark:border-white/5">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1 flex-wrap">
                  <code className="text-xs font-mono font-semibold text-slate-800 dark:text-slate-200">{c.name}</code>
                  <span className={`text-[9px] font-semibold px-1.5 py-0.5 rounded border ${strat.bg} ${strat.color}`}>{strat.label}</span>

                  {c.has_unavailable && (
                    <span
                      className="inline-flex items-center justify-center w-4 h-4 rounded bg-rose-500/20 border border-rose-500/50 text-rose-500 dark:text-rose-400 font-black text-[11px] font-mono shadow-[0_0_8px_rgba(244,63,94,0.4)] animate-pulse cursor-help shrink-0"
                      title={`⚠️ Unavailable model(s) after probing (${c.unavailable_models?.length}): ${c.unavailable_models?.join(', ')}`}
                    >
                      !
                    </span>
                  )}
                  {c.has_high_latency && (
                    <span
                      className="inline-flex items-center justify-center w-4 h-4 rounded bg-amber-500/20 border border-amber-500/50 text-amber-500 dark:text-amber-400 font-black text-[11px] font-mono shadow-[0_0_8px_rgba(245,158,11,0.35)] cursor-help shrink-0"
                      title={`⏱️ High latency model(s) >${maxLatencyThreshold}s (${c.high_latency_models?.length}): ${c.high_latency_models?.map(m => `${m.id} (${m.latency}s)`).join(', ')}`}
                    >
                      ?
                    </span>
                  )}
                </div>
                <div className="flex flex-wrap gap-1">
                  {c.models.slice(0, 4).map((m, i) => {
                    const isUnavail = c.unavailable_models?.includes(m);
                    const isHighLat = c.high_latency_models?.some(h => h.id === m);
                    return (
                      <span
                        key={m}
                        className={`text-[9px] font-mono px-1.5 py-0.5 rounded flex items-center gap-1 ${isUnavail
                          ? 'bg-rose-500/20 text-rose-400 border border-rose-500/40 font-semibold'
                          : isHighLat
                            ? 'bg-amber-500/20 text-amber-400 border border-amber-500/40 font-semibold'
                            : i === 0 && c.strategy === 'fallback'
                              ? 'bg-[#ff6b35]/15 text-[#ff6b35]'
                              : 'bg-slate-200 dark:bg-white/10 text-slate-600 dark:text-slate-400'
                          }`}
                        title={isUnavail ? 'Unavailable after background probing' : isHighLat ? `High latency (>${maxLatencyThreshold}s)` : m}
                      >
                        {isUnavail && <span className="text-rose-400 font-black">!</span>}
                        {isHighLat && !isUnavail && <span className="text-amber-400 font-black">?</span>}
                        {m.split('/').pop()}
                      </span>
                    );
                  })}
                  {c.models.length > 4 && <span className="text-[9px] text-slate-400">+{c.models.length - 4} more</span>}
                </div>
              </div>
              <div className="flex items-center gap-1.5 shrink-0">
                <button onClick={() => setEditing(c)} className="p-1.5 rounded-lg bg-slate-200 dark:bg-white/10 text-slate-600 dark:text-slate-300 hover:text-[#00d2ff] transition text-[10px]">Edit</button>
                {deleting === c.name
                  ? <button onClick={() => handleDelete(c.name)} className="px-2 py-1 rounded-lg bg-rose-500 text-white text-[10px] font-semibold">Confirm</button>
                  : <button onClick={() => setDeleting(c.name)} className="p-1.5 rounded-lg bg-slate-200 dark:bg-white/10 text-slate-400 hover:text-rose-400 transition"><Trash2 className="w-3 h-3" /></button>
                }
              </div>
            </div>
          );
        })}
      </div>

      <button
        onClick={() => setEditing('new')}
        className="w-full py-2.5 rounded-2xl border-2 border-dashed border-black/10 dark:border-white/10 text-slate-400 hover:border-[#00d2ff]/50 hover:text-[#00d2ff] transition flex items-center justify-center gap-2 text-xs font-semibold"
      >
        <Plus className="w-3.5 h-3.5" /> New Combo
      </button>
    </ModalWrapper>
  );
}

export function UsageAnalyticsModal({ onClose, onResetGateway }) {
  const [timeRange, setTimeRange] = useState('all');
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [modelSearch, setModelSearch] = useState('');
  const [activeTab, setActiveTab] = useState('overview');
  const [confirmReset, setConfirmReset] = useState(false);
  const [resetting, setResetting] = useState(false);

  const fetchUsage = async () => {
    setLoading(true);
    try {
      const res = await authFetch(`/api/dashboard/usage?time_range=${timeRange}`);
      if (res.ok) {
        const json = await res.json();
        setData(json);
      }
    } catch (e) {
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchUsage();
  }, [timeRange]);

  const handleReset = async () => {
    setResetting(true);
    try {
      const res = await authFetch('/api/dashboard/usage/reset', { method: 'POST' });
      if (res.ok) {
        setConfirmReset(false);
        await fetchUsage();
        if (onResetGateway) onResetGateway();
      }
    } catch (e) {
    } finally {
      setResetting(false);
    }
  };

  const getProviderColor = (p) => {
    const norm = (p || '').toLowerCase();
    if (norm.includes('groq')) return '#f55036';
    if (norm.includes('cerebras')) return '#00f5a0';
    if (norm.includes('nvidia')) return '#76b900';
    if (norm.includes('openrouter')) return '#6366f1';
    if (norm.includes('opencode')) return '#00d2ff';
    if (norm.includes('bai')) return '#ff6b35';
    return '#a855f7';
  };

  const summary = data?.summary || {
    total_requests: 0,
    successful_requests: 0,
    failed_requests: 0,
    success_rate: 100.0,
    total_prompt_tokens: 0,
    total_completion_tokens: 0,
    total_tokens: 0,
    avg_latency_ms: 0.0
  };

  const providers = data?.providers || [];
  const models = data?.models || [];
  const recent = data?.recent_activity || [];

  const filteredModels = models.filter((m) => {
    if (!modelSearch.trim()) return true;
    const q = modelSearch.toLowerCase().trim();
    return m.model.toLowerCase().includes(q) || m.provider.toLowerCase().includes(q);
  });

  return (
    <ModalWrapper title="Usage & Analytics Dashboard" icon={BarChart3} onClose={onClose} maxWidth="max-w-4xl">
      <div className="space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-black/5 dark:border-white/5">
          <div className="flex items-center gap-1.5 p-1 rounded-2xl bg-black/5 dark:bg-white/5 w-fit">
            {[
              { id: 'all', label: 'All Time' },
              { id: '24h', label: 'Past 24h' },
              { id: '7d', label: 'Past 7d' },
              { id: '30d', label: 'Past 30d' }
            ].map((tab) => (
              <button
                key={tab.id}
                onClick={() => setTimeRange(tab.id)}
                className={`px-3 py-1 rounded-xl text-xs font-semibold transition ${timeRange === tab.id
                    ? 'bg-white dark:bg-black/60 text-slate-900 dark:text-white shadow-sm'
                    : 'text-slate-500 hover:text-slate-900 dark:hover:text-white'
                  }`}
              >
                {tab.label}
              </button>
            ))}
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={fetchUsage}
              disabled={loading}
              className="px-2.5 py-1.5 rounded-xl bg-black/5 dark:bg-white/5 text-slate-700 dark:text-slate-300 hover:bg-black/10 dark:hover:bg-white/10 text-xs font-semibold transition flex items-center gap-1.5 disabled:opacity-50"
              title="Refresh Analytics"
            >
              <RefreshCw className={`w-3 h-3 ${loading ? 'animate-spin text-[#00d2ff]' : ''}`} />
              <span>Refresh</span>
            </button>

            {confirmReset ? (
              <div className="flex items-center gap-1">
                <button
                  onClick={handleReset}
                  disabled={resetting}
                  className="px-2.5 py-1.5 rounded-xl bg-rose-500 hover:bg-rose-600 text-white text-xs font-semibold transition shadow-sm disabled:opacity-50"
                >
                  {resetting ? 'Clearing...' : 'Confirm Reset'}
                </button>
                <button
                  onClick={() => setConfirmReset(false)}
                  className="px-2 py-1.5 rounded-xl bg-black/5 dark:bg-white/5 text-slate-500 hover:text-slate-800 dark:hover:text-white text-xs"
                >
                  Cancel
                </button>
              </div>
            ) : (
              <button
                onClick={() => setConfirmReset(true)}
                className="px-2.5 py-1.5 rounded-xl bg-rose-500/10 text-rose-600 dark:text-rose-400 hover:bg-rose-500/20 text-xs font-semibold transition flex items-center gap-1"
                title="Reset all recorded usage metrics"
              >
                <Trash2 className="w-3 h-3" />
                <span>Reset</span>
              </button>
            )}
          </div>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5">
          <div className="p-3.5 rounded-2xl bg-black/[0.03] dark:bg-white/[0.03] border border-black/5 dark:border-white/5 space-y-1">
            <div className="flex items-center justify-between text-[10px] uppercase font-semibold text-slate-500 dark:text-slate-400 tracking-wider">
              <span>Total Requests</span>
              <Activity className="w-3.5 h-3.5 text-[#00d2ff]" />
            </div>
            <div className="text-xl font-black font-mono text-slate-900 dark:text-white tracking-tight">
              {summary.total_requests.toLocaleString()}
            </div>
            <div className="flex items-center gap-1.5 text-[9.5px]">
              <span className={`px-1.5 py-0.2 rounded font-mono font-bold ${summary.success_rate >= 95 ? 'bg-emerald-500/15 text-emerald-500' : 'bg-amber-500/15 text-amber-500'
                }`}>
                {summary.success_rate}% ok
              </span>
              <span className="text-slate-400">({summary.failed_requests} failed)</span>
            </div>
          </div>

          <div className="p-3.5 rounded-2xl bg-black/[0.03] dark:bg-white/[0.03] border border-black/5 dark:border-white/5 space-y-1">
            <div className="flex items-center justify-between text-[10px] uppercase font-semibold text-slate-500 dark:text-slate-400 tracking-wider">
              <span>Total Tokens</span>
              <Zap className="w-3.5 h-3.5 text-[#00f5a0]" />
            </div>
            <div className="text-xl font-black font-mono text-[#00f5a0] tracking-tight">
              {summary.total_tokens.toLocaleString()}
            </div>
            <div className="text-[9.5px] text-slate-500 dark:text-slate-400 font-mono truncate">
              In: {summary.total_prompt_tokens.toLocaleString()} • Out: {summary.total_completion_tokens.toLocaleString()}
            </div>
          </div>

          <div className="p-3.5 rounded-2xl bg-black/[0.03] dark:bg-white/[0.03] border border-black/5 dark:border-white/5 space-y-1">
            <div className="flex items-center justify-between text-[10px] uppercase font-semibold text-slate-500 dark:text-slate-400 tracking-wider">
              <span>Active Providers</span>
              <Server className="w-3.5 h-3.5 text-[#ff6b35]" />
            </div>
            <div className="text-xl font-black font-mono text-slate-900 dark:text-white tracking-tight">
              {providers.length}
            </div>
            <div className="text-[9.5px] text-slate-500 dark:text-slate-400 truncate">
              {providers.length > 0 ? `Top: ${providers[0]?.provider}` : 'No traffic yet'}
            </div>
          </div>

          <div className="p-3.5 rounded-2xl bg-black/[0.03] dark:bg-white/[0.03] border border-black/5 dark:border-white/5 space-y-1">
            <div className="flex items-center justify-between text-[10px] uppercase font-semibold text-slate-500 dark:text-slate-400 tracking-wider">
              <span>Avg Latency</span>
              <Clock className="w-3.5 h-3.5 text-[#a855f7]" />
            </div>
            <div className="text-xl font-black font-mono text-slate-900 dark:text-white tracking-tight">
              {summary.avg_latency_ms ? `${summary.avg_latency_ms}ms` : '--'}
            </div>
            <div className="text-[9.5px] text-slate-500 dark:text-slate-400 truncate">
              {summary.avg_latency_ms ? `${(summary.avg_latency_ms / 1000).toFixed(2)}s per request` : 'Awaiting data'}
            </div>
          </div>
        </div>

        {summary.total_tokens > 0 && providers.length > 0 && (
          <div className="p-3.5 rounded-2xl bg-black/[0.03] dark:bg-white/[0.03] border border-black/5 dark:border-white/5 space-y-2">
            <div className="flex items-center justify-between text-xs font-semibold">
              <span className="text-slate-700 dark:text-slate-300">Provider Token Share</span>
              <span className="text-[10px] font-mono text-slate-400">{summary.total_tokens.toLocaleString()} total tokens</span>
            </div>
            <div className="h-3 w-full rounded-full overflow-hidden flex bg-black/10 dark:bg-white/10 p-0.5">
              {providers.map((p) => {
                if (!p.total_tokens || p.token_percentage <= 0) return null;
                const col = getProviderColor(p.provider);
                return (
                  <div
                    key={p.provider}
                    style={{ width: `${p.token_percentage}%`, backgroundColor: col }}
                    className="h-full first:rounded-l-full last:rounded-r-full transition-all duration-500"
                    title={`${p.provider}: ${p.total_tokens.toLocaleString()} tokens (${p.token_percentage}%)`}
                  />
                );
              })}
            </div>
            <div className="flex flex-wrap items-center gap-3 pt-1">
              {providers.map((p) => {
                const col = getProviderColor(p.provider);
                return (
                  <div key={p.provider} className="flex items-center gap-1.5 text-[10px] font-medium">
                    <span className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: col }} />
                    <span className="text-slate-700 dark:text-slate-300">{p.provider}</span>
                    <span className="font-mono font-bold text-slate-500 dark:text-slate-400">
                      {p.token_percentage}%
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        <div className="flex items-center gap-2 border-b border-black/5 dark:border-white/5 pb-2">
          <button
            onClick={() => setActiveTab('overview')}
            className={`px-3 py-1.5 rounded-xl text-xs font-bold transition ${activeTab === 'overview'
                ? 'bg-[#00d2ff]/15 text-[#00d2ff]'
                : 'text-slate-500 hover:text-slate-900 dark:hover:text-white'
              }`}
          >
            Providers ({providers.length})
          </button>
          <button
            onClick={() => setActiveTab('models')}
            className={`px-3 py-1.5 rounded-xl text-xs font-bold transition ${activeTab === 'models'
                ? 'bg-[#00d2ff]/15 text-[#00d2ff]'
                : 'text-slate-500 hover:text-slate-900 dark:hover:text-white'
              }`}
          >
            Models ({models.length})
          </button>
          <button
            onClick={() => setActiveTab('recent')}
            className={`px-3 py-1.5 rounded-xl text-xs font-bold transition ${activeTab === 'recent'
                ? 'bg-[#00d2ff]/15 text-[#00d2ff]'
                : 'text-slate-500 hover:text-slate-900 dark:hover:text-white'
              }`}
          >
            Recent Activity ({recent.length})
          </button>
        </div>

        {activeTab === 'overview' && (
          <div className="overflow-x-auto rounded-2xl border border-black/5 dark:border-white/5">
            <table className="w-full text-left border-collapse text-xs">
              <thead>
                <tr className="border-b border-black/5 dark:border-white/5 bg-black/[0.02] dark:bg-white/[0.02] text-slate-400 text-[10px] uppercase tracking-wider font-semibold">
                  <th className="p-3">Provider</th>
                  <th className="p-3 text-right">Requests</th>
                  <th className="p-3 text-right">Success</th>
                  <th className="p-3 text-right">Prompt Tokens</th>
                  <th className="p-3 text-right">Comp Tokens</th>
                  <th className="p-3 text-right">Total Tokens</th>
                  <th className="p-3 text-right">Avg Latency</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-black/5 dark:divide-white/5 font-mono">
                {providers.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="p-6 text-center text-slate-400 italic">
                      No usage data recorded for this time range.
                    </td>
                  </tr>
                ) : (
                  providers.map((p) => (
                    <tr key={p.provider} className="hover:bg-black/[0.02] dark:hover:bg-white/[0.02] transition">
                      <td className="p-3 font-sans font-semibold flex items-center gap-2">
                        <ProviderIcon provider={p.provider} className="h-4 w-auto max-w-[32px] max-h-4 shrink-0" />
                        <span className="text-slate-900 dark:text-white">{p.provider}</span>
                      </td>
                      <td className="p-3 text-right text-slate-700 dark:text-slate-300">
                        {p.requests.toLocaleString()}
                      </td>
                      <td className="p-3 text-right">
                        <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${p.success_rate >= 95 ? 'bg-emerald-500/15 text-emerald-400' : 'bg-amber-500/15 text-amber-400'
                          }`}>
                          {p.success_rate}%
                        </span>
                      </td>
                      <td className="p-3 text-right text-slate-500 dark:text-slate-400">
                        {p.prompt_tokens.toLocaleString()}
                      </td>
                      <td className="p-3 text-right text-slate-500 dark:text-slate-400">
                        {p.completion_tokens.toLocaleString()}
                      </td>
                      <td className="p-3 text-right font-bold text-[#00f5a0]">
                        {p.total_tokens.toLocaleString()}
                      </td>
                      <td className="p-3 text-right text-slate-600 dark:text-slate-300">
                        {p.avg_latency_ms}ms
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        )}

        {activeTab === 'models' && (
          <div className="space-y-2.5">
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-xl bg-black/5 dark:bg-white/5 border border-black/5 dark:border-white/5">
              <Search className="w-3.5 h-3.5 text-slate-400 shrink-0" />
              <input
                type="text"
                value={modelSearch}
                onChange={(e) => setModelSearch(e.target.value)}
                placeholder="Filter models by ID or provider..."
                className="w-full bg-transparent text-xs font-mono text-slate-800 dark:text-slate-200 placeholder:text-slate-400 focus:outline-none"
              />
              {modelSearch && (
                <button onClick={() => setModelSearch('')} className="text-slate-400 hover:text-slate-600">
                  <X className="w-3 h-3" />
                </button>
              )}
            </div>

            <div className="overflow-x-auto rounded-2xl border border-black/5 dark:border-white/5 max-h-[350px]">
              <table className="w-full text-left border-collapse text-xs">
                <thead className="sticky top-0 bg-white dark:bg-[#151922] z-10">
                  <tr className="border-b border-black/5 dark:border-white/5 text-slate-400 text-[10px] uppercase tracking-wider font-semibold">
                    <th className="p-3">Model</th>
                    <th className="p-3">Provider</th>
                    <th className="p-3 text-right">Requests</th>
                    <th className="p-3 text-right">Success</th>
                    <th className="p-3 text-right">Prompt</th>
                    <th className="p-3 text-right">Comp</th>
                    <th className="p-3 text-right">Total Tokens</th>
                    <th className="p-3 text-right">Avg Latency</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-black/5 dark:divide-white/5 font-mono">
                  {filteredModels.length === 0 ? (
                    <tr>
                      <td colSpan={8} className="p-6 text-center text-slate-400 italic">
                        {models.length === 0 ? 'No model metrics recorded yet.' : 'No models match search filter.'}
                      </td>
                    </tr>
                  ) : (
                    filteredModels.map((m) => (
                      <tr key={`${m.provider}-${m.model}`} className="hover:bg-black/[0.02] dark:hover:bg-white/[0.02] transition">
                        <td className="p-3 font-semibold text-slate-900 dark:text-white flex items-center gap-2">
                          <ModelIcon model={m.model} className="h-3 w-auto max-w-[24px] max-h-3 shrink-0" />
                          <span className="truncate max-w-[200px]" title={m.model}>{m.model}</span>
                        </td>
                        <td className="p-3 font-sans text-slate-500 dark:text-slate-400">
                          {m.provider}
                        </td>
                        <td className="p-3 text-right text-slate-700 dark:text-slate-300">
                          {m.requests.toLocaleString()}
                        </td>
                        <td className="p-3 text-right">
                          <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${m.success_rate >= 95 ? 'bg-emerald-500/15 text-emerald-400' : 'bg-amber-500/15 text-amber-400'
                            }`}>
                            {m.success_rate}%
                          </span>
                        </td>
                        <td className="p-3 text-right text-slate-500 dark:text-slate-400">
                          {m.prompt_tokens.toLocaleString()}
                        </td>
                        <td className="p-3 text-right text-slate-500 dark:text-slate-400">
                          {m.completion_tokens.toLocaleString()}
                        </td>
                        <td className="p-3 text-right font-bold text-[#00f5a0]">
                          {m.total_tokens.toLocaleString()}
                        </td>
                        <td className="p-3 text-right text-slate-600 dark:text-slate-300">
                          {m.avg_latency_ms}ms
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {activeTab === 'recent' && (
          <div className="overflow-x-auto rounded-2xl border border-black/5 dark:border-white/5 max-h-[350px]">
            <table className="w-full text-left border-collapse text-xs">
              <thead className="sticky top-0 bg-white dark:bg-[#151922] z-10">
                <tr className="border-b border-black/5 dark:border-white/5 text-slate-400 text-[10px] uppercase tracking-wider font-semibold">
                  <th className="p-3">Time</th>
                  <th className="p-3">Provider</th>
                  <th className="p-3">Model</th>
                  <th className="p-3">Type</th>
                  <th className="p-3 text-right">Tokens</th>
                  <th className="p-3 text-right">Latency</th>
                  <th className="p-3 text-right">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-black/5 dark:divide-white/5 font-mono">
                {recent.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="p-6 text-center text-slate-400 italic">
                      No recent activity recorded.
                    </td>
                  </tr>
                ) : (
                  recent.map((r, i) => (
                    <tr key={i} className="hover:bg-black/[0.02] dark:hover:bg-white/[0.02] transition">
                      <td className="p-3 text-slate-400 text-[11px]">
                        {new Date(r.timestamp * 1000).toLocaleTimeString()}
                      </td>
                      <td className="p-3 font-sans font-semibold text-slate-700 dark:text-slate-300">
                        {r.provider}
                      </td>
                      <td className="p-3 text-slate-900 dark:text-white truncate max-w-[180px]" title={r.model}>
                        {r.model}
                      </td>
                      <td className="p-3">
                        <span className={`px-1.5 py-0.5 rounded text-[9px] font-bold ${r.stream ? 'bg-cyan-500/15 text-cyan-400' : 'bg-purple-500/15 text-purple-400'
                          }`}>
                          {r.stream ? 'STREAM' : 'SYNC'}
                        </span>
                      </td>
                      <td className="p-3 text-right font-bold text-[#00f5a0]">
                        {r.total_tokens.toLocaleString()}
                      </td>
                      <td className="p-3 text-right text-slate-500 dark:text-slate-400">
                        {r.latency_ms}ms
                      </td>
                      <td className="p-3 text-right">
                        <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${r.status_code >= 200 && r.status_code < 400
                            ? 'bg-emerald-500/15 text-emerald-400'
                            : 'bg-rose-500/15 text-rose-400'
                          }`}>
                          {r.status_code}
                        </span>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </ModalWrapper>
  );
}
