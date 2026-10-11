from simdemocracy.config import DIMENSIONS, Config
from simdemocracy.engine import Simulation
from simdemocracy.events import assert_causal
from simdemocracy.metrics import compute_metrics
from simdemocracy.policy import adapt_preferences


def _fingerprint(seed: int, ticks: int = 24) -> list[tuple[object, ...]]:
    simulation = Simulation(Config(population=80, ticks=ticks, parliament_seats=31), seed=seed)
    simulation.run()
    assert_causal(simulation.sim.ledger.events)
    return [
        (event.type, event.tick, event.summary, tuple(sorted(event.factors.items(), key=lambda item: str(item[0]))))
        for event in simulation.sim.ledger.events
    ]


def test_same_seed_replays() -> None:
    assert _fingerprint(4) == _fingerprint(4)


def test_different_seeds_diverge() -> None:
    assert _fingerprint(4) != _fingerprint(5)


def test_no_ambition_means_no_parties() -> None:
    simulation = Simulation(
        Config(population=80, ticks=18, parliament_seats=21, ambition_scale=0.0),
        seed=2,
    )
    simulation.run()
    assert not any(event.type == "party_founded" for event in simulation.sim.ledger.events)


def test_population_is_not_homogeneous() -> None:
    simulation = Simulation(Config(population=120, ticks=1, parliament_seats=31), seed=6)
    citizens = simulation.sim.citizens()
    for dim in DIMENSIONS:
        values = [citizen.positions[dim] for citizen in citizens]
        mean = sum(values) / len(values)
        variance = sum((value - mean) ** 2 for value in values) / len(values)
        assert variance ** 0.5 > 15.0
    ambitions = {round(citizen.ambition, 3) for citizen in citizens}
    assert len(ambitions) > 20


def test_frozen_preferences_stay_put() -> None:
    simulation = Simulation(
        Config(population=80, ticks=24, parliament_seats=31, preference_adaptation=0.0),
        seed=3,
    )
    simulation.run()
    for citizen in simulation.sim.citizens():
        assert citizen.positions == simulation.sim.world.initial_positions[citizen.id]


def test_adapt_preferences_respects_a_zero_rate() -> None:
    simulation = Simulation(Config(population=40, ticks=1), seed=1)
    citizen = simulation.sim.citizens()[0]
    before = dict(citizen.positions)
    applied = {dim: 80.0 for dim in DIMENSIONS}
    assert adapt_preferences(citizen, simulation.sim.world.outcomes, applied, 0.0) == {}
    assert citizen.positions == before


def test_default_history_has_elections_and_explanations() -> None:
    simulation = Simulation(Config(ticks=36), seed=3)
    simulation.run()
    elections = [event for event in simulation.sim.ledger.events if event.type == "election_held"]
    assert {12, 24, 36} <= {event.tick for event in elections}
    for event in elections:
        awarded = sum(int(row["seats"]) for row in event.details["results"])  # type: ignore[index]
        assert awarded == simulation.config.parliament_seats
    metrics = compute_metrics(simulation.sim)
    diversity = metrics["party_diversity"]
    causality = metrics["historical_causality"]
    assert isinstance(diversity, dict)
    assert isinstance(causality, dict)
    assert int(diversity["founded"]) >= 2
    assert float(causality["factor_coverage"]) == 1.0
    # Scheduled elections plus any confidence-triggered early election.
    assert int(metrics["elections"]) >= 3
