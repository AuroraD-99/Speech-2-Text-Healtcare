from collections import Counter
from bson.objectid import ObjectId
import matplotlib.pyplot as plt
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from Database.mongodb import DB

class Analytics:
    def __init__(self, db):
        """
        Inizializza la classe Analytics con un'istanza del database DB.
        """
        self.db = db

    # -------------------------- TRASCRIZIONI --------------------------

    def average_visits_per_day(self, cf=None):
        """
        Calcola la media giornaliera di trascrizioni.
        Se viene fornito il codice fiscale del medico, filtra le trascrizioni associate.
        """
        match_stage = {}
        if cf:
            match_stage = {"dati medico.Anagrafica.Codice Fiscale": cf}

        pipeline = [
            {"$match": match_stage} if match_stage else {"$match": {}},
            {"$project": {
                "day": {"$substr": ["$timestamp", 0, 10]}
            }},
            {"$group": {"_id": "$day", "count": {"$sum": 1}}},
            {"$group": {
                "_id": None,
                "average_per_day": {"$avg": "$count"}
            }}
        ]
        result = list(self.db.transcriptions.aggregate(pipeline))
        return result[0]["average_per_day"] if result else 0

    # -------------------------- REFERTI CLINICI --------------------------

    def reports_per_patient(self):
        """
        Conta quanti referti ha ogni paziente.
        """
        pipeline = [
            {"$group": {"_id": "$patient_id", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}}
        ]
        return list(self.db.reports_collection.aggregate(pipeline))

    def pathology_distribution_by_doctor(self):
        """
        Conta la distribuzione delle patologie trattate da ciascun medico.
        Si assume che la diagnosi sia nel campo 'diagnosi' del referto.
        """
        pipeline = [
            {"$match": {"validated": True}},
            {"$group": {
                "_id": {
                    "medico_cf": "$dati medico.Anagrafica.Codice Fiscale",
                    "diagnosi": "$diagnosi"
                },
                "count": {"$sum": 1}
            }},
            {"$sort": {"count": -1}}
        ]
        return list(self.db.reports_collection.aggregate(pipeline))

    def patients_with_diagnosis_by_doctor(self, diagnosis, doctor_cf): #Lista dei pazienti con una specifica diagnosi, seguiti da un determinato medico.

        pipeline = [
            {"$match": {
                "diagnosi": diagnosis,
                "dati medico.Anagrafica.Codice Fiscale": doctor_cf
            }},
            {"$group": {"_id": "$patient_id"}}
        ]
        return list(self.db.reports_collection.aggregate(pipeline))

    def high_risk_patients(self, threshold=5):
        """
        Trova i pazienti che hanno un numero elevato di referti (alto carico clinico).
        """
        pipeline = [
            {"$group": {"_id": "$patient_id", "report_count": {"$sum": 1}}},
            {"$match": {"report_count": {"$gt": threshold}}},
            {"$sort": {"report_count": -1}}
        ]
        return list(self.db.reports_collection.aggregate(pipeline))

    # -------------------------- OPERATORI MEDICI --------------------------

    def operators_by_role(self): #deve stampare anche la lista degli operatori
        """
        Conta gli operatori per tipo di ruolo.
        """
        pipeline = [
            {"$group": {"_id": "$Anagrafica.Ruolo", "count": {"$sum": 1}}}
        ]
        return list(self.db.operators_collection.aggregate(pipeline))

    def operator_distribution_by_hospital(self):
        """
        Ritorna la distribuzione del personale per ospedale.
        """
        pipeline = [
            {"$group": {"_id": "$Ospedale.Nome Ospedale", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}}
        ]
        return list(self.db.operators_collection.aggregate(pipeline))

    def reports_per_operator(self): #lo fa per ogni medico
        #TODO: MODIFICARE IN MODO CHE VENGA USATO DAL MEDICO REFERTENTE PER CONTROLLARE IL LAVORO DEGLI INTERN 
        #TODO: FARE SECONDA VERSIONE IN CUI VIENE PASSATO IL CF DEL MEDICO E VISUALIZZATI SOLO I SUOI REFERTI DA VALIDARE
        """
        Numero di referti validati per ciascun medico.
        """
        pipeline = [
            {"$match": {"validated": False}},
            {"$project": {
                "day": {"$substr": ["$timestamp", 0, 10]} 
            }},
            {"$group": {
                "_id": "$dati medico.Anagrafica.Codice Fiscale",
                "validated_reports": {"$sum": 1}
            }},
            {"$sort": {"validated_reports": -1}}
        ]
        return list(self.db.reports_collection.aggregate(pipeline))

    # -------------------------- PAZIENTI --------------------------

    def patients_by_city(self):
        """
        Raggruppa i pazienti per città di residenza.
        Si assume che il campo sia 'residenza.comune'.
        """
        pipeline = [
            {"$group": {"_id": "$residenza.comune", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}}
        ]
        return list(self.db.reports_collection.aggregate(pipeline))

    def patients_sharing_medications(self):
        """
        Trova gruppi di pazienti che assumono gli stessi farmaci.
        Assunto: i farmaci sono in una lista nel campo 'farmaci'.
        """
        pipeline = [
            {"$unwind": "$farmaci"},
            {"$group": {
                "_id": "$farmaci",
                "patients": {"$addToSet": "$patient_id"},
                "count": {"$sum": 1}
            }},
            {"$match": {"count": {"$gt": 1}}}
        ]
        return list(self.db.reports_collection.aggregate(pipeline))

    def patient_profiles(self, patient_id):
        """
        Restituisce un profilo clinico aggregato del paziente.
        Include diagnosi, farmaci, numero di referti e medici coinvolti.
        """
        pipeline = [
            {"$match": {"patient_id": patient_id}},
            {"$group": {
                "_id": "$patient_id",
                "diagnosi": {"$addToSet": "$diagnosi"},
                "farmaci": {"$addToSet": "$farmaci"},
                "num_referti": {"$sum": 1},
                "medici_coinvolti": {
                    "$addToSet": "$dati medico.Anagrafica.Codice Fiscale"
                }
            }}
        ]
        result = list(self.db.reports_collection.aggregate(pipeline))
        return result[0] if result else {}

