"""Memory-aware autonomous awakening for AI companions."""

from .engine import CandidateThought, DesireEngine, DesireState
from .heartbeat import AwakeningConfig, AwakeningService

__all__ = [
    "AwakeningConfig",
    "AwakeningService",
    "CandidateThought",
    "DesireEngine",
    "DesireState",
]

