from PyQt5.QtCore import QThread, pyqtSignal,Qt
import traceback
import torch
import whisperx


class TranscriptionThread(QThread):
    update_progress = pyqtSignal(str)
    completed = pyqtSignal(str)
    error = pyqtSignal(str)
    language = 'en' #make this configurable later

    def __init__(self, file_path, transcription_quality, speaker_detection_enabled, hf_auth_key, *args, **kwargs):
        super().__init__(*args, **kwargs)
        print('guy')
        self.file_path = file_path
        self.transcription_quality = transcription_quality
        self.speaker_detection_enabled = speaker_detection_enabled
        self.hf_auth_key = hf_auth_key

    def run(self):
        print("transcript")
        try:
            self.update_progress.emit('Transcription started...')
            device = "cuda" if torch.cuda.is_available() else "cpu"
            compute_type = "float16" if torch.cuda.is_available() else "float32"
            model = whisperx.load_model(self.transcription_quality, device, compute_type=compute_type, language=self.language)
            audio = whisperx.load_audio(self.file_path)
            result = model.transcribe(audio, batch_size=16)
            if not self.speaker_detection_enabled:
                transcript_text = "\n".join(segment['text'] for segment in result['segments'])
                self.completed.emit(transcript_text)
                return
            # Diarize Audio
            self.update_progress.emit('Detecting speakers...')
            diarize_segments = self.diarize_audio(self.file_path, device)

            # Align Transcript
            self.update_progress.emit('Aligning transcript...')
            aligned_result = self.align_transcript(
                result["segments"],
                #result["language"],
                self.language,
                self.file_path,
                device
            )

            # Assign Speaker Labels
            self.update_progress.emit('Assigning speaker labels...')
            final_result = self.assign_speaker_labels(diarize_segments, aligned_result)

            # Parse and Format Transcript
            transcript_text = self.parse_transcript(final_result["segments"])

            self.completed.emit(transcript_text)
            self.update_progress.emit('Transcription finished.')
        except Exception as e:
            self.error.emit(f"Transcription error: {e}")
            print(traceback.format_exc())