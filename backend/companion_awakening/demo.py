from __future__ import annotations

from datetime import datetime

from .engine import CandidateThought
from .heartbeat import AwakeningConfig, AwakeningService


class ConsoleAdapter:
    """Runnable example. Replace this adapter with your real services."""

    def recent_messages(self, limit):
        return [{"role": "user", "content": "I have a difficult meeting tomorrow."}]

    def relevant_memories(self, messages, limit):
        return [{"content": "The user appreciates calm check-ins before meetings."}]

    def create_thoughts(self, messages, memories, drives):
        return [
            CandidateThought(
                text="I remembered your meeting tomorrow. How are you feeling about it?",
                intent="care",
                urge=0.88,
                memory_relevance=0.92,
                novelty=0.90,
                timing=0.85,
                information_gap=0.78,
                expected_impact=0.82,
                urgency=0.60,
                coherence=0.94,
            )
        ]

    def user_returned_since(self, started_at: datetime):
        return False

    def send_message(self, text, metadata):
        print(f"PROACTIVE: {text}")
        return True

    def append_to_shared_timeline(self, text, metadata):
        print("TIMELINE:", metadata)


if __name__ == "__main__":
    service = AwakeningService(
        ConsoleAdapter(), config=AwakeningConfig(think_threshold=0.0)
    )
    print(service.tick())

