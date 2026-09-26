"use client";

import React, { useState } from "react";
import { Activity, AlertTriangle, ChevronDown, ChevronUp } from "lucide-react";
import { ScoreMeta, TraceSpan } from "../types";

const LABELS: Record<string, string> = {
  dedupe: "Duplicate check",
  extract: "Extract claims",
  embed: "Embed (1 batch)",
  search: "Top-k search",
  relevance: "Relevance judge",
  entail: "Coverage judge",
  aggregate: "Aggregate",
  corpus_append: "Corpus append",
  "llm.call": "Upstream call",
};

const FIELD_SHORT: Record<string, string> = { what_you_like: "like", what_you_dislike: "dislike", problem_solved: "solved" };

function barColor(span: TraceSpan): string {
  if (span.attrs.degraded) return "bg-amber-400";
  if (span.name === "llm.call") return "bg-fuchsia-400";
  if (span.name === "extract") return "bg-sky-400";
  if (span.name === "relevance" || span.name === "entail") return "bg-purple-400";
  if (span.name === "embed" || span.name === "search") return "bg-cyan-400";
  return "bg-slate-400";
}

function label(span: TraceSpan): string {
  const base = LABELS[span.name] ?? span.name;
  const field = typeof span.attrs.field === "string" ? FIELD_SHORT[span.attrs.field] ?? span.attrs.field : null;
  return field ? `${base} · ${field}` : base;
}

function chips(span: TraceSpan): string[] {
  const out: string[] = [];
  if (span.served_model) out.push(span.served_model.split("/").pop() || span.served_model);
  if (span.cache_hit === true) out.push("cache hit");
  if (span.cache_hit === false && span.cache_hits > 0) out.push(`${span.cache_hits} cached`);
  if (span.tokens > 0) out.push(`${span.tokens} tok`);
  if (span.cached_tokens > 0) out.push(`${span.cached_tokens} prompt-cached`);
  if (span.cost_usd > 0) out.push(`$${span.cost_usd.toFixed(5)}`);
  const { attempt, queue_ms, claims, ambiguous, error, degraded_reason } = span.attrs;
  if (typeof attempt === "number" && attempt > 1) out.push(`retry ${attempt - 1}`);
  if (typeof queue_ms === "number" && queue_ms >= 1) out.push(`queued ${queue_ms.toFixed(0)}ms`);
  if (typeof ambiguous === "number") out.push(`${ambiguous} ambiguous`);
  else if (typeof claims === "number") out.push(`${claims} claims`);
  if (typeof degraded_reason === "string") out.push(`degraded: ${degraded_reason}`);
  if (typeof error === "string") out.push(`error: ${error}`);
  return out;
}

export const DegradedBadge: React.FC<{ reason?: string | null }> = ({ reason }) => (
  <span
    className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-500/15 text-amber-300 border border-amber-500/40"
    title={reason ?? "Scored without the LLM judge"}
  >
    <AlertTriangle className="w-3 h-3" />
    Degraded
  </span>
);

export const TracePanel: React.FC<{ meta: ScoreMeta }> = ({ meta }) => {
  const [open, setOpen] = useState(false);
  const spans = meta.spans ?? [];
  const totalMs = Math.max(meta.total_latency_ms ?? 0, ...spans.map((s) => s.start_ms + s.duration_ms), 1);

  return (
    <div className="glass-card rounded-2xl border border-slate-800 p-4 text-xs">
      <button type="button" onClick={() => setOpen(!open)} className="w-full flex items-center justify-between gap-2 text-slate-300" aria-expanded={open}>
        <span className="flex items-center gap-2 font-semibold">
          <Activity className="w-4 h-4 text-indigo-400" />
          Trace
          {meta.degraded && <DegradedBadge reason={meta.degraded_reason} />}
        </span>
        <span className="flex items-center gap-3 font-mono text-[11px] text-slate-400">
          <span title="Total latency">{totalMs.toFixed(0)} ms</span>
          <span title="Total cost">${(meta.total_cost ?? 0).toFixed(5)}</span>
          <span title="Upstream LLM calls · cache hits">
            {meta.llm_calls} calls · {meta.cache_hits} cached
          </span>
          {open ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
        </span>
      </button>

      {open && (
        <div className="mt-3 space-y-1.5">
          {meta.degraded && meta.degraded_reason && (
            <p className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-2 text-[11px] text-amber-200">
              LLM unavailable ({meta.degraded_reason}). Affected stages used embedding-only scoring; the score is provisional.
            </p>
          )}
          {spans.length === 0 && <p className="text-slate-500">No spans recorded for this request.</p>}
          {spans.map((span, i) => {
            const nested = span.name === "llm.call";
            const left = (span.start_ms / totalMs) * 100;
            const width = Math.max((span.duration_ms / totalMs) * 100, 0.5);
            return (
              <div key={`${span.name}-${i}`} className="grid grid-cols-[minmax(0,9.5rem)_1fr] gap-2 items-center">
                <div className={`truncate ${nested ? "pl-3 text-slate-500" : "text-slate-300"}`} title={span.name}>
                  {label(span)}
                </div>
                <div>
                  <div className="relative h-2 rounded bg-slate-800/80">
                    <div className={`absolute h-2 rounded ${barColor(span)}`} style={{ left: `${left}%`, width: `${width}%` }} />
                  </div>
                  <div className="mt-0.5 flex flex-wrap gap-x-2 text-[10px] text-slate-500 font-mono">
                    <span className="text-slate-400">{span.duration_ms.toFixed(1)} ms</span>
                    {chips(span).map((chip) => (
                      <span key={chip}>{chip}</span>
                    ))}
                  </div>
                </div>
              </div>
            );
          })}
          <p className="pt-2 text-[10px] text-slate-500 font-mono break-all">
            trace {meta.trace_id} · {meta.prompt_tokens ?? 0} prompt / {meta.completion_tokens ?? 0} completion tokens
            {meta.cached_tokens ? ` · ${meta.cached_tokens} prompt-cached` : ""}
          </p>
        </div>
      )}
    </div>
  );
};
