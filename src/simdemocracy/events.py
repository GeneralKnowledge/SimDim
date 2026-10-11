"""Append-only event ledger.

Events record facts, numeric drivers, and causal references. They do not
contain literary colour, and nothing in the ledger is allowed to reach back
and alter an earlier tick.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Event:
    id: int
    tick: int
    type: str
    significance: str
    summary: str
    actors: dict[str, object] = field(default_factory=dict)
    factors: dict[str, object] = field(default_factory=dict)
    details: dict[str, object] = field(default_factory=dict)
    causes: list[int] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "tick": self.tick,
            "type": self.type,
            "significance": self.significance,
            "summary": self.summary,
            "actors": self.actors,
            "factors": _plain(self.factors),
            "details": _plain(self.details),
            "causes": list(self.causes),
        }


class Ledger:
    def __init__(self) -> None:
        self.events: list[Event] = []

    def add(
        self,
        *,
        tick: int,
        type: str,
        significance: str,
        summary: str,
        actors: dict[str, object] | None = None,
        factors: dict[str, object] | None = None,
        details: dict[str, object] | None = None,
        causes: list[int] | None = None,
    ) -> Event:
        event = Event(
            id=len(self.events) + 1,
            tick=tick,
            type=type,
            significance=significance,
            summary=summary,
            actors=actors or {},
            factors=factors or {},
            details=details or {},
            causes=list(causes or []),
        )
        self.events.append(event)
        return event


def _plain(value: object) -> object:
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    if isinstance(value, float):
        return round(value, 6)
    return value


def assert_causal(events: list[Event]) -> None:
    """Causes must already exist and must be earlier events."""

    seen: set[int] = set()
    for event in events:
        for cause in event.causes:
            if cause not in seen:
                raise AssertionError(
                    f"event {event.id} ({event.type}) cites unknown cause {cause}"
                )
            if cause >= event.id:
                raise AssertionError(
                    f"event {event.id} cites non-prior cause {cause}"
                )
        if (
            event.significance == "major"
            and event.type != "simulation_started"
            and not event.factors
        ):
            raise AssertionError(
                f"major event {event.id} ({event.type}) has no explanatory factors"
            )
        seen.add(event.id)
