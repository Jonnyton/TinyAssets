#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef Architecture
  #define Architecture "x86_64"
#endif

[Setup]
AppId={{AE29C5AB-4807-4DE9-919A-53AF37E793C1}
AppName=TinyAssets Server
AppVersion={#AppVersion}
AppPublisher=TinyAssets
DefaultDirName={localappdata}\Programs\TinyAssets
DefaultGroupName=TinyAssets Server
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible arm64
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist\windows
OutputBaseFilename=TinyAssetsServerSetup-{#AppVersion}-{#Architecture}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupIconFile=..\..\tinyassets\desktop\app.ico
UninstallDisplayIcon={app}\TinyAssets.exe

[Tasks]
Name: "autostart"; Description: "Start TinyAssets Server when I sign in"; GroupDescription: "Startup:"; Flags: checkedonce
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"

[Files]
Source: "..\dist\windows\TinyAssets.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\TinyAssets Server"; Filename: "{app}\TinyAssets.exe"
Name: "{userdesktop}\TinyAssets Server"; Filename: "{app}\TinyAssets.exe"; Tasks: desktopicon
Name: "{userstartup}\TinyAssets Server"; Filename: "{app}\TinyAssets.exe"; Tasks: autostart

[Run]
Filename: "{app}\TinyAssets.exe"; Description: "Launch TinyAssets Server"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{userappdata}\TinyAssets\updates"

[Code]
function ShortcutTarget(Path: String): String;
var
  Shell: Variant;
  Link: Variant;
begin
  Result := '';
  if not FileExists(Path) then
    exit;
  try
    Shell := CreateOleObject('WScript.Shell');
    Link := Shell.CreateShortcut(Path);
    Result := Link.TargetPath;
  except
    Result := '';
  end;
end;

{ Earlier tray installs named their shortcuts "TinyAssets", the name the Electron
  chat app's shortcuts use. Remove one only when it launches THIS install's tray,
  so a chat-app shortcut of the same name is never touched. }
procedure RemoveEarlierTrayShortcut(Path: String);
var
  Target: String;
begin
  Target := ShortcutTarget(Path);
  if (Target <> '') and
     (CompareText(ExpandFileName(Target), ExpandConstant('{app}\TinyAssets.exe')) = 0) then
    DeleteFile(Path);
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  UpdateRoot: String;
  ReleaseRoot: String;
  InstallerName: String;
  CurrentState: String;
begin
  if CurStep <> ssPostInstall then
    exit;
  RemoveEarlierTrayShortcut(ExpandConstant('{userstartup}\TinyAssets.lnk'));
  RemoveEarlierTrayShortcut(ExpandConstant('{userdesktop}\TinyAssets.lnk'));
  RemoveEarlierTrayShortcut(ExpandConstant('{group}\TinyAssets.lnk'));
  UpdateRoot := ExpandConstant('{userappdata}\TinyAssets\updates');
  InstallerName := 'TinyAssetsServerSetup-{#AppVersion}-{#Architecture}.exe';
  ReleaseRoot := UpdateRoot + '\releases\{#AppVersion}';
  ForceDirectories(ReleaseRoot);
  if CompareText(
    ExpandFileName(ExpandConstant('{srcexe}')),
    ExpandFileName(ReleaseRoot + '\' + InstallerName)
  ) <> 0 then
  begin
    if not FileCopy(ExpandConstant('{srcexe}'), ReleaseRoot + '\' + InstallerName, False) then
      RaiseException('Could not retain the signed installer for rollback');
  end;
  CurrentState :=
    '{"artifact":"releases/{#AppVersion}/' + InstallerName +
    '","version":"{#AppVersion}"}' + #13#10;
  if not SaveStringToFile(UpdateRoot + '\current.json', CurrentState, False) then
    RaiseException('Could not initialize the desktop updater state');
end;
