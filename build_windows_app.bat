@echo off
setlocal EnableDelayedExpansion

:: Script to build a standalone Windows application with optional CUDA support
:: All critical path‑quoting, error handling, and launcher‑logging issues fixed

:: --- Configuration ---
set "APP_NAME=Transcribrr"
:: Default version; overwritten after Python introspection
set "VERSION=1.0.0"
echo Building %APP_NAME% version %VERSION% for Windows...

:: -----------------------------------------------------------------
:: Decide on BUILD_TYPE (cpu / cuda) **after** parsing arguments
:: -----------------------------------------------------------------

set "INSTALL_CUDA=0"

:: Select python executable
if defined GITHUB_ACTIONS (
    set "PYTHON_EXECUTABLE=python"
) else (
    set "PYTHON_EXECUTABLE=py -3.9"
)

:: ---------------- Argument parsing ----------------
:ArgLoop
if "%~1"=="" goto ArgsDone
if /I "%~1"=="--cuda" (
    set "INSTALL_CUDA=1"
    echo CUDA installation requested.
) else if /I "%~1"=="--help" (
    goto :Usage
) else (
    echo Unknown argument: %~1
    goto :Usage
)
shift /1
goto ArgLoop
:ArgsDone

:: ---------------- Build type / output dir ----------------
if "%INSTALL_CUDA%"=="1" (
    set "BUILD_TYPE=cuda"
) else (
    set "BUILD_TYPE=cpu"
)
set "OUTPUT_DIR=dist\%APP_NAME%_%BUILD_TYPE%"

:: ---------------- Python version check ----------------
for /f "tokens=*" %%a in ('%PYTHON_EXECUTABLE% -c "import platform,sys;print(platform.python_version())"') do set "CURRENT_PY_VERSION=%%a"
for /f "tokens=*" %%a in ('%PYTHON_EXECUTABLE% -c "import platform,sys;v=platform.python_version().split(\".\");print(v[0]+'.'+v[1])"') do set "MAJOR_MINOR=%%a"
if "%MAJOR_MINOR%" NEQ "3.9" (
    echo Error: Expected Python 3.9.x but found %CURRENT_PY_VERSION%
    exit /b 1
)

:: Extract version from app/__init__.py
for /f "tokens=*" %%a in ('%PYTHON_EXECUTABLE% -c "import importlib.util,pathlib;spec=importlib.util.spec_from_file_location('meta',pathlib.Path('app/__init__.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);print(m.__version__)"') do set "VERSION=%%a"
echo Detected app version: %VERSION%

:: ---------------- Build banner ----------------
echo Building %APP_NAME% %VERSION% [%BUILD_TYPE%]
if "%INSTALL_CUDA%"=="1" echo *** CUDA build enabled ***
echo Build directory: %OUTPUT_DIR%
echo.

:: ---------------- Icon generation ----------------
echo --- Checking icon files ---
if not exist "icons\app\app_icon.ico" (
    echo Creating ICO file from SVG...
    %PYTHON_EXECUTABLE% -m pip install cairosvg Pillow
    if %ERRORLEVEL% NEQ 0 (
        echo WARNING: Failed to install icon dependencies.
    ) else (
        %PYTHON_EXECUTABLE% create_ico.py || echo WARNING: create_ico.py failed.
    )
) else (
    echo ICO file already exists.
)
echo.

:: ---------------- Tool availability checks ----------------
echo --- Checking Python ---
%PYTHON_EXECUTABLE% --version >nul 2>&1 || (echo Python not found & exit /b 1)
echo Python present.

echo --- Checking FFmpeg ---
where ffmpeg >nul 2>&1 && echo FFmpeg found. || echo WARNING: ffmpeg not in PATH.
echo.

:: ---------------- Directory setup ----------------
echo --- Preparing build directories ---
if exist "%OUTPUT_DIR%" (
    echo Removing previous build: %OUTPUT_DIR%
    rmdir /s /q "%OUTPUT_DIR%" || (echo ERROR: cannot clean build dir & exit /b 1)
)
for %%d in ("%OUTPUT_DIR%" "%OUTPUT_DIR%\icons" "%OUTPUT_DIR%\icons\status" "%OUTPUT_DIR%\app" "%OUTPUT_DIR%\Recordings" "%OUTPUT_DIR%\database" "%OUTPUT_DIR%\logs" "%OUTPUT_DIR%\bin") do mkdir "%%~d" >nul
echo Directories ready.

