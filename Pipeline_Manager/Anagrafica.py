import sys
import os
import re
import time
from datetime import datetime
import logging    
from datetime import datetime
from difflib import SequenceMatcher

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from Database.mongodb import DB
from NER.ner import NER

#TODO: INTEGRARE CON model = GLiNER.from_pretrained("DeepMount00/universal_ner_ita") PER AVERE UNA PRECISIONE MAGGIORE

class Anagrafica:
    def __init__(self, ner):
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger("Anagrafica")

        #inizializzazione del database
        self.DB_manager = DB()
        self.NER = ner

    def anonimizza_referto(self, testo):

        patterns = {
            r"\b[A-Z]{6}[0-9]{2}[A-Z][0-9]{2}[A-Z][0-9]{3}[A-Z]\b": "[CODICE_FISCALE]",
            r"\bNome\s*[:\-]?\s*[A-Z][a-z]+": "[NOME]",
            r"\bCognome\s*[:\-]?\s*[A-Z][a-z]+": "[COGNOME]",
            r"\b[A-Z][a-z]+\s[A-Z][a-z]+\b": "[NOME_COMPLETO]",  # es. "Mario Rossi"
            r"\b\d{2}[/-]\d{2}[/-]\d{2,4}\b": "[DATA]",
            r"\b\d{1,2}:\d{2}\b": "[ORA]",
            r"\b\d{11}\b": "[NUM_TESSERA_SANITARIA]",
            r"\b(?:Via|Viale|Piazza|Corso)\s+[A-Z][a-z\s']+": "[INDIRIZZO]",
            r"\b3\d{2}[-\s]?\d{6,7}\b": "[TELEFONO]",
        }

        for pattern, replacement in patterns.items():
            testo = re.sub(pattern, replacement, testo)
        return testo

    def extract_anagrafica(self, text):
        # Entità mediche e anagrafiche da cercare col NER
        ner_labels = [
            "nome", "cognome", "data di nascita", "luogo di nascita", 
            "indirizzo", "età", "paziente", "residenza", "medico", 
            "sesso", "codice fiscale", "recapito telefonico"
        ]

        ner_entities = self.NER.ner_model.predict_entities(text, ner_labels)

        extracted = {
            "codice_fiscale": "N/A",
            "sesso": "N/A",
            "data_nascita": "N/A",
            "età": "N/A",
            "luogo_nascita": {
                "città": "N/A",
                "provincia": "N/A"
            },
            "residenza": {
                "città": "N/A",
                "provincia": "N/A",
                "indirizzo": "N/A"
            },
            "recapito_telefonico": "N/A",
            "dati_dichiarati_da": "N/A",
            "nominativo": {
                "nome": "N/A",
                "cognome": "N/A"
            }
        }

        for ent in ner_entities:
            label = ent["label"].lower()
            value = ent["text"]

            if label in ["nome", "cognome"]:
                extracted["nominativo"][label] = value
            elif label == "data di nascita":
                extracted["data_nascita"] = value
            elif label == "età":
                extracted["età"] = value
            elif label == "indirizzo":
                extracted["residenza"]["indirizzo"] = value
            elif label == "residenza":
                extracted["residenza"]["città"] = value
            elif label == "luogo di nascita":
                extracted["luogo_nascita"]["città"] = value
            elif label == "recapito telefonico":
                extracted["recapito_telefonico"] = value
            elif label == "sesso":
                extracted["sesso"] = value
            elif label == "codice fiscale":
                extracted["codice_fiscale"] = value
            elif label == "paziente":  # fallback per nome completo
                if " " in value:
                    nome, cognome = value.split(" ", 1)
                    extracted["nominativo"]["nome"] = nome
                    extracted["nominativo"]["cognome"] = cognome

        # Fallback regex se NER ha lasciato valori "N/A"
        for key, pattern in self._regex_patterns().items():
            if isinstance(pattern, dict):
                for subkey, subpattern in pattern.items():
                    if extracted[key][subkey] == "N/A":
                        match = re.search(subpattern, text)
                        if match:
                            extracted[key][subkey] = match.group(1).strip()
            else:
                if extracted.get(key, "N/A") == "N/A":
                    match = re.search(pattern, text)
                    if match:
                        extracted[key] = match.group(1).strip()


        return extracted
    
    def _regex_patterns(self):
        return {
            "codice_fiscale": r"\b[A-Z]{6}[0-9]{2}[A-Z][0-9]{2}[A-Z][0-9]{3}[A-Z]\b",
            "nominativo": {
                "nome": r"\b[Nn]ome\s*[:\-]?\s*([A-Z][a-z]+)",
                "cognome": r"\b[Cc]ognome\s*[:\-]?\s*([A-Z][a-z]+)",
            },
            "sesso": r"\b[Ss]esso\s*[:\-]?\s*(Maschio|Femmina|M|F)\b",
            "data_nascita": r"\b[Nn]at[oa]?\s*(?:il)?\s*(\d{2}[/-]\d{2}[/-]\d{4})\b",
            "età": r"\b[ÉE]tà\s*[:\-]?\s*(\d{1,3})\b",
            "luogo_nascita": {
                "città": r"[Nn]at[oa]?\s*(?:a|in)?\s*([A-Z][a-z\s']+)",
                "provincia": r"\(([A-Z]{2})\)"
            },
            "residenza": {
                "città": r"[Rr]esidenza\s*(?:in)?\s*([A-Z][a-z\s']+)",
                "provincia": r"\(([A-Z]{2})\)",
                "indirizzo": r"[Ii]ndirizzo\s*[:\-]?\s*((?:Via|Piazza|Corso)\s+[A-Z][a-z\s']+)"
            },
            "recapito_telefonico": r"\b(3\d{2}[-\s]?\d{6,7})\b",
            "dati_dichiarati_da": r"[Dd]ichiarat[oa]\s+da[:\s]*([A-Z][a-z]+\s[A-Z][a-z]+)",
        }



    """def extract_anagrafica(self, text):

        patterns = {
            "codice_fiscale": r"\b[A-Z]{6}[0-9]{2}[A-Z][0-9]{2}[A-Z][0-9]{3}[A-Z]\b",
            "nominativo": {
                "nome": r"\b[Nn]ome\s*[:\-]?\s*([A-Z][a-z]+)",
                "cognome": r"\b[Cc]ognome\s*[:\-]?\s*([A-Z][a-z]+)",
            },
            "sesso": r"\b[Ss]esso\s*[:\-]?\s*(Maschio|Femmina|M|F)\b",
            "data_nascita": r"\b[Nn]at[oa]?\s*(?:il)?\s*(\d{2}[/-]\d{2}[/-]\d{4})\b",
            "età": r"\b[ÉE]tà\s*[:\-]?\s*(\d{1,3})\b",
            "luogo_nascita": {
                "città": r"[Nn]at[oa]?\s*(?:a|in)?\s*([A-Z][a-z\s']+)",
                "provincia": r"\(([A-Z]{2})\)"
            },
            "residenza": {
                "città": r"[Rr]esidenza\s*(?:in)?\s*([A-Z][a-z\s']+)",
                "provincia": r"\(([A-Z]{2})\)",
                "indirizzo": r"[Ii]ndirizzo\s*[:\-]?\s*((?:Via|Piazza|Corso)\s+[A-Z][a-z\s']+)"
            },
            "recapito_telefonico": r"\b(3\d{2}[-\s]?\d{6,7})\b",
            "dati_dichiarati_da": r"[Dd]ichiarat[oa]\s+da[:\s]*([A-Z][a-z]+\s[A-Z][a-z]+)",
        }

        extracted = {}

        for key, pattern in patterns.items():
            if isinstance(pattern, dict):
                extracted[key] = {}
                for subkey, subpattern in pattern.items():
                    if subpattern:
                        match = re.search(subpattern, text)
                        extracted[key][subkey] = match.group(1).strip() if match else "N/A"
                    else:
                        extracted[key][subkey] = "N/A"
            else:
                match = re.search(pattern, text)
                extracted[key] = match.group(1).strip() if match else "N/A"

        # Fallback: usa "nominativo.completo" se nome/cognome separati non trovati
        if extracted["nominativo"]["nome"] == "N/A" or extracted["nominativo"]["cognome"] == "N/A":
            match = re.search(patterns["nominativo"]["completo"], text)
            if match:
                extracted["nominativo"]["nome"] = match.group(1)
                extracted["nominativo"]["cognome"] = match.group(2)

        return extracted"""

        #DATI CHE POSSONO ESSERE AGGIUNTI IN SEGUITO:
            #chi ha dichiarato i dati può essere aggiunto anche in seguito
            #il sesso se mancante può essere dedotto dal nome (tanto il medico può cambiarlo)
            #è ammesso (per il momento) che non siano presente data e luogo di nascita
            #se ci sono dati mancanti e altri referti per la stessa persona si possono recuperare i dati da li
            #taccuino personale assistito e tessera portatore impianto possono essere sia dati che recuperati degli altri referti

    def check_anagrafica(self, anagrafica):
        #devi controllare che siano presenti almeno il codice fiscale, nominativo e recapito telefonico; -> OK      
        missing_fields = []

        if not anagrafica.get("codice_fiscale") or anagrafica["codice_fiscale"] == "N/A":
            missing_fields.append("codice_fiscale")

        if not anagrafica.get("recapito_telefonico") or anagrafica["recapito_telefonico"] == "N/A":
            missing_fields.append("recapito_telefonico")

        nominativo = anagrafica.get("nominativo", {})
        if not nominativo.get("nome") or not nominativo.get("cognome") or \
        nominativo["nome"] == "N/A" or nominativo["cognome"] == "N/A":
            missing_fields.append("nominativo (nome/cognome)")

        # Calcolo età se mancante e ho la data di nascita
        if not anagrafica.get("età") or anagrafica["età"] in ["", "N/A"]:
            data_nascita = anagrafica.get("data_nascita")
            if data_nascita and data_nascita != "N/A":
                try:
                    giorno, mese, anno = map(int, re.split(r"[/-]", data_nascita))
                    nascita = datetime(anno, mese, giorno)
                    oggi = datetime.today()
                    età = oggi.year - nascita.year - ((oggi.month, oggi.day) < (nascita.month, nascita.day))
                    anagrafica["età"] = str(età)
                except Exception as e:
                    self.logger.warning(f"Impossibile calcolare l'età da data di nascita '{data_nascita}': {e}")
                    anagrafica["età"] = "N/A"

        return True
    
    #DEVI ASSICURARTI CHE L'ANAGRAFICA SIA PRESENTE AL COMPLETO (TUTTI I CAMPI) IN FASE DI VALIDAZIONE DEL REFERTO MEDIANTE CHIAMATA API
    def validate_anagrafica_with_suggestions(self, anagrafica: dict) -> dict: #VA MODIFICATA
        #Valida l'anagrafica di un paziente, completa i campi mancanti con:
        #- euristiche (es. determinazione sesso da nome)
        #- suggerimenti basati su record simili in MongoDB

        missing_fields = []
        suggested_from_db = {}

        # Verifica CF
        if not anagrafica.get("codice_fiscale") or anagrafica["codice_fiscale"] == "N/A":
            missing_fields.append("codice_fiscale")

        # Verifica recapito
        if not anagrafica.get("recapito_telefonico") or anagrafica["recapito_telefonico"] == "N/A":
            missing_fields.append("recapito_telefonico")

        # Verifica nominativo
        nominativo = anagrafica.get("nominativo", {})
        if not nominativo.get("nome") or not nominativo.get("cognome") \
            or nominativo.get("nome") == "N/A" or nominativo.get("cognome") == "N/A":
            missing_fields.append("nominativo (nome/cognome)")  

        # CALCOLO ETÀ SE POSSIBILE
        if not anagrafica.get("età") or anagrafica["età"] in ["", "N/A"]:
            data_nascita = anagrafica.get("data_nascita")
            if data_nascita and data_nascita != "N/A":
                try:
                    giorno, mese, anno = map(int, re.split(r"[/-]", data_nascita))
                    nascita = datetime(anno, mese, giorno)
                    oggi = datetime.today()
                    età = oggi.year - nascita.year - ((oggi.month, oggi.day) < (nascita.month, nascita.day))
                    anagrafica["età"] = str(età)
                except Exception as e:
                    self.logger.warning(f"Errore calcolo età da {data_nascita}: {e}")
                    anagrafica["età"] = "N/A"

        # CERCA RECORD SIMILI IN MONGODB -> si potrebbe anche filtrare in base al medico (se la visita è di routine e non emergency)
        #vanno aggiunte al database le funzioni find_anagrafica_best_match_by_medico CF e finf_anagrafica_best_match
        all_reports = list(self.DB_manager.reports_collection.find({"dati paziente": {"$exists": True}}))
        max_match_score = 0
        best_match_anagrafica = None

        for report in all_reports:
            candidato = report.get("dati paziente", {})
            if not candidato:
                continue

            # Confronto parziale su CF, nome e cognome
            score = 0
            if candidato.get("codice_fiscale") == anagrafica.get("codice_fiscale"):
                score += 3

            nome_cand = candidato.get("nominativo", {}).get("nome", "").lower()
            cognome_cand = candidato.get("nominativo", {}).get("cognome", "").lower()
            nome = nominativo.get("nome", "").lower()
            cognome = nominativo.get("cognome", "").lower()

            score += SequenceMatcher(None, nome, nome_cand).ratio()
            score += SequenceMatcher(None, cognome, cognome_cand).ratio()

            if score > max_match_score and score > 2.5:
                max_match_score = score
                best_match_anagrafica = candidato

        # SUGGERIMENTI DAL DB SE RECORD SIMILE TROVATO
        if best_match_anagrafica:
            for field in ["sesso", "data_nascita", "età", "recapito_telefonico"]:
                if anagrafica.get(field) in [None, "", "N/A"] and best_match_anagrafica.get(field):
                    suggested_from_db[field] = best_match_anagrafica[field]
                    anagrafica[field] = best_match_anagrafica[field]

            for campo in ["nome", "cognome"]:
                if nominativo.get(campo) in [None, "", "N/A"] and \
                best_match_anagrafica.get("nominativo", {}).get(campo):
                    suggested_from_db[f"nominativo.{campo}"] = best_match_anagrafica["nominativo"][campo]
                    anagrafica["nominativo"][campo] = best_match_anagrafica["nominativo"][campo]

        valid = not missing_fields

        return {
            "anagrafica": anagrafica,
            "valid": valid,
            "missing_fields": missing_fields,
            "suggested_from_db": suggested_from_db
        }

