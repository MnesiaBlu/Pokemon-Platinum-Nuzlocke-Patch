"""ARM and Thumb assembly helper using Keystone."""

import re

import keystone

_THUMB_NOP_RE = re.compile(r"\bnop\b", re.IGNORECASE)


class Assembler:
    def __init__(self):
        self._ks_thumb = keystone.Ks(keystone.KS_ARCH_ARM, keystone.KS_MODE_THUMB)
        self._ks_arm = keystone.Ks(keystone.KS_ARCH_ARM, keystone.KS_MODE_ARM)

    def assemble_thumb(self, code: str, base_addr: int = 0) -> bytes:
        """Assemble Thumb assembly instructions into raw bytes.

        Keystone encodes `nop` as the Thumb-2 hint 0xBF00, which is an undefined
        instruction on the DS ARM946E-S (ARMv5TE, Thumb-1 only). Rewrite it to the
        Thumb-1 idiom `mov r8, r8` (0x46C0).
        """
        code = _THUMB_NOP_RE.sub("mov r8, r8", code)
        encoding, _ = self._ks_thumb.asm(code, base_addr)
        return bytes(encoding)

    def assemble_arm(self, code: str, base_addr: int = 0) -> bytes:
        """Assemble ARM 32-bit assembly instructions into raw bytes."""
        encoding, _ = self._ks_arm.asm(code, base_addr)
        return bytes(encoding)
