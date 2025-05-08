from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
from log import Logger
import time

class DB:
    def __init__(self, uri="mongodb://localhost:27017/", db_name="transcriptions_db", collection_name="transcriptions"):
        try:
            self.client = MongoClient(uri)
            self.db = self.client[db_name]
            self.collection = self.db[collection_name]
            self.logger = Logger(self.__class__.__name__).get_logger()
            self.logger.info("Connected to MongoDB successfully.")
        except ConnectionFailure as e:
            self.logger.error(f"Failed to connect to MongoDB: {e}")
            raise
    
    def insert_transcription(self, audio_filename, transcription, language, audio_filepath):
        transcription_data = {
            "filename": audio_filename,
            "transcription": transcription,
            "language": language,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "audio_filepath": audio_filepath
        }
        result = self.collection.insert_one(transcription_data)
        return result.inserted_id

    def get_all_transcriptions(self):
        return list(self.collection.find())

    def find_by_filename(self, filename):
        return self.collection.find_one({"filename": filename})

    def update_transcription(self, filename, new_transcription):
        result = self.collection.update_one(
            {"filename": filename},
            {"$set": {"transcription": new_transcription, "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")}}
        )
        return result.modified_count

    def delete_transcription(self, filename):
        result = self.collection.delete_one({"filename": filename})
        return result.deleted_count

    def close(self):
        self.client.close()
