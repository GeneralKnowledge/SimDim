"""Versioned simulation rules.

These are incentives and institutional settings. Nothing here schedules a
story. Ablation experiments turn individual mechanisms toward zero.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from simdemocracy.version import SIMULATION_VERSION

# Positive pole (+100) for each independent axis.
# Axes are not a political compass: any combination is allowed.
DIMENSIONS: tuple[str, ...] = (
    "distribution",
    "taxation",
    "public_services",
    "authority",
    "liberty",
    "openness",
    "ecology",
    "tradition",
)

POSITIVE_POLE: dict[str, str] = {
    "distribution": "equal rewards",
    "taxation": "high taxation",
    "public_services": "collective provision",
    "authority": "centralised power",
    "liberty": "individual autonomy",
    "openness": "open membership and exchange",
    "ecology": "environmental protection",
    "tradition": "preservation of existing customs",
}

NEGATIVE_POLE: dict[str, str] = {
    "distribution": "unequal rewards",
    "taxation": "low taxation",
    "public_services": "private provision",
    "authority": "decentralised power",
    "liberty": "social control",
    "openness": "restriction",
    "ecology": "immediate production",
    "tradition": "rapid change",
}

ELECTORAL_SYSTEMS = ("dhondt", "sainte_lague")


@dataclass
class Config:
    population: int = 300
    ticks: int = 120
    election_interval: int = 12
    parliament_seats: int = 61
    electoral_system: str = "dhondt"
    electoral_threshold: float = 0.0

    latent_groups: int = 5
    preference_noise: float = 14.0
    homophily: float = 0.72

    party_formation_cost: float = 0.58
    min_cluster: int = 10
    represented_alignment: float = 0.80
    max_foundings_per_tick: int = 1
    founding_attempts_per_tick: int = 8
    founding_grace_ticks: int = 8
    min_members: int = 3
    recruitment_per_party: int = 6
    cluster_alignment: float = 0.84

    relationship_influence: float = 1.0
    ambition_scale: float = 1.0
    preference_adaptation: float = 1.0
    rumor_rate: float = 0.06
    memory_half_life: float = 18.0

    alliance_threshold: float = 0.08
    turnout_threshold: float = 0.33
    abstain_utility: float = -0.95

    policy_strength: float = 1.0
    snapshot_interval: int = 12
    strategic_characters: int = 8
    max_splits_per_tick: int = 1
    early_election_lock: int = 6

    def __post_init__(self) -> None:
        if self.population < 20:
            raise ValueError("population must be at least 20")
        if self.ticks < 1:
            raise ValueError("ticks must be at least 1")
        if self.election_interval < 2:
            raise ValueError("election_interval must be at least 2")
        if self.parliament_seats < 1:
            raise ValueError("parliament_seats must be positive")
        if self.electoral_system not in ELECTORAL_SYSTEMS:
            raise ValueError(
                f"electoral_system must be one of {', '.join(ELECTORAL_SYSTEMS)}"
            )
        if not 0.0 <= self.electoral_threshold <= 0.5:
            raise ValueError("electoral_threshold must be between 0 and 0.5")
        if self.latent_groups < 1:
            raise ValueError("latent_groups must be at least 1")
        if self.min_members < 1:
            raise ValueError("min_members must be at least 1")
        if self.party_formation_cost < 0:
            raise ValueError("party_formation_cost cannot be negative")
        if self.relationship_influence < 0:
            raise ValueError("relationship_influence cannot be negative")
        if self.ambition_scale < 0:
            raise ValueError("ambition_scale cannot be negative")
        if self.preference_adaptation < 0:
            raise ValueError("preference_adaptation cannot be negative")
        if self.strategic_characters < 0:
            raise ValueError("strategic_characters cannot be negative")
        if not 0.0 <= self.homophily <= 1.0:
            raise ValueError("homophily must be between 0 and 1")

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["simulation_version"] = SIMULATION_VERSION
        data["dimensions"] = list(DIMENSIONS)
        data["positive_pole"] = dict(POSITIVE_POLE)
        data["negative_pole"] = dict(NEGATIVE_POLE)
        return data
