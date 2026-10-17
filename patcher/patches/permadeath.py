"""Permadeath Patch for Pokemon Platinum (Italian & US).

Enforces the core Nuzlocke permadeath rule:
1. Fainted Pokemon (HP = 0) cannot be revived by any items (Revive, Max Revive,
   Revival Herb, Sacred Ash, or Rare Candy).
2. Healing events (Pokemon Centers, beds, Mom, overworld doctors/healers)
   skip fainted Pokemon in Party_HealAllMembers, preserving their 0 HP and
   fainted status.
3. Item parameters in pl_item_data.narc have their revive attributes cleared,
   disabling in-battle and out-of-battle revival mechanics.
"""

import ndspy.narc
from .base import BasePatch
from ..rom import RomHandler
from ..arm_asm import Assembler
from ..scanner import UniversalResolver


class PermadeathPatch(BasePatch):
    name = "Permadeath & Hardcore Game Over"
    description = (
        "Fainted Pokemon cannot be revived via items and remain fainted at Pokemon Centers. "
        "A blackout (all party members fainted) triggers Game Over: save file is erased."
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
            "fn_party_get_pokemon_by_slot": 0x0207A19C,
            "fn_pokemon_get_value": 0x02074510,
            "fn_pokemon_set_value": 0x02074BD0,
            "fn_is_move_missing_pp": 0x02096FD4,
            "fn_restore_pokemon_move_pp": 0x02097024,
            "fn_pokemon_check_item_effects": 0x020964C0,
            "revive_item_ids": [28, 29, 37, 44],  # Revive, Max Revive, Revival Herb, Sacred Ash
            "rare_candy_id": 50,
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
    ldr r2, ={hex(cfg['fn_save_data_erase'])}
    blx r2

    @ 3. Call SoftReset(0)
    movs r0, #0
    ldr r2, ={hex(cfg['fn_soft_reset'])}
    blx r2

.dead_halt:
    b .dead_halt
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
        # ldr r3, [pc, #0]; bx r3; .word heal_fn_addr | 1
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

        return True
