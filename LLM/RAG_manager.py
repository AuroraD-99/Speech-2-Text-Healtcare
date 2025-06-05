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
import re
import subprocess

from sklearn.preprocessing import normalize

from sentence_transformers import SentenceTransformer
from langchain.text_splitter import RecursiveCharacterTextSplitter

from chromadb import Client 

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from Database.mongodb import DB
from NER.ner import NER
from dotenv import load_dotenv


class RAGManager:
    def __init__(self, chroma_path: str, ner, db_manager, function_mode, cf = None):

        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger("RAG_Manager")

        self.function_mode = function_mode

        self.chroma_path = os.getenv("CHROMA_DB_PATH") #./rag_data o /var/lib/rag_data
        self.chroma_client = Client() #con Client viene inizializzata una sessione temporanea in RAM quindi una volta terminata vengono persi tutti i dati
        #self.chroma_client = PersistentClient(path=self.chroma_path) 

        self.collection = self.chroma_client.get_or_create_collection(name="fse_rag_index", metadata={"hnsw:space": "cosine"})
        self.embedder = SentenceTransformer("distiluse-base-multilingual-cased-v2")

        #TODO: vedere se si può integrare il NER insieme a spacy o utilizzare un approccio comune/ibrido
            # - usare il ner per salvare nel parent metadata le info sulle entità nel documento
        #Configurazione del modello
        self.model_name = os.getenv("MODEL_PATH_SPACY") #"it_core_news_sm"

        #utilizzo spacy in modo da realizzare embedding con contesto più coeso
        try: #TODO: CONTROLLARE
            self.nlp = spacy.load(self.model_name)
        except OSError:
            #se il path del modello non esiste, il modello viene scaricato al path specificato
            self._model_download()
            self.nlp = spacy.load(self.model_name)

        self.cf = cf

        self.db_manager = db_manager
        self.ner = ner

        self._inizialize_RAG_from_DB()

    def _model_download(self, model_name: str):
            """Scarica il modello spaCy indicato se non è già presente."""
            try:
                self.logger.info(f"Scaricamento modello spaCy '{model_name}'...")
                subprocess.run(["python", "-m", "spacy", "download", model_name], check=True)
                self.logger.info(f"Modello '{model_name}' scaricato con successo.")
            except subprocess.CalledProcessError:
                self.logger.error(f"Errore nel download del modello spaCy '{model_name}'.")
    
    #per l'inizializzazione del RAG
    def _inizialize_RAG_from_DB(self): #funzione richiamata quando viene avviata una sessione del sistema (dopo il login da interfaccia)
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
        
        reports_by_id = {r["embedding_id"]: r for r in reports}

        for doc in documents:
            raw_text = doc.get("text", "")
            doc_type = doc.get("type", "generico")

            doc_id = doc.get("embedding_id") #TODO: DA CONTROLLARE

            #prendo il report
            #TODO: DA CONTROLLARE
            metadata = reports_by_id.get(doc_id)

            if not metadata:
                self.logger.warning(f"Nessun metadata trovato per il documento {doc_id}")
                continue

            self.logger.info(f"Check sul referto: {metadata}")

            record = self.db_manager.get_embedding_by_id(doc_id) #prendo l'embedding dal DB

            self.logger.info(f"Embedding record dal DB: {record}")

            if not record or "chunks" not in record or "complete_embedding" not in record:
                self.logger.warning(f"Nessun embedding trovato o incompleto per il documento {doc_id}") 
                continue

            entities = record["entities"]

            #preparo i dati relativi al documento completo - sono comuni a tutti i chunk dello stesso testo
            parent_metadata = {
                **metadata,
                "parent_doc_id": doc_id,
                "entities": entities,
                "complete_embedding": record["complete_embedding"], 
                "type": doc_type
            }

            for chunk in record["chunks"]:
                chunk_id = chunk.get("id") #sicuri che funziona?
                if not chunk_id:
                    self.logger.warning(f"Chunk senza ID nel documento {doc_id}")
                    continue
                self.logger.info(f"Check sul chunk id: {chunk_id}")

                chunk_entities = chunk.get("entities")

                try:
                    if not self.collection.peek(ids=[chunk_id]):
                        self.collection.add(
                            documents=[chunk["text"]],
                            entities_chunk=chunk_entities,
                            embeddings=[chunk["embedding"]],
                            ids=[chunk_id],
                            metadatas=[parent_metadata]
                        )
                except Exception as e:
                    self.logger.warning(f"Errore inserendo chunk {chunk_id} nel RAG: {e}")
                    continue
            
        self.logger.info(f"Numero di elementi caricati nel RAG: {self.collection.count()}")

    #------------------------------------------ CALCOLO DELL'EMBEDDING ---------------------------------------------
    #per la preparazione del testo fornito - ovvero la trascrizione usata poi per calcolare l'embedding
    def clean_text(self, text):
        return text.strip().replace("\n", " ").replace("  ", " ")
    
    #TODO: VA SCELTA BENE LA CHUNK_SIZE E CHUNK_OVERLAP
    def split_and_clean(self, text: str, chunk_size: int = 512, chunk_overlap: int = 50):
        doc = self.nlp(text) #uso spacy per migliorare il chunking
        #COME FUNZIONA ESATTAMENTE?

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
        #Calcola l'embedding del testo completo (usato per ID univoco e salvataggio nel DB).
        #ho usato l'embedding dell'intero documento perchè dato che prendo tutti i referti dello stesso medico c'è un'alta probabilità che per pazienti con 
        # "situazioni" cliniche molto simili organizzi il referto in modo simile e quindi gli embedding saranno simili
        
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
            entities = self.ner.extract_medical_entities(chunk)

            chunk_data.append({
                "id": chunk_id,
                "text": chunk,  # Conservo il testo perchè lo uso per il retrieval semantico
                "embedding": embedding.tolist(),
                "entities": entities #memorizzo anche le entità che caratterizzano il chunk in modo da favorire il filtraggio
            })

        return chunk_data

    def prepare_embedding_doc(self, text: str, embedding_id, chunk_data, doc_type: str) -> Dict: 
        #PREPARO L'EMBEDDING PER IL SALVATAGGIO NEL DB -> nel DB salvo ID e EMBEDDING
        doc_id, embedding = self.compute_embedding(text, doc_type) #calcolo l'ID della entry (trascrizione, referto, embedding)

        entities = self.ner.extract_medical_entities(text)

        embedding_data = {
            "_id": doc_id,
            "complete_embedding": embedding,
            "entities": entities,
            "chunks": chunk_data,
            "timestamp": datetime.now()
        }

        return embedding_data   
    
    def cosine_similarity(a, b):
        a = np.array(a)
        b = np.array(b)
        return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-10)

    """def retrieve_context(self, embedding, entities, top_k=2): #c'è un problema con i chunk retrieval
        try:
            embedding_chunk = [e["embedding"] for e in embedding]
        except Exception as e:
            self.logger.error(f"Errore nel preprocessing embedding: {e}")
            return None

        results = []

        #recupero documenti interi con filtri stringenti
        docs = self._query_full_documents(embedding, entities)
        results.extend(docs)
        self.logger.info(f"Score match su documenti completi (e con filtraggio delle entità): {docs}")

        #se ancora bastano, recupero chunk (raddoppio il numero di risultati - caso peggiore (tutti duplicati))
        if len(results) < 2*top_k:
            self.logger.info(f"Numero di match insufficiente: {len(results)}. Procedo al matching sui chunk...")
            chunks = self._query_chunks(embedding_chunk, entities)
            self.logger.info(f"")
            results.extend(chunks)

        #tolgo i risultati duplicati e seleziono i top_k
        self.logger.info(f"Rimozione di eventuali risutlati duplicati")
        seen_ids = set()
        unique_results = []
        for score, metadata in sorted(results, key=lambda x: x[0] or 0, reverse=True):
            pid = metadata.get("parent_doc_id")
            if pid not in seen_ids:
                referto = metadata.get("clinical_report") or metadata.get("scheda_ps")
                if referto:
                    self.logger.info(f"Nuovo referto ottenuto mediante il match - id del documento: {pid}")
                    unique_results.append((score, referto))
                    seen_ids.add(pid)
            if len(unique_results) >= top_k:
                break

        if not unique_results:
            self.logger.info(f"Nessun contesto rilevante trovato mediante l'uso dell'embedding.")
            self.logger.info(f"Procedo ad individuare i referti con entità simili.")
            #TODO: QUERY PER MATCH SOLO SULLE ENTITà
            return None

        self.logger.info(f"Totale contesti restituiti: {len(unique_results)}")
        return "\n\n".join([r[1] for r in unique_results])

    def _query_full_documents(self, embedding, entities):
        try:
            metadatas = self.collection.get(include=["metadatas"]).get("metadatas", [])
        except Exception as e:
            self.logger.error(f"Errore nel recupero metadati: {e}")
            return []

        results = []
        for i, meta in enumerate(metadatas):
            if not meta or meta.get("type") != self.function_mode:
                continue

            complete_emb = meta.get("complete_embedding")
            doc_entities = set(meta.get("entities", []))
            parent_id = meta.get("parent_doc_id")

            if not complete_emb or not parent_id:
                continue

            # Entità: se strict, serve almeno un match
            match_entities = len(set(entities).intersection(doc_entities))
            if entities and match_entities < 0.1*len(set(entities)):
                self.logger.info(f"Numero di match troppo basso: {match_entities}")
                continue

            try:
                score = self.cosine_similarity(embedding, complete_emb)
                results.append((score, meta))
            except Exception as e:
                self.logger.error(f"Errore nel calcolo similarità doc {i}: {e}")

        return results

    def _query_chunks(self, embedding_chunks, entities):
        results = []

        for emb in embedding_chunks:
            try:
                query_result = self.collection.query(
                    query_embeddings=[emb],
                    n_results=10,
                    where={"type": self.function_mode},
                    include=["metadatas", "embeddings"]
                )
            except Exception as e:
                self.logger.error(f"Errore nella query per i chunk: {e}")
                continue

            metadatas = query_result.get("metadatas", [[]])[0]
            embeddings = query_result.get("embeddings", [[]])[0]

            for meta, chunk_emb in zip(metadatas, embeddings):
                if not meta:
                    continue

                doc_entities = set(meta.get("entities", []))
                entity_match = len(set(entities).intersection(doc_entities))

                if entities and entity_match < 0.1 * len(set(entities)):
                    self.logger.info(f"Match entità chunk troppo basso: {entity_match}")
                    continue

                try:
                    score = self.cosine_similarity(emb, chunk_emb)
                    results.append((score, meta))
                except Exception as e:
                    self.logger.error(f"Errore nel calcolo della similarità per chunk: {e}")

        return results"""
    
    def retrieve_context(self, entities, top_k=2):
        results = []

        # Recupero documenti completi usando solo le entità
        try:
            docs = self._query_full_documents_by_entities(entities)
            self.logger.info(f"Match su documenti completi usando solo entità: {docs}")
            results.extend(docs)
        except Exception as e:
            self.logger.error(f"Errore durante il recupero dei documenti per entità: {e}")
            return None

        # Se non ci sono abbastanza risultati, provo a interrogare i chunk
        if len(results) < top_k:
            self.logger.info(f"Risultati insufficienti ({len(results)}). Estendo la ricerca ai chunk...")
            try:
                chunks = self._query_chunks_by_entities(entities)
                self.logger.info(f"Chunk ottenuti dal match sulle entità: {chunks}")
                results.extend(chunks)
            except Exception as e:
                self.logger.error(f"Errore nel recupero dei chunk per entità: {e}")

        # Rimozione duplicati (stesso parent_doc_id) e selezione top_k
        self.logger.info("Rimozione di eventuali risultati duplicati...")
        seen_ids = set()
        unique_results = []
        for score, metadata in sorted(results, key=lambda x: x[0] or 0, reverse=True):
            pid = metadata.get("parent_doc_id")
            if pid not in seen_ids:
                referto = metadata.get("clinical_report") or metadata.get("scheda_ps")
                if referto:
                    self.logger.info(f"Nuovo referto ottenuto tramite entità - documento ID: {pid}")
                    unique_results.append((score, referto))
                    seen_ids.add(pid)
            if len(unique_results) >= top_k:
                break

        if not unique_results:
            self.logger.info("Nessun contesto rilevante trovato usando solo le entità.")
            return None

        self.logger.info(f"Totale contesti restituiti: {len(unique_results)}")
        return "\n\n".join([r[1] for r in unique_results])
    
    def _query_full_documents_by_entities(self, entities):
        """
        Recupera documenti interi che contengono tutte (o la maggior parte) delle entità specificate.
        """
        try:
            query_filter = {
                "entity_labels": {"$in": entities}  # Adatta al tuo sistema di filtro
            }

            # Esegui la query sul tuo vector store/database
            matches = self.vector_store.query_metadata(
                filter=query_filter,
                namespace="full_documents"
            )

            results = []
            for match in matches:
                score = match.get("score", 1.0)  # Usa 1.0 come default se non c'è uno score
                metadata = match.get("metadata", {})
                results.append((score, metadata))

            return results
        except Exception as e:
            self.logger.error(f"Errore nella query dei documenti completi per entità: {e}")
            return []


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
