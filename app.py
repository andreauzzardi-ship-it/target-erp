import json
import pandas as pd
import streamlit as st
from google.genai import Client

# Configurazione pagina
st.set_page_config(page_title="Target ERP - Smart Order & Quote Hub", layout="wide")

st.markdown("""
<style>
footer,
#MainMenu,
header,
[data-testid="stHeader"],
[data-testid="stToolbar"],
[data-testid="stStatusWidget"],
[data-testid="stActionButtonIcon"],
div[class*="viewerBadge"],
div[class*="styles_viewerBadge"],
a[class*="viewerBadge"],
iframe[title="streamlitApp"] + div {
    display: none !important;
    visibility: hidden !important;
    height: 0 !important;
    width: 0 !important;
    opacity: 0 !important;
    pointer-events: none !important;
}
</style>
""", unsafe_allow_html=True)

# Recupero SICURO della chiave API dai secrets di Streamlit
client = Client(api_key=st.secrets["GOOGLE_API_KEY"])

# --- INTESTAZIONE + CHAT VICTORIA (POPOVER IN ALTO A DESTRA) ---
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
                                "Se ti chiedono chi ti ha creata o sviluppata, rispondi che sei stata creata da Andrea Uzzardi. "
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

# --- CARICAMENTO SILENZIOSO CLIENTI DA EXCEL ---
@st.cache_data
def carica_clienti():
    try:
        df = pd.read_excel("clienti.xlsx")
        # Pulizia nomi colonne (rimuove spazi vuoti accidentali)
        df.columns = df.columns.str.strip()
        return df
    except Exception:
        return pd.DataFrame()

df_clienti = carica_clienti()

# Prepariamo la struttura dati da passare all'IA
clienti_dict = []
if not df_clienti.empty:
    for _, row in df_clienti.iterrows():
        # Cerca colonne flessibili per evitare errori di battitura nei titoli dell'Excel
        cod = str(row.get("COD_CLIENTE", row.get("Codice", "N/D")))
        rag = str(row.get("RAGIONE_SOCIALE", row.get("Cliente", row.get("Ragione Sociale", "N/D"))))
        if rag != "N/D":
            clienti_dict.append({"COD_CLIENTE": cod, "RAGIONE_SOCIALE": rag})

# --- SEZIONE SELEZIONE TIPO DOCUMENTO ---
st.write("Seleziona il tipo di documento:")
doc_type = st.radio(
    "Seleziona il tipo di documento:", 
    ["🛒 Ordine Cliente", "📋 Offerta"], 
    horizontal=True, 
    label_visibility="collapsed"
)

# --- SEZIONE CARICAMENTO CON TAB (PDF / IMMAGINE E EMAIL) ---
tab_upload, tab_text = st.tabs(["📄 Carica PDF / Immagine", "✉️ Incolla Testo Email"])

with tab_upload:
    uploaded_file = st.file_uploader(
        "Trascina file (PDF o Immagine)", 
        type=["pdf", "jpg", "png", "jpeg"], 
        label_visibility="collapsed"
    )
    if uploaded_file and st.button("⚡ Analizza File ed Inserisci in Tabella", type="primary"):
        with st.spinner("Lettura ed estrazione dati dal file in corso..."):
            try:
                # Lettura dei byte del file caricato
                file_bytes = uploaded_file.read()
                mime_type = uploaded_file.type
                
                # Definizione del prompt per l'estrazione
                prompt_estrazione = f"""
                Estragga le righe dell'ordine/offerta dal documento allegato per un documento di tipo: {doc_type}.
                
                ELENCO CLIENTI ANAGRAFICA REALE:
                {json.dumps(clienti_dict, ensure_ascii=False)}

                REGOLE ESSENZIALI CLIENTI:
                1. Confronta il nome del cliente trovato nel file con l'ELENCO CLIENTI ANAGRAFICA REALE.
                2. Imposta il "RAGIONE_SOCIALE" e "COD_CLIENTE" esatti dall'anagrafica se trovi una corrispondenza.
                
                Restituisci ESCLUSIVAMENTE una lista JSON di oggetti con esattamente queste chiavi:
                "COD_CLIENTE", "RAGIONE_SOCIALE", "COD_ARTICOLO", "DESCRIZIONE", "QUANTITA", "DATA_CONSEGNA".
                Se qualche dato non è presente nel testo, inserisci "N/D".
                La QUANTITA deve essere un numero intero.
                """

                # Chiamata a Gemini inviando sia il file che il prompt
                from google.genai import types
                
                res = client.models.generate_content(
                    model="gemini-3.5-flash",
                    contents=[
                        types.Part.from_bytes(data=file_bytes, mime_type=mime_type),
                        prompt_estrazione
                    ],
                    config={"response_mime_type": "application/json"}
                )

                nuovi_dati = json.loads(res.text)

                if "dati" not in st.session_state:
                    st.session_state.dati = []

                st.session_state.dati.extend(nuovi_dati)
                st.success("Dati estratti dal file e aggiunti alla tabella!")

            except Exception as e:
                st.error(f"Errore durante l'analisi del file: {e}")

