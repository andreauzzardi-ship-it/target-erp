import base64
import io
import json
import re
import time
from difflib import SequenceMatcher
from pathlib import Path

import pandas as pd
import streamlit as st
from openai import OpenAI


# ============================================================
# CONFIGURAZIONE PAGINA
# ============================================================

st.set_page_config(
    page_title="Target ERP - Smart Order & Quote Hub",
    layout="wide"
)


# ============================================================
# CSS
# ============================================================

st.markdown(
    """
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
    a[class*="viewerBadge"] {
        display: none !important;
        visibility: hidden !important;
        height: 0 !important;
        width: 0 !important;
    }
    </style>
    """,
    unsafe_allow_html=True
)


# ============================================================
# CONFIGURAZIONE FILE
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

FILE_CLIENTI = BASE_DIR / "clienti.xlsx"
FILE_ARTICOLI = BASE_DIR / "articoli.xlsx"

# Metti qui il PDF del listino.
# Esempio:
# listino.pdf
FILE_LISTINO = BASE_DIR / "listino.pdf"

MODELLO_OPENAI = "gpt-4.1"


# ============================================================
# CLIENT OPENAI
# ============================================================

@st.cache_resource
def get_client():
    try:
        if "OPENAI_API_KEY" not in st.secrets:
            st.error("❌ Secret OPENAI_API_KEY non trovato nei Secrets di Streamlit.")
            return None

        api_key = st.secrets["OPENAI_API_KEY"]

        if not api_key or not str(api_key).strip():
            st.error("❌ OPENAI_API_KEY presente ma vuota.")
            return None

        api_key = str(api_key).strip()

        # NON mostrare mai la chiave completa
        st.sidebar.success(
            f"🔑 API Key rilevata ({len(api_key)} caratteri)"
        )

        return OpenAI(api_key=api_key)

    except Exception as e:
        st.error(
            f"❌ Errore durante la configurazione OpenAI: {type(e).__name__}: {e}"
        )
        return None

client = get_client()


# ============================================================
# FUNZIONI DI UTILITÀ
# ============================================================

def normalizza_testo(valore):
    """
    Pulisce un valore proveniente da Excel o dall'AI.
    """

    if valore is None:
        return ""

    try:
        if pd.isna(valore):
            return ""
    except Exception:
        pass

    testo = str(valore).strip()

    if testo.lower() in [
        "nan",
        "none",
        "null",
        "n/d",
        "nd",
        "n.a.",
        "na",
    ]:
        return ""

    testo = re.sub(r"\s+", " ", testo)

    return testo


def normalizza_chiave(valore):
    """
    Normalizzazione aggressiva utilizzata per confrontare
    codici articolo e nomi cliente.
    """

    testo = normalizza_testo(valore).upper()

    sostituzioni = {
        "À": "A",
        "Á": "A",
        "È": "E",
        "É": "E",
        "Ì": "I",
        "Í": "I",
        "Ò": "O",
        "Ó": "O",
        "Ù": "U",
        "Ú": "U",
    }

    for vecchio, nuovo in sostituzioni.items():
        testo = testo.replace(vecchio, nuovo)

    return re.sub(
        r"[^A-Z0-9]",
        "",
        testo
    )


def similarita(a, b):
    a = normalizza_chiave(a)
    b = normalizza_chiave(b)

    if not a or not b:
        return 0

    if a == b:
        return 1

    return SequenceMatcher(
        None,
        a,
        b
    ).ratio()


def errore_rate_limit(error):
    testo = str(error).upper()

    return (
        "429" in testo
        or "RATE LIMIT" in testo
        or "TOO MANY REQUESTS" in testo
        or "QUOTA" in testo
    )


# ============================================================
# CARICAMENTO EXCEL
# ============================================================

@st.cache_data
def carica_excel(percorso):
    try:

        percorso = Path(percorso)

        if not percorso.exists():
            return pd.DataFrame()

        df = pd.read_excel(percorso)

        if df.empty:
            return pd.DataFrame()

        df.columns = (
            df.columns
            .astype(str)
            .str.strip()
        )

        return df

    except Exception:
        return pd.DataFrame()


