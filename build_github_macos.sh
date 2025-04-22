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

# Create launcher script (Correct: Logs to ~/Library/Application Support)
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
exec "$PY" "$RESOURCES_DIR/main.py" >> "$APP_LOGS_DIR/launch.log" 2>&1 # Redirect Python stdout/stderr to log
EOF

# Make the launcher executable
chmod +x "${APP_DIR}/Contents/MacOS/${APP_NAME}"

# Copy resources
echo "Copying resources..."
mkdir -p "${APP_DIR}/Contents/Resources/icons/status" # Ensure status dir exists first
cp icons/status/audio.svg "${APP_DIR}/Contents/Resources/icons/status/"
cp icons/status/video.svg "${APP_DIR}/Contents/Resources/icons/status/"
cp icons/status/file.svg "${APP_DIR}/Contents/Resources/icons/status/"
# Now copy all icons, potentially overwriting status icons is fine
cp -R icons "${APP_DIR}/Contents/Resources/"
# Copy app code, config, main script
cp -R app "${APP_DIR}/Contents/Resources/"
cp config.json "${APP_DIR}/Contents/Resources/"
cp preset_prompts.json "${APP_DIR}/Contents/Resources/"
cp main.py "${APP_DIR}/Contents/Resources/"

# Copy Python framework
PY_VER=3.9
echo "Copying Python framework..."

# Debug Python location
echo "Python executable path: $(which python3)"
echo "Python version: $(python3 --version)"

# Explicitly check for python@3.9 from brew first (Fix #10)
if brew list python@3.9 &> /dev/null; then
    BREW_PY_PREFIX=$(brew --prefix python@3.9)
    echo "Found python@3.9 via Homebrew at $BREW_PY_PREFIX"
else
    BREW_PY_PREFIX=""
    echo "python@3.9 not found via Homebrew."
fi

# Look for Python framework in different locations (Fix #3 adapted)
if [ -n "$BREW_PY_PREFIX" ] && [ -d "$BREW_PY_PREFIX/Frameworks/Python.framework" ]; then
  FW_SRC="$BREW_PY_PREFIX/Frameworks/Python.framework"
elif [ -d "/Library/Frameworks/Python.framework" ]; then
  FW_SRC="/Library/Frameworks/Python.framework"
elif [ -d "$HOME/Library/Frameworks/Python.framework" ]; then
  FW_SRC="$HOME/Library/Frameworks/Python.framework"
else
  # Corrected error handling (Fix #5)
  echo "Fatal: Python.framework not found in expected locations (/Library, brew --prefix python@3.9, ~/Library) - aborting."
  exit 1
fi

echo "Found Python framework at: $FW_SRC"
FW_DST="${APP_DIR}/Contents/Frameworks/Python.framework"
# Create parent directory for specific version first (Improvement #6)
mkdir -p "${FW_DST}/Versions"
# Copy only the specific Python version (Improvement #6) & removed || echo (Fix #4)
cp -R "${FW_SRC}/Versions/${PY_VER}" "${FW_DST}/Versions/"

# --- BEGIN Comprehensive Python Framework Path Fixing ---
echo "Fixing Python framework library paths for bundling..."
PYTHON_EXEC="${FW_DST}/Versions/$PY_VER/bin/python3"
PYTHON_LIB_REL_PATH="Versions/$PY_VER/Python" # Relative path within Frameworks dir
PYTHON_LIB_ABS_PATH="${FW_DST}/${PYTHON_LIB_REL_PATH}" # Absolute path to file inside bundle

# Check if Python executable exists
if [ ! -f "$PYTHON_EXEC" ]; then
    echo "ERROR: Embedded Python executable not found at $PYTHON_EXEC. Cannot fix library paths."
