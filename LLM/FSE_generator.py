import os
import sys
import json
from json_repair import repair_json
import transformers
import torch
import json5

import random

from datetime import datetime
from dotenv import load_dotenv
from transformers import AutoTokenizer, AutoModelForCausalLM, pipeline
from log import Logger

import random
import requests
import csv
from datetime import datetime
from collections import Counter
from groq import Groq

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

class LLMWrapper:
    def __init__(self, model):
        self.logger = Logger(self.__class__.__name__).get_logger()

        self.max_new_tokens = 1024

        #Modello 
        api_key_2 = os.getenv("API_KEY_2") 
        api_key_3 = os.getenv("API_KEY_3") 
        api_key_4 = os.getenv("API_KEY_4") 
        api_key_5 = os.getenv("API_KEY_5")

        self.client_story_2 = Groq(api_key=api_key_2)
        self.client_story_3 = Groq(api_key=api_key_3)
        self.client_story_4 = Groq(api_key=api_key_4)
        self.client_story_5 = Groq(api_key=api_key_5)

        self.model = model

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

    #--------------------------------- FUNZIONI PER LA GENERAZIONE DELLA SCHEDA PS ----------------------------------------
    
    def extract_json_from_response(self, response_str: str) -> str:
        start = response_str.find("{")
        if start == -1:
            raise ValueError("JSON non trovato nella risposta")
        return response_str[start:]
    
    def fix_json_format(self, json_str):
        fix = repair_json(json_str)
        return json5.loads(fix)

    def __generate_prompt_scheda(self, entities):
        esempio_scheda = {
            "Chiamata": {
                "data": "N/A",
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
            "Causa trasporto non effettuato": "N/A",
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
            "Annotazioni": "N/A"
        }
        
        esempio_trascrizione = " Motivo dellintervento e "
        "sintomi riferiti La paziente ha accusato un intenso dolore al petto, irradiato al braccio sinistro e accompagnato da nausea, mentre era a casa. "
        "Ha riferito anche di aver avuto episodi simili nei giorni precedenti, ma di entità minore. Contesto clinico La paziente è una donna con una storia "
        "familiare di malattie cardiovascolari; la madre è deceduta per un infarto del miocardio alletà di 70 anni. La paziente è ipertesa e in trattamento "
        "con farmaci antipertensivi. Dinamica dellaccesso al PS La chiamata è stata effettuata alle ore 1115 da un familiare. Lintervento è avvenuto in Via "
        "della Libertà, 25, a Roma. Il trasporto è stato effettuato in ambulanza in codice giallo, con monitoraggio continuo dellECG e della saturazione di "
        "ossigeno. Trattamenti e interventi effettuati Allarrivo sul posto, la paziente era vigile, collaborante, con parametri vitali nella norma, ma con "
        "evidente distress respiratorio. È stata sottoposta a ossigenoterapia con maschera facciale a 6 litriminuto e somministrazione di acido "
        "acetilsalicilico da mg per via endovenosa. La paziente ha ricevuto anche un bolo di morfina da 2 mg per il controllo del dolore. Parametri vitali "
        "rilevati Pressione arteriosa 80 mmHg Frequenza cardiaca 92 bpm Frequenza respiratoria 22 attimin Temperatura 36,8C Saturazione di ossigeno 88 con"
        " aria ambiente, migliorata al 94 con ossigenoterapia Eventuale presenza di autorità Non presente. Annotazioni aggiuntive da parte del personale La"
        " paziente ha riferito di aver assunto gli ultimi pasti regolarmente e di non avere particolari allergie note. La famiglia ha fornito una cartella"
        " clinica incompleta con precedenti episodi di angina. Esami diagnostici Allelettrocardiogramma eseguito in ambulanza è emerso un sopraslivellamento "
        "del tratto ST in derivazioni inferiori, suggestivo per infarto miocardico inferiore. Trasporto al PS La paziente è stata trasportata al Pronto "
        " Soccorso dellOspedale Umberto I di Roma, dove è stata accolta nel percorso Code Rosse. Notazioni È stata avviata la procedura per il trattamento"
        " trombolitico e la paziente è stata sottoposta a ulteriori indagini diagnostice, tra cui ecocardiogramma e esami del sangue per marker cardiaci. "
        "Dettagli clinici aggiuntivi La paziente è stata mantenuta sotto stretto monitoraggio per tutta la durata del trasporto e in Pronto Soccorso, con "
        "controlli continui dei parametri vitali e dellECG. Stato alla fine del trasporto La paziente è arrivata al Pronto Soccorso in buone condizioni"
        " generali, ma con persistente dolore toracico."
        
        esempio_output = """
        ```\n{\n  \"Chiamata\": {\n    \"data\": \n      \"N/A\"\n    ,\n    \"H chiamata\": \"11:15\",\n    \"H partenza\": \"N/A\",\n    \"H sul posto\":
        \"N/A\",\n    \"H partenza posto\": \"N/A\",\n    \"H in PS\": \"N/A\",\n    \"H libero e operativo\": \"N/A\",\n    \"luogo intervento\": 
        \"Via della Libertà, 25, Roma\",\n    \"condizione riferita\": \"Dolore toracico acuto\",\n    \"recapito telefonico\": \"N/A\"\n  },\n 
        \"Ambulanza\": {\n    \"CRI\": \"N/A\",\n    \"Sel\": \"N/A\"\n  },\n  \"Equipaggio\": {\n    \"Aut.\": \"N/A\",\n    \"Socc1\": \"N/A\",\n  
        \"Socc2\": \"N/A\",\n    \"IP\": \"N/A\",\n    \"Medico\": \"N/A\"\n  },\n  \"Causa trasporto non effettuato\": \n    \"N/A\"\n  ,\n  
        \"Attivazioni/Autorità presenti\": {\n    \"descrizione\": \"N/A\",\n    \"referto\": \"N/A\"\n  },\n  \"Decesso\": {\n    \"Ora decesso\": \"\",\n    \"Firma\": \"\"\n  },\n 
        \"Rifiuto (firma dell'interessato)\": {\n    \"Firma\": \"\"\n  },\n  \"Rilevazioni\": {\n    \"Parametri\": {\n     
        \"Coscienza\": \"vigile\",\n      \"Cute\": \"N/A\",\n      \"Respiro\": \"regolare\",\n    
        \"Sp02\": \"88% (aria ambiente), 94% (ossigenoterapia)\",\n      \"FC bpm\": \"92\",\n      \"PA mmHg\": \"80\",\n    
        \"Glic, Mg/dl\": \"N/A\",\n      \"Temp. C°\": \"36.8\"\n    },\n    \"Glasgow Coma Scale\": {\n      \"Apertura occhi\": \"N/A\",\n   
        \"Risposta verbale\": \"N/A\",\n      \"Risposta motoria\": \"N/A\"\n    },\n    \"Pupille\": \"N/A\",\n   
        \"Lesioni riscontrate\": \"nessuna\"\n  },\n  \"Provvedimenti\": {\n    \"Respiro\": \"Ossigenoterapia\",\n  
        \"Circolo\": \"Monitoraggio ECG\",\n    \"Immobilizzazione\": \"N/A\",\n    \"Altro\": \"ECG in loco\",\n  
        \"Infusioni/Farmaci\": \"Acido acetilsalicilico, morfina\"\n  },\n  \"Annotazioni\": \n   
        \"Paziente collaborante, nessuna difficoltà durante il trasporto. La paziente ha riferito di aver assunto gli ultimi pasti regolarmente e di non 
        avere particolari allergie note.\"\n  \n}\n```", 

        """


        self.logger.info(f"Entities: {entities}")

        return (
            "Sei un medico in pronto soccorso. Ricevi un testo discorsivo (esempio trascrizione verbale) e devi generare una scheda di ammissione del paziente al pronto soccorso."
            "La scheda deve essere in italiano formale, chiara e ben strutturata in formato JSON. Non inserire dati inventati, attieniti a quelli forniti nel testo."
            "Se una sezione è assente, scrivi 'N/A'. Ecco un esempio di testo che potresti ricevere:"
            f"{esempio_trascrizione}"
            "Ecco un esempio di output relativo alla trascrizione sopra riportata:"
            f"{esempio_output}"
            "Ecco lo schema che devi seguire per generare la scheda di ammissione al pronto soccorso:"
            f"{json.dumps(esempio_scheda, ensure_ascii=False, indent=2)}"
            f"Le seguenti entità sono state riconosciute nel testo e possono aiutarti a completare la scheda:\n{entities}\n\n"
            "Rispondi solo con un JSON valido, non scrivere introduzioni, commenti o spiegazioni."
        )


    def generate_scheda_from_report(self, referto_ps, entities): #DA CONTROLLAREa
        prompt = self.__generate_prompt_scheda(entities)
        full_prompt = f"{prompt}\n\nEcco il vero input: {referto_ps} \n\n Ora scrivi il vero output:"

        clients = [self.client_story_2, self.client_story_3]

        for i, client in enumerate(clients):
            try:
                result = client.chat.completions.create(
                        messages=[{"role": "user", "content": full_prompt}], #prompt + "\n\nReferto da analizzare:\n" + referto_simulato + "\n \nScheda di ammissione al pronto soccorso:\n" + scheda_ps
                        model=self.model,
                        temperature=0.2,
                        max_completion_tokens=1200
                    )
                content = result.choices[0].message.content.strip()

                self.logger.info(f"Risultato della generazione: {content}")
                result_json = self.extract_json_from_response(content)
                self.logger.info(f"JSON estratto dalla risposta: {result_json}")
                fixed_json = self.fix_json_format(result_json)
                self.logger.info(f"JSON corretto: {fixed_json}")
                # Salva le variabili result, result_json e fixed_json in un file JSON
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
        
        esempio_trascrizione = """Il giorno 5 giugno 2025 alle ore 09:30 presso l’ambulatorio di medicina generale, ho visitato il paziente [NOME E COGNOME].
                                Motivo della visita: febbre persistente da tre giorni con brividi e malessere generale.
                                Anamnesi personale: ipertensione arteriosa in trattamento farmacologico.
                                Anamnesi familiare: padre deceduto per infarto a 65 anni, madre diabetica.
                                Evento attuale: comparsa di febbre fino a 38.5°C, dolori muscolari diffusi, cefalea.
                                All’esame obiettivo: paziente vigile, in buone condizioni generali, temperatura 38.2°C, gola arrossata, linfonodi laterocervicali palpabili.
                                Sono stati eseguiti tampone rapido per streptococco e test COVID-19, entrambi negativi.
                                Diagnosi: faringite virale.
                                Terapia: riposo, paracetamolo 1000mg ogni 8 ore in caso di febbre o dolore.
                                Follow-up: rivalutazione tra 3 giorni se i sintomi persistono o peggiorano.
                                Firma: Dott.ssa Elena Bianchi."""
        
        esempio_output = """{
                            "Intestazione": {
                                "Data visita": "2025-06-05",
                                "Ora visita": "09:30",
                                "Ambulatorio": "Medicina Generale",
                                "Medico": "Dott.ssa Elena Bianchi"
                            },
                            "Motivo della visita": "Febbre persistente da tre giorni con brividi e malessere generale.",
                            "Anamnesi": {
                                "Personale": "Ipertensione arteriosa in trattamento farmacologico.",
                                "Familiare": "Padre deceduto per infarto a 65 anni, madre diabetica.",
                                "Evento attuale": "Comparsa di febbre fino a 38.5°C, dolori muscolari diffusi, cefalea."
                            },
                            "Esame obiettivo": "Paziente vigile, in buone condizioni generali, temperatura 38.2°C, gola arrossata, linfonodi laterocervicali palpabili.",
                            "Esami eseguiti": "Tampone rapido per streptococco e test COVID-19, entrambi negativi.",
                            "Diagnosi": "Faringite virale.",
                            "Terapia": "Riposo, paracetamolo 1000mg ogni 8 ore in caso di febbre o dolore.",
                            "Follow-up": "Rivalutazione tra 3 giorni se i sintomi persistono o peggiorano.",
                            "Firma medico": "Dott.ssa Elena Bianchi",
                            "Data redazione": "2025-06-05"
                            }
                            """
        
        unique_entities = sorted(set(entities), key=str.lower)
        formatted_entities = ", ".join(unique_entities) if unique_entities else "nessuna"

        
        return (
            "Sei un assistente clinico. Ricevi un testo discorsivo (esempio trascrizione verbale) e devi generare un referto medico per un paziente che hai visitato."
            "La scheda deve essere in italiano formale, chiara e ben strutturata in formato JSON. Non inserire dati inventati, attieniti a quelli forniti nel testo."
            "Se una sezione è assente, scrivi 'N/A'. Ecco un esempio di testo che potresti ricevere:"
            f"{esempio_trascrizione}"
            "Ecco un esempio di output relativo alla trascrizione sopra riportata:"
            f"{esempio_output}"
            "Ecco lo schema che devi seguire per generare la scheda di ammissione al pronto soccorso:"
            f"{json.dumps(esempio_referto, ensure_ascii=False, indent=2)}"
            f"Le seguenti entità sono state riconosciute nel testo e possono aiutarti a completare la scheda:\n{formatted_entities}\n\n"
            "Rispondi solo con un JSON valido, non scrivere introduzioni, commenti o spiegazioni."
        )

                
    def generate_clinical_report(self, referto, entities): #DA CONTROLLARE
        prompt = self.__generate_prompt_report(entities) 
        full_prompt = f"{prompt}\n\nReferto da analizzare: {referto}"

        clients = [self.client_story_4, self.client_story_5]

        for i, client in enumerate(clients):
            try:
                test_path = "./assets/test"  # <-- percorso della cartella di test
                timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")  # <-- underscore al posto di `:` e `-`
                out_file = os.path.join(test_path, f"{timestamp}.json")  # opzionale: aggiungi ".json"
                
                result = client.chat.completions.create(
                        messages=[{"role": "user", "content": full_prompt}], #prompt + "\n\nReferto da analizzare:\n" + referto_simulato + "\n \nScheda di ammissione al pronto soccorso:\n" + scheda_ps
                        model=self.model,
                        temperature=0.2,
                        max_completion_tokens=1200
                    )
                content = result.choices[0].message.content.strip()

                self.logger.info(f"Risultato della generazione: {content}")
                result_json = self.extract_json_from_response(content)
                self.logger.info(f"JSON estratto dalla risposta: {result_json}")
                fixed_json = self.fix_json_format(result_json)
                self.logger.info(f"JSON corretto: {fixed_json}")
                
                # Salva le variabili result, result_json e fixed_json in un file JSON
                with open(out_file, 'w', encoding='utf-8') as f:
                    json.dump({
                        "result": result,
                        "result_json": result_json,
                        "fixed_json": fixed_json
                    }, f, ensure_ascii=False, indent=2)
                self.logger.info(f"Referto salvato in {out_file}")
                
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
 