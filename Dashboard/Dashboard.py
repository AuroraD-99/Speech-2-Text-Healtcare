import streamlit as st
import bcrypt
import os
import sys
import time
import re

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from Database.mongodb import DB

class Dashboard:
    def __init__(self):
        self.db = DB()
        if "page" not in st.session_state:
            st.session_state.page = "login"
        if "logged_in" not in st.session_state:
            st.session_state.logged_in = False

    def login(self):
        st.title("Login Operatore Sanitario")
        st.text_input("Email", key="login_email")
        st.text_input("Password", type="password", key="login_password")

        if st.button("Login", key="login_button"):
            user = self.db.get_operator(st.session_state.login_email)
            
            # Assicurati che l'hash della password venga convertito in bytes
            if user:
                hashed_password = user["password"]
                if isinstance(hashed_password, str):
                    hashed_password = hashed_password.encode('utf-8')

                if bcrypt.checkpw(st.session_state.login_password.encode('utf-8'), hashed_password):
                    st.session_state.logged_in = True
                    st.session_state.user = user
                    st.success(f"Benvenuto, {user['anagrafica']['name']} {user['anagrafica']['surname']}!")
                    time.sleep(2)
                    st.rerun()
                else:
                    st.error("Credenziali non valide")
            else:
                st.error("Credenziali non valide")

        st.markdown("---")
        if st.button("Register"):
            st.session_state.page = "register"
            st.rerun()


    def register(self):
        st.title("Registrazione Nuovo Operatore")

        # --- Campi dati personali ---
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        nome = st.text_input("Nome")
        cognome = st.text_input("Cognome")
        cellulare = st.text_input("Cellulare")
        cf = st.text_input("Codice Fiscale")
        ruolo = st.selectbox("Ruolo", ["Medico", "Infermiere", "Tecnico di laboratorio", "Operatore sanitario"])

        # --- Campi struttura ospedaliera ---
        st.markdown("### Informazioni Struttura Ospedaliera")
        nome_struttura = st.text_input("Nome della Struttura")
        reparto = st.text_input("Reparto")
        città = st.text_input("Città")
        provincia = st.text_input("Provincia")
        cap = st.text_input("CAP")

        if st.button("Registrati"):
            # --- Validazioni ---
            email_pattern = r"^[\w\.-]+@(?:gmail\.com|yahoo\.com|libero\.it|outlook\.com|hotmail\.com|icloud\.com)$"
            password_pattern = r"^(?=.*[.,!&#]).{8,16}$"
            cf_pattern = r"^[A-Z]{6}[0-9]{2}[A-Z][0-9]{2}[A-Z][0-9]{3}[A-Z]$"

            if not re.match(email_pattern, email):
                st.error("Inserisci un'email valida (es. @gmail.com, @libero.it, ecc.)")
            elif not re.match(password_pattern, password):
                st.error("La password deve essere lunga 8-16 caratteri e contenere almeno uno tra: . , ! & #")
            elif not nome.strip() or not cognome.strip():
                st.error("Nome e Cognome non possono essere vuoti.")
            elif not cellulare.isdigit() or not (10 <= len(cellulare) <= 11):
                st.error("Il numero di cellulare deve contenere solo cifre e avere 10 o 11 cifre.")
            elif not re.match(cf_pattern, cf.upper()):
                st.error("Codice Fiscale non valido. Deve seguire il formato italiano (16 caratteri).")
            elif not nome_struttura.strip() or not reparto.strip() or not città.strip() or not provincia.strip() or not cap.strip():
                st.error("Tutti i campi relativi alla struttura ospedaliera devono essere compilati.")
            elif not cap.isdigit() or len(cap) != 5:
                st.error("Il CAP deve essere un numero di 5 cifre.")
            elif self.db.get_operator(email):
                st.error("Email già registrata.")
            elif self.db.db.operatori.find_one({"cf": cf.upper()}):
                st.error("Codice fiscale già registrato.")
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
                
                st.success("Registrazione completata con successo! Ora puoi effettuare il login.")
                st.session_state.page = "login"
                st.rerun()
                if st.button("Torna al login"):
                    st.session_state.page = "login"
                    st.rerun()

    def main_page(self):
        st.title("Dashboard Principale")
        user = st.session_state.get("user", {})
        st.write(f"Benvenuto, **{user.get('nome', '')} {user.get('cognome', '')}**")
        st.write("Qui aggiungeremo le funzionalità per trascrizioni, referti, RAG, ecc.")
        if st.button("Logout"):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()

    def run(self):
        if st.session_state.logged_in:
            self.main_page()
        else:
            if st.session_state.page == "login":
                self.login()
            elif st.session_state.page == "register":
                self.register()


# Esecuzione della dashboard
if __name__ == "__main__":
    dashboard = Dashboard()
    dashboard.run()
