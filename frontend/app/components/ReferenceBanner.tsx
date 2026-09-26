"use client";

import React from "react";
import { Target, ShieldCheck, Zap, Info, FileText, CheckCircle2, Layers } from "lucide-react";

interface ReferenceBannerProps {
  referenceText?: string;
}

export const ReferenceBanner: React.FC<ReferenceBannerProps> = ({
  referenceText = "A cloud collaboration platform for product teams that centralizes project planning, customer feedback, roadmaps, and release notes. It helps distributed teams align on priorities and communicate product decisions without switching between many tools.",
}) => {
  const wordCount = referenceText.trim().split(/\s+/).length;

  return (
    <div className="w-full space-y-6">
      {/* Header Card */}
      <div className="glass-card rounded-2xl p-6 border border-indigo-500/20 shadow-xl relative overflow-hidden">
        <div className="absolute -right-20 -top-20 w-60 h-60 bg-gradient-to-br from-indigo-600/10 via-purple-600/10 to-cyan-500/10 rounded-full blur-3xl pointer-events-none" />

        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 border-b border-slate-800 pb-4">
          <div className="flex items-center gap-3.5">
            <div className="p-3 rounded-2xl bg-indigo-500/10 border border-indigo-500/20 text-indigo-400">
              <Target className="w-7 h-7" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-lg font-bold text-slate-100 tracking-wide">
                  Reference Product Baseline
                </h2>
                <span className="px-2.5 py-0.5 text-xs font-mono font-bold bg-indigo-500/20 text-indigo-300 rounded-full border border-indigo-500/30">
                  {wordCount} / 100 words max
                </span>
              </div>
              <p className="text-xs text-slate-400 mt-1">
                Target product context defined in <code className="text-cyan-300 font-mono">backend/reference.py</code>. All review relevance and novelty scores are evaluated against this product definition.
              </p>
            </div>
          </div>
        </div>

        {/* Text Display */}
        <div className="mt-5 p-5 rounded-xl bg-slate-950/80 border border-slate-800/80 relative">
          <span className="text-[10px] font-bold text-cyan-400 uppercase tracking-wider block mb-1">
            Product Definition Context
          </span>
          <p className="text-base leading-relaxed text-slate-100 font-sans italic font-medium">
            &ldquo;{referenceText}&rdquo;
          </p>
        </div>
      </div>

      {/* Rules & Guidelines Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="glass-card rounded-xl p-4 border border-cyan-500/20 space-y-2">
          <div className="flex items-center gap-2 text-cyan-400">
            <ShieldCheck className="w-4 h-4" />
            <h3 className="text-xs font-bold uppercase tracking-wider">Relevance Gate</h3>
          </div>
          <p className="text-xs text-slate-300 leading-relaxed">
            Claims must directly relate to this reference product definition. Off-topic, gibberish, or generic reviews receive a <strong className="text-cyan-300">0.0 relevance gate score</strong>.
          </p>
        </div>

        <div className="glass-card rounded-xl p-4 border border-purple-500/20 space-y-2">
          <div className="flex items-center gap-2 text-purple-400">
            <Layers className="w-4 h-4" />
            <h3 className="text-xs font-bold uppercase tracking-wider">Novelty Baseline</h3>
          </div>
          <p className="text-xs text-slate-300 leading-relaxed">
            Submissions are extracted into atomic claims and vector-searched against the 50 comparison reviews stored in <code className="text-purple-300 font-mono">corpus.json</code>.
          </p>
        </div>

        <div className="glass-card rounded-xl p-4 border border-indigo-500/20 space-y-2">
          <div className="flex items-center gap-2 text-indigo-400">
            <Zap className="w-4 h-4" />
            <h3 className="text-xs font-bold uppercase tracking-wider">LLM Entailment Judge</h3>
          </div>
          <p className="text-xs text-slate-300 leading-relaxed">
            Claims in the ambiguous similarity band (0.48–0.82 cosine sim) are judged by Gemini for semantic coverage and paraphrase detection.
          </p>
        </div>
      </div>

      {/* Field Intents Reference */}
      <div className="glass-card rounded-2xl p-5 border border-slate-800 space-y-4">
        <h3 className="text-sm font-bold text-slate-200 uppercase tracking-wider">
          Expected Review Field Intents
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs">
          <div className="p-3.5 rounded-xl bg-slate-950/60 border border-emerald-500/20">
            <span className="text-emerald-400 font-bold block mb-1">What You Like</span>
            <p className="text-slate-300 text-[11px]">
              Concrete positive product capabilities, specific benefits, or workflow improvements experienced by product teams.
            </p>
          </div>
          <div className="p-3.5 rounded-xl bg-slate-950/60 border border-amber-500/20">
            <span className="text-amber-400 font-bold block mb-1">What You Dislike</span>
            <p className="text-slate-300 text-[11px]">
              Concrete limitations, missing feature requests, frustrations, or specific UX bottlenecks encountered.
            </p>
          </div>
          <div className="p-3.5 rounded-xl bg-slate-950/60 border border-cyan-500/20">
            <span className="text-cyan-400 font-bold block mb-1">Problem Solved</span>
            <p className="text-slate-300 text-[11px]">
              Product-team workflow, alignment challenge, or communication gap that this platform directly addresses.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};
