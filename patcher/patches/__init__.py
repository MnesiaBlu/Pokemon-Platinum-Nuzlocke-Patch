"""Patches package for Pokemon Platinum Nuzlocke."""

from .base import BasePatch
from .level_cap import LevelCapPatch
from .first_encounter import FirstEncounterPatch
from .permadeath import PermadeathPatch
from .starter_by_tid import StarterByTidPatch

__all__ = [
    "BasePatch",
    "LevelCapPatch",
    "FirstEncounterPatch",
    "PermadeathPatch",
    "StarterByTidPatch",
]


