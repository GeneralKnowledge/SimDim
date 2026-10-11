"""Factions, leadership challenges, splits, and mergers.

Internal conflict is a consequence of platform distance, broken promises,
and personality. The engine does not insert a split because a history
would otherwise be quiet.
"""

from __future__ import annotations

from simdemocracy.config import DIMENSIONS
from simdemocracy.context import Sim
from simdemocracy.models import Faction, Party
from simdemocracy.names import party_name
from simdemocracy.organisation import dissolve_party
from simdemocracy.utility import alignment, clamp, clamp01, median


def internal_politics(sim: Sim) -> None:
    sim.world.splits_this_tick = 0
    for party in list(sim.active_parties()):
        if party.status != "active" or len(party.members) < 4:
            continue
        _update_factions(sim, party)
        if party.status != "active":
            continue
        _leadership(sim, party)
        if party.status != "active":
            continue
        _maybe_split(sim, party)
    _maybe_merge(sim)
    _drift_relationships(sim)


def _update_factions(sim: Sim, party: Party) -> None:
    if len(party.members) < 8:
        party.factions = []
        return
    refreshed: list[Faction] = []
    for issue in DIMENSIONS:
        grouped = {1: [], -1: []}
        for citizen_id in sorted(party.members):
            gap = sim.citizen(citizen_id).positions[issue] - party.platform[issue]
            if gap > 42.0:
                grouped[1].append(citizen_id)
            elif gap < -42.0:
                grouped[-1].append(citizen_id)
        threshold = max(5, int(0.28 * len(party.members)))
        for direction, members in grouped.items():
            if len(members) < threshold:
                continue
            existing = next(
                (
                    faction
                    for faction in party.factions
                    if faction.issue == issue and faction.direction == direction
                ),
                None,
            )
            leader_id = max(members, key=lambda cid: (sim.citizen(cid).ambition, sim.citizen(cid).influence, -cid))
            if existing is None:
                faction = Faction(
                    id=sim.world.next_faction_id,
                    party_id=party.id,
                    issue=issue,
                    direction=direction,
                    member_ids=members,
                    formed_tick=sim.world.tick,
                    leader_id=leader_id,
                )
                sim.world.next_faction_id += 1
                refreshed.append(faction)
                share = len(members) / max(len(party.members), 1)
                sim.emit(
                    "faction_formed",
                    (
                        f"A faction in {party.name} coalesced around {issue.replace('_', ' ')} "
                        f"({'higher' if direction > 0 else 'lower'} than the platform), "
                        f"with {len(members)} members."
                    ),
                    significance="major" if share >= 0.35 and len(members) >= 8 else "minor",
                    actors={"party": party.id, "faction": faction.id, "leader": leader_id},
                    factors={
                        "issue": issue,
                        "direction": direction,
                        "members": len(members),
                        "party_members": len(party.members),
                        "gap_threshold": 42.0,
                        "share": share,
                    },
                )
            else:
                existing.member_ids = members
                existing.leader_id = leader_id
                refreshed.append(existing)
    party.factions = refreshed


