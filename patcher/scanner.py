"""Universal Pattern and Signature Scanner for Pokemon Platinum ROMs.

Allows dynamic detection of hook locations, subroutines, and memory pointers
across different language versions and game revisions of Pokemon Platinum
(Italian CPUI, US/English CPUE, French CPUF, German CPUD, Spanish CPUS).
"""

import re
import struct
from typing import Sequence


class PatternScanner:
    """Scans binary buffers for instruction patterns with wildcards."""

    @staticmethod
    def parse_pattern(pattern_str: str) -> tuple[bytes, bytes]:
        """Convert a pattern string like '01 20 ?? b0 38 bd' into (pattern_bytes, mask_bytes)."""
        tokens = pattern_str.strip().split()
        pat = []
        mask = []
        for t in tokens:
            if t in ("??", "?", "*", "**"):
                pat.append(0)
                mask.append(0)
            else:
                pat.append(int(t, 16))
                mask.append(0xFF)
        return bytes(pat), bytes(mask)

    @classmethod
    def find_pattern(
        cls,
        data: bytes | bytearray,
        pattern_str: str,
        start_offset: int = 0,
        alignment: int = 2,
    ) -> int | None:
        """Find the first aligned occurrence of pattern_str in data."""
        pat, mask = cls.parse_pattern(pattern_str)
        pat_len = len(pat)

        # Fast path if no wildcards: use bytes.find
        if all(m == 0xFF for m in mask):
            pos = data.find(pat, start_offset)
            while pos != -1:
                if pos % alignment == 0:
                    return pos
                pos = data.find(pat, pos + 1)
            return None

        # Regex path for patterns with wildcards
        regex_parts = []
        for p, m in zip(pat, mask):
            if m == 0xFF:
                regex_parts.append(re.escape(bytes([p])))
            else:
                regex_parts.append(b".")
        pattern_re = re.compile(b"".join(regex_parts), re.DOTALL)

        for match in pattern_re.finditer(data, start_offset):
            pos = match.start()
            if pos % alignment == 0:
                return pos
        return None

    @classmethod
    def find_all_patterns(
        cls,
        data: bytes | bytearray,
        pattern_str: str,
        start_offset: int = 0,
        alignment: int = 2,
    ) -> list[int]:
        """Find all aligned occurrences of pattern_str in data."""
        pat, mask = cls.parse_pattern(pattern_str)
        regex_parts = []
        for p, m in zip(pat, mask):
            if m == 0xFF:
                regex_parts.append(re.escape(bytes([p])))
            else:
                regex_parts.append(b".")
        pattern_re = re.compile(b"".join(regex_parts), re.DOTALL)

        return [
            m.start()
            for m in pattern_re.finditer(data, start_offset)
            if m.start() % alignment == 0
        ]

    @staticmethod
    def decode_thumb_bl(instr_bytes: bytes, pc: int) -> int:
        """Decode a 4-byte Thumb BL instruction at address pc to find target address.

        In Thumb-1:
          h1 = 0xF000 | imm10
          h2 = 0xF800 | imm11
          target = pc + 4 + sign_extend((imm10 << 12) | (imm11 << 1))
        """
        if len(instr_bytes) < 4:
            raise ValueError("Thumb BL instruction must be at least 4 bytes")
        h1, h2 = struct.unpack("<HH", instr_bytes[:4])
        imm10 = h1 & 0x7FF
        imm11 = h2 & 0x7FF
        offset = (imm10 << 12) | (imm11 << 1)
        # Sign-extend 23-bit to 32-bit signed integer
        if offset & (1 << 22):
            offset -= 1 << 23
        return pc + 4 + offset

    @staticmethod
    def decode_thumb_b(instr_bytes: bytes, pc: int) -> int:
        """Decode a 2-byte Thumb unconditional B instruction at address pc."""
        if len(instr_bytes) < 2:
            raise ValueError("Thumb B instruction must be at least 2 bytes")
        val = struct.unpack("<H", instr_bytes[:2])[0]
        imm11 = val & 0x7FF
        offset = imm11 << 1
        if offset & (1 << 11):
            offset -= 1 << 12
        return pc + 4 + offset


