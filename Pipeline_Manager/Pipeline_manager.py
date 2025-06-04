import sys
import os
import re
import time
from datetime import datetime, timedelta
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
from Pipeline_Manager.Anagrafica import Anagrafica
from ner import NER

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
        #controllo sull'anagrafica del medico
        self.logger.info(f"Anagrafica medico: {self.anagrafica_medico}")

        self.update_time = datetime.now() + timedelta(hours=2)

        #embedder per effettuare l'embedding della trascrizione
        self.embedding_model = os.getenv("EMBEDDING_MODEL")
        self.embedder = SentenceTransformer(self.embedding_model)

        #NER per l'estrazione delle entities - usate sia per il retrieval che per migliorare la generazione
        self.ner = NER()

        #inizializzazione del database
        self.DB_manager = DB()

        #inizializzazione del RAG
        self.chroma_path = os.getenv("CHROMA_DB_PATH")
        self.chroma_client = Client() 

        self.RAGManager = RAGManager(self.chroma_path, self.ner, self.DB_manager, self.function_mode, self.anagrafica_medico["Anagrafica"]["Codice Fiscale"])

        self.collection = self.chroma_client.get_or_create_collection("fse_rag_index") 
        #devi controllare se con questo tutti gli altri file si collegano allo stesso RAG

        #inizializzazione del trascrittore
        self.transcriptor = TranscriptionPipeline()

        #inizializzazione del modello
        self.FSE_manager = FSEManager(self.chroma_client, self.ner, self.function_mode, self.RAGManager, self.env_file)

        self.anagrafica = Anagrafica(self.ner)
        
        
        #--------------------------------------------------- Salvataggio in PDF ---------------------------------------------------------
        self.PDF_output = os.getenv("PDF_PATH")
        self.template_directory = os.getenv("TEMPLATE_DICTIONARY")
        self.template_name = os.getenv("TEMPLATE_NAME")
        self.output_html_path = os.getenv("OUTPUT_HTML_PATH")
        #---------------------------------------------------------------------------------------------------------------------------------

    #---------------------------------------------- FUNZIONI PER LA GESTIONE DELLA PIPELINE ----------------------------------------------

    def Pipeline_manager(self, audio_filepath):
        #OSS. VANNO SALVAGUARDATI I FILE AUDIO E JSON => VEDERE COME SI PUò GESTIRE MEGLIO IL SALVATAGGIO E LO STORAGE

        """Serve una logica di reset o re-inizializzazione del RAGManager e PipelineManager. Al login di un medico dovresti:
            Ricreare un’istanza del PipelineManager
            Chiudere o invalidare quelle precedenti"""
        
        #acquisizione del testo trascritto
        self.logger.info(f"Procedo all'acquisizione della nuova trascrizione...")
        report_text = self.transcriptor.run(audio_filepath)

        #estrazione e check sulla validità dell'anagrafica del paziente nel DB
        self.logger.info(f"Procedo all'estrazione dell'anagrafica del paziente ed alla verifica sulla presenza del suo FSE...")
        try:
            anagrafica_paziente = self.anagrafica.extract_anagrafica(report_text["transcription"])
            #Controllo sull'anagrafica estratta
            self.logger.info(f"Anagrafica paziente estratta: {anagrafica_paziente}")

            #check sull'anagrafica di base (codice fiscale, nominativo e recapito telefonico) del paziente
            self.anagrafica.check_anagrafica(anagrafica_paziente)
        except Exception as e:
            self.logger.warning(f"****Anagrafica del paziente non specificata, dovrai inserirla necessariamente in fase di convalida del documento****")
        

        #Generazione dell'embedding della trascrizione per il RAG - prima procedo all'anonimizzazione del referto
        self.logger.info(f"Procedo all'update del nuovo documento nel RAG...")
        self.logger.info(f"Procedo al calcolo dell'embedding del testo...")
        report_text_RAG = self.anagrafica.anonimizza_referto(report_text["transcription"])

        #Controllo sul referto anonimizzato
        self.logger.info(f"Report anonimizzato: {report_text_RAG}")
        
        #calcolo dell'embedding del testo
        embedding_id = self.RAGManager.compute_id(report_text_RAG, self.function_mode) #calcolo l'id univoco su tutto il testo
        embedding = self.RAGManager.compute_chunk_embeddings(report_text_RAG, self.function_mode) #calcolo gli embedding sui chunk

        try:
            #salvataggio della coppia audio + testo nel database 
            self.logger.info(f"Procedo all'update della trascrizione e dell'audio nel DB...")

            # Store transcription in the database
            self.DB_manager.insert_transcription( 
                audio_filename=report_text["filename"],
                transcription=report_text["transcription"],
                embedding_id=embedding_id, #id dell'embedding è utilizzato come id anche per le altre collezioni
                language=report_text["language"],
                audio_filepath=report_text["audio_filepath"] 
            )
        except Exception as e:
            self.logger.warning(f"Errore nel salvataggio: {e}")

        #-------------------------------------------------------------------------------------------------------------------------

        #generazione del documento dalla LLM - do alla LLM il referto anonimizzato
        self.logger.debug(f"Procedo alla generazione del nuovo referto...")
        clinical_report = self.FSE_manager.FSE_manager(report_text["timestamp"], 
                                                       report_text_RAG, 
                                                       embedding, 
                                                       self.anagrafica_medico, 
                                                       anagrafica_paziente) 
        
        ner_clinical_reports = self.ner.extract_medical_entities(clinical_report[0]) #estrazione delle entità mediche dal referto generato
        self.logger.info(f"Entità mediche estratte dal referto: {ner_clinical_reports}")
        #salvataggio del documento nel DB
        self.logger.info(f"Aggiunta referto all'FSE del paziente...")
        document_id = self.DB_manager.insert_clinical_report(embedding_id, clinical_report[0])

        #salvataggio dell'embedding (strutturato) nel DB
        embedding_doc = self.RAGManager.prepare_embedding_doc(report_text_RAG, embedding_id, embedding, self.function_mode)
        embedding_doc_id = self.DB_manager.insert_embedding(embedding_doc)

        self.logger.info(f"**** Rimozione del referto paziente dalla cartella temporanea... ****")
        #TODO: MECCANISMO DI RECUPERO IN CASO DI INTERRUZIONE PRIMA DEL SALVATAGGIO IN DB
        #Viene effettuato il selvataggio del JSON temporaneamente anche in locale per prevenire la possibile perdita di info fino al salvataggio nel DB
        if os.path.exists(clinical_report[1]): #il check non dovrebbe essere necessario ma è meglio metterlo
            os.remove(clinical_report[1])

        #REFRESH PERIODICO DEL RAG OGNI 2 ORE
        if datetime.now() == self.update_time:
            self.logger.info(f"Sincronizzazione RAG - MongoDB in corso ...")
            self.RAGManager.sync_chroma_from_mongo() #fa la sincronizzazione periodica tra il RAG e MongoDB
            self.update_time = datetime.now() + timedelta(hours=2)
            self.logger.info(f"Sincronizzazione RAG - MongoDB terminata ...")
        
        return document_id
   

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


