"use client";

import React, { useEffect, useState } from "react";
import { Award, Zap, AlertTriangle, CheckCircle, ShieldCheck, Flame } from "lucide-react";
import confetti from "canvas-confetti";

interface ScoreGaugeProps {
  score: number; // 0.0 to 1.0
  scoringMode?: string;
  message?: string;
  reason?: string | null;
  totalClaimsCount: number;
  novelClaimsCount: number;
  coveredClaimsCount: number;
}

export const ScoreGauge: React.FC<ScoreGaugeProps> = ({
  score,
  scoringMode = "novelty × relevance",
  message,
  reason,
  totalClaimsCount,
  novelClaimsCount,
  coveredClaimsCount,
}) => {
  const percentage = Math.round(score * 100);
  const [animatedScore, setAnimatedScore] = useState(0);

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
  const size = 180;
  const strokeWidth = 14;
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
    statusBadge = { label: "High Redundancy / Low Score", bg: "bg-rose-500/10", text: "text-rose-400", border: "border-rose-500/30", icon: AlertTriangle };
  } else if (percentage < 60) {
    colorGradient = "from-amber-400 to-yellow-500";
    strokeColor = "#f59e0b";
    statusBadge = { label: "Moderate Novelty", bg: "bg-amber-500/10", text: "text-amber-400", border: "border-amber-500/30", icon: Flame };
  } else if (percentage < 85) {
    colorGradient = "from-indigo-400 via-purple-400 to-cyan-400";
    strokeColor = "#6366f1";
    statusBadge = { label: "Strong Novel & Relevant Review", bg: "bg-indigo-500/10", text: "text-indigo-400", border: "border-indigo-500/30", icon: Zap };
  }

  const BadgeIcon = statusBadge.icon;

  return (
    <div className="w-full glass-card rounded-2xl p-6 border border-slate-800 shadow-2xl relative overflow-hidden flex flex-col md:flex-row items-center justify-between gap-6">
      {/* Decorative background glow */}
      <div className="absolute top-1/2 left-1/4 -translate-y-1/2 w-48 h-48 bg-indigo-500/10 rounded-full blur-3xl pointer-events-none" />

      {/* Left side: Radial Gauge & Numeric Score */}
      <div className="flex flex-col items-center justify-center relative min-w-[200px]">
        <div className="relative flex items-center justify-center">
          <svg width={size} height={size} className="transform -rotate-90 drop-shadow-lg">
            {/* Background Track */}
            <circle
              cx={size / 2}
              cy={size / 2}
              r={radius}
              stroke="rgba(30, 41, 59, 0.8)"
              strokeWidth={strokeWidth}
              fill="transparent"
            />
            {/* Animated Progress Ring */}
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

          {/* Center Text */}
          <div className="absolute inset-0 flex flex-col items-center justify-center text-center">
            <span className={`text-4xl font-extrabold tracking-tight text-transparent bg-clip-text bg-gradient-to-r ${colorGradient}`}>
              {animatedScore}%
            </span>
            <span className="text-[10px] uppercase font-bold tracking-wider text-slate-400 mt-0.5">
              Novelty Score
            </span>
          </div>
        </div>
      </div>

      {/* Right side: Detailed Status & Breakdown Metrics */}
      <div className="flex-1 w-full space-y-4 text-left">
        <div>
          <div className="flex items-center gap-2 flex-wrap">
            <span className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold border ${statusBadge.bg} ${statusBadge.text} ${statusBadge.border}`}>
              <BadgeIcon className="w-3.5 h-3.5" />
              {statusBadge.label}
            </span>

            <span className="px-2.5 py-1 rounded-full text-[11px] font-mono text-slate-400 bg-slate-900 border border-slate-800">
              Mode: {scoringMode}
            </span>
          </div>

          {message && (
            <p className="text-sm font-medium text-slate-200 mt-2.5 leading-relaxed">
              {message}
            </p>
          )}

          {reason && (
            <p className="text-xs text-amber-300/90 bg-amber-500/10 border border-amber-500/20 rounded-lg p-2.5 mt-2">
              ⚠️ Note: {reason}
            </p>
          )}
        </div>

        {/* Mini stats counters */}
        <div className="grid grid-cols-3 gap-3 pt-3 border-t border-slate-800/80">
          <div className="p-2.5 rounded-xl bg-slate-900/80 border border-slate-800 text-center">
            <span className="block text-xs text-slate-400">Total Claims</span>
            <span className="text-lg font-bold text-slate-100 font-mono">{totalClaimsCount}</span>
          </div>
          <div className="p-2.5 rounded-xl bg-slate-900/80 border border-emerald-500/20 text-center">
            <span className="block text-xs text-emerald-400 font-medium">Novel Claims</span>
            <span className="text-lg font-bold text-emerald-400 font-mono">{novelClaimsCount}</span>
          </div>
          <div className="p-2.5 rounded-xl bg-slate-900/80 border border-rose-500/20 text-center">
            <span className="block text-xs text-rose-400 font-medium">Covered Claims</span>
            <span className="text-lg font-bold text-rose-400 font-mono">{coveredClaimsCount}</span>
          </div>
        </div>
      </div>
    </div>
  );
};
