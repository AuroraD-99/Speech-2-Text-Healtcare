import streamlit as st

class Dashboard:
    def __init__(self):
        self.scope_options = ["Pronto Soccorso", "Visite Ordinarie"]
        self.users = {
            "medico1": "password1",
            "medico2": "password2"
        }

        # Inizializzazione stato
        st.session_state.setdefault('logged_in', False)
        st.session_state.setdefault('username', "")
        st.session_state.setdefault('scope', "")
        st.session_state.setdefault('patients', ["Mario Rossi", "Pepp Scuppett"])
        st.session_state.setdefault('_just_logged_in', False)

    def login_screen(self):
        st.title("Selettore per PS o VO")
        st.session_state.scope = st.selectbox("Seleziona lo scopo di utilizzo", self.scope_options)

        username = st.text_input("Username")
        password = st.text_input("Password", type="password")

        if st.button("Login"):
            if username in self.users and self.users[username] == password:
                st.session_state.logged_in = True
                st.session_state.username = username
                st.session_state._just_logged_in = True  # Trucchetto per mostrare subito la home
                st.rerun()
            else:
                st.error("Credenziali errate")

    def main_screen(self):
        st.sidebar.title(f"Lista pazienti del Dott. {st.session_state.username.capitalize()}")

        if st.sidebar.button("Nuovo paziente"):
            st.info("Nuovo paziente selezionato (placeholder)")
        if st.sidebar.button("Elimina tutti i pazienti"):
            st.session_state.patients = []
            st.success("Tutti i pazienti eliminati")

        for p in st.session_state.patients:
            st.sidebar.write(p)

        st.title("Nuovo paziente")
        if st.button("Clicca qui per iniziare la registrazione"):
            st.info("Registrazione in corso...")

        st.markdown("### PDF da compilare")
        st.write("📄 Documento FSE/PS verrà mostrato qui")

    def run(self):
        if st.session_state.logged_in:
            self.main_screen()
        else:
            self.login_screen()


# Esecuzione
if __name__ == "__main__":
    dashboard = Dashboard()
    dashboard.run()
