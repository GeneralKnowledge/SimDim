"""Coalitions, commitments, breaches, and confidence.

Alliance value is not ideological similarity alone. Each leader scores the
deal from their own weights. A broken commitment changes trust, reputation,
and the chance of withdrawal. No separate betrayal script runs.
"""

from __future__ import annotations

from simdemocracy.config import DIMENSIONS
from simdemocracy.context import Sim
from simdemocracy.models import Commitment, Government, Party
from simdemocracy.policy import adapt_preferences, member_median, personal_welfare, step_outcomes
from simdemocracy.utility import (
    alignment,
    alliance_value,
    clamp,
    clamp01,
    median,
    non_negotiable_veto,
    signature_gap,
)


def form_government(sim: Sim, cause: int | None, *, collapsed: bool = False) -> bool:
    seated = [party for party in sim.active_parties() if sim.world.seats.get(party.id, 0) > 0]
    seated.sort(key=lambda party: (-sim.world.seats[party.id], party.id))
    majority = sim.config.parliament_seats // 2 + 1
    if not seated:
        sim.emit(
            "government_formation_failed",
            "No party holds seats, so no government formed.",
            actors={},
            factors={"seated_parties": 0, "majority": majority},
            causes=[cause] if cause else [],
        )
        return False

    attempts: list[dict[str, object]] = []
    for formateur in seated:
        if sim.world.seats[formateur.id] >= majority:
            return _install(
                sim,
                [formateur],
                [],
                "majority",
                1.0,
                attempts,
                cause,
                collapsed,
            )
        cabinet = [formateur]
        have = sim.world.seats[formateur.id]
        rejections: list[dict[str, object]] = []
        for partner, mine, theirs, veto in _ranked_partners(sim, formateur, seated):
            if have >= majority:
                break
            if veto is not None or mine["value"] < sim.config.alliance_threshold or theirs["value"] < sim.config.alliance_threshold:
                rejections.append(_rejection(partner.id, mine, theirs, veto or "below_threshold"))
                continue
            if not _cabinet_accepts(sim, cabinet, partner):
                rejections.append(_rejection(partner.id, mine, theirs, "existing_partner_refused"))
                continue
            cabinet.append(partner)
            have += sim.world.seats[partner.id]
        if have >= majority:
            return _install(sim, cabinet, [], "majority", 1.0, attempts, cause, collapsed)
        attempts.append(
            {
                "formateur": formateur.id,
                "seats": have,
                "partners": [party.id for party in cabinet if party.id != formateur.id],
                "rejections": rejections,
            }
        )

    largest = seated[0]
    support: list[Party] = []
    have = sim.world.seats[largest.id]
    for partner, mine, theirs, veto in _ranked_partners(sim, largest, seated):
        if have >= majority:
            break
        floor = sim.config.alliance_threshold * 0.55
        if veto is not None or mine["value"] < floor or theirs["value"] < floor:
            continue
        support.append(partner)
        have += sim.world.seats[partner.id]
    if support and have >= majority:
        return _install(sim, [largest], support, "minority", 0.85, attempts, cause, collapsed)
    if sim.world.seats[largest.id] >= max(3, int(sim.config.parliament_seats * 0.15)):
        return _install(sim, [largest], [], "caretaker", 0.35, attempts, cause, collapsed)

    sim.emit(
        "government_formation_failed",
        "Party leaders did not assemble a cabinet or a confidence arrangement.",
        actors={"largest": largest.id},
        factors={"majority": majority, "largest_seats": sim.world.seats[largest.id]},
        details={"attempts": attempts},
        causes=[cause] if cause else [],
    )
    return False


def close_government(sim: Sim, reason: str, cause: int | None) -> None:
    government = sim.world.government
    if government is None or government.ended_tick is not None:
        return
    kept: list[int] = []
    for commitment in government.commitments:
        if commitment.status != "active":
            continue
        if reason in {"election", "replaced"}:
            commitment.status = "kept"
            kept.append(commitment.id)
            _adjust_promise(sim, commitment.debtor_party, 0.04)
            _adjust_promise(sim, commitment.creditor_party, 0.02)
        else:
            commitment.status = "expired"
    government.ended_tick = sim.world.tick
    government.end_reason = reason
    event = sim.emit(
        "government_ended",
        (
            f"The {government.kind} government led by {_name(sim, government.formateur_party)} "
            f"ended ({reason})."
        ),
        actors={
            "government": government.id,
            "formateur": government.formateur_party,
            "parties": list(government.party_ids),
        },
        factors={
            "duration": sim.world.tick - government.formed_tick,
            "kind": government.kind,
            "reason": reason,
            "commitments_kept": len(kept),
        },
        details={"kept_commitment_ids": kept},
        causes=[cause] if cause else [government.formation_event],
    )
    government.end_event = event.id
    sim.world.past_governments.append(government)
    sim.world.government = None


