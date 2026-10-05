from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol, Sequence

from .engine import CandidateThought, DesireEngine, DesireState
from .storage import JsonStore


class AwakeningAdapter(Protocol):
    """Connect these methods to your chat database, memory system and LLM."""

    def recent_messages(self, limit: int) -> Sequence[dict]: ...
    def relevant_memories(self, messages: Sequence[dict], limit: int) -> Sequence[dict]: ...
    def create_thoughts(
        self, messages: Sequence[dict], memories: Sequence[dict], drives: dict[str, float]
    ) -> Sequence[CandidateThought]: ...
    def user_returned_since(self, started_at: datetime) -> bool: ...
    def send_message(self, text: str, metadata: dict) -> bool: ...
    def append_to_shared_timeline(self, text: str, metadata: dict) -> None: ...


@dataclass
class AwakeningConfig:
    enabled: bool = True
    think_threshold: float = 0.35
    speak_threshold: float = 0.72
    recent_message_limit: int = 16
    memory_limit: int = 8
    minimum_wake_minutes: int = 5
    maximum_wake_minutes: int = 180


class AwakeningService:
    def __init__(
        self,
        adapter: AwakeningAdapter,
        state_dir: str | Path = "state",
        config: AwakeningConfig | None = None,
    ):
        self.adapter = adapter
        self.config = config or AwakeningConfig()
        root = Path(state_dir)
        self.state_store = JsonStore(root / "desire-state.json")
        self.private_store = JsonStore(root / "private-experience.json")
        self.sent_store = JsonStore(root / "proactive-history.json")
        self.engine = DesireEngine(
            DesireState.from_dict(self.state_store.load({}))
        )

    def _record_private(self, entry: dict) -> None:
        entries = self.private_store.load([])
        entries.append(entry)
        self.private_store.save(entries[-200:])
        # 未发送念头日志：想了但没发出去的，同步到可读日志
        thought = entry.get("thought")
        if thought and not entry.get("spoken"):
            try:
                t = thought.get("text", "")
                intent = thought.get("intent", "")
                urge = thought.get("urge", 0)
                line = (
                    f"[{entry.get('at', '')}] strength={entry.get('strength', 0):.2f} "
                    f"score={entry.get('score', 0):.2f} intent={intent} urge={urge:.2f}\n"
                    f"    {t}\n"
                )
                with open(
                    Path(__file__).resolve().parents[3]
                    / "backend" / "proactive" / "state" / "unspoken-thoughts.log",
                    "a", encoding="utf-8",
                ) as f:
                    f.write(line)
            except Exception:
                pass

    def _finish(self, outcome: str, next_wake: int, **extra) -> dict:
        self.state_store.save(self.engine.state.to_dict())
        return {"outcome": outcome, "next_wake_minutes": next_wake, **extra}

    def tick(self) -> dict:
        cfg = self.config
        if not cfg.enabled:
            return {"outcome": "disabled", "next_wake_minutes": cfg.maximum_wake_minutes}

        started_at = datetime.now(timezone.utc)
        self.engine.advance(started_at)
        next_wake = self.engine.next_wake_minutes(
            cfg.minimum_wake_minutes, cfg.maximum_wake_minutes
        )
        strength = self.engine.thinking_strength()
        if strength < cfg.think_threshold:
            return self._finish("sleep", next_wake, strength=strength)

        # 晚安静默：user说了晚安后，直接跳过念头生成（不调 LLM，省 token）
        if getattr(self.adapter, "is_night_quiet", None) and self.adapter.is_night_quiet():
            return self._finish("night_quiet", next_wake, strength=strength)

        # 对话活跃：user最近 minutes 分钟内发过消息 = 还在聊，不打扰（直接返回，不调 LLM）
        if getattr(self.adapter, "is_conversation_active", None) and self.adapter.is_conversation_active(minutes=15):
            return self._finish("conversation_active", next_wake, strength=strength)

        messages = self.adapter.recent_messages(cfg.recent_message_limit)
        memories = self.adapter.relevant_memories(messages, cfg.memory_limit)
        candidates = list(
            self.adapter.create_thoughts(messages, memories, self.engine.state.values())
        )[:4]
        sent = self.sent_store.load([])
        spoken_texts = [item.get("text", "") for item in sent[-20:]]
        # 所有候选按分数排序，超过阈值的都发（允许多 intent 同时触发）
        scored = []
        for c in candidates:
            s = self.engine.score(c, spoken_texts)
            scored.append((c, s))
        scored.sort(key=lambda x: x[1], reverse=True)

        spoken_any = False
        # 只触发分数最高的那一条（超阈值才发），避免连发打断
        if scored:
            thought, score = scored[0]
            if score >= cfg.speak_threshold:
                # 发之前检查用户是否回来了
                if not self.adapter.user_returned_since(started_at):
                    metadata = {
                        "proactive": True,
                        "self_initiated": True,
                        "intent": thought.intent,
                        "score": round(score, 4),
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    }
                    if self.adapter.send_message(thought.text, metadata):
                        self.adapter.append_to_shared_timeline(thought.text, metadata)
                        sent.append({"text": thought.text, **metadata})
                        spoken_texts.append(thought.text)
                        spoken_any = True
                        private_entry = {
                            "at": started_at.isoformat(),
                            "strength": strength,
                            "score": score,
                            "thought": asdict(thought),
                            "spoken": True,
                        }
                        self._record_private(private_entry)

        if spoken_any:
            self.sent_store.save(sent[-100:])
            self.engine.satisfy()
            return self._finish("sent", next_wake, score=scored[0][1] if scored else 0, text=scored[0][0].text if scored else "")

        # 一条都没发出去：记录最高分的未说念头
        if scored:
            top_thought, top_score = scored[0]
            private_entry = {
                "at": started_at.isoformat(),
                "strength": strength,
                "score": top_score,
                "thought": asdict(top_thought),
                "spoken": False,
            }
            self._record_private(private_entry)
            return self._finish("silent", next_wake, strength=strength, score=top_score)

        return self._finish("silent", next_wake, strength=strength, score=0)

