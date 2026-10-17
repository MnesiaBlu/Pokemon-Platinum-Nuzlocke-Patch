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
            # Overlay 5 (Overworld Location Banner):
            "ov5_id": 5,
            "ov5_hooks": [0x021DDAE0, 0x021DDBD0],
            "fn_msg_loader_get_string": 0x0200B1CD,
            "fn_font_calc_string_width": 0x02002D91,
            # Overlay 80 (Town Map / Mappa Citta):
            "ov80_id": 80,
            "ov80_hooks": [0x021D1BC8, 0x021D1BEA, 0x021D1C00],
            "fn_map_header_get_map_name_string": 0x02071DA5,
            "fn_map_header_get_label_text_id": 0x0203A1DD,
            # Storage
            "fn_save_data_get_pc_storage": 0x02024491,
            "fn_pc_storage_get_box_pokemon": 0x02079D3D,
            "banner_free_space_addr": 0x020F9408,
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

    def generate_map_banner_code(self, cfg: dict, base_addr: int) -> bytes:
        """Generate Custom_MapHeader_LoadString placed in ARM9 (0x020F9408).

        Overlay 5 calls this function from 0x021DDAE0 and 0x021DDBD0 without expanding Overlay 5.
        Appends ' (O)' if encounter is available, ' (X)' if consumed.
        """
        code = f"""
.thumb
.align 2
Custom_MapHeader_LoadString:
    push {{r4, r5, r6, lr}}
    adds r4, r0, #0
    adds r5, r1, #0
    adds r6, r2, #0

    @ 1. Call MessageLoader_GetString(msgLoader, entryID, string)
    ldr r3, ={hex(cfg['fn_msg_loader_get_string'] | 1)}
    blx r3

    @ 2. Poke Ball Clause: Check if player has Pokedex (flag 146)
    ldr r0, ={hex(cfg['save_data_ptr'])}
    ldr r0, [r0]
    cmp r0, #0
    beq .calc_w

    movs r1, #4            @ SAVE_TABLE_ENTRY_VARS_FLAGS
    ldr r3, ={hex(cfg['fn_save_data_save_table'] | 1)}
    blx r3
    cmp r0, #0
    beq .calc_w

    ldr r1, =0x248
    adds r1, r0, r1
    ldrb r2, [r1, #18]
    movs r3, #4
    tst r2, r3
    beq .calc_w            @ No Pokedex -> skip suffix

    @ 3. Check entryID range (0..149)
    cmp r5, #0
    beq .calc_w
    cmp r5, #150
    bge .calc_w

    @ 4. Check route flag (2562 + entryID)
    ldr r2, =2562
    adds r2, r2, r5
    lsrs r3, r2, #3
    adds r3, r1, r3
    ldrb r3, [r3, #0]
    movs r1, #7
    ands r2, r1
    movs r1, #1
    lsls r1, r2
    tst r3, r1
    bne .app_x

    @ Lake Verity starter clause (entryID 4)
    cmp r5, #4
    beq .app_x

.app_o:
    movs r0, #0x39         @ 'O'
    b .app_suf
.app_x:
    movs r0, #0x42         @ 'X'
.app_suf:
    ldrh r1, [r6, #2]      @ string->size
    ldrh r2, [r6, #0]      @ string->maxsize
    adds r3, r1, #4
    cmp r3, r2
    bgt .calc_w

    lsls r2, r1, #1
    adds r2, r6, r2
    adds r2, #8
    ldr r3, =0x01DE        @ ' '
    strh r3, [r2, #0]
    ldr r3, =0x01B9        @ '('
    strh r3, [r2, #2]
    movs r3, #1
    lsls r3, r3, #8
    orrs r3, r0
    strh r3, [r2, #4]
    ldr r3, =0x01BA        @ ')'
    strh r3, [r2, #6]
    movs r3, #0
    mvns r3, r3
    strh r3, [r2, #8]      @ 0xFFFF terminator
    adds r1, #4
    strh r1, [r6, #2]

.calc_w:
    movs r0, #0            @ fontID = 0
    adds r1, r6, #0        @ string
    movs r2, #0            @ letterSpacing = 0
    ldr r3, ={hex(cfg['fn_font_calc_string_width'] | 1)}
    blx r3
    pop {{r4, r5, r6, pc}}
"""
        return self.asm.assemble_thumb(code, base_addr)

    def generate_town_map_code(self, cfg: dict, base_addr: int) -> bytes:
        """Generate Custom_MapHeader_GetMapNameString for Overlay 80 (Town Map).

        Appends ' (O)' if encounter is available, ' (X)' if consumed or already owned.
        """
        code = f"""
.thumb
.align 2
Custom_MapHeader_GetMapNameString:
    push {{r4, r5, r6, r7, lr}}
    sub sp, #16

    adds r4, r0, #0        @ r4 = mapID
    adds r5, r1, #0        @ r5 = heapID
    adds r6, r2, #0        @ r6 = string

    @ 1. Call original MapHeader_GetMapNameString(mapID, heapID, string)
    ldr r3, ={hex(cfg['fn_map_header_get_map_name_string'])}
    blx r3

    @ 2. Get labelTextID from mapID
    adds r0, r4, #0
    ldr r3, ={hex(cfg['fn_map_header_get_label_text_id'])}
    blx r3
    adds r5, r0, #0        @ r5 = entryID (labelTextID)

    @ 3. Poke Ball Clause: Check if player has Pokedex (flag 146)
    ldr r0, ={hex(cfg['save_data_ptr'])}
    ldr r0, [r0]           @ r0 = saveData
    cmp r0, #0
    beq .done
    str r0, [sp, #8]       @ save saveData on stack

    movs r1, #4            @ SAVE_TABLE_ENTRY_VARS_FLAGS
    ldr r3, ={hex(cfg['fn_save_data_save_table'])}
    blx r3
    cmp r0, #0
    beq .done
    adds r7, r0, #0        @ r7 = varsFlags

    @ Check flag 146: byte = flags[18], bit = (1 << 2) = 4
    ldr r1, =0x248
    adds r0, r7, r1
    ldrb r1, [r0, #18]
    movs r2, #4
    tst r1, r2
    beq .done              @ No Pokedex -> don't show any indicator!

    @ 4. Check entryID range (0..149)
    cmp r5, #0
    beq .done
    cmp r5, #150
    bge .done

    @ 5. Check if flag (2562 + entryID) is set in varsFlags
    ldr r0, =2562
    adds r1, r0, r5        @ r1 = flagID
    lsrs r2, r1, #3        @ r2 = byte index
    movs r3, #7
    ands r1, r3            @ r1 = bit index
    movs r3, #1
    lsls r3, r1            @ r3 = bitmask

    ldr r0, =0x248
    adds r0, r7, r0
    adds r0, r0, r2
    ldrb r1, [r0, #0]
    tst r1, r3
    bne .append_x          @ Route encounter already consumed!

    @ 6. Check Party for a mon with MON_DATA_MET_LOCATION == entryID
    ldr r0, [sp, #8]       @ r0 = saveData
    movs r1, #2            @ SAVE_TABLE_ENTRY_PARTY
    ldr r3, ={hex(cfg['fn_save_data_save_table'])}
    blx r3
    cmp r0, #0
    beq .check_pc
    ldr r1, [r0, #4]       @ party count
    cmp r1, #6
    ble .party_cnt_ok
    movs r1, #6
.party_cnt_ok:
    cmp r1, #0
    ble .check_pc
    str r1, [sp, #12]      @ party count loop counter
    adds r7, r0, #8        @ party Pokemon array start

.party_loop:
    adds r0, r7, #0
    movs r1, #5            @ MON_DATA_SPECIES
    movs r2, #0
    ldr r3, ={hex(cfg['fn_pokemon_get_value'])}
    blx r3
    cmp r0, #0
    beq .party_next

    adds r0, r7, #0
    movs r1, #153          @ MON_DATA_MET_LOCATION
    movs r2, #0
    ldr r3, ={hex(cfg['fn_pokemon_get_value'])}
    blx r3
    cmp r0, r5
    beq .append_x          @ Already owned!

.party_next:
    movs r0, #236          @ sizeof(Pokemon)
    adds r7, r7, r0
    ldr r1, [sp, #12]
    subs r1, r1, #1
    str r1, [sp, #12]
    bgt .party_loop

.check_pc:
    @ 7. Check PC Boxes
    ldr r0, [sp, #8]       @ r0 = saveData
    ldr r3, ={hex(cfg['fn_save_data_get_pc_storage'])}
    blx r3
    cmp r0, #0
    beq .append_o
    str r0, [sp, #0]       @ pcStorage

    movs r7, #0            @ box = 0
.pc_box_loop:
    movs r4, #0            @ slot = 0
.pc_slot_loop:
    ldr r0, [sp, #0]       @ pcStorage
    adds r1, r7, #0        @ box
    adds r2, r4, #0        @ slot
    ldr r3, ={hex(cfg['fn_pc_storage_get_box_pokemon'])}
    blx r3
    cmp r0, #0
    beq .pc_slot_next

    str r0, [sp, #4]       @ boxMon
    movs r1, #5            @ MON_DATA_SPECIES
    movs r2, #0
    ldr r3, ={hex(cfg['fn_box_pokemon_get_value'])}
    blx r3
    cmp r0, #0
    beq .pc_slot_next

    ldr r0, [sp, #4]
    movs r1, #153          @ MON_DATA_MET_LOCATION
    movs r2, #0
    ldr r3, ={hex(cfg['fn_box_pokemon_get_value'])}
    blx r3
    cmp r0, r5
    beq .append_x

.pc_slot_next:
    adds r4, r4, #1
    cmp r4, #30
    blt .pc_slot_loop
    adds r7, r7, #1
    cmp r7, #18
    blt .pc_box_loop

.append_o:
    movs r0, #0x39         @ 'O' charcode = 0x0139
    b .append_suffix

.append_x:
    movs r0, #0x42         @ 'X' charcode = 0x0142

.append_suffix:
    @ Check if string has room for 4 chars: (string->size + 4 <= string->maxsize)
    ldrh r1, [r6, #2]      @ string->size
    ldrh r2, [r6, #0]      @ string->maxsize
    adds r3, r1, #4
    cmp r3, r2
    bgt .done

    @ data pointer = string + 8 + (size * 2)
    lsls r2, r1, #1
    adds r2, r6, r2
    adds r2, #8

    @ Write ' ' (0x01DE)
    ldr r3, =0x01DE
    strh r3, [r2, #0]

    @ Write '(' (0x01B9)
    ldr r3, =0x01B9
    strh r3, [r2, #2]

    @ Write marker (0x0100 + r0)
    movs r3, #1
    lsls r3, r3, #8
    orrs r3, r0
    strh r3, [r2, #4]

    @ Write ')' (0x01BA)
    ldr r3, =0x01BA
    strh r3, [r2, #6]

    @ Write terminator 0xFFFF
    movs r3, #0
    mvns r3, r3
    strh r3, [r2, #8]

    @ Update string->size += 4
    ldrh r1, [r6, #2]
    adds r1, #4
    strh r1, [r6, #2]

.done:
    add sp, #16
    pop {{r4, r5, r6, r7, pc}}
"""
        return self.asm.assemble_thumb(code, base_addr)

    def apply(self, rom_handler: RomHandler) -> bool:
        cfg = self.CONFIG.get(rom_handler.game_code)
        if not cfg:
            cfg = UniversalResolver.resolve_first_encounter(rom_handler)

        # ---------------------------------------------------------------------
        # 1. Overlay 16: Battle System (Catch restriction & route consumption)
        # ---------------------------------------------------------------------
        ov16 = rom_handler.load_arm9_overlay(cfg["overlay_id"])
        ov16_ram = ov16.ramAddress
        orig_size = len(ov16.data)

        # Verify original instructions at both hook locations
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

        # Append custom code at the end of Overlay 16
        custom_base_addr = ov16_ram + orig_size
        code_bytes, fn_init, fn_shakes = self.generate_custom_code(cfg, custom_base_addr)

        padding = (512 - (len(code_bytes) % 512)) % 512
        new_data = bytes(ov16.data) + code_bytes + (b"\x00" * padding)
        new_size = len(new_data)

        hook1_code = f"bl #{hex(fn_init)}"
        hook1_bytes = self.asm.assemble_thumb(hook1_code, cfg["hook_init_addr"])
        assert len(hook1_bytes) == len(cfg["hook_init_expected"])

        hook2_code = f"bl #{hex(fn_shakes)}"
        hook2_bytes = self.asm.assemble_thumb(hook2_code, cfg["hook_addr"])
        assert len(hook2_bytes) == len(cfg["hook_expected"])

        patched_data = bytearray(new_data)
        patched_data[h1_off : h1_off + len(hook1_bytes)] = hook1_bytes
        patched_data[h2_off : h2_off + len(hook2_bytes)] = hook2_bytes

        rom_handler.update_arm9_overlay(
            cfg["overlay_id"], ov16, patched_data, new_ram_size=new_size
        )

        # ---------------------------------------------------------------------
        # 2. Overlay 5: Overworld Location Banner Indicator (In-Place)
        # ---------------------------------------------------------------------
        if "ov5_id" in cfg and "ov5_hooks" in cfg:
            arm9 = rom_handler.rom.arm9
            arm9_ram = rom_handler.rom.arm9RamAddress
            banner_fn_addr = cfg.get("banner_free_space_addr", 0x020F9408)
            code_bytes_5 = self.generate_map_banner_code(cfg, banner_fn_addr)

            # Write custom banner code into ARM9 free space
            banner_off = banner_fn_addr - arm9_ram
            arm9[banner_off : banner_off + len(code_bytes_5)] = code_bytes_5

            # Patch Overlay 5 in-place WITHOUT expanding it (preserves BSS!)
            ov5 = rom_handler.load_arm9_overlay(cfg["ov5_id"])
            ov5_ram = ov5.ramAddress
            new_data_5 = bytearray(bytes(ov5.data))

            for hook_addr in cfg["ov5_hooks"]:
                hook_code = f"bl #{hex(banner_fn_addr)}"
                hook_bytes = self.asm.assemble_thumb(hook_code, hook_addr)
                off = hook_addr - ov5_ram
                new_data_5[off : off + 4] = hook_bytes

            rom_handler.update_arm9_overlay(
                cfg["ov5_id"], ov5, bytes(new_data_5), new_ram_size=len(new_data_5)
            )

        # ---------------------------------------------------------------------
        # 3. Overlay 80: Town Map (Mappa Citta) Catch Indicator
        # ---------------------------------------------------------------------
        if "ov80_id" in cfg and "ov80_hooks" in cfg:
            ov80 = rom_handler.load_arm9_overlay(cfg["ov80_id"])
            ov80_ram = ov80.ramAddress
            orig_size_80 = len(ov80.data)

            custom_base_80 = ov80_ram + orig_size_80
            code_bytes_80 = self.generate_town_map_code(cfg, custom_base_80)
            pad_80 = (512 - (len(code_bytes_80) % 512)) % 512
            new_data_80 = bytearray(bytes(ov80.data) + code_bytes_80 + (b"\x00" * pad_80))

            for hook_addr in cfg["ov80_hooks"]:
                hook_code = f"bl #{hex(custom_base_80)}"
                hook_bytes = self.asm.assemble_thumb(hook_code, hook_addr)
                off = hook_addr - ov80_ram
                new_data_80[off : off + 4] = hook_bytes

            rom_handler.update_arm9_overlay(
                cfg["ov80_id"], ov80, bytes(new_data_80), new_ram_size=len(new_data_80)
            )

        return True
