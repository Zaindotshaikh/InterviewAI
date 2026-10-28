"""Persistable interview state. Everything here is JSON-serialisable so a dropped call can resume exactly."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from typing import Any

STAGES = ("opening", "screening", "clinical", "closing", "ended")


@dataclass
class Slot:
    value: Any = None
    status: str = "empty"  # empty | captured | confirmed | unknown
    attempts: int = 0
    evidence: str = ""
    confidence: float = 0.0
    turn: int = 0


@dataclass
class CareState:
    stance: str = "unknown"  # unknown | comfortable | willing_with_training | hesitant | refuses
    persuasions: int = 0
    asked: int = 0
    reason: str = ""
    evidence: str = ""


@dataclass
class AreaProgress:
    area_id: str = ""
    level: int = 1
    probes: int = 0
    challenges: int = 0
    clarifications: int = 0
    dont_knows: int = 0
    deepened: int = 0
    status: str = "pending"  # pending | active | done
    outcome: str = "unknown"  # strong | adequate | weak | unsafe | unknown
    covered: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    red_flags: list[str] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class FlowState:
    stage: str = "opening"
    language: str = "en-IN"
    turns: int = 0
    elapsed_s: float = 0.0
    screening_started_s: float = 0.0
    clinical_started_s: float = 0.0
    slots: dict[str, Slot] = field(default_factory=dict)
    care: dict[str, CareState] = field(default_factory=dict)
    gate_failed: str | None = None
    care_intro_done: bool = False
    experience_dive_done: bool = False  # post-care experience probe block finished
    experience_probe_queue: list[dict[str, Any]] = field(default_factory=list)
    experience_probe_index: int = 0
    experience_probe_deepens: int = 0  # deepens used on the current queue item
    resume_crosscheck_done: bool = False  # one check when spoken experience conflicts with the resume
    experience_level: str = "unknown"  # fresher | junior | experienced | unknown
    areas: dict[str, AreaProgress] = field(default_factory=dict)
    area_order: list[str] = field(default_factory=list)
    current_area: str | None = None
    claims: list[str] = field(default_factory=list)
    contradictions: list[dict[str, Any]] = field(default_factory=list)
    contradiction_probes: int = 0
    pending_probe: str | None = None
    focus: dict[str, Any] = field(default_factory=dict)  # what the last question was about
    last_question: str = ""
    # behaviour counters, kept for the scorecard and to bound repeated handling
    unclear_streak: int = 0
    unclear_total: int = 0
    dont_know_total: int = 0
    repeat_requests: int = 0
    nervous_events: int = 0
    stop_requests: int = 0
    silence_level: int = 0
    interruptions: int = 0
    outcome: str | None = None  # completed | screened_out | time | withdrew | incomplete_silence | ...

    def slot(self, field_id: str) -> Slot:
        return self.slots.setdefault(field_id, Slot())

    def care_state(self, item_id: str) -> CareState:
        return self.care.setdefault(item_id, CareState())

    def area_progress(self, area_id: str) -> AreaProgress:
        return self.areas.setdefault(area_id, AreaProgress(area_id=area_id))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> FlowState:
        if not data:
            return cls()
        known = {f.name for f in fields(cls)}
        kwargs = {k: v for k, v in data.items() if k in known}
        state = cls(**{k: v for k, v in kwargs.items() if k not in ("slots", "care", "areas")})
        state.slots = {k: Slot(**_only(Slot, v)) for k, v in (data.get("slots") or {}).items()}
        state.care = {k: CareState(**_only(CareState, v)) for k, v in (data.get("care") or {}).items()}
        state.areas = {k: AreaProgress(**_only(AreaProgress, v)) for k, v in (data.get("areas") or {}).items()}
        return state


def _only(cls: type, data: dict[str, Any]) -> dict[str, Any]:
    names = {f.name for f in fields(cls)}
    return {k: v for k, v in (data or {}).items() if k in names}
