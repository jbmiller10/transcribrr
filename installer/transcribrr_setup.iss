; Inno Setup Script for Transcribrr
; Version: 1.0

; ---- App Definition ----
#define MyAppName "Transcribrr"
#define MyAppPublisher "John Miller"
#define MyAppURL "https://github.com/johnmiller/transcribrr"
; Define the actual executable name produced by PyInstaller/Briefcase
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

#if Flavour == "cpu"
  #define FlavorName "CPU"
  #define FlavorDescription " (CPU Version)"
  #define OutputDirName "cpu"
  #define AppIdValue "{E5F78A54-F82A-49C3-A591-76A32F947A99}"
#elif Flavour == "cuda"
  #define FlavorName "CUDA"
  #define FlavorDescription " (CUDA Version)"
  #define OutputDirName "cuda"
  #define AppIdValue "{32D5F3F3-9A1B-4DA7-BEF3-0E66D22F7842}"
#endif

; ---- [Setup] Section ----
[Setup]
; AppId uniquely identifies this application version and flavor.
; Do not reuse GUIDs across different apps or incompatible versions.
AppId={#AppIdValue}
AppName={#MyAppName}{#FlavorDescription} ; Append description only if not default CPU
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
; Default installation directory: e.g., C:\Program Files\Transcribrr or C:\Program Files\Transcribrr (CUDA Version)
DefaultDirName={autopf}\{#MyAppName}{#FlavorDescription}
; Default Start Menu group name
DefaultGroupName={#MyAppName}{#FlavorDescription}
; Relative path to the license file from the installer script directory
LicenseFile=..\LICENSE
; Use modern wizard style
WizardStyle=modern
; Ensure installation into "Program Files" not "Program Files (x86)" on 64-bit Windows
ArchitecturesInstallIn64BitMode=x64
; Require admin rights for installation (needed for Program Files, Start Menu for all users)
PrivilegesRequired=admin
; Compression settings (optional, uncomment if needed)
; Compression=lzma2/ultra64
; SolidCompression=yes
; Output directory and filename for the setup executable
OutputDir=..\dist
OutputBaseFilename=Transcribrr-windows-{#Flavour}-setup-{#MyAppVersion} ; Include version in filename
; Icon for the setup executable
SetupIconFile=..\icons\app\app_icon.ico
; Icon shown in Programs and Features / Add/Remove Programs
UninstallDisplayIcon={app}\{#MyAppActualExeName}
; Name shown in Programs and Features / Add/Remove Programs
UninstallDisplayName={#MyAppName}{#FlavorDescription}
; Installer UI settings
DisableWelcomePage=no
DisableDirPage=no
DisableProgramGroupPage=no

; ---- [Languages] Section ----
[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

; ---- [Tasks] Section ----
; Optional tasks for the user during installation
[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
; Quick Launch is less relevant now, Taskbar pinning is manual. Keep for compatibility or remove.
Name: "quicklaunchicon"; Description: "{cm:CreateQuickLaunchIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked; OnlyBelowVersion: 6.1; Check: not IsAdminInstallMode

; ---- [Files] Section ----
; Specifies the files to be installed.
[Files]
; Source path is relative to the .iss script location.
; Copies everything from the corresponding dist/Transcribrr_<flavour> directory.
Source: "..\dist\Transcribrr_{#Flavour}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

; ---- [Icons] Section ----
; Creates shortcuts in the Start Menu and optionally on the Desktop/Quick Launch.
[Icons]
; Start Menu shortcut
Name: "{group}\{#MyAppName}{#FlavorDescription}"; Filename: "{app}\{#MyAppActualExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\icons\app\app_icon.ico"
; Start Menu > Uninstall shortcut
Name: "{group}\{cm:UninstallProgram,{#MyAppName}{#FlavorDescription}}"; Filename: "{uninstallexe}"
; Desktop shortcut (optional task)
Name: "{autodesktop}\{#MyAppName}{#FlavorDescription}"; Filename: "{app}\{#MyAppActualExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\icons\app\app_icon.ico"; Tasks: desktopicon

; ---- [Run] Section ----
; Actions to perform after installation is complete.
[Run]
; Option to launch the application immediately after installation.
Filename: "{app}\{#MyAppActualExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent