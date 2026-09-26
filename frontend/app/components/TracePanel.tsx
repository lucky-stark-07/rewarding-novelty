"use client";

import React, { useState } from "react";
import {
  Activity,
  AlertTriangle,
  ChevronDown,
  ChevronUp,
  Clock,
  DollarSign,
  Cpu,
  Layers,
  Sparkles,
  Zap,
  Info,
  X,
  Database,
  ArrowRight,
  CheckCircle2,
  HelpCircle,
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

export const DegradedBadge: React.FC<{ reason?: string | null }> = ({ reason }) => (
  <span
    className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-500/15 text-amber-300 border border-amber-500/40"
    title={reason ?? "Scored without the LLM judge"}
  >
    <AlertTriangle className="w-3 h-3" />
    Degraded Mode
  </span>
);

export const TracePanel: React.FC<{ meta: ScoreMeta }> = ({ meta }) => {
  const [open, setOpen] = useState(true);
  const [selectedSpanIndex, setSelectedSpanIndex] = useState<number | null>(null);

  const spans = meta.spans ?? [];
  const totalMs = Math.max(meta.total_latency_ms ?? 0, ...spans.map((s) => s.start_ms + s.duration_ms), 1);

  // Group latencies by category for visualization
  const llmDuration = spans.filter(s => s.name === "llm.call").reduce((acc, s) => acc + s.duration_ms, 0);
  const localDuration = spans.filter(s => s.name === "embed" || s.name === "search" || s.name === "dedupe" || s.name === "aggregate").reduce((acc, s) => acc + s.duration_ms, 0);

  const selectedSpan = selectedSpanIndex !== null ? spans[selectedSpanIndex] : null;

  return (
    <div className="w-full glass-card rounded-2xl border border-slate-800 p-5 shadow-2xl space-y-4">
      {/* Top Header Toggle */}
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between gap-3 text-slate-200 group focus:outline-none"
        aria-expanded={open}
      >
        <div className="flex items-center gap-2.5">
          <div className="p-2 rounded-xl bg-indigo-500/10 border border-indigo-500/20 text-indigo-400 group-hover:bg-indigo-500/20 transition-colors">
            <Activity className="w-4 h-4" />
          </div>
          <div className="text-left">
            <div className="flex items-center gap-2">
              <span className="font-bold text-sm text-slate-100">Execution Trace & Performance Metrics</span>
              {meta.degraded && <DegradedBadge reason={meta.degraded_reason} />}
            </div>
            <p className="text-[11px] text-slate-400 font-medium">
              Real-time pipeline telemetry, latency waterfall & cost analysis
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <div className="hidden sm:flex items-center gap-2 font-mono text-xs">
            <span className="px-2.5 py-1 rounded-lg bg-slate-900 border border-slate-800 text-slate-300 font-bold">
              {totalMs.toFixed(0)} ms
            </span>
            <span className="px-2.5 py-1 rounded-lg bg-slate-900 border border-slate-800 text-emerald-400 font-bold">
              ${(meta.total_cost ?? 0).toFixed(5)}
            </span>
          </div>

          <div className="p-1.5 rounded-lg bg-slate-900 border border-slate-800 text-slate-400 group-hover:text-slate-200">
            {open ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
          </div>
        </div>
      </button>

      {open && (
        <div className="pt-3 border-t border-slate-800/80 space-y-5">
          {/* Degraded Alert */}
          {meta.degraded && meta.degraded_reason && (
            <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-200 flex items-start gap-2">
              <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
              <div>
                <strong className="font-semibold block text-amber-100">LLM Provider Degraded</strong>
                <span>{meta.degraded_reason}. Affected stages fell back to local embedding similarity.</span>
              </div>
            </div>
          )}

          {/* Key Metric Highlights Cards */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div className="p-3 rounded-xl bg-slate-950/70 border border-slate-800 text-left space-y-1">
              <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider flex items-center gap-1">
                <Clock className="w-3 h-3 text-indigo-400" /> Total Latency
              </span>
              <div className="text-lg font-extrabold font-mono text-slate-100">
                {totalMs.toFixed(0)} <span className="text-xs font-normal text-slate-400">ms</span>
              </div>
            </div>

            <div className="p-3 rounded-xl bg-slate-950/70 border border-slate-800 text-left space-y-1">
              <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider flex items-center gap-1">
                <DollarSign className="w-3 h-3 text-emerald-400" /> Est. Total Cost
              </span>
              <div className="text-lg font-extrabold font-mono text-emerald-400">
                ${(meta.total_cost ?? 0).toFixed(5)}
              </div>
            </div>

            <div className="p-3 rounded-xl bg-slate-950/70 border border-slate-800 text-left space-y-1">
              <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider flex items-center gap-1">
                <Zap className="w-3 h-3 text-purple-400" /> LLM API Calls
              </span>
              <div className="text-lg font-extrabold font-mono text-slate-100 flex items-center gap-1.5">
                {meta.llm_calls}
                {meta.cache_hits > 0 && (
                  <span className="text-xs font-normal text-cyan-400">({meta.cache_hits} cached)</span>
                )}
              </div>
            </div>

            <div className="p-3 rounded-xl bg-slate-950/70 border border-slate-800 text-left space-y-1">
              <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider flex items-center gap-1">
                <Sparkles className="w-3 h-3 text-cyan-400" /> Token Volume
              </span>
              <div className="text-sm font-extrabold font-mono text-slate-200">
                {(meta.prompt_tokens ?? 0) + (meta.completion_tokens ?? 0)} <span className="text-[10px] font-normal text-slate-400">tok</span>
              </div>
            </div>
          </div>

          {/* Interactive Timeline & Waterfall Chart */}
          <div className="space-y-2">
            <div className="flex items-center justify-between text-xs">
              <span className="font-bold text-slate-300 flex items-center gap-1.5">
                <Layers className="w-3.5 h-3.5 text-indigo-400" />
                Pipeline Waterfall Timeline
              </span>
              <span className="text-[11px] text-indigo-400 font-medium">💡 Click any span row to inspect detailed metrics</span>
            </div>

            {spans.length === 0 ? (
              <p className="text-xs text-slate-500 italic p-4 text-center">No trace spans recorded.</p>
            ) : (
              <div className="space-y-1.5 bg-slate-950/60 p-3 rounded-xl border border-slate-800/80">
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
                      className={`w-full text-left p-2 rounded-lg transition-all border flex flex-col sm:flex-row sm:items-center justify-between gap-2 group ${
                        isSelected
                          ? "bg-slate-800/90 border-indigo-500 shadow-md shadow-indigo-500/10"
                          : "bg-slate-900/40 hover:bg-slate-800/60 border-slate-800/60 hover:border-slate-700"
                      }`}
                    >
                      {/* Left: Label & Badges */}
                      <div className={`flex items-center gap-2 min-w-[200px] ${nested ? "pl-3" : ""}`}>
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

                      {/* Right: Duration Bar & Chips */}
                      <div className="flex-1 w-full sm:w-auto space-y-1">
                        <div className="relative h-2.5 rounded-full bg-slate-950 overflow-hidden border border-slate-800">
                          <div
                            className={`absolute h-full rounded-full transition-all duration-300 ${cat.color} ${isSelected ? "ring-2 ring-indigo-400" : ""}`}
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
            )}
          </div>

          {/* Clicked Span Inspector Card / Modal Details */}
          {selectedSpan && (
            <div className="p-4 rounded-xl bg-slate-900 border border-indigo-500/40 space-y-3 relative animate-in fade-in duration-200">
              <div className="flex items-center justify-between border-b border-slate-800 pb-2.5">
                <div className="flex items-center gap-2">
                  <div className="p-1.5 rounded-lg bg-indigo-500/20 text-indigo-300">
                    <Info className="w-4 h-4" />
                  </div>
                  <div>
                    <h4 className="text-xs font-bold text-slate-100 flex items-center gap-2">
                      <span>Span Details: {getSpanTitle(selectedSpan)}</span>
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

              {/* Span Detailed Grid */}
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

              {/* Attributes JSON / breakdown */}
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

          {/* Footer Metadata Line */}
          <div className="pt-2 border-t border-slate-800/80 flex items-center justify-between text-[11px] font-mono text-slate-500 flex-wrap gap-2">
            <span>
              Trace ID: <span className="text-slate-400">{meta.trace_id}</span>
            </span>
            <span>
              Prompt: <strong className="text-slate-300">{meta.prompt_tokens ?? 0}</strong> tok · Completion:{" "}
              <strong className="text-slate-300">{meta.completion_tokens ?? 0}</strong> tok
            </span>
          </div>
        </div>
      )}
    </div>
  );
};
