"""Permadeath, Hardcore Game Over & Unmovable Graveyard Patch for Pokemon Platinum.

Enforces the core Nuzlocke permadeath and graveyard rules:
1. Fainted Pokemon (HP = 0) cannot be revived by any items (Revive, Max Revive,
   Revival Herb, Sacred Ash, or Rare Candy).
2. Healing events (Pokemon Centers, beds, Mom, overworld doctors/healers)
   skip fainted Pokemon in Party_HealAllMembers, preserving their 0 HP and
   fainted status.
3. Item parameters in pl_item_data.narc have their revive attributes cleared,
   disabling in-battle and out-of-battle revival mechanics.
4. Hardcore Game Over: Blackout / party wipe permanently wipes the primary
   and backup save sectors via SaveData_Erase and triggers a hardware SoftReset.
5. Unmovable Graveyard (Box 18 "CIMITERO"):
   - When a Pokemon faints in battle, it is automatically transferred to Box 18
     and removed from the active party upon battle transition end.
   - Box 18 is renamed "CIMITERO" via PCStorage_GetBoxName.
   - Box 18 is unmovable: all withdraw, move, swap, deposit, or release actions
     in Box 18 are blocked via Overlay 19 PC storage menu validator.
"""

import ndspy.narc
from .base import BasePatch
from ..rom import RomHandler
from ..arm_asm import Assembler
from ..scanner import UniversalResolver


