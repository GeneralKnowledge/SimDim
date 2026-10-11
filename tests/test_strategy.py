from simdemocracy.config import Config
from simdemocracy.engine import Simulation
from simdemocracy.strategy import ActionProposal, character_report, validate_action


def test_illegal_platform_shift_is_rejected_and_a_small_one_is_not() -> None:
    simulation = Simulation(Config(population=80, ticks=8, parliament_seats=21), seed=2)
    simulation.run()
    sim = simulation.sim
    parties = sim.active_parties()
    assert parties
    party = parties[0]
    leader = sim.citizen(party.leader_id)
    leader.strategic = True
    report = character_report(sim, leader.id)
    assert report["party"]["is_leader"] is True  # type: ignore[index]

    rejected, reason = validate_action(
        sim,
        ActionProposal(leader.id, "shift_platform", {"issue": "liberty", "position": 180}, "test", "none"),
    )
    assert rejected is False
    assert "outside" in reason

    current = party.platform["liberty"]
    accepted, _message = validate_action(
        sim,
        ActionProposal(
            leader.id,
            "shift_platform",
            {"issue": "liberty", "position": current + 10},
            "test",
            "small shift",
        ),
    )
    assert accepted is True

    follower = next(citizen for citizen in sim.citizens() if citizen.id != leader.id)
    follower.strategic = True
    blocked, message = validate_action(
        sim,
        ActionProposal(follower.id, "offer_coalition", {"party_id": party.id}, "test", "none"),
    )
    assert blocked is False
    assert message


def test_unknown_action_is_rejected() -> None:
    simulation = Simulation(Config(population=40, ticks=1), seed=1)
    citizen = simulation.sim.citizens()[0]
    citizen.strategic = True
    accepted, message = validate_action(
        simulation.sim,
        ActionProposal(citizen.id, "rewrite_history", {}, "test", "none"),
    )
    assert accepted is False
    assert "Unknown action" in message
