import os
import sys
import hashlib
import numpy as np
import spacy
from datetime import datetime, timedelta
import json
from typing import List, Dict, Literal, Tuple
from log import Logger
import logging

from langchain.text_splitter import RecursiveCharacterTextSplitter
import re

from sklearn.preprocessing import normalize

from sentence_transformers import SentenceTransformer
from langchain.text_splitter import RecursiveCharacterTextSplitter

from chromadb import Client 

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from Database.mongodb import DB
from dotenv import load_dotenv

#TODO: è IL CASO DI USARE UN NER?

class RAGManager:
    def __init__(self, chroma_path: str, cf = None):

        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger("RAG_Manager")

        self.chroma_path = os.getenv("CHROMA_DB_PATH") #./rag_data o /var/lib/rag_data
        self.chroma_client = Client() #con Client viene inizializzata una sessione temporanea in RAM quindi una volta terminata vengono persi tutti i dati
        #self.chroma_client = PersistentClient(path=self.chroma_path) 

        self.collection = self.chroma_client.get_or_create_collection("fse_rag_index")
        self.embedder = SentenceTransformer("distiluse-base-multilingual-cased-v2")

        self.nlp = spacy.load("it_core_news_sm")

        self.cf = cf

        self.db_manager = DB()

        self.inizialize_RAG_from_DB()
  
    #per l'inizializzazione del RAG
    def inizialize_RAG_from_DB(self): #funzione richiamata quando viene avviata una sessione del sistema (dopo il login da interfaccia)
        try:
            self.logger.info("Inizializzazione del RAG a partire dal database")

            # Recupera tutto ciò che serve dal database in base al codice fiscale del medico
            reports = self.db_manager.get_all_clinical_reports_by_doctor_cf(self.cf) #la funzione ritorna tutti i referti di un medico che sono stati validati
            """Struttura clinical report:
                        "embedding_id"
                        "timestamp": timestamp,
                        "type": self.function_mode,
                        "dati medico": anagrafica_medico,
                        "dati paziente": anagrafica_paziente,
                        "scheda_ps": scheda_ps
            """
            if not reports:
                self.logger.warning("Nessun referto trovato per il medico.")
                return
            
            #Faccio una prova per vedificare la correttezza di reports
            self.logger.info(f"Verifica sulla struttura di reports: {reports[0]}")

            #non posso recuperare le trascrizioni tramite il cf del medico quindi recupero i referti che contengono l'embedding_id
            embedding_ids = [r["embedding_id"] for r in reports if "embedding_id" in r]

            if not embedding_ids:
                self.logger.warning("Nessun embedding_id trovato nei referti.")
                return
            
            #Faccio una prova per vedificare la correttezza di embedding_ids
            self.logger.info(f"Verifica embedding id: {embedding_ids[0]}")
            
            documents = self.db_manager.get_all_transcription_by_embedding_id(embedding_ids)

            if not documents:
                self.logger.warning("Nessun documento trovato per l'inizializzazione.")
                return

            #Faccio una prova per vedificare la correttezza di documents
            self.logger.info(f"Verifica sulla struttura delle trascrizioni: {documents[0]}")

            #TODO: FORSE è MEGLIO ACCOPPIARE DOCUMENTS E REPORTS IN UN UNICO DIZIONARIO
            #       con struttura {"id": , "transcription": , "report": }

            
            self.logger.info(f"**** Procedo all'inizializzazione del RAG con i documenti individuati")
            self.add_to_RAG(documents, reports)
            self.logger.info(f"Inizializzato RAG con {len(documents)} documenti.")

        except Exception as e:
            self.logger.warning("Impossibile effettuate il caricamento dei referti nel RAG perchè non risultano referti prodotti del medico")

    #TODO: CONTROLLARE CHE FUNZIONI CORRETTAMENTE CON IL DB - SENZA NON SEMBRANO ESSERCI ERRORI
    def add_to_RAG(self, documents: List[Dict[str, str]], reports: List[Dict[str, str]]): # nel RAG salvo ID, EMBEDDING e REFERTO 
        #La funzione prende in ingresso una lista di trascrizioni e una lista di referti corrispondenti da inserire nel RAG - provengono sempre dal DB
        # (può essere in fase di inizializzazione, oppure in fase di sincronizzazione - programmata ogni 2 ore) 
        # dato che gli embedding vengono calcolati all'inizio di ogni nuovo report e inseriti nel DB dopo il calcolo del referto
        # non dovrebbero esserci problemi legati alla loro mancanza
        
        reports_by_id = {r["embedding_id"]: r for r in reports}

        for doc in documents:
            raw_text = doc.get("text", "")
            doc_type = doc.get("type", "generico")

            doc_id = doc.get("embedding_id") #TODO: DA CONTROLLARE

            #prendo il report
            #TODO: DA CONTROLLARE
            metadata = reports_by_id.get(doc_id) #self.db_manager.get_validated_clinical_report(doc_id)

            if not metadata:
                self.logger.warning(f"Nessun metadata trovato per il documento {doc_id}")
                continue

            self.logger.info(f"Check sul referto: {metadata}")

            record = self.db_manager.get_embedding_by_id(doc_id) #prendo l'embedding dal DB

            self.logger.info(f"Embedding record dal DB: {record}")

            if not record or "chunks" not in record or "complete_embedding" not in record:
                self.logger.warning(f"Nessun embedding trovato o incompleto per il documento {doc_id}") 
                continue

            #preparo i dati relativi al documento completo - sono comuni a tutti i chunk dello stesso testo
            parent_metadata = {
                **metadata,
                "parent_doc_id": doc_id,
                "complete_embedding": record["complete_embedding"], 
                "type": doc_type
            }

            for chunk in record["chunks"]:
                chunk_id = chunk.get("id") #sicuri che funziona?
                if not chunk_id:
                    self.logger.warning(f"Chunk senza ID nel documento {doc_id}")
                    continue
                self.logger.info(f"Check sul chunk id: {chunk_id}")

                try:
                    if not self.collection.peek(ids=[chunk_id]):
                        self.collection.add(
                            documents=[chunk["text"]],
                            embeddings=[chunk["embedding"]],
                            ids=[chunk_id],
                            metadatas=[parent_metadata]
                        )
                except Exception as e:
                    self.logger.warning(f"Errore inserendo chunk {chunk_id} nel RAG: {e}")
                    continue

    #------------------------------------------ CALCOLO DELL'EMBEDDING ---------------------------------------------
    #per la preparazione del testo fornito - ovvero la trascrizione usata poi per calcolare l'embedding
    def clean_text(self, text):
        return text.strip().replace("\n", " ").replace("  ", " ")
    
    #TODO: VA SCELTA BENE LA CHUNK_SIZE E CHUNK_OVERLAP
    #TODO: DEVE ESSERE OTTIMIZZATA LA SUDDIVISIONE IN CHUNK perchè influenza il matching
    #       c'è il rischio che vengano scartati dei documenti se con la divisione in chunk contenuti simili vengono suddivisi diversamente anche con il retireval ibrido e la cosine similarity?
    def split_and_clean(self, text: str, chunk_size: int = 512, chunk_overlap: int = 50):
        doc = self.nlp(text)

        chunks = []
        current_chunk = ""
        for sent in doc.sents:
            sentence = sent.text.strip()
            if len(current_chunk) + len(sentence) <= chunk_size:
                current_chunk += " " + sentence
            else:
                chunks.append(current_chunk.strip())
                if chunk_overlap > 0:
                    # overlap a livello di parole
                    overlap_words = current_chunk.strip().split()[-chunk_overlap:]
                    current_chunk = " ".join(overlap_words) + " " + sentence
                else:
                    current_chunk = sentence
        if current_chunk:
            chunks.append(current_chunk.strip())
        return chunks
    
    #per la generazione dell'id univoco (da utilizzare sia per il RAG che per il DB)
    def compute_id(self, content: str, doc_type: str = "") -> str:
        return f"{doc_type}_{hashlib.md5(content.encode('utf-8')).hexdigest()}" 
    
    def compute_embedding(self, text: str, doc_type: str) -> Tuple[str, np.ndarray]:
        """
        Calcola l'embedding del testo completo (usato per ID univoco e salvataggio nel DB).
        """
        doc_id = self.compute_id(text, doc_type)
        embedding = self.embedder.encode(text)
        return doc_id, embedding

    def compute_embedding_for_chunk(self, chunk: str) -> np.ndarray:
        """
        Calcola l'embedding di un singolo chunk.
        """
        return self.embedder.encode(chunk)
    
    def compute_chunk_embeddings(self, text: str, doc_type: str) -> Dict:
        chunks = self.split_and_clean(text)

        chunk_data = []
        for chunk in chunks:
            chunk_id = self.compute_id(chunk, doc_type)
            embedding = self.compute_embedding_for_chunk(chunk)

            chunk_data.append({
                "id": chunk_id,
                "text": chunk,  # Conservo il testo perchè lo uso per il retrieval semantico
                "embedding": embedding.tolist()
            })

        return chunk_data

    def prepare_embedding_doc(self, text: str, embedding_id, chunk_data, doc_type: str) -> Dict: 
        #PREPARO L'EMBEDDING PER IL SALVATAGGIO NEL DB -> nel DB salvo ID e EMBEDDING
        doc_id, embedding = self.compute_embedding(text, doc_type) #calcolo l'ID della entry (trascrizione, referto, embedding)
        """chunks = self.split_and_clean(text)

        chunk_data = []
        for chunk in chunks:
            chunk_id = self.compute_id(chunk, doc_type)
            embedding = self.compute_embedding_for_chunk(chunk)

            chunk_data.append({
                "id": chunk_id,
                "text": chunk,  # Conservo il testo perchè lo uso per il retrieval semantico
                "embedding": embedding.tolist()
            })"""

        embedding_data = {
            "_id": doc_id,
            "complete_embedding": embedding,
            "chunks": chunk_data,
            "timestamp": datetime.now()
        }

        return embedding_data   


