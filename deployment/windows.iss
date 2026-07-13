[Setup]
AppName=Lecture Auto
AppVersion=0.1.0
DefaultDirName={autopf}\Lecture Auto
DefaultGroupName=Lecture Auto
OutputDir=dist-installer
OutputBaseFilename=LectureAuto-Setup
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible

[Files]
Source: "dist\LectureAuto\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Lecture Auto"; Filename: "{app}\LectureAuto.exe"
Name: "{autodesktop}\Lecture Auto"; Filename: "{app}\LectureAuto.exe"
