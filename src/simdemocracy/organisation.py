"""Parties as organisations: founding, recruitment, defection, dissolution.

A preference cluster does not automatically become a party. Founding is a
costly, stochastic act by an ambitious citizen, and most attempts can fail.
"""

from __future__ import annotations

from simdemocracy.config import DIMENSIONS
from simdemocracy.context import Sim
from simdemocracy.models import Citizen, Party
from simdemocracy.names import party_name
from simdemocracy.utility import (
    alignment,
    clamp,
    clamp01,
    founding_probability,
    independence_utility,
    join_utility,
    median,
    priority_alignment,
)


def consider_founding(sim: Sim) -> None:
    if sim.config.ambition_scale <= 0.0:
        return
    eligible = [
        citizen
        for citizen in sim.citizens()
        if citizen.party_id is None
        and citizen.engagement >= 0.28
        and citizen.ambition * sim.config.ambition_scale >= 0.58
    ]
    eligible.sort(key=lambda citizen: (-citizen.ambition, citizen.id))
    founded = 0
    attempts = 0
    for citizen in eligible:
        if founded >= sim.config.max_foundings_per_tick:
            break
        if attempts >= sim.config.founding_attempts_per_tick:
            break
        cluster, nearest = _opportunity(sim, citizen)
        probability = founding_probability(citizen, cluster, nearest, sim.config)
        if probability <= 0.0:
            continue
        attempts += 1
        draw = sim.rng.decision.random()
        if draw >= probability:
            continue
        _found(sim, citizen, cluster, nearest, probability, draw)
        founded += 1


def recruit_and_switch(sim: Sim) -> None:
    proposals: list[tuple[float, int, int, dict[str, float]]] = []
    for party in sim.active_parties():
        slots = max(2, int(party.capacity * sim.config.recruitment_per_party))
        for citizen in _targets(sim, party, slots):
            if citizen.id == party.leader_id and citizen.party_id == party.id:
                continue
            social = _social_fraction(sim, citizen, party.id)
            trust = _leader_trust01(sim, citizen, party)
            if not _acceptable_membership(citizen, party):
                continue
            current_utility = None
            if citizen.party_id is not None and citizen.party_id in sim.world.parties:
                current = sim.party(citizen.party_id)
                if current.status == "active":
                    current_utility = join_utility(
                        citizen,
                        current,
                        social=_social_fraction(sim, citizen, current.id),
                        trust=_leader_trust01(sim, citizen, current),
                        seat_share=sim.seat_share(current.id),
                        config=sim.config,
                        current=True,
                    )["utility"]
            scored = join_utility(
                citizen,
                party,
                social=social,
                trust=trust,
                seat_share=sim.seat_share(party.id),
                config=sim.config,
                current=citizen.party_id == party.id,
            )
            if citizen.party_id == party.id:
                continue
            stay = independence_utility(citizen, sim.config)
            if current_utility is not None:
                stay = max(stay, current_utility)
            margin = 0.04 + (0.12 * citizen.loyalty if current_utility is not None else 0.0)
            if scored["utility"] <= stay + margin:
                continue
            chance = clamp((scored["utility"] - stay) * 1.6, 0.05, 0.9)
            if citizen.party_id is not None:
                chance *= 1.0 - 0.45 * citizen.loyalty
            if sim.rng.decision.random() > chance:
                continue
            proposals.append((scored["utility"], party.id, citizen.id, scored))

    chosen: dict[int, tuple[float, int, dict[str, float]]] = {}
    for utility, party_id, citizen_id, scored in proposals:
        current = chosen.get(citizen_id)
        if current is None or utility > current[0] or (
            abs(utility - current[0]) <= 1e-9 and party_id < current[1]
        ):
            chosen[citizen_id] = (utility, party_id, scored)

    for citizen_id in sorted(chosen):
        utility, party_id, scored = chosen[citizen_id]
        _move_into(sim, sim.citizen(citizen_id), sim.party(party_id), utility, scored)


def dissolve_failing(sim: Sim) -> None:
    for party in list(sim.active_parties()):
        if sim.world.tick <= party.grace_until:
            continue
        if len(party.members) < sim.config.min_members:
            party.low_member_ticks += 1
        else:
            party.low_member_ticks = 0
        if party.low_member_ticks >= 3 or not party.members:
            dissolve_party(sim, party, "below the minimum membership for three weeks")


