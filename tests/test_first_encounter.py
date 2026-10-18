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

        # Reload overlay and check modifications (Overlay 16 preserved in-place, NO expansion)
        ov16_after = handler.load_arm9_overlay(cfg["overlay_id"])
        self.assertEqual(len(ov16_after.data), orig_len)

        # Verify battle routines written to ARM9 free space
        init_off = cfg["battle_init_free_space_addr"] - handler.rom.arm9RamAddress
        self.assertNotEqual(bytes(handler.rom.arm9[init_off : init_off + 36]), b"\x00" * 36)

        # Verify hook 1 (battle init) was patched
        h1_off = cfg["hook_init_addr"] - ov16_after.ramAddress
        h1_bytes = bytes(ov16_after.data[h1_off : h1_off + len(cfg["hook_init_expected"])])
        self.assertNotEqual(h1_bytes, cfg["hook_init_expected"])

        # Verify hook 2 (catch formula) was patched
        h2_off = cfg["hook_addr"] - ov16_after.ramAddress
        h2_bytes = bytes(ov16_after.data[h2_off : h2_off + len(cfg["hook_expected"])])
        self.assertNotEqual(h2_bytes, cfg["hook_expected"])

        # Verify Overlay 5 (Location Banner) was patched in-place (NOT expanded to preserve BSS)
        ov5_after = handler.load_arm9_overlay(cfg["ov5_id"])
        self.assertEqual(len(ov5_after.data), 201664)
        for h_addr in cfg["ov5_hooks"]:
            off = h_addr - ov5_after.ramAddress
            # Should be Thumb BL
            instr = int.from_bytes(ov5_after.data[off:off+4], "little")
            self.assertEqual((instr & 0xF800F800), 0xF800F000)

        # Verify banner routine written to ARM9 free space
        banner_off = cfg["banner_free_space_addr"] - handler.rom.arm9RamAddress
        self.assertNotEqual(bytes(handler.rom.arm9[banner_off : banner_off + 176]), b"\x00" * 176)

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
        # Overlay 16 must NOT expand beyond 219808 to avoid heap collision
        self.assertEqual(len(ov16_final.data), orig_len)


if __name__ == "__main__":
    unittest.main()
