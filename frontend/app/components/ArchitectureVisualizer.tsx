"use client";

import React, { useEffect, useState } from "react";
import {
  Activity,
  ArrowDown,
  ArrowRight,
  Bot,
  Cpu,
  Database,
  FileText,
  Gauge,
  Layers,
  RefreshCw,
  Search,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  Timer,
  Wallet,
} from "lucide-react";
import { ServiceStats } from "../types";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type Kind = "harness" | "llm" | "tool";

interface Step {
  num: string;
  title: string;
  detail: string;
  kind: Kind;
  icon: React.ElementType;
  parallel?: string;
}

const KIND_STYLE: Record<Kind, { card: string; tag: string; label: string }> = {
  harness: { card: "border-slate-700 bg-slate-900/70", tag: "bg-slate-800 text-slate-300 border-slate-700", label: "Harness" },
  llm: { card: "border-fuchsia-500/50 bg-fuchsia-500/10 shadow-lg shadow-fuchsia-500/10", tag: "bg-fuchsia-500/15 text-fuchsia-200 border-fuchsia-500/40", label: "Agent · LLM" },
  tool: { card: "border-cyan-500/40 bg-cyan-500/10", tag: "bg-cyan-500/15 text-cyan-200 border-cyan-500/40", label: "Agent · local tool" },
};

const shortModel = (model?: string) => (model ? model.split("/").pop() : "…");

function StepCard({ step }: { step: Step }) {
  const style = KIND_STYLE[step.kind];
  const Icon = step.icon;
  return (
    <div className={`rounded-xl border p-3 ${style.card}`}>
      <div className="flex items-center justify-between gap-2 mb-1.5">
        <span className="text-[10px] font-mono font-bold text-slate-400">{step.num}</span>
        <span className={`text-[9px] font-semibold uppercase tracking-wide px-1.5 py-0.5 rounded border ${style.tag}`}>{style.label}</span>
      </div>
      <div className="flex items-center gap-2">
        <Icon className="w-4 h-4 shrink-0 text-slate-200" />
        <h4 className="text-[13px] font-bold text-slate-100 leading-tight">{step.title}</h4>
      </div>
      <p className="mt-1 text-[11px] leading-relaxed text-slate-300">{step.detail}</p>
      {step.parallel && <p className="mt-1 text-[10px] font-mono text-slate-400">{step.parallel}</p>}
    </div>
  );
}

function Flow({ steps }: { steps: Step[] }) {
  return (
    <div className="flex flex-col lg:flex-row lg:items-stretch gap-2">
      {steps.map((step, i) => (
        <React.Fragment key={step.num}>
          <div className="flex-1 min-w-0">
            <StepCard step={step} />
          </div>
          {i < steps.length - 1 && (
            <div className="flex items-center justify-center text-slate-500" aria-hidden>
              <ArrowDown className="w-4 h-4 lg:hidden" />
              <ArrowRight className="w-4 h-4 hidden lg:block" />
            </div>
          )}
        </React.Fragment>
      ))}
    </div>
  );
}

