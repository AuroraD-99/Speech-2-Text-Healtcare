from faster_whisper import WhisperModel
from log import Logger
import torch

import wave
import platform
import os

class voice_to_text:
    def __init__(self, model_size: str = "medium", device: str = "cuda" if torch.cuda.is_available() else "cpu"):
        """Initialize the voice_to_text class with the specified model size and device."""
        self.model = WhisperModel(model_size, device=device, compute_type="int8")
        self.device = device
        self.logger = Logger("Voice_to_text").get_logger()
        self.logger.info(f"Model loaded on {self.device} with size {model_size}.")

    def transcribe(self, audio_path: str) -> str:
        segments, info = self.model.transcribe(audio_path, beam_size=5)
        self.logger.info(f"Transcribing {audio_path}...")
        self.logger.debug(f"Language info: {info.language}")
        text = ""
        for segment in segments:
            text += segment.text + " "
        self.logger.info(f"Transcription completed for {audio_path}.")
        self.logger.debug(f"Transcription: {text}")
        return text.strip(), info.language

    def play_beep(self):
        """Riproduce un beep cross-platform."""
        system = platform.system()
        if system == "Windows":
            import winsound
            winsound.Beep(1000, 500)
        elif system == "Darwin":
            os.system('say "beep"')
        else:
            os.system('beep -f 1000 -l 500')

    


if __name__ == "__main__":
    transcriptor = voice_to_text()
    audio_filename = "test_audio.wav"  # Sostituisci con il tuo file audio
    transcription = transcriptor.transcribe(audio_filename)
    print(f"Transcription: {transcription}")
