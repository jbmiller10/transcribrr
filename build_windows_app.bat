@echo off
setlocal EnableDelayedExpansion

:: Script to build a standalone Windows application with optional CUDA support
:: FIXED Pip Invocation & Echo Syntax

:: --- Configuration ---
set APP_NAME=Transcribrr
set VERSION=1.0.0
set OUTPUT_DIR=dist\%APP_NAME%
set PYTHON_EXECUTABLE=python

:: --- Default values ---
set INSTALL_CUDA=0 REM Use 0 for false, 1 for true

:: --- Argument Parsing ---
:ArgLoop
if "%1"=="" goto ArgsDone
if /I "%1"=="--cuda" (
    set INSTALL_CUDA=1
    echo CUDA installation requested.
) else if /I "%1"=="--help" (
    call :Usage
    exit /b 0
) else (
    echo Unknown argument: %1
    call :Usage
    exit /b 1
)
shift /1
goto ArgLoop
:ArgsDone

:: --- Build Process ---
echo Building %APP_NAME% version %VERSION% for Windows...
if %INSTALL_CUDA% == 1 (
    echo *** CUDA build enabled ***
) else (
    echo *** Standard CPU build ***
)
echo.

:: Check if Python is installed
echo --- Checking Python ---
%PYTHON_EXECUTABLE% --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo Error: Python is not installed or not in PATH
    exit /b 1
)
echo Python check OK. (%PYTHON_EXECUTABLE% --version)
echo.

:: Check if ffmpeg is installed
echo --- Checking FFmpeg ---
where ffmpeg >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo Warning: ffmpeg not found in PATH - attempting to continue.
) else (
    echo FFmpeg found.
)
echo.

:: Create directories
echo --- Creating Directories ---
if exist "%OUTPUT_DIR%" (
    echo Removing existing build directory...
    rmdir /s /q "%OUTPUT_DIR%"
)
mkdir "%OUTPUT_DIR%"
mkdir "%OUTPUT_DIR%\icons"
mkdir "%OUTPUT_DIR%\icons\status"
mkdir "%OUTPUT_DIR%\app"
mkdir "%OUTPUT_DIR%\Recordings"
mkdir "%OUTPUT_DIR%\database"
mkdir "%OUTPUT_DIR%\logs"
mkdir "%OUTPUT_DIR%\bin"
echo Directories created.
echo.

:: Copy resources
echo --- Copying Resources ---
xcopy /E /I /Q /Y icons "%OUTPUT_DIR%\icons\"
xcopy /E /I /Q /Y icons\status\*.* "%OUTPUT_DIR%\icons\status\"
xcopy /E /I /Q /Y app "%OUTPUT_DIR%\app\"
if exist config.json copy /Y config.json "%OUTPUT_DIR%\"
if exist preset_prompts.json copy /Y preset_prompts.json "%OUTPUT_DIR%\"
copy /Y main.py "%OUTPUT_DIR%\"
echo Resources copied.
echo.

:: Create a virtual environment in the application directory
echo --- Creating Virtual Environment ---
%PYTHON_EXECUTABLE% -m venv "%OUTPUT_DIR%\venv"
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Failed to create virtual environment.
    exit /b 1
)
echo Virtual environment created.
echo.

:: Define path to python within the venv
set VENV_PYTHON="%OUTPUT_DIR%\venv\Scripts\%PYTHON_EXECUTABLE%"

:: Install dependencies in the virtual environment
echo --- Installing Dependencies ---

:: Install base packages using python -m pip
echo   Installing base packages (PyQt6, appdirs, etc.)
%VENV_PYTHON% -m pip install PyQt6 PyQt6-Qt6 appdirs colorlog --log pip_base.log
if %ERRORLEVEL% NEQ 0 ( echo ERROR: Failed installing base packages. Check pip_base.log. & exit /b 1 )
echo   Base packages installed successfully.

:: Conditional PyTorch Installation using python -m pip
if %INSTALL_CUDA% == 1 (
    echo   Installing PyTorch with CUDA 11.8 support
    %VENV_PYTHON% -m pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118 --log pip_torch_cuda.log
    if %ERRORLEVEL% NEQ 0 ( echo ERROR: Failed installing PyTorch CUDA. Check pip_torch_cuda.log. & exit /b 1 )
    echo   PyTorch CUDA installed successfully.
) else (
    echo   Installing PyTorch (CPU version)
    %VENV_PYTHON% -m pip install torch torchvision torchaudio --log pip_torch_cpu.log
    if %ERRORLEVEL% NEQ 0 ( echo ERROR: Failed installing PyTorch CPU. Check pip_torch_cpu.log. & exit /b 1 )
    echo   PyTorch CPU installed successfully.
)

:: Install remaining dependencies from requirements.txt using python -m pip
:: IMPORTANT: torch, torchvision, torchaudio should NOT be in requirements.txt
echo   Installing dependencies from requirements.txt
if exist requirements.txt (
    %VENV_PYTHON% -m pip install -r requirements.txt --log pip_reqs.log
    if %ERRORLEVEL% NEQ 0 ( echo ERROR: Failed installing from requirements.txt. Check pip_reqs.log. & exit /b 1 )
    echo   Dependencies from requirements.txt installed successfully.
) else (
    echo     Warning: requirements.txt not found. Skipping.
)