def campaign_platforms(sim: Sim) -> None:
    """Leaders may edge the official platform toward engaged citizens before a vote."""

    engaged = [citizen for citizen in sim.citizens() if citizen.engagement >= 0.4]
    if len(engaged) < 5:
        return
    electorate = {dim: median([citizen.positions[dim] for citizen in engaged]) for dim in DIMENSIONS}
    for party in sim.active_parties():
        leader = sim.citizen(party.leader_id)
        if leader.ambition * sim.config.ambition_scale < 0.45:
            continue
        if leader.compromise < 0.25 and leader.ideological_rigidity > 0.7:
            continue
        member_positions = {
            dim: median([sim.citizen(cid).positions[dim] for cid in party.members])
            if party.members
            else party.platform[dim]
            for dim in DIMENSIONS
        }
        step = 2.2 + 2.4 * leader.compromise * leader.ambition
        tolerance = 10.0 + 14.0 * _mean(sim.citizen(cid).compromise for cid in party.members)
        if leader.ambition * leader.overconfidence > leader.loyalty + 0.2:
            tolerance += 6.0
            motive = "court_median_voter"
        else:
            motive = "limited_electioneering"
        shifted: dict[str, float] = {}
        for dim in DIMENSIONS:
            if dim in leader.non_negotiable and abs(electorate[dim] - leader.positions[dim]) > 30.0:
                continue
            target = electorate[dim]
            current = party.platform[dim]
            delta = clamp(target - current, -step, step)
            proposed = current + delta * (0.35 + 0.4 * leader.compromise)
            member_gap = abs(proposed - member_positions[dim])
            allowed = abs(current - member_positions[dim]) + tolerance
            if member_gap > allowed:
                direction = 1.0 if proposed > member_positions[dim] else -1.0
                proposed = member_positions[dim] + direction * allowed
            proposed = clamp(proposed, -100.0, 100.0)
            if abs(proposed - current) >= 1.0:
                shifted[dim] = proposed
        if not shifted:
            continue
        before = dict(party.platform)
        party.platform.update(shifted)
        max_shift = max(abs(party.platform[dim] - before[dim]) for dim in shifted)
        if max_shift < 6.0:
            continue
        sim.emit(
            "platform_shifted",
            (
                f"{party.name} moved its platform before the election "
                f"(largest change {max_shift:.0f} points) because its leader sought votes "
                f"outside the current membership."
            ),
            actors={"party": party.id, "leader": leader.id},
            factors={
                "max_shift": max_shift,
                "leader_ambition": leader.ambition,
                "leader_compromise": leader.compromise,
                "member_tolerance": tolerance if tolerance < 100 else -1.0,
                "motive": motive,
            },
            details={"before": before, "after": dict(party.platform), "electorate_median": electorate},
        )


def dissolve_party(sim: Sim, party: Party, reason: str, *, cause: int | None = None) -> None:
    if party.status != "active":
        return
    member_ids = sorted(party.members)
    seats_lost = sim.world.seats.get(party.id, 0)
    for citizen_id in member_ids:
        citizen = sim.citizen(citizen_id)
        if citizen.party_id == party.id:
            citizen.party_id = None
            citizen.joined_tick = None
        party.members.discard(citizen_id)
    party.status = "dissolved"
    party.dissolved_tick = sim.world.tick
    sim.world.seats[party.id] = 0
    causes = [cause] if cause is not None else []
    if party.founding_event is not None:
        causes.append(party.founding_event)
    event = sim.emit(
        "party_dissolved",
        f"{party.name} dissolved: {reason}. {len(member_ids)} members left, and {seats_lost} seats were vacated.",
        actors={"party": party.id, "members": member_ids},
        factors={
            "members": len(member_ids),
            "seats_lost": seats_lost,
            "reason": reason,
        },
        details={"member_ids": member_ids},
        causes=causes,
    )
    _remove_from_government(sim, party.id, event.id)


