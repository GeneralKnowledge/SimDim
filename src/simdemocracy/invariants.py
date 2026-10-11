"""Consistency checks. A broken invariant is an engine bug, not a political outcome."""

from __future__ import annotations

from simdemocracy.config import DIMENSIONS
from simdemocracy.context import Sim


def check_invariants(sim: Sim) -> None:
    world = sim.world
    for party in world.parties.values():
        if party.status != "active":
            if party.members:
                raise AssertionError(
                    f"tick {world.tick}: party {party.id} is {party.status} but still has members"
                )
            continue
        if party.leader_id not in party.members:
            raise AssertionError(
                f"tick {world.tick}: leader {party.leader_id} is not in party {party.id}"
            )
        for citizen_id in party.members:
            citizen = world.citizens[citizen_id]
            if citizen.party_id != party.id:
                raise AssertionError(
                    f"tick {world.tick}: citizen {citizen_id} listed in party {party.id} "
                    f"but party_id is {citizen.party_id}"
                )
    for citizen in world.citizens.values():
        for dim in DIMENSIONS:
            position = citizen.positions[dim]
            if position < -100.0 or position > 100.0:
                raise AssertionError(
                    f"tick {world.tick}: citizen {citizen.id} position {dim}={position}"
                )
        if citizen.party_id is None:
            continue
        party = world.parties.get(citizen.party_id)
        if party is None or party.status != "active" or citizen.id not in party.members:
            raise AssertionError(
                f"tick {world.tick}: citizen {citizen.id} points at party {citizen.party_id} illegally"
            )
    for key, value in world.outcomes.items():
        if value < -0.01 or value > 100.01:
            raise AssertionError(f"tick {world.tick}: outcome {key}={value}")
    seat_total = sum(world.seats.values())
    if seat_total > sim.config.parliament_seats:
        raise AssertionError(
            f"tick {world.tick}: {seat_total} seats exceeds parliament {sim.config.parliament_seats}"
        )
    government = world.government
    if government is None or government.ended_tick is not None:
        return
    for party_id in government.party_ids + government.support_ids:
        party = world.parties.get(party_id)
        if party is None or party.status != "active":
            raise AssertionError(
                f"tick {world.tick}: government includes inactive party {party_id}"
            )
    if government.kind == "caretaker":
        return
    majority = sim.config.parliament_seats // 2 + 1
    confidence = sum(
        world.seats.get(party_id, 0) for party_id in government.confidence_ids()
    )
    if confidence < majority:
        raise AssertionError(
            f"tick {world.tick}: {government.kind} government has {confidence} "
            f"confidence seats, majority is {majority}"
        )
