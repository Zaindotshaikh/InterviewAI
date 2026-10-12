import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import SetupScreen from "./SetupScreen";
import InterviewScreen from "./InterviewScreen";
import { useTAStore } from "../context/TAStore";
import type { CandidateRecord } from "../lib/candidate";
import type { IntegrityReport } from "../lib/integrity";
import type { InterviewSession, Scorecard } from "../types/session";

type Phase = "setup" | "interview";

export default function CandidateInterviewFlow() {
  const { token = "" } = useParams();
  const {
    getCandidateByToken,
    getRole,
    markInterviewInProgress,
    updateCandidateDetails,
    completeLiveInterview,
  } = useTAStore();
  const candidate = getCandidateByToken(token);
  const role = candidate ? getRole(candidate.roleId) : undefined;
  const navigate = useNavigate();

  const [phase, setPhase] = useState<Phase>("setup");
  const [session, setSession] = useState<InterviewSession | null>(null);

  useEffect(() => {
    if (!candidate) navigate(`/i/${token}`, { replace: true });
  }, [candidate, navigate, token]);

  if (!candidate || !role) return null;

  const prefill: CandidateRecord = {
    id: candidate.id,
    name: candidate.name,
    roleId: candidate.roleId,
    roleAppliedFor: role.title,
    email: candidate.email,
    noticePeriod: candidate.noticePeriod,
    currentCompany: candidate.currentCompany,
    yearsOfExperience: candidate.yearsOfExperience,
    resumeText: candidate.resumeText,
    createdAt: new Date().toISOString(),
  };

  return (
    <>
      {phase === "setup" && (
        <SetupScreen
          prefillCandidate={prefill}
          candidateMode
          onStarted={(s) => {
            // Persist form extras; keep pipeline name as the dashboard invite name
            updateCandidateDetails(candidate.id, {
              name: candidate.name,
              email: s.candidateContext?.email,
              noticePeriod: s.candidateContext?.noticePeriod,
              currentCompany: s.candidateContext?.currentCompany,
              yearsOfExperience: s.candidateContext?.yearsOfExperience,
              resumeText: s.candidateContext?.resumeText,
            });
            markInterviewInProgress(candidate.id);
            setSession({
              ...s,
              candidateName: candidate.name,
              pipelineCandidateId: candidate.id,
            });
            setPhase("interview");
          }}
        />
      )}
      {phase === "interview" && session && (
        <InterviewScreen
          session={session}
          onEnded={async (integrity: IntegrityReport) => {
            let scorecard: Scorecard | null = null;
            try {
              const res = await fetch(`/api/interview/${session.id}/summary`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ integrity }),
              });
              if (res.ok) scorecard = (await res.json()) as Scorecard;
            } catch (err) {
              console.error(err);
            }

            if (scorecard) {
              completeLiveInterview({
                candidateId: candidate.id,
                interviewId: session.id,
                candidateName: candidate.name,
                scorecard: {
                  ...scorecard,
                  integrity: scorecard.integrity ?? integrity,
                },
              });
            }

            navigate(`/i/${token}/thanks`);
          }}
        />
      )}
    </>
  );
}
