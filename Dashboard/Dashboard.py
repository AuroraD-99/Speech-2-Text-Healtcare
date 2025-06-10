import streamlit as st
import bcrypt
import os
import sys
import time
import re
import dotenv

import requests
from codicefiscale import codicefiscale
import datetime
import locale
import pandas as pd
import altair as alt
import matplotlib.pyplot as plt
import seaborn as sns
from pandas.plotting import parallel_coordinates

import io

from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Indenter, KeepTogether
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib import colors



sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from Database.mongodb import DB

class Dashboard:
    def __init__(self, env_file="key.env"):
        if "user" not in st.session_state:
            st.session_state.user = {}
        if "deleted" not in st.session_state:
            st.session_state.deleted = False
        if "db" not in st.session_state:
            st.session_state.db = DB()  # salva l'istanza nella sessione
        self.db = st.session_state.db
        if "is_recording" not in st.session_state:
            st.session_state.is_recording = False
        if "page" not in st.session_state:
            st.session_state.page = "login"
        if "logged_in" not in st.session_state:
            st.session_state.logged_in = False
        if "last_report" not in st.session_state:
            st.session_state.last_report = None
        if "function_mode" not in st.session_state:
            st.session_state.function_mode = "Generic"
        if "function_icon" not in st.session_state:
            st.session_state.function_icon = "🔍"
        if "validate" not in st.session_state:
            st.session_state.validate = False
        if "cf" not in st.session_state:
            st.session_state.cf = ""
        if "login_amministratore" not in st.session_state:
            st.session_state.login_amministratore = False
        if "admin_report_to_show" not in st.session_state:
            st.session_state.admin_report_to_show = None
        
        
        locale.setlocale(locale.LC_ALL, 'it_IT.UTF-8')
        
        # Imposta l'environment variable per FastAPI
        dotenv.load_dotenv(env_file, override=True)
        
        self.controller_url = os.getenv('CONTROLLER_URL', 'http://127.0.0.1:8003')
        
    def sidebar_query(self):
        tipo_referto = st.sidebar.selectbox(
            "Seleziona tipo referto", ["Tutti", "Ospedale", "Emergency"]
        )

        filtro_paziente = st.sidebar.text_input("Filtro paziente (nome, cognome, CF)")

        start_date = st.sidebar.date_input("Data inizio", value=None)
        end_date = st.sidebar.date_input("Data fine", value=None)

        filtro_patologia = ""
        filtro_farmaco = ""
        filtro_deceduti = False
        filtro_forze_ordine = False

        if tipo_referto == "Ospedale":
            filtro_patologia = st.sidebar.text_input("Filtro Patologia (Diagnosi)")
            filtro_farmaco = st.sidebar.text_input("Filtro Farmaco (Terapia)")

        if tipo_referto == "Emergency":
            filtro_deceduti = st.sidebar.checkbox("Mostra solo pazienti deceduti")
            filtro_forze_ordine = st.sidebar.checkbox("Mostra solo pazienti con intervento forze dell'ordine")

        return {
            "tipo_referto": tipo_referto,
            "filtro_paziente": filtro_paziente,
            "start_date": start_date if isinstance(start_date, (type(None), datetime.date)) else None,
            "end_date": end_date if isinstance(end_date, (type(None), datetime.date)) else None,
            "filtro_patologia": filtro_patologia,
            "filtro_farmaco": filtro_farmaco,
            "filtro_deceduti": filtro_deceduti,
            "filtro_forze_ordine": filtro_forze_ordine,
        }


    
    
    def filtra_referti(self):
        st.markdown("## 🔍 Filtra Referti Clinici")

        user = st.session_state.get("user", {})
        medico_cf = user.get("Anagrafica", {}).get("Codice Fiscale", "")

        st.markdown("---")
        st.markdown("### 🗂️ Riepilogo referti dei tuoi pazienti")

        try:
            self.db.refresh_queue_for_doctor(medico_cf)
            reports = self.db.get_all_clinical_reports_by_doctor_cf(medico_cf)

            if not reports:
                st.warning("🔍 Non ci sono referti associati al tuo codice fiscale.")
                return

            filtri = self.sidebar_query()

            filtro_attivo = (
                filtri["tipo_referto"] != "Tutti" or
                filtri["filtro_paziente"] != "" or
                filtri["start_date"] is not None or
                filtri["end_date"] is not None or
                (filtri["tipo_referto"] == "Ospedale" and (filtri["filtro_patologia"] or filtri["filtro_farmaco"])) or
                (filtri["tipo_referto"] == "Emergency" and (filtri["filtro_deceduti"] or filtri["filtro_forze_ordine"]))
            )

            container = st.sidebar.container(border=True)
            with container:
                st.markdown(f"#### 🗂️ Tipo referto scelto: {filtri['tipo_referto']}")
                st.markdown(f"#### 📋 Numero referti totali: {len(reports)}")

            if not filtro_attivo:
                # Nessun filtro attivo: mostra i primi 100 referti ordinati per timestamp decrescente
                reports_sorted = sorted(reports, key=lambda x: x.get("timestamp", ""), reverse=True)
                filtered_reports = reports_sorted[:100]
            else:
                def match_report(report):
                    # Tipo referto
                    if filtri["tipo_referto"] != "Tutti" and report.get("type", "") != filtri["tipo_referto"]:
                        return False

                    # Filtro paziente
                    nominativo = report["dati paziente"].get("nominativo", {})
                    nome_paziente = nominativo.get("nome", "").lower()
                    cognome_paziente = nominativo.get("cognome", "").lower()
                    codice_fiscale_paziente = report["dati paziente"].get("codice_fiscale", "").lower()
                    filtro_paz = filtri["filtro_paziente"].lower()

                    if filtro_paz:
                        if (filtro_paz not in nome_paziente and
                            filtro_paz not in cognome_paziente and
                            filtro_paz not in codice_fiscale_paziente):
                            return False

                    # Filtro data
                    timestamp_str = report.get("timestamp", "")
                    if timestamp_str:
                        from datetime import datetime
                        try:
                            ts = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
                            if filtri["start_date"] and ts.date() < filtri["start_date"]:
                                return False
                            if filtri["end_date"] and ts.date() > filtri["end_date"]:
                                return False
                        except Exception:
                            return False

                    # Filtri specifici per tipo referto

                    if filtri["tipo_referto"] == "Ospedale":
                        filtro_patologia = str(filtri.get("filtro_patologia", "")).lower()
                        filtro_farmaco = str(filtri.get("filtro_farmaco", "")).lower()

                        clinical_report = report.get("clinical_report", "")

                        if isinstance(clinical_report, dict):
                            diagnosi = str(clinical_report.get("Diagnosi", "")).lower()
                            terapia = str(clinical_report.get("Terapia", "")).lower()
                        else:
                            # Se clinical_report è stringa o altro, converti tutto in stringa
                            testo_clinical_report = str(clinical_report).lower()
                            diagnosi = testo_clinical_report
                            terapia = testo_clinical_report

                        if filtro_patologia and filtro_patologia not in diagnosi:
                            return False

                        if filtro_farmaco and filtro_farmaco not in terapia:
                            return False

                    elif filtri["tipo_referto"] == "Emergency":
                        # filtro deceduti su scheda_ps.Decesso.Ora decesso
                        if filtri.get("filtro_deceduti", False):
                            ora_decesso = report.get("scheda_ps", {}).get("Decesso", {}).get("Ora decesso", "")
                            if not ora_decesso or ora_decesso == "N/A":
                                return False

                        # filtro forze ordine su scheda_ps.Attivazioni/Autorità presenti.descrizione
                        if filtri.get("filtro_forze_ordine", False):
                            descrizione = report.get("scheda_ps", {}).get("Attivazioni/Autorità presenti", {}).get("descrizione", "")
                            if not descrizione or descrizione == "N/A":
                                return False

                    return True

                filtered_reports = list(filter(match_report, reports))
                filtered_reports.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

            with container:
                st.markdown(f"#### 🔎 Numero referti filtrati: {len(filtered_reports)}")

            if not filtered_reports:
                st.warning("Nessun referto trovato con i filtri selezionati.")
                return

            # Raggruppa per paziente
            grouped = {}
            for report in filtered_reports:
                nominativo = report["dati paziente"].get("nominativo", {})
                paziente = f"{nominativo.get('cognome', '')} {nominativo.get('nome', '')}".strip()
                grouped.setdefault(paziente, []).append(report)

            grouped = dict(sorted(grouped.items(), key=lambda item: item[0].split()[-1].lower()))

            # Visualizza referti
            for paziente, referti in grouped.items():
                with st.expander(f"🧑‍⚕️ Paziente: {paziente} ({len(referti)} referti)"):
                    for referto in referti:
                        st.markdown(f"""
                        - 🩺 {referto.get('type', 'N/A')}
                        - 📄 **ID Referto**: `{referto.get('_id', 'N/A')}`
                        - 🗓️ **Data**: {referto.get('timestamp', 'N/A')}
                        """)
                        with st.container():
                            col1, col2, col3 = st.columns(3)
                            with col3:
                                delete_key = f"delete_{referto.get('_id')}"
                                confirm_key = f"confirm_delete_{referto.get('_id')}"

                                if st.button("❌ Cancella Referto", key=delete_key):
                                    st.session_state[confirm_key] = True

                                if st.session_state.get(confirm_key, False):
                                    st.warning("⚠️ Sei sicuro di voler cancellare questo referto?")
                                    col_confirm, col_cancel = st.columns(2)
                                    with col_confirm:
                                        if st.button("✅ Conferma", key=f"confirm_{referto.get('_id')}"):
                                            self.db.delete_clinical_report(referto.get('_id'))
                                            self.db.refresh_queue_for_doctor(medico_cf)
                                            del st.session_state[confirm_key]
                                            st.session_state.deleted = True
                                            st.rerun()
                                    with col_cancel:
                                        if st.button("❎ Annulla", key=f"cancel_{referto.get('_id')}"):
                                            del st.session_state[confirm_key]
                                            st.rerun()

                            with col2:
                                st.button(
                                    "✏️ Modifica Referto",
                                    key=f"modify_{referto.get('_id')}",
                                    on_click=self.modify_report,
                                    args=(referto.get('_id'),),
                                )

                            with col1:
                                st.button(
                                    "👁️ Visualizza Referto",
                                    key=f"show_{referto.get('_id')}",
                                    on_click=self.show_report,
                                    args=(referto.get('_id'),),
                                )

        except Exception as e:
            st.error(f"❌ Errore nel recupero dei referti: {str(e)}")


        if st.session_state.get("deleted", False):
            st.session_state["deleted"] = False
            st.rerun()
            
        # Pulsanti azioni
        if st.sidebar.button("🔄 Ricarica", use_container_width=True):
            st.rerun()

        if st.sidebar.button("🏠 Torna alla Home", use_container_width=True):
            st.session_state.page = "main"
            st.rerun()

        if st.sidebar.button("🔒 Logout", use_container_width=True):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()

    def save_audio_file_from_upload(self, audio_file):
        output_dir = "./assets/audios"
        os.makedirs(output_dir, exist_ok=True)
        filename = os.path.join(output_dir, f"{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.wav")

        audio_data = audio_file.read()
        with open(filename, "wb") as f:
            f.write(audio_data)

        return filename
    
    def genera_anagrafica(self, dizionario:dict):
        """
        Il dizionario user ha la seguente struttura
        
        {
            "Id":
            "Anagrafica": 
                "Email":
                "Password":
                "Nome":
                "Cognome":
                "Cellulare":
                "Codice Fiscale":
                "Ruolo":
            "Ospedale":
                "Nome Ospedale":
                "Città":
                "Provincia":
                "CAP":
                "Reparto":
        }
        """
        anagrafica = {
            "Anagrafica": {
                k: v for k, v in dizionario.get("Anagrafica", {}).items() if k != "Password"
            },
            "Ospedale": dizionario.get("Ospedale",{}).copy()
        }
        return anagrafica
    
    def update_clinical_report(self, report_id, report):
        """
        Aggiorna un referto clinico nel database.
        """
        response = requests.post(
            url=f"{self.controller_url}/update_report",
            json={
                "report_id": report_id,
                "report": report
            }
        )
        if response.status_code == 200:
            st.success("✅ Referto aggiornato con successo!")
            time.sleep(1)
        else:
            st.error("❌ Errore durante l'aggiornamento del referto.")
    
    def del_and_rerun(self, report_id):
        confirm_key = f"confirm_delete_{report_id}"
        if not st.session_state.get(confirm_key, False):
            # Primo click: settiamo il flag e mostriamo messaggio
            st.session_state[confirm_key] = True
            st.warning("Premi di nuovo per confermare la cancellazione")
        else:
            # Secondo click: cancella e resetta flag
            response = requests.post(
                url = f"{self.controller_url}/delete_report",
                json = {
                    "text": report_id
                }
            )
            if response.status_code == 200:
                st.session_state.deleted = True
                st.session_state[confirm_key] = False
                st.rerun()

    def get_report_by_id(self, report_id):
        """
        Recupera un referto clinico dal database per ID.
        """
        response = requests.post(
            url=f"{self.controller_url}/get_report_by_id",
            json={
                "text": report_id
            }
        )
        if response.status_code == 200:
            return response.json()["report"]
        else:
            st.error("❌ Errore durante il recupero del referto.")
            return None
        
    def modify_report(self, report_id):
        
        id = str(report_id)
        
        response = requests.post(
            url = f"{self.controller_url}/get_report_by_id",
            json = {
                "text": id
            }
        )
        if response.status_code == 200:
            risposta =  response.json()
            report = risposta["report"]
            st.session_state.last_report = report
            st.session_state.page = "report_modify"
            st.session_state.validate = False
        
    def show_report(self, report_id):
        
        id = str(report_id)
        
        response = requests.post(
            url = f"{self.controller_url}/get_report_by_id",
            json = {
                "text": id 
            }
        )
        if response.status_code == 200:
            report =  response.json()
            st.session_state.last_report = report["report"]
            st.session_state.page = "show_report"
        
    def new_report(self, filename):
        func_mode = "Emergency" if st.session_state.function_mode == "Pronto Soccorso" else "Ospedale"
        response = requests.post(
            url=f"{self.controller_url}/new_report",
            json = {
                "text": filename,
                "anagrafica_medico": self.genera_anagrafica(st.session_state.user),
                "function_mode": func_mode,
            })
        
        st.session_state.report_ready = False
        
        if response.status_code == 200:
            report = response.json()
            st.session_state.last_report = report["report"]
            doctor_cf = st.session_state.user["Anagrafica"]["Codice Fiscale"]
            self.db.enqueue_report_for_doctor(doctor_cf, report["report"]["_id"])
            st.session_state.report_ready = True
            st.session_state.page = "report_modify"
            st.session_state.validate = True
        else:
            st.session_state.last_report = {"Error": "Failed to create report"}
            st.session_state.report_ready = True
        
        st.rerun()  # Ricarica la pagina per aggiornare l'interfaccia
        
    def start_audio_recording(self):
        if not st.session_state.get("is_recording", False):
            st.session_state.audio_recorder.start_recording()
            st.session_state.is_recording = True
            st.success("🎤 Registrazione avviata!"),
    
    def stop_audio_recording(self):
        if st.session_state.get("is_recording", False):
            filename = st.session_state.audio_recorder.stop_recording()
            st.session_state.is_recording = False
            st.session_state.last_audio_file = filename
            return filename
        return None

    def login_amministratore(self):
        
        st.markdown("## 🛡️ Login Amministratore")

        with st.container():
            col1, col2 = st.columns(2)
            with col1:
                st.text_input("📧 Email", key="admin_login_email", placeholder="es: admin@locale.it")
            with col2:
                st.text_input("🔑 Password", type="password", key="admin_login_password", placeholder="Password amministratore")

        if st.button("🚪 Accedi come Amministratore", use_container_width=True):
            user = self.db.get_operator(st.session_state.admin_login_email)
            if user and user["Anagrafica"]["Ruolo"] == "Amministratore":
                hashed_password = user["Anagrafica"]["Password"]
                if isinstance(hashed_password, str):
                    hashed_password = hashed_password.encode('utf-8')

                if bcrypt.checkpw(st.session_state.admin_login_password.encode('utf-8'), hashed_password):
                    st.session_state.logged_in = True
                    st.session_state.user = user

                    # Se primo accesso, reindirizza alla pagina completamento profilo
                    if user["Anagrafica"].get("Primo Accesso", True):
                        st.success("🔧 Primo accesso rilevato. Completa il tuo profilo amministratore.")
                        st.session_state.page = "completa_registrazione_admin"
                    else:
                        st.success(f"✅ Benvenuto, {user['Anagrafica']['Nome']} {user['Anagrafica']['Cognome']}!")
                        st.session_state.page = "admin_dashboard"

                    time.sleep(2)
                    st.rerun()
                else:
                    st.error("❌ Credenziali non valide")
            else:
                st.error("❌ Utente non trovato o non autorizzato")
                
        st.markdown("---")
        # Pulsante per tornare al login operatore
        if st.button("🔙 Torna al Login Operatore", use_container_width=True):
            st.session_state.page = "login"
            st.rerun()
    
    def completa_registrazione_admin(self):
        st.markdown("## 📝 Completa Registrazione Amministratore")

        admin_data = st.session_state.user  # Precaricato dal login
        email = admin_data["Anagrafica"]["Email"]
        
        with st.form("complete_admin_form"):
            st.markdown("### 👤 Dati Anagrafici")
            col1, col2 = st.columns(2)
            with col1:
                nome = st.text_input("🧍 Nome", value=admin_data["Anagrafica"].get("Nome", ""))
                cognome = st.text_input("🧍‍♂️ Cognome", value=admin_data["Anagrafica"].get("Cognome", ""))
            with col2:
                cellulare = st.text_input("📱 Cellulare", value=admin_data["Anagrafica"].get("Cellulare", ""))
                cf = st.text_input("🧾 Codice Fiscale", value=admin_data["Anagrafica"].get("Codice Fiscale", ""))

            st.markdown("### 🔐 Scegli una nuova password")
            nuova_password = st.text_input("🔑 Nuova Password", type="password")

            st.markdown("### 🏥 Informazioni Struttura Ospedaliera")
            col3, col4 = st.columns(2)
            with col3:
                nome_struttura = st.text_input("🏢 Nome della Struttura", value=admin_data.get("Ospedale", {}).get("Nome Ospedale", ""))
                reparto = st.text_input("🏨 Reparto", value=admin_data.get("Ospedale", {}).get("Reparto", ""))
            with col4:
                città = st.text_input("📍 Città", value=admin_data.get("Ospedale", {}).get("Città", ""))
                provincia = st.text_input("🌍 Provincia", value=admin_data.get("Ospedale", {}).get("Provincia", ""))
                cap = st.text_input("📬 CAP", value=admin_data.get("Ospedale", {}).get("CAP", ""))

            st.markdown("### 🛡️ Ruolo")
            st.selectbox("Ruolo", options=["Amministratore"], index=0, disabled=True)

            col_reg, col_back = st.columns(2)
            with col_reg:
                submitted = st.form_submit_button("✅ Completa Registrazione")
            with col_back:
                go_back = st.form_submit_button("⬅️ Logout")

        # Gestione logout
        if go_back:
            st.session_state.clear()
            st.rerun()

        # Validazione e aggiornamento
        if submitted:
            cf_pattern = r"^[A-Z]{6}[0-9]{2}[A-Z][0-9]{2}[A-Z][0-9]{3}[A-Z]$"
            password_pattern = r"^(?=.*[,.!#]).{8,}$"  # Almeno 8 caratteri + almeno un carattere speciale

            if not nome.strip() or not cognome.strip():
                st.error("❗ Nome e Cognome non possono essere vuoti.")
            elif not cellulare.isdigit() or not (10 <= len(cellulare) <= 11):
                st.error("📱 Il cellulare deve contenere 10 o 11 cifre.")
            elif not re.match(cf_pattern, cf.upper()):
                st.error("🧾 Codice Fiscale non valido. Deve seguire il formato italiano.")
            elif not nuova_password:
                st.error("🔐 Devi inserire una nuova password.")
            elif bcrypt.checkpw(nuova_password.encode('utf-8'), admin_data["Anagrafica"]["Password"]):
                st.error("🔁 La nuova password non può essere uguale a quella attuale.")
            elif not re.match(password_pattern, nuova_password):
                st.error("❗ La password deve contenere almeno 8 caratteri e almeno uno tra: , . ! #")
            elif not nome_struttura.strip() or not reparto.strip() or not città.strip() or not provincia.strip() or not cap.strip():
                st.error("🏥 Tutti i campi relativi alla struttura devono essere compilati.")
            elif not cap.isdigit() or len(cap) != 5:
                st.error("📬 Il CAP deve essere un numero di 5 cifre.")
            else:
                updated_user = {
                    "Anagrafica": {
                        "Email": email,
                        "Password": nuova_password,
                        "Nome": nome,
                        "Cognome": cognome,
                        "Cellulare": cellulare,
                        "Codice Fiscale": cf.upper(),
                        "Ruolo": "Amministratore",
                        "Primo Accesso": False
                    },
                    "Ospedale": {
                        "Nome Ospedale": nome_struttura,
                        "Città": città,
                        "Provincia": provincia,
                        "CAP": cap,
                        "Reparto": reparto,
                    }
                }

                self.db.update_administrator(admin_data["_id"], updated_user)

                st.success("✅ Registrazione completata con successo! Verrai reindirizzato al pannello amministrativo.")
                time.sleep(2)
                st.session_state.user = updated_user
                st.session_state.page = "admin_dashboard"
                st.rerun()
                
    def get_nested(self, data, path, default='N/A'):
        keys = path.split(".")
        for key in keys:
            data = data.get(key, {})
            if not isinstance(data, dict):
                return data if data else default
        return data or default
    
    def registra_amministratore(self):
        st.markdown("## 📝 Registrazione Nuovo amministratore")

        with st.form("register_form"):
            st.markdown("### 👤 Dati Anagrafici")
            col1, col2 = st.columns(2)
            with col1:
                email = st.text_input("📧 Email")
                password = st.text_input("🔑 Password", type="password")
                nome = st.text_input("🧍 Nome (opzionale)")
                cognome = st.text_input("🧍‍♂️ Cognome (opzionale)")
            with col2:
                cellulare = st.text_input("📱 Cellulare (opzionale)")
                cf = st.text_input("🧾 Codice Fiscale (opzionale)")
                ruolo = st.text_input("💼 Ruolo", value="Amministratore", disabled=True)

            st.markdown("### 🏥 Informazioni Struttura Ospedaliera (opzionali)")
            col3, col4 = st.columns(2)
            with col3:
                nome_struttura = st.text_input("🏢 Nome della Struttura")
                reparto = st.text_input("🏨 Reparto")
            with col4:
                città = st.text_input("📍 Città")
                provincia = st.text_input("🌍 Provincia")
                cap = st.text_input("📬 CAP")

            col_reg, col_back = st.columns(2)
            with col_reg:
                submitted = st.form_submit_button("📌 Registrati")
            with col_back:
                go_back = st.form_submit_button("⬅️ Indietro")

        if go_back:
            st.session_state.page = "admin_dashboard"
            st.rerun()

        if submitted:
            # Validazione minima solo per email e password
            email_pattern = r"^[\w\.-]+@(?:gmail\.com|yahoo\.com|libero\.it|outlook\.com|hotmail\.com|icloud\.com)$"
            password_pattern = r"^(?=.*[.,!&#]).{8,16}$"

            if not re.match(email_pattern, email):
                st.error("📧 Inserisci un'email valida (es. @gmail.com, @libero.it, ecc.)")
            elif not re.match(password_pattern, password):
                st.error("🔑 La password deve essere lunga 8-16 caratteri e contenere almeno uno tra: . , ! & #")
            elif self.db.get_operator(email):
                st.error("📧 Email già registrata.")
            else:
                new_user = {
                    "Anagrafica": {
                        "Email": email,
                        "Password": password,
                        "Nome": nome,
                        "Cognome": cognome,
                        "Cellulare": cellulare,
                        "Codice Fiscale": cf,
                        "Ruolo": "Amministratore",
                    },
                    "Ospedale": {
                        "Nome Ospedale": nome_struttura,
                        "Città": città,
                        "Provincia": provincia,
                        "CAP": cap,
                        "Reparto": reparto,
                    }
                }
                self.db.insert_operator(new_user)
                st.success("✅ Registrazione nuovo amministratore completata con successo! Fornisci le credenziali al nuovo amministratore per consentirgli l'accesso.")
                time.sleep(2)
                st.session_state.page = "admin_dashboard"
                st.rerun()
        
    def admin_dashboard(self):
        def sidebar_admin():
            with st.sidebar:
                st.markdown("### 🔎 Filtri di Ricerca")
                
                # Filtro medico compatto
                filtro_medico = st.text_input("🔍 Cerca medico (nome, cognome, CF)")
                
                # Filtro paziente compatto
                filtro_paziente = st.text_input("🔍 Cerca paziente (nome, cognome, CF)")

                # Intervallo date
                data_inizio = st.date_input("📅 Data Inizio", value=None)
                data_fine = st.date_input("📅 Data Fine", value=None)
                
                # Tipologia
                tipo_referto = st.selectbox("📄 Tipo Referto", options=["", "Pronto Soccorso", "Ospedale"])
                
                limit = st.number_input("🔢 Numero massimo di report", min_value=1, value=10, step=1)
                
                # Costruzione query
                query = {}

                # Filtro medico su nome/cognome/CF
                if filtro_medico:
                    query["$or"] = [
                        {"dati medico.Anagrafica.Nome": {"$regex": filtro_medico, "$options": "i"}},
                        {"dati medico.Anagrafica.Cognome": {"$regex": filtro_medico, "$options": "i"}},
                        {"dati medico.Anagrafica.Codice Fiscale": {"$regex": filtro_medico, "$options": "i"}}
                    ]

                # Filtro paziente su nome/cognome/CF
                if filtro_paziente:
                    query.setdefault("$and", []).append({
                        "$or": [
                            {"dati paziente.nominativo.nome": {"$regex": filtro_paziente, "$options": "i"}},
                            {"dati paziente.nominativo.cognome": {"$regex": filtro_paziente, "$options": "i"}},
                            {"dati paziente.codice fiscale": {"$regex": filtro_paziente, "$options": "i"}}
                        ]
                    })

                # Filtro per tipo
                if tipo_referto:
                    query["type"] = tipo_referto if tipo_referto!="Pronto Soccorso" else "Emergency"

                # Intervallo date
                if data_inizio and data_fine:
                    query["timestamp"] = {
                        "$gte": data_inizio.strftime("%Y-%m-%d"),
                        "$lte": data_fine.strftime("%Y-%m-%d")
                    }
                
                with st.container():
                    
                    if st.button("📊 Analytics",use_container_width=True):
                        st.session_state.page = "analytics"
                        st.rerun()
                    if st.button("👤 Registra nuovo admin", use_container_width=True):
                        st.session_state.page = "register_admin"
                        st.rerun()
                    if st.button("🔒 Logout", use_container_width=True):
                        st.session_state.clear()
                        st.rerun()
                return query, limit

        def dashboard_admin(reports):
            
            st.markdown("## 📋 Report Clinici - Amministratore")
            st.markdown("##### Visualizza e gestisci i referti clinici generati da tutti i medici della struttura.") 
            
            if not reports:
                st.info("❗ Nessun report disponibile al momento.")
            else:
                for report in reports:
                    with st.container():
                        st.markdown("---")
                        cols = st.columns([3, 2, 2])
                        with cols[0]:
                            st.markdown(f"**🧑‍⚕️ Medico:** `{self.get_nested(report, 'dati medico.Anagrafica.Nome')} {self.get_nested(report, 'dati medico.Anagrafica.Cognome')}`")
                            st.markdown(f"**👤 Paziente:** {self.get_nested(report, 'dati paziente.nominativo.nome')} {self.get_nested(report, 'dati paziente.nominativo.cognome')}")
                        with cols[1]:
                            st.markdown(f"**📅 Data:** {report.get('timestamp', 'N/A').split()[0]}")
                            st.markdown(f"**🔬 Tipo Referto:** `{report.get('type')}`")
                        with cols[2]:
                            st.markdown(f"**🏥 Reparto:** {self.get_nested(report, 'dati medico.Ospedale.Reparto')}")
                            st.markdown(f"**📌 Validato:** `{'Si' if report.get('validated', 'In attesa') else 'No'}`")

                        with st.container():
                            if st.button("Visualizza referto", key = f"show_report_{report['_id']}", use_container_width=True):
                                st.session_state.page = "show_report_admin"
                                st.session_state.admin_report_to_show = report
                                st.rerun()
                        st.markdown(" ")
            
        
        query, limit = sidebar_admin()
        reports = self.db.get_all_clinical_reports(query, limit)
        dashboard_admin(reports)
    
    def analytics(self):
        # Sidebar
        with st.sidebar:
            if st.button("🔙 Torna alla Dashboard", use_container_width=True):
                st.session_state.page = "admin_dashboard"
                st.rerun()

        # Titolo principale
        
        st.title("🧠 Data Analytics")
        
        # Indice Analisi
        st.subheader("📑 Indice delle Analisi Disponibili")
        st.markdown("""
        - ⏳ **Analisi Temporale**: Statistiche sui referti in base all'intervallo di tempo.
        - 👨‍⚕️ **Analisi per Medico**: Quantità e distribuzione dei referti per medico e reparto.
        - 🧩 **Query Complesse**: Analisi avanzate multi-parametro o nidificate.
        """)
        st.markdown("---")

        # Tabs per le sezioni
        tab_temp, tab_medico, tab_complesse = st.tabs(["⏳ Analisi Temporale", "👨‍⚕️ Analisi per Medico", "🧩 Analisi Avanzate"])

        with tab_temp:
            self.show_analisi_temporale()

        with tab_medico:
            self.show_analisi_per_medico()

        with tab_complesse:
            self.show_analisi_complesse()


    def show_analisi_temporale(self):
        st.markdown("## ⏳ Analisi Temporale dei Referti Clinici")
        st.markdown("Definisci un intervallo temporale per eseguire le analisi.")
        data_start = st.date_input("📅 Data inizio")
        data_end = st.date_input("📅 Data fine")

        if data_start and data_end and data_start <= data_end:
            
            data_start = str(data_start) + " 00:00:01"
            data_end = str(data_end) + " 23:59:59"
            media_referti, max_referti, referto_comune, decessi = self.db.analitiche_temporali(data_start, data_end)
            st.markdown(f"- 📊 Media referti/giorno: **{media_referti}**")
            st.markdown(f"- 📅 Giorno con più referti: **{max_referti}**")
            st.markdown(f"- 🔬 Tipologia più comune: **{referto_comune}**")
            st.markdown(f"- ⚠️ Decessi (Emergency): **{decessi}**")
            
            # Linear plot numero di referti per giorno
            st.markdown("**📈 Andamento giornaliero dei referti:**")
            
            # Step 1: Recupera dati aggregati dal db (lista di dict con "date" e "count")
            data = self.db.numero_referti_giornalieri(data_start, data_end)
            # Esempio output: [{"date": "2025-06-01", "count": 15}, {"date": "2025-06-02", "count": 20}, ...]

            if not data:
                st.warning("Nessun dato trovato nell'intervallo selezionato.")
                return
            
            # Step 2: Costruisci DataFrame
            df = pd.DataFrame(data)
            df['date'] = pd.to_datetime(df['date'])

            # Step 3: Crea il grafico lineare con Altair
            chart = alt.Chart(df).mark_line(point=True).encode(
                x=alt.X('date:T', title='Data'),
                y=alt.Y('count:Q', title='Numero di referti'),
                tooltip=['date:T', 'count:Q']
            ).properties(
                width=700,
                height=400,
                title="Andamento giornaliero numero di referti"
            ).interactive()

            # Step 4: Mostra con Streamlit
            st.altair_chart(chart)
            
        else:
            st.warning("Seleziona un intervallo di tempo valido.")


    def show_analisi_per_medico(self):
        st.markdown("Analisi aggregate per singolo medico e per reparto.")

        # Top 10 medici per numero di referti
        st.markdown("## **🏆 Top 10 medici per numero di referti:**")
        st.markdown("Visualizza i medici con il maggior numero di referti prodotti.")
        top_medici = self.db.top_medici(limit=10)
        for i, medico in enumerate(top_medici, 1):
            cf = medico['nome_completo'] or "Sconosciuto"
            count = medico['count']
            st.markdown(f"{i}. Dott/Dott.ssa: `{cf}` — Numero referti: {count}")

        # Referti per reparto (grafico)
        st.markdown("## **📊 Numero di referti per reparto:**")
        reparti = self.db.referti_per_reparto()

        if repartis := [r['reparto'] for r in reparti if r['reparto']]:
            counts = [r['count'] for r in reparti if r['reparto']]
            labels = [r['reparto'] for r in reparti if r['reparto']]

            fig, ax = plt.subplots(figsize=(8, 4.5))  # Dimensione più compatta e proporzionata

            ax.bar(labels, counts, color='#4c72b0', edgecolor='black', alpha=0.85)

            ax.set_ylabel('Numero Referti', fontsize=12)
            ax.set_title('Referti per Reparto', fontsize=14, weight='bold')

            plt.xticks(rotation=45, ha='right', fontsize=10)
            plt.yticks(fontsize=10)

            # Rimuovi bordo superiore e destro per uno stile più "pulito"
            ax.spines['top'].set_visible(False)
            ax.spines['right'].set_visible(False)

            # Layout automatico per evitare sovrapposizioni
            plt.tight_layout()

            st.pyplot(fig)

        else:
            st.info("Nessun dato reparto disponibile.")
            
        def mostra_referti_per_fascia(start_date, end_date):
            data = self.db.referti_per_fascia_oraria(start_date, end_date)
            if not data:
                st.info("Nessun dato trovato per l'intervallo selezionato.")
                return

            df = pd.DataFrame(list(data.items()), columns=["Fascia Oraria", "Numero Referti"])

            fig, ax = plt.subplots(figsize=(6, 6))  # Grafico quadrato, dimensioni moderate

            colors = ['#66b3ff', '#99ff99', '#ffcc99', '#ff9999']

            wedges, texts, autotexts = ax.pie(
                df["Numero Referti"],
                labels=df["Fascia Oraria"],
                autopct='%1.1f%%',
                startangle=90,
                colors=colors,
                textprops={'fontsize': 11, 'weight': 'bold', 'color': 'black'}
            )

            ax.set_title("Distribuzione carico di lavoro per fascia oraria nell'ultimo mese", fontsize=14, weight='bold')

            # Migliora la leggibilità delle etichette (sposta un po' le label)
            for text in texts:
                text.set_fontsize(11)
                text.set_weight('bold')

            # Disegna un cerchio al centro per effetto donut (opzionale)
            centre_circle = plt.Circle((0,0),0.70,fc='white')
            fig.gca().add_artist(centre_circle)

            # Assicura che il grafico sia un cerchio perfetto
            ax.axis('equal')

            plt.tight_layout()
            st.pyplot(fig)
            
        st.markdown("## **⏰ Distribuzione dei referti per fascia oraria:**")
        st.markdown("Visualizza la distribuzione dei referti clinici per fascia oraria negli ultimi 30 giorni.")
        
        now = datetime.datetime.now()
        thirty_days_ago = now - datetime.timedelta(days=30)
        
        now = now.strftime("%Y-%m-%d %H:%M:%S")
        thirty_days_ago = thirty_days_ago.strftime("%Y-%m-%d %H:%M:%S")
        
        mostra_referti_per_fascia(thirty_days_ago, now)


    def show_analisi_complesse(self):
        st.markdown("Analisi avanzate sui dati dei referti clinici.")

        st.markdown("### **📅 Referti totali per reparto e giorno della settimana**")
        st.markdown("Visualizza il numero di referti per reparto e giorno della settimana negli ultimi 365 giorni.")

        now_dt = datetime.datetime.now()
        year_ago_dt = now_dt - datetime.timedelta(days=365)

        # Passa date come stringhe nel formato esatto usato in MongoDB
        now_str = now_dt.strftime("%Y-%m-%d %H:%M:%S")
        year_ago_str = year_ago_dt.strftime("%Y-%m-%d %H:%M:%S")

        # Correggi l'ordine: start_date = year_ago, end_date = now
        heatmap = self.db.heatmap_reparto_giorno(year_ago_str, now_str)

        df_heat = pd.DataFrame(heatmap).fillna(0).T

        # Assicurati che le colonne siano tutte presenti, ordinale e riempi missing con 0
        cols_order = [1, 2, 3, 4, 5, 6, 7]
        df_heat = df_heat.reindex(columns=cols_order, fill_value=0)

        day_labels = ['Dom', 'Lun', 'Mar', 'Mer', 'Gio', 'Ven', 'Sab']
        df_heat.columns = day_labels

        plt.figure(figsize=(12, max(4, len(df_heat)*0.4)))
        sns.heatmap(df_heat, annot=True, fmt=".0f", cmap="YlGnBu")
        plt.title("Numero di referti per reparto e giorno della settimana")
        plt.xlabel("Giorno della settimana")
        plt.ylabel("Reparto")
        st.pyplot(plt.gcf())

        st.markdown("### **🔬 Analisi per tipologia di referto**")
        st.markdown("Analizza la stagionalità dei referti per tipo negli ultimi 365 giorni.")
        
        results = self.db.stagionalita_tipo_referto(year_ago_str, now_str)

        # Trasforma in DataFrame
        df = pd.DataFrame(results)

        # Controlla che ci siano risultati
        if df.empty:
            st.write("Nessun dato disponibile per il periodo selezionato.")
        else:
            df["date"] = df["_id"].apply(lambda x: x["date"])
            df["type"] = df["_id"].apply(lambda x: x["type"])
            df["count"] = df["count"]

            # Pivot per avere le date in indice e i tipi come colonne
            df_pivot = df.pivot(index="date", columns="type", values="count").fillna(0)

            # Converti date in datetime
            df_pivot.index = pd.to_datetime(df_pivot.index)

            plt.figure(figsize=(12,6))
            for col in df_pivot.columns:
                plt.plot(df_pivot.index, df_pivot[col], label=col)

            plt.title("Analisi di stagionalità per tipo di referto (ultimi 365 giorni)")
            plt.xlabel("Data")
            plt.ylabel("Numero di referti")
            plt.legend()
            plt.grid(True)

            st.pyplot(plt.gcf())
            
        # PARALLEL COORDINATES PLOT
        st.markdown("### **📊 Analisi parallela per reparto**")
        st.markdown("Visualizza le relazioni tra il totale dei referti, i giorni di lavoro e la media giornaliera per reparto.")
        
        results = self.db.parallel_coords_data(year_ago_str, now_str)

        if not results:
            st.write("Nessun dato disponibile.")
        else:
            df = pd.DataFrame(results)
            
            # Rinomina colonne per comodità
            df.rename(columns={"_id": "Reparto"}, inplace=True)

            # Parallel coordinates plot richiede la colonna con la classe (qui il reparto)
            # Assicuriamoci che le colonne siano tutte numeriche tranne la prima
            df_plot = df[["Reparto", "totale_referti", "giorni_attivi", "media_giornaliera"]].copy()

            plt.figure(figsize=(12,6))
            parallel_coordinates(df_plot, class_column="Reparto", colormap=plt.get_cmap("tab20"))

            plt.title("Analisi parallela su totale referti, giorni di lavoro e media giornaliera per reparto")
            plt.ylabel("Valori aggregati")
            plt.xticks(rotation=45)
            plt.grid(True)
            st.pyplot(plt.gcf())

                    
        
    
    def show_report_admin(self, report):
        st.markdown(f"# 👁️ Visualizza Referto")
        #st.markdown("### Referto del signor/a: " + report["dati paziente"]["nominativo"]["nome"] + " " + report["dati paziente"]["nominativo"]["cognome"] + " Data: " + report["timestamp"])

        with st.container():
            if st.button("⬅️ Torna indietro"):
                st.session_state.page = "admin_dashboard"
                st.rerun()

        st.divider()

        
        if not report:
            st.error("❌ Referto non trovato.")
            return

        if "_id" in report:
            del report["_id"]  # campo non visualizzabile

        def format_key(key):
            """Converte underscore in spazi e mette in maiuscolo ogni parola."""
            return key.replace("_", " ").title()

        def render_read_only_fields(data, parent_key="", level=0):
            excluded_keys = {"validated", "report_id", "dati medico", "timestamp", "type", "Message"}

            col1, col2, col3 = st.columns(3)
            columns = [col1, col2, col3]
            field_counter = 0

            for key, value in data.items():
                if key in excluded_keys:
                    continue

                full_key = f"{parent_key}.{key}" if parent_key else key
                display_key = format_key(key)
                target_col = columns[field_counter % 3]
                field_counter += 1

                header_level = min(5, 3 + level)
                header_prefix = "#" * header_level

                if isinstance(value, dict):
                    st.markdown(f"{header_prefix} 📂 {display_key}")
                    render_read_only_fields(value, full_key, level=level + 1)
                    st.divider()

                elif isinstance(value, list):
                    current_value = "\n".join(str(v) for v in value)
                    line_count = current_value.count("\n") + 1
                    height = min(400, 48 + 20 * line_count)

                    with target_col:
                        st.text_area(
                            f"📋 {display_key}",
                            value=current_value,
                            key=full_key,
                            height=height,
                            disabled=True
                        )

                elif isinstance(value, (int, float)):
                    with target_col:
                        st.number_input(
                            f"🔢 {display_key}",
                            value=value,
                            key=full_key,
                            disabled=True
                        )

                else:
                    str_value = str(value)
                    line_count = str_value.count("\n") + 1
                    height = min(400, 48 + 20 * line_count + len(str_value) // 4)

                    with target_col:
                        if len(str_value) > 50 or "\n" in str_value:
                            st.text_area(
                                f"📄 {display_key}",
                                value=str_value,
                                key=full_key,
                                height=height,
                                disabled=True
                            )
                        else:
                            st.text_input(
                                f"🗒️ {display_key}",
                                value=str_value,
                                key=full_key,
                                disabled=True
                            )

        render_read_only_fields(report)
          
        
    def login(self):
        st.markdown("## 🔐 Login Operatore Sanitario")
        
        with st.container():
            st.markdown(" ⚙️ Seleziona una modalità di funzionamento")
            col1, col2 = st.columns(2)
            with col1:
                st.button(
                    "🚑 Pronto soccorso",
                    key="mode_pronto_soccorso",
                    on_click=lambda: (st.session_state.update({"function_mode": "Pronto Soccorso"}), st.session_state.update({"function_icon": "🚑"})),
                    use_container_width=True
                )
            with col2:
                st.button(
                    "🏥 Reparto",
                    key="mode_reparto",
                    on_click=lambda: (st.session_state.update({"function_mode": "Reparto"}), st.session_state.update({"function_icon": "🏥"})),
                    use_container_width=True
                )
                
                
        with st.container():
            col1, col2 = st.columns(2)
            with col1:
                st.text_input("📧 Email", key="login_email", placeholder="es: mario.rossi@gmail.com")
            with col2:
                st.text_input("🔑 Password", type="password", key="login_password", placeholder="Almeno 8 caratteri")

        st.markdown("")

        if st.button("🚪 Accedi", use_container_width=True):
            if st.session_state.function_mode == "Generic":
                st.error("⚠️ Seleziona una modalità di funzionamento prima di accedere.")
            else:
                user = self.db.get_operator(st.session_state.login_email)
                if user:
                    hashed_password = user["Anagrafica"]["Password"]
                    if isinstance(hashed_password, str):
                        hashed_password = hashed_password.encode('utf-8')

                    if bcrypt.checkpw(st.session_state.login_password.encode('utf-8'), hashed_password):
                        st.session_state.logged_in = True
                        st.session_state.user = user

                        # AGGIUNTA: Ricostruisci la coda Redis se è vuota
                        cf = user["Anagrafica"]["Codice Fiscale"]
                        if not self.db.get_queue_for_doctor(cf):
                            self.db.refresh_queue_for_doctor(cf)

                        st.success(f"✅ Benvenuto, {user['Anagrafica']['Nome']} {user['Anagrafica']['Cognome']}!")
                        time.sleep(2)
                        st.session_state.page = "main"
                        st.rerun()
                    else:
                        st.error("❌ Credenziali non valide")
                else:
                    st.error("❌ Credenziali non valide")

        st.markdown("---")
        
        if st.session_state.function_mode != "Generic":
            st.markdown(f"<div style='text-align: center;'>⚙️ Modalità di funzionamento selezionata: {st.session_state.function_mode} {st.session_state.function_icon}</div>", unsafe_allow_html=True)
            st.markdown("---")
        
        if st.button("📝 Non hai un account? Registrati", use_container_width=True):
            st.session_state.page = "register"
            st.rerun()
        
            
        
        if st.button("🛡️ Vai al login amministratore", use_container_width=True):
            st.session_state.page = "login_amministratore"
            st.rerun()

    def register(self):
        st.markdown("## 📝 Registrazione Nuovo Operatore")

        with st.form("register_form"):
            st.markdown("### 👤 Dati Anagrafici")
            col1, col2 = st.columns(2)
            with col1:
                email = st.text_input("📧 Email")
                password = st.text_input("🔑 Password", type="password")
                nome = st.text_input("🧍 Nome")
                cognome = st.text_input("🧍‍♂️ Cognome")
            with col2:
                cellulare = st.text_input("📱 Cellulare")
                cf = st.text_input("🧾 Codice Fiscale")
                ruolo = st.selectbox("💼 Ruolo", ["Medico", "Infermiere", "Tecnico di laboratorio", "Operatore sanitario"])

            st.markdown("### 🏥 Informazioni Struttura Ospedaliera")
            col3, col4 = st.columns(2)
            with col3:
                nome_struttura = st.text_input("🏢 Nome della Struttura")
                reparto = st.text_input("🏨 Reparto")
            with col4:
                città = st.text_input("📍 Città")
                provincia = st.text_input("🌍 Provincia")
                cap = st.text_input("📬 CAP")

            col_reg, col_back = st.columns(2)
            with col_reg:
                submitted = st.form_submit_button("📌 Registrati")
            with col_back:
                go_back = st.form_submit_button("⬅️ Indietro")

        if go_back:
            st.session_state.page = "login"
            st.rerun()

        if submitted:
            # Validazione
            email_pattern = r"^[\w\.-]+@(?:gmail\.com|yahoo\.com|libero\.it|outlook\.com|hotmail\.com|icloud\.com)$"
            password_pattern = r"^(?=.*[.,!&#]).{8,16}$"
            cf_pattern = r"^[A-Z]{6}[0-9]{2}[A-Z][0-9]{2}[A-Z][0-9]{3}[A-Z]$"

            if not re.match(email_pattern, email):
                st.error("📧 Inserisci un'email valida (es. @gmail.com, @libero.it, ecc.)")
            elif not re.match(password_pattern, password):
                st.error("🔑 La password deve essere lunga 8-16 caratteri e contenere almeno uno tra: . , ! & #")
            elif not nome.strip() or not cognome.strip():
                st.error("❗ Nome e Cognome non possono essere vuoti.")
            elif not cellulare.isdigit() or not (10 <= len(cellulare) <= 11):
                st.error("📱 Il cellulare deve contenere 10 o 11 cifre.")
            elif not re.match(cf_pattern, cf.upper()):
                st.error("🧾 Codice Fiscale non valido. Deve seguire il formato italiano (16 caratteri).")
            elif not nome_struttura.strip() or not reparto.strip() or not città.strip() or not provincia.strip() or not cap.strip():
                st.error("🏥 Tutti i campi relativi alla struttura devono essere compilati.")
            elif not cap.isdigit() or len(cap) != 5:
                st.error("📬 Il CAP deve essere un numero di 5 cifre.")
            elif self.db.get_operator(email):
                st.error("📧 Email già registrata.")
            elif self.db.db.operatori.find_one({"Codice Fiscale": cf.upper()}):
                st.error("🧾 Codice fiscale già registrato.")
            else:
                new_user = {
                    "Anagrafica": {
                        "Email":email,
                        "Password":password,
                        "Nome":nome,
                        "Cognome":cognome,
                        "Cellulare":cellulare,
                        "Codice Fiscale":cf,
                        "Ruolo":ruolo,  # ad esempio "Medico", "Infermiere", etc.
                    
                    },
                    "Ospedale": {
                        "Nome Ospedale":nome_struttura,
                        "Città":città,
                        "Provincia":provincia,
                        "CAP":cap,
                        "Reparto":reparto,
                    }    
                } 
                self.db.insert_operator(new_user)
                st.success("✅ Registrazione completata! Ora puoi effettuare il login.")
                time.sleep(2)
                st.session_state.page = "login"
                st.rerun()

    

    def main_page(self):
        st.markdown("## 🏠 Clinical report AI Assistant")

        # Recupero dati operatore
        user = st.session_state.get("user", {})
        anagrafica = user.get("anagrafica", {})
        nome = anagrafica.get("name", "")
        cognome = anagrafica.get("surname", "")
        medico_cf = anagrafica.get("CF", "")

        
        st.markdown("---")
        st.markdown("### 🗂️ Riepilogo referti dei tuoi pazienti")

        try:
            # Recupero tutti i referti del medico attualmente loggato
            self.db.refresh_queue_for_doctor(st.session_state.user["Anagrafica"]["Codice Fiscale"])
            reports = self.db.get_all_clinical_reports_by_doctor_cf(st.session_state.user["Anagrafica"]["Codice Fiscale"])
            # Ordina i referti per data (più recente prima)
            reports.sort(key=lambda x: x.get("timestamp", ""), reverse=True)


            if not reports:
                st.warning("🔍 Non ci sono referti associati al codice fiscale: " + st.session_state.user["Anagrafica"]["Codice Fiscale"])
            else:
                # Raggruppa per nome paziente
                grouped = {}
                for report in reports:
                    paziente = report["dati paziente"]["nominativo"]["cognome"] + " " + report["dati paziente"]["nominativo"]["nome"]
                    grouped.setdefault(paziente, []).append(report)
                
                # Ordina i pazienti per cognome 
                grouped = dict(sorted(grouped.items(), key=lambda item: item[0].split()[-1].lower()))

                for paziente, referti in grouped.items():
                    with st.expander(f"🧑‍⚕️ Paziente: {paziente} ({len(referti)} referti)"):
                        for referto in referti:
                            st.markdown(f"""
                            - 🩺 {referto.get('type', 'N/A')}
                            - 📄 **ID Referto**: `{referto.get('_id', 'N/A')}`
                            - 🗓️ **Data**: {referto.get('timestamp', 'N/A')}
                            """)
                            with st.container():
                                col1, col2, col3, col4 = st.columns(4)
                                with col3: 
                                    delete_key = f"delete_{referto.get('_id')}"
                                    confirm_key = f"confirm_delete_{referto.get('_id')}"

                                    if st.button("❌ Cancella Referto", key=delete_key):
                                        st.session_state[confirm_key] = True

                                    if st.session_state.get(confirm_key, False):
                                        st.warning("⚠️ Sei sicuro di voler cancellare questo referto?")
                                        col_confirm, col_cancel = st.columns(2)
                                        with col_confirm:
                                            if st.button("✅ Conferma", key=f"confirm_{referto.get('_id')}"):
                                                self.db.delete_clinical_report(referto.get('_id'))
                                                self.db.refresh_queue_for_doctor(st.session_state.user["Anagrafica"]["Codice Fiscale"])
                                                del st.session_state[confirm_key]
                                                st.session_state.deleted = True
                                                st.rerun()
                                        with col_cancel:
                                            if st.button("❎ Annulla", key=f"cancel_{referto.get('_id')}"):
                                                del st.session_state[confirm_key]
                                                st.rerun()

                                
                                with col2: 
                                    st.button(
                                    "✏️ Modifica Referto",
                                    key = f"modify_{referto.get('_id')}",
                                    on_click= self.modify_report,
                                    args = (referto.get('_id'),),
                                    )
                                
                                with col1:
                                    st.button(
                                    "👁️ Visualizza Referto",
                                    key = f"show_{referto.get('_id')}",
                                    on_click=self.show_report,
                                    args = (referto.get('_id'),),
                                    )
                                
                                with col4:
                                    report_id = str(referto.get('_id'))  # 👈 converto in stringa
                                    download_key = f"trigger_download_{report_id}"

                                    if st.button("📥 Scarica Referto", key=f"btn_{report_id}"):
                                        st.session_state[f"download_pdf_{report_id}"] = True

                                    if st.session_state.get(f"download_pdf_{report_id}", False):
                                        report_to_download = self.get_report_by_id(report_id)
                                        try:
                                            pdf_data, file_name = self.download_report(report_to_download)  # 👈 già convertito in str
                                            if pdf_data:
                                                st.download_button(
                                                    label="⬇️ Clicca per scaricare",
                                                    data=pdf_data,
                                                    file_name=file_name,
                                                    mime="application/pdf",
                                                    key=f"download_btn_{report_id}"
                                                )
                                            else:
                                                st.warning("⚠️ Referto non disponibile. Il PDF non è stato generato correttamente.")
                                        except Exception as e:
                                            st.warning(f"⚠️ Referto non disponibile. Errore durante la generazione del PDF: {str(e)}")
        except Exception as e:
            st.error(f"❌ Errore nel recupero dei referti: {str(e)}")

        if st.session_state.deleted:
            st.session_state.deleted = False
            st.rerun()
    
    def format_key_text(self, s: str) -> str:
        # Sostituisce underscore con spazi e capitalizza parole
        parts = s.split('_')
        # Maiuscola solo la prima lettera di ogni parola tranne se è una preposizione/articolo breve
        # (qui semplice capitalizzazione per tutte parole)
        return ' '.join(p.capitalize() for p in parts)

    def download_report(self, report):
        try:
            exclude_keys = {"_id", "report_id", "validated", "timestamp", "type"}

            # --- GESTIONE ROBUSTA DATI PAZIENTE ---
            dati_paziente = report.get("dati paziente", {})
            if not dati_paziente and "scheda_ps" in report:
                dati_paziente = report.get("scheda_ps", {}).get("Dati Paziente", {})

            nominativo = dati_paziente.get("nominativo", {})
            nome_paziente = nominativo.get("nome", dati_paziente.get("Nome", "Sconosciuto"))
            cognome_paziente = nominativo.get("cognome", dati_paziente.get("Cognome", "Sconosciuto"))

            # --- GESTIONE ROBUSTA DATI MEDICO ---
            dati_medico = report.get("dati medico", {})
            nome_medico = dati_medico.get("nome", dati_medico.get("Nome", "Sconosciuto"))
            cognome_medico = dati_medico.get("cognome", dati_medico.get("Cognome", "Sconosciuto"))
            codice_fiscale = dati_medico.get("codice fiscale", dati_medico.get("Codice Fiscale", "Sconosciuto"))

            # Data referto dalla stringa timestamp (formato "YYYY-MM-DD HH:MM:SS")
            timestamp_str = report.get("timestamp", "")
            try:
                data_referto = datetime.datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S").date()
            except:
                data_referto = "data_sconosciuta"

            file_name = f"{nome_paziente}_{cognome_paziente}_{data_referto}.pdf".replace(" ", "_")

            buffer = io.BytesIO()
            doc = SimpleDocTemplate(buffer, pagesize=A4,
                                    rightMargin=50, leftMargin=50,
                                    topMargin=50, bottomMargin=50)

            styles = getSampleStyleSheet()
            title_style = ParagraphStyle('titleStyle', parent=styles['Title'], alignment=TA_CENTER, fontSize=18, spaceAfter=15)
            section_style = ParagraphStyle('sectionStyle', parent=styles['Heading2'], fontSize=14, spaceBefore=12, spaceAfter=8)
            sub_section_style = ParagraphStyle('subSectionStyle', parent=styles['Heading3'], fontSize=12, spaceBefore=8, spaceAfter=6)
            normal_style = styles['BodyText']
            normal_style.spaceAfter = 6

            story = []

            # 1) Titolo come prima riga
            tipo_referto = report.get("type", "")
            if tipo_referto == "Ospedale":
                story.append(Paragraph("Referto Ospedaliero", title_style))
            elif tipo_referto == "Emergency":
                story.append(Paragraph("Referto di Pronto Soccorso", title_style))
            else:
                story.append(Paragraph("Referto Clinico", title_style))

            story.append(Spacer(1, 20))

            # 2) Anagrafiche medico e paziente in rettangoli affiancati
            medico_info = [
                [Paragraph("<b>Dati Medico</b>", section_style)],
                [Paragraph(f"Nome: {nome_medico}", normal_style)],
                [Paragraph(f"Cognome: {cognome_medico}", normal_style)],
                [Paragraph(f"Codice Fiscale: {codice_fiscale}", normal_style)],
            ]
            paziente_info = [
                [Paragraph("<b>Dati Paziente</b>", section_style)],
                [Paragraph(f"Nome: {nome_paziente}", normal_style)],
                [Paragraph(f"Cognome: {cognome_paziente}", normal_style)],
                [Paragraph(f"Data Referto: {str(data_referto)}", normal_style)],
            ]

            table_medico = Table(medico_info, colWidths=[doc.width/2 - 10])
            table_medico.setStyle(TableStyle([
                ('BOX', (0, 0), (-1, -1), 1, colors.darkblue),
                ('BACKGROUND', (0, 0), (-1, 0), colors.lightblue),
                ('LEFTPADDING', (0, 0), (-1, -1), 8),
                ('RIGHTPADDING', (0, 0), (-1, -1), 8),
                ('TOPPADDING', (0, 0), (-1, -1), 6),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ]))

            table_paziente = Table(paziente_info, colWidths=[doc.width/2 - 10])
            table_paziente.setStyle(TableStyle([
                ('BOX', (0, 0), (-1, -1), 1, colors.darkgreen),
                ('BACKGROUND', (0, 0), (-1, 0), colors.lightgreen),
                ('LEFTPADDING', (0, 0), (-1, -1), 8),
                ('RIGHTPADDING', (0, 0), (-1, -1), 8),
                ('TOPPADDING', (0, 0), (-1, -1), 6),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ]))

            info_row = Table([[table_medico, table_paziente]], colWidths=[doc.width/2, doc.width/2])
            info_row.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('LEFTPADDING', (0, 0), (-1, -1), 0),
                ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ]))

            story.append(info_row)
            story.append(Spacer(1, 25))

            # 3) Funzione ricorsiva per il contenuto con rettangoli per le macro-categorie
            def print_dict(d, level=0):
                exclude_keys_local = exclude_keys.union({"dati paziente", "dati medico"})
                for key, value in d.items():
                    if key in exclude_keys_local:
                        continue
                    key_text = self.format_key_text(key)
                    indent = 10 * level
                    if isinstance(value, dict):
                        if level == 0:
                            section_content = []
                            section_content.append(Paragraph(f"<b>{key_text}</b>", section_style))
                            section_content.append(Spacer(1, 8))
                            inner_content = inner_print(value, level + 1)
                            section_content.extend(inner_content)
                            table = Table([[section_content]], colWidths=[doc.width])
                            table.setStyle(TableStyle([
                                ('BOX', (0, 0), (-1, -1), 1.2, colors.darkblue),
                                ('BACKGROUND', (0, 0), (-1, -1), colors.whitesmoke),
                                ('LEFTPADDING', (0, 0), (-1, -1), 12),
                                ('RIGHTPADDING', (0, 0), (-1, -1), 12),
                                ('TOPPADDING', (0, 0), (-1, -1), 12),
                                ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
                                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                            ]))
                            story.append(table)
                            story.append(Spacer(1, 15))
                        else:
                            story.append(Indenter(left=indent))
                            style = sub_section_style if level == 1 else normal_style
                            story.append(Paragraph(f"<b>{key_text}</b>", style))
                            print_dict(value, level + 1)
                            story.append(Indenter(left=-indent))
                    elif isinstance(value, list):
                        story.append(Indenter(left=indent))
                        story.append(Paragraph(f"<b>{key_text}</b>", normal_style))
                        for item in value:
                            if isinstance(item, dict):
                                print_dict(item, level + 1)
                            else:
                                story.append(Paragraph(f"- {str(item)}", normal_style))
                        story.append(Indenter(left=-indent))
                    else:
                        val_str = str(value) if value is not None else ""
                        story.append(Indenter(left=indent))
                        story.append(Paragraph(f"<b>{key_text}:</b> {val_str}", normal_style))
                        story.append(Indenter(left=-indent))

            def inner_print(d, level=1):
                content = []
                indent = 10 * level
                for k, v in d.items():
                    if k in exclude_keys or k in ("timestamp", "type", "dati paziente", "dati medico"):
                        continue
                    key_text = self.format_key_text(k)
                    if isinstance(v, dict):
                        content.append(Indenter(left=indent))
                        content.append(Paragraph(f"<b>{key_text}</b>", sub_section_style if level == 1 else normal_style))
                        content.extend(inner_print(v, level + 1))
                        content.append(Indenter(left=-indent))
                    elif isinstance(v, list):
                        content.append(Indenter(left=indent))
                        content.append(Paragraph(f"<b>{key_text}</b>", normal_style))
                        for item in v:
                            if isinstance(item, dict):
                                content.extend(inner_print(item, level + 1))
                            else:
                                content.append(Paragraph(f"- {str(item)}", normal_style))
                        content.append(Indenter(left=-indent))
                    else:
                        val_str = str(v) if v is not None else ""
                        content.append(Indenter(left=indent))
                        content.append(Paragraph(f"<b>{key_text}:</b> {val_str}", normal_style))
                        content.append(Indenter(left=-indent))
                return content

            # --- SELEZIONE CONTENUTO DA STAMPARE ---
            if report.get("type") == "Emergency" and "scheda_ps" in report:
                filtered_report = report["scheda_ps"]
            elif "clinical_report" in report:
                filtered_report = report["clinical_report"]
            else:
                filtered_report = {k: v for k, v in report.items() if k not in exclude_keys and k not in ("timestamp", "type")}

            print_dict(filtered_report)

            doc.build(story)
            buffer.seek(0)
            pdf_bytes = buffer.getvalue()
            return pdf_bytes, file_name

        except Exception as e:
            print(f"Errore nella generazione del PDF: {e}")
            return None, None

    def _convert_object_ids(self, obj):
        if isinstance(obj, dict):
            return {k: self._convert_object_ids(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._convert_object_ids(v) for v in obj]
        elif str(type(obj)).endswith("ObjectId'>"):
            return str(obj)
        return obj
        
        
    def sidebar(self):
        st.sidebar.markdown("## 👤 Anagrafica Operatore")

        if st.session_state.logged_in:
            #TODO : mostrare i dati anagrafici dell'operatore e il nome dell'ospedale
            operator = st.session_state.user["Anagrafica"]["Nome"] + " " + st.session_state.user["Anagrafica"]["Cognome"]
            operator_cf = st.session_state.user["Anagrafica"]["Codice Fiscale"]
            operator_email = st.session_state.user["Anagrafica"]["Email"]
            role = st.session_state.user["Anagrafica"]["Ruolo"]
            ospedale = st.session_state.user["Ospedale"]["Nome Ospedale"]
            with st.sidebar.container(border=True):
                st.markdown(f"👤 **Operatore:** {operator}")
                st.markdown(f"🧾 **CF:** {operator_cf}")
                st.markdown(f"📧 **Email:** {operator_email}")
                st.markdown(f"💼 **Ruolo:** {role}")
                st.markdown(f"🏥 **Ospedale:** {ospedale}")
                st.markdown(f"⚙️ **Modalità di funzionamento:** {st.session_state.function_mode} {st.session_state.function_icon}")
                if st.button("🔄 Swap", use_container_width=True):
                    if st.session_state.function_mode == "Pronto Soccorso":
                        st.session_state.function_mode = "Reparto"
                        st.session_state.function_icon = "🏥"
                    else:
                        st.session_state.function_mode = "Pronto Soccorso"
                        st.session_state.function_icon = "🚑"
                    st.rerun()
                
        else:
            with st.sidebar.container(border=True):
                st.markdown("🔒 <span style='color:gray'>Non sei loggato.</span>", unsafe_allow_html=True)


        st.sidebar.markdown("---")
        
        audio_file = st.sidebar.audio_input("🎤 Registra Audio", key="mic_recorder")

        if audio_file is not None:
            filename = self.save_audio_file_from_upload(audio_file)
            st.sidebar.success(f"✅ Registrazione salvata: {filename}")

            with st.spinner("Creazione referto in corso..."):
                self.new_report(filename)

            if st.session_state.report_ready:
                report = st.session_state.last_report
                if "Error" in report:
                    st.sidebar.error(f"❌ Errore: {report['Error']}")
                else:
                    st.sidebar.success(f"✅ Referto creato con ID: {report.get('_id', 'N/A')}")
                    time.sleep(2)
            else:
                st.sidebar.error("❌ Errore durante il salvataggio.")

        st.sidebar.markdown("---")

        if st.sidebar.button("📂 Esplora Referti", use_container_width=True):
            st.session_state.page = "query_report"
            st.rerun()
                
                
        if st.sidebar.button("🔄 Ricarica", use_container_width=True):
            st.rerun()
            
        if st.sidebar.button("🔒 Logout", use_container_width=True):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()
    def report_modify_page(self, report_id="6835d760cdc5c3eb8dec00f7"):
        if st.session_state.validate:
            stringa = "Valida"
        else:
            stringa = "Modifica"
        st.markdown(f"# ✏️ {stringa} Referto Clinico")
            

        # Ottieni il referto dal database
        report = self.get_report_by_id(report_id)

        if not report:
            st.error("❌ Referto non trovato.")
            return

        if "_id" in report:
            del report["_id"]  # campo non modificabile
        
        

        updated_report = {}

        def format_key(key):
            """Converte underscore in spazi e mette in maiuscolo ogni parola."""
            return key.replace("_", " ").title()

        def render_edit_fields(data, parent_key="", level=0, invalid_paths=None):
            updated_data = {}
            excluded_keys = {"validated", "report_id", "dati medico", "timestamp", "type", "Message", "codice_fiscale"}
            invalid_paths = invalid_paths or set()

            col1, col2, col3 = st.columns(3)
            columns = [col1, col2, col3]
            field_counter = 0

            for key, value in data.items():
                if key in excluded_keys:
                    continue

                full_key = f"{parent_key}.{key}" if parent_key else key
                display_key = key.replace("_", " ").title()

                if full_key in invalid_paths:
                    display_key = f"❌ {display_key}"
                    help_text = "Questo campo è obbligatorio."
                else:
                    help_text = None

                target_col = columns[field_counter % 3]
                field_counter += 1

                header_level = min(5, 3 + level)
                header_prefix = "#" * header_level

                if isinstance(value, dict):
                    st.markdown(f"{header_prefix} 🔹 {display_key}")
                    updated_data[key] = render_edit_fields(value, full_key, level=level + 1, invalid_paths=invalid_paths)
                    st.divider()

                elif isinstance(value, list):
                    current_value = "\n".join(str(v) for v in value)
                    line_count = current_value.count("\n") + 1
                    height = min(400, 48 + 20 * line_count)

                    with target_col:
                        edited_value = st.text_area(
                            f"🗒️ {display_key}",
                            value=current_value,
                            key=full_key,
                            height=height,
                            help=help_text
                        )
                    updated_data[key] = [v.strip() for v in edited_value.splitlines() if v.strip()]

                elif isinstance(value, (int, float)):
                    with target_col:
                        new_val = st.number_input(
                            f"🔢 {display_key}",
                            value=value,
                            key=full_key,
                            help=help_text
                        )
                    updated_data[key] = new_val

                else:
                    str_value = str(value)
                    line_count = str_value.count("\n") + 1
                    height = min(400, 48 + 20 * line_count + len(str_value) // 4)

                    with target_col:
                        if len(str_value) > 50 or "\n" in str_value:
                            new_val = st.text_area(
                                f"✏️ {display_key}",
                                value=str_value,
                                key=full_key,
                                height=height,
                                help=help_text
                            )
                        else:
                            new_val = st.text_input(
                                f"✏️ {display_key}",
                                value=str_value,
                                key=full_key,
                                help=help_text
                            )
                    updated_data[key] = new_val

            return updated_data



        def check_patient_data_validity(dati_paziente: dict) -> list:
            """
            Verifica che tutti i campi di 'dati paziente' (anche annidati) siano validi.
            Restituisce una lista dei campi mancanti o invalidi.
            """
            invalid_fields = []

            def recursive_check(d, path=""):
                for k, v in d.items():
                    if k == "dati_dichiarati_da":
                        continue
                    current_path = f"{path}.{k}" if path else k
                    if isinstance(v, dict):
                        recursive_check(v, current_path)
                    else:
                        if str(v).strip() == "" or str(v).strip().upper() == "N/A":
                            invalid_fields.append(current_path)

            recursive_check(dati_paziente)
            return invalid_fields

        if codicefiscale.is_valid(report["dati paziente"]["codice_fiscale"]):
            st.session_state.cf = report["dati paziente"]["codice_fiscale"]
        updated_report = render_edit_fields(report)
        
        # --- BLOCCO CODICE FISCALE IN EVIDENZA ---

        st.markdown("### 🧾 Calcolo Codice Fiscale del Paziente")
        st.info("""ℹ️ Per calcolare correttamente il codice fiscale, inserisci prima: \n
        - Nome e Cognome del paziente \n
        - Sesso (usa 'M' per Maschio o 'F' per Femmina) \n
        - Data di nascita nel formato '25/06/1975' \n 
        - Luogo di nascita (nome della città)
        """)

        cf_value = report.get("dati paziente", {}).get("codice_fiscale", "") if st.session_state.cf == "" else st.session_state.cf
        cf_key = "codice_fiscale_main"
        new_cf = st.text_input("🧾 Codice Fiscale", value=cf_value, key=cf_key, disabled= True)

        if st.button("🔐 Calcola Codice Fiscale", key="calcola_cf_main"):
            try:
                nome = updated_report.get("dati paziente", {}).get("nominativo", {}).get("nome", "").strip()
                cognome = updated_report.get("dati paziente", {}).get("nominativo", {}).get("cognome", "").strip()
                sesso = updated_report.get("dati paziente", {}).get("sesso", "").strip().upper()
                data_nascita = updated_report.get("dati paziente", {}).get("data_nascita", "").strip()
                luogo_nascita = updated_report.get("dati paziente", {}).get("luogo_nascita", {}).get("città", "").strip()

                try:
                    try:
                        data_iso = datetime.datetime.strptime(data_nascita, "%d %B %Y").strftime("%Y-%m-%d")
                    except ValueError:
                        data_iso = datetime.datetime.strptime(data_nascita, "%d/%m/%Y").strftime("%Y-%m-%d")
                except ValueError:
                    st.error("⚠️ Data di nascita non valida. Usa il formato '25/06/1975'")
                    data_iso = None

                if all([nome, cognome, sesso in ["M", "F"], data_iso, luogo_nascita]):
                    cf = codicefiscale.encode(
                        lastname=cognome,
                        firstname=nome,
                        gender=sesso,
                        birthdate=data_iso,
                        birthplace=luogo_nascita
                    )
                    st.session_state.cf = cf
                    st.rerun()
                else:
                    st.error("⚠️ Completa tutti i campi anagrafici prima di calcolare il codice fiscale.")

            except Exception as e:
                st.error(f"❌ Errore nel calcolo del codice fiscale: {e}")

        st.markdown("---")
        # --- FINE BLOCCO CODICE FISCALE ---

        if st.button("💾 Salva Modifiche"):
            
            updated_report["dati paziente"]["codice_fiscale"] = st.session_state.cf 
            st.session_state.cf = ""
            # Validazione campi "dati paziente"
            if "dati paziente" not in updated_report:
                st.error("❌ Campo 'dati paziente' mancante.")
                return

            invalid_fields = check_patient_data_validity(updated_report["dati paziente"])

            if invalid_fields:
                st.error("⚠️ I seguenti campi del paziente sono obbligatori e non possono essere vuoti o 'N/A':")
                for f in invalid_fields:
                    st.markdown(f"- `{f}`")
                return

            updated_report["validated"] = True
            numero_modifiche = self.db.update_clinical_report(report_id, updated_report)
            self.db.refresh_queue_for_doctor(st.session_state.user["Anagrafica"]["Codice Fiscale"])
            st.session_state.validate = False
            st.success("✅ Referto aggiornato con successo!")
            time.sleep(2)
            st.session_state.page = "main"
            st.rerun()



    def show_report_page(self, report_id="6835d760cdc5c3eb8dec00f7"):
        report = self.get_report_by_id(report_id)
        st.markdown(f"# 👁️ Visualizza Referto")
        #st.markdown("### Referto del signor/a: " + report["dati paziente"]["nominativo"]["nome"] + " " + report["dati paziente"]["nominativo"]["cognome"] + " Data: " + report["timestamp"])

        with st.container():
            if st.button("⬅️ Torna indietro"):
                st.session_state.page = "main"
                st.rerun()

        st.divider()

        
        if not report:
            st.error("❌ Referto non trovato.")
            return

        if "_id" in report:
            del report["_id"]  # campo non visualizzabile

        def format_key(key):
            """Converte underscore in spazi e mette in maiuscolo ogni parola."""
            return key.replace("_", " ").title()

        def render_read_only_fields(data, parent_key="", level=0):
            excluded_keys = {"validated", "report_id", "dati medico", "timestamp", "type", "Message"}

            col1, col2, col3 = st.columns(3)
            columns = [col1, col2, col3]
            field_counter = 0

            for key, value in data.items():
                if key in excluded_keys:
                    continue

                full_key = f"{parent_key}.{key}" if parent_key else key
                display_key = format_key(key)
                target_col = columns[field_counter % 3]
                field_counter += 1

                header_level = min(5, 3 + level)
                header_prefix = "#" * header_level

                if isinstance(value, dict):
                    st.markdown(f"{header_prefix} 📂 {display_key}")
                    render_read_only_fields(value, full_key, level=level + 1)
                    st.divider()

                elif isinstance(value, list):
                    current_value = "\n".join(str(v) for v in value)
                    line_count = current_value.count("\n") + 1
                    height = min(400, 48 + 20 * line_count)

                    with target_col:
                        st.text_area(
                            f"📋 {display_key}",
                            value=current_value,
                            key=full_key,
                            height=height,
                            disabled=True
                        )

                elif isinstance(value, (int, float)):
                    with target_col:
                        st.number_input(
                            f"🔢 {display_key}",
                            value=value,
                            key=full_key,
                            disabled=True
                        )

                else:
                    str_value = str(value)
                    line_count = str_value.count("\n") + 1
                    height = min(400, 48 + 20 * line_count + len(str_value) // 4)

                    with target_col:
                        if len(str_value) > 50 or "\n" in str_value:
                            st.text_area(
                                f"📄 {display_key}",
                                value=str_value,
                                key=full_key,
                                height=height,
                                disabled=True
                            )
                        else:
                            st.text_input(
                                f"🗒️ {display_key}",
                                value=str_value,
                                key=full_key,
                                disabled=True
                            )

        render_read_only_fields(report)
    
        
    def run(self):
        if st.session_state.logged_in:
            if st.session_state.page == "main":
                self.sidebar()
                self.main_page()
            elif st.session_state.page == "query_report":
                self.filtra_referti()
            elif st.session_state.page == "completa_registrazione_admin":
                self.completa_registrazione_admin()
            elif st.session_state.page == "report_modify":
                self.report_modify_page(st.session_state.last_report["_id"])
            elif st.session_state.page == "show_report":
                self.show_report_page(st.session_state.last_report["_id"])
            elif st.session_state.page == "admin_dashboard":
                self.admin_dashboard()
            elif st.session_state.page == "show_report_admin":
                self.show_report_admin(st.session_state.admin_report_to_show)
            elif st.session_state.page == "analytics":
                self.analytics()
            elif st.session_state.page == "register_admin":
                self.registra_amministratore()
        else:
            if st.session_state.page == "login":
                self.login()
            elif st.session_state.page == "login_amministratore":
                self.login_amministratore()
            elif st.session_state.page == "register":
                self.register()


if __name__ == "__main__":
    dashboard = Dashboard()
    dashboard.run()