def govern(sim: Sim) -> None:
    government = sim.world.government
    if government is None or not government.party_ids:
        return
    if not _alive(sim, government.formateur_party):
        close_government(sim, "formateur_gone", None)
        return
    starting_id = government.id
    if government.kind != "caretaker":
        _member_pressure(sim, government)
    if sim.world.government is None or sim.world.government.id != starting_id:
        return
    government = sim.world.government
    applied, fiscal_motive = _fiscal_response(sim, government)
    _check_commitment_gaps(sim, government, applied, fiscal_motive)
    if sim.world.government is None or sim.world.government.id != starting_id:
        return
    government = sim.world.government
    _enact(sim, government, applied, fiscal_motive)


def on_party_removed(sim: Sim, party_id: int, cause: int) -> None:
    government = sim.world.government
    if government is None:
        return
    if party_id not in government.party_ids and party_id not in government.support_ids:
        return
    ensure_confidence(sim, cause)


def ensure_confidence(sim: Sim, cause: int) -> None:
    government = sim.world.government
    if government is None:
        return
    if government.kind == "caretaker":
        government.party_ids = [pid for pid in government.party_ids if _alive(sim, pid)]
        if government.party_ids:
            return
        close_government(sim, "caretaker_collapsed", cause)
        return
    government.party_ids = [pid for pid in government.party_ids if _alive(sim, pid)]
    government.support_ids = [pid for pid in government.support_ids if _alive(sim, pid)]
    if not government.party_ids:
        close_government(sim, "cabinet_empty", cause)
        _after_collapse(sim, cause)
        return
    have = _confidence_seats(sim, government)
    majority = sim.config.parliament_seats // 2 + 1
    if have >= majority:
        cabinet = sum(sim.world.seats.get(pid, 0) for pid in government.party_ids)
        government.kind = "majority" if cabinet >= majority else "minority"
        return
    sim.emit(
        "government_lost_confidence",
        (
            f"The government led by {_name(sim, government.formateur_party)} "
            f"fell to {have} seats, short of {majority}."
        ),
        actors={"government": government.id, "parties": list(government.party_ids)},
        factors={"seats": have, "majority": majority},
        causes=[cause],
    )
    close_government(sim, "lost_confidence", cause)
    _after_collapse(sim, cause)


def _after_collapse(sim: Sim, cause: int) -> None:
    formed = form_government(sim, cause, collapsed=True)
    if formed and sim.world.government is not None and sim.world.government.kind != "caretaker":
        return
    if _may_call_early_election(sim):
        sim.world.forced_election_tick = sim.world.tick + 1
        sim.world.election_lock_until = sim.world.tick + sim.config.early_election_lock
        sim.emit(
            "early_election_called",
            "No majority arrangement survived, so an election was called for next week.",
            actors={},
            factors={"lock_until": sim.world.election_lock_until},
            causes=[cause],
        )


def _may_call_early_election(sim: Sim) -> bool:
    if sim.world.tick < sim.world.election_lock_until:
        return False
    last = sim.world.last_election_tick or 0
    return sim.world.tick - last >= 4