else
    echo "Processing executable: $PYTHON_EXEC"
    
    # 1. Add RPATH to the executable pointing to the Frameworks directory
    #    @executable_path is the directory containing the executable (MacOS/)
    #    ../Frameworks tells it to look in the sibling Frameworks directory
    install_name_tool -add_rpath "@executable_path/../Frameworks" "$PYTHON_EXEC"
    echo "  Added RPATH @executable_path/../Frameworks to executable"

    # 2. Fix the executable's main dependency link to the Python library
    #    Find the original absolute path it links against
    ORIGINAL_PYTHON_LINK=$(otool -L "$PYTHON_EXEC" | grep 'Python\.framework' | awk '{print $1}' | head -n 1)
    if [ -n "$ORIGINAL_PYTHON_LINK" ]; then
        # Change it to use @rpath, which will resolve using the RPATH added above
        NEW_PYTHON_LINK="@rpath/Python.framework/$PYTHON_LIB_REL_PATH"
        echo "  Changing executable's link from '$ORIGINAL_PYTHON_LINK' to '$NEW_PYTHON_LINK'"
        install_name_tool -change "$ORIGINAL_PYTHON_LINK" "$NEW_PYTHON_LINK" "$PYTHON_EXEC"
    else
        echo "  WARNING: Could not find original Python framework link in executable."
    fi

    # 3. Fix the main Python library's ID
    if [ -f "$PYTHON_LIB_ABS_PATH" ]; then
        echo "Processing library: $PYTHON_LIB_ABS_PATH"
        NEW_LIB_ID="@rpath/Python.framework/$PYTHON_LIB_REL_PATH"
        echo "  Setting library ID to '$NEW_LIB_ID'"
        install_name_tool -id "$NEW_LIB_ID" "$PYTHON_LIB_ABS_PATH"
    else
        echo "  WARNING: Main Python library file not found at $PYTHON_LIB_ABS_PATH."
    fi

    # 4. Fix internal dependencies within *all* dylib files in the framework
    echo "Fixing internal dependencies in all framework dylibs..."
    # Find all files that might be dynamic libraries within the copied framework
    find "$FW_DST" -type f \( -name "*.dylib" -o -name "Python" \) -print0 | while IFS= read -r -d $'\0' file; do
        echo "  Processing internal links in: $file"
        # Get the list of libraries the current file links against
        otool -L "$file" | tail -n +2 | awk '{print $1}' | while read -r linked_lib; do
            # Check if the linked library uses an absolute path pointing back to the *original* source framework
            if [[ "$linked_lib" == "$FW_SRC"* ]]; then
                # Construct the new relative path using @rpath
                lib_basename=$(basename "$linked_lib")
                # Determine the relative path component (e.g., lib/something.dylib or just Python)
                # This part needs careful construction based on where the dependency lives
                # Assuming most dylibs are in Versions/3.9/lib or Versions/3.9
                if [[ "$linked_lib" == *"/lib/"* ]]; then
                    # If it's clearly in a lib subdir (heuristic)
                    new_link="@rpath/$(basename $(dirname "$linked_lib"))/$lib_basename"
                elif [[ "$lib_basename" == "Python" ]]; then
                     # Handle the main Python library link specifically
                     new_link="@rpath/Python.framework/$PYTHON_LIB_REL_PATH"
                else
                     # Fallback for other dylibs likely in the main Versions/3.9 dir or similar standard location
                     # Adjust this logic if your framework has a different internal structure
                     new_link="@rpath/$lib_basename" 
                fi
                
                echo "    Changing internal link from '$linked_lib' to '$new_link'"
                install_name_tool -change "$linked_lib" "$new_link" "$file"
            # Optional: Fix links to system libraries if needed (less common)
            # elif [[ "$linked_lib" == "/usr/lib/"* ]] || [[ "$linked_lib" == "/System/Library/"* ]]; then
            #    : # Usually system libs are okay, do nothing
            fi
        done
    done
fi
echo "Python framework path fixing complete."
# --- END Comprehensive Python Framework Path Fixing ---

# Install dependencies using the embedded Python
echo "Installing dependencies..."
PIP_CMD="${FW_DST}/Versions/$PY_VER/bin/pip3"
if [ ! -f "$PIP_CMD" ]; then
    echo "ERROR: Embedded pip3 not found at $PIP_CMD after framework copy and fixing."
    exit 1
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
    chmod 755 "${APP_DIR}/Contents/MacOS/bin"
    cp "$FFMPEG_PATH" "${APP_DIR}/Contents/MacOS/bin/"
    cp "$FFPROBE_PATH" "${APP_DIR}/Contents/MacOS/bin/"
    chmod 755 "${APP_DIR}/Contents/MacOS/bin/ffmpeg"
    chmod 755 "${APP_DIR}/Contents/MacOS/bin/ffprobe"
    echo "FFmpeg binaries copied successfully."
