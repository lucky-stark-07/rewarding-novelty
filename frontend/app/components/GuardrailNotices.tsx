"use client";

import React from "react";
import { EyeOff, KeyRound, ShieldAlert, ShieldX } from "lucide-react";
import { Guardrails } from "../types";

const LABELS: Record<string, string> = {
  SECRET: "secret / API key",
  EMAIL: "email",
  PHONE: "phone number",
  CREDIT_CARD: "card number",
  IP_ADDRESS: "IP address",
};

function describe(masked: Record<string, number>): string {
  return Object.entries(masked)
    .map(([kind, count]) => `${count} ${LABELS[kind] ?? kind.toLowerCase()}${count > 1 ? "s" : ""}`)
    .join(", ");
}

/** Shown above the score when anything was masked, or when moderation flagged the review or could not run. */
export const MaskingBanner: React.FC<{ guardrails: Guardrails }> = ({ guardrails }) => {
  const maskedTotal = Object.values(guardrails.masked ?? {}).reduce((sum, n) => sum + n, 0);
  const hasSecret = (guardrails.masked?.SECRET ?? 0) > 0;
  const moderationNote = guardrails.moderation === "flag" || guardrails.moderation === "unavailable";
  if (!maskedTotal && !moderationNote) return null;

  return (
    <div
      role="status"
      className={`rounded-xl border p-2.5 text-[11px] space-y-1.5 ${
        hasSecret ? "border-rose-500/40 bg-rose-500/10 text-rose-100" : "border-sky-500/40 bg-sky-500/10 text-sky-100"
      }`}
    >
      {maskedTotal > 0 && (
        <div className="flex items-start gap-2">
          {hasSecret ? <KeyRound className="w-3.5 h-3.5 mt-0.5 shrink-0 text-rose-300" /> : <EyeOff className="w-3.5 h-3.5 mt-0.5 shrink-0 text-sky-300" />}
          <span>
            <strong>Masked before scoring:</strong> {describe(guardrails.masked)}. Placeholders such as <code>[EMAIL_1]</code> were sent to the model instead, and the originals were never stored.
            {hasSecret && <strong className="block mt-0.5 text-rose-200">If the secret is real, rotate it now: it was in text you typed.</strong>}
          </span>
        </div>
      )}
      {moderationNote && (
        <div className="flex items-start gap-2 text-amber-200">
          <ShieldAlert className="w-3.5 h-3.5 mt-0.5 shrink-0 text-amber-300" />
          <span>
            {guardrails.moderation === "flag"
              ? `Flagged by moderation (${guardrails.categories.join(", ") || "content"}): scored, but it will not be added to the corpus.`
              : "Moderation could not run: scored, but it will not be added to the corpus."}
          </span>
        </div>
      )}
    </div>
  );
};

/** Replaces the score card when moderation blocked the review. */
export const BlockedReviewScreen: React.FC<{ guardrails: Guardrails; onEdit?: () => void }> = ({ guardrails, onEdit }) => (
  <div role="alert" className="glass-card rounded-2xl border border-rose-500/50 bg-rose-500/[0.06] p-6 h-full flex flex-col items-center justify-center text-center space-y-3">
    <div className="w-12 h-12 rounded-xl bg-rose-500/15 border border-rose-500/40 text-rose-300 flex items-center justify-center">
      <ShieldX className="w-6 h-6" />
    </div>
    <div>
      <h3 className="text-sm font-bold text-rose-100">Review blocked by content policy</h3>
      <p className="text-[11px] text-rose-200/80 mt-1 max-w-xs">
        This review was not scored and was not stored. Criticism of the product is welcome; threats, hate, harassment and sexual content are not.
      </p>
    </div>
    {guardrails.categories.length > 0 && (
      <div className="flex flex-wrap justify-center gap-1.5">
        {guardrails.categories.map((category) => (
          <span key={category} className="px-2 py-0.5 rounded-full text-[10px] font-semibold uppercase tracking-wide bg-rose-500/15 text-rose-200 border border-rose-500/40">
            {category.replace("_", " ")}
          </span>
        ))}
      </div>
    )}
    {guardrails.moderation_reason && <p className="text-[11px] text-slate-400 italic max-w-xs">{guardrails.moderation_reason}</p>}
    {onEdit && (
      <button type="button" onClick={onEdit} className="text-[11px] font-semibold text-rose-100 underline underline-offset-2 hover:text-white">
        Edit the review and try again
      </button>
    )}
  </div>
);
