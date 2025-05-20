import os
import sys
import hashlib
import json
from typing import List, Dict, Literal
from log import Logger

from sklearn.preprocessing import normalize

from sentence_transformers import SentenceTransformer
from langchain.text_splitter import RecursiveCharacterTextSplitter

from chromadb import Client 

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from Database.mongodb import DB

#check su cosa va nel RAG

class RAGManager:
    def __init__(self, chroma_path: str, cf = None):
        self.logger = Logger(self.__class__.__name__).get_logger()

        self.chroma_path = os.getenv("CHROMA_DB_PATH") #./rag_data o /var/lib/rag_data
        self.chroma_client = Client() #con Client viene inizializzata una sessione temporanea in RAM quindi una volta terminata vengono persi tutti i dati
        #self.chroma_client = PersistentClient(path=self.chroma_path) 

        self.collection = self.chroma_client.get_or_create_collection("fse_rag_index")
        self.embedder = SentenceTransformer("distiluse-base-multilingual-cased-v2")

        self.db_manager = DB()

        self.inizialize_RAG_from_DB(cf)


    def inizialize_RAG_from_DB(self, cf): #funzione richiamata quando viene avviata una sessione del sistema (dopo il login da interfaccia)
        try:
            self.logger.info("Inizializzazione del RAG a partire dal database")

             # Recupera tutto ciò che serve dal database in base al codice fiscale del medico
            documents = self.db_manager.get_all_clinical_reports_by_doctor_cf(cf) #la funzione ritorna trasrizioni+clinical_report+operatori
            if not documents:
                self.logger.warning("Nessun documento trovato per l'inizializzazione.")
                return

            self.add_to_RAG(documents)
            self.logger.info(f"Inizializzato RAG con {len(documents)} documenti.")

        except Exception as e:
            self.logger.warning("Impossibile effettuate il caricamento dei referti nel RAG perchè non risultano referti prodotti del medico")
    
    def compute_id(self, content: str, doc_type: str) -> str:
        # Crea un ID unico per evitare duplicazioni
        raw_id = f"{doc_type}_{hashlib.md5(content.encode('utf-8')).hexdigest()}"
        return raw_id
    
    def rag_element_generator(self, timestamp, report_text_RAG, scheda_ps=None, clinical_report=None): 
        return [
            {"text": report_text_RAG, "type": "referto", "metadata": {"timestamp": timestamp}},
            {"text": scheda_ps, "type": "scheda_ps", "metadata": {"timestamp": timestamp}} if scheda_ps else None,
            {"text": clinical_report, "type": "referto_clinico", "metadata": {"timestamp": timestamp}} if clinical_report else None,
        ]

    def add_to_RAG(self, documents: List[Dict[str, str]]):
        for doc in documents:
            if not doc or not doc.get("text", "").strip():
                continue

            raw_text = doc.get("text", "")
            doc_type = doc.get("type", "generico")
            metadata = doc.get("metadata", {})
            
            # Pulizia testo
            cleaned_text = self.clean_text(raw_text)

            # Estrazione elementi RAG (es. tabelle, paragrafi, etc.)
            for elem in self.rag_element_generator(**doc):
                if elem:
                    elem_id = self.compute_id(elem["text"], elem["type"])
                    if not self.collection.peek(ids=[elem_id]):
                        self.collection.add(
                            documents=[elem["text"]],
                            metadatas=[elem["metadata"]],
                            ids=[elem_id]
                        )

            # Split del testo in chunk
            text_splitter = RecursiveCharacterTextSplitter(
                chunk_size=512,
                chunk_overlap=50
            )
            chunks = text_splitter.split_text(cleaned_text)

            # Preparazione dati per inserimento in blocco
            documents_to_add = []
            embeddings_to_add = []
            ids_to_add = []
            metadatas_to_add = []

            for chunk in chunks:
                chunk_id = self.compute_id(chunk, doc_type)
                if self.collection.peek(ids=[chunk_id]):
                    continue
                embedding = self.embedder.encode(chunk)
                embedding = normalize([embedding])[0]
                
                documents_to_add.append(chunk)
                embeddings_to_add.append(embedding)
                ids_to_add.append(chunk_id)
                metadatas_to_add.append({"type": doc_type, **metadata})

            # Inserimento batch dei chunk
            if documents_to_add:
                self.collection.add(
                    documents=documents_to_add,
                    embeddings=embeddings_to_add,
                    ids=ids_to_add,
                    metadatas=metadatas_to_add
                )
                self.logger.info(f"Aggiunti {len(documents_to_add)} chunk del documento '{doc_type}' all'indice RAG.")

    def clean_text(self, text):
        return text.strip().replace("\n", " ").replace("  ", " ")

    def compute_hash(self, text):
        return hashlib.md5(text.encode("utf-8")).hexdigest()

    def get_or_compute_embedding(self, text, collection, embedder):
        doc_id = self.compute_hash(text)
        result = collection.find_one({"_id": doc_id})
        
        if result and "embedding" in result:
            return result["embedding"]  # già calcolato

        embedding = embedder.encode(text).tolist()
        collection.insert_one({"_id": doc_id, "text": text, "embedding": embedding})
        return embedding