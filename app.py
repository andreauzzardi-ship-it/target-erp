import streamlit as st
import pandas as pd
from google.genai import Client

# Legge la chiave API in modo sicuro dalle impostazioni segrete di Streamlit Cloud
client = Client(api_key=st.secrets["GOOGLE_API_KEY"])

st.set_page_config(page_title="Target ERP - Smart Order & Quote Hub", layout="wide")
st.title("📦 Target ERP — Smart Order & Quote Hub")

# --- SIDEBAR: ASSISTENTE AI ---
with st.sidebar:
    st.header("🤖 Assistente AI")
    st.markdown("Chiedi supporto o informazioni sui prodotti.")
    
    if "messages" not in st.session_state: 
        st.session_state.messages = []
    
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]): 
            st.markdown(msg["content"])

    if prompt := st.chat_input("Chiedi info..."):
        with st.chat_message("user"): 
            st.markdown(prompt)
        st.session_state.messages.append({"role": "user", "content": prompt})
        
        with st.chat_message("assistant"):
            with st.spinner("L'IA sta elaborando..."):
                try:
                    response = client.models.generate_content(
                        model='gemini-2.0-flash',
                        contents=prompt
                    )
                    risposta = response.text
                except Exception as e:
                    risposta = f"Errore nella generazione: {e}"
                st.markdown(risposta)
        st.session_state.messages.append({"role": "assistant", "content": risposta})

# --- CONTENUTO PRINCIPALE ---
st.subheader("Gestione Ordini e Articoli")
if "dati" not in st.session_state:
    st.session_state.dati = [
        {"COD_ARTICOLO": "C-600", "DESCRIZIONE": "Connettore Rapido", "QUANTITA": 5},
        {"COD_ARTICOLO": "A-100", "DESCRIZIONE": "Staffa di fissaggio", "QUANTITA": 12}
    ]

df = pd.DataFrame(st.session_state.dati)
edited_df = st.data_editor(df, use_container_width=True)