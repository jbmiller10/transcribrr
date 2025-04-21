@echo off
setlocal EnableDelayedExpansion

:: Script to build a standalone Windows application with optional CUDA support
:: FIXED Launcher Script Echoing

:: --- Configuration ---
set APP_NAME=Transcribrr
:: Extract version from app/__init__.py
for /f "tokens=*" %%a in ('python -c "import importlib.util, pathlib; p = pathlib.Path('app/__init__.py'); spec = importlib.util.spec_from_file_location('meta', p); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); print(m.__version__)"') do set VERSION=%%a
echo Building %APP_NAME% version %VERSION% for Windows...

:: -----------------------------------------------------------------
:: We decide on BUILD_TYPE (cpu / cuda) AFTER we have parsed any
:: command‑line arguments so that we don't accidentally create the
:: initial dist directory using the wrong target.  Therefore we only
:: define INSTALL_CUDA here and postpone creating BUILD_TYPE/OUTPUT_DIR
:: until the argument‑parsing section has finished.
:: -----------------------------------------------------------------

:: Default values
set INSTALL_CUDA=0
:: In GitHub Actions, python is already the latest 3.9.x
:: For local builds, try to use latest Python 3.9 specifically 
if defined GITHUB_ACTIONS (
    set PYTHON_EXECUTABLE=python
) else (
    set PYTHON_EXECUTABLE=py -3.9
)

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

:: ---------------------------------------------------------------
:: Determine build type (cpu / cuda) **after** parsing arguments
:: and create OUTPUT_DIR variable accordingly.
:: ---------------------------------------------------------------

if %INSTALL_CUDA% == 1 (
    set BUILD_TYPE=cuda
) else (
    set BUILD_TYPE=cpu
)

set OUTPUT_DIR=dist\%APP_NAME%_%BUILD_TYPE%

:: Check Python version
for /f "tokens=*" %%a in ('"%PYTHON_EXECUTABLE%" -c "import platform; print(platform.python_version())"') do set CURRENT_PY_VERSION=%%a
for /f "tokens=*" %%a in ('"%PYTHON_EXECUTABLE%" -c "import platform; v=platform.python_version().split('.'); print(f'{v[0]}.{v[1]}')"') do set MAJOR_MINOR=%%a
if "!MAJOR_MINOR!" NEQ "3.9" (
  echo Error: Expected Python 3.9.x for build, found !CURRENT_PY_VERSION!
  exit /b 1
)

:: --- Build Process ---
echo Building %APP_NAME% version %VERSION% for Windows...
if %INSTALL_CUDA% == 1 (
    echo *** CUDA build enabled ***
    echo Build directory: %OUTPUT_DIR%
) else (
    echo *** Standard CPU build ***
    echo Build directory: %OUTPUT_DIR%
)
echo.

