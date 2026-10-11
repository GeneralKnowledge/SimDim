"""Voting and seat allocation.

Citizens score parties they actually know. Seat arithmetic is deterministic
code: D'Hondt or Sainte-Laguë. A character cannot declare a winner.
"""

from __future__ import annotations

from simdemocracy.config import DIMENSIONS
from simdemocracy.context import Sim
from simdemocracy.models import Citizen, Party
from simdemocracy.utility import clamp01, known_issues_for, memory_valence, vote_utility


def allocate_seats(
    votes: dict[int, int],
    seats: int,
    system: str,
    threshold: float,
) -> dict[int, int]:
    result = {party_id: 0 for party_id in votes}
    total_votes = sum(votes.values())
    if total_votes <= 0 or seats <= 0:
        return result
    eligible = [
        party_id
        for party_id, count in votes.items()
        if count > 0 and (count / total_votes) >= threshold - 1e-15
    ]
    if not eligible:
        return result

    def divisor(already: int) -> int:
        if system == "dhondt":
            return already + 1
        if system == "sainte_lague":
            return 2 * already + 1
        raise ValueError(f"Unknown electoral system: {system}")

    allocated = {party_id: 0 for party_id in eligible}
    for _ in range(seats):
        winner = max(
            eligible,
            key=lambda party_id: (
                votes[party_id] / divisor(allocated[party_id]),
                votes[party_id],
                -party_id,
            ),
        )
        allocated[winner] += 1
    for party_id, count in allocated.items():
        result[party_id] = count
    return result


def hold_election(sim: Sim) -> dict[str, object]:
    world = sim.world
    parties = sim.active_parties()
    votes: dict[int, int] = {party.id: 0 for party in parties}
    abstain = {"low_engagement": 0, "no_known_party": 0, "none_acceptable": 0}
    followed = 0
    considered = 0
    component_totals: dict[int, dict[str, float]] = {
        party.id: {"policy": 0.0, "trust": 0.0, "competence": 0.0, "loyalty": 0.0, "n": 0.0}
        for party in parties
    }

    for citizen in sim.citizens():
        choice, reason, parts = _choose(sim, citizen, parties)
        if choice is None:
            abstain[reason] = abstain.get(reason, 0) + 1
            citizen.last_vote = None
            continue
        votes[choice] += 1
        citizen.last_vote = choice
        considered += 1
        if reason == "followed_trusted":
            followed += 1
        if parts is not None:
            bucket = component_totals[choice]
            bucket["policy"] += float(parts["policy"])
            bucket["trust"] += float(parts["trust"])
            bucket["competence"] += float(parts["competence"])
            bucket["loyalty"] += float(parts["loyalty"])
            bucket["n"] += 1.0

    seat_map = allocate_seats(
        votes,
        sim.config.parliament_seats,
        sim.config.electoral_system,
        sim.config.electoral_threshold,
    )
    world.seats = {party.id: seat_map.get(party.id, 0) for party in parties}
    for party_id in list(world.seats):
        if party_id not in seat_map:
            world.seats[party_id] = 0

    total_cast = sum(votes.values())
    turnout = total_cast / max(len(world.citizens), 1)
    results = []
    for party in parties:
        count = votes.get(party.id, 0)
        bucket = component_totals[party.id]
        n = bucket["n"] or 1.0
        results.append(
            {
                "party_id": party.id,
                "name": party.name,
                "votes": count,
                "seats": world.seats.get(party.id, 0),
                "vote_share": (count / total_cast) if total_cast else 0.0,
                "mean_policy_term": bucket["policy"] / n if bucket["n"] else 0.0,
                "mean_trust_term": bucket["trust"] / n if bucket["n"] else 0.0,
                "mean_competence_term": bucket["competence"] / n if bucket["n"] else 0.0,
                "mean_loyalty_term": bucket["loyalty"] / n if bucket["n"] else 0.0,
            }
        )
    results.sort(key=lambda row: (-int(row["seats"]), -int(row["votes"]), int(row["party_id"])))

    for party in parties:
        won = world.seats.get(party.id, 0)
        if won > 0:
            party.capital = clamp01(party.capital + 0.05 + 0.01 * won)
            leader = sim.citizen(party.leader_id)
            leader.influence = clamp01(leader.influence + 0.01 * won)
        else:
            party.competence = clamp01(party.competence - 0.03)
            party.capital = clamp01(party.capital - 0.04)

    summary_bits = [
        f"{row['name']} {row['seats']} seats ({row['votes']} votes)"
        for row in results
        if int(row["votes"]) > 0
    ]
    summary = (
        f"Election: turnout {total_cast} of {len(world.citizens)}. "
        + ("; ".join(summary_bits) if summary_bits else "No party received votes.")
    )
    event = sim.emit(
        "election_held",
        summary,
        actors={"parties": [party.id for party in parties]},
        factors={
            "turnout": turnout,
            "ballots": total_cast,
            "abstentions": sum(abstain.values()),
            "followed_trusted": followed,
            "parties_contesting": len(parties),
            "electoral_system": sim.config.electoral_system,
            "threshold": sim.config.electoral_threshold,
        },
        details={"results": results, "abstain_reasons": abstain},
        causes=_election_causes(sim),
    )
    world.last_election_tick = world.tick
    return {"event_id": event.id, "results": results, "votes": votes, "abstain": abstain}


