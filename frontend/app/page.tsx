"use client";

import { useEffect, useState } from "react";
import { Header } from "./components/Header";
import { ReferenceBanner } from "./components/ReferenceBanner";
import { ReviewForm } from "./components/ReviewForm";
import { ScoreGauge } from "./components/ScoreGauge";
import { FieldBreakdown } from "./components/FieldBreakdown";
import { CorpusInspector } from "./components/CorpusInspector";
import { ArchitectureVisualizer } from "./components/ArchitectureVisualizer";
import { DegradedBadge, TracePanel } from "./components/TracePanel";
import { ScoreResult, CorpusEntry } from "./types";
import { Sparkles, Layers, RefreshCw, AlertCircle, Award } from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function Home() {
  const [activeTab, setActiveTab] = useState<"evaluator" | "corpus" | "architecture">("evaluator");
  const [apiHealth, setApiHealth] = useState<"checking" | "online" | "offline">("checking");
  const [result, setResult] = useState<ScoreResult | null>(null);
  const [corpus, setCorpus] = useState<CorpusEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadingCorpus, setLoadingCorpus] = useState(false);
  const [error, setError] = useState("");

  const checkHealth = async () => {
    setApiHealth("checking");
    try {
      const res = await fetch(`${API}/health`, { cache: "no-store" });
      if (res.ok) {
        setApiHealth("online");
      } else {
        setApiHealth("offline");
      }
    } catch {
      setApiHealth("offline");
    }
  };

  const fetchCorpus = async () => {
    try {
      const res = await fetch(`${API}/corpus`, { cache: "no-store" });
      if (res.ok) {
        const data = await res.json();
        setCorpus(data);
      }
    } catch {
      // Corpus offline fallback or quiet fail
    }
  };

  useEffect(() => {
    checkHealth();
    fetchCorpus();
  }, []);

  const handleSubmit = async (
    form: {
      what_you_like: string;
      what_you_dislike: string;
      problem_solved: string;
    },
    addToCorpus: boolean
  ) => {
    setLoading(true);
    setError("");
    try {
      const res = await fetch(`${API}/score`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...form, add_to_corpus: addToCorpus }),
      });

      if (!res.ok) {
        const errorText = await res.text();
        let detail = errorText;
        try {
          const parsed = JSON.parse(errorText);
          if (typeof parsed.detail === "string") detail = parsed.detail;
        } catch {
          // Non-JSON error body; show it as-is.
        }
        throw new Error(`${detail || "Request failed"} (HTTP ${res.status})`);
      }

      const scoreData: ScoreResult = await res.json();
      setResult(scoreData);
      if (scoreData.added_to_corpus) await fetchCorpus();
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Scoring request failed. Ensure backend FastAPI server is running on http://localhost:8000."
      );
    } finally {
      setLoading(false);
    }
  };

  const handleRegenerateCorpus = async () => {
    setLoadingCorpus(true);
    try {
      const res = await fetch(`${API}/corpus/regenerate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
      });
      if (!res.ok) throw new Error(await res.text());
      const updatedCorpus = await res.json();
      setCorpus(updatedCorpus);
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to regenerate corpus");
    } finally {
      setLoadingCorpus(false);
    }
  };

  // Calculate totals from claims assessment
  const allAssessments = result?.field_scores?.flatMap((f) => f.claims) || [];
  const novelCount = allAssessments.filter((c) => c.novelty_status === "novel").length;
  const coveredCount = allAssessments.filter((c) => c.novelty_status === "covered").length;

  return (
    <div className="min-h-screen bg-[#0b0f19] flex flex-col selection:bg-indigo-500 selection:text-white">
      {/* Header Navigation */}
      <Header
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        apiHealth={apiHealth}
        checkHealth={checkHealth}
        corpusCount={corpus.length}
      />

      {/* Main Container */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-6">
        {/* Evaluator Tab */}
        {activeTab === "evaluator" && (
          <div className="space-y-6">
            {/* Reference Product Banner */}
            <ReferenceBanner />

            {/* Main Side-by-Side Ergonomic Workspace */}
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
              {/* Left 5 Columns: Review Input Form & Presets */}
              <div className="lg:col-span-5 space-y-6">
                <ReviewForm onSubmit={handleSubmit} loading={loading} error={error} />
              </div>

              {/* Right 7 Columns: Complete Scoring & Claims Console */}
              <div className="lg:col-span-7 space-y-6">
                {result ? (
                  <div className="space-y-6">
                    {/* Degraded mode warning if applicable */}
                    {result.degraded && (
                      <div className="rounded-xl border border-amber-500/40 bg-amber-500/10 p-3 text-xs text-amber-200 flex items-start gap-2">
                        <DegradedBadge reason={result.degraded_reason} />
                        <span>
                          The LLM judge was unavailable, so this score used embedding similarity only and is provisional.
                          {result.degraded_reason ? ` (${result.degraded_reason})` : ""}
                        </span>
                      </div>
                    )}

                    {/* Overall Score Radial Gauge */}
                    <ScoreGauge
                      score={result.submission_score}
                      scoringMode={result.scoring_mode}
                      message={result.message}
                      reason={result.reason}
                      totalClaimsCount={allAssessments.length}
                      novelClaimsCount={novelCount}
                      coveredClaimsCount={coveredCount}
                    />

                    {/* Corpus Add Callouts */}
                    {result.added_to_corpus && (
                      <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/10 p-3 text-center text-xs text-emerald-200">
                        Added to the comparison corpus. Future scores may change.
                      </div>
                    )}
                    {result.add_to_corpus_requested && !result.added_to_corpus && (
                      <div className="rounded-xl border border-slate-700 bg-slate-900 p-3 text-center text-xs text-slate-300">
                        Not added to the comparison corpus. It was already present, did not meet the acceptance threshold, or was scored in degraded mode.
                      </div>
                    )}

                    {/* Execution Telemetry Trace */}
                    {result.meta && <TracePanel meta={result.meta} />}

                    {/* Field-by-Field Claims Assessment Grid */}
                    <FieldBreakdown fieldScores={result.field_scores} />
                  </div>
                ) : (
                  <div className="glass-card rounded-2xl p-8 border border-slate-800 text-center space-y-6">
                    <div className="w-16 h-16 rounded-2xl bg-indigo-500/10 border border-indigo-500/20 text-indigo-400 flex items-center justify-center mx-auto animate-float">
                      <Sparkles className="w-8 h-8" />
                    </div>
                    <div>
                      <h3 className="text-base font-bold text-slate-200">Evaluation Console Ready</h3>
                      <p className="text-xs text-slate-400 leading-relaxed max-w-sm mx-auto mt-1">
                        Fill out the 3 review fields on the left or select a quick preset template, then click &ldquo;Evaluate Review Novelty & Relevance&rdquo;.
                      </p>
                    </div>

                    <div className="pt-4 border-t border-slate-800/80 grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs text-slate-400 text-left">
                      <div className="p-3 rounded-xl bg-slate-900/60 border border-slate-800 space-y-1">
                        <span className="font-semibold text-cyan-300 block">1. Atomic Claim Extraction</span>
                        <p className="text-[11px] text-slate-400">
                          Decomposes text into discrete proposition claims using fast OpenRouter model.
                        </p>
                      </div>
                      <div className="p-3 rounded-xl bg-slate-900/60 border border-slate-800 space-y-1">
                        <span className="font-semibold text-purple-300 block">2. Local Vector & LLM Judge</span>
                        <p className="text-[11px] text-slate-400">
                          Compares claims with 50 baseline reviews & evaluates semantic entailment.
                        </p>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Corpus Tab */}
        {activeTab === "corpus" && (
          <CorpusInspector
            corpus={corpus}
            onRegenerateCorpus={handleRegenerateCorpus}
            loadingRegen={loadingCorpus}
          />
        )}

        {/* Architecture Tab */}
        {activeTab === "architecture" && <ArchitectureVisualizer />}
      </main>

      {/* Footer */}
      <footer className="w-full glass-panel border-t border-slate-800/80 py-6 mt-12">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex flex-col sm:flex-row items-center justify-between gap-4 text-xs text-slate-400">
          <div className="flex items-center gap-2">
            <span className="font-bold text-slate-200">NoveltyLens</span>
            <span>— review novelty &amp; relevance scoring</span>
          </div>

          <div className="flex items-center gap-4">
            <span className="font-mono text-[11px] text-slate-500">
              OpenRouter Gemini + Local CPU Vector Embeddings
            </span>
          </div>
        </div>
      </footer>
    </div>
  );
}
