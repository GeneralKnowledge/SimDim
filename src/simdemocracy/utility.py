"""Decision formulas.

Components stay on a shared scale so personality weights are meaningful.
Stochastic gates live with the caller; these functions are pure.
"""

from __future__ import annotations

import math

from simdemocracy.config import DIMENSIONS, Config
from simdemocracy.models import Citizen, Party


def clamp(value: float, lo: float, hi: float) -> float:
    if value < lo:
        return lo
    if value > hi:
        return hi
    return value


def clamp01(value: float) -> float:
    return clamp(value, 0.0, 1.0)


def median(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return 0.5 * (ordered[mid - 1] + ordered[mid])


def policy_distance(
    left: dict[str, float],
    right: dict[str, float],
    weights: dict[str, float] | None = None,
    issues: list[str] | None = None,
) -> float:
    """0 is identical, 1 is opposite poles. Missing issues are ignored."""

    keys = issues if issues is not None else list(DIMENSIONS)
    weighted = 0.0
    weight_sum = 0.0
    for key in keys:
        if key not in left or key not in right:
            continue
        weight = 1.0 if weights is None else weights.get(key, 0.0)
        if weight <= 0.0:
            continue
        weighted += weight * abs(left[key] - right[key]) / 200.0
        weight_sum += weight
    if weight_sum <= 1e-9:
        return 0.5
    return weighted / weight_sum


def alignment(
    left: dict[str, float],
    right: dict[str, float],
    weights: dict[str, float] | None = None,
    issues: list[str] | None = None,
) -> float:
    return 1.0 - policy_distance(left, right, weights, issues)


def priority_issues(importance: dict[str, float], count: int = 3) -> list[str]:
    return sorted(DIMENSIONS, key=lambda dim: importance.get(dim, 0.0), reverse=True)[:count]


def priority_alignment(
    left: dict[str, float],
    right: dict[str, float],
    importance: dict[str, float],
    count: int = 3,
) -> float:
    """Agreement on the issues the citizen actually weighs, not the mean of all eight."""

    return alignment(left, right, issues=priority_issues(importance, count))


def signature_gap(left: dict[str, float], right: dict[str, float], count: int = 3) -> float:
    """Mean absolute gap, in points, on the dimensions where two platforms differ most."""

    gaps = sorted((abs(left[dim] - right[dim]) for dim in DIMENSIONS), reverse=True)[:count]
    if not gaps:
        return 0.0
    return sum(gaps) / len(gaps)


def known_issues_for(citizen: Citizen, attentive_cutoff: float = 0.45) -> list[str]:
    if citizen.attentiveness >= 0.82:
        return list(DIMENSIONS)
    ranked = sorted(DIMENSIONS, key=lambda key: citizen.importance[key], reverse=True)
    if citizen.attentiveness < attentive_cutoff:
        return ranked[:3]
    return [key for key in DIMENSIONS if citizen.importance[key] >= 0.28] or ranked[:4]


def vote_utility(
    citizen: Citizen,
    platform: dict[str, float],
    issues: list[str],
    trust: float,
    competence: float,
    promise_keeping: float,
    loyalty: float,
    config: Config,
) -> dict[str, float | list[str]]:
    """V = -sum w|p-q| + η T + θ R + ρ L, with components scaled to be comparable."""

    distance = policy_distance(citizen.positions, platform, citizen.importance, issues)
    policy_term = -2.0 * distance
    ideology = 0.65 + 0.7 * citizen.ideological_rigidity
    follow = (1.0 - citizen.attentiveness) * 0.55 + citizen.conformity * 0.35
    eta = (0.12 + 0.5 * follow) * config.relationship_influence
    theta = 0.18 + 0.16 * (1.0 - citizen.ideological_rigidity)
    rho = (0.08 + 0.42 * citizen.loyalty) * config.relationship_influence
    trust_term = clamp01(trust)
    reputation = clamp01(0.55 * competence + 0.45 * promise_keeping)
    loyalty_term = clamp01(loyalty)
    utility = ideology * policy_term + eta * trust_term + theta * reputation + rho * loyalty_term
    return {
        "utility": utility,
        "policy": policy_term,
        "trust": trust_term,
        "competence": reputation,
        "loyalty": loyalty_term,
        "ideology_weight": ideology,
        "trust_weight": eta,
        "competence_weight": theta,
        "loyalty_weight": rho,
        "issues": issues,
    }


def independence_utility(citizen: Citizen, config: Config) -> float:
    return (
        0.40
        + 0.26 * (1.0 - citizen.conformity)
        + 0.16 * citizen.ideological_rigidity
        - 0.12 * citizen.ambition * config.ambition_scale
        + 0.18 * citizen.disappointment
    )


def join_utility(
    citizen: Citizen,
    party: Party,
    *,
    social: float,
    trust: float,
    seat_share: float,
    config: Config,
    current: bool = False,
) -> dict[str, float]:
    issues = known_issues_for(citizen)
    fit = alignment(citizen.positions, party.platform, citizen.importance, issues)
    disagreement = 1.0 - fit
    non_negotiable_hit = 0.0
    for issue in citizen.non_negotiable:
        if abs(citizen.positions[issue] - party.platform[issue]) > 40.0:
            non_negotiable_hit += 1.0
    cost = disagreement * (0.30 + 0.7 * citizen.ideological_rigidity)
    cost += 0.28 * non_negotiable_hit
    influence = clamp01(0.12 + 0.45 * party.attention + 0.4 * seat_share)
    influence *= 0.65 + 0.7 * citizen.overconfidence
    influence = clamp(influence, 0.0, 1.35)
    policy_weight = 0.42 + 0.55 * citizen.ideological_rigidity
    social_weight = (0.12 + 0.5 * citizen.sociability) * config.relationship_influence
    trust_weight = 0.18 + 0.32 * citizen.loyalty
    influence_weight = (0.12 + 0.62 * citizen.ambition) * config.ambition_scale
    utility = (
        policy_weight * fit
        + social_weight * clamp01(social)
        + trust_weight * clamp01(trust)
        + influence_weight * influence
        - cost
    )
    if current:
        utility -= 0.32 * citizen.disappointment
    return {
        "utility": utility,
        "policy_fit": fit,
        "social": social,
        "trust": trust,
        "influence": influence,
        "cost": cost,
        "non_negotiable_hits": non_negotiable_hit,
        "policy_weight": policy_weight,
        "social_weight": social_weight,
        "trust_weight": trust_weight,
        "influence_weight": influence_weight,
    }


def founding_probability(
    citizen: Citizen,
    cluster_size: int,
    nearest_alignment: float,
    config: Config,
) -> float:
    if citizen.party_id is not None or citizen.engagement < 0.28:
        return 0.0
    ambition = citizen.ambition * config.ambition_scale
    if ambition < 0.58 or cluster_size < config.min_cluster:
        return 0.0
    if nearest_alignment > config.represented_alignment:
        return 0.0
    opportunity = clamp01((cluster_size - config.min_cluster) / 16.0)
    gap = clamp01(
        (config.represented_alignment - nearest_alignment)
        / max(config.represented_alignment, 1e-6)
    )
    cost = config.party_formation_cost * (1.1 - 0.45 * citizen.risk_tolerance)
    skill = 0.45 * ambition + 0.25 * citizen.sociability + 0.30 * citizen.influence
    raw = 0.85 * opportunity + 0.75 * gap + skill - cost
    probability = 1.0 / (1.0 + math.exp(-5.2 * (raw - 0.52)))
    return clamp(probability, 0.0, 0.62)


def alliance_value(
    *,
    evaluator: Citizen,
    policy_agreement: float,
    power_benefit: float,
    leader_trust: float,
    shared_enemy: float,
    hostility: float,
    supporter_cost: float,
    config: Config,
) -> dict[str, float]:
    """A_ij from one leader's point of view. Trust and hostility are signed inputs.

    leader_trust is -1..1. hostility and the benefit terms are 0..1.
    """

    alpha = 0.32 + 0.58 * evaluator.ideological_rigidity
    beta = (0.18 + 0.7 * evaluator.ambition * (0.35 + 0.65 * evaluator.compromise)) * (
        config.ambition_scale
    )
    gamma = (0.22 + 0.48 * evaluator.loyalty) * max(config.relationship_influence, 0.15)
    # Relationship influence of 0 should also dull personal trust, but a floor
    # keeps the term defined. Callers zero leader_trust when relationships are off.
    delta = 0.18 + 0.28 * evaluator.risk_tolerance
    lam = 0.22 + 0.62 * (1.0 - evaluator.compromise)
    mu = 0.18 + 0.58 * evaluator.ideological_rigidity
    if config.relationship_influence <= 0.0:
        gamma = 0.0
        leader_trust = 0.0
    value = (
        alpha * policy_agreement
        + beta * power_benefit
        + gamma * leader_trust
        + delta * shared_enemy
        - lam * hostility
        - mu * supporter_cost
    )
    return {
        "value": value,
        "policy": policy_agreement,
        "power": power_benefit,
        "trust": leader_trust,
        "shared_enemy": shared_enemy,
        "hostility": hostility,
        "supporter_cost": supporter_cost,
        "alpha": alpha,
        "beta": beta,
        "gamma": gamma,
        "delta": delta,
        "lambda": lam,
        "mu": mu,
    }


def non_negotiable_veto(leader: Citizen, programme: dict[str, float]) -> str | None:
    tolerance = 24.0 + 30.0 * leader.compromise * (1.0 - 0.45 * leader.ideological_rigidity)
    for issue in leader.non_negotiable:
        gap = abs(programme.get(issue, 0.0) - leader.positions[issue])
        if gap > tolerance:
            return issue
    return None


def memory_valence(
    citizen: Citizen,
    party_id: int,
    tick: int,
    half_life: float,
) -> float:
    weighted = 0.0
    weight_sum = 0.0
    for item in citizen.memory:
        if item.subject != party_id:
            continue
        age = max(0, tick - item.tick)
        recency = 0.5 ** (age / max(half_life, 1.0))
        weighted += recency * item.valence * item.weight
        weight_sum += recency
    if weight_sum <= 1e-9:
        return 0.0
    value = weighted / weight_sum
    if value < 0.0 and citizen.stubbornness > 0.55 and citizen.party_id == party_id:
        value *= 1.0 - 0.7 * citizen.stubbornness
    return clamp(value, -1.0, 1.0)
