from PyQt6.QtCore import QThread, pyqtSignal
import logging
from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor, pipeline
from typing import List, Optional, Union
import numpy as np
import requests
import torch
from pyannote.audio import Pipeline
from torchaudio import functional as F
from transformers.pipelines.audio_utils import ffmpeg_read
import speechbrain as sb
import time

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


class ASRDiarizationPipeline:

    def __init__(
        self,
        asr_pipeline,
        diarization_pipeline,
    ):
        self.asr_pipeline = asr_pipeline
        self.sampling_rate = asr_pipeline.feature_extractor.sampling_rate

        self.diarization_pipeline = diarization_pipeline

    @classmethod
    def from_pretrained(
        cls,
        asr_model: Optional[str] = "openai/whisper-large-v3",
        *,
        diarizer_model: Optional[str] = "pyannote/speaker-diarization",
        chunk_length_s: Optional[int] = 30,
        use_auth_token: Optional[Union[str, bool]] = False,
        **kwargs,
    ):
        asr_pipeline = pipeline(
            "automatic-speech-recognition",
            model=asr_model,
            chunk_length_s=chunk_length_s,
            token=use_auth_token,
            batch_size=12,
            return_timestamps=True,
            **kwargs,
        )
        diarization_pipeline = Pipeline.from_pretrained(diarizer_model, use_auth_token=use_auth_token)
        return cls(asr_pipeline, diarization_pipeline)

    def __call__(
        self,
        inputs: Union[np.ndarray, List[np.ndarray]],
        group_by_speaker: bool = True,
        **kwargs,
    ):
        """
        Transcribe the audio sequence(s) given as inputs to text and label with speaker information. The input
        audio is first passed to the speaker diarization pipeline, which returns timestamps for 'who spoke
        when'. The audio is then passed to the ASR pipeline, which returns utterance-level transcriptions and
        their corresponding timestamps. The speaker diarizer timestamps are aligned with the ASR transcription
        timestamps to give speaker-labelled transcriptions. We cannot use the speaker diarization timestamps
        alone to partition the transcriptions, as these timestamps may straddle across transcribed utterances
        from the ASR output. Thus, we find the diarizer timestamps that are closest to the ASR timestamps and
        partition here.

        Args:
            inputs (`np.ndarray` or `bytes` or `str` or `dict`):
                The inputs is either :
                    - `str` that is the filename of the audio file, the file will be read at the correct sampling rate
                      to get the waveform using *ffmpeg*. This requires *ffmpeg* to be installed on the system.
                    - `bytes` it is supposed to be the content of an audio file and is interpreted by *ffmpeg* in the
                      same way.
                    - (`np.ndarray` of shape (n, ) of type `np.float32` or `np.float64`)
                        Raw audio at the correct sampling rate (no further check will be done)
                    - `dict` form can be used to pass raw audio sampled at arbitrary `sampling_rate` and let this
                      pipeline do the resampling. The dict must be in the format `{"sampling_rate": int, "raw":
                      np.array}` with optionally a `"stride": (left: int, right: int)` than can ask the pipeline to
                      treat the first `left` samples and last `right` samples to be ignored in decoding (but used at
                      inference to provide more context to the model). Only use `stride` with CTC models.
            group_by_speaker (`bool`):
                Whether to group consecutive utterances by one speaker into a single segment. If False, will return
                transcriptions on a chunk-by-chunk basis.
            kwargs (remaining dictionary of keyword arguments, *optional*):
                Can be used to update additional asr or diarization configuration parameters
                        - To update the asr configuration, use the prefix *asr_* for each configuration parameter.
                        - To update the diarization configuration, use the prefix *diarization_* for each configuration parameter.
                        - Added this support related to issue #25: 08/25/2023

        Return:
            A list of transcriptions. Each list item corresponds to one chunk / segment of transcription, and is a
            dictionary with the following keys:
                - **text** (`str` ) -- The recognized text.
                - **speaker** (`str`) -- The associated speaker.
                - **timestamps** (`tuple`) -- The start and end time for the chunk / segment.
        """
        kwargs_asr = {
            argument[len("asr_"):]: value
            for argument, value in kwargs.items() if argument.startswith("asr_")
        }

        kwargs_diarization = {
            argument[len("diarization_"):]: value
            for argument, value in kwargs.items() if argument.startswith("diarization_")
        }

        inputs, diarizer_inputs = self.preprocess(inputs)

        diarization = self.diarization_pipeline(
            {
                "waveform": diarizer_inputs,
                "sample_rate": self.sampling_rate
            },
            **kwargs_diarization,
        )

        segments = []
        for segment, track, label in diarization.itertracks(yield_label=True):
            segments.append({
                'segment': {
                    'start': segment.start,
                    'end': segment.end
                },
                'track': track,
                'label': label
            })

        # diarizer output may contain consecutive segments from the same speaker (e.g. {(0 -> 1, speaker_1), (1 -> 1.5, speaker_1), ...})
        # we combine these segments to give overall timestamps for each speaker's turn (e.g. {(0 -> 1.5, speaker_1), ...})
        new_segments = []
        prev_segment = cur_segment = segments[0]

        for i in range(1, len(segments)):
            cur_segment = segments[i]

            # check if we have changed speaker ("label")
            if cur_segment["label"] != prev_segment["label"] and i < len(segments):
                # add the start/end times for the super-segment to the new list
                new_segments.append({
                    "segment": {
                        "start": prev_segment["segment"]["start"],
                        "end": cur_segment["segment"]["start"]
                    },
                    "speaker": prev_segment["label"],
                })
                prev_segment = segments[i]

        # add the last segment(s) if there was no speaker change
        new_segments.append({
            "segment": {
                "start": prev_segment["segment"]["start"],
                "end": cur_segment["segment"]["end"]
            },
            "speaker": prev_segment["label"],
        })

        asr_out = self.asr_pipeline(
            {
                "array": inputs,
                "sampling_rate": self.sampling_rate
            },
            return_timestamps=True,
            **kwargs_asr,
        )
        transcript = asr_out["chunks"]

        # get the end timestamps for each chunk from the ASR output
        end_timestamps = np.array([chunk["timestamp"][-1] for chunk in transcript])
        segmented_preds = []

        # align the diarizer timestamps and the ASR timestamps
        for segment in new_segments:
            # get the diarizer end timestamp
            end_time = segment["segment"]["end"]
            # find the ASR end timestamp that is closest to the diarizer's end timestamp and cut the transcript to here
            upto_idx = np.argmin(np.abs(end_timestamps - end_time))

            if group_by_speaker:
                segmented_preds.append({
                    "speaker":
                    segment["speaker"],
                    "text":
                    "".join([chunk["text"] for chunk in transcript[:upto_idx + 1]]),
                    "timestamp": (transcript[0]["timestamp"][0], transcript[upto_idx]["timestamp"][1]),
                })
            else:
                for i in range(upto_idx + 1):
                    segmented_preds.append({"speaker": segment["speaker"], **transcript[i]})

            # crop the transcripts and timestamp lists according to the latest timestamp (for faster argmin)
            transcript = transcript[upto_idx + 1:]
            end_timestamps = end_timestamps[upto_idx + 1:]

        return segmented_preds

    # Adapted from transformers.pipelines.automatic_speech_recognition.AutomaticSpeechRecognitionPipeline.preprocess
    # (see https://github.com/huggingface/transformers/blob/238449414f88d94ded35e80459bb6412d8ab42cf/src/transformers/pipelines/automatic_speech_recognition.py#L417)
    def preprocess(self, inputs):
        if isinstance(inputs, str):
            if inputs.startswith("http://") or inputs.startswith("https://"):
                # We need to actually check for a real protocol, otherwise it's impossible to use a local file
                # like http_huggingface_co.png
                inputs = requests.get(inputs).content
            else:
                with open(inputs, "rb") as f:
                    inputs = f.read()

        if isinstance(inputs, bytes):
            inputs = ffmpeg_read(inputs, self.sampling_rate)

        if isinstance(inputs, dict):
            # Accepting `"array"` which is the key defined in `datasets` for better integration
            if not ("sampling_rate" in inputs and ("raw" in inputs or "array" in inputs)):
                raise ValueError(
                    "When passing a dictionary to ASRDiarizePipeline, the dict needs to contain a "
                    '"raw" key containing the numpy array representing the audio and a "sampling_rate" key, '
                    "containing the sampling_rate associated with that array")

            _inputs = inputs.pop("raw", None)
            if _inputs is None:
                # Remove path which will not be used from `datasets`.
                inputs.pop("path", None)
                _inputs = inputs.pop("array", None)
            in_sampling_rate = inputs.pop("sampling_rate")
            inputs = _inputs
            if in_sampling_rate != self.sampling_rate:
                inputs = F.resample(torch.from_numpy(inputs), in_sampling_rate, self.sampling_rate).numpy()

        if not isinstance(inputs, np.ndarray):
            raise ValueError(f"We expect a numpy ndarray as input, got `{type(inputs)}`")
        if len(inputs.shape) != 1:
            raise ValueError("We expect a single channel audio input for ASRDiarizePipeline")

        # diarization model expects float32 torch tensor of shape `(channels, seq_len)`
        diarizer_inputs = torch.from_numpy(inputs).float()
        diarizer_inputs = diarizer_inputs.unsqueeze(0)

        return inputs, diarizer_inputs

