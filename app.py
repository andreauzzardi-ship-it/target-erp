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
# PERCORSI FILE
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

FILE_CLIENTI = BASE_DIR / "clienti.xlsx"
FILE_ARTICOLI = BASE_DIR / "articoli.xlsx"
FILE_LISTINO = BASE_DIR / "listino.pdf"


# ============================================================
# MODELLO OPENAI
# ============================================================

MODELLO_OPENAI = "gpt-5.6-luna"


# ============================================================
# CLIENT OPENAI
# ============================================================

@st.cache_resource
def get_client():
    """
    Inizializza il client OpenAI usando Streamlit Secrets.
    """

    try:
        api_key = st.secrets.get("OPENAI_API_KEY")

        if api_key is None:
            return None

        api_key = str(api_key).strip()

        if not api_key:
            return None

        return OpenAI(api_key=api_key)

    except Exception:
        return None


client = get_client()


# ============================================================
# UTILITÀ TESTO
# ============================================================

def normalizza_testo(valore):
    """
    Converte qualsiasi valore in testo pulito.
    """

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
        "n.a",
    }:
        return ""

    testo = re.sub(r"\s+", " ", testo)

    return testo.strip()


def normalizza_chiave(valore):
    """
    Normalizzazione aggressiva per confrontare
    codici, clienti e descrizioni.
    """

    testo = normalizza_testo(valore).upper()

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
        testo = testo.replace(vecchio, nuovo)

    return re.sub(r"[^A-Z0-9]", "", testo)


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
# ERRORI OPENAI
# ============================================================

def descrivi_errore_openai(error):
    """
    Restituisce un messaggio diagnostico.
    Non trasforma automaticamente ogni errore in un falso
    'rate limit'.
    """

    testo = str(error)

    status = getattr(error, "status_code", None)

    request_id = getattr(
        error,
        "request_id",
        None
    )

    if status is None:

        match = re.search(
            r"Error code:\s*(\d+)",
            testo
        )

        if match:
            status = match.group(1)

    if status == 401:
        messaggio = (
            "Errore 401: API key non valida, "
            "scaduta o non autorizzata."
        )

    elif status == 403:
        messaggio = (
            "Errore 403: richiesta non autorizzata. "
            "Controlla progetto, permessi o billing OpenAI."
        )

    elif status == 400:
        messaggio = (
            "Errore 400: richiesta non valida. "
            "Il problema potrebbe riguardare il file "
            "o il formato della richiesta."
        )

    elif status == 404:
        messaggio = (
            "Errore 404: modello o risorsa non trovata."
        )

    elif status == 429:
        messaggio = (
            "Errore 429: limite di richieste o quota "
            "temporaneamente raggiunta."
        )

    elif status == 500:
        messaggio = (
            "Errore 500: errore temporaneo del server OpenAI."
        )

    elif status == 502:
        messaggio = (
            "Errore 502: servizio OpenAI temporaneamente "
            "non disponibile."
        )

    elif status == 503:
        messaggio = (
            "Errore 503: servizio OpenAI temporaneamente "
            "sovraccarico."
        )

    else:
        messaggio = (
            "Errore durante la comunicazione con OpenAI."
        )

    dettagli = f"\n\nDettagli tecnici: {testo}"

    if request_id:
        dettagli += (
            f"\nRequest ID: {request_id}"
        )

    return messaggio + dettagli


