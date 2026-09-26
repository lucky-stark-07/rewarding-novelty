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
  degraded?: boolean;
  degraded_reason?: string | null;
  guardrails?: Guardrails;
  meta?: ScoreMeta;
}

export interface Guardrails {
  masked: Record<string, number>;
  moderation: "allow" | "flag" | "block" | "unavailable" | "disabled";
  categories: string[];
  moderation_reason?: string;
  warnings: string[];
}

export interface ScoreMeta {
  trace_id: string;
  total_latency_ms: number;
  total_cost: number;
  llm_calls: number;
  cache_hits: number;
  prompt_tokens?: number;
  completion_tokens?: number;
  cached_tokens?: number;
  degraded: boolean;
  degraded_reason?: string | null;
  decisions?: Record<string, number>;
  spans: TraceSpan[];
}

export interface TraceSpan {
  name: string;
  start_ms: number;
  duration_ms: number;
  tokens: number;
  prompt_tokens: number;
  completion_tokens: number;
  cached_tokens: number;
  cost_usd: number;
  llm_calls: number;
  cache_hits: number;
  cache_hit: boolean | null;
  served_model: string | null;
  attrs: Record<string, string | number | boolean | null>;
}

export interface ServiceStats {
  request_count: number;
  latency_ms: { p50: number | null; p95: number | null };
  total_cost_usd: number;
  cache_hit_rate: number | null;
  degraded_count: number;
  llm?: { circuit_breaker?: { state: string }; served_models?: Record<string, number>; budget_usd?: number | null; cost_usd?: number };
  config?: {
    fast_model: string;
    judge_model: string;
    low_threshold: number;
    high_threshold: number;
    entailment_top_k: number;
    max_inflight_requests: number;
    prompt_versions: string[];
  };
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
