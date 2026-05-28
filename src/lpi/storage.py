from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock

from lpi.models import Goal, Signal


@dataclass
class InMemoryStore:
    goals_by_id: dict[str, Goal] = field(default_factory=dict)
    signals_by_id: dict[str, Signal] = field(default_factory=dict)
    lock: Lock = field(default_factory=Lock)

    def reset(self) -> None:
        with self.lock:
            self.goals_by_id.clear()
            self.signals_by_id.clear()


store = InMemoryStore()

