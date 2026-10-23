"""Goal-driven interview flow.

Code owns structure and guarantees: what must be learned, the persuasion limit on essential duties, how many times a
topic may be probed, when to move on, when to stop. The LLM owns the conversation: it only phrases the directive in
the candidate's language. Every decision here is a pure function of (state, analysis), so it is unit-testable.

Stages: opening -> screening -> clinical -> closing -> ended.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from interview.analysis import (
    ClinicalGrade,
    SlotUpdate,
    TurnAnalysis,
    build_user_payload,
    looks_like_care_consent,
)
from interview.blueprint import AreaSpec, Blueprint, FieldSpec
from interview.flow_state import AreaProgress, FlowState
from interview.language import get_profile
from interview.phone_speech import (
    phone_again_line,
    phone_ask_line,
    phone_confirm_line,
    phone_invalid_line,
    store_phone,
    trunk_prefix,
    valid_indian_mobile,
)
from interview.normalize import normalize_field, parse_height_and_weight, plausible_city, spoken_groups
from interview.plan import InterviewPlan
from interview.prompts import opening_seed

NEGATIVE_STANCES = ("hesitant", "refuses")
LOW_CONFIDENCE = 0.6
MAX_CARE_ASKS = 2
SAFETY_BASICS = ("medication_safety", "emergency_response", "infection_control")

_TAG_KEYWORDS: dict[str, tuple[str, ...]] = {
    "icu": ("icu", "nicu", "picu", "critical", "ccu", "ventilator", "iccu"),
    "homecare": ("home", "private duty", "caregiver", "care giver", "elderly", "attendant", "domiciliary"),
    "ward": ("ward", "general", "opd", "ot ", "operation", "clinic", "hospital", "nursing home"),
}

PHONE_ASK = "Ask for their mobile number."

STYLE_FOOTER = (
    "Reply in 1-2 short spoken sentences, like a recruiter on a phone. Ask only ONE question. "
    "No long intros such as 'now we will discuss' or 'there are no trick questions'. "
    "Do not say whether their answer was right or wrong."
)

MAX_FOCUS_RETRIES = 3  # repeat / rephrase / unclear on the same focus before soft-skip

# Spoken English digit words GPT-Live often emits for phone numbers.
_PHONE_DIGIT_WORDS = frozenset(
    {
        "zero",
        "oh",
        "o",
        "one",
        "two",
        "three",
        "four",
        "five",
        "six",
        "seven",
        "eight",
        "nine",
        "double",
        "triple",
        "hundred",
        "thousand",
    }
)


@dataclass
class Move:
    kind: str
    directive: str
    completed: bool = False
    end_session: bool = False
    events: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    # Set outside InterviewFlow (agent layer). Never used for policy.
    tone: str | None = None
    # Spoken as-is. One sentence, so the voice model cannot add a second question.
    verbatim: str | None = None


class InterviewFlow:
    def __init__(
        self,
        plan: InterviewPlan,
        blueprint: Blueprint,
        state: FlowState | None = None,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.plan = plan
        self.bp = blueprint
        self.state = state or FlowState(language=plan.language)
        self._clock = clock
        self._t0 = clock()
        self._base_elapsed = self.state.elapsed_s
        self._invalid: dict[str, str] = {}
        self._invalid_heard: dict[str, str] = {}
        self._phone_agree_rejects = 0
        self._last_user = ""
        self._pending_aside = ""

    # ------------------------------------------------------------------------------------------------ helpers

    @property
    def stage(self) -> str:
        return self.state.stage

    @property
    def done(self) -> bool:
        return self.state.stage == "ended"

    def elapsed_s(self) -> float:
        return self._base_elapsed + (self._clock() - self._t0)

    def facts(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for fid, slot in self.state.slots.items():
            if slot.status in ("captured", "confirmed"):
                out[fid] = slot.value
        for iid, care in self.state.care.items():
            if care.stance != "unknown":
                out[f"care:{iid}"] = care.stance
        if self.state.experience_level != "unknown":
            out["experience_level"] = self.state.experience_level
        return out

    def _facts_line(self) -> str:
        facts = self.facts()
        if not facts:
            return ""
        shown = ", ".join(f"{k}={v}" for k, v in facts.items() if k != "phone")
        return f"\nWhat you already know about the candidate (do not ask again): {shown}."

    def _wrap(self, move: Move, nervous: bool) -> Move:
        aside = (self._pending_aside or "").strip()
        self._pending_aside = ""
        if aside and move.verbatim:
            move.directive = (
                f"They also said something that is not the answer: {aside}. "
                "Reply to that in one short sentence. Then say exactly this and nothing more: "
                f"{move.verbatim}"
            )
            move.verbatim = None
        elif aside and move.kind not in ("aside", "salary_holdout"):
            move.directive = (
                f"They also said something that is not the answer: {aside}. "
                "Reply to that in one short sentence first. Then do only what follows. "
            ) + move.directive
        if nervous:
            self.state.nervous_events += 1
            move.directive = (
                "The candidate sounds nervous. First give one short, warm reassurance (no rush, no trick "
                "questions, any answer is okay), then: " + move.directive
            )
        return move

    def _move(self, kind: str, directive: str, **kw: Any) -> Move:
        return Move(kind=kind, directive=f"{directive}{self._facts_line()}\n{STYLE_FOOTER}", **kw)

    def _set_focus(self, type_: str, **kw: Any) -> None:
        self.state.focus = {"type": type_, **kw}

    # ----------------------------------------------------------------------------------------- analyst context

    def pending_confirmation(self) -> tuple[str, str] | None:
        f = self.state.focus
        if f.get("type") == "confirm":
            slot = self.state.slots.get(f.get("field", ""))
            if slot and slot.value is not None:
                return f["field"], str(slot.value)
        return None

    def expects_short_answer(self) -> bool:
        """True when the current focus is a one-fact / yes-no question (city, phone, year, confirm, care…)."""
        f = self.state.focus or {}
        ftype = f.get("type") or ""
        if ftype in ("confirm", "care"):
            return True
        if ftype == "slots":
            return True  # screening fields are single facts (city, phone, years, height, …)
        return False

    def short_answer_kinds(self) -> tuple[str, ...]:
        """Field kinds currently in focus (empty when focus is not slots)."""
        f = self.state.focus or {}
        if f.get("type") != "slots":
            return ()
        kinds: list[str] = []
        for fid in f.get("ids") or []:
            spec = self.bp.field_spec(str(fid))
            if spec is not None:
                kinds.append(spec.kind)
        return tuple(kinds)

    def utterance_ready_for_focus(self, text: str) -> bool:
        """Whether this transcript is enough to decide, given the live focus (not a fixed length rule)."""
        from interview.plan import WEAK_TOKENS, classify_answer

        text = (text or "").strip()
        # Drop STT garbage (replacement char, bare ellipsis).
        if not text or text in {"\ufffd", "…", "..."} or set(text) <= {"\ufffd", " ", ".", "…"}:
            return False
        verdict = classify_answer(text)
        if verdict == "noise":
            return False

        tokens = [t.strip(".,!?;:\"'\ufffd").lower() for t in text.split() if t.strip(".,!?;:\"'\ufffd")]
        tokens = [t for t in tokens if t and t != "\ufffd"]
        kinds = self.short_answer_kinds()
        # Phone: streaming STT often looks "substantive" after 3 digit-words — wait for a fuller number.
        if kinds and all(k == "phone" for k in kinds):
            digit_chars = sum(1 for ch in text if ch.isdigit())
            digit_words = sum(
                1
                for t in tokens
                if t in _PHONE_DIGIT_WORDS or any(ch.isdigit() for ch in t)
            )
            spoken = trunk_prefix(store_phone(text))
            # Digit-by-digit still waits for a fuller number. A short wording
            # such as "saade paach she" is already the whole phrase.
            other_words = sum(1 for t in tokens if t not in _PHONE_DIGIT_WORDS and not any(ch.isdigit() for ch in t))
            return (
                len(spoken) >= 10
                or digit_chars >= 8
                or digit_words >= 6
                or other_words >= 2
            )

        if verdict == "substantive":
            return True

        if not self.expects_short_answer():
            # Clinical / experience dive: keep holding short scraps for a fuller answer.
            return False

        ftype = (self.state.focus or {}).get("type") or ""
        # Confirm / care: haan / nahi / yes / ok are valid one-word answers.
        if ftype in ("confirm", "care"):
            return True

        if not tokens:
            return False
        numeric_kinds = {"year", "years", "height", "weight"}
        for tok in tokens:
            if tok in WEAK_TOKENS:
                continue
            if any(ch.isdigit() for ch in tok):
                return True
            if kinds and all(k in numeric_kinds for k in kinds) and len(tok) >= 2:
                return True
            if len(tok) >= 2:  # PUNE, Goa, ICU, GNM, …
                return True
        return False

    def focus_lock_summary(self) -> str:
        """Compact description of what the voice model may ask about right now."""
        f = self.state.focus or {}
        ftype = f.get("type") or "none"
        stage = self.state.stage
        if ftype == "slots":
            ids = [str(i) for i in (f.get("ids") or [])]
            kinds = list(self.short_answer_kinds())
            return f"stage={stage} focus=slots fields={','.join(ids) or '?'} kinds={','.join(kinds) or '?'}"
        if ftype == "confirm":
            return f"stage={stage} focus=confirm field={f.get('field') or '?'}"
        if ftype == "care":
            items = [str(i) for i in (f.get("items") or [])]
            return f"stage={stage} focus=care items={','.join(items) or '?'}"
        if ftype == "clinical":
            return (
                f"stage={stage} focus=clinical area={f.get('area') or '?'} "
                f"level={f.get('level') or '?'}"
            )
        if ftype == "experience_dive":
            return f"stage={stage} focus=experience_dive"
        if ftype == "resume_check":
            return f"stage={stage} focus=resume_check"
        if ftype == "contradiction":
            return f"stage={stage} focus=contradiction"
        if ftype == "closing_qa":
            return f"stage={stage} focus=closing_qa"
        return f"stage={stage} focus={ftype}"

    def analysis_payload(self, utterance: str, last_agent_text: str, recent_turns: list[dict[str, str]]) -> str:
        st = self.state
        fields_needed: list[dict[str, str]] = []
        care_focus: list[dict[str, str]] = []
        clinical_ctx: dict[str, Any] | None = None

        if st.stage == "screening":
            for spec in self.bp.fields:
                slot = st.slots.get(spec.id)
                if slot is None or slot.status == "empty":
                    fields_needed.append({"id": spec.id, "label": spec.label, "kind": spec.kind})
            if st.focus.get("type") == "care":
                ids = set(st.focus.get("items") or ())
                care_focus = [{"id": c.id, "label": c.label} for c in self.bp.care_items if c.id in ids]
        elif st.stage == "clinical" and st.current_area:
            area = self.bp.area(st.current_area)
            if area:
                prog = st.area_progress(area.id)
                lv = area.level_spec(prog.level)
                clinical_ctx = {
                    "area_id": area.id,
                    "title": area.title,
                    "level": lv.level,
                    "question_seed": st.focus.get("question") or lv.seed,
                    "key_points": [{"id": k.id, "text": k.text} for k in lv.key_points],
                    "red_flags": list(lv.red_flags),
                }

        pending = self.pending_confirmation()
        return build_user_payload(
            stage=st.stage,
            utterance=utterance,
            last_agent_text=last_agent_text or st.last_question,
            recent_turns=recent_turns,
            fields_needed=fields_needed,
            care_focus=care_focus,
            pending_confirmation={"field": pending[0], "value": pending[1]} if pending else None,
            clinical_context=clinical_ctx,
            known_facts=self.facts(),
            known_claims=st.claims,
            resume_summary=getattr(self.plan, "resume_text", "") or "",
            language=st.language,
        )

    @property
    def wants_clinical_model(self) -> bool:
        return self.state.stage == "clinical"

    # ------------------------------------------------------------------------------------------------ opening

    def opening(self) -> Move:
        st = self.state
        if st.stage != "opening":
            return self.resume()
        full = (self.plan.candidate_name or "").strip()
        name = full.split()[0] if full else "there"
        st.screening_started_s = self.elapsed_s()
        st.stage = "screening"
        first = self._screening_next([])
        ask = first.directive.removesuffix(f"\n{STYLE_FOOTER}")
        lang = (st.language or self.plan.language or "en-IN").strip()
        profile = get_profile(lang)
        seed_word = opening_seed(lang).replace("…", "").strip()
        lang_note = (
            f"Speak in everyday spoken {profile.label} (native script). Do NOT switch to Hindi."
            if not lang.startswith("en")
            else "Speak in clear Indian English."
        )
        greeting = (
            f"OPENING CONTINUATION — the greeting word ({seed_word}) was ALREADY spoken aloud. "
            f"Do NOT say it again.\n"
            f"- Greet them once by their first name ({name}) and say you are {self.plan.interviewer_name} from "
            f"{self.plan.company_name} — one short sentence, then a pause.\n"
            f"- {lang_note} Optional one short beat: {profile.label}/English mix is fine. Do NOT say 'two-part chat', "
            f"'no trick questions', or any long process explanation.\n"
            f"- Then ask ONLY this first question: {ask}\n"
            f"- Keep it SHORT and HUMAN: 2–3 very short sentences total (not one long paragraph). "
            f"Commas and '…' for breath pauses. You MAY write one 'umm,' before the question.\n"
            f"- If ElevenLabs audio tags are active: use several between beats, e.g. [friendly] "
            f"[short pause] [hesitant] [curious]."
        )
        return Move("opening", greeting, events=[("flow.started", {"stage": "screening"})] + first.events)

    def resume(self) -> Move:
        st = self.state
        st.interruptions += 1
        last = f" Your last question was: {st.last_question}" if st.last_question else ""
        if st.stage in ("closing", "ended"):
            return self._move(
                "resume_closing",
                "The call dropped and came back while you were wrapping up. Welcome them back in a few words and "
                "say a warm goodbye. Do not ask anything new.",
                completed=True,
                end_session=True,
            )
        return self._move(
            "resume",
            "The call was briefly interrupted and the candidate is back. In one short sentence say sorry for the "
            f"break and welcome them back, then continue exactly where you were by repeating your last question "
            f"in simple words.{last}",
            events=[("flow.resumed", {"stage": st.stage})],
        )

    # ------------------------------------------------------------------------------------------ non-analysis

    def noise_move(self) -> Move:
        """Nothing usable was heard (empty transcript or noise marker)."""
        return self._unclear()

    def _unclear(self) -> Move:
        """Unrecognised speech: clarify, then soft-skip the stuck focus (never loop forever).

        Production voice agents treat garbled audio as non-consent — ask once, then move on
        rather than inventing an answer or re-asking the same field indefinitely.
        """
        st = self.state
        st.unclear_streak += 1
        st.unclear_total += 1
        # Same focus retried too often → mark unknown / skip area and continue the interview.
        skip = self._bump_focus_retry()
        if skip is not None:
            st.unclear_streak = 0
            skip.directive = (
                "You could not make out their answer after a few tries. In one short warm sentence say you will "
                "note that for now and move on — no blame. Then continue with: "
            ) + skip.directive
            return skip
        if st.unclear_streak >= self.bp.limits.max_unclear_streak:
            st.unclear_streak = 0
            return self._move(
                "noise_help",
                "Say kindly that you are having trouble hearing them. Suggest moving somewhere quieter, closer to the "
                "phone, or using earphones. Then ask your last question again, simply.",
                events=[("audio.noise_help", {"stage": st.stage, "total": st.unclear_total})],
            )
        last = f" Then ask this once: {st.last_question}" if st.last_question else " Then ask your last question once."
        return self._move(
            "ask_repeat",
            "You could not hear that properly. Your FIRST sentence must say, in their language, that you could not "
            "hear it properly. Do not guess what they said and do not ask it as if it were a new question."
            + last,
            events=[("audio.unclear", {"stage": st.stage, "streak": st.unclear_streak})],
        )

    def _preabsorb_screening_facts(self, a: TurnAnalysis) -> list[tuple[str, dict[str, Any]]]:
        """Pull slot/care/confirm facts out of a compound turn before handling a meta-intent.

        Real candidates often mix content with a question ("number is X, what's the salary?").
        Meta-intents must not throw away the extractable fields.
        """
        events: list[tuple[str, dict[str, Any]]] = []
        if self.state.stage not in ("screening", "opening"):
            # Still accept phone etc. mentioned mid-clinical if the analyst extracted them.
            if not a.slot_updates and not a.care_updates and a.confirmation == "none":
                return events
        self._absorb_confirmation(a)
        self._absorb_slot_updates(a, events)
        self._absorb_care(a, events)
        return events

    def _bump_focus_retry(self) -> Move | None:
        """After too many repeats/unclear on the same focus, soft-skip so the call does not loop forever."""
        st = self.state
        focus = st.focus
        if not focus.get("type"):
            return None
        retries = int(focus.get("retries") or 0) + 1
        focus["retries"] = retries
        if retries < MAX_FOCUS_RETRIES:
            return None
        focus_type = focus.get("type")
        events: list[tuple[str, dict[str, Any]]] = [
            ("focus.soft_skip", {"type": focus_type, "retries": retries})
        ]
        if focus_type in ("slots", "confirm"):
            self._give_up_focus_slots(hard_kinds=(), force=True)
            return self._screening_next(events)
        if focus_type == "care":
            self._mark_care_focus_negative("dont_know")
            return self._screening_next(events)
        if focus_type == "experience_dive":
            st.experience_dive_done = True
            return self._screening_next(events)
        if focus_type == "resume_check":
            return self._screening_next(events)
        if focus_type == "clinical" and st.current_area:
            area = self.bp.area(st.current_area)
            if area is not None:
                return self._finish_area(area, st.area_progress(area.id), "unknown")
        if focus_type == "contradiction":
            self._set_focus("none")
            if st.stage == "clinical":
                return self._clinical(TurnAnalysis(), None, False)
            return self._screening_next(events)
        return None

    def silence(self, level: int) -> Move:
        st = self.state
        st.silence_level = level
        if st.stage in ("closing", "ended"):
            return self._move("goodbye", "Say a short goodbye.", completed=True, end_session=True)
        if level <= 1:
            return self._move(
                "silence_nudge",
                "The candidate has been quiet for a while. Gently say there is no hurry and offer to repeat the "
                "question if they would like. Do not ask a new question.",
            )
        if level == 2:
            return self._move(
                "silence_rephrase",
                "Still quiet. Check that they can hear you, then offer to ask the same thing in simpler words, or to "
                "move on to the next question if they prefer.",
            )
        if level == 3:
            return self._move(
                "silence_check",
                "Still no reply. Ask warmly if they are still there and say you will wait a little longer.",
            )
        return self._close(
            "incomplete_silence",
            "There has been no response for a long time. Say kindly that you will pause here, that they can rejoin "
            "using the same link when they are ready, and thank them. Keep it to two short sentences.",
            "silence_end",
        )

    def force_complete(self, reason: str = "time") -> Move:
        return self._close(
            reason,
            "Time is up for this interview. Thank the candidate warmly by name, say the team will review the "
            "conversation and be in touch, and say goodbye. Do not ask any new question.",
            "time_limit",
        )

    # ------------------------------------------------------------------------------------------------- apply

    def apply(self, a: TurnAnalysis) -> Move:
        st = self.state
        st.turns += 1
        st.silence_level = 0
        st.elapsed_s = self.elapsed_s()
        self._invalid = {}
        self._invalid_heard = {}
        self._pending_aside = "" if a.intent == "off_topic" else (a.aside or "").strip()[:200]
        self._prepare_phone_turn(a)
        self._prepare_body_turn(a)

        if st.stage == "ended":
            return self._move("ended", "The interview is over. Reply with one short, warm goodbye.", completed=True, end_session=True)
        if st.elapsed_s >= self.bp.limits.hard_cap_minutes * 60:
            return self.force_complete("time")

        # Partial hearing → only force a read-back on fields marked confirm (phone).
        # Height/weight/qualification must not get a confirm turn on every muddy STT pass.
        if a.intelligibility == "partial":
            for u in a.slot_updates:
                spec = self.bp.field_spec(u.field)
                if spec is not None and spec.confirm:
                    u.confidence = min(float(u.confidence or 0.8), LOW_CONFIDENCE - 0.05)

        if a.intelligibility == "unclear":
            return self._wrap(self._unclear(), a.nervous)

        # Short हाँ/जी/ok: filler on open questions, but usable when care/confirm already extracted a stance.
        if a.intent == "filler_only":
            if a.care_updates or a.slot_updates or a.confirmation != "none":
                a.intent = "answer"
            else:
                return self._wrap(self._unclear(), a.nervous)

        st.unclear_streak = 0

        if a.experience_level != "unknown" and st.experience_level == "unknown":
            st.experience_level = a.experience_level
        self._absorb_claims(a)

        deferred, deferred_dk = None, False
        if st.focus.get("type") == "contradiction":
            deferred = st.focus.get("deferred_grade")
            deferred_dk = bool(st.focus.get("deferred_dont_know"))
            self._resolve_contradiction(a)

        # Intents that never advance the interview (but may still carry slot/care facts).
        if a.intent == "repeat_request":
            st.repeat_requests += 1
            skip = self._bump_focus_retry()
            if skip is not None:
                return self._wrap(skip, a.nervous)
            return self._wrap(self._repeat(), a.nervous)
        if a.intent == "rephrase_request":
            st.repeat_requests += 1
            skip = self._bump_focus_retry()
            if skip is not None:
                return self._wrap(skip, a.nervous)
            return self._wrap(self._rephrase(), a.nervous)
        if a.intent == "candidate_question" and st.stage != "closing":
            pre = self._preabsorb_screening_facts(a)
            move = self._answer_question(a)
            move.events = pre + list(move.events)
            return self._wrap(move, a.nervous)
        if a.intent == "wants_to_stop":
            return self._wrap(self._handle_stop(), a.nervous)
        if a.intent == "off_topic":
            # A clear side remark gets a short reply, then the same question. Unclear audio stays a hearing problem.
            pre = self._preabsorb_screening_facts(a)
            gist = (a.gist_en or "").strip()
            has_facts = bool(a.slot_updates or a.care_updates or a.confirmation != "none")
            if a.intelligibility != "unclear" and gist:
                move = self._aside(gist)
                extra: list[tuple[str, dict[str, Any]]] = []
            else:
                move = self._redirect(a) if has_facts else self._unclear()
                extra = [] if has_facts else [("audio.off_topic_as_noise", {"stage": st.stage})]
            move.events = pre + extra + list(move.events)
            return self._wrap(move, a.nervous)
        if a.intent == "refusal":
            focus_type = st.focus.get("type")
            if focus_type in ("care", "slots", "confirm"):
                pass  # screening absorbs refuse → hesitant / give-up
            elif self._mentions_comp(a):
                return self._wrap(self._salary_or_holdout(a), a.nervous)
            elif st.stage == "clinical":
                a.intent = "dont_know"  # refuse a clinical Q ≈ skip that area path
            else:
                skip = self._bump_focus_retry()
                if skip is not None:
                    return self._wrap(skip, a.nervous)
                return self._wrap(self._redirect(a), a.nervous)

        raw_now = (a.raw_utterance or "").strip()
        if a.intent == "answer" and raw_now:
            previous = self._last_user
            self._last_user = raw_now
            if st.stage in ("screening", "clinical") and self._revises_previous(previous, raw_now):
                if not self._turn_answers_focus(a):
                    self._keep_fuller_known_text(a)
                    return self._wrap(self._restate_current_question(), a.nervous)
        elif raw_now:
            self._last_user = raw_now

        if st.stage == "screening":
            move = self._screening(a)
        elif st.stage == "clinical":
            move = self._clinical(a, deferred, deferred_dk)
        elif st.stage == "closing":
            move = self._closing(a)
        else:
            move = self._screening(a)
        return self._wrap(move, a.nervous)

    def _revises_previous(self, previous: str, current: str) -> bool:
        """True when this turn is the rest of the answer we just took, not a new one.

        The transcriber commits a partial ('पुणे, पुणे और बैंगलोर') and then the
        full sentence. That tail must not be graded as the next question.
        """
        a = re.sub(r"[\s.,।!?॥？]+", " ", previous or "").strip().casefold()
        b = re.sub(r"[\s.,।!?॥？]+", " ", current or "").strip().casefold()
        if len(a) < 4 or len(b) < 4:
            return False
        if a == b or b.startswith(a) or a.startswith(b):
            return True
        shared = 0
        for left, right in zip(a, b):
            if left != right:
                break
            shared += 1
        return shared >= 8

    def _turn_answers_focus(self, a: TurnAnalysis) -> bool:
        """The current question actually got an answer in this utterance."""
        focus = self.state.focus or {}
        kind = focus.get("type")
        raw = a.raw_utterance or ""
        if kind == "confirm":
            if a.confirmation != "none":
                return True
            return bool(store_phone(raw, a.phone_hint))
        if kind == "slots":
            ids = [str(i) for i in (focus.get("ids") or [])]
            spec = self.bp.field_spec(ids[0]) if ids else None
            if spec is None:
                return False
            if spec.kind == "phone":
                return bool(store_phone(raw, a.phone_hint) or a.phone_resolved)
            return any(u.field == spec.id and str(u.value or "").strip() for u in a.slot_updates)
        if kind == "care":
            items = {str(i) for i in (focus.get("items") or [])}
            return any(u.item in items for u in a.care_updates)
        if kind == "clinical":
            return a.clinical is not None
        return False

    def _keep_fuller_known_text(self, a: TurnAnalysis) -> None:
        """A late full transcript can replace a truncated city. It must not invent a phone."""
        for u in a.slot_updates:
            spec = self.bp.field_spec(u.field)
            if spec is None or spec.kind == "phone":
                continue
            slot = self.state.slot(spec.id)
            if slot.status not in ("captured", "confirmed"):
                continue
            norm = normalize_field(spec.kind, u.value)
            if spec.id == "city" and norm.ok:
                ok, cleaned = plausible_city(norm.value)
                if not ok:
                    continue
                norm = type(norm)(True, cleaned, "")
            if not norm.ok or norm.value is None:
                continue
            newer = str(norm.value).strip()
            if len(newer) > len(str(slot.value or "")):
                slot.value = newer

    def _restate_current_question(self) -> Move:
        """Ask the question that is already on the table. Do not apologise for a mis-hear."""
        st = self.state
        focus = st.focus or {}
        kind = focus.get("type")
        if kind == "slots":
            ids = [str(i) for i in (focus.get("ids") or [])]
            spec = self.bp.field_spec(ids[0]) if ids else None
            if spec is not None:
                ask = self._field_ask(spec)
                self._set_focus("slots", ids=[spec.id])
                move = self._move(
                    "ask_field",
                    "They were still finishing their previous answer. Do not say you could not hear them. "
                    f"Ask only this, once: {ask}",
                )
                if spec.kind == "phone":
                    move.verbatim = phone_ask_line(self.state.language)
                return move
        if kind == "confirm":
            field_id = str(focus.get("field") or "")
            spec = self.bp.field_spec(field_id)
            slot = st.slots.get(field_id)
            if spec is not None and slot is not None and slot.value is not None:
                shown = spoken_groups(str(slot.value)) if spec.kind == "phone" else str(slot.value)
                move = self._move("confirm", f"Say exactly: I heard {shown}. Is that correct?")
                if spec.kind == "phone":
                    move.verbatim = phone_confirm_line(self.state.language, shown)
                return move
        if kind == "care":
            items = [str(i) for i in (focus.get("items") or [])]
            if len(items) > 1 and self.bp.care_intro:
                return self._move("ask_care", self.bp.care_intro)
            if items:
                item = self.bp.care_item(items[0])
                if item is not None:
                    return self._move("ask_care_item", item.ask)
        if kind == "clinical":
            question = str(focus.get("question") or st.last_question or "the same clinical question")
            return self._move(
                "clinical_question",
                "They were still finishing their previous answer. Ask the same clinical question once. "
                f"Do not say you could not hear them. Question: {question}",
            )
        if kind == "experience_dive":
            return self._move(
                "experience_dive",
                "They were still finishing their answer. Ask once what they actually did day to day. "
                "Do not say you could not hear them and do not move on.",
            )
        if st.last_question:
            return self._move(
                "ask_field",
                f"Ask this once. Do not say you could not hear them: {st.last_question}",
            )
        return self._move("ask_field", "Ask your last question once. Do not say you could not hear them.")

    # ------------------------------------------------------------------------------------- generic behaviours

    def _repeat(self) -> Move:
        last = f" The question was: {self.state.last_question}" if self.state.last_question else ""
        return self._move(
            "repeat",
            "The candidate asked you to repeat. Say it again once, a little slower and in plain words, without adding "
            f"new content.{last}",
        )

    def _rephrase(self) -> Move:
        return self._move(
            "rephrase",
            "The candidate did not understand your question. Ask the same thing again in simpler, everyday words and, "
            "if it helps, a small relatable example. Do not give away the answer.",
        )

    def _mentions_comp(self, a: TurnAnalysis) -> bool:
        blob = f"{a.gist_en} {getattr(a, 'language', '')}".lower()
        return any(
            w in blob
            for w in (
                "salary", "pay", "ctc", "package", "benefit", "joining", "offer",
                "सैलरी", "पगार", "वेतन", "सैलरी",
            )
        ) or any(w in (a.gist_en or "").lower() for w in ("salary", "pay", "ctc"))

    def _field_ask(self, spec: FieldSpec) -> str:
        if spec.kind == "phone":
            return PHONE_ASK
        if spec.id in ("experience_years", "experience_settings"):
            return self._experience_ask()
        return spec.ask

    def _experience_ask(self) -> str:
        resume = " ".join((getattr(self.plan, "resume_text", "") or "").split())
        if not resume:
            return (
                "Ask about their nursing experience: how many years, and where they worked. "
                "If they are a fresher, ask about hospital postings or internship instead. One question."
            )
        return (
            "Ask ONE question about their nursing experience, using the resume as the starting point. "
            "Pick one concrete fact from it (role, hospital, ward, or years) and ask them to tell you about that work. "
            "Do not read the resume aloud. Do not ask anything else in this turn. "
            f"Resume: {resume[:500]}"
        )

    def _about_experience(self, a: TurnAnalysis) -> bool:
        focus = self.state.focus or {}
        if focus.get("type") == "experience_dive":
            return True
        if focus.get("type") == "resume_check":
            return False
        ids = {str(i) for i in (focus.get("ids") or [])}
        if ids & {"experience_years", "experience_settings"}:
            return True
        return any(u.field in ("experience_years", "experience_settings") for u in a.slot_updates)

    def _resume_crosscheck(self, a: TurnAnalysis) -> Move | None:
        """One friendly check when spoken experience conflicts with the resume, then the interview moves on."""
        note = " ".join((a.resume_mismatch or "").split())[:240]
        if not note or self.state.resume_crosscheck_done:
            return None
        if not (getattr(self.plan, "resume_text", "") or "").strip():
            return None
        if not self._about_experience(a):
            return None
        self.state.resume_crosscheck_done = True
        self._set_focus("resume_check")
        return self._move(
            "resume_check",
            "What they just said about their experience does not match the resume. "
            "In one friendly sentence, mention only this and ask which to note: "
            f"{note}. Do not ask a second question.",
            events=[("resume.mismatch", {"note": note})],
        )

    def _redirect(self, a: TurnAnalysis | None = None) -> Move:
        if a is not None and self._mentions_comp(a):
            return self._salary_or_holdout(a)
        return self._move(
            "redirect",
            "They went off topic. Acknowledge in a few words, then gently bring them back by asking your last "
            "question again in other words.",
        )

    def _aside(self, gist: str) -> Move:
        """Answer a clear side remark, then return to the question already in progress."""
        note = " ".join(gist.split())[:200]
        heard = TurnAnalysis(gist_en=note)
        if self._mentions_comp(heard):
            return self._salary_or_holdout(heard)
        last = (
            f" Then ask this once: {self.state.last_question}"
            if self.state.last_question
            else " Then ask your last question once."
        )
        return self._move(
            "aside",
            f"They said something that is not the answer to your question: {note}. "
            "Reply to it in one short, natural sentence. Do not ignore it. "
            "Do not extend it into a new topic, give medical advice, or quote salary or a result. "
            "Then return to the interview."
            + last,
            events=[("turn.aside", {"gist": note})],
        )

    def _salary_or_holdout(self, a: TurnAnalysis) -> Move:
        return self._move(
            "salary_holdout",
            "They are asking about salary, benefits, or joining, or refusing to continue until you share that. "
            "In one short sentence say you cannot quote numbers — the recruitment team shares salary and benefits "
            "after they review this chat. Then ask if they can continue with the next question, or prefer to stop. "
            "Never invent a figure.",
            events=[("branch.salary_holdout", {"gist": (a.gist_en or "")[:120]})],
        )

    def _answer_question(self, a: TurnAnalysis | None = None) -> Move:
        if a is not None and self._mentions_comp(a):
            return self._salary_or_holdout(a)
        faq = "; ".join(f"{t}: {ans}" for t, ans in self.bp.faq) or "none"
        return self._move(
            "answer_question",
            "The candidate asked you a question. Answer that question in one sentence, using only this: "
            f"{faq}. If their question is not covered, say the recruitment team will follow up on it. "
            "Bring up pay only when they asked about pay. Never invent details "
            "and never discuss their score or result. Then return to your last question in one short ask.",
        )

    def _handle_stop(self) -> Move:
        st = self.state
        st.stop_requests += 1
        if st.stop_requests >= 2:
            return self._close(
                "withdrew",
                "The candidate wants to stop. Accept that respectfully, thank them, say they are welcome to continue "
                "another time, and say goodbye.",
                "candidate_withdrew",
            )
        return self._move(
            "confirm_stop",
            "The candidate may want to stop. Ask kindly whether they would like to stop, or whether a short break or "
            "moving on at an easier pace would help.",
        )

    def _absorb_claims(self, a: TurnAnalysis) -> None:
        st = self.state
        for claim in a.new_claims:
            if claim not in st.claims:
                st.claims.append(claim)
        del st.claims[:-30]

    def _contradiction_move(
        self, a: TurnAnalysis, deferred_grade: dict[str, Any] | None, *, dont_know: bool = False
    ) -> Move | None:
        st = self.state
        lim = self.bp.limits
        if not a.contradictions or st.contradiction_probes >= lim.max_contradiction_probes:
            return None
        c = a.contradictions[0]
        if not self._candidate_said(str(c.get("claim_a") or "")):
            return None
        st.contradiction_probes += 1
        st.contradictions.append({**c, "turn": st.turns, "resolved": False, "resolution": ""})
        # What the answer was is remembered, so the interview carries on from it once the probe is answered.
        self._set_focus("contradiction", deferred_grade=deferred_grade, deferred_dont_know=dont_know)
        return self._move(
            "probe_contradiction",
            f"Earlier the candidate said: \"{c['claim_a']}\". Just now they said: \"{c['claim_b']}\". "
            "Mention only those two things they said. In a friendly way, ask them to help you note it correctly.",
            events=[("contradiction.detected", {"a": c["claim_a"], "b": c["claim_b"], "note": c["note"]})],
        )

    def _candidate_said(self, claim: str) -> bool:
        """A number in an 'earlier you said' line has to be one they actually gave."""
        nums = re.findall(r"\d+", claim or "")
        if not nums:
            return True
        blob = " ".join(self.state.claims)
        for slot in self.state.slots.values():
            blob += " " + str(slot.value or "")
        return all(n in blob for n in nums)

    def _resolve_contradiction(self, a: TurnAnalysis) -> None:
        for c in reversed(self.state.contradictions):
            if not c.get("resolved"):
                c["resolved"] = True
                c["resolution"] = a.gist_en[:300]
                break

    # ---------------------------------------------------------------------------------------------- screening

    def _slots_done(self) -> bool:
        return all(self.state.slots.get(f.id) and self.state.slots[f.id].status != "empty" for f in self.bp.fields)

    def _prepare_phone_turn(self, a: TurnAnalysis) -> None:
        """Store the number they just said, in whatever wording they used.

        The hearing supplies digits for words. A full number replaces the one
        we read back. The same number locks it. A scrap does not rewrite part
        of a number already read back. A short number can still be finished
        with the next group.
        """
        pending = self.pending_confirmation()
        if pending:
            spec = self.bp.field_spec(pending[0])
            if spec is None or spec.kind != "phone":
                return
            previous = str(self.state.slot(spec.id).value or "")
            raw = (a.raw_utterance or "").strip()
            prev_digits = trunk_prefix(re.sub(r"\D", "", previous))
            heard = store_phone(raw, a.phone_hint) if raw else ""
            if heard and len(prev_digits) < 10 and len(heard) < 10 and heard not in prev_digits:
                if len(prev_digits) + len(heard) <= 13:
                    heard = prev_digits + heard
            if heard and heard == prev_digits:
                a.slot_updates = [u for u in a.slot_updates if u.field != spec.id]
                a.confirmation = "confirmed"
                a.confirmation_field = spec.id
                return
            if not heard or (len(heard) < 10 and len(prev_digits) >= 10):
                a.slot_updates = [u for u in a.slot_updates if u.field != spec.id]
                return
            a.phone_resolved = heard
            a.slot_updates = [u for u in a.slot_updates if u.field != spec.id]
            a.slot_updates.append(SlotUpdate(spec.id, heard, 0.9, raw[:80]))
            if a.confirmation == "confirmed":
                a.confirmation = "none"
            return

        focus = self.state.focus or {}
        if focus.get("type") != "slots" or "phone" not in (focus.get("ids") or []):
            return
        raw = (a.raw_utterance or "").strip()
        if not raw:
            return
        parsed = store_phone(raw, a.phone_hint)
        if not parsed:
            a.slot_updates = [u for u in a.slot_updates if u.field != "phone"]
            return
        a.phone_resolved = parsed
        a.slot_updates = [u for u in a.slot_updates if u.field != "phone"]
        a.slot_updates.append(SlotUpdate("phone", parsed, 0.9, raw[:80]))

    def _prepare_body_turn(self, a: TurnAnalysis) -> None:
        """Height and weight said in one sentence stay on the right field."""
        focus = self.state.focus or {}
        if focus.get("type") != "slots":
            return
        ids = {str(i) for i in (focus.get("ids") or [])}
        if not ids & {"height_cm", "weight_kg"}:
            return
        raw = (a.raw_utterance or "").strip()
        if not raw:
            return
        height, weight = parse_height_and_weight(raw)
        if height is not None and "height_cm" in ids:
            a.slot_updates = [u for u in a.slot_updates if u.field != "height_cm"]
            a.slot_updates.append(SlotUpdate("height_cm", str(height), 0.9, raw[:80]))
        if weight is not None and "weight_kg" in ids:
            a.slot_updates = [u for u in a.slot_updates if u.field != "weight_kg"]
            a.slot_updates.append(SlotUpdate("weight_kg", str(weight), 0.9, raw[:80]))

    def _absorb_slot_updates(self, a: TurnAnalysis, events: list[tuple[str, dict[str, Any]]]) -> None:
        st = self.state
        for u in a.slot_updates:
            spec = self.bp.field_spec(u.field)
            if spec is None:
                continue
            source = a.phone_resolved if spec.kind == "phone" and a.phone_resolved else u.value
            norm = normalize_field(spec.kind, source)
            if spec.id == "city" and norm.ok:
                ok, cleaned = plausible_city(norm.value)
                if not ok:
                    continue
                norm = type(norm)(True, cleaned)
            slot = st.slot(spec.id)
            if not norm.ok:
                self._invalid[spec.id] = norm.reason
                continue
            if slot.status == "confirmed" and slot.value == norm.value:
                continue
            slot.value = norm.value
            slot.status = "captured"
            slot.confidence = u.confidence
            slot.evidence = u.evidence[:200]
            slot.turn = st.turns
            events.append(("slot.captured", {"field": spec.id, "confidence": u.confidence, "pii": spec.kind == "phone"}))
        years = st.slots.get("experience_years")
        if years and years.status in ("captured", "confirmed") and years.value is not None:
            n = float(years.value)
            st.experience_level = "fresher" if n < 0.5 else "junior" if n < 3 else "experienced"

    def _absorb_confirmation(self, a: TurnAnalysis) -> None:
        pending = self.pending_confirmation()
        if not pending or a.confirmation == "none":
            return
        field_id = pending[0]
        slot = self.state.slot(field_id)
        spec = self.bp.field_spec(field_id)
        if a.confirmation == "confirmed":
            if spec is not None and spec.kind == "phone" and not valid_indian_mobile(str(slot.value or "")):
                heard = str(slot.value or "")
                self._phone_agree_rejects += 1
                slot.status, slot.value = "empty", None
                if self._phone_agree_rejects < 2 and heard:
                    self._invalid[field_id] = "not a 10-digit mobile"
                    self._invalid_heard[field_id] = heard
                else:
                    slot.status = "unknown"
                return
            slot.status = "confirmed"
        elif a.confirmation == "denied":
            fresh = any(u.field == field_id for u in a.slot_updates)
            if not fresh:
                slot.status, slot.value = "empty", None

    def _absorb_care(self, a: TurnAnalysis, events: list[tuple[str, dict[str, Any]]]) -> None:
        st = self.state
        # Care intro focuses every item at once. Positive stances without care-domain evidence
        # (e.g. "हाँ, तीन साल ICU…") must not clear the diaper gate.
        multi_intro = st.focus.get("type") == "care" and len(st.focus.get("items") or []) > 1
        for u in a.care_updates:
            if self.bp.care_item(u.item) is None:
                continue
            evidence = (u.evidence or u.reason or "").strip()
            if (
                multi_intro
                and u.stance in ("comfortable", "willing_with_training")
                and evidence
                and not looks_like_care_consent(evidence)
            ):
                continue
            care = st.care_state(u.item)
            care.stance, care.reason, care.evidence = u.stance, u.reason[:200], u.evidence[:200]
            events.append(("care.stance", {"item": u.item, "stance": u.stance}))

    def _mark_care_focus_negative(self, intent: str) -> None:
        """Apply no/idk on the current care focus when the analyst omitted care_updates.

        Essential (gate) items must land in a negative stance so persuasion can run. Non-gate
        items are marked too and then skipped — only gate_items enter the persuade loop.
        """
        st = self.state
        for item_id in st.focus.get("items", []):
            if self.bp.care_item(item_id) is None:
                continue
            care = st.care_state(item_id)
            if care.stance not in ("unknown", *NEGATIVE_STANCES):
                continue  # already willing / comfortable — do not overwrite
            if intent == "refusal":
                care.stance = "refuses"
                care.reason = care.reason or "refused"
            elif care.stance == "unknown":
                care.stance, care.reason = "hesitant", "unsure"

    def _screening(self, a: TurnAnalysis) -> Move:
        st = self.state
        events: list[tuple[str, dict[str, Any]]] = []
        focus_type = st.focus.get("type")

        self._absorb_confirmation(a)
        self._absorb_slot_updates(a, events)
        self._absorb_care(a, events)

        if focus_type == "experience_dive":
            # Any substantive reply (or idk) closes the dive; we still keep what they said as claims.
            st.experience_dive_done = True
            if a.intent == "dont_know":
                events.append(("experience.dive", {"status": "skipped"}))
            else:
                events.append(("experience.dive", {"status": "answered"}))

        if a.intent == "dont_know" and focus_type in ("slots", "confirm"):
            # Candidate said they don't know — do not re-ask; mark the focus fields and move on.
            self._give_up_focus_slots(hard_kinds=(), force=True)
        elif a.intent in ("dont_know", "refusal") and focus_type == "care":
            # Gate duties (diaper): no/idk → hesitant/refuses so persuasion runs (up to max_persuasions).
            # Non-gate care: mark and move on — _screening_next only persuades gate_items.
            self._mark_care_focus_negative(a.intent)
        elif a.intent == "refusal" and focus_type in ("slots", "confirm"):
            self._give_up_focus_slots(hard_kinds=(), refusal=True, force=True)

        if focus_type != "contradiction":
            check = self._resume_crosscheck(a)
            if check is not None:
                check.events = events + check.events
                return check
            move = self._contradiction_move(a, None)
            if move:
                move.events = events + move.events
                return move
        missed = self._unheard_slot(a)
        if missed is not None:
            heard = self._could_not_hear(missed, events)
            if heard is not None:
                return heard
        return self._screening_next(events)

    def _unheard_slot(self, a: TurnAnalysis) -> FieldSpec | None:
        """The focused fact is still empty after an answer that was not a real value."""
        if a.intent != "answer" or a.confirmation != "none":
            return None
        focus = self.state.focus or {}
        if focus.get("type") != "slots":
            return None
        ids = [str(i) for i in (focus.get("ids") or [])]
        if not ids:
            return None
        spec = self.bp.field_spec(ids[0])
        if spec is None or self.state.slot(spec.id).status != "empty":
            return None
        if spec.kind == "phone":
            raw = a.raw_utterance or " ".join(str(u.value) for u in a.slot_updates if u.field == spec.id)
            if store_phone(raw, a.phone_hint) or a.phone_resolved:
                return None
        return spec

    def _could_not_hear(self, spec: FieldSpec, events: list[tuple[str, dict[str, Any]]]) -> Move | None:
        slot = self.state.slot(spec.id)
        if slot.attempts >= self.bp.limits.max_field_attempts:
            slot.status = "unknown"
            return None
        slot.attempts += 1
        self._set_focus("slots", ids=[spec.id])
        ask = self._field_ask(spec)
        move = self._move(
            "ask_repeat",
            f"You could not hear their {spec.label} properly. Your FIRST sentence must say, in their language, "
            "that you could not hear it properly. Then ask this once, and only this: "
            f"{ask} Do not guess a value and do not ask it as if they had not spoken.",
            events=events + [("audio.unheard", {"field": spec.id})],
        )
        if spec.kind == "phone":
            move.verbatim = phone_again_line(self.state.language)
        return move

    def _experience_captured(self) -> bool:
        """True once experience years/settings are no longer waiting to be asked."""
        st = self.state
        needed = [f.id for f in self.bp.fields if f.id in ("experience_years", "experience_settings")]
        if not needed:
            return True
        return all(st.slot(fid).status != "empty" for fid in needed)

    def _give_up_focus_slots(
        self, *, hard_kinds: tuple[str, ...], refusal: bool = False, force: bool = False
    ) -> None:
        st = self.state
        for fid in st.focus.get("ids", []):
            spec = self.bp.field_spec(fid)
            slot = st.slot(fid)
            if spec is None or slot.status != "empty":
                continue
            # force=True: candidate said "I don't know" / refused — never hang on the same field.
            if force or spec.kind in hard_kinds or slot.attempts >= 2 or refusal:
                slot.status = "unknown"

    def _missing_group(self) -> list[FieldSpec]:
        st = self.state
        for spec in self.bp.fields:
            slot = st.slot(spec.id)
            if slot.status == "empty":
                if slot.attempts >= self.bp.limits.max_field_attempts:
                    slot.status = "unknown"
                    continue
                return [s for s in self.bp.fields if s.group == spec.group and st.slot(s.id).status == "empty"]
        return []

    def _needs_confirmation(self) -> FieldSpec | None:
        """Read-back only for blueprint `confirm` fields (phone). Other slots auto-accept after normalize."""
        st = self.state
        limit = self.bp.limits.max_field_attempts + 2
        for spec in self.bp.fields:
            slot = st.slot(spec.id)
            if slot.status != "captured":
                continue
            if spec.confirm and slot.attempts <= limit:
                return spec
            # Non-phone captures: no spoken confirm unless the blueprint opts in.
            slot.status = "confirmed"
        return None

    def _screening_next(self, events: list[tuple[str, dict[str, Any]]]) -> Move:
        st = self.state
        lim = self.bp.limits

        # 1. Essential duty the candidate is uncomfortable with: persuade up to the limit, then gate.
        for item in self.bp.gate_items:
            care = st.care_state(item.id)
            if care.stance in NEGATIVE_STANCES:
                if care.persuasions >= lim.max_persuasions:
                    st.gate_failed = item.id
                    events.append(("gate.failed", {"item": item.id, "persuasions": care.persuasions}))
                    move = self._close(
                        "screened_out",
                        f"The candidate is not willing to do {item.label}, which is an essential part of this job, "
                        "even after you explained. Respond with respect and no judgement. Say that because this duty "
                        "is essential, you are not able to take the process forward to the next round right now. "
                        "Thank them sincerely for their time and say goodbye. Do not argue and do not ask anything.",
                        "gate_failed",
                    )
                    move.events = events + move.events
                    return move
                care.persuasions += 1
                points = item.persuasion[min(care.persuasions - 1, len(item.persuasion) - 1)] if item.persuasion else (
                    f"Explain kindly that {item.label} is an essential part of the role and ask if they can do it."
                )
                self._set_focus("care", items=[item.id])
                events.append(("care.persuasion", {"item": item.id, "attempt": care.persuasions}))
                return self._move(
                    "persuade",
                    f"The candidate seems uncomfortable with {item.label} (reason they gave: "
                    f"{care.reason or 'not stated'}). This is an essential duty — do NOT move on or skip it yet. "
                    f"Briefly explain why it matters and ask if they can do it. Never pressure or lecture. "
                    f"Persuasion attempt {care.persuasions} of {lim.max_persuasions}. {points}",
                    events=events,
                )

        # 2. A captured value that needs reading back (phone numbers, low-confidence hearing).
        spec = self._needs_confirmation()
        if spec is not None:
            slot = st.slot(spec.id)
            slot.attempts += 1
            value = slot.value
            shown = spoken_groups(str(value)) if spec.kind == "phone" else str(value)
            self._set_focus("confirm", field=spec.id, ids=[spec.id])
            move = self._move(
                "confirm",
                f"Say exactly: I heard {shown}. Is that correct?",
                events=events,
            )
            if spec.kind == "phone":
                move.verbatim = phone_confirm_line(st.language, shown)
            return move

        # 3. Something was heard but looked wrong: ask again.
        if self._invalid:
            fid, reason = next(iter(self._invalid.items()))
            spec2 = self.bp.field_spec(fid)
            if spec2 is not None:
                heard = self._invalid_heard.get(fid, "")
                if spec2.kind == "phone" and heard:
                    shown = spoken_groups(heard)
                    self._set_focus("slots", ids=[fid])
                    move = self._move(
                        "reask_invalid",
                        f"Say exactly: {shown} is not a complete mobile number. Please say the number again.",
                        events=events,
                    )
                    move.verbatim = phone_invalid_line(st.language, shown)
                    return move
                if spec2.kind == "phone":
                    # A too-long or messy hearing is not a reason to skip the number.
                    self._set_focus("slots", ids=[fid])
                    move = self._move(
                        "reask_invalid",
                        "You did not catch a complete mobile number. Ask them to say the full mobile number once, "
                        "slowly. Stay on the mobile number. Do not move on to another question.",
                        events=events,
                    )
                    move.verbatim = phone_again_line(st.language)
                    return move
                slot = st.slot(fid)
                slot.attempts += 1
                if slot.attempts < lim.max_field_attempts:
                    self._set_focus("slots", ids=[fid])
                    return self._move(
                        "reask_invalid",
                        f"What you heard for their {spec2.label} did not sound right ({reason}). Politely say you may "
                        "have misheard and ask them to say it again, slowly.",
                        events=events,
                    )
                slot.status = "unknown"

        # 4. Next group of missing details.
        group = self._missing_group()
        if group:
            for s in group:
                st.slot(s.id).attempts += 1
            asked_before = any(st.slot(s.id).attempts > 1 for s in group)
            ids = [s.id for s in group]
            self._set_focus("slots", ids=ids)
            ask = self._field_ask(group[0])
            prefix = "They did not answer that yet. " if asked_before else ""
            move = self._move("ask_field", f"{prefix}{ask}", events=events)
            if group[0].kind == "phone":
                move.verbatim = phone_ask_line(st.language)
            return move

        # 5. What did they actually do in those settings (depth before care / clinical).
        if self._experience_captured() and not st.experience_dive_done:
            settings = st.slots.get("experience_settings")
            where = str(settings.value) if settings and settings.value else "that work"
            # A long answer already described the duties. Move on to care instead of another background question.
            if len(where.split()) >= 6:
                st.experience_dive_done = True
            else:
                self._set_focus("experience_dive")
                return self._move(
                    "experience_dive",
                    f"They said they have experience in {where}. Ask ONE short nursing question about what they "
                    "actually did with patients there, such as vitals, medicines, or ward work. "
                    "Do not mention the resume or ask where they worked again. "
                    "Do not start the scored clinical scenarios yet.",
                    events=events,
                )

        # 6. Comfort with hands-on care.
        care_move = self._care_questions(events)
        if care_move is not None:
            return care_move

        return self._enter_clinical(events)

    def _care_questions(self, events: list[tuple[str, dict[str, Any]]]) -> Move | None:
        st = self.state
        if not self.bp.care_items:
            return None
        unasked = [c for c in self.bp.care_items if st.care_state(c.id).stance == "unknown"]
        if not unasked:
            return None
        # First ask about all hands-on care at once; afterwards chase only what is still unanswered.
        if not st.care_intro_done:
            st.care_intro_done = True
            self._set_focus("care", items=[c.id for c in self.bp.care_items])
            return self._move(
                "ask_care",
                self.bp.care_intro or "Ask how comfortable they are with hands-on patient care.",
                events=events,
            )
        unasked.sort(key=lambda c: not c.gate)  # essential duties first
        target = unasked[0]
        care = st.care_state(target.id)
        care.asked += 1
        if care.asked > MAX_CARE_ASKS:
            care.stance, care.reason = "hesitant", "did not give a clear answer"
            return self._screening_next(events)
        self._set_focus("care", items=[target.id])
        return self._move("ask_care_item", target.ask, events=events)

    # ------------------------------------------------------------------------------------------------ clinical

    def _candidate_tags(self) -> set[str]:
        text = " ".join(
            str(self.state.slots[f].value or "")
            for f in ("experience_settings",)
            if f in self.state.slots
        ).lower()
        text += " " + (getattr(self.plan, "resume_text", "") or "").lower()
        tags = {"general"}
        for tag, words in _TAG_KEYWORDS.items():
            if any(w in text for w in words):
                tags.add(tag)
        return tags

    def _plan_areas(self) -> list[str]:
        """Pick the areas to assess: relevant to where the candidate worked, with patient-safety basics always in."""
        tags = self._candidate_tags()
        scored: list[tuple[float, int, str]] = []
        for idx, area in enumerate(self.bp.areas):
            if not set(area.tags) & tags:
                continue  # e.g. ICU-only content for a candidate with no ICU exposure
            score = 3.0 * len(set(area.tags) & tags - {"general"})
            if "general" not in area.tags:
                score += 4.0  # specialty-only content (e.g. critical care) is what this candidate is best placed to show
            if area.id in SAFETY_BASICS:
                score += 2.0
            scored.append((-score, idx, area.id))
        scored.sort()
        n = max(1, self.bp.limits.clinical_areas_target)
        return [area_id for _, _, area_id in scored][:n]

    def _enter_clinical(self, events: list[tuple[str, dict[str, Any]]]) -> Move:
        st = self.state
        if not self.bp.areas:
            return self._begin_closing(events)
        st.stage = "clinical"
        st.clinical_started_s = self.elapsed_s()
        st.area_order = self._plan_areas()
        events.append(("stage.clinical", {"areas": st.area_order, "experience_level": st.experience_level}))
        move = self._start_next_area(
            lead_in=(
                "Screening details are done. Thank them in a few words, then go straight into the first nursing "
                "question — no long preamble. "
            )
        )
        move.events = events + move.events
        return move

    def _start_next_area(self, lead_in: str = "") -> Move:
        st = self.state
        nxt = next((aid for aid in st.area_order if st.area_progress(aid).status == "pending"), None)
        if nxt is None:
            return self._begin_closing([])
        area = self.bp.area(nxt)
        assert area is not None
        prog = st.area_progress(nxt)
        prog.status = "active"
        prog.level = self.bp.start_level_by_experience.get(st.experience_level, 1)
        prog.level = min(prog.level, area.max_level)
        st.current_area = nxt
        lv = area.level_spec(prog.level)
        self._set_focus("clinical", area=nxt, level=lv.level, question=lv.seed)
        return self._move(
            "clinical_question",
            f"{lead_in}Now ask a clinical question on '{area.title}'. Put it in your own natural words and fit it to "
            f"what you know about the candidate's work. Do not reveal the answer or list the points. Question: {lv.seed}",
            events=[("area.started", {"area": nxt, "level": lv.level})],
        )

    def _clinical_over_time(self) -> bool:
        st = self.state
        used = self.elapsed_s() - st.clinical_started_s
        return used >= (self.bp.limits.clinical_target_minutes + 2) * 60

    def _clinical(self, a: TurnAnalysis, deferred: dict[str, Any] | None, deferred_dont_know: bool = False) -> Move:
        st = self.state
        lim = self.bp.limits
        if not st.current_area:
            return self._start_next_area()
        area = self.bp.area(st.current_area)
        assert area is not None
        prog = st.area_progress(area.id)
        lv = area.level_spec(prog.level)

        fresh = a.clinical
        grade = fresh
        if grade is None and deferred:
            grade = ClinicalGrade(**deferred)  # graded before a contradiction probe interrupted; already recorded
        if fresh is not None:
            self._record_grade(area, prog, lv.level, fresh)

        said_dont_know = a.intent == "dont_know" or deferred_dont_know
        if st.focus.get("type") != "contradiction":
            move = self._contradiction_move(
                a, _grade_to_dict(grade) if grade else None, dont_know=a.intent == "dont_know"
            )
            if move:
                return move

        if said_dont_know or (grade is not None and grade.quality == "none" and a.intent == "dont_know"):
            return self._clinical_dont_know(area, prog)

        if grade is None or grade.quality in ("unrelated", "none"):
            if prog.clarifications < lim.max_clarifications_per_area:
                prog.clarifications += 1
                self._set_focus("clinical", area=area.id, level=lv.level, question=st.focus.get("question", lv.seed))
                return self._move(
                    "clarify",
                    "Their reply did not really answer the question. Without judging, restate what you are asking in "
                    "simpler words and invite them to try, even if they are not sure.",
                )
            return self._finish_area(area, prog, "unknown")

        if grade.needs_clarification and prog.clarifications < lim.max_clarifications_per_area:
            prog.clarifications += 1
            return self._move(
                "clarify",
                "Their answer was a bit vague. Ask them to be more specific about the part that was unclear, for "
                "example 'what exactly would you do first?'. Do not hint at the correct answer.",
            )

        missing = [k.text for k in lv.key_points if k.id in grade.missing] or [
            k.text for k in lv.key_points if k.id not in grade.covered
        ]
        over_time = self._clinical_over_time()

        if grade.quality == "correct":
            strong = prog.probes == 0 and prog.challenges == 0 and not prog.red_flags
            if strong and not over_time and prog.deepened < 1 and prog.level < area.max_level:
                prog.deepened += 1
                prog.level += 1
                nxt = area.level_spec(prog.level)
                self._set_focus("clinical", area=area.id, level=nxt.level, question=nxt.seed)
                return self._move(
                    "deepen",
                    "That was a solid answer. Acknowledge it in a few words without saying 'correct', then raise the "
                    f"difficulty a notch with this related question, in your own words: {nxt.seed}",
                    events=[("area.deepened", {"area": area.id, "level": nxt.level})],
                )
            return self._finish_area(area, prog, "strong" if strong else "adequate")

        if grade.quality == "partial":
            if prog.probes < lim.max_probes_per_area and not over_time:
                prog.probes += 1
                target = "; ".join(missing[:2]) or "the parts they skipped"
                self._set_focus("clinical", area=area.id, level=lv.level, question=st.focus.get("question", lv.seed))
                return self._move(
                    "probe",
                    "They gave a partly right answer. Acknowledge what they said briefly, then ask ONE follow-up that "
                    f"makes them think about what is missing, without telling them the answer. Missing ideas (for you "
                    f"only, never say them): {target}. Reference something they actually said.",
                )
            return self._finish_area(area, prog, "adequate" if len(prog.covered) * 2 >= len(lv.key_points) else "weak")

        # incorrect
        if prog.challenges < lim.max_challenges_per_area:
            prog.challenges += 1
            issue = "; ".join(grade.red_flags) or "something in their answer that is not right or not safe"
            self._set_focus("clinical", area=area.id, level=lv.level, question=st.focus.get("question", lv.seed))
            return self._move(
                "challenge",
                f"Part of their answer was not right ({issue}; for you only). Politely challenge it without saying "
                "'wrong': present a short realistic situation where that approach could go badly, or ask 'are you "
                "sure about that step?', and invite them to reconsider. Do not give the correct answer.",
                events=[("area.challenged", {"area": area.id})],
            )
        # After a challenge allow a single easier try; hammering a wrong answer is bad interviewing.
        if prog.probes < 1 and not over_time:
            prog.probes += 1
            return self._move(
                "probe_simpler",
                "They still seem unsure. Make it easier: ask only about the very first thing they would do. Do not "
                "reveal the answer.",
            )
        return self._finish_area(area, prog, "unsafe" if prog.red_flags else "weak")

    def _record_grade(self, area: AreaSpec, prog: AreaProgress, level: int, grade: Any) -> None:
        for pid in grade.covered:
            if pid not in prog.covered:
                prog.covered.append(pid)
        prog.missing = [p for p in grade.missing if p not in prog.covered]
        for rf in grade.red_flags:
            if rf not in prog.red_flags:
                prog.red_flags.append(rf)
        prog.evidence.append(
            {
                "turn": self.state.turns,
                "level": level,
                "quality": grade.quality,
                "covered": list(grade.covered),
                "missing": list(grade.missing),
                "red_flags": list(grade.red_flags),
                "quote": grade.quote[:300],
                "summary": grade.summary_en[:300],
            }
        )

    def _clinical_dont_know(self, area: AreaSpec, prog: AreaProgress) -> Move:
        st = self.state
        lim = self.bp.limits
        prog.dont_knows += 1
        st.dont_know_total += 1
        prog.evidence.append(
            {
                "turn": st.turns,
                "level": prog.level,
                "quality": "dont_know",
                "quote": "",
                "summary": "Candidate said they do not know",
            }
        )
        if st.dont_know_total >= lim.max_dont_know_total:
            prog.status, prog.outcome = "done", "unknown"
            return self._begin_closing([("clinical.ended_early", {"reason": "many_dont_know"})])
        # One "I don't know" / idk is enough — acknowledge briefly and move to the next topic.
        return self._finish_area(area, prog, "unknown")

    def _finish_area(self, area: AreaSpec, prog: AreaProgress, outcome: str) -> Move:
        st = self.state
        prog.status, prog.outcome = "done", outcome
        events = [("area.completed", {"area": area.id, "outcome": outcome, "level": prog.level})]
        done = sum(1 for aid in st.area_order if st.area_progress(aid).status == "done")
        if done >= self.bp.limits.clinical_areas_target or self._clinical_over_time():
            return self._begin_closing(events)
        move = self._start_next_area(lead_in="Move on naturally with a short transition, not a verdict on the last answer. ")
        move.events = events + move.events
        return move

    # ------------------------------------------------------------------------------------------------ closing

    def _begin_closing(self, events: list[tuple[str, dict[str, Any]]]) -> Move:
        st = self.state
        st.stage = "closing"
        st.current_area = None
        self._set_focus("closing_qa", asks=0)
        return self._move(
            "wrap_up",
            "That was the last question. Thank the candidate warmly by name for their time and honest answers, and "
            "ask if they have any questions about the process before you finish. Do not mention scores or results.",
            events=events + [("stage.closing", {})],
        )

    def _closing(self, a: TurnAnalysis) -> Move:
        st = self.state
        if a.intent == "candidate_question" and st.focus.get("asks", 0) < 2:
            self._set_focus("closing_qa", asks=st.focus.get("asks", 0) + 1)
            faq = "; ".join(f"{t}: {ans}" for t, ans in self.bp.faq) or "none"
            asked = (a.gist_en or "their question").strip()
            if self._mentions_comp(a):
                line = (
                    "They asked about pay or benefits. Say the recruitment team will share that, without a figure. "
                    "Then ask if there is anything else."
                )
            else:
                line = (
                    f"They asked: \"{asked}\". Answer that, in one sentence, from this list only: {faq}. "
                    "If it is not on the list, say the team will follow up on what they asked. "
                    "Then ask if there is anything else."
                )
            return self._move("closing_answer", line)
        return self._close(
            "completed",
            "Wish them well, tell them the team will review the conversation and contact them on the phone number "
            "they shared, and say goodbye. Do not mention scores or results and do not ask anything.",
            "goodbye",
        )

    def _close(self, outcome: str, directive: str, kind: str) -> Move:
        st = self.state
        st.stage = "ended"
        st.outcome = outcome
        st.current_area = None
        return self._move(
            kind,
            directive,
            completed=True,
            end_session=True,
            events=[("flow.ended", {"outcome": outcome, "elapsed_s": round(self.elapsed_s())})],
        )


def _grade_to_dict(grade: Any) -> dict[str, Any]:
    return {
        "area_id": grade.area_id,
        "quality": grade.quality,
        "covered": list(grade.covered),
        "missing": list(grade.missing),
        "red_flags": list(grade.red_flags),
        "needs_clarification": grade.needs_clarification,
        "quote": grade.quote,
        "summary_en": grade.summary_en,
    }