def è_rate_limit(error):

    status = getattr(
        error,
        "status_code",
        None
    )

    if status == 429:
        return True

    testo = str(error).upper()

    return (
        "429" in testo
        or "RATE LIMIT" in testo
        or "TOO MANY REQUESTS" in testo
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
# RICERCA COLONNE EXCEL
# ============================================================

def trova_colonna(df, nomi):

    if df.empty:
        return None

    nomi_normalizzati = {
        normalizza_chiave(nome)
        for nome in nomi
    }

    for colonna in df.columns:

        if (
            normalizza_chiave(colonna)
            in nomi_normalizzati
        ):
            return colonna

    return None


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

def costruisci_anagrafica_clienti():

    risultati = []

    if df_clienti.empty:
        return risultati

    if not colonna_ragione_sociale:
        return risultati

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

        risultati.append(
            {
                "ragione_sociale": ragione,
                "codice_cliente": codice,
            }
        )

    return risultati


# ============================================================
# ANAGRAFICA ARTICOLI
# ============================================================

def costruisci_anagrafica_articoli():

    risultati = []

    if df_articoli.empty:
        return risultati

    if not colonna_codice_articolo:
        return risultati

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

        risultati.append(
            {
                "codice": codice,
                "descrizione": descrizione,
            }
        )

    return risultati


anagrafica_clienti = (
    costruisci_anagrafica_clienti()
)

anagrafica_articoli = (
    costruisci_anagrafica_articoli()
)


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

    testo = normalizza_testo(testo)

    if not testo:
        return None

    chiave = normalizza_chiave(testo)

    if chiave in mappa_clienti:
        return mappa_clienti[chiave]

    if chiave in mappa_codici_cliente:
        return mappa_codici_cliente[chiave]

    for cliente in anagrafica_clienti:

        nome = normalizza_chiave(
            cliente["ragione_sociale"]
        )

        if (
            chiave in nome
            or nome in chiave
        ):
            return cliente

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

    codice = normalizza_testo(codice)
    descrizione = normalizza_testo(descrizione)

    # --------------------------------------------------------
    # CODICE ESATTO
    # --------------------------------------------------------

    if codice:

        chiave = normalizza_chiave(
            codice
        )

        articolo = mappa_articoli.get(
            chiave
        )

        if articolo:
            return articolo

    # --------------------------------------------------------
    # DESCRIZIONE ESATTA
    # --------------------------------------------------------

    if descrizione:

        chiave = normalizza_chiave(
            descrizione
        )

        candidati = []

        for articolo in anagrafica_articoli:

            if (
                normalizza_chiave(
                    articolo["descrizione"]
                )
                == chiave
            ):
                candidati.append(
                    articolo
                )

        if len(candidati) == 1:
            return candidati[0]

    # --------------------------------------------------------
    # FUZZY DESCRIPTION
    # --------------------------------------------------------

    if descrizione:

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

        if (
            migliore
            and miglior_score >= 0.92
        ):
            return migliore

    return None


# ============================================================
# QUANTITÀ
# ============================================================

def normalizza_quantita(valore):

    testo = normalizza_testo(valore)

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
# PROMPT ESTRAZIONE
# ============================================================

def prompt_estrazione(tipo_documento):

    return f"""
Sei il motore di estrazione documentale di Target ERP.

TIPO DOCUMENTO:
{tipo_documento}

Devi analizzare il documento allegato ed estrarre
tutte le righe articolo presenti.

Per ogni riga estrai:

COD_CLIENTE
RAGIONE_SOCIALE
COD_ARTICOLO
DESCRIZIONE
QUANTITA
DATA_CONSEGNA

REGOLE IMPORTANTI:

1. NON INVENTARE DATI.

2. Se un dato non è presente o non è leggibile,
   restituisci una stringa vuota.

3. COD_ARTICOLO deve essere copiato dal documento
   esattamente come appare.

4. DESCRIZIONE deve essere copiata dal documento
   se presente.

5. Ogni riga articolo deve essere separata.

6. Se ci sono 10 articoli devi restituire 10 righe.

7. Non sommare articoli diversi.

8. Non modificare i codici.

9. Non cercare di costruire o correggere
   autonomamente i codici.

10. Non aggiungere spiegazioni.

11. Restituisci esclusivamente il JSON richiesto.
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
# CHIAMATA RESPONSES API
# ============================================================

def chiama_openai(
    input_data,
    istruzioni=None,
    json_mode=False
):

    if not client:

        raise RuntimeError(
            "OPENAI_API_KEY non configurata."
        )

    parametri = {
        "model": MODELLO_OPENAI,
        "input": input_data,
    }

    if istruzioni:
        parametri["instructions"] = istruzioni

    if json_mode:

        parametri["text"] = {
            "format": {
                "type": "json_schema",
                "name": "target_erp_extraction",
                "strict": True,
                "schema": SCHEMA_ESTRAZIONE,
            }
        }

    ultimo_errore = None

    # Massimo 3 tentativi solo per 429 / 5xx
    for tentativo in range(3):

        try:

            return client.responses.create(
                **parametri
            )

        except Exception as error:

            ultimo_errore = error

            status = getattr(
                error,
                "status_code",
                None
            )

            # Retry solo su errori temporanei
            if status in {
                429,
                500,
                502,
                503,
                504
            }:

                if tentativo < 2:

                    time.sleep(
                        2 ** tentativo
                    )

                    continue

            raise

    raise ultimo_errore


# ============================================================
# UPLOAD FILE OPENAI
# ============================================================

def carica_file_openai(
    uploaded_file
):

    if not client:

        raise RuntimeError(
            "OPENAI_API_KEY non configurata."
        )

    file_bytes = uploaded_file.getvalue()

    if not file_bytes:

        raise ValueError(
            "Il file caricato è vuoto."
        )

    try:

        file_obj = client.files.create(

            file=(
                uploaded_file.name,
                file_bytes
            ),

            purpose="user_data"
        )

        return file_obj

    except Exception as error:

        raise RuntimeError(
            "Errore durante il caricamento "
            "del file su OpenAI.\n\n"
            + descrivi_errore_openai(error)
        )


# ============================================================
# ANALISI PDF
# ============================================================

def analizza_pdf(
    uploaded_file,
    tipo_documento
):

    file_obj = carica_file_openai(
        uploaded_file
    )

    try:

        response = chiama_openai(

            input_data=[

                {
                    "role": "user",

                    "content": [

                        {
                            "type": "input_file",
                            "file_id": file_obj.id,
                        },

                        {
                            "type": "input_text",

                            "text":
                                prompt_estrazione(
                                    tipo_documento
                                ),
                        },

                    ],
                }

            ],

            json_mode=True
        )

    except Exception as error:

        raise RuntimeError(
            descrivi_errore_openai(error)
        )

    testo = response.output_text

    if not testo:

        raise RuntimeError(
            "OpenAI ha restituito una risposta vuota."
        )

    try:

        risultato = json.loads(
            testo
        )

    except Exception as error:

        raise RuntimeError(
            "OpenAI non ha restituito "
            "un JSON valido.\n\n"
            f"Risposta ricevuta:\n{testo}\n\n"
            f"Errore JSON: {error}"
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
# ANALISI EMAIL
# ============================================================

def analizza_email(
    testo_email,
    tipo_documento
):

    testo_email = normalizza_testo(
        testo_email
    )

    if not testo_email:

        return []

    input_data = [

        {
            "role": "user",

            "content": [

                {
                    "type": "input_text",

                    "text":
                        prompt_estrazione(
                            tipo_documento
                        )
                        + "\n\n"
                        + "TESTO EMAIL:\n"
                        + testo_email,
                }

            ],
        }

    ]

    try:

        response = chiama_openai(
            input_data=input_data,
            json_mode=True
        )

    except Exception as error:

        raise RuntimeError(
            descrivi_errore_openai(error)
        )

    try:

        risultato = json.loads(
            response.output_text
        )

    except Exception as error:

        raise RuntimeError(
            "JSON restituito da OpenAI non valido.\n\n"
            f"{error}"
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
# NORMALIZZAZIONE RECORD
# ============================================================

def normalizza_record(record):

    if not isinstance(record, dict):
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

        codice_cliente = (
            cliente["codice_cliente"]
        )

        ragione_sociale = (
            cliente["ragione_sociale"]
        )

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

        codice=codice_articolo_raw,

        descrizione=descrizione_raw
    )

    if articolo:

        # ====================================================
        # IMPORTANTE:
        #
        # Se il codice esiste in articoli.xlsx,
        # la descrizione viene SEMPRE presa da Excel.
        #
        # OpenAI non può sovrascriverla.
        # ====================================================

        codice_articolo = (
            articolo["codice"]
        )

        descrizione = (
            articolo["descrizione"]
        )

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
            ),
    }


# ============================================================
# LISTINO
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

    if not client:

        raise RuntimeError(
            "OPENAI_API_KEY non configurata."
        )

    pdf_bytes = carica_listino()

    if not pdf_bytes:

        raise RuntimeError(
            "listino.pdf non trovato "
            "nella root del repository."
        )

    try:

        file_obj = client.files.create(

            file=(
                "listino.pdf",
                pdf_bytes
            ),

            purpose="user_data"
        )

    except Exception as error:

        raise RuntimeError(
            descrivi_errore_openai(error)
        )

    istruzioni = """
Sei Victoria, l'assistente virtuale ufficiale
del software Target ERP.

Devi rispondere utilizzando esclusivamente
il listino PDF allegato.

REGOLE:

- Non inventare prezzi.
- Non inventare codici.
- Non inventare caratteristiche.
- Non usare clienti.xlsx.
- Non usare articoli.xlsx.
- Se una informazione non è presente nel listino,
  dichiaralo chiaramente.
- Rispondi sempre in italiano.
- Rispondi in modo professionale e sintetico.
- Se ti chiedono chi ti ha creata o sviluppata,
  rispondi che sei stata creata da Andrea Uzzardi.
"""

    try:

        response = chiama_openai(

            input_data=[

                {
                    "role": "user",

                    "content": [

                        {
                            "type": "input_file",
                            "file_id": file_obj.id,
                        },

                        {
                            "type": "input_text",
                            "text": domanda,
                        },

                    ],
                }

            ],

            istruzioni=istruzioni,

            json_mode=False
        )

    except Exception as error:

        raise RuntimeError(
            descrivi_errore_openai(error)
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

            for messaggio in (
                st.session_state.messages
            ):

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
                    "content": domanda,
                }
            )

            try:

                with st.spinner(
                    "Victoria sta consultando il listino..."
                ):

                    risposta = chiedi_a_victoria(
                        domanda
                    )

            except Exception as error:

                risposta = (
                    f"❌ {error}"
                )

            st.session_state.messages.append(
                {
                    "role": "assistant",
                    "content": risposta,
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
        "📋 Offerta",
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
        "✉️ Incolla Testo Email",
    ]
)


# ============================================================
# UPLOAD
# ============================================================

with tab_upload:

    uploaded_file = st.file_uploader(

        "Trascina qui il PDF o l'immagine",

        type=[
            "pdf",
            "jpg",
            "jpeg",
            "png",
            "webp",
        ],

        label_visibility="collapsed"
    )

    if uploaded_file:

        st.caption(
            f"File selezionato: "
            f"**{uploaded_file.name}** "
            f"({uploaded_file.size / 1024:.1f} KB)"
        )

        if st.button(
            "⚡ Analizza File ed Inserisci in Tabella",
            type="primary"
        ):

            if not client:

                st.error(
                    "❌ OPENAI_API_KEY non configurata."
                )

                st.info(
                    "Controlla Streamlit → "
                    "Settings → Secrets."
                )

            else:

                with st.spinner(
                    "OpenAI sta leggendo il documento..."
                ):

                    try:

                        nuove_righe = analizza_pdf(

                            uploaded_file,

                            tipo_documento
                        )

                        if nuove_righe:

                            st.session_state.dati.extend(
                                nuove_righe
                            )

                            st.success(
                                f"✓ {len(nuove_righe)} "
                                "righe estratte."
                            )

                            st.rerun()

                        else:

                            st.warning(
                                "Nessuna riga articolo "
                                "trovata nel documento."
                            )

                    except Exception as error:

                        st.error(
                            f"❌ {error}"
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
                "❌ OPENAI_API_KEY non configurata."
            )

        else:

            with st.spinner(
                "OpenAI sta analizzando l'email..."
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
                            "righe estratte."
                        )

                        st.rerun()

                    else:

                        st.warning(
                            "Nessuna riga articolo trovata."
                        )

                except Exception as error:

                    st.error(
                        f"❌ {error}"
                    )


# ============================================================
# TABELLA
# ============================================================

st.divider()

st.subheader(
    "Gestione Ordini e Articoli"
)


colonne = [
    "COD_CLIENTE",
    "RAGIONE_SOCIALE",
    "COD_ARTICOLO",
    "DESCRIZIONE",
    "QUANTITA",
    "DATA_CONSEGNA",
]


if st.session_state.dati:

    df = pd.DataFrame(
        st.session_state.dati
    )

else:

    df = pd.DataFrame(
        columns=colonne
    )


for colonna in colonne:

    if colonna not in df.columns:

        df[colonna] = ""


df = df[colonne]


# ============================================================
# SINCRONIZZAZIONE CLIENTE
# ============================================================

def sincronizza_cliente_riga(riga):

    ragione = normalizza_testo(
        riga.get(
            "RAGIONE_SOCIALE",
            ""
        )
    )

    codice = normalizza_testo(
        riga.get(
            "COD_CLIENTE",
            ""
        )
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
# SINCRONIZZAZIONE ARTICOLO
# ============================================================

def sincronizza_articolo_riga(riga):

    codice = normalizza_testo(
        riga.get(
            "COD_ARTICOLO",
            ""
        )
    )

    descrizione = normalizza_testo(
        riga.get(
            "DESCRIZIONE",
            ""
        )
    )

    # ========================================================
    # PRIORITÀ ASSOLUTA AL CODICE
    # ========================================================

    if codice:

        articolo = trova_articolo(
            codice=codice
        )

        if articolo:

            riga["COD_ARTICOLO"] = (
                articolo["codice"]
            )

            riga["DESCRIZIONE"] = (
                articolo["descrizione"]
            )

            return riga

    # ========================================================
    # SE NON ABBIAMO CODICE, CERCHIAMO PER DESCRIZIONE
    # ========================================================

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


# ============================================================
# SINCRONIZZAZIONE INIZIALE
# ============================================================

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
# CONFIGURAZIONE DATA EDITOR
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

    help="Formato GG/MM/AAAA"
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
# SINCRONIZZAZIONE POST-MODIFICA
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
        edited_df[
            "QUANTITA"
        ].apply(
            normalizza_quantita
        )
    )

    edited_df["DATA_CONSEGNA"] = (
        edited_df[
            "DATA_CONSEGNA"
        ].apply(
            normalizza_data
        )
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

    st.write("---")

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
            "⚠ clienti.xlsx non trovato"
        )

    if not df_articoli.empty:

        st.caption(
            f"✓ articoli.xlsx: "
            f"{len(df_articoli)} righe"
        )

    else:

        st.warning(
            "⚠ articoli.xlsx non trovato"
        )

    if FILE_LISTINO.exists():

        st.caption(
            f"✓ Listino trovato: "
            f"{FILE_LISTINO.name}"
        )

    else:

        st.warning(
            "⚠ listino.pdf non trovato"
        )

    st.caption(
        f"Modello OpenAI: {MODELLO_OPENAI}"
    )