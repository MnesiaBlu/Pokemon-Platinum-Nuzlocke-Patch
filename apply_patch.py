#!/usr/bin/env python3
"""Pokemon Platinum Nuzlocke Patcher CLI.

Applies configurable Nuzlocke feature patches to a clean Pokemon Platinum ROM.
Features can be selected interactively or specified via command-line arguments.
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

FEATURE_DETAILS = {
    "level-cap": {
        "title": "Dynamic Level Cap",
        "desc": "Pokemon cannot exceed the level of the upcoming Gym Leader/Champion's ace",
    },
    "first-encounter": {
        "title": "First Encounter Only",
        "desc": "Blocks catching wild Pokemon on routes/areas where a Pokemon was already caught",
    },
    "permadeath": {
        "title": "Complete Permadeath",
        "desc": "Fainted Pokemon cannot be revived by items or healed at Pokemon Centers",
    },
    "starter-by-tid": {
        "title": "Starter by Trainer ID",
        "desc": "Starter determined by Trainer ID last digit (1-3 Grass, 4-6 Fire, 7-9 Water, 0 Player Choice)",
    },
}


def find_default_rom() -> Path | None:
    """Look for an .nds ROM in Game/ directory."""
    game_dir = Path("Game")
    if game_dir.is_dir():
        nds_files = list(game_dir.glob("*.nds"))
        if nds_files:
            return nds_files[0]
    return None


def interactive_feature_selector(available_patches: dict[str, type]) -> list[str]:
    """Interactive console menu to toggle features on or off before patching."""
    keys = list(available_patches.keys())
    enabled = {k: True for k in keys}

    while True:
        print("\n" + "=" * 65)
        print("          POKEMON PLATINUM - NUZLOCKE FEATURE SELECTOR")
        print("=" * 65)
        print("Select features to include in the patch:\n")

        for idx, key in enumerate(keys, 1):
            status = "[X]" if enabled[key] else "[ ]"
            info = FEATURE_DETAILS.get(key, {})
            title = info.get("title", key)
            desc = info.get("desc", available_patches[key].description)
            print(f"  {status} {idx}. {title}")
            print(f"       {desc}")

        print("\nCommands:")
        print(f"  - Type number (1-{len(keys)}) to toggle feature")
        print("  - 'a' to enable all | 'n' to disable all")
        print("  - Press ENTER to confirm and proceed with patching")
        print("  - 'q' to quit without patching")

        try:
            choice = input("\nChoice > ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\nOperation cancelled.")
            sys.exit(0)

        if choice == "":
            selected = [k for k in keys if enabled[k]]
            if not selected:
                print("\n[!] You must select at least one feature to apply!")
                continue
            return selected
        elif choice == "q":
            print("\nOperation cancelled by user.")
            sys.exit(0)
        elif choice == "a":
            for k in keys:
                enabled[k] = True
        elif choice == "n":
            for k in keys:
                enabled[k] = False
        elif choice.isdigit():
            idx = int(choice)
            if 1 <= idx <= len(keys):
                key = keys[idx - 1]
                enabled[key] = not enabled[key]
            else:
                print(f"\n[!] Invalid option: {choice}")
        else:
            print(f"\n[!] Unrecognized command: '{choice}'")


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
        default="out/Pokemon_Platinum_Nuzlocke.nds",
        help="Path where the patched ROM will be saved (default: out/Pokemon_Platinum_Nuzlocke.nds)",
    )
    parser.add_argument(
        "--features",
        nargs="+",
        choices=list(AVAILABLE_PATCHES.keys()) + ["all"],
        default=None,
        help="Select features to patch (e.g. --features level-cap permadeath). If omitted and running in terminal, opens interactive menu.",
    )
    parser.add_argument(
        "--interactive",
        "-i",
        action="store_true",
        help="Force interactive feature selection menu.",
    )
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Disable interactive menu and apply all features (or those given in --features).",
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

    # Determine features to apply
    should_prompt = args.interactive or (
        args.features is None and not args.non_interactive and sys.stdin.isatty()
    )

    if should_prompt:
        selected_keys = interactive_feature_selector(AVAILABLE_PATCHES)
    elif args.features:
        selected_keys = (
            list(AVAILABLE_PATCHES.keys()) if "all" in args.features else args.features
        )
    else:
        # Default headless / non-interactive: all features
        selected_keys = list(AVAILABLE_PATCHES.keys())

    patches_to_apply = [AVAILABLE_PATCHES[k]() for k in selected_keys]
    print(f"\nSelected features to patch ({len(patches_to_apply)}): {', '.join(p.name for p in patches_to_apply)}")

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
