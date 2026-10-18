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

Runtime layout (CPUI):
- Overlay 16 is patched strictly in-place (size stays 0x35AA0), with two BLs
  into ARM9:
    Hook 1 @ 0x02249184  `cmp r0, #100; bne` -> `bl CheckLevelCapHook`
        The following `b 0x02249296` (skip EXP) at 0x02249188 is left intact:
        it is also the target of the "mon has 0 HP" branch at 0x02249178.
        The hook returns to it when level >= cap, or past it otherwise.
    Hook 2 @ 0x02249242  `newExp = exp + gained` -> `mov r0, sp; bl ClampExpHook; mov r8, r8`
        Returns with r2 = new EXP, which the overlay stores into the
        BattleMon at 0x0224925E.
- ARM9 routines live in unused tails of 0xB4-byte template records
  (0x020F3xxx), the same family of slots used by the other patches.
  Every write is checked to land on bytes that are zero in the clean ROM.
"""

from .base import BasePatch
from ..rom import RomHandler
from ..arm_asm import Assembler
from ..scanner import UniversalResolver


# Level cap indexed by number of badges owned (0..8).
LEVEL_CAPS = (14, 22, 26, 32, 37, 41, 44, 50, 62)

# TrainerInfo / BattleSystem field offsets (verified on CPUI: see
# BattleSystem_TrainerInfo @ 0x0223E2CC, TrainerInfo_HasBadge @ 0x02025FA4,
# TrainerInfo_HasBeatenGame @ 0x02026060).
BATTLESYS_TRAINER_INFO = 0x48
TRAINER_INFO_BADGES = 0x1A
TRAINER_INFO_FLAGS = 0x1D  # bit 0 = main story cleared


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
            # cmp r0, #100 ; bne +0 ; b 0x02249296 (only the first 4 bytes are replaced)
            "hook1_expected": bytes.fromhex("642800d185e0"),
            "hook2_addr": 0x02249242,
            "hook2_expected": bytes.fromhex("13990e980a181392"),
            "fn_pokemon_get_value": 0x02074510,
            "fn_species_get_exp_at_level": 0x02075B70,
            "get_cap_free_space_addr": 0x020F3D78,
            "check_cap_free_space_addr": 0x020F3800,
            "clamp_exp_free_space_addr": 0x020F3E50,
        }
    }

    # Bytes available at each free-space slot (zero tails of the template records).
    FREE_SPACE_LIMITS = {
        "get_cap_free_space_addr": 0x70,
        "check_cap_free_space_addr": 0x48,
        "clamp_exp_free_space_addr": 0x4C,
    }

    HOOK1_PATCH_LEN = 4

    def __init__(self):
        self.asm = Assembler()

    def _assemble_get_cap(self, base: int) -> bytes:
        """GetLevelCap(BattleSystem *r0) -> r0 = cap. Leaf, clobbers r0-r3 only.

        Reads the player's TrainerInfo directly from the BattleSystem (no
        SaveData access, no heap, no calls) and maps badge count -> cap.
        """
        def build(table_addr: int) -> bytes:
            return self.asm.assemble_thumb(f"""
    ldr  r0, [r0, #{BATTLESYS_TRAINER_INFO:#x}]
    cmp  r0, #0
    beq  .nocap
    ldrb r1, [r0, #{TRAINER_INFO_FLAGS:#x}]
    lsls r1, r1, #31
    bne  .nocap
    ldrb r1, [r0, #{TRAINER_INFO_BADGES:#x}]
    movs r2, #0
.count:
    cmp  r1, #0
    beq  .lookup
    subs r3, r1, #1
    ands r1, r3
    adds r2, #1
    b    .count
.lookup:
    ldr  r0, ={table_addr:#x}
    ldrb r0, [r0, r2]
    bx   lr
.nocap:
    movs r0, #100
    bx   lr
""", base)

        # Literal size does not depend on its value: first pass gives the length.
        code_len = len(build(base))
        table_addr = base + ((code_len + 3) & ~3)
        code = build(table_addr)
        assert len(code) == code_len
        return code.ljust(table_addr - base, b"\x00") + bytes(LEVEL_CAPS)

    def _assemble_check_cap(self, base: int, get_cap_addr: int) -> bytes:
        """Hook 1 body. In: r0 = current level, r4 = EXP task data, lr = 0x02249189.

        level >= cap -> return to lr (the original `b skip_exp`)
        level <  cap -> return to lr + 2 (normal EXP calculation)
        """
        return self.asm.assemble_thumb(f"""
    push {{r0, lr}}
    ldr  r0, [r4, #0]
    bl   #{get_cap_addr:#x}
    pop  {{r1, r2}}
    cmp  r1, r0
    bhs  .at_cap
    adds r2, #2
.at_cap:
    bx   r2
""", base)

    def _assemble_clamp_exp(self, base: int, get_cap_addr: int, cfg: dict) -> bytes:
        """Hook 2 body. In: r0 = caller sp, r4 = EXP task data, r6 = Pokemon*.

        Caller frame: [sp+0x4C] = current EXP, [sp+0x38] = EXP gained.
        Out: [sp+0x4C] = r2 = new EXP, [sp+0x38] = gained (clamped).
        Six registers are pushed so sp stays 8-byte aligned for the callees.
        """
        return self.asm.assemble_thumb(f"""
    push {{r3, r4, r5, r6, r7, lr}}
    adds r7, r0, #0
    ldr  r5, [r7, #0x4c]
    ldr  r0, [r4, #0]
    bl   #{get_cap_addr:#x}
    cmp  r0, #100
    bhs  .no_clamp
    adds r4, r0, #0
    adds r0, r6, #0
    movs r1, #5
    movs r2, #0
    ldr  r3, ={cfg['fn_pokemon_get_value'] | 1:#x}
    blx  r3
    adds r1, r4, #0
    ldr  r3, ={cfg['fn_species_get_exp_at_level'] | 1:#x}
    blx  r3
    ldr  r1, [r7, #0x38]
    adds r2, r5, r1
    cmp  r2, r0
    bls  .store
    cmp  r5, r0
    bhs  .no_gain
    subs r1, r0, r5
    adds r2, r0, #0
    b    .store_gain
.no_gain:
    movs r1, #0
    adds r2, r5, #0
.store_gain:
    str  r1, [r7, #0x38]
    b    .store
.no_clamp:
    ldr  r1, [r7, #0x38]
    adds r2, r5, r1
.store:
    str  r2, [r7, #0x4c]
    pop  {{r3, r4, r5, r6, r7, pc}}
""", base)

    def generate_custom_code(self, cfg: dict) -> tuple[bytes, bytes, bytes]:
        """Generate GetLevelCap, CheckLevelCapHook, and ClampExpHook for ARM9."""
        get_cap_addr = cfg["get_cap_free_space_addr"]
        b_get_cap = self._assemble_get_cap(get_cap_addr)
        b_check_cap = self._assemble_check_cap(cfg["check_cap_free_space_addr"], get_cap_addr)
        b_clamp_exp = self._assemble_clamp_exp(cfg["clamp_exp_free_space_addr"], get_cap_addr, cfg)
        return b_get_cap, b_check_cap, b_clamp_exp

    def _write_free_space(self, arm9: bytearray, arm9_ram: int, key: str, addr: int, code: bytes):
        limit = self.FREE_SPACE_LIMITS.get(key)
        if limit is not None and len(code) > limit:
            raise RuntimeError(
                f"{key}: routine is {len(code):#x} bytes, slot at 0x{addr:08X} holds {limit:#x}"
            )
        off = addr - arm9_ram
        current = bytes(arm9[off : off + len(code)])
        if current != code and any(current):
            raise RuntimeError(
                f"{key}: ARM9 free space at 0x{addr:08X} is not empty, refusing to overwrite game data"
            )
        arm9[off : off + len(code)] = code

    def apply(self, rom_handler: RomHandler) -> bool:
        cfg = self.CONFIG.get(rom_handler.game_code)
        if not cfg:
            cfg = UniversalResolver.resolve_level_cap(rom_handler)

        ov16 = rom_handler.load_arm9_overlay(cfg["overlay_id"])
        ov16_ram = ov16.ramAddress
        orig_len = len(ov16.data)
        arm9 = bytearray(rom_handler.rom.arm9)
        arm9_ram = rom_handler.rom.arm9RamAddress

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

        # 2. Write custom code to ARM9 free space
        b_get_cap, b_check_cap, b_clamp_exp = self.generate_custom_code(cfg)
        for key, code in (
            ("get_cap_free_space_addr", b_get_cap),
            ("check_cap_free_space_addr", b_check_cap),
            ("clamp_exp_free_space_addr", b_clamp_exp),
        ):
            self._write_free_space(arm9, arm9_ram, key, cfg[key], code)
        rom_handler.rom.arm9 = bytes(arm9)

        # 3. Assemble hooks in Overlay 16
        hook1_bytes = self.asm.assemble_thumb(
            f"bl #{cfg['check_cap_free_space_addr']:#x}", cfg["hook1_addr"]
        )
        assert len(hook1_bytes) == self.HOOK1_PATCH_LEN

        hook2_code = f"""
mov r0, sp
bl #{cfg['clamp_exp_free_space_addr']:#x}
mov r8, r8
"""
        hook2_bytes = self.asm.assemble_thumb(hook2_code, cfg["hook2_addr"])
        assert len(hook2_bytes) == len(cfg["hook2_expected"])

        # 4. Patch hooks into overlay data (in-place, NO overlay expansion)
        patched_data = bytearray(ov16.data)
        patched_data[h1_off : h1_off + len(hook1_bytes)] = hook1_bytes
        patched_data[h2_off : h2_off + len(hook2_bytes)] = hook2_bytes
        assert len(patched_data) == orig_len

        # 5. Save updated overlay to ROM preserving exact original ramSize
        rom_handler.update_arm9_overlay(cfg["overlay_id"], ov16, patched_data)
        return True
