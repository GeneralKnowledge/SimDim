"""Tick loop.

The order is part of the rules. Random draws happen inside the subsystem that
owns them, on that subsystem's stream, over sorted ids. The loop never looks
at whether the history is "interesting" and inserts an event to liven it up.
"""

from __future__ import annotations

from simdemocracy.config import DIMENSIONS, Config
from simdemocracy.conflict import internal_politics
from simdemocracy.context import Sim
from simdemocracy.elections import hold_election
from simdemocracy.events import assert_causal
from simdemocracy.generate import generate_world
from simdemocracy.information import campaign_visibility, decay_attention, spread_information, spread_rumors
from simdemocracy.invariants import check_invariants
from simdemocracy.organisation import (
    campaign_platforms,
    consider_founding,
    dissolve_failing,
    recruit_and_switch,
)
from simdemocracy.parliament import close_government, form_government, govern
from simdemocracy.rng import Streams


class Simulation:
    def __init__(self, config: Config | None = None, seed: int = 1) -> None:
        self.config = config or Config()
        self.seed = seed
        world = generate_world(self.config, Streams(seed))
        self.sim = Sim(self.config, seed, world)

    def run(self, ticks: int | None = None) -> Sim:
        steps = self.config.ticks if ticks is None else ticks
        if steps < 1:
            raise ValueError("ticks must be at least 1")
        self.sim.emit(
            "simulation_started",
            (
                f"Commonwealth opened with {self.config.population} citizens, "
                f"no parties, and seed {self.seed}."
            ),
            actors={"population": self.config.population},
            factors={
                "seed": self.seed,
                "ticks_planned": steps,
                "election_interval": self.config.election_interval,
                "parliament_seats": self.config.parliament_seats,
                "electoral_system": self.config.electoral_system,
            },
            details={"config": self.config.to_dict()},
        )
        _snapshot(self.sim, "start")
        for _ in range(steps):
            step(self.sim)
        if not self.sim.snapshots or self.sim.snapshots[-1]["tick"] != self.sim.world.tick:
            _snapshot(self.sim, "end")
        assert_causal(self.sim.ledger.events)
        return self.sim


def step(sim: Sim) -> None:
    sim.world.tick += 1
    decay_attention(sim)
    spread_information(sim)
    spread_rumors(sim)
    due = sim.world.tick % sim.config.election_interval == 0 or sim.world.tick == sim.world.forced_election_tick
    if due:
        sim.world.forced_election_tick = None
        if sim.world.government is not None:
            close_government(sim, "election", None)
        consider_founding(sim)
        campaign_visibility(sim)
        campaign_platforms(sim)
        recruit_and_switch(sim)
        dissolve_failing(sim)
        result = hold_election(sim)
        form_government(sim, int(result["event_id"]))
        sim.world.election_lock_until = max(sim.world.election_lock_until, sim.world.tick + 4)
    else:
        consider_founding(sim)
        recruit_and_switch(sim)
        dissolve_failing(sim)
        govern(sim)
    internal_politics(sim)
    dissolve_failing(sim)
    if sim.world.tick % sim.config.snapshot_interval == 0:
        _snapshot(sim, "interval")
    check_invariants(sim)


def _snapshot(sim: Sim, reason: str) -> None:
    citizens = sim.citizens()
    count = max(len(citizens), 1)
    preference_means: dict[str, float] = {}
    preference_std: dict[str, float] = {}
    for dim in DIMENSIONS:
        values = [citizen.positions[dim] for citizen in citizens]
        mean = sum(values) / count
        variance = sum((value - mean) ** 2 for value in values) / count
        preference_means[dim] = mean
        preference_std[dim] = variance ** 0.5
    parties = []
    for party in sim.world.parties.values():
        if party.status != "active" and reason != "end":
            continue
        parties.append(
            {
                "id": party.id,
                "name": party.name,
                "status": party.status,
                "leader_id": party.leader_id,
                "members": len(party.members),
                "seats": sim.world.seats.get(party.id, 0),
                "platform": dict(party.platform),
                "founded_tick": party.founded_tick,
                "parent_id": party.parent_id,
            }
        )
    government = None
    if sim.world.government is not None:
        government = {
            "id": sim.world.government.id,
            "kind": sim.world.government.kind,
            "formateur": sim.world.government.formateur_party,
            "parties": list(sim.world.government.party_ids),
            "support": list(sim.world.government.support_ids),
        }
    sim.snapshots.append(
        {
            "tick": sim.world.tick,
            "reason": reason,
            "outcomes": dict(sim.world.outcomes),
            "parties": parties,
            "government": government,
            "active_parties": sum(1 for party in sim.active_parties()),
            "mean_satisfaction": sum(citizen.satisfaction for citizen in citizens) / count,
            "mean_engagement": sum(citizen.engagement for citizen in citizens) / count,
            "preference_means": preference_means,
            "preference_std": preference_std,
        }
    )
