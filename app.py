import json
import pandas as pd
import streamlit as st
from google.genai import Client

# Configurazione pagina
st.set_page_config(page_title="Target ERP - Smart Order & Quote Hub", layout="wide")

# Recupero chiave API sicura dai secrets (o stringa diretta se preferisci)
api_key = st.secrets.get("GOOGLE_API_KEY", "IL_TUO_API_KEY_QUI")
client = Client(api_key=api_key)

# --- INTESTAZIONE + CHAT VICTORIA (POPOVER IN ALTO A DESTRA, NO SIDEBAR) ---
col_titolo, col_chat = st.columns([3, 1])

with col_titolo:
    st.title("📦 Target ERP — Smart Order & Quote Hub")

with col_chat:
    with st.popover("💬 Chat con Victoria", use_container_width=True):
        st.subheader("🤖 Victoria — Target ERP")
        st.caption("Chiedi supporto o informazioni sui prodotti.")
        
        chat_container = st.container(height=300)
        
        if "messages" not in st.session_state:
            st.session_state.messages = []

        with chat_container:
            for msg in st.session_state.messages:
                with st.chat_message(msg["role"]):
                    st.markdown(msg["content"])

        if prompt := st.chat_input("Chiedi info a Victoria..."):
            st.session_state.messages.append({"role": "user", "content": prompt})
            
            with chat_container:
                with st.chat_message("user"):
                    st.markdown(prompt)

                with st.chat_message("assistant"):
                    with st.spinner("Victoria sta rispondendo..."):
                        try:
                            history = [
                                {
                                    "role": "model" if m["role"] == "assistant" else "user",
                                    "parts": [{"text": m["content"]}]
                                } 
                                for m in st.session_state.messages[:-1]
                            ]

                            system_instruction = (
                                "Sei Victoria, l'assistente virtuale ufficiale del software Target ERP. "
                                "Rispondi in modo professionale e sintetico, senza ripetere le presentazioni ad ogni messaggio. "
                                "Non menzionare mai Google, Gemini o di essere un'IA generica."
                            )

                            chat = client.chats.create(
                                model="gemini-3.5-flash",
                                config={"system_instruction": system_instruction},
                                history=history
                            )
                            
                            response = chat.send_message(prompt)
                            risposta = response.text

                        except Exception as e:
                            risposta = f"Errore nella generazione: {e}"

                        st.markdown(risposta)
            
            st.session_state.messages.append({"role": "assistant", "content": risposta})

st.divider()

# --- SEZIONE CARICAMENTO E ESTRAZIONE TESTO EMAIL ---
st.subheader("Inserisci o Incolla Testo Email / Ordine")
email_text = st.text_area("Incolla qui il testo dell'email da analizzare:", height=130)

if st.button("⚡ Analizza Email ed Inserisci in Tabella", type="primary"):
    if email_text.strip():
        with st.spinner("Estrazione articoli e quantità dall'email..."):
            try:
                prompt_estrazione = f"""
                Estragga le righe dell'ordine presenti nel testo fornito.
                Restituisci ESCLUSIVAMENTE una lista JSON di oggetti con queste tre chiavi esatte:
                "COD_ARTICOLO", "DESCRIZIONE", "QUANTITA" (come numero intero).
                Se manca un codice, usa "N/D".

                Testo:
                {email_text}
                """
                
                res = client.models.generate_content(
                    model="gemini-3.5-flash",
                    contents=prompt_estrazione,
                    config={"response_mime_type": "application/json"}
                )
                
                nuovi_dati = json.loads(res.text)
                
                # Aggiunge i nuovi dati alla sessione
                if "dati" not in st.session_state:
                    st.session_state.dati = []
                
                st.session_state.dati.extend(nuovi_dati)
                st.success("Dati estratti e aggiunti alla tabella!")
            except Exception as e:
                st.error(f"Errore durante l'estrazione: {e}")
    else:
        st.warning("Incolla il testo dell'email prima di analizzare.")

st.divider()

# --- CONTENUTO PRINCIPALE: TABELLA ED ESPORTAZIONE ---
st.subheader("Gestione Ordini e Articoli")

if "dati" not in st.session_state:
    st.session_state.dati = [
        {"COD_ARTICOLO": "C-600", "DESCRIZIONE": "Connettore Rapido", "QUANTITA": 5},
        {"COD_ARTICOLO": "A-100", "DESCRIZIONE": "Staffa di fissaggio", "QUANTITA": 12}
    ]

df = pd.DataFrame(st.session_state.dati)
edited_df = st.data_editor(df, use_container_width=True, num_rows="dynamic")

# Pulsante per scaricare la tabella aggiornata in CSV
csv_data = edited_df.to_csv(index=False).encode('utf-8')
st.download_button(
    label="📥 Esporta CSV Tabella",
    data=csv_data,
    file_name="gestione_ordini.csv",
    mime="text/csv"
)