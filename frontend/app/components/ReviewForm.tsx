"use client";

import React, { FormEvent, useState } from "react";
import { PresetsBar, PRESETS } from "./PresetsBar";
import { PresetReview } from "../types";
import { Send, ThumbsUp, ThumbsDown, Target, Loader2, AlertCircle, RotateCcw } from "lucide-react";

interface ReviewFormProps {
  onSubmit: (form: { what_you_like: string; what_you_dislike: string; problem_solved: string }, addToCorpus: boolean) => void;
  loading: boolean;
  error: string;
}

export const ReviewForm: React.FC<ReviewFormProps> = ({ onSubmit, loading, error }) => {
  const [form, setForm] = useState({
    what_you_like: PRESETS[0].what_you_like,
    what_you_dislike: PRESETS[0].what_you_dislike,
    problem_solved: PRESETS[0].problem_solved,
  });
  const [activePresetId, setActivePresetId] = useState<string>(PRESETS[0].id);
  const [addToCorpus, setAddToCorpus] = useState(false);

  const handlePresetSelect = (preset: PresetReview) => {
    setForm({
      what_you_like: preset.what_you_like,
      what_you_dislike: preset.what_you_dislike,
      problem_solved: preset.problem_solved,
    });
    setActivePresetId(preset.id);
  };

  const handleClear = () => {
    setForm({ what_you_like: "", what_you_dislike: "", problem_solved: "" });
    setActivePresetId("");
    setAddToCorpus(false);
  };

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    onSubmit(form, addToCorpus);
  };

  const fields = [
    {
      key: "what_you_like" as const,
      label: "What You Like",
      placeholder: "Describe a positive capability, specific benefit, or workflow win you noticed...",
      icon: ThumbsUp,
      color: "text-emerald-400",
      accent: "focus:border-emerald-500/50 focus:ring-emerald-500/20",
    },
    {
      key: "what_you_dislike" as const,
      label: "What You Dislike",
      placeholder: "Describe a limitation, missing capability, frustration, or improvement request...",
      icon: ThumbsDown,
      color: "text-amber-400",
      accent: "focus:border-amber-500/50 focus:ring-amber-500/20",
    },
    {
      key: "problem_solved" as const,
      label: "Problem Solved",
      placeholder: "Describe the product-team workflow, coordination challenge, or need this product addresses...",
      icon: Target,
      color: "text-cyan-400",
      accent: "focus:border-cyan-500/50 focus:ring-cyan-500/20",
    },
  ];

  return (
    <div className="w-full glass-card rounded-2xl p-5 border border-slate-800 shadow-2xl space-y-4 relative overflow-hidden h-full flex flex-col justify-between">
      {/* Top Header */}
      <div className="flex items-center justify-between border-b border-slate-800 pb-3">
        <div>
          <h2 className="text-base font-bold text-slate-100 flex items-center gap-2">
            <span>Submit a Product Review</span>
          </h2>
          <p className="text-[11px] text-slate-400 mt-0.5">
            Evaluates 3 review dimensions for novel insight relative to the baseline corpus.
          </p>
        </div>

        <button
          type="button"
          onClick={handleClear}
          className="flex items-center gap-1 px-2.5 py-1 text-[11px] font-medium text-slate-400 hover:text-slate-200 bg-slate-900 hover:bg-slate-800 rounded-lg border border-slate-800 transition-colors"
        >
          <RotateCcw className="w-3 h-3" />
          <span>Clear</span>
        </button>
      </div>

      {/* Preset Review Selector */}
      <PresetsBar onSelectPreset={handlePresetSelect} activePresetId={activePresetId} />

      {/* Form Fields */}
      <form onSubmit={handleSubmit} className="space-y-3.5 flex-1 flex flex-col justify-between">
        <div className="space-y-3">
          {fields.map((field) => {
            const Icon = field.icon;
            const value = form[field.key];
            const wordCount = value.trim() ? value.trim().split(/\s+/).length : 0;

            return (
              <div key={field.key} className="space-y-1">
                <div className="flex items-center justify-between">
                  <label className="text-[11px] font-bold text-slate-200 uppercase tracking-wide flex items-center gap-1.5">
                    <Icon className={`w-3.5 h-3.5 ${field.color}`} />
                    <span>{field.label}</span>
                  </label>
                  <span className="text-[10px] font-mono text-slate-500">
                    {wordCount} {wordCount === 1 ? "word" : "words"} · {value.length} chars
                  </span>
                </div>

                <textarea
                  required
                  rows={2}
                  value={value}
                  onChange={(e) => {
                    setForm({ ...form, [field.key]: e.target.value });
                    setActivePresetId("");
                  }}
                  placeholder={field.placeholder}
                  className={`w-full px-3.5 py-2.5 rounded-xl bg-slate-950/80 border border-slate-800 text-xs text-slate-100 placeholder-slate-600 focus:outline-none focus:ring-2 transition-all duration-200 resize-y min-h-[60px] ${field.accent}`}
                />
              </div>
            );
          })}
        </div>

        {/* Error Callout */}
        {error && (
          <div className="p-3 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs flex items-start gap-2">
            <AlertCircle className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
            <div>
              <strong className="font-semibold block text-rose-200">Scoring Failed</strong>
              <p className="mt-0.5 text-[11px]">{error}</p>
            </div>
          </div>
        )}

        <div className="space-y-3 pt-1">
          <label className="flex items-center gap-2.5 rounded-xl border border-slate-800 bg-slate-950/50 p-2.5 text-[11px] text-slate-300 cursor-pointer">
            <input
              type="checkbox"
              checked={addToCorpus}
              onChange={(event) => setAddToCorpus(event.target.checked)}
              className="accent-indigo-500 rounded"
            />
            <span>Opt-in: Add review to baseline corpus if score meets threshold (&ge; 0.60).</span>
          </label>

          {/* Action Button */}
          <button
            type="submit"
            disabled={loading}
            className="w-full py-3 px-5 rounded-xl font-bold text-xs tracking-wide text-white bg-gradient-to-r from-indigo-600 via-purple-600 to-cyan-600 hover:from-indigo-500 hover:via-purple-500 hover:to-cyan-500 disabled:opacity-50 disabled:cursor-not-allowed transition-all duration-300 shadow-lg shadow-indigo-600/20 flex items-center justify-center gap-2 relative overflow-hidden group"
          >
            {loading ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                <span>Extracting Atomic Claims & Vector Embedding...</span>
              </>
            ) : (
              <>
                <Send className="w-3.5 h-3.5 group-hover:translate-x-1 transition-transform" />
                <span>Evaluate Review Novelty & Relevance</span>
              </>
            )}
          </button>
        </div>
      </form>
    </div>
  );
};