echo --- Dependency Installation Complete ---
echo.

:: Download CA certificates
echo --- Downloading CA Certificates ---
powershell -Command "try { Invoke-WebRequest -Uri https://curl.se/ca/cacert.pem -OutFile '%OUTPUT_DIR%\cacert.pem' } catch { Write-Error $_; exit 1 }"
if %ERRORLEVEL% NEQ 0 ( echo ERROR downloading CA certificates & exit /b 1 )
echo CA Certificates downloaded.
echo.

:: Copy ffmpeg binaries if available
echo --- Copying FFmpeg Binaries ---
where ffmpeg >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    where ffmpeg > temp_ffmpeg_path.txt
    where ffprobe > temp_ffprobe_path.txt
    set /p FFMPEG_PATH=<temp_ffmpeg_path.txt
    set /p FFPROBE_PATH=<temp_ffprobe_path.txt
    del temp_ffmpeg_path.txt
    del temp_ffprobe_path.txt

    copy /Y "%FFMPEG_PATH%" "%OUTPUT_DIR%\bin\ffmpeg.exe" > nul
    copy /Y "%FFPROBE_PATH%" "%OUTPUT_DIR%\bin\ffprobe.exe" > nul
    echo FFmpeg binaries copied successfully.
) else (
    echo Warning: Could not find ffmpeg or ffprobe executables.
)
echo.

:: Create launcher batch file
echo --- Creating Launcher Script ---
(
    echo @echo off
    echo :: Launcher for %APP_NAME%
    echo setlocal
    echo set SCRIPT_DIR=%%~dp0
    echo set VENV_PYTHON="%%SCRIPT_DIR%%venv\Scripts\python.exe"
    echo set PYTHONPATH=%%SCRIPT_DIR%%
    echo set SSL_CERT_FILE=%%SCRIPT_DIR%%cacert.pem
    echo set PATH=%%SCRIPT_DIR%%bin;%%PATH%%
    echo.
    echo :: Log startup info
    echo echo Starting application at %%date%% %%time%% ^> "%%SCRIPT_DIR%%logs\launch.log"
    echo echo SCRIPT_DIR: %%SCRIPT_DIR%% ^>^> "%%SCRIPT_DIR%%logs\launch.log"
    echo echo VENV_PYTHON: %%VENV_PYTHON%% ^>^> "%%SCRIPT_DIR%%logs\launch.log"
    echo echo PYTHONPATH: %%PYTHONPATH%% ^>^> "%%SCRIPT_DIR%%logs\launch.log"
    echo echo PATH: %%PATH%% ^>^> "%%SCRIPT_DIR%%logs\launch.log"
    echo.
    echo :: Activate venv (implicit by using venv python) and run app
    echo echo Running Python script using venv python... ^>^> "%%SCRIPT_DIR%%logs\launch.log"
    echo cd /d "%%SCRIPT_DIR%%"
    echo if exist %%VENV_PYTHON%% (
    echo   %%VENV_PYTHON%% main.py
    echo ) else (
    echo   echo ERROR: venv Python not found at %%VENV_PYTHON%% ^>^> "%%SCRIPT_DIR%%logs\launch.log"
    echo   pause
    echo   exit /b 1
    echo )
    echo set EXIT_CODE=%%ERRORLEVEL%%
    echo echo Python script finished with exit code %%EXIT_CODE%% ^>^> "%%SCRIPT_DIR%%logs\launch.log"
    echo.
    echo endlocal
    echo exit /b %%EXIT_CODE%%
) > "%OUTPUT_DIR%\%APP_NAME%.bat"
echo Launcher script created.
echo.

:: Create short startup script (for desktop shortcut)
echo --- Creating Executable Wrapper ---
(
    echo @echo off
    echo start "" /D "%~dp0" "%~dp0%APP_NAME%.bat"
) > "%OUTPUT_DIR%\Start%APP_NAME%.bat"
echo Executable wrapper created.
echo.

:: --- Verify venv contents ---
echo --- Listing venv/Lib/site-packages ---
dir "%OUTPUT_DIR%\venv\Lib\site-packages" /b
echo --- Listing complete ---
echo.

echo.
echo Build completed successfully! App is located at: %OUTPUT_DIR%
if %INSTALL_CUDA% == 1 (
    echo *** Build includes CUDA-enabled PyTorch ***
) else (
    echo *** Build uses CPU-based PyTorch ***
)
echo.
goto End

:Usage
echo.
echo Usage: %~nx0 [--cuda] [--help]
echo Builds the %APP_NAME% application for Windows.
echo.
echo Options:
echo   --cuda    Install PyTorch with CUDA 11.8 support. Requires compatible NVIDIA GPU.
echo   --help    Display this help message.
echo.
goto End

:End
endlocal