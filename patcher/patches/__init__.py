"""Patches package for Pokemon Platinum Nuzlocke."""

from .base import BasePatch
from .level_cap import LevelCapPatch
from .first_encounter import FirstEncounterPatch
from .permadeath import PermadeathPatch

__all__ = ["BasePatch", "LevelCapPatch", "FirstEncounterPatch", "PermadeathPatch"]


