; Inno Setup Script for Transcribrr
; Version: 1.0

; ---- App Definition ----
#define MyAppName "Transcribrr"
#define MyAppPublisher "John Miller"
#define MyAppURL "https://github.com/johnmiller/transcribrr"
; Define the ACTUAL executable name produced by PyInstaller
#define MyAppActualExeName "Transcribrr.exe"

; ---- Version Handling ----
; Version is passed via command line: /DMyAppVersionValue=1.0.0
#ifndef MyAppVersionValue
  #error "MyAppVersionValue must be defined via command line parameter. Example: /DMyAppVersionValue=1.0.0"
#endif
#define MyAppVersion MyAppVersionValue

; ---- Flavor Handling (CPU vs CUDA) ----
; Flavor is passed via command line: /DFlavour=cpu or /DFlavour=cuda
#ifndef Flavour
  #define Flavour "cpu" ; Default to CPU if not specified
#endif

; Define Flavor-specific settings AND the final AppId string directly
#if Flavour == "cpu"
  #define FlavorName "CPU"
  #define FlavorDescription " (CPU Version)"
  #define OutputDirName "cpu"
  #define ActualAppId "{E5F78A54-F82A-49C3-A591-76A32F947A99}"
#elif Flavour == "cuda"
  #define FlavorName "CUDA"
  #define FlavorDescription " (CUDA Version)"
  #define OutputDirName "cuda"
  #define ActualAppId "{32D5F3F3-9A1B-4DA7-BEF3-0E66D22F7842}"
#else
  #error "Unsupported Flavour defined. Use 'cpu' or 'cuda'."
#endif

; ---- [Setup] Section ----
[Setup]
; Use the directly defined ActualAppId based on the flavor
AppId={#ActualAppId}
AppName={#MyAppName}{#FlavorDescription}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}{#FlavorDescription}
DefaultGroupName={#MyAppName}{#FlavorDescription}
LicenseFile=..\LICENSE
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64
PrivilegesRequired=admin
; Compression settings (optional)
;Compression=lzma2/ultra64
;SolidCompression=yes
OutputDir=..\dist
OutputBaseFilename=Transcribrr-windows-{#Flavour}-setup-{#MyAppVersion}
SetupIconFile=..\icons\app\app_icon.ico
; Use the ACTUAL EXE for the uninstall icon reference if possible, otherwise use the setup icon
UninstallDisplayIcon={app}\{#MyAppActualExeName}
UninstallDisplayName={#MyAppName}{#FlavorDescription}
DisableWelcomePage=no
DisableDirPage=no
DisableProgramGroupPage=no

; ---- [Languages] Section ----
[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

; ---- [Tasks] Section ----
[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
; Quick Launch task is mostly obsolete
; Name: "quicklaunchicon"; Description: "{cm:CreateQuickLaunchIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked; OnlyBelowVersion: 6.1; Check: not IsAdminInstallMode

; ---- [Files] Section ----
[Files]
; Source path is relative to the .iss script location.
; Copies everything from the corresponding dist/Transcribrr_<flavour> directory.
Source: "..\dist\Transcribrr_{#Flavour}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

; ---- [Icons] Section ----
; Use the correct MyAppActualExeName for shortcuts
[Icons]
; Start Menu shortcut
Name: "{group}\{#MyAppName}{#FlavorDescription}"; Filename: "{app}\{#MyAppActualExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\icons\app\app_icon.ico"
; Start Menu > Uninstall shortcut
Name: "{group}\{cm:UninstallProgram,{#MyAppName}{#FlavorDescription}}"; Filename: "{uninstallexe}"
; Desktop shortcut (optional task)
Name: "{autodesktop}\{#MyAppName}{#FlavorDescription}"; Filename: "{app}\{#MyAppActualExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\icons\app\app_icon.ico"; Tasks: desktopicon

; ---- [Run] Section ----
; Use the correct MyAppActualExeName for post-install launch
[Run]
Filename: "{app}\{#MyAppActualExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

; ---- [UninstallDelete] Section ----
; REMOVED automatic deletion of user data - this is generally safer.
; Users can manually delete %LOCALAPPDATA%\Transcribrr if desired.
; [UninstallDelete]
; Type: filesandordirs; Name: "{localappdata}\{#MyAppName}"