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

### 3. Permadeath (`feature/permadeath`)
Implementa la regola fondamentale della morte permanente: i Pokémon esausti non possono più essere resuscitati.
- **Blocco totale degli strumenti di rianimazione**:
  - *Revitalizzante*, *Revitalizzante Max*, *Erba Revitalizzante* e *Ceneremagica* hanno i loro attributi di rianimazione azzerati a livello di dati (`pl_item_data.narc`).
  - L'uso di questi strumenti (sia durante la lotta che dalla borsa fuori dalla lotta) viene rifiutato con il messaggio *"Non ha alcun effetto!"*.
  - Anche l'uso di *Caramelle Rare* su Pokémon a 0 HP viene intercettato e bloccato in `Party_CheckItemEffectsOnMember`.
- **Conservazione dello stato esausto nei Centri Pokémon**:
  - La routine generale di guarigione della squadra (`Party_HealAllMembers`), invocata da Infermiera Joy, mamme, letti e medici, intercetta i membri della squadra a 0 HP e ne salta la guarigione.
  - I Pokémon esausti rimangono a 0 HP, con status esausto e PP inalterati, costringendo il giocatore a depositarli in un box PC cimitero o liberarli come da regolamento Nuzlocke.
  - In caso di sconfitta totale (black out), il giocatore riappare al Centro Pokémon con i Pokémon esausti intatti e può recarsi direttamente al terminale PC per depositare la squadra caduta.

### 4. Starter da Trainer ID (`feature/starter-by-tid`)
Determina la scelta obbligatoria dello starter in base all'ultima cifra del Trainer ID (TID) visualizzato sulla Scheda Allenatore:
- **Cifra finale 1, 2, 3:** Pokémon Erba (**Turtwig**)
- **Cifra finale 4, 5, 6:** Pokémon Fuoco (**Chimchar**)
- **Cifra finale 7, 8, 9:** Pokémon Acqua (**Piplup**)
- **Cifra finale 0:** **Scelta libera** tra tutti e tre gli starter

#### Come funziona tecnicamente:
1. Nella scena della valigetta del Lago Verità (Overlay 78, `choose_starter`), il cursore viene inizializzato direttamente sulla Poké Ball assegnata dal TID del giocatore.
2. La navigazione sinistra/destra (`ChangePokeballChoice`) viene bloccata sulla Poké Ball assegnata se la cifra non è 0, impedendo di selezionare un altro starter.
3. Al momento della conferma (`GetSelectedSpecies` / `ChooseStarter_Exit`), il gioco restituisce tassativamente la specie associata al TID (Turtwig: 387, Chimchar: 390, Piplup: 393), garantendo che la sceneggiatura, la consegna al giocatore e la squadra del rivale Barry rimangano perfettamente sincronizzate.

---

## Utilizzo del Patcher

Per applicare le modifiche alla tua ROM pulita di Pokémon Platino:

1. Inserisci la ROM originale nella cartella `Game/` (es. `Game/3794 - Pokemon - Versione Platino (IT)(EXiMiUS).nds`).
2. Esegui il comando:
   ```bash
   python apply_patch.py
   ```
3. Se eseguito in un terminale interattivo, apparirà il **Selettore Interattivo delle Funzionalità**:
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
   Puoi digitare ad esempio `1` per disattivare il Level Cap (diventa `[ ]`), o premere semplicemente Invio per confermare la selezione predefinita con tutte le funzionalità attive!

4. La ROM patchata verrà generata automaticamente nella cartella `out/Pokemon_Platino_Nuzlocke.nds`.

### Opzioni avanzate della CLI:
```bash
# Mostra informazioni e verifica hash della ROM pulita
python apply_patch.py --info

# Modalità test senza scrivere il file di output
python apply_patch.py --dry-run

# Forzare il menu interattivo
python apply_patch.py -i

# Modalità non-interattiva / scripting (applica tutte le feature)
python apply_patch.py --non-interactive

# Selezionare specifiche feature direttamente da riga di comando
python apply_patch.py --features level-cap permadeath starter-by-tid
```

---

## Esecuzione dei Test

Per verificare l'integrità delle patch e dei file generati:
```bash
python -m unittest discover tests
```
