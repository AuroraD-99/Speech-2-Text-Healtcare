from log import Logger
import time
from whisper_base import voice_to_text
from audio_enhancer import AudioEnhancer
import json


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
        self.transcriptor.record_audio(output_filename=audio_filename, sample_rate=16000, channels=1)
        self.logger.info(f"Audio recorded and saved as {audio_filename}.")
        
        self.audio_enhancer.run(audio_filename)
        self.logger.info(f"Audio enhanced and saved as {audio_filename}.")
        
        
        transcription, language = self.transcriptor.transcribe(audio_filename)
        self.logger.info(f"Transcription completed: {transcription}.")
        self.logger.info(f"Language detected: {language}.")
        
        
        # Save transcription to a JSON file
        transcription_data = {
            "filename": audio_filename,
            "transcription": transcription,
            "language": language,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        json_filename = audio_filename.replace(".wav", ".json")
        with open(json_filename, 'w') as json_file:
            json.dump(transcription_data, json_file, indent=4)
        self.logger.info(f"Transcription saved to {json_filename}.")
        self.logger.info("Transcription pipeline completed successfully.")
        
        
        
        
        
if __name__ == "__main__":
    pipeline = TranscriptionPipeline()
    pipeline.run()