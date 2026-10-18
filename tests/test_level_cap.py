"""Unit tests for LevelCapPatch."""

import unittest
from pathlib import Path

from patcher.rom import RomHandler
from patcher.patches import LevelCapPatch
from patcher.scanner import UniversalResolver


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

        # Reload overlay and check modifications (Overlay 16 preserved in-place, NO expansion)
        ov16_after = handler.load_arm9_overlay(cfg["overlay_id"])
        self.assertEqual(len(ov16_after.data), orig_len)

        # Verify custom routines written to ARM9 free space
        arm9 = handler.rom.arm9
        arm9_ram = handler.rom.arm9RamAddress
        get_cap_off = cfg["get_cap_free_space_addr"] - arm9_ram
        self.assertNotEqual(bytes(arm9[get_cap_off : get_cap_off + 16]), b"\x00" * 16)

        # Hook 1 replaces only cmp/bne; the original `b skip_exp` stays in place
        # because the "0 HP" branch at 0x02249178 also lands on it.
        h1_off = cfg["hook1_addr"] - ov16_after.ramAddress
        h1_bytes = bytes(ov16_after.data[h1_off : h1_off + 6])
        self.assertNotEqual(h1_bytes[:4], cfg["hook1_expected"][:4])
        self.assertEqual(h1_bytes[4:], cfg["hook1_expected"][4:])

        # Verify Hook 2 bytes
        h2_off = cfg["hook2_addr"] - ov16_after.ramAddress
        h2_bytes = bytes(ov16_after.data[h2_off : h2_off + 8])
        self.assertNotEqual(h2_bytes, cfg["hook2_expected"])
        # The filler after the BL is executed on return: it must be the Thumb-1
        # `mov r8, r8`, not Keystone's Thumb-2 `nop` (0xBF00, undefined on ARMv5TE).
        self.assertEqual(h2_bytes[6:8], bytes.fromhex("c046"))

        # Only the two hook sites changed in Overlay 16
        diff = [i for i in range(orig_len) if ov16_before.data[i] != ov16_after.data[i]]
        self.assertTrue(all(h1_off <= i < h1_off + 4 or h2_off <= i < h2_off + 8 for i in diff))

    def test_routines_fit_free_space(self):
        handler = RomHandler(self.rom_path)
        patch = LevelCapPatch()
        cfg = patch.CONFIG[b"CPUI"]
        arm9 = handler.rom.arm9
        arm9_ram = handler.rom.arm9RamAddress

        codes = dict(zip(
            ("get_cap_free_space_addr", "check_cap_free_space_addr", "clamp_exp_free_space_addr"),
            patch.generate_custom_code(cfg),
        ))
        for key, code in codes.items():
            off = cfg[key] - arm9_ram
            limit = patch.FREE_SPACE_LIMITS[key]
            self.assertLessEqual(len(code), limit, key)
            self.assertEqual(bytes(arm9[off : off + limit]), b"\x00" * limit, key)

    def test_level_cap_table(self):
        patch = LevelCapPatch()
        cfg = patch.CONFIG[b"CPUI"]
        b_get_cap = patch.generate_custom_code(cfg)[0]
        self.assertTrue(b_get_cap.endswith(bytes([14, 22, 26, 32, 37, 41, 44, 50, 62])))

    def test_scanner_matches_cpui_config(self):
        handler = RomHandler(self.rom_path)
        resolved = UniversalResolver.resolve_level_cap(handler)
        for key, value in LevelCapPatch.CONFIG[b"CPUI"].items():
            self.assertEqual(resolved[key], value, key)

if __name__ == "__main__":
    unittest.main()
