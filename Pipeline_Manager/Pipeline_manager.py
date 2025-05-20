import sys
import os
import re
import time
import logging    

import argparse
from dotenv import load_dotenv

import json
from json2pdf_converter import generate

from chromadb import Client
from sentence_transformers import SentenceTransformer

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from LLM.RAG_manager import RAGManager
from LLM.FSE_pipeline import FSEManager
from Transcriptor.transcription_pipeline import TranscriptionPipeline
from Database.mongodb import DB

class PipelineManager:
    def __init__(self, anagrafica_medico, function_mode="Emergency", env_file="key.env"):
        #e se il medico fa il log-out e un altro fa il login?

        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger("PipelineManager")

        #Gestione del file .env per le variabili di ambiente
        self.env_file = env_file
        load_dotenv(self.env_file)

        self.function_mode = function_mode
        #l'anagrafica del medico viene acquisita con il login
        self.anagrafica_medico = anagrafica_medico #è del tipo {"name": , "surname": , "CF": , "specializzazione": } - RICONTROLLARE

        #embedder per effettuare l'embedding della trascrizione
        self.embedding_model = os.getenv("EMBEDDING_MODEL")
        self.embedder = SentenceTransformer(self.embedding_model)

        #inizializzazione del database
        self.DB_manager = DB()

        #inizializzazione del RAG
        self.chroma_path = os.getenv("CHROMA_DB_PATH")
        self.chroma_client = Client() 

        self.RAGManager = RAGManager(self.chroma_path, self.anagrafica_medico["CF"])

        self.collection = self.chroma_client.get_or_create_collection("fse_rag_index")

        #inizializzazione del trascrittore
        self.transcriptor = TranscriptionPipeline()

        #inizializzazione del modello
        self.FSE_manager = FSEManager(self.chroma_client, self.function_mode, self.env_file)
        
        #--------------------------------------------------- Salvataggio in PDF ---------------------------------------------------------
        self.PDF_output = os.getenv("PDF_PATH")
        self.template_directory = os.getenv("TEMPLATE_DICTIONARY")
        self.template_name = os.getenv("TEMPLATE_NAME")
        self.output_html_path = os.getenv("OUTPUT_HTML_PATH")
        #---------------------------------------------------------------------------------------------------------------------------------

    #---------------------------------------------- FUNZIONI PER LA GESTIONE DELLA PIPELINE ----------------------------------------------

    def Pipeline_manager(self):
        #OSS. VANNO SALVAGUARDATI I FILE AUDIO E JSON => VEDERE COME SI PUò GESTIRE MEGLIO IL SALVATAGGIO E LO STORAGE

        #acquisizione del testo trascritto
        self.logger.debug(f"Procedo all'acquisizione della nuova trascrizione...")
        report_text = self.transcriptor.run()

        #print(report_text)

        #estrazione e check sulla validità dell'anagrafica del paziente nel DB
        self.logger.debug(f"Procedo all'estrazione dell'anagrafica del paziente ed alla verifica sulla presenza del suo FSE...")
        try:
            anagrafica_paziente = self.extract_anagrafica(report_text["transcription"])
        except Exception as e:
            self.logger.warning(f"****Anagrafica del paziente non specificata, dovrai inserirla necessariamente in fase di convalida del documento****")

        """if not self.DB_manager.check_existing_FSE(anagrafica):#aggiungo la scheda al FSE del paziente se già esiste, altrimenti genero un FSE e poi aggiungo la scheda
            self.logger.debug(f"[{timestamp}] Generazione FSE...")
            #richiamare la funzione del DB_Manager per la generazione di un nuovo FSE per il paziente
            self.DB_manager.create_new_FSE(anagrafica)"""
        
        #Generazione dell'embedding della trascrizione per il RAG
        embedding = self.embedder.encode(report_text["transcription"])
        
        embedding_doc = {
            "embedding": embedding.tolist() if hasattr(embedding, "tolist") else embedding
        }

        #salvataggio embedding nel DB
        try:
            embedding_id = self.DB_manager.insert_embedding(embedding_doc) #salvo l'embedding del testo e ottengo il suo id

            #salvataggio della coppia audio + testo nel database 
            self.logger.debug(f"Procedo all'update della trascrizione e dell'audio nel DB...")
            # Store transcription in the database
            self.DB_manager.insert_transcription( 
                audio_filename=report_text["filename"],
                transcription=report_text["transcription"],
                embedding_id=embedding_id,
                language=report_text["language"],
                audio_filepath=report_text["audio_filepath"] 
            )
        except Exception as e:
            self.logger.warning(f"Errore nel salvataggio: {e}")

        #generazione del documento dalla LLM
        self.logger.debug(f"Procedo alla generazione del nuovo referto...")
        clinical_report = self.FSE_manager.FSE_manager(report_text["timestamp"], report_text["transcription"], embedding, self.anagrafica_medico, anagrafica_paziente) 

        #vanno aggiunti i codici fiscali del medico e del paziente
        #check sul codice fiscale del paziente
        #check sulla struttura in base alle richieste del DB

        #modifica/validazione del referto
        self.logger.debug(f"Procedo alla validazione del referto prodotto...")
        #validated_report_text = self.FSE_manager.check_json_structure(clinical_report[0])

        #salvataggio del documento nel DB
        self.logger.debug(f"Aggiunta referto all'FSE del paziente...")
        document_id = self.DB_manager.insert_clinical_report(clinical_report[0])

        self.logger.debug(f"**** Rimozione del referto paziente dalla cartella temporanea... ****")
        os.remove(clinical_report[1]) 

        #salvataggio su RAG -> VA CAMBIATO PERCHè ATTUALMENTE PRENDE IL REFERTO PRODOTTO E LO INSERISCE SENZA VALIDAZIONE
        #DEVE PRENDERE IL REFERTO VALIDATO PER L'INSERIMENTO NEL RAG
        self.logger.debug(f"Procedo all'update del nuovo documento nel RAG...")
        report_text_RAG = self.anonimizza_referto(report_text["transcription"])

        #questo va fatto solo dopo che il medico ha approvato la revisione del referto
        rag_docs = self.RAGManager.rag_element_generator(report_text["timestamp"], report_text, clinical_report)
        self.RAGManager.add_to_RAG(rag_docs)
   

    #------------------------------------- FUNZIONI PER IL SALVATAGGIO DEL FSE ----------------------------------------

    def save_FSE_to_PDF(self): #RICONTROLLARE + VA INSERITO IN UN FILE A PARTE
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


    #------------------------------------- PER LA GESTIONE DEL CONTINUOUS RAG ----------------------------------------

    def anonimizza_referto(self, testo): #VA MIGLIORATO
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

    def extract_anagrafica(self, text): #VA MIGLIORATO
        # Estrattore di dati anagrafici da testo libero
        patterns = {
            "codice_fiscale": r"\b[A-Z]{6}[0-9]{2}[A-Z][0-9]{2}[A-Z][0-9]{3}[A-Z]\b",
            "nominativo": {
                "nome": r"\b[Nn]ome\b[:\s]*([A-Z][a-z]+)",
                "cognome": r"\b[Cc]ognome\b[:\s]*([A-Z][a-z]+)"
            },
            "sesso": r"\b[Ss]esso\b[:\s]*(Maschio|Femmina|M|F)\b",
            "data_nascita": r"\b(\d{2}[/-]\d{2}[/-]\d{4})\b",
            "luogo_nascita": {
                "città": r"[Nn]ato(?:\s*a)?[:\s]*([A-Z][a-z\s']+)",
                "provincia": r"[Pp]rov(?:incia)?[:\s]*\(?([A-Z]{2})\)?"
            },
            "residenza": {
                "città": r"[Rr]esidenza[:\s]*(?:in\s)?([A-Z][a-z\s']+)",
                "provincia": r"[Pp]rov(?:incia)?[:\s]*\(?([A-Z]{2})\)?",
                "indirizzo": r"[Ii]ndirizzo[:\s]*(Via\s[\w\s']+)"
            },
            "recapito_telefonico": r"\b(3\d{2}[-\s]?\d{6,7})\b",
            "dati_dichiarati_da": r"[Dd]ichiarat[oa]\s+da[:\s]*([A-Z][a-z]+\s[A-Z][a-z]+)"
        }

        extracted = {}

        for key, pattern in patterns.items():
            if isinstance(pattern, dict):
                extracted[key] = {}
                for subkey, subpattern in pattern.items():
                    if subpattern:
                        match = re.search(subpattern, text)
                        extracted[key][subkey] = match.group(1).strip() if match else "N/A"
                    else:
                        extracted[key][subkey] = "N/A"
            else:
                if pattern:
                    match = re.search(pattern, text)
                    extracted[key] = match.group(1).strip() if match else "N/A"
                else:
                    extracted[key] = "N/A"

        self.logger.debug(f"L'anagrafica del paziente è: {extracted}")
        return extracted


#------------------------------------- MAIN DI PROVA ----------------------------------------
# Entrypoint
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Gestione referti vocali e generazione FSE")

    args = parser.parse_args()

    anagrafica_medico={"name": "Anna", "surname": "Quercia", "CF": "QRCNNA225H", "specializzazione": "Pneumologa" }

    manager = PipelineManager(
        anagrafica_medico=anagrafica_medico,
        function_mode="Emergency"
    )

    manager.Pipeline_manager()


