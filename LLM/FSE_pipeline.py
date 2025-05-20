import os
import sys
import re
import time
import logging 
import tempfile   

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
from LLM.RAG_manager import RAGManager


class FSEManager:
    def __init__(self, chroma_client, function_mode="Emergency", env_file="key.env"):
        #nella definizione della funzione vanno inserite le variabili per il RAG 

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

        self.logger.debug(f"MODEL PATH {self.cpu_model_path}, MODEL TYPE {self.model_type}")

        #Configurazione del modello
        if not os.path.exists(self.model_path):
            #se il path del modello non esiste, il modello viene scaricato al path specificato
            self.model_download()

        #configurazione del modello in base alle risorse a disposizione
        self.model = self.model_configuration() 

        self.llm = LLMWrapper(model=self.model)

        #---------------------------------------------- Configurazione RAG --------------------------------------------------------------
        self.chroma_client = chroma_client 

        #self.embedding_model = os.getenv("EMBEDDING_MODEL")

        self.collection = self.chroma_client.get_or_create_collection(name="fse_rag_index", metadata={"hnsw:space": "cosine"})
        #self.embedder = SentenceTransformer(self.embedding_model)
        #--------------------------------------------------------------------------------------------------------------------------------

        self.JSON_path = os.getenv("JSON_PATH")

    #------------------------------------- FUNZIONI PER LA GESTIONE DEL MODELLO ----------------------------------------

    def model_download(self): #OK 
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
        
        else:
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
                        local_dir=self.cpu_model_path,
                        local_dir_use_symlinks=False 
                    )
                except Exception as e:
                    raise RuntimeError(f"Errore durante il download del modello GGUF: {e}")
            else:
                self.logger.info("Modello GGUF già presente.")

        self.logger.info("Download completato.")


    def model_configuration(self): #OK 
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

            model = cAutoModelForCausalLM.from_pretrained(
                model_path_or_repo_id=self.CPU_model_name,
                model_file=self.cpu_model_path, #"mistral_ita-7b-Q4_K_M.gguf",
                model_type="mistral",
                gpu_layers=0,
                context_length=4096,
                max_new_tokens=1000
            )

        self.logger.debug("Modello configurato correttamente.")
        return model

    #------------------------------------- FUNZIONI PER LA GESTIONE DEL FSE ----------------------------------------

    def FSE_manager(self, timestamp, record, embedding, anagrafica_medico, anagrafica_paziente):

        try:
            #Prelevo il testo trascritto
            self.logger.debug(f"[{timestamp}] Estrazione del record...")
            report_text = record.get("referto") if isinstance(record, dict) else record

            self.logger.debug(f"[{timestamp}] Elaborazione record...")

            if self.function_mode == "Emergency":
                #con il RAG prendo i documenti che hanno un contesto simile a quello che sto elaborando ora
                self.logger.debug(f"Modalità di funzionamento: Emergency...")
                self.logger.debug(f"Procedo con il recupero dal rag dei documenti simili...")
                context = self.retrieve_context(embedding, doc_type_filter=self.function_mode) #COME FUNZIONA ESATTAMENTE?
                #report_with_context = f"Contesto simile:\n{context}\n\nReferto:\n{report_text}"

                #genero la scheda di ammissione al PS
                self.logger.debug(f"Procedo alla generazione della scheda di ammissione al PS...")
                scheda_ps = self.llm.generate_scheda_from_report(report_text, context) 
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
                self.logger.debug(f"Procedo con il recupero dal rag dei documenti simili...")
                context = self.retrieve_context(embedding, doc_type_filter=self.function_mode)
                #report_with_context = f"Contesto simile:\n{context}\n\nReferto:\n{report_text}"

                self.logger.debug(f"Procedo alla generazione del referto clinico...")
                clinical_report = self.llm.generate_clinical_report(report_text, context) #
                self.llm.check_json_format(clinical_report)

                #Configurazione del formato del file JSON di output
                full_output = {
                        "timestamp": timestamp,
                        "type": self.function_mode,
                        "dati medico": anagrafica_medico,
                        "dati paziente": anagrafica_paziente,
                        "clinical_report": clinical_report
                }

            #self.llm.check_json_format(full_output)

            #Salvataggio in formato JSON dell'output 
            out_file = os.path.join(self.JSON_path, timestamp)
            self.llm.save_to_json(full_output, out_file)
            self.logger.debug(f"[{timestamp}] Output temporaneamente salvato in: {out_file}")                

            return [full_output, out_file]

        except Exception as e:
            self.logger.error(f"[{timestamp}] Errore durante la generazione FSE: {e}")
           
    #------------------------------------- PER LA GESTIONE DEL RETRIEVAL DAL RAG -------------------------------------------
    #DeepMount00/Mistral-RAG
   
    def retrieve_context(self, embedding, top_k=1, doc_type_filter=None):
        """
        Recupera i clinical_report più simili, in base all'embedding e (opzionalmente) al tipo.
        """
        filter_metadata = {"type": doc_type_filter} if doc_type_filter else {}

        try:
            results = self.collection.query(
                query_embeddings=[embedding],
                n_results=top_k,
                where=filter_metadata
            )
        except Exception as e:
            self.logger.error(f"Errore nella query per il contesto: {e}")
            return "Errore nel recupero del contesto."

        documents = results.get("documents", [[]])[0]
        similar_ids = results.get("ids", [[]])[0]

        if not documents or not similar_ids:
            return "Nessun contesto rilevante trovato."

        context_snippets = []
        for doc_id in similar_ids:
            try:
                document = self.reports_collection.find_one({"_id": ObjectId(doc_id)})
                if document and ("clinical_report" or "scheda_ps") in document:
                    context_snippets.append(document["clinical_report"])
            except Exception as e:
                self.logger.warning(f"Impossibile recuperare referto per ID {doc_id}: {e}")

        if not context_snippets:
            return "Nessun referto rilevante trovato."

        return "\n\n".join(context_snippets)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Gestione referti vocali e generazione FSE")

    args = parser.parse_args()

    report_text="Scheda di Ammissione al Pronto Soccorso Paziente Sig.ra Francesca Nanni, 62 anni, residente a Roma. Motivo dellintervento e sintomi riferiti La paziente ha accusato un intenso dolore al petto, irradiato al braccio sinistro e accompagnato da nausea, mentre era a casa. Ha riferito anche di aver avuto episodi simili nei giorni precedenti, ma di entità minore. Contesto clinico La paziente è una donna con una storia familiare di malattie cardiovascolari; la madre è deceduta per un infarto del miocardio alletà di 70 anni. La paziente è ipertesa e in trattamento con farmaci antipertensivi. Dinamica dellaccesso al PS La chiamata è stata effettuata alle ore 1115 da un familiare. Lintervento è avvenuto in Via della Libertà, 25, a Roma. Il trasporto è stato effettuato in ambulanza in codice giallo, con monitoraggio continuo dellECG e della saturazione di ossigeno. Trattamenti e interventi effettuati Allarrivo sul posto, la paziente era vigile, collaborante, con parametri vitali nella norma, ma con evidente distress respiratorio. È stata sottoposta a ossigenoterapia con maschera facciale a 6 litriminuto e somministrazione di acido acetilsalicilico da mg per via endovenosa. La paziente ha ricevuto anche un bolo di morfina da 2 mg per il controllo del dolore. Parametri vitali rilevati Pressione arteriosa 80 mmHg Frequenza cardiaca 92 bpm Frequenza respiratoria 22 attimin Temperatura 36,8C Saturazione di ossigeno 88 con aria ambiente, migliorata al 94 con ossigenoterapia Eventuale presenza di autorità Non presente. Annotazioni aggiuntive da parte del personale La paziente ha riferito di aver assunto gli ultimi pasti regolarmente e di non avere particolari allergie note. La famiglia ha fornito una cartella clinica incompleta con precedenti episodi di angina. Esami diagnostici Allelettrocardiogramma eseguito in ambulanza è emerso un sopraslivellamento del tratto ST in derivazioni inferiori, suggestivo per infarto miocardico inferiore. Trasporto al PS La paziente è stata trasportata al Pronto Soccorso dellOspedale Umberto I di Roma, dove è stata accolta nel percorso Code Rosse. Notazioni È stata avviata la procedura per il trattamento trombolitico e la paziente è stata sottoposta a ulteriori indagini diagnostice, tra cui ecocardiogramma e esami del sangue per marker cardiaci. Dettagli clinici aggiuntivi La paziente è stata mantenuta sotto stretto monitoraggio per tutta la durata del trasporto e in Pronto Soccorso, con controlli continui dei parametri vitali e dellECG. Stato alla fine del trasporto La paziente è arrivata al Pronto Soccorso in buone condizioni generali, ma con persistente dolore toracico. Elementi JSON strutturati json nome Francesca, cognome Nanni, eta 62, residenza Roma, motivo_intervento Dolore toracico acuto, sintomi_riferiti Dolore al petto irradiato al braccio sinistro, Nausea, storia_familiare Malattie cardiovascolari, farmaci_assunti Farmaci anti"
    embedding_model = os.getenv("EMBEDDING_MODEL")
    embedder = SentenceTransformer("distiluse-base-multilingual-cased-v2")

    embedding = embedder.encode(report_text)

    anagrafica_medico={"name": "Anna", "surname": "Quercia", "CF": "QRCNNA225H", "specializzazione": "Pneumologa" }
    anagrafica_paziente={"name": "Giovanni", "surname": "Foglia", "CF": "GVNNFOR347S"}

    chroma_client = Client() 
    function_mode="Emergency"
    env_file="key.env"

    FSE_manager = FSEManager(chroma_client, function_mode, env_file)

    clinical_report = FSE_manager.FSE_manager(time.strftime("%Y-%m-%d %H:%M:%S"), 
                                              report_text, 
                                              embedding, 
                                              anagrafica_medico, 
                                              anagrafica_paziente) 

        

