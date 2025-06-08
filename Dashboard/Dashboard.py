import streamlit as st
import bcrypt
import os
import sys
import time
import re
import dotenv

import requests
import threading
from codicefiscale import codicefiscale
import datetime
import locale

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from Database.mongodb import DB
from audio_recorder import AudioRecorder

class Dashboard:
    def __init__(self, env_file="key.env"):
        if "deleted" not in st.session_state:
            st.session_state.deleted = False
        if "db" not in st.session_state:
            st.session_state.db = DB()  # salva l'istanza nella sessione
        self.db = st.session_state.db
        if "page" not in st.session_state:
            st.session_state.page = "login"
        if "logged_in" not in st.session_state:
            st.session_state.logged_in = False
        if "audio_recorder" not in st.session_state:
            st.session_state.audio_recorder = AudioRecorder()
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
        
        try:
            locale.setlocale(locale.LC_ALL, 'it_IT.UTF-8')
        except locale.Error:
            # Se la localizzazione italiana non è disponibile, usa una fallback
            locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')
            
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
                                            st.experimental_rerun()
                                    with col_cancel:
                                        if st.button("❎ Annulla", key=f"cancel_{referto.get('_id')}"):
                                            del st.session_state[confirm_key]
                                            st.experimental_rerun()

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
        
        with st.sidebar:
            with st.container():
                if st.button("🔙 Torna indietro", use_container_width=True):
                    st.session_state.page = "admin_dashboard"
                    st.rerun()
    
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
        st.markdown("## 🏠 Inserire nome APP")

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
        except Exception as e:
            st.error(f"❌ Errore nel recupero dei referti: {str(e)}")

        if st.session_state.deleted:
            st.session_state.deleted = False
            st.rerun()
        
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
        
        is_recording = st.session_state.get("is_recording", False)

        if not is_recording:
            # Mostra il bottone "Nuovo Referto"
            if st.sidebar.button("➕ Nuovo Referto", use_container_width=True):
                self.start_audio_recording()
                st.session_state.is_recording = True
                st.rerun()  # ricarica la pagina per aggiornare UI
        else:
            # Mostra bottone "Termina registrazione" e spinner di registrazione in corso
            st.sidebar.markdown("### 🎙️ Registrazione in corso...")
            if st.sidebar.button("⏹️ Termina registrazione", use_container_width=True):
                filename = self.stop_audio_recording()
                st.session_state.is_recording = False
                if filename:
                    st.sidebar.success(f"✅ Registrazione salvata: {filename}")
                    with st.spinner("Creazione referto in corso..."):
                        self.new_report(filename)
                    if st.session_state.report_ready:
                        report = st.session_state.last_report
                        if "Error" in report:
                            st.sidebar.error(f"❌ Errore: {report['Error']}")
                        else:
                            st.sidebar.success(f"✅ Referto creato con ID: {report.get('_id', 'N/A')}")
                            time.sleep(2)  # Attendi un attimo per mostrare il messaggio
                                
                        
                    else:
                        st.sidebar.error("❌ Errore durante il salvataggio.")
                    st.rerun()  # ricarica pagina per aggiornare UI
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
