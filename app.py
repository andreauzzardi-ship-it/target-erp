import base64
import json
import re
import time
from difflib import SequenceMatcher
from pathlib import Path

import pandas as pd
import streamlit as st
from openai import OpenAI


# ============================================================
# CONFIGURAZIONE
# ============================================================

st.set_page_config(
    page_title="Target ERP - Smart Order & Quote Hub",
    layout="wide"
)

BASE_DIR = Path(__file__).resolve().parent

FILE_CLIENTI = BASE_DIR / "clienti.xlsx"
FILE_ARTICOLI = BASE_DIR / "articoli.xlsx"
FILE_LISTINO = BASE_DIR / "listino.pdf"

# Modello economico e adatto ad alto volume
MODELLO_ESTRAZIONE = "gpt-5.6-luna"

# Modello per Victoria
MODELLO_VICTORIA = "gpt-5.6-luna"


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
# OPENAI
# ============================================================

@st.cache_resource
def get_client():

    try:

        api_key = st.secrets.get("OPENAI_API_KEY", "")

        if not api_key:
            return None

        api_key = str(api_key).strip()

        if not api_key:
            return None

        return OpenAI(
            api_key=api_key
        )

    except Exception:
        return None


client = get_client()


# ============================================================
# UTILITY
# ============================================================

def normalizza_testo(valore):

    if valore is None:
        return ""

    try:
        if pd.isna(valore):
            return ""
    except Exception:
        pass

    testo = str(valore).strip()

    if testo.lower() in {
        "nan",
        "none",
        "null",
        "n/d",
        "nd",
        "n.a.",
        "na",
    }:
        return ""

    testo = re.sub(
        r"\s+",
        " ",
        testo
    )

    return testo


def normalizza_chiave(valore):

    testo = normalizza_testo(
        valore
    ).upper()

    sostituzioni = {
        "À": "A",
        "Á": "A",
        "Â": "A",
        "Ä": "A",
        "È": "E",
        "É": "E",
        "Ê": "E",
        "Ë": "E",
        "Ì": "I",
        "Í": "I",
        "Î": "I",
        "Ï": "I",
        "Ò": "O",
        "Ó": "O",
        "Ô": "O",
        "Ö": "O",
        "Ù": "U",
        "Ú": "U",
        "Û": "U",
        "Ü": "U",
    }

    for vecchio, nuovo in sostituzioni.items():
        testo = testo.replace(
            vecchio,
            nuovo
        )

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


# ============================================================
# GESTIONE ERRORI OPENAI
# ============================================================

def descrivi_errore_openai(error):

    testo = str(error)
    testo_upper = testo.upper()

    if "401" in testo or "INVALID_API_KEY" in testo_upper:
        return (
            "❌ API Key OpenAI non valida. "
            "Controlla la chiave inserita nei Secrets di Streamlit."
        )

    if "403" in testo:
        return (
            "❌ Accesso OpenAI negato. "
            "Controlla progetto, permessi o configurazione API."
        )

    if "429" in testo or "RATE LIMIT" in testo_upper:

        return (
            "⏳ OpenAI ha temporaneamente limitato le richieste. "
            "Attendi qualche secondo e riprova."
        )

    if "500" in testo:
        return (
            "⚠️ Il server OpenAI ha restituito un errore temporaneo "
            "(500). Riprova tra qualche secondo."
        )

    if "502" in testo or "503" in testo:
        return (
            "⚠️ Il servizio OpenAI è momentaneamente non disponibile. "
            "Riprova tra poco."
        )

    if "TIMEOUT" in testo_upper:
        return (
            "⏱️ La richiesta è scaduta. "
            "Il documento potrebbe essere molto grande."
        )

    return (
        f"Errore OpenAI: {testo}"
    )


# ============================================================
# EXCEL
# ============================================================

