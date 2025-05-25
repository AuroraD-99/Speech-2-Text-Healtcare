import streamlit as st
import bcrypt
import os
import sys
import time
import re
import dotenv


sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from Database.mongodb import DB

class Dashboard:
    def __init__(self, env_file="key.env"):
        if "db" not in st.session_state:
            st.session_state.db = DB()  # salva l'istanza nella sessione
        self.db = st.session_state.db
        if "page" not in st.session_state:
            st.session_state.page = "login"
        if "logged_in" not in st.session_state:
            st.session_state.logged_in = False
        
        # Imposta l'environment variable per FastAPI
        dotenv.load_dotenv(env_file, override=True)

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
                hashed_password = user["password"]
                if isinstance(hashed_password, str):
                    hashed_password = hashed_password.encode('utf-8')

                if bcrypt.checkpw(st.session_state.login_password.encode('utf-8'), hashed_password):
                    st.session_state.logged_in = True
                    st.session_state.user = user
                    st.success(f"✅ Benvenuto, {user['anagrafica']['name']} {user['anagrafica']['surname']}!")
                    time.sleep(2)
                    st.rerun()
                else:
                    st.error("❌ Credenziali non valide")
            else:
                st.error("❌ Credenziali non valide")

        st.markdown("---")
        if st.button("📝 Non hai un account? Registrati", use_container_width=True):
            st.session_state.page = "register"
            st.rerun()
    
    def delete_all_reports_of_a_patient(self, patient_cf):
        """
        Cancella tutti i referti associati a un paziente specifico.
        """
        try:
            self.db.delete_all_reports_by_patient(patient_cf, doctor_cf=st.session_state.user["anagrafica"]["CF"])
            st.success(f"✅ Tutti i referti del paziente con CF {patient_cf} sono stati cancellati.")
            time.sleep(2)
        except Exception as e:
            st.error(f"❌ Errore durante la cancellazione dei referti: {str(e)}")
    
    def delete_report(self, report_id):
        """
        Cancella un referto specifico.
        """
        try:
            self.db.delete_clinical_report(report_id)
            st.success(f"✅ Referto con ID {report_id} cancellato.")
            time.sleep(2)
        except Exception as e:
            st.error(f"❌ Errore durante la cancellazione del referto: {str(e)}")

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
            elif self.db.db.operatori.find_one({"cf": cf.upper()}):
                st.error("🧾 Codice fiscale già registrato.")
            else:
                new_user = {
                    "email": email,
                    "password": password,
                    "anagrafica": {
                        "name": nome.strip(),
                        "surname": cognome.strip(),
                        "CF": cf.upper(),
                        "cellulare": cellulare,
                        "email": email,
                    },
                    "ruolo": ruolo,
                    "struttura": {
                        "nome": nome_struttura.strip(),
                        "reparto": reparto.strip(),
                        "città": città.strip(),
                        "provincia": provincia.strip(),
                        "CAP": cap,
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
            reports = self.db.get_all_clinical_reports_by_doctor_cf(medico_cf)

            if not reports:
                st.warning("🔍 Non ci sono referti associati al tuo profilo medico.")
            else:
                # Raggruppa per nome paziente
                grouped = {}
                for report in reports:
                    paziente = report.get("name", "Sconosciuto")
                    grouped.setdefault(paziente, []).append(report)

                for paziente, referti in grouped.items():
                    with st.expander(f"🧑‍⚕️ Paziente: **{paziente}** ({len(referti)} referti)"):
                        for referto in referti:
                            st.markdown(f"""
                            - 🩺 {referto.get('type', 'N/A')}
                            - 📄 **ID Referto**: `{referto.get('report_id', 'N/A')}`
                            - 🗓️ **Data**: {referto.get('timestamp', 'N/A')}
                            """)
                            st.button(
                                "❌ Cancella Referto",
                                key=f"delete_{referto.get('report_id')}",
                                on_click=self.delete_report,
                                args=(referto.get('report_id'),),)
                            #TODO: INSERIRE CAMPO TYPE PER I REFERTI
        except Exception as e:
            st.error(f"❌ Errore nel recupero dei referti: {str(e)}")

        st.markdown("---")
        if st.button("🚪 Logout", use_container_width=True):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()
            
    def sidebar(self):
        st.sidebar.markdown("## 👤 Anagrafica Operatore")

        if st.session_state.logged_in:
            user = st.session_state.get("user", {})
            anagrafica = user.get("anagrafica", {})
            nome = anagrafica.get("name", "")
            cognome = anagrafica.get("surname", "")
            cf = anagrafica.get("CF", "")
            ruolo = user.get("ruolo", "Sconosciuto")
            struttura = user.get("struttura", {}).get("nome", "Sconosciuta")

            with st.sidebar.container(border=True):
                st.markdown(f"**👤 Nome:** `{nome} {cognome}`")
                st.markdown(f"**🆔 Codice Fiscale:** `{cf}`")
                st.markdown(f"**🎓 Ruolo:** `{ruolo}`")
                st.markdown(f"**🏥 Struttura:** `{struttura}`")
        else:
            with st.sidebar.container(border=True):
                st.markdown("🔒 <span style='color:gray'>Non sei loggato.</span>", unsafe_allow_html=True)


        

        st.sidebar.markdown("---")
        
        # Pulsante per inserimento nuovo referto
        if st.sidebar.button("➕ Nuovo Referto", use_container_width=True):
            #TODO: Implementare la logica per l'inserimento di un nuovo referto
            st.sidebar.success("Funzionalità in arrivo! 🚀")
            
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
        
        



    def run(self):
        if st.session_state.logged_in:
            self.sidebar()
            self.main_page()
        else:
            if st.session_state.page == "login":
                self.login()
            elif st.session_state.page == "register":
                self.register()


if __name__ == "__main__":
    dashboard = Dashboard()
    dashboard.run()
