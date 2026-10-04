import React, { useState } from 'react';
import { 
  Link2, 
  Search, 
  Sparkles, 
  ExternalLink, 
  AlertTriangle, 
  CheckCircle2, 
  FileSpreadsheet, 
  Download, 
  RotateCcw,
  BookOpen,
  Bot
} from 'lucide-react';

const SAMPLE_PRESETS = [
  {
    title: 'Paper 1: IISERs Scientific Productivity',
    title: 'Paper 1: IISERs Productivity',
    id: 'https://www.scopus.com/pages/publications/85118881384?origin=resultslist',
    desc: 'Scopus EID: 85118881384 (Multi-campus institutional evaluation)',
    desc: 'Scopus EID: 85118881384 (14 references in corpus)',
  },
  {
    title: 'Paper 2: Patent Analytics & Tech Trajectories',
    title: 'Paper 2: Patent Analytics',
    id: 'https://www.scopus.com/pages/publications/105042346360?origin=resultslist',
    desc: 'Scopus EID: 105042346360 (High-density patent citation dataset)',
    desc: 'Scopus EID: 105042346360 (35 references in corpus)',
  },
  {
    title: 'Paper 3: AI Scholarly Tools (Scopus 85116424104)',
    id: 'https://www.scopus.com/pages/publications/85116424104?origin=resultslist',
    desc: 'Corpus Cited Reference -> 99 References Extracted',
  },
  {
    title: 'Paper 4: Taylor & Francis Book Review',
    id: 'https://www.tandfonline.com/doi/full/10.1080/09668136.2018.1520499',
    desc: 'Single Publication Audit (Europe-Asia Studies)',
  },
  {
    title: 'Paper 5: PLOS ONE Open Access',
    id: 'https://doi.org/10.1371/journal.pone.0280000',
    desc: 'Direct DOI with 52 Crossref References',
  },
];

