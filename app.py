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
        
        # 1. Inizializzazione della cronologia messaggi
        if "messages" not in st.session_state:
            st.session_state.messages = []

        # 2. Mostra la cronologia nella finestra
        with chat_container:
            for msg in st.session_state.messages:
                with st.chat_message(msg["role"]):
                    st.markdown(msg["content"])

        # 3. Gestione dell'input utente
        if prompt := st.chat_input("Scrivi a Victoria..."):
            st.session_state.messages.append({"role": "user", "content": prompt})
            
            with chat_container:
                with st.chat_message("user"):
                    st.markdown(prompt)

                with st.chat_message("assistant"):
                    with st.spinner("Victoria sta rispondendo..."):
                        try:
                            # Direttiva di sistema pulita ed esplicita
                            system_instruction = (
                                "Sei Victoria, l'assistente virtuale del software Target ERP. "
                                "Rispondi in modo professionale, sintetico e diretto, senza ripetere le presentazioni "
                                "o salutare ogni volta a meno che non sia l'inizio assoluto della conversazione. "
                                "Non menzionare mai Google, Gemini o altre IA."
                            )

                            # Costruiamo la cronologia da passare al modello per mantenere il contesto
                            history = [
                                {"role": m["role"], "parts": [{"text": m["content"]}]} 
                                for m in st.session_state.messages[:-1]
                            ]

                            # Creiamo la sessione di chat con le direttive di sistema vere e proprie
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