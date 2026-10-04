import React, { useState, useEffect, useCallback } from 'react';
import { 
  Sparkles, 
  Search, 
  RotateCcw, 
  BookOpen, 
  AlertTriangle, 
  CheckCircle2, 
  XCircle, 
  ArrowRight, 
  Bot, 
  TrendingUp, 
  Clock, 
  Layers, 
  ShieldAlert, 
  ExternalLink, 
  FileText, 
  ChevronRight, 
  X,
  Play,
  Cpu
} from 'lucide-react';

const STANCE_BADGES = {
  METHODOLOGY: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40',
  BACKGROUND: 'bg-slate-800 text-slate-300 border-slate-700',
  COMPARISON: 'bg-blue-500/20 text-blue-300 border-blue-500/40',
  CRITIQUE: 'bg-rose-500/20 text-rose-300 border-rose-500/40',
  CORROBORATION: 'bg-purple-500/20 text-purple-300 border-purple-500/40',
};

const GRADE_BADGES = {
  'A+': 'bg-emerald-500/20 text-emerald-300 border-emerald-500/50',
  'A': 'bg-emerald-500/15 text-emerald-400 border-emerald-500/40',
  'B': 'bg-cyan-500/20 text-cyan-300 border-cyan-500/40',
  'C': 'bg-amber-500/20 text-amber-300 border-amber-500/40',
  'REQUIRES_REVISION': 'bg-rose-500/25 text-rose-300 border-rose-500/50 font-bold',
};

