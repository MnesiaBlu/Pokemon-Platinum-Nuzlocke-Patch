"""Unit tests for PermadeathPatch."""

import unittest
from pathlib import Path
import ndspy.narc

from patcher.rom import RomHandler
from patcher.patches import LevelCapPatch, FirstEncounterPatch, PermadeathPatch


class TestPermadeathPatch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rom_path = Path("Game/3794 - Pokemon - Versione Platino (IT)(EXiMiUS).nds")
        if not cls.rom_path.exists():
            raise unittest.SkipTest("Clean ROM not found in Game/ directory")

    def test_apply_permadeath_patch(self):
        handler = RomHandler(self.rom_path)
        patch = PermadeathPatch()

        cfg = patch.CONFIG[b"CPUI"]
        arm9_ram = handler.rom.arm9RamAddress

        # Apply patch
        success = patch.apply(handler)
        self.assertTrue(success)

        # 1. Verify NARC modifications (revive items)
        narc_data = handler.rom.getFileByName("itemtool/itemdata/pl_item_data.narc")
        self.assertIsNotNone(narc_data)
        narc = ndspy.narc.NARC(narc_data)

        for item_id in cfg["revive_item_ids"]:
            item_bytes = narc.files[item_id]
            self.assertEqual(item_bytes[15] & 0x03, 0, f"Item {item_id} revive bits were not cleared!")

        rare_candy_bytes = narc.files[cfg["rare_candy_id"]]
        self.assertEqual(rare_candy_bytes[15] & 0x01, 0, "Rare Candy revive bit was not cleared!")

        # 2. Verify ARM9 hooks
        heal_off = cfg["party_heal_hook_addr"] - arm9_ram
        heal_bytes = bytes(handler.rom.arm9[heal_off : heal_off + len(cfg["party_heal_expected"])])
        self.assertNotEqual(heal_bytes, cfg["party_heal_expected"])

        item_off = cfg["item_check_hook_addr"] - arm9_ram
        item_bytes = bytes(handler.rom.arm9[item_off : item_off + len(cfg["item_check_expected"])])
        self.assertNotEqual(item_bytes, cfg["item_check_expected"])

        blackout_off = cfg["hook_blackout_addr"] - arm9_ram
        blackout_bytes = bytes(handler.rom.arm9[blackout_off : blackout_off + len(cfg["hook_blackout_expected"])])
        self.assertNotEqual(blackout_bytes, cfg["hook_blackout_expected"])

        # 3. Verify custom routines written to free space
        free_off = cfg["arm9_free_space_addr"] - arm9_ram
        free_chunk = handler.rom.arm9[free_off : free_off + 180]
        self.assertNotEqual(free_chunk, b"\x00" * 180)

    def test_apply_all_patches(self):
        """Verify all three Nuzlocke patches can be applied together."""
        handler = RomHandler(self.rom_path)
        p1 = LevelCapPatch()
        p2 = FirstEncounterPatch()
        p3 = PermadeathPatch()

        self.assertTrue(p1.apply(handler))
        self.assertTrue(p2.apply(handler))
        self.assertTrue(p3.apply(handler))


if __name__ == "__main__":
    unittest.main()
