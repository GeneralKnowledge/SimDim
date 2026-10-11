"""What citizens know.

Learning, stale platforms, and rumours are explicit. A citizen with low
attentiveness does not carry a full copy of every platform.
"""

from __future__ import annotations

from simdemocracy.config import DIMENSIONS
from simdemocracy.context import Sim
from simdemocracy.models import Belief, Citizen, Party
from simdemocracy.utility import clamp, clamp01, known_issues_for


def decay_attention(sim: Sim) -> None:
    for party in sim.active_parties():
        party.attention = clamp01(party.attention * 0.9)
        party.capital = clamp01(party.capital * 0.985 + 0.004 * len(party.members))
        party.capacity = clamp01(0.12 + 0.015 * len(party.members) + 0.12 * _leader_sociability(sim, party))


def spread_information(sim: Sim) -> None:
    parties = sim.active_parties()
    for citizen in sim.citizens():
        for party in parties:
            if citizen.party_id == party.id:
                _set_belief(citizen, party, accurate=True, tick=sim.world.tick)
                continue
            chance = _learn_chance(sim, citizen, party)
            if chance <= 0.0:
                continue
            if sim.rng.info.random() > chance:
                continue
            _learn(sim, citizen, party)


def spread_rumors(sim: Sim) -> None:
    population = sim.citizens()
    if not population:
        return
    attempts = int(sim.config.rumor_rate * len(population))
    for _ in range(attempts):
        listener = population[sim.rng.rumor.randrange(len(population))]
        if listener.attentiveness > 0.72:
            continue
        neighbors = sim.world.neighbors.get(listener.id, [])
        if not neighbors:
            continue
        source = sim.citizen(neighbors[sim.rng.rumor.randrange(len(neighbors))])
        if not source.beliefs:
            continue
        party_ids = sorted(source.beliefs)
        party_id = party_ids[sim.rng.rumor.randrange(len(party_ids))]
        if party_id not in sim.world.parties:
            continue
        source_belief = source.beliefs[party_id]
        if not source_belief.known_issues:
            continue
        issue = source_belief.known_issues[
            sim.rng.rumor.randrange(len(source_belief.known_issues))
        ]
        noise = sim.rng.rumor.uniform(-14.0, 14.0) * (1.15 - listener.attentiveness)
        perceived = dict(source_belief.perceived_platform)
        perceived[issue] = clamp(perceived.get(issue, 0.0) + noise, -100.0, 100.0)
        competence = clamp01(
            source_belief.perceived_competence + sim.rng.rumor.uniform(-0.08, 0.08)
        )
        listener.beliefs[party_id] = Belief(
            party_id=party_id,
            known_issues=list(source_belief.known_issues),
            perceived_platform=perceived,
            perceived_competence=competence,
            perceived_promise=source_belief.perceived_promise,
            updated_tick=sim.world.tick,
        )


def campaign_visibility(sim: Sim) -> None:
    for party in sim.active_parties():
        boost = 0.22 + 0.15 * party.capital
        party.attention = clamp01(party.attention + boost)
        party.capital = clamp01(party.capital - 0.05)
    # A second learning pass during the campaign, still using the info stream.
    spread_information(sim)


def _learn_chance(sim: Sim, citizen: Citizen, party: Party) -> float:
    chance = party.attention * (0.08 + 0.55 * citizen.attentiveness)
    neighbors = sim.world.neighbors.get(citizen.id, [])
    if any(sim.citizen(nid).party_id == party.id for nid in neighbors):
        chance = max(chance, 0.18 + 0.35 * citizen.sociability)
    if party.attention > 0.75:
        chance = max(chance, 0.15 + 0.4 * citizen.attentiveness)
    return clamp01(chance)


def _learn(sim: Sim, citizen: Citizen, party: Party) -> None:
    issues = known_issues_for(citizen)
    previous = citizen.beliefs.get(party.id)
    perceived: dict[str, float] = {}
    noise_scale = (1.0 - citizen.attentiveness) * 16.0
    for issue in issues:
        noise = sim.rng.info.uniform(-noise_scale, noise_scale) if noise_scale > 0.4 else 0.0
        observed = clamp(party.platform[issue] + noise, -100.0, 100.0)
        if (
            previous
            and issue in previous.perceived_platform
            and citizen.stubbornness > 0.5
        ):
            hold = citizen.stubbornness * 0.65
            observed = previous.perceived_platform[issue] * hold + observed * (1.0 - hold)
        perceived[issue] = observed
    competence = party.competence
    promise = party.promise_keeping
    if previous is not None:
        blend = 0.35 + 0.4 * citizen.attentiveness
        competence = previous.perceived_competence * (1.0 - blend) + party.competence * blend
        promise = previous.perceived_promise * (1.0 - blend) + party.promise_keeping * blend
        if citizen.stubbornness > 0.65 and citizen.last_vote == party.id and party.competence < previous.perceived_competence:
            competence = previous.perceived_competence
    citizen.beliefs[party.id] = Belief(
        party_id=party.id,
        known_issues=issues,
        perceived_platform=perceived,
        perceived_competence=clamp01(competence),
        perceived_promise=clamp01(promise),
        updated_tick=sim.world.tick,
    )


def _set_belief(citizen: Citizen, party: Party, *, accurate: bool, tick: int) -> None:
    if not accurate:
        return
    citizen.beliefs[party.id] = Belief(
        party_id=party.id,
        known_issues=list(DIMENSIONS),
        perceived_platform=dict(party.platform),
        perceived_competence=party.competence,
        perceived_promise=party.promise_keeping,
        updated_tick=tick,
    )


def _leader_sociability(sim: Sim, party: Party) -> float:
    if party.leader_id not in sim.world.citizens:
        return 0.3
    return sim.citizen(party.leader_id).sociability
