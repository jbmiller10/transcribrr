"""
Unit tests for ConfigManager class.
"""

import os
import sys
import json
import tempfile
import unittest
from unittest.mock import patch, mock_open, MagicMock
from PyQt6.QtCore import QApplication

# Import the modules to be tested
from app.utils import ConfigManager
import app.constants
from app.constants import DEFAULT_CONFIG

class TestConfigManager(unittest.TestCase):
    """Test suite for the ConfigManager class."""
    
    @classmethod
    def setUpClass(cls):
        """Set up the test environment once for all tests."""
        # Create a QApplication instance if not already created
        cls.app = QApplication(sys.argv) if not QApplication.instance() else QApplication.instance()
        
        # Create a temporary directory for config files
        cls.temp_dir = tempfile.mkdtemp()
        cls.temp_config_path = os.path.join(cls.temp_dir, "test_config.json")
        
        # Save the original config path
        cls.original_config_path = app.constants.CONFIG_PATH
        
        # Reset the singleton instance before tests
        ConfigManager._instance = None
    
    @classmethod
    def tearDownClass(cls):
        """Clean up the test environment after all tests."""
        # Restore the original config path
        app.constants.CONFIG_PATH = cls.original_config_path
        
        # Cleanup temp directory
        if os.path.exists(cls.temp_dir):
            import shutil
            shutil.rmtree(cls.temp_dir)
        
        # Reset the singleton instance after tests
        ConfigManager._instance = None
    
    def setUp(self):
        """Set up before each test."""
        # Override the config path for testing
        app.constants.CONFIG_PATH = self.temp_config_path
        
        # Reset the singleton instance before each test
        ConfigManager._instance = None
        
        # Delete the config file if it exists
        if os.path.exists(self.temp_config_path):
            os.unlink(self.temp_config_path)
    
    def test_singleton_instance(self):
        """Test that the instance() method returns the same object."""
        config1 = ConfigManager.instance()
        config2 = ConfigManager.instance()
        self.assertIs(config1, config2, "ConfigManager.instance() should return the same object")
    
    def test_load_defaults_when_file_missing(self):
        """Test that default config is loaded when file is missing."""
        # Delete the config file if it exists
        if os.path.exists(self.temp_config_path):
            os.unlink(self.temp_config_path)
        
        # Create ConfigManager instance
        config = ConfigManager.instance()
        
        # Verify all default config values are loaded
        for key, value in DEFAULT_CONFIG.items():
            self.assertEqual(config.get(key), value, f"Default value for {key} should be loaded")
        
        # Verify config file was created
        self.assertTrue(os.path.exists(self.temp_config_path), "Config file should be created")
        
        # Verify config file contents
        with open(self.temp_config_path, 'r') as f:
            loaded_config = json.load(f)
            
        self.assertEqual(loaded_config, DEFAULT_CONFIG, "Saved config should match defaults")
    
    def test_load_from_valid_existing_file(self):
        """Test loading from a valid existing config file."""
        # Create a custom config
        custom_config = DEFAULT_CONFIG.copy()
        custom_config.update({
            'theme': 'dark',
            'transcription_quality': 'openai/whisper-medium',
            'temperature': 0.7
        })
        
        # Write the custom config to the file
        os.makedirs(os.path.dirname(self.temp_config_path), exist_ok=True)
        with open(self.temp_config_path, 'w') as f:
            json.dump(custom_config, f)
        
        # Create ConfigManager instance
        config = ConfigManager.instance()
        
        # Verify the custom values are loaded
        self.assertEqual(config.get('theme'), 'dark', "Custom theme value should be loaded")
        self.assertEqual(config.get('transcription_quality'), 'openai/whisper-medium', "Custom quality value should be loaded")
        self.assertEqual(config.get('temperature'), 0.7, "Custom temperature value should be loaded")
        
        # Verify default values are also loaded
        self.assertEqual(config.get('gpt_model'), DEFAULT_CONFIG['gpt_model'], "Default gpt_model value should be loaded")
    
    def test_load_merges_defaults(self):
        """Test that loading a partial config merges with defaults."""
        # Create a partial config
        partial_config = {
            'theme': 'dark',
            'transcription_quality': 'openai/whisper-medium'
        }
        
        # Write the partial config to the file
        os.makedirs(os.path.dirname(self.temp_config_path), exist_ok=True)
        with open(self.temp_config_path, 'w') as f:
            json.dump(partial_config, f)
        
        # Create ConfigManager instance
        config = ConfigManager.instance()
        
        # Verify custom values are loaded
        self.assertEqual(config.get('theme'), 'dark', "Custom theme value should be loaded")
        self.assertEqual(config.get('transcription_quality'), 'openai/whisper-medium', "Custom quality value should be loaded")
        
        # Verify default values are used for missing fields
        for key, value in DEFAULT_CONFIG.items():
            if key not in partial_config:
                self.assertEqual(config.get(key), value, f"Default value for {key} should be used")
        
        # Verify config file contents are updated with defaults
        with open(self.temp_config_path, 'r') as f:
            loaded_config = json.load(f)
        
        expected_config = DEFAULT_CONFIG.copy()
        expected_config.update(partial_config)
        for key, value in expected_config.items():
            self.assertEqual(loaded_config.get(key), value, f"Saved config should include default for {key}")
    
    @patch('json.load')
    def test_load_handles_corrupt_json(self, mock_json_load):
        """Test that corrupt JSON in the config file falls back to defaults."""
        # Set up the file to exist
        with open(self.temp_config_path, 'w') as f:
            f.write('invalid json')
        
        # Make json.load raise an exception
        mock_json_load.side_effect = json.JSONDecodeError('Invalid JSON', '', 0)
        
        # Create ConfigManager instance
        config = ConfigManager.instance()
        
        # Verify all default config values are loaded
        for key, value in DEFAULT_CONFIG.items():
            self.assertEqual(config.get(key), value, f"Default value for {key} should be loaded")
        
        # Verify config file was recreated
        self.assertTrue(os.path.exists(self.temp_config_path), "Config file should be recreated")
    
    @patch('builtins.open')
    def test_load_handles_io_error(self, mock_open):
        """Test that I/O errors during config loading fall back to defaults."""
        # Make open raise an I/O error
        mock_open.side_effect = IOError("Test I/O error")
        
        # Create ConfigManager instance
        config = ConfigManager.instance()
        
        # Verify all default config values are loaded
        for key, value in DEFAULT_CONFIG.items():
            self.assertEqual(config.get(key), value, f"Default value for {key} should be loaded")
    
    def test_get_existing_key(self):
        """Test retrieving an existing key from config."""
        # Create a config with a custom value
        custom_config = DEFAULT_CONFIG.copy()
        custom_config['theme'] = 'dark'
        
        # Write the config to the file
        os.makedirs(os.path.dirname(self.temp_config_path), exist_ok=True)
        with open(self.temp_config_path, 'w') as f:
            json.dump(custom_config, f)
        
        # Create ConfigManager instance
        config = ConfigManager.instance()
        
        # Verify the custom value is returned
        self.assertEqual(config.get('theme'), 'dark', "Custom theme value should be returned")
    
    def test_get_key_falls_back_to_default(self):
        """Test that retrieving a missing key falls back to default."""
        # Create a partial config
        partial_config = {
            'theme': 'dark'
        }
        
        # Write the partial config to the file
        os.makedirs(os.path.dirname(self.temp_config_path), exist_ok=True)
        with open(self.temp_config_path, 'w') as f:
            json.dump(partial_config, f)
        
        # Create ConfigManager instance
        config = ConfigManager.instance()
        
        # Verify that retrieving a missing key falls back to default
        self.assertEqual(config.get('transcription_quality'), 
                      DEFAULT_CONFIG['transcription_quality'], 
                      "Default value should be returned for missing key")
    
    def test_get_key_with_provided_default(self):
        """Test retrieving a key with a provided default value."""
        # Create ConfigManager instance with defaults
        config = ConfigManager.instance()
        
        # Verify that retrieving a non-existent key with a provided default returns the provided default
        self.assertEqual(config.get('non_existent_key', 'custom_default'), 
                      'custom_default', 
                      "Provided default should be returned for non-existent key")
    
    def test_set_new_key(self):
        """Test setting a new config key."""
        # Create ConfigManager instance
        config = ConfigManager.instance()
        
        # Set up signal spy
        signal_spy = []
        config.config_updated.connect(lambda changes: signal_spy.append(changes))
        
        # Set a new value
        config.set('new_key', 'new_value')
        
        # Verify the value was set
        self.assertEqual(config.get('new_key'), 'new_value', "New value should be set")
        
        # Verify the signal was emitted
        self.assertEqual(len(signal_spy), 1, "config_updated signal should be emitted")
        self.assertEqual(signal_spy[0], {'new_key': 'new_value'}, "Signal should contain changes")
        
        # Verify the config was saved to file
        with open(self.temp_config_path, 'r') as f:
            loaded_config = json.load(f)
        
        self.assertEqual(loaded_config.get('new_key'), 'new_value', "New value should be saved to file")
    
    def test_set_existing_key(self):
        """Test updating an existing config key."""
        # Create config with a custom value
        custom_config = DEFAULT_CONFIG.copy()
        custom_config['theme'] = 'light'
        
        # Write the config to the file
        os.makedirs(os.path.dirname(self.temp_config_path), exist_ok=True)
        with open(self.temp_config_path, 'w') as f:
            json.dump(custom_config, f)
        
        # Create ConfigManager instance
        config = ConfigManager.instance()
        
        # Set up signal spy
        signal_spy = []
        config.config_updated.connect(lambda changes: signal_spy.append(changes))
        
        # Update the value
        config.set('theme', 'dark')
        
        # Verify the value was updated
        self.assertEqual(config.get('theme'), 'dark', "Value should be updated")
        
        # Verify the signal was emitted
        self.assertEqual(len(signal_spy), 1, "config_updated signal should be emitted")
        self.assertEqual(signal_spy[0], {'theme': 'dark'}, "Signal should contain changes")
        
        # Verify the config was saved to file
        with open(self.temp_config_path, 'r') as f:
            loaded_config = json.load(f)
        
        self.assertEqual(loaded_config.get('theme'), 'dark', "Updated value should be saved to file")
    
    def test_set_no_change(self):
        """Test setting a key to its current value (no change)."""
        # Create config with a custom value
        custom_config = DEFAULT_CONFIG.copy()
        custom_config['theme'] = 'dark'
        
        # Write the config to the file
        os.makedirs(os.path.dirname(self.temp_config_path), exist_ok=True)
        with open(self.temp_config_path, 'w') as f:
            json.dump(custom_config, f)
        
        # Create ConfigManager instance
        config = ConfigManager.instance()
        
        # Set up signal spy
        signal_spy = []
        config.config_updated.connect(lambda changes: signal_spy.append(changes))
        
        # Set the value to the same value
        config.set('theme', 'dark')
        
        # Verify no signal was emitted
        self.assertEqual(len(signal_spy), 0, "No signal should be emitted for unchanged value")
    
    def test_update_multiple_keys(self):
        """Test updating multiple config keys at once."""
        # Create ConfigManager instance
        config = ConfigManager.instance()
        
        # Set up signal spy
        signal_spy = []
        config.config_updated.connect(lambda changes: signal_spy.append(changes))
        
        # Update multiple values
        config.update({
            'theme': 'dark',
            'transcription_quality': 'openai/whisper-medium',
            'temperature': 0.7
        })
        
        # Verify values were updated
        self.assertEqual(config.get('theme'), 'dark', "theme should be updated")
        self.assertEqual(config.get('transcription_quality'), 'openai/whisper-medium', "transcription_quality should be updated")
        self.assertEqual(config.get('temperature'), 0.7, "temperature should be updated")
        
        # Verify the signal was emitted with all changes
        self.assertEqual(len(signal_spy), 1, "config_updated signal should be emitted once")
        expected_changes = {
            'theme': 'dark',
            'transcription_quality': 'openai/whisper-medium',
            'temperature': 0.7
        }
        self.assertEqual(signal_spy[0], expected_changes, "Signal should contain all changes")
        
        # Verify the config was saved to file
        with open(self.temp_config_path, 'r') as f:
            loaded_config = json.load(f)
        
        for key, value in expected_changes.items():
            self.assertEqual(loaded_config.get(key), value, f"Updated value for {key} should be saved to file")
    
    def test_get_all_returns_copy(self):
        """Test that get_all() returns a copy of the config that can't modify the original."""
        # Create ConfigManager instance
        config = ConfigManager.instance()
        
        # Get a copy of the config
        config_copy = config.get_all()
        
        # Modify the copy
        config_copy['theme'] = 'modified_theme'
        
        # Verify the original is unchanged
        self.assertNotEqual(config.get('theme'), 'modified_theme', "Modifying the copy should not affect the original")
    
    def test_create_backup(self):
        """Test creating a config backup."""
        # Create a config with custom values
        custom_config = DEFAULT_CONFIG.copy()
        custom_config['theme'] = 'dark'
        
        # Write the config to the file
        os.makedirs(os.path.dirname(self.temp_config_path), exist_ok=True)
        with open(self.temp_config_path, 'w') as f:
            json.dump(custom_config, f)
        
        # Create ConfigManager instance
        config = ConfigManager.instance()
        
        # Create a backup
        with patch('app.utils.create_backup') as mock_create_backup:
            mock_create_backup.return_value = "/path/to/backup.json"
            backup_path = config.create_backup()
            
            # Verify create_backup was called with the correct path
            mock_create_backup.assert_called_once_with(self.temp_config_path)
            
            # Verify the backup path is returned
            self.assertEqual(backup_path, "/path/to/backup.json", "Backup path should be returned")


if __name__ == '__main__':
    unittest.main()