#define MyAppName "Transcribrr"
#define MyAppPublisher "John Miller"
#define MyAppURL "https://github.com/johnmiller/transcribrr"
#define MyAppExeName "Transcribrr.bat"
#define MyAppStartName "StartTranscribrr.bat"

; Define GUIDs for different flavors
#define AppGuidCPU  "{E5F78A54-F82A-49C3-A591-76A32F947A99}"
#define AppGuidCUDA "{32D5F3F3-9A1B-4DA7-BEF3-0E66D22F7842}"

; Preprocessor directives to handle different build flavors
#ifndef Flavour
  #define Flavour "cpu"
#endif

#if Flavour == "cpu"
  #define FlavorName "CPU"
  #define FlavorDescription " (CPU Version)"
  #define OutputDirName "cpu"
  #define AppIdValue AppGuidCPU
#elif Flavour == "cuda" 
  #define FlavorName "CUDA"
  #define FlavorDescription " (CUDA Version)"
  #define OutputDirName "cuda"
  #define AppIdValue AppGuidCUDA
#endif

; Version is provided at compile time
#ifndef MyAppVersionValue
  #error "MyAppVersionValue must be defined via command line parameter"
#endif

#define MyAppVersion MyAppVersionValue

[Setup]
; NOTE: The value of AppId uniquely identifies this application.
; Do not use the same AppId value in installers for other applications.
; Every new version should use exactly the same AppId.
AppId={#AppIdValue}
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

; ---- Files section ----
[Files]
Source: "..\dist\Transcribrr_{#Flavour}\*"; \
       DestDir: "{app}"; \
       Flags: ignoreversion recursesubdirs createallsubdirs


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