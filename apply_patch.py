#!/usr/bin/env python3
"""Pokemon Platinum Nuzlocke Patcher CLI.

Applies configurable Nuzlocke feature patches to a clean Pokemon Platinum ROM.
"""

import argparse
import sys
from pathlib import Path

from patcher.rom import RomHandler
from patcher.patches import (
    LevelCapPatch,
    FirstEncounterPatch,
    PermadeathPatch,
    StarterByTidPatch,
)


AVAILABLE_PATCHES = {
    "level-cap": LevelCapPatch,
    "first-encounter": FirstEncounterPatch,
    "permadeath": PermadeathPatch,
    "starter-by-tid": StarterByTidPatch,
}



def find_default_rom() -> Path | None:
    """Look for an .nds ROM in Game/ directory."""
    game_dir = Path("Game")
    if game_dir.is_dir():
        nds_files = list(game_dir.glob("*.nds"))
        if nds_files:
            return nds_files[0]
    return None


def main():
    parser = argparse.ArgumentParser(
        description="Pokemon Platinum Nuzlocke Patcher",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--rom",
        type=str,
        help="Path to clean Pokemon Platinum NDS ROM. Defaults to ROM found in Game/ directory.",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default="out/Pokemon_Platino_Nuzlocke.nds",
        help="Path where the patched ROM will be saved (default: out/Pokemon_Platino_Nuzlocke.nds)",
    )
    parser.add_argument(
        "--features",
        nargs="+",
        choices=list(AVAILABLE_PATCHES.keys()) + ["all"],
        default=["all"],
        help="Select features to patch (default: all available features)",
    )
    parser.add_argument(
        "--info",
        action="store_true",
        help="Show ROM details and hash verification, then exit.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Verify ROM and patch applicability without writing output file.",
    )

    args = parser.parse_args()

    # Determine ROM path
    rom_path = Path(args.rom) if args.rom else find_default_rom()
    if not rom_path or not rom_path.exists():
        print("Error: No ROM found. Specify with --rom <path/to/rom.nds> or place it in Game/.")
        sys.exit(1)

    print(f"Loading ROM: {rom_path} ...")
    try:
        handler = RomHandler(rom_path)
    except Exception as e:
        print(f"Failed to load ROM: {e}")
        sys.exit(1)

    info = handler.verify()
    print("-" * 50)
    print(f"Game: {info['game_name']} [{info['game_code']}]")
    print(f"Size: {info['size']} bytes")
    print(f"MD5:  {info['md5']}")
    print(f"SHA1: {info['sha1']}")
    print("-" * 50)

    if not info["supported"]:
        print(f"Warning: Game code '{info['game_code']}' is not officially supported.")

    if args.info:
        sys.exit(0)

    # Determine patches to apply
    selected_keys = (
        list(AVAILABLE_PATCHES.keys()) if "all" in args.features else args.features
    )

    patches_to_apply = [AVAILABLE_PATCHES[k]() for k in selected_keys]
    print(f"Selected features to patch: {', '.join(p.name for p in patches_to_apply)}")

    for patch in patches_to_apply:
        print(f"Applying patch: {patch.name} ...")
        try:
            patch.apply(handler)
            print(f"  -> {patch.name} applied successfully!")
        except Exception as e:
            print(f"  -> Failed to apply {patch.name}: {e}")
            sys.exit(1)

    if args.dry_run:
        print("\nDry-run completed successfully! (No output file written)")
        sys.exit(0)

    output_path = Path(args.output)
    print(f"\nSaving patched ROM to: {output_path} ...")
    try:
        handler.save(output_path)
        print(f"Patched ROM saved successfully! ({output_path.stat().st_size} bytes)")
    except Exception as e:
        print(f"Failed to save patched ROM: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
