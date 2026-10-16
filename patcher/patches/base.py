"""Base class for ROM patches."""

from abc import ABC, abstractmethod
from ..rom import RomHandler


class BasePatch(ABC):
    """Abstract base class for all Nuzlocke feature patches."""

    name: str = "BasePatch"
    description: str = "Base description"

    @abstractmethod
    def apply(self, rom_handler: RomHandler) -> bool:
        """Apply the patch modifications to the ROM. Return True on success."""
        pass
