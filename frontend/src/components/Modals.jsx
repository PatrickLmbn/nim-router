import React, { useState } from 'react';
import { 
  X, Check, Search, Key, Sliders, Terminal, Shield, RefreshCw, Plus, Trash2, Zap, Server, Activity, Copy, CheckCircle, Eye, EyeOff, Edit2, Wrench, Code, Brain, MessageSquare, Layers, Sparkles
} from 'lucide-react';
import { ModelIcon, ProviderIcon, resolveProvider } from './ModelIcon';

export { ModelIcon, ProviderIcon, resolveProvider };

export function ModalWrapper({ title, icon: Icon, onClose, children, maxWidth = "max-w-2xl" }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-fade-in">
      <div className={`relative w-full ${maxWidth} max-h-[90vh] flex flex-col bg-white dark:bg-[#151922] text-slate-800 dark:text-slate-100 rounded-3xl border border-black/10 dark:border-white/10 shadow-neu-light dark:shadow-neu-dark overflow-hidden transition-colors duration-300`}>
        <div className="flex items-center justify-between px-6 py-4 border-b border-black/5 dark:border-white/5">
          <div className="flex items-center gap-3">
            {Icon && <div className="p-2 rounded-xl bg-black/5 dark:bg-white/5 text-[#ff6b35]"><Icon className="w-5 h-5" /></div>}
            <h2 className="text-sm font-semibold tracking-wide uppercase">{title}</h2>
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
              className={`p-3 rounded-2xl cursor-pointer border transition ${
                stats?.primary_model === cat.id 
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
                className={`px-2.5 py-1 text-[11px] font-medium rounded-lg transition whitespace-nowrap ${
                  providerFilter === p 
                    ? 'bg-[#ff6b35] text-white' 
                    : 'bg-slate-100 dark:bg-white/5 text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white'
                }`}
              >
                {p}
              </button>
            ))}
          </div>
        </div>

        <div className="space-y-1.5 max-h-60 overflow-y-auto pr-1">
          {filtered.map(m => (
            <div
              key={m.id}
              onClick={() => { onSelectModel(m.id); onClose(); }}
              className={`flex items-center justify-between p-2.5 rounded-xl cursor-pointer border transition ${
                stats?.primary_model === m.id
                  ? 'bg-[#ff6b35]/15 border-[#ff6b35]/50 text-slate-900 dark:text-white'
                  : 'bg-slate-50 dark:bg-white/[0.03] border-black/5 dark:border-white/5 hover:border-black/20 dark:hover:border-white/20'
              }`}
            >
              <div className="flex items-center gap-2 overflow-hidden">
                <span className="w-1.5 h-1.5 rounded-full bg-[#00f5a0] shrink-0" />
                <ModelIcon model={m.id} provider={m.provider} className="h-3.5 w-auto max-w-[48px] max-h-3.5 shrink-0" />
                <span className="text-xs font-mono truncate text-slate-800 dark:text-slate-200">{m.id}</span>
                <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-200 dark:bg-white/5 text-slate-600 dark:text-slate-400 font-mono shrink-0">{m.provider}</span>
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
      const res = await fetch('/api/keys');
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
      const res = await fetch('/api/keys', {
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
              className={`p-2.5 rounded-2xl text-center transition-all flex flex-col items-center justify-center gap-1.5 border neu-button ${
                isSelected 
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
                className={`text-[9px] px-1.5 py-0.5 rounded-full font-mono ${
                  hasKeys
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
                      className={`flex items-center gap-1.5 px-3 py-1.5 rounded-xl border text-xs font-mono shadow-sm transition ${
                        isEditingThis
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
                        className={`ml-1 p-0.5 rounded transition ${
                          isEditingThis ? 'text-[#ff6b35]' : 'text-slate-400 hover:text-slate-700 dark:hover:text-slate-200'
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

  const handleSave = async () => {
    setSaving(true);
    try {
      const res = await fetch('/api/settings', {
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

  return (
    <ModalWrapper title="Routing & Engine Settings" icon={Sliders} onClose={onClose}>
      <div className="space-y-2">
        <label className="text-xs font-semibold text-slate-700 dark:text-slate-300 uppercase tracking-wider">Routing Strategy</label>
        <div className="grid grid-cols-2 gap-3">
          <div
            onClick={() => setStrategy('fallback')}
            className={`p-3.5 rounded-2xl cursor-pointer border transition ${
              strategy === 'fallback' 
                ? 'bg-[#00d2ff]/15 border-[#00d2ff]/50 text-slate-900 dark:text-white font-semibold' 
                : 'bg-slate-100 dark:bg-white/5 border-black/5 dark:border-white/5 text-slate-600 dark:text-slate-400 hover:border-black/20 dark:hover:border-white/20'
            }`}
          >
            <div className="text-xs font-semibold mb-1">Fallback Mode (Recommended)</div>
            <p className="text-[11px] text-slate-500 dark:text-slate-400">Strict latency & reliability order. Cascades to next candidate on error.</p>
          </div>
          <div
            onClick={() => setStrategy('round_robin')}
            className={`p-3.5 rounded-2xl cursor-pointer border transition ${
              strategy === 'round_robin' 
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

      <div className="flex items-center justify-between pt-4 border-t border-black/10 dark:border-white/10">
        {savedMsg ? <span className="text-xs text-[#00f5a0]">{savedMsg}</span> : <div />}
        <button
          onClick={handleSave}
          disabled={saving}
          className="px-5 py-2 rounded-xl bg-[#00d2ff] hover:bg-[#3a7bd5] text-slate-900 font-bold text-xs transition neu-button"
        >
          {saving ? 'Saving...' : 'Apply Settings'}
        </button>
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
            <span className={`font-semibold ${
              log.level === 'INFO' ? 'text-[#00d2ff]' :
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
  fallback:    { label: 'Fallback',    color: 'text-[#ff6b35]', bg: 'bg-[#ff6b35]/15 border-[#ff6b35]/30' },
};

function ComboEditor({ combo, allModels, onSave, onCancel, isNew, maxLatencyThreshold = 3.0 }) {
  const [name, setName] = useState(combo?.name || '');
  const [strategy, setStrategy] = useState(combo?.strategy || 'fallback');
  const [models, setModels] = useState(combo?.models || []);
  const [search, setSearch] = useState('');
  const [focused, setFocused] = useState(false);
  const [taskFilter, setTaskFilter] = useState('ALL');
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

  const getTaskCount = (task) => {
    return allModels.filter(m => matchesTask(m, task) && !models.includes(m.id)).length;
  };

  const filtered = allModels.filter(m =>
    matchesTask(m, taskFilter) &&
    m.id.toLowerCase().includes(search.toLowerCase()) &&
    !models.includes(m.id)
  );

  const addModel = (id) => {
    setModels(prev => [...prev, id]);
    setSearch('');
  };

  const removeModel = (id) => setModels(prev => prev.filter(m => m !== id));
  const moveUp = (i) => { if (i === 0) return; const a = [...models]; [a[i-1], a[i]] = [a[i], a[i-1]]; setModels(a); };

  const handleSave = async () => {
    const finalName = isNew ? slugify(name) : combo.name;
    if (!finalName) { setError('Name is required.'); return; }
    if (models.length === 0) { setError('Add at least one model.'); return; }
    setSaving(true); setError('');
    try {
      const url = isNew ? '/api/combos' : `/api/combos/${combo.name}`;
      const method = isNew ? 'POST' : 'PUT';
      const res = await fetch(url, {
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
      const res = await fetch(`/api/combos/${combo.name}`, { method: 'DELETE' });
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

  return (
    <div className="space-y-4">
      {isNew && (
        <div className="space-y-1">
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

      <div className="space-y-1">
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

      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <label className="text-[10px] uppercase font-semibold text-slate-500 dark:text-slate-400 tracking-wider">
            Models <span className="normal-case text-slate-400">({models.length}){strategy === 'fallback' ? ' — first = primary' : ''}</span>
          </label>
        </div>

        {models.length > 0 && (
          <div className="space-y-1 max-h-40 overflow-y-auto pr-1">
            {models.map((id, i) => {
              const m = allModels.find(x => x.id === id || x.id.toLowerCase() === id.toLowerCase());
              const isUnavailable = !m || !m.healthy;
              const isHighLatency = m && m.healthy && m.latency > maxLatencyThreshold;

              return (
                <div key={id} className="flex items-center gap-2 px-2.5 py-1.5 rounded-xl bg-slate-100 dark:bg-white/5 border border-black/5 dark:border-white/5">
                  {strategy === 'fallback' && (
                    <span className={`text-[9px] font-bold shrink-0 w-12 ${i === 0 ? 'text-[#ff6b35]' : 'text-slate-400'}`}>
                      {i === 0 ? 'PRIMARY' : `FB ${i}`}
                    </span>
                  )}
                  <ModelIcon model={id} provider={m?.provider} className="h-3 w-auto max-w-[42px] max-h-3 shrink-0" />
                  <span className="text-[10px] font-mono flex-1 truncate text-slate-800 dark:text-slate-200">{id}</span>

                  {isUnavailable ? (
                    <span
                      className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-rose-500/20 border border-rose-500/40 text-rose-500 dark:text-rose-400 text-[9px] font-bold font-mono shrink-0 animate-pulse"
                      title="Model unavailable after background probing"
                    >
                      ! Unavailable
                    </span>
                  ) : isHighLatency ? (
                    <span
                      className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-amber-500/20 border border-amber-500/40 text-amber-500 dark:text-amber-400 text-[9px] font-bold font-mono shrink-0"
                      title={`High latency: ${m.latency}s > ${maxLatencyThreshold}s`}
                    >
                      ? {m.latency}s
                    </span>
                  ) : m ? (
                    <span className="text-[9px] font-mono text-emerald-400/90 shrink-0">
                      {m.latency}s
                    </span>
                  ) : null}

                  <span className="text-[9px] text-slate-400 shrink-0">{m?.provider || ''}</span>
                  {strategy === 'fallback' && i > 0 && (
                    <button onClick={() => moveUp(i)} className="text-slate-400 hover:text-[#00d2ff] transition shrink-0 text-[10px]" title="Move up">↑</button>
                  )}
                  <button onClick={() => removeModel(id)} className="text-slate-400 hover:text-rose-400 transition shrink-0">
                    <X className="w-3 h-3" />
                  </button>
                </div>
              );
            })}
          </div>
        )}

        <div className="flex items-center gap-1.5 overflow-x-auto pb-1 scrollbar-none">
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
                className={`flex items-center gap-1 px-2.5 py-1 rounded-xl text-[10px] font-semibold border transition whitespace-nowrap shrink-0 ${
                  active
                    ? 'bg-[#00d2ff]/15 border-[#00d2ff]/60 text-[#00d2ff] shadow-[0_0_10px_rgba(0,210,255,0.2)]'
                    : 'bg-slate-100 dark:bg-white/[0.04] border-black/5 dark:border-white/5 text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white hover:border-black/20 dark:hover:border-white/20'
                }`}
              >
                {Icon && <Icon className="w-3 h-3" />}
                <span>{tf.label}</span>
                <span className={`text-[9px] px-1.5 py-0.2 rounded-full font-mono ${
                  active ? 'bg-[#00d2ff]/25 text-[#00d2ff]' : 'bg-black/5 dark:bg-white/5 text-slate-400'
                }`}>
                  {count}
                </span>
              </button>
            );
          })}
        </div>

        <div className="relative">
          <div className="flex items-center gap-2 px-2.5 py-1.5 rounded-xl bg-slate-100 dark:bg-black/40 border border-black/10 dark:border-white/10">
            <Search className="w-3 h-3 text-slate-400 shrink-0" />
            <input
              type="text"
              value={search}
              onChange={e => setSearch(e.target.value)}
              onFocus={() => setFocused(true)}
              onBlur={() => setTimeout(() => setFocused(false), 200)}
              placeholder={taskFilter === 'ALL' ? 'Search and add a model...' : `Filter ${taskFilter} models...`}
              className="flex-1 bg-transparent text-[11px] font-mono text-slate-800 dark:text-slate-200 focus:outline-none placeholder:text-slate-400"
            />
            {search && (
              <button type="button" onClick={() => setSearch('')} className="text-slate-400 hover:text-slate-600 dark:hover:text-white">
                <X className="w-3 h-3" />
              </button>
            )}
          </div>
          {(focused || search.length > 0 || taskFilter !== 'ALL') && (
            <div className="absolute left-0 right-0 z-20 mt-1 rounded-xl bg-white dark:bg-[#0f1117] border border-black/10 dark:border-white/10 shadow-xl max-h-60 sm:max-h-64 overflow-y-auto divide-y divide-black/5 dark:divide-white/5">
              {filtered.length === 0 ? (
                <div className="p-3 text-center text-xs text-slate-400 font-mono">
                  No models found matching criteria.
                </div>
              ) : (
                filtered.map(m => (
                  <button key={m.id} onMouseDown={() => addModel(m.id)}
                    className="w-full flex items-center justify-between px-3 py-2 text-[10px] font-mono text-slate-700 dark:text-slate-300 hover:bg-[#00d2ff]/10 hover:text-[#00d2ff] transition group text-left"
                  >
                    <div className="flex items-center gap-1.5 truncate min-w-0">
                      <ModelIcon model={m.id} provider={m.provider} className="h-3 w-auto max-w-[38px] max-h-3 shrink-0" />
                      <span className="truncate">{m.id}</span>
                      <div className="flex items-center gap-1 shrink-0 ml-1">
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
                    <div className="flex items-center gap-1.5 shrink-0 ml-2 font-sans">
                      {!m.healthy && (
                        <span className="text-[9px] font-mono text-rose-400 font-bold bg-rose-500/15 px-1 py-0.2 rounded">! Unavailable</span>
                      )}
                      {m.healthy && m.latency > maxLatencyThreshold && (
                        <span className="text-[9px] font-mono text-amber-400 font-bold bg-amber-500/15 px-1 py-0.2 rounded">? {m.latency}s</span>
                      )}
                      {m.healthy && m.latency <= maxLatencyThreshold && (
                        <span className="text-[9px] font-mono text-emerald-400/80">{m.latency}s</span>
                      )}
                      <span className="text-[9px] text-slate-400 dark:text-slate-500 group-hover:text-[#00d2ff]/60">{m.provider}</span>
                      <span className="text-[9px] font-bold text-[#00d2ff] opacity-0 group-hover:opacity-100 transition ml-1 shrink-0">+ Add</span>
                    </div>
                  </button>
                ))
              )}
            </div>
          )}
        </div>
      </div>

      {error && <p className="text-xs text-rose-400">{error}</p>}

      <div className="flex items-center justify-between pt-2 border-t border-black/10 dark:border-white/10">
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
      maxWidth="max-w-3xl sm:max-w-[820px]"
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
      const res = await fetch('/api/combos');
      const data = await res.json();
      setCombos(data.combos || []);
      if (onCombosUpdated) onCombosUpdated();
    } catch (e) {
      console.error('Failed to refresh combos:', e);
    }
  };

  const handleDelete = async (name) => {
    try {
      await fetch(`/api/combos/${name}`, { method: 'DELETE' });
      setDeleting(null);
      await refresh();
    } catch (e) {
      console.error('Failed to delete combo:', e);
    }
  };

  if (editing === 'new') {
    return (
      <ModalWrapper title="Create Combo" icon={Plus} onClose={onClose} maxWidth="max-w-3xl sm:max-w-[820px]">
        <ComboEditor isNew allModels={allModels} maxLatencyThreshold={maxLatencyThreshold} onSave={async () => { await refresh(); setEditing(null); }} onCancel={() => setEditing(null)} />
      </ModalWrapper>
    );
  }

  if (editing) {
    return (
      <ModalWrapper title={`Edit: ${editing.name}`} icon={Sliders} onClose={onClose} maxWidth="max-w-3xl sm:max-w-[820px]">
        <ComboEditor combo={editing} allModels={allModels} maxLatencyThreshold={maxLatencyThreshold} onSave={async () => { await refresh(); setEditing(null); }} onCancel={() => setEditing(null)} />
      </ModalWrapper>
    );
  }

  return (
    <ModalWrapper title="Routing Combos" icon={Activity} onClose={onClose} maxWidth="max-w-3xl sm:max-w-[820px]">
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
                        className={`text-[9px] font-mono px-1.5 py-0.5 rounded flex items-center gap-1 ${
                          isUnavail
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