df_clienti = carica_excel(FILE_CLIENTI)
df_articoli = carica_excel(FILE_ARTICOLI)


# ============================================================
# RICERCA COLONNE
# ============================================================

def trova_colonna(df, nomi):

    if df.empty:
        return None

    nomi_normalizzati = {
        normalizza_chiave(nome)
        for nome in nomi
    }

    for colonna in df.columns:

        if normalizza_chiave(colonna) in nomi_normalizzati:
            return colonna

    return None


# CLIENTI

colonna_ragione_sociale = trova_colonna(
    df_clienti,
    [
        "RAGIONE_SOCIALE",
        "RAGIONE SOCIALE",
        "RAGIONE SOCIALE CLIENTE",
        "CLIENTE",
        "NOME"
    ]
)


colonna_codice_cliente = trova_colonna(
    df_clienti,
    [
        "COD_CLIENTE",
        "CODICE CLIENTE",
        "CODICE",
        "CODCLI"
    ]
)


# ARTICOLI

colonna_codice_articolo = trova_colonna(
    df_articoli,
    [
        "CODART",
        "Codart",
        "COD_ARTICOLO",
        "CODICE ARTICOLO",
        "CODICE"
    ]
)


colonna_descrizione_articolo = trova_colonna(
    df_articoli,
    [
        "DESCRIZIONE ARTICOLO",
        "Descrizione articolo",
        "DESCRIZIONE"
    ]
)


# ============================================================
# COSTRUZIONE ANAGRAFICHE
# ============================================================

def costruisci_anagrafica_clienti():

    clienti = []

    if df_clienti.empty:
        return clienti

    if not colonna_ragione_sociale:
        return clienti

    for _, riga in df_clienti.iterrows():

        ragione = normalizza_testo(
            riga.get(
                colonna_ragione_sociale,
                ""
            )
        )

        if not ragione:
            continue

        codice = ""

        if colonna_codice_cliente:
            codice = normalizza_testo(
                riga.get(
                    colonna_codice_cliente,
                    ""
                )
            )

        clienti.append(
            {
                "ragione_sociale": ragione,
                "codice_cliente": codice
            }
        )

    return clienti


def costruisci_anagrafica_articoli():

    articoli = []

    if df_articoli.empty:
        return articoli

    if not colonna_codice_articolo:
        return articoli

    for _, riga in df_articoli.iterrows():

        codice = normalizza_testo(
            riga.get(
                colonna_codice_articolo,
                ""
            )
        )

        if not codice:
            continue

        descrizione = ""

        if colonna_descrizione_articolo:

            descrizione = normalizza_testo(
                riga.get(
                    colonna_descrizione_articolo,
                    ""
                )
            )

        articoli.append(
            {
                "codice": codice,
                "descrizione": descrizione
            }
        )

    return articoli


anagrafica_clienti = costruisci_anagrafica_clienti()
anagrafica_articoli = costruisci_anagrafica_articoli()


# ============================================================
# MAPPE VELOCI
# ============================================================

mappa_clienti = {}

for cliente in anagrafica_clienti:

    chiave = normalizza_chiave(
        cliente["ragione_sociale"]
    )

    if chiave:
        mappa_clienti[chiave] = cliente


mappa_codici_cliente = {}

for cliente in anagrafica_clienti:

    chiave = normalizza_chiave(
        cliente["codice_cliente"]
    )

    if chiave:
        mappa_codici_cliente[chiave] = cliente


mappa_articoli = {}

for articolo in anagrafica_articoli:

    chiave = normalizza_chiave(
        articolo["codice"]
    )

    if chiave:
        mappa_articoli[chiave] = articolo


lista_clienti = sorted(
    {
        x["ragione_sociale"]
        for x in anagrafica_clienti
    }
)


lista_codici_articoli = sorted(
    {
        x["codice"]
        for x in anagrafica_articoli
    }
)


lista_descrizioni = sorted(
    {
        x["descrizione"]
        for x in anagrafica_articoli
        if x["descrizione"]
    }
)


# ============================================================
# TROVA CLIENTE
# ============================================================

