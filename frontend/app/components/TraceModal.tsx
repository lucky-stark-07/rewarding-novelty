"use client";

import React, { useEffect, useState } from "react";
import {
  Activity,
  AlertTriangle,
  Clock,
  DollarSign,
  Cpu,
  Layers,
  Sparkles,
  Zap,
  Info,
  X,
} from "lucide-react";
import { ScoreMeta, TraceSpan } from "../types";

const LABELS: Record<string, string> = {
  dedupe: "Duplicate check",
  extract: "Extract claims",
  embed: "Embed claims (local CPU)",
  search: "Top-k vector search",
  relevance: "Relevance judge",
  entail: "Coverage judge",
  aggregate: "Aggregate scores",
  corpus_append: "Corpus append",
  "llm.call": "Upstream LLM API call",
};

const FIELD_LABELS: Record<string, { name: string; color: string; bg: string }> = {
  what_you_like: { name: "Like", color: "text-emerald-400", bg: "bg-emerald-500/10 border-emerald-500/20" },
  what_you_dislike: { name: "Dislike", color: "text-amber-400", bg: "bg-amber-500/10 border-amber-500/20" },
  problem_solved: { name: "Solved", color: "text-cyan-400", bg: "bg-cyan-500/10 border-cyan-500/20" },
};

function getSpanCategory(span: TraceSpan) {
  if (span.attrs.degraded) return { label: "Degraded", color: "bg-amber-400", border: "border-amber-500/30", text: "text-amber-400", icon: AlertTriangle };
  if (span.name === "llm.call") return { label: "LLM Upstream", color: "bg-fuchsia-400", border: "border-fuchsia-500/30", text: "text-fuchsia-400", icon: Sparkles };
  if (span.name === "extract") return { label: "Claim Extraction", color: "bg-sky-400", border: "border-sky-500/30", text: "text-sky-400", icon: Layers };
  if (span.name === "relevance") return { label: "Relevance Judge", color: "bg-purple-400", border: "border-purple-500/30", text: "text-purple-400", icon: Zap };
  if (span.name === "entail") return { label: "Coverage Judge", color: "bg-indigo-400", border: "border-indigo-500/30", text: "text-indigo-400", icon: Activity };
  if (span.name === "embed" || span.name === "search") return { label: "Local Vector CPU", color: "bg-cyan-400", border: "border-cyan-500/30", text: "text-cyan-400", icon: Cpu };
  return { label: "Pipeline Stage", color: "bg-slate-400", border: "border-slate-700", text: "text-slate-400", icon: Clock };
}

function getSpanTitle(span: TraceSpan): string {
  const base = LABELS[span.name] ?? span.name;
  const fieldKey = typeof span.attrs.field === "string" ? span.attrs.field : null;
  const fieldMeta = fieldKey ? FIELD_LABELS[fieldKey] : null;
  return fieldMeta ? `${base} · ${fieldMeta.name}` : base;
}

interface TraceModalProps {
  isOpen: boolean;
  onClose: () => void;
  meta?: ScoreMeta;
}

