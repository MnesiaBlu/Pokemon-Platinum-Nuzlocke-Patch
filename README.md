# Pokémon Platinum Nuzlocke Patcher

A modular Python toolkit to generate a patched ROM of **Pokémon Platinum Version** (universal support: Italian `CPUI`, US/English `CPUE`, French `CPUF`, German `CPUD`, Spanish `CPUS`) with standard Nuzlocke challenge rules enforced directly at the game engine level.

> [!NOTE]
> - **AI-Assisted Development**: This project, including its reverse-engineering analysis, ARM/Thumb assembly patches, Python patching scripts, and documentation, was developed with the assistance of Artificial Intelligence (AI).
> - **Legal Notice**: This repository strictly contains the source code for the **patcher** tool and ARM/Thumb assembly hooks. No copyrighted ROM files or Nintendo assets are distributed or tracked within this Git repository.

---

## Requirements

- **Python 3.10+**
- Dependencies (installable via `pip`):
  ```bash
  pip install -r requirements.txt
  ```
  Core libraries used:
  - [`ndspy`](https://github.com/RoadrunnerW/ndspy): Disassembly, manipulation, and repackaging of NDS ROMs, file systems, and overlays.
  - [`keystone-engine`](https://www.keystone-engine.org/): Dynamic on-the-fly ARM/Thumb assembly generation.
  - [`capstone`](https://www.capstone-engine.org/): Disassembly and memory instruction verification.

---

## Features

### 1. Dynamic Level Cap (`feature/level-cap`)
Prevents party Pokémon from exceeding the level of the upcoming Gym Leader's or Pokémon League Champion's ace:
- **1st Badge (Roark / Oreburgh Gym):** Max level **14** *(Cranidos)*
- **2nd Badge (Gardenia / Eterna Gym):** Max level **22** *(Roserade)*
- **3rd Badge (Fantina / Hearthome Gym):** Max level **26** *(Mismagius)*
- **4th Badge (Maylene / Veilstone Gym):** Max level **32** *(Lucario)*
- **5th Badge (Crasher Wake / Pastoria Gym):** Max level **37** *(Floatzel)*
- **6th Badge (Byron / Canalave Gym):** Max level **41** *(Bastiodon)*
- **7th Badge (Candice / Snowpoint Gym):** Max level **44** *(Froslass)*
- **8th Badge (Volkner / Sunyshore Gym):** Max level **50** *(Electivire)*
- **Pokémon League (Champion Cynthia):** Max level **62** *(Garchomp)*
- **Post-Game (Main story completed):** Level cap uncapped to **100**

#### Technical Details:
1. At the beginning of battle experience distribution (`BattleScript_GetExpTask`), the Pokémon's current level is evaluated against the dynamically calculated level cap based on badges stored in `TrainerInfo`. If the Pokémon has reached or exceeded the cap, gained EXP is set to 0 and the loop terminates immediately.
2. If a Pokémon is below the cap but the EXP rewarded would cause it to level up past the cap, the awarded EXP is clamped to the exact threshold needed to reach the cap with 0 excess points.

### 2. First Encounter Only (`feature/first-encounter`)
Enforces the authentic Nuzlocke rule: the very first wild Pokémon encountered on a route or area is the player's **only** chance to catch a Pokémon there.
- **Persistent Route Consumption**:
  - The instant a wild battle starts, the location of the battle (`mapLabelTextID`) is evaluated.
  - If it is the first encounter on that route, it is granted catch authorization. However, that route is **immediately marked as consumed / burned** in the game's persistent save data (`VarsFlags`).
  - If the wild Pokémon faints, escapes, or the player runs away, that route remains burned forever. Any subsequent wild encounters on that route cannot be caught.
- **Poké Ball Clause**:
  - Standard Nuzlocke rules dictate that encounter tracking begins only after the player receives their Pokédex and their initial Poké Balls from Rowan/Dawn (`FLAG_HAS_POKEDEX = 146`). Early forced or wild encounters before Sandgem Town (e.g. Route 201 before receiving Poké Balls) do not consume the route prematurely.
- **Gift / Starter Pokémon Clause**:
  - Before authorizing a catch, the game also verifies if a Pokémon from that location is already owned in the **Party** or **PC Storage Boxes** (e.g. Lake Verity starter, gift Pokémon). If one is already owned, wild catches in that location are blocked.
- **Encounter Behavior on Burned Routes**:
  - Throwing any Poké Ball on a consumed route is blocked: the ball shakes 0 times and breaks out immediately with the native game message *"Oh no! The Pokémon broke free!"*.
  - Catching tutorial sequences (e.g. Lucas/Dawn on Route 202) and Pal Park transfers are preserved and never blocked.

### 3. Permadeath (`feature/permadeath`)
Enforces permanent faint / death mechanics across all recovery pathways:
- **Revival Items Disabled**:
  - *Revive*, *Max Revive*, *Revival Herb*, and *Sacred Ash* have their revival parameters cleared in the item database (`pl_item_data.narc`).
  - Attempting to use any of these items (in or out of battle) is rejected with the in-game message *"It won't have any effect."*.
  - Using *Rare Candies* on Pokémon with 0 HP is intercepted and blocked in `Party_CheckItemEffectsOnMember`.
- **Faint Preservation at Healing Facilities**:
  - The universal party healing function (`Party_HealAllMembers`), invoked by Nurse Joy, mothers, beds, and overworld doctors, detects party members with 0 HP and skips healing them.
  - Fainted Pokémon remain at 0 HP, with fainted status and unmodified PP.
- **Hardcore Game Over on Blackout (Ironman Mode)**:
  - If all Pokémon in the party faint (a total party blackout/whiteout):
    - The blackout handler (`Field_PlayerLostBattle`) is intercepted by `Custom_BlackoutGameOver`.
    - The engine invokes `SaveData_Erase` to completely wipe all 64 sectors of Flash memory (both primary and backup save blocks).
    - The console executes a clean hardware soft reset (`SoftReset`) directly back to the Title Screen.
    - Because the save file has been wiped, the run is permanently over: the Title Screen displays no "Continue" option, only "New Game".

### 4. Starter by Trainer ID (`feature/starter-by-tid`)
Determines the player's mandatory starter Pokémon based on the final digit of their Trainer ID (TID) on the Trainer Card:
- **Last digit 1, 2, 3:** Grass starter (**Turtwig**)
- **Last digit 4, 5, 6:** Fire starter (**Chimchar**)
- **Last digit 7, 8, 9:** Water starter (**Piplup**)
- **Last digit 0:** **Player's choice** (free selection among all three)

#### Technical Details:
1. In the Lake Verity briefcase scene (Overlay 78, `choose_starter`), the cursor is initialized directly on the assigned Poké Ball.
2. D-Pad Left/Right navigation (`ChangePokeballChoice`) is locked to the assigned Poké Ball if the digit is 1–9, preventing the player from scrolling to another starter.
3. At the confirmation dialog and exit routine (`GetSelectedSpecies` / `ChooseStarter_Exit`), the species is strictly returned according to the TID (Turtwig: 387, Chimchar: 390, Piplup: 393), keeping the dialogue, delivery, Starly battle, and rival Barry's team perfectly synchronized.

### 5. Universal Pattern Scanner (`feature/universal-pattern-scanner`)
Provides dynamic hook and symbol resolution across different game revisions and language releases of Pokémon Platinum (`CPUI`, `CPUE`, `CPUF`, `CPUD`, `CPUS`, etc.):
- **Dynamic Pattern Matching**: Scans binary code in ARM9 and code overlays (`overlay_0016`, `overlay_0078`) using fuzzy wildcard signatures rather than rigid hardcoded offsets.
- **Instruction Branch Disassembly**: Automatically decodes ARM/Thumb branch instructions (`BL` and `B`) to locate target subroutines (`Party_GetCurrentCount`, `ChangePokeballChoice`, `Battle_CalcCatchShakes`).
- **Zero Configuration Needed**: Run the patcher on any standard Platinum ROM — the scanner automatically identifies memory addresses, literal pool pointers, and overlay structures.

---

## Using the Patcher

To apply the patches to your clean Pokémon Platinum ROM:

1. Place your clean ROM into the `Game/` directory (e.g., `Game/3794 - Pokemon - Versione Platino (IT)(EXiMiUS).nds` or an English/US `CPUE` ROM).
2. Run the patcher:
   ```bash
   python apply_patch.py
   ```
3. When executed in an interactive terminal, the **Interactive Feature Selector** menu appears:
   ```text
   =================================================================
             POKEMON PLATINUM - NUZLOCKE FEATURE SELECTOR
   =================================================================
   Select features to include in the patch:

     [X] 1. Dynamic Level Cap
          Pokemon cannot exceed the level of the upcoming Gym Leader/Champion's ace
     [X] 2. First Encounter Only
          Exactly one catch chance per route; fleeing or defeating it permanently burns the route
     [X] 3. Permadeath & Hardcore Game Over
          Fainted Pokemon cannot be revived; blacking out erases save file (Game Over)
     [X] 4. Starter by Trainer ID
          Starter determined by Trainer ID last digit (1-3 Grass, 4-6 Fire, 7-9 Water, 0 Player Choice)

   Commands:
     - Type number (1-4) to toggle feature
     - 'a' to enable all | 'n' to disable all
     - Press ENTER to confirm and proceed with patching
     - 'q' to quit without patching
   ```
   You can type e.g. `1` to toggle off the Level Cap (showing `[ ]`), or simply press **Enter** to proceed with all features enabled!

4. The patched ROM will be saved automatically to `out/Pokemon_Platinum_Nuzlocke.nds`.

### Advanced CLI Options:
```bash
# View ROM info and verify MD5/SHA1 hashes
python apply_patch.py --info

# Perform a dry-run without writing output files
python apply_patch.py --dry-run

# Force interactive selection menu
python apply_patch.py -i

# Non-interactive / headless mode (applies all features)
python apply_patch.py --non-interactive

# Specify custom features directly from the command line
python apply_patch.py --features level-cap permadeath starter-by-tid

# Custom input/output paths
python apply_patch.py --rom "path/to/rom.nds" --output "path/to/output.nds"
```

---

## Running Unit Tests

To verify patch integrity and ROM modifications:
```bash
python -m unittest discover tests
```

---

## Disclaimer

- **AI-Assisted Project**: This project was designed and developed with the assistance of Artificial Intelligence (AI) for reverse-engineering research, assembly patch engineering, test suite implementation, and documentation.
- **Trademarks & Copyrights**: Pokémon and Nintendo DS are registered trademarks and copyrights of Nintendo, Creatures Inc., and GAME FREAK inc. This repository is an unofficial, non-commercial fan-made project created solely for research and personal entertainment purposes.

---

## License

This project is licensed under the [MIT License](LICENSE).