def trova_cliente(testo):

    testo = normalizza_testo(testo)

    if not testo:
        return None

    chiave = normalizza_chiave(testo)

    # Match esatto
    if chiave in mappa_clienti:
        return mappa_clienti[chiave]

    # Match per codice cliente
    if chiave in mappa_codici_cliente:
        return mappa_codici_cliente[chiave]

    # Contiene
    for cliente in anagrafica_clienti:

        nome = normalizza_chiave(
            cliente["ragione_sociale"]
        )

        if (
            chiave in nome
            or nome in chiave
        ):
            return cliente

    # Similarità
    migliore = None
    miglior_score = 0

    for cliente in anagrafica_clienti:

        score = similarita(
            testo,
            cliente["ragione_sociale"]
        )

        if score > miglior_score:

            miglior_score = score
            migliore = cliente

    if migliore and miglior_score >= 0.88:
        return migliore

    return None


# ============================================================
# TROVA ARTICOLO
# ============================================================

def trova_articolo(
    codice="",
    descrizione=""
):

    codice = normalizza_testo(codice)
    descrizione = normalizza_testo(descrizione)

    # --------------------------------------------------------
    # 1. CODICE ARTICOLO
    # --------------------------------------------------------

    if codice:

        chiave = normalizza_chiave(codice)

        if chiave in mappa_articoli:
            return mappa_articoli[chiave]

    # --------------------------------------------------------
    # 2. DESCRIZIONE
    # --------------------------------------------------------

    if descrizione:

        chiave_descrizione = normalizza_chiave(
            descrizione
        )

        candidati = []

        for articolo in anagrafica_articoli:

            if normalizza_chiave(
                articolo["descrizione"]
            ) == chiave_descrizione:

                candidati.append(
                    articolo
                )

        if len(candidati) == 1:
            return candidati[0]

        # Fuzzy match
        migliore = None
        miglior_score = 0

        for articolo in anagrafica_articoli:

            if not articolo["descrizione"]:
                continue

            score = similarita(
                descrizione,
                articolo["descrizione"]
            )

            if score > miglior_score:

                miglior_score = score
                migliore = articolo

        if migliore and miglior_score >= 0.92:
            return migliore

    return None


# ============================================================
# NORMALIZZA QUANTITÀ
# ============================================================

def normalizza_quantita(valore):

    testo = normalizza_testo(valore)

    if not testo:
        return ""

    # Gestisce 3
    # Gestisce 3 pezzi
    # Gestisce Q.tà 3
    # Gestisce 3,00

    match = re.search(
        r"\d+(?:[.,]\d+)?",
        testo
    )

    if not match:
        return ""

    try:

        numero = float(
            match.group()
            .replace(",", ".")
        )

        if numero.is_integer():
            return int(numero)

        return numero

    except Exception:
        return ""


# ============================================================
# NORMALIZZA DATA
# ============================================================

def normalizza_data(valore):

    testo = normalizza_testo(valore)

    if not testo:
        return ""

    try:

        data = pd.to_datetime(
            testo,
            dayfirst=True,
            errors="coerce"
        )

        if pd.isna(data):
            return ""

        return data.strftime(
            "%d/%m/%Y"
        )

    except Exception:
        return ""


# ============================================================
# PROMPT OPENAI
# ============================================================

def prompt_estrazione(tipo_documento):

    return f"""
Sei il motore di estrazione documentale di Target ERP.

TIPO DOCUMENTO:
{tipo_documento}

Analizza il documento allegato.

Devi estrarre tutte le righe articolo presenti.

Per ogni riga devi identificare:

- COD_CLIENTE
- RAGIONE_SOCIALE
- COD_ARTICOLO
- DESCRIZIONE
- QUANTITA
- DATA_CONSEGNA

REGOLE:

1. NON INVENTARE DATI.

2. Se un dato non è presente o non è leggibile,
   restituisci una stringa vuota.

3. Il COD_ARTICOLO deve essere copiato esattamente
   come appare nel documento.

4. La DESCRIZIONE deve essere quella visibile
   nel documento, se presente.

5. Ogni articolo deve essere una riga separata.

6. Se il documento contiene più articoli,
   restituisci tutte le righe.

7. Non sommare automaticamente articoli diversi.

8. Non modificare i codici articolo.

9. Non aggiungere spiegazioni.

10. Restituisci esclusivamente il JSON richiesto.
"""


