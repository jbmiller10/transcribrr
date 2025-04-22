#!/bin/bash
# Script to build a standalone macOS app bundle for GitHub Actions

# Stop on errors
set -e

# Verify correct Python version
CURRENT_PY_VERSION=$(python3 -c "import platform; print(platform.python_version())")
MAJOR_MINOR=$(python3 -c "import platform; v=platform.python_version().split('.'); print(f'{v[0]}.{v[1]}')")
if [ "$MAJOR_MINOR" != "3.9" ]; then
  echo "Error: Expected Python 3.9.x for build, found $CURRENT_PY_VERSION"
  exit 1
fi

# App information
APP_NAME="Transcribrr"
# Extract version from app/__init__.py
VERSION=$(python3 - <<'PY'
import importlib.util, pathlib, sys
p = pathlib.Path('app/__init__.py')
spec = importlib.util.spec_from_file_location('meta', p)
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
print(m.__version__)
PY)
BUNDLE_ID="com.transcribrr.app"

echo "Building $APP_NAME version $VERSION for macOS..."

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

# Create launcher script - MODIFIED TO INCLUDE FFMPEG PATH DIRECTLY
echo "Creating launcher script..."
cat > "${APP_DIR}/Contents/MacOS/${APP_NAME}" << 'EOF'
#!/bin/bash

# Get the directory where this script is located
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
RESOURCES_DIR="$DIR/../Resources"

# Set Python environment variables
export PYTHONPATH="$RESOURCES_DIR:$PYTHONPATH"
# Don't set PYTHONHOME as it can cause problems with the venv

# Add ffmpeg to PATH
export PATH="$DIR/bin:$PATH"

export SSL_CERT_FILE="$RESOURCES_DIR/cacert.pem"

# Set Qt plugins path to find platform plugins
export QT_PLUGIN_PATH="@executable_path/../PlugIns"

# Create a user-writable log directory in ~/Library/Application Support
APP_SUPPORT_DIR="$HOME/Library/Application Support/Transcribrr"
APP_LOGS_DIR="$APP_SUPPORT_DIR/logs"
mkdir -p "$APP_LOGS_DIR"

# Create a user data directory if it doesn't exist
mkdir -p "$APP_SUPPORT_DIR/Recordings"
mkdir -p "$APP_SUPPORT_DIR/database"

# Use embedded Python framework or system Python if not found
PY_VER=3.9
PY="$DIR/../Frameworks/Python.framework/Versions/$PY_VER/bin/python3"

# Echo diagnostic information to a log file in the user-writable directory
echo "Starting application at $(date)" > "$APP_LOGS_DIR/launch.log"
echo "RESOURCES_DIR: $RESOURCES_DIR" >> "$APP_LOGS_DIR/launch.log" 
echo "APP_SUPPORT_DIR: $APP_SUPPORT_DIR" >> "$APP_LOGS_DIR/launch.log"
echo "PYTHONPATH: $PYTHONPATH" >> "$APP_LOGS_DIR/launch.log"
echo "PATH: $PATH" >> "$APP_LOGS_DIR/launch.log"
echo "QT_PLUGIN_PATH: $QT_PLUGIN_PATH" >> "$APP_LOGS_DIR/launch.log"

# Check if the embedded Python exists, fall back to system Python if needed
if [ ! -f "$PY" ]; then
  echo "Embedded Python not found, using system Python" >> "$APP_LOGS_DIR/launch.log"
  PY=$(which python3)
fi

echo "Python executable: $PY" >> "$APP_LOGS_DIR/launch.log"
echo "Python version: $($PY --version)" >> "$APP_LOGS_DIR/launch.log" 2>&1
echo "ffmpeg location: $(which ffmpeg)" >> "$APP_LOGS_DIR/launch.log" 2>&1

# Set environment variable to tell the app to use the user data directory
export TRANSCRIBRR_USER_DATA_DIR="$APP_SUPPORT_DIR"

# Launch the app with Python
cd "$RESOURCES_DIR"  # Change to resources directory before launching
exec "$PY" "$RESOURCES_DIR/main.py"
EOF

# Make the launcher executable
chmod +x "${APP_DIR}/Contents/MacOS/${APP_NAME}"

