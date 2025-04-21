import json
import os
import logging
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication
from app.utils import resource_path

logger = logging.getLogger('transcribrr')

class ThemeManager:
    """Manage app themes."""
    
    _instance = None
    
    @classmethod
    def instance(cls):
        """Return singleton ThemeManager."""
        if cls._instance is None:
            cls._instance = ThemeManager()
        return cls._instance
    
    def __init__(self):
        """Init ThemeManager."""
        # Base theme variables (shared between light and dark)
        self.base_variables = {
            # Primary colors
            'primary': '#3366CC',
            'primary-light': '#5588EE',
            'primary-dark': '#224499',
            
            # Secondary colors
            'secondary': '#6699CC',
            'secondary-light': '#88BBEE',
            'secondary-dark': '#447799',
            
            # Accent color
            'accent': '#FF9900',
            'accent-light': '#FFBB33',
            'accent-dark': '#DD7700',
            
            # Status colors
            'error': '#FF5252',
            'success': '#4CAF50',
            'warning': '#FFC107',
            'info': '#2196F3',
            
            # Font settings
            'font-family': 'Arial, Helvetica, sans-serif',
            'font-size-small': '11px',
            'font-size-normal': '13px',
            'font-size-large': '15px',
            'font-size-xlarge': '18px',
            
            # Spacing
            'spacing-xs': '4px',
            'spacing-small': '8px',
            'spacing-normal': '12px',
            'spacing-large': '16px',
            'spacing-xl': '24px',
            
            # Borders
            'border-radius-small': '3px',
            'border-radius': '4px',
            'border-radius-large': '6px',
            'border-width': '1px',
            'border-width-thick': '2px',
        }
        
        # Light theme variables
        self.light_variables = {
            'background': '#FFFFFF',
            'background-secondary': '#F5F5F5',
            'background-tertiary': '#EEEEEE',
            'foreground': '#202020',
            'foreground-secondary': '#505050',
            'foreground-tertiary': '#707070',
            'border': '#DDDDDD',
            'border-light': '#EEEEEE',
            'border-dark': '#BBBBBB',
            'inactive': '#AAAAAA',
            'hover': '#F0F0F0',
            'selected': '#E0E0E0',
            'overlay': 'rgba(0, 0, 0, 0.1)',
        }
        
        # Dark theme variables
        self.dark_variables = {
            'background': '#2B2B2B',
            'background-secondary': '#333333',
            'background-tertiary': '#3A3A3A',
            'foreground': '#EEEEEE',
            'foreground-secondary': '#BBBBBB',
            'foreground-tertiary': '#999999',
            'border': '#555555',
            'border-light': '#666666',
            'border-dark': '#444444',
            'inactive': '#777777',
            'hover': '#3E3E3E',
            'selected': '#404040',
            'overlay': 'rgba(0, 0, 0, 0.25)',
        }
        
        self.current_theme = 'light'
        self.current_variables = {}
        self.current_stylesheet = ""
        
        # Load saved theme preference
        self.load_theme_preference()
    
    def load_theme_preference(self):
        """Load theme preference."""
        config_path = resource_path('config.json')
        try:
            if os.path.exists(config_path):
                with open(config_path, 'r') as config_file:
                    config = json.load(config_file)
                    theme = config.get('theme', 'light').lower()
                    if theme in ['light', 'dark']:
                        self.current_theme = theme
        except Exception as e:
            logger.error(f"Error loading theme preference: {e}")
    
    def save_theme_preference(self, theme):
        """Save theme preference."""
        config_path = resource_path('config.json')
        try:
            if os.path.exists(config_path):
                with open(config_path, 'r') as config_file:
                    config = json.load(config_file)
            else:
                config = {}
            
            config['theme'] = theme
            
            with open(config_path, 'w') as config_file:
                json.dump(config, config_file, indent=4)
        except Exception as e:
            logger.error(f"Error saving theme preference: {e}")
    
    def toggle_theme(self):
        """Toggle theme."""
        if self.current_theme == 'light':
            self.apply_theme('dark')
        else:
            self.apply_theme('light')
    
    def apply_theme(self, theme_name):
        """Apply theme."""
        if theme_name not in ['light', 'dark']:
            logger.warning(f"Unknown theme: {theme_name}, defaulting to light")
            theme_name = 'light'
        
        self.current_theme = theme_name
        
        # Save preference
        self.save_theme_preference(theme_name)
        
        # Combine base variables with theme-specific variables
        self.current_variables = {**self.base_variables}
        if theme_name == 'dark':
            self.current_variables.update(self.dark_variables)
        else:
            self.current_variables.update(self.light_variables)
        
        # Generate stylesheet
        self.current_stylesheet = self._generate_stylesheet()
        
        # Apply to application
        if QApplication.instance():
            QApplication.instance().setStyleSheet(self.current_stylesheet)
    
    def _generate_stylesheet(self):
        """Generate stylesheet."""
        v = self.current_variables  # Shorthand for variables
        
        # Common stylesheet for all widgets
        stylesheet = f"""
        /* Global styles */
        QWidget {{
            font-family: {v['font-family']};
            font-size: {v['font-size-normal']};
            color: {v['foreground']};
            background-color: {v['background']};
        }}
        
        QMainWindow, QDialog {{
            background-color: {v['background']};
        }}
        
        /* Headers */
        QLabel[header="true"] {{
            font-size: {v['font-size-xlarge']};
            font-weight: bold;
            color: {v['foreground']};
        }}
        
        /* Regular labels */
        QLabel {{
            color: {v['foreground']};
            background-color: transparent;
        }}
        
        QLabel[secondary="true"] {{
            color: {v['foreground-secondary']};
            font-size: {v['font-size-normal']};
        }}
        
        QLabel[tertiary="true"] {{
            color: {v['foreground-tertiary']};
            font-size: {v['font-size-small']};
        }}
        
        /* Text input fields */
        QLineEdit, QTextEdit, QPlainTextEdit {{
            background-color: {v['background-secondary']};
            color: {v['foreground']};
            border: {v['border-width']} solid {v['border']};
            border-radius: {v['border-radius']};
            padding: {v['spacing-small']};
            selection-background-color: {v['primary']};
            selection-color: white;
        }}
        
        QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{
            border: {v['border-width']} solid {v['primary']};
        }}
        
        QLineEdit:disabled, QTextEdit:disabled, QPlainTextEdit:disabled {{
            background-color: {v['background-tertiary']};
            color: {v['inactive']};
        }}
        
        /* Buttons */
        QPushButton {{
            background-color: {v['background-secondary']};
            color: {v['foreground']};
            border: {v['border-width']} solid {v['border']};
            border-radius: {v['border-radius']};
            padding: {v['spacing-small']} {v['spacing-normal']};
            min-height: 30px;
        }}
        
        QPushButton:hover {{
            background-color: {v['hover']};
            border-color: {v['primary']};
        }}
        
        QPushButton:pressed {{
            background-color: {v['primary']};
            color: white;
        }}
        
        QPushButton:disabled {{
            background-color: {v['background-tertiary']};
            color: {v['inactive']};
            border-color: {v['border']};
        }}
        
        QPushButton[primary="true"] {{
            background-color: {v['primary']};
            color: white;
            border-color: {v['primary-dark']};
        }}
        
        QPushButton[primary="true"]:hover {{
            background-color: {v['primary-light']};
        }}
        
        QPushButton[primary="true"]:pressed {{
            background-color: {v['primary-dark']};
        }}
        
        QPushButton[accent="true"] {{
            background-color: {v['accent']};
            color: white;
            border-color: {v['accent-dark']};
        }}
        
        QPushButton[accent="true"]:hover {{
            background-color: {v['accent-light']};
        }}
        
        QPushButton[accent="true"]:pressed {{
            background-color: {v['accent-dark']};
        }}
        
        QPushButton[flat="true"] {{
            background-color: transparent;
            border: none;
        }}
        
        QPushButton[flat="true"]:hover {{
            background-color: {v['hover']};
        }}
        
        /* Dropdowns */
        QComboBox {{
            background-color: {v['background-secondary']};
            color: {v['foreground']};
            border: {v['border-width']} solid {v['border']};
            border-radius: {v['border-radius']};
            padding: {v['spacing-small']};
            min-height: 30px;
        }}
        
        QComboBox::drop-down {{
            width: 20px;
            border: none;
        }}
        
        QComboBox QAbstractItemView {{
            background-color: {v['background']};
            color: {v['foreground']};
            border: {v['border-width']} solid {v['border']};
            selection-background-color: {v['primary']};
            selection-color: white;
        }}
        
        /* Spinboxes */
        QSpinBox, QDoubleSpinBox {{
            background-color: {v['background-secondary']};
            color: {v['foreground']};
            border: {v['border-width']} solid {v['border']};
            border-radius: {v['border-radius']};
            padding: {v['spacing-small']};
            min-height: 30px;
        }}
        
        QSpinBox::up-button, QDoubleSpinBox::up-button,
        QSpinBox::down-button, QDoubleSpinBox::down-button {{
            width: 20px;
            border: none;
        }}
        
        /* Sliders */
        QSlider::groove:horizontal {{
            border: {v['border-width']} solid {v['border']};
            height: 8px;
            background: {v['background-tertiary']};
            margin: 2px 0;
            border-radius: 4px;
        }}
        
        QSlider::handle:horizontal {{
            background: {v['primary']};
            border: {v['border-width']} solid {v['primary']};
            width: 18px;
            height: 18px;
            margin: -5px 0;
            border-radius: 9px;
        }}
        
        /* List Widget */
        QListWidget {{
            background-color: {v['background-secondary']};
            color: {v['foreground']};
            border: {v['border-width']} solid {v['border']};
            border-radius: {v['border-radius']};
            outline: none;
        }}
        
        QListWidget::item {{
            background-color: {v['background-secondary']};
            color: {v['foreground']};
            border-bottom: 1px solid {v['border']};
            padding: {v['spacing-small']};
        }}
        
        QListWidget::item:selected {{
            background-color: {v['selected']};
            color: {v['foreground']};
        }}
        
        QListWidget::item:hover {{
            background-color: {v['hover']};
        }}
        
        /* Scroll bars */
        QScrollBar:vertical {{
            background: {v['background']};
            width: 12px;
            margin: 12px 0px 12px 0px;
            border: none;
        }}
        
        QScrollBar::handle:vertical {{
            background-color: {v['background-tertiary']};
            min-height: 20px;
            border-radius: 6px;
        }}
        
        QScrollBar::handle:vertical:hover {{
            background-color: {v['primary']};
        }}
        
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0px;
        }}
        
        QScrollBar:horizontal {{
            background: {v['background']};
            height: 12px;
            margin: 0px 12px 0px 12px;
            border: none;
        }}
        
        QScrollBar::handle:horizontal {{
            background-color: {v['background-tertiary']};
            min-width: 20px;
            border-radius: 6px;
        }}
        
        QScrollBar::handle:horizontal:hover {{
            background-color: {v['primary']};
        }}
        
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
            width: 0px;
        }}
        
        /* Tab Widget */
        QTabWidget::pane {{
            border: 1px solid {v['border']};
            background-color: {v['background']};
        }}
        
        QTabBar::tab {{
            background-color: {v['background-secondary']};
            color: {v['foreground']};
            padding: 8px 12px;
            border: 1px solid {v['border']};
            border-bottom-color: {'transparent' if self.current_theme == 'dark' else v['border']};
            border-top-left-radius: {v['border-radius']};
            border-top-right-radius: {v['border-radius']};
        }}
        
        QTabBar::tab:selected {{
            background-color: {v['background']};
            border-bottom-color: transparent;
        }}
        
        QTabBar::tab:!selected {{
            margin-top: 2px;
        }}
        
        /* Toolbars */
        QToolBar {{
            background-color: {v['background-secondary']};
            border: none;
            spacing: {v['spacing-normal']};
            padding: {v['spacing-small']};
        }}
        
        QToolButton {{
            background-color: transparent;
            border: none;
            border-radius: {v['border-radius']};
            padding: {v['spacing-small']};
        }}
        
        QToolButton:hover {{
            background-color: {v['hover']};
        }}
        
        QToolButton:pressed {{
            background-color: {v['selected']};
        }}
        
        /* Status Bar */
        QStatusBar {{
            background-color: {v['background-secondary']};
            color: {v['foreground-secondary']};
            border-top: 1px solid {v['border']};
        }}
        
        /* Group Box */
        QGroupBox {{
            font-weight: bold;
            border: 1px solid {v['border']};
            border-radius: {v['border-radius']};
            margin-top: 1.5ex;
            padding-top: 1ex;
        }}
        
        QGroupBox::title {{
            subcontrol-origin: margin;
            subcontrol-position: top center;
            padding: 0 3px;
            background-color: {v['background']};
        }}
        
        /* Progress Bar */
        QProgressBar {{
            border: 1px solid {v['border']};
            border-radius: {v['border-radius']};
            text-align: center;
            background-color: {v['background-secondary']};
        }}
        
        QProgressBar::chunk {{
            background-color: {v['primary']};
            width: 1px;
        }}
        
        /* Menu */
        QMenu {{
            background-color: {v['background']};
            border: 1px solid {v['border']};
        }}
        
        QMenu::item {{
            padding: 5px 20px 5px 20px;
        }}
        
        QMenu::item:selected {{
            background-color: {v['primary']};
            color: white;
        }}
        
        QMenu::separator {{
            height: 1px;
            background-color: {v['border']};
            margin: 5px 0px 5px 0px;
        }}
        
        /* CheckBox */
        QCheckBox {{
            spacing: 10px;
        }}
        
        QCheckBox::indicator {{
            width: 18px;
            height: 18px;
            border: 1px solid {v['border']};
            border-radius: 3px;
            background-color: {v['background-secondary']};
        }}
        
        QCheckBox::indicator:checked {{
            background-color: {v['primary']};
        }}
        
        QCheckBox::indicator:unchecked:hover {{
            border: 1px solid {v['primary']};
        }}
        
        /* RadioButton */
        QRadioButton {{
            spacing: 10px;
        }}
        
        QRadioButton::indicator {{
            width: 18px;
            height: 18px;
            border: 1px solid {v['border']};
            border-radius: 9px;
            background-color: {v['background-secondary']};
        }}
        
        QRadioButton::indicator:checked {{
            background-color: {v['primary']};
        }}
        
        QRadioButton::indicator:unchecked:hover {{
            border: 1px solid {v['primary']};
        }}
        
        /* Dialog Buttons */
        QDialogButtonBox > QPushButton {{
            min-width: 80px;
        }}
        """
        
        return stylesheet
    
    def get_color(self, name):
        """Return color."""
        return self.current_variables.get(name, '#000000')
    
    def get_qcolor(self, name):
        """Return QColor."""
        color_str = self.get_color(name)
        return QColor(color_str)
    
    def get_palette(self):
        """Return QPalette."""
        palette = QPalette()
        
        if self.current_theme == 'dark':
            # Dark theme palette
            palette.setColor(QPalette.ColorRole.Window, self.get_qcolor('background'))
            palette.setColor(QPalette.ColorRole.WindowText, self.get_qcolor('foreground'))
            palette.setColor(QPalette.ColorRole.Base, self.get_qcolor('background-secondary'))
            palette.setColor(QPalette.ColorRole.AlternateBase, self.get_qcolor('background-tertiary'))
            palette.setColor(QPalette.ColorRole.ToolTipBase, self.get_qcolor('background'))
            palette.setColor(QPalette.ColorRole.ToolTipText, self.get_qcolor('foreground'))
            palette.setColor(QPalette.ColorRole.Text, self.get_qcolor('foreground'))
            palette.setColor(QPalette.ColorRole.Button, self.get_qcolor('background-secondary'))
            palette.setColor(QPalette.ColorRole.ButtonText, self.get_qcolor('foreground'))
            palette.setColor(QPalette.ColorRole.Link, self.get_qcolor('primary'))
            palette.setColor(QPalette.ColorRole.Highlight, self.get_qcolor('primary'))
            palette.setColor(QPalette.ColorRole.HighlightedText, QColor('white'))
        else:
            # Light theme palette
            palette.setColor(QPalette.ColorRole.Window, self.get_qcolor('background'))
            palette.setColor(QPalette.ColorRole.WindowText, self.get_qcolor('foreground'))
            palette.setColor(QPalette.ColorRole.Base, self.get_qcolor('background'))
            palette.setColor(QPalette.ColorRole.AlternateBase, self.get_qcolor('background-secondary'))
            palette.setColor(QPalette.ColorRole.ToolTipBase, self.get_qcolor('background'))
            palette.setColor(QPalette.ColorRole.ToolTipText, self.get_qcolor('foreground'))
            palette.setColor(QPalette.ColorRole.Text, self.get_qcolor('foreground'))
            palette.setColor(QPalette.ColorRole.Button, self.get_qcolor('background-secondary'))
            palette.setColor(QPalette.ColorRole.ButtonText, self.get_qcolor('foreground'))
            palette.setColor(QPalette.ColorRole.Link, self.get_qcolor('primary'))
            palette.setColor(QPalette.ColorRole.Highlight, self.get_qcolor('primary'))
            palette.setColor(QPalette.ColorRole.HighlightedText, QColor('white'))
        
        return palette