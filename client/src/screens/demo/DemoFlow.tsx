import { useEffect, useState } from "react";
import InterviewScreen from "../InterviewScreen";
import type { IntegrityReport } from "../../lib/integrity";
import type { InterviewSession, Scorecard } from "../../types/session";
import DemoComplete from "./DemoComplete";
import DemoDetailsStep from "./DemoDetailsStep";
import DemoLanding from "./DemoLanding";
import DemoRoleStep from "./DemoRoleStep";
import type { DemoCatalog, DemoProspect, DemoRole } from "./types";

type Phase = "landing" | "details" | "role" | "interview" | "complete";

export default function DemoFlow() {
  const [catalog, setCatalog] = useState<DemoCatalog | null>(null);
  const [catalogError, setCatalogError] = useState<string | null>(null);
  const [phase, setPhase] = useState<Phase>("landing");
  const [prospect, setProspect] = useState<DemoProspect | null>(null);
  const [leadId, setLeadId] = useState<string | null>(null);
  const [leadSaving, setLeadSaving] = useState(false);
  const [leadError, setLeadError] = useState<string | null>(null);
  const [session, setSession] = useState<InterviewSession | null>(null);
  const [scorecard, setScorecard] = useState<Scorecard | null>(null);

  useEffect(() => {
    void fetch("/api/demo/catalog")
      .then((r) => {
        if (!r.ok) throw new Error("Could not load demo catalog");
        return r.json();
      })
      .then((data: DemoCatalog) => setCatalog(data))
      .catch(() => setCatalogError("Could not load the live demo. Is the server running?"));
  }, []);

  const industry = catalog?.industries.find((item) => item.id === prospect?.industry) ?? null;
  const interviewerName = catalog?.interviewer.name;
  const interviewerTitle = catalog?.interviewer.title;

  async function saveLead(next: DemoProspect) {
    setLeadError(null);
    setProspect(next);
    if (leadId) {
      setPhase("role");
      return;
    }
    setLeadSaving(true);
    try {
      const res = await fetch("/api/demo/leads", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(next),
      });
      if (!res.ok) throw new Error(await res.text());
      const saved = (await res.json()) as { id: string };
      setLeadId(saved.id);
      setPhase("role");
    } catch (err) {
      setLeadError(err instanceof Error ? err.message : "Could not save your details");
    } finally {
      setLeadSaving(false);
    }
  }

  async function attachInterview(nextSession: InterviewSession, role: DemoRole) {
    setSession(nextSession);
    setPhase("interview");
    if (!leadId) return;
    try {
      await fetch(`/api/demo/leads/${leadId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          roleId: role.id,
          roleTitle: role.title,
          interviewId: nextSession.id,
        }),
      });
    } catch {
      // Non-fatal; interview can proceed
    }
  }

  if (catalogError) {
    return (
      <div className="grid min-h-screen place-items-center px-6">
        <p className="max-w-md text-center text-[var(--color-muted)]">{catalogError}</p>
      </div>
    );
  }

  if (!catalog) {
    return (
      <div className="grid min-h-screen place-items-center px-6">
        <p className="text-[var(--color-muted)]">Loading live demo…</p>
      </div>
    );
  }

  return (
    <>
      {phase === "landing" && (
        <DemoLanding
          interviewerName={interviewerName}
          interviewerTitle={interviewerTitle}
          onStart={() => setPhase("details")}
        />
      )}

      {phase === "details" && (
        <DemoDetailsStep
          industries={catalog.industries}
          initial={prospect ?? undefined}
          submitting={leadSaving}
          error={leadError}
          onBack={() => setPhase("landing")}
          onContinue={(next) => void saveLead(next)}
        />
      )}

      {phase === "role" && prospect && industry && (
        <DemoRoleStep
          industry={industry}
          prospect={prospect}
          interviewerName={interviewerName}
          onBack={() => setPhase("details")}
          onStarted={(nextSession, role) => void attachInterview(nextSession, role)}
        />
      )}

      {phase === "interview" && session && (
        <InterviewScreen
          session={session}
          onEnded={async (integrity: IntegrityReport) => {
            let nextCard: Scorecard | null = null;
            try {
              const res = await fetch(`/api/interview/${session.id}/summary`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ integrity }),
              });
              if (res.ok) nextCard = (await res.json()) as Scorecard;
            } catch (err) {
              console.error(err);
            }
            setScorecard(nextCard);
            setPhase("complete");
          }}
        />
      )}

      {phase === "complete" && session && (
        <DemoComplete
          session={session}
          scorecard={scorecard}
          interviewerName={interviewerName}
          onTryAnotherRole={() => {
            setSession(null);
            setScorecard(null);
            setPhase("role");
          }}
          onStartOver={() => {
            setSession(null);
            setScorecard(null);
            setProspect(null);
            setLeadId(null);
            setPhase("landing");
          }}
        />
      )}
    </>
  );
}
