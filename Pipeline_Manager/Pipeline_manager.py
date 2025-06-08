import sys
import os
import re
import time
from datetime import datetime, timedelta
import logging    
import hashlib
import random

import argparse
from dotenv import load_dotenv

import json
from json2pdf_converter import generate

from bs4 import BeautifulSoup
import random
import requests
import csv
from datetime import datetime
from collections import Counter
from groq import Groq

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from LLM.FSE_pipeline import FSEManager
from Database.mongodb import DB
from Pipeline_Manager.Anagrafica import Anagrafica
from NER.ner import NER

class PipelineManager:
    def __init__(self, anagrafica_medico, function_mode="Emergency", env_file="key.env"):

        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger("PipelineManager")

        #Gestione del file .env per le variabili di ambiente
        self.env_file = env_file
        load_dotenv(self.env_file)

        self.function_mode = function_mode

        self.model = os.getenv("GROQ_MODEL_NAME")
        api_key = os.getenv("API_KEY_0") 
        api_key_1 = os.getenv("API_KEY_1") 
        api_key_2 = os.getenv("API_KEY_2") 
        api_key_3 = os.getenv("API_KEY_3")

        self.client_story = Groq(api_key=api_key) 
        self.client_story_1 = Groq(api_key=api_key_1)
        self.client_story_2 = Groq(api_key=api_key_2)
        self.client_story_3 = Groq(api_key=api_key_3)

        #NER per l'estrazione delle entities - usate sia per il retrieval che per migliorare la generazione
        self.ner = NER()

        #inizializzazione del database
        self.DB_manager = DB()

        #inizializzazione del modello
        self.FSE_manager = FSEManager(self.ner, self.function_mode, self.env_file)

        self.anagrafica = Anagrafica(self.ner)

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
        self.logger.info(f"Procedo all'acquisizione degli articoli da usare per la generazione del referto...")

        query = ["cancro", "ipertensione", "diabete", "infarto", "asma", "COVID-19", "ictus", "sclerosi multipla", "malattie rare", 
                 "malattie renali", "cardiopatia", "HIV", "allergie", "dolore cronico", "depressione", "medicina d'urgenza", "pediatria"]

        anagrafica_medici = [
            {
                "dati medico": {
                    "Anagrafica": {
                        "Email": "anna.quercia@fintoemail.it",
                        "Nome": "Anna",
                        "Cognome": "Quercia",
                        "Cellulare": "3331234567",
                        "Codice Fiscale": "QRCSNN80A41H501U",
                        "Ruolo": "Medico"
                    },
                    "Ospedale": {
                        "Nome Ospedale": "San Lorenzo",
                        "Città": "Torviano",
                        "Provincia": "TV",
                        "CAP": "30125",
                        "Reparto": "Oncologia"
                    }
                }
            },
            {
                "dati medico": {
                    "Anagrafica": {
                        "Email": "mario.rossi@fintoemail.it",
                        "Nome": "Mario",
                        "Cognome": "Rossi",
                        "Cellulare": "3332345678",
                        "Codice Fiscale": "RSSMRA65C12F205Z",
                        "Ruolo": "Medico"
                    },
                    "Ospedale": {
                        "Nome Ospedale": "CardioCenter",
                        "Città": "Belmonte",
                        "Provincia": "RM",
                        "CAP": "00145",
                        "Reparto": "Cardiologia"
                    }
                }
            },
            {
                "dati medico": {
                    "Anagrafica": {
                        "Email": "giovanni.bianchi@fintoemail.it",
                        "Nome": "Giovanni",
                        "Cognome": "Bianchi",
                        "Cellulare": "3333456789",
                        "Codice Fiscale": "BNCGNN70D15H501V",
                        "Ruolo": "Medico"
                    },
                    "Ospedale": {
                        "Nome Ospedale": "San Matteo",
                        "Città": "Maricella",
                        "Provincia": "MI",
                        "CAP": "20152",
                        "Reparto": "Dietologia"
                    }
                }
            },
            {
                "dati medico": {
                    "Anagrafica": {
                        "Email": "maria.verdi@fintoemail.it",
                        "Nome": "Maria",
                        "Cognome": "Verdi",
                        "Cellulare": "3334567890",
                        "Codice Fiscale": "VRDMRA75E41F205H",
                        "Ruolo": "Medico"
                    },
                    "Ospedale": {
                        "Nome Ospedale": "Respiro Pulito",
                        "Città": "Novaterra",
                        "Provincia": "NA",
                        "CAP": "80126",
                        "Reparto": "Pneumologia"
                    }
                }
            },
            {
                "dati medico": {
                    "Anagrafica": {
                        "Email": "paolo.amato@fintoemail.it",
                        "Nome": "Paolo",
                        "Cognome": "Amato",
                        "Cellulare": "3335678901",
                        "Codice Fiscale": "MTAPLO60B12A662S",
                        "Ruolo": "Medico"
                    },
                    "Ospedale": {
                        "Nome Ospedale": "Villa Iris",
                        "Città": "Lunaria",
                        "Provincia": "FI",
                        "CAP": "50121",
                        "Reparto": "Endocrinologia"
                    }
                }
            },
            {
                "dati medico": {
                    "Anagrafica": {
                        "Email": "chiara.rossi@fintoemail.it",
                        "Nome": "Chiara",
                        "Cognome": "Rossi",
                        "Cellulare": "3336789012",
                        "Codice Fiscale": "RSSCHR85C52F205W",
                        "Ruolo": "Medico"
                    },
                    "Ospedale": {
                        "Nome Ospedale": "Santa Croce",
                        "Città": "Alberone",
                        "Provincia": "TO",
                        "CAP": "10128",
                        "Reparto": "Allergologia"
                    }
                }
            },
            {
                "dati medico": {
                    "Anagrafica": {
                        "Email": "filippo.greco@fintoemail.it",
                        "Nome": "Filippo",
                        "Cognome": "Greco",
                        "Cellulare": "3337890123",
                        "Codice Fiscale": "GRCFPP72A01H501L",
                        "Ruolo": "Medico"
                    },
                    "Ospedale": {
                        "Nome Ospedale": "Piccoli Angeli",
                        "Città": "Borgonovo",
                        "Provincia": "BG",
                        "CAP": "24100",
                        "Reparto": "Pediatria"
                    }
                }
            },
            {
                "dati medico": {
                    "Anagrafica": {
                        "Email": "giuseppe.esposito@fintoemail.it",
                        "Nome": "Giuseppe",
                        "Cognome": "Esposito",
                        "Cellulare": "3338901234",
                        "Codice Fiscale": "SPSGPP68D22H703S",
                        "Ruolo": "Medico"
                    },
                    "Ospedale": {
                        "Nome Ospedale": "Movimento e Salute",
                        "Città": "Castelverde",
                        "Provincia": "CE",
                        "CAP": "81100",
                        "Reparto": "Ortopedia"
                    }
                }
            },
            {
                "dati medico": {
                    "Anagrafica": {
                        "Email": "laura.moretti@fintoemail.it",
                        "Nome": "Laura",
                        "Cognome": "Moretti",
                        "Cellulare": "3339012345",
                        "Codice Fiscale": "MRTLRA82M45F205V",
                        "Ruolo": "Medico"
                    },
                    "Ospedale": {
                        "Nome Ospedale": "NeuroPoint",
                        "Città": "Lucidonia",
                        "Provincia": "GE",
                        "CAP": "16100",
                        "Reparto": "Neurologia"
                    }
                }
            },
            {
                "dati medico": {
                    "Anagrafica": {
                        "Email": "alessandro.conti@fintoemail.it",
                        "Nome": "Alessandro",
                        "Cognome": "Conti",
                        "Cellulare": "3330123456",
                        "Codice Fiscale": "CNTLSS77P10H703H",
                        "Ruolo": "Medico"
                    },
                    "Ospedale": {
                        "Nome Ospedale": "BioGen Lab",
                        "Città": "Genetica",
                        "Provincia": "BS",
                        "CAP": "25121",
                        "Reparto": "Genetica"
                    }
                }
            }
        ]

        # Mappatura: condizione → specializzazione
        query_specialization_map = {
            "cancro": "Oncologia",
            "ipertensione": "Cardiologia",
            "diabete": "Endocrinologia",
            "infarto": "Cardiologia",
            "asma": "Pneumologia",
            "COVID-19": "Pneumologia",
            "ictus": "Neurologia",  
            "sclerosi multipla": "Neurologia",
            "malattie rare": "Genetica", 
            "malattie renali": "Nefrologia",
            "cardiopatia": "Cardiologia",
            "HIV": "Infettivologia",
            "allergie": "Allergologia",
            "dolore cronico": "Ortopedia",
            "depressione": "Psichiatria",
            "medicina d'urgenza": "Medicina d'urgenza",
            "pediatria": "Pediatria"
        }

        articoli = []
                
        for q in query:
            specializzazione = query_specialization_map.get(q, "").lower()

            medico = next(
                (m for m in anagrafica_medici
                if m["dati medico"]["Ospedale"]["Reparto"].lower() == specializzazione),
                None
            )

            if not medico:
                self.logger.warning(f"Nessun medico trovato per la specializzazione '{specializzazione}' (query: '{q}'). Salto...")
                continue

            report_context = {
                "query": q,
                "medico": medico
            }

            articoli.append((report_context, q))

        with open('assets/project_dataset.jsonl', 'w', encoding='utf-8') as f:
            for report_context, query_text in articoli:
                medico_info = report_context["medico"]
                anagrafica_medico = medico_info["dati medico"]["Anagrafica"]
                self.logger.info("Procedo alla generazione del referto...")

                query_type, query_text, testo_simulato = self.generate_medical_report(report_context)
                testo_simulato_pulito = self.clean_text(re.sub('<[^<]+?>', '', testo_simulato))

                #estrazione e check sulla validità dell'anagrafica del paziente nel DB
                self.logger.info(f"Procedo all'estrazione dell'anagrafica del paziente ed alla verifica sulla presenza del suo FSE...")
                try:
                    anagrafica_paziente = self.anagrafica.extract_anagrafica(testo_simulato_pulito)
                    #Controllo sull'anagrafica estratta
                    self.logger.info(f"Anagrafica paziente estratta: {anagrafica_paziente}")

                    #check sull'anagrafica di base (codice fiscale, nominativo e recapito telefonico) del paziente
                    self.anagrafica.check_anagrafica(anagrafica_paziente)
                except Exception as e:
                    self.logger.warning(f"****Anagrafica del paziente non specificata, dovrai inserirla necessariamente in fase di convalida del documento****")
                
                file_id = self.compute_id(testo_simulato_pulito, self.function_mode)

                #Generazione dell'embedding della trascrizione per il RAG - prima procedo all'anonimizzazione del referto
                self.logger.info(f"Procedo all'update del nuovo documento nel RAG...")
                self.logger.info(f"Procedo al calcolo dell'embedding del testo...")
                report_text_RAG = self.anagrafica.anonimizza_referto(testo_simulato_pulito)

                #Controllo sul referto anonimizzato
                self.logger.info(f"Report anonimizzato: {report_text_RAG}")

                try:
                    #salvataggio della coppia audio + testo nel database 
                    self.logger.info(f"Procedo all'update della trascrizione e dell'audio nel DB...")

                    # Store transcription in the database
                    self.DB_manager.insert_transcription( 
                        audio_filename=None,
                        transcription=testo_simulato_pulito,
                        embedding_id=file_id, #id dell'embedding è utilizzato come id anche per le altre collezioni
                        language="it",
                        audio_filepath=None
                    )
                except Exception as e:
                    self.logger.warning(f"Errore nel salvataggio: {e}")

                #-------------------------------------------------------------------------------------------------------------------------

                #generazione del documento dalla LLM - do alla LLM il referto anonimizzato
                self.logger.debug(f"Procedo alla generazione del nuovo referto...")
                clinical_report = self.FSE_manager.FSE_manager(time.strftime("%Y-%m-%d %H:%M:%S"), 
                                                            report_text_RAG,
                                                            anagrafica_medico, 
                                                            anagrafica_paziente) 
                #salvataggio del documento nel DB
                self.logger.info(f"Aggiunta referto all'FSE del paziente...")
                #document_id = self.DB_manager.insert_clinical_report(file_id, clinical_report[0])

                if query_type == "report":
                    json_dump = {
                                    "referto_simulato": testo_simulato_pulito,
                                    "referto": json.dumps(clinical_report, ensure_ascii=False),
                                    "report_id": file_id,
                                    "validated": True,
                                }
                else:
                    json_dump = {
                                    "referto_simulato": testo_simulato_pulito,
                                    "scheda_ps": json.dumps(clinical_report, ensure_ascii=False),
                                    "report_id": file_id,
                                    "validated": True,
                                }

                f.write(json.dumps(json_dump, ensure_ascii=False) + '\n')

            #return document_id
    
    def compute_id(self, content: str, doc_type: str = "") -> str:
        return f"{doc_type}_{hashlib.md5(content.encode('utf-8')).hexdigest()}" 
    
    def generate_random_annotations(self):
        random_note = random.choice([
                "Ha una storia clinica di ipertensione.",
                "È un paziente allergico alla penicillina.",
                "Ha avuto accessi recenti al pronto soccorso per dolori toracici.",
                "È affetto anche da diabete mellito tipo 2.",
                "Ha avuto un incidente d'auto.",
                "È risultato positivo al COVID-19.",
                "È una visita di controllo.",
                "È una visita di routine.",
                "Ha riportato sintomi diversi nelle ultime visite.",
                "Ha una reazione avversa ai farmaci.",
                "È stato recentemente sottoposto a esami aggiuntivi."
        ]) #se necessario prova ad aggiungere altro

        name = random.choice(["a", "b", "c", "d", "e", "f", "g", "h", "i", "l", "m", "n", "o", "p", "q", "r", "s", "t", "u", "v", "z"])
        surname = random.choice(["a", "b", "c", "d", "e", "f", "g", "h", "i", "l", "m", "n", "o", "p", "q", "r", "s", "t", "u", "v", "z"])

        return random_note, name, surname
    
    def clean_text(self, text):
        text = re.sub(r'http[s]?://\S+', '', text)
        text = re.sub(r'PMCID?=\S+', '', text)
        text = re.sub(r'\d{4}[-]\d{2}[-]\d{2}', '', text)
        text = re.sub(r'\d{3,}', '', text)
        text = re.sub(r'\(.*?\)', '', text)
        text = re.sub(r'\\n', ' ', text)
        text = re.sub(r'[^\w\s.,;]', '', text)
        text = re.sub(r'(Springer|PMC|DOI|Creative Commons|license|Journal)', '', text)
        return re.sub(r'\s+', ' ', text).strip()
    
    def query_selection_report(self, context):

        random_note, name, surname = self.generate_random_annotations()

        query_referto = [
                      {
                            "role": "user",
                            "content": f"""Sei un medico specialista che ha appena esaminato un paziente. Basati sul testo specificato in seguito per simulare il dettato di un referto clinico realistico in stile conversazionale
                                            Menziona una diagnosi coerente con la patologia {context}, i sintomi riferiti, eventuali terapie, farmaci prescritti, anamnesi e piano di follow-up e utilizza {random_note} per rendere ancora più realistico il referto generato.
                                            Inserisci dati anagrafici e di contesto del paziente e del medico, generati in modo fittizio con nome che inizia per {name} e cognome per {surname}, ma coerenti (es. età compatibile con la patologia).  
                                            **Non inserire i dati del medico o infermiere in quanto il referto deve essere il frutto di un dettato in prima persona**
                                            **Inizia il testo direttamente con l'anamnesi del paziente senza aggiungere alcuna introduzione.**
                                            **Non sempre sono disponibili dati dell'anamnesi personale pregressa del paziente**
                                            **Non realizzare testi troppo lunghi, basati su una dinamica reale di visita di un paziente**"""
                      }
                    ]

        query_scheda = [
                        {
                            "role": "user",
                            "content": f"""Sei un infermiere che lavora in pronto soccorso (PS) e hai appena completato la valutazione e il trasporto di un paziente.
                                            Sulla base della patologia {context}, **simula una scheda di ammissione al pronto soccorso realistica, in forma di racconto dettagliato in stile conversazionale**, che includa tutte le informazioni necessarie per poter essere successivamente convertita in un file JSON strutturato come nell'esempio.

                                            **La descrizione deve includere chiaramente, anche sotto forma narrativa:**
                                            - **Motivo dell'intervento e sintomi riferiti**
                                            - **Contesto clinico coerente con il testo**
                                            - **Dinamica dell'accesso al PS** (modalità di chiamata, orari, luogo, trasporto in ambulanza, eventuali rifiuti o decessi)
                                            - **Trattamenti e interventi effettuati (es. ossigenoterapia, farmaci, monitoraggio)**
                                            - **Parametri vitali rilevati**
                                            - **Eventuale presenza di autorità**
                                            - **Annotazioni aggiuntive da parte del personale**
                                            - **Non sempre sono disponibili dati dell'anamnesi personale pregressa del paziente**
                                            - **Inserisci i dati appartenenti all'anagrafica con nome che inizia per {name} e cognome per {surname}, coerenti (es. età compatibile con la patologia). **
                                            - **Non inserire i dati del medico o infermiere in quanto il referto deve essere il frutto di un dettato in prima persona**
                                            -
                                            - **Utilizza elementi casuali e verosimili come {random_note} per rendere il racconto più realistico**

                                            **Il testo deve essere scritto come se fosse un dettato clinico, in prima persona, di un professionista del PS, da cui un medico possa facilmente compilare una scheda di accesso in JSON.**
                                            **Inizia il testo direttamente con l'anamnesi del paziente senza aggiungere alcuna introduzione.**

                                            Esempio di elementi da includere:
                                            - "Il paziente ha accusato dolore toracico acuto mentre si trovava a casa..."
                                            - "Chiamata effettuata alle ore 08:30, intervento in Via Roma 12..."
                                            - "All’arrivo sul posto, il paziente era vigile, collaborante, parametri nella norma..."
                                            - "Trasportato al PS in codice giallo con monitoraggio continuo..."

                                            Non omettere informazioni importanti e non usare abbreviazioni non mediche.
                                            **Non realizzare testi troppo lunghi, basati su una dinamica reale di visita di un paziente**"""
                        }
                    ]


        query_options = {
            "referto": query_referto,
            "scheda": query_scheda
        }
        query_type = random.choice(list(query_options.keys()))
        query = query_options[query_type]

        return query_type, query

    def generate_medical_report(self, context):
        temp = random.choice([0.2, 0.4, 0.6])
        query_type, query = self.query_selection_report(context)  # Passa il contesto

        clients = [self.client_story, self.client_story_1]

        for client in clients:
            try:
                response = client.chat.completions.create(
                    messages=query,
                    model=self.model,
                    temperature=temp,
                    max_tokens=800
                )
                content = response.choices[0].message.content.strip()
                query_text = query[0]["content"]
                return query_type, query_text, content
            except Exception as e:
                self.logger.warning(f"Errore nella generazione referto: {e}")
                continue

   

#------------------------------------- MAIN DI PROVA ----------------------------------------
# Entrypoint
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Gestione referti vocali e generazione FSE")

    args = parser.parse_args()

    anagrafica_medico={"name": "Anna", "surname": "Quercia", "CF": "QRCNNA44M64L225H", "specializzazione": "Pneumologa" }

    manager = PipelineManager(
        anagrafica_medico=anagrafica_medico,
        function_mode="Emergency"
    )

    manager.Pipeline_manager()


