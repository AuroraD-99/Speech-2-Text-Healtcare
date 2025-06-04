from transformers import AutoTokenizer, AutoModelForTokenClassification, pipeline
import os
from dotenv import load_dotenv
import logging

import os
import logging
from dotenv import load_dotenv
from transformers import AutoTokenizer, AutoModelForTokenClassification, pipeline

import spacy
from gliner import GLiNER


class NER:
    def __init__(self, env_file: str = "key.env"):
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger("NER")

        # Caricamento delle variabili ambiente
        load_dotenv(env_file)
        self.ner_model_path = os.getenv("MODEL_PATH_NER")
        self.model_name = os.getenv("MODEL_NAME_NER", "DeepMount00/universal_ner_ita") #provare anche questo DeepMount00/universal_ner_ita

        self.spacy_nlp = spacy.load("it_core_news_sm")

        # Validazione del path e del nome modello
        if not self.ner_model_path:
            self.logger.warning(f"La variabile d'ambiente MODEL_PATH_NER è mancante.")

        # Setup o download del modello
        self.ner_model = GLiNER.from_pretrained(self.model_name)

    def split_text(self, text, max_length=400):
        """
        Suddivide il testo in blocchi di frasi con massimo `max_length` caratteri.
        """
        doc = self.spacy_nlp(text)
        sentences = [sent.text.strip() for sent in doc.sents]

        blocks = []
        current_block = ""
        for sentence in sentences:
            if len(current_block) + len(sentence) <= max_length:
                current_block += " " + sentence
            else:
                blocks.append(current_block.strip())
                current_block = sentence
        if current_block:
            blocks.append(current_block.strip())

        return blocks

    def extract_medical_entities(self, text: str, confidence_threshold: float = 0.6):
        """
        Estrae entità mediche dal testo fornito, suddividendolo in blocchi se necessario.
        Ritorna una lista di tuple (entità, label) solo per quelle con score >= soglia.

        :param text: Testo da cui estrarre le entità.
        :param confidence_threshold: Soglia minima di confidenza per accettare un'entità.
        :return: Lista di tuple (entità, categoria)
        """
        if not text.strip():
            raise ValueError("Il testo fornito è vuoto.")

        """labels = [
            "data visita", "diagnosi", "indirizzo", "prescrizione", "durata trattamento", "farmaco"
        ]"""

        labels = [
                        # Chiamata
                        "data_chiamata",
                        "ora_chiamata",
                        "ora_partenza",
                        "ora_sul_posto",
                        "ora_partenza_posto",
                        "ora_arrivo_ps",
                        "ora_libero_operativo",
                        "luogo_intervento",
                        "condizione_riferita",

                        # Ambulanza
                        "ambulanza_cri",
                        "ambulanza_sel",

                        # Equipaggio
                        "equipaggio_autista",
                        "equipaggio_socc1",
                        "equipaggio_socc2",
                        "equipaggio_ip",
                        "equipaggio_medico",

                        # Causa trasporto non effettuato
                        "causa_trasporto_non_effettuato",

                        # Autorità
                        "autorita_descrizione",
                        "autorita_referto",

                        # Decesso
                        "ora_decesso",
                        "firma_decesso",

                        # Rifiuto
                        "firma_rifiuto",

                        # Rilevazioni – Parametri
                        "coscienza",
                        "cute",
                        "respiro",
                        "saturazione_spo2",
                        "frequenza_cardiaca_bpm",
                        "pressione_arteriosa_mmhg",
                        "glicemia_mgdl",
                        "temperatura_c",

                        # Glasgow Coma Scale
                        "glasgow_occhi",
                        "glasgow_verbale",
                        "glasgow_motoria",

                        # Altre rilevazioni
                        "pupille",
                        "lesioni_riscontrate",

                        # Provvedimenti
                        "provvedimenti_respiro",
                        "provvedimenti_circolo",
                        "provvedimenti_immobilizzazione",
                        "provvedimenti_altro",
                        "provvedimenti_farmaci",

                        # Annotazioni
                        "annotazioni",

                        # Intestazione
                        "data_visita",
                        "ora_visita",
                        "ambulatorio",
                        "medico_visita",

                        # Visita e anamnesi
                        "motivo_visita",
                        "anamnesi_personale",
                        "anamnesi_familiare",
                        "evento_attuale",

                        # Referto
                        "esame_obiettivo",
                        "esami_eseguiti",
                        "diagnosi",
                        "terapia",
                        "follow_up",

                        # Firma e data
                        "firma_medico",
                        "data_redazione"
                    ]


        blocks = self.split_text(text)
        extracted_entities = []

        for i, block in enumerate(blocks):
            try:
                entities = self.ner_model.predict_entities(block, labels)
                if entities:
                    for ent in entities:
                        if ent.get("score", 0) >= confidence_threshold:
                            extracted_entities.append((ent["text"]))
            except Exception as e:
                self.logger.error(f"Errore NER nel blocco {i}: {e}")

        if not extracted_entities:
            self.logger.info("Nessuna entità rilevata con score sufficiente.")

        return extracted_entities


