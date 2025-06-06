import os
import sys
import json
import json5
from json_repair import repair_json
import transformers
import torch
from guardrails import Guard

from datetime import datetime
from dotenv import load_dotenv
from transformers import AutoTokenizer, AutoModelForCausalLM, pipeline
from log import Logger

from pydantic import BaseModel
import json

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from LLM.scheda_ps import SchedaPS
from LLM.clinical_report import RefertoClinico

class LLMWrapper:
    def __init__(self, model):
        self.logger = Logger(self.__class__.__name__).get_logger()

        #Gestione del modello
        self.model = model
        self.max_new_tokens = 1024

    def generator(self, prompt, **kwargs):
        return self.model(prompt, **kwargs) if callable(self.model) else self.model.generate(prompt, **kwargs)
    
    def model_to_json_schema(self, model: BaseModel) -> dict:
        return json.loads(model.model_json_schema(mode="json"))["properties"]
    
    def _build_default(self, field):
            if hasattr(field.outer_type_, '__origin__') and field.outer_type_.__origin__ is list:
                return ["N/A"]
            elif hasattr(field.outer_type_, '__origin__') and field.outer_type_.__origin__ is dict:
                return {}
            elif isinstance(field.default, BaseModel):
                return self.model_to_default_json(type(field.default))
            elif isinstance(field.default, list):
                return field.default
            elif isinstance(field.default, dict):
                return field.default
            elif field.default is not None:
                return field.default
            return "N/A"
    
    def model_to_default_json(self, model_cls):
        defaults = {}
        for field_name, field in model_cls.model_fields.items():
            alias = field.alias or field_name
            if issubclass(field.annotation, BaseModel):
                defaults[alias] = self.model_to_default_json(field.annotation)
            elif hasattr(field.annotation, '__origin__') and field.annotation.__origin__ is list:
                defaults[alias] = ["N/A"]
            else:
                defaults[alias] = "N/A"
        return defaults


    #--------------------------------- FUNZIONI PER LA GENERAZIONE DELLA SCHEDA PS ----------------------------------------
    
    def extract_json_from_response(self, response_str: str) -> str:
        start = response_str.find("{")
        end = response_str.rfind("}")
        if start == -1 or end == -1:
            raise ValueError("JSON non trovato nella risposta")
        return response_str[start:end+1]
    
    def fix_json_format(self, json_str):
        obj = json5.loads(json_str)
        
        return json.dumps(obj, ensure_ascii=False, indent=2)

    def __generate_prompt_scheda(self, entities):
        esempio_scheda = {
            "Chiamata": {
                "data": ["N/A"],
                "H chiamata": "N/A",
                "H partenza": "N/A",
                "H sul posto": "N/A",
                "H partenza posto": "N/A",
                "H in PS": "N/A",
                "H libero e operativo": "N/A",
                "luogo intervento": "N/A",
                "condizione riferita": "N/A"
            },
            "Ambulanza": {
                "CRI": "N/A",
                "Sel": "N/A"
            },
            "Equipaggio": {
                "Aut.": "N/A",
                "Socc1": "N/A",
                "Socc2": "N/A",
                "IP": "N/A",
                "Medico": "N/A"
            },
            "Causa trasporto non effettuato": ["N/A"],
            "Attivazioni/Autorità presenti": {
                "descrizione": "N/A",
                "referto": "N/A"
            },
            "Decesso": {"Ora decesso": "", "Firma": "N/A"},
            "Rifiuto (firma dell'interessato)": {"Firma": "N/A"},
            "Rilevazioni": {
                "Parametri": {
                    "Coscienza": "N/A",
                    "Cute": "N/A",
                    "Respiro": "N/A",
                    "Sp02": "N/A",
                    "FC bpm": "N/A",
                    "PA mmHg": "N/A0",
                    "Glic, Mg/dl": "N/A",
                    "Temp. C°": "N/A"
                },
                "Glasgow Coma Scale": {
                    "Apertura occhi": "N/A",
                    "Risposta verbale": "N/A",
                    "Risposta motoria": "N/A"
                },
                "Pupille": "N/A",
                "Lesioni riscontrate": "N/A"
            },
            "Provvedimenti": {
                "Respiro": "N/A",
                "Circolo": "N/A",
                "Immobilizzazione": "N/A",
                "Altro": "N/A",
                "Infusioni/Farmaci": "N/A"
            },
            "Annotazioni": ["N/A"]
        }

        self.logger.info(f"Entities: {entities}")

        return (
            "Sei un medico d’emergenza. Ricevi un testo discorsivo (es. trascrizione verbale) e devi generare una scheda di ammissione al Pronto Soccorso (PS) in italiano, formale, "
            "chiara e ben strutturata, in formato JSON. Non inserire dati inventati anche se plausibili per il contesto. Se una sezione è assente, scrivi 'N/A'.\n\n"
            "Compila questo schema basandoti esclusivamente sulle informazioni fornite nel testo seguente."
            "Non aggiungere paragrafi introduttivi, produci solo la scheda richiesta."
            "Struttura attesa:\n"
            f"{json.dumps(esempio_scheda, ensure_ascii=False, indent=2)}"
            f"Le seguenti entità sono state riconosciute nel testo e possono aiutarti a completare la scheda:\n{entities}\n\n"
        )


    def generate_scheda_from_report(self, referto_ps, entities): #DA CONTROLLARE
        #schema = PydanticSchema(SchedaPS) 
        guard = Guard.for_pydantic(output_class=SchedaPS)

        esempio_scheda = self.model_to_default_json(SchedaPS)

        self.logger.info(f"Entities: {entities}")

        prompt = self.__generate_prompt_scheda(entities)
        self.logger.info(f"Generazione della scheda PS con contesto")
        full_prompt = f"{prompt}\n\nReferto da analizzare: {referto_ps}"
        
        try:
            result = self.generator(full_prompt, max_new_tokens=self.max_new_tokens)
            
            # Validazione e parsing con Guardrails
            validated_output = guard.parse(result)
            validated_dict = validated_output.model_dump_json()
            # validated_dict è un dizionario valido secondo RefertoClinico
            self.logger.info(f"Output json: {validated_dict}")
            #Provo a salvare il risultato per vedere cosa ha prodotto
            self.save_to_json(validated_dict, "assets/transcriptions/prova_guardrail_pydantic.json")

            result_json = self.extract_json_from_response(result)
            fixed_json = self.fix_json_format(result_json)
            return fixed_json #[0]["generated_text"].replace(full_prompt, "").strip()
        except Exception as e:
            self.logger.error(f"Errore nella generazione scheda: {e}")
            return "{}"
        
    def __generate_prompt_report(self, entities):
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
        
        unique_entities = sorted(set(entities), key=str.lower)
        formatted_entities = ", ".join(unique_entities) if unique_entities else "nessuna"

        
        return (
            "Sei un assistente clinico. Ricevi un testo discorsivo (es. trascrizione verbale) e devi generare un referto medico in italiano, formale, "
            "chiaro e ben strutturato, in formato JSON. Non inserire dati inventati anche se plausibili per il contesto. Se una sezione è assente, scrivi 'N/A'.\n\n"
            "Compila questo schema basandoti esclusivamente sulle informazioni fornite nel testo seguente. "
            "NON SCRIVERE INTRODUZIONI, COMMENTI O SPIEGAZIONI. RISPONDI SOLO CON UN OGGETTO JSON VALIDO.\n\n"
            f"Le seguenti entità sono state riconosciute nel testo e possono aiutarti a completare la scheda:\n{formatted_entities}\n\n"
            "Struttura attesa:\n"
            f"{json.dumps(esempio_referto, ensure_ascii=False, indent=2)}"
        )

                
    def generate_clinical_report(self, referto, entities): #DA CONTROLLARE
        #schema = PydanticSchema(RefertoClinico)
        guard = Guard.for_pydantic(output_class=RefertoClinico)
        
        prompt = self.__generate_prompt_report(entities) 
        full_prompt = f"{prompt}\n\nReferto da analizzare: {referto}"
        
        try:
            result = self.generator(full_prompt, max_new_tokens=self.max_new_tokens)

            # Validazione e parsing con Guardrails
            validated_output = guard.parse(result)
            validated_dict = validated_output.model_dump_json()
            # validated_dict è un dizionario valido secondo RefertoClinico
            self.logger.info(f"Output json: {validated_dict}")
            #Provo a salvare il risultato per vedere cosa ha prodotto
            self.save_to_json(validated_dict, "assets/transcriptions/prova_guardrail_pydantic.json")

            result_json = self.extract_json_from_response(result)
            fixed_json = self.fix_json_format(result_json)
            
            return fixed_json #[0]["generated_text"].replace(full_prompt, "").strip()
        except Exception as e:
            self.logger.error(f"Errore nella generazione referto: {e}")
            return "{}"

    def check_json_format(self, document): #pydantic
        """
        Controlla se l'input è un JSON valido.
        Supporta:
        - dizionari Python
        - stringhe JSON
        Ritorna True se il formato è valido, altrimenti False.
        """
        if isinstance(document, dict):
            try:
                json.dumps(document)  # verifica serializzabilità
                return True
            except (TypeError, ValueError):
                self.logger.warning(f"")
                return False

        elif isinstance(document, str):
            try:
                json.loads(document)  # verifica deserializzabilità
                return True
            except json.JSONDecodeError:
                self.logger.warning(f"")
                return False

        return False
    
    def parse_json_if_valid(self, document):
        """
        Tenta di convertire un input in dizionario JSON.
        Ritorna:
        - dict se valido
        - {} se non valido
        """
        if isinstance(document, dict):
            return document
        elif isinstance(document, str):
            try:
                return json.loads(document)
            except json.JSONDecodeError:
                return {}
        return {}

    
    def save_to_json(self, result, file_path="output.json"): #DA RICONTROLLARE
        self.logger.info(f"Salvataggio su {file_path}: IN CORSO")
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            self.logger.info(f"Salvataggio su {file_path}: COMPLETATO")
        except Exception as e:
            self.logger.error(f"Errore nel salvataggio JSON: {e}")
 