export default function LinkAuditorView({ onSelectReference }) {
  const [linkInput, setLinkInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');
  const [resultData, setResultData] = useState(null);
  const [searchQuery, setSearchQuery] = useState('');

  const handleAudit = async (identifier) => {
    const idToUse = (identifier || linkInput).trim();
    if (!idToUse) {
      setErrorMsg('Please enter a Scopus URL, Scopus EID, or DOI.');
      return;
    }

    setLoading(true);
    setErrorMsg('');
    try {
      const formData = new FormData();
      formData.append('scopus_link', idToUse);

      const res = await fetch('/api/custom-audit/run', {
        method: 'POST',
        body: formData,
      });

      if (!res.ok) {
        const errJson = await res.json().catch(() => ({}));
        throw new Error(errJson.detail || `Audit failed (HTTP ${res.status})`);
      }

      const data = await res.json();
      setResultData(data);
    } catch (err) {
      console.error('Link audit failed:', err);
      setErrorMsg(err.message || 'Audit execution error.');
    } finally {
      setLoading(false);
    }
  };

  const filteredItems = (resultData?.items || []).filter((r) => {
    if (!searchQuery.trim()) return true;
    const q = searchQuery.toLowerCase();
    return (
      (r.raw_reference && r.raw_reference.toLowerCase().includes(q)) ||
      (r.resolved_title && r.resolved_title.toLowerCase().includes(q)) ||
      (r.normalized_doi && r.normalized_doi.toLowerCase().includes(q)) ||
      (r.final_status && r.final_status.toLowerCase().includes(q))
    );
  });

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="bg-gradient-to-r from-cyan-950/80 via-[#0a182d] to-slate-900 border border-cyan-500/40 rounded-2xl p-6 shadow-2xl">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="space-y-1.5 max-w-2xl">
            <div className="flex items-center gap-2">
              <span className="px-2.5 py-0.5 rounded-full bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 font-mono text-[11px] font-bold uppercase tracking-wider">
                Link &amp; Identifier Auditor
              </span>
              <span className="text-xs text-slate-400 font-mono">
                Direct Resolution via Scopus &amp; Crossref
              </span>
            </div>
            <h1 className="text-xl sm:text-2xl font-black text-white tracking-tight flex items-center gap-2">
              <span>Audit Manuscript by Link or Identifier</span>
              <Link2 className="w-5 h-5 text-cyan-400 shrink-0" />
            </h1>
            <p className="text-xs sm:text-sm text-slate-300 leading-relaxed">
              Enter any <strong>Scopus Publication URL</strong>, <strong>Abstract EID</strong>, or <strong>DOI</strong>. The studio automatically resolves authoritative metadata, checks citation validity, detects phantom citations, and synthesizes scientometric indicators.
            </p>
          </div>
        </div>

        {/* Input Form */}
        <div className="mt-6 space-y-3">
          <div className="flex flex-wrap sm:flex-nowrap items-center gap-2.5">
            <div className="relative flex-1">
              <Link2 className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-cyan-400" />
              <input
                type="text"
                value={linkInput}
                onChange={(e) => setLinkInput(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') handleAudit(); }}
                placeholder="Paste Scopus link, EID (e.g. 2-s2.0-85118881384), or DOI (e.g. 10.1016/...)"
                className="w-full pl-10 pr-4 py-3 bg-slate-950 border border-slate-700 rounded-xl text-xs sm:text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 shadow-inner font-mono"
              />
            </div>
            <button
              onClick={() => handleAudit()}
              disabled={loading}
              className={`px-6 py-3 rounded-xl text-xs sm:text-sm font-bold transition-all shadow-lg flex items-center gap-2 cursor-pointer whitespace-nowrap ${
                loading
                  ? 'bg-slate-800 text-slate-400 border border-slate-700 cursor-not-allowed'
                  : 'bg-gradient-to-r from-cyan-600 to-indigo-600 hover:from-cyan-500 hover:to-indigo-500 text-white shadow-cyan-600/30 active:scale-98 ring-1 ring-white/10'
              }`}
            >
              {loading ? (
                <>
                  <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                  <span>Auditing Link...</span>
                </>
              ) : (
                <>
                  <Sparkles className="w-4 h-4 text-cyan-200" />
                  <span>Audit Link</span>
                </>
              )}
            </button>
          </div>

          {/* Quick Preset Buttons */}
          <div className="flex flex-wrap items-center gap-2 pt-2 text-xs">
            <span className="text-[11px] text-slate-400 font-bold uppercase">Quick Samples:</span>
            {SAMPLE_PRESETS.map((p, idx) => (
              <button
                key={idx}
                onClick={() => {
                  setLinkInput(p.id);
                  handleAudit(p.id);
                }}
                className="px-3 py-1 rounded-lg bg-slate-900/90 hover:bg-indigo-600/90 text-slate-300 hover:text-white border border-slate-800 transition cursor-pointer text-[11px]"
              >
                {p.title}
              </button>
            ))}
          </div>

          {errorMsg && (
            <div className="p-3.5 rounded-xl bg-rose-950/60 border border-rose-500/50 text-xs text-rose-200 flex items-center gap-2 mt-2">
              <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0" />
              <span>{errorMsg}</span>
            </div>
          )}
        </div>
      </div>

      {/* Results Section */}
      {resultData && (
        <div className="space-y-6">
          {/* Header Bar */}
          <div className="bg-[#0e1628] border border-slate-800 rounded-xl p-4 flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className="flex items-center gap-2">
                <span className="text-xs font-mono font-bold px-2 py-0.5 rounded bg-indigo-950 text-indigo-300 border border-indigo-500/40">
                  {resultData.source_info?.source_eid || 'LINK AUDIT'}
                </span>
                <span className="text-xs text-slate-400">
                  {resultData.source_info?.source_authors} ({resultData.source_info?.source_year || 'N/A'})
                </span>
              </div>
              <h2 className="text-base font-bold text-white mt-1">
                {resultData.source_info?.source_title || 'Audited Publication'}
              </h2>
            </div>

            <div className="flex items-center gap-2">
              {resultData.excel_download_url && (
                <a
                  href={resultData.excel_download_url}
                  className="px-3 py-1.5 rounded-lg bg-emerald-600/80 hover:bg-emerald-500 text-white font-bold text-xs transition flex items-center gap-1.5 shadow-xs"
                >
                  <Download className="w-3.5 h-3.5" />
                  <span>Download Excel</span>
                </a>
              )}
              {resultData.csv_download_url && (
                <a
                  href={resultData.csv_download_url}
                  className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 font-bold text-xs transition flex items-center gap-1.5 border border-slate-700 shadow-xs"
                >
                  <FileSpreadsheet className="w-3.5 h-3.5 text-emerald-400" />
                  <span>Download CSV</span>
                </a>
              )}
            </div>
          </div>

          {/* Target Document & Link Verification Card */}
          {resultData.target_audit && (
            <div className="bg-gradient-to-r from-slate-900 via-[#0a1730] to-slate-900 border border-cyan-500/40 rounded-2xl p-5 shadow-2xl space-y-4">
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800/80 pb-3">
                <div className="flex items-center gap-2.5">
                  <span className="px-2.5 py-1 rounded-full text-xs font-mono font-bold uppercase tracking-wider flex items-center gap-1.5 border bg-emerald-950/80 text-emerald-300 border-emerald-500/40">
                    <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                    <span>{resultData.target_audit.doi_resolves ? 'Link Resolving (Reachable)' : 'Resolution Failed'}</span>
                  </span>
                  {resultData.target_audit.http_status && (
                    <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700">
                      HTTP {resultData.target_audit.http_status}
                    </span>
                  )}
                  <span className="text-xs font-mono px-2 py-0.5 rounded bg-indigo-950 text-indigo-300 border border-indigo-500/30">
                    {resultData.target_audit.metadata_source || 'Verified Registry'}
                  </span>
                </div>

                <div className="flex items-center gap-2">
                  {resultData.target_audit.final_url && (
                    <a
                      href={resultData.target_audit.final_url}
                      target="_blank"
                      rel="noreferrer"
                      className="text-xs font-mono text-cyan-400 hover:text-cyan-300 flex items-center gap-1 hover:underline"
                    >
                      <span>Visit Target Page</span>
                      <ExternalLink className="w-3 h-3" />
                    </a>
                  )}
                </div>
              </div>

              <div>
                <h2 className="text-base sm:text-lg font-bold text-white leading-snug">
                  {resultData.target_audit.title || resultData.source_info?.source_title || 'Audited Scholarly Artifact'}
                </h2>
                <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 mt-2.5 text-xs text-slate-300">
                  {resultData.target_audit.authors && (
                    <div>
                      <strong className="text-slate-400 font-semibold">Authors: </strong>
                      <span>{resultData.target_audit.authors}</span>
                    </div>
                  )}
                  {resultData.target_audit.journal && (
                    <div>
                      <strong className="text-slate-400 font-semibold">Venue: </strong>
                      <span className="text-cyan-300">{resultData.target_audit.journal}</span>
                    </div>
                  )}
                  {resultData.target_audit.year && (
                    <div>
                      <strong className="text-slate-400 font-semibold">Year: </strong>
                      <span>{resultData.target_audit.year}</span>
                    </div>
                  )}
                  {resultData.target_audit.doi && (
                    <div>
                      <strong className="text-slate-400 font-semibold">DOI: </strong>
                      <a
                        href={`https://doi.org/${resultData.target_audit.doi}`}
                        target="_blank"
                        rel="noreferrer"
                        className="font-mono text-indigo-400 hover:underline"
                      >
                        {resultData.target_audit.doi}
                      </a>
                    </div>
                  )}
                  {resultData.target_audit.scopus_id && (
                    <div>
                      <strong className="text-slate-400 font-semibold">Scopus ID: </strong>
                      <span className="font-mono text-emerald-400">{resultData.target_audit.scopus_id}</span>
                    </div>
                  )}
                </div>
              </div>

              {/* Corpus match alert if present */}
              {resultData.target_audit.in_corpus && (
                <div className="p-3 rounded-xl bg-emerald-950/40 border border-emerald-500/30 text-xs text-emerald-200 flex items-start gap-2.5">
                  <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
                  <div>
                    <strong className="font-bold text-emerald-300">Indexed in Scientometric Corpus: </strong>
                    <span>
                      This work is cited by {resultData.target_audit.corpus_citations_count} manuscript(s) in the local reference database.
                      {resultData.target_audit.corpus_citing_papers?.length > 0 && (
                        <span className="text-slate-300 ml-1">
                          (e.g. &ldquo;{resultData.target_audit.corpus_citing_papers[0]}&rdquo;)
                        </span>
                      )}
                    </span>
                  </div>
                </div>
              )}

              {/* Single work notice if 0 downstream references */}
              {resultData.target_audit.is_single_work_audit && (
                <div className="p-3 rounded-xl bg-indigo-950/40 border border-indigo-500/30 text-xs text-indigo-200 flex items-start gap-2.5">
                  <BookOpen className="w-4 h-4 text-indigo-400 shrink-0 mt-0.5" />
                  <div>
                    <strong className="font-bold text-indigo-300">Single Publication Audit: </strong>
                    <span>
                      Target publication link is 100% verified and active. The publisher has not deposited downstream reference bibliographies in open registries (e.g. Book Review or closed citation index). The publication itself is audited above and in the table below.
                    </span>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Scientometric Indicators */}
          {resultData.scientometric_audit && (
            <div className="bg-gradient-to-r from-slate-900 via-[#0c1830] to-slate-900 border border-indigo-500/40 rounded-xl p-5 space-y-4 shadow-xl">
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800/80 pb-3">
                <div className="flex items-center gap-2">
                  <Sparkles className="w-4 h-4 text-cyan-400" />
                  <span className="font-bold text-xs uppercase tracking-wider text-white">
                    LLM Scientometric Health Assessment
                  </span>
                  <span className="text-[10px] font-mono font-bold px-2 py-0.5 rounded bg-indigo-950 text-indigo-300 border border-indigo-500/40 uppercase">
                    Grade: {resultData.scientometric_audit.audit_grade || 'A'}
                  </span>
                </div>
                <span className="text-xs font-bold px-2.5 py-1 rounded-full border bg-cyan-500/15 text-cyan-300 border-cyan-500/40">
                  Freshness: {resultData.scientometric_audit.temporal_freshness_verdict || 'BALANCED'}
                </span>
              </div>

              {/* 4 KPIs */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <div className="p-3 rounded-lg bg-slate-950/80 border border-slate-800">
                  <div className="text-[10px] uppercase font-bold text-slate-400">Price's Index</div>
                  <div className="text-lg font-extrabold text-cyan-300 mt-0.5">
                    {resultData.scientometric_audit.indicators?.price_index || 0}%
                  </div>
                  <div className="text-[10px] text-slate-500">&le; 5 yrs recency</div>
                </div>

                <div className="p-3 rounded-lg bg-slate-950/80 border border-slate-800">
                  <div className="text-[10px] uppercase font-bold text-slate-400">Citation Half-Life</div>
                  <div className="text-lg font-extrabold text-indigo-300 mt-0.5">
                    {resultData.scientometric_audit.indicators?.median_citation_age || 0} yrs
                  </div>
                  <div className="text-[10px] text-slate-500">Median citation age</div>
                </div>

                <div className="p-3 rounded-lg bg-slate-950/80 border border-slate-800">
                  <div className="text-[10px] uppercase font-bold text-slate-400">Scopus Linked</div>
                  <div className="text-lg font-extrabold text-emerald-300 mt-0.5">
                    {resultData.stats?.scopus_linked_pct || 0}%
                  </div>
                  <div className="text-[10px] text-slate-500">{resultData.stats?.scopus_linked || 0} references</div>
                </div>

                <div className="p-3 rounded-lg bg-slate-950/80 border border-slate-800">
                  <div className="text-[10px] uppercase font-bold text-slate-400">DOI Resolution</div>
                  <div className="text-lg font-extrabold text-purple-300 mt-0.5">
                    {resultData.stats?.resolving_pct || 0}%
                  </div>
                  <div className="text-[10px] text-slate-500">{resultData.stats?.resolving_dois || 0} verified DOIs</div>
                </div>
              </div>

              {/* Executive Summary */}
              <div className="p-3.5 rounded-lg bg-slate-950/90 border border-slate-800 text-xs text-slate-300 space-y-1.5 leading-relaxed">
                <div className="font-bold text-slate-200 flex items-center gap-1.5">
                  <Bot className="w-4 h-4 text-cyan-400" />
                  <span>Peer-Review Executive Critique:</span>
                </div>
                <p>{resultData.scientometric_audit.executive_summary}</p>
                {resultData.scientometric_audit.methodological_backbone && (
                  <div className="pt-2 border-t border-slate-800/80 text-slate-400">
                    <strong className="text-slate-200">Methodological Backbone: </strong>
                    {resultData.scientometric_audit.methodological_backbone}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Reference Table */}
          <div className="bg-[#0b1120] border border-slate-800 rounded-xl overflow-hidden shadow-xl space-y-3 p-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="text-xs font-bold text-white uppercase tracking-wider flex items-center gap-2">
                <BookOpen className="w-4 h-4 text-indigo-400" />
                <span>Extracted Citations ({filteredItems.length})</span>
              </div>

              <div className="relative w-64">
                <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400" />
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Filter references..."
                  className="w-full pl-8 pr-3 py-1 bg-slate-900 border border-slate-700 rounded-lg text-xs text-slate-200 focus:outline-none focus:border-indigo-500"
                />
              </div>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="bg-[#0e1628] border-b border-slate-800 text-slate-400 uppercase text-[10px] font-bold">
                  <tr>
                    <th className="py-2.5 px-3">#</th>
                    <th className="py-2.5 px-3">Status</th>
                    <th className="py-2.5 px-3">Reference Text</th>
                    <th className="py-2.5 px-3">DOI</th>
                    <th className="py-2.5 px-3">Stance</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60">
                  {filteredItems.map((r, idx) => (
                    <tr 
                      key={r.reference_id || idx}
                      onClick={() => onSelectReference && onSelectReference(r.reference_id, r)}
                      className="hover:bg-slate-900/60 transition cursor-pointer"
                    >
                      <td className="py-2.5 px-3 font-mono text-slate-500 font-bold">{r.reference_no}</td>
                      <td className="py-2.5 px-3">
                        <span className={`px-2 py-0.5 rounded font-mono font-bold text-[10px] ${
                          r.final_status === 'VALID_CORRECT' || r.doi_resolves
                            ? 'bg-emerald-950 text-emerald-300 border border-emerald-500/40'
                            : r.final_status === 'INVALID_DOI'
                            ? 'bg-rose-950 text-rose-300 border border-rose-500/40'
                            : 'bg-slate-800 text-slate-400'
                        }`}>
                          {r.final_status}
                        </span>
                      </td>
                      <td className="py-2.5 px-3 max-w-md">
                        <p className="line-clamp-2 text-slate-200 text-[11px]">{r.raw_reference}</p>
                      </td>
                      <td className="py-2.5 px-3 font-mono text-indigo-300 text-[11px]">
                        {r.normalized_doi || r.extracted_doi || 'N/A'}
                      </td>
                      <td className="py-2.5 px-3">
                        <span className="text-[10px] px-2 py-0.5 rounded-full bg-slate-800 text-slate-300 border border-slate-700 font-bold">
                          {r.citation_intent || 'BACKGROUND'}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

