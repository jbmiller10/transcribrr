#!/bin/bash
# Script to build a standalone macOS app bundle

# Stop on errors
set -e

# App information
APP_NAME="Transcribrr"
VERSION="1.0.0"
BUNDLE_ID="com.transcribrr.app"

# Check if ffmpeg is installed
if ! command -v brew &> /dev/null; then
    echo "Error: Homebrew is required to install ffmpeg. Please install Homebrew first."
    echo "Visit https://brew.sh/ for installation instructions."
    exit 1
fi

# Check if portaudio is installed (Needed for PyAudio)
if ! brew list portaudio &> /dev/null; then
    echo "Installing portaudio via Homebrew (required for PyAudio)..."
    brew install portaudio
fi

# Check if ffmpeg is installed via Homebrew
if ! brew list ffmpeg &> /dev/null; then
    echo "Installing ffmpeg via Homebrew..."
    brew install ffmpeg
fi

# Create directories
echo "Creating app bundle structure..."
APP_DIR="dist/${APP_NAME}.app"
mkdir -p "${APP_DIR}/Contents/MacOS"
mkdir -p "${APP_DIR}/Contents/Resources"
mkdir -p "${APP_DIR}/Contents/Frameworks"

# Copy icon
echo "Copying icon..."
cp icons/app/app_icon.icns "${APP_DIR}/Contents/Resources/"

# Create Info.plist
echo "Creating Info.plist..."
cat > "${APP_DIR}/Contents/Info.plist" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleDevelopmentRegion</key>
    <string>English</string>
    <key>CFBundleDisplayName</key>
    <string>${APP_NAME}</string>
    <key>CFBundleExecutable</key>
    <string>${APP_NAME}</string>
    <key>CFBundleIconFile</key>
    <string>app_icon.icns</string>
    <key>CFBundleIdentifier</key>
    <string>${BUNDLE_ID}</string>
    <key>CFBundleInfoDictionaryVersion</key>
    <string>6.0</string>
    <key>CFBundleName</key>
    <string>${APP_NAME}</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleShortVersionString</key>
    <string>${VERSION}</string>
    <key>CFBundleVersion</key>
    <string>${VERSION}</string>
    <key>NSHighResolutionCapable</key>
    <true/>
    <key>NSRequiresAquaSystemAppearance</key>
    <false/>
    <key>NSMicrophoneUsageDescription</key>
    <string>${APP_NAME} needs access to the microphone for voice recording.</string>
</dict>
</plist>
EOF

# Create launcher script
echo "Creating launcher script..."
cat > "${APP_DIR}/Contents/MacOS/${APP_NAME}" << 'EOF'
#!/bin/bash

# Get the directory where this script is located
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
RESOURCES_DIR="$DIR/../Resources"

# Set Python environment variables
export PYTHONPATH="$RESOURCES_DIR:$PYTHONPATH"
# Don't set PYTHONHOME as it can cause problems with the venv
export SSL_CERT_FILE="$RESOURCES_DIR/cacert.pem"

# Activate the virtual environment using source
source "$RESOURCES_DIR/python/bin/activate"

# Echo diagnostic information to a log file
echo "Starting application at $(date)" > "$RESOURCES_DIR/logs/launch.log"
echo "RESOURCES_DIR: $RESOURCES_DIR" >> "$RESOURCES_DIR/logs/launch.log"
echo "PYTHONPATH: $PYTHONPATH" >> "$RESOURCES_DIR/logs/launch.log"
echo "PATH: $PATH" >> "$RESOURCES_DIR/logs/launch.log"
echo "Python executable: $(which python3)" >> "$RESOURCES_DIR/logs/launch.log"
echo "Python version: $(python3 --version)" >> "$RESOURCES_DIR/logs/launch.log"
# Consider limiting module output or removing if logs get too large
# echo "Available modules:" >> "$RESOURCES_DIR/logs/launch.log"
# python3 -c "import pkgutil; print([module.name for module in pkgutil.iter_modules()])" >> "$RESOURCES_DIR/logs/launch.log" 2>&1

# Launch the app with Python
cd "$RESOURCES_DIR"  # Change to resources directory before launching
echo "Launching main.py..." >> "$RESOURCES_DIR/logs/launch.log"
exec python3 "$RESOURCES_DIR/main.py" >> "$RESOURCES_DIR/logs/launch.log" 2>&1
EOF

# Make the launcher executable
chmod +x "${APP_DIR}/Contents/MacOS/${APP_NAME}"

