#!/usr/bin/env python
"""
Test ThemeManager and ConfigManager integration
"""

import sys
from PyQt6.QtWidgets import QApplication

from app.utils import ConfigManager
from app.ThemeManager import ThemeManager

def run_test():
    # Create application to enable Qt signal/slot system
    app = QApplication(sys.argv)
    
    # Create instances and connect manually
    config_manager = ConfigManager.instance()
    theme_manager = ThemeManager.instance()
    
    print("Initial theme:", theme_manager.current_theme)
    print("Initial config theme:", config_manager.get('theme'))
    
    # Simulate theme toggle
    print("\nToggling theme...")
    current_theme = theme_manager.current_theme
    theme_manager.toggle_theme()
    print("New theme:", theme_manager.current_theme)
    print("Config theme:", config_manager.get('theme'))
    print("Toggle successful:", current_theme != theme_manager.current_theme)
    
    # Simulate ConfigManager change
    print("\nChanging theme via ConfigManager...")
    target_theme = 'light' if theme_manager.current_theme == 'dark' else 'dark'
    print("Setting theme to:", target_theme)
    config_manager.set('theme', target_theme)
    print("ThemeManager theme:", theme_manager.current_theme)
    print("ConfigManager theme:", config_manager.get('theme'))
    print("Config update successful:", theme_manager.current_theme == target_theme)
    
    return 0

if __name__ == "__main__":
    sys.exit(run_test())