# ============================================================
# JSON SCHEMA
# ============================================================

SCHEMA_ESTRAZIONE = {

    "type": "object",

    "properties": {

        "righe": {

            "type": "array",

            "items": {

                "type": "object",

                "properties": {

                    "COD_CLIENTE": {
                        "type": "string"
                    },

                    "RAGIONE_SOCIALE": {
                        "type": "string"
                    },

                    "COD_ARTICOLO": {
                        "type": "string"
                    },

                    "DESCRIZIONE": {
                        "type": "string"
                    },

                    "QUANTITA": {
                        "type": "string"
                    },

                    "DATA_CONSEGNA": {
                        "type": "string"
                    }

                },

                "required": [
                    "COD_CLIENTE",
                    "RAGIONE_SOCIALE",
                    "COD_ARTICOLO",
                    "DESCRIZIONE",
                    "QUANTITA",
                    "DATA_CONSEGNA"
                ],

                "additionalProperties": False
            }
        }
    },

    "required": [
        "righe"
    ],

    "additionalProperties": False
}


# ============================================================
# CHIAMATA OPENAI
# ============================================================

def chiama_openai(
    input_data,
    istruzioni=None,
    usa_json=False
):

    if not client:

        raise RuntimeError(
            "OPENAI_API_KEY non configurata."
        )

    parametri = {
        "model": MODELLO_OPENAI,
        "input": input_data
    }

    if istruzioni:
        parametri["instructions"] = istruzioni

    if usa_json:

        parametri["text"] = {
            "format": {
                "type": "json_schema",
                "name": "target_erp_extraction",
                "strict": True,
                "schema": SCHEMA_ESTRAZIONE
            }
        }

    try:

        return client.responses.create(
            **parametri
        )

    except Exception as e:

        if errore_rate_limit(e):

            time.sleep(2)

            return client.responses.create(
                **parametri
            )

        raise


# ============================================================
# CONVERTE FILE IN INPUT OPENAI
# ============================================================

def prepara_file_openai(uploaded_file):

    file_bytes = uploaded_file.getvalue()

    if not file_bytes:
        raise ValueError(
            "Il file è vuoto."
        )

    mime = uploaded_file.type

    encoded = base64.b64encode(
        file_bytes
    ).decode("utf-8")

    # PDF
    if mime == "application/pdf":

        return {
            "type": "input_file",
            "filename": uploaded_file.name,
            "file_data": (
                "data:application/pdf;base64,"
                + encoded
            )
        }

    # IMMAGINI
    if mime.startswith("image/"):

        return {
            "type": "input_image",
            "image_url": (
                f"data:{mime};base64,{encoded}"
            ),
            "detail": "high"
        }

    raise ValueError(
        "Formato file non supportato."
    )


# ============================================================
# NORMALIZZA RECORD
# ============================================================

