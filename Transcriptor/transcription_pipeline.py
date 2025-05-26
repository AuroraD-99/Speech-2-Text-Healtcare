from log import Logger
import time
from Transcriptor.whisper_base import voice_to_text
import os
from Transcriptor.audio_enhancer import AudioEnhancer


class TranscriptionPipeline:
    def __init__(self):
        """Initialize the transcription pipeline with the specified model size and device."""
        self.transcriptor = voice_to_text()
        self.audio_enhancer = AudioEnhancer()
        self.logger = Logger("TranscriptionPipeline").get_logger()
        self.logger.info(f"Transcription pipeline initialized.")

        self.audio_path = os.getenv("AUDIO_PATH")
        os.makedirs(self.audio_path, exist_ok=True)

    def run(self, audio_filename):
        """Run the transcription pipeline."""
        
        self.audio_enhancer.run(audio_filename)
        self.logger.info(f"Audio enhanced and saved as {audio_filename}.")
        
        
        transcription, language = self.transcriptor.transcribe(audio_filename)
        self.logger.info(f"Transcription completed: {transcription}.")
        self.logger.info(f"Language detected: {language}.")
        
        # Move the audio file to a different directory
        #audio_filepath = f"assets/audios/{audio_filename}"
        audio_filepath = os.path.join(self.audio_path, audio_filename)
        os.rename(audio_filename, audio_filepath)
        
        
        # Save transcription to a JSON file
        transcription_data = {
            "filename": audio_filename,
            "transcription": transcription,
            "language": language,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "audio_filepath": audio_filepath
        }
        self.logger.info("Transcription pipeline completed successfully.")
        
        return transcription_data
             
        
"""if __name__ == "__main__":
    pipeline = TranscriptionPipeline()
    pipeline.run()"""