export const ArchitectureVisualizer: React.FC = () => {
  const [stats, setStats] = useState<ServiceStats | null>(null);
  const [offline, setOffline] = useState(false);

  const load = async () => {
    try {
      const res = await fetch(`${API}/stats`, { cache: "no-store" });
      if (!res.ok) throw new Error(String(res.status));
      setStats(await res.json());
      setOffline(false);
    } catch {
      setOffline(true);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const cfg = stats?.config;
  const breaker = stats?.llm?.circuit_breaker?.state ?? "unknown";
  const low = cfg?.low_threshold ?? 0.35;
  const high = cfg?.high_threshold ?? 0.75;
  const k = cfg?.entailment_top_k ?? 3;

  const agentSteps: Step[] = [
    { num: "03", title: "Claim extractor", detail: `Splits each review field into ≤3 atomic claims. Model: ${shortModel(cfg?.fast_model)}.`, kind: "llm", icon: Sparkles, parallel: "3 fields in parallel · 1 call each" },
    { num: "04", title: "Embed", detail: "All claims in one encode call (MiniLM, CPU, thread pool). Cached by text hash.", kind: "tool", icon: Cpu },
    { num: "05", title: "Vector search", detail: `Top-${k} same-field neighbours: one matmul against the normalized corpus matrix built at startup.`, kind: "tool", icon: Search },
    { num: "06", title: "Judges", detail: `Relevance (graded rubric) and coverage (full / partial / none for sims in ${low}–${high}). Model: ${shortModel(cfg?.judge_model)}.`, kind: "llm", icon: Bot, parallel: "1 batched call per field per judge · all concurrent" },
  ];

  const harness = [
    { icon: Gauge, title: "Admission control", detail: `>${cfg?.max_inflight_requests ?? 32} in-flight → 503 + Retry-After` },
    { icon: Timer, title: "Concurrency limit", detail: "Global semaphore of 8 around every upstream call" },
    { icon: RefreshCw, title: "Retries + fallbacks", detail: "tenacity: 3 attempts, exp. backoff + jitter, honours Retry-After; OpenRouter model fallbacks" },
    { icon: ShieldCheck, title: "Output validation", detail: "Pydantic schema + batch-id checks; one repair re-ask with the error" },
    { icon: Database, title: "Caches", detail: "In-memory LRU → disk (model, prompt version, temperature, schema, prompt); in-flight de-dup" },
    { icon: ShieldAlert, title: "Circuit breaker + budget", detail: `3 consecutive failures or budget cap → degraded mode. Now: ${breaker}` },
    { icon: Wallet, title: "Cost accounting", detail: "Reported cost, tokens and cached tokens per call; served model logged" },
    { icon: Activity, title: "Tracing", detail: "contextvars spans → response meta, logs/traces.jsonl, GET /stats" },
  ];

  return (
    <div className="w-full space-y-6">
      <div className="glass-card rounded-2xl p-6 border border-slate-800 shadow-xl flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="p-3 rounded-xl bg-fuchsia-500/10 border border-fuchsia-500/30 text-fuchsia-300">
            <Bot className="w-6 h-6" />
          </div>
          <div>
            <h2 className="text-lg font-bold text-slate-100">Novelty Scoring Agent and its Harness</h2>
            <p className="text-xs text-slate-400 mt-0.5">
              The agent (pink: LLM roles, cyan: local tools) runs inside a production harness (grey) that bounds its latency, cost and failure modes.
            </p>
          </div>
        </div>
        <div className="text-[11px] font-mono text-slate-400 space-y-0.5 sm:text-right">
          {offline ? (
            <span className="text-amber-300">API offline: showing defaults</span>
          ) : stats ? (
            <>
              <div>
                {stats.request_count} requests · p50 {stats.latency_ms.p50?.toFixed(0) ?? "–"} ms · p95 {stats.latency_ms.p95?.toFixed(0) ?? "–"} ms
              </div>
              <div>
                ${stats.total_cost_usd.toFixed(4)} spent · cache hit {stats.cache_hit_rate === null ? "–" : `${Math.round(stats.cache_hit_rate * 100)}%`} · degraded {stats.degraded_count}
              </div>
            </>
          ) : (
            <span>loading live config…</span>
          )}
        </div>
      </div>

      {/* Harness boundary wrapping the workflow */}
      <section className="rounded-2xl border-2 border-dashed border-slate-600 p-4 sm:p-5 space-y-4" aria-label="Harness">
        <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wide text-slate-300">
          <ShieldCheck className="w-4 h-4" /> Harness
        </div>

        <Flow
          steps={[
            { num: "01", title: "POST /score", detail: "Validated input (3 fields, ≤4000 chars). A trace_id starts here.", kind: "harness", icon: Layers },
            { num: "02", title: "Admit + dedupe", detail: "Overload shedding, then an exact-duplicate check against the corpus (no LLM call).", kind: "harness", icon: Gauge },
          ]}
        />

        <div className="flex justify-center text-slate-500" aria-hidden>
          <ArrowDown className="w-4 h-4" />
        </div>

        {/* The agent */}
        <section className="rounded-2xl border-2 border-fuchsia-500/60 bg-fuchsia-500/[0.04] p-4 space-y-3 shadow-xl shadow-fuchsia-500/10" aria-label="Agent">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wide text-fuchsia-200">
              <Bot className="w-4 h-4" /> Agent: novelty and relevance scorer
            </div>
            <div className="flex flex-wrap gap-1.5 text-[10px] font-mono">
              <span className="px-1.5 py-0.5 rounded border border-fuchsia-500/40 text-fuchsia-200">fast: {cfg?.fast_model ?? "…"}</span>
              <span className="px-1.5 py-0.5 rounded border border-fuchsia-500/40 text-fuchsia-200">judge: {cfg?.judge_model ?? "…"}</span>
              <span className="px-1.5 py-0.5 rounded border border-slate-600 text-slate-300 inline-flex items-center gap-1">
                <FileText className="w-3 h-3" /> prompts/*.md
              </span>
            </div>
          </div>
          <Flow steps={agentSteps} />
          {cfg?.prompt_versions && <p className="text-[10px] font-mono text-slate-500">Prompt versions: {cfg.prompt_versions.join(" · ")}</p>}
        </section>

        <div className="flex justify-center text-slate-500" aria-hidden>
          <ArrowDown className="w-4 h-4" />
        </div>

        <Flow
          steps={[
            { num: "07", title: "Aggregate", detail: "Per claim: novelty × relevance. Field = mean of claims; submission = mean of populated fields.", kind: "harness", icon: Gauge },
            { num: "08", title: "Response + trace", detail: "ScoreResult with meta: trace_id, latency, cost, LLM calls, cache hits, degraded, spans.", kind: "harness", icon: Activity },
          ]}
        />

        <div className="rounded-xl border border-amber-500/40 bg-amber-500/10 p-3 text-[11px] text-amber-100 flex gap-2">
          <ShieldAlert className="w-4 h-4 shrink-0 text-amber-300" />
          <span>
            <strong>Degraded path.</strong> When the breaker is open, the budget is spent, or an LLM stage fails after retries, that stage falls back to embeddings only. Extraction splits sentences, the ambiguous band gets partial credit, and relevance is the similarity to the reference text. The response is marked <code>degraded=true</code> with a reason and is never added to the corpus.
          </span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2">
          {harness.map(({ icon: Icon, title, detail }) => (
            <div key={title} className="rounded-lg border border-slate-700 bg-slate-900/60 p-2.5">
              <div className="flex items-center gap-1.5 text-[12px] font-semibold text-slate-200">
                <Icon className="w-3.5 h-3.5 text-slate-400" /> {title}
              </div>
              <p className="mt-0.5 text-[10.5px] leading-snug text-slate-400">{detail}</p>
            </div>
          ))}
        </div>
      </section>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="p-4 rounded-xl glass-card border border-rose-500/20">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-bold text-rose-400 uppercase tracking-wide">Covered</span>
            <span className="font-mono text-xs font-bold text-rose-400">sim ≥ {high}</span>
          </div>
          <p className="text-xs text-slate-300">Nearest same-field corpus claim is a near-paraphrase: novelty 0, no judge call.</p>
        </div>
        <div className="p-4 rounded-xl glass-card border border-purple-500/20">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-bold text-purple-400 uppercase tracking-wide">Ambiguous</span>
            <span className="font-mono text-xs font-bold text-purple-400">
              {low} &lt; sim &lt; {high}
            </span>
          </div>
          <p className="text-xs text-slate-300">The coverage judge compares the claim with its top-{k} neighbours: full = 0, partial = 0.5, none = 1.</p>
        </div>
        <div className="p-4 rounded-xl glass-card border border-emerald-500/20">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-bold text-emerald-400 uppercase tracking-wide">Novel</span>
            <span className="font-mono text-xs font-bold text-emerald-400">sim ≤ {low}</span>
          </div>
          <p className="text-xs text-slate-300">Nothing close in the corpus: novelty 1, still gated by relevance.</p>
        </div>
      </div>
    </div>
  );
};
