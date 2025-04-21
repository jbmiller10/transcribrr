#define MyAppName "Transcribrr"
#define MyAppPublisher "John Miller"
#define MyAppURL "https://github.com/johnmiller/transcribrr"
#define MyAppExeName "Transcribrr.bat"
#define MyAppStartName "StartTranscribrr.bat"

; Preprocessor directives to handle different build flavors
#ifndef Flavour
  #define Flavour "cpu"
#endif

#if Flavour == "cpu"
  #define FlavorName "CPU"
  #define FlavorDescription " (CPU Version)"
  #define OutputDirName "cpu"
#elif Flavour == "cuda" 
  #define FlavorName "CUDA"
  #define FlavorDescription " (CUDA Version)"
  #define OutputDirName "cuda"
#endif

; Read version from app/__init__.py
#define FindVersionLine(str FileName) \
   Local[0] = FileOpen(FileName), \
   Local[1] = "", \
   Local[2] = "", \
   While (!FileEof(Local[0])) Do \
   ( \
     Local[1] = FileRead(Local[0]), \
     If Pos("__version__", Local[1]) > 0 Then \
       Local[2] = Local[1] \
   ), \
   FileClose(Local[0]), \
   Local[2]

#define ExtractVersion(str VersionLine) \
   Copy(VersionLine, Pos('"', VersionLine) + 1, \
   Pos('"', VersionLine, Pos('"', VersionLine) + 1) - Pos('"', VersionLine) - 1)

#define VersionLine FindVersionLine("..\app\__init__.py")
#define MyAppVersion ExtractVersion(VersionLine)

[Setup]
; NOTE: The value of AppId uniquely identifies this application.
; Do not use the same AppId value in installers for other applications.
; Every new version should use exactly the same AppId.
AppId={{E5F78A54-F82A-49C3-A591-76A32F947A99}-{#Flavour}}
AppName={#MyAppName} {#FlavorName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}{#FlavorDescription}
DefaultGroupName={#MyAppName}{#FlavorDescription}
LicenseFile=..\LICENSE
; Uncomment this to enable compression (default is already good)
;Compression=lzma2/ultra64
;SolidCompression=yes
; Require admin rights for installation (for Start Menu shortcuts)
PrivilegesRequired=admin
; Output filename
OutputDir=..\dist
OutputBaseFilename=Transcribrr-windows-{#Flavour}-setup
; App icon
SetupIconFile=..\icons\app\app_icon.ico
; Installer/uninstaller display settings
WizardStyle=modern
UninstallDisplayIcon={app}\icons\app\app_icon.ico
UninstallDisplayName={#MyAppName} {#FlavorName}
DisableWelcomePage=no
DisableDirPage=no
DisableProgramGroupPage=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "quicklaunchicon"; Description: "{cm:CreateQuickLaunchIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked; OnlyBelowVersion: 6.1; Check: not IsAdminInstallMode

[Files]
; Include all application files from the build directory
Source: "..\dist\{#MyAppName}_{#OutputDirName}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; Start Menu shortcuts
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppStartName}"; WorkingDir: "{app}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
; Desktop icon
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppStartName}"; WorkingDir: "{app}"; Tasks: desktopicon
; Quick Launch icon
Name: "{userappdata}\Microsoft\Internet Explorer\Quick Launch\{#MyAppName}"; Filename: "{app}\{#MyAppStartName}"; WorkingDir: "{app}"; Tasks: quicklaunchicon

[Run]
; Option to launch the application after installation
Filename: "{app}\{#MyAppStartName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Delete application data directory during uninstallation
Type: filesandordirs; Name: "{localappdata}\{#MyAppName}"