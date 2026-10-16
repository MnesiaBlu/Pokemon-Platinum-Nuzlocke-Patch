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
        "Blocks catching subsequent wild Pokemon on routes/areas where a Pokemon was already caught."
    )

    CONFIG = {
        b"CPUI": {
            "overlay_id": 16,
            "hook_addr": 0x02249EAA,
            "hook_expected": bytes.fromhex("00f0f9fc"),
            "fn_battle_get_map_header": 0x0223ED4D,  # Thumb address
            "fn_pokemon_get_value": 0x02074511,      # Thumb address
            "fn_box_pokemon_get_value": 0x02074611,  # Thumb address
            "fn_battle_calc_shakes": 0x0224A8A1,     # Thumb address
        }
    }

    def __init__(self):
        self.asm = Assembler()

    def generate_custom_code(self, cfg: dict, base_addr: int) -> tuple[bytes, int]:
        """Generate Custom_CalcCatchShakes assembly."""
        asm_code = f"""
.thumb
.align 2
Custom_CalcCatchShakes:
    push {{r4, r5, r6, r7, lr}}
    sub sp, #12
    adds r4, r0, #0
    str r1, [sp, #0]

    @ 1. Check special battle types: Tutorial (0x0400) or Pal Park (0x0200)
    ldr r0, [r4, #0x2c]
    movs r1, #0x06
    lsls r1, r1, #8
    tst r0, r1
    bne .calc_normal

    @ 2. Get current location (mapHeader / mapLabelTextID)
    adds r0, r4, #0
    ldr r1, ={hex(cfg['fn_battle_get_map_header'])}
    blx r1
    adds r7, r0, #0
    cmp r7, #0
    beq .calc_normal

    @ 3. Check Player Party (parties[0])
    ldr r0, [r4, #0x68]
    cmp r0, #0
    beq .check_pc
    ldr r5, [r0, #4]
    cmp r5, #6
    ble .party_count_ok
    movs r5, #6
.party_count_ok:
    cmp r5, #0
    ble .check_pc
    adds r6, r0, #0
    adds r6, #8
.party_loop:
    adds r0, r6, #0
    movs r1, #5            @ MON_DATA_SPECIES
    movs r2, #0
    ldr r3, ={hex(cfg['fn_pokemon_get_value'])}
    blx r3
    cmp r0, #0
    beq .next_party_mon

    adds r0, r6, #0
    movs r1, #153          @ MON_DATA_MET_LOCATION
    movs r2, #0
    ldr r3, ={hex(cfg['fn_pokemon_get_value'])}
    blx r3
    cmp r0, r7
    beq .catch_blocked

.next_party_mon:
    movs r0, #236          @ sizeof(Pokemon)
    adds r6, r6, r0
    subs r5, r5, #1
    bgt .party_loop

.check_pc:
    ldr r0, [r4, #0x64]
    cmp r0, #0
    beq .calc_normal
    adds r6, r0, #0
    adds r6, #4
    ldr r5, =540           @ 18 * 30 slots
.pc_loop:
    ldr r0, [r6, #0]       @ personality
    cmp r0, #0
    beq .next_pc_mon

    adds r0, r6, #0
    movs r1, #153          @ MON_DATA_MET_LOCATION
    movs r2, #0
    ldr r3, ={hex(cfg['fn_box_pokemon_get_value'])}
    blx r3
    cmp r0, r7
    beq .catch_blocked

.next_pc_mon:
    movs r0, #136          @ sizeof(BoxPokemon)
    adds r6, r6, r0
    subs r5, r5, #1
    bgt .pc_loop

.calc_normal:
    adds r0, r4, #0
    ldr r1, [sp, #0]
    ldr r2, ={hex(cfg['fn_battle_calc_shakes'])}
    blx r2
    add sp, #12
    pop {{r4, r5, r6, r7, pc}}

.catch_blocked:
    movs r0, #0
    add sp, #12
    pop {{r4, r5, r6, r7, pc}}
"""
        raw_bytes = self.asm.assemble_thumb(asm_code, base_addr)
        fn_addr = base_addr
        return raw_bytes, fn_addr

    def apply(self, rom_handler: RomHandler) -> bool:
        cfg = self.CONFIG.get(rom_handler.game_code)
        if not cfg:
            cfg = UniversalResolver.resolve_first_encounter(rom_handler)

        ov16 = rom_handler.load_arm9_overlay(cfg["overlay_id"])
        ov16_ram = ov16.ramAddress
        orig_size = len(ov16.data)

        # 1. Verify original instruction at hook location
        h_off = cfg["hook_addr"] - ov16_ram
        h_curr = bytes(ov16.data[h_off : h_off + len(cfg["hook_expected"])])
        if h_curr != cfg["hook_expected"]:
            raise RuntimeError(
                f"Hook mismatch at 0x{cfg['hook_addr']:08X}! Expected {cfg['hook_expected'].hex()}, got {h_curr.hex()}"
            )

        # 2. Append custom code at the end of Overlay 16
        custom_base_addr = ov16_ram + orig_size
        code_bytes, fn_addr = self.generate_custom_code(cfg, custom_base_addr)

        # Pad custom code to 512 bytes for alignment
        padding = (512 - (len(code_bytes) % 512)) % 512
        new_data = bytes(ov16.data) + code_bytes + (b"\x00" * padding)
        new_size = len(new_data)

        # 3. Assemble hook
        hook_code = f"""
bl {hex(fn_addr)}
"""
        hook_bytes = self.asm.assemble_thumb(hook_code, cfg["hook_addr"])
        assert len(hook_bytes) == len(cfg["hook_expected"])

        # 4. Patch hook into overlay data
        patched_data = bytearray(new_data)
        patched_data[h_off : h_off + len(hook_bytes)] = hook_bytes

        # 5. Save updated overlay to ROM
        rom_handler.update_arm9_overlay(
            cfg["overlay_id"], ov16, patched_data, new_ram_size=new_size
        )
        return True
