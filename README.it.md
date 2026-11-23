<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/brand/skerry-logo-dark.svg">
    <img src="assets/brand/skerry-logo.svg" alt="Skerry" width="360">
  </picture>
</p>

<p align="center">
  <b>Una dynamic island per Windows che mostra cosa stanno facendo Claude Code e Codex e ti fa approvare le loro richieste di permesso senza lasciare il lavoro.</b>
</p>

<p align="center">
  <a href="https://github.com/fabrisimo/skerry/actions/workflows/ci.yml"><img src="https://github.com/fabrisimo/skerry/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="Licenza MIT"></a>
  <img src="https://img.shields.io/badge/platform-Windows%2010%20%7C%2011-0078d4.svg" alt="Windows 10 | 11">
</p>

<p align="center"><a href="README.md">English</a> · <b>Italiano</b></p>

---

Skerry è una piccola pillola sempre in primo piano agganciata a un bordo dello schermo. Oltre agli agenti di
programmazione mostra il brano in riproduzione e il volume, microfono/fotocamera in uso, la batteria del portatile e dei
dispositivi Bluetooth, un timer/Pomodoro, una mensola per i file, il consumo locale di token e la prossima riunione di
Microsoft 365. Tutto gira in locale.

<p align="center">
  <img src="docs/img/it/00-compact-states.png" alt="Stati compatti: agente al lavoro, musica, Pomodoro, attività finita, richiesta di permesso" width="48%">
  &nbsp;
  <img src="docs/img/it/06-expanded.png" alt="Vista espansa con musica, riunione, agenti, consumo, sistema, timer e mensola" width="48%">
</p>

<details>
<summary>Altri screenshot</summary>

| | |
|---|---|
| ![Agente al lavoro](docs/img/it/01-agent.png) | ![Richiesta di permesso](docs/img/it/04-permission.png) |
| ![Musica](docs/img/it/02-music.png) | ![Timer](docs/img/it/03-timer.png) |
| ![Attività finita](docs/img/it/05-done.png) | ![Impostazioni: aspetto](docs/img/it/07-settings-appearance.png) |
| ![Impostazioni: moduli](docs/img/it/07-settings-modules.png) | ![Impostazioni: connessioni](docs/img/it/07-settings-connections.png) |

</details>

> L'interfaccia è in inglese e in italiano: segue la lingua di Windows, oppure scegli in *Impostazioni → Generale →
> Lingua* (cambia subito, senza riavvio).

## Funzioni

| Modulo | Cosa fa |
|---|---|
| **Claude Code** | Azione in corso, richieste di permesso (*Consenti · Sempre · Nega · Terminale*), avanzamento dei task, completamento, contesto per sessione, limiti 5 ore/settimanali con avvisi a soglia |
| **Codex** | Azione in corso, richieste di permesso, completamento (tramite gli hook di Codex) |
| **Musica e video** | "In riproduzione" di Windows (Spotify, YouTube nel browser, VLC…): copertina, colore d'accento dalla copertina, barra di avanzamento cliccabile, controlli, volume con la rotellina o lo slider |
| **Microfono e fotocamera** | Pallino arancione/verde mentre un'app li usa, con il nome dell'app |
| **Batteria** | Portatili: alimentazione collegata/scollegata e batteria scarica |
| **Dispositivi Bluetooth** | Livello della batteria dei dispositivi che lo comunicano, con avviso di batteria scarica |
| **Timer e Pomodoro** | Conto alla rovescia nella pillola, cicli Pomodoro configurabili |
| **Mensola** | Trascina dei file sulla pillola, poi *Copia* e Ctrl+V dove vuoi |
| **Utilizzo di Claude** | Token usati nelle ultime 5 ore / 7 giorni, letti dai file di sessione locali di Claude Code |
| **Riunioni** | Prossima riunione di Microsoft 365 (Outlook/Teams) con il pulsante *Entra* e un avviso prima dell'inizio (facoltativo) |

**Uso**