:: ---------------- Resource copy ----------------
echo --- Copying resources ---
xcopy /E /I /Q /Y "icons" "%OUTPUT_DIR%\icons\" >nul || (echo ERROR copying icons & exit /b 1)
xcopy /E /I /Q /Y "icons\status" "%OUTPUT_DIR%\icons\status\" >nul
xcopy /E /I /Q /Y "app" "%OUTPUT_DIR%\app\" >nul || (echo ERROR copying app & exit /b 1)
if exist config.json  copy /Y config.json  "%OUTPUT_DIR%" >nul
if exist preset_prompts.json copy /Y preset_prompts.json "%OUTPUT_DIR%" >nul
copy /Y main.py "%OUTPUT_DIR%" >nul || (echo ERROR copying main.py & exit /b 1)
echo Resources copied.

:: ---------------- Virtualenv ----------------
echo --- Creating venv ---
%PYTHON_EXECUTABLE% -m venv "%OUTPUT_DIR%\venv" || (echo ERROR creating venv & exit /b 1)
set "VENV_PY=%OUTPUT_DIR%\venv\Scripts\python.exe"
echo venv ready.

echo --- Installing dependencies ---
"%VENV_PY%" -m pip install PyQt6 PyQt6-Qt6 appdirs colorlog --log pip_base.log || (echo ERROR base deps & exit /b 1)
if "%INSTALL_CUDA%"=="1" (
    "%VENV_PY%" -m pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118 --log pip_torch_cuda.log || (echo ERROR torch cuda & exit /b 1)
) else (
    "%VENV_PY%" -m pip install torch torchvision torchaudio --log pip_torch_cpu.log || (echo ERROR torch cpu & exit /b 1)
)
if exist requirements.txt (
    "%VENV_PY%" -m pip install -r requirements.txt --log pip_reqs.log || (echo ERROR requirements.txt & exit /b 1)
)
echo Dependency installation done.

:: ---------------- CA certs ----------------
echo --- Downloading CA certificates ---
for /l %%R in (1,1,3) do (
    powershell -Command "try{Invoke-WebRequest -Uri https://curl.se/ca/cacert.pem -OutFile '%OUTPUT_DIR%\cacert.pem';exit 0}catch{exit 1}" && goto :CACertOK
    echo   Download attempt %%R failed. Retrying...
    timeout /t 2 >nul
)
echo WARNING: Failed to download cacert.pem after 3 attempts.
:CACertOK
echo.

:: ---------------- FFmpeg copy ----------------
echo --- Copying FFmpeg binaries ---
for /f "delims=" %%a in ('where ffmpeg 2^>nul') do set "FFMPEG_PATH=%%a" & goto :GotFFMPEG
set "FFMPEG_PATH="
:GotFFMPEG
for /f "delims=" %%a in ('where ffprobe 2^>nul') do set "FFPROBE_PATH=%%a" & goto :GotFFPROBE
set "FFPROBE_PATH="
:GotFFPROBE
if defined FFMPEG_PATH copy /Y "%FFMPEG_PATH%" "%OUTPUT_DIR%\bin\ffmpeg.exe" >nul
if defined FFPROBE_PATH copy /Y "%FFPROBE_PATH%" "%OUTPUT_DIR%\bin\ffprobe.exe" >nul
echo FFmpeg binaries handled.