def _election_causes(sim: Sim) -> list[int]:
    causes: list[int] = []
    for key in ("government_ended", "party_founded", "party_split"):
        event_id = sim.latest_by_type.get(key)
        if event_id is not None and sim.ledger.events[event_id - 1].tick == sim.world.tick:
            causes.append(event_id)
    return causes


def _choose(
    sim: Sim,
    citizen: Citizen,
    parties: list[Party],
) -> tuple[int | None, str, dict[str, float | list[str]] | None]:
    noise = sim.rng.election.uniform(-0.05, 0.05)
    trust_climate = sim.world.outcomes["institutional_trust"] / 100.0
    propensity = citizen.engagement * (0.55 + 0.45 * trust_climate)
    propensity *= 0.75 + 0.25 * citizen.attentiveness
    if propensity + noise <= sim.config.turnout_threshold:
        return None, "low_engagement", None

    known = _known_parties(sim, citizen, parties)
    if not known:
        return None, "no_known_party", None

    follow_p = (1.0 - citizen.attentiveness) * citizen.conformity * sim.config.relationship_influence
    if follow_p > 0.42 and sim.rng.election.random() < follow_p:
        followed = _follow_neighbor(sim, citizen, known)
        if followed is not None:
            return followed, "followed_trusted", None

    best_id: int | None = None
    best_utility = 0.0
    best_parts: dict[str, float | list[str]] | None = None
    for party in known:
        parts = _score_party(sim, citizen, party)
        utility = float(parts["utility"])
        if best_id is None or utility > best_utility + 1e-9 or (
            abs(utility - best_utility) <= 1e-9 and party.id < best_id
        ):
            best_id = party.id
            best_utility = utility
            best_parts = parts
    if best_id is None or best_utility < sim.config.abstain_utility:
        return None, "none_acceptable", best_parts
    return best_id, "scored", best_parts


def _known_parties(sim: Sim, citizen: Citizen, parties: list[Party]) -> list[Party]:
    if citizen.attentiveness >= 0.82:
        return parties
    known_ids = {
        party_id
        for party_id, belief in citizen.beliefs.items()
        if belief.known_issues or belief.perceived_platform
    }
    if citizen.party_id is not None:
        known_ids.add(citizen.party_id)
    return [party for party in parties if party.id in known_ids]


def _follow_neighbor(sim: Sim, citizen: Citizen, known: list[Party]) -> int | None:
    known_ids = {party.id for party in known}
    best: tuple[float, int] | None = None
    for neighbor_id in sim.world.neighbors.get(citizen.id, []):
        neighbor = sim.citizen(neighbor_id)
        if neighbor.party_id not in known_ids:
            continue
        relation = sim.relationship(citizen.id, neighbor_id)
        trust = relation.trust if relation else 0.0
        if best is None or trust > best[0] or (trust == best[0] and neighbor_id < best[1]):
            best = (trust, neighbor_id)
    if best is None or best[0] < 0.15:
        return None
    return sim.citizen(best[1]).party_id


def _score_party(sim: Sim, citizen: Citizen, party: Party) -> dict[str, float | list[str]]:
    platform, issues = _perceived_platform(sim, citizen, party)
    trust = _party_trust(sim, citizen, party)
    loyalty = _loyalty(sim, citizen, party)
    belief = citizen.beliefs.get(party.id)
    competence = belief.perceived_competence if belief else party.competence
    promise = belief.perceived_promise if belief else party.promise_keeping
    if citizen.attentiveness >= 0.82 or citizen.party_id == party.id:
        competence = party.competence
        promise = party.promise_keeping
    return vote_utility(
        citizen,
        platform,
        issues,
        trust,
        competence,
        promise,
        loyalty,
        sim.config,
    )


def _perceived_platform(
    sim: Sim,
    citizen: Citizen,
    party: Party,
) -> tuple[dict[str, float], list[str]]:
    if citizen.attentiveness >= 0.82 or citizen.party_id == party.id:
        return dict(party.platform), list(DIMENSIONS)
    belief = citizen.beliefs.get(party.id)
    if belief is None or not belief.known_issues:
        return dict(party.platform), known_issues_for(citizen)
    platform = {
        issue: belief.perceived_platform.get(issue, party.platform[issue])
        for issue in belief.known_issues
    }
    return platform, list(belief.known_issues)


def _party_trust(sim: Sim, citizen: Citizen, party: Party) -> float:
    if sim.config.relationship_influence <= 0.0:
        base = party.trust_reputation * 2.0 - 1.0
        memory = 0.0
    else:
        leader_rel = sim.relationship(citizen.id, party.leader_id)
        base = leader_rel.trust if leader_rel is not None else party.trust_reputation * 2.0 - 1.0
        memory = memory_valence(citizen, party.id, sim.world.tick, sim.config.memory_half_life)
    combined = base + 0.4 * memory
    return clamp01((combined + 1.0) / 2.0)


def _loyalty(sim: Sim, citizen: Citizen, party: Party) -> float:
    score = 0.0
    if citizen.party_id == party.id:
        score += 0.55
    if citizen.last_vote == party.id:
        score += 0.2
    friends = sim.world.neighbors.get(citizen.id, [])
    if friends:
        inside = sum(1 for nid in friends if sim.citizen(nid).party_id == party.id)
        score += 0.4 * (inside / len(friends)) * sim.config.relationship_influence
    return clamp01(score)
