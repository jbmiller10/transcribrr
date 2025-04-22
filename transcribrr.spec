# -*- mode: python ; coding: utf-8 -*-
"""
Transcribrr – PyInstaller specification
• Python 3.9, PyInstaller 6.x
• One‑folder windowed build (`dist/Transcribrr`)

Changed 2025‑04‑22: removed hard dependency on `cacert.pem` because the
project doesn't ship one.  If you later add a certificate bundle, place it
next to `main.py`; the conditional block below will include it automatically.
Other inclusions:
  – bundled **ffmpeg / ffprobe** executables (expected at `third_party/ffmpeg/bin/`)
  – hidden imports for **torchvision** and **torchaudio** if installed
"""
from pathlib import Path
from glob import glob
from PyInstaller.utils.hooks import collect_submodules, collect_data_files
from PyInstaller.utils.spec import specpath  # already injected; import for clarity

# Define specpath - path to the directory containing this spec file
specpath = Path(specpath).resolve()

# ---------------------------------------------------------------------------
# 1  Hidden imports – Torch + optional packages
# ---------------------------------------------------------------------------
hidden_imports = collect_submodules("torch")
for extra_pkg in ("torchvision", "torchaudio"):
    try:
        __import__(extra_pkg)
    except ImportError:
        continue
    hidden_imports += collect_submodules(extra_pkg)

# Include Qt SVG module to ensure plugins are included
hidden_imports += collect_submodules("PyQt6.QtSvg")

# ---------------------------------------------------------------------------
# 2  Data files – icons, presets, optional config / cacert
# ---------------------------------------------------------------------------
RESOURCE_PATTERNS = [
    "icons/**",
    "preset_prompts.json",
]
# Optional runtime files – include only if present
for optional in ("config.json", "cacert.pem"):
    if Path(optional).exists():
        RESOURCE_PATTERNS.append(optional)

datas = [(f, f.replace("icons/", "icons", 1))              # keep folder tree
         for f in glob("icons/**/*", recursive=True)]
datas += [("preset_prompts.json", ".")]

# Optional runtime files – include only if present
for optional in ("config.json", "cacert.pem"):
    if Path(optional).exists():
        datas.append((optional, "."))

datas += collect_data_files("lightning_fabric", includes=["version.info"])

# ---------------------------------------------------------------------------
# 3  Binaries – bundled ffmpeg & ffprobe executables
# ---------------------------------------------------------------------------
BINARIES = []
# Look for ffmpeg in bin/ directory at root of project
bin_dir = Path(specpath) / "bin"
for exe_name in ("ffmpeg.exe", "ffprobe.exe"):
    src = bin_dir / exe_name
    if src.exists():
        BINARIES.append((str(src), "bin"))

# ---------------------------------------------------------------------------
# 4  Analysis – core PyInstaller phase
# ---------------------------------------------------------------------------
a = Analysis(
    ["main.py"],
    pathex=[str(specpath), str(specpath / "app")],
    binaries=BINARIES,
    datas=datas,
    hiddenimports=hidden_imports,
    excludedimports=["torch.utils.tensorboard"],
    noarchive=False,
    cipher=None,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=None)

# ---------------------------------------------------------------------------
# 5  Executable – GUI app, no console window
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
# 6  Collect – assemble final bundle
# ---------------------------------------------------------------------------
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,  # Disabled for reproducible CI builds
    name="Transcribrr",
)