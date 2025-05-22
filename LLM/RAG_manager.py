import os
import sys
import hashlib
from datetime import datetime, timedelta
import json
from typing import List, Dict, Literal
from log import Logger
import logging

from sklearn.preprocessing import normalize

from sentence_transformers import SentenceTransformer
from langchain.text_splitter import RecursiveCharacterTextSplitter

from chromadb import Client 

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from Database.mongodb import DB

class RAGManager:
    def __init__(self, chroma_path: str, cf = None):
        #self.logger = Logger(self.__class__.__name__).get_logger()
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

    #per la preparazione del testo fornito  
    def clean_text(self, text):
        return text.strip().replace("\n", " ").replace("  ", " ")

    def split_and_clean(self, text): #pulisce il testo da caratteri per la formattazione e lo suddivide in chunck
        cleaned = self.clean_text(text)
        splitter = RecursiveCharacterTextSplitter(chunk_size=512, chunk_overlap=50)
        return splitter.split_text(cleaned)
    
    #per la generazione dell'id univoco (da utilizzare sia per il RAG che per il DB)
    def compute_id(self, content: str, doc_type: str = "") -> str:
        return f"{doc_type}_{hashlib.md5(content.encode('utf-8')).hexdigest()}"
  
    #per l'inizializzazione del RAG
    def inizialize_RAG_from_DB(self): #funzione richiamata quando viene avviata una sessione del sistema (dopo il login da interfaccia)
        try:
            self.logger.info("Inizializzazione del RAG a partire dal database")

             # Recupera tutto ciò che serve dal database in base al codice fiscale del medico
            documents = self.db_manager.get_all_clinical_reports_by_doctor_cf(self.cf) #la funzione ritorna trasrizioni+clinical_report+operatori
            if not documents:
                self.logger.warning("Nessun documento trovato per l'inizializzazione.")
                return

            self.add_to_RAG(documents)
            self.logger.info(f"Inizializzato RAG con {len(documents)} documenti.")

        except Exception as e:
            self.logger.warning("Impossibile effettuate il caricamento dei referti nel RAG perchè non risultano referti prodotti del medico")

    def add_to_RAG(self, documents: List[Dict[str, str]]):

        for doc in documents:
            raw_text = doc.get("text", "")
            doc_type = doc.get("type", "generico")
            metadata = doc.get("metadata", {})
            chunks = self.split_and_clean(raw_text)

            for chunk in chunks:
                chunk_id = self.compute_id(chunk, doc_type)
                if not self.collection.peek(ids=[chunk_id]):
                    record = self.db_manager.get_embedding_by_id(chunk_id)
                    if record:
                        self.collection.add(
                            documents=[chunk],
                            embeddings=[record["embedding"]],
                            ids=[chunk_id],
                            metadatas=[metadata]
                        )

    def compute_embedding(self, text: str, doc_type: str):
        doc_id = self.compute_id(text, doc_type) #calcolo l'id da utilizzare sia per il RAG che per il DB
        embedding = self.embedder.encode(text) #calcolo l'embedding del testo
        embedding = normalize([embedding])[0] #normalizzo l'embedding del testo
        return doc_id, embedding

    def prepare_embedding_doc(self, doc_id, embedding, doc_type: str, metadata: dict) -> str: #VA CAMBIATA PERCHè SERVONO ANCHE I REFERTI
        #preparo i dati da inserire nel RAG
        embedding_data = {
            "_id": doc_id, #id del testo
            "type": doc_type, #testo -> non serve si può togliere
            "embedding": embedding.tolist(), #embedding del testo
            "referto": metadata, #passo in metadata i referti relativi al testo
            "timestamp": datetime.now()
        }
        return embedding_data

    def sync_chroma_from_mongo(self, from_date: datetime = None):
        """
        Sincronizza embedding da MongoDB a ChromaDB per il medico loggato.
        Può filtrare solo quelli aggiornati nelle ultime X ore.
        """
        try:
            self.logger.info("Inizio sincronizzazione da MongoDB a ChromaDB")

            if from_date is None:
                from_date = datetime.now() - timedelta(hours=2)

            all_embeddings = self.db_manager.get_embeddings_by_doc_cf(self.cf)

            # Filtro per timestamp recente
            recent_embeddings = [
                e for e in all_embeddings
                if e.get("timestamp") and isinstance(e["timestamp"], datetime) and e["timestamp"] > from_date
            ]

            new_embeddings = []
            for emb in recent_embeddings:
                try:
                    # Verifica se l'embedding è già presente
                    found = self.collection.get(emb["_id"])
                    if not found:
                        self.collection.add(
                            documents=[emb["text"]],
                            embeddings=[emb["embedding"]],
                            ids=[emb["_id"]],
                            metadatas=[emb.get("metadata", {})]
                        )
                        new_embeddings.append(emb["_id"])
                except Exception as e:
                    self.logger.warning(f"Errore con embedding ID {emb['_id']}: {e}")

            self.logger.info(f"Sincronizzati {len(new_embeddings)} nuovi embedding.")

        except Exception as e:
            self.logger.error(f"Errore nella sincronizzazione: {e}")
