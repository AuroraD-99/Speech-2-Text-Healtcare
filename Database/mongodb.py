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
import datetime
from dotenv import load_dotenv
import json
import random
from datetime import datetime, timedelta


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
    def insert_transcription(self, audio_filename="", transcription="", embedding_id="", language="", audio_filepath=""):
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
        #report["validated"] = False
        result = self.reports_collection.insert_one(report)
        
        
        try:
            doctor_cf = report["dati medico"]["Anagrafica"]["Codice Fiscale"]
            self.enqueue_report_for_doctor(doctor_cf, str(result.inserted_id))  # Aggiunge il referto alla coda del medico
            self.logger.info(f"Referto inserito nella coda per il medico con CF: {doctor_cf}")
        except KeyError as e:
            self.logger.error(f"Errore nell'inserimento del referto: {e}. Assicurati che il report contenga i dati del medico.")
            raise ValueError(f"Report non valido: {e} non trovato nei dati del report.")
        return result.inserted_id
    
    def insert_clinical_report_from_dataset(self, report_id, report):
        """
        Insert a clinical report into the 'clinical_reports' collection.
        """
        
        def genera_timestamp_casuale():
            oggi = datetime.now()
            un_anno_fa = oggi - timedelta(days=365)

            # Genera un datetime casuale tra un anno fa e oggi
            delta_secondi = int((oggi - un_anno_fa).total_seconds())
            timestamp_casuale = un_anno_fa + timedelta(seconds=random.randint(0, delta_secondi))

            # Formatta nel formato corretto: "YYYY-MM-DD HH:MM:SS"
            return timestamp_casuale.strftime("%Y-%m-%d %H:%M:%S")
        #si potrebbe anche aggiungere una voce che indica la validazione del referto per facilitare l'inserimento nel RAG

        # Campi obbligatori: report_id
        timestamp = genera_timestamp_casuale()
        report["timestamp"] = timestamp
        report["report_id"] = report_id #str(uuid.uuid4())  # ID unico per il report: coincide anche con quello per gli embedding e il referto
        #VA AGGIUNTO ANCHE L'ID DEL REFERTO NEL RAG PER IL RECUPERO
        
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
        
        
    # ---------------------SEZIONE ANALYTICS--------------------------
    def mean_reports(self, start_date, end_date):
        """
        Calcola la media dei referti totali diviso il numero di giorni dell'intervallo.
        start_date, end_date sono stringhe nel formato 'YYYY-MM-DD HH:mm:ss'.
        """
        pipeline = [
            {"$match": {"timestamp": {"$gte": start_date, "$lte": end_date}}},
            {"$count": "total_reports"}
        ]
        result = list(self.reports_collection.aggregate(pipeline))
        total_reports = result[0]["total_reports"] if result else 0
        

        # Calcolo numero giorni nell'intervallo
        fmt = "%Y-%m-%d %H:%M:%S"
        start_dt = datetime.datetime.strptime(start_date, fmt)
        end_dt = datetime.datetime.strptime(end_date, fmt)
        days_diff = (end_dt - start_dt).days + 1  # +1 per includere entrambi i giorni
        

        if days_diff <= 0:
            return 0

        return total_reports / days_diff

    def max_reports(self, start_date, end_date):
        """
        Calcola il numero massimo di referti giornalieri tra due date (stringhe nel formato 'YYYY-MM-DD HH:mm:ss').
        """
        pipeline = [
            {"$match": {"timestamp": {"$gte": start_date, "$lte": end_date}}},
            {
                "$group": {
                    "_id": {"$substr": ["$timestamp", 0, 10]},  # data YYYY-MM-DD
                    "count": {"$sum": 1}
                }
            },
            {
                "$group": {
                    "_id": None,
                    "max_count": {"$max": "$count"}
                }
            }
        ]
        result = list(self.reports_collection.aggregate(pipeline))
        return result[0]["max_count"] if result else 0

    def most_common_type(self, start_date, end_date):
        """
        Trova il tipo di referto più comune tra due date.
        """
        pipeline = [
            {"$match": {"timestamp": {"$gte": start_date, "$lte": end_date}}},
            {"$group": {"_id": "$type", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 1}
        ]
        result = list(self.reports_collection.aggregate(pipeline))
        return result[0]["_id"] if result else None

    def deaths(self, start_date_str, end_date_str):
        """
        Calcola il numero di decessi tra due date stringa.
        Il campo scheda_ps.Decesso.Ora decesso deve essere un orario valido,
        cioè non vuoto, non 'N/A' e deve corrispondere a un pattern orario HH:mm o HH.mm.
        """

        pipeline = [
            {
                "$match": {
                    "timestamp": {"$gte": start_date_str, "$lte": end_date_str},
                    "scheda_ps.Decesso.Ora decesso": {
                        "$exists": True,
                        "$ne": "",
                        "$ne": "N/A",
                        # regex per formati 18:30 oppure 18.30 (ore da 00 a 23, minuti da 00 a 59)
                        "$regex": r"^(?:[01]\d|2[0-3])[:.][0-5]\d$"
                    }
                }
            },
            {"$count": "death_count"}
        ]
        result = list(self.reports_collection.aggregate(pipeline))
        return result[0]["death_count"] if result else 0


    def analitiche_temporali(self, start_date, end_date):
        """
        Esegue un'analisi temporale dei referti tra due date.
        start_date, end_date sono stringhe 'YYYY-MM-DD HH:mm:ss'.
        """
        media = self.mean_reports(start_date, end_date)
        massimo = self.max_reports(start_date, end_date)
        tipo_comune = self.most_common_type(start_date, end_date)
        decessi = self.deaths(start_date, end_date)
        return media, massimo, tipo_comune, decessi
    
    def numero_referti_giornalieri(self, start_date, end_date):
        """
        Restituisce il numero di referti giornalieri tra due date.
        start_date, end_date sono stringhe nel formato 'YYYY-MM-DD HH:mm:ss'.
        """
        pipeline = [
            {
                "$match": {
                    "timestamp": {
                        "$gte": start_date,
                        "$lte": end_date
                    }
                }
            },
            {
                "$group": {
                    "_id": {
                        "$dateToString": {
                            "format": "%Y-%m-%d",
                            "date": {
                                "$dateFromString": {
                                    "dateString": "$timestamp",
                                    "format": "%Y-%m-%d %H:%M:%S"
                                }
                            }
                        }
                    },
                    "count": {"$sum": 1}
                }
            },
            {"$sort": {"_id": 1}}
        ]

        results = list(self.reports_collection.aggregate(pipeline))
        return [{"date": r["_id"], "count": r["count"]} for r in results]
    
    def top_medici(self, limit=10):
        """
        Restituisce i primi 'limit' medici ordinati per numero di referti,
        usando il campo dati medico.Anagrafica.Codice Fiscale.
        """
        pipeline = [
            {
                "$group": {
                    "_id": "$dati medico.Anagrafica.Codice Fiscale",
                    "count": {"$sum": 1},
                    "nome": {"$first": "$dati medico.Anagrafica.Nome"},
                    "cognome": {"$first": "$dati medico.Anagrafica.Cognome"}
                }
            },
            {"$sort": {"count": -1}},
            {"$limit": limit}
        ]
        results = list(self.reports_collection.aggregate(pipeline))
        return [
            {
                "nome_completo": f"{r.get('nome', '')} {r.get('cognome', '')}".strip(),
                "count": r["count"]
            }
            for r in results
    ]



    def referti_per_reparto(self):
        """
        Restituisce il conteggio dei referti per reparto,
        usando il campo dati medico.Ospedale.Reparto.
        """
        pipeline = [
            {"$group": {
                "_id": "$dati medico.Ospedale.Reparto",
                "count": {"$sum": 1}
            }},
            {"$sort": {"count": -1}}
        ]
        results = list(self.reports_collection.aggregate(pipeline))
        return [{"reparto": r["_id"], "count": r["count"]} for r in results]



    def referti_per_fascia_oraria(self, start_date, end_date):
        """
        Conta il numero di referti per fascia oraria (Mattina, Pomeriggio, Sera, Notte)
        nel range di date indicato.
        start_date e end_date sono stringhe 'YYYY/MM/DD HH:mm:ss'.
        """
        pipeline = [
            {"$match": {"timestamp": {"$gte": start_date, "$lte": end_date}}},
            {"$addFields": {
                "hour": {"$toInt": {"$substr": ["$timestamp", 11, 2]}}  # estrae ore dalla stringa "YYYY/MM/DD HH:mm:ss"
            }},
            {"$addFields": {
                "fascia": {
                    "$switch": {
                        "branches": [
                            {"case": {"$and": [{"$gte": ["$hour", 6]}, {"$lt": ["$hour", 12]}]}, "then": "Mattina"},
                            {"case": {"$and": [{"$gte": ["$hour", 12]}, {"$lt": ["$hour", 18]}]}, "then": "Pomeriggio"},
                            {"case": {"$and": [{"$gte": ["$hour", 18]}, {"$lt": ["$hour", 24]}]}, "then": "Sera"},
                        ],
                        "default": "Notte"
                    }
                }
            }},
            {"$group": {
                "_id": "$fascia",
                "count": {"$sum": 1}
            }},
            {"$sort": {"_id": 1}}  # Ordina per fascia
        ]

        results = list(self.reports_collection.aggregate(pipeline))
        return {r["_id"]: r["count"] for r in results}


    def heatmap_reparto_giorno(self, start_date, end_date):
        pipeline = [
            {
                "$match": {
                    "timestamp": {
                        "$gte": start_date,
                        "$lte": end_date
                    }
                }
            },
            {
                "$project": {
                    "reparto": {
                        "$ifNull": ["$dati medico.Ospedale.Reparto", "Sconosciuto"]
                    },
                    "dayOfWeek": {
                        "$dayOfWeek": {
                            "$dateFromString": {
                                "dateString": "$timestamp",
                                "format": "%Y-%m-%d %H:%M:%S"
                            }
                        }
                    }
                }
            },
            {
                "$group": {
                    "_id": {"reparto": "$reparto", "dayOfWeek": "$dayOfWeek"},
                    "count": {"$sum": 1}
                }
            },
            {
                "$sort": {"_id.reparto": 1, "_id.dayOfWeek": 1}
            }
        ]
        results = list(self.reports_collection.aggregate(pipeline))

        heatmap = {}
        for r in results:
            rep = r["_id"]["reparto"]
            day = r["_id"]["dayOfWeek"]
            heatmap.setdefault(rep, {})[day] = r["count"]
        return heatmap
    
    
    def stagionalita_tipo_referto(self, start_date, end_date):
        pipeline = [
            {
                "$match": {
                    "timestamp": {
                        "$gte": start_date,
                        "$lte": end_date
                    },
                    "type": {"$exists": True, "$ne": None}   # SOLO documenti con 'type' definito e non null
                }
            },
            {
                "$project": {
                    "type": 1,
                    "date": {
                        "$dateFromString": {
                            "dateString": "$timestamp",
                            "format": "%Y-%m-%d %H:%M:%S"
                        }
                    }
                }
            },
            {
                "$group": {
                    "_id": {
                        "date": {"$dateToString": {"format": "%Y-%m-%d", "date": "$date"}},
                        "type": "$type"
                    },
                    "count": {"$sum": 1}
                }
            },
            {
                "$sort": {"_id.date": 1}
            }
        ]

        results = list(self.reports_collection.aggregate(pipeline))
        return results
    
    def parallel_coords_data(self, start_date, end_date):
        pipeline = [
            {
                "$match": {
                    "timestamp": {
                        "$gte": start_date,
                        "$lte": end_date
                    },
                    "dati medico.Ospedale.Reparto": {"$exists": True, "$ne": None}
                }
            },
            {
                "$project": {
                    "reparto": "$dati medico.Ospedale.Reparto",
                    "date": {
                        "$dateToString": {
                            "format": "%Y-%m-%d",
                            "date": {
                                "$dateFromString": {
                                    "dateString": "$timestamp",
                                    "format": "%Y-%m-%d %H:%M:%S"
                                }
                            }
                        }
                    }
                }
            },
            {
                "$group": {
                    "_id": {
                        "reparto": "$reparto",
                        "date": "$date"
                    },
                    "count_giornaliero": {"$sum": 1}
                }
            },
            {
                "$group": {
                    "_id": "$_id.reparto",
                    "totale_referti": {"$sum": "$count_giornaliero"},
                    "giorni_attivi": {"$sum": 1},
                    "media_giornaliera": {"$avg": "$count_giornaliero"}
                }
            },
            {
                "$sort": {"totale_referti": -1}
            }
        ]

        results = list(self.reports_collection.aggregate(pipeline))
        return results




    
    # Chiude la connessione al database
    def close(self):
        self.client.close()
   

if __name__ == "__main__":
    db = DB()
    load_dotenv('key.env', override=True)
    dataset_path = os.getenv("dataset_path")

    base_dir = os.path.dirname(os.path.abspath(__file__))
    medici_file_path = os.path.join(base_dir, "medici_unici.json")
    medici_unici_set = set()
    medici_unici_list = []

    # Ospedale fisso senza reparto
    ospedale_fisso_base = {
        "Nome Ospedale": "Ospedale Maggiore",
        "Città": "Bologna",
        "Provincia": "BO",
        "CAP": "40138",
        # "Reparto": ... -> da scegliere casualmente
    }

    reparti_possibili = [
        "Pronto Soccorso",
        "Medicina d'urgenza",
        "Terapia intensiva",
        "Cardiologia",
        "Ortopedia",
        "Neurologia"
    ]

    try:
        with open(dataset_path, 'r', encoding='utf-8') as file:
            data = [json.loads(line) for line in file]

        for idx, row in enumerate(data):  # Limita a 5 righe per test
            line_number = idx + 1
            report_str = row.get("referto")
            transcription_str = row.get("referto_simulato")
            report_id = row.get("report_id")

            if transcription_str:
                db.insert_transcription(transcription=transcription_str)
            if report_str and report_id:
                try:
                    loaded = json.loads(report_str)
                    report_data = loaded[0] if isinstance(loaded, list) and len(loaded) > 0 else loaded

                    dati_medico = report_data.get("dati medico", {})
                    anagrafica_keys = ["Email", "Nome", "Cognome", "Cellulare", "Codice Fiscale", "Ruolo"]
                    anagrafica = {k: dati_medico.get(k, "N/A") for k in anagrafica_keys}

                    chiave_medico = anagrafica.get("Codice Fiscale", "") + anagrafica.get("Email", "")
                    if chiave_medico not in medici_unici_set:
                        medici_unici_set.add(chiave_medico)
                        # Il reparto è scelto casualmente solo qui, nei dati unici medici
                        reparto_casuale = random.choice(reparti_possibili)
                        ospedale_con_reparto = {**ospedale_fisso_base, "Reparto": reparto_casuale}
                        medici_unici_list.append({
                            "Anagrafica": anagrafica,
                            "Ospedale": ospedale_con_reparto
                        })

                    # Ricostruisco il referto con reparto casuale
                    reparto_casuale = random.choice(reparti_possibili)
                    ospedale_con_reparto = {**ospedale_fisso_base, "Reparto": reparto_casuale}
                    report_data["dati medico"] = {
                        "Anagrafica": anagrafica,
                        "Ospedale": ospedale_con_reparto
                    }

                    report_data["validated"] = True

                    db.insert_clinical_report(report_id=report_id, report=report_data)
                    print(f"[✔️ Riga {line_number}] Referto inserito correttamente.")

                except json.JSONDecodeError as e:
                    print(f"[Errore parsing JSON - Riga {line_number}] {e}")
                except Exception as e:
                    print(f"[Errore inserimento - Riga {line_number}] {e}")

        with open(medici_file_path, 'w', encoding='utf-8') as f:
            json.dump(medici_unici_list, f, indent=2, ensure_ascii=False)
        print(f"\n✅ File medici unici salvato in: {medici_file_path}")
        
        # Inserimento dei medici nel database operatori
        for medico in medici_unici_list:
            medico["Anagrafica"]["Password"] = "Password123."
            new_data = {
                **medico,
            }
            try:
                db.insert_operator(new_data)
                print(f"[✔️ Operatore] Inserito: {medico['Anagrafica']['Codice Fiscale']}")
            except Exception as e:
                print(f"[❌ Errore inserimento operatore] {e}")

    except Exception as e:
        print(f"[❌ Errore JSON] Errore nel parsing del dataset: {e}")
        
    amministratore = {
            "Anagrafica": {
                "Email": "amministratore1@gmail.com",
                "Password": "Password123.",
                "Nome": "Gennaro",
                "Cognome": "Esposito",
                "Cellulare": "3331234567",
                "Codice Fiscale": "GNSGNN80A01H703Z",  # Esempio di CF
                "Ruolo": "Amministratore",
                "Primo Accesso": True
            },
            "Ospedale": {
                "Nome Ospedale": "Ospedale Maggiore",
                "Città": "Bologna",
                "Provincia": "BO",
                "CAP": "40138",
                "Reparto": "Amministrazione",
            },
        }
        
    db.insert_operator(amministratore)