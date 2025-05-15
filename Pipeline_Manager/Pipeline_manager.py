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

from LLM.FSE_generator import LLMWrapper 
from LLM.RAG_manager import RAGManager
from LLM.FSE_pipeline import FSEManager
from Transcriptor. import TranscriptorManager #fare l'import per la trascrizione
from Database. import DBManager


class PipelineManager:
    def __init__(self, function_mode="Emergency", env_file="key.env"):
        #nella definizione della funzione vanno inserite le variabili per il RAG 

        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger("PipelineManager")

        #Gestione del file .env per le variabili di ambiente
        self.env_file = env_file
        load_dotenv(self.env_file)

        self.function_mode = function_mode

        #inizializzazione del database
        self.DM_manager = DBManager()

        #inizializzazione del RAG
        self.chroma_path = os.getenv("CHROMA_DB_PATH")
        self.chroma_client = Client() 

        self.RAGManager = RAGManager(self.chroma_path) #PER IL MOMENTO è FATTO QUI MA UNA VOLTA CHE SI HA IL PIPELINE MANAGER VA MESSO LI

        self.collection = self.chroma_client.get_or_create_collection("fse_rag_index")

        #inizializzazione del trascrittore
        self.transcriptor = TranscriptorManager()

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

        #acquisizione del testo trascritto
        self.logger.debug(f"Procedo all'acquisizione della nuova trascrizione...")
        report_text = self.transcriptor.

        #check sull'anagrafica del paziente nel DB
        #estraggo l'anagrafica del paziente per verificare che l'FSE a lui relativo esista
        self.logger.debug(f"Procedo all'estrazione dell'anagrafica del paziente ed alla verifica sulla presenza del suo FSE...")
        anagrafica = self.extract_anagrafica(report_text)

        if not self.DB_manager.check_existing_FSE(anagrafica):#aggiungo la scheda al FSE del paziente se già esiste, altrimenti genero un FSE e poi aggiungo la scheda
            self.logger.debug(f"[{timestamp}] Generazione FSE...")
            #richiamare la funzione del DB_Manager per la generazione di un nuovo FSE per il paziente
            self.DB_manager.create_new_FSE(anagrafica)


        #salvataggio della coppia audio + testo nel database 
        self.logger.debug(f"Procedo all'update della trascrizione e dell'audio nel DB...")
        self.DB_manager.

        #generazione del documento dalla LLM
        self.logger.debug(f"Procedo alla generazione del nuovo referto...")
        clinical_report, out_file = self.FSE_manager.FSE_manager(transcribed_test_path) #per il momento questa funzione prende il path del documento JSON in cui è salvata la trascrizione

        #modifica/validazione del referto
        self.logger.debug(f"Procedo alla validazione del referto prodotto...")
        validated_report_text = 

        #salvataggio del documento nel DB
        self.logger.debug(f"Aggiunta referto all'FSE del paziente...")
        success = self.DB_manager.update_document(document_id, new_data)
        if success:
            self.logger.info(f"FSE {document_id} modificato con successo in MongoDB")
        else:
            self.logger.warning(f"FSE {document_id} non trovato o non modificato")

        self.logger.debug(f"**** Rimozione del referto pazienre dalla cartella temporanea... ****")
        os.remove(out_file) #per la rimozione del file dalla cartella /tmp/ 

        #salvataggio su RAG 
        self.logger.debug(f"Procedo all'update del nuovo documento nel RAG...")
        report_text_RAG = self.anonimizza_referto(validated_report_text)
        #questo va fatto solo dopo che il medico ha approvato la revisione del referto
        rag_docs = self.RAGManager.rag_element_generator(timestamp, report_text, clinical_report)
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
            
        self.logger.debug(f"L'anagrafica del paziente è: {extracted}")
        return extracted


#------------------------------------- MAIN DI PROVA ----------------------------------------
# Entrypoint
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Gestione referti vocali e generazione FSE")

    args = parser.parse_args()

    manager = PipelineManager(
        transcribed_text_path = "C:/Users/HP/Desktop/BD/Speech-2-Voice-Healtcare/transcription_example.jsonl",
        function_mode="Follow_up"
    )

    manager.Pipeline_manager()
