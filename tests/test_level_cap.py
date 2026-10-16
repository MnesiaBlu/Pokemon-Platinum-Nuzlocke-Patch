"""Unit tests for LevelCapPatch."""

import unittest
from pathlib import Path

from patcher.rom import RomHandler
from patcher.patches import LevelCapPatch


class TestLevelCapPatch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rom_path = Path("Game/3794 - Pokemon - Versione Platino (IT)(EXiMiUS).nds")
        if not cls.rom_path.exists():
            raise unittest.SkipTest("Clean ROM not found in Game/ directory")

    def test_verify_rom(self):
        handler = RomHandler(self.rom_path)
        info = handler.verify()
        self.assertEqual(info["game_code"], "CPUI")
        self.assertTrue(info["supported"])
        self.assertEqual(info["sha1"], "7b888e056042b9018f9ea6903706c75dcabf37ad")

    def test_apply_level_cap_patch(self):
        handler = RomHandler(self.rom_path)
        patch = LevelCapPatch()

        cfg = patch.CONFIG[b"CPUI"]
        ov16_before = handler.load_arm9_overlay(cfg["overlay_id"])
        orig_len = len(ov16_before.data)

        # Apply patch
        success = patch.apply(handler)
        self.assertTrue(success)

        # Reload overlay and check modifications
        ov16_after = handler.load_arm9_overlay(cfg["overlay_id"])
        self.assertGreater(len(ov16_after.data), orig_len)

        # Verify Hook 1 bytes
        h1_off = cfg["hook1_addr"] - ov16_after.ramAddress
        h1_bytes = bytes(ov16_after.data[h1_off : h1_off + 6])
        self.assertNotEqual(h1_bytes, cfg["hook1_expected"])

        # Verify Hook 2 bytes
        h2_off = cfg["hook2_addr"] - ov16_after.ramAddress
        h2_bytes = bytes(ov16_after.data[h2_off : h2_off + 8])
        self.assertNotEqual(h2_bytes, cfg["hook2_expected"])


if __name__ == "__main__":
    unittest.main()
