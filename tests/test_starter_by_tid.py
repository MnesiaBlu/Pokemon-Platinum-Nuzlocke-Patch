"""Unit tests for StarterByTidPatch."""

import unittest
from pathlib import Path

from patcher.rom import RomHandler
from patcher.patches import (
    LevelCapPatch,
    FirstEncounterPatch,
    PermadeathPatch,
    StarterByTidPatch,
)


class TestStarterByTidPatch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rom_path = Path("Game/3794 - Pokemon - Versione Platino (IT)(EXiMiUS).nds")
        if not cls.rom_path.exists():
            raise unittest.SkipTest("Clean ROM not found in Game/ directory")

    def test_apply_starter_by_tid_patch(self):
        handler = RomHandler(self.rom_path)
        patch = StarterByTidPatch()

        cfg = patch.CONFIG[b"CPUI"]
        e_orig = handler.get_overlay_entry(cfg["overlay_id"])
        orig_ram_size = e_orig["ram_size"]

        # Apply patch
        success = patch.apply(handler)
        self.assertTrue(success)

        # 1. Verify overlay table entry updated
        e_patched = handler.get_overlay_entry(cfg["overlay_id"])
        self.assertGreater(e_patched["ram_size"], orig_ram_size)
        self.assertEqual(e_patched["ram_size"], orig_ram_size + 116)

        # 2. Reload overlay and verify modifications
        ov78 = handler.load_arm9_overlay(cfg["overlay_id"])
        ov78_ram = ov78.ramAddress

        # Verify Hook 1 at 0x021D103C
        h1_off = cfg["hook1_init_addr"] - ov78_ram
        h1_bytes = bytes(ov78.data[h1_off : h1_off + len(cfg["hook1_expected"])])
        self.assertNotEqual(h1_bytes, cfg["hook1_expected"])
        # In Thumb, BL instruction opcode starts with 0xF0..0xF7
        self.assertEqual(h1_bytes[1] & 0xF8, 0xF0)

        # Verify Hook 2 at 0x021D1B08
        h2_off = cfg["hook2_choice_addr"] - ov78_ram
        h2_bytes = bytes(ov78.data[h2_off : h2_off + len(cfg["hook2_expected"])])
        self.assertNotEqual(h2_bytes, cfg["hook2_expected"])
        self.assertEqual(h2_bytes[1] & 0xF8, 0xF0)

        # 3. Verify appended custom code
        appended_code = bytes(ov78.data[orig_ram_size:])
        self.assertEqual(len(appended_code), 116)
        # Verify literal pool entry (SaveDataPtr 0x021C08F4)
        self.assertIn(bytes.fromhex("f4081c02"), appended_code)

    def test_tid_starter_mapping_logic(self):
        """Verify the mathematical mapping logic across all Trainer ID digits."""
        # Mapping:
        # 1, 2, 3 -> Turtwig (0)
        # 4, 5, 6 -> Chimchar (1)
        # 7, 8, 9 -> Piplup (2)
        # 0 -> Player's choice (0xFF)
        for tid in range(100):
            digit = tid % 10
            if digit == 0:
                expected = 0xFF
            elif digit in (1, 2, 3):
                expected = 0  # Turtwig
            elif digit in (4, 5, 6):
                expected = 1  # Chimchar
            else:
                expected = 2  # Piplup

            # Fast division / modulo algorithm used in assembly
            q = (tid * 52429) >> 19
            rem = tid - q * 10
            self.assertEqual(rem, digit)

            if rem == 0:
                result = 0xFF
            elif rem <= 3:
                result = 0
            elif rem <= 6:
                result = 1
            else:
                result = 2

            self.assertEqual(result, expected)

    def test_apply_all_four_patches(self):
        """Verify all four Nuzlocke patches can be applied together seamlessly."""
        handler = RomHandler(self.rom_path)
        p1 = LevelCapPatch()
        p2 = FirstEncounterPatch()
        p3 = PermadeathPatch()
        p4 = StarterByTidPatch()

        self.assertTrue(p1.apply(handler))
        self.assertTrue(p2.apply(handler))
        self.assertTrue(p3.apply(handler))
        self.assertTrue(p4.apply(handler))


if __name__ == "__main__":
    unittest.main()
