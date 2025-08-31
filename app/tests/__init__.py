"""Tests package for Transcribrr app.

This module also provides a lightweight fallback stub for the `keyring`
package when it isn't installed in the CI environment. Several tests patch
`keyring.get_password` / `set_password` / `delete_password` directly using
`unittest.mock.patch`, which attempts to import the top-level module name.

To keep tests hermetic and avoid adding a hard dependency on the external
`keyring` package for CI, we create a minimal in-memory stub only when
`keyring` isn't available. When the real package is installed, this stub is
not used and nothing is changed.
"""

from __future__ import annotations

import sys
import types


# Ensure `keyring` is importable for tests that patch it directly.
# If the real package isn't installed, provide a minimal stub.
try:  # pragma: no cover - trivial import guard
    import keyring  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - only runs in lean CI envs
    keyring_stub = types.ModuleType("keyring")

    # Simple in-memory store keyed by (service, key)
    _store: dict[tuple[str, str], str] = {}

    def _k(service: str, name: str) -> tuple[str, str]:
        return (str(service), str(name))

    # Errors submodule with PasswordDeleteError to match API surface
    errors_mod = types.ModuleType("keyring.errors")

    class PasswordDeleteError(Exception):
        pass

    errors_mod.PasswordDeleteError = PasswordDeleteError  # type: ignore[attr-defined]

    def get_password(service: str, key: str) -> str | None:
        return _store.get(_k(service, key))

    def set_password(service: str, key: str, value: str) -> None:
        _store[_k(service, key)] = value

    def delete_password(service: str, key: str) -> None:
        try:
            del _store[_k(service, key)]
        except KeyError as exc:  # match real API behavior
            raise PasswordDeleteError("Key not found") from exc

    # Attach API to stub module
    keyring_stub.errors = errors_mod  # type: ignore[attr-defined]
    keyring_stub.get_password = get_password  # type: ignore[attr-defined]
    keyring_stub.set_password = set_password  # type: ignore[attr-defined]
    keyring_stub.delete_password = delete_password  # type: ignore[attr-defined]

    # Register both `keyring` and `keyring.errors` so patch() can resolve them
    sys.modules.setdefault("keyring", keyring_stub)
    sys.modules.setdefault("keyring.errors", errors_mod)
