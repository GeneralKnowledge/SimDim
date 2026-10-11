"""Policy consequences and preference feedback.

The equations are deliberately small. They exist so a choice has a trade-off
and so tomorrow's electorate is not a copy of today's.
"""

from __future__ import annotations

from simdemocracy.config import DIMENSIONS
from simdemocracy.context import Sim
from simdemocracy.models import Citizen
from simdemocracy.utility import alignment, clamp, clamp01, median


def step_outcomes(
    outcomes: dict[str, float],
    applied: dict[str, float],
    strength: float,
    promise_keeping: float,
) -> tuple[dict[str, float], dict[str, float]]:
    """Move social indicators. Inputs on the policy axes are -100..100."""

    unit = {dim: applied[dim] / 100.0 for dim in DIMENSIONS}
    tax = unit["taxation"]
    services = unit["public_services"]
    ecology = unit["ecology"]
    distribution = unit["distribution"]
    authority = unit["authority"]
    liberty = unit["liberty"]
    tradition = unit["tradition"]

    updated = dict(outcomes)
    treasury_delta = strength * (
        3.0 * tax
        - 2.4 * max(services, 0.0)
        - 1.3 * max(ecology, 0.0)
        - 0.5 * max(distribution, 0.0)
    )
    updated["treasury"] = clamp(updated["treasury"] + treasury_delta, 0.0, 100.0)

    funding_gap = 0.0
    if services > 0.0 and updated["treasury"] < 28.0:
        funding_gap = (28.0 - updated["treasury"]) / 28.0
    effective_services = services * (1.0 - 0.75 * funding_gap)
    service_target = 50.0 + 30.0 * effective_services
    material_delta = strength * (
        -1.05 * max(ecology, 0.0)
        + 0.7 * max(-ecology, 0.0)
        - 0.55 * max(tax, 0.0)
        + 0.2 * max(-tax, 0.0)
    )
    env_target = 50.0 + 32.0 * ecology
    stability_target = clamp(
        56.0 + 14.0 * authority + 10.0 * tradition - 5.0 * max(liberty, 0.0) * max(0.0, 0.4 - authority),
        0.0,
        100.0,
    )
    trust_target = clamp(
        52.0
        + 8.0 * liberty
        - 9.0 * max(authority, 0.0)
        + 16.0 * (promise_keeping - 0.5),
        0.0,
        100.0,
    )

    deltas = {
        "treasury": updated["treasury"] - outcomes["treasury"],
        "material_wellbeing": strength * 0.0,
        "service_quality": 0.0,
        "environment": 0.0,
        "stability": 0.0,
        "institutional_trust": 0.0,
    }
    updated["material_wellbeing"] = clamp(
        updated["material_wellbeing"] + material_delta, 0.0, 100.0
    )
    updated["service_quality"] = clamp(
        updated["service_quality"] + strength * 0.28 * (service_target - updated["service_quality"]),
        0.0,
        100.0,
    )
    updated["environment"] = clamp(
        updated["environment"] + strength * 0.22 * (env_target - updated["environment"]),
        0.0,
        100.0,
    )
    updated["stability"] = clamp(
        updated["stability"] + strength * 0.18 * (stability_target - updated["stability"]),
        0.0,
        100.0,
    )
    updated["institutional_trust"] = clamp(
        updated["institutional_trust"] + strength * 0.16 * (trust_target - updated["institutional_trust"]),
        0.0,
        100.0,
    )
    for key in updated:
        deltas[key] = updated[key] - outcomes[key]
    return updated, deltas


