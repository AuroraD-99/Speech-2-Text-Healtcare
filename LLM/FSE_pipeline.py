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
        self.cpu_model_path_ = os.getenv("CPU_MODEL_PATH_")

        self.logger.debug(f"MODEL PATH {self.cpu_model_path}, MODEL TYPE {self.model_type}")
    

        #Configurazione del modello
        if not os.path.exists(self.model_path) or os.path.exists(self.model_path):
            #se il path del modello non esiste, il modello viene scaricato al path specificato
            self.model_download()

        #configurazione del modello in base alle risorse a disposizione
        self.model = self.model_configuration() 

        self.llm = LLMWrapper(model=self.model)

        #---------------------------------------------- Configurazione RAG --------------------------------------------------------------
        self.chroma_client = chroma_client 

        self.collection = self.chroma_client.get_or_create_collection(name="fse_rag_index", metadata={"hnsw:space": "cosine"})
        #--------------------------------------------------------------------------------------------------------------------------------

        self.JSON_path = os.getenv("JSON_PATH")
        if not os.path.exists(self.JSON_path):
            os.makedirs(self.JSON_path, exist_ok=True)

    #------------------------------------- FUNZIONI PER LA GESTIONE DEL MODELLO ----------------------------------------

    def model_download(self):
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


    def model_configuration(self):
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
                context = self.retrieve_context(embedding) 

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

            self.llm.check_json_format(full_output) #TODO: CONTROLLARE LA FUNZIONE

            #Salvataggio in formato JSON dell'output 
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")  # <-- underscore al posto di `:` e `-`
            out_file = os.path.join(self.JSON_path, f"{timestamp}.json")  # opzionale: aggiungi ".json"

            #Salvataggio anche in locale per sicurezza  
            self.llm.save_to_json(full_output, out_file)
            self.logger.debug(f"[{timestamp}] Output temporaneamente salvato in: {out_file}")                

            return [full_output, out_file]

        except Exception as e:
            self.logger.error(f"[{timestamp}] Errore durante la generazione FSE: {e}")
           
    #------------------------------------- PER LA GESTIONE DEL RETRIEVAL DAL RAG -------------------------------------------
    #DeepMount00/Mistral-RAG

    def cosine_similarity(a, b): #TODO: VEDERE SE CI SONO ANCHE ALTRE ALTERNATIVE E SCEGLIERE LA MIGLIORE
        a = np.array(a)
        b = np.array(b)
        return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-10)

    def retrieve_context(self, embedding, top_k=4): #TODO: CONTROLLARE FUNZIONAMENTO

        filter_metadata = {"type": self.function_mode}

        #l'embedding viene calcolato in Pipeline_manager con la funzione del RAGManager compute_embedding
        #e ha come formato:
        """chunk_data.append({
                "id": chunk_id,
                "text": chunk,  # Conservo il testo perchè lo uso per il retrieval semantico
                "embedding": embedding.tolist()
            })"""

        try: #fa il confronto per tutti i chunk: trova i chunk più simili -> prende l'id dell'elemento a cui appartiene -> carica il referto corrispondente
            results = self.collection.query( 
                query_embeddings=[embedding], #embedding del testo che voglio utilizzare per il retrieval
                n_results=top_k * 2, #numero di risultati che voglio trovare
                where=filter_metadata, #regola che restringe i risultati - voglio che ci sia un filtraggio in base al tipo di documento
                include=["metadatas", "documents"]
            )
        except Exception as e:
            self.logger.error(f"Errore nella query per il contesto: {e}")
            return None
        
        try:
            chunk_metadatas = results.get("metadatas", [[]])[0] #TODO: COSA PRENDE ESATTAMENTE?
            self.logger.info(f"Chunk metadata: {chunk_metadatas[0]}") #stampo un esempio di chunk metatada per capire cosa contiene
        except Exception as e:
            self.logger.error(f"Errore nel recupero metadati per i chunk: {e}")

        # Retrieval su documenti interi (ibrido)
        try:
            # Recupero tutti i metadati dei documenti memorizzati
            metadatas = self.collection.get(include=["metadatas"]).get("metadatas", [])
            self.logger.info(f"metadata: {metadatas[0]}") #stampo un esempio di metatada per capire cosa contiene

        except Exception as e:
            self.logger.error(f"Errore nel recupero metadati per embedding completi: {e}")
            metadatas = [] #perchè altrimenti fa cosi?

        complete_scores = [] #lista che conterrà i punteggi di similarità calcolati per le query
 
        """similar_ids = results.get("ids", [[]])[0]

        if not metadatas or not similar_ids:
            self.logger.info("Nessun contesto rilevante trovato.")
            return None
        """

        for metadata in metadatas:
            #verifico che i documenti siano del tipo che mi serve - DOVREBBE ESSERE INUTILE MA LO USO PER IL CHECK
            if not metadata or metadata.get("type") != self.function_mode: 
                self.logger.info(f"Metadati assenti o tipologia di documento errato")
                continue

            #Prendo le info (id ed embedding) della trascrizione completa
            complete_emb = metadata.get("complete_embedding")
            parent_id = metadata.get("parent_doc_id")
            #Verifico che siano presenti - è INUTILE MA LO INSERISCO PER DEBUG
            if not complete_emb or not parent_id:
                self.logger.info(f"Embedding della trascrizione completa o id della trascrizione mancanti")
                continue

            #Calcolo lo score di similarità tra l'embedding fornito in input alla funzione e quelli nel RAG
            score = self.cosine_similarity(embedding, complete_emb)
            complete_scores.append((score, metadata))

        # Ordino per similarità: per prendere gli embedding più simili a quello in input
        complete_scores.sort(key=lambda x: x[0], reverse=True)

        # Unione: deduplica e ordina
        # Per evitare duplicati se più chunk appartengono allo stesso documento
        combined_context = []
        seen_docs = set()

        # Prima i documenti interi più rilevanti
        for score, metadata in complete_scores:
            parent_id = metadata.get("parent_doc_id")
            if parent_id in seen_docs: #verifico che il documento intero non sia già stato preso
                continue

            referto = ( #prelievo del referto
                metadata.get("clinical_report") or
                metadata.get("scheda_ps") or
                None
            )
            if referto:
                combined_context.append((score, referto))
                seen_docs.add(parent_id)

            if len(combined_context) >= top_k:
                break

        # Se non bastano i documenti interi, aggiungi i più simili da chunk
        for metadata in chunk_metadatas:
            parent_id = metadata.get("parent_doc_id")
            if parent_id in seen_docs:
                continue

            referto = (
                metadata.get("clinical_report") or
                metadata.get("scheda_ps") or
                None
            )
            if referto:
                combined_context.append((None, referto))
                seen_docs.add(parent_id)

            if len(combined_context) >= top_k:
                break

        if not combined_context:
            self.logger.info("Nessun contesto rilevante trovato.")
            return None

        # Restituisco solo i testi
        return "\n\n".join([referto for _, referto in combined_context])


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
    report_text = (
        "Scheda di Ammissione al Pronto Soccorso Paziente Sig.ra Francesca Nanni, 62 anni, residente a Roma. "
        "Motivo dell’intervento e sintomi riferiti: La paziente ha accusato un intenso dolore al petto, irradiato al braccio sinistro "
        "e accompagnato da nausea, mentre era a casa. [...] ECG e della saturazione di ossigeno."
    )

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
