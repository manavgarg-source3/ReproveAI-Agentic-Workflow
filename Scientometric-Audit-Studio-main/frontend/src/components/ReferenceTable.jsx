import React, { useState } from 'react';
import { 
  ExternalLink, 
  CheckCircle2, 
  XCircle, 
  Eye, 
  AlertTriangle, 
  HelpCircle,
  Link,
  ShieldCheck,
  ChevronDown,
  ChevronRight,
  Sparkles,
  BookOpen,
  FileText
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

// Returns specific human review badge based on scientometric failure mode
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
    case 'METADATA_MISMATCH':
      return (
        <span className="inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full bg-orange-500/20 text-orange-300 border border-orange-500/40 shadow-xs">
          <AlertTriangle className="w-2.5 h-2.5 text-orange-400" /> Review: Metadata Mismatch
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

export default function ReferenceTable({ items, loading, onSelectReference, onFilterBySource }) {
  const [expandedRows, setExpandedRows] = useState({});

  const toggleRowExpand = (refId) => {
    setExpandedRows((prev) => ({ ...prev, [refId]: !prev[refId] }));
  };

  if (loading) {
    return (
      <div className="w-full bg-[#0e1628]/95 border border-slate-800/90 rounded-xl p-16 text-center shadow-xl">
        <div className="w-9 h-9 border-3 border-indigo-500 border-t-transparent rounded-full animate-spin mx-auto mb-3"></div>
        <p className="text-slate-400 text-sm font-medium">Querying SQLite indexed references (&lt;10ms)...</p>
      </div>
    );
  }

  if (!items || items.length === 0) {
    return (
      <div className="w-full bg-[#0e1628]/95 border border-slate-800/90 rounded-xl p-16 text-center shadow-xl">
        <HelpCircle className="w-12 h-12 text-slate-500 mx-auto mb-3" />
        <h3 className="text-slate-200 font-bold text-base mb-1">No matching references found</h3>
        <p className="text-slate-400 text-xs">Try broadening your search term or resetting active filters.</p>
      </div>
    );
  }

  return (
    <div className="w-full bg-[#0e1628]/95 border border-slate-800/90 rounded-xl shadow-xl overflow-hidden mb-5">
      <div className="overflow-x-auto w-full">
        <table className="w-full text-left border-collapse text-xs">
          <thead>
            <tr className="bg-slate-900/95 text-slate-400 uppercase tracking-wider font-bold border-b border-slate-800 text-[11px]">
              <th className="py-3 px-3 w-10 text-center"></th>
              <th className="py-3 px-3 w-40">Reference ID</th>
              <th className="py-3 px-4 w-72">Source Manuscript</th>
              <th className="py-3 px-3 w-32 text-center">Scopus Link</th>
              <th className="py-3 px-3 w-44">Scientometric Status</th>
              <th className="py-3 px-3 w-48">Audit Review Badge</th>
              <th className="py-3 px-3 w-24 text-center">Title Sim</th>
              <th className="py-3 px-3 w-28 text-center">Score</th>
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

              return (
                <React.Fragment key={row.reference_id}>
                  <tr 
                    className={`hover:bg-slate-800/40 transition-colors group cursor-pointer ${
                      isExpanded ? 'bg-indigo-950/20' : ''
                    }`}
                    onClick={() => toggleRowExpand(row.reference_id)}
                  >
                    {/* Expand arrow */}
                    <td className="py-3 px-2 text-center align-top text-slate-400">
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          toggleRowExpand(row.reference_id);
                        }}
                        className="p-1 hover:text-white transition"
                        title={isExpanded ? 'Collapse row' : 'Expand row details'}
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
                    </td>

                    {/* Source Manuscript */}
                    <td className="py-3 px-4 align-top">
                      <div 
                        className="font-semibold text-slate-200 line-clamp-2 hover:text-indigo-300 cursor-pointer"
                        title={row.source_title}
                        onClick={(e) => {
                          e.stopPropagation();
                          onFilterBySource(row.source_eid);
                        }}
                      >
                        {row.source_title || 'Untitled Manuscript'}
                      </div>
                      <div className="text-[11px] text-slate-400 truncate mt-0.5">
                        {row.source_authors} ({row.source_year || 'N/A'})
                      </div>
                    </td>

                    {/* Scopus Link Status */}
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
                          <XCircle className="w-2.5 h-2.5" /> Unlinked
                        </span>
                      )}
                    </td>

                    {/* Status */}
                    <td className="py-3 px-3 align-top">
                      <span className={`inline-block text-[10px] font-bold px-2.5 py-0.5 rounded border uppercase tracking-wider ${badgeStyle}`}>
                        {row.final_status}
                      </span>
                      <div className="text-[10px] text-slate-400 mt-1">
                        Confidence: <strong className="text-slate-200">{row.confidence}</strong>
                      </div>
                    </td>

                    {/* Human Review Badge */}
                    <td className="py-3 px-3 align-top">
                      {renderReviewBadge(row)}
                      {row.reviewed_by_user ? (
                        <span className="text-[9px] text-cyan-400 font-semibold block mt-1">
                          ✓ Signed off by researcher
                        </span>
                      ) : null}
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
                    <td className="py-3 px-3 align-top text-center">
                      <div className="font-mono font-bold text-slate-100 text-xs">
                        {scorePct}%
                      </div>
                      <div className="w-full bg-slate-800 rounded-full h-1.5 mt-1 overflow-hidden">
                        <div 
                          className={`h-1.5 rounded-full ${
                            scorePct >= 80 ? 'bg-emerald-500' : scorePct >= 60 ? 'bg-cyan-500' : 'bg-amber-500'
                          }`}
                          style={{ width: `${scorePct}%` }}
                        ></div>
                      </div>
                    </td>

                    {/* Normalized DOI */}
                    <td className="py-3 px-3 align-top font-mono text-[11px]">
                      {row.normalized_doi ? (
                        <a
                          href={`https://doi.org/${row.normalized_doi}`}
                          target="_blank"
                          rel="noreferrer"
                          onClick={(e) => e.stopPropagation()}
                          className="text-cyan-400 hover:text-cyan-300 hover:underline flex items-center gap-1 truncate max-w-[180px]"
                          title={row.normalized_doi}
                        >
                          <Link className="w-3 h-3 shrink-0" />
                          <span className="truncate">{row.normalized_doi}</span>
                        </a>
                      ) : (
                        <span className="text-[10px] text-slate-500 italic">No DOI</span>
                      )}
                      {row.doi_resolves ? (
                        <span className="text-[9px] text-emerald-400 block mt-0.5">✓ Resolves (HTTP {row.http_status || 200})</span>
                      ) : row.normalized_doi ? (
                        <span className="text-[9px] text-rose-400 block mt-0.5">✗ Fails to resolve</span>
                      ) : null}
                    </td>

                    {/* Resolved Title & Rationale */}
                    <td className="py-3 px-4 align-top">
                      <div className="font-semibold text-slate-200 line-clamp-1">
                        {row.resolved_title || <span className="text-slate-500 italic">Unresolved publication</span>}
                      </div>
                      <div className="text-[11px] text-slate-400 line-clamp-1 mt-0.5 italic">
                        "{row.raw_reference}"
                      </div>
                      {row.decision_rationale && (
                        <div className="text-[10px] text-slate-400 mt-1 line-clamp-1">
                          <span className="text-slate-500 font-medium">Rationale:</span> {row.decision_rationale}
                        </div>
                      )}
                    </td>

                    {/* Actions */}
                    <td className="py-3 px-3 align-top text-center">
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          onSelectReference(row.reference_id);
                          if (onSelectReference) onSelectReference(row.reference_id, row);
                        }}
                        className="px-3 py-1 rounded-lg bg-slate-800 hover:bg-indigo-600 text-slate-200 hover:text-white transition font-semibold text-xs flex items-center gap-1 mx-auto shadow-xs border border-slate-700/80 hover:border-indigo-500"
                        title="Open full diagnostic inspection drawer"
                      >
                        <Eye className="w-3.5 h-3.5" />
                        <span>Inspect</span>
                      </button>
                    </td>
                  </tr>

                  {/* Inline Expanded Row */}
                  {isExpanded && (
                    <tr className="bg-[#0b1220] border-b border-slate-800/80">
                      <td colSpan={11} className="p-4 pl-12 text-xs">
                        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 bg-slate-900/90 p-4 rounded-xl border border-slate-800">
                          
                          {/* Raw Citation */}
                          <div>
                            <span className="text-[10px] font-bold uppercase tracking-wider text-cyan-400 block mb-1 flex items-center gap-1.5">
                              <FileText className="w-3 h-3" /> Verbatim Citation in Manuscript
                            </span>
                            <blockquote className="p-2.5 rounded bg-slate-950/80 border-l-2 border-cyan-500 font-serif italic text-slate-200 text-xs leading-relaxed">
                              "{row.raw_reference}"
                            </blockquote>
                          </div>

                          {/* Resolved Publication Details */}
                          <div>
                            <span className="text-[10px] font-bold uppercase tracking-wider text-emerald-400 block mb-1 flex items-center gap-1.5">
                              <CheckCircle2 className="w-3 h-3" /> Resolved Bibliographic Metadata
                            </span>
                            <div className="p-2.5 rounded bg-slate-950/80 space-y-1 text-slate-300">
                              <p><strong className="text-slate-400">Title:</strong> {row.resolved_title || 'N/A'}</p>
                              <p><strong className="text-slate-400">Authors:</strong> {row.resolved_authors || 'N/A'}</p>
                              <p><strong className="text-slate-400">Venue:</strong> {row.resolved_journal} ({row.resolved_year || 'N/A'})</p>
                              {row.normalized_doi && (
                                <p><strong className="text-slate-400">DOI:</strong> <a href={`https://doi.org/${row.normalized_doi}`} target="_blank" rel="noreferrer" className="text-cyan-400 underline">{row.normalized_doi}</a></p>
                              )}
                            </div>
                          </div>

                          {/* Diagnostic Matching Scores */}
                          <div>
                            <span className="text-[10px] font-bold uppercase tracking-wider text-purple-400 block mb-1 flex items-center gap-1.5">
                              <ShieldCheck className="w-3 h-3" /> Diagnostic Matching Metrics
                            </span>
                            <div className="p-2.5 rounded bg-slate-950/80 space-y-2 text-slate-300">
                              <div className="flex justify-between items-center text-[11px]">
                                <span className="text-slate-400">Title Similarity:</span>
                                <span className="font-mono font-bold text-slate-100">{Math.round((row.title_similarity || 0) * 100)}%</span>
                              </div>
                              <div className="flex justify-between items-center text-[11px]">
                                <span className="text-slate-400">Author Similarity:</span>
                                <span className="font-mono font-bold text-slate-100">{Math.round((row.author_similarity || 0) * 100)}%</span>
                              </div>
                              <div className="flex justify-between items-center text-[11px]">
                                <span className="text-slate-400">Composite Score:</span>
                                <span className="font-mono font-bold text-emerald-400">{scorePct}%</span>
                              </div>
                              <p className="text-[11px] text-slate-400 pt-1 border-t border-slate-800">
                                <strong className="text-slate-300">Decision Rationale:</strong> {row.decision_rationale}
                              </p>
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
  );
}