def _install(
    sim: Sim,
    cabinet: list[Party],
    support: list[Party],
    kind: str,
    multiplier: float,
    attempts: list[dict[str, object]],
    cause: int | None,
    collapsed: bool,
) -> bool:
    if sim.world.government is not None:
        close_government(sim, "replaced", cause)
    programme, commitments = _negotiate_programme(sim, cabinet, support)
    government = Government(
        id=sim.world.next_government_id,
        formed_tick=sim.world.tick,
        kind=kind,
        formateur_party=cabinet[0].id,
        party_ids=[party.id for party in cabinet],
        support_ids=[party.id for party in support],
        programme=programme,
        commitments=commitments,
        policy_multiplier=multiplier,
        party_platforms={party.id: dict(party.platform) for party in cabinet + support},
        formation_event=0,
    )
    sim.world.next_government_id += 1
    distances = _pairwise_distances(sim, [party.id for party in cabinet + support])
    names = ", ".join(party.name for party in cabinet)
    support_names = ", ".join(party.name for party in support)
    summary = f"A {kind} government formed under {cabinet[0].name}"
    if len(cabinet) > 1:
        summary = f"A {kind} government formed: {names}"
    if support_names:
        summary += f", with confidence from {support_names}"
    summary += "."
    event = sim.emit(
        "government_formed",
        summary,
        actors={
            "government": government.id,
            "formateur": cabinet[0].id,
            "parties": government.party_ids,
            "support": government.support_ids,
        },
        factors={
            "kind": kind,
            "cabinet_seats": sum(sim.world.seats.get(pid, 0) for pid in government.party_ids),
            "confidence_seats": _confidence_seats_of(sim, government.party_ids, government.support_ids),
            "mean_platform_distance": distances,
            "signature_gap": _signature_gap(sim, [party.id for party in cabinet + support]),
            "commitments": len(commitments),
            "collapsed_reform": 1.0 if collapsed else 0.0,
            "policy_multiplier": multiplier,
        },
        details={
            "programme": dict(programme),
            "attempts": attempts,
            "commitments": [_commitment_dict(item) for item in commitments],
            "party_platforms": government.party_platforms,
        },
        causes=[cause] if cause else [],
    )
    government.formation_event = event.id
    for commitment in commitments:
        commitment.source_event = event.id
    for party in cabinet + support:
        for other in cabinet + support:
            if party.id == other.id:
                continue
            tie = sim.tie(party.id, other.id)
            tie.coalitions += 1
            tie.trust = clamp(tie.trust + 0.08, -1.0, 1.0)
    sim.world.government = government
    return True


def _negotiate_programme(
    sim: Sim,
    cabinet: list[Party],
    support: list[Party],
) -> tuple[dict[str, float], list[Commitment]]:
    weights = {party.id: max(sim.world.seats.get(party.id, 0), 1) for party in cabinet}
    total = float(sum(weights.values()))
    programme = {dim: 0.0 for dim in DIMENSIONS}
    for party in cabinet:
        share = weights[party.id] / total
        for dim in DIMENSIONS:
            programme[dim] += share * party.platform[dim]
    formateur = cabinet[0]
    commitments: list[Commitment] = []
    juniors = cabinet[1:] + support
    for junior in juniors:
        leader = sim.citizen(junior.leader_id)
        ranked = sorted(
            DIMENSIONS,
            key=lambda dim: leader.importance[dim] * abs(junior.platform[dim] - programme[dim]),
            reverse=True,
        )
        given = 0
        limit = 1 if junior in support else 2
        for issue in ranked:
            if given >= limit:
                break
            gap = junior.platform[issue] - programme[issue]
            if abs(gap) < 10.0:
                continue
            pull = 0.28 if junior in support else 0.55
            pull *= 0.55 + weights.get(junior.id, 1) / total
            proposed = programme[issue] + pull * gap
            formateur_leader = sim.citizen(formateur.leader_id)
            if issue in formateur_leader.non_negotiable:
                tolerance = 24.0 + 20.0 * formateur_leader.compromise
                low = formateur_leader.positions[issue] - tolerance
                high = formateur_leader.positions[issue] + tolerance
                proposed = clamp(proposed, low, high)
            programme[issue] = clamp(proposed, -100.0, 100.0)
            commitment = Commitment(
                id=sim.world.next_commitment_id,
                tick=sim.world.tick,
                creditor_party=junior.id,
                debtor_party=formateur.id,
                issue=issue,
                promised_position=programme[issue],
                tolerance=16.0 if junior in support else 12.0,
                status="active",
                source_event=0,
            )
            sim.world.next_commitment_id += 1
            commitments.append(commitment)
            given += 1
    return programme, commitments


