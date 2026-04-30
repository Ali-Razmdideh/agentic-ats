// Hand-typed shapes mirroring ats/storage/models.py.
// Schema source-of-truth lives in Python; these types must match.

export type Role = "admin" | "hiring_manager" | "reviewer";

export type RunStatus =
  | "queued"
  | "running"
  | "completed"
  | "failed"
  | "cancelled"
  | "blocked_by_bias"
  | "budget_exceeded"
  | "ok";

export type DecisionKind = "shortlist" | "reject" | "hold";

export interface Org {
  id: number;
  slug: string;
  name: string;
}

export interface User {
  id: number;
  email: string;
  display_name: string | null;
}

export interface Membership {
  org_id: number;
  user_id: number;
  role: Role;
}

export interface Run {
  id: number;
  org_id: number;
  jd_path: string;
  jd_hash: string;
  jd_blob_key: string | null;
  started_at: string;
  finished_at: string | null;
  status: RunStatus;
  usage: Record<string, unknown> | null;
  created_by_user_id: number | null;
  queued_inputs: QueuedInputs | null;
}

export interface QueuedInputs {
  jd_blob_key: string;
  resume_blob_keys: string[];
  top_n: number;
  skip_optional: boolean;
}

export interface Candidate {
  id: number;
  org_id: number;
  file_hash: string;
  file_blob_key: string;
  source_filename: string | null;
  name: string | null;
  email: string | null;
  phone: string | null;
  parsed: Record<string, unknown> | null;
}

export interface VerifierPayload {
  verified?: string[];
  hallucinated?: string[];
  adjusted_score?: number;
}

export interface ScoreRow {
  candidate_id: number;
  score: number;
  rationale: string | null;
  verified: VerifierPayload | null;
  name: string | null;
  email: string | null;
}

export interface Decision {
  run_id: number;
  candidate_id: number;
  decision: DecisionKind;
  notes: string | null;
  decided_by_user_id: number;
  decided_at: string;
  updated_at: string;
}

export interface CandidateComment {
  id: number;
  run_id: number;
  candidate_id: number;
  author_user_id: number;
  body: string;
  created_at: string;
}

export interface AuditEntry {
  kind: string;
  payload: Record<string, unknown>;
}

export interface AuditEvent {
  id: number;
  kind: string;
  created_at: string;
}
