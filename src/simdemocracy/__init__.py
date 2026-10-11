"""SimDemocracy: a deterministic, event-sourced political simulation."""

from simdemocracy.config import Config
from simdemocracy.engine import Simulation
from simdemocracy.version import SIMULATION_VERSION

__all__ = ["Config", "Simulation", "SIMULATION_VERSION"]
__version__ = SIMULATION_VERSION
