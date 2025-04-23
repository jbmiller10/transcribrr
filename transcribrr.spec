# -*- mode: python ; coding: utf-8 -*-
"""
Transcribrr – PyInstaller specification
• Python 3.9, PyInstaller 6.x
• One‑folder windowed build (`dist/Transcribrr`)

Changed 2025‑04‑22: removed hard dependency on `cacert.pem` because the
project doesn’t ship one.  If you later add a certificate bundle, place it
next to `main.py`; the conditional block below will include it automatically.
Other inclusions:
  – bundled **ffmpeg / ffprobe** executables (expected at `third_party/ffmpeg/bin/`)
  – hidden imports for **torchvision** and **torchaudio** if installed
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
RESOURCE_PATTERNS = ["icons/**", "preset_prompts.json"]
for opt in ("config.json", "cacert.pem"):
    if Path(opt).exists():
        RESOURCE_PATTERNS.append(opt)

datas = collect_data_files(str(spec_dir), includes=RESOURCE_PATTERNS)
datas += collect_data_files("lightning_fabric", includes=["version.info"])

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
    pathex=[str(spec_dir), str(spec_dir / "app")],
    binaries=BINARIES,
    datas=datas,
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
    icon="icons/app/app_icon.ico",
    console=False,
)

# ---------------------------------------------------------------------------
# 6  Collect – assemble final bundle
# ---------------------------------------------------------------------------
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="Transcribrr",
)