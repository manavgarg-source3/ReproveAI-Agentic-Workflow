import React, { useState, useEffect, useCallback } from 'react';
import { BookOpen, RotateCcw } from 'lucide-react';
import Navbar from './components/Navbar';
import KpiCards from './components/KpiCards';
import FilterBar from './components/FilterBar';
import ReferenceTable from './components/ReferenceTable';
import ReferenceDrawer from './components/ReferenceDrawer';
import Pagination from './components/Pagination';
import DocumentsView from './components/DocumentsView';
import AnalyticsView from './components/AnalyticsView';
import CustomAuditView from './components/CustomAuditView';
import V2ScientometricsView from './components/V2ScientometricsView';
import LinkAuditorView from './components/LinkAuditorView';

const INITIAL_FILTERS = {
  page: 1,
  page_size: 50,
  q: '',
  status: '',
  confidence: '',
  scopus_linked: 'all',
  needs_review: 'all',
  has_doi: 'all',
  source_eid: '',
  sort_by: 'reference_id',
  sort_order: 'asc',
};

export default function App() {
  const [activeTab, setActiveTab] = useState('explorer');
  const [primaryMode, setPrimaryMode] = useState('v1'); // 'v1' | 'v2' | 'links' | 'document_test'
  const [v1SubTab, setV1SubTab] = useState('explorer'); // 'explorer' | 'review' | 'discrepancies' | 'analytics'
  const [v1SubTab, setV1SubTab] = useState('explorer'); // 'explorer' | 'review' | 'discrepancies' | 'documents' | 'analytics'
  const [stats, setStats] = useState(null);
  const [items, setItems] = useState([]);
  const [totalMatches, setTotalMatches] = useState(0);
  const [totalPages, setTotalPages] = useState(1);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState(INITIAL_FILTERS);
  const [selectedReferenceId, setSelectedReferenceId] = useState(null);
  const [selectedReferenceData, setSelectedReferenceData] = useState(null);

  const handleSelectReference = (id, data = null) => {
    setSelectedReferenceId(id);
    setSelectedReferenceData(data);
  };

  // Fetch KPI Stats
  const fetchStats = useCallback(() => {
    fetch('/api/stats')
      .then((res) => res.json())
      .then((data) => setStats(data))
      .catch((err) => console.error('Error loading stats:', err));
  }, []);

  useEffect(() => {
    fetchStats();
  }, [fetchStats]);

  // Fetch References based on current filters
  const fetchReferences = useCallback(() => {
    setLoading(true);
    const params = new URLSearchParams();
    params.set('page', filters.page);
    params.set('page_size', filters.page_size);

    if (filters.q) params.set('q', filters.q);
    if (filters.status) params.set('status', filters.status);
    if (filters.confidence) params.set('confidence', filters.confidence);
    if (filters.scopus_linked !== 'all') params.set('scopus_linked', filters.scopus_linked);
    if (filters.needs_review !== 'all') params.set('needs_review', filters.needs_review);
    if (filters.has_doi !== 'all') params.set('has_doi', filters.has_doi);
    if (filters.source_eid) params.set('source_eid', filters.source_eid);
    if (filters.sort_by) params.set('sort_by', filters.sort_by);
    if (filters.sort_order) params.set('sort_order', filters.sort_order);

    fetch(`/api/references?${params.toString()}`)
      .then((res) => res.json())
      .then((data) => {
        setItems(data.items || []);
        setTotalMatches(data.total || 0);
        setTotalPages(data.total_pages || 1);
        setLoading(false);
      })
      .catch((err) => {
        console.error('Error fetching references:', err);
        setLoading(false);
      });
  }, [filters]);

  useEffect(() => {
    fetchReferences();
  }, [fetchReferences]);

  // Synchronize Tab Changes with Filters
  const handleTabChange = (tabId) => {
    setActiveTab(tabId);
  // Synchronize V1 SubTab Changes with Filters
  const handleV1SubTabChange = (tabId) => {
    setV1SubTab(tabId);
    if (tabId === 'review') {
      setFilters((prev) => ({ ...prev, needs_review: 'true', status: '', page: 1 }));
    } else if (tabId === 'discrepancies') {
      setFilters((prev) => ({ ...prev, status: 'VALID_DOI_WRONG_REFERENCE,BROKEN_URL', needs_review: 'all', page: 1 }));
    } else if (tabId === 'explorer') {
      setFilters((prev) => ({ ...prev, needs_review: 'all', status: '', page: 1 }));
    }
  };

  // KPI Quick Filter Click Handler
  const handleKpiFilter = (filterOverrides) => {
    setActiveTab('explorer');
    setPrimaryMode('v1');
    setV1SubTab('explorer');
    setFilters((prev) => ({ ...prev, ...filterOverrides, page: 1 }));
  };

  // Filter By Source Manuscript
  // Filter By Source Manuscript - resets conflicting filters so all references immediately display in front!
  const handleFilterBySource = (eid) => {
    setActiveTab('explorer');
    setPrimaryMode('v1');
    setV1SubTab('explorer');
    setFilters({
      ...INITIAL_FILTERS,
      source_eid: eid,
      sort_by: eid ? 'reference_no' : 'reference_id',
      sort_order: 'asc',
      page: 1,
    });
  };

  // Filter By Status from Analytics
  const handleFilterByStatus = (status) => {
    setActiveTab('explorer');
    setPrimaryMode('v1');
    setV1SubTab('explorer');
    setFilters((prev) => ({ ...prev, status: status, page: 1 }));
  };

  // Reset Filters
  const resetFilters = () => {
    setFilters(INITIAL_FILTERS);
  };

  // Export Filtered CSV
  const handleExport = () => {
    const params = new URLSearchParams();
    if (filters.q) params.set('q', filters.q);
    if (filters.status) params.set('status', filters.status);
    if (filters.confidence) params.set('confidence', filters.confidence);
    if (filters.scopus_linked !== 'all') params.set('scopus_linked', filters.scopus_linked);
    if (filters.needs_review !== 'all') params.set('needs_review', filters.needs_review);
    if (filters.has_doi !== 'all') params.set('has_doi', filters.has_doi);
    if (filters.source_eid) params.set('source_eid', filters.source_eid);

    window.open(`/api/export?${params.toString()}`, '_blank');
  };

  // Callback when review is updated in drawer
  const handleReviewUpdated = (updatedRef) => {
    fetchStats();
    setItems((prev) =>
      prev.map((item) => (item.reference_id === updatedRef.reference_id ? updatedRef : item))
    );
  };

  return (
    <div className="min-h-screen w-full bg-[#080d1a] text-slate-100 flex flex-col font-sans antialiased">
      {/* Full-width Navigation Header */}
      <Navbar
        activeTab={activeTab}
        setActiveTab={handleTabChange}
        primaryMode={primaryMode}
        setPrimaryMode={setPrimaryMode}
        v1SubTab={v1SubTab}
        setV1SubTab={handleV1SubTabChange}
        stats={stats}
        onExport={handleExport}
      />

      {/* Full-width Workspace Container */}
      <main className="flex-1 w-full px-4 sm:px-6 lg:px-8 py-5">
        
        {/* KPI Metric Cards (Corpus Scope) */}
        {activeTab !== 'custom_audit' && (
          <KpiCards stats={stats} onFilterClick={handleKpiFilter} />
        )}

        {/* View Switcher Content */}
        {activeTab === 'custom_audit' ? (
        {/* Mode 1: V2 AI Scientometrics Document-Wise Results */}
        {primaryMode === 'v2' ? (
          <V2ScientometricsView 
            onSelectDocumentInV1={(eid) => handleFilterBySource(eid)} 
          />
        ) : primaryMode === 'links' ? (
          /* Mode 2: Link Auditor */
          <LinkAuditorView 
            onSelectReference={(id, data) => handleSelectReference(id, data)} 
          />
        ) : primaryMode === 'document_test' ? (
          /* Mode 3: Document Testing Module */
          <CustomAuditView
            onBack={() => setActiveTab('explorer')}
            onBack={() => setPrimaryMode('v1')}
            onSelectReference={(id, data) => handleSelectReference(id, data)}
          />
        ) : activeTab === 'documents' ? (
          <DocumentsView onSelectDocument={handleFilterBySource} />
        ) : activeTab === 'analytics' ? (
          <AnalyticsView stats={stats} onFilterByStatus={handleFilterByStatus} />
        ) : (
          /* Mode 4: V1 Baseline References (17,252) */
          <>
            {/* Filter Bar with Source Doc Selector */}
            <FilterBar
              filters={filters}
              setFilters={setFilters}
              totalMatches={totalMatches}
              resetFilters={resetFilters}
            />
            {v1SubTab === 'analytics' ? (
            {v1SubTab === 'documents' ? (
              <DocumentsView onSelectDocument={handleFilterBySource} />
            ) : v1SubTab === 'analytics' ? (
              <AnalyticsView stats={stats} onFilterByStatus={handleFilterByStatus} />
            ) : (
              <>
                {/* KPI Metric Cards (Corpus Scope) */}
                <KpiCards stats={stats} onFilterClick={handleKpiFilter} />

            {/* Active Manuscript Banner */}
            {filters.source_eid && (
              <div className="flex flex-wrap items-center justify-between gap-3 bg-gradient-to-r from-indigo-950/70 via-[#0e172e] to-slate-900 border border-indigo-500/40 px-4 py-3 rounded-xl text-xs mb-4 shadow-lg">
                <div className="flex items-center gap-3">
                  <div className="w-8 h-8 rounded-lg bg-indigo-600/30 border border-indigo-400/30 flex items-center justify-center shrink-0">
                    <BookOpen className="w-4 h-4 text-indigo-300" />
                  </div>
                  <div>
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-bold text-slate-100 text-sm">
                        {items[0]?.source_title || 'Active Manuscript'}
                      </span>
                      <span className="font-mono text-[11px] px-2 py-0.5 rounded bg-indigo-900/60 text-indigo-300 border border-indigo-500/40">
                        {filters.source_eid}
                      </span>
                {/* Filter Bar with Source Doc Selector */}
                <FilterBar
                  filters={filters}
                  setFilters={setFilters}
                  totalMatches={totalMatches}
                  resetFilters={resetFilters}
                />

                {/* Active Manuscript Banner */}
                {filters.source_eid && (
                  <div className="flex flex-wrap items-center justify-between gap-3 bg-gradient-to-r from-indigo-950/70 via-[#0e172e] to-slate-900 border border-indigo-500/40 px-4 py-3 rounded-xl text-xs mb-4 shadow-lg">
                    <div className="flex items-center gap-3">
                      <div className="w-8 h-8 rounded-lg bg-indigo-600/30 border border-indigo-400/30 flex items-center justify-center shrink-0">
                        <BookOpen className="w-4 h-4 text-indigo-300" />
                      </div>
                      <div>
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="font-bold text-slate-100 text-sm">
                            {items[0]?.source_title || 'Active Manuscript'}
                          </span>
                          <span className="font-mono text-[11px] px-2 py-0.5 rounded bg-indigo-900/60 text-indigo-300 border border-indigo-500/40">
                            {filters.source_eid}
                          </span>
                        </div>
                        <p className="text-slate-400 text-[11px] mt-0.5 flex flex-wrap items-center gap-2">
                          {items[0]?.source_authors && <span>{items[0].source_authors} ({items[0].source_year || 'N/A'}) &bull;</span>}
                          <span>Showing <strong className="text-white font-semibold">{totalMatches}</strong> total references in V1</span>
                          {filters.status && <span className="text-amber-400 font-medium">&bull; Filtered by Status: {filters.status}</span>}
                          {filters.needs_review !== 'all' && <span className="text-amber-400 font-medium">&bull; Review Queue: {filters.needs_review}</span>}
                          {filters.scopus_linked !== 'all' && <span className="text-cyan-400 font-medium">&bull; Scopus Linked: {filters.scopus_linked}</span>}
                        </p>
                      </div>
                    </div>
                    <p className="text-slate-400 text-[11px] mt-0.5 flex flex-wrap items-center gap-2">
                      {items[0]?.source_authors && <span>{items[0].source_authors} ({items[0].source_year || 'N/A'}) &bull;</span>}
                      <span>Showing <strong className="text-white font-semibold">{totalMatches}</strong> total references</span>
                      {filters.status && <span className="text-amber-400 font-medium">&bull; Filtered by Status: {filters.status}</span>}
                      {filters.needs_review !== 'all' && <span className="text-amber-400 font-medium">&bull; Review Queue: {filters.needs_review}</span>}
                      {filters.scopus_linked !== 'all' && <span className="text-cyan-400 font-medium">&bull; Scopus Linked: {filters.scopus_linked}</span>}
                    </p>

                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => handleFilterBySource('')}
                        className="px-3.5 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white font-semibold transition text-xs shadow-sm flex items-center gap-1.5 cursor-pointer"
                      >
                        <RotateCcw className="w-3.5 h-3.5" />
                        <span>Show All Manuscripts ({stats?.total_documents || 841})</span>
                      </button>
                    </div>
                  </div>
                </div>
                )}

                <div className="flex items-center gap-2">
                  <button
                    onClick={() => handleFilterBySource('')}
                    className="px-3.5 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white font-semibold transition text-xs shadow-sm flex items-center gap-1.5 cursor-pointer"
                  >
                    <RotateCcw className="w-3.5 h-3.5" />
                    <span>Show All Manuscripts ({stats?.total_documents || 864})</span>
                  </button>
                </div>
              </div>
                {/* Reference Table Grid */}
                <ReferenceTable
                  items={items}
                  loading={loading}
                  onSelectReference={(id, data) => handleSelectReference(id, data)}
                  onFilterBySource={handleFilterBySource}
                />

                {/* Pagination Controls */}
                <Pagination
                  page={filters.page}
                  totalPages={totalPages}
                  total={totalMatches}
                  pageSize={filters.page_size}
                  onPageChange={(p) => setFilters((prev) => ({ ...prev, page: p }))}
                  onPageSizeChange={(sz) => setFilters((prev) => ({ ...prev, page_size: sz, page: 1 }))}
                />
              </>
            )}

            {/* Reference Table Grid */}
            <ReferenceTable
              items={items}
              loading={loading}
              onSelectReference={(id, data) => handleSelectReference(id, data)}
              onFilterBySource={handleFilterBySource}
            />

            {/* Pagination Controls */}
            <Pagination
              page={filters.page}
              totalPages={totalPages}
              total={totalMatches}
              pageSize={filters.page_size}
              onPageChange={(p) => setFilters((prev) => ({ ...prev, page: p }))}
              onPageSizeChange={(sz) => setFilters((prev) => ({ ...prev, page_size: sz, page: 1 }))}
            />
          </>
        )}
      </main>

      {/* Slide-Over Reference Detail Drawer */}
      <ReferenceDrawer
        referenceId={selectedReferenceId}
        referenceData={selectedReferenceData}
        onClose={() => {
          setSelectedReferenceId(null);
          setSelectedReferenceData(null);
        }}
        onUpdate={handleReviewUpdated}
      />

      {/* Footer */}
      <footer className="border-t border-slate-800/80 py-4 text-center text-xs text-slate-500">
        Scientometric Reference Validation Studio &bull; Elsevier Scopus Ground-Truth Engine &bull; Sub-10ms Indexed SQLite Engine
      </footer>
    </div>
  );
}
