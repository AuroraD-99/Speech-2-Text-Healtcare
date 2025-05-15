from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
from log import Logger
import os
import time


class DB:
    def __init__(self, uri="mongodb://localhost:27017/", db_name="transcriptions_db"):
        try:
            # Connessione al database MongoDB
            self.client = MongoClient(uri)
            self.db = self.client[db_name]
            # Definizione delle collezioni separate
            self.transcriptions = self.db["transcriptions"]
            self.fse_collection = self.db["fse"]
            # Logger per il monitoraggio
            self.logger = Logger(self.__class__.__name__).get_logger()
            self.logger.info("Connected to MongoDB successfully.")
        except ConnectionFailure as e:
            self.logger.error(f"Failed to connect to MongoDB: {e}")
            raise

    # Inserisce una trascrizione nella collezione 'transcriptions'
    def insert_transcription(self, audio_filename, transcription, language, audio_filepath):
        transcription_data = {
            "filename": audio_filename,
            "transcription": transcription,
            "language": language,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "audio_filepath": audio_filepath
        }
        result = self.transcriptions.insert_one(transcription_data)
        return result.inserted_id

    # Ottiene tutte le trascrizioni dalla collezione 'transcriptions'
    def get_all_transcriptions(self):
        return list(self.transcriptions.find())

    # Trova una trascrizione per 'filename'
    def find_transcription_by_filename(self, filename):
        return self.transcriptions.find_one({"filename": filename})

    # Aggiorna la trascrizione per 'filename'
    def update_transcription(self, filename, new_transcription):
        result = self.transcriptions.update_one(
            {"filename": filename},
            {"$set": {"transcription": new_transcription, "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")}}
        )
        return result.modified_count

    # Elimina una trascrizione per 'filename' e rimuove il file audio associato
    def delete_transcription(self, filename):
        transcription = self.transcriptions.find_one({"filename": filename})
        if transcription:
            audio_filepath = transcription.get("audio_filepath")
            if audio_filepath and os.path.exists(audio_filepath):
                os.remove(audio_filepath)
            result = self.transcriptions.delete_one({"filename": filename})
            return result.deleted_count
        return 0

    # Elimina tutte le trascrizioni e i file audio associati
    def delete_all_transcriptions(self):
        transcriptions = self.transcriptions.find()
        for transcription in transcriptions:
            audio_filepath = transcription.get("audio_filepath")
            if audio_filepath and os.path.exists(audio_filepath):
                os.remove(audio_filepath)
        result = self.transcriptions.delete_many({})
        return result.deleted_count

    # Inserisce un documento FSE nella collezione 'fse'
    def insert_fse(self, pdf_informations):
        if not pdf_informations or "filename" not in pdf_informations:
            raise ValueError("Il campo 'filename' è obbligatorio per inserire un FSE.")
        
        pdf_informations["timestamp"] = time.strftime("%Y-%m-%d %H:%M:%S")
        result = self.fse_collection.insert_one(pdf_informations)
        return result.inserted_id

    # Ottiene tutti i documenti FSE dalla collezione 'fse'
    def get_all_fse(self):
        return list(self.fse_collection.find())

    # Trova un documento FSE per 'filename'
    def find_fse_by_filename(self, filename):
        return self.fse_collection.find_one({"filename": filename})

    # Aggiorna un documento FSE per 'filename'
    def update_fse(self, filename, new_pdf_informations):
        result = self.fse_collection.update_one(
            {"filename": filename},
            {"$set": new_pdf_informations}
        )
        return result.modified_count

    # Elimina un documento FSE per 'filename'
    def delete_fse(self, filename):
        result = self.fse_collection.delete_one({"filename": filename})
        return result.deleted_count

    # Elimina tutti i documenti FSE
    def delete_all_fse(self):
        result = self.fse_collection.delete_many({})
        return result.deleted_count

    # Chiude la connessione al database
    def close(self):
        self.client.close()



if __name__ == "__main__":
    # Esempio di utilizzo
    db = DB()
    db.insert_transcription("example.wav", "This is a test transcription.", "en", "/path/to/audio/example.wav")
    transcriptions = db.get_all_transcriptions()
    print(transcriptions)
    
    
    fse_test = {
        "filename": "test_fse.pdf",
        "transcription": "This is a test FSE transcription.",
        "language": "it",
    }
    db.insert_fse(fse_test)
    fse = db.get_all_fse()

    db.close()