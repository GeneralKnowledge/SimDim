"""Export a run. The observer reads this document and does not recompute politics."""

from __future__ import annotations

import json
from pathlib import Path

from simdemocracy.context import Sim
from simdemocracy.explain import chronicle
from simdemocracy.metrics import compute_metrics
from simdemocracy.version import SIMULATION_VERSION


def export_history(sim: Sim) -> dict[str, object]:
    metrics = compute_metrics(sim)
    return {
        "simulation_version": SIMULATION_VERSION,
        "seed": sim.seed,
        "ticks_run": sim.world.tick,
        "config": sim.config.to_dict(),
        "events": [event.to_dict() for event in sim.ledger.events],
        "snapshots": sim.snapshots,
        "governments": _governments(sim),
        "final": {
            "outcomes": dict(sim.world.outcomes),
            "parties": [_party(sim, party_id) for party_id in sorted(sim.world.parties)],
            "citizens": [_citizen(sim, citizen_id) for citizen_id in sorted(sim.world.citizens)],
            "government": _current_government(sim),
            "mean_satisfaction": sim.world.mean_satisfaction,
            "mean_engagement": sum(c.engagement for c in sim.citizens()) / max(len(sim.world.citizens), 1),
        },
        "metrics": metrics,
    }


def write_run(sim: Sim, directory: str | Path) -> dict[str, object]:
    path = Path(directory)
    path.mkdir(parents=True, exist_ok=True)
    history = export_history(sim)
    (path / "history.json").write_text(json.dumps(history, indent=2), encoding="utf-8")
    (path / "chronicle.md").write_text(chronicle(sim.ledger.events), encoding="utf-8")
    (path / "metrics.json").write_text(json.dumps(history["metrics"], indent=2), encoding="utf-8")
    return history


def _governments(sim: Sim) -> list[dict[str, object]]:
    records = list(sim.world.past_governments)
    if sim.world.government is not None:
        records.append(sim.world.government)
    output = []
    for government in records:
        output.append(
            {
                "id": government.id,
                "kind": government.kind,
                "formateur_party": government.formateur_party,
                "party_ids": list(government.party_ids),
                "support_ids": list(government.support_ids),
                "formed_tick": government.formed_tick,
                "ended_tick": government.ended_tick,
                "end_reason": government.end_reason,
                "programme": dict(government.programme),
                "party_platforms": government.party_platforms,
                "policy_multiplier": government.policy_multiplier,
                "commitments": [
                    {
                        "id": item.id,
                        "creditor": item.creditor_party,
                        "debtor": item.debtor_party,
                        "issue": item.issue,
                        "promised": item.promised_position,
                        "tolerance": item.tolerance,
                        "status": item.status,
                    }
                    for item in government.commitments
                ],
            }
        )
    return output


def _current_government(sim: Sim) -> dict[str, object] | None:
    government = sim.world.government
    if government is None:
        return None
    return {
        "id": government.id,
        "kind": government.kind,
        "formateur_party": government.formateur_party,
        "party_ids": list(government.party_ids),
        "support_ids": list(government.support_ids),
        "formed_tick": government.formed_tick,
        "programme": dict(government.programme),
    }


def _party(sim: Sim, party_id: int) -> dict[str, object]:
    party = sim.party(party_id)
    founder = sim.world.citizens.get(party.founder_id)
    leader = sim.world.citizens.get(party.leader_id)
    return {
        "id": party.id,
        "name": party.name,
        "status": party.status,
        "founder_id": party.founder_id,
        "founder_name": founder.name if founder else None,
        "leader_id": party.leader_id,
        "leader_name": leader.name if leader else None,
        "founded_tick": party.founded_tick,
        "dissolved_tick": party.dissolved_tick,
        "parent_id": party.parent_id,
        "merged_into": party.merged_into,
        "platform": dict(party.platform),
        "members": sorted(party.members),
        "member_count": len(party.members),
        "seats": sim.world.seats.get(party.id, 0),
        "trust_reputation": party.trust_reputation,
        "competence": party.competence,
        "promise_keeping": party.promise_keeping,
        "attention": party.attention,
        "capacity": party.capacity,
        "factions": [
            {
                "id": faction.id,
                "issue": faction.issue,
                "direction": faction.direction,
                "members": len(faction.member_ids),
                "formed_tick": faction.formed_tick,
                "leader_id": faction.leader_id,
            }
            for faction in party.factions
        ],
        "event_ids": list(party.event_ids),
    }


def _citizen(sim: Sim, citizen_id: int) -> dict[str, object]:
    citizen = sim.citizen(citizen_id)
    return {
        "id": citizen.id,
        "name": citizen.name,
        "party_id": citizen.party_id,
        "strategic": citizen.strategic,
        "influence": citizen.influence,
        "ambition": citizen.ambition,
        "loyalty": citizen.loyalty,
        "compromise": citizen.compromise,
        "ideological_rigidity": citizen.ideological_rigidity,
        "attentiveness": citizen.attentiveness,
        "engagement": citizen.engagement,
        "satisfaction": citizen.satisfaction,
        "disappointment": citizen.disappointment,
        "resources": citizen.resources,
        "positions": dict(citizen.positions),
        "importance": dict(citizen.importance),
        "non_negotiable": list(citizen.non_negotiable),
    }
