"""ROM handler for Nintendo DS Pokemon Platinum."""

import hashlib
import os
import struct
from pathlib import Path
import ndspy.rom


class RomHandler:
    SUPPORTED_GAME_CODES = {
        b"CPUI": "Pokemon Versione Platino (IT)",
        b"CPUE": "Pokemon Platinum Version (US)",
        b"CPUF": "Pokemon Version Platine (FR)",
        b"CPUD": "Pokemon Platin-Edition (DE)",
        b"CPUS": "Pokemon Edicion Platino (ES)",
        b"CPUJ": "Pokemon Platinum (JP)",
    }

    def __init__(self, rom_path: str | Path):
        self.path = Path(rom_path)
        if not self.path.exists():
            raise FileNotFoundError(f"ROM file not found: {self.path}")

        self.rom = ndspy.rom.NintendoDSRom.fromFile(str(self.path))
        self.game_code = bytes(self.rom.idCode)
        self.game_name = self.SUPPORTED_GAME_CODES.get(
            self.game_code, f"Pokemon Platinum ({self.game_code.decode('latin1', errors='replace')})"
        )

    def verify(self) -> dict:
        """Calculate hashes and verify game code."""
        with open(self.path, "rb") as f:
            raw = f.read()

        md5 = hashlib.md5(raw).hexdigest()
        sha1 = hashlib.sha1(raw).hexdigest()
        return {
            "game_code": self.game_code.decode("latin1", errors="replace"),
            "game_name": self.game_name,
            "size": len(raw),
            "md5": md5,
            "sha1": sha1,
            "supported": self.game_code in self.SUPPORTED_GAME_CODES or self.game_code.startswith(b"CPU"),
        }

    def get_overlay_entry(self, overlay_id: int) -> dict:
        """Parse the 32-byte overlay table entry for a given overlay ID."""
        start = overlay_id * 32
        entry = self.rom.arm9OverlayTable[start : start + 32]
        (
            oid,
            ram_addr,
            ram_size,
            bss_size,
            init_start,
            init_end,
            file_id,
            flags,
        ) = struct.unpack("<IIIIIIII", entry)
        return {
            "id": oid,
            "ram_addr": ram_addr,
            "ram_size": ram_size,
            "bss_size": bss_size,
            "init_start": init_start,
            "init_end": init_end,
            "file_id": file_id,
            "flags": flags,
        }

    def load_arm9_overlay(self, overlay_id: int):
        """Load and return an Arm9Overlay object."""
        overlays = self.rom.loadArm9Overlays([overlay_id])
        return overlays[overlay_id]

    def update_arm9_overlay(
        self, overlay_id: int, overlay_obj, new_data: bytes, new_ram_size: int = None
    ):
        """Update overlay data and table entry, then update ROM files."""
        overlay_obj.data = bytearray(new_data)
        self.rom.files[overlay_obj.fileID] = overlay_obj.save()

        # Update overlay table ram_size if expanded
        if new_ram_size is not None:
            entry_offset = overlay_id * 32
            entry = bytearray(
                self.rom.arm9OverlayTable[entry_offset : entry_offset + 32]
            )
            struct.pack_into("<I", entry, 8, new_ram_size)
            self.rom.arm9OverlayTable[entry_offset : entry_offset + 32] = entry

    def save(self, output_path: str | Path):
        """Save patched ROM to disk."""
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        self.rom.saveToFile(str(out))
