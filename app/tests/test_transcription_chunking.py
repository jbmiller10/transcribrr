import unittest
import os
import tempfile
import wave
import struct
import numpy as np
from unittest.mock import patch, MagicMock

from app.threads.TranscriptionThread import TranscriptionThread

class TemporaryAPIChunkingTest(unittest.TestCase):
    """Tests for the new temporary API chunking feature."""
    
    def setUp(self):
        # Create a test audio file
        self.test_file_path = self._create_test_wav_file(30)  # 30 seconds
        
    def tearDown(self):
        # Clean up test file
        if os.path.exists(self.test_file_path):
            os.remove(self.test_file_path)
    
    def _create_test_wav_file(self, duration_seconds):
        """Create a test WAV file of specified duration."""
        file_handle, file_path = tempfile.mkstemp(suffix='.wav')
        os.close(file_handle)
        
        sample_rate = 16000
        num_samples = sample_rate * duration_seconds
        
        # Generate a simple sine wave
        t = np.linspace(0, duration_seconds, num_samples)
        audio_data = np.sin(2 * np.pi * 440 * t) * 32767
        audio_data = audio_data.astype(np.int16)
        
        with wave.open(file_path, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(audio_data.tobytes())
        
        return file_path
    
    def _create_large_test_wav_file(self):
        """Create a test WAV file that exceeds the API size limit."""
        # Creating a file with 30 seconds of audio but artificially large
        file_path = self._create_test_wav_file(30)
        
        # Use a mock to make it appear large without actually creating a huge file
        original_getsize = os.path.getsize
        
        def mock_getsize(path):
            if path == file_path:
                return 26 * 1024 * 1024  # 26 MB (just over the 25 MB limit)
            return original_getsize(path)
        
        return file_path, mock_getsize
    
    @patch('app.threads.TranscriptionThread.os.path.getsize')
    @patch('app.services.transcription_service.TranscriptionService._transcribe_with_api')
    def test_api_chunking_for_large_file(self, mock_transcribe_api, mock_getsize):
        """Test that large files are chunked when using API transcription."""
        # Set up mocks
        test_file, getsize_func = self._create_large_test_wav_file()
        mock_getsize.side_effect = getsize_func
        
        # Mock the API transcription to return a simple result
        mock_transcribe_api.return_value = {'text': 'Test transcription'}
        
        # Create a TranscriptionThread with API method
        thread = TranscriptionThread(
            file_path=test_file,
            transcription_quality='whisper-1',
            speaker_detection_enabled=False,
            hf_auth_key=None,
            transcription_method='api',
            openai_api_key='fake_key'
        )
        
        # Use a mock for _create_temporary_chunks to avoid actual file operations
        with patch.object(thread, '_create_temporary_chunks') as mock_create_chunks:
            # Make it return a list of two "fake" temporary chunk paths
            temp_chunks = ['/tmp/chunk1.wav', '/tmp/chunk2.wav']
            mock_create_chunks.return_value = temp_chunks
            
            # Use another mock for _process_temporary_chunks
            with patch.object(thread, '_process_temporary_chunks') as mock_process_chunks:
                mock_process_chunks.return_value = "Combined transcription result"
                
                # Call process_single_file to trigger the chunking logic
                result = thread.process_single_file(test_file, 0)
                
                # Verify that temporary chunking methods were called
                mock_create_chunks.assert_called_once()
                mock_process_chunks.assert_called_once_with(temp_chunks, mock_process_chunks.call_args[0][1])
                
                # Verify the result is what we expect
                self.assertEqual(result, "Combined transcription result")

    @patch('app.threads.TranscriptionThread.os.path.getsize')
    @patch('app.services.transcription_service.TranscriptionService.transcribe_file')
    def test_no_chunking_for_small_file(self, mock_transcribe, mock_getsize):
        """Test that small files are not chunked when using API transcription."""
        # Use a smaller file that doesn't exceed API limit
        mock_getsize.return_value = 10 * 1024 * 1024  # 10 MB (under the 25 MB limit)
        
        # Mock the transcription to return a simple result
        mock_transcribe.return_value = {'text': 'Test transcription'}
        
        # Create a TranscriptionThread with API method
        thread = TranscriptionThread(
            file_path=self.test_file_path,
            transcription_quality='whisper-1',
            speaker_detection_enabled=False,
            hf_auth_key=None,
            transcription_method='api',
            openai_api_key='fake_key'
        )
        
        # Use mocks to verify the API chunking methods are NOT called
        with patch.object(thread, '_create_temporary_chunks') as mock_create_chunks:
            with patch.object(thread, '_process_temporary_chunks') as mock_process_chunks:
                # Call process_single_file
                result = thread.process_single_file(self.test_file_path, 0)
                
                # Verify that temporary chunking methods were NOT called
                mock_create_chunks.assert_not_called()
                mock_process_chunks.assert_not_called()
                
                # Verify that the regular transcribe_file was called
                mock_transcribe.assert_called_once()

if __name__ == '__main__':
    unittest.main()