def normalizza_record(record):

    if not isinstance(record, dict):
        return None

    ragione_raw = normalizza_testo(
        record.get(
            "RAGIONE_SOCIALE",
            ""
        )
    )

    codice_cliente_raw = normalizza_testo(
        record.get(
            "COD_CLIENTE",
            ""
        )
    )

    codice_articolo_raw = normalizza_testo(
        record.get(
            "COD_ARTICOLO",
            ""
        )
    )

    descrizione_raw = normalizza_testo(
        record.get(
            "DESCRIZIONE",
            ""
        )
    )

    quantita_raw = normalizza_testo(
        record.get(
            "QUANTITA",
            ""
        )
    )

    data_raw = normalizza_testo(
        record.get(
            "DATA_CONSEGNA",
            ""
        )
    )

    # --------------------------------------------------------
    # CLIENTE
    # --------------------------------------------------------

    cliente = trova_cliente(
        ragione_raw
    )

    if not cliente and codice_cliente_raw:

        cliente = mappa_codici_cliente.get(
            normalizza_chiave(
                codice_cliente_raw
            )
        )

    if cliente:

        codice_cliente = cliente[
            "codice_cliente"
        ]

        ragione_sociale = cliente[
            "ragione_sociale"
        ]

    else:

        codice_cliente = (
            codice_cliente_raw
        )

        ragione_sociale = (
            ragione_raw
        )

    # --------------------------------------------------------
    # ARTICOLO
    # --------------------------------------------------------

    articolo = trova_articolo(
        codice=codice_articolo_raw,
        descrizione=descrizione_raw
    )

    if articolo:

        # QUESTO È IL PUNTO FONDAMENTALE:
        #
        # Se troviamo il codice nell'anagrafica,
        # la descrizione ufficiale viene presa
        # DIRETTAMENTE DA articoli.xlsx.

        codice_articolo = articolo[
            "codice"
        ]

        descrizione = articolo[
            "descrizione"
        ]

    else:

        codice_articolo = (
            codice_articolo_raw
        )

        descrizione = (
            descrizione_raw
        )

    return {

        "COD_CLIENTE":
            codice_cliente,

        "RAGIONE_SOCIALE":
            ragione_sociale,

        "COD_ARTICOLO":
            codice_articolo,

        "DESCRIZIONE":
            descrizione,

        "QUANTITA":
            normalizza_quantita(
                quantita_raw
            ),

        "DATA_CONSEGNA":
            normalizza_data(
                data_raw
            )
    }


# ============================================================
# ANALIZZA PDF / IMMAGINE
# ============================================================

def analizza_file(
    uploaded_file,
    tipo_documento
):

    file_input = prepara_file_openai(
        uploaded_file
    )

    response = chiama_openai(

        input_data=[

            {
                "role": "user",

                "content": [

                    file_input,

                    {
                        "type": "input_text",

                        "text":
                            prompt_estrazione(
                                tipo_documento
                            )
                    }

                ]
            }

        ],

        usa_json=True
    )

    testo_json = response.output_text

    try:

        risultato = json.loads(
            testo_json
        )

    except Exception as e:

        raise ValueError(
            "OpenAI non ha restituito "
            f"un JSON valido: {e}"
        )

    righe = []

    for record in risultato.get(
        "righe",
        []
    ):

        riga = normalizza_record(
            record
        )

        if riga:
            righe.append(riga)

    return righe


# ============================================================
# ANALIZZA EMAIL
# ============================================================

def analizza_email(
    testo_email,
    tipo_documento
):

    response = chiama_openai(

        input_data=[

            {
                "role": "user",

                "content": [

                    {
                        "type": "input_text",

                        "text":
                            prompt_estrazione(
                                tipo_documento
                            )
                            + """

TESTO EMAIL / DOCUMENTO:

"""
                            + testo_email
                    }

                ]
            }

        ],

        usa_json=True
    )

    try:

        risultato = json.loads(
            response.output_text
        )

    except Exception as e:

        raise ValueError(
            "Risposta JSON non valida: "
            f"{e}"
        )

    righe = []

    for record in risultato.get(
        "righe",
        []
    ):

        riga = normalizza_record(
            record
        )

        if riga:
            righe.append(riga)

    return righe


# ============================================================
# VICTORIA
# ============================================================

@st.cache_data
def carica_listino():

    if not FILE_LISTINO.exists():
        return None

    try:
        return FILE_LISTINO.read_bytes()

    except Exception:
        return None