class PermadeathPatch(BasePatch):
    name = "Permadeath, Hardcore Game Over & Unmovable Graveyard"
    description = (
        "Fainted Pokemon cannot be revived via items and remain fainted at Pokemon Centers. "
        "Fallen party Pokemon are automatically transferred to Box 18 ('CIMITERO') and removed "
        "from the active party at battle end. Box 18 is unmovable (cannot withdraw or move). "
        "A blackout triggers mandatory Game Over: save file is completely erased."
    )

    CONFIG = {
        b"CPUI": {
            "arm9_free_space_addr": 0x020F9408,
            "party_heal_hook_addr": 0x02097324,
            "party_heal_expected": bytes.fromhex("f0b583b00090e2f7"),
            "item_check_hook_addr": 0x020969EE,
            "item_check_expected": bytes.fromhex("fff767fd"),
            "hook_blackout_addr": 0x02051954,
            "hook_blackout_expected": bytes.fromhex("38b5041c"),
            "fn_save_data_erase": 0x02024659,
            "fn_soft_reset": 0x02000F75,
            "save_data_ptr": 0x021C08F4,
            "fn_party_get_current_count": 0x0207A198,
            "fn_party_get_pokemon_by_slot": 0x0207A19D,
            "fn_pokemon_get_value": 0x02074511,
            "fn_pokemon_set_value": 0x02074BD0,
            "fn_is_move_missing_pp": 0x02096FD4,
            "fn_restore_pokemon_move_pp": 0x02097024,
            "fn_pokemon_check_item_effects": 0x020964C0,
            "revive_item_ids": [28, 29, 37, 44],  # Revive, Max Revive, Revival Herb, Sacred Ash
            "rare_candy_id": 50,
            "ov5_id": 5,
            "battle_end_hooks": [0x020518E0, 0x02051946],
            "battle_end_expected": [bytes.fromhex("fff762f8"), bytes.fromhex("fff72ff8")],
            "fn_field_battle_transition_end": 0x020509A9,
            "fn_party_remove_pokemon_by_slot": 0x0207A121,
            "fn_save_data_save_table": 0x0202462D,
            "fn_save_data_get_pc_storage": 0x02024491,
            "fn_pc_storage_get_box_pokemon": 0x02079D3D,
            "box_name_hook_addr": 0x02079BA8,
            "box_name_expected": bytes.fromhex("054a9b1828224a439918aaf7f1f808bd"),
            "box_name_free_space_addr": 0x020F30D0,
            "fn_string_copy_from_u16_array": 0x02023D99,
            "ov19_id": 19,
            "ov19_hook_addr": 0x021D5484,
            "ov19_hook_expected": bytes.fromhex("a4f65afc"),
        }
    }

    def __init__(self):
        self.asm = Assembler()

    def generate_party_heal_code(self, cfg: dict, base_addr: int) -> bytes:
        """Generate Party_HealAllMembers_Nuzlocke assembly."""
        asm_code = f"""
.thumb
.align 2
Party_HealAllMembers_Nuzlocke:
    push {{r4, r5, r6, r7, lr}}
    sub sp, #12

    str r0, [sp, #0]
    bl #{hex(cfg['fn_party_get_current_count'])}
    str r0, [sp, #4]
    cmp r0, #0
    ble .end_heal

    movs r6, #127
    movs r7, #0

.heal_loop_start:
    ldr r0, [sp, #0]
    adds r1, r7, #0
    bl #{hex(cfg['fn_party_get_pokemon_by_slot'])}
    adds r5, r0, #0

    @ Check if species exists (param 0xAC = 172)
    movs r1, #0xac
    movs r2, #0
    bl #{hex(cfg['fn_pokemon_get_value'])}
    cmp r0, #0
    beq .heal_next_mon

    @ PERMADEATH: Check cur HP (param 0xA3 = 163)
    adds r0, r5, #0
    movs r1, #0xa3
    movs r2, #0
    bl #{hex(cfg['fn_pokemon_get_value'])}
    cmp r0, #0
    beq .heal_next_mon

    @ Heal HP: maxHP (param 0xA4 = 164)
    adds r0, r5, #0
    movs r1, #0xa4
    movs r2, #0
    bl #{hex(cfg['fn_pokemon_get_value'])}
    str r0, [sp, #8]
    adds r0, r5, #0
    movs r1, #0xa3
    add r2, sp, #8
    bl #{hex(cfg['fn_pokemon_set_value'])}

    @ Heal Status: 0 (param 0xA0 = 160)
    movs r0, #0
    str r0, [sp, #8]
    adds r0, r5, #0
    movs r1, #0xa0
    add r2, sp, #8
    bl #{hex(cfg['fn_pokemon_set_value'])}

    @ Restore PP for moves 0..3
    movs r4, #0
.pp_loop:
    adds r0, r5, #0
    adds r1, r4, #0
    bl #{hex(cfg['fn_is_move_missing_pp'])}
    cmp r0, #1
    bne .next_move
    adds r0, r5, #0
    adds r1, r4, #0
    adds r2, r6, #0
    bl #{hex(cfg['fn_restore_pokemon_move_pp'])}

.next_move:
    adds r4, r4, #1
    cmp r4, #4
    blt .pp_loop

.heal_next_mon:
    ldr r0, [sp, #4]
    adds r7, r7, #1
    cmp r7, r0
    blt .heal_loop_start

.end_heal:
    add sp, #12
    pop {{r4, r5, r6, r7, pc}}
"""
        return self.asm.assemble_thumb(asm_code, base_addr)

    def generate_item_check_code(self, cfg: dict, base_addr: int) -> bytes:
        """Generate Party_CheckItemEffects_Nuzlocke assembly."""
        asm_code = f"""
.thumb
.align 2
Party_CheckItemEffects_Nuzlocke:
    push {{r4, r5, r6, lr}}
    sub sp, #16
    str r0, [sp, #0]
    str r1, [sp, #4]
    str r2, [sp, #8]
    str r3, [sp, #12]

    @ Check if mon is dead: curHP (param 0xA3 = 163)
    movs r1, #0xa3
    movs r2, #0
    bl #{hex(cfg['fn_pokemon_get_value'])}
    cmp r0, #0
    bne .not_dead

    @ Mon is dead (curHP == 0): return FALSE (0)
    movs r0, #0
    add sp, #16
    pop {{r4, r5, r6, pc}}

.not_dead:
    ldr r0, [sp, #0]
    ldr r1, [sp, #4]
    ldr r2, [sp, #8]
    ldr r3, [sp, #12]
    add sp, #16
    bl #{hex(cfg['fn_pokemon_check_item_effects'])}
    pop {{r4, r5, r6, pc}}
"""
        return self.asm.assemble_thumb(asm_code, base_addr)

    def generate_blackout_code(self, cfg: dict, base_addr: int) -> bytes:
        """Generate Custom_BlackoutGameOver routine.

        When the player blacks out (all party Pokémon fainted):
        1. Calls SaveData_Erase(saveData) to completely wipe all primary and backup save sectors.
        2. Calls SoftReset(0) to reset the console directly to the title screen.
        """
        asm_code = f"""
.thumb
.align 2
Custom_BlackoutGameOver:
    push {{r4, lr}}

    @ 1. Get SaveData pointer
    ldr r0, ={hex(cfg['save_data_ptr'])}
    ldr r0, [r0]

    @ 2. Call SaveData_Erase(saveData)
    ldr r2, ={hex(cfg['fn_save_data_erase'] | 1)}
    blx r2

    @ 3. Call SoftReset(0)
    movs r0, #0
    ldr r2, ={hex(cfg['fn_soft_reset'] | 1)}
    blx r2

.dead_halt:
    b .dead_halt
"""
        return self.asm.assemble_thumb(asm_code, base_addr)

    def generate_box_name_code(self, cfg: dict, base_addr: int) -> bytes:
        """Generate Custom_GetBoxName routine (64 bytes).

        If box == 17 (Box 18), sets name to 'CIMITERO'.
        Otherwise, calculates offset into pcStorage and copies normal box name.
        """
        asm_code = f"""
.thumb
.align 2
Custom_GetBoxName:
    push {{r4, lr}}
    cmp r1, #17
    bne .normal_box

    @ Box 18 (index 17) -> 'CIMITERO'
    adr r1, .str_cimitero
    ldr r2, ={hex(cfg['fn_string_copy_from_u16_array'] | 1)}
    blx r2
    pop {{r4, pc}}

.normal_box:
    ldr r2, =0x11EE4
    adds r3, r3, r2
    movs r2, #40
    muls r2, r1, r2
    adds r1, r3, r2
    ldr r2, ={hex(cfg['fn_string_copy_from_u16_array'] | 1)}
    blx r2
    pop {{r4, pc}}

.align 2
.str_cimitero:
    .short 0x012D, 0x0133, 0x0137, 0x0133, 0x013E, 0x012F, 0x013C, 0x0139, 0xFFFF
"""
        return self.asm.assemble_thumb(asm_code, base_addr)

    def generate_graveyard_box_code(self, cfg: dict, base_addr: int) -> bytes:
        """Generate Custom_GetBoxPokemon_OrGraveyardBlock routine (28 bytes).

        In Overlay 19 PC storage menu validator:
        If box == 17 (or box < 0 and currentBox == 17), returns NULL (0)
        to completely block any withdraw, move, swap, deposit, or release actions in Box 18.
        """
        asm_code = f"""
.thumb
.align 2
Custom_GetBoxPokemon_OrGraveyardBlock:
    push {{r4, lr}}
    adds r4, r1, #0
    cmp r4, #0
    bge .check_box17
    ldr r4, [r0]

.check_box17:
    cmp r4, #17
    bne .allow_access

    movs r0, #0
    pop {{r4, pc}}

.allow_access:
    ldr r3, ={hex(cfg['fn_pc_storage_get_box_pokemon'] | 1)}
    blx r3
    pop {{r4, pc}}
"""
        return self.asm.assemble_thumb(asm_code, base_addr)

    def generate_battle_end_code(self, cfg: dict, base_addr: int) -> bytes:
        """Generate Custom_BattleEndTransition routine.

        Called at battle end:
        1. Checks party for alive Pokémon. If 0 alive, triggers blackout game over.
        2. Iterates party backwards from count - 1 down to 0.
        3. For any Pokémon with curHP == 0:
           - Copies 136-byte BoxPokemon into the first empty slot in Box 18 (index 17).
           - Removes the Pokémon from the party using Party_RemovePokemonBySlot.
        4. Resumes normal battle transition via fn_field_battle_transition_end.
        """
        asm_code = f"""
.thumb
.align 2
Custom_BattleEndTransition:
    push {{r4, r5, r6, r7, lr}}
    sub sp, #28
    str r0, [sp, #16]
    str r1, [sp, #20]
    str r2, [sp, #24]

    @ 1. Get SaveData pointer
    ldr r0, ={hex(cfg['save_data_ptr'])}
    ldr r0, [r0]
    cmp r0, #0
    beq .finish_transition
    str r0, [sp, #8]

    @ 2. Get Party: SaveData_SaveTable(saveData, 2)
    movs r1, #2
    ldr r3, ={hex(cfg['fn_save_data_save_table'] | 1)}
    blx r3
    cmp r0, #0
    beq .finish_transition
    str r0, [sp, #4]

    @ 3. Get PC Storage: SaveData_GetPCStorage(saveData)
    ldr r0, [sp, #8]
    ldr r3, ={hex(cfg['fn_save_data_get_pc_storage'] | 1)}
    blx r3
    cmp r0, #0
    beq .finish_transition
    str r0, [sp, #0]

    @ 4. Check Party Count
    ldr r0, [sp, #4]
    ldr r4, [r0, #4]
    cmp r4, #0
    ble .finish_transition
    cmp r4, #6
    ble .party_cnt_valid
    movs r4, #6
.party_cnt_valid:

    @ 5. Check how many are alive
    movs r5, #0
    movs r6, #0
.count_alive_loop:
    ldr r0, [sp, #4]
    adds r1, r6, #0
    ldr r3, ={hex(cfg['fn_party_get_pokemon_by_slot'] | 1)}
    blx r3
    cmp r0, #0
    beq .count_alive_next

    str r0, [sp, #12]
    movs r1, #5
    movs r2, #0
    ldr r3, ={hex(cfg['fn_pokemon_get_value'] | 1)}
    blx r3
    cmp r0, #0
    beq .count_alive_next

    ldr r0, [sp, #12]
    movs r1, #0xa3
    movs r2, #0
    ldr r3, ={hex(cfg['fn_pokemon_get_value'] | 1)}
    blx r3
    cmp r0, #0
    beq .count_alive_next

    adds r5, r5, #1

.count_alive_next:
    adds r6, r6, #1
    cmp r6, r4
    blt .count_alive_loop

    cmp r5, #0
    bne .process_dead_members

    @ All dead! Trigger Game Over
    ldr r0, [sp, #8]
    ldr r2, ={hex(cfg['fn_save_data_erase'] | 1)}
    blx r2
    movs r0, #0
    ldr r2, ={hex(cfg['fn_soft_reset'] | 1)}
    blx r2

.process_dead_members:
    ldr r0, [sp, #4]
    ldr r5, [r0, #4]
    subs r5, r5, #1

.party_backwards_loop:
    cmp r5, #0
    blt .finish_transition

    ldr r0, [sp, #4]
    adds r1, r5, #0
    ldr r3, ={hex(cfg['fn_party_get_pokemon_by_slot'] | 1)}
    blx r3
    cmp r0, #0
    beq .party_slot_next

    str r0, [sp, #12]

    movs r1, #5
    movs r2, #0
    ldr r3, ={hex(cfg['fn_pokemon_get_value'] | 1)}
    blx r3
    cmp r0, #0
    beq .party_slot_next

    ldr r0, [sp, #12]
    movs r1, #0xa3
    movs r2, #0
    ldr r3, ={hex(cfg['fn_pokemon_get_value'] | 1)}
    blx r3
    cmp r0, #0
    bne .party_slot_next

    @ Mon is fainted: find first empty slot in Box 18 (index 17)
    movs r6, #0
.find_box18_slot:
    ldr r0, [sp, #0]
    movs r1, #17
    adds r2, r6, #0
    ldr r3, ={hex(cfg['fn_pc_storage_get_box_pokemon'] | 1)}
    blx r3
    cmp r0, #0
    beq .box18_next_slot

    ldr r1, [r0, #0]
    cmp r1, #0
    beq .do_transfer_to_box18

.box18_next_slot:
    adds r6, r6, #1
    cmp r6, #30
    blt .find_box18_slot
    b .remove_from_party

.do_transfer_to_box18:
    ldr r1, [sp, #12]
    movs r2, #34
.copy_boxmon:
    ldr r3, [r1, #0]
    str r3, [r0, #0]
    adds r1, #4
    adds r0, #4
    subs r2, r2, #1
    bne .copy_boxmon

.remove_from_party:
    ldr r0, [sp, #4]
    adds r1, r5, #0
    ldr r3, ={hex(cfg['fn_party_remove_pokemon_by_slot'] | 1)}
    blx r3

.party_slot_next:
    subs r5, r5, #1
    b .party_backwards_loop

.finish_transition:
    ldr r0, [sp, #16]
    ldr r1, [sp, #20]
    ldr r2, [sp, #24]
    add sp, #28
    ldr r3, ={hex(cfg['fn_field_battle_transition_end'] | 1)}
    blx r3
    pop {{r4, r5, r6, r7, pc}}
"""
        return self.asm.assemble_thumb(asm_code, base_addr)

    def apply(self, rom_handler: RomHandler) -> bool:
        cfg = self.CONFIG.get(rom_handler.game_code)
        if not cfg:
            cfg = UniversalResolver.resolve_permadeath(rom_handler)

        arm9 = rom_handler.rom.arm9
        arm9_ram = rom_handler.rom.arm9RamAddress

        # 1. Update pl_item_data.narc to disable revive attributes
        narc_path = "itemtool/itemdata/pl_item_data.narc"
        narc_raw = rom_handler.rom.getFileByName(narc_path)
        if narc_raw:
            narc = ndspy.narc.NARC(narc_raw)
            for item_id in cfg["revive_item_ids"]:
                if item_id < len(narc.files):
                    item_bytes = bytearray(narc.files[item_id])
                    if len(item_bytes) > 15:
                        item_bytes[15] &= ~0x03  # Clear revive and reviveAll bits
                        narc.files[item_id] = bytes(item_bytes)

            rare_candy_id = cfg.get("rare_candy_id")
            if rare_candy_id is not None and rare_candy_id < len(narc.files):
                rc_bytes = bytearray(narc.files[rare_candy_id])
                if len(rc_bytes) > 15:
                    rc_bytes[15] &= ~0x01  # Clear revive bit on Rare Candy
                    narc.files[rare_candy_id] = bytes(rc_bytes)

            rom_handler.rom.setFileByName(narc_path, narc.save())

        # 2. Verify original instructions at hook locations
        heal_off = cfg["party_heal_hook_addr"] - arm9_ram
        heal_curr = bytes(arm9[heal_off : heal_off + len(cfg["party_heal_expected"])])
        if heal_curr != cfg["party_heal_expected"]:
            raise RuntimeError(
                f"Hook mismatch at 0x{cfg['party_heal_hook_addr']:08X}! "
                f"Expected {cfg['party_heal_expected'].hex()}, got {heal_curr.hex()}"
            )

        item_off = cfg["item_check_hook_addr"] - arm9_ram
        item_curr = bytes(arm9[item_off : item_off + len(cfg["item_check_expected"])])
        if item_curr != cfg["item_check_expected"]:
            raise RuntimeError(
                f"Hook mismatch at 0x{cfg['item_check_hook_addr']:08X}! "
                f"Expected {cfg['item_check_expected'].hex()}, got {item_curr.hex()}"
            )

        blackout_off = cfg["hook_blackout_addr"] - arm9_ram
        blackout_curr = bytes(arm9[blackout_off : blackout_off + len(cfg["hook_blackout_expected"])])
        if blackout_curr != cfg["hook_blackout_expected"]:
            raise RuntimeError(
                f"Hook mismatch at 0x{cfg['hook_blackout_addr']:08X}! "
                f"Expected {cfg['hook_blackout_expected'].hex()}, got {blackout_curr.hex()}"
            )

        # 3. Assemble and place custom code in ARM9 free space
        heal_fn_addr = cfg["arm9_free_space_addr"]
        heal_bytes = self.generate_party_heal_code(cfg, heal_fn_addr)

        item_fn_addr = (heal_fn_addr + len(heal_bytes) + 3) & ~3
        item_bytes = self.generate_item_check_code(cfg, item_fn_addr)

        blackout_fn_addr = (item_fn_addr + len(item_bytes) + 3) & ~3
        blackout_bytes = self.generate_blackout_code(cfg, blackout_fn_addr)

        free_off = heal_fn_addr - arm9_ram
        arm9[free_off : free_off + len(heal_bytes)] = heal_bytes

        item_free_off = item_fn_addr - arm9_ram
        arm9[item_free_off : item_free_off + len(item_bytes)] = item_bytes

        blackout_free_off = blackout_fn_addr - arm9_ram
        arm9[blackout_free_off : blackout_free_off + len(blackout_bytes)] = blackout_bytes

        # 4. Hook 1: Party_HealAllMembers universal 8-byte jump
        heal_hook_asm = f"""
.thumb
ldr r3, [pc, #0]
bx r3
.align 2
.word {hex(heal_fn_addr | 1)}
"""
        heal_hook_bytes = self.asm.assemble_thumb(heal_hook_asm, cfg["party_heal_hook_addr"])
        arm9[heal_off : heal_off + len(heal_hook_bytes)] = heal_hook_bytes

        # 5. Hook 2: Party_CheckItemEffectsOnMember bl call
        item_hook_asm = f"""
.thumb
bl #{hex(item_fn_addr)}
"""
        item_hook_bytes = self.asm.assemble_thumb(item_hook_asm, cfg["item_check_hook_addr"])
        arm9[item_off : item_off + len(item_hook_bytes)] = item_hook_bytes

        # 6. Hook 3: Blackout penalty handler -> bl Custom_BlackoutGameOver
        blackout_hook_asm = f"""
.thumb
bl #{hex(blackout_fn_addr)}
"""
        blackout_hook_bytes = self.asm.assemble_thumb(blackout_hook_asm, cfg["hook_blackout_addr"])
        arm9[blackout_off : blackout_off + len(blackout_hook_bytes)] = blackout_hook_bytes

        # 7. Box 18 Naming ('CIMITERO') in ARM9
        if "box_name_hook_addr" in cfg and "box_name_free_space_addr" in cfg:
            box_hook_off = cfg["box_name_hook_addr"] - arm9_ram
            if "box_name_expected" in cfg:
                box_curr = bytes(arm9[box_hook_off : box_hook_off + len(cfg["box_name_expected"])])
                if box_curr != cfg["box_name_expected"]:
                    raise RuntimeError(
                        f"Hook mismatch at 0x{cfg['box_name_hook_addr']:08X}! "
                        f"Expected {cfg['box_name_expected'].hex()}, got {box_curr.hex()}"
                    )
            box_fn_addr = cfg["box_name_free_space_addr"]
            box_bytes = self.generate_box_name_code(cfg, box_fn_addr)
            box_free_off = box_fn_addr - arm9_ram
            arm9[box_free_off : box_free_off + len(box_bytes)] = box_bytes

            box_hook_asm = f"""
.thumb
bl #{hex(box_fn_addr)}
pop {{r3, pc}}
nop
nop
nop
nop
nop
"""
            box_hook_bytes = self.asm.assemble_thumb(box_hook_asm, cfg["box_name_hook_addr"])
            arm9[box_hook_off : box_hook_off + len(box_hook_bytes)] = box_hook_bytes

        # 8. Unmovable Box 18 in Overlay 19
        if "ov19_id" in cfg and "ov19_hook_addr" in cfg:
            ov19 = rom_handler.load_arm9_overlay(cfg["ov19_id"])
            ov19_ram = ov19.ramAddress
            ov19_hook_off = cfg["ov19_hook_addr"] - ov19_ram

            if "ov19_hook_expected" in cfg:
                ov19_curr = bytes(ov19.data[ov19_hook_off : ov19_hook_off + len(cfg["ov19_hook_expected"])])
                if ov19_curr != cfg["ov19_hook_expected"]:
                    raise RuntimeError(
                        f"Hook mismatch at 0x{cfg['ov19_hook_addr']:08X}! "
                        f"Expected {cfg['ov19_hook_expected'].hex()}, got {ov19_curr.hex()}"
                    )

            orig_size_19 = len(ov19.data)
            custom_base_19 = ov19_ram + orig_size_19
            code_bytes_19 = self.generate_graveyard_box_code(cfg, custom_base_19)
            pad_19 = (512 - (len(code_bytes_19) % 512)) % 512
            new_data_19 = bytearray(bytes(ov19.data) + code_bytes_19 + (b"\x00" * pad_19))

            hook19_code = f"bl #{hex(custom_base_19)}"
            hook19_bytes = self.asm.assemble_thumb(hook19_code, cfg["ov19_hook_addr"])
            new_data_19[ov19_hook_off : ov19_hook_off + len(hook19_bytes)] = hook19_bytes

            rom_handler.update_arm9_overlay(
                cfg["ov19_id"], ov19, bytes(new_data_19), new_ram_size=len(new_data_19)
            )

        # 9. Automatic Faint Transfer on Battle End (Overlay 5 + ARM9 battle end hooks)
        if "ov5_id" in cfg and "battle_end_hooks" in cfg:
            if "battle_end_expected" in cfg:
                for idx, hook_addr in enumerate(cfg["battle_end_hooks"]):
                    expected = cfg["battle_end_expected"][idx]
                    h_off = hook_addr - arm9_ram
                    curr = bytes(arm9[h_off : h_off + len(expected)])
                    if curr != expected:
                        raise RuntimeError(
                            f"Hook mismatch at 0x{hook_addr:08X}! "
                            f"Expected {expected.hex()}, got {curr.hex()}"
                        )

            ov5 = rom_handler.load_arm9_overlay(cfg["ov5_id"])
            ov5_ram = ov5.ramAddress
            orig_size_5 = len(ov5.data)
            custom_base_5 = ov5_ram + orig_size_5
            code_bytes_5 = self.generate_battle_end_code(cfg, custom_base_5)
            pad_5 = (512 - (len(code_bytes_5) % 512)) % 512
            new_data_5 = bytearray(bytes(ov5.data) + code_bytes_5 + (b"\x00" * pad_5))

            rom_handler.update_arm9_overlay(
                cfg["ov5_id"], ov5, bytes(new_data_5), new_ram_size=len(new_data_5)
            )

            for hook_addr in cfg["battle_end_hooks"]:
                hook_code = f"bl #{hex(custom_base_5)}"
                hook_bytes = self.asm.assemble_thumb(hook_code, hook_addr)
                h_off = hook_addr - arm9_ram
                arm9[h_off : h_off + len(hook_bytes)] = hook_bytes

        return True
