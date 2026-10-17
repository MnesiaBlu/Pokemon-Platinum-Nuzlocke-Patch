"""Unit tests for FirstEncounterPatch."""

import unittest
from pathlib import Path

from patcher.rom import RomHandler
from patcher.patches import LevelCapPatch, FirstEncounterPatch


class TestFirstEncounterPatch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rom_path = Path("Game/3794 - Pokemon - Versione Platino (IT)(EXiMiUS).nds")
        if not cls.rom_path.exists():
            raise unittest.SkipTest("Clean ROM not found in Game/ directory")

    def test_apply_first_encounter_patch(self):
        handler = RomHandler(self.rom_path)
        patch = FirstEncounterPatch()

        cfg = patch.CONFIG[b"CPUI"]
        ov16_before = handler.load_arm9_overlay(cfg["overlay_id"])
        orig_len = len(ov16_before.data)

        # Apply patch
        success = patch.apply(handler)
        self.assertTrue(success)

        # Reload overlay and check modifications
        ov16_after = handler.load_arm9_overlay(cfg["overlay_id"])
        self.assertGreater(len(ov16_after.data), orig_len)

        # Verify hook 1 (battle init) was patched
        h1_off = cfg["hook_init_addr"] - ov16_after.ramAddress
        h1_bytes = bytes(ov16_after.data[h1_off : h1_off + len(cfg["hook_init_expected"])])
        self.assertNotEqual(h1_bytes, cfg["hook_init_expected"])

        # Verify hook 2 (catch formula) was patched
        h2_off = cfg["hook_addr"] - ov16_after.ramAddress
        h2_bytes = bytes(ov16_after.data[h2_off : h2_off + len(cfg["hook_expected"])])
        self.assertNotEqual(h2_bytes, cfg["hook_expected"])

        # Verify Overlay 5 (Location Banner) was patched and expanded
        ov5_after = handler.load_arm9_overlay(cfg["ov5_id"])
        self.assertEqual(len(ov5_after.data), 201664 + 512)
        for h_addr in cfg["ov5_hooks"]:
            off = h_addr - ov5_after.ramAddress
            # Should be Thumb BL
            instr = int.from_bytes(ov5_after.data[off:off+4], "little")
            self.assertEqual((instr & 0xF800F800), 0xF800F000)

        # Verify Overlay 80 (Town Map) was patched and expanded
        ov80_after = handler.load_arm9_overlay(cfg["ov80_id"])
        self.assertEqual(len(ov80_after.data), 9888 + 512)
        for h_addr in cfg["ov80_hooks"]:
            off = h_addr - ov80_after.ramAddress
            instr = int.from_bytes(ov80_after.data[off:off+4], "little")
            self.assertEqual((instr & 0xF800F800), 0xF800F000)

    def test_apply_both_level_cap_and_first_encounter(self):
        handler = RomHandler(self.rom_path)
        p1 = LevelCapPatch()
        p2 = FirstEncounterPatch()

        ov16_orig = handler.load_arm9_overlay(16)
        orig_len = len(ov16_orig.data)

        # Apply both patches sequentially
        self.assertTrue(p1.apply(handler))
        self.assertTrue(p2.apply(handler))

        ov16_final = handler.load_arm9_overlay(16)
        # Should have expanded by both patches (each padded to 512 bytes)
        self.assertEqual(len(ov16_final.data), orig_len + 1024)


if __name__ == "__main__":
    unittest.main()
