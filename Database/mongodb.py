from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
from log import Logger
import os
import time
import uuid
import numpy as np
from typing import List, Optional
import bcrypt
from bson import Binary
from bson import ObjectId
import redis

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
            #Per le code Redis
            self.redis = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
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
    
    #Recupera tutte le trascrizioni associate a una lista di embedding_id
    def get_all_transcription_by_embedding_id(self, embedding_ids: List[str]):
        return list(self.transcriptions.find({"embedding_id": {"$in": embedding_ids}}))

    
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
        
        
        try:
            doctor_cf = report["dati medico"]["Anagrafica"]["Codice Fiscale"]
            self.enqueue_report_for_doctor(doctor_cf, str(result.inserted_id))  # Aggiunge il referto alla coda del medico
            self.logger.info(f"Referto inserito nella coda per il medico con CF: {doctor_cf}")
        except KeyError as e:
            self.logger.error(f"Errore nell'inserimento del referto: {e}. Assicurati che il report contenga i dati del medico.")
            raise ValueError(f"Report non valido: {e} non trovato nei dati del report.")
        return result.inserted_id

    
    def get_clinical_reports_by_patient(self, patient_id):
        """
        Returns all clinical reports for a specific patient.
        """
        return list(self.reports_collection.find({"patient_id": patient_id}))
    
    def get_all_clinical_reports_by_doctor_cf(self, doctor_cf):
        
        report_ids = self.get_queue_for_doctor(doctor_cf)

        if not report_ids:
            self.logger.warning(f"Nessun report trovato nella coda per il medico con CF {doctor_cf}.")
            reports = list(self.reports_collection.find({"dati medico.Anagrafica.Codice Fiscale": doctor_cf}))

            for report in reports:
                self.enqueue_report_for_doctor(doctor_cf, str(report["_id"]))
            
            return reports

        # Converti gli ID in ObjectId in sicurezza
        object_ids = []
        for report_id in report_ids:
            try:
                object_ids.append(ObjectId(report_id))
            except Exception as e:
                self.logger.warning(f"ID non valido nella coda Redis: {report_id} → {e}")

        reports = list(self.reports_collection.find({"_id": {"$in": object_ids}}))

        # Ricostruzione ordinata
        id_to_report = {str(report["_id"]): report for report in reports}
        ordered_reports = [id_to_report[report_id] for report_id in report_ids if report_id in id_to_report]

        return ordered_reports
    
    def get_validated_clinical_report(self, report_id: str) -> dict:
        #Recupera un referto validato. Se non è validato, restituisce None e mostra un warning.

        report = self.reports_collection.find_one({"report_id": report_id, "validated": True})
        
        if not report:
            print(f"[WARNING] Il referto con ID {report_id} non è ancora stato validato o non esiste.")
            return None
        
        return report

    def get_report_by_id(self, report_id):
        """
        Returns a clinical report by report_id.
        """
        return self.reports_collection.find_one({"_id": ObjectId(report_id)})
    
    def get_all_clinical_reports(self, query={}, limit = 30):
        """
        Returns all clinical reports.
        """
        return list(self.reports_collection.find(query).limit(limit))
    
    def find_clinical_report_by_patient(self, patient_name):
        """
        returns a clinical report for a specific patient.
        """
        return self.reports_collection.find_one({"name": patient_name})
    
    def update_clinical_report(self, report_id, new_report):
        """
        Update a clinical report by report_id.
        """
        self.logger.info(f"Aggiornamento del referto con ID {report_id} con i nuovi dati: {new_report}")
        result = self.reports_collection.update_one(
            {"_id": ObjectId(report_id)},
            {"$set": new_report}
        )
        return result.modified_count
    
    def delete_clinical_report(self, report_id):
        """
        Delete a clinical report by report_id.
        """
        report = self.reports_collection.find_one({"_id": report_id})
        if report:
            doctor_cf = report["dati medico"]["Anagrafica"]["Codice Fiscale"]
            key = f"queue:referti:{doctor_cf}"
            self.redis.lrem(key, 0, str(report_id))
        result = self.reports_collection.delete_one({"_id": report_id})
        return result.deleted_count
    
    def delete_all_reports_by_patient(self, patient_name, doctor_cf=None):
        """
        Delete all clinical reports of a patient.
        """
        result = self.reports_collection.delete_many({"name": patient_name}, {"doctor_cf": doctor_cf})
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
     
    #--------------------------------------------------- PERSONALE MEDICO ------------------------------------------------------
    def insert_operator(self, new_user):
        """
        Inserisce un operatore medico nella collezione 'medical_operators' con la seguente struttura:
        {
            "Anagrafica": {
                "Email":,
                "Password":,
                "Nome":,
                "Cognome":,
                "Cellulare":,
                "Codice Fiscale":,
                "Ruolo":,  # ad esempio "Medico", "Infermiere", etc.
                
            }
            "Ospedale": {
                "Nome Ospedale":,
                "Città":,
                "Provincia":,
                "CAP":,
                "Reparto":,
                
            }
        }
        
        La password viene cryptata prima di essere memorizzata nel database.
        """
        # Controlla se l'operatore esiste già
        existing_operator = self.get_operator(new_user["Anagrafica"]["Email"])
        if existing_operator:
            raise ValueError("Operatore già esistente")

        # Crittografia della password
        hashed_password = self.hash_password(new_user["Anagrafica"]["Password"])

        # Inserimento dell'operatore
        new_user["Anagrafica"]["Password"] = hashed_password
        result = self.operators_collection.insert_one(new_user)
        return result.inserted_id
    
    def hash_password(self, password):
        """
        Crittografa la password utilizzando bcrypt.
        """
        if isinstance(password, str):
            password = password.encode('utf-8')  # codifica solo se è una stringa

        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(password, salt)
        return hashed

    
    def get_operator(self, email):
        """
        Recupera un operatore medico dato il nome utente.
        """
        # L'email si trova sotto il campo "EMail" all'interno della struttura "Anagrafica"
        
        return self.operators_collection.find_one({"Anagrafica.Email": email})
    
    def get_operator_by_name_and_surname(self, name, surname):
        """
        Recupera un operatore medico dato il nome e il cognome.
        """
        return self.operators_collection.find_one({"anagrafica.name": name, "anagrafica.surname": surname})
    
    def get_operator_by_cf(self, cf):
        """
        Recupera un operatore medico dato il codice fiscale.
        """
        return self.operators_collection.find_one({"anagrafica.CF": cf})
    
    def update_operator(self, email, updated_data):
        """
        Aggiorna i dati di un operatore medico dato il nome utente.
        """
        # Crittografia della nuova password se presente
        
        hashed_password = self.hash_password(updated_data["Anagrafica"]["Password"])
        updated_data["Anagrafica"]["Password"] = hashed_password
        result = self.operators_collection.update_one(
            {"Anagrafica.Email": email},
            {"$set": updated_data}
        )
        return result.modified_count
    
    def update_administrator(self, id, updated_data):
        """
        Aggiorna i dati di un amministratore dato l'id.
        """
        # Crittografia della nuova password se presente
        hashed_password = self.hash_password(updated_data["Anagrafica"]["Password"])
        updated_data["Anagrafica"]["Password"] = hashed_password

        result = self.operators_collection.update_one(
            {"_id": ObjectId(id)},
            {"$set": updated_data}
        )
        return result.modified_count

    #----------------------------------------- PER LE CODE REDIS --------------------------------------------------
    #TODO: FINIRE DI INTEGRARE NEL SISTEMA LE CODE REDIS
    def enqueue_report_for_doctor(self, doctor_cf: str, report_id: str):
        """
        Aggiunge un referto alla coda Redis per il medico identificato dal CF.
        """
        key = f"queue:referti:{doctor_cf}"
        self.redis.rpush(key, report_id)  # inserisce in coda (push a destra)

    def dequeue_report_for_doctor(self, doctor_cf: str) -> Optional[str]:
        """
        Estrae il prossimo report_id dalla coda Redis per il medico (FIFO).
        """
        key = f"queue:referti:{doctor_cf}"
        return self.redis.lpop(key)

    def get_queue_for_doctor(self, doctor_cf: str) -> List[str]:
        """
        Ritorna tutti i report_id attualmente nella coda del medico.
        """
        key = f"queue:referti:{doctor_cf}"
        return self.redis.lrange(key, 0, -1)

    def clear_queue_for_doctor(self, doctor_cf: str):
        key = f"queue:referti:{doctor_cf}"
        self.redis.delete(key)
    
    def refresh_queue_for_doctor(self, doctor_cf: str):
        """
        Ricostruisce la coda Redis dei referti per il medico specificato.
        """
        self.clear_queue_for_doctor(doctor_cf)
        reports = self.reports_collection.find({"dati medico.Anagrafica.Codice Fiscale": doctor_cf})
        for report in reports:
            self.enqueue_report_for_doctor(doctor_cf, str(report["_id"]))
        self.logger.info(f"Coda Redis aggiornata per il medico {doctor_cf}.")


    
    # Chiude la connessione al database
    def close(self):
        self.client.close()
   


if __name__ == "__main__":
    # Esempio di utilizzo
    db = DB()    
    
    db.insert_operator({
        "Anagrafica": {
            "Email": "amministratore1@gmail.com",
            "Password": "GennyPeppeAurora123.",
            "Nome": "Gennaro",
            "Cognome": "Esposito",
            "Cellulare": "3331234567",
            "Codice Fiscale": "ESPGRN80A01H703Z",
            "Ruolo": "Amministratore",
            "Primo Accesso": True,  # Indica se è il primo accesso
        },
        "Ospedale": {
            "Nome Ospedale": "Ospedale Generico",
            "Città": "Napoli",
            "Provincia": "NA",
            "CAP": "80100",
            "Reparto": "Amministrazione",
        }
    }
)
    