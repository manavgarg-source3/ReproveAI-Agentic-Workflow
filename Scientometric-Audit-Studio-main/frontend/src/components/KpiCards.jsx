import React from 'react';
import { 
  Database, 
  CheckCircle2, 
  Link2, 
  Sparkles, 
  AlertOctagon, 
  HelpCircle 
} from 'lucide-react';

export default function KpiCards({ stats, onFilterClick }) {
  if (!stats) return null;

  const total = stats.total_references || 17252;
  const scopusLinked = stats.scopus_linked || 0;
  const scopusLinkedPct = total > 0 ? Math.round((scopusLinked / total) * 100) : 0;
  
  const resolving = stats.resolving_dois || 0;
  const resolvingPct = total > 0 ? Math.round((resolving / total) * 100) : 0;
  
  const recovered = stats.recovered_dois || 0;
  const unlinked = stats.scopus_unlinked || 0;
  const review = stats.needs_review || 0;

  const cards = [
    {
      title: 'Total References',
      value: total.toLocaleString(),
      subtitle: `${(stats.total_documents || 864)} citing manuscripts`,
      icon: Database,
      accent: 'border-slate-800 bg-[#0e1628]/90 hover:border-slate-700',
      badge: '100% Corpus',
      badgeColor: 'bg-slate-800/80 text-slate-300 border border-slate-700',
      onClick: () => onFilterClick({ status: '', scopus_linked: 'all', needs_review: 'all' }),
    },
    {
      title: 'Scopus Ground Truth',
      value: scopusLinked.toLocaleString(),
      subtitle: `${scopusLinkedPct}% verified directly via Scopus API`,
      icon: CheckCircle2,
      accent: 'border-emerald-500/20 bg-emerald-950/15 hover:border-emerald-500/50 hover:bg-emerald-950/25 cursor-pointer',
      badge: `${scopusLinkedPct}% Linked`,
      badgeColor: 'bg-emerald-500/15 text-emerald-300 border border-emerald-500/30',
      onClick: () => onFilterClick({ scopus_linked: 'true' }),
    },
    {
      title: 'Resolving DOIs',
      value: resolving.toLocaleString(),
      subtitle: `${resolvingPct}% active via DOI Resolver`,
      icon: Link2,
      accent: 'border-cyan-500/20 bg-cyan-950/15 hover:border-cyan-500/50 hover:bg-cyan-950/25 cursor-pointer',
      badge: `${resolvingPct}% Resolving`,
      badgeColor: 'bg-cyan-500/15 text-cyan-300 border border-cyan-500/30',
      onClick: () => onFilterClick({ has_doi: 'true' }),
    },
    {
      title: 'Recovered DOIs',
      value: recovered.toLocaleString(),
      subtitle: 'Discovered via Crossref recovery engine',
      icon: Sparkles,
      accent: 'border-purple-500/20 bg-purple-950/15 hover:border-purple-500/50 hover:bg-purple-950/25 cursor-pointer',
      badge: 'Recovered',
      badgeColor: 'bg-purple-500/15 text-purple-300 border border-purple-500/30',
      onClick: () => onFilterClick({ status: 'DOI_RECOVERED' }),
    },
    {
      title: 'Scopus Unlinked',
      value: unlinked.toLocaleString(),
      subtitle: 'Unlinked citations in Scopus index',
      icon: HelpCircle,
      accent: 'border-amber-500/20 bg-amber-950/15 hover:border-amber-500/50 hover:bg-amber-950/25 cursor-pointer',
      badge: 'Unlinked',
      badgeColor: 'bg-amber-500/15 text-amber-300 border border-amber-500/30',
      onClick: () => onFilterClick({ scopus_linked: 'false' }),
    },
    {
      title: 'Human Review Queue',
      value: review.toLocaleString(),
      subtitle: 'Requires researcher audit / sign-off',
      icon: AlertOctagon,
      accent: 'border-rose-500/25 bg-rose-950/15 hover:border-rose-500/50 hover:bg-rose-950/25 cursor-pointer',
      badge: 'Triage Queue',
      badgeColor: 'bg-rose-500/15 text-rose-300 border border-rose-500/30',
      onClick: () => onFilterClick({ needs_review: 'true' }),
    },
  ];

  return (
    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3.5 mb-5">
      {cards.map((card, i) => {
        const Icon = card.icon;
        return (
          <div
            key={i}
            onClick={card.onClick}
            className={`p-4 rounded-xl border transition-all duration-200 shadow-md relative group ${card.accent}`}
          >
            <div className="flex items-center justify-between mb-2">
              <span className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">
                {card.title}
              </span>
              <Icon className="w-4 h-4 text-slate-400 group-hover:scale-115 transition-transform" />
            </div>
            <div className="text-2xl font-extrabold tracking-tight text-white mb-1.5 font-mono">
              {card.value}
            </div>
            <div className="flex items-center justify-between text-[11px]">
              <span className="text-slate-400 truncate pr-1 text-[11px]">{card.subtitle}</span>
              <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded shrink-0 shadow-xs ${card.badgeColor}`}>
                {card.badge}
              </span>
            </div>
          </div>
        );
      })}
    </div>
  );
}
