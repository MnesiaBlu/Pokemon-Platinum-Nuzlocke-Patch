"""Unit tests for Universal Pattern Scanner and Dynamic Hook Resolver."""

import unittest
from pathlib import Path

from patcher.rom import RomHandler
from patcher.scanner import PatternScanner, UniversalResolver
from patcher.patches import (
    LevelCapPatch,
    FirstEncounterPatch,
    PermadeathPatch,
    StarterByTidPatch,
)


class TestPatternScanner(unittest.TestCase):
    def test_parse_pattern(self):
        pat_str = "01 20 ?? b0 38 bd"
        pat, mask = PatternScanner.parse_pattern(pat_str)
        self.assertEqual(len(pat), 6)
        self.assertEqual(len(mask), 6)
        self.assertEqual(pat[0], 0x01)
        self.assertEqual(mask[0], 0xFF)
        self.assertEqual(pat[2], 0x00)
        self.assertEqual(mask[2], 0x00)
        self.assertEqual(pat[3], 0xB0)
        self.assertEqual(mask[3], 0xFF)

    def test_find_pattern_exact(self):
        buf = b"\x00\x11\x22\x33\x44\x55\x66\x77"
        pos = PatternScanner.find_pattern(buf, "22 33 44", alignment=1)
        self.assertEqual(pos, 2)

    def test_find_pattern_wildcard(self):
        buf = b"\x00\x11\x22\x99\x44\x55\x66\x77"
        pos = PatternScanner.find_pattern(buf, "22 ?? 44", alignment=1)
        self.assertEqual(pos, 2)

    def test_find_pattern_alignment(self):
        buf = b"\x00\x22\x33\x00\x22\x33"
        # Index 1 is odd, index 4 is even (divisible by 2)
        pos = PatternScanner.find_pattern(buf, "22 33", alignment=2)
        self.assertEqual(pos, 4)

    def test_decode_thumb_b(self):
        # 0xE087 at PC=0x02249188
        # imm11 = 0x87 = 135 -> offset = 270
        # target = 0x02249188 + 4 + 270 = 0x0224929A -> Thumb bit 1: 0x0224929B
        instr = bytes.fromhex("87e0")
        target = PatternScanner.decode_thumb_b(instr, 0x02249188)
        self.assertEqual(target, 0x0224929A)


class TestUniversalResolver(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rom_path = Path("Game/3794 - Pokemon - Versione Platino (IT)(EXiMiUS).nds")
        if not cls.rom_path.exists():
            raise unittest.SkipTest("Clean ROM not found in Game/ directory")

    def test_resolve_level_cap(self):
        handler = RomHandler(self.rom_path)
        cfg = UniversalResolver.resolve_level_cap(handler)
        self.assertEqual(cfg["overlay_id"], 16)
        self.assertEqual(cfg["hook1_addr"], 0x02249184)
        self.assertEqual(cfg["hook2_addr"], 0x02249242)
        self.assertEqual(cfg["exp_skip_target"], 0x02249297)

    def test_resolve_first_encounter(self):
        handler = RomHandler(self.rom_path)
        cfg = UniversalResolver.resolve_first_encounter(handler)
        self.assertEqual(cfg["overlay_id"], 16)
        self.assertEqual(cfg["hook_init_addr"], 0x0223D984)
        self.assertEqual(cfg["fn_battle_sys_new"], 0x0223C421)
        self.assertEqual(cfg["save_data_ptr"], 0x021C08F4)
        self.assertEqual(cfg["fn_save_data_save_table"], 0x0202462D)
        self.assertEqual(cfg["hook_addr"], 0x02249EAA)
        self.assertEqual(cfg["fn_battle_calc_shakes"], 0x0224A8A1)

    def test_resolve_permadeath(self):
        handler = RomHandler(self.rom_path)
        cfg = UniversalResolver.resolve_permadeath(handler)
        self.assertEqual(cfg["party_heal_hook_addr"], 0x02097324)
        self.assertEqual(cfg["item_check_hook_addr"], 0x020969EE)
        self.assertEqual(cfg["hook_blackout_addr"], 0x02051954)
        self.assertEqual(cfg["fn_save_data_erase"], 0x02024659)
        self.assertEqual(cfg["fn_soft_reset"], 0x02000F75)
        self.assertEqual(cfg["save_data_ptr"], 0x021C08F4)
        self.assertEqual(cfg["fn_party_get_current_count"], 0x0207A198)
        self.assertEqual(cfg["fn_party_get_pokemon_by_slot"], 0x0207A19C)
        self.assertEqual(cfg["fn_pokemon_check_item_effects"], 0x020964C0)

    def test_resolve_starter_by_tid(self):
        handler = RomHandler(self.rom_path)
        cfg = UniversalResolver.resolve_starter_by_tid(handler)
        self.assertEqual(cfg["overlay_id"], 78)
        self.assertEqual(cfg["hook1_init_addr"], 0x021D103C)
        self.assertEqual(cfg["hook2_choice_addr"], 0x021D1B08)
        self.assertEqual(cfg["hook3_species_addr"], 0x021D2A7C)
        self.assertEqual(cfg["fn_change_pokeball_choice"], 0x021D1DB8)
        self.assertEqual(cfg["fn_save_get_trainer_info"], 0x02025EA8)
        self.assertEqual(cfg["save_data_ptr"], 0x021C08F4)

    def test_dynamic_patch_application_arbitrary_game_code(self):
        """Simulate an unknown regional ROM code (e.g. CPUE or CPUF) triggering dynamic scanning."""
        handler = RomHandler(self.rom_path)
        # Override game_code to trigger dynamic scanner fallback
        handler.game_code = b"CPUE"

        # All patches should resolve dynamically and apply cleanly
        p_cap = LevelCapPatch()
        self.assertTrue(p_cap.apply(handler))

        p_enc = FirstEncounterPatch()
        self.assertTrue(p_enc.apply(handler))

        p_perm = PermadeathPatch()
        self.assertTrue(p_perm.apply(handler))

        p_tid = StarterByTidPatch()
        self.assertTrue(p_tid.apply(handler))


if __name__ == "__main__":
    unittest.main()
