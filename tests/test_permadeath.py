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

        # 4. Verify Box 18 Naming ('CIMITERO') in ARM9
        box_off = cfg["box_name_hook_addr"] - arm9_ram
        box_bytes = bytes(handler.rom.arm9[box_off : box_off + 16])
        self.assertNotEqual(box_bytes, cfg["box_name_expected"])

        box_fn_off = cfg["box_name_free_space_addr"] - arm9_ram
        box_fn_chunk = bytes(handler.rom.arm9[box_fn_off : box_fn_off + 64])
        self.assertNotEqual(box_fn_chunk, b"\x00" * 64)
        # Check for 'CIMITERO' string encoded in Gen 4 u16: 0x012D, 0x0133, 0x0137...
        cimitero_bytes = bytes.fromhex("2d013301370133013e012f013c013901ffff")
        self.assertIn(cimitero_bytes, box_fn_chunk)

        # 5. Verify Unmovable Box 18 in Overlay 19
        ov19 = handler.load_arm9_overlay(cfg["ov19_id"])
        ov19_off = cfg["ov19_hook_addr"] - ov19.ramAddress
        ov19_hook_bytes = bytes(ov19.data[ov19_off : ov19_off + 4])
        self.assertNotEqual(ov19_hook_bytes, cfg["ov19_hook_expected"])
        self.assertGreater(len(ov19.data), 1800)

        # 6. Verify Battle End Hooks (Overlay 5 + ARM9 battle end transitions)
        ov5 = handler.load_arm9_overlay(cfg["ov5_id"])
        self.assertGreater(len(ov5.data), 201664)

        for idx, hook_addr in enumerate(cfg["battle_end_hooks"]):
            h_off = hook_addr - arm9_ram
            curr = bytes(handler.rom.arm9[h_off : h_off + 4])
            self.assertNotEqual(curr, cfg["battle_end_expected"][idx])

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
