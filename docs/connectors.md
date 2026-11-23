# Connecting services

Setup guides for the optional connectors. Back to the [README](../README.md).

## Microsoft 365

Skerry can show your next Outlook/Teams meeting with a *Join* button. It uses Microsoft Graph, **read-only**, with a
browser sign-in: no password is stored, and the token cache is encrypted with Windows DPAPI.

You need an app registration in Microsoft Entra ID (once, a couple of minutes). If you can't create one, ask your
IT administrator.

1. Open the [Microsoft Entra admin center](https://entra.microsoft.com) → **Identity → Applications → App registrations → New registration**.
   - Name: anything, e.g. `Skerry`.
   - Supported account types: *Accounts in this organizational directory only* (or *any organizational directory* if
     several organizations will use it).
   - Leave the redirect URI empty and click **Register**.
2. **Authentication → Add a platform → Mobile and desktop applications**, add the redirect URI `http://localhost`.
   Under **Advanced settings**, set **Allow public client flows** to *Yes*. Save.
3. **API permissions → Add a permission → Microsoft Graph → Delegated permissions**: add `User.Read` and
   `Calendars.Read`. Depending on your organization's policy, an administrator may need to *Grant admin consent*.
4. On the **Overview** page copy the **Application (client) ID**.
5. In Skerry: **Settings → Connections → Microsoft 365**, paste the client ID. *Tenant*: keep `organizations`, or put
   your directory (tenant) ID. Click **Sign in** and complete the sign-in in the browser.

No client secret is needed: Skerry is a public client. *Sign out* deletes the local token cache.

## Google Calendar

Skerry can show your next Google Calendar event with its **Google Meet** link and a *Join* button (with Microsoft 365
connected too, the island shows whichever meeting comes first). It reads the primary calendar, **read-only**
(scope `calendar.events.readonly`), every 2 minutes. The guide is also in **Settings → Connections → Google Calendar**.

1. In the **Google Cloud console** create a project (e.g. `skerry-calendar`) and enable the **Google Calendar API**.
2. In **Google Auth Platform** (OAuth consent screen) choose the audience (*Internal* for a Workspace organization,
   otherwise *External* and add yourself as a test user) and add the scope `calendar.events.readonly`.
3. **Clients → Create client → Desktop app**; copy the client ID and the client secret into Skerry. Google requires a
   secret even for desktop apps: Skerry encrypts it with DPAPI, like the refresh token, never in `settings.json`.
4. **Sign in**: the browser opens, Skerry receives the answer on a one-shot `http://127.0.0.1:<port>` address (PKCE).

While the app is in *Testing*, Google ends the access after 7 days: sign in again or publish the app. *Sign out*
deletes the local refresh token.

## Azure Data Factory

Skerry shows the latest run of the pipelines you choose and alerts you when one fails. It is **read-only**: it calls
Azure Resource Manager `queryPipelineRuns` every 5 minutes (last 7 days). The step-by-step guide is also in
**Settings → Connections → Azure Data Factory**.

1. Choose the sign-in:
   - **Azure CLI**: install the Azure CLI and run `az login` once. Skerry runs `az account get-access-token` (no
     password or token is stored by Skerry).
   - **Service principal**: in **Microsoft Entra ID → App registrations** create an app (e.g. `skerry-adf-reader`), copy
     the application (client) ID and the directory (tenant) ID, create a client secret and paste its value in Skerry.
     The secret is encrypted with DPAPI in `%APPDATA%\Skerry\secrets\`, never written to `settings.json`, never shown again.
2. On the data factory, **Access control (IAM) → Add role assignment → Reader** for your account or the app.
3. Enter subscription ID, resource group and factory name (e.g. `rg-contoso-data`, `adf-contoso-prod`) and the
   pipelines to watch, separated by commas (e.g. `PL_Nightly_Load, PL_Sales_Export`). Turn the switch on.

Errors (expired `az login`, missing role, network) appear next to the switch; the island is never blocked.

## SQL Server and Azure SQL widgets

Each widget runs one query and shows its first value in the expanded island, green, amber or red by two thresholds
(if red is lower than amber, lower values are worse). You get an alert when a widget turns red. Set them up in
**Settings → Connections → SQL Server · Azure SQL**, which has the same step-by-step guide.

- **Read-only, three times over.** A query is saved and run only if it is a single `SELECT` or `WITH` statement with
  no writing command (`INSERT`, `UPDATE`, `DELETE`, `MERGE`, `DROP`, `ALTER`, `CREATE`, `TRUNCATE`, `EXEC`,
  `SELECT … INTO`, `WAITFOR`, `OPENROWSET`…; comments and string literals are ignored by the check). Every query runs
  with autocommit off and is rolled back. And the guide asks for a login that can only read (`db_datareader`).
- **Sign-in per widget:** Windows (integrated, for SQL Server on your network), SQL user and password (the password
  is encrypted with DPAPI in `%APPDATA%\Skerry\secrets\`, never in `settings.json`; removing the widget deletes
  it), or Microsoft Entra ID for Azure SQL (token from `az login`).
- Needs **Microsoft ODBC Driver 18 (or 17) for SQL Server** and the `pyodbc` package (in `requirements.txt`).
  Login timeout 10 s, query timeout 15 s, each widget every 30 s or more: errors show on the widget, the island is
  never blocked.
- Example (invented names): server `sql-contoso.database.windows.net`, database `ContosoSales`,
  `SELECT COUNT(*) FROM dbo.Orders WHERE Status = 'Open'`, amber from 10, red from 20.