def main():
    env_file="key.env"
    load_dotenv(env_file)

    # Imposta variabili d'ambiente se non già impostate
    chroma_path = os.getenv("CHROMA_DB_PATH")
    chroma_client = Client() 

    # Codice fiscale medico fittizio per test
    medico_cf = "ABC123DEF45"

    # Istanzia il gestore RAG
    rag = RAGManager(chroma_path=os.environ["CHROMA_DB_PATH"], cf=medico_cf)

    # Simula una trascrizione clinica
    test_text = """
    Il paziente presenta un forte dolore al petto. Si sospetta un infarto miocardico acuto.
    Viene somministrata aspirina e si procede a elettrocardiogramma. La pressione è 150/95,
    frequenza cardiaca elevata. Si consiglia ricovero immediato.
    """

    doc_type = "Emergency"

    # Test pulizia + chunking
    print("\n🔹 Test chunking:")
    chunks = rag.split_and_clean(test_text)
    for i, c in enumerate(chunks):
        print(f"[Chunk {i}]: {c}\n")

    # Test embedding
    print("\n🔹 Test embedding completo:")
    doc_id, complete_embedding = rag.compute_embedding(test_text, doc_type)
    print("Doc ID:", doc_id)
    print("Embedding shape:", len(complete_embedding))

    print("\n🔹 Test embedding per chunks:")
    chunk_data = rag.compute_chunk_embeddings(test_text, doc_type)
    for ch in chunk_data:
        print(f"Chunk ID: {ch['id']} | Lunghezza embedding: {len(ch['embedding'])}")

    # Simula salvataggio
    print("\n🔹 Test preparazione documento per salvataggio:")
    embedding_doc = rag.prepare_embedding_doc(test_text, embedding_id=doc_id, chunk_data=chunk_data, doc_type=doc_type)
    print("Chiavi documento embedding:", embedding_doc.keys())

    # Simula struttura report + documento per test add_to_RAG()
    report = {
        "embedding_id": doc_id,
        "timestamp": datetime.now().isoformat(),
        "type": doc_type,
        "dati medico": {"cf": medico_cf, "nome": "Mario", "cognome": "Rossi"},
        "dati paziente": {"cf": "XYZ987LMN65", "nome": "Giuseppe", "cognome": "Verdi"},
        "scheda_ps": {}
    }

    doc = {
        "embedding_id": doc_id,
        "text": test_text,
        "type": doc_type
    }

    # Simula inserimento nel RAG (RAM)
    print("\n🔹 Test inserimento nel RAG (RAM):")
    rag.add_to_RAG([doc], [report])
    print("Inserimento completato")

if __name__ == "__main__":
    main()