def _found(
    sim: Sim,
    founder: Citizen,
    cluster: int,
    nearest: float,
    probability: float,
    draw: float,
) -> None:
    platform = dict(founder.positions)
    # Soften the platform one step toward the nearby unrepresented citizens so
    # it is an offer, not only a self-portrait.
    nearby = _nearby_unrepresented(sim, founder)
    if nearby:
        for dim in DIMENSIONS:
            platform[dim] = clamp(
                0.65 * founder.positions[dim]
                + 0.35 * median([citizen.positions[dim] for citizen in nearby]),
                -100.0,
                100.0,
            )
    party = Party(
        id=sim.world.next_party_id,
        name=party_name(sim.rng.names, sim.world.used_party_names),
        founder_id=founder.id,
        leader_id=founder.id,
        platform=platform,
        members={founder.id},
        founded_tick=sim.world.tick,
        grace_until=sim.world.tick + sim.config.founding_grace_ticks,
        merge_cooldown_until=sim.world.tick + 10,
    )
    sim.world.next_party_id += 1
    sim.world.parties[party.id] = party
    sim.world.seats[party.id] = 0
    founder.party_id = party.id
    founder.joined_tick = sim.world.tick
    founder.influence = clamp01(founder.influence + 0.07)
    event = sim.emit(
        "party_founded",
        (
            f"{founder.name} founded {party.name} after finding {cluster} citizens "
            f"whose priorities were poorly covered. The closest existing party aligned "
            f"at {nearest:.2f}. Founding probability was {probability:.2f}."
        ),
        actors={"party": party.id, "founder": founder.id, "leader": founder.id},
        factors={
            "unrepresented_nearby": cluster,
            "nearest_party_alignment": nearest,
            "ambition": founder.ambition,
            "influence": founder.influence,
            "sociability": founder.sociability,
            "probability": probability,
            "draw": draw,
        },
        details={"platform": dict(platform), "initial_member_ids": [founder.id]},
    )
    party.founding_event = event.id
    _set_accurate_belief(sim, founder, party)
    recruits = _nearby_unrepresented(sim, founder)[:6]
    joined: list[int] = []
    for citizen in recruits:
        if citizen.id == founder.id or citizen.party_id is not None:
            continue
        if not _acceptable_membership(citizen, party):
            continue
        social = _social_fraction(sim, citizen, party.id)
        trust = _leader_trust01(sim, citizen, party)
        scored = join_utility(
            citizen,
            party,
            social=social,
            trust=trust,
            seat_share=0.0,
            config=sim.config,
        )
        stay = independence_utility(citizen, sim.config)
        if scored["utility"] <= stay + 0.02:
            continue
        if sim.rng.decision.random() > clamp((scored["utility"] - stay) * 1.4, 0.1, 0.85):
            continue
        _move_into(sim, citizen, party, scored["utility"], scored, cause=event.id)
        joined.append(citizen.id)
    event.details["initial_recruits"] = joined


def _move_into(
    sim: Sim,
    citizen: Citizen,
    party: Party,
    utility: float,
    scored: dict[str, float],
    *,
    cause: int | None = None,
) -> None:
    if party.status != "active":
        return
    previous = citizen.party_id
    if previous == party.id:
        return
    if previous is not None and previous in sim.world.parties:
        _leave(sim, citizen, sim.party(previous), "moved to another organisation", defected=True, cause=cause)
    party.members.add(citizen.id)
    citizen.party_id = party.id
    citizen.joined_tick = sim.world.tick
    citizen.disappointment = max(0.0, citizen.disappointment - 0.05)
    _set_accurate_belief(sim, citizen, party)
    kind = "member_defected" if previous is not None else "member_joined"
    # Joining from independence is recruitment. Leaving is recorded by _leave.
    if previous is None:
        significance = "minor"
        sim.emit(
            kind,
            f"{citizen.name} joined {party.name}.",
            significance=significance,
            actors={"party": party.id, "citizen": citizen.id},
            factors={
                "utility": utility,
                "policy_fit": scored.get("policy_fit", 0.0),
                "social": scored.get("social", 0.0),
                "trust": scored.get("trust", 0.0),
                "influence": scored.get("influence", 0.0),
                "cost": scored.get("cost", 0.0),
                "previous_party": -1,
            },
            causes=[cause] if cause is not None else [],
        )


def _leave(
    sim: Sim,
    citizen: Citizen,
    party: Party,
    reason: str,
    *,
    defected: bool,
    cause: int | None,
) -> None:
    if citizen.id not in party.members and citizen.party_id != party.id:
        return
    was_leader = party.leader_id == citizen.id
    party.members.discard(citizen.id)
    if citizen.party_id == party.id:
        citizen.party_id = None
        citizen.joined_tick = None
    event_type = "member_defected" if defected else "member_left"
    significance = "major" if was_leader or citizen.influence > 0.72 else "minor"
    event = sim.emit(
        event_type,
        f"{citizen.name} left {party.name}: {reason}.",
        significance=significance,
        actors={"party": party.id, "citizen": citizen.id, "leader": was_leader},
        factors={
            "influence": citizen.influence,
            "loyalty": citizen.loyalty,
            "disappointment": citizen.disappointment,
            "was_leader": 1.0 if was_leader else 0.0,
        },
        details={"reason": reason},
        causes=[cause] if cause is not None else [],
    )
    if was_leader and party.status == "active":
        if party.members:
            _succeed(sim, party, f"{citizen.name} left the leadership", event.id)
        else:
            dissolve_party(sim, party, "its last member left", cause=event.id)


def leave_party(sim: Sim, citizen: Citizen, reason: str, *, cause: int | None = None) -> None:
    if citizen.party_id is None:
        return
    party = sim.world.parties.get(citizen.party_id)
    if party is None or party.status != "active":
        citizen.party_id = None
        return
    _leave(sim, citizen, party, reason, defected=True, cause=cause)


