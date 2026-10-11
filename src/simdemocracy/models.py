"""State objects. The engine mutates these; the ledger records why."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class MemoryItem:
    tick: int
    kind: str
    subject: int
    valence: float
    weight: float = 1.0


@dataclass
class Belief:
    party_id: int
    known_issues: list[str]
    perceived_platform: dict[str, float]
    perceived_competence: float
    perceived_promise: float
    updated_tick: int


@dataclass
class Citizen:
    id: int
    name: str
    ambition: float
    risk_tolerance: float
    loyalty: float
    sociability: float
    conformity: float
    compromise: float
    ideological_rigidity: float
    stubbornness: float
    attentiveness: float
    overconfidence: float
    positions: dict[str, float]
    importance: dict[str, float]
    certainty: dict[str, float]
    non_negotiable: list[str]
    resources: float
    public_service_reliance: float
    environmental_exposure: float
    engagement: float
    satisfaction: float
    influence: float
    strategic: bool = False
    party_id: int | None = None
    memory: list[MemoryItem] = field(default_factory=list)
    beliefs: dict[int, Belief] = field(default_factory=dict)
    joined_tick: int | None = None
    last_vote: int | None = None
    disappointment: float = 0.0


@dataclass
class Relationship:
    trust: float
    affinity: float
    rivalry: float
    obligation: float = 0.0


@dataclass
class PartyTie:
    """Directed organisational memory between two parties."""

    trust: float = 0.05
    hostility: float = 0.0
    coalitions: int = 0
    breaches_suffered: int = 0


@dataclass
class Faction:
    id: int
    party_id: int
    issue: str
    direction: int
    member_ids: list[int]
    formed_tick: int
    leader_id: int | None


@dataclass
class Commitment:
    id: int
    tick: int
    creditor_party: int
    debtor_party: int
    issue: str
    promised_position: float
    tolerance: float
    status: str
    source_event: int


@dataclass
class Government:
    id: int
    formed_tick: int
    kind: str
    formateur_party: int
    party_ids: list[int]
    support_ids: list[int]
    programme: dict[str, float]
    commitments: list[Commitment]
    policy_multiplier: float
    party_platforms: dict[int, dict[str, float]]
    formation_event: int
    ended_tick: int | None = None
    end_reason: str | None = None
    end_event: int | None = None

    def cabinet_ids(self) -> list[int]:
        return list(self.party_ids)

    def confidence_ids(self) -> list[int]:
        return list(self.party_ids) + [
            pid for pid in self.support_ids if pid not in self.party_ids
        ]


@dataclass
class Party:
    id: int
    name: str
    founder_id: int
    leader_id: int
    platform: dict[str, float]
    members: set[int]
    founded_tick: int
    grace_until: int
    status: str = "active"
    capacity: float = 0.25
    attention: float = 0.8
    capital: float = 0.3
    trust_reputation: float = 0.55
    competence: float = 0.5
    promise_keeping: float = 0.66
    factions: list[Faction] = field(default_factory=list)
    parent_id: int | None = None
    merged_into: int | None = None
    dissolved_tick: int | None = None
    leadership_cooldown_until: int = 0
    split_cooldown_until: int = 0
    merge_cooldown_until: int = 0
    renege_cooldown: dict[str, int] = field(default_factory=dict)
    event_ids: list[int] = field(default_factory=list)
    low_member_ticks: int = 0
    founding_event: int | None = None


@dataclass
class World:
    tick: int
    citizens: dict[int, Citizen]
    parties: dict[int, Party]
    relationships: dict[tuple[int, int], Relationship]
    neighbors: dict[int, list[int]]
    ties: dict[tuple[int, int], PartyTie]
    used_party_names: set[str]
    seats: dict[int, int]
    outcomes: dict[str, float]
    government: Government | None = None
    past_governments: list[Government] = field(default_factory=list)
    last_election_tick: int | None = None
    forced_election_tick: int | None = None
    election_lock_until: int = 0
    next_party_id: int = 1
    next_government_id: int = 1
    next_commitment_id: int = 1
    next_faction_id: int = 1
    initial_positions: dict[int, dict[str, float]] = field(default_factory=dict)
    mean_satisfaction: float = 0.55
    mean_welfare: float = 0.55
    previous_mean_welfare: float = 0.55
    last_policy_tick: int = 0
    splits_this_tick: int = 0
