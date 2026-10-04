import React, { useState, useEffect } from 'react';
import { Search, Files, ArrowRight, ExternalLink, BookOpen } from 'lucide-react';

export default function DocumentsView({ onSelectDocument }) {
  const [docs, setDocs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');

  useEffect(() => {
    setLoading(true);
    fetch(`/api/documents?q=${encodeURIComponent(search)}&limit=150`)
      .then((res) => res.json())
      .then((data) => {
        setDocs(data.items || []);
        setLoading(false);
      })
      .catch((err) => {
        console.error('Error fetching documents:', err);
        setLoading(false);
      });
  }, [search]);

  return (
    <div className="space-y-4">
      {/* Search header */}
      <div className="flex items-center justify-between gap-4 bg-[#111827]/90 border border-slate-800 p-4 rounded-xl">
        <div className="flex items-center gap-2 text-slate-300">
          <Files className="w-5 h-5 text-indigo-400" />
          <span className="font-semibold text-sm">Citing Manuscripts Directory</span>
          <span className="text-xs text-slate-500">({docs.length} papers listed)</span>
        </div>

        <div className="relative w-80">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search manuscripts by title, author, or EID..."
            className="w-full pl-9 pr-3 py-1.5 bg-slate-900 border border-slate-700 rounded-lg text-xs text-slate-200 focus:outline-none focus:border-indigo-500"
          />
        </div>
      </div>

      {/* Manuscripts Grid */}
      {loading ? (
        <div className="bg-[#111827]/90 border border-slate-800 rounded-xl p-12 text-center">
          <div className="w-8 h-8 border-3 border-indigo-500 border-t-transparent rounded-full animate-spin mx-auto mb-3"></div>
          <p className="text-slate-400 text-xs">Loading manuscript metadata...</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {docs.map((doc) => {
            const linkedPct = doc.ref_count > 0 ? Math.round((doc.linked_count / doc.ref_count) * 100) : 0;
            return (
              <div
                key={doc.source_eid}
                onClick={() => onSelectDocument(doc.source_eid)}
                className="p-4 rounded-xl bg-[#111827]/90 border border-slate-800 hover:border-indigo-500/50 hover:bg-slate-900/60 transition cursor-pointer group shadow-sm flex flex-col justify-between"
              >
                <div>
                  <div className="flex items-center justify-between text-[11px] text-slate-400 mb-1">
                    <span className="font-mono text-indigo-300 font-semibold">{doc.source_eid}</span>
                    <span className="bg-slate-800 px-2 py-0.5 rounded text-[10px] font-bold text-slate-300">
                      {doc.source_year || 'N/A'}
                    </span>
                  </div>

                  <h3 className="font-semibold text-slate-100 text-sm line-clamp-2 group-hover:text-indigo-200 mb-1">
                    {doc.source_title || 'Untitled Manuscript'}
                  </h3>

                  <p className="text-xs text-slate-400 line-clamp-1 mb-3">
                    {doc.source_authors}
                  </p>
                </div>

                <div className="pt-3 border-t border-slate-800/80 flex items-center justify-between text-xs">
                  <div className="flex items-center gap-3">
                    <span className="font-bold text-slate-200">
                      {doc.ref_count} <span className="font-normal text-slate-400 text-[11px]">refs</span>
                    </span>
                    <span className="text-[11px] text-emerald-400 font-semibold">
                      {linkedPct}% Scopus linked
                    </span>
                    {doc.review_count > 0 && (
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-300 border border-amber-500/30">
                        {doc.review_count} to review
                      </span>
                    )}
                  </div>

                  <span className="text-indigo-400 group-hover:translate-x-1 transition-transform flex items-center gap-1 text-[11px] font-medium">
                    View Refs <ArrowRight className="w-3 h-3" />
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

