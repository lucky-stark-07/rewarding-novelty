"use client";

import React, { useState } from "react";
import { Info, Target, FileText, ChevronDown, ChevronUp } from "lucide-react";

interface ReferenceBannerProps {
  referenceText?: string;
}

export const ReferenceBanner: React.FC<ReferenceBannerProps> = ({
  referenceText = "A cloud collaboration platform for product teams that centralizes project planning, customer feedback, roadmaps, and release notes. It helps distributed teams align on priorities and communicate product decisions without switching between many tools.",
}) => {
  const [isExpanded, setIsExpanded] = useState(true);
  const wordCount = referenceText.trim().split(/\s+/).length;

  return (
    <div className="w-full glass-card rounded-2xl p-5 border border-indigo-500/20 shadow-xl relative overflow-hidden group">
      {/* Subtle background gradient splash */}
      <div className="absolute -right-20 -top-20 w-60 h-60 bg-gradient-to-br from-indigo-600/10 via-purple-600/10 to-cyan-500/10 rounded-full blur-3xl pointer-events-none" />

      <div className="flex items-start justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="p-2.5 rounded-xl bg-indigo-500/10 border border-indigo-500/20 text-indigo-400">
            <Target className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-sm font-bold text-slate-100 tracking-wide uppercase">
                Reference Product Baseline
              </h2>
              <span className="px-2 py-0.5 text-[10px] font-mono font-medium bg-slate-800 text-slate-300 rounded-md border border-slate-700">
                {wordCount} words
              </span>
            </div>
            <p className="text-xs text-slate-400 mt-0.5">
              Review novelty and relevance are strictly judged against this baseline description & corpus.
            </p>
          </div>
        </div>

        <button
          onClick={() => setIsExpanded(!isExpanded)}
          className="p-1.5 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-slate-800/60 transition-colors"
          title={isExpanded ? "Collapse reference text" : "Expand reference text"}
        >
          {isExpanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
        </button>
      </div>

      {isExpanded && (
        <div className="mt-4 pt-3.5 border-t border-slate-800/80">
          <div className="p-3.5 rounded-xl bg-slate-950/70 border border-slate-800/80 relative">
            <p className="text-xs leading-relaxed text-slate-300 italic font-sans">
              &ldquo;{referenceText}&rdquo;
            </p>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mt-3 text-[11px] text-slate-400">
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-cyan-400" />
              <span>
                <strong className="text-slate-200">Relevance Gate:</strong> Off-topic claims score 0.
              </span>
            </div>
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-purple-400" />
              <span>
                <strong className="text-slate-200">Novelty Threshold:</strong> Cosine sim comparison against 50 corpus reviews.
              </span>
            </div>
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-indigo-400" />
              <span>
                <strong className="text-slate-200">LLM Judge:</strong> Ambiguous matches checked for semantic entailment.
              </span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
