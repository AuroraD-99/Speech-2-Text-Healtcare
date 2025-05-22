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

class Anagrafica:
    def __init__(self):
        logging.basicConfig(level=logging.INFO)
        #self.logger = logging.getLogger("Anagrafica")

        #inizializzazione del database
        self.DB_manager = DB()

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

        patterns = {
            "codice_fiscale": r"\b[A-Z]{6}[0-9]{2}[A-Z][0-9]{2}[A-Z][0-9]{3}[A-Z]\b",
            "nominativo": {
                "nome": r"\b[Nn]ome\s*[:\-]?\s*([A-Z][a-z]+)",
                "cognome": r"\b[Cc]ognome\s*[:\-]?\s*([A-Z][a-z]+)",
                "completo": r"\b([A-Z][a-z]+)\s+([A-Z][a-z]+)\b",  # fallback
            },
            "sesso": r"\b[Ss]esso\s*[:\-]?\s*(Maschio|Femmina|M|F)\b",
            "data_nascita": r"\b[Nn]at[oa]?\s*(?:il)?\s*(\d{2}[/-]\d{2}[/-]\d{4})\b",
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

        return extracted

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

        #Determinazione del sesso se mancante
        if not anagrafica.get("sesso") or anagrafica["sesso"] in ["", "N/A"]:
            nome = nominativo.get("nome")
            if nome and nome != "N/A":
                if nome[-1].lower() == "a":
                    anagrafica["sesso"] = "F"
                elif nome[-1].lower() in ["o", "e"]:
                    anagrafica["sesso"] = "M"
                else:
                    anagrafica["sesso"] = "N/A"


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

        # CERCA RECORD SIMILI IN MONGODB
        all_reports = list(self.reports_collection.find({"dati paziente": {"$exists": True}}))
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

