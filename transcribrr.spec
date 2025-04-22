# -*- mode: python ; coding: utf-8 -*-
"""
Transcribrr – PyInstaller specification

Compatible with **PyInstaller ≥ 6.0**
• Python 3.9
• One‑folder windowed build (`dist/Transcribrr`)

Important note (2025‑04‑22): PyInstaller 6 dropped the helper symbol
`PyInstaller.utils.spec.specpath`.  The spec now determines its own location
via `Path(__file__)`.  If you maintain additional spec files, apply the same
pattern.

Changed 2025‑04‑22: removed hard dependency on `cacert.pem` because the
project doesn't ship one.  If you later add a certificate bundle, place it
next to `main.py`; the conditional block below will include it automatically.
Other inclusions:
  – bundled **ffmpeg / ffprobe** executables (expected at `third_party/ffmpeg/bin/`)
  – hidden imports for **torchvision** and **torchaudio** if installed
"""
# ---------------------------------------------------------------------------
#  PyInstaller ≥ 6.0 removed `PyInstaller.utils.spec.specpath`.  We can obtain
#  the directory that contains this spec file simply via `__file__`.
# ---------------------------------------------------------------------------

from __future__ import annotations

import os
from glob import glob
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# Absolute path of the folder that contains *this* transcribrr.spec.  Using
# `Path(__file__).resolve()` makes the spec independent from internal
# PyInstaller helpers that were removed in v6.
specpath = Path(__file__).resolve().parent

# ---------------------------------------------------------------------------
# 1  Hidden imports – Torch + optional packages
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# 1  Hidden imports – Torch (CUDA flavour only) + required Qt plugins
# ---------------------------------------------------------------------------

# The previous version unconditionally pulled in *every* torch sub‑module.
# This increases bundle size dramatically and, worse, can break CPU‑only
# builds.  Instead, respect an optional build‑time flag `--flavour cuda`
# (exposed to the spec via environment variable `TRANSCRIBRR_FLAVOUR`).

flavour = os.getenv("TRANSCRIBRR_FLAVOUR", "cpu").lower()

hidden_imports: list[str] = []

if flavour == "cuda":
    # Full CUDA build – include torch and related eco‑system packages.
    hidden_imports += collect_submodules("torch")

    for extra_pkg in ("torchvision", "torchaudio"):
        try:
            __import__(extra_pkg)
        except ImportError:
            # Package not available – skip silently.
            continue
        hidden_imports += collect_submodules(extra_pkg)

# Qt – ensure that frequently‑used plugins are present regardless of flavour.
hidden_imports += [
    "PyQt6.QtSvg",  # SVG icon support
    "PyQt6.QtQml",  # QML plugin loader
    "PyQt6.QtNetwork",  # Network bearer plugin
]

# ---------------------------------------------------------------------------
# 2  Data files – icons, presets, optional config / cacert
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# 2  Data files – icons, presets, optional config / cacert
# ---------------------------------------------------------------------------

RESOURCE_PATTERNS: list[str] = [
    "icons/**",
    "preset_prompts.json",
]

# Optional runtime files – include only if present.
for optional in ("config.json", "cacert.pem"):
    if Path(optional).exists():
        RESOURCE_PATTERNS.append(optional)


def _build_datas(patterns: list[str]) -> list[tuple[str, str]]:
    """Expand glob patterns and build PyInstaller (src, dest) tuples once."""

    collected: list[tuple[str, str]] = []

    for pattern in patterns:
        for f in glob(pattern, recursive=True):
            p = Path(f)
            # Skip directories – PyInstaller wants individual files only.
            if p.is_dir():
                continue

            if str(p).replace("\\", "/").startswith("icons/"):
                # Preserve folder hierarchy under `icons/`.
                dest = str(p.parent)
            else:
                # Flat files -> project root inside the bundle.
                dest = "."

            collected.append((str(p), dest))

    return collected


datas = _build_datas(RESOURCE_PATTERNS)

# Additional data files from dependencies
datas += collect_data_files("lightning_fabric", includes=["version.info"])

# ---------------------------------------------------------------------------
# 3  Binaries – bundled ffmpeg & ffprobe executables
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# 3  Binaries – bundled ffmpeg & ffprobe executables
# ---------------------------------------------------------------------------


def _resolve_ffmpeg_binaries() -> list[tuple[str, str]]:
    """Locate *ffmpeg* & *ffprobe* executables and return PyInstaller tuples.

    Primary location  : <project_root>/third_party/ffmpeg/bin
    Workflow fallback : <project_root>/bin  (GH‑Actions artefact)
    """

    primary_dir = specpath / "third_party" / "ffmpeg" / "bin"
    fallback_dir = specpath / "bin"

    binaries: list[tuple[str, str]] = []
    missing: list[str] = []

    for exe_name in ("ffmpeg.exe", "ffprobe.exe"):
        src: Path | None = None

        if (primary := primary_dir / exe_name).exists():
            src = primary
        elif (fallback := fallback_dir / exe_name).exists():
            src = fallback

        if src is not None:
            binaries.append((str(src), "bin"))
        else:
            missing.append(exe_name)

    # Fail early (during spec execution) if either executable is missing.
    if missing:
        raise FileNotFoundError(
            "Missing required FFmpeg binaries: " + ", ".join(missing)
        )

    return binaries


BINARIES = _resolve_ffmpeg_binaries()

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