def _leadership(sim: Sim, party: Party) -> None:
    if sim.world.tick < party.leadership_cooldown_until or len(party.members) < 4:
        return
    leader = sim.citizen(party.leader_id)
    supports = [_appeal(sim, sim.citizen(cid), leader, party, as_incumbent=True) for cid in sorted(party.members)]
    mean_support = sum(supports) / len(supports)
    if mean_support >= 0.52:
        return
    challenger_id = None
    challenger_score = -1.0
    for citizen_id in sorted(party.members):
        if citizen_id == leader.id:
            continue
        citizen = sim.citizen(citizen_id)
        if citizen.ambition * sim.config.ambition_scale < 0.52:
            continue
        expected = _mean(
            _appeal(sim, sim.citizen(member_id), citizen, party, as_incumbent=False)
            for member_id in party.members
        )
        score = expected * (0.6 + 0.4 * citizen.ambition)
        if score > challenger_score:
            challenger_score = score
            challenger_id = citizen_id
    if challenger_id is None:
        return
    probability = clamp((0.52 - mean_support) * 1.5 + 0.25 * sim.citizen(challenger_id).ambition, 0.0, 0.8)
    draw = sim.rng.internal.random()
    if draw >= probability:
        return
    votes_for = 0
    votes_against = 0
    for member_id in sorted(party.members):
        member = sim.citizen(member_id)
        for_challenger = _appeal(sim, member, sim.citizen(challenger_id), party, as_incumbent=False)
        for_leader = _appeal(sim, member, leader, party, as_incumbent=True)
        if for_challenger > for_leader:
            votes_for += 1
        else:
            votes_against += 1
    party.leadership_cooldown_until = sim.world.tick + 6
    if votes_for > votes_against:
        previous = party.leader_id
        party.leader_id = challenger_id
        winner = sim.citizen(challenger_id)
        winner.influence = clamp01(winner.influence + 0.06)
        leader.influence = clamp01(leader.influence - 0.04)
        _sour_relationship(sim, leader.id, challenger_id, trust_drop=0.25, rivalry_gain=0.2)
        sim.emit(
            "leadership_changed",
            (
                f"{winner.name} replaced {leader.name} as leader of {party.name} "
                f"by {votes_for} votes to {votes_against}."
            ),
            actors={
                "party": party.id,
                "leader": challenger_id,
                "previous_leader": previous,
            },
            factors={
                "mean_support": mean_support,
                "votes_for_challenger": votes_for,
                "votes_for_leader": votes_against,
                "attempt_probability": probability,
                "draw": draw,
            },
            causes=_recent_party_causes(sim, party.id),
        )
    else:
        sim.emit(
            "leadership_challenge",
            (
                f"{sim.citizen(challenger_id).name} challenged {leader.name} for the leadership "
                f"of {party.name} and lost {votes_for} to {votes_against}."
            ),
            actors={"party": party.id, "leader": leader.id, "challenger": challenger_id},
            factors={
                "mean_support": mean_support,
                "votes_for_challenger": votes_for,
                "votes_for_leader": votes_against,
                "attempt_probability": probability,
                "draw": draw,
            },
            causes=_recent_party_causes(sim, party.id),
        )


def _maybe_split(sim: Sim, party: Party) -> None:
    if sim.world.splits_this_tick >= sim.config.max_splits_per_tick:
        return
    if sim.world.tick < party.split_cooldown_until or len(party.members) < 8:
        return
    if not party.factions:
        return
    faction = max(party.factions, key=lambda item: (len(item.member_ids), -item.id))
    if sim.world.tick - faction.formed_tick < 4:
        return
    if len(faction.member_ids) < max(5, int(0.28 * len(party.members))):
        return
    projected = {
        dim: median([sim.citizen(cid).positions[dim] for cid in faction.member_ids])
        for dim in DIMENSIONS
    }
    issue_gap = abs(projected[faction.issue] - party.platform[faction.issue])
    other_gap = max(
        abs(projected[dim] - party.platform[dim])
        for dim in DIMENSIONS
        if dim != faction.issue
    )
    # One noisy dimension is a faction. A split needs a broader break.
    if issue_gap < 36.0 or other_gap < 16.0:
        return
    rigidity = _mean(sim.citizen(cid).ideological_rigidity for cid in faction.member_ids)
    loyalty = _mean(sim.citizen(cid).loyalty for cid in faction.member_ids)
    if rigidity < 0.4:
        return
    probability = clamp(0.08 + 0.35 * rigidity - 0.28 * loyalty, 0.04, 0.4)
    # Recent breach by this party's leadership raises the chance, because the
    # faction can point at a recorded commitment rather than a mood.
    if _party_broke_recently(sim, party.id):
        probability = clamp(probability + 0.2, 0.0, 0.85)
    draw = sim.rng.internal.random()
    if draw >= probability:
        return
    leavers: list[int] = []
    for citizen_id in faction.member_ids:
        citizen = sim.citizen(citizen_id)
        if citizen.party_id != party.id:
            continue
        if citizen.loyalty > 0.78 and sim.rng.internal.random() > 0.35:
            continue
        leavers.append(citizen_id)
    if len(leavers) < 3:
        return
    _execute_split(sim, party, faction, leavers, probability, draw)