class UniversalResolver:
    """Dynamically resolves patch configurations across any Pokemon Platinum ROM."""

    @classmethod
    def resolve_starter_by_tid(cls, rom_handler) -> dict:
        """Resolve hook addresses and function pointers for StarterByTidPatch."""
        ov78 = rom_handler.load_arm9_overlay(78)
        ov78_ram = ov78.ramAddress
        ov78_data = bytes(ov78.data)

        # Hook 1: End of ChooseStarter_Init (movs r0, #1; add sp, #0x10; pop {r3, r4, r5, pc})
        h1_off = PatternScanner.find_pattern(ov78_data, "01 20 ?? b0 38 bd")
        if h1_off is None:
            raise RuntimeError("Could not find ChooseStarter_Init end signature in Overlay 78")

        # Hook 2: ChangePokeballChoice call inside IsSelectionMade
        h2_match = PatternScanner.find_pattern(ov78_data, "20 1c ?? ?? ?? ?? ?? 48 01 21 ?? 6c")
        if h2_match is None:
            raise RuntimeError("Could not find ChangePokeballChoice call in Overlay 78")
        h2_off = h2_match + 2  # skip 'adds r0, r4, #0'
        h2_addr = ov78_ram + h2_off
        fn_change_pokeball_choice = PatternScanner.decode_thumb_bl(ov78_data[h2_off:h2_off+4], h2_addr)

        # Hook 3: GetSelectedSpecies entry point
        h3_off = PatternScanner.find_pattern(ov78_data, "08 b5 00 28 ?? d0 01 28 ?? d0 02 28")
        if h3_off is None:
            raise RuntimeError("Could not find GetSelectedSpecies signature in Overlay 78")

        # SaveData_GetTrainerInfo and sSaveDataPtr in ARM9
        arm9 = bytes(rom_handler.rom.arm9)
        arm9_ram = rom_handler.rom.arm9RamAddress
        trainer_info_off = PatternScanner.find_pattern(arm9, "08 b5 01 21 ?? ?? ?? ?? 00 1d 08 bd")
        if trainer_info_off is None:
            raise RuntimeError("Could not find SaveData_GetTrainerInfo signature in ARM9")
        fn_save_get_trainer_info = arm9_ram + trainer_info_off

        # sSaveDataPtr pointer in ARM9
        save_ptr_off = PatternScanner.find_pattern(arm9, "08 b5 04 48 00 68 00 28 ?? d1 ?? ?? ?? ?? 01 48 00 68 08 bd")
        if save_ptr_off is not None:
            # Word follows at save_ptr_off + 20
            save_data_ptr = struct.unpack("<I", arm9[save_ptr_off + 20 : save_ptr_off + 24])[0]
        else:
            # Fallback to known default if exact wrapper differs
            save_data_ptr = 0x021C08F4

        return {
            "overlay_id": 78,
            "hook1_init_addr": ov78_ram + h1_off,
            "hook1_expected": bytes(ov78_data[h1_off : h1_off + 6]),
            "hook2_choice_addr": h2_addr,
            "hook2_expected": bytes(ov78_data[h2_off : h2_off + 4]),
            "hook3_species_addr": ov78_ram + h3_off,
            "hook3_expected": bytes(ov78_data[h3_off : h3_off + 4]),
            "save_data_ptr": save_data_ptr,
            "fn_save_get_trainer_info": fn_save_get_trainer_info,
            "fn_change_pokeball_choice": fn_change_pokeball_choice,
        }

    @classmethod
    def resolve_level_cap(cls, rom_handler) -> dict:
        """Resolve hook addresses and function pointers for LevelCapPatch."""
        ov16 = rom_handler.load_arm9_overlay(16)
        ov16_ram = ov16.ramAddress
        ov16_data = bytes(ov16.data)

        # Hook 1: cmp r0, #100; bne ...; b exp_skip_target
        h1_off = PatternScanner.find_pattern(ov16_data, "64 28 00 d1 ?? e0")
        if h1_off is None:
            raise RuntimeError("Could not find LevelCap Hook 1 signature in Overlay 16")
        h1_addr = ov16_ram + h1_off
        b_target = PatternScanner.decode_thumb_b(ov16_data[h1_off + 4 : h1_off + 6], h1_addr + 4)
        exp_skip_target = b_target | 1  # Thumb mode bit

        # Hook 2: Exp clamping hook before level up
        h2_off = PatternScanner.find_pattern(ov16_data, "13 99 0e 98 0a 18 13 92")
        if h2_off is None:
            raise RuntimeError("Could not find LevelCap Hook 2 signature in Overlay 16")
        h2_addr = ov16_ram + h2_off

        # Core functions in ARM9
        arm9 = bytes(rom_handler.rom.arm9)
        arm9_ram = rom_handler.rom.arm9RamAddress

        trainer_info_off = PatternScanner.find_pattern(arm9, "08 b5 01 21 ?? ?? ?? ?? 00 1d 08 bd")
        fn_save_get_trainer_info = arm9_ram + trainer_info_off if trainer_info_off else 0x02025EA8

        save_ptr_off = PatternScanner.find_pattern(arm9, "08 b5 04 48 00 68 00 28 ?? d1 ?? ?? ?? ?? 01 48 00 68 08 bd")
        save_data_ptr = struct.unpack("<I", arm9[save_ptr_off + 20 : save_ptr_off + 24])[0] if save_ptr_off else 0x021C08F4

        return {
            "overlay_id": 16,
            "hook1_addr": h1_addr,
            "hook1_expected": bytes(ov16_data[h1_off : h1_off + 6]),
            "hook2_addr": h2_addr,
            "hook2_expected": bytes(ov16_data[h2_off : h2_off + 8]),
            "exp_skip_target": exp_skip_target,
            "save_data_ptr": save_data_ptr,
            "fn_save_get_trainer_info": fn_save_get_trainer_info,
            "fn_pokemon_get_value": 0x02074510,
            "fn_pokemon_get_species_base_exp": 0x02075B70,
        }

    @classmethod
    def resolve_first_encounter(cls, rom_handler) -> dict:
        """Resolve hook addresses and function pointers for FirstEncounterPatch."""
        ov16 = rom_handler.load_arm9_overlay(16)
        ov16_ram = ov16.ramAddress
        ov16_data = bytes(ov16.data)

        # Hook 1: BattleSys_New call during battle initialization in Overlay 16
        h1_match = PatternScanner.find_pattern(ov16_data, "20 1c 29 1c ?? ?? ?? ?? e0 6a 04 21 01 42")
        if h1_match is None:
            raise RuntimeError("Could not find BattleSys_New initialization signature in Overlay 16")
        h1_off = h1_match + 4
        h1_addr = ov16_ram + h1_off
        fn_battle_sys_new = (PatternScanner.decode_thumb_bl(ov16_data[h1_off : h1_off + 4], h1_addr)) | 1

        # Hook 2: ThrowBallTask before Battle_CalcCatchShakes in Overlay 16
        h2_match = PatternScanner.find_pattern(ov16_data, "20 68 61 68 ?? ?? ?? ?? a0 63 04 28")
        if h2_match is None:
            raise RuntimeError("Could not find ThrowBallTask catch formula signature in Overlay 16")
        h2_off = h2_match + 4
        h2_addr = ov16_ram + h2_off
        fn_battle_calc_shakes = (PatternScanner.decode_thumb_bl(ov16_data[h2_off : h2_off + 4], h2_addr)) | 1

        # SaveData_GetTrainerInfo and sSaveDataPtr in ARM9
        arm9 = bytes(rom_handler.rom.arm9)
        arm9_ram = rom_handler.rom.arm9RamAddress

        trainer_info_off = PatternScanner.find_pattern(arm9, "08 b5 01 21 ?? ?? ?? ?? 00 1d 08 bd")
        if trainer_info_off is not None:
            fn_save_data_save_table = (
                PatternScanner.decode_thumb_bl(arm9[trainer_info_off + 4 : trainer_info_off + 8], arm9_ram + trainer_info_off + 4)
                | 1
            )
        else:
            fn_save_data_save_table = 0x0202462D

        save_ptr_off = PatternScanner.find_pattern(arm9, "08 b5 04 48 00 68 00 28 ?? d1 ?? ?? ?? ?? 01 48 00 68 08 bd")
        if save_ptr_off is not None:
            save_data_ptr = struct.unpack("<I", arm9[save_ptr_off + 20 : save_ptr_off + 24])[0]
        else:
            save_data_ptr = 0x021C08F4

        # Overlay 5: Overworld Location Banner hooks
        ov5 = rom_handler.load_arm9_overlay(5)
        ov5_ram = ov5.ramAddress
        ov5_data = bytes(ov5.data)
        ov5_matches = PatternScanner.find_all_patterns(ov5_data, "e0 6b a1 69 22 6c ?? ?? ?? ?? 01 1c")
        if not ov5_matches or len(ov5_matches) < 2:
            raise RuntimeError("Could not find MapHeader_LoadString hook signatures in Overlay 5")
        ov5_hooks = [ov5_ram + m + 6 for m in ov5_matches]

        # Overlay 80: Town Map (Mappa Citta) hooks
        ov80 = rom_handler.load_arm9_overlay(80)
        ov80_ram = ov80.ramAddress
        ov80_data = bytes(ov80.data)
        ov80_matches = PatternScanner.find_all_patterns(ov80_data, "88 34 22 68 ?? ?? ?? ??")
        ov80_hooks = [ov80_ram + m + 4 for m in ov80_matches]
        m3 = PatternScanner.find_pattern(ov80_data, "88 34 22 68 00 20 ?? ?? ?? ??")
        if m3 is not None and len(ov80_hooks) >= 2:
            ov80_hooks = [ov80_hooks[0], ov80_hooks[1], ov80_ram + m3 + 6]

        # ARM9 functions for string and storage manipulation
        m_load_str = PatternScanner.find_pattern(arm9, "10 b5 14 1c ?? ?? ?? ?? 00 20 21 1c 02 1c ?? ?? ?? ?? 10 bd")
        if m_load_str is not None:
            fn_msg_loader_get_string = (
                PatternScanner.decode_thumb_bl(arm9[m_load_str+4:m_load_str+8], arm9_ram + m_load_str + 4) | 1
            )
            fn_font_calc_string_width = (
                PatternScanner.decode_thumb_bl(arm9[m_load_str+14:m_load_str+18], arm9_ram + m_load_str + 14) | 1
            )
        else:
            fn_msg_loader_get_string = 0x0200B1CD
            fn_font_calc_string_width = 0x02002D91

        m_get_name = PatternScanner.find_pattern(arm9, "70 b5 16 1c 05 1c 0b 1c ?? 4a 01 20 1a 21 ?? ?? ?? ?? 04 1c")
        if m_get_name is not None:
            fn_map_header_get_map_name_string = (arm9_ram + m_get_name) | 1
            fn_map_header_get_label_text_id = (
                PatternScanner.decode_thumb_bl(arm9[m_get_name+0x16:m_get_name+0x1a], arm9_ram + m_get_name + 0x16) | 1
            )
        else:
            fn_map_header_get_map_name_string = 0x02071DA5
            fn_map_header_get_label_text_id = 0x0203A1DD

        m_pc_storage = PatternScanner.find_pattern(arm9, "01 4b 25 21 18 47 c0 46")
        fn_save_data_get_pc_storage = (arm9_ram + m_pc_storage) | 1 if m_pc_storage is not None else 0x02024491

        m_box_mon = PatternScanner.find_pattern(arm9, "70 b5 0c 1c 05 1c 16 1c 12 2c 05 d3")
        fn_pc_storage_get_box_pokemon = (arm9_ram + m_box_mon) | 1 if m_box_mon is not None else 0x02079D3D

        return {
            "overlay_id": 16,
            "hook_init_addr": h1_addr,
            "hook_init_expected": bytes(ov16_data[h1_off : h1_off + 4]),
            "fn_battle_sys_new": fn_battle_sys_new,
            "save_data_ptr": save_data_ptr,
            "fn_save_data_save_table": fn_save_data_save_table,
            "hook_addr": h2_addr,
            "hook_expected": bytes(ov16_data[h2_off : h2_off + 4]),
            "fn_pokemon_get_value": 0x02074511,
            "fn_box_pokemon_get_value": 0x02074611,
            "fn_battle_calc_shakes": fn_battle_calc_shakes,
            "ov5_id": 5,
            "ov5_hooks": ov5_hooks,
            "fn_msg_loader_get_string": fn_msg_loader_get_string,
            "fn_font_calc_string_width": fn_font_calc_string_width,
            "ov80_id": 80,
            "ov80_hooks": ov80_hooks,
            "fn_map_header_get_map_name_string": fn_map_header_get_map_name_string,
            "fn_map_header_get_label_text_id": fn_map_header_get_label_text_id,
            "fn_save_data_get_pc_storage": fn_save_data_get_pc_storage,
            "fn_pc_storage_get_box_pokemon": fn_pc_storage_get_box_pokemon,
        }

    @classmethod
    def resolve_permadeath(cls, rom_handler) -> dict:
        """Resolve hook addresses and function pointers for PermadeathPatch."""
        arm9 = bytes(rom_handler.rom.arm9)
        arm9_ram = rom_handler.rom.arm9RamAddress

        # Party_HealAllMembers
        heal_off = PatternScanner.find_pattern(arm9, "f0 b5 83 b0 00 90 ?? ?? ?? ?? 00 27 01 90 00 28 ?? dd")
        if heal_off is None:
            raise RuntimeError("Could not find Party_HealAllMembers signature in ARM9")
        heal_addr = arm9_ram + heal_off

        # Decode Party_GetCurrentCount from bl at heal_off + 6
        fn_party_get_current_count = PatternScanner.decode_thumb_bl(arm9[heal_off+6:heal_off+10], heal_addr + 6)

        # Party_CheckItemEffectsOnMember
        item_match = PatternScanner.find_pattern(arm9, "38 b5 0d 1c 11 1c 1c 1c ?? ?? ?? ?? 04 9b 29 1c 22 1c ?? ?? ?? ?? 38 bd")
        if item_match is None:
            raise RuntimeError("Could not find Party_CheckItemEffectsOnMember signature in ARM9")
        item_off = item_match + 18
        item_addr = arm9_ram + item_off

        fn_party_get_pokemon_by_slot = PatternScanner.decode_thumb_bl(arm9[item_match+8:item_match+12], arm9_ram + item_match + 8)
        fn_pokemon_check_item_effects = PatternScanner.decode_thumb_bl(arm9[item_off:item_off+4], item_addr)

        # Blackout / Game Over: entry of Field_PlayerLostBattle / blackout penalty
        blackout_off = PatternScanner.find_pattern(arm9, "38 b5 04 1c 08 68 04 23 ?? 69 03 42")
        if blackout_off is None:
            raise RuntimeError("Could not find Blackout signature in ARM9")
        hook_blackout_addr = arm9_ram + blackout_off

        # SaveData_Erase in ARM9
        erase_off = PatternScanner.find_pattern(arm9, "f8 b5 01 21 00 90 03 20 09 03")
        if erase_off is None:
            raise RuntimeError("Could not find SaveData_Erase signature in ARM9")
        fn_save_data_erase = (arm9_ram + erase_off) | 1

        # SoftReset in ARM9
        reset_off = PatternScanner.find_pattern(arm9, "10 b5 ?? 49 04 1c 00 20 ?? f0 ?? ?? ?? 49 01 20")
        if reset_off is None:
            raise RuntimeError("Could not find SoftReset signature in ARM9")
        fn_soft_reset = (arm9_ram + reset_off) | 1

        # sSaveDataPtr in ARM9
        save_ptr_off = PatternScanner.find_pattern(arm9, "08 b5 04 48 00 68 00 28 ?? d1 ?? ?? ?? ?? 01 48 00 68 08 bd")
        if save_ptr_off is not None:
            save_data_ptr = struct.unpack("<I", arm9[save_ptr_off + 20 : save_ptr_off + 24])[0]
        else:
            save_data_ptr = 0x021C08F4

        # Battle end hooks in ARM9 (Trainer battle end & Wild battle end)
        battle_end_matches = PatternScanner.find_all_patterns(arm9, "03 49 28 1c ?? ?? ?? ?? f8 bd")
        if not battle_end_matches or len(battle_end_matches) < 2:
            raise RuntimeError("Could not find battle end hook signatures in ARM9")
        battle_end_hooks = [arm9_ram + m + 4 for m in battle_end_matches]
        fn_field_battle_transition_end = (
            PatternScanner.decode_thumb_bl(arm9[battle_end_matches[0]+4:battle_end_matches[0]+8], battle_end_hooks[0]) | 1
        )

        # Party_RemovePokemonBySlot in ARM9
        m_remove = PatternScanner.find_pattern(arm9, "f8 b5 07 1c 0c 1c 01 d5")
        if m_remove is not None:
            fn_party_remove_pokemon_by_slot = (arm9_ram + m_remove) | 1
        else:
            fn_party_remove_pokemon_by_slot = 0x0207A121

        # Box name hook in ARM9
        m_box_name = PatternScanner.find_pattern(arm9, "19 68 12 29 ?? d2 10 1c ?? 4a 9b 18 28 22 4a 43")
        box_name_hook_addr = arm9_ram + m_box_name + 8 if m_box_name is not None else 0x02079BA8
        box_name_expected = (
            bytes(arm9[m_box_name + 8 : m_box_name + 24])
            if m_box_name is not None
            else bytes.fromhex("054a9b1828224a439918aaf7f1f808bd")
        )
        fn_string_copy_from_u16_array = (
            PatternScanner.decode_thumb_bl(arm9[m_box_name + 0x12 : m_box_name + 0x16], arm9_ram + m_box_name + 0x12) | 1
            if m_box_name is not None
            else 0x02023D99
        )

        # Overlay 19: PC Storage unmovable Graveyard hook
        ov19 = rom_handler.load_arm9_overlay(19)
        ov19_ram = ov19.ramAddress
        ov19_data = bytes(ov19.data)
        m_ov19 = PatternScanner.find_pattern(ov19_data, "07 22 a2 56 28 68 49 1e ?? ?? ?? ?? 20 60 15 e0")
        ov19_hook_addr = ov19_ram + m_ov19 + 8 if m_ov19 is not None else 0x021D5484
        ov19_hook_expected = (
            bytes(ov19_data[m_ov19 + 8 : m_ov19 + 12])
            if m_ov19 is not None
            else bytes.fromhex("a4f65afc")
        )

        # Core functions for Graveyard
        m_pc_storage = PatternScanner.find_pattern(arm9, "01 4b 25 21 18 47 c0 46")
        fn_save_data_get_pc_storage = (arm9_ram + m_pc_storage) | 1 if m_pc_storage is not None else 0x02024491

        m_box_mon = PatternScanner.find_pattern(arm9, "70 b5 0c 1c 05 1c 16 1c 12 2c 05 d3")
        fn_pc_storage_get_box_pokemon = (arm9_ram + m_box_mon) | 1 if m_box_mon is not None else 0x02079D3D

        trainer_info_off = PatternScanner.find_pattern(arm9, "08 b5 01 21 ?? ?? ?? ?? 00 1d 08 bd")
        if trainer_info_off is not None:
            fn_save_data_save_table = (
                PatternScanner.decode_thumb_bl(arm9[trainer_info_off + 4 : trainer_info_off + 8], arm9_ram + trainer_info_off + 4)
                | 1
            )
        else:
            fn_save_data_save_table = 0x0202462D

        battle_end_expected = [bytes(arm9[m + 4 : m + 8]) for m in battle_end_matches]

        return {
            "arm9_free_space_addr": 0x020F9408,
            "party_heal_hook_addr": heal_addr,
            "party_heal_expected": bytes(arm9[heal_off : heal_off + 8]),
            "item_check_hook_addr": item_addr,
            "item_check_expected": bytes(arm9[item_off : item_off + 4]),
            "hook_blackout_addr": hook_blackout_addr,
            "hook_blackout_expected": bytes(arm9[blackout_off : blackout_off + 4]),
            "fn_save_data_erase": fn_save_data_erase,
            "fn_soft_reset": fn_soft_reset,
            "save_data_ptr": save_data_ptr,
            "fn_party_get_current_count": fn_party_get_current_count,
            "fn_party_get_pokemon_by_slot": fn_party_get_pokemon_by_slot,
            "fn_pokemon_get_value": 0x02074511,
            "fn_pokemon_set_value": 0x02074BD0,
            "fn_is_move_missing_pp": 0x02096FD4,
            "fn_restore_pokemon_move_pp": 0x02097024,
            "fn_pokemon_check_item_effects": fn_pokemon_check_item_effects,
            "revive_item_ids": [28, 29, 37, 44],
            "rare_candy_id": 50,
            "ov5_id": 5,
            "battle_end_hooks": battle_end_hooks,
            "battle_end_expected": battle_end_expected,
            "fn_field_battle_transition_end": fn_field_battle_transition_end,
            "fn_party_remove_pokemon_by_slot": fn_party_remove_pokemon_by_slot,
            "fn_save_data_save_table": fn_save_data_save_table,
            "fn_save_data_get_pc_storage": fn_save_data_get_pc_storage,
            "fn_pc_storage_get_box_pokemon": fn_pc_storage_get_box_pokemon,
            "box_name_hook_addr": box_name_hook_addr,
            "box_name_expected": box_name_expected,
            "box_name_free_space_addr": 0x020F30D0,
            "fn_string_copy_from_u16_array": fn_string_copy_from_u16_array,
            "ov19_id": 19,
            "ov19_hook_addr": ov19_hook_addr,
            "ov19_hook_expected": ov19_hook_expected,
        }
