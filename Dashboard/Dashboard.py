import streamlit as st
import bcrypt
import os
import sys
import time
import re
import dotenv

import requests
import threading


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
            st.session_state.function_mode = "Emergency"
        
        
        # Imposta l'environment variable per FastAPI
        dotenv.load_dotenv(env_file, override=True)
        
        self.controller_url = os.getenv('CONTROLLER_URL', 'http://127.0.0.1:8003')
        
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

        
    def modify_report(self, report_id):
        
        id = str(report_id)
        
        response = requests.post(
            url = f"{self.controller_url}/get_report_by_id",
            json = {
                "text": id
            }
        )
        if response.status_code == 200:
            report =  response.json()
            report = report["report"]
            st.session_state.last_report = report
            st.session_state.page = "report_modify"
        
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
            print(report)
            st.session_state.last_report = report["report"]
            st.session_state.page = "show_report"
        
    def new_report(self, filename):
        response = requests.post(
            url=f"{self.controller_url}/new_report",
            json = {
                "text": filename,
                "anagrafica_medico": self.genera_anagrafica(st.session_state.user)
            })
        
        st.session_state.report_ready = False
        
        if response.status_code == 200:
            id = response.json().get("report_id")
            report = self.db.get_report_by_id(id)
            st.session_state.last_report = report
            st.session_state.report_ready = True
            st.session_state.page = "report_modify"
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

    def login(self):
        st.markdown("## 🔐 Login Operatore Sanitario")
        with st.container():
            col1, col2 = st.columns(2)
            with col1:
                st.text_input("📧 Email", key="login_email", placeholder="es: mario.rossi@gmail.com")
            with col2:
                st.text_input("🔑 Password", type="password", key="login_password", placeholder="Almeno 8 caratteri")

        st.markdown("")

        if st.button("🚪 Accedi", use_container_width=True):
            user = self.db.get_operator(st.session_state.login_email)
            if user:
                hashed_password = user["Anagrafica"]["Password"]
                if isinstance(hashed_password, str):
                    hashed_password = hashed_password.encode('utf-8')

                if bcrypt.checkpw(st.session_state.login_password.encode('utf-8'), hashed_password):
                    st.session_state.logged_in = True
                    st.session_state.user = user
                    st.success(f"✅ Benvenuto, {user['Anagrafica']['Nome']} {user['Anagrafica']['Cognome']}!")
                    time.sleep(2)
                    st.session_state.page = "main"
                    st.rerun()
                else:
                    st.error("❌ Credenziali non valide")
            else:
                st.error("❌ Credenziali non valide")

        st.markdown("---")
        if st.button("📝 Non hai un account? Registrati", use_container_width=True):
            st.session_state.page = "register"
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
            reports = self.db.get_all_clinical_reports_by_doctor_cf(st.session_state.user["Anagrafica"]["Codice Fiscale"])
            if not reports:
                st.warning("🔍 Non ci sono referti associati al codice fiscale: " + st.session_state.user["Anagrafica"]["Codice Fiscale"])
            else:
                # Raggruppa per nome paziente
                grouped = {}
                for report in reports:
                    paziente = report["dati paziente"]["nominativo"]["nome"] + report["dati paziente"]["nominativo"]["cognome"]
                    grouped.setdefault(paziente, []).append(report)

                for paziente, referti in grouped.items():
                    with st.expander(f"🧑‍⚕️ Paziente: **{paziente}** ({len(referti)} referti)"):
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
                                    args = (report.get('_id'),),
                                    )
        except Exception as e:
            st.error(f"❌ Errore nel recupero dei referti: {str(e)}")

        if st.session_state.deleted:
            st.session_state.deleted = False
            st.rerun()
        
        st.markdown("---")
        if st.button("🚪 Logout", use_container_width=True):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()
            
    def sidebar(self):
        st.sidebar.markdown("### 📋 Modalità di funzionamento")
        col1, col2 = st.sidebar.columns(2)
        
        with col1:
            st.sidebar.button(
                "🚑 Emergenza",
                key="emergency_mode",
                on_click=lambda: st.session_state.update({"function_mode": "Emergency"})
            )
        
        with col2:
            st.sidebar.button(
                "🏥 Ordinaria",
                key="ordinary_mode",
                on_click=lambda: st.session_state.update({"function_mode": "Ordinary"})
            )
        st.sidebar.markdown("---")
        
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

        # Filtri per i pazienti
        st.sidebar.markdown("### Filtra Pazienti")

        # Filtro testuale per nome
        nome_filtro = st.sidebar.text_input("Nome paziente")

        # Filtro testuale per cognome
        cognome_filtro = st.sidebar.text_input("Cognome paziente")

        # Filtro per data referto - solo input per ora
        data_inizio = st.sidebar.date_input("Data inizio", value=None)
        data_fine = st.sidebar.date_input("Data fine", value=None)

        # Filtro stato referto (esempio con opzioni fittizie)
        stato_referto = st.sidebar.selectbox("Stato Referto", options=["Tutti", "Validato", "Non Validato"])

        # Per ora salviamo i filtri in session_state (utile per future query)
        st.session_state["filters"] = {
            "nome": nome_filtro,
            "cognome": cognome_filtro,
            "data_inizio": data_inizio,
            "data_fine": data_fine,
            "stato_referto": stato_referto
        }
        
    def report_modify_page(self, report_id="6835d760cdc5c3eb8dec00f7"): 
        # Questa funzione apre una pagina per modificare un referto specifico
        st.markdown(f"## 📝 Modifica Referto ID: `{report_id}`")

        
        # Ottieni il referto dal database
        report = self.db.get_report_by_id(report_id)
        
        st.markdown(type(report["scheda_ps"]))
        
        if not report:
            st.error("❌ Referto non trovato.")
            return

        # Mostra i campi in base al tipo di valore
        for key, value in report.items():
            if isinstance(value, str):
                new_value = st.text_input(f"✏️ {key.capitalize()}", value=value)
                report[key] = new_value
            elif isinstance(value, list):
                new_value = st.text_area(f"🗒️ {key.capitalize()}", value="\n".join(value))
                report[key] = new_value.split("\n")
            

        # Bottone per salvare
        if st.button("💾 Salva Modifiche"):
            # aggiungi anagrafica medico al referto
            if "anagrafica_medico" not in report:
                report["anagrafica_medico"] = st.session_state.user["Anagrafica"]
            if "ospedale" not in report:
                report["ospedale"] = st.session_state.user["Ospedale"]
            self.db.update_clinical_report(report_id, report)
            st.success("✅ Referto aggiornato con successo!")
            time.sleep(2)
            # ritorna alla pagina principale
            st.session_state.page = "main"
            st.rerun()


    def show_report_page(self, report_id="6835d760cdc5c3eb8dec00f7"):
        st.markdown(f"# 👁️ Visualizza Referto")
        st.markdown(f"### ID: `{report_id}`")
        
        with st.container():
            if st.button("Torna indietro"):
                st.session_state.page = "main"
                st.rerun()
        st.write("---")

        report = self.db.get_report_by_id(report_id)
        if not report:
            st.error("❌ Referto non trovato.")
            return

        # CSS aggiornato con palette TOML e stile più "medical dark"
        st.markdown(
            """
            <style>
            /* Container principale referto */
            .report-box {
                background-color: #1E1E1E;              /* secondaryBackgroundColor */
                border: 1.5px solid #4DD0E1;            /* primaryColor */
                border-radius: 12px;
                padding: 18px 22px;
                margin-bottom: 20px;
                box-shadow: 0 2px 6px rgba(77, 208, 225, 0.35);
                color: #E0E0E0;                         /* textColor */
                font-family: "sans-serif", Arial, Helvetica, sans-serif;
                max-height: 140px;
                overflow-y: auto;
                transition: box-shadow 0.3s ease;
            }
            .report-box:hover {
                box-shadow: 0 4px 12px rgba(77, 208, 225, 0.6);
            }
            /* Scrollbar stile */
            .report-box::-webkit-scrollbar {
                width: 7px;
            }
            .report-box::-webkit-scrollbar-thumb {
                background-color: #4DD0E1;
                border-radius: 10px;
            }
            /* Chiave (titolo campo) */
            .report-key {
                font-weight: 700;
                font-size: 1.2em;
                color: #4DD0E1;                        /* primaryColor */
                margin-bottom: 8px;
                border-bottom: 2px solid #4DD0E1;
                padding-bottom: 6px;
                user-select: text;
            }
            /* Valore */
            .report-value {
                font-size: 1em;
                color: #E0E0E0;                        /* textColor */
                white-space: pre-wrap;
                user-select: text;
                line-height: 1.4em;
            }
            /* Layout colonne */
            .report-columns > div {
                padding: 0 12px;
            }
            /* Titoli e linee di separazione */
            hr {
                border: none;
                border-top: 1px solid #333;
                margin: 20px 0;
            }
            </style>
            """,
            unsafe_allow_html=True,
        )

        items = list(report.items())
        mid_index = (len(items) + 1) // 2
        left_items = items[:mid_index]
        right_items = items[mid_index:]

        col1, col2 = st.columns(2)

        def render_boxes(container, items_to_render):
            with container:
                for key, value in items_to_render:
                    display_key = key.replace('_', ' ').capitalize()
                    if isinstance(value, list):
                        value_str = "\n".join(f"• {item}" for item in value)
                    else:
                        value_str = str(value)

                    box_html = f"""
                    <div class="report-box">
                        <div class="report-key">{display_key}</div>
                        <div class="report-value">{value_str}</div>
                    </div>
                    """
                    st.markdown(box_html, unsafe_allow_html=True)

        render_boxes(col1, left_items)
        render_boxes(col2, right_items)

        st.write("---")





    def run(self):
        if st.session_state.logged_in:
            if st.session_state.page == "main":
                self.sidebar()
                self.main_page()
            elif st.session_state.page == "report_modify":
                self.report_modify_page(st.session_state.last_report["_id"])
            elif st.session_state.page == "show_report":
                self.show_report_page(st.session_state.last_report["_id"])
        else:
            if st.session_state.page == "login":
                self.login()
            elif st.session_state.page == "register":
                self.register()


if __name__ == "__main__":
    dashboard = Dashboard()
    dashboard.run()
