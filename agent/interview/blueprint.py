"""Typed interview blueprint: what to learn, what to assess, and how to classify.

The blueprint is data, not code. The server owns the canonical JSON (server/v2/lib/blueprints/*.json) and ships it
inside the interview plan, so recruiters can change questions, rubrics, limits and tiers without touching the agent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Limits:
    screening_max_minutes: float = 7
    clinical_target_minutes: float = 10
    hard_cap_minutes: float = 25
    clinical_areas_target: int = 4
    max_probes_per_area: int = 2
    max_challenges_per_area: int = 1
    max_clarifications_per_area: int = 1
    max_persuasions: int = 2
    max_contradiction_probes: int = 2
    max_unclear_streak: int = 3
    max_dont_know_total: int = 4
    max_field_attempts: int = 3
    # Post-care experience block (after diaper gate clears).
    experience_resume_tied: int = 3
    experience_bank_target: int = 4
    experience_fresher_target: int = 4
    max_deepens_per_experience_probe: int = 1


@dataclass(frozen=True)
class ExperienceProbeSpec:
    id: str
    ask: str
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class FieldSpec:
    id: str
    label: str
    kind: str  # text | phone | year | height | weight | years
    group: str
    ask: str
    confirm: bool = False


@dataclass(frozen=True)
class CareItem:
    id: str
    label: str
    ask: str
    gate: bool = False
    persuasion: tuple[str, ...] = ()


@dataclass(frozen=True)
class KeyPoint:
    id: str
    text: str


@dataclass(frozen=True)
class LevelSpec:
    level: int
    seed: str
    key_points: tuple[KeyPoint, ...]
    red_flags: tuple[str, ...] = ()


@dataclass(frozen=True)
class AreaSpec:
    id: str
    title: str
    tags: tuple[str, ...]
    levels: tuple[LevelSpec, ...]

    @property
    def max_level(self) -> int:
        return max(lv.level for lv in self.levels)

    def level_spec(self, level: int) -> LevelSpec:
        """Closest defined level at or below the request, so an area with fewer levels still works."""
        ordered = sorted(self.levels, key=lambda lv: lv.level)
        chosen = ordered[0]
        for lv in ordered:
            if lv.level <= level:
                chosen = lv
        return chosen


@dataclass(frozen=True)
class TierSpec:
    id: str
    name: str
    description: str
    criteria: tuple[str, ...]


@dataclass(frozen=True)
class Blueprint:
    id: str
    limits: Limits
    fields: tuple[FieldSpec, ...]
    care_intro: str
    care_items: tuple[CareItem, ...]
    areas: tuple[AreaSpec, ...]
    start_level_by_experience: dict[str, int]
    tiers: tuple[TierSpec, ...]
    experience_probes: tuple[ExperienceProbeSpec, ...] = ()
    faq: tuple[tuple[str, str], ...] = ()
    raw: dict[str, Any] = field(default_factory=dict, compare=False, repr=False)

    def field_spec(self, field_id: str) -> FieldSpec | None:
        return next((f for f in self.fields if f.id == field_id), None)

    def care_item(self, item_id: str) -> CareItem | None:
        return next((c for c in self.care_items if c.id == item_id), None)

    def area(self, area_id: str) -> AreaSpec | None:
        return next((a for a in self.areas if a.id == area_id), None)

    def experience_probe(self, probe_id: str) -> ExperienceProbeSpec | None:
        return next((p for p in self.experience_probes if p.id == probe_id), None)

    @property
    def gate_items(self) -> tuple[CareItem, ...]:
        return tuple(c for c in self.care_items if c.gate)

    @classmethod
    def from_api(cls, data: dict[str, Any] | None) -> Blueprint:
        if not data:
            return cls.minimal()
        lim = data.get("limits") or {}
        base = Limits()
        limits = Limits(**{k: type(getattr(base, k))(lim[k]) for k in base.__dataclass_fields__ if k in lim})

        screening = data.get("screening") or {}
        fields = tuple(
            FieldSpec(
                id=f["id"],
                label=f.get("label") or f["id"],
                kind=f.get("kind") or "text",
                group=f.get("group") or f["id"],
                ask=f.get("ask") or f"Ask for their {f.get('label') or f['id']}.",
                confirm=bool(f.get("confirm")),
            )
            for f in screening.get("fields") or []
        )
        care_items = tuple(
            CareItem(
                id=c["id"],
                label=c.get("label") or c["id"],
                ask=c.get("ask") or f"Ask if they are comfortable with {c.get('label') or c['id']}.",
                gate=bool(c.get("gate")),
                persuasion=tuple(c.get("persuasion") or ()),
            )
            for c in screening.get("care_items") or []
        )
        experience_probes = tuple(
            ExperienceProbeSpec(
                id=str(p["id"]),
                ask=str(p.get("ask") or "").strip()
                or f"Ask one short nursing question about {p.get('id')}.",
                tags=tuple(str(t) for t in (p.get("tags") or ()) if str(t).strip()),
            )
            for p in screening.get("experience_probes") or []
            if p.get("id") and str(p.get("ask") or "").strip()
        )
        areas = tuple(
            AreaSpec(
                id=a["id"],
                title=a.get("title") or a["id"],
                tags=tuple(a.get("tags") or ("general",)),
                levels=tuple(
                    LevelSpec(
                        level=int(lv["level"]),
                        seed=lv["seed"],
                        key_points=tuple(KeyPoint(k["id"], k["text"]) for k in lv.get("key_points") or ()),
                        red_flags=tuple(lv.get("red_flags") or ()),
                    )
                    for lv in a.get("levels") or ()
                ),
            )
            for a in (data.get("clinical") or {}).get("areas") or []
            if a.get("levels")
        )
        tiers = tuple(
            TierSpec(t["id"], t.get("name") or t["id"], t.get("description") or "", tuple(t.get("criteria") or ()))
            for t in data.get("tiers") or []
        )
        faq = tuple((f.get("topic", ""), f.get("answer", "")) for f in data.get("faq") or [])
        levels = (data.get("clinical") or {}).get("start_level_by_experience") or {}
        return cls(
            id=data.get("id") or "custom",
            limits=limits,
            fields=fields,
            care_intro=screening.get("care_intro") or "",
            care_items=care_items,
            areas=areas,
            start_level_by_experience={"fresher": 1, "junior": 1, "experienced": 2, **{k: int(v) for k, v in levels.items()}},
            tiers=tiers,
            experience_probes=experience_probes,
            faq=faq,
            raw=data,
        )

    @classmethod
    def minimal(cls) -> Blueprint:
        """Fallback when a plan carries no blueprint: a short open clinical conversation, no gating."""
        return cls.from_api(
            {
                "id": "minimal",
                "screening": {"fields": [], "care_items": []},
                "clinical": {
                    "areas": [
                        {
                            "id": "general_nursing",
                            "title": "General nursing practice",
                            "tags": ["general"],
                            "levels": [
                                {
                                    "level": 1,
                                    "seed": "Ask them to describe how they look after a patient from admission to discharge.",
                                    "key_points": [{"id": "gn1", "text": "Assessment, safe care, communication, documentation"}],
                                }
                            ],
                        }
                    ]
                },
                "tiers": [],
            }
        )
