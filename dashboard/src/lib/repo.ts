// Tenant-scoped query helpers. Mirrors ats/storage/repositories/.
// Every function takes ``orgId`` and includes it in the WHERE clause.

import { pool, withTx } from "@/lib/db";
import type {
  AuditEntry,
  AuditEvent,
  Candidate,
  CandidateComment,
  Decision,
  DecisionKind,
  Run,
  RunStatus,
  ScoreRow,
} from "@/lib/types";

// ----- Runs ---------------------------------------------------------------

export async function listRuns(orgId: number, limit = 50): Promise<Run[]> {
  const res = await pool.query<Run>(
    `SELECT id, org_id, jd_path, jd_hash, jd_blob_key,
            started_at, finished_at, status, usage,
            created_by_user_id, queued_inputs
       FROM runs
      WHERE org_id = $1
      ORDER BY id DESC
      LIMIT $2`,
    [orgId, limit],
  );
  return res.rows;
}

export async function getRun(orgId: number, runId: number): Promise<Run | null> {
  const res = await pool.query<Run>(
    `SELECT id, org_id, jd_path, jd_hash, jd_blob_key,
            started_at, finished_at, status, usage,
            created_by_user_id, queued_inputs
       FROM runs
      WHERE org_id = $1 AND id = $2`,
    [orgId, runId],
  );
  return res.rows[0] ?? null;
}

export async function createQueuedRun(
  orgId: number,
  userId: number,
  jdPath: string,
  jdHash: string,
  jdBlobKey: string,
  resumeBlobKeys: string[],
  topN: number,
  skipOptional: boolean,
): Promise<number> {
  const res = await pool.query<{ id: number }>(
    `INSERT INTO runs
       (org_id, jd_path, jd_hash, jd_blob_key, status,
        created_by_user_id, queued_inputs)
     VALUES ($1, $2, $3, $4, 'queued', $5, $6)
     RETURNING id`,
    [
      orgId,
      jdPath,
      jdHash,
      jdBlobKey,
      userId,
      {
        jd_blob_key: jdBlobKey,
        resume_blob_keys: resumeBlobKeys,
        top_n: topN,
        skip_optional: skipOptional,
      },
    ],
  );
  return res.rows[0]!.id;
}

// ----- Candidates ---------------------------------------------------------

export async function getCandidate(
  orgId: number,
  candidateId: number,
): Promise<Candidate | null> {
  const res = await pool.query<Candidate>(
    `SELECT id, org_id, file_hash, file_blob_key, source_filename,
            name, email, phone, parsed
       FROM candidates
      WHERE org_id = $1 AND id = $2`,
    [orgId, candidateId],
  );
  return res.rows[0] ?? null;
}

// ----- Scores -------------------------------------------------------------

export async function listScoresForRun(
  orgId: number,
  runId: number,
): Promise<ScoreRow[]> {
  const res = await pool.query<ScoreRow>(
    `SELECT s.candidate_id, s.score, s.rationale, s.verified,
            c.name, c.email
       FROM scores s
       JOIN candidates c ON c.id = s.candidate_id AND c.org_id = s.org_id
      WHERE s.org_id = $1 AND s.run_id = $2
      ORDER BY s.score DESC`,
    [orgId, runId],
  );
  return res.rows;
}

// ----- Audits -------------------------------------------------------------

export async function listAuditsForRun(
  orgId: number,
  runId: number,
): Promise<AuditEntry[]> {
  const res = await pool.query<AuditEntry>(
    `SELECT kind, payload FROM audits
      WHERE org_id = $1 AND run_id = $2
      ORDER BY id`,
    [orgId, runId],
  );
  return res.rows;
}

/** Lightweight audit event list for the pipeline timeline. */
export async function listAuditEventsForRun(
  orgId: number,
  runId: number,
  limit = 50,
): Promise<AuditEvent[]> {
  const res = await pool.query<AuditEvent>(
    `SELECT id, kind, created_at FROM audits
      WHERE org_id = $1 AND run_id = $2
      ORDER BY id DESC
      LIMIT $3`,
    [orgId, runId, limit],
  );
  return res.rows;
}

// ----- Decisions ----------------------------------------------------------