def _member_pressure(sim: Sim, government: Government) -> None:
    """A leader may walk back a concession when members will not tolerate it."""

    leader = sim.citizen(sim.party(government.formateur_party).leader_id)
    party = sim.party(government.formateur_party)
    if not party.members:
        return
    for commitment in list(government.commitments):
        if sim.world.government is None or sim.world.government.id != government.id:
            return
        if commitment.status != "active":
            continue
        issue = commitment.issue
        if sim.world.tick < party.renege_cooldown.get(issue, 0):
            continue
        midpoint = member_median(sim, party.id, issue)
        gap = abs(government.programme[issue] - midpoint)
        leader_gap = abs(government.programme[issue] - leader.positions[issue])
        if gap < 16.0 and leader_gap < 20.0:
            continue
        rigidity = _mean(sim.citizen(cid).ideological_rigidity for cid in party.members)
        pressure = (max(gap, 0.65 * leader_gap) / 100.0) * (0.45 + 0.55 * (1.0 - leader.compromise)) * (0.5 + 0.5 * rigidity)
        if issue in leader.non_negotiable:
            pressure += 0.12
        partner = sim.tie(government.formateur_party, commitment.creditor_party)
        partner_trust = clamp01((partner.trust + 1.0) / 2.0)
        resistance = leader.loyalty * (0.35 + 0.65 * partner_trust)
        if pressure < 0.2 + resistance:
            continue
        probability = clamp((pressure - resistance) * 0.85, 0.0, 0.55)
        draw = sim.rng.internal.random()
        if draw >= probability:
            continue
        before = government.programme[issue]
        government.programme[issue] = clamp(before + 0.55 * (midpoint - before), -100.0, 100.0)
        party.renege_cooldown[issue] = sim.world.tick + 4
        motive = "base_pressure"
        public = "The leadership said the commitment no longer matched its mandate."
        if abs(government.programme[issue] - commitment.promised_position) > commitment.tolerance:
            _break_commitment(
                sim,
                government,
                commitment,
                government.programme[issue],
                motive,
                public,
                probability,
                pressure,
                resistance,
            )


def _fiscal_response(sim: Sim, government: Government) -> tuple[dict[str, float], str | None]:
    programme = dict(government.programme)
    treasury = sim.world.outcomes["treasury"]
    if treasury >= 26.0:
        return programme, None
    leader = sim.citizen(sim.party(government.formateur_party).leader_id)
    party = sim.party(government.formateur_party)
    medians = {dim: member_median(sim, party.id, dim) if party.members else programme[dim] for dim in DIMENSIONS}

    def cost(candidate: dict[str, float]) -> float:
        total = 0.0
        if treasury < 16.0 and candidate["public_services"] > 15.0 and candidate["taxation"] < 10.0:
            total += 0.45
        for dim in DIMENSIONS:
            total += abs(candidate[dim] - leader.positions[dim]) / 140.0 * (0.25 + leader.ideological_rigidity)
            total += abs(candidate[dim] - medians[dim]) / 140.0 * (1.0 - 0.25 * leader.ambition)
        for commitment in government.commitments:
            if commitment.status != "active":
                continue
            if abs(candidate[commitment.issue] - commitment.promised_position) > commitment.tolerance:
                total += 0.28 + 0.3 * leader.loyalty
        return total

    options: list[tuple[float, float, int, dict[str, float], str | None]] = []
    options.append((cost(programme), 0.0, 0, programme, None))
    cut_services = dict(programme)
    if cut_services["public_services"] > 0.0:
        cut_services["public_services"] = clamp(cut_services["public_services"] - 22.0, -100.0, 100.0)
        options.append((cost(cut_services), 22.0, 1, cut_services, "treasury"))
    raise_tax = dict(programme)
    raise_tax["taxation"] = clamp(raise_tax["taxation"] + 18.0, -100.0, 100.0)
    options.append((cost(raise_tax), 18.0, 2, raise_tax, "treasury"))
    cut_ecology = dict(programme)
    if cut_ecology["ecology"] > 0.0:
        cut_ecology["ecology"] = clamp(cut_ecology["ecology"] - 18.0, -100.0, 100.0)
        options.append((cost(cut_ecology), 18.0, 3, cut_ecology, "treasury"))
    options.sort(key=lambda item: (item[0], item[1], item[2]))
    _best_cost, _magnitude, _priority, chosen, motive = options[0]
    if motive is not None:
        government.programme = dict(chosen)
    return chosen, motive


def _check_commitment_gaps(
    sim: Sim,
    government: Government,
    applied: dict[str, float],
    fiscal_motive: str | None,
) -> None:
    for commitment in list(government.commitments):
        if sim.world.government is None or sim.world.government.id != government.id:
            return
        if commitment.status != "active":
            continue
        actual = applied[commitment.issue]
        if abs(actual - commitment.promised_position) <= commitment.tolerance:
            continue
        if fiscal_motive:
            private = "treasury"
            public = "The leadership said the treasury could not support the commitment."
        else:
            private = "programme_shift"
            public = "The leadership said the commitment had become incompatible with its mandate."
        _break_commitment(
            sim,
            government,
            commitment,
            actual,
            private,
            public,
            probability=1.0,
            pressure=abs(actual - commitment.promised_position),
            resistance=0.0,
        )
        if sim.world.government is None or sim.world.government.id != government.id:
            return


