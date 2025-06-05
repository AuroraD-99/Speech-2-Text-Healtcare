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
from huggingface_hub import hf_hub_download

from peft import LoraConfig, PeftModel, prepare_model_for_kbit_training
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig, MistralForCausalLM
from ctransformers import AutoModelForCausalLM as cAutoModelForCausalLM


from chromadb import Client
from sentence_transformers import SentenceTransformer

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

        #Modello 
        self.model_type = os.getenv("MODEL_TYPE_M")
        self.model_name = os.getenv("MODEL_NAME_M")
        self.CPU_model_name = os.getenv("CPU_MODEL_NAME_M")
        self.logger.info(f"Model name: {self.model_name}")

        self.model_path = os.getenv("MODEL_PATH_M")
        self.cpu_model_path = os.getenv("CPU_MODEL_PATH_M")
        self.cpu_model_path_ = os.getenv("CPU_MODEL_PATH_")

        self.logger.debug(f"MODEL PATH {self.cpu_model_path}, MODEL TYPE {self.model_type}")
    

        #Configurazione del modello
        if not os.path.exists(self.model_path) or os.path.exists(self.model_path):
            #se il path del modello non esiste, il modello viene scaricato al path specificato
            self._model_download()

        #configurazione del modello in base alle risorse a disposizione
        self.model = self._model_configuration() 

        self.llm = LLMWrapper(model=self.model)

        #--------------------------------------------------------------------------------------------------------------------------------

        self.JSON_path = os.getenv("JSON_PATH")
        if not os.path.exists(self.JSON_path):
            os.makedirs(self.JSON_path, exist_ok=True)

        self.ner = ner

    #------------------------------------- FUNZIONI PER LA GESTIONE DEL MODELLO ----------------------------------------

    def _model_download(self):
        self.logger.info(f"Controllo modello in: {self.model_path}")

        if torch.cuda.is_available():
            # GPU: Scarica con huggingface-cli da riga di comando
            os.makedirs(self.model_path, exist_ok=True)

            required_files = ["config.json", "model.safetensors", "tokenizer.json"]
            missing_files = [f for f in required_files if not os.path.exists(os.path.join(self.model_path, f))]

            if missing_files:
                self.logger.info(f"File mancanti: {missing_files}. Avvio download via huggingface-cli...")

                try:
                    subprocess.run([
                        "huggingface-cli", "download", 
                        "DeepMount00/Mistral-Ita-7b-Instruct-v0.1", 
                        "--cache-dir", self.model_path, 
                        "--include", ",".join(required_files)
                    ], check=True)
                except subprocess.CalledProcessError as e:
                    raise RuntimeError(f"Errore nel download del modello GPU: {e}")
                
                self.logger.info(f"Modello scaricato in {self.model_path}")
            else:
                self.logger.info("Tutti i file del modello GPU sono già presenti.")
        
        else: #RIVEDER I PATH DEI MODELLI
            # CPU (quantizzato, GGUF)
            self.logger.info("Ambiente CPU rilevato. Verifica modello GGUF...")
            gguf_repo = "DeepMount00/Mistral-Ita-7b-GGUF"
            gguf_filename = "mistral_ita-7b-Q4_K_M.gguf" 

            os.makedirs(self.cpu_model_path, exist_ok=True)
            gguf_path = os.path.join(self.cpu_model_path, gguf_filename)

            if not os.path.exists(gguf_path):
                try:
                    self.logger.info(f"Scarico modello GGUF da {gguf_repo}...")
                    hf_hub_download(
                        repo_id=gguf_repo,
                        filename=gguf_filename,
                        local_dir=self.cpu_model_path
                    )

                    self.logger.info(f"Modello scaricato in {self.cpu_model_path}")

                except Exception as e:
                    raise RuntimeError(f"Errore durante il download del modello GGUF: {e}")
            else:
                self.logger.info("Modello GGUF già presente.")

        self.logger.info("Download completato.")


    def _model_configuration(self):
        self.logger.debug(f"Inizializzazione modello da: {self.model_path}")

        if torch.cuda.is_available():
            self.logger.debug("CUDA disponibile. Configurazione con quantizzazione `bitsandbytes`.")

            compute_dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16

            bnb_config = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_compute_dtype=compute_dtype,
                bnb_4bit_use_double_quant=True,
            )

            model = MistralForCausalLM.from_pretrained(
                self.model_path,
                quantization_config=bnb_config,
                device_map="auto"
            )
        else:
            self.logger.debug("CUDA non disponibile. Caricamento modello quantizzato per CPU con `ctransformers`.")

            model_file = os.path.join(self.cpu_model_path, "mistral_ita-7b-Q4_K_M.gguf")

            model = cAutoModelForCausalLM.from_pretrained(
                model_path_or_repo_id=model_file, #self.CPU_model_name,
                #model_file=model_file, #"mistral_ita-7b-Q4_K_M.gguf",
                model_type="mistral",
                gpu_layers=0,
                context_length=4096,
                max_new_tokens=1000
            )

        self.logger.debug("Modello configurato correttamente.")
        return model

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

    # Inizializzazione embedder
    logger.info("Inizializzo modello di embedding...")
    embedder = SentenceTransformer("distiluse-base-multilingual-cased-v2")
    embedding = embedder.encode(report_text)

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

    # Inizializzazione ChromaDB client
    logger.info("Creo client ChromaDB...")
    chroma_client = Client()

    # Inizializzazione del manager
    logger.info("Inizializzo FSEManager...")
    fse_manager = FSEManager(chroma_client, function_mode, env_file)

    # Generazione report clinico
    logger.info("Avvio generazione del documento FSE...")
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    output, file_path = fse_manager.FSE_manager(
        timestamp,
        report_text,
        embedding,
        anagrafica_medico,
        anagrafica_paziente
    )

    # Output finale
    logger.info("Output JSON generato:")
    print(output)

    logger.info(f"Salvato temporaneamente in: {file_path}")

if __name__ == "__main__":
    main()
