"""First Encounter Only Patch for Pokemon Platinum (Italian & US).

Enforces the Nuzlocke first encounter rule:
Only the first Pokemon encountered/caught in each route/area can be caught.
Subsequent catch attempts on routes where a Pokemon has already been caught
(found in the player's Party or PC Storage Boxes) are blocked:
the thrown ball shakes 0 times and the Pokemon immediately breaks free.
"""

from .base import BasePatch
from ..rom import RomHandler
from ..arm_asm import Assembler
from ..scanner import UniversalResolver


class FirstEncounterPatch(BasePatch):
    name = "First Encounter Only"
    description = (
        "Enforces Nuzlocke first encounter: exactly one chance to catch per route. "
        "Fleeing or defeating it permanently burns the route."
    )

    CONFIG = {
        b"CPUI": {
            "overlay_id": 16,
            "hook_init_addr": 0x0223D984,
            "hook_init_expected": bytes.fromhex("fef74cfd"),
            "fn_battle_sys_new": 0x0223C421,
            "save_data_ptr": 0x021C08F4,
            "fn_save_data_save_table": 0x0202462D,
            "hook_addr": 0x02249EAA,
            "hook_expected": bytes.fromhex("00f0f9fc"),
            "fn_pokemon_get_value": 0x02074511,      # Thumb address
            "fn_box_pokemon_get_value": 0x02074611,  # Thumb address
            "fn_battle_calc_shakes": 0x0224A8A1,     # Thumb address
        }
    }

    def __init__(self):
        self.asm = Assembler()

    def generate_custom_code(self, cfg: dict, base_addr: int) -> tuple[bytes, int, int]:
        """Generate Custom_BattleInit and Custom_CalcCatchShakes routines.

        Returns:
            Tuple of (total_bytes, addr_battle_init, addr_calc_shakes).
        """
        code_init = f"""
.thumb
.align 2
Custom_BattleInit:
    push {{r4, r5, r6, r7, lr}}
    sub sp, #12

    adds r4, r0, #0        @ r4 = battleSys
    adds r5, r1, #0        @ r5 = dto

    @ 1. Call original BattleSys_New(battleSys, dto)
    ldr r2, ={hex(cfg['fn_battle_sys_new'])}
    blx r2

    @ 2. Check if this is a wild battle (singles wild mon has battleType == 0)
    ldr r0, [r4, #0x2c]    @ battleType
    movs r1, #1
    tst r0, r1
    bne .init_done         @ Trainer battle -> done

    @ Also check special wild battles: Pal Park (1<<9) or Catch Tutorial (1<<10)
    movs r1, #0x06
    lsls r1, r1, #8        @ r1 = 0x0600
    tst r0, r1
    bne .init_done         @ Pal Park / Catch Tutorial -> done

    @ 3. Check Poke Ball Clause: Has player received Pokedex? (FLAG_HAS_POKEDEX = 146)
    ldr r0, ={hex(cfg['save_data_ptr'])}
    ldr r0, [r0]           @ r0 = saveData
    cmp r0, #0
    beq .init_done

    movs r1, #4            @ SAVE_TABLE_ENTRY_VARS_FLAGS
    ldr r2, ={hex(cfg['fn_save_data_save_table'])}
    blx r2
    cmp r0, #0
    beq .init_done
    adds r7, r0, #0        @ r7 = varsFlags

    @ Check flag 146: byte = flags[18], bit = (1 << 2) = 4
    ldr r1, =0x248
    adds r0, r7, r1
    ldrb r1, [r0, #18]
    movs r2, #4
    tst r1, r2
    beq .init_done         @ No Pokedex yet -> don't consume route!

    @ 4. Get current location (mapLabelTextID) from battleSys->mapHeader (0x240C)
    ldr r1, =0x240c
    ldr r6, [r4, r1]       @ r6 = mapLabelTextID (loc)
    cmp r6, #0
    beq .init_done
    cmp r6, #150
    bge .init_done

    @ 5. Check if a mon with MON_DATA_MET_LOCATION == loc is already in Party
    ldr r0, [r4, #0x68]    @ parties[0]
    cmp r0, #0
    beq .check_pc
    ldr r5, [r0, #4]       @ party count
    cmp r5, #6
    ble .party_cnt_ok
    movs r5, #6
.party_cnt_ok:
    cmp r5, #0
    ble .check_pc
    adds r1, r0, #0
    adds r1, #8            @ party Pokemon array
.party_chk_loop:
    adds r0, r1, #0
    str r1, [sp, #0]
    movs r1, #5            @ MON_DATA_SPECIES
    movs r2, #0
    ldr r3, ={hex(cfg['fn_pokemon_get_value'])}
    blx r3
    cmp r0, #0
    beq .party_chk_next

    ldr r0, [sp, #0]
    movs r1, #153          @ MON_DATA_MET_LOCATION
    movs r2, #0
    ldr r3, ={hex(cfg['fn_pokemon_get_value'])}
    blx r3
    cmp r0, r6
    beq .route_blocked     @ Already caught/owned! Block!

.party_chk_next:
    ldr r1, [sp, #0]
    movs r0, #236          @ sizeof(Pokemon)
    adds r1, r1, r0
    subs r5, r5, #1
    bgt .party_chk_loop

.check_pc:
    @ 6. Check if a mon with MON_DATA_MET_LOCATION == loc is already in PC Boxes
    ldr r0, [r4, #0x64]    @ pcBoxes
    cmp r0, #0
    beq .check_route_flag
    adds r1, r0, #0
    adds r1, #4            @ box mon array start
    ldr r5, =540           @ 18 * 30 slots
.pc_chk_loop:
    ldr r0, [r1, #0]       @ personality
    cmp r0, #0
    beq .pc_chk_next

    str r1, [sp, #0]
    adds r0, r1, #0
    movs r1, #153          @ MON_DATA_MET_LOCATION
    movs r2, #0
    ldr r3, ={hex(cfg['fn_box_pokemon_get_value'])}
    blx r3
    cmp r0, r6
    beq .route_blocked     @ Already caught/owned! Block!
    ldr r1, [sp, #0]

.pc_chk_next:
    movs r0, #136          @ sizeof(BoxPokemon)
    adds r1, r1, r0
    subs r5, r5, #1
    bgt .pc_chk_loop

.check_route_flag:
    @ 7. Check if this route has already had a wild encounter:
    @ Flag ID = BASE_FLAG (2562) + loc
    ldr r0, =2562
    adds r1, r0, r6        @ r1 = flagID
    lsrs r2, r1, #3        @ r2 = byte index
    movs r3, #7
    ands r1, r3            @ r1 = bit index
    movs r3, #1
    lsls r3, r1            @ r3 = bitmask (1 << bit_index)

    ldr r0, =0x248
    adds r0, r7, r0        @ r0 = &varsFlags->flags[0]
    adds r0, r0, r2        @ r0 = &varsFlags->flags[byte_index]
    ldrb r1, [r0, #0]
    tst r1, r3
    bne .route_blocked     @ Flag is ALREADY set -> Route already burned! Block!

    @ 8. THIS IS THE FIRST ENCOUNTER!
    @ Mark this battle as ALLOWED in battleSys->unread_2440:
    movs r2, #1
    ldr r1, =0x2440
    strb r2, [r4, r1]

    @ Mark route as consumed in SaveData now:
    orrs r1, r3
    strb r1, [r0, #0]
    b .init_done

.route_blocked:
    @ Mark this battle as BLOCKED in battleSys->unread_2440:
    movs r0, #2
    ldr r1, =0x2440
    strb r0, [r4, r1]

.init_done:
    add sp, #12
    pop {{r4, r5, r6, r7, pc}}
"""
        b1 = self.asm.assemble_thumb(code_init, base_addr)
        pad = (4 - (len(b1) % 4)) % 4
        calc_shakes_addr = base_addr + len(b1) + pad

        code_shakes = f"""
.thumb
.align 2
Custom_CalcCatchShakes:
    push {{r4, lr}}
    adds r4, r0, #0
    ldr r1, =0x2440
    ldrb r0, [r4, r1]
    cmp r0, #2             @ 2 = BLOCKED!
    beq .catch_blocked

.calc_normal:
    adds r0, r4, #0
    ldr r1, [sp, #8]
    ldr r2, ={hex(cfg['fn_battle_calc_shakes'])}
    blx r2
    pop {{r4, pc}}

.catch_blocked:
    movs r0, #0            @ 0 shakes -> breaks free immediately!
    pop {{r4, pc}}
"""
        b2 = self.asm.assemble_thumb(code_shakes, calc_shakes_addr)
        total_bytes = b1 + (b"\x00" * pad) + b2
        return total_bytes, base_addr, calc_shakes_addr

    def apply(self, rom_handler: RomHandler) -> bool:
        cfg = self.CONFIG.get(rom_handler.game_code)
        if not cfg:
            cfg = UniversalResolver.resolve_first_encounter(rom_handler)

        ov16 = rom_handler.load_arm9_overlay(cfg["overlay_id"])
        ov16_ram = ov16.ramAddress
        orig_size = len(ov16.data)

        # 1. Verify original instructions at both hook locations
        h1_off = cfg["hook_init_addr"] - ov16_ram
        h1_curr = bytes(ov16.data[h1_off : h1_off + len(cfg["hook_init_expected"])])
        if h1_curr != cfg["hook_init_expected"]:
            raise RuntimeError(
                f"Hook 1 (init) mismatch at 0x{cfg['hook_init_addr']:08X}! "
                f"Expected {cfg['hook_init_expected'].hex()}, got {h1_curr.hex()}"
            )

        h2_off = cfg["hook_addr"] - ov16_ram
        h2_curr = bytes(ov16.data[h2_off : h2_off + len(cfg["hook_expected"])])
        if h2_curr != cfg["hook_expected"]:
            raise RuntimeError(
                f"Hook 2 (throw ball) mismatch at 0x{cfg['hook_addr']:08X}! "
                f"Expected {cfg['hook_expected'].hex()}, got {h2_curr.hex()}"
            )

        # 2. Append custom code at the end of Overlay 16
        custom_base_addr = ov16_ram + orig_size
        code_bytes, fn_init, fn_shakes = self.generate_custom_code(cfg, custom_base_addr)

        # Pad custom code to 512 bytes for alignment
        padding = (512 - (len(code_bytes) % 512)) % 512
        new_data = bytes(ov16.data) + code_bytes + (b"\x00" * padding)
        new_size = len(new_data)

        # 3. Assemble hooks
        # Hook 1: bl Custom_BattleInit
        hook1_code = f"bl #{hex(fn_init)}"
        hook1_bytes = self.asm.assemble_thumb(hook1_code, cfg["hook_init_addr"])
        assert len(hook1_bytes) == len(cfg["hook_init_expected"])

        # Hook 2: bl Custom_CalcCatchShakes
        hook2_code = f"bl #{hex(fn_shakes)}"
        hook2_bytes = self.asm.assemble_thumb(hook2_code, cfg["hook_addr"])
        assert len(hook2_bytes) == len(cfg["hook_expected"])

        # 4. Patch hooks into overlay data
        patched_data = bytearray(new_data)
        patched_data[h1_off : h1_off + len(hook1_bytes)] = hook1_bytes
        patched_data[h2_off : h2_off + len(hook2_bytes)] = hook2_bytes

        # 5. Save updated overlay to ROM
        rom_handler.update_arm9_overlay(
            cfg["overlay_id"], ov16, patched_data, new_ram_size=new_size
        )
        return True