# Copy resources
echo "Copying resources..."
mkdir -p "${APP_DIR}/Contents/Resources/icons/status"
mkdir -p "${APP_DIR}/Contents/Resources/app"
mkdir -p "${APP_DIR}/Contents/Resources/Recordings"
mkdir -p "${APP_DIR}/Contents/Resources/database"
mkdir -p "${APP_DIR}/Contents/Resources/logs"

# Copy directories first
cp -R icons "${APP_DIR}/Contents/Resources/"
cp -R app "${APP_DIR}/Contents/Resources/"

# Copy specific root files (handle potential absence)
cp main.py "${APP_DIR}/Contents/Resources/"
# Consider if config/prompts are truly needed *in the bundle* or just user data
# If they are default fallbacks, maybe copy them only if they exist
if [ -f config.json ]; then cp config.json "${APP_DIR}/Contents/Resources/"; fi
if [ -f preset_prompts.json ]; then cp preset_prompts.json "${APP_DIR}/Contents/Resources/"; fi

# Create a virtual environment in the Resources directory
# Use python3 explicitly
echo "Creating virtual environment using python3..."
python3 -m venv "${APP_DIR}/Contents/Resources/python"
if [ $? -ne 0 ]; then
    echo "Error: Failed to create virtual environment."
    exit 1
fi

# Install dependencies in the virtual environment
# Define python/pip executables within venv
VENV_PYTHON="${APP_DIR}/Contents/Resources/python/bin/python3"
VENV_PIP="${APP_DIR}/Contents/Resources/python/bin/pip3"

echo "Installing dependencies..."
"$VENV_PIP" install --upgrade pip
if [ $? -ne 0 ]; then echo "Error upgrading pip"; exit 1; fi

"$VENV_PIP" install PyQt6 PyQt6-Qt6 appdirs colorlog
if [ $? -ne 0 ]; then echo "Error installing base GUI packages"; exit 1; fi

# Install PyTorch (Remove from requirements.txt first!)
# Choose one: CPU or MPS (or add flag logic) - Assuming MPS for macOS build
echo "Installing PyTorch for Apple Silicon (MPS)..."
"$VENV_PIP" install torch torchvision torchaudio
if [ $? -ne 0 ]; then echo "Error installing PyTorch"; exit 1; fi

# Install remaining requirements
echo "Installing remaining dependencies from requirements.txt..."
if [ -f requirements.txt ]; then
    "$VENV_PIP" install -r requirements.txt
    if [ $? -ne 0 ]; then echo "Error installing from requirements.txt"; exit 1; fi
else
    echo "Warning: requirements.txt not found."
fi

# Download CA certificates
echo "Downloading CA certificates..."
curl -o "${APP_DIR}/Contents/Resources/cacert.pem" https://curl.se/ca/cacert.pem
if [ $? -ne 0 ]; then echo "Error downloading CA certificates"; exit 1; fi

# Copy ffmpeg binaries into the app bundle
echo "Copying ffmpeg binaries..."
FFMPEG_PATH=$(which ffmpeg)
FFPROBE_PATH=$(which ffprobe)

if [ -f "$FFMPEG_PATH" ] && [ -f "$FFPROBE_PATH" ]; then
    mkdir -p "${APP_DIR}/Contents/MacOS/bin"
    cp "$FFMPEG_PATH" "${APP_DIR}/Contents/MacOS/bin/"
    cp "$FFPROBE_PATH" "${APP_DIR}/Contents/MacOS/bin/"
    chmod +x "${APP_DIR}/Contents/MacOS/bin/ffmpeg"
    chmod +x "${APP_DIR}/Contents/MacOS/bin/ffprobe"
    echo "FFmpeg binaries copied successfully."
else
    echo "Warning: Could not find ffmpeg or ffprobe executables."
    echo "Your app may not work correctly without these binaries."
    # Consider exiting here if ffmpeg is essential: exit 1
fi

# Update the launcher script to include ffmpeg in PATH
# Use the corrected sed command
echo "Updating launcher script PATH..."
sed -i '' -e '/export PYTHONPATH/a\
# Add ffmpeg to PATH\
export PATH="$DIR/bin:$PATH"
' "${APP_DIR}/Contents/MacOS/${APP_NAME}"
if [ $? -ne 0 ]; then echo "Error updating launcher script PATH"; exit 1; fi


echo ""
echo "Build completed successfully! App is located at: ${APP_DIR}"