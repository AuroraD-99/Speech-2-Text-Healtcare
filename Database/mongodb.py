from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
from log import Logger
import os 
import time


Scheda_FSE = {
    "filename": ,
    "transcription": ,
    "language": ,
    "timestamp": ,
    "audio_filepath": ,
    "scheda": {
        "Chiamata":{
            "data":,
            "H chiamata":,
            "H partenza":,
            "H sul posto":,
            "H partenza posto",
            "H in PS":,
            "H libero e operativo":,
            "luogo intervento":,
            "condizione riferita":,
            "recapito telefonico":
        },
        "Ambulanza":{
          "CRI":,
          "SEL":,  
        },
        "Equipaggio":{
            "Aut.":,
            "Socc1":,
            "Socc2":,
            "IP":,
            "Medico":,
        },
        "Causa trasporto non effettuato":,
        "Attivazioni/Autorità presenti":{
            "Descrizione":,
            "Referto":,
        },
        "Dati anagrafica paziente":{
            "Cognome Nome":,
            "Sesso":,
            "Nato il":,
            "A":,
            "Prov_nascita":,
            "Residente a":,
            "Prov_residenza":,
            "Via":,
            "N":,
            "Telefono":,
            "Dati dichiarati da":,
        },
        "Decesso":{
            "Ora decesso":,
            "Firma":,
        },
        "Rifiuto (firma dell'interessato)":{
          "Firma":,  
        },
        "Rilevazioni":{
            "Parametri":{
                "Coscienza":,
                "Cute":,
                "Respiro":,
                "Sp02":,
                "FC bpm":,
                "PA mmHg":,
                "Glic, Mg/dl":,
                "Temp. C°":,
            },
            "Glasgow Coma Scale":{
                "Apertura occhi":,
                "Risposta verbale":,
                "Risposta motoria":,
            },
            "Pupille":,
            "Lesioni riscontrate":
        }
        "Provvedimenti":{
            "Respiro":,
            "Circolo":,
            "Immobilizzazione":,
            "Altro":,
            "Infusioni/Farmaci":,
        }
        "Annotazioni":
    }
    
    "FSE":{
        "Dati identificativi amministrativi":{
            "Nome":,
            "Età":,
            "Sesso":,
        },
        "Referto laboratorio":{
            "Esame":,
            "Risultati":,
            "Data":,
        },
        "Referto radiologia":{
            "Esame":,
            "Referto":,
            "Data":,
        },
        "Referto specialisitca ambulatoriale":{
            "Descrizione visita":,
            "Note":,
        },
        "Referto anatomia patologica":{
            "Descrizione":,
            "Referto":,
        },
        "Verbale pronto soccorso":{
            "Motivo accesso":,
            "Trattamento":,
        },
        "Lettera dimissione":{
            "Diagnosi dimissione":,
            "Terapia domiciliare":,
        },
        "Profilo sanitario sintetico":{
            "Condizioni pregresse":,
            "Allergie":,
        },
        "Prescrizione farmaceutica":{
            "Farmaci":,
        },
        "Prescrizione specialistica":{
            "Esami prescritti":,
        },
        "Cartella clinica":{
            "Contenuto":,
        },
        "Erogazione farmaci":{
            "Farmaci erogati":,
            "Farmaci acquistati privato":,
        },
        "Scheda singola vaccinazione":{
            "Vaccino":,
            "Dose":,
            "Data":,
        },
        "Certificato stato vaccinale":{
            "Vaccini completati":,
            "Note":,
        },
        "Erogazione prestazione specialistica":{
            "Prestazioni":,
        },
        "Taccuino personale assistito":{
            "Note personali":,
        },
        "Tessera portatore impianto":{
            "Impianto":,
        },
        "Lettera invito screening prevenzione":{
            "Programma":,
            "Data invito":,
        },
    }
}

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
        self.collection = self.db["transcriptions"] if "transcriptions" in self.db.list_collection_names() else self.db.create_collection("transcriptions")
        result = self.collection.insert_one(transcription_data)
        return result.inserted_id

    def get_all_transcriptions(self):
        self.collection = self.db["transcriptions"] if "transcriptions" in self.db.list_collection_names() else self.db.create_collection("transcriptions")
        return list(self.collection.find())

    def find_by_filename(self, filename):
        self.collection = self.db["transcriptions"] if "transcriptions" in self.db.list_collection_names() else self.db.create_collection("transcriptions")
        return self.collection.find_one({"filename": filename})

    def update_transcription(self, filename, new_transcription):
        self.collection = self.db["transcriptions"] if "transcriptions" in self.db.list_collection_names() else self.db.create_collection("transcriptions")
        result = self.collection.update_one(
            {"filename": filename},
            {"$set": {"transcription": new_transcription, "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")}}
        )
        return result.modified_count

    def delete_transcription(self, filename):
        
        """ 
        Delete a transcription by filename and remove the associated audio file.
        """
        self.collection = self.db["transcriptions"] if "transcriptions" in self.db.list_collection_names() else self.db.create_collection("transcriptions")
        transcription = self.collection.find_one({"filename": filename})
        if transcription:
            audio_filepath = transcription.get("audio_filepath")
            if audio_filepath and os.path.exists(audio_filepath):
                os.remove(audio_filepath)
            result = self.collection.delete_one({"filename": filename})
            return result.deleted_count
        return 0

    
    def delete_all_transcriptions(self):
        """ 
        Delete all transcriptions and remove all associated audio files.
        """
        self.collection = self.db["transcriptions"] if "transcriptions" in self.db.list_collection_names() else self.db.create_collection("transcriptions")
        transcriptions = self.collection.find()
        for transcription in transcriptions:
            audio_filepath = transcription.get("audio_filepath")
            if audio_filepath and os.path.exists(audio_filepath):
                os.remove(audio_filepath)
        result = self.collection.delete_many({})
        return result.deleted_count
    
    

    def close(self):
        self.client.close()
        
        
    
        
        
if __name__ == "__main__":
    db = DB()
    # Example usage
    db.delete_all_transcriptions()