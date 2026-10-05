import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from companion_awakening.engine import CandidateThought, DesireEngine, DesireState
from companion_awakening.heartbeat import AwakeningConfig, AwakeningService


class FakeAdapter:
    def __init__(self):
        self.sent = []

    def recent_messages(self, limit):
        return [{"role": "user", "content": "hello"}]

    def relevant_memories(self, messages, limit):
        return [{"content": "likes concise messages"}]

    def create_thoughts(self, messages, memories, drives):
        return [CandidateThought("Thinking of you", urge=1, memory_relevance=1,
            novelty=1, timing=1, information_gap=1, expected_impact=1,
            urgency=1, coherence=1)]

    def user_returned_since(self, started_at):
        return False

    def send_message(self, text, metadata):
        self.sent.append((text, metadata))
        return True

    def append_to_shared_timeline(self, text, metadata):
        pass


class EngineTests(unittest.TestCase):
    def test_time_changes_are_deterministic(self):
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        state = DesireState(attachment=0.2, updated_at=start.isoformat())
        engine = DesireEngine(state)
        engine.advance(start + timedelta(hours=2))
        self.assertAlmostEqual(engine.state.attachment, 0.236)

    def test_repetition_reduces_score(self):
        engine = DesireEngine()
        new = engine.score(CandidateThought("a fresh thought", novelty=1))
        repeated = engine.score(CandidateThought("a fresh thought", novelty=1), ["a fresh thought"])
        self.assertLess(repeated, new)

    def test_successful_send_is_tagged_and_satisfies_drive(self):
        with tempfile.TemporaryDirectory() as directory:
            adapter = FakeAdapter()
            service = AwakeningService(adapter, directory, AwakeningConfig(
                think_threshold=0, speak_threshold=0,
            ))
            before = service.engine.state.attachment
            result = service.tick()
            self.assertEqual(result["outcome"], "sent")
            self.assertTrue(adapter.sent[0][1]["self_initiated"])
            self.assertLess(service.engine.state.attachment, before)


if __name__ == "__main__":
    unittest.main()