#LISTA DI MEDICI PER PAZIENTE
    
    def doctors_for_patient(self, patient_id):
        """
        Lista dei medici che hanno seguito il paziente.
        """
        pipeline = [
            {"$match": {"patient_id": patient_id}},
            {"$group": {
                "_id": "$dati medico.Anagrafica.Codice Fiscale"
            }}
        ]
        return list(self.db.reports_collection.aggregate(pipeline))

#PROTESI PER PAZIENTE
    def patient_prosthetics(self, patient_id): #TODO: RICONTROLLARE
        """
        Elenco delle protesi associate a un paziente.
        """
        pipeline = [
            {"$match": {"patient_id": patient_id}},
            {"$unwind": "$protesi"},
            {"$group": {"_id": "$patient_id", "protesi": {"$addToSet": "$protesi"}}}
        ]
        return list(self.db.reports_collection.aggregate(pipeline))

#ACCESSI AL PS GIORNALIERO
#ACCESSI AL PS GIORNALIRERO PER MEDICO
    def daily_er_accesses(self):
        """
        Numero giornaliero di accessi al pronto soccorso.
        """
        pipeline = [
            {"$project": {"day": {"$substr": ["$Chiamata.data", 0, 10]}}},
            {"$group": {"_id": "$day", "count": {"$sum": 1}}},
            {"$sort": {"_id": 1}}
        ]
        return list(self.db.reports_collection.aggregate(pipeline))

    def daily_er_accesses_by_doctor(self, doctor_cf):
        """
        Numero giornaliero di accessi PS seguiti da un medico specifico.
        """
        pipeline = [
            {"$match": {"Equipaggio.Medico": doctor_cf}},
            {"$project": {"day": {"$substr": ["$Chiamata.data", 0, 10]}}},
            {"$group": {"_id": "$day", "count": {"$sum": 1}}},
            {"$sort": {"_id": 1}}
        ]
        return list(self.db.reports_collection.aggregate(pipeline))

    def emergency_with_authority_involvement(self):
        """
        Lista degli interventi di emergenza con coinvolgimento di autorità.
        """
        pipeline = [
            {"$match": {"Attivazioni/Autorità presenti.descrizione": {"$ne": "N/A"}}}
        ]
        return list(self.db.reports_collection.aggregate(pipeline))

#REFERTI PAZIENTE
#REFERTI PER MEDICO CF
#PLOT DISTRIBUZIONE VISITE E ACCESSI PS DEL PAZIENTE
#DISTRIBUZIONE PAZIENTI DECEDUTI (ANNO) PER OSPEDALE
#DISTRIBUZIONE PAZIENTI DECEDUTI (ANNO) PER MEDICO
    def deceased_patients_by_year_and_hospital(self): #TODO:CORREGGERE
        """
        Conta dei pazienti deceduti per anno e ospedale.
        """
        pipeline = [
            {"$match": {"Decesso.Ora decesso": {"$ne": ""}}},
            {"$project": {
                "year": {"$substr": ["$Decesso.Ora decesso", 0, 4]},
                "hospital": "$Ospedale"
            }},
            {"$group": {"_id": {"year": "$year", "hospital": "$hospital"}, "count": {"$sum": 1}}},
            {"$sort": {"_id.year": 1, "count": -1}}
        ]
        return list(self.db.reports_collection.aggregate(pipeline))
    

    def deceased_patients_by_doctor(self): #TODO:CORREGGERE
        """
        Distribuzione dei pazienti deceduti per medico.
        """
        pipeline = [
            {"$match": {"Decesso.Ora decesso": {"$ne": ""}}},
            {"$group": {
                "_id": "$Equipaggio.Medico",
                "count": {"$sum": 1}
            }},
            {"$sort": {"count": -1}}
        ]
        return list(self.db.reports_collection.aggregate(pipeline))

#RELAZIONE TEMPO TRASPORTO IN OSPEDALE E GRAVITà DEI DANNI RIPORTATI (COMA, MORTE, ...)
    def coma_or_death_vs_transport_time(self):
        """
        Analizza se esiste correlazione tra tempo di trasporto e gravità esiti.
        """
        pipeline = [
            {"$match": {
                "$or": [
                    {"Decesso.Ora decesso": {"$ne": ""}},
                    {"Rilevazioni.Glasgow Coma Scale.Risposta verbale": "1"}
                ]
            }},
            {"$project": {
                "gravita": {
                    "$cond": [{"$ne": ["$Decesso.Ora decesso", ""]}, "Morte", "Coma"]
                },
                "tempo_trasporto": {
                    "$subtract": [
                        {"$toDate": "$Chiamata.H in PS"},
                        {"$toDate": "$Chiamata.H partenza posto"}
                    ]
                }
            }}
        ]
        return list(self.db.reports_collection.aggregate(pipeline))

#FARMACI PAZIENTI CON CANCRO
    def medications_for_cancer_patients(self):
        """
        Farmaci utilizzati dai pazienti con diagnosi oncologiche.
        """
        pipeline = [
            {"$match": {"diagnosi": {"$regex": "cancro|neoplasia|tumore", "$options": "i"}}},
            {"$unwind": "$farmaci"},
            {"$group": {"_id": "$farmaci", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}}
        ]
        return list(self.db.reports_collection.aggregate(pipeline))

