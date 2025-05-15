import os
import hashlib
import json
from typing import List, Dict, Literal
from log import Logger
from sentence_transformers import SentenceTransformer
from chromadb import Client 

from Database. import DBManager

#check su cosa va nel RAG

class RAGManager:
    def __init__(self, chroma_path: str):
        self.logger = Logger(self.__class__.__name__).get_logger()

        self.chroma_path = os.getenv("CHROMA_DB_PATH") #./rag_data o /var/lib/rag_data
        self.chroma_client = Client() #con Client viene inizializzata una sessione temporanea in RAM quindi una volta terminata vengono persi tutti i dati
        #self.chroma_client = PersistentClient(path=self.chroma_path) 

        self.collection = self.chroma_client.get_or_create_collection("fse_rag_index")
        self.embedder = SentenceTransformer("distiluse-base-multilingual-cased-v2")

        self.db_manager = DBManager()


    def inizialize_RAG_from_DB(self): #funzione richiamata quando viene avviata una sessione del sistema (dopo il login da interfaccia)
        self.logger.info("Inizializzazione del RAG a partire dal database")

        documents = self.db_manager.get_validated_documents()  # Recupera tutto ciò che serve dal database 
        #potrebbe essere necessario limitare il numero di campioni recuperati dal database => si potrebbero recuperare solo i documenti relativi allo stesso medico ad esempio

        if not documents:
            self.logger.warning("Nessun documento trovato per l'inizializzazione.")
            return

        self.add_to_RAG(documents)
        self.logger.info(f"Inizializzato RAG con {len(documents)} documenti.")
    
    def compute_id(self, content: str, doc_type: str) -> str:
        # Crea un ID unico per evitare duplicazioni
        raw_id = f"{doc_type}_{hashlib.md5(content.encode('utf-8')).hexdigest()}"
        return raw_id
    
    def rag_element_generator(self, timestamp, report_text_RAG, scheda_ps=None, clinical_report=None):
        # Non aggiunge più al RAG qui, solo genera
        return [
            {"text": report_text_RAG, "type": "referto", "metadata": {"timestamp": timestamp}},
            {"text": scheda_ps, "type": "scheda_ps", "metadata": {"timestamp": timestamp}} if scheda_ps else None,
            {"text": clinical_report, "type": "referto_clinico", "metadata": {"timestamp": timestamp}} if clinical_report else None,
        ]

    def add_to_RAG(self, documents: List[Dict[str, str]]): #può essere cambiato in modo da farlo dal database così dovrebbero essere presi i documenti già validati
        for doc in documents:
            if not doc or not doc.get("text", "").strip():
                continue
            text = doc["text"]
            doc_type = doc.get("type", "generico")
            metadata = doc.get("metadata", {})
            doc_id = self.compute_id(text, doc_type)
            embedding = self.embedder.encode(text)
            self.collection.add(
                documents=[text],
                embeddings=[embedding],
                ids=[doc_id],
                metadatas=[{"type": doc_type, **metadata}]
            )
            self.logger.info(f"Aggiunto documento {doc_type} con ID {doc_id} all'indice RAG.")