# Copy resources 
echo "Copying resources..."
mkdir -p "${APP_DIR}/Contents/Resources/icons"
mkdir -p "${APP_DIR}/Contents/Resources/icons/status"
mkdir -p "${APP_DIR}/Contents/Resources/app"
mkdir -p "${APP_DIR}/Contents/Resources/Recordings"
mkdir -p "${APP_DIR}/Contents/Resources/database"
mkdir -p "${APP_DIR}/Contents/Resources/logs"

# Copy specific SVG files that the app is looking for
cp -f icons/status/audio.svg "${APP_DIR}/Contents/Resources/icons/"
cp -f icons/status/video.svg "${APP_DIR}/Contents/Resources/icons/"
cp -f icons/status/file.svg "${APP_DIR}/Contents/Resources/icons/"

# Now copy all icons with proper structure
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

# Debug Python location
echo "Python executable path: $(which python3)"
echo "Python version: $(python3 --version)"
echo "Python framework path check:"
ls -la /Library/Frameworks/Python.framework/Versions/ 2>/dev/null || echo "No framework in /Library/Frameworks"
ls -la "$(brew --prefix)/Frameworks/Python.framework/Versions/" 2>/dev/null || echo "No framework in brew prefix"
ls -la "$HOME/Library/Frameworks/Python.framework/Versions/" 2>/dev/null || echo "No framework in user Library"

# Look for Python framework in different locations
if [ -d "/Library/Frameworks/Python.framework" ]; then
  FW_SRC="/Library/Frameworks/Python.framework"
elif [ -d "$(brew --prefix)/Frameworks/Python.framework" ]; then
  FW_SRC="$(brew --prefix)/Frameworks/Python.framework"
elif [ -d "$HOME/Library/Frameworks/Python.framework" ]; then
  FW_SRC="$HOME/Library/Frameworks/Python.framework"
else
  echo "ERROR: Could not find Python.framework. Will attempt to use system Python."
  # Create the framework directory structure
  mkdir -p "${APP_DIR}/Contents/Frameworks/Python.framework/Versions/$PY_VER/bin"
  # Create symlinks to system Python
  ln -sf "$(which python3)" "${APP_DIR}/Contents/Frameworks/Python.framework/Versions/$PY_VER/bin/python3"
  ln -sf "$(which pip3)" "${APP_DIR}/Contents/Frameworks/Python.framework/Versions/$PY_VER/bin/pip3"
  FW_DST="${APP_DIR}/Contents/Frameworks/Python.framework"
  # Skip the copy since we're using system Python
  echo "Using system Python through symlinks"
  exit 1
fi

echo "Found Python framework at: $FW_SRC"
FW_DST="${APP_DIR}/Contents/Frameworks/Python.framework"
cp -R "$FW_SRC" "$FW_DST" || echo "WARNING: Failed to copy framework. Will attempt to use Python from PATH."

# --- Add these steps to fix library loading ---
echo "Fixing Python framework library paths..."
# Define paths based on existing script variables
PYTHON_EXEC="${FW_DST}/Versions/$PY_VER/bin/python3" 
PYTHON_LIB_FILE="${FW_DST}/Versions/$PY_VER/Python" # Path to the actual library *file*

# 1. Check if the Python executable exists before proceeding
if [ ! -f "$PYTHON_EXEC" ]; then
    echo "ERROR: Embedded Python executable not found at $PYTHON_EXEC. Cannot fix library paths."
else
    # 2. Find the original absolute path the executable links against for the Python library
    #    Use otool -L, grep for the framework, extract the path (first field), get the first result.
    ORIGINAL_PYTHON_LINK=$(otool -L "$PYTHON_EXEC" | grep 'Python\.framework' | awk '{print $1}' | head -n 1)

    if [ -z "$ORIGINAL_PYTHON_LINK" ]; then
        echo "WARNING: Could not determine original Python library link path in $PYTHON_EXEC. Skipping install_name_tool fix for executable."
    else
        echo "Original Python library link in executable: $ORIGINAL_PYTHON_LINK"

        # 3. Define the new relative path using @loader_path
        #    @loader_path = directory of the executable (bin/)
        #    ../Python = go up one level (to Versions/3.9/) and find the Python library file
        NEW_PYTHON_LINK="@loader_path/../Python" 
        echo "Changing library link in executable '$PYTHON_EXEC' from '$ORIGINAL_PYTHON_LINK' to '$NEW_PYTHON_LINK'"

        # 4. Use install_name_tool to change the reference in the executable
        install_name_tool -change "$ORIGINAL_PYTHON_LINK" "$NEW_PYTHON_LINK" "$PYTHON_EXEC"

        # 5. Verify the change (Optional but good practice)
        echo "Verifying changes in executable:"
        otool -L "$PYTHON_EXEC" | grep 'Python' 
    fi
