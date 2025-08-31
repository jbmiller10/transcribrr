"""
Transcribrr: A desktop application for audio transcription and processing.

This package initializer stays minimal and ensures a few commonly patched
submodules are importable for the test suite's patch resolution.
"""

__version__ = "1.0.0"

# Make legacy UI utils importable as attribute `app.ui_utils_legacy` for tests
try:  # pragma: no cover - resolved during tests
    from . import ui_utils_legacy  # noqa: F401
except Exception:
    # Headless/CI: provide a lightweight stub so unit tests can patch
    # attributes on `app.ui_utils_legacy` without importing PyQt6.
    import sys as _sys
    import types as _types

    _stub = _types.ModuleType('app.ui_utils_legacy')
    for _name in ('QMovie', 'QWidgetAction', 'QAction', 'QLabel', 'QPushButton'):
        setattr(_stub, _name, object())
    _sys.modules.setdefault('app.ui_utils_legacy', _stub)
    # Expose as attribute on the package for getattr-based resolution
    ui_utils_legacy = _stub  # type: ignore
