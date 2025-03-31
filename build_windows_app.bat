@echo off
:: Script to build a standalone Windows application

:: App information
set APP_NAME=Transcribrr
set VERSION=1.0.0
set OUTPUT_DIR=dist\%APP_NAME%

echo Building %APP_NAME% version %VERSION% for Windows...

:: Check if Python is installed
python --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo Error: Python is not installed or not in PATH
    exit /b 1
)

:: Check if ffmpeg is installed
where ffmpeg >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo Warning: ffmpeg not found in PATH
    echo You will need to manually install ffmpeg and add it to PATH
    echo Visit https://ffmpeg.org/download.html for installation instructions
    choice /c YN /m "Continue without ffmpeg?"
    if %ERRORLEVEL% EQU 2 exit /b 1
)

:: Create directories
echo Creating application structure...
if exist %OUTPUT_DIR% (
    echo Removing existing build directory...
    rmdir /s /q %OUTPUT_DIR%
)

mkdir %OUTPUT_DIR%
mkdir %OUTPUT_DIR%\icons
mkdir %OUTPUT_DIR%\icons\status
mkdir %OUTPUT_DIR%\app
mkdir %OUTPUT_DIR%\Recordings
mkdir %OUTPUT_DIR%\database
mkdir %OUTPUT_DIR%\logs
mkdir %OUTPUT_DIR%\bin

:: Copy resources
echo Copying resources...
xcopy /E /I icons %OUTPUT_DIR%\icons
:: Ensure status icons are copied to the expected location
xcopy /Y icons\status\*.* %OUTPUT_DIR%\icons\status\
xcopy /E /I app %OUTPUT_DIR%\app
copy config.json %OUTPUT_DIR%\
copy preset_prompts.json %OUTPUT_DIR%\
copy main.py %OUTPUT_DIR%\

:: Create a virtual environment in the application directory
echo Creating virtual environment...
python -m venv %OUTPUT_DIR%\venv

:: Install dependencies in the virtual environment
echo Installing dependencies...
%OUTPUT_DIR%\venv\Scripts\pip install --upgrade pip
%OUTPUT_DIR%\venv\Scripts\pip install PyQt6 PyQt6-Qt6 appdirs colorlog
%OUTPUT_DIR%\venv\Scripts\pip install -r requirements.txt

:: Download CA certificates
echo Downloading CA certificates...
powershell -Command "Invoke-WebRequest -Uri https://curl.se/ca/cacert.pem -OutFile %OUTPUT_DIR%\cacert.pem"

:: Copy ffmpeg binaries if available
echo Copying ffmpeg binaries...
where ffmpeg >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    where ffmpeg > temp_ffmpeg_path.txt
    where ffprobe > temp_ffprobe_path.txt
    set /p FFMPEG_PATH=<temp_ffmpeg_path.txt
    set /p FFPROBE_PATH=<temp_ffprobe_path.txt
    del temp_ffmpeg_path.txt
    del temp_ffprobe_path.txt
    
    copy "%FFMPEG_PATH%" %OUTPUT_DIR%\bin\ffmpeg.exe
    copy "%FFPROBE_PATH%" %OUTPUT_DIR%\bin\ffprobe.exe
    echo FFmpeg binaries copied successfully.
) else (
    echo Warning: Could not find ffmpeg or ffprobe executables.
    echo Your app may not work correctly without these binaries.
)

:: Create launcher batch file
echo Creating launcher script...
(
echo @echo off
echo :: Launcher for %APP_NAME%
echo setlocal
echo set SCRIPT_DIR=%%~dp0
echo set PYTHONPATH=%%SCRIPT_DIR%%
echo set SSL_CERT_FILE=%%SCRIPT_DIR%%cacert.pem
echo set PATH=%%SCRIPT_DIR%%bin;%%PATH%%
echo.
echo :: Log startup info
echo echo Starting application at %%date%% %%time%% ^> %%SCRIPT_DIR%%logs\launch.log
echo echo SCRIPT_DIR: %%SCRIPT_DIR%% ^>^> %%SCRIPT_DIR%%logs\launch.log
echo echo PYTHONPATH: %%PYTHONPATH%% ^>^> %%SCRIPT_DIR%%logs\launch.log
echo.
echo :: Activate the virtual environment and run the app
echo call %%SCRIPT_DIR%%venv\Scripts\activate.bat
echo cd %%SCRIPT_DIR%%
echo python main.py
echo.
echo :: Deactivate the virtual environment when done
echo deactivate
echo endlocal
) > %OUTPUT_DIR%\%APP_NAME%.bat

:: Create short startup script (for desktop shortcut)
echo Creating executable wrapper...
(
echo @echo off
echo start "" /D "%~dp0" "%~dp0%APP_NAME%.bat"
) > %OUTPUT_DIR%\Start%APP_NAME%.bat

echo.
echo Build completed successfully! App is located at: %OUTPUT_DIR%
echo.
echo To create a desktop shortcut:
echo 1. Right-click on Start%APP_NAME%.bat
echo 2. Select "Create shortcut"
echo 3. Move the shortcut to your desktop
echo 4. Right-click the shortcut and select Properties to customize the icon
echo.
echo Note: You may want to package this directory into an installer using a tool
echo       like NSIS (https://nsis.sourceforge.io) or Inno Setup (https://jrsoftware.org/isinfo.php)