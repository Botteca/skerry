; Inno Setup 6: per-user installer (no admin rights).
; The version is not written here: build.bat and the release workflow pass it from skerry/__init__.py:
;   ISCC /DAppVersion=1.2.0 build\installer.iss      (python tools\release.py version prints it)
; Silent update, as started by Skerry itself:  Skerry-Setup-X.Y.Z.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART
#ifndef AppVersion
  #error AppVersion is not defined: run ISCC /DAppVersion=X.Y.Z (see build.bat)
#endif
#define AppName "Skerry"
#define AppExe "Skerry.exe"
; Uninstall key of the installer used before the rename (same per-user scope).
#define LegacyUninstallKey "Software\Microsoft\Windows\CurrentVersion\Uninstall\{6E3B1C52-8E7A-4B4E-9C1D-6A0F5D2B9A11}_is1"

[Setup]
AppId={{6FCF8BCB-3479-4913-B7B6-E586160E575F}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppName}
AppPublisherURL=https://github.com/fabrisimo/skerry
AppSupportURL=https://github.com/fabrisimo/skerry/issues
AppUpdatesURL=https://github.com/fabrisimo/skerry/releases
VersionInfoVersion={#AppVersion}
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
DisableDirPage=auto
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=Skerry-Setup-{#AppVersion}
SetupIconFile=..\assets\brand\skerry.ico
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; Same name as win32.single_instance(): Setup knows when Skerry is running.
AppMutex=SkerrySingleInstance
; Close Skerry (Restart Manager) if it still runs when files are replaced, and restart what was closed.
CloseApplications=force
RestartApplications=yes
ShowLanguageDialog=auto
UsePreviousTasks=yes

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"
Name: "it"; MessagesFile: "compiler:Languages\Italian.isl"
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "de"; MessagesFile: "compiler:Languages\German.isl"
Name: "fr"; MessagesFile: "compiler:Languages\French.isl"

[CustomMessages]
en.Options=Options:
it.Options=Opzioni:
es.Options=Opciones:
de.Options=Optionen:
fr.Options=Options :
en.TaskAutostart=Start Skerry with Windows
it.TaskAutostart=Avvia Skerry con Windows
es.TaskAutostart=Iniciar Skerry con Windows
de.TaskAutostart=Skerry mit Windows starten
fr.TaskAutostart=Démarrer Skerry avec Windows
en.TaskConnect=Connect Claude Code and Codex to Skerry
it.TaskConnect=Collega Claude Code e Codex a Skerry
es.TaskConnect=Conectar Claude Code y Codex a Skerry
de.TaskConnect=Claude Code und Codex mit Skerry verbinden
fr.TaskConnect=Connecter Claude Code et Codex à Skerry
en.TaskDesktop=Desktop icon
it.TaskDesktop=Icona sul desktop
es.TaskDesktop=Icono en el escritorio
de.TaskDesktop=Desktopsymbol
fr.TaskDesktop=Icône sur le Bureau
en.LaunchApp=Start Skerry
it.LaunchApp=Avvia Skerry
es.LaunchApp=Iniciar Skerry
de.LaunchApp=Skerry starten
fr.LaunchApp=Lancer Skerry

[Tasks]
Name: "autostart"; Description: "{cm:TaskAutostart}"; GroupDescription: "{cm:Options}"
Name: "connect"; Description: "{cm:TaskConnect}"; GroupDescription: "{cm:Options}"
Name: "desktopicon"; Description: "{cm:TaskDesktop}"; GroupDescription: "{cm:Options}"; Flags: unchecked

[Files]
Source: "..\dist\Skerry\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "{#AppName}"; \
  ValueData: """{app}\{#AppExe}"""; Flags: uninsdeletevalue; Tasks: autostart
; Autostart values left by earlier app names
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: none; ValueName: "Island"; Flags: deletevalue

[Run]
Filename: "{app}\skerry-cli.exe"; Parameters: "connect"; Flags: runhidden; Tasks: connect
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchApp}"; Flags: nowait postinstall skipifsilent
; silent install or update: start (again) the app; a second instance only expands the first one
Filename: "{app}\{#AppExe}"; Flags: nowait; Check: WizardSilent

[UninstallRun]
Filename: "{app}\skerry-cli.exe"; Parameters: "disconnect"; Flags: runhidden; RunOnceId: "Disconnect"
Filename: "{sys}\taskkill.exe"; Parameters: "/F /IM {#AppExe}"; Flags: runhidden; RunOnceId: "Kill"

[Code]
{ Silently uninstall the pre-rename app if present. Its own uninstaller stops it, removes its
  autostart value and disconnects its hooks; Skerry's "connect" task then installs the new ones. }
procedure RemoveLegacyInstall();
var
  Cmd: String;
  Code: Integer;
begin
  if RegQueryStringValue(HKCU, '{#LegacyUninstallKey}', 'UninstallString', Cmd) then
  begin
    Log('Removing legacy install: ' + Cmd);
    Exec(RemoveQuotes(Cmd), '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART', '', SW_HIDE, ewWaitUntilTerminated, Code);
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssInstall then
    RemoveLegacyInstall();
end;
