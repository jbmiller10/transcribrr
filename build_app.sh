#!/bin/bash
set -e

echo "=== Transcribrr App Build Script ==="
echo "Installing required dependencies..."

# Install Python dependencies
pip install -r requirements.txt
pip install pyinstaller cairosvg pillow

# Create app icon
echo "Creating app icon..."
python create_icns.py

# Build the app
echo "Building macOS app with PyInstaller..."
pyinstaller --clean transcribrr.spec

echo "Build completed successfully!"
echo "The app is available at: $(pwd)/dist/Transcribrr.app"
echo ""
echo "You can run the app with: open dist/Transcribrr.app"
echo "Or install it by dragging to your Applications folder"