import os
import json
import transformers
import torch

from datetime import datetime
from dotenv import load_dotenv
from transformers import AutoTokenizer, AutoModelForCausalLM, pipeline
from log import Logger

#from utility.html_to_pdf import generate
#from utility.logger import Logger

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
            "Sei un medico. Compila la seguente scheda di ammissione PS in formato JSON. "
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
                    "Sei un medico. Compila il referto clinico in formato JSON. "
                    "Usa solo i dati presenti nel testo. Rispondi solo con JSON.\n\n"
                ) 
        
    def generate_clinical_report(self, referto, report_with_context): #DA CONTROLLARE
        prompt = self.__generate_prompt_report() 
        full_prompt = f"{prompt}\n\nReferto da analizzare:\n{referto}\n\nPuoi fare riferimento ai seguenti esempi\n{report_with_context}"
        try:
            result = self.generator(full_prompt, max_new_tokens=self.max_new_tokens)
            return result #[0]["generated_text"].replace(full_prompt, "").strip()
        except Exception as e:
            self.logger.error(f"Errore nella generazione referto: {e}")
            return "{}"
        
    #---------------------------------------- FUNZIONI PER LA GENERAZIONE DEL FSE ------------------------------------------------

    def __generate_prompt_fse(self):
        esempio_fse = {
            "dati_identificativi_amministrativi": {"nome": "Giulia Verdi", "età": 45, "sesso": "F"},
            "referto_laboratorio": {"esame": ["Emocromo"], "risultati": ["Valori nella norma"], "data": "2023-04-18"},
            "referto_radiologia": {"esame": ["RX Torace"], "referto": "Presenza di addensamenti basali", "data": "2023-04-19"},
            "referto_specialistica_ambulatoriale": {"descrizione_visita": "Visita cardiologica", "note": "Presenza di soffi sistolici"},
            "referto_anatomia_patologica": {"descrizione": "N/A", "referto": "N/A"},
            "verbale_pronto_soccorso": {"motivo_accesso": "Dolore toracico", "trattamento": "Monitoraggio e terapia analgesica"},
            "lettera_dimissione": {"diagnosi_dimissione": ["Angina stabile"], "terapia_domiciliare": ["Aspirina", "Atorvastatina"]},
            "profilo_sanitario_sintetico": {"condizioni_pregresse": "Ipertensione", "allergie": "Penicillina"},
            "prescrizione_farmaceutica": {"farmaci": ["Aspirina", "Atorvastatina"]},
            "prescrizione_specialistica": {"esami_prescritti": ["Ecocardiogramma", "Holter"]},
            "cartella_clinica": {"contenuto": "Il paziente lamenta dolore al petto ..."},
            "erogazione_farmaci": {"farmaci_erogati": ["Aspirina"], "farmaci_acquistati_privato": "N/A"},
            "scheda_singola_vaccinazione": {"vaccino": "Anti Covid", "dose": "3ª", "data": "2022-11-10"},
            "certificato_stato_vaccinale": {"vaccini_completati": "Covid-19", "note": "Completo"},
            "erogazione_prestazioni_specialistica": {"prestazioni": "Elettrocardiogramma"},
            "taccuino_personale_assistito": {"note_personali": "Controllo annuale raccomandato"},
            "tessera_portatore_impianto": {"impianto": "N/A"},
            "lettera_invito_screening_prevenzione": {"programma": "Cardiovascolare", "data_invito": "2023-01-20"}
        }

        return (
            "Compila il fascicolo sanitario elettronico (FSE) in formato JSON usando **solo** le informazioni nel testo. "
            "Se una sezione non è presente, scrivi 'N/A'. Esempio di struttura:\n\n"
            f"{json.dumps(esempio_fse, ensure_ascii=False, indent=2)}"
        )


    def check_json_format(self, document): #FUNZIONE PER IL CHECK SUL FORMATO DEL FILE JSON

        return True
    
    def save_to_json(self, result, file_path="output.json"):
        self.logger.info(f"Salvataggio su {file_path}")
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.logger.error(f"Errore nel salvataggio JSON: {e}")