@st.cache_data
def carica_excel(percorso):

    try:

        percorso = Path(percorso)

        if not percorso.exists():
            return pd.DataFrame()

        df = pd.read_excel(
            percorso
        )

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


df_clienti = carica_excel(
    FILE_CLIENTI
)

df_articoli = carica_excel(
    FILE_ARTICOLI
)


# ============================================================
# TROVA COLONNA
# ============================================================

def trova_colonna(df, possibili):

    if df.empty:
        return None

    target = {
        normalizza_chiave(x)
        for x in possibili
    }

    for colonna in df.columns:

        if normalizza_chiave(
            colonna
        ) in target:

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
        "NOME",
    ]
)

colonna_codice_cliente = trova_colonna(
    df_clienti,
    [
        "COD_CLIENTE",
        "CODICE CLIENTE",
        "CODICE",
        "CODCLI",
    ]
)


# ARTICOLI

colonna_codice_articolo = trova_colonna(
    df_articoli,
    [
        "CODART",
        "COD_ARTICOLO",
        "CODICE ARTICOLO",
        "CODICE",
    ]
)

colonna_descrizione_articolo = trova_colonna(
    df_articoli,
    [
        "DESCRIZIONE ARTICOLO",
        "DESCRIZIONE",
    ]
)


# ============================================================
# ANAGRAFICA CLIENTI
# ============================================================

def costruisci_clienti():

    risultato = []

    if df_clienti.empty:
        return risultato

    if not colonna_ragione_sociale:
        return risultato

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

        risultato.append(
            {
                "ragione_sociale": ragione,
                "codice_cliente": codice,
            }
        )

    return risultato


# ============================================================
# ANAGRAFICA ARTICOLI
# ============================================================

def costruisci_articoli():

    risultato = []

    if df_articoli.empty:
        return risultato

    if not colonna_codice_articolo:
        return risultato

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

        risultato.append(
            {
                "codice": codice,
                "descrizione": descrizione,
            }
        )

    return risultato


anagrafica_clienti = costruisci_clienti()
anagrafica_articoli = costruisci_articoli()


# ============================================================
# MAPPE
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
# RICERCA CLIENTE
# ============================================================

def trova_cliente(testo):

    testo = normalizza_testo(
        testo
    )

    if not testo:
        return None

    chiave = normalizza_chiave(
        testo
    )

    # MATCH ESATTO
    if chiave in mappa_clienti:
        return mappa_clienti[chiave]

    # CODICE CLIENTE
    if chiave in mappa_codici_cliente:
        return mappa_codici_cliente[chiave]

    # CONTIENE
    for cliente in anagrafica_clienti:

        nome = normalizza_chiave(
            cliente["ragione_sociale"]
        )

        if (
            chiave in nome
            or nome in chiave
        ):
            return cliente

    # FUZZY
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

    if (
        migliore
        and miglior_score >= 0.88
    ):
        return migliore

    return None


# ============================================================
# RICERCA ARTICOLO
# ============================================================

def trova_articolo(
    codice="",
    descrizione=""
):

    codice = normalizza_testo(
        codice
    )

    descrizione = normalizza_testo(
        descrizione
    )

    # ========================================================
    # PRIORITÀ ASSOLUTA: CODICE
    # ========================================================

    if codice:

        chiave = normalizza_chiave(
            codice
        )

        # MATCH ESATTO
        if chiave in mappa_articoli:

            return mappa_articoli[
                chiave
            ]

    # ========================================================
    # DESCRIZIONE ESATTA
    # ========================================================

    if descrizione:

        chiave = normalizza_chiave(
            descrizione
        )

        for articolo in anagrafica_articoli:

            if (
                normalizza_chiave(
                    articolo["descrizione"]
                )
                == chiave
            ):

                return articolo

    # ========================================================
    # DESCRIZIONE FUZZY
    # ========================================================

    if descrizione:

        migliore = None
        miglior_score = 0

        for articolo in anagrafica_articoli:

            desc = articolo[
                "descrizione"
            ]

            if not desc:
                continue

            score = similarita(
                descrizione,
                desc
            )

            if score > miglior_score:

                miglior_score = score
                migliore = articolo

        if (
            migliore
            and miglior_score >= 0.90
        ):
            return migliore

    return None