else
    echo "Warning: Could not find ffmpeg or ffprobe executables."
    echo "Your app may not work correctly without these binaries."
fi

# Copy Qt plugins (Pruned - Improvement #7)
echo "Copying Qt plugins..."
PY_SITE_PACKAGES="${FW_DST}/Versions/$PY_VER/lib/python$PY_VER/site-packages"
QT_PLUGIN_PATH_SRC="${PY_SITE_PACKAGES}/PyQt6/Qt6/plugins"
QT_PLUGIN_PATH_DST="${APP_DIR}/Contents/PlugIns"

if [ -d "$QT_PLUGIN_PATH_SRC" ]; then
    echo "Copying essential Qt plugins from $QT_PLUGIN_PATH_SRC to $QT_PLUGIN_PATH_DST"
    mkdir -p "$QT_PLUGIN_PATH_DST"

    # Platform plugin (Essential)
    mkdir -p "${QT_PLUGIN_PATH_DST}/platforms"
    cp "${QT_PLUGIN_PATH_SRC}/platforms/libqcocoa.dylib" "${QT_PLUGIN_PATH_DST}/platforms/" || echo "Warning: libqcocoa.dylib not found."

    # Image formats (Copy common ones)
    mkdir -p "${QT_PLUGIN_PATH_DST}/imageformats"
    cp "${QT_PLUGIN_PATH_SRC}/imageformats/libqgif.dylib" "${QT_PLUGIN_PATH_DST}/imageformats/" || echo "Warning: libqgif.dylib not found."
    cp "${QT_PLUGIN_PATH_SRC}/imageformats/libqico.dylib" "${QT_PLUGIN_PATH_DST}/imageformats/" || echo "Warning: libqico.dylib not found."
    cp "${QT_PLUGIN_PATH_SRC}/imageformats/libqjpeg.dylib" "${QT_PLUGIN_PATH_DST}/imageformats/" || echo "Warning: libqjpeg.dylib not found."
    cp "${QT_PLUGIN_PATH_SRC}/imageformats/libqmacheif.dylib" "${QT_PLUGIN_PATH_DST}/imageformats/" || echo "Warning: libqmacheif.dylib not found." # For HEIC
    cp "${QT_PLUGIN_PATH_SRC}/imageformats/libqmacjp2.dylib" "${QT_PLUGIN_PATH_DST}/imageformats/" || echo "Warning: libqmacjp2.dylib not found." # For JP2
    cp "${QT_PLUGIN_PATH_SRC}/imageformats/libqsvg.dylib" "${QT_PLUGIN_PATH_DST}/imageformats/" || echo "Warning: libqsvg.dylib not found."
    cp "${QT_PLUGIN_PATH_SRC}/imageformats/libqtiff.dylib" "${QT_PLUGIN_PATH_DST}/imageformats/" || echo "Warning: libqtiff.dylib not found."
    cp "${QT_PLUGIN_PATH_SRC}/imageformats/libqwebp.dylib" "${QT_PLUGIN_PATH_DST}/imageformats/" || echo "Warning: libqwebp.dylib not found."

    # Print support (If needed)
    if [ -d "${QT_PLUGIN_PATH_SRC}/printsupport" ]; then
        mkdir -p "${QT_PLUGIN_PATH_DST}/printsupport"
        cp "${QT_PLUGIN_PATH_SRC}/printsupport/libcocoaprintersupport.dylib" "${QT_PLUGIN_PATH_DST}/printsupport/" || echo "Warning: libcocoaprintersupport.dylib not found."
    fi

    # Ensure correct permissions
    chmod -R 755 "$QT_PLUGIN_PATH_DST"
    echo "Qt plugins copied."
else
    echo "Warning: Qt plugins source directory not found at $QT_PLUGIN_PATH_SRC"
    echo "The application may not display correctly."
fi

echo "Build completed successfully! App is located at: ${APP_DIR}"