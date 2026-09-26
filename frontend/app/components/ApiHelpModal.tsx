"use client";

import React, { useEffect, useState } from "react";
import { HelpCircle, X, ChevronDown, ChevronUp, ShieldCheck, Layers, Cpu, Send } from "lucide-react";

interface ApiHelpModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const ApiHelpModal: React.FC<ApiHelpModalProps> = ({ isOpen, onClose }) => {
  const [openSection, setOpenSection] = useState<string>("inputs");

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

  if (!isOpen) return null;

  const toggleSection = (id: string) => {
    setOpenSection(openSection === id ? "" : id);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-md animate-in fade-in duration-200">
      <div className="relative w-full max-w-2xl max-h-[85vh] glass-card rounded-2xl border border-indigo-500/30 shadow-2xl flex flex-col overflow-hidden">
        {/* Modal Header */}
        <div className="flex items-center justify-between p-5 border-b border-slate-800 bg-slate-900/80">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-xl bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">
              <HelpCircle className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-base font-bold text-slate-100">API Inputs & Output Metrics Guide</h3>
              <p className="text-xs text-slate-400">
                Detailed schema breakdown for request payload & evaluation output metrics
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

        {/* Scrollable Content Body with Accordions */}
        <div className="flex-1 overflow-y-auto p-5 space-y-4 text-xs">
          {/* Section 1: Input Submission Payload */}
          <div className="rounded-xl border border-slate-800 bg-slate-950/60 overflow-hidden">
            <button
              type="button"
              onClick={() => toggleSection("inputs")}
              className="w-full flex items-center justify-between p-3.5 bg-slate-900/80 hover:bg-slate-900 text-left font-bold text-slate-200 transition-colors"
            >
              <span className="flex items-center gap-2">
                <Send className="w-4 h-4 text-cyan-400" />
                <span>1. Request Input Payload (POST /score)</span>
              </span>
              {openSection === "inputs" ? <ChevronUp className="w-4 h-4 text-slate-400" /> : <ChevronDown className="w-4 h-4 text-slate-400" />}
            </button>

            {openSection === "inputs" && (
              <div className="p-4 space-y-3 border-t border-slate-800">
                <div className="p-3 rounded-lg bg-slate-900/80 border border-slate-800 space-y-1">
                  <div className="flex items-center justify-between font-mono">
                    <span className="font-bold text-emerald-400">what_you_like</span>
                    <span className="text-[10px] text-slate-400">string (max 4000 chars) · Required</span>
                  </div>
                  <p className="text-slate-300 text-[11px] leading-relaxed">
                    Positive product observations, specific features praised, or key workflow benefits experienced.
                  </p>
                </div>

                <div className="p-3 rounded-lg bg-slate-900/80 border border-slate-800 space-y-1">
                  <div className="flex items-center justify-between font-mono">
                    <span className="font-bold text-amber-400">what_you_dislike</span>
                    <span className="text-[10px] text-slate-400">string (max 4000 chars) · Required</span>
                  </div>
                  <p className="text-slate-300 text-[11px] leading-relaxed">
                    Limitations, missing capabilities, frustrations, or specific improvement opportunities.
                  </p>
                </div>

                <div className="p-3 rounded-lg bg-slate-900/80 border border-slate-800 space-y-1">
                  <div className="flex items-center justify-between font-mono">
                    <span className="font-bold text-cyan-400">problem_solved</span>
                    <span className="text-[10px] text-slate-400">string (max 4000 chars) · Required</span>
                  </div>
                  <p className="text-slate-300 text-[11px] leading-relaxed">
                    The specific product team workflow, coordination gap, or business outcome the product addresses.
                  </p>
                </div>

                <div className="p-3 rounded-lg bg-slate-900/80 border border-slate-800 space-y-1">
                  <div className="flex items-center justify-between font-mono">
                    <span className="font-bold text-purple-400">add_to_corpus</span>
                    <span className="text-[10px] text-slate-400">boolean (default: false) · Optional</span>
                  </div>
                  <p className="text-slate-300 text-[11px] leading-relaxed">
                    Opt-in flag requesting high-scoring novel reviews to be appended to the comparison baseline corpus.
                  </p>
                </div>
              </div>
            )}
          </div>

          {/* Section 2: Output Score Result */}
          <div className="rounded-xl border border-slate-800 bg-slate-950/60 overflow-hidden">
            <button
              type="button"
              onClick={() => toggleSection("output")}
              className="w-full flex items-center justify-between p-3.5 bg-slate-900/80 hover:bg-slate-900 text-left font-bold text-slate-200 transition-colors"
            >
              <span className="flex items-center gap-2">
                <ShieldCheck className="w-4 h-4 text-emerald-400" />
                <span>2. Overall Score Result (ScoreResult)</span>
              </span>
              {openSection === "output" ? <ChevronUp className="w-4 h-4 text-slate-400" /> : <ChevronDown className="w-4 h-4 text-slate-400" />}
            </button>

            {openSection === "output" && (
              <div className="p-4 space-y-3 border-t border-slate-800">
                <div className="p-3 rounded-lg bg-slate-900/80 border border-slate-800 space-y-1">
                  <div className="flex items-center justify-between font-mono">
                    <span className="font-bold text-indigo-400">submission_score</span>
                    <span className="text-[10px] text-slate-400">float (0.0 to 1.0)</span>
                  </div>
                  <p className="text-slate-300 text-[11px] leading-relaxed">
                    Final overall novelty score normalized from 0% to 100%. Aggregates novelty fraction and relevance gate across all review fields.
                  </p>
                </div>

                <div className="p-3 rounded-lg bg-slate-900/80 border border-slate-800 space-y-1">
                  <div className="flex items-center justify-between font-mono">
                    <span className="font-bold text-purple-400">scoring_mode</span>
                    <span className="text-[10px] text-slate-400">string</span>
                  </div>
                  <p className="text-slate-300 text-[11px] leading-relaxed">
                    Mathematical aggregation rule: <code className="text-cyan-300 font-mono">mean(novelty × relevance) per claim</code>. Ensures off-topic claims stay low-scoring.
                  </p>
                </div>

                <div className="p-3 rounded-lg bg-slate-900/80 border border-slate-800 space-y-1">
                  <div className="flex items-center justify-between font-mono">
                    <span className="font-bold text-amber-400">degraded</span>
                    <span className="text-[10px] text-slate-400">boolean</span>
                  </div>
                  <p className="text-slate-300 text-[11px] leading-relaxed">
                    True if the cloud LLM judge was unavailable, causing the system to fall back safely to CPU vector similarity scoring.
                  </p>
                </div>
              </div>
            )}
          </div>

          {/* Section 3: Extracted Atomic Claims */}
          <div className="rounded-xl border border-slate-800 bg-slate-950/60 overflow-hidden">
            <button
              type="button"
              onClick={() => toggleSection("claims")}
              className="w-full flex items-center justify-between p-3.5 bg-slate-900/80 hover:bg-slate-900 text-left font-bold text-slate-200 transition-colors"
            >
              <span className="flex items-center gap-2">
                <Layers className="w-4 h-4 text-purple-400" />
                <span>3. Extracted Claim Metrics (ClaimAssessment)</span>
              </span>
              {openSection === "claims" ? <ChevronUp className="w-4 h-4 text-slate-400" /> : <ChevronDown className="w-4 h-4 text-slate-400" />}
            </button>

            {openSection === "claims" && (
              <div className="p-4 space-y-3 border-t border-slate-800">
                <div className="p-3 rounded-lg bg-slate-900/80 border border-slate-800 space-y-1">
                  <div className="flex items-center justify-between font-mono">
                    <span className="font-bold text-emerald-400">novelty_status</span>
                    <span className="text-[10px] text-slate-400">"novel" | "covered" | "partial"</span>
                  </div>
                  <p className="text-slate-300 text-[11px] leading-relaxed">
                    🟢 <strong className="text-emerald-300">novel</strong>: introduces new information not found in corpus. 🔴 <strong className="text-rose-300">covered</strong>: repeated/paraphrased observation. 🟡 <strong className="text-amber-300">partial</strong>: adds partial credit.
                  </p>
                </div>

                <div className="p-3 rounded-lg bg-slate-900/80 border border-slate-800 space-y-1">
                  <div className="flex items-center justify-between font-mono">
                    <span className="font-bold text-cyan-400">nearest_similarity</span>
                    <span className="text-[10px] text-slate-400">float (0.0 to 1.0)</span>
                  </div>
                  <p className="text-slate-300 text-[11px] leading-relaxed">
                    Cosine similarity score against closest baseline claim in <code className="text-cyan-300 font-mono">corpus.json</code>. High threshold is ≥0.82; low threshold is ≤0.48.
                  </p>
                </div>

                <div className="p-3 rounded-lg bg-slate-900/80 border border-slate-800 space-y-1">
                  <div className="flex items-center justify-between font-mono">
                    <span className="font-bold text-purple-400">entailment_reason</span>
                    <span className="text-[10px] text-slate-400">string | null</span>
                  </div>
                  <p className="text-slate-300 text-[11px] leading-relaxed">
                    Natural language explanation provided by the Gemini LLM judge when checking semantic coverage for ambiguous similarity claims.
                  </p>
                </div>
              </div>
            )}
          </div>

          {/* Section 4: Execution Trace Telemetry */}
          <div className="rounded-xl border border-slate-800 bg-slate-950/60 overflow-hidden">
            <button
              type="button"
              onClick={() => toggleSection("trace")}
              className="w-full flex items-center justify-between p-3.5 bg-slate-900/80 hover:bg-slate-900 text-left font-bold text-slate-200 transition-colors"
            >
              <span className="flex items-center gap-2">
                <Cpu className="w-4 h-4 text-indigo-400" />
                <span>4. Telemetry & Trace Metadata (ScoreMeta)</span>
              </span>
              {openSection === "trace" ? <ChevronUp className="w-4 h-4 text-slate-400" /> : <ChevronDown className="w-4 h-4 text-slate-400" />}
            </button>

            {openSection === "trace" && (
              <div className="p-4 space-y-3 border-t border-slate-800">
                <div className="p-3 rounded-lg bg-slate-900/80 border border-slate-800 space-y-1">
                  <div className="flex items-center justify-between font-mono">
                    <span className="font-bold text-slate-200">total_latency_ms</span>
                    <span className="text-[10px] text-slate-400">float (ms)</span>
                  </div>
                  <p className="text-slate-300 text-[11px] leading-relaxed">
                    End-to-end server latency from claim extraction through vector search to final score aggregation.
                  </p>
                </div>

                <div className="p-3 rounded-lg bg-slate-900/80 border border-slate-800 space-y-1">
                  <div className="flex items-center justify-between font-mono">
                    <span className="font-bold text-emerald-400">total_cost</span>
                    <span className="text-[10px] text-slate-400">float (USD)</span>
                  </div>
                  <p className="text-slate-300 text-[11px] leading-relaxed">
                    Calculated OpenRouter API cost based on exact prompt & completion token consumption for fast & judge models.
                  </p>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Footer close button */}
        <div className="p-4 border-t border-slate-800 bg-slate-900/80 text-right">
          <button
            type="button"
            onClick={onClose}
            className="px-5 py-2 rounded-xl text-xs font-bold text-white bg-indigo-600 hover:bg-indigo-500 transition-colors"
          >
            Close Guide
          </button>
        </div>
      </div>
    </div>
  );
};