- **Clic** sulla pillola per espanderla; si richiude quando il mouse esce.
- **Trascinala**: si aggancia al bordo più vicino (sopra, sotto, sinistra, destra), su qualsiasi monitor. Sui bordi laterali diventa una linguetta verticale.
- **Rotellina**: sulla musica cambia il volume, sugli agenti scorre tra le sessioni.
- **`Win+Alt+I`** la espande/richiude da qualsiasi app (configurabile).
- **Clic su una sessione** nella vista espansa per portare in primo piano il suo terminale o VS Code.
- **Icona nell'area di notifica**: Impostazioni, Pausa, Avvia con Windows, aggiornamenti, log, Esci.
- Si nasconde con le app a **schermo intero** (le richieste di permesso restano visibili, configurabile) e, a scelta, dalla **condivisione e registrazione dello schermo**.

## Installazione

### Installer

1. Scarica `Skerry-Setup-x.y.z.exe` dalla pagina [Releases](https://github.com/fabrisimo/skerry/releases).
2. Eseguilo. Non servono diritti di amministratore; si installa in `%LOCALAPPDATA%\Programs\Skerry`.
   *Avvia Skerry con Windows* e *Collega Claude Code e Codex a Skerry* sono già selezionati.

Gli eseguibili non sono ancora firmati, quindi SmartScreen può mostrare "Autore sconosciuto" (*Ulteriori informazioni →
Esegui comunque*). La disinstallazione scollega gli hook da Claude Code e Codex e rimuove l'avvio automatico.

### Da sorgente

Requisiti: Windows 10/11, Python 3.11 o successivo.

```powershell
git clone https://github.com/fabrisimo/skerry.git
cd skerry
.\setup_dev.bat      # crea un venv in %LOCALAPPDATA%\venvs\skerry e installa requirements.txt
.\run_dev.bat        # avvia Skerry; log in .\logs\skerry.log
```

Per creare l'installer installa [Inno Setup 6](https://jrsoftware.org/isinfo.php) ed esegui `.\build.bat`.
Produce `dist\Skerry\` (`Skerry.exe` e `skerry-cli.exe`) e `dist\Skerry-Setup-x.y.z.exe`.

## Configurare Claude Code e Codex

Skerry riceve gli eventi tramite gli **hook** degli agenti. Aggiunge le proprie voci e non tocca il resto;
`~/.claude/settings.json` e `~/.codex/hooks.json` vengono copiati in `%LOCALAPPDATA%\Skerry\backup\` prima di ogni modifica.

Puoi collegarli in uno di questi modi:

- l'opzione dell'installer *Collega Claude Code e Codex a Skerry* (attiva di default);
- **Impostazioni → Agenti → Collega**;
- da terminale: `skerry-cli connect` (e `skerry-cli disconnect` per toglierli).

Poi:

- **Claude Code**: avvia una nuova sessione. Skerry registra hook HTTP, un hook a comando `SessionStart` (per trovare la
  finestra del terminale) e una status line. Una status line già presente viene mantenuta e concatenata; scollegando
  viene ripristinata.
- **Codex**: apri Codex e approva i nuovi hook con `/hooks` (Codex esegue solo gli hook approvati).

**Come funzionano i permessi.** Quando un agente chiede un permesso, la richiesta resta in attesa in Skerry. *Consenti*,
*Sempre* (applica la regola suggerita da Claude Code) e *Nega* rispondono; *Terminale*, o nessuna risposta entro il tempo
configurato (5 minuti di default), restituisce la decisione al prompt dell'agente. Se rispondi nel terminale, Skerry
scarta la richiesta. Se Skerry non è in esecuzione, gli hook terminano in silenzio e gli agenti non restano mai bloccati.

> **Nota** — i limiti 5 ore/settimanali vengono comunicati da Claude Code solo con i piani Pro/Max. Con gli altri piani
> Skerry mostra comunque contesto, sessioni e consumo locale di token.

Se lo esegui da sorgente, *Collega* fa puntare gli hook a `python cli.py`. Dopo l'installazione con l'installer,
ricollegali perché usino `skerry-cli.exe`.

## Collegare Microsoft 365 (facoltativo)

Skerry può mostrare la prossima riunione di Outlook/Teams con il pulsante *Entra*. Usa Microsoft Graph in **sola
lettura**, con accesso dal browser: nessuna password viene salvata e la cache dei token è cifrata con DPAPI di Windows.

Serve una registrazione app in Microsoft Entra ID (una volta sola, un paio di minuti). Se non puoi crearla, chiedi al tuo
amministratore IT.

1. Apri l'[interfaccia di amministrazione di Microsoft Entra](https://entra.microsoft.com) → **Identità → Applicazioni →
   Registrazioni app → Nuova registrazione**.
   - Nome: quello che vuoi, ad es. `Skerry`.
   - Tipi di account supportati: *Solo account in questa directory organizzativa* (oppure *qualsiasi directory
     organizzativa* se la useranno più organizzazioni).
   - Lascia vuoto l'URI di reindirizzamento e fai clic su **Registra**.
2. **Autenticazione → Aggiungi una piattaforma → Applicazioni per dispositivi mobili e desktop**, aggiungi l'URI
   `http://localhost`. In **Impostazioni avanzate** imposta **Consenti flussi client pubblici** su *Sì*. Salva.
3. **Autorizzazioni API → Aggiungi un'autorizzazione → Microsoft Graph → Autorizzazioni delegate**: aggiungi `User.Read` e
   `Calendars.Read`. A seconda dei criteri dell'organizzazione, un amministratore potrebbe dover *Concedere il consenso
   amministratore*.
4. Nella pagina **Panoramica** copia l'**ID applicazione (client)**.
5. In Skerry: **Impostazioni → Connessioni → Microsoft 365**, incolla il client ID. *Tenant*: lascia `organizations`
   oppure inserisci l'ID della tua directory (tenant). Fai clic su **Accedi** e completa l'accesso nel browser.

Non serve un segreto client: Skerry è un client pubblico. *Disconnetti* cancella la cache locale dei token.

## Privacy

**Nessuna telemetria; i dati restano sul PC.**

- Skerry non invia statistiche, report di crash o dati di utilizzo da nessuna parte.
- Il server degli hook ascolta solo su `127.0.0.1`. Le decisioni sui permessi arrivano solo dalla finestra di Skerry,
  mai via HTTP.
- Il consumo di token è calcolato dai file di sessione di Claude Code sul disco; non viene caricato nulla.
- L'accesso alla rete avviene solo per: il controllo degli aggiornamenti (API delle release di GitHub, disattivabile
  nelle impostazioni) e, se lo colleghi, Microsoft Graph per leggere il calendario.
