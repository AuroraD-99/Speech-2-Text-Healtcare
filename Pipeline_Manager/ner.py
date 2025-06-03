from transformers import AutoTokenizer, AutoModelForTokenClassification, pipeline
import os
from dotenv import load_dotenv
import logging


class NER:
    def __init__(self, env_file="key.env"):
        # Load environment variables from .env file
        load_dotenv(env_file)
        
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger("Ner")
        
        self.ner_model_path = os.getenv("MODEL_PATH_NER")
        self.model_name = os.getenv("MODEL_NAME_NER")#"HUMADEX/italian-medical-ner"
        
        self.logger.info(f"Model path: {self.ner_model_path}")
        if not self.ner_model_path:
            raise ValueError("NER_MODEL_PATH non definito. Inseriscilo nel file .env o passalo come parametro.")

        if not os.path.exists(self.ner_model_path):
            os.makedirs(self.ner_model_path, exist_ok=True)
            self.logger.info(f"Creating directory for NER model at {self.ner_model_path}")
            tokenizer = AutoTokenizer.from_pretrained(self.model_name)
            model = AutoModelForTokenClassification.from_pretrained(self.model_name)
            tokenizer.save_pretrained(self.ner_model_path)
            model.save_pretrained(self.ner_model_path)
        else:
            self.logger.info(f"Using existing NER model at {self.ner_model_path}")


        if not self.ner_model_path:
            raise ValueError("NER model path must be provided or set in the environment variable 'NER_MODEL'.")

        # Initialize the tokenizer and model for NER
        self.ner_tokenizer = AutoTokenizer.from_pretrained(self.ner_model_path)
        self.ner_model = AutoModelForTokenClassification.from_pretrained(self.ner_model_path)
        self.ner_pipeline = pipeline("ner", 
                                     model=self.ner_model, 
                                     tokenizer=self.ner_tokenizer, 
                                     aggregation_strategy="average")
        
        
    def extract_medical_entities(self, text):
        """
        Estrae entità mediche dal testo utilizzando il modello NER.
        """
        
        if not text:
            raise ValueError("Input text cannot be empty.")

        # Esegui il riconoscimento delle entità
        ner_results = self.ner_pipeline(text)

        return [(entity['word'], entity['entity_group']) for entity in ner_results]

if __name__ == "__main__":
    # Example usage
    ner = NER()
    
    #Ottieni il testo da analizzare dal file referto_di_prova.txt
    """with open("referto_di_prova.txt", "r", encoding="utf-8") as file:
        text = file.read()"""
    
    text = "Sig.ra Francesca Nanni, 62 anni, residente a Roma. Motivo dellintervento e sintomi riferiti La paziente ha accusato un intenso dolore al petto, irradiato al braccio sinistro e accompagnato da nausea, mentre era a casa. Ha riferito anche di aver avuto episodi simili nei giorni precedenti, ma di entità minore. Contesto clinico La paziente è una donna con una storia familiare di malattie cardiovascolari; la madre è deceduta per un infarto del miocardio alletà di 70 anni. La paziente è ipertesa e in trattamento con farmaci antipertensivi. Dinamica dellaccesso al PS La chiamata è stata effettuata alle ore 1115 da un familiare. Lintervento è avvenuto in Via della Libertà, 25, a Roma. Il trasporto è stato effettuato in ambulanza in codice giallo, con monitoraggio continuo dellECG e della saturazione di ossigeno. Trattamenti e interventi effettuati Allarrivo sul posto, la paziente era vigile, collaborante, con parametri vitali nella norma, ma con evidente distress respiratorio. È stata sottoposta a ossigenoterapia con maschera facciale a 6 litriminuto e somministrazione di acido acetilsalicilico da mg per via endovenosa. La paziente ha ricevuto anche un bolo di morfina da 2 mg per il controllo del dolore. Parametri vitali rilevati Pressione arteriosa 80 mmHg Frequenza cardiaca 92 bpm Frequenza respiratoria 22 attimin Temperatura 36,8C Saturazione di ossigeno 88 con aria ambiente, migliorata al 94 con ossigenoterapia Eventuale presenza di autorità Non presente. Annotazioni aggiuntive da parte del personale La paziente ha riferito di aver assunto gli ultimi pasti regolarmente e di non avere particolari allergie note. La famiglia ha fornito una cartella clinica incompleta con precedenti episodi di angina. Esami diagnostici Allelettrocardiogramma eseguito in ambulanza è emerso un sopraslivellamento del tratto ST in derivazioni inferiori, suggestivo per infarto miocardico inferiore. Trasporto al PS La paziente è stata trasportata al Pronto Soccorso dellOspedale Umberto I di Roma, dove è stata accolta nel percorso Code Rosse. Notazioni È stata avviata la procedura per il trattamento trombolitico e la paziente è stata sottoposta a ulteriori indagini diagnostice, tra cui ecocardiogramma e esami del sangue per marker cardiaci. Dettagli clinici aggiuntivi La paziente è stata mantenuta sotto stretto monitoraggio per tutta la durata del trasporto e in Pronto Soccorso, con controlli continui dei parametri vitali e dellECG. Stato alla fine del trasporto La paziente è arrivata al Pronto Soccorso in buone condizioni generali, ma con persistente dolore toracico. Elementi JSON strutturati json nome Francesca, cognome Nanni, eta 62, residenza Roma, motivo_intervento Dolore toracico acuto, sintomi_riferiti Dolore al petto irradiato al braccio sinistro, Nausea, storia_familiare Malattie cardiovascolari."
    
    entities = ner.extract_medical_entities(text)
    print(entities)