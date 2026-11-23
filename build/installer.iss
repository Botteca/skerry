; Inno Setup 6: per-user installer (no admin rights)
#define AppName "Skerry"
#define AppVersion "1.0.0"
#define AppExe "Skerry.exe"
; Uninstall key of the installer used before the rename (same per-user scope).
#define LegacyUninstallKey "Software\Microsoft\Windows\CurrentVersion\Uninstall\{6E3B1C52-8E7A-4B4E-9C1D-6A0F5D2B9A11}_is1"

[Setup]
AppId={{6FCF8BCB-3479-4913-B7B6-E586160E575F}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppName}
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=Skerry-Setup-{#AppVersion}
SetupIconFile=..\assets\brand\skerry.ico
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=force
RestartApplications=no

[Languages]
Name: "it"; MessagesFile: "compiler:Languages\Italian.isl"

[Tasks]
Name: "autostart"; Description: "Avvia Skerry con Windows"; GroupDescription: "Opzioni:"
Name: "connect"; Description: "Collega Claude Code e Codex a Skerry"; GroupDescription: "Opzioni:"
Name: "desktopicon"; Description: "Icona sul desktop"; GroupDescription: "Opzioni:"; Flags: unchecked

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
Filename: "{app}\{#AppExe}"; Description: "Avvia {#AppName}"; Flags: nowait postinstall skipifsilent
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
