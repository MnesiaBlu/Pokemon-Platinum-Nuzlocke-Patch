"""Patches package for Pokemon Platinum Nuzlocke."""

from .base import BasePatch
from .level_cap import LevelCapPatch
from .first_encounter import FirstEncounterPatch

__all__ = ["BasePatch", "LevelCapPatch", "FirstEncounterPatch"]

