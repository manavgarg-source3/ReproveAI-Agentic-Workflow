import React, { useState, useEffect } from 'react';
import { 
  X, 
  ExternalLink, 
  CheckCircle2, 
  AlertTriangle, 
  Save, 
  ShieldCheck, 
  Link, 
  BookOpen, 
  Calendar, 
  User, 
  FileText,
  Sparkles,
  XCircle
} from 'lucide-react';

export default function ReferenceDrawer({ referenceId, referenceData, onClose, onUpdate }) {
  const [data, setData] = useState(referenceData || null);
  const [loading, setLoading] = useState(!referenceData);
  const [saving, setSaving] = useState(false);
  const [reviewed, setReviewed] = useState(Boolean(referenceData?.reviewed_by_user));
  const [notes, setNotes] = useState(referenceData?.user_notes || '');
  const [statusOverride, setStatusOverride] = useState(referenceData?.final_status || '');
  const [successMsg, setSuccessMsg] = useState('');

  // Close on Escape key
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  useEffect(() => {
    if (referenceData) {
      setData(referenceData);
      setReviewed(Boolean(referenceData.reviewed_by_user));
      setNotes(referenceData.user_notes || '');
      setStatusOverride(referenceData.final_status);
      setLoading(false);
      return;
    }
    if (!referenceId) return;
    setLoading(true);
    fetch(`/api/references/${encodeURIComponent(referenceId)}`)
      .then((res) => res.json())
      .then((res) => {
        if (!res.ok) throw new Error('Reference record not found');
        return res.json();
      })
      .then((item) => {
        setData(item);
        setReviewed(Boolean(item.reviewed_by_user));
        setNotes(item.user_notes || '');
        setStatusOverride(item.final_status);
        setLoading(false);
      })
      .catch((err) => {
        console.error('Error fetching reference detail:', err);
        setLoading(false);
      });
  }, [referenceId, referenceData]);

  const handleSave = async () => {
    setSaving(true);
    try {
      const res = await fetch(`/api/references/${encodeURIComponent(referenceId)}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          reviewed: reviewed,
          user_notes: notes,
          status_override: statusOverride !== data.final_status ? statusOverride : null,
        }),
      });
      if (res.ok) {
        const result = await res.json();
        setData(result.reference);
        setSuccessMsg('Review decision recorded successfully!');
        setTimeout(() => setSuccessMsg(''), 3000);
        if (onUpdate) onUpdate(result.reference);
      }
    } catch (err) {
      console.error('Error updating reference review:', err);
    } finally {
      setSaving(false);
    }
  };

  if (!referenceId) return null;

  return (
    <div 
      className="fixed inset-0 z-50 overflow-hidden bg-black/70 backdrop-blur-sm transition-opacity flex justify-end"
      onClick={onClose}
    >
      <div 
        className="w-full max-w-2xl bg-[#0e1628] border-l border-slate-800 shadow-2xl h-full flex flex-col transition-transform"
        onClick={(e) => e.stopPropagation()}
      >
        
        {/* Drawer Header */}
        <div className="p-4 bg-slate-900/95 border-b border-slate-800 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <span className="font-mono font-bold text-sm text-indigo-300">
              {referenceId}
            </span>
            {data?.final_status && (
              <span className="text-[10px] font-extrabold uppercase px-2.5 py-0.5 rounded bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">
                {data.final_status}
              </span>
            )}
            {data?.needs_human_review ? (
              <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-amber-500/20 text-amber-300 border border-amber-500/40">
                ⚠️ Review Flagged
              </span>
            ) : (
              <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/40">
                ✓ Auto-Approved
              </span>
            )}
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition"
            title="Close Drawer (Esc)"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Drawer Body */}
        {loading ? (
          <div className="flex-1 flex items-center justify-center">
            <div className="w-8 h-8 border-3 border-indigo-500 border-t-transparent rounded-full animate-spin"></div>
          </div>
        ) : !data ? (
          <div className="p-6 text-slate-400">Reference record not found.</div>
        ) : (
          <div className="flex-1 overflow-y-auto p-5 space-y-4 text-xs text-slate-300">
            
            {/* Section 1: Citing Manuscript */}
            <div className="p-4 rounded-xl bg-slate-900/80 border border-slate-800 shadow-sm">
              <span className="text-[10px] font-bold uppercase tracking-wider text-indigo-400 block mb-1.5 flex items-center gap-1.5">
                <BookOpen className="w-3.5 h-3.5" /> Citing Source Manuscript
              </span>
              <h4 className="font-bold text-slate-100 text-sm mb-1.5 leading-snug">
                {data.source_title}
              </h4>
              <div className="text-slate-400 space-y-1">
                <p><strong className="text-slate-300 font-medium">Authors:</strong> {data.source_authors}</p>
                <p><strong className="text-slate-300 font-medium">Year:</strong> {data.source_year} | <strong className="text-slate-300 font-medium">EID:</strong> <span className="font-mono text-indigo-300">{data.source_eid}</span></p>
                {data.source_doi && (
                  <p><strong className="text-slate-300 font-medium">Source DOI:</strong> <span className="font-mono text-cyan-400">{data.source_doi}</span></p>
                )}
              </div>
            </div>

            {/* Section 2: Cited Reference Text */}
            <div className="p-4 rounded-xl bg-slate-900/80 border border-slate-800 shadow-sm">
              <span className="text-[10px] font-bold uppercase tracking-wider text-cyan-400 block mb-1.5 flex items-center gap-1.5">
                <FileText className="w-3.5 h-3.5" /> Verbatim Citation (From Manuscript Bibliography)
              </span>
              <blockquote className="p-3 rounded-lg bg-slate-950/80 border-l-2 border-cyan-500 font-serif text-slate-200 italic leading-relaxed text-xs">
                "{data.raw_reference}"
              </blockquote>
            </div>

            {/* Section 3: Resolved Bibliographic Entity */}
            <div className="p-4 rounded-xl bg-slate-900/80 border border-slate-800 shadow-sm">
              <div className="flex items-center justify-between mb-2">
                <span className="text-[10px] font-bold uppercase tracking-wider text-emerald-400 flex items-center gap-1.5">
                  <CheckCircle2 className="w-3.5 h-3.5" /> Resolved Bibliographic Metadata
                </span>
                <span className="text-[10px] px-2 py-0.5 rounded bg-slate-800 text-slate-300 font-mono font-semibold">
                  Source: {data.metadata_source || 'Scopus Ground Truth'}
                </span>
              </div>

              <div className="space-y-1.5 bg-slate-950/70 p-3 rounded-lg border border-slate-800/80">
                <p className="text-slate-100 font-semibold text-sm">
                  {data.resolved_title || <span className="text-slate-500 italic">No resolved title available</span>}
                </p>
                <p><strong className="text-slate-400">Authors:</strong> {data.resolved_authors || 'N/A'}</p>
                <p><strong className="text-slate-400">Venue:</strong> {data.resolved_journal} ({data.resolved_year || 'N/A'})</p>
                
                {data.normalized_doi && (
                  <div className="flex items-center gap-2 pt-1">
                    <strong className="text-slate-400">DOI:</strong>
                    <a
                      href={`https://doi.org/${data.normalized_doi}`}
                      target="_blank"
                      rel="noreferrer"
                      className="text-cyan-400 hover:underline flex items-center gap-1 font-mono font-semibold"
                    >
                      {data.normalized_doi} <ExternalLink className="w-3 h-3" />
                    </a>
                    {data.doi_resolves ? (
                      <span className="text-[10px] px-1.5 py-0.2 rounded bg-emerald-500/20 text-emerald-300 font-medium">Resolves (HTTP {data.http_status || 200})</span>
                    ) : (
                      <span className="text-[10px] px-1.5 py-0.2 rounded bg-rose-500/20 text-rose-300 font-medium">Unresolved</span>
                    )}
                  </div>
                )}

                {data.scopus_reference_link && data.scopus_reference_link.startsWith('http') && (
                  <div className="flex items-center gap-2 pt-1 border-t border-slate-800/60 mt-1">
                    <strong className="text-slate-400">Scopus Web:</strong>
                    <a
                      href={data.scopus_reference_link}
                      target="_blank"
                      rel="noreferrer"
                      className="text-indigo-400 hover:text-indigo-300 hover:underline flex items-center gap-1 font-medium"
                    >
                      Official Scopus Document Record <ExternalLink className="w-3 h-3" />
                    </a>
                  </div>
                )}
              </div>
            </div>

            {/* Section 4: Scientometric Matching Diagnostics Matrix */}
            <div className="p-4 rounded-xl bg-slate-900/80 border border-slate-800 shadow-sm">
              <span className="text-[10px] font-bold uppercase tracking-wider text-purple-400 block mb-2.5 flex items-center gap-1.5">
                <ShieldCheck className="w-3.5 h-3.5" /> Scientometric Similarity Diagnostics
              </span>

              <div className="grid grid-cols-2 gap-3 mb-3">
                {/* Title Similarity */}
                <div className="bg-slate-950/70 p-3 rounded-lg border border-slate-800/80">
                  <div className="flex justify-between mb-1.5 text-xs">
                    <span className="text-slate-400">Title Similarity:</span>
                    <span className="font-mono font-bold text-slate-100">
                      {Math.round((data.title_similarity || 0) * 100)}%
                    </span>
                  </div>
                  <div className="w-full bg-slate-800 rounded-full h-1.5 overflow-hidden">
                    <div 
                      className="h-1.5 bg-indigo-500 rounded-full" 
                      style={{ width: `${Math.round((data.title_similarity || 0) * 100)}%` }}
                    />
                  </div>
                </div>

                {/* Author Similarity */}
                <div className="bg-slate-950/70 p-3 rounded-lg border border-slate-800/80">
                  <div className="flex justify-between mb-1.5 text-xs">
                    <span className="text-slate-400">Author Similarity:</span>
                    <span className="font-mono font-bold text-slate-100">
                      {Math.round((data.author_similarity || 0) * 100)}%
                    </span>
                  </div>
                  <div className="w-full bg-slate-800 rounded-full h-1.5 overflow-hidden">
                    <div 
                      className="h-1.5 bg-cyan-500 rounded-full" 
                      style={{ width: `${Math.round((data.author_similarity || 0) * 100)}%` }}
                    />
                  </div>
                </div>
              </div>

              <div className="flex items-center justify-between bg-slate-950/70 p-3 rounded-lg border border-slate-800/80">
                <span className="text-slate-300 font-medium">Composite Scientometric Score:</span>
                <span className="text-lg font-black text-emerald-400 font-mono">
                  {Math.round((data.composite_score || 0) * 100)}%
                </span>
              </div>
            </div>

            {/* Section 5: Decision Rationale */}
            <div className="p-4 rounded-xl bg-slate-900/80 border border-slate-800 shadow-sm">
              <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400 block mb-1.5">
                Automated Decision Rationale
              </span>
              <p className="text-slate-300 leading-relaxed bg-slate-950/70 p-3 rounded-lg border border-slate-800/80 text-xs">
                {data.decision_rationale || 'Verified using Scopus ground-truth and Crossref bibliographic registries.'}
              </p>
            </div>

            {/* Section 6: Reviewer Triage & Actions */}
            <div className="p-4 rounded-xl bg-indigo-950/25 border border-indigo-500/30 shadow-sm">
              <span className="text-[10px] font-bold uppercase tracking-wider text-indigo-300 block mb-2.5">
                Researcher Review & Verification Actions
              </span>

              <div className="space-y-3">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={reviewed}
                    onChange={(e) => setReviewed(e.target.checked)}
                    className="w-4 h-4 rounded bg-slate-900 border-slate-700 text-indigo-600 focus:ring-indigo-500"
                  />
                  <span className="text-slate-200 font-semibold">Mark as Manually Reviewed & Verified</span>
                </label>

                <div>
                  <label className="text-[11px] text-slate-400 block mb-1">Status Override (Optional):</label>
                  <select
                    value={statusOverride}
                    onChange={(e) => setStatusOverride(e.target.value)}
                    className="w-full bg-slate-900 border border-slate-700 rounded-lg p-2 text-slate-200 text-xs focus:outline-none focus:border-indigo-500"
                  >
                    <option value="VALID_CORRECT">VALID_CORRECT (Verified)</option>
                    <option value="SCOPUS_LINKED_NO_DOI">SCOPUS_LINKED_NO_DOI (Indexed in Scopus)</option>
                    <option value="SCOPUS_UNLINKED">SCOPUS_UNLINKED (Unlinked)</option>
                    <option value="DOI_RECOVERED">DOI_RECOVERED (External DOI)</option>
                    <option value="ACCESS_RESTRICTED">ACCESS_RESTRICTED (Paywall)</option>
                    <option value="BROKEN_URL">BROKEN_URL (404)</option>
                    <option value="VALID_DOI_WRONG_REFERENCE">VALID_DOI_WRONG_REFERENCE (Mismatch)</option>
                  </select>
                </div>

                <div>
                  <label className="text-[11px] text-slate-400 block mb-1">Researcher Audit Notes:</label>
                  <textarea
                    value={notes}
                    onChange={(e) => setNotes(e.target.value)}
                    rows={3}
                    placeholder="Enter observations, manual cross-checks, or sign-off comments..."
                    className="w-full bg-slate-900 border border-slate-700 rounded-lg p-2 text-slate-200 text-xs placeholder-slate-500 focus:outline-none focus:border-indigo-500"
                  />
                </div>

                {successMsg && (
                  <div className="text-emerald-400 font-semibold text-xs py-1">
                    ✓ {successMsg}
                  </div>
                )}

                <button
                  onClick={handleSave}
                  disabled={saving}
                  className="w-full py-2.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white font-bold transition flex items-center justify-center gap-1.5 shadow-md active:scale-99"
                >
                  <Save className="w-3.5 h-3.5" />
                  <span>{saving ? 'Saving...' : 'Save Review Decision'}</span>
                </button>
              </div>
            </div>

          </div>
        )}

      </div>
    </div>
  );
}
