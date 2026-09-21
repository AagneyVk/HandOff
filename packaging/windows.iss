#ifndef AppVersion
  #define AppVersion "1.0.0-rc12"
#endif
[Setup]
AppId={{A821EB94-4D41-4C2D-9A0B-EA2B17C83C16}
AppName=HandOff
AppVersion={#AppVersion}
AppPublisher=HandOff
DefaultDirName={localappdata}\Programs\HandOff
DefaultGroupName=HandOff
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist\installer
OutputBaseFilename=HandOff-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
UninstallDisplayIcon={app}\HandOff.exe
[Files]
Source: "..\dist\HandOff\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
[Icons]
Name: "{userprograms}\HandOff"; Filename: "{app}\HandOff.exe"
[Run]
Filename: "{app}\HandOff.exe"; Description: "Open HandOff"; Flags: nowait postinstall skipifsilent
