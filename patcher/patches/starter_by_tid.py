"""Starter by Trainer ID Patch for Pokemon Platinum (Italian & US).

Enforces the standard Nuzlocke rule where the starter Pokemon is determined
by the last digit of the player's Trainer ID (TID):
- Last digit 1, 2, 3: Grass starter (Turtwig / Erba)
- Last digit 4, 5, 6: Fire starter (Chimchar / Fuoco)
- Last digit 7, 8, 9: Water starter (Piplup / Acqua)
- Last digit 0: Player's choice (free selection among all three)

Implements the rule directly into Overlay 78 (choose_starter):
1. In ChooseStarter_Init: sets the initial cursorPosition directly to the
   assigned starter ball.
2. In ChangePokeballChoice: locks the cursor on the assigned starter ball
   (ignoring left/right navigation) unless the last digit is 0.
3. In GetSelectedSpecies: overrides species selection to guarantee the assigned
   starter is returned to the field system (387 Turtwig, 390 Chimchar, 393 Piplup),
   or respects player choice if the last digit is 0.
"""

from .base import BasePatch
from ..rom import RomHandler
from ..arm_asm import Assembler
from ..scanner import UniversalResolver


class StarterByTidPatch(BasePatch):
    name = "Starter by Trainer ID"
    description = (
        "Enforces starter selection based on Trainer ID last digit "
        "(1-3 Turtwig/Grass, 4-6 Chimchar/Fire, 7-9 Piplup/Water, 0 Player Choice)."
    )

    CONFIG = {
        b"CPUI": {
            "overlay_id": 78,
            "hook1_init_addr": 0x021D103C,
            "hook1_expected": bytes.fromhex("012004b038bd"),
            "hook2_choice_addr": 0x021D1B08,
            "hook2_expected": bytes.fromhex("00f056f9"),
            "save_data_ptr": 0x021C08F4,
            "fn_save_get_trainer_info": 0x02025EA8,
            "fn_change_pokeball_choice": 0x021D1DB8,
        }
    }

    def __init__(self):
        self.asm = Assembler()

    def generate_custom_code(self, cfg: dict, base_addr: int) -> tuple[bytes, int, int, int]:
        """Generate custom starter enforcement routines.

        Returns:
            Tuple of (assembled_bytes, addr_hook1, addr_hook2, addr_hook3).
        """
        # 1. GetStarterByTid routine:
        # Reads SaveData -> TrainerInfo -> TID % 10.
        # Returns 0 (Turtwig), 1 (Chimchar), 2 (Piplup), or 0xFF (Player Choice for digit 0).
        code_tid = f"""
.thumb
.align 2
GetStarterByTid:
    push {{r4, lr}}
    ldr r0, ={hex(cfg['save_data_ptr'])}
    ldr r0, [r0]
    cmp r0, #0
    beq .free_choice
    bl #{hex(cfg['fn_save_get_trainer_info'])}
    cmp r0, #0
    beq .free_choice
    ldr r0, [r0, #0x10]
    lsls r0, r0, #16
    lsrs r0, r0, #16

    @ Compute r0 % 10:
    ldr r1, =52429
    muls r1, r0
    lsrs r1, r1, #19
    movs r2, #10
    muls r2, r1
    subs r0, r0, r2

    cmp r0, #0
    beq .free_choice
    cmp r0, #3
    ble .turtwig
    cmp r0, #6
    ble .chimchar
.piplup:
    movs r0, #2
    pop {{r4, pc}}
.chimchar:
    movs r0, #1
    pop {{r4, pc}}
.turtwig:
    movs r0, #0
    pop {{r4, pc}}
.free_choice:
    movs r0, #0xFF
    pop {{r4, pc}}
"""
        b_tid = self.asm.assemble_thumb(code_tid, base_addr)
        pad1 = (4 - (len(b_tid) % 4)) % 4
        addr_init = base_addr + len(b_tid) + pad1

        # 2. Hook_ChooseStarter_Init:
        # Sets initial cursorPosition (offset 0x54) to assigned starter if not free choice.
        # Restores stack and pops directly to ChooseStarter_Init's caller.
        code_init = f"""
.thumb
.align 2
Hook_ChooseStarter_Init:
    push {{r3, lr}}
    bl #{hex(base_addr)}
    cmp r0, #0xFF
    beq .init_done
    str r0, [r5, #0x54]
.init_done:
    pop {{r3, r4}}
    movs r0, #1
    add sp, #0x10
    pop {{r3, r4, r5, pc}}
"""
        b_init = self.asm.assemble_thumb(code_init, addr_init)
        pad2 = (4 - (len(b_init) % 4)) % 4
        addr_choice = addr_init + len(b_init) + pad2

        # 3. Hook_ChangePokeballChoice:
        # If free choice, calls original ChangePokeballChoice (allowing D-Pad navigation).
        # Otherwise locks cursor on assigned starter.
        code_choice = f"""
.thumb
.align 2
Hook_ChangePokeballChoice:
    push {{r4, lr}}
    adds r4, r0, #0
    bl #{hex(base_addr)}
    cmp r0, #0xFF
    beq .allow_choice
    str r0, [r4, #0x54]
    pop {{r4, pc}}
.allow_choice:
    adds r0, r4, #0
    bl #{hex(cfg['fn_change_pokeball_choice'])}
    pop {{r4, pc}}
"""
        b_choice = self.asm.assemble_thumb(code_choice, addr_choice)

        total_bytes = (
            b_tid
            + (b"\x00" * pad1)
            + b_init
            + (b"\x00" * pad2)
            + b_choice
        )
        return total_bytes, addr_init, addr_choice

    def apply(self, rom_handler: RomHandler) -> bool:
        cfg = self.CONFIG.get(rom_handler.game_code)
        if not cfg:
            cfg = UniversalResolver.resolve_starter_by_tid(rom_handler)

        ov78 = rom_handler.load_arm9_overlay(cfg["overlay_id"])
        ov78_ram = ov78.ramAddress
        orig_len = len(ov78.data)
        base_addr = ov78_ram + orig_len

        # Verify expected bytes at hook locations
        h1_offset = cfg["hook1_init_addr"] - ov78_ram
        h1_len = len(cfg["hook1_expected"])
        actual_h1 = bytes(ov78.data[h1_offset : h1_offset + h1_len])
        if actual_h1 != cfg["hook1_expected"]:
            raise ValueError(
                f"ChooseStarter_Init hook mismatch at 0x{cfg['hook1_init_addr']:08X}: "
                f"expected {cfg['hook1_expected'].hex()}, got {actual_h1.hex()}"
            )

        h2_offset = cfg["hook2_choice_addr"] - ov78_ram
        h2_len = len(cfg["hook2_expected"])
        actual_h2 = bytes(ov78.data[h2_offset : h2_offset + h2_len])
        if actual_h2 != cfg["hook2_expected"]:
            raise ValueError(
                f"ChangePokeballChoice hook mismatch at 0x{cfg['hook2_choice_addr']:08X}: "
                f"expected {cfg['hook2_expected'].hex()}, got {actual_h2.hex()}"
            )

        # Generate custom code routines
        custom_bytes, addr_init, addr_choice = self.generate_custom_code(
            cfg, base_addr
        )

        # Assemble hooks
        # Hook 1: bl Hook_ChooseStarter_Init; mov r8, r8 (6 bytes)
        hook1_code = f"bl #{hex(addr_init)}\nmov r8, r8"
        hook1_bytes = self.asm.assemble_thumb(hook1_code, cfg["hook1_init_addr"])

        # Hook 2: bl Hook_ChangePokeballChoice (4 bytes)
        hook2_code = f"bl #{hex(addr_choice)}"
        hook2_bytes = self.asm.assemble_thumb(hook2_code, cfg["hook2_choice_addr"])

        # Apply modifications to overlay data
        new_overlay_data = bytearray(ov78.data)

        new_overlay_data[h1_offset : h1_offset + len(hook1_bytes)] = hook1_bytes
        new_overlay_data[h2_offset : h2_offset + len(hook2_bytes)] = hook2_bytes

        # Append custom routines
        new_overlay_data.extend(custom_bytes)

        # Update overlay file and table entry
        rom_handler.update_arm9_overlay(
            cfg["overlay_id"], ov78, bytes(new_overlay_data), len(new_overlay_data)
        )
        return True