if __name__ == "__main__":
    testo = "Sig.ra Francesca Nanni, 62 anni, residente a Roma. Motivo dellintervento e sintomi riferiti La paziente ha accusato un intenso dolore al petto, irradiato al braccio sinistro e accompagnato da nausea, mentre era a casa. Ha riferito anche di aver avuto episodi simili nei giorni precedenti, ma di entità minore. Contesto clinico La paziente è una donna con una storia familiare di malattie cardiovascolari; la madre è deceduta per un infarto del miocardio alletà di 70 anni. La paziente è ipertesa e in trattamento con farmaci antipertensivi. Dinamica dellaccesso al PS La chiamata è stata effettuata alle ore 1115 da un familiare. Lintervento è avvenuto in Via della Libertà, 25, a Roma. Il trasporto è stato effettuato in ambulanza in codice giallo, con monitoraggio continuo dellECG e della saturazione di ossigeno. Trattamenti e interventi effettuati Allarrivo sul posto, la paziente era vigile, collaborante, con parametri vitali nella norma, ma con evidente distress respiratorio. È stata sottoposta a ossigenoterapia con maschera facciale a 6 litriminuto e somministrazione di acido acetilsalicilico da mg per via endovenosa. La paziente ha ricevuto anche un bolo di morfina da 2 mg per il controllo del dolore. Parametri vitali rilevati Pressione arteriosa 80 mmHg Frequenza cardiaca 92 bpm Frequenza respiratoria 22 attimin Temperatura 36,8C Saturazione di ossigeno 88 con aria ambiente, migliorata al 94 con ossigenoterapia Eventuale presenza di autorità Non presente. Annotazioni aggiuntive da parte del personale La paziente ha riferito di aver assunto gli ultimi pasti regolarmente e di non avere particolari allergie note. La famiglia ha fornito una cartella clinica incompleta con precedenti episodi di angina. Esami diagnostici Allelettrocardiogramma eseguito in ambulanza è emerso un sopraslivellamento del tratto ST in derivazioni inferiori, suggestivo per infarto miocardico inferiore. Trasporto al PS La paziente è stata trasportata al Pronto Soccorso dellOspedale Umberto I di Roma, dove è stata accolta nel percorso Code Rosse. Notazioni È stata avviata la procedura per il trattamento trombolitico e la paziente è stata sottoposta a ulteriori indagini diagnostice, tra cui ecocardiogramma e esami del sangue per marker cardiaci. Dettagli clinici aggiuntivi La paziente è stata mantenuta sotto stretto monitoraggio per tutta la durata del trasporto e in Pronto Soccorso, con controlli continui dei parametri vitali e dellECG. Stato alla fine del trasporto La paziente è arrivata al Pronto Soccorso in buone condizioni generali, ma con persistente dolore toracico. Elementi JSON strutturati json nome Francesca, cognome Nanni, eta 62, residenza Roma, motivo_intervento Dolore toracico acuto, sintomi_riferiti Dolore al petto irradiato al braccio sinistro, Nausea, storia_familiare Malattie cardiovascolari."
    
    ana = Anagrafica()
    
    estratti = ana.extract_anagrafica(testo)
    print("Dati estratti:\n", estratti)

    validazione = ana.validate_anagrafica_with_suggestions(estratti)
    print("\nRisultato validazione:\n", validazione)