def _execute_split(
    sim: Sim,
    party: Party,
    faction: Faction,
    leavers: list[int],
    probability: float,
    draw: float,
) -> None:
    platform = {
        dim: median([sim.citizen(cid).positions[dim] for cid in leavers]) for dim in DIMENSIONS
    }
    founder_id = faction.leader_id if faction.leader_id in leavers else max(
        leavers, key=lambda cid: (sim.citizen(cid).ambition, -cid)
    )
    child = Party(
        id=sim.world.next_party_id,
        name=party_name(sim.rng.names, sim.world.used_party_names),
        founder_id=founder_id,
        leader_id=founder_id,
        platform=platform,
        members=set(),
        founded_tick=sim.world.tick,
        grace_until=sim.world.tick + sim.config.founding_grace_ticks,
        parent_id=party.id,
        attention=0.55,
        merge_cooldown_until=sim.world.tick + 12,
    )
    sim.world.next_party_id += 1
    sim.world.parties[child.id] = child
    sim.world.seats[child.id] = 0
    for citizen_id in leavers:
        citizen = sim.citizen(citizen_id)
        party.members.discard(citizen_id)
        child.members.add(citizen_id)
        citizen.party_id = child.id
        citizen.joined_tick = sim.world.tick
    if party.leader_id in leavers and party.members:
        party.leader_id = max(
            party.members,
            key=lambda cid: (sim.citizen(cid).influence, sim.citizen(cid).ambition, -cid),
        )
    if not party.members:
        # The parent should keep at least the non-leavers; if everyone left, dissolve it.
        dissolve_party(sim, party, "every member left in a split", cause=None)
    sim.tie(party.id, child.id).hostility = clamp01(sim.tie(party.id, child.id).hostility + 0.55)
    sim.tie(child.id, party.id).hostility = clamp01(sim.tie(child.id, party.id).hostility + 0.6)
    sim.tie(party.id, child.id).trust = -0.35
    sim.tie(child.id, party.id).trust = -0.4
    _sour_relationship(sim, party.leader_id, child.leader_id, trust_drop=0.3, rivalry_gain=0.35)
    party.split_cooldown_until = sim.world.tick + 8
    child.split_cooldown_until = sim.world.tick + 8
    party.merge_cooldown_until = max(party.merge_cooldown_until, sim.world.tick + 12)
    sim.world.splits_this_tick += 1
    party.factions = [item for item in party.factions if item.id != faction.id]
    event = sim.emit(
        "party_split",
        (
            f"{child.name} split from {party.name} over {faction.issue.replace('_', ' ')}. "
            f"{len(leavers)} members left; {len(party.members)} stayed. "
            f"Parliamentary seats stay with {party.name} until the next election."
        ),
        actors={
            "party": party.id,
            "child": child.id,
            "founder": founder_id,
            "faction": faction.id,
        },
        factors={
            "leavers": len(leavers),
            "stayers": len(party.members),
            "issue": faction.issue,
            "direction": faction.direction,
            "probability": probability,
            "draw": draw,
            "seats_remain_with_parent": sim.world.seats.get(party.id, 0),
        },
        details={"leaver_ids": leavers, "platform": platform},
        causes=_recent_party_causes(sim, party.id),
    )
    child.founding_event = event.id
    if party.status == "active" and len(party.members) < sim.config.min_members:
        party.low_member_ticks = max(party.low_member_ticks, 1)


