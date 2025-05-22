from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
from log import Logger
import os
import time
import uuid
import numpy as np
from typing import List
import bcrypt

# Struttura Trascrizioni: filename, transcription, language, timestamp, audio_filepath
# Struttura clinical report: sottoparte della struttura FSE
# Struttura operatore ospedaliero: username, password, anagrafica, ruolo
#Struttura embedding: è necessaria per ottimizzare il RAG, così ogni volta che viene inizializzato il sistema non è necessario ricalcolare gli embeddings

class DB:
    def __init__(self, uri="mongodb://localhost:27017/", db_name="clinical_report_transcriptions"):
        """
        Inizializza la connessione al database MongoDB.
        """
        try:
            # Connessione al database MongoDB
            self.client = MongoClient(uri)
            self.db = self.client[db_name]
            # Definizione delle collezioni separate
            self.transcriptions = self.db["transcriptions"]
            self.reports_collection = self.db["clinical_reports"] #deve contenere anche l'id dell'embedding
            self.operators_collection = self.db["medical_operators"]
            self.RAG_embedding_cache = self.db["RAG_embeddings_cache"]
            # Logger per il monitoraggio
            self.logger = Logger(self.__class__.__name__).get_logger()
            self.logger.info("Connected to MongoDB successfully.")
        except ConnectionFailure as e:
            self.logger.error(f"Failed to connect to MongoDB: {e}")
            raise

    #-------------------------------------------- TRANSCRIPTION -------------------------------------------------------------

    # Inserisce una trascrizione nella collezione 'transcriptions'
    def insert_transcription(self, audio_filename, transcription, embedding_id, language, audio_filepath):
        transcription_data = {
            "transcription_id": str(uuid.uuid4()),  # Genera un ID unico per la trascrizione
            "filename": audio_filename,
            "transcription": transcription,
            "embedding_id": embedding_id, #id dell'embedding
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
                try:
                    os.remove(audio_filepath)
                except FileNotFoundError:
                    self.logger.warning(f"File non trovato: {audio_filepath}")
        result = self.transcriptions.delete_many({})
        return result.deleted_count
    
    #--------------------------------------------- CLINICAL REPORT -------------------------------------------------------------
    
    def insert_clinical_report(self, report_id, report):
        """
        Insert a clinical report into the 'clinical_reports' collection.
        """
        #si potrebbe anche aggiungere una voce che indica la validazione del referto per facilitare l'inserimento nel RAG

        # Campi obbligatori: report_id
        report["report_id"] = report_id #str(uuid.uuid4())  # ID unico per il report: coincide anche con quello per gli embedding e il referto
        #VA AGGIUNTO ANCHE L'ID DEL REFERTO NEL RAG PER IL RECUPERO
        report["timestamp"] = time.strftime("%Y-%m-%d %H:%M:%S")
        report["validated"] = False
        result = self.reports_collection.insert_one(report)
        return result.inserted_id

    
    def get_clinical_reports_by_patient(self, patient_id):
        """
        Returns all clinical reports for a specific patient.
        """
        return list(self.reports_collection.find({"patient_id": patient_id}))
    
    def get_all_clinical_reports_by_doctor_cf(self, doctor_cf):
        """
        Returns all clinical reports for a specific doctor.
        """
        return list(self.reports_collection.find({"doctor_cf": doctor_cf}))
    
    def get_validated_clinical_report(self, report_id: str) -> dict:
        #Recupera un referto validato. Se non è validato, restituisce None e mostra un warning.

        report = self.reports_collection.find_one({"report_id": report_id, "validated": True})
        
        if not report:
            print(f"[WARNING] Il referto con ID {report_id} non è ancora stato validato o non esiste.")
            return None
        
        return report

       
    def get_all_clinical_reports(self):
        """
        Returns all clinical reports.
        """
        return list(self.reports_collection.find())
    
    def find_clinical_report_by_patient(self, patient_name):
        """
        returns a clinical report for a specific patient.
        """
        return self.reports_collection.find_one({"name": patient_name})
    
    def update_clinical_report(self, report_id, new_report):
        """
        Update a clinical report by report_id.
        """
        result = self.reports_collection.update_one(
            {"report_id": report_id},
            {"validater": True},
            {"$set": new_report}
        )
        return result.modified_count
    
    def delete_clinical_report(self, report_id):
        """
        Delete a clinical report by report_id.
        """
        result = self.reports_collection.delete_one({"report_id": report_id})
        return result.deleted_count
    
    def delete_all_clinical_reports_of_a_patient(self, patient_name):
        """
        Delete all clinical reports of a patient.
        """
        result = self.reports_collection.delete_many({"name": patient_name})
        return result.deleted_count
    
    def group_clinical_reports_by_patient_name(self, patient_name):
        """
        Group clinical reports by patient name.
        """
        pipeline = [
            {"$match": {"name": patient_name}},
            {"$group": {"_id": "$name", "reports": {"$push": "$$ROOT"}}}
        ]
        return list(self.reports_collection.aggregate(pipeline))
        

    """# Inserisce un documento FSE nella collezione 'fse'
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
    def find_fse_by_name(self, name):
        return self.fse_collection.find_one({"name": name})

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
        return result.deleted_count"""
    
    #--------------------------------------------------- EMBEDDING ------------------------------------------------------

    def insert_embedding(self, embedding_data: dict) -> bool:
        try:
            if not isinstance(embedding_data, dict):
                raise TypeError("embedding_data must be a dict")

            # Convertiamo eventuali numpy array
            if isinstance(embedding_data.get("embedding"), np.ndarray):
                embedding_data["embedding"] = embedding_data["embedding"].tolist()

            result = self.RAG_embedding_cache.insert_one(embedding_data)
            return result.inserted_id
        except Exception as e:
            print(f"[ERROR] insert_embedding: {e}")
            return False


    def get_embedding_by_id(self, doc_id: str) -> dict:
        """Recupera un embedding dato un ID."""
        return self.RAG_embedding_cache.find_one({"_id": doc_id})  

    def get_embeddings_by_doc_cf(self, cf: str) -> List[dict]: 
        return list(self.RAG_embedding_cache.find({"metadata.medico_cf": cf}))
     
    #--------------------------------------------------- PERSONALE MEDICO ------------------------------------------------------
    def insert_operator(self, username, password, anagrafica, ruolo):
        """
        Inserisce un operatore medico nella collezione 'medical_operators' con la seguente struttura:
        {
            "username": username,
            "password": password,
            "anagrafica": {
                "name": name,
                "surname": surname,
                "birthdate": birthdate,
                "CF": cf,
                "address": address,
            },
            "ruolo": ruolo
        }
        
        La password viene cryptata prima di essere memorizzata nel database.
        """
        # Controlla se l'operatore esiste già
        existing_operator = self.operators_collection.find_one({"username": username})
        if existing_operator:
            raise ValueError("Operatore già esistente")

        # Crittografia della password
        hashed_password = self.hash_password(password)

        # Inserimento dell'operatore
        operator_data = {
            "username": username,
            "password": hashed_password,
            "anagrafica": anagrafica,
            "ruolo": ruolo
        }
        result = self.operators_collection.insert_one(operator_data)
        return result.inserted_id
    
    def hash_password(self, password):
        """
        Crittografa la password utilizzando bcrypt.
        """
        if isinstance(password, str):
            password = password.encode('utf-8')  # codifica solo se è una stringa

        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(password, salt)
        return hashed.decode('utf-8')

    
    def get_operator(self, username):
        """
        Recupera un operatore medico dato il nome utente.
        """
        return self.operators_collection.find_one({"username": username})

    # Chiude la connessione al database
    def close(self):
        self.client.close()



if __name__ == "__main__":
    # Esempio di utilizzo
    db = DB()
    db.insert_clinical_report({
        "report_id": "12345",
        "cf_paziente": "ABC123",
        "cf_medico": "XYZ789",
        
        "name": "Mario Rossi",
        "Patologia":"Morto"
    })
    
    
    db.insert_clinical_report({
        "report_id": "12345",
        "cf_paziente": "ABC123",
        "cf_medico": "XYZ789",
        
        "name": "Mario Rossi",
        "Patologia":"Ho sbagliato è ancora vivo"
    })
    
    print(db.group_clinical_reports_by_patient_name("Mario Rossi"))
    db.delete_all_clinical_reports_of_a_patient("Mario Rossi")
    print(db.get_all_clinical_reports())
    
    db.close()