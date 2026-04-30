import Link from "next/link";
import { notFound } from "next/navigation";
import { requireUserAndOrg } from "@/lib/auth";
import {
  getCandidate,
  getDecision,
  getRun,
  listAuditsForRun,
  listCommentsForCandidate,
  listScoresForRun,
} from "@/lib/repo";
import DecisionPanel from "@/components/DecisionPanel";
import CommentThread from "@/components/CommentThread";
import ResumeDownload from "@/components/ResumeDownload";
import CandidateSummary from "@/components/CandidateSummary";
import {
  EnrichmentView,
  InterviewQuestionsView,
  ParsedResumeView,
  RedFlagsView,
} from "@/components/CandidateViews";

export const dynamic = "force-dynamic";

export default async function CandidateDetailPage({
  params,
}: {
  params: Promise<{ id: string; cid: string }>;
}) {
  const { id, cid } = await params;
  const runId = Number(id);
  const candId = Number(cid);
  if (!Number.isFinite(runId) || !Number.isFinite(candId)) notFound();

  const { org, user } = await requireUserAndOrg();
  const [run, candidate] = await Promise.all([
    getRun(org.id, runId),
    getCandidate(org.id, candId),
  ]);
  if (!run || !candidate) notFound();

  const [scores, audits, decision, comments] = await Promise.all([
    listScoresForRun(org.id, runId),
    listAuditsForRun(org.id, runId),
    getDecision(org.id, runId, candId),
    listCommentsForCandidate(org.id, runId, candId),
  ]);
  const score = scores.find((s) => s.candidate_id === candId);
  const interviewQs = audits.find(
    (a) => a.kind === `interview_qs:${candId}`,
  )?.payload;
  const redFlags = audits.find(
    (a) => a.kind === `red_flags:${candId}`,
  )?.payload;
  const enrichment = audits.find(
    (a) => a.kind === `enricher:${candId}`,
  )?.payload;

  return (
    <div className="space-y-8">
      <div>
        <Link
          href={`/runs/${runId}`}
          className="text-sm text-slate-500 hover:text-slate-900"
        >
          ← Back to run #{runId}
        </Link>
        <div className="mt-2 flex items-start justify-between gap-6">
          <div>
            <h1 className="text-2xl font-semibold">
              {candidate.name || `Candidate #${candidate.id}`}
            </h1>
            <p className="text-sm text-slate-500">
              {candidate.email || "—"} · {candidate.phone || "—"}
            </p>
          </div>
          <div className="flex flex-col items-end gap-2">
            <ResumeDownload blobKey={candidate.file_blob_key} />
          </div>
        </div>
      </div>

      <CandidateSummary
        score={score}
        redFlagsPayload={redFlags}
        enrichmentPayload={enrichment}
        decision={decision}
      />

      <DecisionPanel
        runId={runId}
        candidateId={candId}
        currentDecision={decision?.decision ?? null}
        currentNotes={decision?.notes ?? ""}
      />

      {redFlags != null && (
        <Section title="Red flags">
          <RedFlagsView payload={redFlags} />
        </Section>
      )}

      {interviewQs != null && (
        <Section title="Interview questions">
          <InterviewQuestionsView payload={interviewQs} />
        </Section>
      )}

      {enrichment != null && (
        <Section title="GitHub enrichment">
          <EnrichmentView payload={enrichment} />
        </Section>
      )}

      <Section title="Parsed resume">
        <ParsedResumeView parsed={candidate.parsed} />
      </Section>

      <Section title="Comments">
        <CommentThread
          runId={runId}
          candidateId={candId}
          comments={comments}
          currentUserEmail={user.email}
        />
      </Section>
    </div>
  );
}

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-xl border border-slate-200 bg-white p-4">
      <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500">
        {title}
      </h2>
      {children}
    </section>
  );
}
