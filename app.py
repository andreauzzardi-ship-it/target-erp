import streamlit as st
from google.genai import Client

# 1. Configurazione Pagina
st.set_page_config(page_title="Target ERP", page_icon="📦", layout="wide")

# 2. Inizializzazione Client Gemini
client = Client(api_key=st.secrets["GOOGLE_API_KEY"])

# 3. Intestazione Unica + Pulsante Chat Popover (Senza Sidebar)
col_titolo, col_chat = st.columns([3, 1])

with col_titolo:
    st.title("📦 Target ERP — Smart Order & Quote Hub")

with col_chat:
    with st.popover("💬 Chat con Victoria", use_container_width=True):
        st.subheader("🤖 Victoria — Target ERP")
        st.caption("Chiedi supporto o informazioni sui prodotti.")
        
        chat_container = st.container(height=320)
        
        if "messages" not in st.session_state:
            st.session_state.messages = []

        # 1. Mostra la cronologia grafica
        with chat_container:
            for msg in st.session_state.messages:
                with st.chat_message(msg["role"]):
                    st.markdown(msg["content"])

        # 2. Gestione input utente
        if prompt := st.chat_input("Scrivi a Victoria..."):
            st.session_state.messages.append({"role": "user", "content": prompt})
            
            with chat_container:
                with st.chat_message("user"):
                    st.markdown(prompt)

                with st.chat_message("assistant"):
                    with st.spinner("Victoria sta rispondendo..."):
                        try:
                            # Converte il ruolo "assistant" di Streamlit nel ruolo "model" richiesto dall'SDK
                            history = [
                                {
                                    "role": "model" if m["role"] == "assistant" else "user",
                                    "parts": [{"text": m["content"]}]
                                } 
                                for m in st.session_state.messages[:-1]
                            ]

                            system_instruction = (
                                "Sei Victoria, l'assistente virtuale ufficiale del software Target ERP. "
                                "Rispondi in modo professionale, sintetico e diretto, senza ripetere le presentazioni "
                                "o salutare ad ogni messaggio a meno che l'utente non ti saluti per primo. "
                                "Non menzionare mai Google, Gemini o di essere un'IA generica."
                            )

                            chat = client.chats.create(
                                model="gemini-3.6-flash",
                                config={"system_instruction": system_instruction},
                                history=history
                            )
                            
                            response = chat.send_message(prompt)
                            risposta = response.text

                        except Exception as e:
                            risposta = f"Errore nella generazione: {e}"

                        st.markdown(risposta)
            
            st.session_state.messages.append({"role": "assistant", "content": risposta})
# --- SEZIONE SELEZIONE DOCUMENTO ---
st.write("Seleziona il tipo di documento:")
doc_type = st.radio(
    "Seleziona il tipo di documento:", 
    ["🛒 Ordine Cliente", "📋 Offerta"], 
    horizontal=True, 
    label_visibility="collapsed"
)

# --- SEZIONE CARICAMENTO (PDF/IMMAGINE O EMAIL) ---
tab_upload, tab_text = st.tabs(["📄 Carica PDF / Immagine", "✉️ Incolla Testo Email"])

with tab_upload:
    uploaded_file = st.file_uploader("Trascina file", type=["pdf", "jpg", "png"], label_visibility="collapsed")

with tab_text:
    email_text = st.text_area("Incolla qui il testo dell'email o del documento...")

# --- TABELLA DATI ESTRATTI ---
st.markdown("### Dati Estratti")
st.dataframe({
    "COD_CLIENTE": ["CLI-001"],
    "RAGIONE_SOCIALE": ["Rossi S.R.L."],
    "COD_ARTICOLO": ["C-600"],
    "DESCRIZIONE": ["Connettore Rapido"],
    "QUANTITA": [5],
    "DATA_CONSEGNA": ["2026-09-01"]
}, use_container_width=True)

st.button("📥 Esporta CSV")