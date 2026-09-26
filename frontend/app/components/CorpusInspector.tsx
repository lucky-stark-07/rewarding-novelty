"use client";

import React, { useState } from "react";
import { CorpusEntry, FieldName } from "../types";
import { Database, Search, RefreshCw, Layers, ThumbsUp, ThumbsDown, Target, FileText, CheckCircle2 } from "lucide-react";

interface CorpusInspectorProps {
  corpus: CorpusEntry[];
  onRegenerateCorpus: () => Promise<void>;
  loadingRegen: boolean;
}

export const CorpusInspector: React.FC<CorpusInspectorProps> = ({
  corpus,
  onRegenerateCorpus,
  loadingRegen,
}) => {
  const [searchTerm, setSearchTerm] = useState("");
  const [selectedField, setSelectedField] = useState<string>("all");

  const totalReviews = corpus.length;
  const allClaims = corpus.flatMap((entry) => entry.claims || []);
  const totalClaims = allClaims.length;

  const fieldCounts = {
    what_you_like: allClaims.filter((c) => c.field === "what_you_like").length,
    what_you_dislike: allClaims.filter((c) => c.field === "what_you_dislike").length,
    problem_solved: allClaims.filter((c) => c.field === "problem_solved").length,
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

        {/* Action Button */}
        <button
          onClick={onRegenerateCorpus}
          disabled={loadingRegen}
          className="w-full md:w-auto px-5 py-3 rounded-xl font-semibold text-xs text-white bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 transition-all shadow-lg shadow-indigo-600/20 flex items-center justify-center gap-2 shrink-0 border border-indigo-400/30"
        >
          <RefreshCw className={`w-4 h-4 ${loadingRegen ? "animate-spin" : ""}`} />
          <span>{loadingRegen ? "Generating 50 Reviews..." : "Regenerate Synthetic Corpus"}</span>
        </button>
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
              ? "The comparison corpus is currently empty. Click 'Regenerate Synthetic Corpus' to populate it with 50 synthetic review samples."
              : "No reviews match your current search query. Try clearing the search filter."}
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {filteredEntries.slice(0, 20).map((entry, i) => (
            <div
              key={entry.id || i}
              className="p-4 rounded-xl glass-card border border-slate-800 hover:border-indigo-500/30 transition-all space-y-3"
            >
              <div className="flex items-center justify-between text-xs text-slate-400 border-b border-slate-800/80 pb-2">
                <span className="font-mono font-bold text-indigo-400">#{entry.id}</span>
                <span className="bg-slate-900 px-2 py-0.5 rounded text-[10px]">
                  {entry.claims.length} Extracted Claims
                </span>
              </div>

              <div className="space-y-2 text-xs">
                <div>
                  <span className="text-[10px] uppercase font-bold text-emerald-400 block mb-0.5">
                    What You Like
                  </span>
                  <p className="text-slate-300 line-clamp-2 italic">
                    &ldquo;{entry.submission.what_you_like}&rdquo;
                  </p>
                </div>

                <div>
                  <span className="text-[10px] uppercase font-bold text-amber-400 block mb-0.5">
                    What You Dislike
                  </span>
                  <p className="text-slate-300 line-clamp-2 italic">
                    &ldquo;{entry.submission.what_you_dislike}&rdquo;
                  </p>
                </div>

                <div>
                  <span className="text-[10px] uppercase font-bold text-cyan-400 block mb-0.5">
                    Problem Solved
                  </span>
                  <p className="text-slate-300 line-clamp-2 italic">
                    &ldquo;{entry.submission.problem_solved}&rdquo;
                  </p>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
