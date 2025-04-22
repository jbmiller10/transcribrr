@echo off
setlocal EnableDelayedExpansion

:: Script to build a standalone Windows application with optional CUDA support

:: --- Configuration ---
set APP_NAME=Transcribrr
:: Will be extracted later after Python checks
set VERSION=?.?.?
echo Building %APP_NAME% for Windows...

:: Default values
set INSTALL_CUDA=0
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

:: --- Determine Build Type and Output Directory ---
if %INSTALL_CUDA% == 1 (
    set BUILD_TYPE=cuda
) else (
    set BUILD_TYPE=cpu
)
set OUTPUT_DIR=dist\%APP_NAME%_%BUILD_TYPE%

:: --- Verify Python Version ---
echo --- Checking Python Version ---
for /f "tokens=*" %%a in ('%PYTHON_EXECUTABLE% --version 2^>^&1') do set PYTHON_OUTPUT=%%a
echo Found Python: %PYTHON_OUTPUT%

for /f "tokens=*" %%a in ('%PYTHON_EXECUTABLE% -c "import platform; print(platform.python_version())"') do set CURRENT_PY_VERSION=%%a
for /f "tokens=*" %%a in ('%PYTHON_EXECUTABLE% -c "import platform; v=platform.python_version().split(\".\"); print(v[0] + \".\" + v[1])"') do set MAJOR_MINOR=%%a
if "!MAJOR_MINOR!" NEQ "3.9" (
  echo Error: Expected Python 3.9.x for build, found !CURRENT_PY_VERSION!
  exit /b 1
)
echo Python version 3.9 verified.
echo.

:: --- Extract Application Version ---
for /f "tokens=*" %%a in ('%PYTHON_EXECUTABLE% -c "import importlib.util, pathlib; p = pathlib.Path(\"app/__init__.py\"); spec = importlib.util.spec_from_file_location(\"meta\", p); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); print(m.__version__)"') do set VERSION=%%a
echo Detected app version: %VERSION%
echo.

:: --- Build Process Start ---
echo Building %APP_NAME% version %VERSION% for Windows...
if %INSTALL_CUDA% == 1 (
    echo *** CUDA build enabled ***
) else (
    echo *** Standard CPU build ***
)
echo Build directory: %OUTPUT_DIR%
echo.

:: --- Icon Check ---
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

:: --- FFmpeg Check ---
echo --- Checking FFmpeg ---
where ffmpeg >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo Warning: ffmpeg not found in PATH - attempting to continue.
) else (
    echo FFmpeg found.
)
echo.

:: --- Create Directories ---
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

:: --- Copy Resources ---
echo --- Copying Resources ---
xcopy /E /I /Q /Y icons "%OUTPUT_DIR%\icons\" > nul
xcopy /E /I /Q /Y icons\status\*.* "%OUTPUT_DIR%\icons\status\" > nul
xcopy /E /I /Q /Y app "%OUTPUT_DIR%\app\" > nul
if exist config.json copy /Y config.json "%OUTPUT_DIR%\" > nul
if exist preset_prompts.json copy /Y preset_prompts.json "%OUTPUT_DIR%\" > nul
copy /Y main.py "%OUTPUT_DIR%\" > nul
echo Resources copied.
echo.

:: --- Create Virtual Environment ---
echo --- Creating Virtual Environment ---
%PYTHON_EXECUTABLE% -m venv --copies "%OUTPUT_DIR%\venv"
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Failed to create virtual environment.
    exit /b 1
)
echo Virtual environment created.
echo.

:: --- Copy Core Python DLLs ---
echo --- Copying Core Python DLLs ---
for /f "tokens=*" %%a in ('where %PYTHON_EXECUTABLE%') do set BUILD_PYTHON_EXE=%%a
for %%i in ("%BUILD_PYTHON_EXE%") do set BUILD_PYTHON_DIR=%%~dpi
echo Build Python directory: %BUILD_PYTHON_DIR%
set DLL1=python3.dll
set DLL2=python39.dll
if exist "%BUILD_PYTHON_DIR%%DLL1%" (
    echo Copying %DLL1% to %OUTPUT_DIR%\
    copy /Y "%BUILD_PYTHON_DIR%%DLL1%" "%OUTPUT_DIR%\" > nul
) else (
    echo Warning: %DLL1% not found in %BUILD_PYTHON_DIR%
)
if exist "%BUILD_PYTHON_DIR%%DLL2%" (
    echo Copying %DLL2% to %OUTPUT_DIR%\
    copy /Y "%BUILD_PYTHON_DIR%%DLL2%" "%OUTPUT_DIR%\" > nul
) else (
    echo Warning: %DLL2% not found in %BUILD_PYTHON_DIR%
)
echo Core Python DLLs copied (if found).
echo.

