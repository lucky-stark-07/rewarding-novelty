"use client";

import React, { useState } from "react";
import { Activity, ChevronDown, ChevronUp } from "lucide-react";
import { ScoreResult, TraceSpan } from "../types";

const LABELS: Record<string, string> = {
  "corpus.duplicate_check": "Duplicate check",
  "llm.extract_claims": "Claim extraction",
  "embed.claims": "Embed claims",
  "retrieval.knn": "Top-k retrieval",
  "judge.batch": "Batched judging",
  "llm.judge_relevance": "Relevance judge",
  "llm.judge_coverage": "Coverage judge",
  "llm.request": "Upstream call",
  "corpus.append": "Corpus append",
};

function barColor(name: string): string {
  if (name === "llm.request") return "bg-fuchsia-400";
  if (name.startsWith("llm.")) return "bg-purple-400";
  if (name === "judge.batch") return "bg-indigo-400";
  if (name.startsWith("embed") || name.startsWith("retrieval")) return "bg-cyan-400";
  return "bg-slate-400";
}

function depthOf(span: TraceSpan, spans: TraceSpan[]): number {
  const end = span.start_ms + span.duration_ms;
  return spans.filter(
    (other) => other !== span && other.start_ms <= span.start_ms && other.start_ms + other.duration_ms >= end && other.duration_ms > span.duration_ms,
  ).length;
}

function chips(attrs: TraceSpan["attrs"]): string[] {
  const out: string[] = [];
  if (typeof attrs.model === "string") out.push(attrs.model.split("/").pop() || attrs.model);
  if (attrs.cached === true) out.push("cache hit");
  if (attrs.repaired === true) out.push("repaired");
  if (typeof attrs.prompt_tokens === "number") out.push(`${attrs.prompt_tokens}→${attrs.completion_tokens ?? 0} tok`);
  if (typeof attrs.queue_ms === "number" && attrs.queue_ms >= 1) out.push(`queued ${attrs.queue_ms.toFixed(0)}ms`);
  if (typeof attrs.attempt === "number" && attrs.attempt > 1) out.push(`attempt ${attrs.attempt}`);
  if (typeof attrs.ambiguous === "number") out.push(`${attrs.ambiguous} ambiguous`);
  if (typeof attrs.claims === "number" && attrs.ambiguous === undefined) out.push(`${attrs.claims} claims`);
  if (typeof attrs.k === "number") out.push(`k=${attrs.k}`);
  if (typeof attrs.error === "string") out.push(`error: ${attrs.error}`);
  return out;
}

export const TracePanel: React.FC<{ meta: NonNullable<ScoreResult["meta"]> }> = ({ meta }) => {
  const [open, setOpen] = useState(false);
  const spans = meta.trace ?? [];
  const totalMs = Math.max((meta.stage_latency_seconds?.total ?? 0) * 1000, ...spans.map((s) => s.start_ms + s.duration_ms), 1);

  return (
    <div className="glass-card rounded-2xl border border-slate-800 p-4 text-xs">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between gap-2 text-slate-300"
        aria-expanded={open}
      >
        <span className="flex items-center gap-2 font-semibold">
          <Activity className="w-4 h-4 text-indigo-400" />
          Request trace
        </span>
        <span className="flex items-center gap-3 font-mono text-[11px] text-slate-400">
          <span>{totalMs.toFixed(0)} ms</span>
          <span>{meta.llm_calls ?? 0} calls · {meta.llm_cache_hits ?? 0} cached</span>
          <span>${(meta.estimated_cost_usd ?? 0).toFixed(5)}</span>
          {open ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
        </span>
      </button>

      {open && (
        <div className="mt-3 space-y-1.5">
          {spans.length === 0 && <p className="text-slate-500">No spans recorded for this request.</p>}
          {spans.map((span, i) => {
            const depth = depthOf(span, spans);
            const left = (span.start_ms / totalMs) * 100;
            const width = Math.max((span.duration_ms / totalMs) * 100, 0.5);
            return (
              <div key={`${span.name}-${i}`} className="grid grid-cols-[minmax(0,9rem)_1fr] gap-2 items-center">
                <div className="truncate text-slate-300" style={{ paddingLeft: `${depth * 0.6}rem` }} title={span.name}>
                  {LABELS[span.name] ?? span.name}
                </div>
                <div>
                  <div className="relative h-2 rounded bg-slate-800/80">
                    <div className={`absolute h-2 rounded ${barColor(span.name)}`} style={{ left: `${left}%`, width: `${width}%` }} />
                  </div>
                  <div className="mt-0.5 flex flex-wrap gap-x-2 text-[10px] text-slate-500 font-mono">
                    <span>{span.duration_ms.toFixed(1)} ms</span>
                    {chips(span.attrs).map((chip) => (
                      <span key={chip}>{chip}</span>
                    ))}
                  </div>
                </div>
              </div>
            );
          })}
          <p className="pt-2 text-[10px] text-slate-500 font-mono">
            request {meta.request_id} · {meta.prompt_tokens ?? 0} prompt / {meta.completion_tokens ?? 0} completion tokens
          </p>
        </div>
      )}
    </div>
  );
};
