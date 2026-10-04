import React, { useState, useEffect, useRef } from 'react';
import { 
  Search, 
  X, 
  Filter, 
  ArrowUpDown, 
  RotateCcw,
  Check,
  BookOpen,
  ChevronDown,
  Sparkles,
  AlertTriangle,
  Link2,
  FileText
} from 'lucide-react';

const ALL_STATUSES = [
  { id: 'VALID_CORRECT', label: 'Valid Correct', color: 'text-emerald-300 border-emerald-500/50 bg-emerald-950/40' },
  { id: 'SCOPUS_LINKED_NO_DOI', label: 'Scopus Linked (No DOI)', color: 'text-cyan-300 border-cyan-500/50 bg-cyan-950/40' },
  { id: 'SCOPUS_UNLINKED', label: 'Scopus Unlinked', color: 'text-amber-300 border-amber-500/50 bg-amber-950/40' },
  { id: 'DOI_RECOVERED', label: 'DOI Recovered', color: 'text-purple-300 border-purple-500/50 bg-purple-950/40' },
  { id: 'ACCESS_RESTRICTED', label: 'Access Restricted (Paywall)', color: 'text-blue-300 border-blue-500/50 bg-blue-950/40' },
  { id: 'BROKEN_URL', label: 'Broken URL (404)', color: 'text-rose-300 border-rose-500/50 bg-rose-950/40' },
  { id: 'VALID_DOI_WRONG_REFERENCE', label: 'Wrong Reference Discrepancy', color: 'text-red-300 border-red-500/60 bg-red-950/50' },
  { id: 'DOI_RECOVERY_UNCERTAIN', label: 'Uncertain Recovery', color: 'text-orange-300 border-orange-500/50 bg-orange-950/40' },
  { id: 'DOI_MISSING', label: 'DOI Missing', color: 'text-slate-300 border-slate-600/50 bg-slate-900/40' },
];

