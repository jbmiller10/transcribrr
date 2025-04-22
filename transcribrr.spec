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
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

# ---------------------------------------------------------------------------
# 1  Hidden imports – Torch + optional packages
# ---------------------------------------------------------------------------
hidden_imports = collect_submodules("torch")
for extra_pkg in ("torchvision", "torchaudio"):
    try:
        __import__(extra_pkg)
    except ImportError:
        continue
    hidden_imports += collect_submodules(extra_pkg)

# ---------------------------------------------------------------------------
# 2  Data files – icons, presets, optional config / cacert
# ---------------------------------------------------------------------------
RESOURCE_PATTERNS = [
    "icons/**",
    "preset_prompts.json",
]
# Optional runtime files – include only if present
for optional in ("config.json", "cacert.pem"):
    if Path(optional).exists():
        RESOURCE_PATTERNS.append(optional)

datas = collect_data_files(".", includes=RESOURCE_PATTERNS)
datas += collect_data_files("lightning_fabric", includes=["version.info"])

# ---------------------------------------------------------------------------
# 3  Binaries – bundled ffmpeg & ffprobe executables
# ---------------------------------------------------------------------------
BINARIES = []
ffmpeg_dir = Path(__file__).parent / "third_party" / "ffmpeg" / "bin"
for exe_name in ("ffmpeg.exe", "ffprobe.exe"):
    src = ffmpeg_dir / exe_name
    if src.exists():
        BINARIES.append((str(src), "bin"))

# ---------------------------------------------------------------------------
# 4  Analysis – core PyInstaller phase
# ---------------------------------------------------------------------------
a = Analysis(
    ["main.py"],
    pathex=[],
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
    upx=True,
    name="Transcribrr",
)