def _break_commitment(
    sim: Sim,
    government: Government,
    commitment: Commitment,
    actual: float,
    private_motive: str,
    public_claim: str,
    probability: float,
    pressure: float,
    resistance: float,
) -> None:
    if commitment.status == "broken":
        return
    commitment.status = "broken"
    debtor = sim.party(commitment.debtor_party)
    creditor = sim.party(commitment.creditor_party)
    debtor.promise_keeping = clamp01(debtor.promise_keeping - 0.16)
    debtor.trust_reputation = clamp01(debtor.trust_reputation - 0.1)
    debtor.attention = clamp01(debtor.attention + 0.2)
    outbound = sim.tie(debtor.id, creditor.id)
    outbound.trust = clamp(outbound.trust - 0.35, -1.0, 1.0)
    outbound.hostility = clamp01(outbound.hostility + 0.3)
    outbound.breaches_suffered += 0
    inbound = sim.tie(creditor.id, debtor.id)
    inbound.trust = clamp(inbound.trust - 0.4, -1.0, 1.0)
    inbound.hostility = clamp01(inbound.hostility + 0.35)
    inbound.breaches_suffered += 1
    _hit_leaders(sim, debtor, creditor)
    _remember_breach(sim, debtor, creditor)
    sim.world.outcomes["institutional_trust"] = clamp(
        sim.world.outcomes["institutional_trust"] - 3.0,
        0.0,
        100.0,
    )
    event = sim.emit(
        "commitment_broken",
        (
            f"{debtor.name} moved {commitment.issue.replace('_', ' ')} to {int(round(actual))}, "
            f"breaking a promise of {int(round(commitment.promised_position))} to {creditor.name}. "
            f"Privately the driver was {private_motive}. Public claim: {public_claim}"
        ),
        actors={
            "party": debtor.id,
            "creditor": creditor.id,
            "government": government.id,
            "commitment": commitment.id,
        },
        factors={
            "issue": commitment.issue,
            "promised": commitment.promised_position,
            "actual": actual,
            "private_motive": private_motive,
            "public_claim": public_claim,
            "pressure": pressure,
            "resistance": resistance,
            "probability": probability,
            "debtor_promise_keeping": debtor.promise_keeping,
        },
        causes=[commitment.source_event] if commitment.source_event else [],
    )
    _maybe_withdraw(sim, government, creditor, debtor, event.id, private_motive)


def _maybe_withdraw(
    sim: Sim,
    government: Government,
    creditor: Party,
    debtor: Party,
    breach_event: int,
    motive: str,
) -> None:
    if creditor.status != "active":
        return
    if creditor.id not in government.party_ids and creditor.id not in government.support_ids:
        return
    leader = sim.citizen(creditor.leader_id)
    mine = _score_pair(sim, creditor, debtor)
    stay = mine["value"] - 0.45 * (1.0 - leader.compromise)
    if stay >= sim.config.alliance_threshold and leader.loyalty > 0.45:
        return
    probability = clamp(0.3 + (sim.config.alliance_threshold - stay), 0.2, 0.9)
    probability *= 1.0 - 0.35 * leader.loyalty
    draw = sim.rng.internal.random()
    if draw >= probability:
        return
    if creditor.id in government.party_ids:
        government.party_ids = [pid for pid in government.party_ids if pid != creditor.id]
    government.support_ids = [pid for pid in government.support_ids if pid != creditor.id]
    event = sim.emit(
        "party_withdrew",
        (
            f"{creditor.name} withdrew from the government after {debtor.name} broke "
            f"a commitment ({motive})."
        ),
        actors={"party": creditor.id, "debtor": debtor.id, "government": government.id},
        factors={
            "alliance_value": mine["value"],
            "stay_value": stay,
            "probability": probability,
            "draw": draw,
            "leader_loyalty": leader.loyalty,
            "leader_compromise": leader.compromise,
        },
        causes=[breach_event],
    )
    ensure_confidence(sim, event.id)


