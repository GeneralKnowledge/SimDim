"""Create a blank Commonwealth.

Latent preference clusters are unlabelled. They give citizens neighbours in
policy space so organisation is possible. They are not parties, ideologies,
or roles.
"""

from __future__ import annotations

from simdemocracy.config import DIMENSIONS, Config
from simdemocracy.models import Citizen, Relationship, World
from simdemocracy.names import citizen_names
from simdemocracy.rng import Streams
from simdemocracy.utility import alignment, clamp, clamp01


def _gamma_weights(rng: object, count: int, alpha: float) -> list[float]:
    draws = [rng.gammavariate(alpha, 1.0) for _ in range(count)]  # type: ignore[attr-defined]
    total = sum(draws)
    return [draw / total for draw in draws]


def _place_centers(rng: object, groups: int) -> list[dict[str, float]]:
    """Unlabelled basins. Each basin is extreme on different axes so constituencies
    can form. The axes are not named ideologies, and citizens still vary inside them.
    """

    centers: list[dict[str, float]] = []
    for index in range(groups):
        center = {dim: rng.uniform(-18.0, 18.0) for dim in DIMENSIONS}  # type: ignore[attr-defined]
        primary = DIMENSIONS[index % len(DIMENSIONS)]
        secondary = DIMENSIONS[(index * 3 + 2) % len(DIMENSIONS)]
        sign = 1.0 if index % 2 == 0 else -1.0
        center[primary] = clamp(sign * rng.uniform(62.0, 90.0), -100.0, 100.0)  # type: ignore[attr-defined]
        center[secondary] = clamp(-sign * rng.uniform(48.0, 84.0), -100.0, 100.0)  # type: ignore[attr-defined]
        tertiary = DIMENSIONS[(index * 5 + 1) % len(DIMENSIONS)]
        if tertiary not in {primary, secondary}:
            pole = 1.0 if index % 3 else -1.0
            center[tertiary] = clamp(pole * rng.uniform(28.0, 58.0), -100.0, 100.0)  # type: ignore[attr-defined]
        centers.append(center)
    return centers


def _skew(rng: object, power: float) -> float:
    return rng.random() ** power  # type: ignore[attr-defined]


def generate_world(config: Config, rng: Streams) -> World:
    gen = rng.gen
    centers = _place_centers(gen, config.latent_groups)
    weights = _gamma_weights(gen, config.latent_groups, 1.35)
    names = citizen_names(rng.names, config.population)
    citizens: dict[int, Citizen] = {}

    for index in range(config.population):
        group = _weighted_index(gen, weights)
        center = centers[group]
        positions = {
            dim: clamp(
                center[dim] + gen.gauss(0.0, config.preference_noise),
                -100.0,
                100.0,
            )
            for dim in DIMENSIONS
        }
        resources = clamp01(gen.random() ** 1.15)
        service_reliance = clamp01(1.0 - resources + gen.uniform(-0.18, 0.18))
        exposure = gen.random()
        positions["distribution"] = clamp(
            positions["distribution"] + (0.45 - resources) * 14.0,
            -100.0,
            100.0,
        )
        positions["public_services"] = clamp(
            positions["public_services"] + (service_reliance - 0.5) * 10.0,
            -100.0,
            100.0,
        )
        positions["ecology"] = clamp(
            positions["ecology"] + (exposure - 0.4) * 8.0,
            -100.0,
            100.0,
        )
        importance = {
            dim: clamp01(
                0.05 + 0.2 * gen.random() + 0.72 * (abs(positions[dim]) / 100.0) ** 0.8
            )
            for dim in DIMENSIONS
        }
        extremes = sorted(DIMENSIONS, key=lambda dim: abs(positions[dim]), reverse=True)
        importance[extremes[0]] = clamp01(importance[extremes[0]] + 0.22)
        importance[extremes[1]] = clamp01(importance[extremes[1]] + 0.12)
        importance["distribution"] = clamp01(
            importance["distribution"] + (0.18 if resources < 0.35 else 0.0)
        )
        importance["public_services"] = clamp01(
            importance["public_services"] + 0.16 * service_reliance
        )
        importance["ecology"] = clamp01(importance["ecology"] + 0.22 * exposure)
        certainty = {
            dim: clamp01(0.2 + 0.65 * gen.random() * (0.45 + 0.55 * importance[dim]))
            for dim in DIMENSIONS
        }
        compromise = _skew(gen, 1.15)
        rigidity = clamp01(0.65 * (1.0 - compromise) + 0.35 * gen.random())
        non_negotiable: list[str] = []
        if rigidity > 0.62:
            ranked = sorted(
                DIMENSIONS,
                key=lambda dim: importance[dim] * (0.4 + abs(positions[dim]) / 100.0),
                reverse=True,
            )
            for dim in ranked:
                if importance[dim] < 0.68:
                    break
                non_negotiable.append(dim)
                if len(non_negotiable) >= (2 if rigidity > 0.82 else 1):
                    break
        ambition = _skew(gen, 1.7)
        attentiveness = _skew(gen, 1.25)
        sociability = _skew(gen, 1.1)
        influence = clamp01(
            0.12 + 0.34 * ambition + 0.24 * sociability + 0.16 * resources + 0.1 * gen.random()
        )
        engagement = clamp01(0.22 + 0.38 * attentiveness + 0.2 * ambition + 0.12 * gen.random())
        citizens[index] = Citizen(
            id=index,
            name=names[index],
            ambition=ambition,
            risk_tolerance=gen.random(),
            loyalty=_skew(gen, 0.9),
            sociability=sociability,
            conformity=gen.random(),
            compromise=compromise,
            ideological_rigidity=rigidity,
            stubbornness=_skew(gen, 1.3),
            attentiveness=attentiveness,
            overconfidence=_skew(gen, 1.4),
            positions=positions,
            importance=importance,
            certainty=certainty,
            non_negotiable=non_negotiable,
            resources=resources,
            public_service_reliance=service_reliance,
            environmental_exposure=exposure,
            engagement=engagement,
            satisfaction=0.55,
            influence=influence,
        )

    _mark_strategic(citizens, config.strategic_characters)
    relationships, neighbors = _relationships(citizens, config, rng.social)
    satisfactions = [citizen.satisfaction for citizen in citizens.values()]
    mean_satisfaction = sum(satisfactions) / len(satisfactions)
    return World(
        tick=0,
        citizens=citizens,
        parties={},
        relationships=relationships,
        neighbors=neighbors,
        ties={},
        used_party_names=set(),
        seats={},
        outcomes={
            "material_wellbeing": 55.0,
            "service_quality": 50.0,
            "stability": 62.0,
            "environment": 50.0,
            "institutional_trust": 58.0,
            "treasury": 60.0,
        },
        initial_positions={
            cid: dict(citizen.positions) for cid, citizen in citizens.items()
        },
        mean_satisfaction=mean_satisfaction,
        mean_welfare=mean_satisfaction,
        previous_mean_welfare=mean_satisfaction,
    )