:: Create ICO file for installer if it doesn't exist
echo --- Checking Icon Files ---
if not exist "icons\app\app_icon.ico" (
    echo Creating ICO file from SVG...
    %PYTHON_EXECUTABLE% -m pip install cairosvg Pillow
    %PYTHON_EXECUTABLE% create_ico.py
    if %ERRORLEVEL% NEQ 0 (
        echo Warning: Failed to create ICO file. Continuing without app icon.
    ) else (
        echo ICO file created successfully.
    )
) else (
    echo ICO file already exists.
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

:: Define path to python within the venv (without quotes)
set VENV_PYTHON=%OUTPUT_DIR%\venv\Scripts\%PYTHON_EXECUTABLE%

:: Install dependencies in the virtual environment
echo --- Installing Dependencies ---

:: Install base packages using python -m pip
echo   Installing base packages (PyQt6, appdirs, etc.)
"%VENV_PYTHON%" -m pip install PyQt6 PyQt6-Qt6 appdirs colorlog --log pip_base.log
if %ERRORLEVEL% NEQ 0 ( echo ERROR: Failed installing base packages. Check pip_base.log. & exit /b 1 )
echo   Base packages installed successfully.

:: Conditional PyTorch Installation using python -m pip
if %INSTALL_CUDA% == 1 (
    echo   Installing PyTorch with CUDA 11.8 support
    "%VENV_PYTHON%" -m pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118 --log pip_torch_cuda.log
    if %ERRORLEVEL% NEQ 0 ( echo ERROR: Failed installing PyTorch CUDA. Check pip_torch_cuda.log. & exit /b 1 )
    echo   PyTorch CUDA installed successfully.
) else (
    echo   Installing PyTorch (CPU version)
    "%VENV_PYTHON%" -m pip install torch torchvision torchaudio --log pip_torch_cpu.log
    if %ERRORLEVEL% NEQ 0 ( echo ERROR: Failed installing PyTorch CPU. Check pip_torch_cpu.log. & exit /b 1 )
    echo   PyTorch CPU installed successfully.
)

echo   Installing dependencies from requirements.txt
if exist requirements.txt (
    "%VENV_PYTHON%" -m pip install -r requirements.txt --log pip_reqs.log
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
    echo set VENV_PYTHON=%%SCRIPT_DIR%%venv\Scripts\python.exe
    echo set PYTHONPATH=%%SCRIPT_DIR%%
    echo set SSL_CERT_FILE=%%SCRIPT_DIR%%cacert.pem
    echo set PATH=%%SCRIPT_DIR%%bin;%%PATH%%
    echo set QT_PLUGIN_PATH=%%SCRIPT_DIR%%PyQt6\Qt6\plugins
    echo.
    echo :: Create logs dir if it doesn't exist
    echo if not exist "%%SCRIPT_DIR%%logs" mkdir "%%SCRIPT_DIR%%logs"
    echo.
    echo :: Log startup info
    echo echo Starting application at %%date%% %%time%% ^> "%%SCRIPT_DIR%%logs\launch.log"
    echo echo SCRIPT_DIR: %%SCRIPT_DIR%% ^>^> "%%SCRIPT_DIR%%logs\launch.log"
    echo echo VENV_PYTHON: %%VENV_PYTHON%% ^>^> "%%SCRIPT_DIR%%logs\launch.log"
    echo echo PYTHONPATH: %%PYTHONPATH%% ^>^> "%%SCRIPT_DIR%%logs\launch.log"
    echo echo PATH: %%PATH%% ^>^> "%%SCRIPT_DIR%%logs\launch.log"
    echo echo QT_PLUGIN_PATH: %%QT_PLUGIN_PATH%% ^>^> "%%SCRIPT_DIR%%logs\launch.log"
    echo.
    echo echo Running Python script using venv python... ^>^> "%%SCRIPT_DIR%%logs\launch.log"
    echo cd /d "%%SCRIPT_DIR%%"
    echo if exist "%%VENV_PYTHON%%" ^(
    echo   "%%VENV_PYTHON%%" main.py
    echo ^) else ^(
    echo   echo ERROR: venv Python not found at %%VENV_PYTHON%% ^>^> "%%SCRIPT_DIR%%logs\launch.log"
    echo   pause
    echo   exit /b 1
    echo ^)
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

:: --- Copy CUDA/VC++ Runtime DLLs if CUDA build ---
if %INSTALL_CUDA% == 1 (
    echo --- Copying CUDA/VC++ Runtime DLLs ---
    
    :: Check common locations for cuDNN DLLs (installed via choco or manual CUDA toolkit)
    set CUDNN_PATHS=
    set CUDNN_PATHS=%CUDNN_PATHS% "C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v11.8\bin"
    set CUDNN_PATHS=%CUDNN_PATHS% "C:\tools\cudnn\bin"
    set CUDNN_PATHS=%CUDNN_PATHS% "%CHOCOLATEYINSTALL%\lib\cudnn\tools\cuda\bin"

    :: Loop through possible paths and check for cuDNN DLLs
    set CUDNN_FOUND=0
    for %%p in (%CUDNN_PATHS%) do (
        if exist %%p\cudnn*.dll (
            echo Found cuDNN DLLs in %%p
            for %%f in (%%p\cudnn*.dll) do (
                echo   Copying %%~nxf to "%OUTPUT_DIR%\bin\"
                copy /Y "%%f" "%OUTPUT_DIR%\bin\" > nul
                set CUDNN_FOUND=1
            )
        )
    )

    :: Copy VC++ Runtime DLLs
    set VCRUNTIME_PATH=C:\Windows\System32
    echo Copying VC++ Runtime DLLs from %VCRUNTIME_PATH%
    if exist "%VCRUNTIME_PATH%\msvcp140.dll" copy /Y "%VCRUNTIME_PATH%\msvcp140.dll" "%OUTPUT_DIR%\bin\" > nul
    if exist "%VCRUNTIME_PATH%\vcruntime140.dll" copy /Y "%VCRUNTIME_PATH%\vcruntime140.dll" "%OUTPUT_DIR%\bin\" > nul
    if exist "%VCRUNTIME_PATH%\vcruntime140_1.dll" copy /Y "%VCRUNTIME_PATH%\vcruntime140_1.dll" "%OUTPUT_DIR%\bin\" > nul
    if exist "%VCRUNTIME_PATH%\msvcp140_1.dll" copy /Y "%VCRUNTIME_PATH%\msvcp140_1.dll" "%OUTPUT_DIR%\bin\" > nul
    if exist "%VCRUNTIME_PATH%\msvcp140_2.dll" copy /Y "%VCRUNTIME_PATH%\msvcp140_2.dll" "%OUTPUT_DIR%\bin\" > nul
    if exist "%VCRUNTIME_PATH%\concrt140.dll" copy /Y "%VCRUNTIME_PATH%\concrt140.dll" "%OUTPUT_DIR%\bin\" > nul

    :: Search for any CUDA DLLs in PyTorch directory to determine what's needed
    echo Searching for CUDA DLLs referenced by PyTorch...
    set TORCH_DIR="%OUTPUT_DIR%\venv\Lib\site-packages\torch\lib"
    if exist %TORCH_DIR% (
        dir /b %TORCH_DIR%\*.dll | findstr /i "cu" > cuda_dlls.txt
        for /F "tokens=*" %%f in (cuda_dlls.txt) do (
            echo   Found CUDA DLL: %%f
        )
        del cuda_dlls.txt
    )

    :: Check if we successfully copied cuDNN DLLs
    if %CUDNN_FOUND% == 0 (
        echo WARNING: Failed to find and copy cuDNN DLLs. CUDA build might fail at runtime.
        echo Searched paths:
        for %%p in (%CUDNN_PATHS%) do echo   - %%p
    ) else (
        echo CUDA/VC++ DLLs copied successfully to %OUTPUT_DIR%\bin\
    )
    echo.
)

:: --- Copy Qt6 plugins ---
echo --- Copying Qt6 Plugins ---
set QT_PLUGIN_PATH=%OUTPUT_DIR%\venv\Lib\site-packages\PyQt6\Qt6\plugins
if exist "%QT_PLUGIN_PATH%" (
    echo Qt6 plugins found at %QT_PLUGIN_PATH%
    
    :: Create target directory
    if not exist "%OUTPUT_DIR%\PyQt6\Qt6\plugins" mkdir "%OUTPUT_DIR%\PyQt6\Qt6\plugins"
    
    :: Copy the entire plugins directory
    echo Copying Qt6 plugins...
    xcopy /E /I /Y "%QT_PLUGIN_PATH%" "%OUTPUT_DIR%\PyQt6\Qt6\plugins\"
    echo Qt6 plugins copied successfully.
) else (
    echo Warning: Qt6 plugins directory not found at %QT_PLUGIN_PATH%
    echo The application may not display correctly.
)
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
    echo Build output directory: %OUTPUT_DIR% (case-sensitive)
) else (
    echo *** Build uses CPU-based PyTorch ***
    echo Build output directory: %OUTPUT_DIR% (case-sensitive)
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