- I segreti (la cache dei token di Microsoft 365) sono cifrati con DPAPI e leggibili solo dal tuo utente Windows.

| Percorso | Contenuto |
|---|---|
| `%APPDATA%\Skerry\settings.json` | Impostazioni (nessun segreto) |
| `%APPDATA%\Skerry\shelf.json` | File sulla mensola (solo i percorsi) |
| `%APPDATA%\Skerry\secrets\` | Token dei connettori (cifrati con DPAPI) |
| `%LOCALAPPDATA%\Skerry\logs\` | Log a rotazione |
| `%LOCALAPPDATA%\Skerry\backup\` | Backup della configurazione degli agenti |

## Come funziona

```
Claude Code ──hook http──────────────────▶ 127.0.0.1:47800 ─┐
Claude Code ──skerry-cli statusline──────▶ /statusline      ─┼─▶ Store ─▶ UI (pywebview / WebView2)
Codex ───────skerry-cli hook codex───────▶ /hook/...        ─┘
Windows (media, audio, registro, alimentazione, Bluetooth), M365, consumo locale ─▶ moduli ─▶ UI
```

Python 3.11+, pywebview su WebView2, un server Flask locale e una UI in HTML/JS/CSS semplice. `Skerry.exe` esegue l'app
sotto un supervisore che la riavvia in caso di crash. La mappa dei moduli e le note di progetto sono in
[`CLAUDE.md`](CLAUDE.md) (in inglese).

## Contribuire

I contributi sono benvenuti! Leggi [CONTRIBUTING.md](CONTRIBUTING.md) (in inglese) per l'ambiente di sviluppo, i
controlli e le linee guida, e il [Codice di condotta](CODE_OF_CONDUCT.md). Segnala i problemi di sicurezza in privato
come descritto in [SECURITY.md](SECURITY.md).

## Licenza

[MIT](LICENSE) © Fabrizio (fabrisimo)

Skerry è un progetto indipendente, non affiliato né approvato da Anthropic, OpenAI o Microsoft.