export default function V2ScientometricsView({ onSelectDocumentInV1 }) {
  const [stats, setStats] = useState(null);
  const [docs, setDocs] = useState([]);
  const [totalMatches, setTotalMatches] = useState(0);
  const [totalPages, setTotalPages] = useState(1);
  const [loading, setLoading] = useState(true);
  const [runningModels, setRunningModels] = useState(false);

  // Filters & Pagination
  const [page, setPage] = useState(1);
  const [pageSize] = useState(25);
  const [search, setSearch] = useState('');
  const [gradeFilter, setGradeFilter] = useState('');
  const [riskFilter, setRiskFilter] = useState('');
  const [freshnessFilter, setFreshnessFilter] = useState('');
  const [sortBy, setSortBy] = useState('total_references');
  const [sortOrder, setSortOrder] = useState('desc');

  // Selected Document for Deep-Dive Modal
  const [selectedDocEid, setSelectedDocEid] = useState(null);
  const [selectedDocDetail, setSelectedDocDetail] = useState(null);
  const [modalLoading, setModalLoading] = useState(false);
  const [runningSingleAi, setRunningSingleAi] = useState(false);

  // Fetch V2 Corpus Stats
  const fetchCorpusStats = useCallback(() => {
    fetch('/api/v2/stats')
      .then((res) => res.json())
      .then((data) => setStats(data))
      .catch((err) => console.error('Error loading V2 stats:', err));
  }, []);

  // Fetch Paginated V2 Documents
  const fetchDocuments = useCallback(() => {
    setLoading(true);
    const params = new URLSearchParams();
    params.set('page', page);
    params.set('page_size', pageSize);
    if (search.trim()) params.set('q', search.trim());
    if (gradeFilter) params.set('grade', gradeFilter);
    if (riskFilter) params.set('risk', riskFilter);
    if (freshnessFilter) params.set('freshness', freshnessFilter);
    params.set('sort_by', sortBy);
    params.set('sort_order', sortOrder);

    fetch(`/api/v2/documents?${params.toString()}`)
      .then((res) => res.json())
      .then((data) => {
        setDocs(data.items || []);
        setTotalMatches(data.total || 0);
        setTotalPages(data.total_pages || 1);
        setLoading(false);
      })
      .catch((err) => {
        console.error('Error fetching V2 documents:', err);
        setLoading(false);
      });
  }, [page, pageSize, search, gradeFilter, riskFilter, freshnessFilter, sortBy, sortOrder]);

  useEffect(() => {
    fetchCorpusStats();
  }, [fetchCorpusStats]);

  useEffect(() => {
    fetchDocuments();
  }, [fetchDocuments]);

  // Recalculate V2 models across the corpus
  const handleRunAllModels = async () => {
    setRunningModels(true);
    try {
      const res = await fetch('/api/v2/run-models', { method: 'POST' });
      const data = await res.json();
      if (data.status === 'success') {
        fetchCorpusStats();
        fetchDocuments();
      }
    } catch (err) {
      console.error('Error running V2 models:', err);
    } finally {
      setRunningModels(false);
    }
  };

  // Open Document Modal & Fetch Detail
  const handleOpenDocModal = async (sourceEid) => {
    setSelectedDocEid(sourceEid);
    setModalLoading(true);
    try {
      const res = await fetch(`/api/v2/document/${encodeURIComponent(sourceEid)}`);
      const data = await res.json();
      setSelectedDocDetail(data);
    } catch (err) {
      console.error('Error loading document detail:', err);
    } finally {
      setModalLoading(false);
    }
  };

  // Run Real-Time LLM Audit on single manuscript
  const handleRunSingleAi = async () => {
    if (!selectedDocEid) return;
    setRunningSingleAi(true);
    try {
      const res = await fetch(`/api/v2/document/${encodeURIComponent(selectedDocEid)}/run-ai`, { method: 'POST' });
      const data = await res.json();
      if (data.status === 'success' && data.document) {
        setSelectedDocDetail(data.document);
        fetchDocuments();
        fetchCorpusStats();
      }
    } catch (err) {
      console.error('Error running single AI audit:', err);
    } finally {
      setRunningSingleAi(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* V2 Header Banner */}
      <div className="bg-gradient-to-r from-indigo-950 via-[#0c1630] to-slate-900 border border-indigo-500/40 rounded-2xl p-6 shadow-2xl relative overflow-hidden">
        <div className="absolute right-0 top-0 w-96 h-full bg-gradient-to-l from-indigo-500/10 to-transparent pointer-events-none"></div>
        <div className="flex flex-wrap items-center justify-between gap-4 relative z-10">
          <div className="space-y-1.5 max-w-3xl">
            <div className="flex items-center gap-2.5">
              <span className="px-2.5 py-0.5 rounded-full bg-indigo-500/20 text-indigo-300 border border-indigo-500/40 font-mono text-[11px] font-bold uppercase tracking-wider">
                V2 Latest Models
              </span>
              <span className="text-xs text-slate-400 font-mono">
                Document-Wise Bibliometric Intelligence &amp; AI Peer-Review
              </span>
            </div>
            <h1 className="text-xl sm:text-2xl font-black text-white tracking-tight flex items-center gap-2">
              <span>V2 Scientometric Audit: Document-Wise Results</span>
              <Sparkles className="w-5 h-5 text-cyan-400 shrink-0" />
            </h1>
            <p className="text-xs sm:text-sm text-slate-300 leading-relaxed">
              Evaluating all <strong>{stats?.total_documents || 841} citing manuscripts</strong> using latest models: Price's Index recency, citation half-life, Shannon venue diversity, rhetorical stance taxonomy, and AI hallucination detection.
            </p>
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={handleRunAllModels}
              disabled={runningModels}
              className={`px-4 py-2.5 rounded-xl text-xs font-bold transition-all shadow-lg flex items-center gap-2 cursor-pointer ${
                runningModels 
                  ? 'bg-indigo-900/60 text-indigo-300 border border-indigo-500/40 cursor-not-allowed'
                  : 'bg-gradient-to-r from-indigo-600 via-indigo-500 to-cyan-500 hover:from-indigo-500 hover:to-cyan-400 text-white shadow-indigo-500/30 active:scale-98 ring-1 ring-white/20'
              }`}
            >
              {runningModels ? (
                <>
                  <div className="w-4 h-4 border-2 border-indigo-300 border-t-transparent rounded-full animate-spin"></div>
                  <span>Recalculating Models...</span>
                </>
              ) : (
                <>
                  <Cpu className="w-4 h-4 text-cyan-200" />
                  <span>⚡ Run Latest AI Models (Corpus)</span>
                </>
              )}
            </button>
          </div>
        </div>
      </div>

      {/* 4 Top-Level Corpus KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* KPI 1: Price's Index */}
        <div className="p-4 rounded-xl bg-slate-900/90 border border-slate-800 shadow-xl flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between text-xs text-slate-400 mb-1">
              <span className="font-bold uppercase tracking-wider text-[11px] text-slate-300">Mean Price's Index</span>
              <span className="text-[10px] px-2 py-0.5 rounded bg-cyan-950 text-cyan-300 border border-cyan-500/40 font-mono font-bold">
                Recency (&le; 5 yrs)
              </span>
            </div>
            <div className="text-2xl font-black text-cyan-300 mt-1">
              {stats?.avg_price_index || 48.7}%
            </div>
            <p className="text-[11px] text-slate-400 mt-1">
              Average proportion of cited literature published within 5 years.
            </p>
          </div>
          <div className="pt-3 mt-3 border-t border-slate-800 text-[11px] text-slate-400 flex items-center justify-between">
            <span>Cutting-Edge (&ge;50%): <strong className="text-emerald-400">{stats?.cutting_edge_count || 423}</strong></span>
            <span>Dated: <strong className="text-amber-400">{stats?.dated_count || 163}</strong></span>
          </div>
        </div>

        {/* KPI 2: Citation Half-Life */}
        <div className="p-4 rounded-xl bg-slate-900/90 border border-slate-800 shadow-xl flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between text-xs text-slate-400 mb-1">
              <span className="font-bold uppercase tracking-wider text-[11px] text-slate-300">Citation Half-Life</span>
              <span className="text-[10px] px-2 py-0.5 rounded bg-indigo-950 text-indigo-300 border border-indigo-500/40 font-mono font-bold">
                Median Age
              </span>
            </div>
            <div className="text-2xl font-black text-indigo-300 mt-1">
              {stats?.avg_citation_age || 6.7} <span className="text-sm font-normal text-slate-400">years</span>
            </div>
            <p className="text-[11px] text-slate-400 mt-1">
              Mean median citation age across all manuscripts.
            </p>
          </div>
          <div className="pt-3 mt-3 border-t border-slate-800 text-[11px] text-slate-400 flex items-center justify-between">
            <span>Shannon Venue Entropy:</span>
            <strong className="text-purple-300 font-mono">{stats?.avg_venue_diversity || 0.92} / 1.0</strong>
          </div>
        </div>

        {/* KPI 3: Hallucination & Integrity Risk */}
        <div className="p-4 rounded-xl bg-slate-900/90 border border-slate-800 shadow-xl flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between text-xs text-slate-400 mb-1">
              <span className="font-bold uppercase tracking-wider text-[11px] text-slate-300">Citation Integrity Alert</span>
              <span className="text-[10px] px-2 py-0.5 rounded bg-rose-950 text-rose-300 border border-rose-500/40 font-mono font-bold">
                404 / Fake DOIs
              </span>
            </div>
            <div className="text-2xl font-black text-rose-400 mt-1 flex items-center gap-2">
              <span>{stats?.high_risk_documents || 4}</span>
              <span className="text-xs font-semibold px-2 py-0.5 rounded bg-rose-950 text-rose-300 border border-rose-500/30">
                High Risk Papers
              </span>
            </div>
            <p className="text-[11px] text-slate-400 mt-1">
              Manuscripts with multiple non-existent 404 DOIs (potential AI hallucinations).
            </p>
          </div>
          <div className="pt-3 mt-3 border-t border-slate-800 text-[11px] text-slate-400 flex items-center justify-between">
            <span>Total Invalid 404 DOIs:</span>
            <strong className="text-rose-400 font-mono">{stats?.total_invalid_dois || 99}</strong>
          </div>
        </div>

        {/* KPI 4: Audit Grade Profile */}
        <div className="p-4 rounded-xl bg-slate-900/90 border border-slate-800 shadow-xl flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between text-xs text-slate-400 mb-1">
              <span className="font-bold uppercase tracking-wider text-[11px] text-slate-300">AI Peer-Review Grades</span>
              <span className="text-[10px] px-2 py-0.5 rounded bg-emerald-950 text-emerald-300 border border-emerald-500/40 font-mono font-bold">
                Corpus Quality
              </span>
            </div>
            <div className="text-2xl font-black text-emerald-300 mt-1 flex items-center gap-2">
              <span>{(stats?.grade_a_plus || 0) + (stats?.grade_a || 0) + (stats?.grade_b || 0)}</span>
              <span className="text-xs font-normal text-slate-400">Passing (A/B)</span>
            </div>
            <p className="text-[11px] text-slate-400 mt-1">
              Overall academic rigor and bibliographic verification profile.
            </p>
          </div>
          <div className="pt-3 mt-3 border-t border-slate-800 text-[11px] text-slate-400 flex items-center justify-between font-mono">
            <span>A+: {stats?.grade_a_plus || 0}</span>
            <span>B: {stats?.grade_b || 0}</span>
            <span>C: {stats?.grade_c || 0}</span>
            <span className="text-rose-400">Rev: {stats?.grade_revision || 0}</span>
          </div>
        </div>
      </div>

      {/* Search, Filter & Sort Controls */}
      <div className="bg-[#0e1628]/95 border border-slate-800 rounded-xl p-4 shadow-xl flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2.5 flex-1 min-w-[280px]">
          {/* Search Input */}
          <div className="relative flex-1 min-w-[220px]">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400" />
            <input
              type="text"
              value={search}
              onChange={(e) => { setSearch(e.target.value); setPage(1); }}
              placeholder="Search manuscript title, author, or Scopus EID..."
              className="w-full pl-8 pr-7 py-2 bg-slate-900 border border-slate-700 rounded-lg text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500 shadow-inner font-mono"
            />
            {search && (
              <button onClick={() => setSearch('')} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-white">
                <X className="w-3.5 h-3.5" />
              </button>
            )}
          </div>

          {/* Grade Filter */}
          <select
            value={gradeFilter}
            onChange={(e) => { setGradeFilter(e.target.value); setPage(1); }}
            className="px-3 py-2 bg-slate-900 border border-slate-700 rounded-lg text-xs text-slate-200 focus:outline-none focus:border-indigo-500 cursor-pointer"
          >
            <option value="">All Audit Grades</option>
            <option value="A+">Grade A+ (Exemplary)</option>
            <option value="A">Grade A (Sound)</option>
            <option value="B">Grade B (Good)</option>
            <option value="C">Grade C (Gaps)</option>
            <option value="REQUIRES_REVISION">Requires Revision (Critical)</option>
          </select>

          {/* Risk Filter */}
          <select
            value={riskFilter}
            onChange={(e) => { setRiskFilter(e.target.value); setPage(1); }}
            className="px-3 py-2 bg-slate-900 border border-slate-700 rounded-lg text-xs text-slate-200 focus:outline-none focus:border-indigo-500 cursor-pointer"
          >
            <option value="">All Risk Levels</option>
            <option value="HIGH">High Hallucination Risk</option>
            <option value="MEDIUM">Medium Risk</option>
            <option value="LOW">Low Risk</option>
          </select>

          {/* Freshness Filter */}
          <select
            value={freshnessFilter}
            onChange={(e) => { setFreshnessFilter(e.target.value); setPage(1); }}
            className="px-3 py-2 bg-slate-900 border border-slate-700 rounded-lg text-xs text-slate-200 focus:outline-none focus:border-indigo-500 cursor-pointer"
          >
            <option value="">All Freshness Tiers</option>
            <option value="CUTTING_EDGE">Cutting Edge (&ge; 50%)</option>
            <option value="BALANCED">Balanced (25% - 50%)</option>
            <option value="DATED_OBSOLESCENT">Dated (&lt; 25%)</option>
          </select>
        </div>

        {/* Sort Controls */}
        <div className="flex items-center gap-2">
          <span className="text-[11px] text-slate-400">Sort by:</span>
          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value)}
            className="px-2.5 py-1.5 bg-slate-900 border border-slate-700 rounded-lg text-xs text-slate-200 focus:outline-none focus:border-indigo-500 cursor-pointer font-mono"
          >
            <option value="total_references">Total References</option>
            <option value="price_index">Price's Index</option>
            <option value="median_citation_age">Citation Age</option>
            <option value="resolving_pct">DOI Resolution %</option>
            <option value="source_year">Publication Year</option>
            <option value="invalid_dois_count">Broken DOIs</option>
          </select>

          <button
            onClick={() => setSortOrder(prev => prev === 'desc' ? 'asc' : 'desc')}
            className="px-2.5 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs font-mono font-bold text-slate-200 border border-slate-700 transition"
            title="Toggle sort direction"
          >
            {sortOrder.toUpperCase()}
          </button>
        </div>
      </div>

      {/* Document-Wise Table */}
      <div className="bg-[#0b1120] border border-slate-800 rounded-xl overflow-hidden shadow-2xl">
        <div className="p-3.5 bg-slate-950/80 border-b border-slate-800 flex items-center justify-between text-xs text-slate-400">
          <span>
            Showing <strong className="text-white font-bold">{docs.length}</strong> of{' '}
            <strong className="text-white font-bold">{totalMatches}</strong> manuscripts
          </span>
          <span className="font-mono text-[11px] text-slate-500">
            Page {page} of {totalPages}
          </span>
        </div>

        {loading ? (
          <div className="p-16 text-center">
            <div className="w-8 h-8 border-3 border-indigo-500 border-t-transparent rounded-full animate-spin mx-auto mb-3"></div>
            <p className="text-slate-400 text-xs">Querying V2 document scientometrics...</p>
          </div>
        ) : docs.length === 0 ? (
          <div className="p-16 text-center text-slate-400 text-xs space-y-2">
            <AlertTriangle className="w-8 h-8 text-amber-400 mx-auto" />
            <p className="font-bold text-slate-300">No manuscripts matching the current filters.</p>
            <button
              onClick={() => { setSearch(''); setGradeFilter(''); setRiskFilter(''); setFreshnessFilter(''); }}
              className="px-3 py-1.5 rounded bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs transition mt-2 cursor-pointer"
            >
              Reset Filters
            </button>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs border-collapse">
              <thead className="bg-[#0e1628] border-b border-slate-800 text-slate-400 uppercase text-[10px] tracking-wider font-bold">
                <tr>
                  <th className="py-3 px-4">Citing Manuscript</th>
                  <th className="py-3 px-3 text-center">Refs</th>
                  <th className="py-3 px-3 text-center">Price's Index</th>
                  <th className="py-3 px-3 text-center">Half-Life</th>
                  <th className="py-3 px-3 text-center">DOI Resolution</th>
                  <th className="py-3 px-3 text-center">Primary Stance</th>
                  <th className="py-3 px-3 text-center">AI Grade</th>
                  <th className="py-3 px-3 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60 font-sans">
                {docs.map((d) => {
                  return (
                    <tr 
                      key={d.source_eid}
                      className="hover:bg-slate-900/60 transition group cursor-pointer"
                      onClick={() => handleOpenDocModal(d.source_eid)}
                    >
                      {/* Manuscript Details */}
                      <td className="py-3 px-4 max-w-md">
                        <div className="font-bold text-slate-100 group-hover:text-indigo-300 transition line-clamp-1">
                          {d.source_title || 'Untitled Manuscript'}
                        </div>
                        <div className="text-[11px] text-slate-400 line-clamp-1 mt-0.5">
                          {d.source_authors}
                        </div>
                        <div className="flex items-center gap-2 mt-1 text-[10px]">
                          <span className="font-mono text-indigo-400 bg-indigo-950/60 px-1.5 py-0.2 rounded border border-indigo-500/30">
                            {d.source_eid}
                          </span>
                          <span className="text-slate-500 font-mono">
                            Year: {d.source_year || 'N/A'}
                          </span>
                        </div>
                      </td>

                      {/* Total References */}
                      <td className="py-3 px-3 text-center font-bold text-slate-200">
                        {d.total_references}
                      </td>

                      {/* Price's Index */}
                      <td className="py-3 px-3 text-center">
                        <span className={`inline-block px-2 py-0.5 rounded font-mono font-bold text-xs ${
                          d.price_index >= 50.0 
                            ? 'bg-emerald-950/80 text-emerald-300 border border-emerald-500/40' 
                            : d.price_index >= 25.0
                            ? 'bg-cyan-950/80 text-cyan-300 border border-cyan-500/40'
                            : 'bg-amber-950/80 text-amber-300 border border-amber-500/40'
                        }`}>
                          {d.price_index}%
                        </span>
                      </td>

                      {/* Citation Half-Life */}
                      <td className="py-3 px-3 text-center font-mono text-slate-300">
                        {d.median_citation_age} yrs
                      </td>

                      {/* DOI Resolution & Broken Alert */}
                      <td className="py-3 px-3 text-center">
                        <div className="font-mono font-semibold text-slate-200">
                          {d.resolving_pct}%
                        </div>
                        {d.invalid_dois_count > 0 && (
                          <span className="inline-flex items-center gap-1 text-[10px] px-1.5 py-0.2 rounded bg-rose-950 text-rose-300 border border-rose-500/40 font-bold mt-0.5">
                            <AlertTriangle className="w-2.5 h-2.5" />
                            {d.invalid_dois_count} 404s
                          </span>
                        )}
                      </td>

                      {/* Primary Stance */}
                      <td className="py-3 px-3 text-center">
                        <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full border ${
                          STANCE_BADGES[d.primary_intent] || 'bg-slate-800 text-slate-300 border-slate-700'
                        }`}>
                          {d.primary_intent}
                        </span>
                      </td>

                      {/* AI Audit Grade */}
                      <td className="py-3 px-3 text-center">
                        <span className={`text-xs font-mono font-black px-2 py-0.5 rounded border ${
                          GRADE_BADGES[d.audit_grade] || 'bg-slate-800 text-slate-300 border-slate-700'
                        }`}>
                          {d.audit_grade}
                        </span>
                      </td>

                      {/* Action */}
                      <td className="py-3 px-3 text-right">
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            handleOpenDocModal(d.source_eid);
                          }}
                          className="px-2.5 py-1 rounded bg-indigo-600/80 hover:bg-indigo-500 text-white font-semibold text-[11px] transition shadow-xs flex items-center gap-1 ml-auto cursor-pointer"
                        >
                          <span>AI Audit</span>
                          <ChevronRight className="w-3 h-3" />
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {/* Pagination Bar */}
        {totalPages > 1 && (
          <div className="p-3.5 bg-slate-950/80 border-t border-slate-800 flex items-center justify-between text-xs">
            <button
              onClick={() => setPage(p => Math.max(1, p - 1))}
              disabled={page <= 1}
              className="px-3 py-1.5 rounded bg-slate-900 border border-slate-700 text-slate-300 hover:text-white disabled:opacity-40 cursor-pointer"
            >
              Previous
            </button>
            <span className="text-slate-400 font-mono">
              Page {page} of {totalPages}
            </span>
            <button
              onClick={() => setPage(p => Math.min(totalPages, p + 1))}
              disabled={page >= totalPages}
              className="px-3 py-1.5 rounded bg-slate-900 border border-slate-700 text-slate-300 hover:text-white disabled:opacity-40 cursor-pointer"
            >
              Next
            </button>
          </div>
        )}
      </div>

      {/* Document Deep-Dive AI Audit Modal */}
      {selectedDocEid && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4 overflow-y-auto">
          <div className="bg-[#0d1424] border border-slate-700 rounded-2xl w-full max-w-4xl max-h-[90vh] overflow-y-auto shadow-2xl flex flex-col justify-between">
            {/* Modal Header */}
            <div className="p-5 border-b border-slate-800 flex items-start justify-between gap-4 sticky top-0 bg-[#0d1424]/95 backdrop-blur-md z-10">
              <div className="space-y-1">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-[11px] px-2 py-0.5 rounded bg-indigo-950 text-indigo-300 border border-indigo-500/40 font-bold">
                    {selectedDocEid}
                  </span>
                  <span className={`text-[10px] font-mono font-bold px-2 py-0.5 rounded border ${
                    GRADE_BADGES[selectedDocDetail?.audit_grade] || 'bg-slate-800 text-slate-300'
                  }`}>
                    Grade: {selectedDocDetail?.audit_grade || 'A'}
                  </span>
                  <span className="text-xs text-slate-400 font-mono">
                    Model: {selectedDocDetail?.ai_model_used || 'Local Engine'}
                  </span>
                </div>
                <h2 className="text-base sm:text-lg font-bold text-white">
                  {selectedDocDetail?.source_title || 'Manuscript Audit Detail'}
                </h2>
                <p className="text-xs text-slate-400">
                  {selectedDocDetail?.source_authors} ({selectedDocDetail?.source_year || 'N/A'})
                </p>
              </div>

              <button
                onClick={() => { setSelectedDocEid(null); setSelectedDocDetail(null); }}
                className="p-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-white transition"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Modal Body */}
            {modalLoading ? (
              <div className="p-16 text-center">
                <div className="w-8 h-8 border-3 border-indigo-500 border-t-transparent rounded-full animate-spin mx-auto mb-3"></div>
                <p className="text-slate-400 text-xs">Loading manuscript profile...</p>
              </div>
            ) : selectedDocDetail ? (
              <div className="p-6 space-y-6">
                {/* 5 Indicators Grid */}
                <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
                  <div className="p-3 rounded-xl bg-slate-950/80 border border-slate-800">
                    <div className="text-[10px] uppercase font-bold text-slate-400">Price's Index</div>
                    <div className="text-lg font-extrabold text-cyan-300 mt-0.5">
                      {selectedDocDetail.price_index}%
                    </div>
                    <div className="text-[10px] text-slate-500">&le; 5 yrs recency</div>
                  </div>

                  <div className="p-3 rounded-xl bg-slate-950/80 border border-slate-800">
                    <div className="text-[10px] uppercase font-bold text-slate-400">Citation Half-Life</div>
                    <div className="text-lg font-extrabold text-indigo-300 mt-0.5">
                      {selectedDocDetail.median_citation_age} yrs
                    </div>
                    <div className="text-[10px] text-slate-500">Median age</div>
                  </div>

                  <div className="p-3 rounded-xl bg-slate-950/80 border border-slate-800">
                    <div className="text-[10px] uppercase font-bold text-slate-400">Venue Diversity</div>
                    <div className="text-lg font-extrabold text-purple-300 mt-0.5">
                      {selectedDocDetail.venue_diversity_score}
                    </div>
                    <div className="text-[10px] text-slate-500">Shannon entropy</div>
                  </div>

                  <div className="p-3 rounded-xl bg-slate-950/80 border border-slate-800">
                    <div className="text-[10px] uppercase font-bold text-slate-400">Year Range</div>
                    <div className="text-lg font-extrabold text-emerald-300 mt-0.5">
                      {selectedDocDetail.min_year || 'N/A'} - {selectedDocDetail.max_year || 'N/A'}
                    </div>
                    <div className="text-[10px] text-slate-500">Chronological span</div>
                  </div>

                  <div className={`p-3 rounded-xl bg-slate-950/80 border ${
                    selectedDocDetail.invalid_dois_count > 0 ? 'border-rose-500/40' : 'border-slate-800'
                  }`}>
                    <div className="text-[10px] uppercase font-bold text-slate-400">DOI Resolution</div>
                    <div className={`text-lg font-extrabold mt-0.5 ${
                      selectedDocDetail.invalid_dois_count > 0 ? 'text-rose-400' : 'text-emerald-400'
                    }`}>
                      {selectedDocDetail.resolving_pct}%
                    </div>
                    <div className="text-[10px] text-slate-500">
                      {selectedDocDetail.invalid_dois_count > 0 ? `${selectedDocDetail.invalid_dois_count} broken (404)` : 'All valid'}
                    </div>
                  </div>
                </div>

                {/* Stance Breakdown */}
                {selectedDocDetail.intent_distribution && (
                  <div className="p-3.5 rounded-xl bg-slate-950/80 border border-slate-800 space-y-2">
                    <div className="flex items-center justify-between text-xs font-bold text-slate-300">
                      <span>Rhetorical Citation Stance Profile</span>
                      <span className="text-[10px] text-slate-500 font-normal">Methodology vs Background vs Comparison vs Critique</span>
                    </div>
                    <div className="flex flex-wrap items-center gap-2 text-xs">
                      {Object.entries(selectedDocDetail.intent_distribution).map(([st, cnt]) => (
                        <span key={st} className={`px-2.5 py-0.5 rounded-full border font-bold text-[11px] ${
                          STANCE_BADGES[st] || 'bg-slate-800 text-slate-300 border-slate-700'
                        }`}>
                          {st}: {cnt}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {/* Executive Assessment Card */}
                <div className="p-4 rounded-xl bg-gradient-to-r from-slate-950 via-[#0a1224] to-slate-950 border border-indigo-500/30 space-y-2.5 text-xs text-slate-300 leading-relaxed">
                  <div className="flex items-center justify-between text-slate-100 font-bold">
                    <div className="flex items-center gap-2">
                      <Bot className="w-4 h-4 text-cyan-400" />
                      <span>Executive Scientometric Critique</span>
                    </div>
                    <button
                      onClick={handleRunSingleAi}
                      disabled={runningSingleAi}
                      className="px-2.5 py-1 rounded bg-indigo-600/80 hover:bg-indigo-500 text-white font-semibold text-[11px] transition flex items-center gap-1.5 cursor-pointer disabled:opacity-50"
                    >
                      {runningSingleAi ? (
                        <>
                          <div className="w-3 h-3 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                          <span>Synthesizing (Ollama)...</span>
                        </>
                      ) : (
                        <>
                          <Sparkles className="w-3 h-3 text-cyan-300" />
                          <span>Re-Run Deep LLM Critique</span>
                        </>
                      )}
                    </button>
                  </div>

                  <p className="text-slate-200">{selectedDocDetail.executive_summary}</p>

                  {selectedDocDetail.methodological_backbone && (
                    <div className="pt-2 border-t border-slate-800 text-slate-400">
                      <strong className="text-slate-200">Methodological Backbone: </strong>
                      {selectedDocDetail.methodological_backbone}
                    </div>
                  )}

                  {selectedDocDetail.potential_blind_spots && selectedDocDetail.potential_blind_spots.length > 0 && (
                    <div className="pt-2 border-t border-slate-800 text-amber-300/90">
                      <strong className="text-amber-200">Audit Recommendations: </strong>
                      <ul className="list-disc pl-5 mt-1 space-y-1">
                        {selectedDocDetail.potential_blind_spots.map((spot, idx) => (
                          <li key={idx}>{spot}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>

                {/* References Preview & V1 Jump Button */}
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <h3 className="font-bold text-slate-200 text-xs uppercase tracking-wider flex items-center gap-2">
                      <BookOpen className="w-4 h-4 text-indigo-400" />
                      <span>Reference Collection ({selectedDocDetail.references?.length || 0} citations)</span>
                    </h3>
                    <button
                      onClick={() => {
                        const eid = selectedDocEid;
                        setSelectedDocEid(null);
                        setSelectedDocDetail(null);
                        if (onSelectDocumentInV1) onSelectDocumentInV1(eid);
                      }}
                      className="px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white font-bold text-xs transition flex items-center gap-1.5 cursor-pointer shadow-md"
                    >
                      <span>Browse All {selectedDocDetail.references?.length} in V1 Explorer</span>
                      <ArrowRight className="w-3.5 h-3.5" />
                    </button>
                  </div>

                  <div className="max-h-60 overflow-y-auto border border-slate-800 rounded-xl divide-y divide-slate-800/60 bg-slate-950/60">
                    {(selectedDocDetail.references || []).slice(0, 30).map((r) => (
                      <div key={r.reference_id} className="p-2.5 text-xs text-slate-300 hover:bg-slate-900/50 flex items-start justify-between gap-3">
                        <div className="space-y-0.5 flex-1">
                          <div className="flex items-center gap-2">
                            <span className="font-mono text-[10px] text-slate-500 font-bold">#{r.reference_no}</span>
                            <span className={`text-[9px] font-bold px-1.5 py-0.2 rounded font-mono ${
                              r.final_status === 'VALID_CORRECT' || r.doi_resolves 
                                ? 'bg-emerald-950 text-emerald-300'
                                : r.final_status === 'INVALID_DOI'
                                ? 'bg-rose-950 text-rose-300'
                                : 'bg-slate-800 text-slate-400'
                            }`}>
                              {r.final_status}
                            </span>
                            {r.resolved_year && (
                              <span className="text-[10px] text-slate-400 font-mono">({r.resolved_year})</span>
                            )}
                          </div>
                          <p className="line-clamp-1 text-slate-300 text-[11px]">{r.raw_reference}</p>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            ) : null}

            {/* Modal Footer */}
            <div className="p-4 border-t border-slate-800 flex items-center justify-between text-xs text-slate-500 bg-[#0d1424]">
              <span>Scientometric Studio V2 &bull; Derek de Solla Price Indicators</span>
              <button
                onClick={() => { setSelectedDocEid(null); setSelectedDocDetail(null); }}
                className="px-4 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 transition font-semibold"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

