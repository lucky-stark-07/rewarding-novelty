"use client";

import React from "react";
import { ClaimAssessment } from "../types";
import { CheckCircle2, XCircle, HelpCircle, Layers, Sparkles, AlertCircle, ArrowRight } from "lucide-react";

interface ClaimCardProps {
  assessment: ClaimAssessment;
  index: number;
}

export const ClaimCard: React.FC<ClaimCardProps> = ({ assessment, index }) => {
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
  } = assessment;

  const isNovel = novelty_status === "novel" || novelty_score > 0.5;
  const simPercent = typeof nearest_similarity === "number" ? Math.round(nearest_similarity * 100) : null;
  const relPercent = Math.round(relevance_score * 100);

  // Field badge color mapping
  const fieldLabel = claim.field ? claim.field.replace("_", " ") : "claim";
  const fieldColors: Record<string, string> = {
    what_you_like: "bg-emerald-500/10 text-emerald-400 border-emerald-500/30",
    what_you_dislike: "bg-amber-500/10 text-amber-400 border-amber-500/30",
    problem_solved: "bg-cyan-500/10 text-cyan-400 border-cyan-500/30",
  };

  return (
    <div className={`p-4 rounded-xl glass-card border transition-all duration-200 ${
      isNovel
        ? "border-emerald-500/30 hover:border-emerald-500/50 hover:shadow-lg hover:shadow-emerald-500/10"
        : "border-rose-500/20 hover:border-rose-500/40"
    }`}>
      {/* Top Header Row */}
      <div className="flex items-center justify-between gap-3 mb-2.5 flex-wrap">
        <div className="flex items-center gap-2">
          {/* Status Badge */}
          {isNovel ? (
            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-bold bg-emerald-500/15 text-emerald-300 border border-emerald-500/40">
              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
              Novel Claim
            </span>
          ) : (
            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-bold bg-rose-500/15 text-rose-300 border border-rose-500/40">
              <XCircle className="w-3.5 h-3.5 text-rose-400" />
              Covered / Redundant
            </span>
          )}

          {/* Entailment Badge */}
          {entailment_judged && (
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-medium bg-purple-500/15 text-purple-300 border border-purple-500/30" title="Middle similarity band was evaluated by OpenRouter LLM judge for entailment">
              <Sparkles className="w-3 h-3 text-purple-400" />
              LLM Entailment Judged
            </span>
          )}
        </div>

        {/* Field Name Badge */}
        <span className={`px-2.5 py-0.5 rounded-md text-[11px] font-semibold tracking-wide uppercase border ${fieldColors[claim.field || ""] || "bg-slate-800 text-slate-300 border-slate-700"}`}>
          {fieldLabel}
        </span>
      </div>

      {/* Main Extracted Claim Text */}
      <div className="p-3 rounded-lg bg-slate-950/80 border border-slate-800/80 mb-3">
        <p className="text-sm font-semibold text-slate-100 leading-snug">
          &ldquo;{claim.text}&rdquo;
        </p>
      </div>

      {/* Scoring Metrics Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs mb-3">
        {/* Relevance Metric */}
        <div className="p-2.5 rounded-lg bg-slate-900/60 border border-slate-800">
          <div className="flex items-center justify-between mb-1">
            <span className="text-slate-400 font-medium">Relevance Gate</span>
            <span className="font-mono font-bold text-slate-200">{relPercent}%</span>
          </div>
          <div className="w-full h-1.5 bg-slate-800 rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full transition-all duration-500 ${
                relPercent >= 70 ? "bg-emerald-400" : relPercent >= 40 ? "bg-amber-400" : "bg-rose-400"
              }`}
              style={{ width: `${relPercent}%` }}
            />
          </div>
          {relevance_reason && (
            <p className="text-[11px] text-slate-400 mt-1.5 italic line-clamp-2">
              Reason: {relevance_reason}
            </p>
          )}
        </div>

        {/* Nearest Similarity Metric */}
        {simPercent !== null && (
          <div className="p-2.5 rounded-lg bg-slate-900/60 border border-slate-800">
            <div className="flex items-center justify-between mb-1">
              <span className="text-slate-400 font-medium">Nearest Vector Sim</span>
              <span className="font-mono font-bold text-slate-200">{simPercent}%</span>
            </div>
            <div className="w-full h-1.5 bg-slate-800 rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full transition-all duration-500 ${
                  simPercent >= 65 ? "bg-rose-400" : simPercent <= 35 ? "bg-emerald-400" : "bg-purple-400"
                }`}
                style={{ width: `${simPercent}%` }}
              />
            </div>
            <p className="text-[11px] text-slate-400 mt-1.5">
              {simPercent >= 65
                ? "≥ 65% (High similarity: Covered)"
                : simPercent <= 35
                ? "≤ 35% (Low similarity: Novel)"
                : "35-65% (LLM checked entailment)"}
            </p>
          </div>
        )}
      </div>

      {/* Nearest Corpus Match Callout */}
      {nearest_claim && (
        <div className="mt-2.5 p-2.5 rounded-lg bg-indigo-950/30 border border-indigo-500/20 text-xs">
          <div className="flex items-center gap-1.5 text-indigo-300 font-semibold mb-1">
            <ArrowRight className="w-3.5 h-3.5" />
            <span>Nearest Corpus Match</span>
          </div>
          <p className="text-slate-300 italic text-[11px]">
            &ldquo;{nearest_claim.text}&rdquo;
          </p>
        </div>
      )}

      {/* Entailment Reason Callout */}
      {entailment_reason && (
        <div className="mt-2.5 p-2.5 rounded-lg bg-purple-950/30 border border-purple-500/20 text-xs">
          <div className="flex items-center gap-1.5 text-purple-300 font-semibold mb-1">
            <Sparkles className="w-3.5 h-3.5" />
            <span>Judge Entailment Reason</span>
          </div>
          <p className="text-purple-200 text-[11px]">
            {entailment_reason}
          </p>
        </div>
      )}
    </div>
  );
};
