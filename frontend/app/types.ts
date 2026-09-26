export type FieldName = "what_you_like" | "what_you_dislike" | "problem_solved";

export interface Claim {
  id?: string;
  field?: FieldName;
  text: string;
  source_submission_id?: string | null;
}

export interface ClaimAssessment {
  claim: {
    id?: string;
    field?: FieldName;
    text: string;
  };
  novelty_status: "novel" | "partial" | "covered" | "pending" | string;
  novelty_score: number;
  relevance_score: number;
  relevance_reason?: string;
  nearest_claim?: {
    id?: string;
    text: string;
    field?: FieldName;
  } | null;
  nearest_similarity?: number | null;
  neighbors?: { claim: Claim; similarity: number }[];
  entailment_judged?: boolean;
  entailment_reason?: string | null;
}

export interface FieldScore {
  field: FieldName;
  score: number;
  novelty_fraction: number;
  relevance_gate: number;
  claims: ClaimAssessment[];
}

export interface ScoreResult {
  submission_score: number;
  field_scores: FieldScore[];
  scoring_mode: string;
  message: string;
  reason?: string | null;
  add_to_corpus_requested: boolean;
  added_to_corpus: boolean;
  meta?: {
    request_id?: string;
    estimated_cost_usd?: number;
    llm_calls?: number;
    llm_cache_hits?: number;
    prompt_tokens?: number;
    completion_tokens?: number;
    stage_latency_seconds?: Record<string, number>;
    decisions?: Record<string, number>;
    trace?: TraceSpan[];
  };
}

export interface TraceSpan {
  name: string;
  start_ms: number;
  duration_ms: number;
  attrs: Record<string, string | number | boolean | null>;
}

export interface CorpusEntry {
  id: string;
  submission: {
    what_you_like: string;
    what_you_dislike: string;
    problem_solved: string;
  };
  claims: {
    id: string;
    field: FieldName;
    text: string;
  }[];
}

export interface PresetReview {
  id: string;
  title: string;
  subtitle: string;
  badge: string;
  badgeColor: string;
  what_you_like: string;
  what_you_dislike: string;
  problem_solved: string;
}
