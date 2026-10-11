from simdemocracy.config import DIMENSIONS, Config
from simdemocracy.engine import Simulation
from simdemocracy.models import Commitment, Government, Party
from simdemocracy.parliament import _break_commitment


def test_broken_commitment_changes_trust_and_records_a_cause() -> None:
    simulation = Simulation(Config(population=60, ticks=1, parliament_seats=21), seed=4)
    sim = simulation.sim
    citizens = sim.citizens()
    debtor_members = [citizen.id for citizen in citizens[:12]]
    creditor_members = [citizen.id for citizen in citizens[12:24]]

    def build(party_id: int, name: str, members: list[int], shift: float) -> Party:
        leader = sim.citizen(members[0])
        platform = {dim: max(-100.0, min(100.0, leader.positions[dim] + shift)) for dim in DIMENSIONS}
        party = Party(
            id=party_id,
            name=name,
            founder_id=leader.id,
            leader_id=leader.id,
            platform=platform,
            members=set(members),
            founded_tick=0,
            grace_until=0,
            promise_keeping=0.7,
        )
        sim.world.parties[party_id] = party
        for member_id in members:
            sim.citizen(member_id).party_id = party_id
        return party

    debtor = build(1, "The North Table", debtor_members, 10.0)
    creditor = build(2, "The South Table", creditor_members, -30.0)
    sim.world.seats = {1: 15, 2: 6}
    commitment = Commitment(
        id=1,
        tick=1,
        creditor_party=creditor.id,
        debtor_party=debtor.id,
        issue="tradition",
        promised_position=-40.0,
        tolerance=12.0,
        status="active",
        source_event=0,
    )
    programme = {dim: 0.0 for dim in DIMENSIONS}
    programme["tradition"] = -40.0
    government = Government(
        id=1,
        formed_tick=1,
        kind="majority",
        formateur_party=debtor.id,
        party_ids=[debtor.id, creditor.id],
        support_ids=[],
        programme=programme,
        commitments=[commitment],
        policy_multiplier=1.0,
        party_platforms={debtor.id: dict(debtor.platform), creditor.id: dict(creditor.platform)},
        formation_event=0,
    )
    sim.world.government = government
    sim.world.tick = 4
    tie = sim.tie(debtor.id, creditor.id)
    tie.trust = 0.4
    tie.hostility = 0.05
    before_trust = sim.world.outcomes["institutional_trust"]

    _break_commitment(
        sim,
        government,
        commitment,
        actual=10.0,
        private_motive="base_pressure",
        public_claim="The leadership said the commitment no longer matched its mandate.",
        probability=0.4,
        pressure=0.5,
        resistance=0.1,
    )

    assert commitment.status == "broken"
    assert debtor.promise_keeping < 0.7
    assert sim.tie(creditor.id, debtor.id).hostility > 0.05
    assert sim.tie(creditor.id, debtor.id).breaches_suffered == 1
    assert sim.world.outcomes["institutional_trust"] < before_trust
    broken = [event for event in sim.ledger.events if event.type == "commitment_broken"]
    assert len(broken) == 1
    assert broken[0].factors["private_motive"] == "base_pressure"
    assert broken[0].factors["issue"] == "tradition"
    assert "Privately the driver was base_pressure" in broken[0].summary
    assert any(item.kind == "breach_suffered" for item in sim.citizen(creditor.leader_id).memory)
