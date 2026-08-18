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

# --- TAB 2: CHAT CON VICTORIA ---
with tab_victoria:
    st.header("Victoria — Assistente Target ERP")
    st.caption("Chiedi supporto o informazioni sui prodotti.")

    if "messages" not in st.session_state:
        st.session_state.messages = []

    # Mostra la cronologia messaggi
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # Utilizzo del chat_input nativo al centro della pagina (funziona alla perfezione nei tab)
    if prompt := st.chat_input("Chiedi info a Victoria..."):
        # Messaggio Utente
        with st.chat_message("user"):
            st.markdown(prompt)
        st.session_state.messages.append({"role": "user", "content": prompt})

        # Risposta Assistente
        with st.chat_message("assistant"):
            with st.spinner("Victoria sta elaborando..."):
                try:
                    system_directive = (
                        "Sei Victoria, l'assistente virtuale ufficiale del software Target ERP. "
                        "Se ti chiedono come ti chiami, rispondi che ti chiami Victoria. "
                        "Non menzionare mai Google, Gemini o di essere un'IA generica. "
                    )
                    response = client.models.generate_content(
                        model="gemini-3.5-flash",
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