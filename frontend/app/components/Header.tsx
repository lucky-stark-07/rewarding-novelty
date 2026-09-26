"use client";

import React, { useState } from "react";
import { Sparkles, Database, Cpu, Layers, Target, AlertCircle, RefreshCw, HelpCircle } from "lucide-react";
import { ApiHelpModal } from "./ApiHelpModal";

export type TabType = "evaluator" | "reference" | "corpus" | "architecture";

interface HeaderProps {
  activeTab: TabType;
  setActiveTab: (tab: TabType) => void;
  apiHealth: "checking" | "online" | "offline";
  checkHealth: () => void;
  corpusCount?: number;
}

export const Header: React.FC<HeaderProps> = ({
  activeTab,
  setActiveTab,
  apiHealth,
  checkHealth,
  corpusCount,
}) => {
  const [isHelpOpen, setIsHelpOpen] = useState(false);

  return (
    <>
      <header className="sticky top-0 z-40 w-full glass-panel border-b border-slate-800/80 backdrop-blur-xl">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-20 flex items-center justify-between gap-4">
          {/* Logo & Brand */}
          <div className="flex items-center gap-3">
            <div className="relative flex items-center justify-center w-11 h-11 rounded-xl bg-gradient-to-br from-indigo-500 via-purple-500 to-cyan-400 p-[1px] shadow-lg shadow-indigo-500/20 animate-float">
              <div className="w-full h-full bg-slate-950 rounded-[11px] flex items-center justify-center">
                <Sparkles className="w-6 h-6 text-cyan-400 animate-pulse" />
              </div>
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-xl font-extrabold tracking-tight text-transparent bg-clip-text bg-gradient-to-r from-white via-slate-200 to-cyan-300">
                  NoveltyLens
                </h1>
              </div>
              <p className="text-xs text-slate-400 font-medium hidden sm:block">
                See what is genuinely new in every review
              </p>
            </div>
          </div>

          {/* Navigation Tabs */}
          <nav className="flex items-center gap-1.5 p-1 bg-slate-900/80 rounded-xl border border-slate-800">
            <button
              onClick={() => setActiveTab("evaluator")}
              className={`flex items-center gap-2 px-3.5 py-2 text-xs font-semibold rounded-lg transition-all ${
                activeTab === "evaluator"
                  ? "bg-gradient-to-r from-indigo-600 to-purple-600 text-white shadow-md shadow-indigo-500/25"
                  : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/50"
              }`}
            >
              <Layers className="w-3.5 h-3.5" />
              <span>Evaluator</span>
            </button>

            <button
              onClick={() => setActiveTab("reference")}
              className={`flex items-center gap-2 px-3.5 py-2 text-xs font-semibold rounded-lg transition-all ${
                activeTab === "reference"
                  ? "bg-gradient-to-r from-indigo-600 to-purple-600 text-white shadow-md shadow-indigo-500/25"
                  : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/50"
              }`}
            >
              <Target className="w-3.5 h-3.5" />
              <span>Reference Product</span>
            </button>

            <button
              onClick={() => setActiveTab("corpus")}
              className={`flex items-center gap-2 px-3.5 py-2 text-xs font-semibold rounded-lg transition-all relative ${
                activeTab === "corpus"
                  ? "bg-gradient-to-r from-indigo-600 to-purple-600 text-white shadow-md shadow-indigo-500/25"
                  : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/50"
              }`}
            >
              <Database className="w-3.5 h-3.5" />
              <span>Corpus</span>
              {typeof corpusCount === "number" && (
                <span className="ml-1 px-1.5 py-0.5 text-[10px] font-mono bg-indigo-950/80 text-cyan-300 border border-indigo-700/50 rounded-md">
                  {corpusCount}
                </span>
              )}
            </button>

            <button
              onClick={() => setActiveTab("architecture")}
              className={`flex items-center gap-2 px-3.5 py-2 text-xs font-semibold rounded-lg transition-all ${
                activeTab === "architecture"
                  ? "bg-gradient-to-r from-indigo-600 to-purple-600 text-white shadow-md shadow-indigo-500/25"
                  : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/50"
              }`}
            >
              <Cpu className="w-3.5 h-3.5" />
              <span className="hidden md:inline">Architecture</span>
            </button>
          </nav>

          {/* API Health Pill & Help Icon Button */}
          <div className="flex items-center gap-2">
            <button
              onClick={checkHealth}
              title="Click to re-check API status"
              className="flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-medium border glass-panel transition-all hover:border-slate-700"
            >
              {apiHealth === "online" ? (
                <>
                  <span className="relative flex h-2 w-2">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                    <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
                  </span>
                  <span className="text-emerald-400 font-mono text-[11px]">API Online</span>
                </>
              ) : apiHealth === "offline" ? (
                <>
                  <AlertCircle className="w-3.5 h-3.5 text-rose-400" />
                  <span className="text-rose-400 font-mono text-[11px]">Backend Offline</span>
                </>
              ) : (
                <>
                  <RefreshCw className="w-3.5 h-3.5 text-amber-400 animate-spin" />
                  <span className="text-amber-400 font-mono text-[11px]">Connecting...</span>
                </>
              )}
            </button>

            {/* Help Icon Button */}
            <button
              type="button"
              onClick={() => setIsHelpOpen(true)}
              title="View API Inputs & Output Metrics Guide"
              className="p-1.5 rounded-full bg-slate-900 hover:bg-slate-800 border border-slate-800 text-indigo-400 hover:text-indigo-300 transition-all shadow-sm group"
            >
              <HelpCircle className="w-4 h-4 group-hover:scale-110 transition-transform" />
            </button>
          </div>
        </div>
      </header>

      {/* API Inputs & Output Guide Modal */}
      <ApiHelpModal isOpen={isHelpOpen} onClose={() => setIsHelpOpen(false)} />
    </>
  );
};