:: --- Install Dependencies ---
set VENV_PYTHON=%OUTPUT_DIR%\venv\Scripts\python.exe
echo --- Installing Dependencies ---
echo   Installing base packages (PyQt6, appdirs, etc.)
"%VENV_PYTHON%" -m pip install PyQt6 PyQt6-Qt6 appdirs colorlog --log pip_base.log
if %ERRORLEVEL% NEQ 0 ( echo ERROR: Failed installing base packages. Check pip_base.log. & exit /b 1 )
echo   Base packages installed successfully.

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

:: --- Download CA Certificates ---
echo --- Downloading CA Certificates ---
powershell -Command "try { Invoke-WebRequest -Uri https://curl.se/ca/cacert.pem -OutFile '%OUTPUT_DIR%\cacert.pem' } catch { Write-Error $_; exit 1 }"
if %ERRORLEVEL% NEQ 0 ( echo ERROR downloading CA certificates & exit /b 1 )
echo CA Certificates downloaded.
echo.

:: --- Copy FFmpeg Binaries ---
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

:: --- Create Launcher Script ---
echo --- Creating Launcher Script ---

echo DEBUG: Checking variables before launcher creation...
echo DEBUG: OUTPUT_DIR is [%OUTPUT_DIR%]
echo DEBUG: APP_NAME is [%APP_NAME%]
if not exist "%OUTPUT_DIR%" echo ERROR: OUTPUT_DIR does not exist!

(
    echo @echo off
    echo :: Launcher for %APP_NAME%
    echo setlocal
	echo set "SCRIPT_DIR=%%~dp0%%"
	echo set "VENV_PYTHON=%%SCRIPT_DIR%%venv\Scripts\python.exe"
	echo set "PYTHONPATH=%%SCRIPT_DIR%%"
	echo set "SSL_CERT_FILE=%%SCRIPT_DIR%%cacert.pem"
	echo set "PATH=%%SCRIPT_DIR%%bin;%%PATH%%"
	echo set "QT_PLUGIN_PATH=%%SCRIPT_DIR%%PyQt6\Qt6\plugins"

	echo :: Log startup info
	echo ^>^> "%%LOG_FILE%%" echo Starting application at %%date%% %%time%%
	echo ^>^> "%%LOG_FILE%%" echo SCRIPT_DIR: %%SCRIPT_DIR%%
	echo ^>^> "%%LOG_FILE%%" echo VENV_PYTHON: %%VENV_PYTHON%%
	echo ^>^> "%%LOG_FILE%%" echo PYTHONPATH: %%PYTHONPATH%%
	echo ^>^> "%%LOG_FILE%%" echo PATH: %%PATH%%
	echo ^>^> "%%LOG_FILE%%" echo QT_PLUGIN_PATH: %%QT_PLUGIN_PATH%%

	echo cd /d "%%SCRIPT_DIR%%"
	echo if errorlevel 1 ^(
    echo   echo ERROR: Failed to change directory to %%SCRIPT_DIR%% ^>^> "%%LOG_FILE%%"
    echo   pause
    echo   exit /b 1
    echo ^)
    echo.
    echo echo Checking for Python at %%VENV_PYTHON%%... ^>^> "%%LOG_FILE%%"
	echo if exist "%%VENV_PYTHON%%" ^( goto :RunPython ^) else ^( goto :PythonNotFound ^)

    echo.
    echo :PythonNotFound
    echo   echo ERROR: venv Python not found at %%VENV_PYTHON%% ^>^> "%%LOG_FILE%%"
    echo   pause
    echo   set "EXIT_CODE=1"
    echo   goto :Finish
    echo.
    echo :RunPython
    echo   echo Found Python. Executing main.py... ^>^> "%%LOG_FILE%%"
    echo   "%%VENV_PYTHON%%" main.py
    echo   set "EXIT_CODE=%%ERRORLEVEL%%"
    echo   goto :Finish
    echo.
    echo :Finish
    echo echo Python script finished with exit code %%EXIT_CODE%% ^>^> "%%LOG_FILE%%"
    echo.
    echo endlocal
    echo exit /b %%EXIT_CODE%%
) > "%OUTPUT_DIR%\%APP_NAME%.bat"

if not exist "%OUTPUT_DIR%\%APP_NAME%.bat" (
    echo ERROR: Failed to create %APP_NAME%.bat in %OUTPUT_DIR%
    echo DEBUG: Last errorlevel was %ERRORLEVEL%
) else (
    echo Launcher script created successfully at %OUTPUT_DIR%\%APP_NAME%.bat
)
echo.

