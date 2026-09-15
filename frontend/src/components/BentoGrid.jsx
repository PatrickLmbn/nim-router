import React, { useState, useEffect, useRef } from 'react';
import { 
  Zap, Activity, ArrowUpRight, Play, RefreshCw, Plus, 
  Gauge, Shield, Terminal, Copy, Check, RotateCcw, CheckCircle2,
  Key, Globe, Sparkles, Server, GitMerge, X, ChevronDown, Radio, Search, Trash2,
  Eye, EyeOff, BarChart3
} from 'lucide-react';
import { ProviderIcon, ModelIcon } from './ModelIcon';

export function BentoGrid({
  stats,
  logs,
  onOpenModelSelector,
  onOpenKeysManager,
  onOpenSettings,
  onOpenLogs,
  onOpenComboEditor,
  onOpenAnalytics,
  onDeleteCombo,
  onRunProbe,
  onRestartGateway,
  probing,
  restarting
}) {
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState(null);
  const [copiedEndpoint, setCopiedEndpoint] = useState(false);
  const [copiedApiKey, setCopiedApiKey] = useState(false);
  const [showApiKey, setShowApiKey] = useState(false);
  const logsContainerRef = useRef(null);

  const isProbingActive = probing || Boolean(stats?.probing_status?.is_probing);
  const [countdown, setCountdown] = useState(null);

  const [comboSearch, setComboSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');

  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(comboSearch);
    }, 250);
    return () => clearTimeout(timer);
  }, [comboSearch]);

  const filteredCombos = (stats?.combos || []).filter((c) => {
    if (!debouncedSearch.trim()) return true;
    const q = debouncedSearch.toLowerCase().trim();
    const matchesName = c.name.toLowerCase().includes(q);
    const matchesStrategy = c.strategy?.toLowerCase().includes(q);
    const matchesModels = (c.models || []).some((m) => m.toLowerCase().includes(q));
    return matchesName || matchesStrategy || matchesModels;
  });

  useEffect(() => {
    if (stats?.probing_status?.next_probe_seconds != null) {
      setCountdown(stats.probing_status.next_probe_seconds);
    }
  }, [stats?.probing_status?.next_probe_seconds]);

  useEffect(() => {
    if (countdown === null || countdown <= 0) return;
    const interval = setInterval(() => {
      setCountdown((prev) => (prev > 0 ? prev - 1 : 0));
    }, 1000);
    return () => clearInterval(interval);
  }, [countdown]);

  useEffect(() => {
    if (logsContainerRef.current) {
      logsContainerRef.current.scrollTop = logsContainerRef.current.scrollHeight;
    }
  }, [logs]);

  const formatMinSec = (totalSeconds) => {
    if (totalSeconds == null || isNaN(totalSeconds)) return '--:--';
    const m = Math.floor(Math.max(0, totalSeconds) / 60);
    const s = Math.floor(Math.max(0, totalSeconds) % 60);
    return `${m}:${s.toString().padStart(2, '0')}`;
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

  const totalInterval = stats?.probing_status?.interval_seconds || 180;
  const progressPercent = countdown != null && totalInterval > 0
    ? Math.max(0, Math.min(100, (countdown / totalInterval) * 100))
    : 100;


  const handleQuickTest = async () => {
    if (testing) return;
    setTesting(true);
    setTestResult(null);
    const t0 = performance.now();
    try {
      const response = await fetch('/v1/chat/completions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          model: stats?.primary_model || 'nim-auto',
          messages: [{ role: 'user', content: 'Reply with exactly: ok' }],
          max_tokens: 32,
          stream: true
        })
      });

      if (!response.ok) {
        const elapsed = parseFloat(((performance.now() - t0) / 1000).toFixed(2));
        setTestResult({ success: false, latency: elapsed, message: `HTTP ${response.status}` });
        return;
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let tokenCount = 0;
      let done = false;

      while (!done) {
        const { value, done: streamDone } = await reader.read();
        done = streamDone;
        if (value) {
          const chunk = decoder.decode(value, { stream: true });
          const lines = chunk.split('\n');
          for (const line of lines) {
            if (!line.startsWith('data:')) continue;
            const raw = line.slice(5).trim();
            if (raw === '[DONE]') break;
            try {
              const parsed = JSON.parse(raw);
              const delta = parsed?.choices?.[0]?.delta?.content;
              if (delta) {
                tokenCount += Math.max(1, Math.ceil(delta.length / 4));
              }
              const usage = parsed?.usage?.completion_tokens;
              if (usage) tokenCount = usage;
            } catch (_) {}
          }
        }
      }

      const elapsed = parseFloat(((performance.now() - t0) / 1000).toFixed(2));
      const measuredTps = elapsed > 0.05 ? Math.round(tokenCount / elapsed) : null;
      setTestResult({
        success: true,
        latency: elapsed,
        tps: measuredTps,
        message: '200 OK • Optimal'
      });
    } catch (e) {
      const elapsed = parseFloat(((performance.now() - t0) / 1000).toFixed(2));
      setTestResult({ success: false, latency: elapsed, message: 'Connection Error' });
    } finally {
      setTesting(false);
    }
  };

  const routerPort = '11435';
  const host = typeof window !== 'undefined' ? window.location.hostname : 'localhost';
  const protocol = typeof window !== 'undefined' ? window.location.protocol : 'http:';
  const endpointUrl = `${protocol}//${host}:${routerPort}/v1`;

  const copyToClipboard = (text, setCopied) => {
    const done = () => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    };
    const fallback = () => {
      const ta = document.createElement('textarea');
      try {
        ta.value = text;
        ta.style.position = 'fixed';
        ta.style.opacity = '0';
        document.body.appendChild(ta);
        ta.focus();
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
        done();
      } catch (_) {
        document.body.removeChild(ta);
      }
    };
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(text).then(done).catch(fallback);
    } else {
      fallback();
    }
  };

  const handleCopyEndpoint = () => copyToClipboard(endpointUrl, setCopiedEndpoint);
  const handleCopyApiKey = () => copyToClipboard('sk-nim-local', setCopiedApiKey);

  return (
    <div className="w-full max-w-7xl mx-auto px-1 sm:px-2 lg:h-full flex flex-col lg:justify-center">
      <div className="rounded-3xl p-2.5 sm:p-4 bg-[#e8edf5] dark:bg-[#12151c]/95 border border-black/5 dark:border-white/10 shadow-neu-light dark:shadow-neu-dark flex flex-col lg:flex-1 lg:min-h-0 lg:max-h-[700px] lg:justify-between gap-3 sm:gap-3.5 lg:gap-0 transition-all duration-300">
        
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-3.5 lg:gap-4 items-stretch lg:flex-1 lg:min-h-0">

          <div className="lg:col-span-5 flex flex-col lg:min-h-0">
            <div className="rounded-3xl p-3 sm:p-3.5 bg-gradient-to-b from-[#ffffff] to-[#e8edf5] dark:from-[#181d28] dark:to-[#121620] border border-black/5 dark:border-white/10 shadow-neu-light dark:shadow-neu-dark flex flex-col justify-start gap-2.5 sm:gap-2.5 relative transition-colors duration-300 lg:flex-1 lg:min-h-0 lg:overflow-y-auto scrollbar-none">
              
              <div className="flex items-center justify-between shrink-0">
                <div className="flex items-center gap-2">
                  <span className="px-2 py-0.5 rounded-lg bg-black/5 dark:bg-white/5 text-[9px] font-mono font-semibold text-[#00d2ff]">
                    FEATURED ROUTE
                  </span>
                </div>
                <div className="flex items-center gap-1.5">
                  <button 
                    onClick={onRunProbe}
                    disabled={isProbingActive}
                    className="flex items-center gap-1 px-2.5 py-1 rounded-xl text-[10px] font-semibold bg-[#ff6b35]/15 text-[#ff6b35] dark:text-[#ff8c42] hover:bg-[#ff6b35]/25 transition disabled:opacity-50 neu-button"
                    title="Probe all active endpoints"
                  >
                    <RefreshCw className={`w-2.5 h-2.5 ${isProbingActive ? 'animate-spin' : ''}`} />
                    <span>{isProbingActive ? 'Probing...' : 'Probe'}</span>
                  </button>
                  <button 
                    onClick={onRestartGateway}
                    disabled={restarting}
                    className="flex items-center gap-1 px-2 py-1 rounded-xl text-[10px] font-semibold bg-slate-200 dark:bg-white/5 text-slate-700 dark:text-slate-300 hover:bg-slate-300 dark:hover:bg-white/10 transition disabled:opacity-50 neu-button"
                    title="Restart Gateway Process"
                  >
                    <RotateCcw className={`w-2.5 h-2.5 ${restarting ? 'animate-spin text-[#00d2ff]' : ''}`} />
                  </button>
                </div>
              </div>

              <div className="p-3 sm:p-3.5 rounded-2xl bg-black/[0.03] dark:bg-white/[0.03] border border-black/5 dark:border-white/5 shadow-neu-light-inset dark:shadow-neu-dark-inset space-y-1.5 shrink-0">
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-1.5">
                    <div className="w-2 h-2 rounded-full bg-[#00f5a0] animate-pulse" />
                    <span className="text-[9px] font-mono uppercase tracking-wider font-semibold text-slate-500 dark:text-slate-400">
                      Active Primary Model
                    </span>
                  </div>

                  <div className="flex items-center gap-1.5">
                    {stats?.usage_summary?.total_tokens > 0 && (
                      <button
                        type="button"
                        onClick={onOpenAnalytics}
                        className="flex items-center gap-1 px-2 py-0.5 rounded-lg bg-[#00f5a0]/15 hover:bg-[#00f5a0]/25 text-[#00f5a0] text-[9px] font-mono font-bold transition neu-button"
                        title="View Usage & Analytics"
                      >
                        <Zap className="w-2.5 h-2.5" />
                        <span>{stats.usage_summary.total_tokens.toLocaleString()} tokens</span>
                      </button>
                    )}

                    {testResult && (
                      <div className="flex items-center gap-1 px-2 py-0.5 rounded-lg bg-black/5 dark:bg-white/10 text-[9px] font-mono animate-fade-in shrink-0">
                        {testResult.success ? (
                          <>
                            <CheckCircle2 className="w-3 h-3 text-[#00f5a0]" />
                            <span className="text-[#00f5a0] font-semibold">{testResult.latency}s</span>
                            {testResult.tps != null && (
                              <span className="text-slate-400">({testResult.tps} tps)</span>
                            )}
                          </>
                        ) : (
                          <span className="text-rose-400 font-semibold truncate max-w-[120px]">{testResult.message}</span>
                        )}
                      </div>
                    )}
                  </div>
                </div>

                <div className="flex flex-wrap sm:flex-nowrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2 min-w-0">
                    <ModelIcon model={stats?.primary_model} className="h-5 w-auto max-w-[65px] max-h-5 shrink-0" />
                    <h3 className="text-lg sm:text-xl font-black text-slate-900 dark:text-white tracking-tight leading-snug truncate">
                      {stats?.primary_model || 'nim-auto'}
                    </h3>
                  </div>

                  <div className="flex items-center gap-2 shrink-0">
                    <button
                      onClick={onOpenModelSelector}
                      className="px-2.5 py-1 rounded-xl bg-slate-900 dark:bg-white text-white dark:text-slate-900 font-bold text-[10px] uppercase tracking-wider flex items-center gap-1 hover:scale-[1.02] transition neu-button shadow-md"
                      title="Change primary model"
                    >
                      <span>Change</span>
                      <ArrowUpRight className="w-3 h-3" />
                    </button>

                    <button
                      onClick={handleQuickTest}
                      disabled={testing}
                      className="px-3 py-1 rounded-xl bg-[#ff6b35] hover:bg-[#ff8c42] text-white font-bold text-[10px] uppercase tracking-wider flex items-center gap-1.5 transition neu-button shadow-glow-orange disabled:opacity-50"
                      title="Test route with active model"
                    >
                      {testing ? (
                        <>
                          <RefreshCw className="w-3 h-3 animate-spin fill-white" />
                          <span>Testing...</span>
                        </>
                      ) : (
                        <>
                          <Play className="w-3 h-3 fill-white" />
                          <span>Test Route</span>
                        </>
                      )}
                    </button>
                  </div>
                </div>

                <p className="text-[10.5px] text-slate-600 dark:text-slate-400 leading-relaxed line-clamp-2">
                  Universal zero-downtime routing across NVIDIA NIM, Groq, Cerebras, OpenRouter, OpenCode, and B.AI with dynamic latency ranking.
                </p>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 shrink-0">
                <div className="flex items-center justify-between p-2 rounded-2xl bg-[#dbe2ee] dark:bg-black/40 shadow-neu-light-inset dark:shadow-neu-dark-inset border border-black/5 dark:border-white/5">
                  <div className="flex items-center gap-1.5 overflow-hidden">
                    <Globe className="w-3.5 h-3.5 text-[#00d2ff] shrink-0" />
                    <div className="truncate">
                      <div className="text-[8px] uppercase font-semibold text-slate-500 dark:text-slate-400">Endpoint URL</div>
                      <div className="text-[10px] font-mono font-semibold text-slate-800 dark:text-slate-200 truncate">{endpointUrl}</div>
                    </div>
                  </div>
                  <button
                    onClick={handleCopyEndpoint}
                    className="p-1 rounded-md bg-black/5 dark:bg-white/10 hover:bg-black/15 text-slate-700 dark:text-slate-300 transition shrink-0 ml-1"
                    title="Copy Endpoint URL"
                  >
                    {copiedEndpoint ? <Check className="w-3 h-3 text-[#00f5a0]" /> : <Copy className="w-3 h-3 text-slate-400" />}
                  </button>
                </div>

                <div className="flex items-center justify-between p-2 rounded-2xl bg-[#dbe2ee] dark:bg-black/40 shadow-neu-light-inset dark:shadow-neu-dark-inset border border-black/5 dark:border-white/5">
                  <div className="flex items-center gap-1.5 overflow-hidden">
                    <Key className="w-3.5 h-3.5 text-[#ff6b35] shrink-0" />
                    <div className="truncate">
                      <div className="text-[8px] uppercase font-semibold text-slate-500 dark:text-slate-400">API Key</div>
                      <div className="text-[10px] font-mono font-semibold text-slate-800 dark:text-slate-200 truncate">
                        {showApiKey ? 'sk-nim-local' : '••••••••••••'}
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-1 shrink-0 ml-1">
                    <button
                      type="button"
                      onClick={() => setShowApiKey(!showApiKey)}
                      className="p-1 rounded-md bg-black/5 dark:bg-white/10 hover:bg-black/15 text-slate-700 dark:text-slate-300 transition"
                      title={showApiKey ? "Hide API Key" : "View API Key"}
                    >
                      {showApiKey ? <EyeOff className="w-3 h-3 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200" /> : <Eye className="w-3 h-3 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200" />}
                    </button>
                    <button
                      type="button"
                      onClick={handleCopyApiKey}
                      className="p-1 rounded-md bg-black/5 dark:bg-white/10 hover:bg-black/15 text-slate-700 dark:text-slate-300 transition"
                      title="Copy API Key"
                    >
                      {copiedApiKey ? <Check className="w-3 h-3 text-[#00f5a0]" /> : <Copy className="w-3 h-3 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200" />}
                    </button>
                  </div>
                </div>
              </div>

              <div className="space-y-1.5 shrink-0">
                <div className="space-y-1">
                  <div className="flex justify-between items-center text-[10px]">
                    <span className="text-slate-500 dark:text-slate-400 font-medium">Healthy Model Pool</span>
                    <span className="font-mono font-semibold text-[#ff6b35] dark:text-[#ff8c42]">
                      {stats?.healthy_pool_size || 0} / {stats?.total_models || 0} ({stats?.total_models ? Math.round(((stats?.healthy_pool_size || 0) / stats.total_models) * 100) : 100}%)
                    </span>
                  </div>
                  <div className="grid grid-cols-10 gap-1 p-1 rounded-xl bg-[#dbe2ee] dark:bg-black/40 shadow-neu-light-inset dark:shadow-neu-dark-inset">
                    {[...Array(10)].map((_, i) => (
                      <div 
                        key={i} 
                        className="h-2 rounded-sm bg-[#ff6b35] shadow-[0_0_8px_rgba(255,107,53,0.6)] transition-all"
                      />
                    ))}
                  </div>
                </div>

                <div className="p-3 rounded-2xl bg-[#dbe2ee]/70 dark:bg-black/40 border border-black/5 dark:border-white/5 shadow-neu-light-inset dark:shadow-neu-dark-inset flex items-center gap-3.5">
                  
                  <div className="relative w-14 h-14 shrink-0 flex items-center justify-center">
                    <svg className="w-14 h-14 -rotate-90 absolute inset-0" viewBox="0 0 36 36">
                      <circle
                        cx="18"
                        cy="18"
                        r="15.9155"
                        fill="none"
                        className="stroke-slate-300 dark:stroke-white/10"
                        strokeWidth="3.2"
                      />
                    </svg>

                    <svg 
                      className={`w-14 h-14 absolute inset-0 ${
                        isProbingActive 
                          ? 'animate-spin' 
                          : '-rotate-90 transition-all duration-1000 ease-linear'
                      }`} 
                      viewBox="0 0 36 36"
                    >
                      <circle
                        cx="18"
                        cy="18"
                        r="15.9155"
                        fill="none"
                        className="stroke-[#00f5a0]"
                        strokeWidth="3.2"
                        strokeDasharray={isProbingActive ? '28, 72' : `${progressPercent}, 100`}
                        strokeLinecap="round"
                      />
                    </svg>

                    <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
                      {isProbingActive ? (
                        <>
                          <RefreshCw className="w-3 h-3 text-[#00f5a0] animate-spin mb-0.5" />
                          <span className="text-[6.5px] font-mono font-bold text-[#00f5a0] tracking-wider uppercase animate-pulse">
                            PROBING
                          </span>
                        </>
                      ) : (
                        <>
                          <span className="text-xs sm:text-[13px] font-mono font-black tracking-tight text-slate-800 dark:text-white leading-none">
                            {formatMinSec(countdown)}
                          </span>
                          <span className="text-[6px] font-mono font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-widest mt-0.5">
                            NEXT SCAN
                          </span>
                        </>
                      )}
                    </div>
                  </div>

                  <div className="flex-1 min-w-0 space-y-2">
                    <div className="flex justify-between items-center text-[10px]">
                      <div className="flex items-center gap-1.5">
                        {isProbingActive ? (
                          <>
                            <Radio className="w-3.5 h-3.5 text-[#00f5a0] animate-pulse" />
                            <span className="font-bold text-[#00f5a0] tracking-wide animate-pulse">
                              PROBING IN BACKGROUND...
                            </span>
                          </>
                        ) : (
                          <span className="font-semibold text-slate-700 dark:text-slate-200">
                            Background Health Prober
                          </span>
                        )}
                      </div>
                      <div className="font-mono text-[9px] text-slate-500 dark:text-slate-400 flex items-center gap-1">
                        <span>Cycle:</span>
                        <span className="font-bold text-slate-800 dark:text-slate-200">
                          {stats?.probing_status?.interval_seconds ? `${Math.round(stats.probing_status.interval_seconds / 60)}m` : '3m'}
                        </span>
                      </div>
                    </div>

                    <div className="flex flex-wrap items-center gap-1.5 pt-0.5">
                      {Object.entries(stats?.providers || {}).map(([name, p]) => {
                        if (!p.active && !p.models_count) return null;
                        const hasModels = (p.models_count || 0) > 0;
                        return (
                          <button 
                            key={name}
                            type="button"
                            onClick={onOpenKeysManager}
                            className="px-2 py-0.5 rounded-lg bg-black/5 dark:bg-white/5 border border-black/5 dark:border-white/5 hover:border-[#ff6b35]/40 flex items-center gap-1.5 text-[9.5px] transition cursor-pointer"
                            title={`${name}: ${p.models_count || 0} models probed & responsive. Click to manage API keys.`}
                          >
                            <span className={`w-1.5 h-1.5 rounded-full ${hasModels ? 'bg-[#00f5a0] shadow-[0_0_4px_#00f5a0]' : 'bg-slate-400'}`} />
                            <ProviderIcon provider={name} className="h-3 w-auto max-w-[42px] max-h-3 shrink-0" />
                            <span className="text-slate-600 dark:text-slate-300 font-medium">{name}</span>
                            <span className="font-mono font-bold text-slate-800 dark:text-slate-200 text-[8px] px-1 bg-black/10 dark:bg-white/10 rounded">
                              {p.models_count || 0}
                            </span>
                          </button>
                        );
                      })}
                    </div>
                  </div>
                </div>
              </div>

              <div className="p-3 sm:p-3.5 rounded-2xl bg-black/[0.03] dark:bg-white/[0.03] border border-black/5 dark:border-white/5 shadow-neu-light-inset dark:shadow-neu-dark-inset flex flex-col justify-between flex-1 min-h-[220px] gap-2">
                <div className="space-y-2 shrink-0">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-1.5">
                      <BarChart3 className="w-3.5 h-3.5 text-[#00f5a0]" />
                      <span className="text-[11px] font-bold text-slate-800 dark:text-slate-200 tracking-tight">
                        Provider Analytics
                      </span>
                      {(stats?.usage_providers?.length > 0) && (
                        <span className="text-[8.5px] font-mono px-1.5 py-0.2 rounded bg-emerald-500/15 text-emerald-500 font-bold">
                          {stats.usage_providers.length} Active
                        </span>
                      )}
                    </div>

                    <div className="flex items-center gap-2">
                      {stats?.usage_summary?.total_tokens > 0 && (
                        <span className="text-[9.5px] font-mono font-bold text-[#00f5a0]">
                          {stats.usage_summary.total_tokens.toLocaleString()} tok
                        </span>
                      )}
                      <button
                        type="button"
                        onClick={onOpenAnalytics}
                        className="text-[9.5px] font-semibold text-[#00d2ff] hover:underline flex items-center gap-0.5 neu-button"
                        title="Open full usage & analytics modal"
                      >
                        <span>Full</span>
                        <ArrowUpRight className="w-3 h-3" />
                      </button>
                    </div>
                  </div>

                  <div className="grid grid-cols-3 gap-1.5">
                    <div className="p-1.5 rounded-xl bg-black/5 dark:bg-white/5 border border-black/5 dark:border-white/5 flex flex-col">
                      <span className="text-[7.5px] uppercase font-semibold text-slate-500 dark:text-slate-400 tracking-wider">
                        Requests
                      </span>
                      <span className="text-xs font-mono font-bold text-slate-800 dark:text-slate-200">
                        {stats?.usage_summary?.total_requests?.toLocaleString() || 0}
                      </span>
                    </div>
                    <div className="p-1.5 rounded-xl bg-black/5 dark:bg-white/5 border border-black/5 dark:border-white/5 flex flex-col">
                      <span className="text-[7.5px] uppercase font-semibold text-slate-500 dark:text-slate-400 tracking-wider">
                        Success
                      </span>
                      <span className="text-xs font-mono font-bold text-emerald-500 dark:text-emerald-400">
                        {stats?.usage_summary?.success_rate != null ? `${stats.usage_summary.success_rate}%` : '100%'}
                      </span>
                    </div>
                    <div className="p-1.5 rounded-xl bg-black/5 dark:bg-white/5 border border-black/5 dark:border-white/5 flex flex-col">
                      <span className="text-[7.5px] uppercase font-semibold text-slate-500 dark:text-slate-400 tracking-wider">
                        Avg Latency
                      </span>
                      <span className="text-xs font-mono font-bold text-[#00d2ff]">
                        {stats?.usage_summary?.avg_latency_ms ? `${(stats.usage_summary.avg_latency_ms / 1000).toFixed(2)}s` : '--'}
                      </span>
                    </div>
                  </div>

                  {stats?.usage_summary?.total_tokens > 0 && stats?.usage_providers?.length > 0 && (
                    <div className="space-y-1">
                      <div className="flex items-center justify-between text-[8px] font-mono text-slate-500 dark:text-slate-400">
                        <span>Token Distribution</span>
                        <span>{stats.usage_summary.total_tokens.toLocaleString()} total</span>
                      </div>
                      <div className="h-1.5 w-full rounded-full overflow-hidden flex bg-black/10 dark:bg-white/10 p-0.5">
                        {stats.usage_providers.map((p) => {
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
                      <div className="flex flex-wrap items-center gap-2 pt-0.5">
                        {stats.usage_providers.map((p) => {
                          const col = getProviderColor(p.provider);
                          return (
                            <div key={p.provider} className="flex items-center gap-1 text-[8px] font-medium">
                              <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ backgroundColor: col }} />
                              <span className="text-slate-600 dark:text-slate-300">{p.provider}</span>
                              <span className="font-mono font-bold text-slate-500 dark:text-slate-400">
                                {p.token_percentage}%
                              </span>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  )}
                </div>

                <div className="overflow-x-auto overflow-y-auto rounded-xl border border-black/5 dark:border-white/5 flex-1 min-h-[80px] scrollbar-none">
                  <table className="w-full text-left border-collapse text-[10px]">
                    <thead className="sticky top-0 bg-[#eef2f7] dark:bg-[#161a22] z-10">
                      <tr className="border-b border-black/5 dark:border-white/5 text-slate-400 text-[8px] uppercase tracking-wider font-semibold">
                        <th className="py-1 px-1.5">Provider</th>
                        <th className="py-1 px-1 text-right">Requests</th>
                        <th className="py-1 px-1 text-right">Success</th>
                        <th className="py-1 px-1 text-right">Prompt</th>
                        <th className="py-1 px-1 text-right">Comp</th>
                        <th className="py-1 px-1 text-right">Total</th>
                        <th className="py-1 px-1.5 text-right">Avg Latency</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-black/5 dark:divide-white/5 font-mono">
                      {(!stats?.usage_providers || stats.usage_providers.length === 0) ? (
                        <tr>
                          <td colSpan={7} className="py-3 px-2 text-center text-slate-400 text-[10px] italic">
                            No requests routed yet.
                          </td>
                        </tr>
                      ) : (
                        stats.usage_providers.map((p) => (
                          <tr key={p.provider} className="hover:bg-black/[0.02] dark:hover:bg-white/[0.02] transition">
                            <td className="py-1 px-1.5 font-sans font-semibold flex items-center gap-1.5 whitespace-nowrap">
                              <ProviderIcon provider={p.provider} className="h-3 w-auto max-w-[26px] max-h-3 shrink-0" />
                              <span className="text-slate-900 dark:text-white text-[10px]">{p.provider}</span>
                            </td>
                            <td className="py-1 px-1 text-right text-slate-700 dark:text-slate-300">
                              {p.requests.toLocaleString()}
                            </td>
                            <td className="py-1 px-1 text-right">
                              <span className={`px-1 py-0.2 rounded text-[8.5px] font-bold ${
                                p.success_rate >= 95 ? 'bg-emerald-500/15 text-emerald-400' : 'bg-amber-500/15 text-amber-400'
                              }`}>
                                {p.success_rate}%
                              </span>
                            </td>
                            <td className="py-1 px-1 text-right text-slate-500 dark:text-slate-400">
                              {p.prompt_tokens.toLocaleString()}
                            </td>
                            <td className="py-1 px-1 text-right text-slate-500 dark:text-slate-400">
                              {p.completion_tokens.toLocaleString()}
                            </td>
                            <td className="py-1 px-1 text-right font-bold text-[#00f5a0]">
                              {p.total_tokens.toLocaleString()}
                            </td>
                            <td className="py-1 px-1.5 text-right text-slate-600 dark:text-slate-300 whitespace-nowrap">
                              {p.avg_latency_ms}ms
                            </td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>

                <div className="flex items-center justify-between pt-1 border-t border-black/5 dark:border-white/5 text-[9.5px] shrink-0">
                  <button
                    type="button"
                    onClick={onOpenSettings}
                    className="flex items-center gap-1 text-slate-500 hover:text-slate-900 dark:hover:text-white transition font-medium"
                    title="Click to tune routing strategy"
                  >
                    <Gauge className="w-3 h-3 text-[#00d2ff]" />
                    <span className="capitalize">{stats?.routing_strategy || 'Fallback'} Mode</span>
                  </button>
                  <div className="flex items-center gap-2 font-mono text-[9px] text-slate-400">
                    <span>Latency: <strong className="text-slate-700 dark:text-slate-200">{stats?.avg_latency != null ? `${stats.avg_latency}s` : '--'}</strong></span>
                    <span>Speed: <strong className="text-slate-700 dark:text-slate-200">{stats?.avg_tps != null ? `${stats.avg_tps} tps` : '--'}</strong></span>
                  </div>
                </div>
              </div>

            </div>
          </div>

          <div className="lg:col-span-7 flex flex-col gap-3.5 lg:gap-4 lg:min-h-0">

            <div className="rounded-3xl p-3.5 sm:p-5 bg-white dark:bg-[#171b24] border border-black/5 dark:border-white/10 shadow-neu-light dark:shadow-neu-dark flex flex-col justify-between transition-colors duration-300 relative group">
              <div>
                <div className="mb-3 space-y-2">
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                    <div className="flex items-center justify-between sm:justify-start gap-2 min-w-0">
                      <div className="flex items-center gap-2 min-w-0">
                        <div className="p-1.5 rounded-xl bg-[#00d2ff]/15 text-[#00d2ff] shadow-[0_0_10px_rgba(0,210,255,0.2)] shrink-0">
                          <GitMerge className="w-4 h-4" />
                        </div>
                        <div className="flex items-center gap-1.5 min-w-0">
                          <h3 className="text-sm sm:text-base font-extrabold text-slate-900 dark:text-white tracking-tight shrink-0">
                            Routing Combos
                          </h3>
                          {(stats?.combos?.length > 0) && (
                            <span className="px-2 py-0.5 rounded-full bg-[#00d2ff]/15 text-[#00d2ff] text-[10px] font-bold shrink-0">
                              {stats.combos.length} Active
                            </span>
                          )}
                        </div>
                      </div>
                      {stats?.combos?.some(c => c.has_unavailable) && (
                        <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md bg-rose-500/15 border border-rose-500/30 text-rose-500 dark:text-rose-400 text-[9px] font-bold animate-pulse shrink-0">
                          <span className="w-1.5 h-1.5 rounded-full bg-rose-500" />
                          <span>Action needed</span>
                        </span>
                      )}
                    </div>

                    <div className="flex items-center gap-2 w-full sm:w-auto">
                      <div className="relative flex-1 sm:w-44 sm:flex-none">
                        <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-xl bg-slate-100 dark:bg-black/40 border border-black/10 dark:border-white/10 focus-within:border-[#00d2ff]/60 transition">
                          <Search className="w-3 h-3 text-slate-400 shrink-0" />
                          <input
                            type="text"
                            value={comboSearch}
                            onChange={(e) => setComboSearch(e.target.value)}
                            placeholder="Search combos..."
                            className="w-full min-w-0 bg-transparent text-[11px] font-mono text-slate-800 dark:text-slate-200 placeholder:text-slate-400 focus:outline-none"
                          />
                          {comboSearch && (
                            <button
                              type="button"
                              onClick={() => setComboSearch('')}
                              className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 p-0.5 shrink-0"
                              title="Clear search"
                            >
                              <X className="w-2.5 h-2.5" />
                            </button>
                          )}
                        </div>
                      </div>

                      <button
                        onClick={() => onOpenComboEditor('new')}
                        className="px-3 py-1 rounded-xl text-xs font-bold bg-[#00d2ff] hover:bg-[#3a7bd5] text-slate-900 transition neu-button flex items-center gap-1 shadow-md shrink-0"
                      >
                        <Plus className="w-3.5 h-3.5" />
                        <span className="hidden sm:inline">New Combo</span>
                        <span className="sm:hidden">New</span>
                      </button>
                    </div>
                  </div>

                  <p className="text-[11px] text-slate-500 dark:text-slate-400 leading-relaxed">
                    Named multi-model routing groups. Use combo name as <code className="text-[#00d2ff] font-mono font-semibold">model</code> in API calls.
                  </p>
                </div>

                {(!stats?.combos || stats.combos.length === 0) ? (
                  <div className="min-h-[160px] lg:h-[235px] flex items-center justify-center">
                    <button
                      onClick={() => onOpenComboEditor('new')}
                      className="w-full h-full rounded-2xl border-2 border-dashed border-black/10 dark:border-white/10 text-slate-400 hover:border-[#00d2ff]/40 hover:text-[#00d2ff] transition flex flex-col items-center justify-center gap-1 text-xs font-semibold p-4"
                    >
                      <Plus className="w-5 h-5 text-[#00d2ff]" />
                      <span className="font-bold">Create your first routing combo</span>
                      <span className="text-[11px] text-slate-400 font-normal text-center">Combine multiple free models with Fallback or Round Robin strategies</span>
                    </button>
                  </div>
                ) : filteredCombos.length === 0 ? (
                  <div className="min-h-[160px] lg:h-[235px] flex items-center justify-center text-xs text-slate-400 font-mono">
                    No combos match "<span className="text-[#00d2ff]">{debouncedSearch}</span>"
                  </div>
                ) : (
                  <div className="space-y-2 max-h-[300px] lg:h-[235px] overflow-y-auto pr-1 sm:pr-1.5">
                    {filteredCombos.map(c => (
                      <div 
                        key={c.name} 
                        onClick={() => onOpenComboEditor(c)}
                        className="flex flex-col p-2.5 sm:p-3 rounded-2xl bg-slate-100 dark:bg-white/[0.03] hover:bg-slate-200/60 dark:hover:bg-white/[0.06] border border-black/5 dark:border-white/5 transition cursor-pointer group gap-1.5"
                        title={`Click to edit settings for ${c.name}`}
                      >
                        <div className="flex items-center justify-between gap-2 min-w-0 w-full">
                          <div className="flex items-center gap-2 min-w-0 flex-1">
                            <span className={`text-[9px] font-bold px-2 py-0.5 rounded-md border shrink-0 ${
                              c.strategy === 'round_robin'
                                ? 'bg-[#00d2ff]/15 border-[#00d2ff]/30 text-[#00d2ff]'
                                : 'bg-[#ff6b35]/15 border-[#ff6b35]/30 text-[#ff6b35]'
                            }`}>
                              {c.strategy === 'round_robin' ? '↻ Round Robin' : '⬇ Fallback'}
                            </span>

                            <code className="text-xs font-mono font-bold text-slate-900 dark:text-slate-100 group-hover:text-[#00d2ff] transition truncate">
                              {c.name}
                            </code>

                            <div className="flex items-center gap-1 shrink-0">
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
                                  title={`⏱️ High latency model(s) >${stats?.max_latency_threshold || 3.0}s (${c.high_latency_models?.length}): ${c.high_latency_models?.map(m => `${m.id} (${m.latency}s)`).join(', ')}`}
                                >
                                  ?
                                </span>
                              )}
                            </div>

                            <div className="hidden sm:flex items-center gap-1 overflow-hidden flex-1">
                              {c.models.slice(0, 3).map((m, i) => {
                                const isUnavail = c.unavailable_models?.includes(m);
                                const isHighLat = c.high_latency_models?.some(h => h.id === m);
                                return (
                                  <span
                                    key={m}
                                    className={`inline-flex items-center gap-1 text-[9px] font-mono px-1.5 py-0.5 rounded truncate max-w-[130px] ${
                                      isUnavail
                                        ? 'bg-rose-500/15 border border-rose-500/30 text-rose-400 font-semibold'
                                        : isHighLat
                                        ? 'bg-amber-500/15 border border-amber-500/30 text-amber-400 font-semibold'
                                        : i === 0 && c.strategy === 'fallback'
                                        ? 'bg-[#ff6b35]/15 text-[#ff6b35]'
                                        : 'bg-slate-200 dark:bg-white/10 text-slate-600 dark:text-slate-400'
                                    }`}
                                    title={m}
                                  >
                                    <ModelIcon model={m} className="h-2.5 w-auto max-w-[28px] max-h-2.5 shrink-0" />
                                    <span className="truncate">{m.split('/').pop()}</span>
                                  </span>
                                );
                              })}
                              {c.models.length > 3 && (
                                <span className="text-[9px] text-slate-400 shrink-0 font-mono">
                                  +{c.models.length - 3} more
                                </span>
                              )}
                            </div>
                          </div>

                          <div className="flex items-center gap-1.5 shrink-0">
                            <span className="text-[10px] font-semibold text-slate-500 dark:text-slate-400 font-mono">
                              {c.models.length} <span className="hidden sm:inline">models</span>
                            </span>
                            <button
                              type="button"
                              onClick={(e) => {
                                e.stopPropagation();
                                if (onDeleteCombo) onDeleteCombo(c.name);
                              }}
                              className="p-1 rounded-lg hover:bg-rose-500/15 text-slate-400 hover:text-rose-500 transition neu-button"
                              title={`Delete combo "${c.name}"`}
                            >
                              <Trash2 className="w-3.5 h-3.5" />
                            </button>
                            <button
                              type="button"
                              onClick={(e) => {
                                e.stopPropagation();
                                onOpenComboEditor(c);
                              }}
                              className="p-1 rounded-lg hover:bg-[#00d2ff]/15 text-slate-400 hover:text-[#00d2ff] transition neu-button"
                              title="Open combo settings"
                            >
                              <ArrowUpRight className="w-3.5 h-3.5 group-hover:text-[#00d2ff] transition" />
                            </button>
                          </div>
                        </div>

                        {/* Mobile model preview chips */}
                        {c.models && c.models.length > 0 && (
                          <div className="flex sm:hidden items-center gap-1 overflow-x-auto scrollbar-none w-full pt-1 border-t border-black/5 dark:border-white/5">
                            {c.models.map((m, idx) => {
                              const isUnavail = c.unavailable_models?.includes(m);
                              const isHighLat = c.high_latency_models?.some(h => h.id === m);
                              return (
                                <span
                                  key={m}
                                  className={`inline-flex items-center gap-1 text-[8.5px] font-mono px-1.5 py-0.5 rounded shrink-0 ${
                                    isUnavail
                                      ? 'bg-rose-500/15 border border-rose-500/30 text-rose-400 font-semibold'
                                      : isHighLat
                                      ? 'bg-amber-500/15 border border-amber-500/30 text-amber-400 font-semibold'
                                      : idx === 0 && c.strategy === 'fallback'
                                      ? 'bg-[#ff6b35]/15 text-[#ff6b35]'
                                      : 'bg-black/5 dark:bg-white/10 text-slate-600 dark:text-slate-400'
                                  }`}
                                  title={m}
                                >
                                  <ModelIcon model={m} className="h-2.5 w-auto max-w-[20px] max-h-2.5 shrink-0" />
                                  <span className="truncate max-w-[120px]">{m.split('/').pop()}</span>
                                </span>
                              );
                            })}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <div className="mt-3 pt-2.5 border-t border-black/5 dark:border-white/5 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-1 text-[9.5px] text-slate-400 dark:text-slate-500">
                <div className="flex items-center gap-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-[#00f5a0]" />
                  <span>Always cascades to <span className="text-[#00f5a0] font-semibold">nim-auto</span> if all combo models fail</span>
                </div>
                <div>Fastest response wins across configured providers</div>
              </div>
            </div>

            <div className="rounded-3xl p-3.5 sm:p-4.5 bg-white dark:bg-[#171b24] border border-black/5 dark:border-white/10 shadow-neu-light dark:shadow-neu-dark flex flex-col min-h-[160px] lg:flex-1 transition-colors duration-300">
              <div className="flex items-center justify-between mb-2.5 shrink-0">
                <div className="flex items-center gap-1.5">
                  <Terminal className="w-3.5 h-3.5 text-[#00d2ff]" />
                  <span className="text-[11px] font-semibold text-slate-800 dark:text-slate-200">
                    Live Server Logs
                  </span>
                </div>
                <div className="flex items-center gap-1.5">
                  <span className="text-[9px] font-mono text-[#00f5a0] flex items-center gap-1">
                    <span className="w-1.5 h-1.5 rounded-full bg-[#00f5a0] animate-pulse" />
                    SSE Stream
                  </span>
                  <button
                    onClick={onOpenLogs}
                    className="p-1 rounded-full bg-black/5 dark:bg-white/10 text-slate-700 dark:text-white hover:bg-[#00d2ff] hover:text-black transition"
                    title="Expand Full Terminal"
                  >
                    <Plus className="w-3 h-3" />
                  </button>
                </div>
              </div>

              <div 
                ref={logsContainerRef}
                className="flex-1 min-h-[120px] max-h-[220px] overflow-hidden p-3 rounded-2xl bg-[#0a0c10] font-mono text-[10.5px] space-y-1.5 shadow-neu-dark-inset text-slate-300 flex flex-col justify-end"
              >
                {logs.slice(-7).map((l, i) => (
                  <div key={i} className="flex items-center gap-2 leading-tight truncate">
                    <span className="text-[#00d2ff] shrink-0 font-mono">{l.timestamp}</span>
                    <span className={`font-semibold shrink-0 px-1.5 py-0.2 rounded text-[9px] ${
                      l.level === 'INFO' ? 'bg-blue-500/15 text-blue-400' :
                      l.level === 'SUCCESS' ? 'bg-emerald-500/15 text-emerald-400' :
                      l.level === 'WARNING' ? 'bg-amber-500/15 text-amber-400' :
                      l.level === 'ERROR' ? 'bg-rose-500/15 text-rose-400' : 'text-slate-400'
                    }`}>
                      {l.level}
                    </span>
                    <span className="truncate text-slate-300">{l.message}</span>
                  </div>
                ))}
                {logs.length === 0 && (
                  <div className="text-slate-500 italic py-4 text-center">Listening for server events...</div>
                )}
              </div>
            </div>

          </div>

        </div>

      </div>
    </div>
  );
}
