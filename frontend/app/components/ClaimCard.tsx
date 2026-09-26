"use client";

import React from "react";
import { ClaimAssessment } from "../types";
import { CheckCircle2, XCircle, HelpCircle, Sparkles, ArrowRight, ShieldCheck, Zap } from "lucide-react";

interface ClaimCardProps {
  assessment: ClaimAssessment;
  index: number;
  thresholds?: { low: number; high: number };
}

export const ClaimCard: React.FC<ClaimCardProps> = ({ assessment, index, thresholds }) => {
  const lowPct = thresholds ? Math.round(thresholds.low * 100) : null;
  const highPct = thresholds ? Math.round(thresholds.high * 100) : null;
  const {
    claim,
    novelty_status,
    novelty_score,
    relevance_score,
    relevance_reason,
    nearest_claim,
    nearest_similarity,
    entailment_judged,
    entailment_reason,
    neighbors = [],
  } = assessment;

  const isNovel = novelty_status === "novel";
  const isPartial = novelty_status === "partial";
  const otherNeighbors = neighbors.filter((n) => n.claim.text !== nearest_claim?.text);
  const simPercent = typeof nearest_similarity === "number" ? Math.round(nearest_similarity * 100) : null;
  const relPercent = Math.round(relevance_score * 100);

  const fieldLabel = claim.field ? claim.field.replace("_", " ") : "claim";
  const fieldColors: Record<string, string> = {
    what_you_like: "bg-emerald-500/10 text-emerald-400 border-emerald-500/30",
    what_you_dislike: "bg-amber-500/10 text-amber-400 border-amber-500/30",
    problem_solved: "bg-cyan-500/10 text-cyan-400 border-cyan-500/30",
  };

  return (
    <div
      className={`p-5 rounded-2xl glass-card border transition-all duration-300 space-y-4 ${
        isNovel
          ? "border-emerald-500/40 hover:border-emerald-500/60 shadow-lg shadow-emerald-500/5"
          : isPartial
          ? "border-amber-500/40 hover:border-amber-500/60"
          : "border-rose-500/30 hover:border-rose-500/50"
      }`}
    >
      {/* Top Badge Header Row */}
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-2 flex-wrap">
          {/* Status Badge */}
          {isNovel ? (
            <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 shadow-sm">
              <CheckCircle2 className="w-4 h-4 text-emerald-400" />
              Novel Claim
            </span>
          ) : isPartial ? (
            <span
              className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold bg-amber-500/20 text-amber-300 border border-amber-500/40"
              title="Core observation exists in the corpus, but this claim adds a new detail"
            >
              <HelpCircle className="w-4 h-4 text-amber-400" />
              Partly New · {Math.round(novelty_score * 100)}% credit
            </span>
          ) : (
            <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold bg-rose-500/20 text-rose-300 border border-rose-500/40">
              <XCircle className="w-4 h-4 text-rose-400" />
              Covered / Redundant
            </span>
          )}

          {/* Entailment Badge */}
          {entailment_judged && (
            <span
              className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-[11px] font-semibold bg-purple-500/20 text-purple-300 border border-purple-500/30"
              title="Middle similarity band was evaluated by OpenRouter LLM judge for entailment"
            >
              <Sparkles className="w-3.5 h-3.5 text-purple-400" />
              LLM Entailment Judged
            </span>
          )}
        </div>

        {/* Field Name Badge */}
        <span
          className={`px-3 py-1 rounded-md text-xs font-bold tracking-wide uppercase border ${
            fieldColors[claim.field || ""] || "bg-slate-800 text-slate-300 border-slate-700"
          }`}
        >
          {fieldLabel}
        </span>
      </div>

      {/* Main Extracted Claim Text */}
      <div className="p-4 rounded-xl bg-slate-950/90 border border-slate-800/90 shadow-inner">
        <span className="text-[10px] font-bold uppercase tracking-wider text-slate-500 block mb-1">
          Extracted Atomic Claim #{index + 1}
        </span>
        <p className="text-base font-semibold text-slate-100 leading-relaxed font-sans">
          &ldquo;{claim.text}&rdquo;
        </p>
      </div>

      {/* Scoring Metrics Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3.5 text-xs">
        {/* Relevance Metric */}
        <div className="p-3 rounded-xl bg-slate-900/80 border border-slate-800 space-y-1.5">
          <div className="flex items-center justify-between font-semibold">
            <span className="text-slate-300 flex items-center gap-1">
              <ShieldCheck className="w-3.5 h-3.5 text-cyan-400" /> Relevance Gate
            </span>
            <span className="font-mono font-bold text-slate-100 text-sm">{relPercent}%</span>
          </div>
          <div className="w-full h-2 bg-slate-950 rounded-full overflow-hidden border border-slate-800">
            <div
              className={`h-full rounded-full transition-all duration-500 ${
                relPercent >= 70 ? "bg-emerald-400" : relPercent >= 40 ? "bg-amber-400" : "bg-rose-400"
              }`}
              style={{ width: `${relPercent}%` }}
            />
          </div>
          {relevance_reason && (
            <p className="text-[11px] text-slate-400 mt-1 italic leading-normal">
              {relevance_reason}
            </p>
          )}
        </div>

        {/* Nearest Similarity Metric */}
        {simPercent !== null && (
          <div className="p-3 rounded-xl bg-slate-900/80 border border-slate-800 space-y-1.5">
            <div className="flex items-center justify-between font-semibold">
              <span className="text-slate-300 flex items-center gap-1">
                <Zap className="w-3.5 h-3.5 text-purple-400" /> Vector Similarity
              </span>
              <span className="font-mono font-bold text-slate-100 text-sm">{simPercent}%</span>
            </div>
            <div className="w-full h-2 bg-slate-950 rounded-full overflow-hidden border border-slate-800">
              <div
                className={`h-full rounded-full transition-all duration-500 ${
                  entailment_judged ? "bg-purple-400" : isNovel ? "bg-emerald-400" : isPartial ? "bg-amber-400" : "bg-rose-400"
                }`}
                style={{ width: `${simPercent}%` }}
              />
            </div>
            <p className="text-[11px] text-slate-400 mt-1">
              {entailment_judged
                ? "Ambiguous similarity band checked by LLM judge"
                : isNovel
                ? `Low similarity band${lowPct !== null ? ` (≤ ${lowPct}%)` : ""}: novel`
                : isPartial
                ? "Ambiguous band: partial credit"
                : `High similarity band${highPct !== null ? ` (≥ ${highPct}%)` : ""}: covered`}
            </p>
          </div>
        )}
      </div>

      {/* Nearest Corpus Match Callout */}
      {nearest_claim && (
        <div className="p-3.5 rounded-xl bg-indigo-950/40 border border-indigo-500/25 text-xs space-y-1">
          <div className="flex items-center gap-1.5 text-indigo-300 font-bold uppercase tracking-wider text-[10px]">
            <ArrowRight className="w-3.5 h-3.5" />
            <span>Closest Corpus Baseline Match</span>
          </div>
          <p className="text-slate-200 italic text-xs leading-relaxed font-sans">
            &ldquo;{nearest_claim.text}&rdquo;
          </p>
          {otherNeighbors.length > 0 && (
            <div className="pt-2 mt-2 border-t border-indigo-500/20 space-y-1">
              <span className="text-[10px] text-slate-400 font-mono block">Other top vector matches:</span>
              {otherNeighbors.map((n) => (
                <div key={n.claim.id ?? n.claim.text} className="flex items-center justify-between text-[11px] text-slate-300">
                  <span className="italic truncate max-w-[80%]">&ldquo;{n.claim.text}&rdquo;</span>
                  <span className="font-mono text-cyan-300 font-bold">{Math.round(n.similarity * 100)}%</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Entailment Reason Callout */}
      {entailment_reason && (
        <div className="p-3.5 rounded-xl bg-purple-950/40 border border-purple-500/25 text-xs space-y-1">
          <div className="flex items-center gap-1.5 text-purple-300 font-bold uppercase tracking-wider text-[10px]">
            <Sparkles className="w-3.5 h-3.5" />
            <span>LLM Entailment Judgment Reasoning</span>
          </div>
          <p className="text-purple-200 text-xs leading-relaxed">
            {entailment_reason}
          </p>
        </div>
      )}
    </div>
  );
};
