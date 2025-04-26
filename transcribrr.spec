# -*- mode: python ; coding: utf-8 -*-
"""
Transcribrr – PyInstaller specification
• Python 3.11, PyInstaller 6.x
• One‑folder windowed build (`dist/Transcribrr`)

Changed 2025‑04‑22: removed hard dependency on `cacert.pem` because the
project doesn’t ship one.  If you later add a certificate bundle, place it
next to `main.py`; the conditional block below will include it automatically.
Other inclusions:
  – bundled **ffmpeg / ffprobe** executables (expected at `third_party/ffmpeg/bin/`)
  – hidden imports for **torchvision** and **torchaudio** if installed
  – Explicitly listed icon files instead of wildcard.
"""
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules, collect_data_files, collect_dynamic_libs
import inspect

spec_dir = Path(inspect.getfile(inspect.currentframe())).resolve().parent

# ── 1.  Hidden-imports ─────────────────────────────────────────────
hidden_imports = collect_submodules("torch")
for extra in ("torchvision", "torchaudio"):
    try:
        __import__(extra)
    except ImportError:
        continue
    hidden_imports += collect_submodules(extra)

hidden_imports += [
    "PyQt6.QtSvg",          # SVG icons
    "PyQt6.QtNetwork",      # bearer
    "PyQt6.QtPrintSupport", # printing
]

# ── 2.  Data files ─────────────────────────────────────────────────

# --- Start with non-icon resource files ---
RESOURCE_PATTERNS = ["preset_prompts.json"] # Removed "icons/**"
for opt in ("config.json", "cacert.pem"):
    if Path(opt).exists():
        RESOURCE_PATTERNS.append(opt)

# Use collect_data_files for non-icon patterns
datas = collect_data_files(str(spec_dir), includes=RESOURCE_PATTERNS)

# Add lightning_fabric data files
datas += collect_data_files("lightning_fabric", includes=["version.info"])

# --- Explicitly add each icon file ---
# PyInstaller datas format: list of tuples (source_path, destination_in_bundle)
icon_files = [
    # TextEditor Icons
    ('icons/TextEditor/align_center.svg', 'icons/TextEditor'),
    ('icons/TextEditor/align_left.svg', 'icons/TextEditor'),
    ('icons/TextEditor/align_right.svg', 'icons/TextEditor'),
    ('icons/TextEditor/bold.svg', 'icons/TextEditor'),
    ('icons/TextEditor/bullet.svg', 'icons/TextEditor'),
    ('icons/TextEditor/decrease_indent.svg', 'icons/TextEditor'),
    ('icons/TextEditor/find.svg', 'icons/TextEditor'),
    ('icons/TextEditor/font_color.svg', 'icons/TextEditor'),
    ('icons/TextEditor/highlight.svg', 'icons/TextEditor'),
    ('icons/TextEditor/increase_indent.svg', 'icons/TextEditor'),
    ('icons/TextEditor/italic.svg', 'icons/TextEditor'),
    ('icons/TextEditor/justify.svg', 'icons/TextEditor'),
    ('icons/TextEditor/numbered.svg', 'icons/TextEditor'),
    ('icons/TextEditor/print.svg', 'icons/TextEditor'),
    ('icons/TextEditor/strikethrough.svg', 'icons/TextEditor'),
    ('icons/TextEditor/underline.svg', 'icons/TextEditor'),
    # App Icons
    ('icons/app/app_icon.icns', 'icons/app'),
    ('icons/app/app_icon.ico', 'icons/app'),
    ('icons/app/app_icon.svg', 'icons/app'),
    ('icons/app/splash.svg', 'icons/app'),
    # Status Icons
    ('icons/status/audio.svg', 'icons/status'),
    ('icons/status/file.svg', 'icons/status'),
    ('icons/status/video.svg', 'icons/status'),
    # Root Icons
    ('icons/Spinner-1s-200px.gif', 'icons'),
    ('icons/batch.svg', 'icons'),
    ('icons/clear.svg', 'icons'),
    ('icons/delete.svg', 'icons'),
    ('icons/dropdown_arrow.svg', 'icons'),
    ('icons/dropdown_night.svg', 'icons'),
    ('icons/edit.svg', 'icons'),
    ('icons/export.svg', 'icons'),
    ('icons/folder.svg', 'icons'),
    ('icons/folder_open.svg', 'icons'),
    ('icons/help.svg', 'icons'),
    ('icons/import.svg', 'icons'),
    ('icons/lightbulb.svg', 'icons'),
    ('icons/magic_wand.svg', 'icons'),
    ('icons/pause.svg', 'icons'),
    ('icons/quill.svg', 'icons'),
    ('icons/record.svg', 'icons'),
    ('icons/refresh.svg', 'icons'),
    ('icons/rename.svg', 'icons'),
    ('icons/save.svg', 'icons'),
    ('icons/save_night.svg', 'icons'),
    ('icons/settings.svg', 'icons'),
    ('icons/settings_hover.svg', 'icons'),
    ('icons/settings_hover_night.svg', 'icons'),
    ('icons/settings_night.svg', 'icons'),
    ('icons/smart_format.svg', 'icons'),
    ('icons/sort.svg', 'icons'),
    ('icons/spinner.gif', 'icons'),
    ('icons/transcribe.svg', 'icons'),
    ('icons/upload.svg', 'icons'),
    ('icons/youtube.svg', 'icons'),
]

# Add the list of icon files to the datas list
datas += icon_files

# ── 3.  Binaries (FFmpeg + Qt plug-ins) ────────────────────────────
BINARIES = []

# FFmpeg/ffprobe copied by workflow → bin/
bin_dir = spec_dir / "bin"
for exe in ("ffmpeg.exe", "ffprobe.exe"):
    p = bin_dir / exe
    if p.exists():
        BINARIES.append((str(p), "bin"))

# Collect ALL Qt plug-ins into qt6_plugins/
BINARIES += collect_dynamic_libs("PyQt6", destdir="qt6_plugins")

# ── 4.  Analysis / EXE / COLLECT unchanged ────────────────────────
a = Analysis(
    ["main.py"], 
    pathex=[str(spec_dir)], 
    binaries=BINARIES,
    datas=datas, # Use the updated datas list here
    hiddenimports=hidden_imports,
    noarchive=False,
    cipher=None,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=None)

# ---------------------------------------------------------------------------
# 5  Executable – GUI app, no console window
# ---------------------------------------------------------------------------
exe = EXE(
    pyz,
    a.scripts,
    exclude_binaries=True,
    name="Transcribrr",
    icon="icons/app/app_icon.ico", # Ensure this path is correct relative to spec
    console=False,
)

# ---------------------------------------------------------------------------
# 6  Collect – assemble final bundle
# ---------------------------------------------------------------------------
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas, # Pass the updated datas list here as well
    strip=False,
    upx=False,
    name="Transcribrr",
)