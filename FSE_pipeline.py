# Class to run the full pipeline of audio transcription, enhancement, database storage

from log import Logger
import time
from Database.mongodb import DB
from Transcriptor.transcription_pipeline import TranscriptionPipeline


class FSEPipeline:
    def __init__(self):
        """Initialize the FSE pipeline with the transcription pipeline and database."""
        self.logger = Logger(self.__class__.__name__).get_logger()
        self.transcription_pipeline = TranscriptionPipeline()
        
        # TODO: Insert LLM pipeline initialization here
        # self.llm_pipeline = LLM_Pipeline()
        
        self.db = DB()
        self.logger.info("FSE pipeline initialized with transcription pipeline and database.")
        self.logger.info("FSE pipeline initialized")
        
        
    def run(self):
        """Run the full pipeline: record audio, enhance it, transcribe, store in the database, process it with LLM, save results to database."""
        
        self.logger.info("Starting FSE pipeline...")
        
        # Record and transcribe audio
        transcription_data = self.transcription_pipeline.run()
        
        # Store transcription in the database
        self.db.insert_transcription(
            audio_filename=transcription_data["filename"],
            transcription=transcription_data["transcription"],
            language=transcription_data["language"],
            audio_filepath=transcription_data["audio_filepath"]
        )
        
        
        

if __name__ == "__main__":
    pipeline = FSEPipeline()
    pipeline.run()