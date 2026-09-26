"use client";

import { useEffect, useState } from "react";
import { Header, TabType } from "./components/Header";
import { ReferenceBanner } from "./components/ReferenceBanner";
import { ReviewForm } from "./components/ReviewForm";
import { ScoreGauge } from "./components/ScoreGauge";
import { FieldBreakdown } from "./components/FieldBreakdown";
import { CorpusInspector } from "./components/CorpusInspector";
import { ArchitectureVisualizer } from "./components/ArchitectureVisualizer";
import { DegradedBadge } from "./components/TracePanel";
import { TraceModal } from "./components/TraceModal";
import { ScoreResult, CorpusEntry } from "./types";
import { Sparkles, Layers, Cpu } from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function Home() {
  const [activeTab, setActiveTab] = useState<TabType>("evaluator");
  const [apiHealth, setApiHealth] = useState<"checking" | "online" | "offline">("checking");
  const [result, setResult] = useState<ScoreResult | null>(null);
  const [corpus, setCorpus] = useState<CorpusEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadingCorpus, setLoadingCorpus] = useState(false);
  const [error, setError] = useState("");
  const [isTraceOpen, setIsTraceOpen] = useState(false);

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

  const [regenerateEnabled, setRegenerateEnabled] = useState(false);

  const fetchRegenerateFlag = async () => {
    try {
      const res = await fetch(`${API}/stats`, { cache: "no-store" });
      if (res.ok) setRegenerateEnabled(Boolean((await res.json()).config?.corpus_regenerate_enabled));
    } catch {
      setRegenerateEnabled(false);
    }
  };

  useEffect(() => {
    checkHealth();
    fetchCorpus();
    fetchRegenerateFlag();
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
    const confirmed = window.confirm(
      `Replace all ${corpus.length} comparison reviews with 50 newly generated ones?\n\n` +
        "Every future score will change, reviews added from this UI will be lost, and this makes paid model calls."
    );
    if (!confirmed) return;
    // Asked for on each use and never stored in the browser.
    const token = window.prompt("Admin token (ADMIN_TOKEN on the server):");
    if (!token) return;
    setLoadingCorpus(true);
    try {
      const res = await fetch(`${API}/corpus/regenerate`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "x-admin-token": token },
      });
      if (!res.ok) {
        let detail = await res.text();
        try {
          detail = JSON.parse(detail).detail ?? detail;
        } catch {
          // Non-JSON error body; show it as-is.
        }
        throw new Error(`${detail} (HTTP ${res.status})`);
      }
      setCorpus(await res.json());
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to regenerate corpus");
    } finally {
      setLoadingCorpus(false);
    }
  };

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
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-5 space-y-6">
        {/* Evaluator Tab */}
        {activeTab === "evaluator" && (
          <div className="space-y-6">
            {/* ROW 1: Submit Form (70% / 8 cols) & Score Card (30% / 4 cols) side-by-side */}
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 items-stretch">
              {/* Left: Review Submission Form */}
              <div className="lg:col-span-8 w-full">
                <ReviewForm onSubmit={handleSubmit} loading={loading} error={error} />
              </div>

              {/* Right: Score Card (30% width) */}
              <div className="lg:col-span-4 w-full flex flex-col justify-stretch">
                {result ? (
                  <div className="space-y-3 h-full flex flex-col justify-between">
                    {result.degraded && (
                      <div className="rounded-xl border border-amber-500/40 bg-amber-500/10 p-2.5 text-xs text-amber-200 flex items-start gap-2">
                        <DegradedBadge reason={result.degraded_reason} />
                        <span className="text-[11px]">
                          LLM judge unavailable; used embedding similarity.
                        </span>
                      </div>
                    )}

                    {/* Compact Score Gauge Card */}
                    <ScoreGauge
                      score={result.submission_score}
                      scoringMode={result.scoring_mode}
                      message={result.message}
                      reason={result.reason}
                      totalClaimsCount={allAssessments.length}
                      novelClaimsCount={novelCount}
                      coveredClaimsCount={coveredCount}
                      onShowTrace={result.meta ? () => setIsTraceOpen(true) : undefined}
                      latencyMs={result.meta?.total_latency_ms}
                    />

                    {/* Corpus Add Callout */}
                    {result.added_to_corpus && (
                      <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/10 p-2.5 text-center text-xs text-emerald-200 font-medium">
                        Added to baseline comparison corpus.
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="glass-card rounded-2xl p-6 border border-slate-800 text-center space-y-4 h-full flex flex-col items-center justify-center">
                    <div className="w-12 h-12 rounded-xl bg-indigo-500/10 border border-indigo-500/20 text-indigo-400 flex items-center justify-center mx-auto animate-float">
                      <Sparkles className="w-6 h-6" />
                    </div>
                    <div>
                      <h3 className="text-sm font-bold text-slate-200">Evaluation Console Ready</h3>
                      <p className="text-[11px] text-slate-400 leading-relaxed max-w-xs mx-auto mt-0.5">
                        Submit a product review or select a preset to evaluate novelty & relevance score.
                      </p>
                    </div>

                    <div className="pt-3 border-t border-slate-800/80 space-y-2 text-left w-full text-[11px] text-slate-400">
                      <div className="p-2.5 rounded-lg bg-slate-900/60 border border-slate-800 flex items-start gap-2">
                        <Layers className="w-3.5 h-3.5 text-cyan-400 shrink-0 mt-0.5" />
                        <div>
                          <span className="font-semibold text-cyan-300 block">Atomic Claim Extraction</span>
                          <span className="text-[10px]">Decomposes text into discrete proposition claims.</span>
                        </div>
                      </div>
                      <div className="p-2.5 rounded-lg bg-slate-900/60 border border-slate-800 flex items-start gap-2">
                        <Cpu className="w-3.5 h-3.5 text-purple-400 shrink-0 mt-0.5" />
                        <div>
                          <span className="font-semibold text-purple-300 block">Vector Search & Judge</span>
                          <span className="text-[10px]">Compares claims with 50 baseline reviews.</span>
                        </div>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* ROW 2: Field-by-Field Claim Assessment cards below */}
            {result && (
              <div className="pt-4 border-t border-slate-800/80">
                <FieldBreakdown fieldScores={result.field_scores} />
              </div>
            )}
          </div>
        )}

        {/* Reference Product Tab */}
        {activeTab === "reference" && <ReferenceBanner />}

        {/* Corpus Tab */}
        {activeTab === "corpus" && (
          <CorpusInspector
            corpus={corpus}
            onRegenerateCorpus={handleRegenerateCorpus}
            regenerateEnabled={regenerateEnabled}
            loadingRegen={loadingCorpus}
          />
        )}

        {/* Architecture Tab */}
        {activeTab === "architecture" && <ArchitectureVisualizer />}
      </main>

      {/* Pop-up Execution Trace Modal Window */}
      {result?.meta && (
        <TraceModal
          isOpen={isTraceOpen}
          onClose={() => setIsTraceOpen(false)}
          meta={result.meta}
        />
      )}

      {/* Footer */}
      <footer className="w-full glass-panel border-t border-slate-800/80 py-5 mt-10">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex flex-col sm:flex-row items-center justify-between gap-4 text-xs text-slate-400">
          <div className="flex items-center gap-2">
            <span className="font-bold text-slate-200">NoveltyLens</span>
            <span>— Hackathon Theme 3</span>
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