def chiedi_a_victoria(domanda):

    pdf_bytes = carica_listino()

    if not pdf_bytes:

        raise RuntimeError(
            "Il file listino.pdf non è presente."
        )

    encoded = base64.b64encode(
        pdf_bytes
    ).decode("utf-8")

    istruzioni = """
Sei Victoria, l'assistente virtuale ufficiale
del software Target ERP.

Devi rispondere esclusivamente utilizzando
il listino PDF allegato.

REGOLE:

- Non inventare prezzi.
- Non inventare codici.
- Non inventare caratteristiche.
- Se una informazione non è presente nel listino,
  dichiaralo chiaramente.
- Non utilizzare clienti.xlsx.
- Non utilizzare articoli.xlsx.
- Rispondi sempre in italiano.
- Rispondi in modo professionale e sintetico.
- Se ti chiedono chi ti ha creata o sviluppata,
  rispondi che sei stata creata da Andrea Uzzardi.
- Non parlare spontaneamente di OpenAI,
  API o dettagli tecnici.
"""

    response = chiama_openai(

        input_data=[

            {
                "role": "user",

                "content": [

                    {
                        "type": "input_file",
                        "filename": "listino.pdf",
                        "file_data":
                            "data:application/pdf;base64,"
                            + encoded
                    },

                    {
                        "type": "input_text",
                        "text": domanda
                    }

                ]
            }

        ],

        istruzioni=istruzioni,
        usa_json=False
    )

    return response.output_text.strip()


# ============================================================
# SESSION STATE
# ============================================================

if "dati" not in st.session_state:
    st.session_state.dati = []


if "messages" not in st.session_state:
    st.session_state.messages = []


# ============================================================
# HEADER
# ============================================================

col_titolo, col_chat = st.columns(
    [3, 1]
)


with col_titolo:

    st.title(
        "📦 Target ERP — Smart Order & Quote Hub"
    )


with col_chat:

    with st.popover(
        "💬 Chat con Victoria",
        use_container_width=True
    ):

        st.subheader(
            "🤖 Victoria — Target ERP"
        )

        st.caption(
            "Chiedi informazioni sui prodotti "
            "del listino."
        )

        chat_container = st.container(
            height=350
        )

        with chat_container:

            for messaggio in st.session_state.messages:

                with st.chat_message(
                    messaggio["role"]
                ):

                    st.markdown(
                        messaggio["content"]
                    )

        domanda = st.chat_input(
            "Chiedi informazioni sul listino..."
        )

        if domanda:

            st.session_state.messages.append(
                {
                    "role": "user",
                    "content": domanda
                }
            )

            try:

                with st.spinner(
                    "Victoria sta consultando il listino..."
                ):

                    risposta = chiedi_a_victoria(
                        domanda
                    )

            except Exception as e:

                if errore_rate_limit(e):

                    risposta = (
                        "Il servizio è momentaneamente "
                        "sovraccarico. Riprova tra poco."
                    )

                else:

                    risposta = (
                        f"Si è verificato un errore: {e}"
                    )

            st.session_state.messages.append(
                {
                    "role": "assistant",
                    "content": risposta
                }
            )

            st.rerun()


# ============================================================
# SELEZIONE DOCUMENTO
# ============================================================

st.write(
    "Seleziona il tipo di documento:"
)


tipo_documento = st.radio(

    "Tipo documento",

    [
        "🛒 Ordine Cliente",
        "📋 Offerta"
    ],

    horizontal=True,

    label_visibility="collapsed"
)


# ============================================================
# TABS
# ============================================================

tab_upload, tab_email = st.tabs(
    [
        "📄 Carica PDF / Immagine",
        "✉️ Incolla Testo Email"
    ]
)


# ============================================================
# UPLOAD FILE
# ============================================================

with tab_upload:

    uploaded_file = st.file_uploader(

        "Trascina qui il PDF o l'immagine",

        type=[
            "pdf",
            "jpg",
            "jpeg",
            "png",
            "webp"
        ],

        label_visibility="collapsed"
    )

    if uploaded_file:

        if st.button(
            "⚡ Analizza File ed Inserisci in Tabella",
            type="primary"
        ):

            if not client:

                st.error(
                    "OPENAI_API_KEY non configurata."
                )

            else:

                with st.spinner(
                    "ChatGPT sta leggendo il documento..."
                ):

                    try:

                        nuove_righe = analizza_file(

                            uploaded_file,

                            tipo_documento
                        )

                        if nuove_righe:

                            st.session_state.dati.extend(
                                nuove_righe
                            )

                            st.success(
                                f"{len(nuove_righe)} "
                                "righe estratte correttamente."
                            )

                            st.rerun()

                        else:

                            st.warning(
                                "Non sono state trovate "
                                "righe articolo."
                            )

                    except Exception as e:

                        st.error(
                            f"Errore durante l'analisi: {e}"
                        )