def _enact(
    sim: Sim,
    government: Government,
    applied: dict[str, float],
    fiscal_motive: str | None,
) -> None:
    promise = _mean(
        sim.party(pid).promise_keeping for pid in government.party_ids if _alive(sim, pid)
    )
    strength = sim.config.policy_strength * government.policy_multiplier
    before = dict(sim.world.outcomes)
    updated, deltas = step_outcomes(before, applied, strength, promise or 0.5)
    sim.world.outcomes = updated
    welfares: list[float] = []
    for citizen in sim.citizens():
        welfare = personal_welfare(citizen, updated, applied)
        welfares.append(welfare)
        citizen.satisfaction = clamp01(0.82 * citizen.satisfaction + 0.18 * welfare)
        if citizen.satisfaction < 0.34:
            citizen.engagement = clamp01(citizen.engagement - 0.012 * (0.7 + citizen.stubbornness))
            citizen.disappointment = clamp01(citizen.disappointment + 0.025)
        elif citizen.satisfaction > 0.62:
            citizen.engagement = clamp01(citizen.engagement + 0.006)
            citizen.disappointment = max(0.0, citizen.disappointment - 0.02)
        if sim.config.preference_adaptation > 0.0:
            adapt_preferences(citizen, updated, applied, sim.config.preference_adaptation)
        _belief_stubbornness(sim, citizen, government)
    mean_welfare = sum(welfares) / max(len(welfares), 1)
    delta_welfare = mean_welfare - sim.world.previous_mean_welfare
    sim.world.previous_mean_welfare = sim.world.mean_welfare
    sim.world.mean_welfare = mean_welfare
    sim.world.mean_satisfaction = _mean(citizen.satisfaction for citizen in sim.citizens())
    cabinet_seats = sum(sim.world.seats.get(pid, 0) for pid in government.party_ids) or 1
    for pid in government.party_ids:
        if not _alive(sim, pid):
            continue
        share = sim.world.seats.get(pid, 0) / cabinet_seats
        party = sim.party(pid)
        party.competence = clamp01(party.competence + 0.45 * delta_welfare * share)
        party.trust_reputation = clamp01(party.trust_reputation + 0.25 * delta_welfare * share)
    peak = max(abs(value) for value in deltas.values()) if deltas else 0.0
    notable = peak >= 3.5 or fiscal_motive is not None or sim.world.tick % 4 == 0
    if not notable:
        return
    sim.emit(
        "policy_enacted",
        (
            f"The government applied its programme"
            f"{' under a treasury constraint' if fiscal_motive else ''}. "
            f"Mean welfare is {mean_welfare:.2f}."
        ),
        significance="major" if peak >= 3.5 or fiscal_motive else "minor",
        actors={"government": government.id, "parties": list(government.party_ids)},
        factors={
            "mean_welfare": mean_welfare,
            "welfare_change": delta_welfare,
            "mean_satisfaction": sim.world.mean_satisfaction,
            "peak_outcome_shift": peak,
            "fiscal_motive": fiscal_motive or "none",
            "treasury": updated["treasury"],
            "institutional_trust": updated["institutional_trust"],
        },
        details={"official": dict(government.programme), "applied": applied, "deltas": deltas},
        causes=[government.formation_event],
    )


def _belief_stubbornness(sim: Sim, citizen: object, government: Government) -> None:
    if not isinstance(citizen, type(sim.citizen(0))):
        return
    for pid in government.party_ids:
        belief = citizen.beliefs.get(pid)  # type: ignore[attr-defined]
        if belief is None:
            continue
        party = sim.party(pid)
        if (
            citizen.stubbornness > 0.65  # type: ignore[attr-defined]
            and citizen.last_vote == pid  # type: ignore[attr-defined]
            and party.competence < belief.perceived_competence
        ):
            continue
        belief.perceived_competence = clamp01(
            0.8 * belief.perceived_competence + 0.2 * party.competence
        )
        belief.perceived_promise = clamp01(
            0.8 * belief.perceived_promise + 0.2 * party.promise_keeping
        )


def _hit_leaders(sim: Sim, debtor: Party, creditor: Party) -> None:
    relation = sim.relationship(creditor.leader_id, debtor.leader_id)
    if relation is not None:
        relation.trust = clamp(relation.trust - 0.4, -1.0, 1.0)
        relation.rivalry = clamp01(relation.rivalry + 0.28)
    back = sim.relationship(debtor.leader_id, creditor.leader_id)
    if back is not None:
        back.trust = clamp(back.trust - 0.25, -1.0, 1.0)
        back.rivalry = clamp01(back.rivalry + 0.18)


