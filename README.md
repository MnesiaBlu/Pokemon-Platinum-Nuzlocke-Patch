# Pokémon Platinum Nuzlocke Patcher

A modular Python toolkit to generate a patched ROM of **Pokémon Platinum Version (Italian - CPUI)** with standard Nuzlocke challenge rules enforced directly at the game engine level.

> [!NOTE]
> This repository strictly contains the source code for the **patcher** tool and ARM/Thumb assembly hooks. No copyrighted ROM files or Nintendo assets are distributed or tracked within this Git repository.

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
Enforces the quintessential Nuzlocke rule: players may only capture one Pokémon per route or area.
- Whenever the player throws any Poké Ball at a wild Pokémon:
  - The game scans the **Party** and all **PC Boxes** to verify if any existing Pokémon shares the same met location (`MON_DATA_MET_LOCATION`) as the current route/area (`mapHeader` / `mapLabelTextID`).
  - If a Pokémon from that location is already present (in the party or PC boxes, including gift Pokémon, starters, or fainted graveyard mons), the catch is **blocked**: the Ball shakes 0 times and the wild Pokémon breaks out immediately with the native game message *"Oh no! The Pokémon broke free!"*.
  - Catching tutorial sequences (e.g. Lucas/Dawn on Route 202) and Pal Park transfers are preserved and never blocked.

### 3. Permadeath (`feature/permadeath`)
Enforces permanent faint / death mechanics across all recovery pathways:
- **Revival Items Disabled**:
  - *Revive*, *Max Revive*, *Revival Herb*, and *Sacred Ash* have their revival parameters cleared in the item database (`pl_item_data.narc`).
  - Attempting to use any of these items (in or out of battle) is rejected with the in-game message *"It won't have any effect."*.
  - Using *Rare Candies* on Pokémon with 0 HP is intercepted and blocked in `Party_CheckItemEffectsOnMember`.
- **Faint Preservation at Healing Facilities**:
  - The universal party healing function (`Party_HealAllMembers`), invoked by Nurse Joy, mothers, beds, and overworld doctors, detects party members with 0 HP and skips healing them.
  - Fainted Pokémon remain at 0 HP, with fainted status and unmodified PP, requiring the player to deposit them into a graveyard PC box or release them.
  - In the event of a total party blackout, the player respawns at the Pokémon Center with their fallen team still fainted, ready to deposit them in the PC.

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

---

## Using the Patcher

To apply the patches to your clean Pokémon Platinum ROM:

1. Place your clean ROM into the `Game/` directory (e.g., `Game/3794 - Pokemon - Versione Platino (IT)(EXiMiUS).nds`).
2. Run the patcher:
   ```bash
   python apply_patch.py
   ```
3. When executed in an interactive terminal, the **Interactive Feature Selector** menu appears:
   ```text
   =================================================================
             POKEMON PLATINO - NUZLOCKE FEATURE SELECTOR
   =================================================================
   Seleziona le funzionalita da includere nella patch:

     [X] 1. Level Cap Dinamico
     [X] 2. First Encounter Only
     [X] 3. Permadeath Completo
     [X] 4. Starter da Trainer ID

   Comandi:
     - Digita il numero (1-4) per attivare/disattivare
     - 'a' per attivare tutte | 'n' per disattivare tutte
     - Premi INVIO per confermare e procedere con il patch
     - 'q' per uscire senza applicare
   ```
   You can type e.g. `1` to toggle off the Level Cap (showing `[ ]`), or simply press **Enter** to proceed with all features enabled!

4. The patched ROM will be saved automatically to `out/Pokemon_Platino_Nuzlocke.nds`.

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