/** Throws CROSS_TENANT if the (run_id, candidate_id) pair isn't valid for
 *  org_id. "Valid" = the candidate was actually screened in this run AND
 *  both rows belong to the org.
 *
 *  The org-membership check alone is not enough: a reviewer in Org A could
 *  otherwise post a comment on Run #X about Candidate #Y where Y was never
 *  screened in X (just happens to live in the same org). The composite FKs
 *  on `decisions` / `candidate_comments` only enforce per-org membership of
 *  each side independently, not that the pair appears together in a run.
 *
 *  We use `scores` as the source of truth for "candidate participated in
 *  run": the orchestrator writes one scores row per candidate per run after
 *  the matcher step, so any candidate the reviewer can legitimately act on
 *  has a row there. */
async function assertRunAndCandidateInOrg(
  orgId: number,
  runId: number,
  candidateId: number,
): Promise<void> {
  const r = await pool.query<{ ok: boolean }>(
    `SELECT EXISTS (
        SELECT 1 FROM scores
         WHERE org_id = $1 AND run_id = $2 AND candidate_id = $3
     ) AS ok`,
    [orgId, runId, candidateId],
  );
  if (!r.rows[0]?.ok) {
    throw new Error("CROSS_TENANT");
  }
}

export async function upsertDecision(
  orgId: number,
  runId: number,
  candidateId: number,
  decision: DecisionKind,
  notes: string | null,
  decidedByUserId: number,
): Promise<void> {
  // Hard tenant guard: refuse writes for run/candidate IDs that don't
  // belong to ``orgId``. The composite FK to runs/candidates would
  // ultimately reject them too, but a row could still be inserted with
  // ``org_id = orgId`` for an attacker-supplied (run_id, candidate_id)
  // pair from another tenant if the FK weren't composite — defence in
  // depth.
  await assertRunAndCandidateInOrg(orgId, runId, candidateId);
  await pool.query(
    `INSERT INTO decisions
       (run_id, candidate_id, org_id, decision, notes, decided_by_user_id)
     VALUES ($1, $2, $3, $4, $5, $6)
     ON CONFLICT (run_id, candidate_id) DO UPDATE
       SET decision = EXCLUDED.decision,
           notes = EXCLUDED.notes,
           decided_by_user_id = EXCLUDED.decided_by_user_id,
           updated_at = now()
     WHERE decisions.org_id = EXCLUDED.org_id`,
    [runId, candidateId, orgId, decision, notes, decidedByUserId],
  );
}

export async function getDecision(
  orgId: number,
  runId: number,
  candidateId: number,
): Promise<Decision | null> {
  const res = await pool.query<Decision>(
    `SELECT run_id, candidate_id, decision, notes,
            decided_by_user_id, decided_at, updated_at
       FROM decisions
      WHERE org_id = $1 AND run_id = $2 AND candidate_id = $3`,
    [orgId, runId, candidateId],
  );
  return res.rows[0] ?? null;
}

export async function listDecisionsForRun(
  orgId: number,
  runId: number,
): Promise<Decision[]> {
  const res = await pool.query<Decision>(
    `SELECT run_id, candidate_id, decision, notes,
            decided_by_user_id, decided_at, updated_at
       FROM decisions
      WHERE org_id = $1 AND run_id = $2`,
    [orgId, runId],
  );
  return res.rows;
}

// ----- Comments -----------------------------------------------------------

export async function addComment(
  orgId: number,
  runId: number,
  candidateId: number,
  authorUserId: number,
  body: string,
): Promise<number> {
  await assertRunAndCandidateInOrg(orgId, runId, candidateId);
  const res = await pool.query<{ id: number }>(
    `INSERT INTO candidate_comments
       (org_id, run_id, candidate_id, author_user_id, body)
     VALUES ($1, $2, $3, $4, $5)
     RETURNING id`,
    [orgId, runId, candidateId, authorUserId, body],
  );
  return res.rows[0]!.id;
}

export async function listCommentsForCandidate(
  orgId: number,
  runId: number,
  candidateId: number,
): Promise<Array<CandidateComment & { author_email: string | null }>> {
  const res = await pool.query(
    `SELECT cc.id, cc.run_id, cc.candidate_id, cc.author_user_id, cc.body,
            cc.created_at, u.email AS author_email
       FROM candidate_comments cc
       LEFT JOIN users u ON u.id = cc.author_user_id
      WHERE cc.org_id = $1 AND cc.run_id = $2 AND cc.candidate_id = $3
      ORDER BY cc.created_at`,
    [orgId, runId, candidateId],
  );
  return res.rows;
}

export async function setRunFinishedStatus(
  orgId: number,
  runId: number,
  status: RunStatus,
): Promise<void> {
  await pool.query(
    `UPDATE runs SET status = $3, finished_at = now()
      WHERE org_id = $1 AND id = $2`,
    [orgId, runId, status],
  );
}

export { withTx };
