import React, { useState, useEffect } from 'react';
import { 
  BookOpen, 
  Search, 
  Database,
  Sparkles, 
  Link2, 
  Upload, 
  FileSpreadsheet, 
  Bot, 
  AlertTriangle, 
  FileSpreadsheet, 
  ShieldAlert, 
  BarChart3, 
  Files, 
  ShieldAlert, 
  Sparkles,
  Bot,
  Cpu
  Search
  Files
} from 'lucide-react';

export default function Navbar({ activeTab, setActiveTab, stats, onExport }) {
export default function Navbar({ 
  primaryMode, 
  setPrimaryMode, 
  v1SubTab, 
  setV1SubTab, 
  stats, 
  onExport 
}) {
  const reviewCount = stats?.needs_review || 0;
  const wrongCount = stats?.wrong_doi || 0;
  const brokenCount = stats?.broken_url || 0;

  const [llmStatus, setLlmStatus] = useState(null);

  useEffect(() => {
    fetch('/api/llm/status')
      .then((r) => r.json())
      .then((d) => setLlmStatus(d))
      .catch(() => setLlmStatus(null));
  }, []);

  const tabs = [
  const PRIMARY_OPTIONS = [
    { 
      id: 'v1', 
      label: 'V1: Baseline References', 
      badge: '17,252', 
      badgeColor: 'bg-indigo-950/80 text-indigo-300 border border-indigo-500/30',
      icon: Database 
    },
    { 
      id: 'v2', 
      label: 'V2: AI Scientometrics', 
      badge: 'Latest Models', 
      badgeColor: 'bg-cyan-950/80 text-cyan-300 border border-cyan-500/40',
      icon: Sparkles 
    },
    { 
      id: 'links', 
      label: 'Link Auditor', 
      badge: 'Scopus / DOI',
      badgeColor: 'bg-slate-800 text-slate-300 border border-slate-700',
      icon: Link2 
    },
    { 
      id: 'document_test', 
      label: 'Document Testing Module', 
      badge: 'PDF / Word', 
      badgeColor: 'bg-purple-950/80 text-purple-300 border border-purple-500/40',
      icon: Upload 
    },
  ];

  const V1_SUB_TABS = [
    { id: 'explorer', label: 'Reference Explorer', icon: Search },
    { 
      id: 'review', 
      label: 'Human Review Queue', 
      label: 'Review Queue', 
      icon: AlertTriangle, 
      badge: reviewCount > 0 ? reviewCount.toLocaleString() : null,
      badgeColor: 'bg-amber-500/20 text-amber-300 border border-amber-500/40'
    },
    { 
      id: 'discrepancies', 
      label: 'Discrepancies & Dead Links', 
      icon: ShieldAlert,
      badge: (wrongCount + brokenCount) > 0 ? (wrongCount + brokenCount) : null,
      badgeColor: 'bg-rose-500/20 text-rose-300 border border-rose-500/40'
    },
    { id: 'documents', label: 'Citing Manuscripts', icon: Files },
    { id: 'analytics', label: 'Analytics', icon: BarChart3 },
    { id: 'analytics', label: 'Corpus Analytics', icon: BarChart3 },
  ];

  return (
    <header className="sticky top-0 z-40 bg-[#090e1a]/95 backdrop-blur-md border-b border-slate-800/90 shadow-xl py-2.5">
      <div className="w-full px-4 sm:px-6 lg:px-8">
    <header className="sticky top-0 z-40 bg-[#090e1a]/95 backdrop-blur-md border-b border-slate-800/90 shadow-xl">
      {/* Primary Top Bar */}
      <div className="w-full px-4 sm:px-6 lg:px-8 py-2.5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          
          {/* Brand & Corpus Metadata */}
          <div className="flex items-center gap-3 shrink-0">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-indigo-500 via-indigo-600 to-cyan-500 flex items-center justify-center shadow-lg shadow-indigo-500/25 ring-1 ring-white/10 shrink-0">
              <BookOpen className="w-5 h-5 text-white" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="font-extrabold text-base sm:text-lg text-slate-100 tracking-tight whitespace-nowrap">
                  Scientometric Audit Studio
                </span>
                <span className="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full bg-indigo-500/15 text-indigo-300 border border-indigo-500/30 whitespace-nowrap">
                  Scopus Ground-Truth
                  v2.0 AI-Augmented
                </span>
                {llmStatus && (
                  <span className={`inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full border whitespace-nowrap shadow-xs ${
                    llmStatus.available 
                      ? 'bg-emerald-500/15 text-emerald-300 border-emerald-500/40' 
                      : 'bg-slate-800 text-slate-400 border-slate-700'
                  }`} title={`Provider: ${llmStatus.provider} | Base: ${llmStatus.base_url}`}>
                    <span className={`w-1.5 h-1.5 rounded-full ${llmStatus.available ? 'bg-emerald-400 animate-pulse' : 'bg-slate-500'}`}></span>
                    <Bot className="w-2.5 h-2.5" />
                    <span>{llmStatus.provider.toUpperCase()} ({llmStatus.model})</span>
                  </span>
                )}
              </div>
              <div className="text-[11px] text-slate-400 flex flex-wrap items-center gap-x-2 gap-y-0.5 mt-0.5">
                <span><strong className="text-slate-200 font-semibold">{stats?.total_documents || 841}</strong> Manuscripts</span>
                <span className="text-slate-600">&bull;</span>
                <span><strong className="text-slate-200 font-semibold">{(stats?.total_references || 17252).toLocaleString()}</strong> References</span>
                <span className="text-slate-600">&bull;</span>
                <span className="text-emerald-400 font-medium">Sub-10ms SQLite</span>
              </div>
            </div>
          </div>

          {/* Navigation Tabs */}
          <nav className="flex items-center gap-1 bg-[#0e1628] p-1 rounded-xl border border-slate-800/90 shadow-inner overflow-x-auto">
            {tabs.map((tab) => {
              const Icon = tab.icon;
              const isActive = activeTab === tab.id;
          {/* 4 Main Dashboard Navigation Options */}
          <nav className="flex items-center gap-1.5 bg-[#0e1628] p-1.5 rounded-xl border border-slate-800/90 shadow-inner overflow-x-auto">
            {PRIMARY_OPTIONS.map((opt) => {
              const Icon = opt.icon;
              const isActive = primaryMode === opt.id;
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all whitespace-nowrap cursor-pointer ${
                  key={opt.id}
                  onClick={() => setPrimaryMode(opt.id)}
                  className={`flex items-center gap-2 px-3.5 py-2 rounded-lg text-xs font-bold transition-all whitespace-nowrap cursor-pointer ${
                    isActive
                      ? 'bg-gradient-to-r from-indigo-600 to-indigo-700 text-white shadow-md shadow-indigo-600/30 ring-1 ring-indigo-400/30'
                      : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
                      ? opt.id === 'v2'
                        ? 'bg-gradient-to-r from-cyan-600 to-indigo-600 text-white shadow-lg shadow-cyan-600/30 ring-1 ring-cyan-400/40'
                        : opt.id === 'links'
                        ? 'bg-gradient-to-r from-teal-600 to-cyan-600 text-white shadow-lg shadow-teal-600/30 ring-1 ring-teal-400/40'
                        : opt.id === 'document_test'
                        ? 'bg-gradient-to-r from-purple-600 to-indigo-600 text-white shadow-lg shadow-purple-600/30 ring-1 ring-purple-400/40'
                        : 'bg-gradient-to-r from-indigo-600 to-indigo-700 text-white shadow-lg shadow-indigo-600/30 ring-1 ring-indigo-400/30'
                      : 'text-slate-300 hover:text-white hover:bg-slate-800/80 border border-transparent'
                  }`}
                >
                  <Icon className="w-3.5 h-3.5 shrink-0" />
                  <span>{tab.label}</span>
                  {tab.badge && (
                    <span className={`text-[10px] font-bold px-1.5 py-0.2 rounded-full shadow-xs ${
                      isActive ? 'bg-white/20 text-white' : tab.badgeColor
                  <Icon className="w-4 h-4 shrink-0" />
                  <span>{opt.label}</span>
                  {opt.badge && (
                    <span className={`text-[10px] font-bold px-1.5 py-0.2 rounded-full font-mono ${
                      isActive ? 'bg-black/30 text-white' : opt.badgeColor
                    }`}>
                      {tab.badge}
                      {opt.badge}
                    </span>
                  )}
                </button>
              );
            })}
          </nav>

          {/* Action Buttons */}
          {/* Export CSV Button */}
          <div className="flex items-center gap-2 shrink-0">
            <button
              onClick={() => setActiveTab('custom_audit')}
              className={`flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-xs font-bold transition-all shadow-md cursor-pointer whitespace-nowrap ${
                activeTab === 'custom_audit'
                  ? 'bg-gradient-to-r from-cyan-500 to-indigo-600 text-white ring-2 ring-cyan-400/50 shadow-cyan-500/25'
                  : 'bg-gradient-to-r from-indigo-600 to-indigo-700 hover:from-indigo-500 hover:to-indigo-600 text-white hover:scale-102 ring-1 ring-white/10 shadow-indigo-600/30'
              }`}
              title="Submit custom Scopus link or upload your own dataset"
            >
              <Sparkles className="w-3.5 h-3.5 text-cyan-300 shrink-0" />
              <span>Validate Custom Paper / Data</span>
            </button>
            {primaryMode === 'v1' && (
              <button
                onClick={onExport}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-gradient-to-r from-slate-800 to-slate-900 hover:from-slate-700 hover:to-slate-800 text-slate-200 border border-slate-700/80 transition-all shadow-sm hover:border-slate-600 cursor-pointer active:scale-98 whitespace-nowrap"
                title="Download currently filtered references as CSV"
              >
                <FileSpreadsheet className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
                <span>Export CSV</span>
              </button>
            )}
          </div>

            <button
              onClick={onExport}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-gradient-to-r from-slate-800 to-slate-900 hover:from-slate-700 hover:to-slate-800 text-slate-200 border border-slate-700/80 transition-all shadow-sm hover:border-slate-600 cursor-pointer active:scale-98 whitespace-nowrap"
              title="Download currently filtered references as CSV"
            >
              <FileSpreadsheet className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
              <span>Export CSV</span>
            </button>
        </div>
      </div>

      {/* Secondary Sub-Tabs bar when V1 is active */}
      {primaryMode === 'v1' && (
        <div className="bg-[#0b101d] border-t border-slate-800/80 px-4 sm:px-6 lg:px-8 py-1.5 flex items-center justify-between gap-3 text-xs">
          <div className="flex items-center gap-1 overflow-x-auto">
            <span className="text-[10px] font-bold uppercase tracking-wider text-slate-500 mr-2">V1 Corpus Views:</span>
            {V1_SUB_TABS.map((sub) => {
              const SubIcon = sub.icon;
              const isSubActive = v1SubTab === sub.id;
              return (
                <button
                  key={sub.id}
                  onClick={() => setV1SubTab(sub.id)}
                  className={`flex items-center gap-1.5 px-3 py-1 rounded-md text-xs font-medium transition cursor-pointer whitespace-nowrap ${
                    isSubActive
                      ? 'bg-indigo-600/30 text-indigo-300 border border-indigo-500/40 font-bold'
                      : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/40'
                  }`}
                >
                  <SubIcon className="w-3 h-3" />
                  <span>{sub.label}</span>
                  {sub.badge && (
                    <span className={`text-[9px] font-bold px-1.5 py-0.1 rounded-full ${
                      isSubActive ? 'bg-indigo-900 text-white' : sub.badgeColor
                    }`}>
                      {sub.badge}
                    </span>
                  )}
                </button>
              );
            })}
          </div>

          <div className="text-[11px] text-slate-500 font-mono hidden md:block">
            Corpus Baseline: 17,252 Validated Records
          </div>
        </div>
      </div>
      )}
    </header>
  );
}