with tab_text:
    email_text = st.text_area("Incolla qui il testo dell'email o del documento...", height=130)
    
    if st.button("⚡ Analizza Email ed Inserisci in Tabella", type="primary"):
        if email_text.strip():
            with st.spinner("Estrazione dati dall'email in corso..."):
                try:
                    prompt_estrazione = f"""
                    Estragga le righe dell'ordine/offerta per un documento di tipo: {doc_type}.
                    
                    ELENCO CLIENTI ANAGRAFICA REALE:
                    {json.dumps(clienti_dict, ensure_ascii=False)}

                    REGOLE ESSENZIALI CLIENTI:
                    1. Confronta il nome del cliente trovato nel testo con l'ELENCO CLIENTI ANAGRAFICA REALE.
                    2. Imposta il "RAGIONE_SOCIALE" e "COD_CLIENTE" esatti dall'anagrafica se trovi una corrispondenza.

                    Restituisci ESCLUSIVAMENTE una lista JSON di oggetti con esattamente queste chiavi:
                    "COD_CLIENTE", "RAGIONE_SOCIALE", "COD_ARTICOLO", "DESCRIZIONE", "QUANTITA", "DATA_CONSEGNA".
                    Se manca un dato o codice, usa "N/D".
                    La QUANTITA deve essere un numero intero.

                    Testo:
                    {email_text}
                    """
                    
                    res = client.models.generate_content(
                        model="gemini-3.5-flash",
                        contents=prompt_estrazione,
                        config={"response_mime_type": "application/json"}
                    )
                    
                    nuovi_dati = json.loads(res.text)
                    
                    if "dati" not in st.session_state:
                        st.session_state.dati = []
                    
                    st.session_state.dati.extend(nuovi_dati)
                    st.success("Dati estratti e aggiunti alla tabella!")
                except Exception as e:
                    st.error(f"Errore durante l'estrazione: {e}")
        else:
            st.warning("Incolla il testo prima di procedere con l'analisi.")

st.divider()

# --- CONTENUTO PRINCIPALE: TABELLA COMPLETA ED ESPORTAZIONE ---
st.subheader("Gestione Ordini e Articoli")

if "dati" not in st.session_state:
    st.session_state.dati = [
        {
            "COD_CLIENTE": "CLI-001",
            "RAGIONE_SOCIALE": "Rossi S.R.L.",
            "COD_ARTICOLO": "C-600",
            "DESCRIZIONE": "Connettore Rapido",
            "QUANTITA": 5,
            "DATA_CONSEGNA": "2026-09-01"
        }
    ]

df = pd.DataFrame(st.session_state.dati)
edited_df = st.data_editor(df, use_container_width=True, num_rows="dynamic")

# Pulsante di esportazione CSV
csv_data = edited_df.to_csv(index=False).encode('utf-8')
st.download_button(
    label="📥 Esporta CSV Tabella",
    data=csv_data,
    file_name="gestione_ordini.csv",
    mime="text/csv"
)