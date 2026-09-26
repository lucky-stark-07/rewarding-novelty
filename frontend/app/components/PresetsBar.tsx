"use client";

import React from "react";
import { PresetReview } from "../types";
import { Sparkles, RefreshCcw, AlertTriangle, Scale, Check } from "lucide-react";

export const PRESETS: PresetReview[] = [
  {
    id: "novel_relevant",
    title: "Novel & Relevant",
    subtitle: "High novelty & baseline aligned",
    badge: "High Score Candidate",
    badgeColor: "bg-emerald-500/10 text-emerald-400 border-emerald-500/30",
    what_you_like:
      "The automated AI release-note compiler extracts customer feedback quotes directly from Gong calls and links them to Jira epics in real time.",
    what_you_dislike:
      "It currently lacks native webhooks for linear regression forecasting on launch timelines and multi-region SOC2 audit export logs.",
    problem_solved:
      "Eliminates manual product context switching for distributed engineering teams by automatically generating sprint changelogs for executive stakeholders.",
  },
  {
    id: "duplicate_covered",
    title: "Duplicate / Redundant",
    subtitle: "Standard feedback in corpus",
    badge: "Low Novelty",
    badgeColor: "bg-amber-500/10 text-amber-400 border-amber-500/30",
    what_you_like:
      "Great tool for centralizing product roadmaps, customer feedback, and project planning in one shared team workspace.",
    what_you_dislike:
      "The notification emails can get noisy when multiple team members edit release notes at the same time.",
    problem_solved:
      "Helps product managers keep distributed teams aligned on priorities without switching between many tools.",
  },
  {
    id: "off_topic",
    title: "Off-Topic / Irrelevant",
    subtitle: "Unrelated review content",
    badge: "Zero Relevance Gate",
    badgeColor: "bg-rose-500/10 text-rose-400 border-rose-500/30",
    what_you_like:
      "The extra cheese pizza arrived hot in under 20 minutes and the crust was super crispy.",
    what_you_dislike:
      "The delivery driver forgot the garlic dipping sauce and the soda was lukewarm.",
    problem_solved:
      "Satisfied late-night pizza cravings after a long gaming session with friends.",
  },
  {
    id: "balanced_mixed",
    title: "Balanced Feedback",
    subtitle: "Mix of common & new ideas",
    badge: "Moderate Score",
    badgeColor: "bg-indigo-500/10 text-indigo-400 border-indigo-500/30",
    what_you_like:
      "Centralizes roadmaps effectively, and the new visual canvas for customer feedback tagging is surprisingly fluid.",
    what_you_dislike:
      "Search filters can be slow when searching past release notes from over a year ago.",
    problem_solved:
      "Bridges the communication gap between customer support agents reporting bugs and developers triaging release notes.",
  },
];

interface PresetsBarProps {
  onSelectPreset: (preset: PresetReview) => void;
  activePresetId?: string;
}

export const PresetsBar: React.FC<PresetsBarProps> = ({
  onSelectPreset,
  activePresetId,
}) => {
  return (
    <div className="w-full space-y-3">
      <div className="flex items-center justify-between">
        <label className="text-xs font-bold text-slate-300 uppercase tracking-wider flex items-center gap-1.5">
          <Sparkles className="w-3.5 h-3.5 text-cyan-400" />
          <span>Quick Preset Reviews (1-Click Test)</span>
        </label>
        <span className="text-[11px] text-slate-400">Click to auto-fill review fields</span>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        {PRESETS.map((preset) => {
          const isActive = activePresetId === preset.id;
          return (
            <button
              key={preset.id}
              type="button"
              onClick={() => onSelectPreset(preset)}
              className={`p-3 rounded-xl glass-panel text-left transition-all duration-200 border relative group hover:-translate-y-0.5 ${
                isActive
                  ? "border-cyan-400 bg-slate-900/90 shadow-lg shadow-cyan-500/10"
                  : "border-slate-800 hover:border-slate-700 hover:bg-slate-900/60"
              }`}
            >
              <div className="flex items-center justify-between gap-2 mb-1.5">
                <span className="text-xs font-bold text-slate-100 group-hover:text-cyan-300 transition-colors">
                  {preset.title}
                </span>
                {isActive && <Check className="w-4 h-4 text-cyan-400" />}
              </div>

              <p className="text-[11px] text-slate-400 mb-2">{preset.subtitle}</p>

              <span
                className={`inline-block px-2 py-0.5 text-[10px] font-semibold rounded-md border ${preset.badgeColor}`}
              >
                {preset.badge}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
};