if __name__ == "__main__":
    # Example usage
    ner = NER()
    
    #Ottieni il testo da analizzare dal file referto_di_prova.txt
    """with open("referto_di_prova.txt", "r", encoding="utf-8") as file:
        text = file.read()"""
    
    text = "Sig.ra Francesca Nanni, 62 anni, residente a Roma. Motivo dellintervento e sintomi riferiti La paziente ha accusato un intenso dolore al petto, irradiato al braccio sinistro e accompagnato da nausea, mentre era a casa. Ha riferito anche di aver avuto episodi simili nei giorni precedenti, ma di entità minore. Contesto clinico La paziente è una donna con una storia familiare di malattie cardiovascolari; la madre è deceduta per un infarto del miocardio alletà di 70 anni. La paziente è ipertesa e in trattamento con farmaci antipertensivi. Dinamica dellaccesso al PS La chiamata è stata effettuata alle ore 1115 da un familiare. Lintervento è avvenuto in Via della Libertà, 25, a Roma. Il trasporto è stato effettuato in ambulanza in codice giallo, con monitoraggio continuo dellECG e della saturazione di ossigeno. Trattamenti e interventi effettuati Allarrivo sul posto, la paziente era vigile, collaborante, con parametri vitali nella norma, ma con evidente distress respiratorio. È stata sottoposta a ossigenoterapia con maschera facciale a 6 litriminuto e somministrazione di acido acetilsalicilico da mg per via endovenosa. La paziente ha ricevuto anche un bolo di morfina da 2 mg per il controllo del dolore. Parametri vitali rilevati Pressione arteriosa 80 mmHg Frequenza cardiaca 92 bpm Frequenza respiratoria 22 attimin Temperatura 36,8C Saturazione di ossigeno 88 con aria ambiente, migliorata al 94 con ossigenoterapia Eventuale presenza di autorità Non presente. Annotazioni aggiuntive da parte del personale La paziente ha riferito di aver assunto gli ultimi pasti regolarmente e di non avere particolari allergie note. La famiglia ha fornito una cartella clinica incompleta con precedenti episodi di angina. Esami diagnostici Allelettrocardiogramma eseguito in ambulanza è emerso un sopraslivellamento del tratto ST in derivazioni inferiori, suggestivo per infarto miocardico inferiore. Trasporto al PS La paziente è stata trasportata al Pronto Soccorso dellOspedale Umberto I di Roma, dove è stata accolta nel percorso Code Rosse. Notazioni È stata avviata la procedura per il trattamento trombolitico e la paziente è stata sottoposta a ulteriori indagini diagnostice, tra cui ecocardiogramma e esami del sangue per marker cardiaci. Dettagli clinici aggiuntivi La paziente è stata mantenuta sotto stretto monitoraggio per tutta la durata del trasporto e in Pronto Soccorso, con controlli continui dei parametri vitali e dellECG. Stato alla fine del trasporto La paziente è arrivata al Pronto Soccorso in buone condizioni generali, ma con persistente dolore toracico. Elementi JSON strutturati json nome Francesca, cognome Nanni, eta 62, residenza Roma, motivo_intervento Dolore toracico acuto, sintomi_riferiti Dolore al petto irradiato al braccio sinistro, Nausea, storia_familiare Malattie cardiovascolari."
    
    entities = ner.extract_medical_entities(text)
    print("\n🔍 Entità estratte:")
    for ent in entities:
        print(f"- {ent}")