def format_speech_to_dialogue(speech_text):
    """
    Formats the given text into a dialogue format.

    Args:
        speech_text (str): The dialogue text to be formatted.

    Returns:
        str: Formatted text in dialogue format.
    """
    # Parse the given text appropriately
    dialog_list = eval(str(speech_text))
    dialog_text = ""

    for i, turn in enumerate(dialog_list):
        speaker = f"Speaker {i % 2 + 1}"
        text = turn['text']
        dialog_text += f"{speaker}: {text}\n"

    return dialog_text

class SpeechToTextPipeline:
    """Class for converting audio to text using a pre-trained speech recognition model."""

    def __init__(self, model_id: str = "openai/whisper-large-v3"):
        self.model = None
        self.device = None

        if self.model is None:
            self.load_model(model_id)
        else:
            logging.info("Model already loaded.")

        self.set_device()

    def set_device(self):
        """Sets the device to be used for inference based on availability."""
        if torch.backends.mps.is_available():
            self.device = "mps"
        else:
            self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        logging.info(f"Using device: {self.device}")

    def load_model(self, model_id: str = "openai/whisper-large-v3"):
        """
        Loads the pre-trained speech recognition model and moves it to the specified device.

        Args:
            model_id (str): Identifier of the pre-trained model to be loaded.
        """
        logging.info("Loading model...")
        model = AutoModelForSpeechSeq2Seq.from_pretrained(
            model_id, torch_dtype=torch.float16, low_cpu_mem_usage=False, use_safetensors=True)
        model.to(self.device)
        logging.info("Model loaded successfully.")

        self.model = model

    def __call__(self, audio_path: str, model_id: str = "openai/whisper-large-v3", language: str = "english"):
        """
        Converts audio to text using the pre-trained speech recognition model.

        Args:
            audio_path (str): Path to the audio file to be transcribed.
            model_id (str): Identifier of the pre-trained model to be used for transcription.

        Returns:
            str: Transcribed text from the audio.
        """
        processor = AutoProcessor.from_pretrained(model_id)
        pipe = pipeline(
            "automatic-speech-recognition",
            model=self.model,
            torch_dtype=torch.float16,
            chunk_length_s=15,
            max_new_tokens=128,
            batch_size=8,
            return_timestamps=False,
            device=self.device,
            tokenizer=processor.tokenizer,
            feature_extractor=processor.feature_extractor,
            model_kwargs={"use_flash_attention_2": True},
            #generate_kwargs={"language": language},
        )
        logging.info("Transcribing audio...")
        result = pipe(audio_path)
        return result


