from log import Logger
import time
from whisper_base import voice_to_text
from audio_enhancer import AudioEnhancer


class TranscriptionPipeline:
    def __init__(self):
        """Initialize the transcription pipeline with the specified model size and device."""
        self.transcriptor = voice_to_text()
        self.audio_enhancer = AudioEnhancer()
        self.logger = Logger("TranscriptionPipeline").get_logger()
        self.logger.info(f"Transcription pipeline initialized.")

    def run(self):
        """Run the transcription pipeline."""
        self.logger.info("Starting transcription pipeline...")
        audio_filename = time.strftime("%Y-%m-%d_%H-%M-%S") + ".wav"
        self.transcriptor.record_audio(output_filename=audio_filename, record_seconds=5, sample_rate=16000, channels=1)
        self.logger.info(f"Audio recorded and saved as {audio_filename}.")
        
        self.audio_enhancer.run(audio_filename)
        self.logger.info(f"Audio enhanced and saved as {audio_filename}.")