# ============================================================
# EMAIL
# ============================================================

with tab_email:

    testo_email = st.text_area(

        "Incolla qui il testo dell'email "
        "o dell'ordine",

        height=180
    )

    if st.button(
        "⚡ Analizza Email ed Inserisci in Tabella",
        type="primary"
    ):

        if not testo_email.strip():

            st.warning(
                "Incolla il testo prima di procedere."
            )

        elif not client:

            st.error(
                "OPENAI_API_KEY non configurata."
            )

        else:

            with st.spinner(
                "ChatGPT sta analizzando l'email..."
            ):

                try:

                    nuove_righe = analizza_email(

                        testo_email,

                        tipo_documento
                    )

                    if nuove_righe:

                        st.session_state.dati.extend(
                            nuove_righe
                        )

                        st.success(
                            f"{len(nuove_righe)} "
                            "righe estratte correttamente."
                        )

                        st.rerun()

                    else:

                        st.warning(
                            "Non sono state trovate "
                            "righe articolo."
                        )

                except Exception as e:

                    st.error(
                        f"Errore durante l'estrazione: {e}"
                    )


# ============================================================
# TABELLA
# ============================================================

st.divider()

st.subheader(
    "Gestione Ordini e Articoli"
)


if st.session_state.dati:

    df = pd.DataFrame(
        st.session_state.dati
    )

else:

    df = pd.DataFrame(
        columns=[
            "COD_CLIENTE",
            "RAGIONE_SOCIALE",
            "COD_ARTICOLO",
            "DESCRIZIONE",
            "QUANTITA",
            "DATA_CONSEGNA"
        ]
    )


# Assicuriamoci che tutte le colonne esistano

for colonna in [
    "COD_CLIENTE",
    "RAGIONE_SOCIALE",
    "COD_ARTICOLO",
    "DESCRIZIONE",
    "QUANTITA",
    "DATA_CONSEGNA"
]:

    if colonna not in df.columns:
        df[colonna] = ""


df = df[
    [
        "COD_CLIENTE",
        "RAGIONE_SOCIALE",
        "COD_ARTICOLO",
        "DESCRIZIONE",
        "QUANTITA",
        "DATA_CONSEGNA"
    ]
]


# ============================================================
# SINCRONIZZAZIONE CLIENTI
# ============================================================

def sincronizza_cliente_riga(riga):

    ragione = normalizza_testo(
        riga["RAGIONE_SOCIALE"]
    )

    codice = normalizza_testo(
        riga["COD_CLIENTE"]
    )

    cliente = trova_cliente(
        ragione
    )

    if not cliente and codice:

        cliente = mappa_codici_cliente.get(
            normalizza_chiave(
                codice
            )
        )

    if cliente:

        riga["RAGIONE_SOCIALE"] = (
            cliente["ragione_sociale"]
        )

        riga["COD_CLIENTE"] = (
            cliente["codice_cliente"]
        )

    return riga


# ============================================================
# SINCRONIZZAZIONE ARTICOLI
# ============================================================

def sincronizza_articolo_riga(riga):

    codice = normalizza_testo(
        riga["COD_ARTICOLO"]
    )

    descrizione = normalizza_testo(
        riga["DESCRIZIONE"]
    )

    # --------------------------------------------------------
    # CODICE → DESCRIZIONE
    # --------------------------------------------------------

    if codice:

        articolo = trova_articolo(
            codice=codice
        )

        if articolo:

            riga["COD_ARTICOLO"] = (
                articolo["codice"]
            )

            # DESCRIZIONE UFFICIALE
            riga["DESCRIZIONE"] = (
                articolo["descrizione"]
            )

            return riga

    # --------------------------------------------------------
    # DESCRIZIONE → CODICE
    # --------------------------------------------------------

    if descrizione:

        articolo = trova_articolo(
            descrizione=descrizione
        )

        if articolo:

            riga["COD_ARTICOLO"] = (
                articolo["codice"]
            )

            riga["DESCRIZIONE"] = (
                articolo["descrizione"]
            )

    return riga


