from PyQt6.QtCore import QThread, pyqtSignal
import traceback
import torch
import whisperx

class TranscriptionThread(QThread):
    update_progress = pyqtSignal(str)
    completed = pyqtSignal(str)
    error = pyqtSignal(str)
    language = 'en'  # Make this configurable later

    def __init__(self, file_path, transcription_quality, speaker_detection_enabled, hf_auth_key, *args, **kwargs):
        super().__init__(*args, **kwargs)  # Changed to PyQt6 super() call
        self.file_path = file_path
        self.transcription_quality = transcription_quality
        self.speaker_detection_enabled = speaker_detection_enabled
        self.hf_auth_key = hf_auth_key


    def run(self):
        print("transcript")
        try:
            self.update_progress.emit('Transcription started...')
            device = "cuda" if torch.cuda.is_available() else "cpu"
            compute_type = "float16" if torch.cuda.is_available() else "int8"
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

    def diarize_audio(self, audio_file, device):
        audio = whisperx.load_audio(audio_file)
        diarize_model = whisperx.DiarizationPipeline(model_name='pyannote/speaker-diarization@2.1', use_auth_token=self.hf_auth_key, device=device)
        diarize_segments = diarize_model(audio)
        return diarize_segments

    def align_transcript(self, segments, language_code, audio_file, device):
        model_a, metadata = whisperx.load_align_model(language_code=language_code, device=device)
        try:
            result = whisperx.align(segments, model_a, metadata, whisperx.load_audio(audio_file), device,
                                    return_char_alignments=False)
            return result
        finally:
            del model_a
            torch.cuda.empty_cache()

    def assign_speaker_labels(self, diarize_segments, result):
        return whisperx.assign_word_speakers(diarize_segments, result)

    def parse_transcript(self, segments):
        transcript = ""
        current_speaker = None
        for segment in segments:
            # Extract speaker information
            speaker = segment.get('speaker')
            if not speaker and 'words' in segment and len(segment['words']) > 0:
                # If speaker is not in the segment directly, check the first word
                speaker = segment['words'][0].get('speaker')

            if not speaker:
                speaker = "UNKNOWN_SPEAKER"

            text = segment.get('text', '').strip()

            # Check if the speaker has changed
            if speaker != current_speaker:
                if current_speaker is not None:
                    transcript += "\n"
                transcript += f"{speaker}: "
                current_speaker = speaker

            transcript += text + " "

        return transcript.strip()