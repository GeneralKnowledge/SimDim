from simdemocracy.config import DIMENSIONS, Config
from simdemocracy.models import Citizen
from simdemocracy.utility import (
    founding_probability,
    priority_alignment,
    signature_gap,
    vote_utility,
)


def _citizen(**overrides: object) -> Citizen:
    positions = {dim: 0.0 for dim in DIMENSIONS}
    importance = {dim: 0.5 for dim in DIMENSIONS}
    base = dict(
        id=1,
        name="Ada Hale",
        ambition=0.8,
        risk_tolerance=0.5,
        loyalty=0.5,
        sociability=0.5,
        conformity=0.4,
        compromise=0.4,
        ideological_rigidity=0.6,
        stubbornness=0.2,
        attentiveness=0.7,
        overconfidence=0.3,
        positions=positions,
        importance=importance,
        certainty={dim: 0.5 for dim in DIMENSIONS},
        non_negotiable=[],
        resources=0.5,
        public_service_reliance=0.5,
        environmental_exposure=0.4,
        engagement=0.6,
        satisfaction=0.5,
        influence=0.4,
    )
    base.update(overrides)
    return Citizen(**base)  # type: ignore[arg-type]


def test_founding_requires_ambition_and_a_cluster() -> None:
    config = Config()
    citizen = _citizen(ambition=0.2)
    assert founding_probability(citizen, 40, 0.2, config) == 0.0
    ambitious = _citizen(ambition=0.9, engagement=0.8, influence=0.7, sociability=0.6)
    low = founding_probability(ambitious, 4, 0.2, config)
    high = founding_probability(ambitious, 40, 0.2, config)
    assert low == 0.0
    assert high > 0.2


def test_higher_formation_cost_lowers_probability() -> None:
    citizen = _citizen(
        ambition=0.62,
        engagement=0.45,
        influence=0.3,
        sociability=0.2,
        risk_tolerance=0.1,
    )
    cheap = founding_probability(citizen, 12, 0.7, Config(party_formation_cost=0.3))
    costly = founding_probability(citizen, 12, 0.7, Config(party_formation_cost=0.95))
    assert 0.0 < cheap < 0.62
    assert costly < cheap


def test_zero_ambition_scale_blocks_founding() -> None:
    citizen = _citizen(ambition=0.95, engagement=0.9)
    assert founding_probability(citizen, 40, 0.1, Config(ambition_scale=0.0)) == 0.0


def test_relationship_influence_removes_trust_from_the_vote() -> None:
    citizen = _citizen()
    platform = {dim: 20.0 for dim in DIMENSIONS}
    social = vote_utility(citizen, platform, list(DIMENSIONS), 0.9, 0.5, 0.5, 0.8, Config())
    solitary = vote_utility(
        citizen,
        platform,
        list(DIMENSIONS),
        0.9,
        0.5,
        0.5,
        0.8,
        Config(relationship_influence=0.0),
    )
    assert float(social["trust_weight"]) > 0
    assert float(solitary["trust_weight"]) == 0.0
    assert float(solitary["loyalty_weight"]) == 0.0
    assert float(social["utility"]) != float(solitary["utility"])


def test_signature_gap_uses_the_largest_disagreements() -> None:
    left = {dim: 0.0 for dim in DIMENSIONS}
    right = {dim: 0.0 for dim in DIMENSIONS}
    right["ecology"] = 90.0
    right["taxation"] = -60.0
    assert signature_gap(left, left) == 0.0
    assert signature_gap(left, right) == (90.0 + 60.0) / 3.0


def test_priority_alignment_ignores_unimportant_axes() -> None:
    left = {dim: 0.0 for dim in DIMENSIONS}
    right = {dim: 0.0 for dim in DIMENSIONS}
    right["tradition"] = 100.0
    importance = {dim: 0.1 for dim in DIMENSIONS}
    importance["distribution"] = 0.9
    importance["taxation"] = 0.8
    importance["liberty"] = 0.7
    assert priority_alignment(left, right, importance) == 1.0