:: ---------------- Launcher script ----------------
echo --- Creating launcher ---
(
    echo @echo off
    echo :: Launcher for %APP_NAME%
    echo setlocal
    echo set "SCRIPT_DIR=%%~dp0"
    echo set "VENV_PYTHON=%%SCRIPT_DIR%%venv\Scripts\python.exe"
    echo set "PYTHONPATH=%%SCRIPT_DIR%%"
    echo set "SSL_CERT_FILE=%%SCRIPT_DIR%%cacert.pem"
    echo set "PATH=%%SCRIPT_DIR%%bin\;%%PATH%%"
    echo set "QT_PLUGIN_PATH=%%SCRIPT_DIR%%PyQt6\Qt6\plugins"
    echo.
    echo if not exist "%%SCRIPT_DIR%%logs" mkdir "%%SCRIPT_DIR%%logs"
    echo.
    REM ==== CRITICAL FIX: REMOVED double 'echo' from logging commands ====
    echo Starting application at %%date%% %%time%% ^> "%%SCRIPT_DIR%%logs\launch.log"
    echo SCRIPT_DIR: %%SCRIPT_DIR%% ^>^> "%%SCRIPT_DIR%%logs\launch.log"
    echo VENV_PYTHON: %%VENV_PYTHON%% ^>^> "%%SCRIPT_DIR%%logs\launch.log"
    echo PYTHONPATH: %%PYTHONPATH%% ^>^> "%%SCRIPT_DIR%%logs\launch.log"
    echo PATH: %%PATH%% ^>^> "%%SCRIPT_DIR%%logs\launch.log"
    echo QT_PLUGIN_PATH: %%QT_PLUGIN_PATH%% ^>^> "%%SCRIPT_DIR%%logs\launch.log"
    echo.
    echo Running Python script using venv python... ^>^> "%%SCRIPT_DIR%%logs\launch.log"
    REM ==== End double 'echo' fix ====
    echo cd /d "%%SCRIPT_DIR%%"
    echo if exist "%%VENV_PYTHON%%" ^(
    echo     "%%VENV_PYTHON%%" main.py
    echo ^) else ^(
    REM ==== CRITICAL FIX: REMOVED double 'echo' from error logging ====
    echo     ERROR: venv Python not found at %%VENV_PYTHON%% ^>^> "%%SCRIPT_DIR%%logs\launch.log"
    echo     pause
    echo     exit /b 1
    echo ^)
    echo set "EXIT_CODE=%%ERRORLEVEL%%"
    REM ==== CRITICAL FIX: REMOVED double 'echo' from final status ====
    echo Python script finished with exit code %%EXIT_CODE%% ^>^> "%%SCRIPT_DIR%%logs\launch.log"
    echo endlocal
    echo exit /b %%EXIT_CODE%%
) > "%OUTPUT_DIR%\%APP_NAME%.bat"
echo Launcher created.

:: ---------------- Shortcut wrapper ----------------
echo --- Creating Executable Wrapper ---
(
    echo @echo off
    echo rem Wrapper to launch from shortcuts
    REM FIX: Reverted to 'start' for standard GUI shortcut behavior
    echo start "" /D "%%~dp0" "%%~dp0%APP_NAME%.bat"
) > "%OUTPUT_DIR%\Start%APP_NAME%.bat"
echo Wrapper created.

:: ---------------- CUDA / VC runtimes ----------------
if "%INSTALL_CUDA%"=="0" goto :SkipCuda
echo --- Copying CUDA / VC++ runtimes ---
set "CUDNN_PATHS=\"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v11.8\bin\" \"C:\tools\cudnn\bin\" \"%CHOCOLATEYINSTALL%\lib\cudnn\tools\cuda\bin\""
set "CUDNN_FOUND=0"
for %%p in (%CUDNN_PATHS%) do if exist "%%~p\cudnn*.dll" (
    for %%f in ("%%~p\cudnn*.dll") do copy /Y "%%~f" "%OUTPUT_DIR%\bin\" >nul & set "CUDNN_FOUND=1"
)
set "VCRUNTIME_PATH=C:\Windows\System32"
for %%d in (msvcp140.dll vcruntime140.dll vcruntime140_1.dll msvcp140_1.dll msvcp140_2.dll concrt140.dll) do if exist "%VCRUNTIME_PATH%\%%d" copy /Y "%VCRUNTIME_PATH%\%%d" "%OUTPUT_DIR%\bin\" >nul
if "%CUDNN_FOUND%"=="0" echo WARNING: cuDNN DLLs not found.
:SkipCuda

:: ---------------- Qt plugins ----------------
set "QT_PLUGIN_PATH=%OUTPUT_DIR%\venv\Lib\site-packages\PyQt6\Qt6\plugins"
if exist "%QT_PLUGIN_PATH%" (
    if not exist "%OUTPUT_DIR%\PyQt6\Qt6\plugins" mkdir "%OUTPUT_DIR%\PyQt6\Qt6\plugins"
    xcopy /E /I /Y "%QT_PLUGIN_PATH%" "%OUTPUT_DIR%\PyQt6\Qt6\plugins\" >nul || (echo ERROR copying Qt plugins & exit /b 1)
) else (
    echo WARNING: Qt plugin dir missing: %QT_PLUGIN_PATH%
)

:: ---------------- Finished ----------------
echo.
echo Build completed successfully.  Output: %OUTPUT_DIR%
if "%INSTALL_CUDA%"=="1" (
    echo Build includes CUDA‑enabled PyTorch.
) else (
    echo CPU‑only build.
)

goto :End

:Usage
echo.
echo Usage: %~nx0 [--cuda] [--help]
echo.
echo   --cuda    Build with CUDA 11.8 PyTorch wheels
echo   --help    Show this help message
echo.
goto :End

:End
endlocal