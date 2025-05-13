import os
import hashlib
from typing import List, Dict, Literal
from log import Logger
from sentence_transformers import SentenceTransformer
from chromadb import Client 

class RAGManager:
    def __init__(self, chroma_path: str):
        self.logger = Logger(self.__class__.__name__).get_logger()
        self.chroma_path = os.getenv("CHROMA_DB_PATH")
        self.chroma_client = Client() #vedere se usare PersistentClient o qualcos'altro
        self.collection = self.chroma_client.get_or_create_collection("fse_rag_index")
        self.embedder = SentenceTransformer("distiluse-base-multilingual-cased-v2")

    def compute_id(self, content: str, doc_type: str) -> str:
        # Crea un ID unico per evitare duplicazioni
        raw_id = f"{doc_type}_{hashlib.md5(content.encode('utf-8')).hexdigest()}"
        return raw_id
    
    def rag_element_generator(self, timestamp, report_text_RAG, scheda_ps = None, clinical_report = None):
        embedding = self.embedder.encode(report_text_RAG)
        self.collection.add(documents=[report_text_RAG], embeddings=[embedding], ids=[f"record_{timestamp}"])

        rag_docs = [
                    {"text": report_text_RAG, "type": "referto"},
                    {"text": scheda_ps, "type": "scheda_ps"} if scheda_ps else None,
                    {"text": clinical_report, "type": "referto_clinico"} if scheda_ps else None
        ]
        rag_docs = [d for d in rag_docs if d]  # Rimuove i None
        return rag_docs

    def add_to_RAG(self, documents: List[Dict[str, str]]):
        """
        Aggiunge documenti all'indice RAG.
        Ogni documento deve essere un dizionario con chiavi: 'text', 'type', e opzionalmente 'metadata'.
        'type' può essere: 'referto', 'fse', 'scheda_ps', ecc.
        """
        for doc in documents:
            text = doc["text"]
            doc_type = doc.get("type", "generico")
            metadata = doc.get("metadata", {})

            if not text.strip():
                continue

            doc_id = self.compute_id(text, doc_type)
            embedding = self.embedder.encode(text)

            self.collection.add(
                documents=[text],
                embeddings=[embedding],
                ids=[doc_id],
                metadatas=[{
                    "type": doc_type,
                    **metadata
                }]
            )
            self.logger.info(f"Aggiunto documento {doc_type} con ID {doc_id} all'indice RAG.")
