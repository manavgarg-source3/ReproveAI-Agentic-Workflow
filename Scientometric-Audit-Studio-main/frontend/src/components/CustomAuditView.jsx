import React, { useState } from 'react';
import { 
  ArrowLeft, 
  Upload, 
  FileSpreadsheet, 
  BookOpen, 
  Sparkles, 
  CheckCircle2, 
  AlertTriangle, 
  XCircle, 
  FileText, 
  Download, 
  Search, 
  X, 
  RotateCcw,
  ExternalLink,
  ChevronDown,
  ChevronRight,
  ShieldCheck,
  Eye,
  Check,
  Filter,
  Layers,
  AlertCircle,
  Hash,
  Link2,
  FileSearch,
  CheckCheck
} from 'lucide-react';

const STATUS_BADGE_STYLES = {
  VALID_CORRECT: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/40',
  SCOPUS_LINKED_NO_DOI: 'bg-cyan-500/15 text-cyan-300 border-cyan-500/40',
  SCOPUS_UNLINKED: 'bg-amber-500/15 text-amber-300 border-amber-500/40',
  DOI_RECOVERED: 'bg-purple-500/15 text-purple-300 border-purple-500/40',
  ACCESS_RESTRICTED: 'bg-blue-500/15 text-blue-300 border-blue-500/40',
  BROKEN_URL: 'bg-rose-500/15 text-rose-300 border-rose-500/40',
  VALID_DOI_WRONG_REFERENCE: 'bg-red-600/30 text-red-200 border-red-500/60 font-black animate-pulse',
  DOI_RECOVERY_UNCERTAIN: 'bg-orange-500/15 text-orange-300 border-orange-500/40',
  DOI_MISSING: 'bg-slate-700/40 text-slate-300 border-slate-600/40',
  UNVERIFIED: 'bg-slate-800 text-slate-400 border-slate-700',
};

const STANCE_BADGE_STYLES = {
  METHODOLOGY: 'bg-blue-500/20 text-blue-300 border-blue-500/40',
  BACKGROUND: 'bg-slate-700/50 text-slate-300 border-slate-600/40',
  COMPARISON: 'bg-purple-500/20 text-purple-300 border-purple-500/40',
  CRITIQUE: 'bg-rose-500/25 text-rose-300 border-rose-500/50 font-bold',
  CORROBORATION: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40',
};

function renderReviewBadge(row) {
  if (!row.needs_human_review) {
    return (
      <span className="inline-flex items-center gap-1 text-[10px] font-semibold px-2 py-0.5 rounded-full bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">
        <CheckCircle2 className="w-2.5 h-2.5" /> Auto-Approved
      </span>
    );
  }

  switch (row.final_status) {
    case 'SCOPUS_UNLINKED':
      return (
        <span className="inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full bg-amber-500/20 text-amber-300 border border-amber-500/40 shadow-xs">
          <AlertTriangle className="w-2.5 h-2.5 text-amber-400" /> Review: Unlinked in Scopus
        </span>
      );
    case 'DOI_RECOVERED':
      return (
        <span className="inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full bg-purple-500/20 text-purple-300 border border-purple-500/40 shadow-xs">
          <Sparkles className="w-2.5 h-2.5 text-purple-400" /> Review: External Recovered DOI
        </span>
      );
    case 'VALID_DOI_WRONG_REFERENCE':
      return (
        <span className="inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full bg-red-600/30 text-red-200 border border-red-500/60 animate-pulse shadow-xs">
          <AlertTriangle className="w-2.5 h-2.5 text-red-400" /> Review: Wrong DOI Discrepancy
        </span>
      );
    case 'BROKEN_URL':
      return (
        <span className="inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full bg-rose-500/20 text-rose-300 border border-rose-500/40 shadow-xs">
          <XCircle className="w-2.5 h-2.5 text-rose-400" /> Review: Broken Link (404)
        </span>
      );
    case 'DOI_RECOVERY_UNCERTAIN':
      return (
        <span className="inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full bg-orange-500/20 text-orange-300 border border-orange-500/40 shadow-xs">
          <AlertTriangle className="w-2.5 h-2.5 text-orange-400" /> Review: Uncertain Candidate
        </span>
      );
    default:
      return (
        <span className="inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full bg-amber-500/20 text-amber-300 border border-amber-500/40 shadow-xs">
          <AlertTriangle className="w-2.5 h-2.5 text-amber-400" /> Human Review Required
        </span>
      );
  }
}

function highlightMarker(context, marker) {
  if (!context || !marker) return context;
  const parts = context.split(marker);
  if (parts.length <= 1) return context;
  return (
    <span>
      {parts.map((part, i) => (
        <React.Fragment key={i}>
          {part}
          {i < parts.length - 1 && (
            <mark className="bg-cyan-500/30 text-cyan-200 px-1 py-0.5 rounded font-mono font-bold border border-cyan-400/40">
              {marker}
            </mark>
          )}
        </React.Fragment>
      ))}
    </span>
  );
}