:: --- Create Executable Wrapper ---
echo --- Creating Executable Wrapper ---
(
    echo @echo off
    rem Wrapper to launch the main script from any shortcut location
    rem Use %%~dp0 so that the path is evaluated at runtime, not during build.
    echo start "" /D "%%~dp0" "%%~dp0%APP_NAME%.bat"
) > "%OUTPUT_DIR%\Start%APP_NAME%.bat"
echo Executable wrapper created.
echo.

:: --- Copy CUDA/VC++ Runtime DLLs if CUDA build ---
if %INSTALL_CUDA% == 0 goto SkipCudaDlls
echo --- Copying CUDA/VC++ Runtime DLLs ---
set CUDNN_PATHS=
set CUDNN_PATHS=%CUDNN_PATHS% "C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v11.8\bin"
set CUDNN_PATHS=%CUDNN_PATHS% "C:\tools\cudnn\bin"
set CUDNN_PATHS=%CUDNN_PATHS% "%CHOCOLATEYINSTALL%\lib\cudnn\tools\cuda\bin"
set CUDNN_FOUND=0
for %%p in (%CUDNN_PATHS%) do (
    if exist "%%~p\cudnn*.dll" (
        echo Found cuDNN DLLs in %%~p
        for %%f in ("%%~p\cudnn*.dll") do (
            echo   Copying %%~nxf to "%OUTPUT_DIR%\bin\"
            copy /Y "%%~f" "%OUTPUT_DIR%\bin\" > nul
            set CUDNN_FOUND=1
        )
    )
)
set VCRUNTIME_PATH=C:\Windows\System32
echo Copying VC++ Runtime DLLs from %VCRUNTIME_PATH%
if exist "%VCRUNTIME_PATH%\msvcp140.dll" copy /Y "%VCRUNTIME_PATH%\msvcp140.dll" "%OUTPUT_DIR%\bin\" > nul
if exist "%VCRUNTIME_PATH%\vcruntime140.dll" copy /Y "%VCRUNTIME_PATH%\vcruntime140.dll" "%OUTPUT_DIR%\bin\" > nul
if exist "%VCRUNTIME_PATH%\vcruntime140_1.dll" copy /Y "%VCRUNTIME_PATH%\vcruntime140_1.dll" "%OUTPUT_DIR%\bin\" > nul
if exist "%VCRUNTIME_PATH%\msvcp140_1.dll" copy /Y "%VCRUNTIME_PATH%\msvcp140_1.dll" "%OUTPUT_DIR%\bin\" > nul
if exist "%VCRUNTIME_PATH%\msvcp140_2.dll" copy /Y "%VCRUNTIME_PATH%\msvcp140_2.dll" "%OUTPUT_DIR%\bin\" > nul
if exist "%VCRUNTIME_PATH%\concrt140.dll" copy /Y "%VCRUNTIME_PATH%\concrt140.dll" "%OUTPUT_DIR%\bin\" > nul
echo Searching for CUDA DLLs referenced by PyTorch...
set TORCH_DIR="%OUTPUT_DIR%\venv\Lib\site-packages\torch\lib"
if exist %TORCH_DIR% (
    dir /b "%TORCH_DIR%\*.dll" | findstr /i "cu" > cuda_dlls.txt
    for /F "tokens=*" %%f in (cuda_dlls.txt) do (
        echo   Found CUDA DLL: %%f
    )
    del cuda_dlls.txt
)
if %CUDNN_FOUND% == 0 (
    echo WARNING: Failed to find and copy cuDNN DLLs. CUDA build might fail at runtime.
    echo Searched paths:
    for %%p in (%CUDNN_PATHS%) do echo   - %%~p
) else (
    echo CUDA/VC++ DLLs copied successfully to %OUTPUT_DIR%\bin\
)
echo.
:SkipCudaDlls

:: --- Copy Qt6 Plugins ---
echo --- Copying Qt6 Plugins ---
set QT_PLUGIN_PATH=%OUTPUT_DIR%\venv\Lib\site-packages\PyQt6\Qt6\plugins
if exist "%QT_PLUGIN_PATH%" (
    echo Qt6 plugins found at %QT_PLUGIN_PATH%
    if not exist "%OUTPUT_DIR%\PyQt6\Qt6\plugins" mkdir "%OUTPUT_DIR%\PyQt6\Qt6\plugins"
    echo Copying Qt6 plugins...
    xcopy /E /I /Y "%QT_PLUGIN_PATH%" "%OUTPUT_DIR%\PyQt6\Qt6\plugins\" > nul
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

:: --- Final Build Output Message ---
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