# Sincronizzazione iniziale

if not df.empty:

    df = df.apply(
        sincronizza_cliente_riga,
        axis=1
    )

    df = df.apply(
        sincronizza_articolo_riga,
        axis=1
    )


# ============================================================
# CONFIGURAZIONE TABELLA
# ============================================================

column_config = {}


if lista_clienti:

    column_config[
        "RAGIONE_SOCIALE"
    ] = st.column_config.SelectboxColumn(

        "RAGIONE SOCIALE",

        options=lista_clienti,

        required=False
    )


if lista_codici_articoli:

    column_config[
        "COD_ARTICOLO"
    ] = st.column_config.SelectboxColumn(

        "COD_ARTICOLO",

        options=lista_codici_articoli,

        required=False
    )


if lista_descrizioni:

    column_config[
        "DESCRIZIONE"
    ] = st.column_config.SelectboxColumn(

        "DESCRIZIONE",

        options=lista_descrizioni,

        required=False
    )


column_config[
    "COD_CLIENTE"
] = st.column_config.TextColumn(

    "COD_CLIENTE",

    disabled=True
)


column_config[
    "QUANTITA"
] = st.column_config.NumberColumn(

    "QUANTITA",

    min_value=0,

    step=1
)


column_config[
    "DATA_CONSEGNA"
] = st.column_config.TextColumn(

    "DATA CONSEGNA",

    help="Formato: GG/MM/AAAA"
)


# ============================================================
# DATA EDITOR
# ============================================================

edited_df = st.data_editor(

    df,

    column_config=column_config,

    use_container_width=True,

    num_rows="dynamic",

    key="editor_tabella"
)


# ============================================================
# SINCRONIZZAZIONE DOPO MODIFICA
# ============================================================

if not edited_df.empty:

    edited_df = edited_df.apply(
        sincronizza_cliente_riga,
        axis=1
    )

    edited_df = edited_df.apply(
        sincronizza_articolo_riga,
        axis=1
    )

    edited_df["QUANTITA"] = (
        edited_df["QUANTITA"]
        .apply(normalizza_quantita)
    )

    edited_df["DATA_CONSEGNA"] = (
        edited_df["DATA_CONSEGNA"]
        .apply(normalizza_data)
    )


edited_df = edited_df.fillna("")


st.session_state.dati = (
    edited_df
    .to_dict(
        orient="records"
    )
)


# ============================================================
# ESPORTAZIONE CSV
# ============================================================

st.divider()


csv_data = (
    edited_df
    .to_csv(
        index=False,
        encoding="utf-8-sig"
    )
    .encode("utf-8-sig")
)


st.download_button(

    label="📥 Esporta CSV Tabella",

    data=csv_data,

    file_name="gestione_ordini.csv",

    mime="text/csv",

    type="primary"
)


# ============================================================
# STATO SISTEMA
# ============================================================

with st.expander(
    "ℹ️ Stato sistema"
):

    col1, col2, col3 = st.columns(3)

    with col1:

        st.metric(
            "Clienti caricati",
            len(anagrafica_clienti)
        )

    with col2:

        st.metric(
            "Articoli caricati",
            len(anagrafica_articoli)
        )

    with col3:

        st.metric(
            "Righe in tabella",
            len(edited_df)
        )

    if client:

        st.success(
            "OpenAI API configurata"
        )

    else:

        st.error(
            "OPENAI_API_KEY non configurata"
        )

    if not df_clienti.empty:

        st.caption(
            f"✓ clienti.xlsx: "
            f"{len(df_clienti)} righe"
        )

    else:

        st.warning(
            "clienti.xlsx non trovato"
        )

    if not df_articoli.empty:

        st.caption(
            f"✓ articoli.xlsx: "
            f"{len(df_articoli)} righe"
        )

    else:

        st.warning(
            "articoli.xlsx non trovato"
        )

    if FILE_LISTINO.exists():

        st.caption(
            f"✓ Listino trovato: "
            f"{FILE_LISTINO.name}"
        )

    else:

        st.warning(
            "listino.pdf non trovato"
        )