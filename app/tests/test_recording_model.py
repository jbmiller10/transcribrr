"""Tests for the Recording model dataclass."""

import copy
import dataclasses
import inspect
import sys
import unittest
from pathlib import Path
from typing import Optional

# Add parent directories to path to allow imports when running directly
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.models.recording import Recording


class TestRecordingModel(unittest.TestCase):
    """Test cases for the Recording dataclass model."""

    # Basic initialization and attribute access tests
    
    def test_initialization_with_required_fields(self):
        """Tests successful initialization with all required fields."""
        # Creating a Recording instance with all required fields provided
        recording = Recording(
            id=1,
            filename="test_audio.mp3",
            file_path="/path/to/test_audio.mp3",
            date_created="2024-01-15 10:30:00",
            duration=120.5
        )
        
        # Recording instance is created successfully
        self.assertIsInstance(recording, Recording)
        
        # All required attributes are set correctly
        self.assertEqual(recording.id, 1)
        self.assertEqual(recording.filename, "test_audio.mp3")
        self.assertEqual(recording.file_path, "/path/to/test_audio.mp3")
        self.assertEqual(recording.date_created, "2024-01-15 10:30:00")
        self.assertEqual(recording.duration, 120.5)
        
        # Optional fields default to None
        self.assertIsNone(recording.raw_transcript)
        self.assertIsNone(recording.processed_text)
        self.assertIsNone(recording.raw_transcript_formatted)
        self.assertIsNone(recording.processed_text_formatted)
        self.assertIsNone(recording.original_source_identifier)
        
        # All attributes are accessible via dot notation
        _ = recording.id
        _ = recording.filename
        _ = recording.file_path
        _ = recording.date_created
        _ = recording.duration
        _ = recording.raw_transcript
        _ = recording.processed_text
        _ = recording.raw_transcript_formatted
        _ = recording.processed_text_formatted
        _ = recording.original_source_identifier

    def test_initialization_with_all_fields(self):
        """Tests initialization with all fields including optional ones."""
        # Creating a Recording instance with all fields (required and optional) provided
        recording = Recording(
            id=2,
            filename="complete.wav",
            file_path="/data/complete.wav",
            date_created="2024-01-16 14:45:00",
            duration=300.0,
            raw_transcript="This is raw transcript",
            processed_text="This is processed text",
            raw_transcript_formatted="**Formatted Raw**",
            processed_text_formatted="**Formatted Processed**",
            original_source_identifier="source_123"
        )
        
        # Recording instance is created with all attributes set
        self.assertIsInstance(recording, Recording)
        
        # Optional fields contain the provided values
        self.assertEqual(recording.raw_transcript, "This is raw transcript")
        self.assertEqual(recording.processed_text, "This is processed text")
        self.assertEqual(recording.raw_transcript_formatted, "**Formatted Raw**")
        self.assertEqual(recording.processed_text_formatted, "**Formatted Processed**")
        self.assertEqual(recording.original_source_identifier, "source_123")
        
        # No attributes are None when all fields are provided
        self.assertIsNotNone(recording.id)
        self.assertIsNotNone(recording.filename)
        self.assertIsNotNone(recording.file_path)
        self.assertIsNotNone(recording.date_created)
        self.assertIsNotNone(recording.duration)
        self.assertIsNotNone(recording.raw_transcript)
        self.assertIsNotNone(recording.processed_text)
        self.assertIsNotNone(recording.raw_transcript_formatted)
        self.assertIsNotNone(recording.processed_text_formatted)
        self.assertIsNotNone(recording.original_source_identifier)

    # Type validation tests
    
    def test_type_validation_for_integer_id(self):
        """Tests type validation for integer id field."""
        # Attempting to create Recording with non-integer id
        recording = Recording(
            id="not_an_int",  # String instead of int
            filename="test.mp3",
            file_path="/path/test.mp3",
            date_created="2024-01-15",
            duration=60.0
        )
        
        # Recording accepts the value (dataclass does not enforce runtime type checking)
        self.assertEqual(recording.id, "not_an_int")
        
        # Type checkers should flag this as an error during static analysis
        # (but runtime allows it)
        self.assertIsInstance(recording, Recording)

    def test_type_validation_for_float_duration(self):
        """Tests type validation for float duration field."""
        # Creating Recording with integer duration (should be coerced to float)
        recording = Recording(
            id=3,
            filename="test.mp3",
            file_path="/path/test.mp3",
            date_created="2024-01-15",
            duration=60  # Integer instead of float
        )
        
        # Integer duration is accepted and works as float
        self.assertEqual(recording.duration, 60)
        
        # No runtime errors occur
        self.assertIsInstance(recording, Recording)

    def test_string_fields_with_empty_strings(self):
        """Tests string fields with empty strings."""
        # Creating Recording with empty strings for filename, file_path, and date_created
        recording = Recording(
            id=4,
            filename="",
            file_path="",
            date_created="",
            duration=0.0
        )
        
        # Recording is created successfully with empty strings
        self.assertIsInstance(recording, Recording)
        
        # Empty strings are stored as-is (no validation in dataclass)
        self.assertEqual(recording.filename, "")
        self.assertEqual(recording.file_path, "")
        self.assertEqual(recording.date_created, "")

    # Edge cases and boundary conditions
    
    def test_initialization_with_none_for_optional_fields(self):
        """Tests initialization with None for optional fields."""
        # Explicitly setting optional fields to None
        recording = Recording(
            id=5,
            filename="test.mp3",
            file_path="/path/test.mp3",
            date_created="2024-01-15",
            duration=60.0,
            raw_transcript=None,
            processed_text=None,
            raw_transcript_formatted=None,
            processed_text_formatted=None,
            original_source_identifier=None
        )
        
        # Recording accepts None for all optional fields
        self.assertIsNone(recording.raw_transcript)
        self.assertIsNone(recording.processed_text)
        self.assertIsNone(recording.raw_transcript_formatted)
        self.assertIsNone(recording.processed_text_formatted)
        self.assertIsNone(recording.original_source_identifier)
        
        # No errors or warnings are raised
        self.assertIsInstance(recording, Recording)

    def test_initialization_with_very_long_strings(self):
        """Tests initialization with very long strings."""
        # Creating Recording with extremely long strings for text fields
        long_string = "x" * 100000  # 100k characters
        recording = Recording(
            id=6,
            filename=long_string[:255],  # Reasonable filename length
            file_path="/path/" + long_string[:1000],  # Long path
            date_created="2024-01-15",
            duration=60.0,
            raw_transcript=long_string,
            processed_text=long_string
        )
        
        # Recording stores long strings without truncation
        self.assertEqual(len(recording.raw_transcript), 100000)
        self.assertEqual(len(recording.processed_text), 100000)
        
        # No memory errors for reasonable string lengths
        self.assertIsInstance(recording, Recording)

    def test_initialization_with_negative_duration(self):
        """Tests initialization with negative duration."""
        # Creating Recording with negative duration value
        recording = Recording(
            id=7,
            filename="test.mp3",
            file_path="/path/test.mp3",
            date_created="2024-01-15",
            duration=-30.5
        )
        
        # Negative duration is accepted (no validation in dataclass)
        self.assertEqual(recording.duration, -30.5)
        
        # Value is stored as provided
        self.assertIsInstance(recording, Recording)

    def test_initialization_with_zero_duration(self):
        """Tests initialization with zero duration."""
        # Creating Recording with duration of 0.0
        recording = Recording(
            id=8,
            filename="test.mp3",
            file_path="/path/test.mp3",
            date_created="2024-01-15",
            duration=0.0
        )
        
        # Zero duration is accepted
        self.assertEqual(recording.duration, 0.0)
        
        # Value is stored as 0.0
        self.assertIsInstance(recording, Recording)

    # Dataclass-specific functionality tests
    
    def test_equality_comparison_same_values(self):
        """Tests equality comparison between Recording instances."""
        # Comparing two Recording instances with identical values
        recording1 = Recording(
            id=9,
            filename="test.mp3",
            file_path="/path/test.mp3",
            date_created="2024-01-15",
            duration=60.0,
            raw_transcript="test"
        )
        recording2 = Recording(
            id=9,
            filename="test.mp3",
            file_path="/path/test.mp3",
            date_created="2024-01-15",
            duration=60.0,
            raw_transcript="test"
        )
        
        # Two instances with same values are equal
        self.assertEqual(recording1, recording2)
        
        # Equality uses all fields for comparison
        self.assertTrue(recording1 == recording2)

    def test_inequality_comparison_different_values(self):
        """Tests inequality comparison between Recording instances."""
        # Comparing two Recording instances with different values
        recording1 = Recording(
            id=10,
            filename="test1.mp3",
            file_path="/path/test1.mp3",
            date_created="2024-01-15",
            duration=60.0
        )
        recording2 = Recording(
            id=11,
            filename="test2.mp3",
            file_path="/path/test2.mp3",
            date_created="2024-01-16",
            duration=90.0
        )
        
        # Two instances with different values are not equal
        self.assertNotEqual(recording1, recording2)
        
        # Changing any single field makes instances unequal
        recording3 = Recording(
            id=10,  # Same as recording1
            filename="test1.mp3",
            file_path="/path/test1.mp3",
            date_created="2024-01-15",
            duration=61.0  # Different duration
        )
        self.assertNotEqual(recording1, recording3)

    def test_repr_string_representation(self):
        """Tests string representation of Recording instance."""
        # Getting repr() of a Recording instance
        recording = Recording(
            id=12,
            filename="test.mp3",
            file_path="/path/test.mp3",
            date_created="2024-01-15",
            duration=60.0
        )
        
        repr_string = repr(recording)
        
        # repr() returns a string containing class name and all field values
        self.assertIn("Recording", repr_string)
        self.assertIn("id=12", repr_string)
        self.assertIn("filename='test.mp3'", repr_string)
        self.assertIn("file_path='/path/test.mp3'", repr_string)
        self.assertIn("date_created='2024-01-15'", repr_string)
        self.assertIn("duration=60.0", repr_string)
        
        # String can be used to recreate the object (eval-able)
        # Note: eval is generally unsafe, but this tests the format
        self.assertTrue(repr_string.startswith("Recording("))

    def test_hashability_of_recording_instances(self):
        """Tests hashability of Recording instances."""
        # Attempting to use Recording instance as dictionary key or in set
        recording = Recording(
            id=13,
            filename="test.mp3",
            file_path="/path/test.mp3",
            date_created="2024-01-15",
            duration=60.0
        )
        
        # Recording instances are not hashable by default (dataclass with mutable fields)
        # TypeError is raised when trying to hash
        with self.assertRaises(TypeError):
            hash(recording)
        
        with self.assertRaises(TypeError):
            {recording: "value"}
        
        with self.assertRaises(TypeError):
            {recording}

    # Field mutation tests
    
    def test_attribute_mutation(self):
        """Tests mutability of Recording fields."""
        # Modifying attributes after initialization
        recording = Recording(
            id=14,
            filename="original.mp3",
            file_path="/original/path.mp3",
            date_created="2024-01-15",
            duration=60.0
        )
        
        # All fields can be modified after initialization
        recording.id = 15
        recording.filename = "modified.mp3"
        recording.file_path = "/modified/path.mp3"
        recording.date_created = "2024-01-16"
        recording.duration = 90.0
        recording.raw_transcript = "New transcript"
        
        # Changes persist in the instance
        self.assertEqual(recording.id, 15)
        self.assertEqual(recording.filename, "modified.mp3")
        self.assertEqual(recording.file_path, "/modified/path.mp3")
        self.assertEqual(recording.date_created, "2024-01-16")
        self.assertEqual(recording.duration, 90.0)
        self.assertEqual(recording.raw_transcript, "New transcript")
        
        # No frozen dataclass errors
        self.assertIsInstance(recording, Recording)

    # Special date handling scenarios
    
    def test_date_created_edge_cases(self):
        """Tests Recording with various date_created formats."""
        # Creating Recording with date_created as 'pending', 'None', or empty string (as seen in db_utils)
        
        # Test with 'pending'
        recording1 = Recording(
            id=16,
            filename="test.mp3",
            file_path="/path/test.mp3",
            date_created="pending",
            duration=60.0
        )
        
        # Recording accepts any string value for date_created
        self.assertEqual(recording1.date_created, "pending")
        
        # Test with 'None' as string
        recording2 = Recording(
            id=17,
            filename="test.mp3",
            file_path="/path/test.mp3",
            date_created="None",
            duration=60.0
        )
        
        # Special values like 'pending' are stored as-is
        self.assertEqual(recording2.date_created, "None")
        
        # No date validation or parsing occurs in the model
        self.assertIsInstance(recording1, Recording)
        self.assertIsInstance(recording2, Recording)

    # Field access patterns
    
    def test_field_access_via_dot_notation(self):
        """Tests accessing all fields via dot notation."""
        # Accessing each field of a fully populated Recording instance
        recording = Recording(
            id=18,
            filename="complete.mp3",
            file_path="/path/complete.mp3",
            date_created="2024-01-15",
            duration=120.0,
            raw_transcript="Raw text",
            processed_text="Processed text",
            raw_transcript_formatted="**Raw formatted**",
            processed_text_formatted="**Processed formatted**",
            original_source_identifier="source_456"
        )
        
        # All fields are accessible via dot notation
        self.assertEqual(recording.id, 18)
        self.assertEqual(recording.filename, "complete.mp3")
        self.assertEqual(recording.file_path, "/path/complete.mp3")
        self.assertEqual(recording.date_created, "2024-01-15")
        self.assertEqual(recording.duration, 120.0)
        self.assertEqual(recording.raw_transcript, "Raw text")
        self.assertEqual(recording.processed_text, "Processed text")
        self.assertEqual(recording.raw_transcript_formatted, "**Raw formatted**")
        self.assertEqual(recording.processed_text_formatted, "**Processed formatted**")
        self.assertEqual(recording.original_source_identifier, "source_456")
        
        # No AttributeError for defined fields
        # Fields return exact values that were set
        for attr_name in ['id', 'filename', 'file_path', 'date_created', 'duration',
                          'raw_transcript', 'processed_text', 'raw_transcript_formatted',
                          'processed_text_formatted', 'original_source_identifier']:
            self.assertTrue(hasattr(recording, attr_name))

    def test_undefined_attribute_access(self):
        """Tests accessing undefined attributes."""
        # Attempting to access an attribute that doesn't exist on Recording
        recording = Recording(
            id=19,
            filename="test.mp3",
            file_path="/path/test.mp3",
            date_created="2024-01-15",
            duration=60.0
        )
        
        # AttributeError is raised for undefined attributes
        with self.assertRaises(AttributeError) as context:
            _ = recording.undefined_attribute
        
        # Error message indicates the attribute name
        self.assertIn("undefined_attribute", str(context.exception))

    # Integration scenarios based on actual usage
    
    def test_creation_from_database_tuple(self):
        """Tests creating Recording from database query result."""
        # Simulating the pattern used in db_utils.get_recording_by_id
        # Column order: id, filename, file_path, date_created, duration, raw_transcript,
        # processed_text, raw_transcript_formatted, processed_text_formatted, original_source_identifier
        db_record = (
            20,
            "database.mp3",
            "/db/path/database.mp3",
            "2024-01-15 10:00:00",
            180.5,
            "Raw from DB",
            "Processed from DB",
            None,  # Optional field can be None
            None,
            "db_source_789"
        )
        
        # Recording can be created from positional arguments matching database columns
        recording = Recording(
            id=db_record[0],
            filename=db_record[1],
            file_path=db_record[2],
            date_created=db_record[3],
            duration=db_record[4],
            raw_transcript=db_record[5],
            processed_text=db_record[6],
            raw_transcript_formatted=db_record[7],
            processed_text_formatted=db_record[8],
            original_source_identifier=db_record[9]
        )
        
        # Missing optional fields can be handled with conditional logic
        self.assertEqual(recording.id, 20)
        self.assertEqual(recording.filename, "database.mp3")
        self.assertIsNone(recording.raw_transcript_formatted)
        
        # Tuple unpacking works correctly
        self.assertIsInstance(recording, Recording)

    def test_creation_from_dictionary(self):
        """Tests creating Recording from dictionary (as in MainTranscriptionWidget)."""
        # Creating Recording using dictionary key access pattern
        recording_dict = {
            "id": 21,
            "filename": "widget.mp3",
            "file_path": "/widget/path.mp3",
            "date_created": "2024-01-15",
            "duration": 90.0
        }
        
        # Recording can be created by passing dictionary values as arguments
        recording = Recording(
            id=recording_dict["id"],
            filename=recording_dict["filename"],
            file_path=recording_dict["file_path"],
            date_created=recording_dict["date_created"],
            duration=recording_dict["duration"]
        )
        
        # Dictionary keys map correctly to Recording fields
        self.assertEqual(recording.id, 21)
        self.assertEqual(recording.filename, "widget.mp3")
        self.assertEqual(recording.file_path, "/widget/path.mp3")

    # Memory and performance considerations
    
    def test_large_transcript_data(self):
        """Tests Recording with very large transcript strings."""
        # Creating Recording with multi-megabyte transcript strings
        large_transcript = "x" * (2 * 1024 * 1024)  # 2MB string
        recording = Recording(
            id=22,
            filename="large.mp3",
            file_path="/path/large.mp3",
            date_created="2024-01-15",
            duration=3600.0,
            raw_transcript=large_transcript,
            processed_text=large_transcript
        )
        
        # Large strings are stored without issues
        self.assertEqual(len(recording.raw_transcript), 2 * 1024 * 1024)
        self.assertEqual(len(recording.processed_text), 2 * 1024 * 1024)
        
        # Memory usage is proportional to data size
        # No artificial limits on string sizes
        self.assertIsInstance(recording, Recording)

    # Dataclass features verification
    
    def test_field_order_preservation(self):
        """Tests that field order is preserved as defined."""
        # Verifying the order of fields in the dataclass
        fields = dataclasses.fields(Recording)
        field_names = [f.name for f in fields]
        
        # Fields maintain definition order
        expected_order = [
            'id', 'filename', 'file_path', 'date_created', 'duration',
            'raw_transcript', 'processed_text', 'raw_transcript_formatted',
            'processed_text_formatted', 'original_source_identifier'
        ]
        self.assertEqual(field_names, expected_order)
        
        # __dataclass_fields__ preserves order
        self.assertEqual(list(Recording.__dataclass_fields__.keys()), expected_order)
        
        # Required fields come before optional fields
        required_fields = ['id', 'filename', 'file_path', 'date_created', 'duration']
        optional_fields = ['raw_transcript', 'processed_text', 'raw_transcript_formatted',
                          'processed_text_formatted', 'original_source_identifier']
        
        for i, field_name in enumerate(field_names[:5]):
            self.assertIn(field_name, required_fields)
        for i, field_name in enumerate(field_names[5:]):
            self.assertIn(field_name, optional_fields)

    def test_init_signature(self):
        """Tests the generated __init__ method signature."""
        # Inspecting the __init__ method parameters
        sig = inspect.signature(Recording.__init__)
        params = sig.parameters
        
        # __init__ has parameters for all fields
        expected_params = ['self', 'id', 'filename', 'file_path', 'date_created', 'duration',
                          'raw_transcript', 'processed_text', 'raw_transcript_formatted',
                          'processed_text_formatted', 'original_source_identifier']
        self.assertEqual(list(params.keys()), expected_params)
        
        # Optional fields have None as default
        self.assertEqual(params['raw_transcript'].default, None)
        self.assertEqual(params['processed_text'].default, None)
        self.assertEqual(params['raw_transcript_formatted'].default, None)
        self.assertEqual(params['processed_text_formatted'].default, None)
        self.assertEqual(params['original_source_identifier'].default, None)
        
        # Required fields have no defaults
        self.assertEqual(params['id'].default, inspect.Parameter.empty)
        self.assertEqual(params['filename'].default, inspect.Parameter.empty)
        self.assertEqual(params['file_path'].default, inspect.Parameter.empty)
        self.assertEqual(params['date_created'].default, inspect.Parameter.empty)
        self.assertEqual(params['duration'].default, inspect.Parameter.empty)

    # Copy and modification patterns
    
    def test_copy_operations(self):
        """Tests creating copies of Recording instances."""
        # Using copy module or manual field copying
        original = Recording(
            id=23,
            filename="original.mp3",
            file_path="/path/original.mp3",
            date_created="2024-01-15",
            duration=60.0,
            raw_transcript="Original transcript"
        )
        
        # Shallow copy creates new instance with same values
        shallow_copy = copy.copy(original)
        self.assertEqual(shallow_copy.id, original.id)
        self.assertEqual(shallow_copy.filename, original.filename)
        self.assertEqual(shallow_copy.raw_transcript, original.raw_transcript)
        
        # Modifying copy doesn't affect original
        shallow_copy.id = 24
        shallow_copy.filename = "copy.mp3"
        self.assertEqual(original.id, 23)
        self.assertEqual(original.filename, "original.mp3")
        
        # Deep copy handles nested data correctly
        deep_copy = copy.deepcopy(original)
        self.assertEqual(deep_copy.id, original.id)
        self.assertEqual(deep_copy.raw_transcript, original.raw_transcript)

    # Serialization readiness
    
    def test_dict_conversion(self):
        """Tests converting Recording to dictionary."""
        # Using dataclasses.asdict() or manual conversion
        recording = Recording(
            id=25,
            filename="dict_test.mp3",
            file_path="/path/dict_test.mp3",
            date_created="2024-01-15",
            duration=120.0,
            raw_transcript="Test transcript",
            processed_text=None
        )
        
        # All fields are included in dictionary
        recording_dict = dataclasses.asdict(recording)
        
        # Dictionary keys match field names
        expected_keys = ['id', 'filename', 'file_path', 'date_created', 'duration',
                        'raw_transcript', 'processed_text', 'raw_transcript_formatted',
                        'processed_text_formatted', 'original_source_identifier']
        self.assertEqual(list(recording_dict.keys()), expected_keys)
        
        # None values are preserved for optional fields
        self.assertIsNone(recording_dict['processed_text'])
        self.assertIsNone(recording_dict['raw_transcript_formatted'])
        
        # Values match original
        self.assertEqual(recording_dict['id'], 25)
        self.assertEqual(recording_dict['filename'], "dict_test.mp3")
        self.assertEqual(recording_dict['raw_transcript'], "Test transcript")

    def test_tuple_conversion(self):
        """Tests converting Recording to tuple."""
        # Using dataclasses.astuple() for database operations
        recording = Recording(
            id=26,
            filename="tuple_test.mp3",
            file_path="/path/tuple_test.mp3",
            date_created="2024-01-15",
            duration=180.0,
            raw_transcript="Transcript",
            processed_text="Processed",
            raw_transcript_formatted=None,
            processed_text_formatted=None,
            original_source_identifier="source_999"
        )
        
        # Fields are converted to tuple in definition order
        recording_tuple = dataclasses.astuple(recording)
        
        # Verify tuple order matches field definition order
        self.assertEqual(recording_tuple[0], 26)  # id
        self.assertEqual(recording_tuple[1], "tuple_test.mp3")  # filename
        self.assertEqual(recording_tuple[2], "/path/tuple_test.mp3")  # file_path
        self.assertEqual(recording_tuple[3], "2024-01-15")  # date_created
        self.assertEqual(recording_tuple[4], 180.0)  # duration
        self.assertEqual(recording_tuple[5], "Transcript")  # raw_transcript
        self.assertEqual(recording_tuple[6], "Processed")  # processed_text
        
        # None values are preserved
        self.assertIsNone(recording_tuple[7])  # raw_transcript_formatted
        self.assertIsNone(recording_tuple[8])  # processed_text_formatted
        
        # Tuple can be used for database inserts
        self.assertEqual(recording_tuple[9], "source_999")  # original_source_identifier
        self.assertEqual(len(recording_tuple), 10)


if __name__ == "__main__":
    unittest.main()