def personal_welfare(
    citizen: Citizen,
    outcomes: dict[str, float],
    applied: dict[str, float],
) -> float:
    material = outcomes["material_wellbeing"] / 100.0
    distribution = applied["distribution"] / 100.0
    tax = applied["taxation"] / 100.0
    if citizen.resources < 0.45:
        personal_material = material + 0.14 * distribution - 0.04 * max(tax, 0.0)
    else:
        personal_material = material - 0.16 * distribution - 0.1 * max(tax, 0.0)
    services = outcomes["service_quality"] / 100.0
    if citizen.public_service_reliance >= 0.5:
        personal_services = services
    else:
        personal_services = 0.6 * services + 0.4 * (1.0 - max(applied["public_services"], 0.0) / 100.0)
    environment = outcomes["environment"] / 100.0
    env_weight = citizen.importance["ecology"]
    personal_env = environment * env_weight + (1.0 - env_weight) * 0.55
    fit = alignment(citizen.positions, applied, citizen.importance)
    welfare = (
        0.30 * clamp01(personal_material)
        + 0.22 * clamp01(personal_services)
        + 0.12 * personal_env
        + 0.12 * outcomes["stability"] / 100.0
        + 0.08 * outcomes["institutional_trust"] / 100.0
        + 0.16 * fit
    )
    return clamp01(welfare)


def adapt_preferences(
    citizen: Citizen,
    outcomes: dict[str, float],
    applied: dict[str, float] | None,
    rate: float,
) -> dict[str, float]:
    """Return position deltas. Stubborn citizens move less. Conformists drift toward the programme."""

    if rate <= 0.0:
        return {}
    personal_rate = rate * (1.0 - 0.82 * citizen.stubbornness)
    changes: dict[str, float] = {}
    nudges = _experience_nudges(citizen, outcomes, applied)
    for dim in DIMENSIONS:
        delta = nudges.get(dim, 0.0) * personal_rate
        if applied is not None:
            gap = applied[dim] - citizen.positions[dim]
            delta += gap * 0.012 * citizen.conformity * rate
        delta *= 1.05 - citizen.certainty.get(dim, 0.5)
        delta = clamp(delta, -1.25, 1.25)
        if abs(delta) < 0.01:
            continue
        updated = clamp(citizen.positions[dim] + delta, -100.0, 100.0)
        applied_delta = updated - citizen.positions[dim]
        if abs(applied_delta) < 0.01:
            continue
        citizen.positions[dim] = updated
        if abs(applied_delta) > 0.2:
            citizen.importance[dim] = clamp01(citizen.importance[dim] + 0.008)
        changes[dim] = applied_delta
    return changes


def _experience_nudges(
    citizen: Citizen,
    outcomes: dict[str, float],
    applied: dict[str, float] | None,
) -> dict[str, float]:
    nudges = {dim: 0.0 for dim in DIMENSIONS}
    if citizen.resources < 0.4 and outcomes["material_wellbeing"] < 50.0:
        nudges["distribution"] += 0.45
        if outcomes["service_quality"] < 48.0:
            nudges["public_services"] += 0.25
            nudges["taxation"] += 0.15
    if citizen.resources > 0.7 and applied is not None and applied["distribution"] > 25.0:
        nudges["distribution"] -= 0.35
        nudges["taxation"] -= 0.2
    if citizen.public_service_reliance > 0.6 and outcomes["service_quality"] < 46.0:
        nudges["public_services"] += 0.5
    if (
        citizen.public_service_reliance < 0.3
        and citizen.resources > 0.6
        and applied is not None
        and applied["taxation"] > 25.0
    ):
        nudges["taxation"] -= 0.3
        nudges["public_services"] -= 0.15
    if citizen.environmental_exposure > 0.6 and outcomes["environment"] < 46.0:
        nudges["ecology"] += 0.5
    if (
        citizen.resources < 0.45
        and applied is not None
        and applied["ecology"] > 35.0
        and outcomes["material_wellbeing"] < 48.0
    ):
        nudges["ecology"] -= 0.3
    if outcomes["institutional_trust"] < 46.0:
        if citizen.positions["liberty"] > 0.0:
            nudges["authority"] -= 0.3
            nudges["liberty"] += 0.15
        else:
            nudges["authority"] += 0.12
    if outcomes["stability"] < 42.0 and citizen.conformity > 0.55:
        nudges["tradition"] += 0.35
        nudges["authority"] += 0.15
    return nudges


def member_median(sim: Sim, party_id: int, issue: str) -> float:
    party = sim.party(party_id)
    return median([sim.citizen(cid).positions[issue] for cid in party.members])
