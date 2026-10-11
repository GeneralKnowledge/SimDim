"""Boundary for strategic characters.

Algorithmic citizens act through the tick rules. A later decision provider can
propose structured actions for the small set of strategic characters. This
module checks whether a proposal is legal. It does not apply world edits, and
it does not call a language model. Recorded proposals can be replayed; a
failed call falls back to the algorithmic rules already running in the engine.
"""

from __future__ import annotations

from dataclasses import dataclass

from simdemocracy.context import Sim
from simdemocracy.utility import clamp

ACTIONS = (
    "offer_coalition",
    "reject_demand",
    "propose_leadership_challenge",
    "shift_platform",
    "publish_statement",
    "withdraw_from_government",
    "invite_member",
)


@dataclass
class ActionProposal:
    actor_id: int
    action: str
    payload: dict[str, object]
    reason: str
    expected_outcome: str


def character_report(sim: Sim, citizen_id: int) -> dict[str, object]:
    citizen = sim.citizen(citizen_id)
    party = sim.world.parties.get(citizen.party_id) if citizen.party_id is not None else None
    government = sim.world.government
    recent = [
        {"id": event.id, "tick": event.tick, "type": event.type, "summary": event.summary}
        for event in sim.ledger.events[-8:]
    ]
    return {
        "tick": sim.world.tick,
        "citizen": {
            "id": citizen.id,
            "name": citizen.name,
            "ambition": citizen.ambition,
            "loyalty": citizen.loyalty,
            "compromise": citizen.compromise,
            "rigidity": citizen.ideological_rigidity,
            "non_negotiable": list(citizen.non_negotiable),
            "positions": dict(citizen.positions),
        },
        "party": None
        if party is None
        else {
            "id": party.id,
            "name": party.name,
            "leader_id": party.leader_id,
            "is_leader": party.leader_id == citizen.id,
            "members": len(party.members),
            "seats": sim.world.seats.get(party.id, 0),
            "platform": dict(party.platform),
            "promise_keeping": party.promise_keeping,
        },
        "government": None
        if government is None
        else {
            "id": government.id,
            "kind": government.kind,
            "parties": list(government.party_ids),
            "support": list(government.support_ids),
            "programme": dict(government.programme),
        },
        "recent_events": recent,
    }


def validate_action(sim: Sim, proposal: ActionProposal) -> tuple[bool, str]:
    if proposal.action not in ACTIONS:
        return False, f"Unknown action {proposal.action}"
    if proposal.actor_id not in sim.world.citizens:
        return False, "Actor does not exist"
    citizen = sim.citizen(proposal.actor_id)
    if not citizen.strategic:
        return False, "Actor is not a strategic character"
    party = sim.world.parties.get(citizen.party_id) if citizen.party_id is not None else None

    if proposal.action in {
        "offer_coalition",
        "reject_demand",
        "shift_platform",
        "withdraw_from_government",
        "propose_leadership_challenge",
    }:
        if party is None or party.status != "active":
            return False, "Actor does not lead an active party"
        if party.leader_id != citizen.id and proposal.action != "propose_leadership_challenge":
            return False, "Actor lacks authority for that party action"
        if proposal.action == "propose_leadership_challenge" and party.leader_id == citizen.id:
            return False, "The leader cannot challenge their own leadership"

    if proposal.action == "offer_coalition":
        target = proposal.payload.get("party_id")
        if not isinstance(target, int) or target not in sim.world.parties:
            return False, "Target party does not exist"
        if sim.party(target).status != "active":
            return False, "Target party is not active"
        if party is not None and target == party.id:
            return False, "A party cannot form a coalition with itself"
        return True, "Coalition offer is a legal proposal"

    if proposal.action == "shift_platform":
        issue = proposal.payload.get("issue")
        value = proposal.payload.get("position")
        if not isinstance(issue, str) or issue not in citizen.positions:
            return False, "Unknown policy dimension"
        if not isinstance(value, (int, float)):
            return False, "Position must be numeric"
        if not -100.0 <= float(value) <= 100.0:
            return False, "Position is outside -100 to 100"
        if party is not None and abs(float(value) - party.platform[issue]) > 25.0:
            return False, "Platform shifts are limited to 25 points at a time"
        return True, "Platform shift is within authority"

    if proposal.action == "withdraw_from_government":
        government = sim.world.government
        if government is None or party is None:
            return False, "There is no government to leave"
        if party.id not in government.party_ids and party.id not in government.support_ids:
            return False, "Party is not supporting the government"
        return True, "Withdrawal is legally available"

    if proposal.action == "invite_member":
        target = proposal.payload.get("citizen_id")
        if party is None:
            return False, "Actor has no party"
        if not isinstance(target, int) or target not in sim.world.citizens:
            return False, "Invitee does not exist"
        if target in party.members:
            return False, "Invitee is already a member"
        return True, "Invitation is a legal proposal"

    if proposal.action == "publish_statement":
        text = proposal.payload.get("text")
        if not isinstance(text, str) or not text.strip():
            return False, "Statement text is empty"
        if len(text) > 400:
            return False, "Statement exceeds 400 characters"
        return True, "Statement can be recorded without changing institutional state"

    if proposal.action in {"reject_demand", "propose_leadership_challenge"}:
        return True, "Proposal is structurally legal"

    return False, "Proposal was not accepted"


def clamp_shift(current: float, proposed: float, limit: float = 25.0) -> float:
    delta = clamp(proposed - current, -limit, limit)
    return current + delta
