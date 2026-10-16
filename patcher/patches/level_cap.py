"""Level Cap Patch for Pokemon Platinum (Italian & US).

Enforces Nuzlocke level caps based on the highest-level Pokemon of the upcoming
Gym Leader or Champion:
- Pedro (Oreburgh): Lv 14
- Gardenia (Eterna): Lv 22
- Fannie (Hearthome): Lv 26
- Marzia (Veilstone): Lv 32
- Omar (Pastoria): Lv 37
- Ferruccio (Canalave): Lv 41
- Bianca (Snowpoint): Lv 44
- Corrado (Sunyshore): Lv 50
- Camilla (Pokemon League): Lv 62
- Post-game (Story cleared): Lv 100 (Uncapped)

When at or above the level cap, Pokemon do not gain EXP in battle.
Any battle EXP gained that would push the Pokemon past the level cap is
clamped exactly to the cap level with 0 surplus EXP.
"""

from .base import BasePatch
from ..rom import RomHandler
from ..arm_asm import Assembler


class LevelCapPatch(BasePatch):
    name = "Level Cap"
    description = (
        "Limits battle EXP so Pokemon cannot exceed the upcoming Gym Leader/Champion's level cap."
    )

    # Memory map / config per game version
    CONFIG = {
        b"CPUI": {
            "overlay_id": 16,
            "hook1_addr": 0x02249184,
            "hook1_expected": bytes.fromhex("642800d185e0"),
            "hook2_addr": 0x02249242,
            "hook2_expected": bytes.fromhex("13990e980a181392"),
            "exp_skip_target": 0x02249297,  # Thumb address of 0x02249296
            "save_data_ptr": 0x021C08F4,
            "fn_save_get_trainer_info": 0x02025EA8,
            "fn_pokemon_get_value": 0x02074510,
            "fn_pokemon_get_species_base_exp": 0x02075B70,
        }
    }

    def __init__(self):
        self.asm = Assembler()

    def generate_custom_code(self, cfg: dict, base_addr: int) -> tuple[bytes, int, int]:
        """Generate GetLevelCap, CheckLevelCapHook, and ClampExpHook assembly."""
        asm_code = f"""
.thumb
.align 2
GetLevelCap:
    push {{r4, r5, lr}}
    cmp r0, #0
    bne .from_battlesys
    @ If battleSys is NULL, try sSaveDataPtr
    ldr r0, ={hex(cfg['save_data_ptr'])}
    ldr r0, [r0]
    cmp r0, #0
    beq .cap100
    ldr r1, ={hex(cfg['fn_save_get_trainer_info'])}
    blx r1
    b .check_info
.from_battlesys:
    ldr r0, [r0, #0x48]
.check_info:
    cmp r0, #0
    beq .cap100
    @ Check if main story cleared (Cynthia beaten)
    ldrb r1, [r0, #0x1d]
    movs r2, #1
    tst r1, r2
    bne .cap100
    @ Check badges (Coal: 0x01, Forest: 0x02, Cobble: 0x04, Fen: 0x08, Relic: 0x10, Mine: 0x20, Icicle: 0x40, Beacon: 0x80)
    ldrb r1, [r0, #0x1a]
    movs r2, #0x01
    tst r1, r2
    beq .cap14
    movs r2, #0x02
    tst r1, r2
    beq .cap22
    movs r2, #0x10
    tst r1, r2
    beq .cap26
    movs r2, #0x0c
    tst r1, r2
    beq .cap32
    movs r3, #0x0c
    ands r3, r1
    cmp r3, #0x0c
    bne .cap37
    movs r2, #0x20
    tst r1, r2
    beq .cap41
    movs r2, #0x40
    tst r1, r2
    beq .cap44
    movs r2, #0x80
    tst r1, r2
    beq .cap50
    movs r0, #62
    pop {{r4, r5, pc}}
.cap14:
    movs r0, #14
    pop {{r4, r5, pc}}
.cap22:
    movs r0, #22
    pop {{r4, r5, pc}}
.cap26:
    movs r0, #26
    pop {{r4, r5, pc}}
.cap32:
    movs r0, #32
    pop {{r4, r5, pc}}
.cap37:
    movs r0, #37
    pop {{r4, r5, pc}}
.cap41:
    movs r0, #41
    pop {{r4, r5, pc}}
.cap44:
    movs r0, #44
    pop {{r4, r5, pc}}
.cap50:
    movs r0, #50
    pop {{r4, r5, pc}}
.cap100:
    movs r0, #100
    pop {{r4, r5, pc}}

.align 2
CheckLevelCapHook:
    push {{r4, lr}}
    adds r1, r0, #0
    ldr r0, [r4, #0]
    bl GetLevelCap
    cmp r1, r0
    bhs .skip_exp
    pop {{r4, pc}}
.skip_exp:
    pop {{r4}}
    pop {{r3}}
    ldr r0, ={hex(cfg['exp_skip_target'])}
    bx r0

.align 2
ClampExpHook:
    push {{r4, r5, r6, r7, lr}}
    adds r7, r0, #0
    ldr r5, [r7, #0x4c]
    ldr r1, [r7, #0x38]
    adds r2, r5, r1
    ldr r0, [r4, #0]
    bl GetLevelCap
    cmp r0, #100
    bge .done_clamp
    adds r4, r0, #0
    adds r0, r6, #0
    movs r1, #5
    movs r2, #0
    ldr r3, ={hex(cfg['fn_pokemon_get_value'])}
    blx r3
    adds r1, r4, #0
    ldr r3, ={hex(cfg['fn_pokemon_get_species_base_exp'])}
    blx r3
    ldr r1, [r7, #0x38]
    adds r2, r5, r1
    cmp r2, r0
    blo .done_clamp
    adds r2, r0, #0
    subs r1, r2, r5
    bge .store_total
    movs r1, #0
.store_total:
    str r1, [r7, #0x38]
.done_clamp:
    str r2, [r7, #0x4c]
    pop {{r4, r5, r6, r7, pc}}
"""
        raw_bytes = self.asm.assemble_thumb(asm_code, base_addr)

        # Offsets inside the assembled block:
        # GetLevelCap is at +0x00
        # CheckLevelCapHook is at +0x80
        # ClampExpHook is at +0x98
        hook1_fn_addr = base_addr + 0x80
        hook2_fn_addr = base_addr + 0x98
        return raw_bytes, hook1_fn_addr, hook2_fn_addr

    def apply(self, rom_handler: RomHandler) -> bool:
        cfg = self.CONFIG.get(rom_handler.game_code)
        if not cfg:
            raise ValueError(f"LevelCapPatch does not support game code: {rom_handler.game_code}")

        ov16 = rom_handler.load_arm9_overlay(cfg["overlay_id"])
        ov16_ram = ov16.ramAddress
        orig_size = len(ov16.data)

        # 1. Verify original instructions at hook locations
        h1_off = cfg["hook1_addr"] - ov16_ram
        h1_curr = bytes(ov16.data[h1_off : h1_off + len(cfg["hook1_expected"])])
        if h1_curr != cfg["hook1_expected"]:
            raise RuntimeError(
                f"Hook 1 mismatch at 0x{cfg['hook1_addr']:08X}! Expected {cfg['hook1_expected'].hex()}, got {h1_curr.hex()}"
            )

        h2_off = cfg["hook2_addr"] - ov16_ram
        h2_curr = bytes(ov16.data[h2_off : h2_off + len(cfg["hook2_expected"])])
        if h2_curr != cfg["hook2_expected"]:
            raise RuntimeError(
                f"Hook 2 mismatch at 0x{cfg['hook2_addr']:08X}! Expected {cfg['hook2_expected'].hex()}, got {h2_curr.hex()}"
            )

        # 2. Append custom code at the end of Overlay 16
        custom_base_addr = ov16_ram + orig_size
        code_bytes, hook1_fn, hook2_fn = self.generate_custom_code(cfg, custom_base_addr)

        # Pad custom code to 512 bytes for alignment
        padding = (512 - (len(code_bytes) % 512)) % 512
        new_data = bytes(ov16.data) + code_bytes + (b"\x00" * padding)
        new_size = len(new_data)

        # 3. Assemble hooks
        hook1_code = f"""
bl {hex(hook1_fn)}
nop
"""
        hook1_bytes = self.asm.assemble_thumb(hook1_code, cfg["hook1_addr"])
        assert len(hook1_bytes) == len(cfg["hook1_expected"])

        hook2_code = f"""
add r0, sp, #0
bl {hex(hook2_fn)}
nop
"""
        hook2_bytes = self.asm.assemble_thumb(hook2_code, cfg["hook2_addr"])
        assert len(hook2_bytes) == len(cfg["hook2_expected"])

        # 4. Patch hooks into overlay data
        patched_data = bytearray(new_data)
        patched_data[h1_off : h1_off + len(hook1_bytes)] = hook1_bytes
        patched_data[h2_off : h2_off + len(hook2_bytes)] = hook2_bytes

        # 5. Save updated overlay to ROM
        rom_handler.update_arm9_overlay(
            cfg["overlay_id"], ov16, patched_data, new_ram_size=new_size
        )
        return True
