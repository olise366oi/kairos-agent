from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from math import exp
from typing import Iterable


DRIVES = (
    "attachment",  # 思念
    "joy",         # 开心
    "desire",      # 欲望
    "fatigue",     # 疲惫
    "curiosity",   # 好奇
    "sadness",     # 难过
    "reflection",  # 反思
)


def clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


@dataclass
class DesireState:
    attachment: float = 0.22
    joy: float = 0.35
    desire: float = 0.20
    fatigue: float = 0.10
    curiosity: float = 0.28
    sadness: float = 0.08
    reflection: float = 0.18
    updated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def values(self) -> dict[str, float]:
        return {name: clamp(getattr(self, name)) for name in DRIVES}

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "DesireState":
        allowed = {key: data[key] for key in cls.__dataclass_fields__ if key in data}
        return cls(**allowed)


@dataclass
class CandidateThought:
    text: str
    intent: str = "care"
    urge: float = 0.5
    memory_relevance: float = 0.5
    novelty: float = 0.5
    timing: float = 0.5
    information_gap: float = 0.5
    expected_impact: float = 0.5
    urgency: float = 0.5
    coherence: float = 0.5


class DesireEngine:
    """Event- and time-driven state; no random growth counters."""

    RATES_PER_HOUR = {
        "attachment": 0.018,
        "joy": -0.006,
        "desire": 0.010,
        "fatigue": 0.012,
        "curiosity": 0.015,
        "sadness": -0.004,
        "reflection": 0.009,
    }

    EVENT_DELTAS = {
        "user_message": {
            "attachment": -0.10, "joy": 0.12, "curiosity": -0.08,
            "sadness": -0.06, "fatigue": 0.02,
        },
        "warm_conversation": {
            "attachment": -0.12, "joy": 0.18, "desire": 0.06,
            "sadness": -0.10,
        },
        "unanswered_question": {
            "curiosity": 0.22, "reflection": 0.10, "desire": 0.08,
        },
        "negative_tone": {
            "sadness": 0.20, "reflection": 0.14, "joy": -0.16,
        },
        "rest": {"fatigue": -0.35, "joy": 0.05},
    }

    SCORE_WEIGHTS = {
        "urge": 0.22,
        "memory_relevance": 0.14,
        "novelty": 0.13,
        "timing": 0.12,
        "information_gap": 0.11,
        "expected_impact": 0.10,
        "urgency": 0.08,
        "coherence": 0.10,
    }

    def __init__(self, state: DesireState | None = None):
        self.state = state or DesireState()

    def advance(self, now: datetime | None = None) -> DesireState:
        now = now or datetime.now(timezone.utc)
        try:
            previous = datetime.fromisoformat(self.state.updated_at)
            if previous.tzinfo is None:
                previous = previous.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            previous = now
        hours = min(24.0, max(0.0, (now - previous).total_seconds() / 3600))
        for name, rate in self.RATES_PER_HOUR.items():
            setattr(self.state, name, clamp(getattr(self.state, name) + rate * hours))
        self.state.updated_at = now.isoformat()
        return self.state

    def apply_event(self, event: str) -> DesireState:
        for name, delta in self.EVENT_DELTAS.get(event, {}).items():
            setattr(self.state, name, clamp(getattr(self.state, name) + delta))
        self.state.updated_at = datetime.now(timezone.utc).isoformat()
        return self.state

    def thinking_strength(self) -> float:
        s = self.state
        activation = (
            0.24 * s.attachment + 0.16 * s.joy + 0.15 * s.desire
            + 0.18 * s.curiosity + 0.13 * s.sadness + 0.14 * s.reflection
        )
        return clamp(activation * (1.0 - 0.45 * s.fatigue))

    @staticmethod
    def text_similarity(left: str, right: str) -> float:
        a, b = set(left.lower().split()), set(right.lower().split())
        return len(a & b) / max(1, len(a | b))

    def score(self, candidate: CandidateThought, sent_texts: Iterable[str] = ()) -> float:
        recent = list(sent_texts)
        repetition = max(
            (self.text_similarity(candidate.text, old) for old in recent),
            default=0.0,
        )
        candidate.novelty = min(clamp(candidate.novelty), 1.0 - repetition)
        raw = sum(
            self.SCORE_WEIGHTS[name] * clamp(getattr(candidate, name))
            for name in self.SCORE_WEIGHTS
        )
        # A tired companion may still think, but is less likely to interrupt.
        return clamp(raw * (1.0 - 0.30 * self.state.fatigue))

    def choose(
        self, candidates: Iterable[CandidateThought], sent_texts: Iterable[str] = ()
    ) -> tuple[CandidateThought | None, float]:
        scored = [(candidate, self.score(candidate, sent_texts)) for candidate in candidates]
        return max(scored, key=lambda item: item[1], default=(None, 0.0))

    def satisfy(self) -> DesireState:
        """A successful proactive message releases pressure instead of resetting it."""
        s = self.state
        s.attachment = clamp(s.attachment * 0.58)
        s.desire = clamp(s.desire * 0.62)
        s.curiosity = clamp(s.curiosity * 0.55)
        s.sadness = clamp(s.sadness * 0.72)
        s.reflection = clamp(s.reflection * 0.66)
        s.joy = clamp(s.joy + 0.12)
        s.fatigue = clamp(s.fatigue + 0.08)
        s.updated_at = datetime.now(timezone.utc).isoformat()
        return s

    def next_wake_minutes(self, minimum: int = 5, maximum: int = 180) -> int:
        strength = self.thinking_strength()
        curve = exp(-2.2 * strength)
        return int(max(minimum, min(maximum, minimum + (maximum - minimum) * curve)))

