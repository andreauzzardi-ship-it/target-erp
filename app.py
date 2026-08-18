import streamlit as st
import pandas as pd
from google.genai import Client

# Questa riga legge la chiave dai 'Secrets' di Streamlit. 
# Non scrivere mai la chiave qui dentro!
client = Client(api_key=st.secrets["GOOGLE_API_KEY"])

st.set_page_config(page_title="Target ERP - Gestione Ordini & Offerte", page_icon="📦", layout="wide")
st.title("📦 Target ERP — Smart Order & Quote Hub")

import streamlit as st

# Creazione delle schede nella pagina principale
tab_gestionale, tab_victoria = st.tabs(["📋 Gestione Documenti", "🤖 Victoria AI"])

# --- TAB 1: GESTIONE ORDINI & OFFERTE ---
with tab_gestionale:
    st.title("Target ERP — Smart Order & Quote Hub")
    # Qui inserisci tutto il codice attuale dei documenti, upload file, tabelle ed export CSV

# --- CHAT FLUTTUANTE STILE MESSENGER CON VICTORIA ---
with st.sidebar:
    st.divider() # Linea separatoria pulita
    
    # Creiamo il pulsante popover che apre la chat fluttuante
    with st.popover("💬 Chat con Victoria", use_container_width=True):
        st.subheader("🤖 Victoria — Target ERP")
        st.caption("Chiedi supporto o informazioni sui prodotti.")
        
        # Contenitore per la cronologia dei messaggi
        chat_container = st.container(height=300)
        
        if "messages" not in st.session_state:
            st.session_state.messages = []

        # Mostra i messaggi passati dentro il rettangolo fluttuante
        with chat_container:
            for msg in st.session_state.messages:
                with st.chat_message(msg["role"]):
                    st.markdown(msg["content"])

        # Input pulito e nativo che non si sovrappone
        if prompt := st.chat_input("Scrivi a Victoria..."):
            st.session_state.messages.append({"role": "user", "content": prompt})
            
            with chat_container:
                with st.chat_message("user"):
                    st.markdown(prompt)

                with st.chat_message("assistant"):
                    with st.spinner("Victoria sta scrivendo..."):
                        try:
                            system_directive = (
                                "Sei Victoria, l'assistente virtuale ufficiale del software Target ERP. "
                                "Se ti chiedono come ti chiami, rispondi che ti chiami Victoria. "
                                "Non menzionare mai Google, Gemini o di essere un'IA generica. "
                            )
                            response = client.models.generate_content(
                                model="gemini-3.6-flash",
                                contents=system_directive + prompt
                            )
                            risposta = response.text
                        except Exception as e:
                            risposta = f"Errore nella generazione: {e}"

                        st.markdown(risposta)
            st.session_state.messages.append({"role": "assistant", "content": risposta})

# --- CONTENUTO PRINCIPALE ---
tipo_doc = st.radio("Seleziona il tipo di documento:", ["🛒 Ordine Cliente", "📄 Offerta"], horizontal=True)

# Tab di Input
input_tab1, input_tab2 = st.tabs(["📄 Carica PDF / Immagine", "✉️ Incolla Testo Email"])
with input_tab1: 
    st.file_uploader("Trascina file", type=["pdf", "jpg", "jpeg"])
with input_tab2: 
    st.text_area("Incolla testo richiesta:", height=100)

st.divider()

# Dati e Revisione
if "dati" not in st.session_state:
    st.session_state.dati = [
        {"COD_CLIENTE": "CLI-001", "RAGIONE_SOCIALE": "Rossi S.R.L.", "COD_ARTICOLO": "C-600", "DESCRIZIONE": "Connettore Rapido", "QUANTITA": 5, "DATA_CONSEGNA": "2026-09-01"}
    ]

df = pd.DataFrame(st.session_state.dati)
edited_df = st.data_editor(df, use_container_width=True, num_rows="dynamic")

csv = edited_df.to_csv(index=False, sep=';', encoding='utf-8-sig')
st.download_button("⬇️ Esporta CSV", data=csv, file_name="EXPORT.csv", mime="text/csv")