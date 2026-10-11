"""Measures used to tell emergence from noise.

These are descriptive. They are not targets the engine tries to hit.
"""

from __future__ import annotations

from simdemocracy.config import DIMENSIONS
from simdemocracy.context import Sim
from simdemocracy.events import Event
from simdemocracy.utility import signature_gap


def compute_metrics(sim: Sim) -> dict[str, object]:
    events = sim.ledger.events
    counts: dict[str, int] = {}
    for event in events:
        counts[event.type] = counts.get(event.type, 0) + 1
    elections = [event for event in events if event.type == "election_held"]
    last = elections[-1] if elections else None
    diversity = _diversity(last)
    governments = _governments(sim)
    durations = [item["duration"] for item in governments]
    # Diluted 0–1 distance averages every axis. Signature gap is the mean of
    # the three largest absolute platform differences, in points.
    distances = [
        float(item["mean_platform_distance"])
        for item in governments
        if item["parties"] > 1 and item["mean_platform_distance"] is not None
    ]
    signatures = [
        float(item["signature_gap"])
        for item in governments
        if item["parties"] > 1 and item["signature_gap"] is not None
    ]
    distant = [value for value in signatures if value >= 40.0]
    switches = sum(
        1
        for event in events
        if event.type == "member_defected"
    )
    joins = counts.get("member_joined", 0)
    population = max(len(sim.world.citizens), 1)
    influence_total = sum(citizen.influence for citizen in sim.citizens()) or 1.0
    shares = [citizen.influence / influence_total for citizen in sim.citizens()]
    top10 = sum(sorted((citizen.influence for citizen in sim.citizens()), reverse=True)[:10])
    preference_shift = _preference_shift(sim)
    major = [
        event
        for event in events
        if event.significance == "major" and event.type != "simulation_started"
    ]
    explained = sum(1 for event in major if event.factors)
    caused = sum(1 for event in major if event.causes)
    return {
        "event_counts": counts,
        "party_diversity": {
            "founded": counts.get("party_founded", 0),
            "dissolved": counts.get("party_dissolved", 0),
            "merged": counts.get("party_merged", 0),
            "split": counts.get("party_split", 0),
            "active_at_end": len(sim.active_parties()),
            "effective_number_last_election": diversity["effective"],
            "largest_vote_share_last_election": diversity["largest_share"],
            "seat_herfindahl_last_election": diversity["herfindahl"],
        },
        "organisational_turnover": {
            "founded": counts.get("party_founded", 0),
            "dissolved": counts.get("party_dissolved", 0),
            "merged": counts.get("party_merged", 0),
            "split": counts.get("party_split", 0),
            "factions": counts.get("faction_formed", 0),
        },
        "coalition_diversity": {
            "governments": len(governments),
            "multi_party": sum(1 for item in governments if item["parties"] > 1),
            "mean_platform_distance": _mean(distances),
            "mean_signature_gap": _mean(signatures),
            "distant_alliances": len(distant),
            "distant_alliance_share": (len(distant) / len(signatures)) if signatures else 0.0,
        },
        "alliance_stability": {
            "mean_duration_ticks": _mean(durations),
            "broken_commitments": counts.get("commitment_broken", 0),
            "withdrawals": counts.get("party_withdrew", 0),
            "confidence_losses": counts.get("government_lost_confidence", 0),
        },
        "political_mobility": {
            "joins": joins,
            "defections": switches,
            "defections_per_citizen": switches / population,
            "disengaged_share": sum(
                1 for citizen in sim.citizens() if citizen.engagement < 0.2
            )
            / population,
        },
        "leadership_concentration": {
            "influence_herfindahl": _herfindahl(shares),
            "top10_influence_share": top10 / influence_total,
            "leadership_changes": counts.get("leadership_changed", 0),
            "leadership_challenges": counts.get("leadership_challenge", 0),
        },
        "preference_change": preference_shift,
        "historical_causality": {
            "major_events": len(major),
            "major_with_factors": explained,
            "major_with_causes": caused,
            "factor_coverage": (explained / len(major)) if major else 1.0,
        },
        "elections": len(elections),
    }


def _diversity(election: Event | None) -> dict[str, float]:
    if election is None:
        return {"effective": 0.0, "largest_share": 0.0, "herfindahl": 0.0}
    results = election.details.get("results", [])
    if not isinstance(results, list) or not results:
        return {"effective": 0.0, "largest_share": 0.0, "herfindahl": 0.0}
    shares = [float(row["vote_share"]) for row in results if float(row["votes"]) > 0]
    herfindahl = _herfindahl(shares)
    return {
        "effective": (1.0 / herfindahl) if herfindahl > 1e-9 else 0.0,
        "largest_share": max(shares) if shares else 0.0,
        "herfindahl": herfindahl,
    }


def _governments(sim: Sim) -> list[dict[str, object]]:
    records = list(sim.world.past_governments)
    if sim.world.government is not None:
        records.append(sim.world.government)
    output = []
    for government in records:
        end = government.ended_tick if government.ended_tick is not None else sim.world.tick
        distance = None
        signature = None
        platforms = list(government.party_platforms.values())
        if len(platforms) > 1:
            gaps = []
            signatures = []
            for index, left in enumerate(platforms):
                for right in platforms[index + 1 :]:
                    gaps.append(
                        sum(abs(left[dim] - right[dim]) for dim in DIMENSIONS)
                        / (200.0 * len(DIMENSIONS))
                    )
                    signatures.append(signature_gap(left, right))
            distance = sum(gaps) / len(gaps)
            signature = sum(signatures) / len(signatures)
        output.append(
            {
                "id": government.id,
                "kind": government.kind,
                "formed_tick": government.formed_tick,
                "ended_tick": government.ended_tick,
                "duration": end - government.formed_tick,
                "parties": len(government.party_ids),
                "end_reason": government.end_reason,
                "mean_platform_distance": distance,
                "signature_gap": signature,
            }
        )
    return output


def _preference_shift(sim: Sim) -> dict[str, float]:
    deltas = []
    moved = 0
    for citizen in sim.citizens():
        initial = sim.world.initial_positions[citizen.id]
        citizen_max = 0.0
        for dim in DIMENSIONS:
            delta = abs(citizen.positions[dim] - initial[dim])
            deltas.append(delta)
            citizen_max = max(citizen_max, delta)
        if citizen_max > 10.0:
            moved += 1
    population = max(len(sim.world.citizens), 1)
    return {
        "mean_absolute_shift": _mean(deltas),
        "max_shift": max(deltas) if deltas else 0.0,
        "citizens_shifted_over_10": moved / population,
    }


def _herfindahl(shares: list[float]) -> float:
    total = sum(shares)
    if total <= 1e-9:
        return 0.0
    return sum((share / total) ** 2 for share in shares)


def _mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)