def _mark_strategic(citizens: dict[int, Citizen], count: int) -> None:
    ranked = sorted(citizens.values(), key=lambda citizen: (-citizen.ambition, citizen.id))
    for citizen in ranked[:count]:
        citizen.strategic = True


def _weighted_index(rng: object, weights: list[float]) -> int:
    roll = rng.random()  # type: ignore[attr-defined]
    cursor = 0.0
    for index, weight in enumerate(weights):
        cursor += weight
        if roll <= cursor:
            return index
    return len(weights) - 1


def _relationships(
    citizens: dict[int, Citizen],
    config: Config,
    rng: object,
) -> tuple[dict[tuple[int, int], Relationship], dict[int, list[int]]]:
    relationships: dict[tuple[int, int], Relationship] = {}
    neighbors: dict[int, list[int]] = {cid: [] for cid in citizens}
    ids = sorted(citizens)
    for source_id in ids:
        source = citizens[source_id]
        degree = 2 + int(source.sociability * 8)
        scored: list[tuple[float, int]] = []
        for target_id in ids:
            if target_id == source_id:
                continue
            similarity = alignment(source.positions, citizens[target_id].positions)
            jitter = rng.random()  # type: ignore[attr-defined]
            score = config.homophily * similarity + (1.0 - config.homophily) * jitter
            scored.append((score, target_id))
        scored.sort(key=lambda item: (-item[0], item[1]))
        for _score, target_id in scored[:degree]:
            similarity = alignment(source.positions, citizens[target_id].positions)
            trust = clamp(
                -0.05 + 0.85 * similarity + rng.uniform(-0.18, 0.15),  # type: ignore[attr-defined]
                -1.0,
                1.0,
            )
            affinity = clamp(
                -0.05 + 0.7 * similarity + rng.uniform(-0.2, 0.2),  # type: ignore[attr-defined]
                -1.0,
                1.0,
            )
            rivalry = clamp(max(0.0, -affinity) + (0.15 if trust < -0.1 else 0.0), 0.0, 1.0)
            relationships[(source_id, target_id)] = Relationship(
                trust=trust,
                affinity=affinity,
                rivalry=rivalry,
            )
            neighbors[source_id].append(target_id)
    return relationships, neighbors
