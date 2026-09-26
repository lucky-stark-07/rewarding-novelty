"use client";

import React, { useState } from "react";
import { CorpusEntry } from "../types";
import {
  Database,
  Search,
  RefreshCw,
  ThumbsUp,
  ThumbsDown,
  Target,
  FileText,
  ChevronDown,
  ChevronUp,
  Layers,
} from "lucide-react";

interface CorpusInspectorProps {
  corpus: CorpusEntry[];
  onRegenerateCorpus: () => Promise<void>;
  loadingRegen: boolean;
  regenerateEnabled: boolean;
}

export const CorpusInspector: React.FC<CorpusInspectorProps> = ({
  corpus,
  onRegenerateCorpus,
  loadingRegen,
  regenerateEnabled,
}) => {
  const [searchTerm, setSearchTerm] = useState("");
  const [expandedEntries, setExpandedEntries] = useState<Record<string, boolean>>({});

  const totalReviews = corpus.length;
  const allClaims = corpus.flatMap((entry) => entry.claims || []);
  const totalClaims = allClaims.length;

  const fieldCounts = {
    what_you_like: allClaims.filter((c) => c.field === "what_you_like").length,
    what_you_dislike: allClaims.filter((c) => c.field === "what_you_dislike").length,
    problem_solved: allClaims.filter((c) => c.field === "problem_solved").length,
  };

  const toggleExpand = (id: string) => {
    setExpandedEntries((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  const filteredEntries = corpus.filter((entry) => {
    if (!searchTerm) return true;
    const term = searchTerm.toLowerCase();
    const likesMatch = entry.submission.what_you_like.toLowerCase().includes(term);
    const dislikesMatch = entry.submission.what_you_dislike.toLowerCase().includes(term);
    const problemMatch = entry.submission.problem_solved.toLowerCase().includes(term);
    const claimsMatch = entry.claims.some((c) => c.text.toLowerCase().includes(term));
    return likesMatch || dislikesMatch || problemMatch || claimsMatch;
  });

  return (
    <div className="w-full space-y-6">
      {/* Top Banner Stats */}
      <div className="glass-card rounded-2xl p-6 border border-slate-800 shadow-xl flex flex-col md:flex-row items-center justify-between gap-6">
        <div className="flex items-center gap-4">
          <div className="p-3.5 rounded-2xl bg-indigo-500/10 border border-indigo-500/20 text-indigo-400">
            <Database className="w-7 h-7" />
          </div>
          <div>
            <h2 className="text-lg font-bold text-slate-100 flex items-center gap-2">
              <span>Comparison Baseline Corpus</span>
              <span className="px-2.5 py-0.5 text-xs font-mono font-bold bg-indigo-500/20 text-indigo-300 rounded-full border border-indigo-500/30">
                {totalReviews} Submissions
              </span>
            </h2>
            <p className="text-xs text-slate-400 mt-1 max-w-xl">
              Local vector database containing synthetic review claims used as the similarity baseline. New review claims are compared against all stored claims in this corpus.
            </p>
          </div>
        </div>

        {/* Admin-only action: hidden unless the server has ADMIN_TOKEN set */}
        {regenerateEnabled ? (
          <button
            type="button"
            onClick={onRegenerateCorpus}
            disabled={loadingRegen}
            title="Admin only: replaces the whole corpus (asks for confirmation and the admin token)"
            className="w-full md:w-auto px-5 py-3 rounded-xl font-semibold text-xs text-rose-100 bg-rose-600/80 hover:bg-rose-600 disabled:opacity-50 transition-all flex items-center justify-center gap-2 shrink-0 border border-rose-400/30"
          >
            <RefreshCw className={`w-4 h-4 ${loadingRegen ? "animate-spin" : ""}`} />
            <span>{loadingRegen ? "Generating 50 Reviews..." : "Regenerate Corpus (admin)"}</span>
          </button>
        ) : (
          <span className="text-[11px] text-slate-500 max-w-[14rem] md:text-right">
            Read-only baseline. Regeneration is an admin action and is disabled on this server.
          </span>
        )}
      </div>

      {/* Stats Breakdown Bar */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="p-3.5 rounded-xl glass-card border border-slate-800 text-center">
          <span className="text-xs text-slate-400 block font-medium">Total Stored Claims</span>
          <span className="text-xl font-bold font-mono text-cyan-400">{totalClaims}</span>
        </div>
        <div className="p-3.5 rounded-xl glass-card border border-emerald-500/20 text-center">
          <span className="text-xs text-emerald-400 block font-medium flex items-center justify-center gap-1">
            <ThumbsUp className="w-3 h-3" /> Likes Claims
          </span>
          <span className="text-xl font-bold font-mono text-slate-100">{fieldCounts.what_you_like}</span>
        </div>
        <div className="p-3.5 rounded-xl glass-card border border-amber-500/20 text-center">
          <span className="text-xs text-amber-400 block font-medium flex items-center justify-center gap-1">
            <ThumbsDown className="w-3 h-3" /> Dislikes Claims
          </span>
          <span className="text-xl font-bold font-mono text-slate-100">{fieldCounts.what_you_dislike}</span>
        </div>
        <div className="p-3.5 rounded-xl glass-card border border-cyan-500/20 text-center">
          <span className="text-xs text-cyan-400 block font-medium flex items-center justify-center gap-1">
            <Target className="w-3 h-3" /> Problem Claims
          </span>
          <span className="text-xl font-bold font-mono text-slate-100">{fieldCounts.problem_solved}</span>
        </div>
      </div>

      {/* Search & Filter Controls */}
      <div className="flex flex-col sm:flex-row items-center justify-between gap-3">
        <div className="relative w-full sm:w-80">
          <Search className="w-4 h-4 text-slate-500 absolute left-3.5 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            placeholder="Search corpus claims & text..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full pl-10 pr-4 py-2.5 rounded-xl bg-slate-900 border border-slate-800 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-indigo-500/50"
          />
        </div>

        <span className="text-xs text-slate-400 font-mono">
          Showing {filteredEntries.length} of {totalReviews} reviews
        </span>
      </div>

      {/* Corpus Reviews List */}
      {filteredEntries.length === 0 ? (
        <div className="p-12 text-center glass-card rounded-2xl border border-slate-800 space-y-3">
          <FileText className="w-10 h-10 text-slate-600 mx-auto" />
          <h3 className="text-base font-bold text-slate-300">No Corpus Reviews Found</h3>
          <p className="text-xs text-slate-500 max-w-sm mx-auto">
            {totalReviews === 0
              ? "The comparison corpus is empty, so every claim is treated as novel. An admin can populate it with `make gen-corpus` or the admin regenerate action."
              : "No reviews match your current search query. Try clearing the search filter."}
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {filteredEntries.map((entry, i) => {
            const isExpanded = !!expandedEntries[entry.id];
            return (
              <div
                key={entry.id || i}
                className="p-5 rounded-xl glass-card border border-slate-800 hover:border-indigo-500/30 transition-all space-y-4 flex flex-col justify-between"
              >
                {/* Header info */}
                <div className="flex items-center justify-between text-xs text-slate-400 border-b border-slate-800/80 pb-2.5">
                  <span className="font-mono font-bold text-indigo-400 truncate max-w-[200px]" title={entry.id}>
                    #{entry.id}
                  </span>
                  <span className="bg-slate-900 px-2.5 py-1 rounded-md text-[11px] font-mono text-cyan-300 border border-slate-800">
                    {entry.claims.length} Extracted Claims
                  </span>
                </div>

                {/* Review Body (Un-truncated full text) */}
                <div className="space-y-3 text-xs leading-relaxed">
                  <div className="p-3 rounded-lg bg-slate-950/60 border border-slate-800/80">
                    <span className="text-[10px] uppercase font-bold text-emerald-400 flex items-center gap-1 mb-1">
                      <ThumbsUp className="w-3 h-3" /> What You Like
                    </span>
                    <p className="text-slate-200 italic font-sans whitespace-pre-wrap">
                      &ldquo;{entry.submission.what_you_like}&rdquo;
                    </p>
                  </div>

                  <div className="p-3 rounded-lg bg-slate-950/60 border border-slate-800/80">
                    <span className="text-[10px] uppercase font-bold text-amber-400 flex items-center gap-1 mb-1">
                      <ThumbsDown className="w-3 h-3" /> What You Dislike
                    </span>
                    <p className="text-slate-200 italic font-sans whitespace-pre-wrap">
                      &ldquo;{entry.submission.what_you_dislike}&rdquo;
                    </p>
                  </div>

                  <div className="p-3 rounded-lg bg-slate-950/60 border border-slate-800/80">
                    <span className="text-[10px] uppercase font-bold text-cyan-400 flex items-center gap-1 mb-1">
                      <Target className="w-3 h-3" /> Problem Solved
                    </span>
                    <p className="text-slate-200 italic font-sans whitespace-pre-wrap">
                      &ldquo;{entry.submission.problem_solved}&rdquo;
                    </p>
                  </div>
                </div>

                {/* Extracted Atomic Claims Collapsible */}
                {entry.claims.length > 0 && (
                  <div className="pt-2 border-t border-slate-800/80">
                    <button
                      type="button"
                      onClick={() => toggleExpand(entry.id)}
                      className="w-full flex items-center justify-between p-2 rounded-lg bg-slate-900/80 hover:bg-slate-800/80 border border-slate-800 text-[11px] font-semibold text-slate-300 transition-colors"
                    >
                      <span className="flex items-center gap-1.5">
                        <Layers className="w-3.5 h-3.5 text-indigo-400" />
                        {isExpanded ? "Hide Extracted Claims" : `View ${entry.claims.length} Extracted Atomic Claims`}
                      </span>
                      {isExpanded ? <ChevronUp className="w-3.5 h-3.5 text-slate-400" /> : <ChevronDown className="w-3.5 h-3.5 text-slate-400" />}
                    </button>

                    {isExpanded && (
                      <div className="mt-2.5 space-y-1.5 pl-2 border-l-2 border-indigo-500/30">
                        {entry.claims.map((claim, idx) => (
                          <div key={idx} className="p-2 rounded bg-slate-950 text-[11px] text-slate-300 border border-slate-800 flex items-start gap-2">
                            <span className="px-1.5 py-0.5 rounded text-[9px] font-mono uppercase bg-slate-900 text-slate-400 border border-slate-800 shrink-0">
                              {claim.field ? claim.field.replace("_", " ") : "claim"}
                            </span>
                            <span className="font-mono text-slate-200">&ldquo;{claim.text}&rdquo;</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
