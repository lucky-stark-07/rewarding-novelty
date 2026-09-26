"use client";

import React from "react";
import { FieldScore as FieldScoreType } from "../types";
import { ClaimCard } from "./ClaimCard";
import { ThumbsUp, ThumbsDown, Target, Sparkles } from "lucide-react";

interface FieldBreakdownProps {
  fieldScores: FieldScoreType[];
  thresholds?: { low: number; high: number };
}

export const FieldBreakdown: React.FC<FieldBreakdownProps> = ({ fieldScores, thresholds }) => {
  const getFieldMeta = (field: string) => {
    switch (field) {
      case "what_you_like":
        return {
          title: "What You Like",
          subtitle: "Positive observations & product capabilities",
          icon: ThumbsUp,
          color: "text-emerald-400",
          border: "border-emerald-500/20",
          bg: "bg-emerald-500/10",
        };
      case "what_you_dislike":
        return {
          title: "What You Dislike",
          subtitle: "Limitations, missing features & frustrations",
          icon: ThumbsDown,
          color: "text-amber-400",
          border: "border-amber-500/20",
          bg: "bg-amber-500/10",
        };
      case "problem_solved":
        return {
          title: "Problem Solved",
          subtitle: "Target workflow or team problem addressed",
          icon: Target,
          color: "text-cyan-400",
          border: "border-cyan-500/20",
          bg: "bg-cyan-500/10",
        };
      default:
        return {
          title: field.replace("_", " "),
          subtitle: "Review section",
          icon: Sparkles,
          color: "text-indigo-400",
          border: "border-indigo-500/20",
          bg: "bg-indigo-500/10",
        };
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-bold text-slate-100 flex items-center gap-2">
          <span>Field-by-Field Claim Assessment</span>
          <span className="px-2 py-0.5 text-xs font-mono font-normal text-slate-400 bg-slate-800 rounded-md border border-slate-700">
            3 review dimensions
          </span>
        </h3>
      </div>

      <div className="grid grid-cols-1 gap-6">
        {fieldScores.map((fieldScore) => {
          const meta = getFieldMeta(fieldScore.field);
          const Icon = meta.icon;
          const scorePercent = Math.round(fieldScore.score * 100);
          const noveltyPercent = Math.round(fieldScore.novelty_fraction * 100);
          const relevancePercent = Math.round(fieldScore.relevance_gate * 100);

          return (
            <div
              key={fieldScore.field}
              className={`glass-card rounded-2xl p-5 border ${meta.border} space-y-4`}
            >
              {/* Field Header */}
              <div className="flex items-center justify-between gap-4 pb-3 border-b border-slate-800/80 flex-wrap">
                <div className="flex items-center gap-3">
                  <div className={`p-2.5 rounded-xl ${meta.bg} ${meta.color}`}>
                    <Icon className="w-5 h-5" />
                  </div>
                  <div>
                    <h4 className="text-base font-bold text-slate-100 flex items-center gap-2">
                      {meta.title}
                    </h4>
                    <p className="text-xs text-slate-400">{meta.subtitle}</p>
                  </div>
                </div>

                {/* Score Pills */}
                <div className="flex items-center gap-2">
                  <div className="px-3 py-1.5 rounded-xl bg-slate-900 border border-slate-800 text-center">
                    <span className="text-[10px] text-slate-400 block font-medium">Field Score</span>
                    <span className={`text-base font-extrabold font-mono ${meta.color}`}>
                      {scorePercent}%
                    </span>
                  </div>

                  <div className="hidden sm:flex gap-2">
                    <div className="px-2.5 py-1 rounded-lg bg-slate-900/60 border border-slate-800 text-center text-xs">
                      <span className="text-[10px] text-slate-400 block">Novelty</span>
                      <span className="font-mono font-bold text-slate-200">{noveltyPercent}%</span>
                    </div>
                    <div className="px-2.5 py-1 rounded-lg bg-slate-900/60 border border-slate-800 text-center text-xs">
                      <span className="text-[10px] text-slate-400 block">Relevance</span>
                      <span className="font-mono font-bold text-slate-200">{relevancePercent}%</span>
                    </div>
                  </div>
                </div>
              </div>

              {/* Claims extracted in this field */}
              {fieldScore.claims.length === 0 ? (
                <div className="p-4 rounded-xl bg-slate-950/40 border border-slate-800/60 text-center">
                  <p className="text-xs text-slate-400 italic">
                    No specific atomic claims could be extracted for this section.
                  </p>
                </div>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {fieldScore.claims.map((claimAss, idx) => (
                    <ClaimCard key={idx} assessment={claimAss} index={idx} thresholds={thresholds} />
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};
