import os
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

from FSE_generator import LLMWrapper 
from RAG_manager import RAGManager


class FSEManager:
    def __init__(self, chroma_client, function_mode="Emergency", env_file="key.env"):
        #nella definizione della funzione vanno inserite le variabili per il RAG 

        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger("FSEManager")

        #Gestione del file .env per le variabili di ambiente
        load_dotenv(env_file)

        self.function_mode = function_mode

        #Modello 
        self.model_name = os.getenv("MODEL_NAME_M")
        self.logger.info(f"Model name: {self.model_name}")

        self.model_path = os.getenv("MODEL_PATH_M")
        self.cpu_model_path = os.getenv("CPU_MODEL_PATH_M")

        #Configurazione del modello
        if not os.path.exists(self.model_path):
            #se il path del modello non esiste, il modello viene scaricato al path specificato
            self.model_download()

        #configurazione del modello in base alle risorse a disposizione
        self.model = self.model_configuration() 

        self.llm = LLMWrapper(model=self.model)

        #---------------------------------------------- Configurazione RAG --------------------------------------------------------------
        self.chroma_client = chroma_client 

        self.collection = self.chroma_client.get_or_create_collection("fse_rag_index")
        self.embedder = SentenceTransformer("distiluse-base-multilingual-cased-v2")
        #--------------------------------------------------------------------------------------------------------------------------------

    #------------------------------------- FUNZIONI PER LA GESTIONE DEL MODELLO ----------------------------------------

    def model_download(self): #OK - DEVONO ESSERE SOLO ASTRATTI I DATI RELATIVI AL MODELLO NEL KEY.ENV
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
            gguf_filename = "mistral_ita-7b-Q4_K_M.gguf" #serve una quantizzazione diversa? FAI UN TEST CON REFERTO IN INGLESE

            os.makedirs(self.cpu_model_path, exist_ok=True)
            gguf_path = os.path.join(self.cpu_model_path, gguf_filename)

            if not os.path.exists(gguf_path):
                try:
                    self.logger.info(f"Scarico modello GGUF da {gguf_repo}...")
                    hf_hub_download(
                        repo_id=gguf_repo,
                        filename=gguf_filename,
                        local_dir=self.cpu_model_path,
                        local_dir_use_symlinks=False #è deprecato -> da ricontrollare
                    )
                except Exception as e:
                    raise RuntimeError(f"Errore durante il download del modello GGUF: {e}")
            else:
                self.logger.info("Modello GGUF già presente.")

        self.logger.info("Download completato.")


    def model_configuration(self): #OK - DEVONO ESSERE SOLO ASTRATTI I DATI RELATIVI AL MODELLO NEL KEY.ENV
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
                model_path_or_repo_id=self.cpu_model_path,
                model_file="mistral_ita-7b-Q4_K_M.gguf",
                model_type="mistral",
                gpu_layers=0,
                context_length=4096,
                max_new_tokens=1000
            )

        self.logger.debug("Modello configurato correttamente.")
        return model

    #------------------------------------- FUNZIONI PER LA GESTIONE DEL FSE ----------------------------------------

    def FSE_manager(self, transcribed_text_path):

        #Caricamento testo trascritto (per il momento lo considero come salvato in JSON) - DA CAMBIARE
        self.transcribed_text_path = transcribed_text_path

        with open(self.transcribed_text_path, "r", encoding="utf-8") as f:
            self.transcribed_data = [json.loads(line) for line in f]

        for timestamp, record in enumerate(self.transcribed_data):
            try:
                #Prelevo il testo trascritto
                report_text = record.get("referto") if isinstance(record, dict) else record

                self.logger.debug(f"[{timestamp}] Elaborazione record...")

                #Conviene utilizzare un NER?

                if self.function_mode == "Emergency":
                    #con il RAG prendo i documenti che hanno un contesto simile a quello che sto elaborando ora
                    self.logger.debug(f"Modalità di funzionamento: Emergency...")
                    self.logger.debug(f"Procedo con il recupero dal rag dei documenti simili...")
                    context = self.retrieve_context(report_text)
                    report_with_context = f"Contesto simile:\n{context}\n\nReferto:\n{report_text}"

                    #genero la scheda di ammissione al PS
                    self.logger.debug(f"Procedo alla generazione della scheda di ammissione al PS...")
                    scheda_ps = self.llm.generate_scheda_from_report(report_text) 
                    self.llm.check_json_format(scheda_ps)

                    #Configurazione del formato del file JSON di output
                    full_output = {
                        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "type": self.function_mode,
                        "scheda_ps": scheda_ps
                    }

                else:
                    self.logger.debug(f"Modalità di funzionamento: Follow-up o Visita...")
                    self.logger.debug(f"Procedo con il recupero dal rag dei documenti simili...")
                    context = self.retrieve_context(report_text)
                    report_with_context = f"Contesto simile:\n{context}\n\nReferto:\n{report_text}"

                    self.logger.debug(f"Procedo alla generazione del referto clinico...")
                    clinical_report = self.llm.generate_clinical_report(report_text, report_with_context) 
                    self.llm.check_json_format(clinical_report)

                    #Configurazione del formato del file JSON di output
                    full_output = {
                        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "type": self.function_mode,
                        "clinical_report": clinical_report
                    }

                #self.llm.check_json_format(full_output)

                #Salvataggio in formato JSON dell'output - realizzato su una cartella tmp e poi usa un meccanismo di garbage collection
                with tempfile.NamedTemporaryFile(mode="w", suffix=".json", prefix="fse_", dir="/tmp", delete=False, encoding="utf-8") as tmp_file:

                    self.llm.save_to_json(full_output, tmp_file)
                    out_file = tmp_file.name
                    self.logger.debug(f"[{timestamp}] Output temporaneamente salvato in: {out_file}")                

                return full_output, out_file

            except Exception as e:
                self.logger.error(f"[{timestamp}] Errore durante la generazione FSE: {e}")
           
    #------------------------------------- PER LA GESTIONE DEL RETRIEVAL DAL RAG -------------------------------------------

    def retrieve_context(self, query_text, top_k=3): 
        #funzione per l'individuazione di documenti con contesto simile per la generazione del referto
        embedding = self.embedder.encode(query_text)
        results = self.collection.query(query_embeddings=[embedding], n_results=top_k)
        if not results["documents"] or not results["documents"][0]:
            return "Nessun contesto rilevante trovato."
        else:
            return "\n\n".join([doc for doc in results["documents"][0]])

#------------------------------------- MAIN DI PROVA ----------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Gestione referti vocali e generazione FSE")

    args = parser.parse_args()

    manager = FSEManager(
        transcribed_text_path = "C:/Users/HP/Desktop/BD/Speech-2-Voice-Healtcare/transcription_example.jsonl",
        function_mode="Follow_up"
    )

    manager.FSE_manager()
