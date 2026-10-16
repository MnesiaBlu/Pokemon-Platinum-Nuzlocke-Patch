"""ARM and Thumb assembly helper using Keystone."""

import keystone


class Assembler:
    def __init__(self):
        self._ks_thumb = keystone.Ks(keystone.KS_ARCH_ARM, keystone.KS_MODE_THUMB)
        self._ks_arm = keystone.Ks(keystone.KS_ARCH_ARM, keystone.KS_MODE_ARM)

    def assemble_thumb(self, code: str, base_addr: int = 0) -> bytes:
        """Assemble Thumb assembly instructions into raw bytes."""
        encoding, _ = self._ks_thumb.asm(code, base_addr)
        return bytes(encoding)

    def assemble_arm(self, code: str, base_addr: int = 0) -> bytes:
        """Assemble ARM 32-bit assembly instructions into raw bytes."""
        encoding, _ = self._ks_arm.asm(code, base_addr)
        return bytes(encoding)