def _maybe_merge(sim: Sim) -> None:
    parties = sim.active_parties()
    pairs: list[tuple[float, int, int]] = []
    for index, left in enumerate(parties):
        for right in parties[index + 1 :]:
            fit = alignment(left.platform, right.platform)
            widest = max(abs(left.platform[dim] - right.platform[dim]) for dim in DIMENSIONS)
            if fit < 0.9 or widest > 32.0:
                continue
            if sim.tie(left.id, right.id).hostility > 0.3 or sim.tie(right.id, left.id).hostility > 0.3:
                continue
            smaller = min(len(left.members), len(right.members))
            if smaller > 16 and widest > 22.0:
                continue
            pairs.append((fit, left.id, right.id))
    pairs.sort(key=lambda item: (-item[0], item[1], item[2]))
    for fit, left_id, right_id in pairs:
        left = sim.party(left_id)
        right = sim.party(right_id)
        if left.status != "active" or right.status != "active":
            continue
        if sim.world.tick < left.merge_cooldown_until or sim.world.tick < right.merge_cooldown_until:
            continue
        smaller, larger = (left, right) if len(left.members) <= len(right.members) else (right, left)
        if smaller.id == larger.id:
            continue
        leader_a = sim.citizen(smaller.leader_id)
        leader_b = sim.citizen(larger.leader_id)
        if leader_a.ideological_rigidity > 0.8 and leader_a.compromise < 0.3:
            continue
        if leader_b.ideological_rigidity > 0.8 and leader_b.compromise < 0.3:
            continue
        _execute_merge(sim, smaller, larger, fit)
        return


def _execute_merge(sim: Sim, smaller: Party, larger: Party, fit: float) -> None:
    refused: list[int] = []
    moved: list[int] = []
    for citizen_id in sorted(smaller.members):
        citizen = sim.citizen(citizen_id)
        fit_to_larger = alignment(citizen.positions, larger.platform, citizen.importance)
        if fit_to_larger < 0.48 and citizen.ideological_rigidity > 0.45:
            refused.append(citizen_id)
            continue
        smaller.members.discard(citizen_id)
        larger.members.add(citizen_id)
        citizen.party_id = larger.id
        citizen.joined_tick = sim.world.tick
        moved.append(citizen_id)
    for citizen_id in refused:
        citizen = sim.citizen(citizen_id)
        smaller.members.discard(citizen_id)
        if citizen.party_id == smaller.id:
            citizen.party_id = None
            citizen.joined_tick = None
    for dim in DIMENSIONS:
        larger.platform[dim] = clamp(0.8 * larger.platform[dim] + 0.2 * smaller.platform[dim], -100.0, 100.0)
    seats = sim.world.seats.get(smaller.id, 0)
    sim.world.seats[larger.id] = sim.world.seats.get(larger.id, 0) + seats
    sim.world.seats[smaller.id] = 0
    smaller.members.clear()
    smaller.status = "merged"
    smaller.merged_into = larger.id
    smaller.dissolved_tick = sim.world.tick
    event = sim.emit(
        "party_merged",
        (
            f"{smaller.name} merged into {larger.name}. {len(moved)} members transferred"
            f"{f', {len(refused)} refused' if refused else ''}. "
            f"{seats} seats moved to {larger.name}."
        ),
        actors={"party": larger.id, "absorbed": smaller.id, "leader": larger.leader_id},
        factors={
            "platform_alignment": fit,
            "moved": len(moved),
            "refused": len(refused),
            "seats_transferred": seats,
        },
        details={"moved_ids": moved, "refused_ids": refused},
        causes=[smaller.founding_event] if smaller.founding_event else [],
    )
    _inherit_government_seat(sim, smaller.id, larger.id, event.id)