fi
# --- End of library path fixing steps ---

# Install dependencies using the embedded Python
echo "Installing dependencies..."

# Check if our embedded pip3 exists
if [ -f "${APP_DIR}/Contents/Frameworks/Python.framework/Versions/$PY_VER/bin/pip3" ]; then
  PIP_CMD="${APP_DIR}/Contents/Frameworks/Python.framework/Versions/$PY_VER/bin/pip3"
  echo "Using embedded pip at: $PIP_CMD"
else
  # Fall back to system pip
  echo "Embedded pip not found, falling back to system pip"
  PIP_CMD="pip3"
  
  # Create the framework bin directory if it doesn't exist
  mkdir -p "${APP_DIR}/Contents/Frameworks/Python.framework/Versions/$PY_VER/bin"
  
  # Create a symlink to the system Python and pip
  ln -sf "$(which python3)" "${APP_DIR}/Contents/Frameworks/Python.framework/Versions/$PY_VER/bin/python3"
  ln -sf "$(which pip3)" "${APP_DIR}/Contents/Frameworks/Python.framework/Versions/$PY_VER/bin/pip3"
fi

echo "Installing pip packages using: $PIP_CMD"
"$PIP_CMD" install --upgrade pip
"$PIP_CMD" install PyQt6 PyQt6-Qt6 appdirs colorlog
"$PIP_CMD" install -r requirements.txt

# Download CA certificates
echo "Downloading CA certificates..."
curl -o "${APP_DIR}/Contents/Resources/cacert.pem" https://curl.se/ca/cacert.pem

# Copy ffmpeg binaries into the app bundle
echo "Copying ffmpeg binaries..."
FFMPEG_PATH=$(which ffmpeg)
FFPROBE_PATH=$(which ffprobe)

if [ -f "$FFMPEG_PATH" ] && [ -f "$FFPROBE_PATH" ]; then
    mkdir -p "${APP_DIR}/Contents/MacOS/bin"
    
    # Ensure bin directory has proper permissions
    chmod 755 "${APP_DIR}/Contents/MacOS/bin"
    
    # Copy the binaries (GitHub Actions should have sufficient permissions)
    cp "$FFMPEG_PATH" "${APP_DIR}/Contents/MacOS/bin/"
    cp "$FFPROBE_PATH" "${APP_DIR}/Contents/MacOS/bin/"
    
    # Make executables executable
    chmod 755 "${APP_DIR}/Contents/MacOS/bin/ffmpeg"
    chmod 755 "${APP_DIR}/Contents/MacOS/bin/ffprobe"
    echo "FFmpeg binaries copied successfully."
else
    echo "Warning: Could not find ffmpeg or ffprobe executables."
    echo "Your app may not work correctly without these binaries."
fi

# Copy Qt plugins
echo "Copying Qt plugins..."
# Path to PyQt6 Qt plugins
PY_SITE_PACKAGES="${APP_DIR}/Contents/Frameworks/Python.framework/Versions/$PY_VER/lib/python$PY_VER/site-packages"
QT_PLUGIN_PATH="${PY_SITE_PACKAGES}/PyQt6/Qt6/plugins"

if [ -d "$QT_PLUGIN_PATH" ]; then
    # Create plugins directory
    mkdir -p "${APP_DIR}/Contents/PlugIns"
    
    # Copy the entire plugins directory
    echo "Copying Qt plugins from $QT_PLUGIN_PATH to ${APP_DIR}/Contents/PlugIns"
    cp -R "$QT_PLUGIN_PATH"/* "${APP_DIR}/Contents/PlugIns/"
    
    # Ensure correct permissions
    chmod -R 755 "${APP_DIR}/Contents/PlugIns"
    echo "Qt plugins copied successfully."
else
    echo "Warning: Qt plugins directory not found at $QT_PLUGIN_PATH"
    echo "The application may not display correctly."
fi

echo "Build completed successfully! App is located at: ${APP_DIR}"