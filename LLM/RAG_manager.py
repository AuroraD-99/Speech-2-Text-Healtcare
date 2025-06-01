import os
import sys
import hashlib
import numpy as np
from datetime import datetime, timedelta
import json
from typing import List, Dict, Literal, Tuple
from log import Logger
import logging

from sklearn.preprocessing import normalize

from sentence_transformers import SentenceTransformer
from langchain.text_splitter import RecursiveCharacterTextSplitter

from chromadb import Client 

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from Database.mongodb import DB

#TODO: CAPIRE MEGLIO COME COMPORTARSI CON IL RETRIEVAL SUI CHUNK O SE BISOGNA TROVARE UN ALTRO MODO
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

        self.cf = cf

        self.db_manager = DB()

        self.inizialize_RAG_from_DB()
  
    #per l'inizializzazione del RAG
    def inizialize_RAG_from_DB(self): #funzione richiamata quando viene avviata una sessione del sistema (dopo il login da interfaccia)
        try:
            self.logger.info("Inizializzazione del RAG a partire dal database")

            # Recupera tutto ciò che serve dal database in base al codice fiscale del medico
            documents = self.db_manager.get_all_clinical_reports_by_doctor_cf(self.cf) 
            #la funzione ritorna trasrizioni+clinical_report+operatori 
            # - CONTROLLARE MEGLIO E SE è MEGLIO CAMBIARE COSA VIENE RITORNATO

            if not documents:
                self.logger.warning("Nessun documento trovato per l'inizializzazione.")
                return

            self.add_to_RAG(documents)
            self.logger.info(f"Inizializzato RAG con {len(documents)} documenti.")

        except Exception as e:
            self.logger.warning("Impossibile effettuate il caricamento dei referti nel RAG perchè non risultano referti prodotti del medico")


    #TODO: CAMBIARE IN BASE ALLA SCELTA SUL CONTENUTO DEL RAG
    def add_to_RAG(self, documents: List[Dict[str, str]]):
        #La funzione prende in ingresso un "documento" da inserire nel RAG - il documento proviene sempre dal DB
        # (può essere in fase di inizializzazione, oppure in fase di sincronizzazione - programmata ogni 2 ore) 
        # dato che gli embedding vengono calcolati all'inizio di ogni nuovo report e inseriti nel DB dopo il calcolo del referto
        # non dovrebbero esserci problemi legati alla loro mancanza
        # salvo ID, EMBEDDING e REFERTO 

        for doc in documents:
            raw_text = doc.get("text", "")
            doc_type = doc.get("type", "generico")

            doc_id = self.compute_id(raw_text, doc_type) #uso l'id calcolato sul testo completo per identificare il testo nel database
            metadata = self.db_manager.get_validated_clinical_report(doc_id)

            if not metadata:
                self.logger.warning(f"Nessun metadata trovato per il documento {doc_id}")
                continue
            
            record = self.db_manager.get_embedding_by_id(doc_id) #recupero gli embedding dal database

            if not record or "chunks" not in record: #DA CONTROLLARE MEGLIO
                self.logger.warning(f"Nessun embedding trovato per il documento {doc_id}")
                continue

            parent_metadata = {
                                    **metadata,
                                    "parent_doc_id": doc_id
                                }

            for chunk in record["chunks"]:
                chunk_id = chunk.get("id")
                if not chunk_id:
                    continue

                try:
                    if not self.collection.peek(ids=[chunk_id]):
                        self.collection.add(
                            documents=[chunk["text"]], #è il testo del chunk
                            embeddings=[chunk["embedding"]], #è l'embedding del chunk
                            ids=[chunk_id], #è l'id del chunk
                            metadatas=[parent_metadata] #sono il referto e l'id del documento
                        )
                except Exception as e:
                    self.logger.warning(f"Errore inserendo chunk {chunk_id} nel RAG: {e}")
                    continue


    def sync_chroma_from_mongo(self, from_date: datetime = None):
        #TODO: ATTESA ATTIVA DURANTE LA SINCRONIZZAZIONE OPPURE VAI INDIETRO DI 2.15 ORE INVECE DI 2
        try:
            self.logger.info("Inizio sincronizzazione da MongoDB a ChromaDB")

            if from_date is None:
                from_date = datetime.now() - timedelta(hours=2)

            all_embeddings = self.db_manager.get_embeddings_by_doc_cf(self.cf)
            documents_to_add = []

            for emb in all_embeddings: #scarta tutti i "documenti" già inseriti nel RAG
                if emb.get("timestamp") and emb["timestamp"] < from_date:
                    continue

                doc_type = emb.get("metadata", {}).get("type", "generico")
                original_text = " ".join(chunk["text"] for chunk in emb.get("chunks", []))

                documents_to_add.append({
                    "text": original_text,
                    "type": doc_type
                    # NOTE: non serve "metadata" perché add_to_RAG() lo recupera dal DB usando l'id
                })

            if documents_to_add:
                self.add_to_RAG(documents_to_add)
                self.logger.info(f"Sincronizzati {len(documents_to_add)} nuovi documenti.")
            else:
                self.logger.info("Nessun nuovo embedding da sincronizzare.")

        except Exception as e:
            self.logger.error(f"Errore nella sincronizzazione: {e}")

    #------------------------------------------ CALCOLO DELL'EMBEDDING ---------------------------------------------
    #per la preparazione del testo fornito - ovvero la trascrizione usata poi per calcolare l'embedding
    def clean_text(self, text):
        return text.strip().replace("\n", " ").replace("  ", " ")
    
    #TODO: VA SCELTA BENE LA CHUNK_SIZE E CHUNK_OVERLAP
    def split_and_clean(self, text: str, chunk_size: int = 512, chunk_overlap: int = 50): #pulisce il testo da caratteri per la formattazione e lo suddivide in chunck
        cleaned = self.clean_text(text)
        splitter = RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        return splitter.split_text(cleaned)
    
    #per la generazione dell'id univoco (da utilizzare sia per il RAG che per il DB)
    def compute_id(self, content: str, doc_type: str = "") -> str:
        return f"{doc_type}_{hashlib.md5(content.encode('utf-8')).hexdigest()}" 
    
    def compute_embedding_for_doc(self, text: str, doc_type: str) -> Tuple[str, np.ndarray]:
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

    def prepare_embedding_doc(self, text: str, doc_type: str) -> Dict:
        #PREPARO L'EMBEDDING PER IL SALVATAGGIO NEL DB -> nel DB salvo ID e EMBEDDING
        doc_id, _ = self.compute_embedding_for_doc(text, doc_type)
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

        embedding_data = {
            "_id": doc_id,
            "chunks": chunk_data,
            "timestamp": datetime.now()
        }

        return embedding_data   