# ============================================================
# QUANTITÀ
# ============================================================

def normalizza_quantita(valore):

    testo = normalizza_testo(
        valore
    )

    if not testo:
        return ""

    match = re.search(
        r"\d+(?:[.,]\d+)?",
        testo
    )

    if not match:
        return ""

    try:

        numero = float(
            match.group().replace(
                ",",
                "."
            )
        )

        if numero.is_integer():
            return int(numero)

        return numero

    except Exception:
        return ""


# ============================================================
# DATA
# ============================================================

def normalizza_data(valore):

    testo = normalizza_testo(
        valore
    )

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
# SCHEMA
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

                    "DESCRIZIONE_DOCUMENTO": {
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
                    "DESCRIZIONE_DOCUMENTO",
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
# PROMPT
# ============================================================

def prompt_estrazione(tipo_documento):

    return f"""
Sei il motore OCR/documentale di Target ERP.

TIPO DOCUMENTO:
{tipo_documento}

Devi leggere il documento e individuare tutte le righe
relative agli articoli ordinati o richiesti.

Per ogni riga estrai:

COD_CLIENTE
RAGIONE_SOCIALE
COD_ARTICOLO
DESCRIZIONE_DOCUMENTO
QUANTITA
DATA_CONSEGNA

REGOLE IMPORTANTISSIME:

1. NON INVENTARE MAI UN CODICE.

2. COPIA IL CODICE ARTICOLO ESATTAMENTE COME APPARE
   NEL DOCUMENTO.

3. Se il codice è poco leggibile, prova a leggerlo
   dal documento ma non inventarlo.

4. DESCRIZIONE_DOCUMENTO deve contenere la descrizione
   visibile nel documento, se presente.

5. Non devi cercare la descrizione ufficiale:
   quella verrà recuperata automaticamente da articoli.xlsx.

6. Ogni riga articolo deve diventare una riga JSON.

7. Non unire articoli diversi.

8. Non eliminare righe duplicate.

9. Se un valore non è presente restituisci stringa vuota.

10. Restituisci esclusivamente il JSON richiesto.
"""


# ============================================================
# INPUT FILE
# ============================================================

def prepara_file(uploaded_file):

    dati = uploaded_file.getvalue()

    if not dati:
        raise ValueError(
            "Il file caricato è vuoto."
        )

    mime = uploaded_file.type

    encoded = base64.b64encode(
        dati
    ).decode("utf-8")

    # PDF
    if mime == "application/pdf":

        return {
            "type": "input_file",
            "filename": uploaded_file.name,
            "file_data":
                "data:application/pdf;base64,"
                + encoded
        }

    # IMMAGINE
    if mime.startswith("image/"):

        return {
            "type": "input_image",
            "image_url":
                f"data:{mime};base64,{encoded}",
            "detail": "high"
        }

    raise ValueError(
        "Formato non supportato."
    )


# ============================================================
# CHIAMATA OPENAI
# ============================================================

def chiama_openai(
    input_data,
    istruzioni=None,
    schema=None
):

    if not client:

        raise RuntimeError(
            "OPENAI_API_KEY non configurata."
        )

    params = {

        "model":
            MODELLO_ESTRAZIONE,

        "input":
            input_data,
    }

    if istruzioni:

        params[
            "instructions"
        ] = istruzioni

    if schema:

        params["text"] = {

            "format": {

                "type":
                    "json_schema",

                "name":
                    "target_erp_extraction",

                "strict":
                    True,

                "schema":
                    schema,
            }
        }

    # UNA SOLA RICHIESTA.
    # Nessun retry automatico aggressivo.
    return client.responses.create(
        **params
    )


# ============================================================
# NORMALIZZAZIONE RECORD
# ============================================================

def normalizza_record(record):

    if not isinstance(
        record,
        dict
    ):
        return None

    codice_cliente_raw = normalizza_testo(
        record.get(
            "COD_CLIENTE",
            ""
        )
    )

    ragione_raw = normalizza_testo(
        record.get(
            "RAGIONE_SOCIALE",
            ""
        )
    )

    codice_articolo_raw = normalizza_testo(
        record.get(
            "COD_ARTICOLO",
            ""
        )
    )

    descrizione_documento = normalizza_testo(
        record.get(
            "DESCRIZIONE_DOCUMENTO",
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

    # ========================================================
    # CLIENTE
    # ========================================================

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

    # ========================================================
    # ARTICOLO
    # ========================================================

    articolo = trova_articolo(

        codice=
            codice_articolo_raw,

        descrizione=
            descrizione_documento
    )

    if articolo:

        # ====================================================
        # QUESTO È IL PUNTO CHIAVE
        #
        # La descrizione NON viene presa da OpenAI.
        #
        # Viene presa direttamente da articoli.xlsx.
        # ====================================================

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
            descrizione_documento
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
# ANALISI FILE
# ============================================================

def analizza_file(
    uploaded_file,
    tipo_documento
):

    file_input = prepara_file(
        uploaded_file
    )

    response = chiama_openai(

        input_data=[

            {

                "role":
                    "user",

                "content": [

                    file_input,

                    {

                        "type":
                            "input_text",

                        "text":
                            prompt_estrazione(
                                tipo_documento
                            )
                    }
                ]
            }
        ],

        schema=
            SCHEMA_ESTRAZIONE
    )

    testo = response.output_text

    if not testo:

        raise RuntimeError(
            "OpenAI non ha restituito alcun risultato."
        )

    try:

        risultato = json.loads(
            testo
        )

    except Exception as e:

        raise RuntimeError(
            "Risposta OpenAI non valida: "
            + str(e)
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
            righe.append(
                riga
            )

    return righe


# ============================================================
# ANALISI EMAIL
# ============================================================

def analizza_email(
    testo_email,
    tipo_documento
):

    if not testo_email.strip():

        return []

    input_data = [

        {

            "role":
                "user",

            "content": [

                {

                    "type":
                        "input_text",

                    "text":
                        prompt_estrazione(
                            tipo_documento
                        )
                        + """

TESTO DEL DOCUMENTO:

"""
                        + testo_email
                }
            ]
        }
    ]

    response = chiama_openai(

        input_data=input_data,

        schema=
            SCHEMA_ESTRAZIONE
    )

    try:

        risultato = json.loads(
            response.output_text
        )

    except Exception as e:

        raise RuntimeError(
            "JSON OpenAI non valido: "
            + str(e)
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
            righe.append(
                riga
            )

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

    pdf = carica_listino()

    if not pdf:

        raise RuntimeError(
            "listino.pdf non trovato."
        )

    encoded = base64.b64encode(
        pdf
    ).decode("utf-8")

    istruzioni = """
Sei Victoria, l'assistente virtuale ufficiale
del software Target ERP.

Devi rispondere utilizzando esclusivamente
il listino PDF allegato.

Regole:

- Non inventare prezzi.
- Non inventare codici.
- Non inventare caratteristiche.
- Se una informazione non è presente,
  dichiaralo chiaramente.
- Non usare clienti.xlsx.
- Non usare articoli.xlsx.
- Rispondi in italiano.
- Sii professionale e sintetica.
- Se chiedono chi ti ha creata:
  rispondi che sei stata creata da Andrea Uzzardi.
"""

    response = client.responses.create(

        model=
            MODELLO_VICTORIA,

        instructions=
            istruzioni,

        input=[

            {

                "role":
                    "user",

                "content": [

                    {

                        "type":
                            "input_file",

                        "filename":
                            "listino.pdf",

                        "file_data":
                            "data:application/pdf;base64,"
                            + encoded
                    },

                    {

                        "type":
                            "input_text",

                        "text":
                            domanda
                    }
                ]
            }
        ]
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

            for msg in st.session_state.messages:

                with st.chat_message(
                    msg["role"]
                ):

                    st.markdown(
                        msg["content"]
                    )

        domanda = st.chat_input(
            "Chiedi informazioni sul listino..."
        )

        if domanda:

            st.session_state.messages.append(
                {
                    "role":
                        "user",

                    "content":
                        domanda
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

                risposta = descrivi_errore_openai(
                    e
                )

            st.session_state.messages.append(
                {
                    "role":
                        "assistant",

                    "content":
                        risposta
                }
            )

            st.rerun()


# ============================================================
# TIPO DOCUMENTO
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
# UPLOAD
# ============================================================

with tab_upload:

    uploaded_file = st.file_uploader(

        "Trascina qui il documento",

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

        st.caption(
            f"📎 {uploaded_file.name}"
        )

        if st.button(
            "⚡ Analizza File ed Inserisci in Tabella",
            type="primary"
        ):

            if not client:

                st.error(
                    "❌ OPENAI_API_KEY non configurata."
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
                                f"✓ {len(nuove_righe)} "
                                "righe inserite."
                            )

                            time.sleep(
                                0.5
                            )

                            st.rerun()

                        else:

                            st.warning(
                                "Nessuna riga articolo trovata."
                            )

                    except Exception as e:

                        st.error(
                            descrivi_errore_openai(
                                e
                            )
                        )


# ============================================================
# EMAIL
# ============================================================

with tab_email:

    testo_email = st.text_area(

        "Incolla qui il testo dell'email",

        height=180
    )

    if st.button(
        "⚡ Analizza Email ed Inserisci in Tabella",
        type="primary"
    ):

        if not testo_email.strip():

            st.warning(
                "Incolla prima il testo dell'email."
            )

        elif not client:

            st.error(
                "❌ OPENAI_API_KEY non configurata."
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
                            f"✓ {len(nuove_righe)} "
                            "righe inserite."
                        )

                        st.rerun()

                    else:

                        st.warning(
                            "Nessuna riga articolo trovata."
                        )

                except Exception as e:

                    st.error(
                        descrivi_errore_openai(
                            e
                        )
                    )


# ============================================================
# TABELLA
# ============================================================

st.divider()

st.subheader(
    "Gestione Ordini e Articoli"
)


COLONNE = [
    "COD_CLIENTE",
    "RAGIONE_SOCIALE",
    "COD_ARTICOLO",
    "DESCRIZIONE",
    "QUANTITA",
    "DATA_CONSEGNA"
]


if st.session_state.dati:

    df = pd.DataFrame(
        st.session_state.dati
    )

else:

    df = pd.DataFrame(
        columns=COLONNE
    )


for colonna in COLONNE:

    if colonna not in df.columns:

        df[colonna] = ""


df = df[COLONNE]


# ============================================================
# SINCRONIZZAZIONE
# ============================================================

def sincronizza_riga(riga):

    # ========================================================
    # CLIENTE
    # ========================================================

    cliente = trova_cliente(
        riga.get(
            "RAGIONE_SOCIALE",
            ""
        )
    )

    if not cliente:

        cliente = mappa_codici_cliente.get(
            normalizza_chiave(
                riga.get(
                    "COD_CLIENTE",
                    ""
                )
            )
        )

    if cliente:

        riga["RAGIONE_SOCIALE"] = (
            cliente[
                "ragione_sociale"
            ]
        )

        riga["COD_CLIENTE"] = (
            cliente[
                "codice_cliente"
            ]
        )

    # ========================================================
    # ARTICOLO
    # ========================================================

    articolo = trova_articolo(

        codice=
            riga.get(
                "COD_ARTICOLO",
                ""
            ),

        descrizione=
            riga.get(
                "DESCRIZIONE",
                ""
            )
    )

    if articolo:

        # ====================================================
        # CODICE E DESCRIZIONE DEVONO SEMPRE ESSERE
        # QUELLI DELL'ANAGRAFICA EXCEL.
        # ====================================================

        riga["COD_ARTICOLO"] = (
            articolo["codice"]
        )

        riga["DESCRIZIONE"] = (
            articolo["descrizione"]
        )

    riga["QUANTITA"] = normalizza_quantita(
        riga.get(
            "QUANTITA",
            ""
        )
    )

    riga["DATA_CONSEGNA"] = normalizza_data(
        riga.get(
            "DATA_CONSEGNA",
            ""
        )
    )

    return riga


if not df.empty:

    df = df.apply(
        sincronizza_riga,
        axis=1
    )


# ============================================================
# CONFIGURAZIONE EDITOR
# ============================================================

column_config = {}


if lista_clienti:

    column_config[
        "RAGIONE_SOCIALE"
    ] = st.column_config.SelectboxColumn(

        "RAGIONE SOCIALE",

        options=
            lista_clienti,

        required=False
    )


if lista_codici_articoli:

    column_config[
        "COD_ARTICOLO"
    ] = st.column_config.SelectboxColumn(

        "COD_ARTICOLO",

        options=
            lista_codici_articoli,

        required=False
    )


if lista_descrizioni:

    column_config[
        "DESCRIZIONE"
    ] = st.column_config.SelectboxColumn(

        "DESCRIZIONE",

        options=
            lista_descrizioni,

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

    help=
        "Formato GG/MM/AAAA"
)


# ============================================================
# DATA EDITOR
# ============================================================

edited_df = st.data_editor(

    df,

    column_config=
        column_config,

    use_container_width=True,

    num_rows="dynamic",

    key=
        "editor_tabella"
)


# ============================================================
# DOPO MODIFICA
# ============================================================

if not edited_df.empty:

    edited_df = edited_df.apply(
        sincronizza_riga,
        axis=1
    )


edited_df = edited_df.fillna("")


st.session_state.dati = (
    edited_df.to_dict(
        orient="records"
    )
)


# ============================================================
# CSV
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

    label=
        "📥 Esporta CSV Tabella",

    data=
        csv_data,

    file_name=
        "gestione_ordini.csv",

    mime=
        "text/csv",

    type=
        "primary"
)


# ============================================================
# STATO SISTEMA
# ============================================================

with st.expander(
    "ℹ️ Stato sistema"
):

    col1, col2, col3 = st.columns(
        3
    )

    with col1:

        st.metric(
            "Clienti caricati",
            len(
                anagrafica_clienti
            )
        )

    with col2:

        st.metric(
            "Articoli caricati",
            len(
                anagrafica_articoli
            )
        )

    with col3:

        st.metric(
            "Righe in tabella",
            len(
                edited_df
            )
        )

    if client:

        st.success(
            "✓ OpenAI API configurata"
        )

    else:

        st.error(
            "✗ OPENAI_API_KEY non configurata"
        )

    if not df_clienti.empty:

        st.caption(
            f"✓ clienti.xlsx: "
            f"{len(df_clienti)} righe"
        )

    else:

        st.warning(
            "⚠️ clienti.xlsx non trovato"
        )

    if not df_articoli.empty:

        st.caption(
            f"✓ articoli.xlsx: "
            f"{len(df_articoli)} righe"
        )

    else:

        st.warning(
            "⚠️ articoli.xlsx non trovato"
        )

    if FILE_LISTINO.exists():

        st.caption(
            f"✓ listino trovato: "
            f"{FILE_LISTINO.name}"
        )

    else:

        st.warning(
            "⚠️ listino.pdf non trovato"
        )