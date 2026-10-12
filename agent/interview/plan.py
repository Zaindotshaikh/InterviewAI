"""Interview plan types and answer classification."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


StepKind = Literal[
    "greeting",
    "intro",
    "intro_followup",
    "resume_question",
    "resume_followup",
    "closing",
]

TurnVerdict = Literal["noise", "weak", "substantive"]


NOISE_MARKERS = {
    "",
    "((noise))",
    "(noise)",
    "...",
    "…",
}

WEAK_TOKENS = {
    "um",
    "uh",
    "hmm",
    "okay",
    "ok",
    "yeah",
    "yes",
    "no",
    "right",
    "hello",
    "hi",
    "haan",
    "ha",
    "nahi",
    "achha",
}


@dataclass
class PlanStep:
    id: str
    kind: StepKind
    prompt: str
    max_follow_ups: int = 0


@dataclass
class InterviewPlan:
    interview_id: str
    language: str
    stt_mode: str
    target_minutes: int
    company_name: str
    interviewer_name: str
    role_title: str
    criteria: list[str]
    keyterms: list[str]
    glossary_hints: list[str]
    steps: list[PlanStep]
    system_prompt: str
    candidate_name: str = ""
    resume_text: str = ""
    # Interview blueprint (screening fields, clinical rubric, tiers); parsed by interview.blueprint.Blueprint.
    blueprint: dict[str, Any] = field(default_factory=dict)
    # Last turns of an interrupted call, so a restarted agent can rebuild the conversation.
    recent_transcript: list[dict[str, str]] = field(default_factory=list)

    @classmethod
    def from_api(cls, payload: dict[str, Any]) -> InterviewPlan:
        plan = payload["plan"]
        ctx = plan.get("candidateContext") or {}
        steps = [
            PlanStep(
                id=s["id"],
                kind=s["kind"],
                prompt=s.get("prompt") or "",
                max_follow_ups=int(s.get("maxFollowUps") or 0),
            )
            for s in plan.get("steps") or []
        ]
        return cls(
            interview_id=plan["interviewId"],
            language=plan["language"],
            stt_mode=plan.get("sttMode") or "codemix",
            target_minutes=int(plan.get("targetMinutes") or 8),
            company_name=plan.get("companyName") or "",
            interviewer_name=plan.get("interviewerName") or "Aven",
            role_title=plan.get("roleTitle") or "",
            criteria=list(plan.get("criteria") or []),
            keyterms=list(plan.get("keyterms") or []),
            glossary_hints=list(plan.get("glossaryHints") or []),
            steps=steps,
            system_prompt=plan.get("systemPrompt") or "",
            candidate_name=ctx.get("name") or "",
            resume_text=ctx.get("resumeText") or "",
            blueprint=plan.get("blueprint") or {},
            recent_transcript=[
                {"role": t["role"], "text": t["text"]}
                for t in payload.get("recentTranscript") or []
                if t.get("role") in ("user", "assistant") and t.get("text")
            ],
        )


@dataclass
class ControllerState:
    step_index: int = 0
    follow_ups_used: int = 0
    consecutive_noise: int = 0
    consecutive_weak: int = 0
    language: str = "en-IN"
    completed: bool = False
    turn_index: int = 0
    events: list[dict[str, Any]] = field(default_factory=list)
    # Serialised interview.flow_state.FlowState; this is what lets a dropped call resume without losing context.
    flow: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_api(cls, payload: dict[str, Any]) -> ControllerState:
        c = payload.get("controller") or {}
        return cls(
            step_index=int(c.get("stepIndex") or 0),
            follow_ups_used=int(c.get("followUpsUsed") or 0),
            consecutive_noise=int(c.get("consecutiveNoise") or 0),
            consecutive_weak=int(c.get("consecutiveWeak") or 0),
            language=c.get("language") or "en-IN",
            completed=bool(c.get("completed")),
            flow=dict(c.get("flow") or {}),
        )

    def to_api_patch(self) -> dict[str, Any]:
        return {
            "stepIndex": self.step_index,
            "followUpsUsed": self.follow_ups_used,
            "consecutiveNoise": self.consecutive_noise,
            "consecutiveWeak": self.consecutive_weak,
            "language": self.language,
            "completed": self.completed,
            "flow": self.flow,
        }


def classify_answer(text: str | None) -> TurnVerdict:
    raw = (text or "").strip()
    if not raw or raw.lower() in NOISE_MARKERS:
        return "noise"
    # Strip punctuation for weak-token check
    tokens = [t.strip(".,!?;:\"'").lower() for t in raw.split()]
    tokens = [t for t in tokens if t]
    if not tokens:
        return "noise"
    if len(tokens) <= 2 and all(t in WEAK_TOKENS for t in tokens):
        return "weak"
    # Very short replies without substance
    if len(raw) < 12 and len(tokens) <= 2:
        return "weak"
    return "substantive"