def _inherit_government_seat(sim: Sim, absorbed_id: int, survivor_id: int, cause: int) -> None:
    government = sim.world.government
    if government is None or government.ended_tick is not None:
        return
    if absorbed_id in government.party_ids and survivor_id not in government.party_ids:
        government.party_ids = [
            survivor_id if pid == absorbed_id else pid for pid in government.party_ids
        ]
    else:
        government.party_ids = [pid for pid in government.party_ids if pid != absorbed_id]
    if absorbed_id in government.support_ids and survivor_id not in government.confidence_ids():
        government.support_ids = [
            survivor_id if pid == absorbed_id else pid for pid in government.support_ids
        ]
    else:
        government.support_ids = [pid for pid in government.support_ids if pid != absorbed_id]
    from simdemocracy.parliament import ensure_confidence

    ensure_confidence(sim, cause)


def _appeal(
    sim: Sim,
    member: object,
    candidate: object,
    party: Party,
    *,
    as_incumbent: bool,
) -> float:
    personal = candidate.positions  # type: ignore[attr-defined]
    reference = {
        dim: 0.55 * party.platform[dim] + 0.45 * personal[dim] if as_incumbent else personal[dim]
        for dim in DIMENSIONS
    }
    fit = alignment(member.positions, reference, member.importance)  # type: ignore[attr-defined]
    relation = sim.relationship(member.id, candidate.id)  # type: ignore[attr-defined]
    trust = 0.5
    if relation is not None and sim.config.relationship_influence > 0.0:
        trust = clamp01((relation.trust + 1.0) / 2.0)
    promise = party.promise_keeping if as_incumbent else 0.55
    return (
        (0.4 + 0.35 * member.ideological_rigidity) * fit  # type: ignore[attr-defined]
        + (0.15 + 0.35 * member.loyalty) * trust  # type: ignore[attr-defined]
        + 0.15 * promise
        - 0.2 * member.disappointment  # type: ignore[attr-defined]
    )


def _sour_relationship(
    sim: Sim,
    left: int,
    right: int,
    *,
    trust_drop: float,
    rivalry_gain: float,
) -> None:
    if left == right:
        return
    for source, target in ((left, right), (right, left)):
        relation = sim.relationship(source, target)
        if relation is None:
            continue
        relation.trust = clamp(relation.trust - trust_drop, -1.0, 1.0)
        relation.rivalry = clamp01(relation.rivalry + rivalry_gain)


def _drift_relationships(sim: Sim) -> None:
    for source, target in sorted(sim.world.relationships):
        relation = sim.world.relationships[(source, target)]
        same = (
            sim.citizen(source).party_id is not None
            and sim.citizen(source).party_id == sim.citizen(target).party_id
        )
        if same:
            relation.trust = clamp(relation.trust + 0.004, -1.0, 1.0)
            relation.affinity = clamp(relation.affinity + 0.002, -1.0, 1.0)
        else:
            relation.trust *= 0.998
        if relation.rivalry > 0.0:
            relation.rivalry = clamp(relation.rivalry * 0.997, 0.0, 1.0)


def _party_broke_recently(sim: Sim, party_id: int) -> bool:
    window = 6
    for event in reversed(sim.ledger.events):
        if event.tick < sim.world.tick - window:
            break
        if event.type == "commitment_broken" and event.actors.get("party") == party_id:
            return True
    return False


def _recent_party_causes(sim: Sim, party_id: int) -> list[int]:
    causes: list[int] = []
    for event in reversed(sim.ledger.events[-12:]):
        if event.actors.get("party") == party_id and event.type in {
            "commitment_broken",
            "platform_shifted",
            "faction_formed",
            "leadership_challenge",
        }:
            causes.append(event.id)
            if len(causes) >= 3:
                break
    causes.reverse()
    return causes


def _mean(values: object) -> float:
    data = list(values)  # type: ignore[arg-type]
    if not data:
        return 0.0
    return sum(data) / len(data)