def _remember_breach(sim: Sim, debtor: Party, creditor: Party) -> None:
    for citizen_id in sorted(creditor.members):
        sim.remember(
            sim.citizen(citizen_id),
            kind="breach_suffered",
            subject=debtor.id,
            valence=-0.75,
            weight=1.0,
        )
    for citizen_id in sorted(debtor.members):
        citizen = sim.citizen(citizen_id)
        # Members who disliked the concession are less angry than those who wanted it kept.
        valence = -0.15 if citizen.ambition > citizen.loyalty else -0.35
        sim.remember(citizen, kind="breach_committed", subject=debtor.id, valence=valence, weight=0.6)
    sim.remember(
        sim.citizen(creditor.leader_id),
        kind="personal_breach",
        subject=debtor.id,
        valence=-0.9,
        weight=1.2,
    )


def _ranked_partners(
    sim: Sim,
    formateur: Party,
    seated: list[Party],
) -> list[tuple[Party, dict[str, float], dict[str, float], str | None]]:
    ranked: list[tuple[float, int, Party, dict[str, float], dict[str, float], str | None]] = []
    for other in seated:
        if other.id == formateur.id:
            continue
        mine = _score_pair(sim, formateur, other)
        theirs = _score_pair(sim, other, formateur)
        programme, _commitments = _negotiate_programme(sim, [formateur, other], [])
        # Negotiation above consumes commitment ids. Roll them back: this was hypothetical.
        # Commitments created as a side effect must not survive a hypothetical.
        sim.world.next_commitment_id -= len(_commitments)
        veto = non_negotiable_veto(sim.citizen(formateur.leader_id), programme)
        if veto is None:
            veto = non_negotiable_veto(sim.citizen(other.leader_id), programme)
        score = min(mine["value"], theirs["value"])
        ranked.append((score, other.id, other, mine, theirs, veto))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    return [(party, mine, theirs, veto) for _score, _pid, party, mine, theirs, veto in ranked]


def _cabinet_accepts(sim: Sim, cabinet: list[Party], candidate: Party) -> bool:
    trial = cabinet + [candidate]
    programme, created = _negotiate_programme(sim, trial, [])
    sim.world.next_commitment_id -= len(created)
    floor = sim.config.alliance_threshold * 0.8
    for party in cabinet:
        mine = _score_pair(sim, party, candidate)
        theirs = _score_pair(sim, candidate, party)
        if mine["value"] < floor or theirs["value"] < floor:
            return False
        if non_negotiable_veto(sim.citizen(party.leader_id), programme):
            return False
        if non_negotiable_veto(sim.citizen(candidate.leader_id), programme):
            return False
    return True


def _score_pair(sim: Sim, actor: Party, other: Party) -> dict[str, float]:
    leader = sim.citizen(actor.leader_id)
    other_leader = sim.citizen(other.leader_id)
    issues = _relevant_issues(leader, other_leader)
    agreement = alignment(actor.platform, other.platform, None, issues)
    seats_i = sim.world.seats.get(actor.id, 0)
    seats_j = sim.world.seats.get(other.id, 0)
    majority = sim.config.parliament_seats // 2 + 1
    if seats_i >= majority:
        power = 0.12
    else:
        combined = seats_i + seats_j
        if combined >= majority:
            balance = 1.0 - abs(seats_i - seats_j) / max(majority, 1)
            power = clamp01(0.5 + 0.45 * balance)
        else:
            power = clamp01(0.4 * combined / max(majority, 1))
    if sim.config.relationship_influence <= 0.0:
        trust = 0.0
    else:
        relation = sim.relationship(actor.leader_id, other.leader_id)
        trust = relation.trust if relation is not None else sim.tie(actor.id, other.id).trust
    enemy = _shared_enemy(sim, actor.id, other.id)
    tie = sim.tie(actor.id, other.id)
    hostility = tie.hostility
    if sim.config.relationship_influence > 0.0:
        relation = sim.relationship(actor.leader_id, other.leader_id)
        if relation is not None:
            hostility = max(hostility, relation.rivalry)
    hypothetical = {
        dim: 0.5 * (actor.platform[dim] + other.platform[dim]) for dim in DIMENSIONS
    }
    supporter_cost = _supporter_cost(sim, actor, hypothetical)
    return alliance_value(
        evaluator=leader,
        policy_agreement=agreement,
        power_benefit=power,
        leader_trust=trust,
        shared_enemy=enemy,
        hostility=hostility,
        supporter_cost=supporter_cost,
        config=sim.config,
    )


def _relevant_issues(left: object, right: object) -> list[str]:
    issues = set(left.non_negotiable) | set(right.non_negotiable)  # type: ignore[attr-defined]
    left_top = sorted(DIMENSIONS, key=lambda dim: left.importance[dim], reverse=True)[:3]  # type: ignore[attr-defined]
    right_top = sorted(DIMENSIONS, key=lambda dim: right.importance[dim], reverse=True)[:3]  # type: ignore[attr-defined]
    issues.update(left_top)
    issues.update(right_top)
    return sorted(issues)