export default function CustomAuditView({ onBack, onSelectReference }) {
  const [scopusLink, setScopusLink] = useState('');
  const [file, setFile] = useState(null);
  const [loading, setLoading] = useState(false);
  const [progressText, setProgressText] = useState('');
  const [errorMsg, setErrorMsg] = useState('');
  const [resultData, setResultData] = useState(null);
  const [expandedRows, setExpandedRows] = useState({});

  // Sub-filters for the results view
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [scopusFilter, setScopusFilter] = useState('all');
  const [reviewFilter, setReviewFilter] = useState('all');
  const [activeTab, setActiveTab] = useState('references'); // 'references' or 'in_text'
  const [inTextSearch, setInTextSearch] = useState('');
  const [inTextStatusFilter, setInTextStatusFilter] = useState('all'); // 'all', 'linked', 'missing'

  const handleFileChange = (e) => {
    if (e.target.files && e.target.files[0]) {
      setFile(e.target.files[0]);
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      setFile(e.dataTransfer.files[0]);
    }
  };

  const handleSubmit = async (e) => {
    if (e) e.preventDefault();
    if (!scopusLink.trim() && !file) {
      setErrorMsg('Please enter a Scopus link or select a CSV/Excel file to upload.');
      return;
    }

    setLoading(true);
    setErrorMsg('');
    setProgressText('Submitting input data to Scientometric Validator...');

    try {
      const formData = new FormData();
      if (scopusLink.trim()) {
        formData.append('scopus_link', scopusLink.trim());
      }
      if (file) {
        formData.append('file', file);
      }

      setProgressText('Resolving Scopus ground truth & validating references...');

      const response = await fetch('/api/custom-audit/run', {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        const errJson = await response.json().catch(() => ({}));
        throw new Error(errJson.detail || `Server error (HTTP ${response.status})`);
      }

      const data = await response.json();
      setResultData(data);
    } catch (err) {
      console.error('Custom audit run failed:', err);
      setErrorMsg(err.message || 'Validation process failed. Please check your inputs.');
    } finally {
      setLoading(false);
      setProgressText('');
    }
  };

  const handleReset = () => {
    setResultData(null);
    setScopusLink('');
    setFile(null);
    setErrorMsg('');
    setSearchQuery('');
    setStatusFilter('');
    setScopusFilter('all');
    setReviewFilter('all');
    setActiveTab('references');
    setInTextSearch('');
    setInTextStatusFilter('all');
  };

  const toggleRowExpand = (refId) => {
    setExpandedRows((prev) => ({ ...prev, [refId]: !prev[refId] }));
  };

  // Filtered items from resultData
  const items = (resultData?.items || []).filter((r) => {
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      const match =
        (r.raw_reference && r.raw_reference.toLowerCase().includes(q)) ||
        (r.resolved_title && r.resolved_title.toLowerCase().includes(q)) ||
        (r.normalized_doi && r.normalized_doi.toLowerCase().includes(q)) ||
        (r.resolved_authors && r.resolved_authors.toLowerCase().includes(q)) ||
        (r.reference_id && r.reference_id.toLowerCase().includes(q));
      if (!match) return false;
    }
    if (statusFilter && r.final_status !== statusFilter) {
      return false;
    }
    if (scopusFilter === 'true' && !r.scopus_link_valid) return false;
    if (scopusFilter === 'false' && r.scopus_link_valid) return false;
    if (reviewFilter === 'true' && !r.needs_human_review) return false;
    if (reviewFilter === 'false' && r.needs_human_review) return false;
    return true;
  });

  // Filtered in-text citations from resultData.document_diagnostics
  const inTextCitations = resultData?.document_diagnostics?.in_text_citations || [];
  const bibRefNumbers = new Set((resultData?.items || []).map((r) => Number(r.reference_no)));

  const filteredInText = inTextCitations.filter((c) => {
    if (inTextSearch.trim()) {
      const q = inTextSearch.toLowerCase();
      const match =
        (c.marker && c.marker.toLowerCase().includes(q)) ||
        (c.context && c.context.toLowerCase().includes(q)) ||
        (c.type && c.type.toLowerCase().includes(q)) ||
        (c.author && c.author.toLowerCase().includes(q));
      if (!match) return false;
    }

    const isMissing = (c.unrolled_keys && c.unrolled_keys.length > 0)
      ? c.unrolled_keys.some((k) => !bibRefNumbers.has(k))
      : false;

    if (inTextStatusFilter === 'linked' && isMissing) return false;
    if (inTextStatusFilter === 'missing' && !isMissing) return false;

    return true;
  });

  return (
    <div className="space-y-5">
      
      {/* Navigation & Header */}
      <div className="flex flex-wrap items-center justify-between gap-4 bg-[#0e1628]/95 border border-slate-800/90 rounded-xl p-4 shadow-xl">
        <div className="flex items-center gap-3">
          <button
            onClick={onBack}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-700/80 hover:bg-slate-800 text-slate-300 hover:text-white transition text-xs font-semibold shadow-xs cursor-pointer"
          >
            <ArrowLeft className="w-4 h-4" />
            <span>Back to Corpus Dashboard</span>
          </button>
          <div>
            <h2 className="text-base font-bold text-white flex items-center gap-2">
              <span>Custom Paper & Data Audit Studio</span>
              <span className="text-[10px] font-bold uppercase px-2 py-0.5 rounded-full bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">
                On-Demand Pipeline
              </span>
            </h2>
            <p className="text-xs text-slate-400">
              Submit a Scopus publication link, upload your own XLS/CSV file, or combine both to run the automated scientometric validation pipeline.
            </p>
          </div>
        </div>

        {resultData && (
          <div className="flex items-center gap-2">
            <a
              href={resultData.excel_download_url}
              target="_blank"
              rel="noreferrer"
              className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white transition text-xs font-semibold shadow-md"
            >
              <FileSpreadsheet className="w-3.5 h-3.5" />
              <span>Download Excel Report (.xlsx)</span>
            </a>
            <a
              href={resultData.csv_download_url}
              target="_blank"
              rel="noreferrer"
              className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-slate-800 border border-slate-700 hover:bg-slate-700 text-slate-200 transition text-xs font-semibold shadow-sm"
            >
              <Download className="w-3.5 h-3.5" />
              <span>CSV (.csv)</span>
            </a>
            <button
              onClick={handleReset}
              className="p-1.5 rounded-lg bg-slate-900 border border-slate-700 text-slate-400 hover:text-white hover:bg-slate-800 transition text-xs cursor-pointer"
              title="Reset & Audit Another Paper"
            >
              <RotateCcw className="w-4 h-4" />
            </button>
          </div>
        )}
      </div>

      {/* Input Submission Card (Hidden if results already present, unless user clicks new run) */}
      {!resultData && (
        <div className="bg-[#0e1628]/95 border border-slate-800/90 rounded-xl p-6 shadow-xl space-y-6">
          
          {errorMsg && (
            <div className="p-3.5 rounded-lg bg-rose-950/50 border border-rose-500/40 text-xs text-rose-200 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0" />
                <span>{errorMsg}</span>
              </div>
              <button onClick={() => setErrorMsg('')} className="text-rose-400 hover:text-white">
                <X className="w-4 h-4" />
              </button>
            </div>
          )}

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            
            {/* Option 1: Scopus Link Input */}
            <div className="space-y-3 p-5 rounded-xl bg-slate-900/70 border border-slate-800 flex flex-col justify-between">
              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <label className="text-xs font-bold text-slate-200 uppercase tracking-wider flex items-center gap-1.5">
                    <BookOpen className="w-4 h-4 text-indigo-400" />
                    Option 1: Scopus Publication Link or EID
                  </label>
                  <span className="text-[10px] text-slate-400 bg-slate-800 px-2 py-0.5 rounded">Scopus API / Cache</span>
                </div>
                <p className="text-xs text-slate-400 mb-3">
                  Paste the publication URL, abstract URL, or EID. The pipeline will automatically retrieve and audit the reference list.
                </p>

                <input
                  type="text"
                  value={scopusLink}
                  onChange={(e) => setScopusLink(e.target.value)}
                  placeholder="e.g. https://www.scopus.com/pages/publications/85118881384?origin=resultslist"
                  className="w-full px-3.5 py-2.5 bg-slate-950 border border-slate-700/90 rounded-lg text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 shadow-inner font-mono"
                />

                {/* Quick 1-click presets */}
                <div className="flex flex-wrap items-center gap-2 mt-3 pt-3 border-t border-slate-800/80 text-[11px]">
                  <span className="text-slate-500 text-[10px] font-bold uppercase">Quick Samples:</span>
                  <button
                    type="button"
                    onClick={() => setScopusLink('https://www.scopus.com/pages/publications/85118881384?origin=resultslist')}
                    className="px-2.5 py-1 rounded bg-slate-800/90 hover:bg-indigo-600 text-slate-300 hover:text-white transition cursor-pointer"
                  >
                    Paper 1: IISERs (85118881384)
                  </button>
                  <button
                    type="button"
                    onClick={() => setScopusLink('https://www.scopus.com/pages/publications/105042346360?origin=resultslist')}
                    className="px-2.5 py-1 rounded bg-slate-800/90 hover:bg-indigo-600 text-slate-300 hover:text-white transition cursor-pointer"
                  >
                    Paper 2: Patent Analysis (105042346360)
                  </button>
                </div>
              </div>
            </div>

            {/* Option 2: Upload Manuscript or Reference Table */}
            <div className="space-y-3 p-5 rounded-xl bg-slate-900/70 border border-slate-800 flex flex-col justify-between">
              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <label className="text-xs font-bold text-slate-200 uppercase tracking-wider flex items-center gap-1.5">
                    <Upload className="w-4 h-4 text-cyan-400" />
                    Option 2: Upload Manuscript (PDF / Word) or Spreadsheet
                  </label>
                  <span className="text-[10px] text-cyan-300 bg-cyan-950/60 border border-cyan-500/30 px-2 py-0.5 rounded font-mono font-semibold">.pdf, .docx, .xlsx, .csv</span>
                </div>
                <p className="text-xs text-slate-400 mb-3">
                  Upload a research paper in <strong>PDF</strong> or <strong>Word (.docx)</strong> to audit citation styles and in-text references, or upload a reference spreadsheet.
                </p>

                {/* Dropzone */}
                <div
                  onDragOver={(e) => e.preventDefault()}
                  onDrop={handleDrop}
                  className="relative border-2 border-dashed border-slate-700 hover:border-cyan-500/60 rounded-xl p-6 text-center bg-slate-950/60 transition cursor-pointer group"
                  onClick={() => document.getElementById('file-upload-input').click()}
                >
                  <input
                    id="file-upload-input"
                    type="file"
                    accept=".pdf,.docx,.doc,.xlsx,.xls,.csv"
                    onChange={handleFileChange}
                    className="hidden"
                  />
                  {file ? (
                    <div className="flex items-center justify-center gap-3">
                      {file.name.toLowerCase().endsWith('.pdf') ? (
                        <FileText className="w-8 h-8 text-rose-400 shrink-0" />
                      ) : file.name.toLowerCase().endsWith('.docx') || file.name.toLowerCase().endsWith('.doc') ? (
                        <FileText className="w-8 h-8 text-blue-400 shrink-0" />
                      ) : (
                        <FileSpreadsheet className="w-8 h-8 text-cyan-400 shrink-0" />
                      )}
                      <div className="text-left truncate">
                        <div className="font-semibold text-slate-200 text-xs truncate max-w-xs">{file.name}</div>
                        <div className="text-[10px] text-slate-400">
                          {(file.size / 1024).toFixed(1)} KB &bull;{' '}
                          <span className="text-emerald-400 font-semibold">
                            {file.name.toLowerCase().endsWith('.pdf') ? 'PDF Research Paper' : file.name.toLowerCase().endsWith('.docx') ? 'Word Manuscript' : 'Reference Spreadsheet'}
                          </span>
                        </div>
                      </div>
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          setFile(null);
                        }}
                        className="p-1 hover:text-white text-slate-400"
                        title="Remove file"
                      >
                        <X className="w-4 h-4" />
                      </button>
                    </div>
                  ) : (
                    <div>
                      <Upload className="w-8 h-8 text-slate-500 group-hover:text-cyan-400 group-hover:scale-110 transition mx-auto mb-2" />
                      <div className="text-xs font-semibold text-slate-300">
                        Drag &amp; drop your <strong className="text-cyan-300">PDF, Word (.docx)</strong> or spreadsheet here, or <span className="text-cyan-400 underline">browse</span>
                      </div>
                      <div className="text-[10px] text-slate-500 mt-1">
                        Detects citation styles, in-text citation gaps, Scopus links &amp; DOI accuracy
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </div>

          </div>

          {/* Submit Action */}
          <div className="pt-4 border-t border-slate-800 flex items-center justify-between">
            <div className="text-xs text-slate-400">
              <span>You can submit a <strong>Scopus link alone</strong>, upload a <strong>file alone</strong>, or provide <strong>both</strong> to cross-validate.</span>
            </div>

            <button
              onClick={handleSubmit}
              disabled={loading || (!scopusLink.trim() && !file)}
              className={`px-6 py-2.5 rounded-xl font-bold text-xs flex items-center gap-2 transition shadow-lg ${
                loading || (!scopusLink.trim() && !file)
                  ? 'bg-slate-800 text-slate-500 cursor-not-allowed border border-slate-700'
                  : 'bg-gradient-to-r from-indigo-600 via-indigo-500 to-cyan-500 hover:from-indigo-500 hover:to-cyan-400 text-white ring-1 ring-white/20 hover:scale-102 cursor-pointer shadow-indigo-600/30'
              }`}
            >
              {loading ? (
                <>
                  <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                  <span>{progressText || 'Processing Validation Pipeline...'}</span>
                </>
              ) : (
                <>
                  <Sparkles className="w-4 h-4" />
                  <span>Run Automated Validation Pipeline</span>
                </>
              )}
            </button>
          </div>

        </div>
      )}

      {/* Results View */}
      {resultData && (
        <div className="space-y-5 animate-fade-in">
          
          {/* Paper Info Banner */}
          <div className="bg-gradient-to-r from-indigo-950/70 via-[#0e172e] to-slate-900 border border-indigo-500/40 px-5 py-4 rounded-xl shadow-xl flex flex-wrap items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-indigo-600/30 border border-indigo-400/30 flex items-center justify-center shrink-0">
                <BookOpen className="w-5 h-5 text-indigo-300" />
              </div>
              <div>
                <div className="flex flex-wrap items-center gap-2">
                  <h3 className="font-bold text-white text-base">
                    {resultData.source_info?.source_title || 'Audited Paper References'}
                  </h3>
                  <span className="font-mono text-xs px-2.5 py-0.5 rounded bg-indigo-900/60 text-indigo-300 border border-indigo-500/40">
                    {resultData.source_info?.source_eid}
                  </span>
                </div>
                <p className="text-slate-400 text-xs mt-0.5">
                  {resultData.source_info?.source_authors && <span>{resultData.source_info.source_authors} ({resultData.source_info.source_year || 'N/A'}) &bull; </span>}
                  <span>Job ID: <strong className="font-mono text-slate-300">{resultData.job_id}</strong> &bull; </span>
                  <span>Total References: <strong className="text-white font-semibold">{resultData.stats?.total_references}</strong></span>
                </p>
              </div>
            </div>

            <div className="flex items-center gap-2">
              <button
                onClick={handleReset}
                className="px-3.5 py-1.5 rounded-lg bg-slate-800 border border-slate-700 hover:bg-slate-700 text-slate-200 transition text-xs font-semibold shadow-sm flex items-center gap-1.5 cursor-pointer"
              >
                <RotateCcw className="w-3.5 h-3.5" />
                <span>Audit Another Paper</span>
              </button>
            </div>
          </div>

          {/* Manuscript Citation Style & Integrity Diagnostics (Only when manuscript uploaded) */}
          {resultData.document_diagnostics && (
            <div className="bg-gradient-to-r from-slate-900 via-[#101a36] to-slate-900 border border-cyan-500/30 rounded-xl p-5 shadow-xl space-y-4">
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800/80 pb-3">
                <div className="flex items-center gap-2.5">
                  <div className="w-8 h-8 rounded-lg bg-cyan-500/20 border border-cyan-400/30 flex items-center justify-center">
                    <FileSearch className="w-4 h-4 text-cyan-400" />
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-bold text-white uppercase tracking-wider">
                        Manuscript Citation Audit &amp; Consistency Report
                      </span>
                      <span className="text-[10px] font-mono font-bold px-2 py-0.5 rounded bg-cyan-950 text-cyan-300 border border-cyan-500/40 uppercase">
                        {resultData.document_diagnostics.file_type || 'MANUSCRIPT'}
                      </span>
                    </div>
                    <p className="text-[11px] text-slate-400">
                      Cross-referenced in-text citation markers against the extracted bibliography section.
                    </p>
                  </div>
                </div>

                <div className="flex items-center gap-3 text-xs text-slate-300">
                  {resultData.document_diagnostics.page_count && (
                    <span className="px-2.5 py-1 rounded bg-slate-800/80 border border-slate-700/60 font-mono text-[11px]">
                      📄 {resultData.document_diagnostics.page_count} Pages
                    </span>
                  )}
                  {resultData.document_diagnostics.word_count && (
                    <span className="px-2.5 py-1 rounded bg-slate-800/80 border border-slate-700/60 font-mono text-[11px]">
                      📝 {resultData.document_diagnostics.word_count.toLocaleString()} Words
                    </span>
                  )}
                </div>
              </div>

              {/* Warnings / Scanned alert if any */}
              {resultData.document_diagnostics.is_scanned && (
                <div className="p-3 rounded-lg bg-amber-950/40 border border-amber-500/40 text-xs text-amber-200 flex items-center gap-2">
                  <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0" />
                  <span>
                    <strong>Low text density detected:</strong> This manuscript may be an image or scanned PDF. High-confidence OCR is recommended.
                  </span>
                </div>
              )}

              {/* 4 Diagnostic Metrics */}
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3.5">
                {/* 1. Citation Style */}
                <div className="p-3.5 rounded-xl bg-slate-950/70 border border-indigo-500/30">
                  <div className="text-[10px] uppercase font-bold text-slate-400 mb-1 flex items-center justify-between">
                    <span>Citation Style</span>
                    <span className="text-[9px] px-1.5 py-0.2 rounded bg-indigo-900/60 text-indigo-300 font-mono">
                      {resultData.document_diagnostics.citation_style || 'AUTO'}
                    </span>
                  </div>
                  <div className="text-sm font-extrabold text-white line-clamp-1">
                    {resultData.document_diagnostics.citation_style_display || 'Unknown Style'}
                  </div>
                  <div className="text-[11px] text-slate-400 mt-1">
                    {resultData.document_diagnostics.total_in_text_citations} markers &bull; {resultData.document_diagnostics.distinct_keys_cited} unique keys
                  </div>
                </div>

                {/* 2. Consistency Score */}
                <div className={`p-3.5 rounded-xl bg-slate-950/70 border ${
                  (resultData.document_diagnostics.consistency_score || 0) >= 90
                    ? 'border-emerald-500/30'
                    : (resultData.document_diagnostics.consistency_score || 0) >= 70
                    ? 'border-amber-500/30'
                    : 'border-rose-500/30'
                }`}>
                  <div className="text-[10px] uppercase font-bold text-slate-400 mb-1 flex items-center justify-between">
                    <span>Citation Alignment</span>
                    <span className={`text-[9px] px-1.5 py-0.2 rounded font-mono font-bold ${
                      (resultData.document_diagnostics.consistency_score || 0) >= 90
                        ? 'bg-emerald-950 text-emerald-300'
                        : (resultData.document_diagnostics.consistency_score || 0) >= 70
                        ? 'bg-amber-950 text-amber-300'
                        : 'bg-rose-950 text-rose-300'
                    }`}>
                      {resultData.document_diagnostics.consistency_score}%
                    </span>
                  </div>
                  <div className="text-sm font-extrabold text-white flex items-center gap-1.5">
                    {(resultData.document_diagnostics.consistency_score || 0) >= 90 ? (
                      <>
                        <CheckCheck className="w-4 h-4 text-emerald-400" />
                        <span className="text-emerald-300">High Alignment</span>
                      </>
                    ) : (resultData.document_diagnostics.consistency_score || 0) >= 70 ? (
                      <>
                        <AlertTriangle className="w-4 h-4 text-amber-400" />
                        <span className="text-amber-300">Moderate Gaps</span>
                      </>
                    ) : (
                      <>
                        <XCircle className="w-4 h-4 text-rose-400" />
                        <span className="text-rose-300">Alignment Discrepancies</span>
                      </>
                    )}
                  </div>
                  <div className="text-[11px] text-slate-400 mt-1">
                    Text-to-bibliography matching ratio
                  </div>
                </div>

                {/* 3. Orphan References */}
                <div className={`p-3.5 rounded-xl bg-slate-950/70 border ${
                  resultData.document_diagnostics.orphan_count > 0 ? 'border-amber-500/40' : 'border-slate-800'
                }`}>
                  <div className="text-[10px] uppercase font-bold text-slate-400 mb-1 flex items-center justify-between">
                    <span>Orphan References</span>
                    {resultData.document_diagnostics.orphan_count > 0 ? (
                      <span className="text-[9px] px-1.5 py-0.2 rounded bg-amber-950 text-amber-300 font-mono font-bold">
                        {resultData.document_diagnostics.orphan_count} Uncited
                      </span>
                    ) : (
                      <span className="text-[9px] px-1.5 py-0.2 rounded bg-emerald-950 text-emerald-300 font-mono">
                        Clean
                      </span>
                    )}
                  </div>
                  <div className="text-sm font-extrabold text-white">
                    {resultData.document_diagnostics.orphan_count > 0 ? (
                      <span className="text-amber-300">{resultData.document_diagnostics.orphan_count} References in Bib</span>
                    ) : (
                      <span className="text-emerald-400 flex items-center gap-1">
                        <Check className="w-4 h-4" /> 0 Orphans (All cited)
                      </span>
                    )}
                  </div>
                  <div className="text-[11px] text-slate-400 mt-1 truncate" title={(resultData.document_diagnostics.orphan_references || []).join(', ')}>
                    {resultData.document_diagnostics.orphan_count > 0
                      ? `Refs: ${(resultData.document_diagnostics.orphan_references || []).slice(0, 5).join(', ')}${(resultData.document_diagnostics.orphan_references || []).length > 5 ? '...' : ''}`
                      : 'Every bibliography entry is cited'}
                  </div>
                </div>

                {/* 4. Missing In-Text Citations */}
                <div className={`p-3.5 rounded-xl bg-slate-950/70 border ${
                  resultData.document_diagnostics.missing_count > 0 ? 'border-rose-500/40' : 'border-slate-800'
                }`}>
                  <div className="text-[10px] uppercase font-bold text-slate-400 mb-1 flex items-center justify-between">
                    <span>Missing In-Text Keys</span>
                    {resultData.document_diagnostics.missing_count > 0 ? (
                      <span className="text-[9px] px-1.5 py-0.2 rounded bg-rose-950 text-rose-300 font-mono font-bold">
                        {resultData.document_diagnostics.missing_count} Missing
                      </span>
                    ) : (
                      <span className="text-[9px] px-1.5 py-0.2 rounded bg-emerald-950 text-emerald-300 font-mono">
                        Clean
                      </span>
                    )}
                  </div>
                  <div className="text-sm font-extrabold text-white">
                    {resultData.document_diagnostics.missing_count > 0 ? (
                      <span className="text-rose-300">{resultData.document_diagnostics.missing_count} Missing from Bib</span>
                    ) : (
                      <span className="text-emerald-400 flex items-center gap-1">
                        <Check className="w-4 h-4" /> 0 Missing (All resolved)
                      </span>
                    )}
                  </div>
                  <div className="text-[11px] text-slate-400 mt-1 truncate" title={(resultData.document_diagnostics.missing_references || []).join(', ')}>
                    {resultData.document_diagnostics.missing_count > 0
                      ? `Keys: ${(resultData.document_diagnostics.missing_references || []).slice(0, 5).join(', ')}${(resultData.document_diagnostics.missing_references || []).length > 5 ? '...' : ''}`
                      : 'All in-text citations exist in bibliography'}
                  </div>
                </div>
              </div>

              {/* Sequence Gaps Banner */}
              {resultData.document_diagnostics.sequence_gaps && resultData.document_diagnostics.sequence_gaps.length > 0 && (
                <div className="p-2.5 rounded-lg bg-blue-950/40 border border-blue-500/30 text-xs text-blue-200 flex items-center gap-2">
                  <Hash className="w-4 h-4 text-blue-400 shrink-0" />
                  <span>
                    <strong>Numeric Sequence Gaps:</strong> In-text citation numbering skips index [
                    {resultData.document_diagnostics.sequence_gaps.join(', ')}
                    ]. Check if citations were removed during drafting.
                  </span>
                </div>
              )}
            </div>
          )}

          {/* Scientometric Intelligence & Executive Audit Panel */}
          {resultData.scientometric_audit && (
            <div className="bg-gradient-to-r from-slate-900 via-[#0c1b33] to-slate-900 border border-indigo-500/40 rounded-xl p-5 shadow-2xl space-y-4">
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800/80 pb-3">
                <div className="flex items-center gap-2.5">
                  <div className="w-8 h-8 rounded-lg bg-indigo-500/20 border border-indigo-400/40 flex items-center justify-center">
                    <Sparkles className="w-4 h-4 text-cyan-300" />
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-bold text-white uppercase tracking-wider">
                        LLM Scientometric Intelligence &amp; Executive Audit
                      </span>
                      <span className="text-[10px] font-mono font-bold px-2 py-0.5 rounded bg-indigo-950 text-indigo-300 border border-indigo-500/40 uppercase">
                        Grade: {resultData.scientometric_audit.audit_grade || 'A'}
                      </span>
                    </div>
                    <p className="text-[11px] text-slate-400">
                      In-depth bibliometric indicator synthesis, Price's Index, citation half-life, and peer-review audit.
                    </p>
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  <span className={`text-xs font-bold px-2.5 py-1 rounded-full border ${
                    resultData.scientometric_audit.temporal_freshness_verdict === 'CUTTING_EDGE'
                      ? 'bg-emerald-500/15 text-emerald-300 border-emerald-500/40'
                      : resultData.scientometric_audit.temporal_freshness_verdict === 'BALANCED'
                      ? 'bg-cyan-500/15 text-cyan-300 border-cyan-500/40'
                      : 'bg-amber-500/15 text-amber-300 border-amber-500/40'
                  }`}>
                    Freshness: {resultData.scientometric_audit.temporal_freshness_verdict || 'BALANCED'}
                  </span>
                </div>
              </div>

              {/* Critical Integrity Alert Banner if fabricated/404 DOIs detected */}
              {(resultData.scientometric_audit.indicators?.invalid_dois > 0 || resultData.scientometric_audit.indicators?.discrepancies > 0) && (
                <div className="p-3.5 rounded-lg bg-rose-950/60 border border-rose-500/50 text-xs text-rose-200 flex items-start gap-3 shadow-lg">
                  <AlertTriangle className="w-5 h-5 text-rose-400 shrink-0 mt-0.5" />
                  <div className="space-y-0.5">
                    <div className="font-bold text-rose-100 flex items-center gap-2">
                      <span>Citation Integrity Alert: {resultData.scientometric_audit.indicators.invalid_dois} Failed DOIs (HTTP 404)</span>
                      <span className="text-[9px] px-2 py-0.5 rounded bg-rose-900/90 text-rose-200 font-mono font-bold uppercase">
                        High Hallucination Risk
                      </span>
                    </div>
                    <p className="text-[11px] text-rose-300/90 leading-relaxed">
                      Multiple cited DOIs do not exist on the global resolver (HTTP 404 Not Found), and {resultData.scientometric_audit.indicators?.discrepancies || 0} reference resolved to an unrelated work. This pattern commonly indicates unverified synthetic / AI-hallucinated citations.
                    </p>
                  </div>
                </div>
              )}

              {/* Scientometric Indicators Grid */}
              <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
                <div className="p-3 rounded-lg bg-slate-950/70 border border-slate-800">
                  <div className="text-[10px] uppercase font-bold text-slate-400">Price's Index (&le; 5 yrs)</div>
                  <div className="text-lg font-extrabold text-cyan-300 mt-0.5">
                    {resultData.scientometric_audit.indicators?.price_index || 0}%
                  </div>
                  <div className="text-[10px] text-slate-500">Literature freshness ratio</div>
                </div>

                <div className="p-3 rounded-lg bg-slate-950/70 border border-slate-800">
                  <div className="text-[10px] uppercase font-bold text-slate-400">Citation Half-Life</div>
                  <div className="text-lg font-extrabold text-indigo-300 mt-0.5">
                    {resultData.scientometric_audit.indicators?.median_citation_age || 0} yrs
                  </div>
                  <div className="text-[10px] text-slate-500">Median citation age</div>
                </div>

                <div className="p-3 rounded-lg bg-slate-950/70 border border-slate-800">
                  <div className="text-[10px] uppercase font-bold text-slate-400">Venue Diversity</div>
                  <div className="text-lg font-extrabold text-purple-300 mt-0.5">
                    {resultData.scientometric_audit.indicators?.venue_diversity_score || 1.0}
                  </div>
                  <div className="text-[10px] text-slate-500">Shannon entropy (0-1.0)</div>
                </div>

                <div className="p-3 rounded-lg bg-slate-950/70 border border-slate-800">
                  <div className="text-[10px] uppercase font-bold text-slate-400">Year Range</div>
                  <div className="text-lg font-extrabold text-emerald-300 mt-0.5">
                    {resultData.scientometric_audit.indicators?.min_year || 'N/A'} - {resultData.scientometric_audit.indicators?.max_year || 'N/A'}
                  </div>
                  <div className="text-[10px] text-slate-500">Chronological span</div>
                </div>

                <div className={`p-3 rounded-lg bg-slate-950/70 border ${
                  (resultData.scientometric_audit.indicators?.invalid_dois || 0) > 0 ? 'border-rose-500/40' : 'border-slate-800'
                }`}>
                  <div className="text-[10px] uppercase font-bold text-slate-400">DOI Resolution</div>
                  <div className={`text-lg font-extrabold mt-0.5 ${
                    (resultData.scientometric_audit.indicators?.invalid_dois || 0) > 0 ? 'text-rose-400' : 'text-emerald-400'
                  }`}>
                    {resultData.scientometric_audit.indicators?.resolving_dois || 0} / {resultData.scientometric_audit.indicators?.total_references || 0}
                  </div>
                  <div className="text-[10px] text-slate-500">
                    {(resultData.scientometric_audit.indicators?.invalid_dois || 0) > 0
                      ? `${resultData.scientometric_audit.indicators.invalid_dois} Failed (404)`
                      : 'All DOIs verified'}
                  </div>
                </div>
              </div>

              {/* Citation Intent Breakdown Bar */}
              {resultData.scientometric_audit.indicators?.intent_distribution && (
                <div className="p-3 rounded-lg bg-slate-950/70 border border-slate-800 space-y-2">
                  <div className="flex items-center justify-between text-xs font-bold text-slate-300">
                    <span>In-Text Citation Stance Profile</span>
                    <span className="text-[10px] text-slate-400 font-normal">Methodology vs Background vs Critique</span>
                  </div>
                  <div className="flex flex-wrap items-center gap-2 text-[11px]">
                    {Object.entries(resultData.scientometric_audit.indicators.intent_distribution).map(([intent, count]) => (
                      <span key={intent} className={`px-2.5 py-0.5 rounded-full border font-bold ${
                        STANCE_BADGE_STYLES[intent] || 'bg-slate-800 text-slate-300 border-slate-700'
                      }`}>
                        {intent}: {count}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Executive Summary Narrative */}
              <div className="p-4 rounded-xl bg-slate-950/90 border border-slate-800/90 space-y-2.5 text-xs text-slate-300 leading-relaxed">
                <div className="font-bold text-slate-100 flex items-center gap-2">
                  <BookOpen className="w-4 h-4 text-cyan-400" />
                  <span>Executive Bibliometric Assessment</span>
                </div>
                <p>{resultData.scientometric_audit.executive_summary}</p>
                {resultData.scientometric_audit.methodological_backbone && (
                  <div className="pt-2 border-t border-slate-800 text-slate-400">
                    <strong className="text-slate-200">Methodological Backbone: </strong>
                    {resultData.scientometric_audit.methodological_backbone}
                  </div>
                )}
                {resultData.scientometric_audit.potential_blind_spots && resultData.scientometric_audit.potential_blind_spots.length > 0 && (
                  <div className="pt-2 border-t border-slate-800 text-amber-300/90">
                    <strong className="text-amber-200">Audit Recommendations: </strong>
                    <ul className="list-disc pl-5 mt-1 space-y-1">
                      {resultData.scientometric_audit.potential_blind_spots.map((spot, idx) => (
                        <li key={idx}>{spot}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* KPI Summary Cards for this custom run */}
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3.5">
            {[
              {
                title: 'Total References',
                val: resultData.stats?.total_references || 0,
                sub: 'Extracted citations',
                badge: '100%',
                color: 'border-slate-800 bg-[#0e1628]/90 text-slate-100',
              },
              {
                title: 'Scopus Ground Truth',
                val: resultData.stats?.scopus_linked || 0,
                sub: `${resultData.stats?.scopus_linked_pct || 0}% verified in Scopus`,
                badge: 'Linked',
                color: 'border-emerald-500/20 bg-emerald-950/20 text-emerald-300',
              },
              {
                title: 'Scopus Unlinked',
                val: resultData.stats?.scopus_unlinked || 0,
                sub: 'Unlinked in Scopus index',
                badge: 'Unlinked',
                color: 'border-amber-500/20 bg-amber-950/20 text-amber-300',
              },
              {
                title: 'Resolving DOIs',
                val: resultData.stats?.resolving_dois || 0,
                sub: `${resultData.stats?.resolving_pct || 0}% active via resolver`,
                badge: 'Resolving',
                color: 'border-cyan-500/20 bg-cyan-950/20 text-cyan-300',
              },
              {
                title: 'Recovered DOIs',
                val: resultData.stats?.recovered_dois || 0,
                sub: 'Found via Crossref',
                badge: 'Recovered',
                color: 'border-purple-500/20 bg-purple-950/20 text-purple-300',
              },
              {
                title: 'Human Review Queue',
                val: resultData.stats?.needs_review || 0,
                sub: 'Requires triage / sign-off',
                badge: 'Flagged',
                color: 'border-rose-500/25 bg-rose-950/20 text-rose-300',
              },
            ].map((kpi, idx) => (
              <div key={idx} className={`p-4 rounded-xl border shadow-md ${kpi.color}`}>
                <div className="flex items-center justify-between text-[11px] uppercase font-bold text-slate-400 mb-1">
                  <span>{kpi.title}</span>
                  <span className="text-[10px] px-1.5 py-0.2 rounded bg-slate-800 text-slate-300">{kpi.badge}</span>
                </div>
                <div className="text-2xl font-extrabold font-mono text-white mb-1">
                  {kpi.val}
                </div>
                <div className="text-[11px] text-slate-400 truncate">{kpi.sub}</div>
              </div>
            ))}
          </div>

          {/* Tab Switcher: Validated References vs In-Text Matrix */}
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 pb-2">
            <div className="flex items-center gap-2">
              <button
                onClick={() => setActiveTab('references')}
                className={`px-4 py-2 rounded-xl text-xs font-bold transition flex items-center gap-2 cursor-pointer ${
                  activeTab === 'references'
                    ? 'bg-gradient-to-r from-indigo-600 to-indigo-700 text-white shadow-lg shadow-indigo-600/30'
                    : 'bg-slate-900/80 text-slate-400 hover:text-slate-200 hover:bg-slate-800 border border-slate-800'
                }`}
              >
                <BookOpen className="w-3.5 h-3.5" />
                <span>Validated Bibliography References</span>
                <span className="text-[10px] px-2 py-0.5 rounded-full bg-black/30 text-indigo-200 font-mono font-bold">
                  {items.length}
                </span>
              </button>

              {resultData.document_diagnostics && (
                <button
                  onClick={() => setActiveTab('in_text')}
                  className={`px-4 py-2 rounded-xl text-xs font-bold transition flex items-center gap-2 cursor-pointer ${
                    activeTab === 'in_text'
                      ? 'bg-gradient-to-r from-cyan-600 to-cyan-700 text-white shadow-lg shadow-cyan-600/30'
                      : 'bg-slate-900/80 text-slate-400 hover:text-slate-200 hover:bg-slate-800 border border-slate-800'
                  }`}
                >
                  <Layers className="w-3.5 h-3.5" />
                  <span>In-Text Citation Audit Matrix</span>
                  <span className="text-[10px] px-2 py-0.5 rounded-full bg-black/30 text-cyan-200 font-mono font-bold">
                    {resultData.document_diagnostics.total_in_text_citations || 0}
                  </span>
                </button>
              )}
            </div>

            {activeTab === 'in_text' && (
              <div className="text-xs text-slate-400">
                Extracted citation occurrences mapped to manuscript sentences and bibliography entries.
              </div>
            )}
          </div>

          {/* Tab 1: Validated References View */}
          {activeTab === 'references' && (
            <div className="space-y-4">
              {/* Filter Bar for Custom Results */}
              <div className="bg-[#0e1628]/95 border border-slate-800/90 rounded-xl p-3.5 shadow-xl flex flex-wrap items-center justify-between gap-3">
            <div className="flex flex-wrap items-center gap-2.5 flex-1 min-w-[280px]">
              {/* Search */}
              <div className="relative flex-1 min-w-[220px]">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400" />
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Search citation text, DOI, or title..."
                  className="w-full pl-8 pr-7 py-1.5 bg-slate-900 border border-slate-700 rounded-lg text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500 shadow-inner"
                />
                {searchQuery && (
                  <button onClick={() => setSearchQuery('')} className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-400 hover:text-white">
                    <X className="w-3.5 h-3.5" />
                  </button>
                )}
              </div>

              {/* Scopus Link Toggle */}
              <div className="flex items-center bg-slate-900 border border-slate-700/80 rounded-lg p-0.5 text-xs shadow-inner">
                <span className="px-2 text-slate-400 font-medium">Scopus:</span>
                {[
                  { id: 'all', label: 'All' },
                  { id: 'true', label: 'Linked' },
                  { id: 'false', label: 'Unlinked' },
                ].map((btn) => (
                  <button
                    key={btn.id}
                    onClick={() => setScopusFilter(btn.id)}
                    className={`px-2 py-0.5 rounded-md font-medium transition ${
                      scopusFilter === btn.id ? 'bg-indigo-600 text-white font-semibold' : 'text-slate-400 hover:text-slate-200'
                    }`}
                  >
                    {btn.label}
                  </button>
                ))}
              </div>

              {/* Review Filter */}
              <div className="flex items-center bg-slate-900 border border-slate-700/80 rounded-lg p-0.5 text-xs shadow-inner">
                <span className="px-2 text-slate-400 font-medium">Review:</span>
                {[
                  { id: 'all', label: 'All' },
                  { id: 'true', label: 'Queue' },
                  { id: 'false', label: 'Auto-Approved' },
                ].map((btn) => (
                  <button
                    key={btn.id}
                    onClick={() => setReviewFilter(btn.id)}
                    className={`px-2 py-0.5 rounded-md font-medium transition ${
                      reviewFilter === btn.id
                        ? btn.id === 'true' ? 'bg-amber-600 text-white font-semibold' : 'bg-emerald-600 text-white font-semibold'
                        : 'text-slate-400 hover:text-slate-200'
                    }`}
                  >
                    {btn.label}
                  </button>
                ))}
              </div>
            </div>

            <div className="text-xs text-slate-400">
              Showing <strong className="text-indigo-300 font-bold">{items.length}</strong> of {resultData.stats?.total_references} references
            </div>
          </div>

          {/* Interactive Reference Table */}
          <div className="w-full bg-[#0e1628]/95 border border-slate-800/90 rounded-xl shadow-xl overflow-hidden">
            <div className="overflow-x-auto w-full">
              <table className="w-full text-left border-collapse text-xs">
                <thead>
                  <tr className="bg-slate-900/95 text-slate-400 uppercase tracking-wider font-bold border-b border-slate-800 text-[11px]">
                    <th className="py-3 px-3 w-10 text-center"></th>
                    <th className="py-3 px-3 w-36">Reference ID</th>
                    <th className="py-3 px-3 w-32 text-center">Scopus Link</th>
                    <th className="py-3 px-3 w-44">Scientometric Status</th>
                    <th className="py-3 px-3 w-48">Audit Review Badge</th>
                    <th className="py-3 px-3 w-32 text-center">Citation Stance</th>
                    <th className="py-3 px-3 w-24 text-center">Title Sim</th>
                    <th className="py-3 px-3 w-24 text-center">Score</th>
                    <th className="py-3 px-3 w-48">DOI Status</th>
                    <th className="py-3 px-4">Resolved Publication / Decision Rationale</th>
                    <th className="py-3 px-3 w-24 text-center">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60">
                  {items.map((row) => {
                    const isScopusLinked = Boolean(row.scopus_link_valid);
                    const badgeStyle = STATUS_BADGE_STYLES[row.final_status] || 'bg-slate-800 text-slate-300';
                    const scorePct = Math.round((row.composite_score || 0) * 100);
                    const titleSimPct = Math.round((row.title_similarity || 0) * 100);
                    const isExpanded = Boolean(expandedRows[row.reference_id]);
                    const isOrphan = (resultData.document_diagnostics?.orphan_references || []).some(
                      (ref) => String(ref) === String(row.reference_no) || String(ref) === String(row.reference_id)
                    );

                    return (
                      <React.Fragment key={row.reference_id}>
                        <tr
                          className={`hover:bg-slate-800/40 transition-colors group cursor-pointer ${
                            isExpanded ? 'bg-indigo-950/20' : ''
                          }`}
                          onClick={() => toggleRowExpand(row.reference_id)}
                        >
                          {/* Expand chevron */}
                          <td className="py-3 px-2 text-center align-top text-slate-400">
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                toggleRowExpand(row.reference_id);
                              }}
                              className="p-1 hover:text-white transition cursor-pointer"
                            >
                              {isExpanded ? (
                                <ChevronDown className="w-4 h-4 text-indigo-400" />
                              ) : (
                                <ChevronRight className="w-4 h-4" />
                              )}
                            </button>
                          </td>

                          {/* Ref ID & Number */}
                          <td className="py-3 px-3 align-top font-mono text-xs">
                            <div className="font-bold text-indigo-300 group-hover:text-indigo-200">
                              {row.reference_id}
                            </div>
                            <div className="text-[10px] text-slate-500 font-semibold mt-0.5">
                              Citation #{row.reference_no}
                            </div>
                            {isOrphan && (
                              <div className="mt-1">
                                <span className="inline-flex items-center gap-1 text-[9px] font-bold px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-300 border border-amber-500/30" title="This reference appears in the bibliography but is never cited in the body of the manuscript.">
                                  <AlertTriangle className="w-2.5 h-2.5 text-amber-400" /> Uncited (Orphan)
                                </span>
                              </div>
                            )}
                          </td>

                          {/* Scopus Link */}
                          <td className="py-3 px-3 align-top text-center">
                            {isScopusLinked ? (
                              <div className="inline-flex flex-col items-center">
                                <span className="inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full bg-emerald-500/15 text-emerald-300 border border-emerald-500/30">
                                  <CheckCircle2 className="w-2.5 h-2.5" /> Scopus Linked
                                </span>
                                {row.scopus_reference_link && row.scopus_reference_link.startsWith('http') && (
                                  <a
                                    href={row.scopus_reference_link}
                                    target="_blank"
                                    rel="noreferrer"
                                    onClick={(e) => e.stopPropagation()}
                                    className="text-[10px] text-indigo-400 hover:text-indigo-300 inline-flex items-center gap-0.5 mt-1 underline font-medium"
                                  >
                                    Scopus Record <ExternalLink className="w-2.5 h-2.5" />
                                  </a>
                                )}
                              </div>
                            ) : (
                              <span className="inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full bg-amber-500/15 text-amber-300 border border-amber-500/30">
                                <AlertTriangle className="w-2.5 h-2.5" /> Scopus Unlinked
                              </span>
                            )}
                          </td>

                          {/* Status */}
                          <td className="py-3 px-3 align-top">
                            <span className={`inline-block px-2.5 py-0.5 rounded-full text-[10px] font-bold border ${badgeStyle}`}>
                              {row.final_status}
                            </span>
                          </td>

                          {/* Audit Badge */}
                          <td className="py-3 px-3 align-top">
                            {renderReviewBadge(row)}
                          </td>

                          {/* Citation Stance */}
                          <td className="py-3 px-3 align-top text-center">
                            {row.citation_intent ? (
                              <span
                                className={`inline-block px-2 py-0.5 rounded-full text-[10px] font-bold border ${
                                  STANCE_BADGE_STYLES[row.citation_intent] || 'bg-slate-800 text-slate-300 border-slate-700'
                                }`}
                                title={row.citation_rationale || row.in_text_context || ''}
                              >
                                {row.citation_intent}
                              </span>
                            ) : (
                              <span className="text-slate-500 text-[10px]">-</span>
                            )}
                          </td>

                          {/* Title Similarity */}
                          <td className="py-3 px-3 align-top text-center font-mono">
                            {row.title_similarity !== undefined && row.title_similarity !== null ? (
                              <span className={`inline-block px-2 py-0.5 rounded text-[11px] font-bold ${
                                titleSimPct >= 85 ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30' :
                                titleSimPct >= 60 ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/30' :
                                'bg-amber-500/20 text-amber-300 border border-amber-500/30'
                              }`}>
                                {titleSimPct}%
                              </span>
                            ) : (
                              <span className="text-slate-500 text-[10px] italic">N/A</span>
                            )}
                          </td>

                          {/* Score */}
                          <td className="py-3 px-3 align-top text-center font-mono">
                            <span className={`font-bold ${scorePct >= 85 ? 'text-emerald-400' : scorePct >= 65 ? 'text-cyan-400' : 'text-amber-400'}`}>
                              {scorePct}%
                            </span>
                          </td>

                          {/* DOI */}
                          <td className="py-3 px-3 align-top font-mono text-[11px]">
                            {row.normalized_doi ? (
                              <div>
                                <a
                                  href={`https://doi.org/${row.normalized_doi}`}
                                  target="_blank"
                                  rel="noreferrer"
                                  onClick={(e) => e.stopPropagation()}
                                  className="text-cyan-400 hover:text-cyan-300 hover:underline flex items-center gap-1"
                                >
                                  <span className="truncate max-w-[150px]">{row.normalized_doi}</span>
                                  <ExternalLink className="w-2.5 h-2.5 shrink-0" />
                                </a>
                                {row.doi_resolves ? (
                                  <span className="text-[10px] text-emerald-400 font-medium">Resolves (200 OK)</span>
                                ) : (
                                  <span className="text-[10px] text-rose-400 font-medium">Dead link / Unresolved</span>
                                )}
                              </div>
                            ) : (
                              <span className="text-slate-500 italic text-[10px]">No DOI registered</span>
                            )}
                          </td>

                          {/* Publication metadata */}
                          <td className="py-3 px-4 align-top">
                            {row.resolved_title ? (
                              <div className="font-medium text-slate-100 line-clamp-1">
                                {row.resolved_title}
                              </div>
                            ) : (
                              <div className="text-slate-400 line-clamp-1 italic">
                                "{row.raw_reference}"
                              </div>
                            )}
                            <div className="text-[11px] text-slate-400 line-clamp-1 mt-0.5">
                              {row.decision_rationale || 'Ground-truth verified via Scopus API.'}
                            </div>
                          </td>

                          {/* Inspect action */}
                          <td className="py-3 px-3 align-top text-center">
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                if (onSelectReference) onSelectReference(row.reference_id, row);
                              }}
                              className="px-2.5 py-1 rounded bg-slate-800 hover:bg-indigo-600 text-slate-300 hover:text-white transition text-[11px] font-semibold flex items-center gap-1 mx-auto cursor-pointer"
                            >
                              <Eye className="w-3 h-3" />
                              <span>Inspect</span>
                            </button>
                          </td>
                        </tr>

                        {/* Inline expanded details row */}
                        {isExpanded && (
                          <tr className="bg-slate-900/90 border-b border-indigo-500/30">
                            <td colSpan={10} className="p-4 pl-12">
                              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
                                <div>
                                  <span className="text-[10px] font-bold uppercase tracking-wider text-cyan-400 block mb-1">
                                    Verbatim Cited Reference
                                  </span>
                                  <blockquote className="p-2.5 rounded bg-slate-950 border-l-2 border-cyan-500 italic text-slate-200 text-xs">
                                    "{row.raw_reference}"
                                  </blockquote>
                                </div>
                                <div>
                                  <span className="text-[10px] font-bold uppercase tracking-wider text-emerald-400 block mb-1">
                                    Resolved Metadata &amp; Match Diagnostics
                                  </span>
                                  <div className="p-2.5 rounded bg-slate-950 border border-slate-800 space-y-1 text-slate-300">
                                    <div><strong className="text-slate-400">Title:</strong> {row.resolved_title || 'N/A'}</div>
                                    <div><strong className="text-slate-400">Authors:</strong> {row.resolved_authors || 'N/A'}</div>
                                    <div><strong className="text-slate-400">Journal/Venue:</strong> {row.resolved_journal || 'N/A'} ({row.resolved_year || 'N/A'})</div>
                                    <div><strong className="text-slate-400">Similarity:</strong> Title {Math.round((row.title_similarity || 0) * 100)}% &bull; Author {Math.round((row.author_similarity || 0) * 100)}% &bull; Score {scorePct}%</div>
                                  </div>
                                </div>
                              </div>
                            </td>
                          </tr>
                        )}
                      </React.Fragment>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

          {/* Tab 2: In-Text Citation Audit Matrix */}
          {activeTab === 'in_text' && resultData.document_diagnostics && (
            <div className="space-y-4">
              {/* Filter Bar for In-Text Citations */}
              <div className="bg-[#0e1628]/95 border border-slate-800/90 rounded-xl p-3.5 shadow-xl flex flex-wrap items-center justify-between gap-3">
                <div className="flex flex-wrap items-center gap-2.5 flex-1 min-w-[280px]">
                  {/* Search */}
                  <div className="relative flex-1 min-w-[220px]">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400" />
                    <input
                      type="text"
                      value={inTextSearch}
                      onChange={(e) => setInTextSearch(e.target.value)}
                      placeholder="Search citation marker or manuscript sentence context..."
                      className="w-full pl-8 pr-7 py-1.5 bg-slate-900 border border-slate-700 rounded-lg text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-cyan-500 shadow-inner"
                    />
                    {inTextSearch && (
                      <button onClick={() => setInTextSearch('')} className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-400 hover:text-white">
                        <X className="w-3.5 h-3.5" />
                      </button>
                    )}
                  </div>

                  {/* Status filter: All, Linked in Bib, Missing */}
                  <div className="flex items-center bg-slate-900 border border-slate-700/80 rounded-lg p-0.5 text-xs shadow-inner">
                    <span className="px-2 text-slate-400 font-medium">Filter:</span>
                    {[
                      { id: 'all', label: 'All Markers' },
                      { id: 'linked', label: 'In Bibliography' },
                      { id: 'missing', label: 'Missing from Bib' },
                    ].map((btn) => (
                      <button
                        key={btn.id}
                        onClick={() => setInTextStatusFilter(btn.id)}
                        className={`px-2.5 py-0.5 rounded-md font-medium transition cursor-pointer ${
                          inTextStatusFilter === btn.id
                            ? btn.id === 'missing'
                              ? 'bg-rose-600 text-white font-semibold'
                              : 'bg-cyan-600 text-white font-semibold'
                            : 'text-slate-400 hover:text-slate-200'
                        }`}
                      >
                        {btn.label}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="text-xs text-slate-400">
                  Showing <strong className="text-cyan-300 font-bold">{filteredInText.length}</strong> of {inTextCitations.length} occurrences
                </div>
              </div>

              {/* In-Text Citations Table */}
              <div className="w-full bg-[#0e1628]/95 border border-slate-800/90 rounded-xl shadow-xl overflow-hidden">
                <div className="overflow-x-auto w-full">
                  <table className="w-full text-left border-collapse text-xs">
                    <thead>
                      <tr className="bg-slate-900/95 text-slate-400 uppercase tracking-wider font-bold border-b border-slate-800 text-[11px]">
                        <th className="py-3 px-3 w-12 text-center">#</th>
                        <th className="py-3 px-3 w-36">Citation Marker</th>
                        <th className="py-3 px-3 w-40 text-center">Bibliography Status</th>
                        <th className="py-3 px-4">Manuscript Sentence Context</th>
                        <th className="py-3 px-4 w-72">Matched Bibliography Reference</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800/60">
                      {filteredInText.length === 0 ? (
                        <tr>
                          <td colSpan={5} className="py-8 text-center text-slate-400">
                            No in-text citations match the search or filter criteria.
                          </td>
                        </tr>
                      ) : (
                        filteredInText.map((it, idx) => {
                          const keys = it.unrolled_keys || [];
                          const isMissing = keys.length > 0
                            ? keys.some((k) => !bibRefNumbers.has(k))
                            : false;

                          const matchedRefs = (resultData.items || []).filter((r) => {
                            if (keys.length > 0) {
                              return keys.includes(Number(r.reference_no));
                            }
                            if (it.author && r.cited_authors) {
                              return r.cited_authors.toLowerCase().includes(it.author.toLowerCase());
                            }
                            return false;
                          });

                          return (
                            <tr key={idx} className="hover:bg-slate-800/30 transition-colors">
                              <td className="py-3 px-3 text-center align-top text-slate-400 font-mono">
                                {idx + 1}
                              </td>

                              <td className="py-3 px-3 align-top font-mono">
                                <span className="inline-block px-2.5 py-1 rounded bg-cyan-950/80 text-cyan-300 border border-cyan-500/40 font-bold text-xs shadow-xs">
                                  {it.marker}
                                </span>
                                <div className="text-[10px] text-slate-500 font-sans mt-1">
                                  {it.type}
                                </div>
                                {keys.length > 1 && (
                                  <div className="text-[10px] text-indigo-300 font-mono mt-0.5">
                                    Keys: [{keys.join(', ')}]
                                  </div>
                                )}
                              </td>

                              <td className="py-3 px-3 align-top text-center">
                                {!isMissing && matchedRefs.length > 0 ? (
                                  <span className="inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full bg-emerald-500/15 text-emerald-300 border border-emerald-500/30">
                                    <CheckCircle2 className="w-2.5 h-2.5 text-emerald-400" />
                                    In Bibliography
                                  </span>
                                ) : (
                                  <span className="inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full bg-rose-500/20 text-rose-300 border border-rose-500/40 animate-pulse">
                                    <AlertTriangle className="w-2.5 h-2.5 text-rose-400" />
                                    Missing from Bib!
                                  </span>
                                )}
                              </td>

                              <td className="py-3 px-4 align-top">
                                <div className="bg-slate-950/70 p-2.5 rounded-lg border-l-2 border-cyan-500 text-slate-300 text-xs font-sans leading-relaxed">
                                  {highlightMarker(it.context, it.marker)}
                                </div>
                              </td>

                              <td className="py-3 px-4 align-top">
                                {matchedRefs.length > 0 ? (
                                  <div className="space-y-1.5">
                                    {matchedRefs.map((mr) => (
                                      <div key={mr.reference_id} className="p-2 rounded bg-slate-950/50 border border-slate-800 text-[11px]">
                                        <div className="flex items-center justify-between gap-1 mb-0.5">
                                          <span className="font-mono font-bold text-indigo-300">
                                            Ref #{mr.reference_no}
                                          </span>
                                          {mr.normalized_doi && (
                                            <span className="text-[10px] font-mono text-cyan-400 truncate max-w-[120px]">
                                              {mr.normalized_doi}
                                            </span>
                                          )}
                                        </div>
                                        <div className="text-slate-300 line-clamp-1 font-medium">
                                          {mr.resolved_title || mr.raw_reference}
                                        </div>
                                        <button
                                          onClick={() => {
                                            setActiveTab('references');
                                            setSearchQuery(mr.reference_id);
                                          }}
                                          className="text-[10px] text-cyan-400 hover:text-cyan-300 hover:underline flex items-center gap-1 mt-1 cursor-pointer font-semibold"
                                        >
                                          <span>View Reference Entry</span>
                                          <ExternalLink className="w-2.5 h-2.5" />
                                        </button>
                                      </div>
                                    ))}
                                  </div>
                                ) : (
                                  <div className="p-2 rounded bg-rose-950/20 border border-rose-500/30 text-[11px] text-rose-300 italic">
                                    Marker cited in manuscript, but no matching entry was found in the bibliography.
                                  </div>
                                )}
                              </td>
                            </tr>
                          );
                        })
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}

        </div>
      )}

    </div>
  );
}