class TranscriptionThread(QThread):
    update_progress = pyqtSignal(str)
    completed = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, file_path, transcription_quality, speaker_detection_enabled, hf_auth_key, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.file_path = file_path
        self.transcription_quality = transcription_quality
        self.speaker_detection_enabled = speaker_detection_enabled
        self.hf_auth_key = hf_auth_key

    def run(self):
        try:
            start_time = time.time()
            self.update_progress.emit('Transcription started...')
            device = "cuda" if torch.cuda.is_available() else "mps"

            model_id = self.transcription_quality
            pipeline = SpeechToTextPipeline(model_id=model_id)
            result = pipeline(self.file_path,model_id,"english")
            transcript = result

            if not self.speaker_detection_enabled:
                end_time = time.time()
                runtime = end_time - start_time
                print(f"Runtime: {runtime:.2f} seconds")
                self.completed.emit(transcript['text'])
                return

            print(self.hf_auth_key)
            dir_pipeline = ASRDiarizationPipeline.from_pretrained(
                asr_model=model_id,
                diarizer_model="pyannote/speaker-diarization",
                use_auth_token=self.hf_auth_key,
                chunk_length_s=15,
                device=device,
            )
            output_text = dir_pipeline(self.file_path, num_speakers=2, min_speaker=1, max_speaker=6)
            dialogue = format_speech_to_dialogue(output_text)
            end_time = time.time()
            runtime = end_time - start_time
            print(f"Runtime: {runtime:.2f} seconds")
            print(dialogue)

            self.completed.emit(dialogue)
            self.update_progress.emit('Transcription finished.')
        except Exception as e:
            self.error.emit(str(e))
            self.update_progress.emit('Error encountered; stopping...')
            self.completed.emit("")  # Signal completion with an empty string to handle the spinner