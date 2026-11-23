# Collegare i servizi

Guide di configurazione dei connettori facoltativi. Torna al [README](../README.it.md).

## Microsoft 365

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

## Google Calendar

Skerry può mostrare il prossimo evento di Google Calendar con il link **Google Meet** e il pulsante *Entra* (se è
collegato anche Microsoft 365, l'isola mostra la riunione che arriva prima). Legge il calendario principale in **sola
lettura** (ambito `calendar.events.readonly`) ogni 2 minuti. La guida è anche in **Impostazioni → Connessioni → Google
Calendar**.

1. Nella **console Google Cloud** crea un progetto (es. `skerry-calendar`) e abilita la **Google Calendar API**.
2. In **Google Auth Platform** (schermata di consenso OAuth) scegli il pubblico (*Interno* per un'organizzazione
   Workspace, altrimenti *Esterno* e aggiungiti come utente di test) e aggiungi l'ambito `calendar.events.readonly`.
3. **Client → Crea client → App desktop**; copia in Skerry client ID e client secret. Google chiede un segreto anche
   per le app desktop: Skerry lo cifra con DPAPI, come il refresh token, mai in `settings.json`.
4. **Accedi**: si apre il browser, Skerry riceve la risposta su un indirizzo `http://127.0.0.1:<porta>` usato una
   volta sola (PKCE).

Finché l'app è in *Test*, Google chiude l'accesso dopo 7 giorni: accedi di nuovo o pubblica l'app. *Disconnetti*
cancella il refresh token locale.

## Azure Data Factory

Skerry mostra l'ultima esecuzione delle pipeline che scegli e ti avvisa quando una non riesce. È in **sola lettura**:
chiama `queryPipelineRuns` di Azure Resource Manager ogni 5 minuti (ultimi 7 giorni). La guida passo passo è anche in
**Impostazioni → Connessioni → Azure Data Factory**.

1. Scegli l'accesso:
   - **Azure CLI**: installa la Azure CLI ed esegui una volta `az login`. Skerry esegue `az account get-access-token`
     (Skerry non salva password né token).
   - **Service principal**: in **Microsoft Entra ID → Registrazioni app** crea un'app (es. `skerry-adf-reader`), copia
     l'ID applicazione (client) e l'ID directory (tenant), crea un segreto client e incolla il suo valore in Skerry. Il
     segreto è cifrato con DPAPI in `%APPDATA%\Skerry\secrets\`, mai scritto in `settings.json`, mai più mostrato.
2. Sulla data factory, **Controllo di accesso (IAM) → Aggiungi assegnazione di ruolo → Lettore** per il tuo account o l'app.
3. Inserisci ID sottoscrizione, gruppo di risorse e nome della factory (es. `rg-contoso-data`, `adf-contoso-prod`) e le
   pipeline da controllare separate da virgole (es. `PL_Nightly_Load, PL_Sales_Export`). Accendi l'interruttore.

Gli errori (`az login` scaduto, ruolo mancante, rete) compaiono accanto all'interruttore; l'isola non si blocca mai.

## Widget SQL Server e Azure SQL

Ogni widget esegue una query e mostra il primo valore nell'isola espansa, verde, ambra o rosso secondo due soglie (se
il rosso è più basso dell'ambra, valori più bassi sono peggiori). Ricevi un avviso quando un widget diventa rosso. Si
configurano in **Impostazioni → Connessioni → SQL Server · Azure SQL**, che ha la stessa guida passo passo.

- **Sola lettura, tre volte.** Una query viene salvata ed eseguita solo se è una sola istruzione `SELECT` o `WITH`
  senza comandi che scrivono (`INSERT`, `UPDATE`, `DELETE`, `MERGE`, `DROP`, `ALTER`, `CREATE`, `TRUNCATE`, `EXEC`,
  `SELECT … INTO`, `WAITFOR`, `OPENROWSET`…; commenti e stringhe sono ignorati dal controllo). Ogni query gira con
  autocommit disattivato e viene annullata (rollback). E la guida chiede un accesso che può solo leggere (`db_datareader`).
- **Accesso per widget:** Windows (integrato, per SQL Server nella tua rete), utente e password SQL (la password è
  cifrata con DPAPI in `%APPDATA%\Skerry\secrets\`, mai in `settings.json`; rimuovendo il widget viene cancellata),
  oppure Microsoft Entra ID per Azure SQL (token da `az login`).
- Serve **Microsoft ODBC Driver 18 (o 17) for SQL Server** e il pacchetto `pyodbc` (in `requirements.txt`). Timeout
  di accesso 10 s, di query 15 s, ogni widget al massimo ogni 30 s: gli errori compaiono sul widget, l'isola non si
  blocca mai.
- Esempio (nomi inventati): server `sql-contoso.database.windows.net`, database `ContosoSales`,
  `SELECT COUNT(*) FROM dbo.Orders WHERE Status = 'Open'`, ambra da 10, rosso da 20.
