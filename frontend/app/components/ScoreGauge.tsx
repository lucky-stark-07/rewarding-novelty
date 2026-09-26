"use client";

import React, { useEffect, useState } from "react";
import { Award, Zap, AlertTriangle, Flame, Activity, Info } from "lucide-react";
import confetti from "canvas-confetti";

interface ScoreGaugeProps {
  score: number; // 0.0 to 1.0
  scoringMode?: string;
  message?: string;
  reason?: string | null;
  totalClaimsCount: number;
  novelClaimsCount: number;
  coveredClaimsCount: number;
  onShowTrace?: () => void;
  latencyMs?: number;
}

export const ScoreGauge: React.FC<ScoreGaugeProps> = ({
  score,
  scoringMode = "novelty × relevance",
  message,
  reason,
  totalClaimsCount,
  novelClaimsCount,
  coveredClaimsCount,
  onShowTrace,
  latencyMs,
}) => {
  const percentage = Math.round(score * 100);
  const [animatedScore, setAnimatedScore] = useState(0);
  const [showTooltip, setShowTooltip] = useState(false);

  useEffect(() => {
    const duration = 1000;
    const steps = 30;
    const increment = percentage / steps;
    let current = 0;
    const timer = setInterval(() => {
      current += increment;
      if (current >= percentage) {
        setAnimatedScore(percentage);
        clearInterval(timer);
        if (percentage >= 75) {
          confetti({
            particleCount: 50,
            spread: 60,
            origin: { y: 0.7 },
          });
        }
      } else {
        setAnimatedScore(Math.round(current));
      }
    }, duration / steps);

    return () => clearInterval(timer);
  }, [percentage]);

  // SVG Gauge constants
  const size = 150;
  const strokeWidth = 12;
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const strokeDashoffset = circumference - (animatedScore / 100) * circumference;

  // Determine color scheme
  let colorGradient = "from-emerald-400 to-cyan-400";
  let strokeColor = "#10b981"; // emerald
  let statusBadge = { label: "Exceptional Novelty", bg: "bg-emerald-500/10", text: "text-emerald-400", border: "border-emerald-500/30", icon: Award };

  if (percentage < 30) {
    colorGradient = "from-rose-500 to-amber-500";
    strokeColor = "#f43f5e";
    statusBadge = { label: "High Redundancy", bg: "bg-rose-500/10", text: "text-rose-400", border: "border-rose-500/30", icon: AlertTriangle };
  } else if (percentage < 60) {
    colorGradient = "from-amber-400 to-yellow-500";
    strokeColor = "#f59e0b";
    statusBadge = { label: "Moderate Novelty", bg: "bg-amber-500/10", text: "text-amber-400", border: "border-amber-500/30", icon: Flame };
  } else if (percentage < 85) {
    colorGradient = "from-indigo-400 via-purple-400 to-cyan-400";
    strokeColor = "#6366f1";
    statusBadge = { label: "Strong Novelty", bg: "bg-indigo-500/10", text: "text-indigo-400", border: "border-indigo-500/30", icon: Zap };
  }

  const BadgeIcon = statusBadge.icon;

  return (
    <div className="w-full glass-card rounded-2xl p-5 border border-slate-800 shadow-2xl relative overflow-hidden flex flex-col justify-between space-y-4 h-full">
      {/* Background glow */}
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-40 h-40 bg-indigo-500/10 rounded-full blur-3xl pointer-events-none" />

      {/* Header Info Bar */}
      <div className="flex items-center justify-between gap-2 border-b border-slate-800/80 pb-3">
        <span className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-bold border ${statusBadge.bg} ${statusBadge.text} ${statusBadge.border}`}>
          <BadgeIcon className="w-3.5 h-3.5" />
          {statusBadge.label}
        </span>

        {/* Info Tooltip Icon */}
        <div className="relative">
          <button
            type="button"
            onMouseEnter={() => setShowTooltip(true)}
            onMouseLeave={() => setShowTooltip(false)}
            onClick={() => setShowTooltip(!showTooltip)}
            className="p-1 rounded-lg bg-slate-900 hover:bg-slate-800 text-slate-400 hover:text-slate-200 border border-slate-800 transition-colors"
            title="Score Formula & Info"
          >
            <Info className="w-4 h-4" />
          </button>

          {showTooltip && (
            <div className="absolute right-0 top-7 z-30 w-64 p-3 rounded-xl bg-slate-900 border border-indigo-500/40 text-xs text-slate-200 shadow-2xl space-y-1">
              <strong className="font-bold text-cyan-300 block">Scoring Mode</strong>
              <p className="text-[11px] text-slate-300 leading-normal">
                {scoringMode}: Each claim&apos;s novelty is multiplied by its relevance gate, so off-topic claims stay low-scoring.
              </p>
            </div>
          )}
        </div>
      </div>

      {/* Center Radial Score Gauge */}
      <div className="flex flex-col items-center justify-center relative py-1">
        <div className="relative flex items-center justify-center">
          <svg width={size} height={size} className="transform -rotate-90 drop-shadow-lg">
            <circle
              cx={size / 2}
              cy={size / 2}
              r={radius}
              stroke="rgba(30, 41, 59, 0.8)"
              strokeWidth={strokeWidth}
              fill="transparent"
            />
            <circle
              cx={size / 2}
              cy={size / 2}
              r={radius}
              stroke={strokeColor}
              strokeWidth={strokeWidth}
              fill="transparent"
              strokeDasharray={circumference}
              strokeDashoffset={strokeDashoffset}
              strokeLinecap="round"
              className="transition-all duration-700 ease-out"
            />
          </svg>

          <div className="absolute inset-0 flex flex-col items-center justify-center text-center">
            <span className={`text-3xl font-extrabold tracking-tight text-transparent bg-clip-text bg-gradient-to-r ${colorGradient}`}>
              {animatedScore}%
            </span>
            <span className="text-[9px] uppercase font-bold tracking-wider text-slate-400 mt-0.5">
              Novelty Score
            </span>
          </div>
        </div>

        {message && (
          <p className="text-[11px] text-slate-300 text-center mt-2 font-medium line-clamp-2 px-2">
            {message}
          </p>
        )}
      </div>

      {/* Mini Claim Metrics */}
      <div className="grid grid-cols-3 gap-2 pt-2 border-t border-slate-800/80">
        <div className="p-1.5 rounded-lg bg-slate-900/80 border border-slate-800 text-center">
          <span className="block text-[10px] text-slate-400">Claims</span>
          <span className="text-sm font-bold text-slate-100 font-mono">{totalClaimsCount}</span>
        </div>
        <div className="p-1.5 rounded-lg bg-slate-900/80 border border-emerald-500/20 text-center">
          <span className="block text-[10px] text-emerald-400">Novel</span>
          <span className="text-sm font-bold text-emerald-400 font-mono">{novelClaimsCount}</span>
        </div>
        <div className="p-1.5 rounded-lg bg-slate-900/80 border border-rose-500/20 text-center">
          <span className="block text-[10px] text-rose-400">Covered</span>
          <span className="text-sm font-bold text-rose-400 font-mono">{coveredClaimsCount}</span>
        </div>
      </div>

      {/* Show Execution Trace Option Button */}
      {onShowTrace && (
        <button
          type="button"
          onClick={onShowTrace}
          className="w-full py-2.5 px-3 rounded-xl bg-indigo-600/20 hover:bg-indigo-600/30 text-indigo-300 border border-indigo-500/30 text-xs font-bold transition-all shadow-sm flex items-center justify-center gap-2 group"
        >
          <Activity className="w-3.5 h-3.5 text-indigo-400 group-hover:scale-110 transition-transform" />
          <span>Show Execution Trace</span>
          {typeof latencyMs === "number" && (
            <span className="text-[10px] font-mono text-cyan-400 font-normal">({latencyMs.toFixed(0)}ms)</span>
          )}
        </button>
      )}
    </div>
  );
};
