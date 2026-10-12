import { Link, useNavigate, useParams } from "react-router-dom";
import SummaryScreen from "./SummaryScreen";
import { useTAStore } from "../context/TAStore";
import type { InterviewSession, Scorecard } from "../types/session";

export default function TAScorecardScreen() {
  const { candidateId = "" } = useParams();
  const { getCandidate, getRole, updateCandidateStatus } = useTAStore();
  const candidate = getCandidate(candidateId);
  const role = candidate ? getRole(candidate.roleId) : undefined;
  const navigate = useNavigate();

  if (!candidate || !candidate.scorecard || !role) {
    return (
      <div className="mx-auto max-w-2xl px-6 py-12">
        <p className="text-[var(--color-muted)]">Scorecard not found.</p>
        <Link to="/dashboard" className="mt-4 inline-block text-[var(--color-accent)]">
          Back to dashboard
        </Link>
      </div>
    );
  }

  const session: InterviewSession = {
    id: candidate.interviewId ?? candidate.id,
    candidateName: candidate.name,
    roleTitle: role.title,
    questions: [],
    instructions: "",
  };

  const scorecard = candidate.scorecard as Scorecard;

  return (
    <div>
      <div className="mx-auto max-w-2xl px-6 pt-8">
        <button
          type="button"
          onClick={() => navigate(`/roles/${candidate.roleId}`)}
          className="text-sm text-[var(--color-muted)] hover:text-[var(--color-fg)]"
        >
          ← Back to pipeline
        </button>
      </div>
      <SummaryScreen
        session={session}
        scorecard={scorecard}
        onRestart={() => navigate(`/roles/${candidate.roleId}`)}
        hideActions
        showIntegrity
      />
      <div className="mx-auto flex max-w-2xl flex-wrap gap-3 px-6 pb-12">
        <button
          type="button"
          onClick={() => {
            updateCandidateStatus(candidate.id, "Shortlisted");
            navigate(`/roles/${candidate.roleId}`);
          }}
          className="rounded-xl bg-[var(--color-accent)] px-4 py-2.5 text-sm font-semibold text-[var(--color-on-accent)]"
        >
          Shortlist / Move to Next Round
        </button>
        <button
          type="button"
          onClick={() => {
            updateCandidateStatus(candidate.id, "Rejected");
            navigate(`/roles/${candidate.roleId}`);
          }}
          className="rounded-xl border border-[var(--color-danger)]/40 px-4 py-2.5 text-sm text-[var(--color-danger)]"
        >
          Reject
        </button>
      </div>
    </div>
  );
}