def _succeed(sim: Sim, party: Party, reason: str, cause: int) -> None:
    if not party.members:
        return
    successor_id = max(
        party.members,
        key=lambda cid: (sim.citizen(cid).influence, sim.citizen(cid).ambition, -cid),
    )
    previous = party.leader_id
    party.leader_id = successor_id
    successor = sim.citizen(successor_id)
    successor.influence = clamp01(successor.influence + 0.05)
    sim.emit(
        "leadership_changed",
        f"{successor.name} became leader of {party.name} after {reason}.",
        actors={"party": party.id, "leader": successor_id, "previous_leader": previous},
        factors={
            "successor_influence": successor.influence,
            "successor_ambition": successor.ambition,
        },
        details={"reason": reason},
        causes=[cause],
    )


def _opportunity(sim: Sim, citizen: Citizen) -> tuple[int, float]:
    nearest = 0.0
    for party in sim.active_parties():
        nearest = max(
            nearest,
            priority_alignment(citizen.positions, party.platform, citizen.importance),
        )
    cluster = len(_nearby_unrepresented(sim, citizen))
    return cluster, nearest


def _nearby_unrepresented(sim: Sim, citizen: Citizen) -> list[Citizen]:
    found: list[Citizen] = []
    for other in sim.citizens():
        if other.id == citizen.id:
            continue
        fit = priority_alignment(citizen.positions, other.positions, citizen.importance)
        theirs = priority_alignment(other.positions, citizen.positions, other.importance)
        if min(fit, theirs) < sim.config.cluster_alignment:
            continue
        if other.party_id is not None:
            continue
        best = 0.0
        for party in sim.active_parties():
            best = max(
                best,
                priority_alignment(other.positions, party.platform, other.importance),
            )
        if best > sim.config.represented_alignment:
            continue
        found.append(other)
    found.sort(key=lambda other: (-alignment(citizen.positions, other.positions), other.id))
    return found


def _acceptable_membership(citizen: Citizen, party: Party) -> bool:
    """Membership requires agreement on what the citizen treats as important.

    Voting can still cross that line: trust and fear are allowed to outweigh
    a platform at the ballot, but joining an organisation is a heavier act.
    """

    if priority_alignment(citizen.positions, party.platform, citizen.importance) < 0.78:
        return False
    top = max(DIMENSIONS, key=lambda dim: citizen.importance[dim])
    return abs(citizen.positions[top] - party.platform[top]) <= 32.0


def _targets(sim: Sim, party: Party, slots: int) -> list[Citizen]:
    scored: list[tuple[float, int]] = []
    member_neighbors: set[int] = set()
    for member_id in party.members:
        member_neighbors.update(sim.world.neighbors.get(member_id, []))
    for citizen in sim.citizens():
        if citizen.id in party.members:
            continue
        fit = alignment(citizen.positions, party.platform, citizen.importance)
        social = 1.0 if citizen.id in member_neighbors else 0.0
        if fit < 0.45 and social < 1.0:
            continue
        scored.append((fit + 0.15 * social, citizen.id))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [sim.citizen(cid) for _score, cid in scored[: slots * 3]]


def _social_fraction(sim: Sim, citizen: Citizen, party_id: int) -> float:
    friends = sim.world.neighbors.get(citizen.id, [])
    if not friends or sim.config.relationship_influence <= 0.0:
        return 0.0
    inside = sum(1 for nid in friends if sim.citizen(nid).party_id == party_id)
    return inside / len(friends)


def _leader_trust01(sim: Sim, citizen: Citizen, party: Party) -> float:
    relation = sim.relationship(citizen.id, party.leader_id)
    if relation is None or sim.config.relationship_influence <= 0.0:
        return party.trust_reputation
    return clamp01((relation.trust + 1.0) / 2.0)


def _set_accurate_belief(sim: Sim, citizen: Citizen, party: Party) -> None:
    from simdemocracy.models import Belief

    citizen.beliefs[party.id] = Belief(
        party_id=party.id,
        known_issues=list(DIMENSIONS),
        perceived_platform=dict(party.platform),
        perceived_competence=party.competence,
        perceived_promise=party.promise_keeping,
        updated_tick=sim.world.tick,
    )


def _mean(values: object) -> float:
    data = list(values)  # type: ignore[arg-type]
    if not data:
        return 0.5
    return sum(data) / len(data)


def _remove_from_government(sim: Sim, party_id: int, cause: int) -> None:
    # Imported lazily: parliament also calls organisation.
    from simdemocracy.parliament import on_party_removed

    on_party_removed(sim, party_id, cause)
