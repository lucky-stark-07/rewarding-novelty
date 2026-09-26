"use client";

import React from "react";
import { Cpu, ArrowRight, Layers, Database, ShieldCheck, Sparkles, Filter, CheckCircle2 } from "lucide-react";

export const ArchitectureVisualizer: React.FC = () => {
  const steps = [
    {
      num: "01",
      title: "G2 Review Input",
      subtitle: "3 Discrete Properties",
      description: "User submits what_you_like, what_you_dislike, and problem_solved.",
      icon: Layers,
      color: "from-cyan-500 to-blue-500",
      badge: "FastAPI / Next.js",
    },
    {
      num: "02",
      title: "Claim Extraction",
      subtitle: "OpenRouter Fast LLM",
      description: "Extracts atomic, self-contained product claims for each field.",
      icon: Sparkles,
      color: "from-blue-500 to-indigo-500",
      badge: "google/gemini-2.0-flash",
    },
    {
      num: "03",
      title: "Local CPU Embedding",
      subtitle: "Sentence Transformers",
      description: "Embeds extracted claims into vector representations locally.",
      icon: Cpu,
      color: "from-indigo-500 to-purple-500",
      badge: "Local Vector Model",
    },
    {
      num: "04",
      title: "Similarity & Entailment",
      subtitle: "Thresholds + LLM Judge",
      description: "Cosine sim: ≥0.82 covered, ≤0.48 novel. Middle band checked by OpenRouter judge.",
      icon: Filter,
      color: "from-purple-500 to-pink-500",
      badge: "High 0.82 / Low 0.48",
    },
    {
      num: "05",
      title: "Field & Overall Score",
      subtitle: "Novelty × Relevance",
      description: "Aggregates novelty fraction with relevance gate across all 3 fields.",
      icon: ShieldCheck,
      color: "from-pink-500 to-emerald-400",
      badge: "Final 0.0 – 1.0 Score",
    },
  ];

  return (
    <div className="w-full space-y-6">
      {/* Header card */}
      <div className="glass-card rounded-2xl p-6 border border-slate-800 shadow-xl">
        <div className="flex items-center gap-3">
          <div className="p-3 rounded-xl bg-purple-500/10 border border-purple-500/20 text-purple-400">
            <Cpu className="w-6 h-6" />
          </div>
          <div>
            <h2 className="text-lg font-bold text-slate-100">Scoring Pipeline & System Architecture</h2>
            <p className="text-xs text-slate-400 mt-0.5">
              Hybrid pipeline combining local vector embeddings with cloud LLM judges for accurate, cost-effective novelty evaluation.
            </p>
          </div>
        </div>
      </div>

      {/* Visual Pipeline Flow Cards */}
      <div className="grid grid-cols-1 md:grid-cols-5 gap-3 relative">
        {steps.map((step, idx) => {
          const Icon = step.icon;
          return (
            <div
              key={step.num}
              className="glass-card rounded-xl p-4 border border-slate-800 hover:border-indigo-500/40 transition-all flex flex-col justify-between space-y-3 relative group"
            >
              <div>
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-mono font-bold text-indigo-400">{step.num}</span>
                  <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-900 text-slate-400 border border-slate-800">
                    {step.badge}
                  </span>
                </div>

                <div className="flex items-center gap-2 mb-1">
                  <div className={`p-1.5 rounded-lg bg-gradient-to-r ${step.color} text-white`}>
                    <Icon className="w-4 h-4" />
                  </div>
                  <h3 className="text-sm font-bold text-slate-100">{step.title}</h3>
                </div>

                <p className="text-[11px] font-semibold text-slate-400 mb-2">{step.subtitle}</p>
                <p className="text-[11px] text-slate-300 leading-relaxed">{step.description}</p>
              </div>

              {idx < steps.length - 1 && (
                <div className="hidden md:block absolute -right-3 top-1/2 -translate-y-1/2 z-10 p-1 rounded-full bg-slate-900 border border-slate-700 text-slate-400">
                  <ArrowRight className="w-3 h-3" />
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Threshold Matrix explanation */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="p-4 rounded-xl glass-card border border-rose-500/20">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-bold text-rose-400 uppercase tracking-wide">High Similarity Band</span>
            <span className="font-mono text-xs font-bold text-rose-400">Cosine Sim ≥ 0.82</span>
          </div>
          <p className="text-xs text-slate-300">
            Automatically classified as <strong className="text-rose-300">Covered (Novelty 0.0)</strong>. The claim is semantically identical or near-paraphrased to an existing claim in the 50-review corpus.
          </p>
        </div>

        <div className="p-4 rounded-xl glass-card border border-purple-500/20">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-bold text-purple-400 uppercase tracking-wide">Ambiguous Middle Band</span>
            <span className="font-mono text-xs font-bold text-purple-400">0.48 &lt; Sim &lt; 0.82</span>
          </div>
          <p className="text-xs text-slate-300">
            Passed to <strong className="text-purple-300">OpenRouter LLM Entailment Judge</strong>. Evaluates whether the existing claim semantically entails the candidate claim.
          </p>
        </div>

        <div className="p-4 rounded-xl glass-card border border-emerald-500/20">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-bold text-emerald-400 uppercase tracking-wide">Low Similarity Band</span>
            <span className="font-mono text-xs font-bold text-emerald-400">Cosine Sim ≤ 0.48</span>
          </div>
          <p className="text-xs text-slate-300">
            Automatically classified as <strong className="text-emerald-300">Novel (Novelty 1.0)</strong>. The claim introduces distinct product feedback not present in the baseline corpus.
          </p>
        </div>
      </div>
    </div>
  );
};
