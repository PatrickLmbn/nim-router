import React, { useEffect, useRef } from 'react';
import { ChevronDown } from 'lucide-react';

function MenuItem({ item, onSelect }) {
  const Icon = item.icon;
  return (
    <button
      type="button"
      onClick={() => onSelect(item)}
      disabled={item.disabled}
      className="group flex items-start gap-2.5 rounded-xl px-2.5 py-2 text-left transition hover:bg-slate-100 dark:hover:bg-white/[0.07] disabled:opacity-50 disabled:cursor-not-allowed"
    >
      <span className={`mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg ${item.tint || 'bg-slate-100 dark:bg-white/5'}`}>
        <Icon className={`h-3.5 w-3.5 ${item.iconClass || 'text-slate-600 dark:text-slate-300'}`} />
      </span>
      <span className="min-w-0">
        <span className="flex items-center gap-1.5 text-[11px] font-semibold text-slate-800 dark:text-slate-100">
          {item.label}
          {item.badge && (
            <span className="rounded-full bg-[#00f5a0]/15 px-1.5 py-0.5 text-[8px] font-bold uppercase tracking-wide text-[#00a86b] dark:text-[#00f5a0]">
              {item.badge}
            </span>
          )}
        </span>
        <span className="mt-0.5 block text-[10px] leading-snug text-slate-500 dark:text-slate-400">
          {item.description}
        </span>
      </span>
    </button>
  );
}

export function MegaMenu({ groups, openMenu, setOpenMenu }) {
  const navRef = useRef(null);
  const closeTimer = useRef(null);
  const activeGroup = groups.find((group) => group.id === openMenu) || null;

  const canHover = () =>
    typeof window !== 'undefined' &&
    window.matchMedia('(hover: hover) and (pointer: fine)').matches;

  const clearCloseTimer = () => {
    if (closeTimer.current) {
      clearTimeout(closeTimer.current);
      closeTimer.current = null;
    }
  };

  const handleHoverOpen = (id) => {
    if (!canHover()) return;
    clearCloseTimer();
    setOpenMenu(id);
  };

  const handleHoverLeave = () => {
    if (!canHover()) return;
    clearCloseTimer();
    closeTimer.current = setTimeout(() => setOpenMenu(null), 200);
  };

  useEffect(() => clearCloseTimer, []);

  useEffect(() => {
    const handlePointerDown = (event) => {
      if (navRef.current && !navRef.current.contains(event.target)) {
        setOpenMenu(null);
      }
    };
    const handleKeyDown = (event) => {
      if (event.key === 'Escape') setOpenMenu(null);
    };
    document.addEventListener('mousedown', handlePointerDown);
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('mousedown', handlePointerDown);
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [setOpenMenu]);

  const handleSelect = (item) => {
    setOpenMenu(null);
    item.onSelect();
  };

  return (
    <nav ref={navRef} className="relative flex items-center justify-center gap-1" aria-label="Dashboard sections" onMouseEnter={clearCloseTimer} onMouseLeave={handleHoverLeave}>
      {groups.map((group) => {
        const GroupIcon = group.icon;
        const isOpen = openMenu === group.id;
        return (
          <button
            key={group.id}
            type="button"
            onClick={() => setOpenMenu(isOpen ? null : group.id)}
            onMouseEnter={() => handleHoverOpen(group.id)}
            aria-expanded={isOpen}
            aria-haspopup="true"
            className={`flex items-center gap-1.5 rounded-xl px-2.5 py-1 text-xs font-semibold transition neu-button border ${
              isOpen
                ? 'bg-slate-900 text-white dark:bg-white dark:text-slate-900 border-transparent'
                : 'bg-white dark:bg-white/5 text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-white/10 border-black/5 dark:border-transparent'
            }`}
          >
            <GroupIcon className="h-3.5 w-3.5" />
            <span className="hidden sm:inline">{group.label}</span>
            <ChevronDown className={`h-3 w-3 transition-transform ${isOpen ? 'rotate-180' : ''}`} />
          </button>
        );
      })}

      {activeGroup && (
        <div
          className="absolute left-1/2 top-full z-50 mt-2 max-h-[72vh] w-[calc(100vw-1rem)] max-w-[560px] -translate-x-1/2 overflow-y-auto rounded-2xl border border-black/5 bg-white/95 shadow-2xl backdrop-blur-xl dark:border-white/10 dark:bg-[#151922]/95"
          role="menu"
        >
          <div className="flex items-center gap-2 border-b border-black/5 px-3 py-2 dark:border-white/5">
            <span className="flex h-6 w-6 items-center justify-center rounded-lg bg-[#da7756]/15">
              <activeGroup.icon className="h-3.5 w-3.5 text-[#da7756]" />
            </span>
            <div>
              <p className="text-[11px] font-bold tracking-wide text-slate-800 dark:text-slate-100">{activeGroup.label}</p>
              <p className="text-[9px] text-slate-500 dark:text-slate-400">{activeGroup.description}</p>
            </div>
          </div>
          <div className="grid grid-cols-1 gap-0.5 p-1.5 sm:grid-cols-2">
            {activeGroup.items.map((item) => (
              <MenuItem key={item.label} item={item} onSelect={handleSelect} />
            ))}
          </div>
        </div>
      )}
    </nav>
  );
}