def _shared_enemy(sim: Sim, left: int, right: int) -> float:
    best = 0.0
    for party in sim.active_parties():
        if party.id in {left, right}:
            continue
        hostile_left = sim.tie(left, party.id).hostility
        hostile_right = sim.tie(right, party.id).hostility
        if hostile_left > 0.25 and hostile_right > 0.25:
            threat = sim.world.seats.get(party.id, 0) / max(sim.config.parliament_seats, 1)
            best = max(best, min(hostile_left, hostile_right) * (0.4 + threat))
    government = sim.world.government
    if government is not None and left not in government.party_ids and right not in government.party_ids:
        best = max(best, 0.2)
    return clamp01(best)


def _supporter_cost(sim: Sim, party: Party, programme: dict[str, float]) -> float:
    if not party.members:
        return 0.0
    current = _mean(
        alignment(sim.citizen(cid).positions, party.platform, sim.citizen(cid).importance)
        for cid in party.members
    )
    proposed = _mean(
        alignment(sim.citizen(cid).positions, programme, sim.citizen(cid).importance)
        for cid in party.members
    )
    rigidity = _mean(sim.citizen(cid).ideological_rigidity for cid in party.members)
    leader = sim.citizen(party.leader_id)
    hits = 0.0
    for issue in leader.non_negotiable:
        if abs(leader.positions[issue] - programme[issue]) > 30.0:
            hits += 0.2
    return clamp01((current - proposed) * (0.7 + rigidity) + hits)


def _confidence_seats(sim: Sim, government: Government) -> int:
    return _confidence_seats_of(sim, government.party_ids, government.support_ids)


def _confidence_seats_of(sim: Sim, cabinet: list[int], support: list[int]) -> int:
    ids = list(cabinet) + [pid for pid in support if pid not in cabinet]
    return sum(sim.world.seats.get(pid, 0) for pid in ids)


def _alive(sim: Sim, party_id: int) -> bool:
    party = sim.world.parties.get(party_id)
    return party is not None and party.status == "active"


def _name(sim: Sim, party_id: int) -> str:
    party = sim.world.parties.get(party_id)
    return party.name if party else f"party {party_id}"


def _adjust_promise(sim: Sim, party_id: int, delta: float) -> None:
    if not _alive(sim, party_id):
        return
    party = sim.party(party_id)
    party.promise_keeping = clamp01(party.promise_keeping + delta)


def _rejection(
    party_id: int,
    mine: dict[str, float],
    theirs: dict[str, float],
    reason: str,
) -> dict[str, object]:
    return {
        "party": party_id,
        "our_value": round(mine["value"], 4),
        "their_value": round(theirs["value"], 4),
        "reason": reason,
        "policy": round(mine["policy"], 4),
        "power": round(mine["power"], 4),
        "trust": round(mine["trust"], 4),
        "hostility": round(mine["hostility"], 4),
        "supporter_cost": round(mine["supporter_cost"], 4),
    }


def _commitment_dict(commitment: Commitment) -> dict[str, object]:
    return {
        "id": commitment.id,
        "creditor": commitment.creditor_party,
        "debtor": commitment.debtor_party,
        "issue": commitment.issue,
        "promised": commitment.promised_position,
        "tolerance": commitment.tolerance,
        "status": commitment.status,
    }


def _mean(values: object) -> float:
    data = list(values)  # type: ignore[arg-type]
    if not data:
        return 0.0
    return sum(data) / len(data)


def _signature_gap(sim: Sim, party_ids: list[int]) -> float:
    if len(party_ids) < 2:
        return 0.0
    gaps = []
    for index, left in enumerate(party_ids):
        for right in party_ids[index + 1 :]:
            gaps.append(signature_gap(sim.party(left).platform, sim.party(right).platform))
    return sum(gaps) / len(gaps)


def _pairwise_distances(sim: Sim, party_ids: list[int]) -> float:
    if len(party_ids) < 2:
        return 0.0
    gaps: list[float] = []
    for index, left in enumerate(party_ids):
        for right in party_ids[index + 1 :]:
            gaps.append(
                1.0
                - alignment(
                    sim.party(left).platform,
                    sim.party(right).platform,
                )
            )
    return sum(gaps) / len(gaps)