export const TraceModal: React.FC<TraceModalProps> = ({ isOpen, onClose, meta }) => {
  const [selectedSpanIndex, setSelectedSpanIndex] = useState<number | null>(null);

  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = "hidden";
    } else {
      document.body.style.overflow = "";
    }
    return () => {
      document.body.style.overflow = "";
    };
  }, [isOpen]);

  if (!isOpen || !meta) return null;

  const spans = meta.spans ?? [];
  const totalMs = Math.max(meta.total_latency_ms ?? 0, ...spans.map((s) => s.start_ms + s.duration_ms), 1);
  const selectedSpan = selectedSpanIndex !== null ? spans[selectedSpanIndex] : null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-md animate-in fade-in duration-200">
      <div className="relative w-full max-w-3xl max-h-[90vh] glass-card rounded-2xl border border-indigo-500/30 shadow-2xl flex flex-col overflow-hidden">
        {/* Modal Header */}
        <div className="flex items-center justify-between p-5 border-b border-slate-800 bg-slate-900/80">
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-xl bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">
              <Activity className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-base font-bold text-slate-100 flex items-center gap-2">
                <span>Execution Trace & Telemetry Details</span>
                {meta.degraded && (
                  <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-500/20 text-amber-300 border border-amber-500/40">
                    Degraded Mode
                  </span>
                )}
              </h3>
              <p className="text-xs text-slate-400 font-mono">
                Trace ID: {meta.trace_id} · Total Latency: {totalMs.toFixed(0)} ms
              </p>
            </div>
          </div>

          <button
            type="button"
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Modal Body */}
        <div className="flex-1 overflow-y-auto p-5 space-y-5 text-xs">
          {/* Top Metric Cards */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div className="p-3 rounded-xl bg-slate-950/80 border border-slate-800 space-y-1">
              <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider flex items-center gap-1">
                <Clock className="w-3 h-3 text-indigo-400" /> Total Duration
              </span>
              <div className="text-lg font-extrabold font-mono text-slate-100">
                {totalMs.toFixed(0)} <span className="text-xs font-normal text-slate-400">ms</span>
              </div>
            </div>

            <div className="p-3 rounded-xl bg-slate-950/80 border border-slate-800 space-y-1">
              <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider flex items-center gap-1">
                <DollarSign className="w-3 h-3 text-emerald-400" /> Total Cost
              </span>
              <div className="text-lg font-extrabold font-mono text-emerald-400">
                ${(meta.total_cost ?? 0).toFixed(5)}
              </div>
            </div>

            <div className="p-3 rounded-xl bg-slate-950/80 border border-slate-800 space-y-1">
              <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider flex items-center gap-1">
                <Zap className="w-3 h-3 text-purple-400" /> LLM Calls
              </span>
              <div className="text-lg font-extrabold font-mono text-slate-100 flex items-center gap-1.5">
                {meta.llm_calls}
                {meta.cache_hits > 0 && (
                  <span className="text-xs font-normal text-cyan-400">({meta.cache_hits} cached)</span>
                )}
              </div>
            </div>

            <div className="p-3 rounded-xl bg-slate-950/80 border border-slate-800 space-y-1">
              <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider flex items-center gap-1">
                <Sparkles className="w-3 h-3 text-cyan-400" /> Total Tokens
              </span>
              <div className="text-sm font-extrabold font-mono text-slate-200">
                {(meta.prompt_tokens ?? 0) + (meta.completion_tokens ?? 0)} <span className="text-[10px] font-normal text-slate-400">tok</span>
              </div>
            </div>
          </div>

          {/* Waterfall Timeline */}
          <div className="space-y-2">
            <div className="flex items-center justify-between text-xs">
              <span className="font-bold text-slate-300 flex items-center gap-1.5">
                <Layers className="w-3.5 h-3.5 text-indigo-400" />
                Pipeline Execution Waterfall
              </span>
              <span className="text-[11px] text-indigo-400 font-medium">💡 Click any span row for in-depth metrics</span>
            </div>

            <div className="space-y-1.5 bg-slate-950/80 p-3 rounded-xl border border-slate-800">
              {spans.map((span, i) => {
                const nested = span.name === "llm.call";
                const left = Math.min((span.start_ms / totalMs) * 100, 98);
                const width = Math.max((span.duration_ms / totalMs) * 100, 1.5);
                const isSelected = selectedSpanIndex === i;
                const cat = getSpanCategory(span);
                const Icon = cat.icon;
                const fieldKey = typeof span.attrs.field === "string" ? span.attrs.field : null;
                const fieldMeta = fieldKey ? FIELD_LABELS[fieldKey] : null;

                return (
                  <button
                    key={`${span.name}-${i}`}
                    type="button"
                    onClick={() => setSelectedSpanIndex(isSelected ? null : i)}
                    className={`w-full text-left p-2.5 rounded-lg transition-all border flex flex-col sm:flex-row sm:items-center justify-between gap-2 group ${
                      isSelected
                        ? "bg-slate-800/90 border-indigo-500 shadow-md shadow-indigo-500/10"
                        : "bg-slate-900/50 hover:bg-slate-800/70 border-slate-800 hover:border-slate-700"
                    }`}
                  >
                    <div className={`flex items-center gap-2 min-w-[210px] ${nested ? "pl-3" : ""}`}>
                      <div className={`p-1 rounded ${cat.text} bg-slate-950 border border-slate-800`}>
                        <Icon className="w-3.5 h-3.5" />
                      </div>
                      <div className="truncate">
                        <span className={`text-xs font-semibold ${isSelected ? "text-cyan-300 font-bold" : "text-slate-200 group-hover:text-white"}`}>
                          {getSpanTitle(span)}
                        </span>
                        {fieldMeta && (
                          <span className={`ml-1.5 px-1.5 py-0.2 rounded text-[10px] font-mono border ${fieldMeta.bg} ${fieldMeta.color}`}>
                            {fieldMeta.name}
                          </span>
                        )}
                      </div>
                    </div>

                    <div className="flex-1 w-full sm:w-auto space-y-1">
                      <div className="relative h-2.5 rounded-full bg-slate-950 overflow-hidden border border-slate-800">
                        <div
                          className={`absolute h-full rounded-full transition-all duration-300 ${cat.color}`}
                          style={{ left: `${left}%`, width: `${width}%` }}
                        />
                      </div>
                      <div className="flex items-center justify-between text-[10px] font-mono text-slate-400">
                        <span className="font-bold text-slate-300">{span.duration_ms.toFixed(1)} ms</span>
                        <div className="flex items-center gap-2">
                          {span.served_model && (
                            <span className="text-purple-300">{span.served_model.split("/").pop()}</span>
                          )}
                          {span.cost_usd > 0 && (
                            <span className="text-emerald-400">${span.cost_usd.toFixed(5)}</span>
                          )}
                          {span.tokens > 0 && <span>{span.tokens} tok</span>}
                        </div>
                      </div>
                    </div>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Span Details Inspector Card */}
          {selectedSpan && (
            <div className="p-4 rounded-xl bg-slate-900 border border-indigo-500/40 space-y-3 relative animate-in fade-in duration-200">
              <div className="flex items-center justify-between border-b border-slate-800 pb-2.5">
                <div className="flex items-center gap-2">
                  <div className="p-1.5 rounded-lg bg-indigo-500/20 text-indigo-300">
                    <Info className="w-4 h-4" />
                  </div>
                  <div>
                    <h4 className="text-xs font-bold text-slate-100">
                      Span Inspector: {getSpanTitle(selectedSpan)}
                    </h4>
                    <p className="text-[11px] text-slate-400 font-mono">
                      Start: +{selectedSpan.start_ms.toFixed(1)} ms · Duration: {selectedSpan.duration_ms.toFixed(1)} ms
                    </p>
                  </div>
                </div>

                <button
                  type="button"
                  onClick={() => setSelectedSpanIndex(null)}
                  className="p-1 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-slate-800"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>

              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 text-xs">
                <div className="p-2.5 rounded-lg bg-slate-950 border border-slate-800">
                  <span className="text-[10px] text-slate-400 block font-medium">Model Served</span>
                  <span className="font-mono font-bold text-purple-300 truncate block">
                    {selectedSpan.served_model || "N/A (Local Step)"}
                  </span>
                </div>

                <div className="p-2.5 rounded-lg bg-slate-950 border border-slate-800">
                  <span className="text-[10px] text-slate-400 block font-medium">Tokens Used</span>
                  <span className="font-mono font-bold text-cyan-300 block">
                    {selectedSpan.tokens || 0} tok
                  </span>
                  {selectedSpan.prompt_tokens > 0 && (
                    <span className="text-[10px] text-slate-500 block">
                      {selectedSpan.prompt_tokens} prompt / {selectedSpan.completion_tokens} completion
                    </span>
                  )}
                </div>

                <div className="p-2.5 rounded-lg bg-slate-950 border border-slate-800">
                  <span className="text-[10px] text-slate-400 block font-medium">Cost</span>
                  <span className="font-mono font-bold text-emerald-400 block">
                    ${selectedSpan.cost_usd > 0 ? selectedSpan.cost_usd.toFixed(6) : "0.000000"}
                  </span>
                </div>

                <div className="p-2.5 rounded-lg bg-slate-950 border border-slate-800">
                  <span className="text-[10px] text-slate-400 block font-medium">Cache Status</span>
                  <span className="font-mono font-bold text-slate-200 block">
                    {selectedSpan.cache_hit === true
                      ? "⚡ Cache Hit"
                      : selectedSpan.cache_hits > 0
                      ? `${selectedSpan.cache_hits} cached`
                      : "Cache Miss"}
                  </span>
                </div>
              </div>

              {Object.keys(selectedSpan.attrs).length > 0 && (
                <div className="pt-2 border-t border-slate-800/80">
                  <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block mb-1.5">
                    Span Metadata Attributes
                  </span>
                  <div className="flex flex-wrap gap-2 text-[11px] font-mono">
                    {Object.entries(selectedSpan.attrs).map(([key, val]) => (
                      <div key={key} className="px-2 py-1 rounded bg-slate-950 border border-slate-800 text-slate-300">
                        <span className="text-slate-500">{key}:</span> <strong className="text-cyan-300">{String(val)}</strong>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Modal Footer */}
        <div className="p-4 border-t border-slate-800 bg-slate-900/80 flex items-center justify-between text-xs text-slate-400">
          <span className="font-mono text-[11px]">
            Prompt: {meta.prompt_tokens ?? 0} tok · Completion: {meta.completion_tokens ?? 0} tok
          </span>
          <button
            type="button"
            onClick={onClose}
            className="px-5 py-2 rounded-xl text-xs font-bold text-white bg-indigo-600 hover:bg-indigo-500 transition-colors"
          >
            Close Trace Window
          </button>
        </div>
      </div>
    </div>
  );
};