export default function FilterBar({ filters, setFilters, totalMatches, resetFilters }) {
  const [localSearch, setLocalSearch] = useState(filters.q || '');
  const [documents, setDocuments] = useState([]);
  const [docSearch, setDocSearch] = useState('');
  const [isDocDropdownOpen, setIsDocDropdownOpen] = useState(false);
  const dropdownRef = useRef(null);

  // Load manuscripts list once for the dropdown
  useEffect(() => {
    fetch('/api/documents?limit=1000')
      .then((res) => res.json())
      .then((data) => setDocuments(data.items || []))
      .catch((err) => console.error('Error fetching documents list:', err));
  }, []);

  // Handle clicking outside the document dropdown
  useEffect(() => {
    const handleClickOutside = (event) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        setIsDocDropdownOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Debounce global search input by 250ms
  useEffect(() => {
    const timer = setTimeout(() => {
      if (localSearch !== filters.q) {
        setFilters((prev) => ({ ...prev, q: localSearch, page: 1 }));
      }
    }, 250);
    return () => clearTimeout(timer);
  }, [localSearch]);

  // Sync external search query reset
  useEffect(() => {
    setLocalSearch(filters.q || '');
  }, [filters.q]);

  // Select manuscript: Reset conflicting filters so ALL references of that manuscript display immediately!
  const handleSelectManuscript = (eid) => {
    setFilters((prev) => ({
      ...prev,
      source_eid: eid,
      status: '',
      confidence: '',
      scopus_linked: 'all',
      needs_review: 'all',
      has_doi: 'all',
      q: '',
      sort_by: eid ? 'reference_no' : 'reference_id',
      sort_order: 'asc',
      page: 1,
    }));
    setLocalSearch('');
    setIsDocDropdownOpen(false);
  };

  const toggleStatus = (statusId) => {
    const current = filters.status ? filters.status.split(',').filter(Boolean) : [];
    let updated;
    if (current.includes(statusId)) {
      updated = current.filter((s) => s !== statusId);
    } else {
      updated = [...current, statusId];
    }
    setFilters((prev) => ({ ...prev, status: updated.join(','), page: 1 }));
  };

  const currentStatuses = filters.status ? filters.status.split(',').filter(Boolean) : [];

  // Filtered documents for search inside dropdown
  const filteredDocs = documents.filter((d) => 
    !docSearch || 
    (d.source_title && d.source_title.toLowerCase().includes(docSearch.toLowerCase())) ||
    (d.source_eid && d.source_eid.toLowerCase().includes(docSearch.toLowerCase())) ||
    (d.source_authors && d.source_authors.toLowerCase().includes(docSearch.toLowerCase()))
  );

  const selectedDocObj = documents.find((d) => d.source_eid === filters.source_eid);

  return (
    <div className="bg-[#0e1628]/95 border border-slate-800/90 rounded-xl p-4 mb-5 shadow-xl space-y-3.5">
      
      {/* Row 1: Target Manuscripts Quick Presets & Full Searchable Selector */}
      <div className="flex flex-wrap items-center justify-between gap-2.5 pb-3 border-b border-slate-800/80">
        
        {/* Left: Quick Presets */}
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-[11px] font-bold text-slate-400 uppercase tracking-wider flex items-center gap-1.5 mr-1">
            <BookOpen className="w-3.5 h-3.5 text-indigo-400" /> Manuscript Scope:
          </span>

          {/* Preset 0: All Papers */}
          <button
            onClick={() => handleSelectManuscript('')}
            className={`px-3 py-1 rounded-lg text-xs font-semibold transition shadow-xs flex items-center gap-1.5 cursor-pointer ${
              !filters.source_eid
                ? 'bg-indigo-600 text-white shadow-indigo-600/30'
                : 'bg-slate-900/80 text-slate-400 hover:text-slate-200 hover:bg-slate-800 border border-slate-800'
            }`}
          >
            <span>All Manuscripts ({documents.length || 841})</span>
          </button>

          {/* Preset 1: Paper 1 (IISERs) */}
          <button
            onClick={() => handleSelectManuscript('2-s2.0-85118881384')}
            className={`px-3 py-1 rounded-lg text-xs font-semibold transition shadow-xs flex items-center gap-1.5 cursor-pointer ${
              filters.source_eid === '2-s2.0-85118881384'
                ? 'bg-indigo-600 text-white ring-2 ring-indigo-400/50 font-bold'
                : 'bg-slate-900/80 text-slate-300 hover:text-white hover:bg-slate-800 border border-slate-700/80'
            }`}
          >
            <span>📄 Paper 1: IISERs</span>
            <span className="text-[10px] px-1.5 py-0.2 rounded bg-indigo-950 text-indigo-300 border border-indigo-500/30">
              14 refs
            </span>
          </button>

          {/* Preset 2: Paper 2 (Patent Analysis) */}
          <button
            onClick={() => handleSelectManuscript('2-s2.0-105042346360')}
            className={`px-3 py-1 rounded-lg text-xs font-semibold transition shadow-xs flex items-center gap-1.5 cursor-pointer ${
              filters.source_eid === '2-s2.0-105042346360'
                ? 'bg-indigo-600 text-white ring-2 ring-indigo-400/50 font-bold'
                : 'bg-slate-900/80 text-slate-300 hover:text-white hover:bg-slate-800 border border-slate-700/80'
            }`}
          >
            <span>📄 Paper 2: Patent Analysis</span>
            <span className="text-[10px] px-1.5 py-0.2 rounded bg-indigo-950 text-indigo-300 border border-indigo-500/30">
              35 refs
            </span>
          </button>
        </div>

        {/* Right: Searchable Manuscript Dropdown */}
        <div className="relative min-w-[280px] max-w-md w-full sm:w-auto" ref={dropdownRef}>
          <button
            onClick={() => setIsDocDropdownOpen(!isDocDropdownOpen)}
            className={`w-full flex items-center justify-between px-3 py-1.5 bg-slate-900/90 border rounded-lg text-xs transition shadow-inner cursor-pointer ${
              filters.source_eid 
                ? 'border-indigo-500/80 text-indigo-200 bg-indigo-950/30 font-semibold' 
                : 'border-slate-700/80 text-slate-300 hover:border-slate-600'
            }`}
          >
            <div className="flex items-center gap-2 truncate pr-1">
              <BookOpen className="w-3.5 h-3.5 text-indigo-400 shrink-0" />
              <span className="truncate">
                {selectedDocObj ? selectedDocObj.source_title : 'Select any of 841 manuscripts...'}
              </span>
            </div>
            <div className="flex items-center gap-1 shrink-0 ml-1">
              {filters.source_eid && (
                <span
                  onClick={(e) => {
                    e.stopPropagation();
                    handleSelectManuscript('');
                  }}
                  className="p-0.5 hover:text-white text-slate-400 cursor-pointer"
                  title="Clear manuscript filter"
                >
                  <X className="w-3.5 h-3.5" />
                </span>
              )}
              <ChevronDown className="w-3.5 h-3.5 text-slate-400" />
            </div>
          </button>

          {/* Searchable Dropdown Panel */}
          {isDocDropdownOpen && (
            <div className="absolute top-full right-0 left-0 sm:left-auto sm:w-[460px] mt-1.5 z-50 bg-[#0f172a] border border-slate-700/90 rounded-xl shadow-2xl overflow-hidden">
              <div className="p-2.5 border-b border-slate-800 bg-slate-900/95">
                <div className="relative">
                  <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400" />
                  <input
                    type="text"
                    value={docSearch}
                    onChange={(e) => setDocSearch(e.target.value)}
                    placeholder="Search by manuscript title, author, or EID..."
                    className="w-full pl-8 pr-2.5 py-1.5 bg-slate-950 border border-slate-700 rounded-lg text-xs text-slate-200 focus:outline-none focus:border-indigo-500 shadow-inner"
                    autoFocus
                  />
                </div>
              </div>

              <div className="max-h-72 overflow-y-auto divide-y divide-slate-800/60 text-xs">
                <div
                  onClick={() => handleSelectManuscript('')}
                  className="p-2.5 hover:bg-slate-800/60 cursor-pointer text-slate-400 font-semibold italic flex items-center justify-between"
                >
                  <span>-- Show All Citing Manuscripts --</span>
                  <span className="text-[10px] text-slate-500">{documents.length} papers</span>
                </div>

                {filteredDocs.slice(0, 80).map((d) => (
                  <div
                    key={d.source_eid}
                    onClick={() => handleSelectManuscript(d.source_eid)}
                    className={`p-2.5 hover:bg-slate-800/70 cursor-pointer transition ${
                      filters.source_eid === d.source_eid 
                        ? 'bg-indigo-950/50 text-indigo-200 font-semibold border-l-2 border-indigo-500' 
                        : 'text-slate-200'
                    }`}
                  >
                    <div className="line-clamp-1 font-medium">{d.source_title || 'Untitled Manuscript'}</div>
                    <div className="text-[10px] text-slate-400 flex items-center gap-2 mt-0.5">
                      <span className="font-mono text-indigo-400">{d.source_eid}</span>
                      <span>&bull;</span>
                      <span className="text-emerald-400 font-bold">{d.ref_count} refs</span>
                      <span>&bull;</span>
                      <span>{d.source_year || 'N/A'}</span>
                    </div>
                  </div>
                ))}

                {filteredDocs.length === 0 && (
                  <div className="p-4 text-center text-xs text-slate-500">
                    No manuscripts matching "{docSearch}"
                  </div>
                )}
              </div>
            </div>
          )}
        </div>

      </div>

      {/* Row 2: Search, Filters & Sorting Toolbar */}
      <div className="flex flex-wrap items-center gap-2.5">
        
        {/* Full text search */}
        <div className="relative flex-1 min-w-[260px]">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
          <input
            type="text"
            value={localSearch}
            onChange={(e) => setLocalSearch(e.target.value)}
            placeholder="Search citation text, DOI, author, title, or Ref ID..."
            className="w-full pl-9 pr-8 py-1.5 bg-slate-900/90 border border-slate-700/80 rounded-lg text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition shadow-inner"
          />
          {localSearch && (
            <button
              onClick={() => {
                setLocalSearch('');
                setFilters((prev) => ({ ...prev, q: '', page: 1 }));
              }}
              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-200 cursor-pointer"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          )}
        </div>

        {/* Scopus Link Toggle */}
        <div className="flex items-center bg-slate-900/90 border border-slate-700/80 rounded-lg p-0.5 text-xs shadow-inner">
          <span className="px-2 text-slate-400 font-medium">Scopus:</span>
          {[
            { id: 'all', label: 'All' },
            { id: 'true', label: 'Linked' },
            { id: 'false', label: 'Unlinked' },
          ].map((btn) => (
            <button
              key={btn.id}
              onClick={() => setFilters((prev) => ({ ...prev, scopus_linked: btn.id, page: 1 }))}
              className={`px-2.5 py-1 rounded-md font-medium transition cursor-pointer ${
                filters.scopus_linked === btn.id
                  ? 'bg-indigo-600 text-white font-semibold shadow-xs'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              {btn.label}
            </button>
          ))}
        </div>

        {/* Human Review Filter */}
        <div className="flex items-center bg-slate-900/90 border border-slate-700/80 rounded-lg p-0.5 text-xs shadow-inner">
          <span className="px-2 text-slate-400 font-medium">Review:</span>
          {[
            { id: 'all', label: 'All' },
            { id: 'true', label: 'Queue' },
            { id: 'false', label: 'Auto-Approved' },
          ].map((btn) => (
            <button
              key={btn.id}
              onClick={() => setFilters((prev) => ({ ...prev, needs_review: btn.id, page: 1 }))}
              className={`px-2.5 py-1 rounded-md font-medium transition cursor-pointer ${
                filters.needs_review === btn.id
                  ? btn.id === 'true'
                    ? 'bg-amber-600 text-white font-semibold shadow-xs'
                    : 'bg-emerald-600 text-white font-semibold shadow-xs'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              {btn.label}
            </button>
          ))}
        </div>

        {/* DOI Filter */}
        <div className="flex items-center bg-slate-900/90 border border-slate-700/80 rounded-lg p-0.5 text-xs shadow-inner">
          <span className="px-2 text-slate-400 font-medium flex items-center gap-1">
            <Link2 className="w-3 h-3 text-cyan-400" /> DOI:
          </span>
          {[
            { id: 'all', label: 'All' },
            { id: 'true', label: 'Has DOI' },
            { id: 'false', label: 'No DOI' },
          ].map((btn) => (
            <button
              key={btn.id}
              onClick={() => setFilters((prev) => ({ ...prev, has_doi: btn.id, page: 1 }))}
              className={`px-2 py-1 rounded-md font-medium transition cursor-pointer ${
                filters.has_doi === btn.id
                  ? 'bg-cyan-600 text-white font-semibold shadow-xs'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              {btn.label}
            </button>
          ))}
        </div>

        {/* Sort Selector */}
        <div className="flex items-center gap-1.5 bg-slate-900/90 border border-slate-700/80 rounded-lg px-2.5 py-1 text-xs shadow-inner">
          <ArrowUpDown className="w-3.5 h-3.5 text-slate-400" />
          <span className="text-slate-400 font-medium">Sort:</span>
          <select
            value={filters.sort_by || (filters.source_eid ? 'reference_no' : 'reference_id')}
            onChange={(e) => setFilters((prev) => ({ ...prev, sort_by: e.target.value, page: 1 }))}
            className="bg-transparent text-slate-200 focus:outline-none cursor-pointer pr-1"
          >
            <option value="reference_no" className="bg-slate-900">Citation Order (#)</option>
            <option value="reference_id" className="bg-slate-900">Reference ID</option>
            <option value="composite_score" className="bg-slate-900">Composite Score</option>
            <option value="title_similarity" className="bg-slate-900">Title Similarity</option>
            <option value="author_similarity" className="bg-slate-900">Author Similarity</option>
            <option value="source_year" className="bg-slate-900">Publication Year</option>
          </select>
          <button
            onClick={() => setFilters((prev) => ({
              ...prev,
              sort_order: prev.sort_order === 'desc' ? 'asc' : 'desc',
              page: 1,
            }))}
            className="text-indigo-400 hover:text-white px-1 font-bold text-xs cursor-pointer"
            title="Toggle sort direction"
          >
            {filters.sort_order === 'desc' ? '▼ Desc' : '▲ Asc'}
          </button>
        </div>

        {/* Reset All Filters */}
        <button
          onClick={resetFilters}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition border border-transparent hover:border-slate-700 ml-auto cursor-pointer"
        >
          <RotateCcw className="w-3.5 h-3.5" />
          <span>Reset All</span>
        </button>

      </div>

      {/* Row 3: Multi-Select Scientometric Status Pills */}
      <div className="flex flex-wrap items-center gap-1.5 pt-2.5 border-t border-slate-800/80">
        <span className="text-xs font-semibold text-slate-400 mr-1 flex items-center gap-1">
          <Filter className="w-3 h-3 text-indigo-400" /> Status:
        </span>
        {ALL_STATUSES.map((st) => {
          const isSelected = currentStatuses.includes(st.id);
          return (
            <button
              key={st.id}
              onClick={() => toggleStatus(st.id)}
              className={`text-[11px] font-semibold px-2.5 py-0.5 rounded-full border transition-all flex items-center gap-1 shadow-xs cursor-pointer ${
                isSelected
                  ? `${st.color} font-bold ring-1 ring-white/30 scale-102`
                  : 'border-slate-800/90 text-slate-400 bg-slate-900/60 hover:bg-slate-800 hover:text-slate-200'
              }`}
            >
              {isSelected && <Check className="w-2.5 h-2.5 stroke-[3]" />}
              <span>{st.label}</span>
            </button>
          );
        })}

        {currentStatuses.length > 0 && (
          <button
            onClick={() => setFilters((prev) => ({ ...prev, status: '', page: 1 }))}
            className="text-xs text-indigo-400 hover:text-indigo-300 underline font-medium ml-2 cursor-pointer"
          >
            Clear status filter ({currentStatuses.length})
          </button>
        )}
      </div>

      {/* Row 4: Live Filter Match Metrics */}
      <div className="flex items-center justify-between text-xs text-slate-400 pt-1">
        <div className="flex items-center gap-2">
          <span>
            Matching references: <strong className="text-indigo-300 font-bold font-mono text-sm">{totalMatches.toLocaleString()}</strong>
          </span>
          {filters.source_eid && (
            <span className="text-[11px] px-2 py-0.5 rounded bg-indigo-950/80 text-indigo-300 border border-indigo-500/40 font-mono">
              EID: {filters.source_eid}
            </span>
          )}
          {filters.q && (
            <span className="text-[11px] px-2 py-0.5 rounded bg-slate-800 text-slate-300 font-mono">
              Query: "{filters.q}"
            </span>
          )}
        </div>
      </div>

    </div>
  );
}
