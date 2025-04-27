#!/usr/bin/env python
"""
Simple test script to verify ThemeManager and ConfigManager integration.
This script mocks PyQt dependencies to allow testing without a GUI.
"""

from app.ThemeManager import ThemeManager
import os
import sys
from unittest.mock import MagicMock

# Mock PyQt dependencies


class MockQObject:
    def __init__(self):
        self.connections = []

    def connect(self, handler):
        self.connections.append(handler)
        print(f"Signal connected to {handler.__name__}")
        return True


class MockSignal:
    def __init__(self):
        self.signal = MockQObject()

    def connect(self, handler):
        return self.signal.connect(handler)

    def emit(self, data):
        print(f"Signal emitted with: {data}")
        for handler in self.signal.connections:
            handler(data)


class MockConfigManager:
    def __init__(self):
        self.config = {"theme": "light"}
        self.config_updated = MockSignal()

    def get(self, key, default=None):
        return self.config.get(key, default)

    def set(self, key, value):
        old_value = self.config.get(key)
        if old_value != value:
            self.config[key] = value
            self.config_updated.emit({key: value})
            print(f"Config updated: {key}={value}")

    def get_all(self):
        return self.config.copy()


class MockApplication:
    def __init__(self):
        self.stylesheet = ""

    def setStyleSheet(self, stylesheet):
        self.stylesheet = stylesheet
        print("Stylesheet updated")


# Setup the mock QObject and QApplication
sys.modules["PyQt6"] = MagicMock()
sys.modules["PyQt6.QtCore"] = MagicMock()
sys.modules["PyQt6.QtCore"].QObject = MockQObject
sys.modules["PyQt6.QtWidgets"] = MagicMock()
sys.modules["PyQt6.QtWidgets"].QApplication = MagicMock()
sys.modules["PyQt6.QtWidgets"].QApplication.instance.return_value = MockApplication()
sys.modules["PyQt6.QtGui"] = MagicMock()

# Mock resource_path and os.path.exists for migration


def mock_resource_path(path):
    return f"/mock/path/{path}"


def mock_exists(path):
    return False


# Inject our mocks
sys.modules["app.utils"] = MagicMock()
sys.modules["app.utils"].resource_path = mock_resource_path
sys.modules["app.utils"].ConfigManager.instance.return_value = MockConfigManager()
orig_exists = os.path.exists
os.path.exists = mock_exists

# Now import the module under test

# Restore os.path.exists to prevent side effects
os.path.exists = orig_exists


def run_tests():
    """Run basic integration tests for ThemeManager."""
    print("=== ThemeManager Integration Test ===")

    # Get the singleton instance
    theme_manager = ThemeManager.instance()
    config_manager = theme_manager.config_manager

    print(f"Initial theme: {theme_manager.current_theme}")

    # Test theme toggle
    theme_manager.toggle_theme()
    new_theme = theme_manager.current_theme
    config_theme = config_manager.get("theme")
    print(f"After toggle: theme={new_theme}, config={config_theme}")

    # Test theme change through ConfigManager
    target_theme = "light" if new_theme == "dark" else "dark"
    print(f"Setting theme through ConfigManager to {target_theme}")
    config_manager.set("theme", target_theme)

    # Theme manager should have updated its theme
    print(f"ThemeManager theme is now: {theme_manager.current_theme}")

    if theme_manager.current_theme == target_theme:
        print("SUCCESS: Theme was updated via ConfigManager!")
    else:
        print("ERROR: Theme was not updated correctly")

    print("=== Test Complete ===")


if __name__ == "__main__":
    run_tests()
