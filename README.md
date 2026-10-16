# Pokémon Platino Nuzlocke Patcher

Toolkit modulare in Python per generare una ROM modificata di **Pokémon Versione Platino (Italiano - CPUI)** con le regole standard della sfida Nuzlocke applicate a livello di engine di gioco.

> [!NOTE]
> Questo repository include esclusivamente il codice sorgente del **patcher** e le definizioni di patch/hook in assembly ARM/Thumb. Nessuna ROM o asset protetto da copyright è distribuito o tracciato nel repository Git.

---

## Requisiti

- **Python 3.10+**
- Dipendenze (installabili con `pip`):
  ```bash
  pip install -r requirements.txt
  ```
  Le librerie utilizzate sono:
  - [`ndspy`](https://github.com/RoadrunnerW/ndspy): disassemblaggio, manipolazione e repack della ROM NDS e dei suoi overlay/file system.
  - [`keystone-engine`](https://www.keystone-engine.org/): assemblaggio al volo del codice ARM/Thumb.
  - [`capstone`](https://www.capstone-engine.org/): disassemblaggio e verifica delle istruzioni di memoria.

---

## Funzionalità

### 1. Level Cap Dinamico (`feature/level-cap`)
Impedisce ai Pokémon della squadra di superare il livello del Pokémon più forte del prossimo Capopalestra o della Lega Pokémon:
- **1ª Medaglia (Pedro / Mineraria):** Livello massimo **14** *(Cranidos)*
- **2ª Medaglia (Gardenia / Bosco):** Livello massimo **22** *(Roserade)*
- **3ª Medaglia (Fannie / Vestigia):** Livello massimo **26** *(Mismagius)*
- **4ª Medaglia (Marzia / Ciottolo):** Livello massimo **32** *(Lucario)*
- **5ª Medaglia (Omar / Pantano):** Livello massimo **37** *(Floatzel)*
- **6ª Medaglia (Ferruccio / Cava):** Livello massimo **41** *(Bastiodon)*
- **7ª Medaglia (Bianca / Ghiacciolo):** Livello massimo **44** *(Froslass)*
- **8ª Medaglia (Corrado / Faro):** Livello massimo **50** *(Electivire)*
- **Lega Pokémon (Campionessa Camilla):** Livello massimo **62** *(Garchomp)*
- **Post-Lega (Storia principale completata):** Cap sbloccato a **100**

#### Come funziona tecnicamente:
1. All'inizio dell'assegnazione dell'esperienza in battaglia (`BattleScript_GetExpTask`), viene controllato il livello del Pokémon rispetto al cap calcolato dinamicamente in base alle medaglie salvate nel `TrainerInfo`. Se il Pokémon è già al cap o superiore, l'EXP guadagnata è pari a 0 e il ciclo viene saltato immediatamente.
2. Se un Pokémon è sotto il cap ma l'esperienza vinta lo farebbe salire oltre il livello consentito, l'esperienza viene troncata esattamente alla soglia necessaria per raggiungere il livello cap con 0 punti in eccesso.

### 2. Primo Incontro per Percorso (`feature/first-encounter`)
Impone la regola classica del Nuzlocke: è possibile catturare un solo Pokémon per percorso/area.
- Quando il giocatore tenta di lanciare una Poké Ball su un Pokémon selvatico:
  - Il gioco scansiona la **Squadra** (Party) e tutti i **Box del PC** alla ricerca di un Pokémon il cui luogo di cattura (`MON_DATA_MET_LOCATION`) coincida con l'area attuale (`mapHeader` / `mapLabelTextID`).
  - Se un Pokémon di quell'area è già presente (in squadra o nei box, inclusi starter, Pokémon dono o Pokémon svenuti nel box cimitero), la cattura viene **bloccata**: la Ball effettua 0 oscillazioni e il Pokémon selvatico si libera immediatamente con il messaggio nativo *"Oh no! Il Pokémon si è liberato!"*.
  - La cattura guidata del tutorial (Lucas/Dawn sul Percorso 202) e il Parco Amici sono preservati e non vengono bloccati.


---

## Utilizzo del Patcher

Per applicare le modifiche alla tua ROM pulita di Pokémon Platino:

1. Inserisci la ROM originale nella cartella `Game/` (es. `Game/3794 - Pokemon - Versione Platino (IT)(EXiMiUS).nds`).
2. Esegui il comando:
   ```bash
   python apply_patch.py
   ```
3. La ROM patchata verrà generata automaticamente nella cartella `out/Pokemon_Platino_Nuzlocke.nds`.

### Opzioni avanzate della CLI:
```bash
# Mostra informazioni e verifica hash della ROM pulita
python apply_patch.py --info

# Modalità test senza scrivere il file di output
python apply_patch.py --dry-run

# Specificare percorsi personalizzati
python apply_patch.py --rom "percorso/alla/tua/rom.nds" --output "percorso/output.nds"

# Selezionare specifiche feature
python apply_patch.py --features level-cap
```

---

## Esecuzione dei Test

Per verificare l'integrità delle patch e dei file generati:
```bash
python -m unittest discover tests
```
