import os
import sys
import re
import time
import numpy as np
from datetime import datetime
import logging 
import tempfile   
from bson import ObjectId

import argparse
from dotenv import load_dotenv

import json
from json2pdf_converter import generate

import subprocess
import torch

import random
import requests
import csv
from datetime import datetime
from collections import Counter
from groq import Groq

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from LLM.FSE_generator import LLMWrapper 
from NER.ner import NER


class FSEManager:
    def __init__(self, ner, function_mode="Emergency", env_file="key.env"):

        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger("FSEManager")

        #Gestione del file .env per le variabili di ambiente
        load_dotenv(env_file)

        self.function_mode = function_mode

        self.model = os.getenv("GROQ_MODEL_NAME")

        self.llm = LLMWrapper(model=self.model)

        #--------------------------------------------------------------------------------------------------------------------------------

        self.JSON_path = os.getenv("JSON_PATH")
        if not os.path.exists(self.JSON_path):
            os.makedirs(self.JSON_path, exist_ok=True)

        self.ner = ner

    #------------------------------------- FUNZIONI PER LA GESTIONE DEL MODELLO ----------------------------------------

    #------------------------------------- FUNZIONI PER LA GESTIONE DEL FSE ----------------------------------------

    def FSE_manager(self, timestamp, record, anagrafica_medico, anagrafica_paziente):

        try:
            #Prelevo il testo trascritto
            self.logger.debug(f"[{timestamp}] Estrazione del record...")
            report_text = record.get("referto") if isinstance(record, dict) else record
            entities = self.ner.extract_medical_entities(record)

            self.logger.info(f"Entities: {entities}")
            unique_entities = sorted(set(entities), key=str.lower)
            formatted_entities = ", ".join(unique_entities) if unique_entities else "nessuna"

            self.logger.info(f"Formatted Entities: {formatted_entities}")

            self.logger.info(f"[{timestamp}] Elaborazione record...")

            if self.function_mode == "Emergency":
                #con il RAG prendo i documenti che hanno un contesto simile a quello che sto elaborando ora
                self.logger.info(f"Modalità di funzionamento: Emergency...")

                #genero la scheda di ammissione al PS
                self.logger.info(f"Procedo alla generazione della scheda di ammissione al PS...")
                scheda_ps = self.llm.generate_scheda_from_report(report_text, formatted_entities) 
                self.llm.check_json_format(scheda_ps)

                #Configurazione del formato del file JSON di output
                full_output = {
                        "timestamp": timestamp,
                        "type": self.function_mode,
                        "dati medico": anagrafica_medico,
                        "dati paziente": anagrafica_paziente,
                        "scheda_ps": scheda_ps
                }

            else:
                self.logger.debug(f"Modalità di funzionamento: Follow-up o Visita...")
                
                self.logger.debug(f"Procedo alla generazione del referto clinico...")
                clinical_report = self.llm.generate_clinical_report(report_text, formatted_entities) #
                self.llm.check_json_format(clinical_report)

                #Configurazione del formato del file JSON di output
                full_output = {
                        "timestamp": timestamp,
                        "type": self.function_mode,
                        "dati medico": anagrafica_medico,
                        "dati paziente": anagrafica_paziente,
                        "clinical_report": clinical_report
                }

            self.llm.check_json_format(full_output) #TODO: CONTROLLARE LA FUNZIONE

            #Salvataggio in formato JSON dell'output 
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")  # <-- underscore al posto di `:` e `-`
            out_file = os.path.join(self.JSON_path, f"{timestamp}.json")  # opzionale: aggiungi ".json"

            #Salvataggio anche in locale per sicurezza  
            self.llm.save_to_json(full_output, out_file)
            self.logger.info(f"[{timestamp}] Output temporaneamente salvato in: {out_file}")                

            return [full_output, out_file]

        except Exception as e:
            self.logger.error(f"[{timestamp}] Errore durante la generazione FSE: {e}")
           
    #------------------------------------- PER LA GESTIONE DEL RETRIEVAL DAL RAG -------------------------------------------
    #DeepMount00/Mistral-RAG

def main():
    # Impostazioni iniziali
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("FSEManagerMain")

    # Caricamento variabili ambiente
    env_file = "key.env"
    load_dotenv(env_file)

    # Modalità di funzionamento (Emergency, Follow-up, ecc.)
    function_mode = "Emergency"

    # Report di test
    report_text = "Motivo dellintervento e sintomi riferiti La paziente ha accusato un intenso dolore al petto, irradiato al braccio sinistro e accompagnato da nausea, mentre era a casa. Ha riferito anche di aver avuto episodi simili nei giorni precedenti, ma di entità minore. Contesto clinico La paziente è una donna con una storia familiare di malattie cardiovascolari. La paziente è ipertesa e in trattamento con farmaci antipertensivi. Dinamica dellaccesso al PS La chiamata è stata effettuata alle ore 1115 da un familiare. Lintervento è avvenuto in Via della Libertà, 25, a Roma. Il trasporto è stato effettuato in ambulanza in codice giallo, con monitoraggio continuo dellECG e della saturazione di ossigeno. Trattamenti e interventi effettuati Allarrivo sul posto, la paziente era vigile, collaborante, con parametri vitali nella norma, ma con evidente distress respiratorio. È stata sottoposta a ossigenoterapia con maschera facciale a 6 litriminuto e somministrazione di acido acetilsalicilico da mg per via endovenosa. La paziente ha ricevuto anche un bolo di morfina da 2 mg per il controllo del dolore. Parametri vitali rilevati Pressione arteriosa 80 mmHg Frequenza cardiaca 92 bpm Frequenza respiratoria 22 attimin Temperatura 36,8C Saturazione di ossigeno 88 con aria ambiente, migliorata al 94 con ossigenoterapia Eventuale presenza di autorità Non presente. Annotazioni aggiuntive da parte del personale La paziente ha riferito di aver assunto gli ultimi pasti regolarmente e di non avere particolari allergie note. La famiglia ha fornito una cartella clinica incompleta con precedenti episodi di angina. Esami diagnostici Allelettrocardiogramma eseguito in ambulanza è emerso un sopraslivellamento del tratto ST in derivazioni inferiori, suggestivo per infarto miocardico inferiore. Trasporto al PS La paziente è stata trasportata al Pronto Soccorso dellOspedale Umberto I di Roma, dove è stata accolta nel percorso Code Rosse. Notazioni È stata avviata la procedura per il trattamento trombolitico e la paziente è stata sottoposta a ulteriori indagini diagnostice, tra cui ecocardiogramma e esami del sangue per marker cardiaci. Dettagli clinici aggiuntivi La paziente è stata mantenuta sotto stretto monitoraggio per tutta la durata del trasporto e in Pronto Soccorso, con controlli continui dei parametri vitali e dellECG. Stato alla fine del trasporto La paziente è arrivata al Pronto Soccorso in buone condizioni generali, ma con persistente dolore toracico. Elementi JSON strutturati json nome Francesca, cognome Nanni, eta 62, residenza Roma, motivo_intervento Dolore toracico acuto, sintomi_riferiti Dolore al petto irradiato al braccio sinistro, Nausea, storia_familiare Malattie cardiovascolari."

    # Anagrafiche fittizie
    anagrafica_medico = {
        "name": "Anna",
        "surname": "Quercia",
        "CF": "QRCNNA225H",
        "specializzazione": "Pneumologa"
    }

    anagrafica_paziente = {
        "name": "Francesca",
        "surname": "Nanni",
        "CF": "FRNNNI62R"
    }

if __name__ == "__main__":
    main()
