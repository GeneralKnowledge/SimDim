from simdemocracy.config import Config
from simdemocracy.engine import Simulation
from simdemocracy.explain import chronicle, explain


def test_explain_walks_recorded_causes() -> None:
    simulation = Simulation(Config(population=100, ticks=24, parliament_seats=31), seed=9)
    simulation.run()
    formed = next(event for event in simulation.sim.ledger.events if event.type == "government_formed")
    account = explain(simulation.sim.ledger.events, formed.id)
    assert account["event"]["id"] == formed.id  # type: ignore[index]
    for cause in formed.causes:
        assert any(item["id"] == cause for item in account["because"])  # type: ignore[index]
    text = chronicle(simulation.sim.ledger.events)
    assert "Week" in text
    assert "Commonwealth chronicle" in text
    assert formed.summary in text
