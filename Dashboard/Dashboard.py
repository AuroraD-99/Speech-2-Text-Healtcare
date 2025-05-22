import streamlit as st
import bcrypt

import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from Database.mongodb import DB
# Inizializza il DB
db = DB()

# Funzione per il login
def login():
    st.title("Login Operatore Sanitario")

    st.text_input("Username", key="login_username")
    st.text_input("Password", type="password", key="login_password")

    if st.button("Login"):
        user = db.get_operator(st.session_state.login_username)
        if user and bcrypt.checkpw(st.session_state.login_password.encode('utf-8'), user["password"]):
            st.session_state.logged_in = True
            st.session_state.user = user
            st.success(f"Benvenuto, {user['nome']}!")
        else:
            st.error("Credenziali non valide")

    st.markdown("---")
    if st.button("Register"):
        st.session_state.page = "register"

# Funzione per la registrazione
def register():
    st.title("Registrazione Nuovo Operatore")

    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    nome = st.text_input("Nome")
    cognome = st.text_input("Cognome")
    cf = st.text_input("Codice Fiscale")

    if st.button("Registrati"):
        if db.get_operator(username):
            st.error("Username già esistente.")
        elif db.db.operatori.find_one({"cf": cf}):
            st.error("Codice fiscale già registrato.")
        else:
            password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
            new_user = {
                "username": username,
                "password": password_hash,
                "anagrafica": {
                    "name": nome,
                    "surname": cognome,
                    "CF": cf,
                },
                "ruolo": "operatore",
            }
            db.insert_operator(new_user["username"], new_user["password"], new_user["anagrafica"], new_user["ruolo"])
            st.success("Registrazione completata con successo! Ora puoi effettuare il login.")
            st.session_state.page = "login"

    if st.button("Torna al login"):
        st.session_state.page = "login"

# Pagina principale dopo il login
def main_page():
    st.title("Dashboard Principale")
    user = st.session_state.get("user", {})
    st.write(f"Benvenuto, **{user.get('nome', '')} {user.get('cognome', '')}**")
    st.write("Qui aggiungeremo le funzionalità per trascrizioni, referti, RAG, ecc.")
    if st.button("Logout"):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()

# Routing semplice
if "page" not in st.session_state:
    st.session_state.page = "login"
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if st.session_state.logged_in:
    main_page()
else:
    if st.session_state.page == "login":
        login()
    elif st.session_state.page == "register":
        register()
