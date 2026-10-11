"""Shared simulation handle passed through the tick."""

from __future__ import annotations

from simdemocracy.config import Config
from simdemocracy.events import Event, Ledger
from simdemocracy.models import Citizen, MemoryItem, Party, PartyTie, Relationship, World
from simdemocracy.rng import Streams


class Sim:
    def __init__(self, config: Config, seed: int, world: World) -> None:
        self.config = config
        self.seed = seed
        self.rng = Streams(seed)
        self.world = world
        self.ledger = Ledger()
        self.latest_by_type: dict[str, int] = {}
        self.snapshots: list[dict[str, object]] = []

    def emit(
        self,
        type: str,
        summary: str,
        *,
        significance: str = "major",
        actors: dict[str, object] | None = None,
        factors: dict[str, object] | None = None,
        details: dict[str, object] | None = None,
        causes: list[int] | None = None,
    ) -> Event:
        event = self.ledger.add(
            tick=self.world.tick,
            type=type,
            significance=significance,
            summary=summary,
            actors=actors,
            factors=factors,
            details=details,
            causes=causes,
        )
        self.latest_by_type[type] = event.id
        party = (actors or {}).get("party")
        if isinstance(party, int) and party in self.world.parties:
            self.world.parties[party].event_ids.append(event.id)
        return event

    def citizen(self, citizen_id: int) -> Citizen:
        return self.world.citizens[citizen_id]

    def party(self, party_id: int) -> Party:
        return self.world.parties[party_id]

    def active_parties(self) -> list[Party]:
        return [
            self.world.parties[pid]
            for pid in sorted(self.world.parties)
            if self.world.parties[pid].status == "active"
        ]

    def citizens(self) -> list[Citizen]:
        return [self.world.citizens[cid] for cid in sorted(self.world.citizens)]

    def relationship(self, source: int, target: int) -> Relationship | None:
        return self.world.relationships.get((source, target))

    def tie(self, source: int, target: int) -> PartyTie:
        key = (source, target)
        existing = self.world.ties.get(key)
        if existing is None:
            existing = PartyTie()
            self.world.ties[key] = existing
        return existing

    def seat_share(self, party_id: int) -> float:
        total = self.config.parliament_seats
        if total <= 0:
            return 0.0
        return self.world.seats.get(party_id, 0) / total

    def remember(
        self,
        citizen: Citizen,
        *,
        kind: str,
        subject: int,
        valence: float,
        weight: float = 1.0,
    ) -> None:
        citizen.memory.append(
            MemoryItem(
                tick=self.world.tick,
                kind=kind,
                subject=subject,
                valence=valence,
                weight=weight,
            )
        )
        if len(citizen.memory) > 24:
            del citizen.memory[:-24]
