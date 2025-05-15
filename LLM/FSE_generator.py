import os
import sys
import json
import transformers
import torch

from datetime import datetime
from dotenv import load_dotenv
from transformers import AutoTokenizer, AutoModelForCausalLM, pipeline
from log import Logger

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

class LLMWrapper:
    def __init__(self, model):
        self.logger = Logger(self.__class__.__name__).get_logger()

        #Gestione del modello
        self.model = model
        self.max_new_tokens = 1024

    def generator(self, prompt, **kwargs):
        return self.model(prompt, **kwargs) if callable(self.model) else self.model.generate(prompt, **kwargs)

    #--------------------------------- FUNZIONI PER LA GENERAZIONE DELLA SCHEDA PS ----------------------------------------

    def __generate_prompt_scheda(self):
        esempio_scheda = {
            "Chiamata": {
                "data": ["06.05.2025"],
                "H chiamata": "08:30",
                "H partenza": "08:35",
                "H sul posto": "08:45",
                "H partenza posto": "09:15",
                "H in PS": "09:45",
                "H libero e operativo": "10:00",
                "luogo intervento": "Via Roma 12, Milano",
                "condizione riferita": "Dolore toracico",
                "recapito telefonico": "3331234567"
            },
            "Ambulanza": {
                "CRI": "MI102",
                "Sel": "SEL3"
            },
            "Equipaggio": {
                "Aut.": "Mario Rossi",
                "Socc1": "Luca Bianchi",
                "Socc2": "Anna Verdi",
                "IP": "N/A",
                "Medico": "Dr. Paolo Neri"
            },
            "Causa trasporto non effettuato": ["Non necessaria"],
            "Attivazioni/Autorità presenti": {
                "descrizione": "Polizia Locale",
                "referto": "Intervento per incidente stradale"
            },
            "Dati anagrafica paziente": {
                "Cognome Nome": "Giulia Verdi",
                "sesso": "F",
                "nato il": "1979-08-12",
                "a": "Milano",
                "Prov_nascita": "MI",
                "Residente a": "Milano",
                "Prov_residenza": "MI",
                "Via": "Via Dante",
                "N": "45",
                "Telefono": "3391122334",
                "Dati dichiarati da": "Paziente"
            },
            "Decesso": {"Ora decesso": "", "Firma": ""},
            "Rifiuto (firma dell'interessato)": {"Firma": ""},
            "Rilevazioni": {
                "Parametri": {
                    "Coscienza": "vigile",
                    "Cute": "normale",
                    "Respiro": "regolare",
                    "Sp02": "98%",
                    "FC bpm": "72",
                    "PA mmHg": "120/80",
                    "Glic, Mg/dl": "95",
                    "Temp. C°": "36.7"
                },
                "Glasgow Coma Scale": {
                    "Apertura occhi": "Spontanea",
                    "Risposta verbale": "Orientata",
                    "Risposta motoria": "Obbedisce ai comandi"
                },
                "Pupille": "isocoriche",
                "Lesioni riscontrate": "nessuna"
            },
            "Provvedimenti": {
                "Respiro": "Ossigenoterapia",
                "Circolo": "Monitoraggio",
                "Immobilizzazione": "N/A",
                "Altro": "ECG in loco",
                "Infusioni/Farmaci": "Fiale di Paracetamolo"
            },
            "Annotazioni": ["Paziente collaborante, nessuna difficoltà durante il trasporto"]
        }

        return (
            "Sei un medico. Compila la seguente scheda di ammissione PS in italiano in formato JSON. "
            "Usa solo i dati presenti nel testo. Se mancano, inserisci 'N/A'. Rispondi solo con JSON.\n\n"
            f"{json.dumps(esempio_scheda, ensure_ascii=False, indent=2)}"
        )

    def generate_scheda_from_report(self, referto_ps, report_with_context): #DA CONTROLLARE
        prompt = self.__generate_prompt_scheda()
        full_prompt = f"{prompt}\n\nReferto da analizzare:\n{referto_ps}\n\nPuoi fare riferimento ai seguenti esempi\n{report_with_context}"
        try:
            result = self.generator(full_prompt, max_new_tokens=self.max_new_tokens)
            return result #[0]["generated_text"].replace(full_prompt, "").strip()
        except Exception as e:
            self.logger.error(f"Errore nella generazione scheda: {e}")
            return "{}"
        
    def __generate_prompt_report(self): #VEDERE SE BISOGNA CAMBIARLO
        return (
                    "Sei un assistente medico specializzato nella redazione di referti clinici formali."
                    "Il tuo compito è analizzare un testo discorsivo fornito in seguito, comprendere le informazioni cliniche essenziali, e riscriverle in forma di referto professionale, chiaro e strutturato."
                    "Compila il referto clinico in italiano formato JSON. Usa solo i dati presenti nel testo.\n\n"
                ) 
    
        """    🧾 Intestazione / Identificativi
        Nome e cognome del paziente

        Data di nascita

        Codice fiscale / ID paziente

        Numero del referto / identificativo visita

        Data e ora della visita

        Reparto / ambulatorio di riferimento

        Nome e qualifica del medico specialista

        🩺 Contenuto clinico
        Motivo della visita (o del ricovero)

        Es. “Controllo post-operatorio”, “Dolore toracico acuto”, “Follow-up oncologico”

        Anamnesi

        Personale e familiare (patologie pregresse, farmaci, allergie, abitudini)

        Anamnesi recente / evento attuale

        Esame obiettivo

        Risultati dell’osservazione clinica diretta (es. PA, FC, stato neurologico, esame addominale…)

        Esami eseguiti / indagini

        Analisi di laboratorio, imaging, ECG, ecc. con risultati sintetici o allegati

        Diagnosi / sospetto diagnostico

        Formulazione clinica o differenziale

        Terapia consigliata / eseguita

        Farmaci, dosaggi, durata, interventi

        Indicazioni e follow-up

        Controlli successivi, esami da effettuare, invio ad altri specialisti

        🖋️ Chiusura
        Firma del medico (digitale o manoscritta)

        Timbro del medico o struttura sanitaria

        Data di redazione del referto"""
                
    def generate_clinical_report(self, referto, report_with_context): #DA CONTROLLARE
        prompt = self.__generate_prompt_report() 
        full_prompt = f"{prompt}\n\nReferto da analizzare:\n{referto}\n\nPuoi fare riferimento ai seguenti esempi\n{report_with_context}"
        try:
            result = self.generator(full_prompt, max_new_tokens=self.max_new_tokens)
            return result #[0]["generated_text"].replace(full_prompt, "").strip()
        except Exception as e:
            self.logger.error(f"Errore nella generazione referto: {e}")
            return "{}"

    def check_json_format(self, document): #FUNZIONE PER IL CHECK SUL FORMATO DEL FILE JSON - potrebbe essere inutile o dover essere cambiata
        try:
            if isinstance(document, str):
                json.loads(document)
            elif isinstance(document, dict):
                json.dumps(document)
            else:
                return False
            return True
        except Exception:
            return False
    
    def save_to_json(self, result, file_path="output.json"):
        self.logger.info(f"Salvataggio su {file_path}")
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.logger.error(f"Errore nel salvataggio JSON: {e}")

