import os
import sys
import json
from json_repair import repair_json
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
                "condizione riferita": "Dolore toracico"
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
            "Sei un medico d’emergenza. Ricevi un testo discorsivo da una trascrizione. "
            "Compila in formato JSON una scheda di Pronto Soccorso (PS), riempiendo i seguenti campi obbligatori. "
            "Non inventare nulla: se un’informazione è assente, inserisci 'N/A'. L'anagrafica del paziente è già stata inserita."
            "Rispondi in italiano e con JSON ben formattato, senza testo introduttivo.\n\n"
            "Esempio di struttura attesa:\n"
            f"{json.dumps(esempio_scheda, ensure_ascii=False, indent=2)}"
        )


    def generate_scheda_from_report(self, referto_ps, report_with_context = None): #DA CONTROLLARE
        prompt = self.__generate_prompt_scheda()
        full_prompt = f"{prompt}\n\nPuoi fare riferimento ai seguenti esempi: {report_with_context}\n\nReferto da analizzare: {referto_ps}"
        try:
            result = self.generator(full_prompt, max_new_tokens=self.max_new_tokens)
            return result #[0]["generated_text"].replace(full_prompt, "").strip()
        except Exception as e:
            self.logger.error(f"Errore nella generazione scheda: {e}")
            return "{}"
        
    def __generate_prompt_report(self):
        esempio_referto = {
              "Intestazione": {
                "Data visita": "N/A",
                "Ora visita": "N/A",
                "Ambulatorio": "N/A",
                "Medico": "N/A"
              },
              "Motivo della visita": "N/A",
              "Anamnesi": {
                "Personale": "N/A",
                "Familiare": "N/A",
                "Evento attuale": "N/A"
              },
              "Esame obiettivo": "N/A",
              "Esami eseguiti": "N/A",
              "Diagnosi": "N/A",
              "Terapia": "N/A",
              "Follow-up": "N/A",
              "Firma medico": "N/A",
              "Data redazione": "N/A"
            }
        
        return (
            "Sei un assistente clinico. Ricevi un testo discorsivo (es. trascrizione verbale) e devi generare un referto medico formale, "
            "chiaro e strutturato, in formato JSON. Non inserire dati inventati. Se una sezione è assente, scrivi 'N/A'.\n\n"
            "Compila questo schema basandoti esclusivamente sulle informazioni fornite nel testo seguente. "
            "Rispondi in italiano e con JSON ben formattato. L'anagrafica del paziente è già stata inserita."
            "Esempio di struttura attesa:\n"
            f"{json.dumps(esempio_referto, ensure_ascii=False, indent=2)}"
        )

                
    def generate_clinical_report(self, referto, report_with_context = None): #DA CONTROLLARE
        prompt = self.__generate_prompt_report() 
        full_prompt = f"{prompt}\n\nPuoi fare riferimento ai seguenti esempi: {report_with_context}\n\nReferto da analizzare: {referto}"
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
        except  json.JSONDecodeError:
            try:
                fixed = repair_json(document)
                return json.loads(fixed)
            except Exception as e:
                return {}
    
    def save_to_json(self, result, file_path="output.json"): #DA RICONTROLLARE
        self.logger.info(f"Salvataggio su {file_path}: IN CORSO")
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            self.logger.info(f"Salvataggio su {file_path}: COMPLETATO")
        except Exception as e:
            self.logger.error(f"Errore nel salvataggio JSON: {e}")
 