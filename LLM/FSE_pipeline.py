import os
import re
import time
import logging    

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

from FSE_generator import LLMWrapper  # Assicurati che sia correttamente implementato
from RAG_manager import RAGManager


class FSEManager:
    def __init__(self, transcribed_text_path, function_mode="Emergency", env_file="key.env"):

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
            #se il path del modello non è stato specificato o non esiste, il modello viene scaricato al path specificato
            self.model_download()

        self.model = self.model_configuration() #configurazione del modello in base alle risorse a disposizione

        self.llm = LLMWrapper(model=self.model)

        #Configurazione RAG
        self.chroma_path = os.getenv("CHROMA_DB_PATH")
        self.chroma_client = Client() #vedere se usare PersistentClient o qualcos'altro
        self.collection = self.chroma_client.get_or_create_collection("fse_rag_index")
        self.embedder = SentenceTransformer("distiluse-base-multilingual-cased-v2")

        self.RAGManager = RAGManager(self.chroma_path)

        #Salvataggio - PER IL MOMENTO IL SALVATAGGIO è GESTITO IN CARTELLE, DOPO DEVE ESSERE GESTITO IN MONGO DB E IN NEO4J
        self.JSON_output =  os.getenv("JSON_OUTPUT_PATH")
        self.PDF_output = os.getenv("PDF_PATH")
        self.template_directory = os.getenv("TEMPLATE_DICTIONARY")
        self.template_name = os.getenv("TEMPLATE_NAME")
        self.output_html_path = os.getenv("OUTPUT_HTML_PATH")

        #controllo se la cartella esiste, altrimenti la creo
        os.makedirs(self.JSON_output, exist_ok=True)

        #Caricamento testo trascritto (per il momento lo considero come salvato in JSON) - DA CAMBIARE
        self.transcribed_text_path = transcribed_text_path

        with open(self.transcribed_text_path, "r", encoding="utf-8") as f:
            self.transcribed_data = [json.loads(line) for line in f]


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
                        local_dir_use_symlinks=False #è deprecato -> da ricontrollare
                    )
                except Exception as e:
                    raise RuntimeError(f"Errore durante il download del modello GGUF: {e}")
            else:
                self.logger.info("Modello GGUF già presente.")

        self.logger.info("Download completato.")


    def model_configuration(self):
        self.logger.info(f"Inizializzazione modello da: {self.model_path}")

        if torch.cuda.is_available():
            self.logger.info("CUDA disponibile. Configurazione con quantizzazione `bitsandbytes`.")

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
            self.logger.info("CUDA non disponibile. Caricamento modello quantizzato per CPU con `ctransformers`.")

            model = cAutoModelForCausalLM.from_pretrained(
                model_path_or_repo_id=self.cpu_model_path,
                model_file="mistral_ita-7b-Q4_K_M.gguf",
                model_type="mistral",
                gpu_layers=0,
                context_length=4096,
                max_new_tokens=1000
            )

        self.logger.info("Modello configurato correttamente.")
        return model

    #------------------------------------- FUNZIONI PER LA GESTIONE DEL FSE ----------------------------------------

    def check_existing_FSE(self, anagrafica): #funzione che controlla se l'FSE per una certa persona già esiste
        return True

    def FSE_manager(self):
        #bisogna fare una modifica: l'FSE va visto come una collezione di referti relativi allo stesso paziente
        #quindi al posto di generare ogni volta un nuovo FSE va generato un nuovo referto ad aggiungere all'FSE corrente
        #e vanno aggiornati se necessario determinati campi del FSE

        for timestamp, record in enumerate(self.transcribed_data):
            try:
                #Prelevo il testo trascritto
                report_text = record.get("referto") if isinstance(record, dict) else record

                self.logger.info(f"[{timestamp}] Elaborazione record...")

                #estraggo l'anagrafica del paziente per verificare che l'FSE a lui relativo esista
                anagrafica = self.extract_anagrafica(report_text)
                #aggiungo la scheda al FSE del paziente se già esiste, altrimenti genero un FSE e poi aggiungo la scheda
                if not self.check_existing_FSE(anagrafica):
                    self.logger.info(f"[{timestamp}] Generazione FSE...")

                #Conviene utilizzare un NER?

                if self.function_mode == "Emergency":
                    #con il RAG prendo i documenti che hanno un contesto simile a quello che sto elaborando ora
                    self.logger.info(f"Modalità di funzionamento: Emergency...")
                    self.logger.info(f"Procedo con il recupero dal rag dei documenti simili...")
                    context = self.retrieve_context(report_text)
                    report_with_context = f"Contesto simile:\n{context}\n\nReferto:\n{report_text}"

                    #genero la scheda di ammissione al PS
                    self.logger.info(f"Procedo alla generazione della scheda di ammissione al PS...")
                    scheda_ps = self.llm.generate_scheda_from_report(report_text) 

                    #Configurazione del formato del file JSON di output
                    full_output = {
                        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "type": self.function_mode,
                        "scheda_ps": scheda_ps
                    }

                    self.logger.info(f"Procedo all'update del nuovo documento nel RAG...")
                    report_text_RAG = self.anonimizza_referto(report_text)
                    #questo va fatto solo dopo che il medico ha approvato la revisione del referto
                    rag_docs = self.RAGManager.rag_element_generator(timestamp, report_text, scheda_ps)

                else:
                    self.logger.info(f"Modalità di funzionamento: Follow-up o Visita...")
                    self.logger.info(f"Procedo con il recupero dal rag dei documenti simili...")
                    context = self.retrieve_context(report_text)
                    report_with_context = f"Contesto simile:\n{context}\n\nReferto:\n{report_text}"

                    self.logger.info(f"Procedo alla generazione del referto clinico...")
                    clinical_report = self.llm.generate_clinical_report(report_text, report_with_context) 

                    #Configurazione del formato del file JSON di output
                    full_output = {
                        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "type": self.function_mode,
                        "clinical_report": clinical_report
                    }

                    self.logger.info(f"Procedo all'update del nuovo documento nel RAG...")
                    report_text_RAG = self.anonimizza_referto(report_text)
                    #questo va fatto solo dopo che il medico ha approvato la revisione del referto
                    rag_docs = self.RAGManager.rag_element_generator(timestamp, report_text, clinical_report)

                #Salvataggio in formato JSON dell'output - DEVE POI ESSERE FATTO L'UPDATE SU MONGO DB
                out_file = os.path.join(self.JSON_output, f"FSE_{timestamp}.json")
                self.llm.check_json_format(full_output) #validatore del JSON
                self.llm.save_to_json(full_output, out_file)
                self.logger.info(f"[{timestamp}] Referto/scheda di ammissione al PS salvato in: {out_file}")                

                #aggiungo la scheda all'FSE
                self.logger.info(f"Aggiunta referto all'FSE...")
                #DEVI RICHIAMARE UNA FUNZIONE PER EFFETTUARE L'UPDATE DEL REFERTO SUL FSE


                #aggiungo i nuovi contenuti al RAG
                self.RAGManager.add_to_RAG(rag_docs)

            except Exception as e:
                self.logger.error(f"[{timestamp}] Errore durante la generazione FSE: {e}")
           

    def modify_clinical_report(self, index, new_data): 
        #deve dare la possibilità al medico di cambiare il contenuto del referto mediante interazione con la dashboard
        path = os.path.join(self.JSON_output, f"FSE_{index}.json")

        #Verifico che il file esista - DEVE ESSERE MODIFICATO PER CONTROLLARE IN MONGO DB
        if not os.path.exists(path):
            raise FileNotFoundError(f"FSE {index} non trovato")

        with open(path, "r", encoding="utf-8") as f:
            #DEVE ESSERE MODIFICATO PER GESTIRE LA MODIFICA IN BASE ALL'INTERAZIONE CON L'INTERFACCIA
            # - FARE IN SEGUITO QUANDO SI HANNO TUTTI I PEZZI
            data = json.load(f)

        #Update delle modifiche
        data.update(new_data)

        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        #inserted_id = self.db_controller.insert_document(full_output)
        #self.logger.info(f"[{timestamp}] FSE salvato in MongoDB con ID: {inserted_id}")

        self.logger.info(f"FSE {index} modificato con successo")

    #------------------------------------- FUNZIONI PER IL SALVATAGGIO DEL FSE ----------------------------------------

    def save_FSE_to_PDF(self): #RICONTROLLARE
        self.logger.info("Esportazione FSE in PDF in corso ...")
        for filename in os.listdir(self.JSON_output):
            if filename.endswith(".json"):
                path = os.path.join(self.JSON_output, filename)
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                output_pdf = os.path.join(self.PDF_output, filename.replace(".json", ".pdf"))

                generate(
                    json_file_path=path,
                    template_directory_path=self.template_directory,
                    output_html_path=self.output_html_path,
                    output_pdf_path=output_pdf,
                    options={
                        'encoding': 'UTF-8',
                        'margin-top': '0px',
                        'margin-right': '30px',
                        'margin-bottom': '30px',
                        'margin-left': '30px',
                        'footer-right': "Page [page] of [topage]",
                        'footer-font-size': "9",
                        'orientation': 'Portrait',
                        'page-size': 'A4',
                    },
                    template_name=self.template_name,
                    data_variables={"data": data}
                )

        #success = self.db_controller.update_document(document_id, new_data)
        #if success:
        #    self.logger.info(f"FSE {document_id} modificato con successo in MongoDB")
        #else:
        #    self.logger.warning(f"FSE {document_id} non trovato o non modificato")

    def save_FSE_to_DB(self):
        self.logger.info("Salvataggio su DB in corso ...")

    #------------------------------------- PER LA GESTIONE DEL CONTINUOUS RAG ----------------------------------------

    def retrieve_context(self, query_text, top_k=3): 
        #funzione per l'individuazione di documenti con contesto simile per la generazione del referto
        embedding = self.embedder.encode(query_text)
        results = self.collection.query(query_embeddings=[embedding], n_results=top_k)
        if not results["documents"] or not results["documents"][0]:
            return "Nessun contesto rilevante trovato."
        else:
            return "\n\n".join([doc for doc in results["documents"][0]])

    def anonimizza_referto(self, testo):
        #funzione per mascherare nomi propri, CF, date, numeri identificativi, indirizzi ecc.
        #è necessaria per il continuous RAG in modo che i dati sensibili dei pazienti non vengano considerati
        patterns = {
            r"\b[Cc]odice\s?[Ff]iscale\b.*?:?\s?[A-Z0-9]{16}": "[CODICE_FISCALE]",
            r"\b[Nn]ome\b.*?:?\s?[A-Z][a-z]+": "[NOME]",
            r"\b[Cc]ognome\b.*?:?\s?[A-Z][a-z]+": "[COGNOME]",
            r"\b\d{2}/\d{2}/\d{4}\b": "[DATA]",
            r"\b\d{1,2}-\d{1,2}-\d{4}\b": "[DATA]",
            r"\b\d{1,2}:\d{2}\b": "[ORA]",
            r"\b[\d]{11}\b": "[NUM_TESSERA]",
            r"\bVia\s[\w\s]+": "[INDIRIZZO]",
        }
        for pattern, replacement in patterns.items():
            testo = re.sub(pattern, replacement, testo)
        return testo
    
    def extract_anagrafica(self, text):
        # Ritorna dizionario con i dati sensibili trovati e mascherati
        patterns = {
            "codice_fiscale": r"[A-Z0-9]{16}",
            "nome": r"\b[Nn]ome\b.*?:?\s?([A-Z][a-z]+)",
            "cognome": r"\b[Cc]ognome\b.*?:?\s?([A-Z][a-z]+)",
            "data_nascita": r"\b\d{2}/\d{2}/\d{4}\b|\b\d{1,2}-\d{1,2}-\d{4}\b",
            "indirizzo": r"\bVia\s[\w\s]+"
        }
        extracted = {}
        for key, pattern in patterns.items():
            match = re.search(pattern, text)
            if match:
                extracted[key] = match.group(0)
        return extracted


#------------------------------------- MAIN DI PROVA ----------------------------------------
# Entrypoint
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Gestione referti vocali e generazione FSE")

    args = parser.parse_args()

    manager = FSEManager(
        transcribed_text_path = "C:/Users/HP/Desktop/BD/Speech-2-Voice-Healtcare/transcription_example.jsonl",
        function_mode="Follow_up"
    )

    manager.FSE_manager()
