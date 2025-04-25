"""
Unit tests for PromptManager class.
"""

import os
import sys
import json
import tempfile
import unittest
from unittest.mock import patch, mock_open, MagicMock
from PyQt6.QtCore import QApplication

# Import the modules to be tested
from app.utils import PromptManager
import app.constants
from app.constants import DEFAULT_PROMPTS

class TestPromptManager(unittest.TestCase):
    """Test suite for the PromptManager class."""
    
    @classmethod
    def setUpClass(cls):
        """Set up the test environment once for all tests."""
        # Create a QApplication instance if not already created
        cls.app = QApplication(sys.argv) if not QApplication.instance() else QApplication.instance()
        
        # Create a temporary directory for prompt files
        cls.temp_dir = tempfile.mkdtemp()
        cls.temp_prompts_path = os.path.join(cls.temp_dir, "test_prompts.json")
        
        # Save the original prompts path
        cls.original_prompts_path = app.constants.PROMPTS_PATH
        
        # Reset the singleton instance before tests
        PromptManager._instance = None
    
    @classmethod
    def tearDownClass(cls):
        """Clean up the test environment after all tests."""
        # Restore the original prompts path
        app.constants.PROMPTS_PATH = cls.original_prompts_path
        
        # Cleanup temp directory
        if os.path.exists(cls.temp_dir):
            import shutil
            shutil.rmtree(cls.temp_dir)
        
        # Reset the singleton instance after tests
        PromptManager._instance = None
    
    def setUp(self):
        """Set up before each test."""
        # Override the prompts path for testing
        app.constants.PROMPTS_PATH = self.temp_prompts_path
        
        # Reset the singleton instance before each test
        PromptManager._instance = None
        
        # Delete the prompts file if it exists
        if os.path.exists(self.temp_prompts_path):
            os.unlink(self.temp_prompts_path)
    
    def test_singleton_instance(self):
        """Test that the instance() method returns the same object."""
        prompt_manager1 = PromptManager.instance()
        prompt_manager2 = PromptManager.instance()
        self.assertIs(prompt_manager1, prompt_manager2, "PromptManager.instance() should return the same object")
    
    def test_load_defaults_when_file_missing(self):
        """Test that default prompts are loaded when file is missing."""
        # Delete the prompts file if it exists
        if os.path.exists(self.temp_prompts_path):
            os.unlink(self.temp_prompts_path)
        
        # Create PromptManager instance
        prompt_manager = PromptManager.instance()
        
        # Verify all default prompts are loaded
        for name, data in DEFAULT_PROMPTS.items():
            self.assertEqual(prompt_manager.get_prompt_text(name), data['text'], 
                          f"Default text for prompt '{name}' should be loaded")
            self.assertEqual(prompt_manager.get_prompt_category(name), data['category'], 
                          f"Default category for prompt '{name}' should be loaded")
        
        # Verify prompts file was created
        self.assertTrue(os.path.exists(self.temp_prompts_path), "Prompts file should be created")
        
        # Verify prompts file contents
        with open(self.temp_prompts_path, 'r') as f:
            loaded_prompts = json.load(f)
            
        for name, data in DEFAULT_PROMPTS.items():
            self.assertEqual(loaded_prompts[name]['text'], data['text'], 
                          f"Saved text for prompt '{name}' should match default")
            self.assertEqual(loaded_prompts[name]['category'], data['category'], 
                          f"Saved category for prompt '{name}' should match default")
    
    def test_load_from_valid_existing_file(self):
        """Test loading from a valid existing prompts file."""
        # Create custom prompts
        custom_prompts = {
            "Custom Prompt": {
                "text": "This is a custom prompt",
                "category": "Custom"
            },
            "Another Prompt": {
                "text": "Another custom prompt",
                "category": "Testing"
            }
        }
        
        # Write the custom prompts to the file
        os.makedirs(os.path.dirname(self.temp_prompts_path), exist_ok=True)
        with open(self.temp_prompts_path, 'w') as f:
            json.dump(custom_prompts, f)
        
        # Create PromptManager instance
        prompt_manager = PromptManager.instance()
        
        # Verify the custom prompts are loaded
        self.assertEqual(prompt_manager.get_prompt_text("Custom Prompt"), "This is a custom prompt",
                      "Custom prompt text should be loaded")
        self.assertEqual(prompt_manager.get_prompt_category("Custom Prompt"), "Custom",
                      "Custom prompt category should be loaded")
        self.assertEqual(prompt_manager.get_prompt_text("Another Prompt"), "Another custom prompt",
                      "Another custom prompt text should be loaded")
        self.assertEqual(prompt_manager.get_prompt_category("Another Prompt"), "Testing",
                      "Another custom prompt category should be loaded")
        
        # Verify default prompts are also loaded
        for name, data in DEFAULT_PROMPTS.items():
            self.assertEqual(prompt_manager.get_prompt_text(name), data['text'], 
                          f"Default text for prompt '{name}' should be loaded")
            self.assertEqual(prompt_manager.get_prompt_category(name), data['category'], 
                          f"Default category for prompt '{name}' should be loaded")
    
    def test_load_merges_defaults(self):
        """Test that loading partial prompts merges with defaults."""
        # Create custom prompts that overwrite some defaults
        custom_prompts = {
            "Translate": {
                "text": "Custom translation prompt",
                "category": "Custom Translation"
            },
            "Custom Prompt": {
                "text": "This is a custom prompt",
                "category": "Custom"
            }
        }
        
        # Write the custom prompts to the file
        os.makedirs(os.path.dirname(self.temp_prompts_path), exist_ok=True)
        with open(self.temp_prompts_path, 'w') as f:
            json.dump(custom_prompts, f)
        
        # Create PromptManager instance
        prompt_manager = PromptManager.instance()
        
        # Verify the custom prompts are loaded
        self.assertEqual(prompt_manager.get_prompt_text("Translate"), "Custom translation prompt",
                      "Custom translation prompt text should be loaded")
        self.assertEqual(prompt_manager.get_prompt_category("Translate"), "Custom Translation",
                      "Custom translation prompt category should be loaded")
        self.assertEqual(prompt_manager.get_prompt_text("Custom Prompt"), "This is a custom prompt",
                      "Custom prompt text should be loaded")
        
        # Verify other default prompts are still loaded
        for name, data in DEFAULT_PROMPTS.items():
            if name != "Translate":  # Skip the one we overrode
                self.assertEqual(prompt_manager.get_prompt_text(name), data['text'], 
                              f"Default text for prompt '{name}' should be loaded")
                self.assertEqual(prompt_manager.get_prompt_category(name), data['category'], 
                              f"Default category for prompt '{name}' should be loaded")
    
    def test_load_handles_old_format(self):
        """Test that old format prompts (simple string) are loaded correctly."""
        # Create prompts in old format (just text strings)
        old_format_prompts = {
            "Old Format Prompt": "This is an old format prompt",
            "Another Old Format": "Another old format prompt text"
        }
        
        # Write the old format prompts to the file
        os.makedirs(os.path.dirname(self.temp_prompts_path), exist_ok=True)
        with open(self.temp_prompts_path, 'w') as f:
            json.dump(old_format_prompts, f)
        
        # Create PromptManager instance
        prompt_manager = PromptManager.instance()
        
        # Verify the old format prompts are converted correctly
        self.assertEqual(prompt_manager.get_prompt_text("Old Format Prompt"), "This is an old format prompt",
                      "Old format prompt text should be loaded")
        self.assertEqual(prompt_manager.get_prompt_category("Old Format Prompt"), "General",
                      "Old format prompt should get 'General' category")
        self.assertEqual(prompt_manager.get_prompt_text("Another Old Format"), "Another old format prompt text",
                      "Another old format prompt text should be loaded")
        
        # Verify the prompts were saved in new format
        with open(self.temp_prompts_path, 'r') as f:
            saved_prompts = json.load(f)
        
        self.assertIsInstance(saved_prompts["Old Format Prompt"], dict, 
                           "Old format prompt should be saved as a dictionary")
        self.assertEqual(saved_prompts["Old Format Prompt"]["text"], "This is an old format prompt",
                      "Old format prompt text should be preserved")
        self.assertEqual(saved_prompts["Old Format Prompt"]["category"], "General",
                      "Old format prompt should be saved with 'General' category")
    
    def test_load_handles_missing_category(self):
        """Test that prompts with missing category are loaded correctly."""
        # Create prompts with missing category
        missing_category_prompts = {
            "Missing Category": {
                "text": "This prompt has no category"
            }
        }
        
        # Write the prompts to the file
        os.makedirs(os.path.dirname(self.temp_prompts_path), exist_ok=True)
        with open(self.temp_prompts_path, 'w') as f:
            json.dump(missing_category_prompts, f)
        
        # Create PromptManager instance
        prompt_manager = PromptManager.instance()
        
        # Verify the prompt text is loaded
        self.assertEqual(prompt_manager.get_prompt_text("Missing Category"), "This prompt has no category",
                      "Prompt text should be loaded")
        
        # Verify the category defaults to "General"
        self.assertEqual(prompt_manager.get_prompt_category("Missing Category"), "General",
                      "Missing category should default to 'General'")
        
        # Verify the prompt was saved with the default category
        with open(self.temp_prompts_path, 'r') as f:
            saved_prompts = json.load(f)
        
        self.assertEqual(saved_prompts["Missing Category"]["category"], "General",
                      "Prompt should be saved with 'General' category")
    
    @patch('json.load')
    def test_load_handles_corrupt_json(self, mock_json_load):
        """Test that corrupt JSON in the prompts file falls back to defaults."""
        # Set up the file to exist
        with open(self.temp_prompts_path, 'w') as f:
            f.write('invalid json')
        
        # Make json.load raise an exception
        mock_json_load.side_effect = json.JSONDecodeError('Invalid JSON', '', 0)
        
        # Create PromptManager instance
        prompt_manager = PromptManager.instance()
        
        # Verify all default prompts are loaded
        for name, data in DEFAULT_PROMPTS.items():
            self.assertEqual(prompt_manager.get_prompt_text(name), data['text'], 
                          f"Default text for prompt '{name}' should be loaded")
            self.assertEqual(prompt_manager.get_prompt_category(name), data['category'], 
                          f"Default category for prompt '{name}' should be loaded")
        
        # Verify prompts file was recreated
        self.assertTrue(os.path.exists(self.temp_prompts_path), "Prompts file should be recreated")
    
    @patch('builtins.open')
    def test_load_handles_io_error(self, mock_open):
        """Test that I/O errors during prompts loading fall back to defaults."""
        # Make open raise an I/O error
        mock_open.side_effect = IOError("Test I/O error")
        
        # Create PromptManager instance
        prompt_manager = PromptManager.instance()
        
        # Verify all default prompts are loaded
        for name, data in DEFAULT_PROMPTS.items():
            self.assertEqual(prompt_manager.get_prompt_text(name), data['text'], 
                          f"Default text for prompt '{name}' should be loaded")
            self.assertEqual(prompt_manager.get_prompt_category(name), data['category'], 
                          f"Default category for prompt '{name}' should be loaded")
    
    def test_get_prompt_text_existing(self):
        """Test retrieving text for an existing prompt."""
        # Create PromptManager instance with defaults
        prompt_manager = PromptManager.instance()
        
        # Verify retrieving text for an existing prompt
        self.assertEqual(prompt_manager.get_prompt_text("Translate"), 
                      DEFAULT_PROMPTS["Translate"]["text"], 
                      "Should return correct prompt text")
    
    def test_get_prompt_text_missing_returns_none(self):
        """Test that retrieving text for a non-existent prompt returns None."""
        # Create PromptManager instance
        prompt_manager = PromptManager.instance()
        
        # Verify retrieving text for a non-existent prompt returns None
        self.assertIsNone(prompt_manager.get_prompt_text("Non-existent Prompt"), 
                        "Should return None for non-existent prompt")
    
    def test_get_prompt_category_existing(self):
        """Test retrieving category for an existing prompt."""
        # Create PromptManager instance with defaults
        prompt_manager = PromptManager.instance()
        
        # Verify retrieving category for an existing prompt
        self.assertEqual(prompt_manager.get_prompt_category("Translate"), 
                      DEFAULT_PROMPTS["Translate"]["category"], 
                      "Should return correct prompt category")
    
    def test_get_prompt_category_missing_returns_none(self):
        """Test that retrieving category for a non-existent prompt returns None."""
        # Create PromptManager instance
        prompt_manager = PromptManager.instance()
        
        # Verify retrieving category for a non-existent prompt returns None
        self.assertIsNone(prompt_manager.get_prompt_category("Non-existent Prompt"), 
                        "Should return None for non-existent prompt")
    
    def test_add_new_prompt(self):
        """Test adding a new prompt."""
        # Create PromptManager instance
        prompt_manager = PromptManager.instance()
        
        # Set up signal spy
        signal_called = False
        def on_prompts_changed():
            nonlocal signal_called
            signal_called = True
        
        prompt_manager.prompts_changed.connect(on_prompts_changed)
        
        # Add a new prompt
        result = prompt_manager.add_prompt("New Prompt", "This is a new prompt", "Testing")
        
        # Verify the operation was successful
        self.assertTrue(result, "add_prompt should return True for success")
        
        # Verify the prompt was added
        self.assertEqual(prompt_manager.get_prompt_text("New Prompt"), "This is a new prompt", 
                      "Prompt text should be added")
        self.assertEqual(prompt_manager.get_prompt_category("New Prompt"), "Testing", 
                      "Prompt category should be added")
        
        # Verify the signal was emitted
        self.assertTrue(signal_called, "prompts_changed signal should be emitted")
        
        # Verify the prompts were saved to file
        with open(self.temp_prompts_path, 'r') as f:
            saved_prompts = json.load(f)
        
        self.assertEqual(saved_prompts["New Prompt"]["text"], "This is a new prompt", 
                      "Prompt text should be saved to file")
        self.assertEqual(saved_prompts["New Prompt"]["category"], "Testing", 
                      "Prompt category should be saved to file")
        
        # Clean up
        prompt_manager.prompts_changed.disconnect(on_prompts_changed)
    
    def test_add_prompt_with_empty_name_or_text(self):
        """Test that adding a prompt with empty name or text fails."""
        # Create PromptManager instance
        prompt_manager = PromptManager.instance()
        
        # Set up signal spy
        signal_called = False
        def on_prompts_changed():
            nonlocal signal_called
            signal_called = True
        
        prompt_manager.prompts_changed.connect(on_prompts_changed)
        
        # Try to add a prompt with empty name
        result = prompt_manager.add_prompt("", "This is a prompt", "Testing")
        
        # Verify the operation failed
        self.assertFalse(result, "add_prompt should return False for empty name")
        
        # Verify the signal was not emitted
        self.assertFalse(signal_called, "prompts_changed signal should not be emitted")
        
        # Try to add a prompt with empty text
        result = prompt_manager.add_prompt("Empty Text", "", "Testing")
        
        # Verify the operation failed
        self.assertFalse(result, "add_prompt should return False for empty text")
        
        # Verify the signal was not emitted
        self.assertFalse(signal_called, "prompts_changed signal should not be emitted")
        
        # Clean up
        prompt_manager.prompts_changed.disconnect(on_prompts_changed)
    
    def test_update_prompt_existing(self):
        """Test updating an existing prompt."""
        # Create custom prompts
        custom_prompts = {
            "Test Prompt": {
                "text": "Original text",
                "category": "Testing"
            }
        }
        
        # Write the custom prompts to the file
        os.makedirs(os.path.dirname(self.temp_prompts_path), exist_ok=True)
        with open(self.temp_prompts_path, 'w') as f:
            json.dump(custom_prompts, f)
        
        # Create PromptManager instance
        prompt_manager = PromptManager.instance()
        
        # Set up signal spy
        signal_called = False
        def on_prompts_changed():
            nonlocal signal_called
            signal_called = True
        
        prompt_manager.prompts_changed.connect(on_prompts_changed)
        
        # Update the prompt
        result = prompt_manager.update_prompt("Test Prompt", "Updated text", "New Category")
        
        # Verify the operation was successful
        self.assertTrue(result, "update_prompt should return True for success")
        
        # Verify the prompt was updated
        self.assertEqual(prompt_manager.get_prompt_text("Test Prompt"), "Updated text", 
                      "Prompt text should be updated")
        self.assertEqual(prompt_manager.get_prompt_category("Test Prompt"), "New Category", 
                      "Prompt category should be updated")
        
        # Verify the signal was emitted
        self.assertTrue(signal_called, "prompts_changed signal should be emitted")
        
        # Verify the prompts were saved to file
        with open(self.temp_prompts_path, 'r') as f:
            saved_prompts = json.load(f)
        
        self.assertEqual(saved_prompts["Test Prompt"]["text"], "Updated text", 
                      "Updated prompt text should be saved to file")
        self.assertEqual(saved_prompts["Test Prompt"]["category"], "New Category", 
                      "Updated prompt category should be saved to file")
        
        # Clean up
        prompt_manager.prompts_changed.disconnect(on_prompts_changed)
    
    def test_update_prompt_text_only(self):
        """Test updating only the text of an existing prompt."""
        # Create custom prompts
        custom_prompts = {
            "Test Prompt": {
                "text": "Original text",
                "category": "Testing"
            }
        }
        
        # Write the custom prompts to the file
        os.makedirs(os.path.dirname(self.temp_prompts_path), exist_ok=True)
        with open(self.temp_prompts_path, 'w') as f:
            json.dump(custom_prompts, f)
        
        # Create PromptManager instance
        prompt_manager = PromptManager.instance()
        
        # Update only the text
        result = prompt_manager.update_prompt("Test Prompt", "Updated text")
        
        # Verify the operation was successful
        self.assertTrue(result, "update_prompt should return True for success")
        
        # Verify only the text was updated
        self.assertEqual(prompt_manager.get_prompt_text("Test Prompt"), "Updated text", 
                      "Prompt text should be updated")
        self.assertEqual(prompt_manager.get_prompt_category("Test Prompt"), "Testing", 
                      "Prompt category should remain unchanged")
    
    def test_update_prompt_missing(self):
        """Test that updating a non-existent prompt fails."""
        # Create PromptManager instance
        prompt_manager = PromptManager.instance()
        
        # Set up signal spy
        signal_called = False
        def on_prompts_changed():
            nonlocal signal_called
            signal_called = True
        
        prompt_manager.prompts_changed.connect(on_prompts_changed)
        
        # Try to update a non-existent prompt
        result = prompt_manager.update_prompt("Non-existent Prompt", "Updated text")
        
        # Verify the operation failed
        self.assertFalse(result, "update_prompt should return False for non-existent prompt")
        
        # Verify the signal was not emitted
        self.assertFalse(signal_called, "prompts_changed signal should not be emitted")
        
        # Clean up
        prompt_manager.prompts_changed.disconnect(on_prompts_changed)
    
    def test_update_prompt_empty_text(self):
        """Test that updating a prompt with empty text fails."""
        # Add a test prompt
        prompt_manager = PromptManager.instance()
        prompt_manager.add_prompt("Test Prompt", "Original text", "Testing")
        
        # Set up signal spy
        signal_called = False
        def on_prompts_changed():
            nonlocal signal_called
            signal_called = True
        
        prompt_manager.prompts_changed.connect(on_prompts_changed)
        
        # Try to update with empty text
        result = prompt_manager.update_prompt("Test Prompt", "")
        
        # Verify the operation failed
        self.assertFalse(result, "update_prompt should return False for empty text")
        
        # Verify the prompt was not updated
        self.assertEqual(prompt_manager.get_prompt_text("Test Prompt"), "Original text", 
                      "Prompt text should remain unchanged")
        
        # Verify the signal was not emitted
        self.assertFalse(signal_called, "prompts_changed signal should not be emitted")
        
        # Clean up
        prompt_manager.prompts_changed.disconnect(on_prompts_changed)
    
    def test_delete_prompt_existing(self):
        """Test deleting an existing prompt."""
        # Add a test prompt
        prompt_manager = PromptManager.instance()
        prompt_manager.add_prompt("Test Prompt", "Test text", "Testing")
        
        # Set up signal spy
        signal_called = False
        def on_prompts_changed():
            nonlocal signal_called
            signal_called = True
        
        prompt_manager.prompts_changed.connect(on_prompts_changed)
        
        # Delete the prompt
        result = prompt_manager.delete_prompt("Test Prompt")
        
        # Verify the operation was successful
        self.assertTrue(result, "delete_prompt should return True for success")
        
        # Verify the prompt was deleted
        self.assertIsNone(prompt_manager.get_prompt_text("Test Prompt"), 
                        "Prompt should be deleted")
        
        # Verify the signal was emitted
        self.assertTrue(signal_called, "prompts_changed signal should be emitted")
        
        # Verify the prompt was deleted from the file
        with open(self.temp_prompts_path, 'r') as f:
            saved_prompts = json.load(f)
        
        self.assertNotIn("Test Prompt", saved_prompts, 
                       "Deleted prompt should not be present in saved file")
        
        # Clean up
        prompt_manager.prompts_changed.disconnect(on_prompts_changed)
    
    def test_delete_prompt_missing(self):
        """Test that deleting a non-existent prompt fails."""
        # Create PromptManager instance
        prompt_manager = PromptManager.instance()
        
        # Set up signal spy
        signal_called = False
        def on_prompts_changed():
            nonlocal signal_called
            signal_called = True
        
        prompt_manager.prompts_changed.connect(on_prompts_changed)
        
        # Try to delete a non-existent prompt
        result = prompt_manager.delete_prompt("Non-existent Prompt")
        
        # Verify the operation failed
        self.assertFalse(result, "delete_prompt should return False for non-existent prompt")
        
        # Verify the signal was not emitted
        self.assertFalse(signal_called, "prompts_changed signal should not be emitted")
        
        # Clean up
        prompt_manager.prompts_changed.disconnect(on_prompts_changed)
    
    def test_import_prompts_merge(self):
        """Test importing prompts with merge mode."""
        # Create initial prompts
        prompt_manager = PromptManager.instance()
        prompt_manager.add_prompt("Existing Prompt", "Existing text", "Existing")
        
        # Create prompts to import
        import_prompts = {
            "Imported Prompt": {
                "text": "Imported text",
                "category": "Imported"
            },
            "Existing Prompt": {
                "text": "Updated text",
                "category": "Updated"
            }
        }
        
        # Create a temporary import file
        import_file = os.path.join(self.temp_dir, "import_prompts.json")
        with open(import_file, 'w') as f:
            json.dump(import_prompts, f)
        
        # Set up signal spy
        signal_called = False
        def on_prompts_changed():
            nonlocal signal_called
            signal_called = True
        
        prompt_manager.prompts_changed.connect(on_prompts_changed)
        
        # Import prompts with merge mode
        result, message = prompt_manager.import_prompts_from_file(import_file, merge=True)
        
        # Verify the operation was successful
        self.assertTrue(result, f"import_prompts_from_file should return True for success, message: {message}")
        
        # Verify the prompts were merged
        self.assertEqual(prompt_manager.get_prompt_text("Imported Prompt"), "Imported text", 
                      "Imported prompt should be added")
        self.assertEqual(prompt_manager.get_prompt_text("Existing Prompt"), "Updated text", 
                      "Existing prompt should be updated")
        
        # Verify the default prompts are still present
        for name in DEFAULT_PROMPTS:
            self.assertIsNotNone(prompt_manager.get_prompt_text(name), 
                              f"Default prompt '{name}' should still be present")
        
        # Verify the signal was emitted
        self.assertTrue(signal_called, "prompts_changed signal should be emitted")
        
        # Clean up
        prompt_manager.prompts_changed.disconnect(on_prompts_changed)
    
    def test_import_prompts_replace(self):
        """Test importing prompts with replace mode."""
        # Create initial prompts
        prompt_manager = PromptManager.instance()
        prompt_manager.add_prompt("Existing Prompt", "Existing text", "Existing")
        
        # Create prompts to import
        import_prompts = {
            "Imported Prompt": {
                "text": "Imported text",
                "category": "Imported"
            }
        }
        
        # Create a temporary import file
        import_file = os.path.join(self.temp_dir, "import_prompts.json")
        with open(import_file, 'w') as f:
            json.dump(import_prompts, f)
        
        # Set up signal spy
        signal_called = False
        def on_prompts_changed():
            nonlocal signal_called
            signal_called = True
        
        prompt_manager.prompts_changed.connect(on_prompts_changed)
        
        # Import prompts with replace mode
        result, message = prompt_manager.import_prompts_from_file(import_file, merge=False)
        
        # Verify the operation was successful
        self.assertTrue(result, f"import_prompts_from_file should return True for success, message: {message}")
        
        # Verify the prompts were replaced
        self.assertEqual(prompt_manager.get_prompt_text("Imported Prompt"), "Imported text", 
                      "Imported prompt should be present")
        
        # Verify the custom prompt was removed (but defaults should remain)
        self.assertIsNone(prompt_manager.get_prompt_text("Existing Prompt"), 
                        "Existing custom prompt should be removed")
        
        # Verify default prompts are still present
        for name in DEFAULT_PROMPTS:
            self.assertIsNotNone(prompt_manager.get_prompt_text(name), 
                              f"Default prompt '{name}' should be present")
        
        # Verify the signal was emitted
        self.assertTrue(signal_called, "prompts_changed signal should be emitted")
        
        # Clean up
        prompt_manager.prompts_changed.disconnect(on_prompts_changed)
    
    def test_import_prompts_error(self):
        """Test handling errors during prompt import."""
        # Create PromptManager instance
        prompt_manager = PromptManager.instance()
        
        # Set up signal spy
        signal_called = False
        def on_prompts_changed():
            nonlocal signal_called
            signal_called = True
        
        prompt_manager.prompts_changed.connect(on_prompts_changed)
        
        # Try to import from a non-existent file
        result, message = prompt_manager.import_prompts_from_file("/non/existent/path.json")
        
        # Verify the operation failed
        self.assertFalse(result, "import_prompts_from_file should return False for non-existent file")
        self.assertIn("Import failed", message, "Error message should indicate import failure")
        
        # Verify the signal was not emitted
        self.assertFalse(signal_called, "prompts_changed signal should not be emitted")
        
        # Create an invalid JSON file
        invalid_json_file = os.path.join(self.temp_dir, "invalid.json")
        with open(invalid_json_file, 'w') as f:
            f.write("This is not valid JSON")
        
        # Try to import from the invalid JSON file
        result, message = prompt_manager.import_prompts_from_file(invalid_json_file)
        
        # Verify the operation failed
        self.assertFalse(result, "import_prompts_from_file should return False for invalid JSON")
        self.assertIn("Invalid JSON", message, "Error message should indicate invalid JSON")
        
        # Verify the signal was not emitted
        self.assertFalse(signal_called, "prompts_changed signal should not be emitted")
        
        # Clean up
        prompt_manager.prompts_changed.disconnect(on_prompts_changed)
    
    def test_export_prompts(self):
        """Test exporting prompts to a file."""
        # Create prompts to export
        prompt_manager = PromptManager.instance()
        prompt_manager.add_prompt("Test Prompt", "Test text", "Testing")
        
        # Create export file path
        export_file = os.path.join(self.temp_dir, "export", "exported_prompts.json")
        
        # Export prompts
        result, message = prompt_manager.export_prompts_to_file(export_file)
        
        # Verify the operation was successful
        self.assertTrue(result, f"export_prompts_to_file should return True for success, message: {message}")
        self.assertIn("Successfully exported", message, "Message should indicate successful export")
        
        # Verify the export directory was created
        self.assertTrue(os.path.exists(os.path.dirname(export_file)), 
                      "Export directory should be created")
        
        # Verify the file was created
        self.assertTrue(os.path.exists(export_file), 
                      "Export file should be created")
        
        # Verify the file contents
        with open(export_file, 'r') as f:
            exported_prompts = json.load(f)
        
        # Check for both default prompts and the added prompt
        for name in DEFAULT_PROMPTS:
            self.assertIn(name, exported_prompts, f"Default prompt '{name}' should be exported")
            self.assertEqual(exported_prompts[name]["text"], DEFAULT_PROMPTS[name]["text"], 
                          f"Text for prompt '{name}' should match")
            self.assertEqual(exported_prompts[name]["category"], DEFAULT_PROMPTS[name]["category"], 
                          f"Category for prompt '{name}' should match")
        
        self.assertIn("Test Prompt", exported_prompts, "Custom prompt should be exported")
        self.assertEqual(exported_prompts["Test Prompt"]["text"], "Test text", 
                      "Custom prompt text should match")
        self.assertEqual(exported_prompts["Test Prompt"]["category"], "Testing", 
                      "Custom prompt category should match")
    
    @patch('builtins.open')
    def test_export_prompts_error(self, mock_open):
        """Test handling errors during prompt export."""
        # Create PromptManager instance
        prompt_manager = PromptManager.instance()
        
        # Make open raise an I/O error
        mock_open.side_effect = IOError("Test I/O error")
        
        # Try to export prompts
        result, message = prompt_manager.export_prompts_to_file("/path/to/export.json")
        
        # Verify the operation failed
        self.assertFalse(result, "export_prompts_to_file should return False for I/O error")
        self.assertIn("Export failed", message, "Message should indicate export failure")


if __name__ == '__main__':
    unittest.main()