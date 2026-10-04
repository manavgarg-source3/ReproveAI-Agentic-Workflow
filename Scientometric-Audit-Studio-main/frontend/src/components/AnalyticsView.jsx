import React from 'react';
import { 
  BarChart3, 
  PieChart, 
  CheckCircle2, 
  AlertTriangle, 
  Link2, 
  ShieldCheck,
  Award
} from 'lucide-react';

const STATUS_COLORS = {
  VALID_CORRECT: 'bg-emerald-500',
  SCOPUS_LINKED_NO_DOI: 'bg-cyan-500',
  SCOPUS_UNLINKED: 'bg-amber-500',
  DOI_RECOVERED: 'bg-purple-500',
  ACCESS_RESTRICTED: 'bg-blue-500',
  BROKEN_URL: 'bg-rose-500',
  VALID_DOI_WRONG_REFERENCE: 'bg-red-600',
  DOI_RECOVERY_UNCERTAIN: 'bg-orange-500',
  DOI_MISSING: 'bg-slate-600',
  UNVERIFIED: 'bg-slate-700',
};

export default function AnalyticsView({ stats, onFilterByStatus }) {
  if (!stats) return null;

  const total = stats.total_references || 17252;
  const statusBreakdown = stats.status_breakdown || {};
  const confidenceBreakdown = stats.confidence_breakdown || {};

  return (
    <div className="space-y-5">
      {/* Top Banner */}
      <div className="p-5 rounded-xl bg-gradient-to-r from-indigo-950/40 via-slate-900 to-slate-900 border border-indigo-500/20 flex items-center justify-between">
        <div>
          <h2 className="text-lg font-bold text-white mb-1 flex items-center gap-2">
            <BarChart3 className="w-5 h-5 text-indigo-400" /> Scientometric Distribution & Audit Analytics
          </h2>
          <p className="text-xs text-slate-400">
            Automated diagnostic taxonomy across {stats.total_documents} citing manuscripts and {total.toLocaleString()} bibliographic references.
          </p>
        </div>
        <div className="text-right font-mono">
          <div className="text-2xl font-black text-indigo-300">{total.toLocaleString()}</div>
          <div className="text-[10px] text-slate-400 uppercase tracking-wider">References Audited</div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        
        {/* Status Distribution Breakdown */}
        <div className="bg-[#111827]/90 border border-slate-800 rounded-xl p-5 shadow-lg">
          <h3 className="font-semibold text-sm text-slate-100 mb-4 flex items-center gap-2">
            <ShieldCheck className="w-4 h-4 text-emerald-400" /> Scientometric Status Taxonomy
          </h3>

          <div className="space-y-3">
            {Object.entries(statusBreakdown).map(([status, count]) => {
              const pct = total > 0 ? ((count / total) * 100).toFixed(1) : 0;
              const barColor = STATUS_COLORS[status] || 'bg-indigo-500';

              return (
                <div 
                  key={status}
                  onClick={() => onFilterByStatus(status)}
                  className="p-2 rounded-lg hover:bg-slate-800/40 cursor-pointer transition group"
                >
                  <div className="flex justify-between items-center text-xs mb-1">
                    <span className="font-medium text-slate-300 group-hover:text-indigo-300">
                      {status}
                    </span>
                    <span className="font-mono text-slate-400">
                      <strong className="text-slate-200">{count.toLocaleString()}</strong> ({pct}%)
                    </span>
                  </div>
                  <div className="w-full bg-slate-800 rounded-full h-2 overflow-hidden">
                    <div 
                      className={`h-2 rounded-full ${barColor} transition-all duration-500`}
                      style={{ width: `${Math.max(Number(pct), 1)}%` }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Right Column: Scopus Linkage & Resolution Ratios */}
        <div className="space-y-5">
          
          {/* Scopus Linkage Card */}
          <div className="bg-[#111827]/90 border border-slate-800 rounded-xl p-5 shadow-lg">
            <h3 className="font-semibold text-sm text-slate-100 mb-3 flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 text-cyan-400" /> Scopus Ground-Truth Alignment
            </h3>

            <div className="grid grid-cols-2 gap-3 mb-4">
              <div className="p-3 rounded-lg bg-emerald-950/20 border border-emerald-500/30">
                <span className="text-[10px] text-emerald-300 font-bold uppercase">Linked in Scopus</span>
                <div className="text-xl font-bold text-white mt-0.5">
                  {(stats.scopus_linked || 0).toLocaleString()}
                </div>
                <div className="text-xs text-emerald-400 mt-0.5">
                  {total > 0 ? ((stats.scopus_linked / total) * 100).toFixed(1) : 0}% of all refs
                </div>
              </div>

              <div className="p-3 rounded-lg bg-amber-950/20 border border-amber-500/30">
                <span className="text-[10px] text-amber-300 font-bold uppercase">Unlinked in Scopus</span>
                <div className="text-xl font-bold text-white mt-0.5">
                  {(stats.scopus_unlinked || 0).toLocaleString()}
                </div>
                <div className="text-xs text-amber-400 mt-0.5">
                  {total > 0 ? ((stats.scopus_unlinked / total) * 100).toFixed(1) : 0}% of all refs
                </div>
              </div>
            </div>

            <p className="text-xs text-slate-400 leading-relaxed">
              Scopus identifies citations as either <code className="text-indigo-300 font-mono">resolvedReference</code> (linked to an indexed Scopus record) or <code className="text-amber-300 font-mono">originalReference/other</code> (unindexed monographs, conference presentations, or government reports).
            </p>
          </div>

          {/* Confidence Breakdown Card */}
          <div className="bg-[#111827]/90 border border-slate-800 rounded-xl p-5 shadow-lg">
            <h3 className="font-semibold text-sm text-slate-100 mb-3 flex items-center gap-2">
              <Award className="w-4 h-4 text-purple-400" /> Decision Confidence Distribution
            </h3>

            <div className="grid grid-cols-4 gap-2 text-center">
              {['HIGH', 'MEDIUM', 'LOW', 'UNCERTAIN'].map((conf) => {
                const count = confidenceBreakdown[conf] || 0;
                const pct = total > 0 ? ((count / total) * 100).toFixed(1) : 0;
                return (
                  <div key={conf} className="p-2.5 rounded-lg bg-slate-900/80 border border-slate-800">
                    <span className="text-[10px] font-bold text-slate-400 uppercase">{conf}</span>
                    <div className="text-lg font-bold text-white mt-0.5 font-mono">{count.toLocaleString()}</div>
                    <div className="text-[10px] text-slate-400 mt-0.5">{pct}%</div>
                  </div>
                );
              })}
            </div>
          </div>

        </div>

      </div>
    </div>
  );
}

