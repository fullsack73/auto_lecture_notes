[Setup]
AppName=Lecture Auto
AppVersion=0.1.3
DefaultDirName={autopf}\Lecture Auto
DefaultGroupName=Lecture Auto
OutputDir=..\dist-installer
OutputBaseFilename=LectureAuto-Setup
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
WizardStyle=modern
CloseApplications=yes

[Files]
Source: "..\build\windows\LectureAuto.dist\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Lecture Auto"; Filename: "{app}\LectureAuto.exe"
Name: "{autodesktop}\Lecture Auto"; Filename: "{app}\LectureAuto.exe"

[Run]
Filename: "{app}\LectureAuto.exe"; Description: "Launch Lecture Auto"; Flags: nowait postinstall skipifsilent
