#!/bin/bash
# Script to build a standalone macOS app bundle

set -e

APP_NAME="Transcribrr"
VERSION="1.0.0"
BUNDLE_ID="com.transcribrr.app"

if ! command -v brew &> /dev/null; then
    echo "Error: Homebrew is required to install ffmpeg. Please install Homebrew first."
    echo "Visit https://brew.sh/ for installation instructions."
    exit 1
fi

if ! brew list ffmpeg &> /dev/null; then
    echo "Installing ffmpeg via Homebrew..."
    brew install ffmpeg
fi

echo "Creating app bundle structure..."
echo "Creating app bundle structure..."
APP_DIR="dist/${APP_NAME}.app"
mkdir -p "${APP_DIR}/Contents/MacOS"
mkdir -p "${APP_DIR}/Contents/Resources"
mkdir -p "${APP_DIR}/Contents/Frameworks"

echo "Copying icon..."
echo "Copying icon..."
cp icons/app/app_icon.icns "${APP_DIR}/Contents/Resources/"

echo "Creating Info.plist..."
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

echo "Creating launcher script..."
echo "Creating launcher script..."
cat > "${APP_DIR}/Contents/MacOS/${APP_NAME}" << 'EOF'
#!/bin/bash

# Get the directory where this script is located
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
RESOURCES_DIR="$DIR/../Resources"

export PYTHONPATH="$RESOURCES_DIR:$PYTHONPATH"
# Don't set PYTHONHOME as it can cause problems with the venv
export SSL_CERT_FILE="$RESOURCES_DIR/cacert.pem"

# Add ffmpeg to PATH
export PATH="$DIR/bin:$PATH"

# Use embedded Python framework
PY_VER=3.9
PY="@executable_path/../Frameworks/Python.framework/Versions/$PY_VER/bin/python3"

echo "Starting application at $(date)" > "$RESOURCES_DIR/launch.log"
echo "RESOURCES_DIR: $RESOURCES_DIR" >> "$RESOURCES_DIR/launch.log" 
echo "PYTHONPATH: $PYTHONPATH" >> "$RESOURCES_DIR/launch.log"
echo "PATH: $PATH" >> "$RESOURCES_DIR/launch.log"
echo "Python executable: $PY" >> "$RESOURCES_DIR/launch.log"
echo "Python version: $($PY --version)" >> "$RESOURCES_DIR/launch.log" 2>&1
echo "ffmpeg location: $(which ffmpeg)" >> "$RESOURCES_DIR/launch.log" 2>&1

cd "$RESOURCES_DIR"
exec "$PY" "$RESOURCES_DIR/main.py"
EOF

chmod +x "${APP_DIR}/Contents/MacOS/${APP_NAME}"

echo "Copying resources..."
echo "Copying resources..."
mkdir -p "${APP_DIR}/Contents/Resources/icons"
mkdir -p "${APP_DIR}/Contents/Resources/icons/status"
mkdir -p "${APP_DIR}/Contents/Resources/app"
mkdir -p "${APP_DIR}/Contents/Resources/Recordings"
mkdir -p "${APP_DIR}/Contents/Resources/database"
mkdir -p "${APP_DIR}/Contents/Resources/logs"

cp -f icons/status/audio.svg "${APP_DIR}/Contents/Resources/icons/"
cp -f icons/status/video.svg "${APP_DIR}/Contents/Resources/icons/"
cp -f icons/status/file.svg "${APP_DIR}/Contents/Resources/icons/"

# Now copy all icons
cp -r icons "${APP_DIR}/Contents/Resources/"
# Ensure status icons are also copied to the expected location
cp -f icons/status/* "${APP_DIR}/Contents/Resources/icons/status/"
cp -r app "${APP_DIR}/Contents/Resources/"
cp config.json "${APP_DIR}/Contents/Resources/"
cp preset_prompts.json "${APP_DIR}/Contents/Resources/"
cp main.py "${APP_DIR}/Contents/Resources/"

# Copy Python framework
PY_VER=3.9
echo "Copying Python framework..."
FW_SRC="$(brew --prefix)/Frameworks/Python.framework"
FW_DST="${APP_DIR}/Contents/Frameworks/Python.framework"
cp -R "$FW_SRC" "$FW_DST"

echo "Installing dependencies..."
"${APP_DIR}/Contents/Frameworks/Python.framework/Versions/$PY_VER/bin/pip3" install --upgrade pip
"${APP_DIR}/Contents/Frameworks/Python.framework/Versions/$PY_VER/bin/pip3" install PyQt6 PyQt6-Qt6 appdirs colorlog
"${APP_DIR}/Contents/Frameworks/Python.framework/Versions/$PY_VER/bin/pip3" install -r requirements.txt

echo "Downloading CA certificates..."
echo "Downloading CA certificates..."
curl -o "${APP_DIR}/Contents/Resources/cacert.pem" https://curl.se/ca/cacert.pem

echo "Copying ffmpeg binaries..."
echo "Copying ffmpeg binaries..."
FFMPEG_PATH=$(which ffmpeg)
FFPROBE_PATH=$(which ffprobe)

if [ -f "$FFMPEG_PATH" ] && [ -f "$FFPROBE_PATH" ]; then
    mkdir -p "${APP_DIR}/Contents/MacOS/bin"
    
chmod 755 "${APP_DIR}/Contents/MacOS/bin"
    
    # Use sudo for the copy operation if necessary
    echo "Copying FFmpeg and FFprobe (may require your password)..."
    if ! cp "$FFMPEG_PATH" "${APP_DIR}/Contents/MacOS/bin/"; then
        echo "Using sudo to copy FFmpeg..."
        sudo cp "$FFMPEG_PATH" "${APP_DIR}/Contents/MacOS/bin/"
        sudo chown $(whoami) "${APP_DIR}/Contents/MacOS/bin/ffmpeg"
    fi
    
    if ! cp "$FFPROBE_PATH" "${APP_DIR}/Contents/MacOS/bin/"; then
        echo "Using sudo to copy FFprobe..."
        sudo cp "$FFPROBE_PATH" "${APP_DIR}/Contents/MacOS/bin/"
        sudo chown $(whoami) "${APP_DIR}/Contents/MacOS/bin/ffprobe"
    fi
    
    # Make executables executable
    chmod 755 "${APP_DIR}/Contents/MacOS/bin/ffmpeg"
    chmod 755 "${APP_DIR}/Contents/MacOS/bin/ffprobe"
    echo "FFmpeg binaries copied successfully."
else
    echo "Warning: Could not find ffmpeg or ffprobe executables."
    echo "Your app may not work correctly without these binaries."
fi

# Ensure executable permissions
chmod +x "${APP_DIR}/Contents/MacOS/${APP_NAME}"

echo "Build completed successfully! App is located at: ${APP_DIR}"