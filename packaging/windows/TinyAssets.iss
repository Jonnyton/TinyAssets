#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef Architecture
  #define Architecture "x86_64"
#endif

[Setup]
AppId={{AE29C5AB-4807-4DE9-919A-53AF37E793C1}
AppName=TinyAssets
AppVersion={#AppVersion}
AppPublisher=TinyAssets
DefaultDirName={localappdata}\Programs\TinyAssets
DefaultGroupName=TinyAssets
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible arm64
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist\windows
OutputBaseFilename=TinyAssetsSetup-{#AppVersion}-{#Architecture}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupIconFile=..\..\tinyassets\desktop\app.ico
UninstallDisplayIcon={app}\TinyAssets.exe

[Tasks]
Name: "autostart"; Description: "Start TinyAssets when I sign in"; GroupDescription: "Startup:"; Flags: checkedonce
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"

[Files]
Source: "..\dist\windows\TinyAssets.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\TinyAssets"; Filename: "{app}\TinyAssets.exe"
Name: "{userdesktop}\TinyAssets"; Filename: "{app}\TinyAssets.exe"; Tasks: desktopicon
Name: "{userstartup}\TinyAssets"; Filename: "{app}\TinyAssets.exe"; Tasks: autostart

[Run]
Filename: "{app}\TinyAssets.exe"; Description: "Launch TinyAssets"; Flags: nowait postinstall skipifsilent
