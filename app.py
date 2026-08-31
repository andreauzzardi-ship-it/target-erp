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
FILE_LISTINO = BASE_DIR / "listino.pdf"

# Modello OpenAI
MODELLO_OPENAI = "gpt-5.6-luna"


# ============================================================
# CLIENT OPENAI
# ============================================================

@st.cache_resource
def get_client():

    try:

        if "OPENAI_API_KEY" not in st.secrets:
            return None, "Secret OPENAI_API_KEY non trovato."

        api_key = str(
            st.secrets["OPENAI_API_KEY"]
        ).strip()

        if not api_key:
            return None, "OPENAI_API_KEY presente ma vuota."

        return OpenAI(
            api_key=api_key
        ), None

    except Exception as e:

        return None, (
            f"{type(e).__name__}: {e}"
        )


client, client_error = get_client()


# ============================================================
# FUNZIONI DI UTILITÀ
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


def errore_rate_limit(error):

    testo = str(error).upper()

    return (
        "429" in testo
        or "RATE LIMIT" in testo
        or "TOO MANY REQUESTS" in testo
        or "QUOTA" in testo
    )


def errore_server(error):

    testo = str(error).upper()

    return (
        "500" in testo
        or "502" in testo
        or "503" in testo
        or "504" in testo
        or "SERVER_ERROR" in testo
        or "SERVICE UNAVAILABLE" in testo
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


colonna_codice_articolo = trova_colonna(
    df_articoli,
    [
        "CODART",
        "COD_ARTICOLO",
        "CODICE ARTICOLO",
        "CODICE"
    ]
)


colonna_descrizione_articolo = trova_colonna(
    df_articoli,
    [
        "DESCRIZIONE ARTICOLO",
        "DESCRIZIONE"
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
                "codice_cliente": codice
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
                "descrizione": descrizione
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
# TROVA CLIENTE
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
# TROVA ARTIGO
# ============================================================

def encontra_artigo_por_codigo(codigo):

    codigo = normalizza_testo(
        codigo
    )

    if not codigo:
        return None

    chiave = normalizza_chiave(
        codigo
    )

    # Match esatto
    if chiave in mappa_articoli:
        return mappa_articoli[chiave]

    # Match OCR molto comune:
    # spazi, trattini, punti ecc.
    for articolo in anagrafica_articoli:

        codice_db = articolo["codice"]

        if (
            normalizza_chiave(
                codice_db
            )
            == chiave
        ):
            return articolo

    # Fuzzy solo se il codice è abbastanza simile.
    migliore = None
    miglior_score = 0

    for articolo in anagrafica_articoli:

        score = similarita(
            codigo,
            articolo["codice"]
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

    # PRIORITÀ ASSOLUTA AL CODICE
    if codice:

        articolo = (
            encontra_artigo_por_codigo(
                codice
            )
        )

        if artigo_valido(articolo):
            return articolo

    # Solo se il codice non è stato trovato,
    # proviamo la descrizione.
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


def artigo_valido(articolo):

    return (
        isinstance(articolo, dict)
        and bool(
            normalizza_testo(
                articolo.get(
                    "codice",
                    ""
                )
            )
        )
    )


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
# PROMPT ESTRAZIONE
# ============================================================

def prompt_estrazione(tipo_documento):

    return f"""
Sei il motore di estrazione documentale di Target ERP.

TIPO DOCUMENTO:
{tipo_documento}

Devi leggere il documento allegato ed estrarre
tutte le righe articolo.

Per ogni riga estrai:

COD_CLIENTE
RAGIONE_SOCIALE
COD_ARTICOLO
DESCRIZIONE
QUANTITA
DATA_CONSEGNA

REGOLE IMPORTANTI:

1. NON INVENTARE DATI.

2. Se un dato non è presente, restituisci "".

3. COD_ARTICOLO:
   COPIA ESATTAMENTE il codice che compare nel documento.

4. NON correggere o reinterpretare il codice articolo.

5. Se il codice contiene lettere, numeri,
   trattini, slash, punti o altri caratteri,
   mantienili.

6. DESCRIZIONE:
   riporta la descrizione visibile nel documento
   se presente.

7. Ogni articolo deve essere una riga separata.

8. Non sommare articoli diversi.

9. Non creare articoli che non compaiono
   nel documento.

10. Se ci sono più pagine, analizzale tutte.

11. COD_CLIENTE e RAGIONE_SOCIALE devono essere
    estratti dall'intestazione del documento
    quando presenti.

12. QUANTITA deve contenere solamente il valore
    numerico quando possibile.

13. DATA_CONSEGNA deve contenere la data richiesta
    dal cliente quando presente.

Restituisci esclusivamente il JSON richiesto.
"""


# ============================================================
# SCHEMA JSON
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

        parametri[
            "instructions"
        ] = istruzioni

    if usa_json:

        parametri["text"] = {

            "format": {

                "type": "json_schema",

                "name":
                    "target_erp_extraction",

                "strict": True,

                "schema":
                    SCHEMA_ESTRAZIONE
            }
        }

    tentativi = 3

    ultimo_errore = None

    for tentativo in range(
        tentativi
    ):

        try:

            return client.responses.create(
                **parametri
            )

        except Exception as e:

            ultimo_errore = e

            if (
                errore_rate_limit(e)
                or errore_server(e)
            ):

                if tentativo < tentativi - 1:

                    time.sleep(
                        2 * (tentativo + 1)
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
            "OpenAI non configurata."
        )

    file_bytes = (
        uploaded_file.getvalue()
    )

    if not file_bytes:

        raise ValueError(
            "Il file è vuoto."
        )

    nome = uploaded_file.name

    # Upload tramite Files API.
    # Questo è più robusto del passaggio
    # del PDF direttamente come base64.
    file_obj = client.files.create(

        file=(
            nome,
            io.BytesIO(file_bytes)
        ),

        purpose="user_data"
    )

    return file_obj


# ============================================================
# ANALISI PDF / IMMAGINE
# ============================================================

def analizza_file(
    uploaded_file,
    tipo_documento
):

    mime = (
        uploaded_file.type
        or ""
    )

    # --------------------------------------------------------
    # PDF
    # --------------------------------------------------------

    if mime == "application/pdf":

        file_obj = carica_file_openai(
            uploaded_file
        )

        input_data = [

            {

                "role": "user",

                "content": [

                    {

                        "type": "input_file",

                        "file_id":
                            file_obj.id
                    },

                    {

                        "type": "input_text",

                        "text":
                            prompt_estrazione(
                                tipo_documento
                            )
                    }
                ]
            }
        ]

    # --------------------------------------------------------
    # IMMAGINI
    # --------------------------------------------------------

    elif mime.startswith(
        "image/"
    ):

        import base64

        encoded = base64.b64encode(
            uploaded_file.getvalue()
        ).decode("utf-8")

        input_data = [

            {

                "role": "user",

                "content": [

                    {

                        "type": "input_image",

                        "image_url":
                            f"data:{mime};base64,{encoded}",

                        "detail": "high"
                    },

                    {

                        "type": "input_text",

                        "text":
                            prompt_estrazione(
                                tipo_documento
                            )
                    }
                ]
            }
        ]

    else:

        raise ValueError(
            "Formato file non supportato."
        )

    response = chiama_openai(

        input_data=input_data,

        usa_json=True
    )

    texto = response.output_text

    try:

        resultado = json.loads(
            texto
        )

    except Exception as e:

        raise ValueError(
            "OpenAI non ha restituito "
            f"un JSON valido: {e}"
        )

    righe = []

    for record in resultado.get(
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
# NORMALIZZA RECORD
# ============================================================

def normalizza_record(record):

    if not isinstance(
        record,
        dict
    ):
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

    if (
        not cliente
        and codice_cliente_raw
    ):

        cliente = (
            mappa_codici_cliente.get(
                normalizza_chiave(
                    codice_cliente_raw
                )
            )
        )

    if cliente:

        codice_cliente = (
            cliente[
                "codice_cliente"
            ]
        )

        ragione_sociale = (
            cliente[
                "ragione_sociale"
            ]
        )

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

        # IMPORTANTISSIMO:
        #
        # La descrizione ufficiale
        # NON viene presa da ChatGPT.
        #
        # Viene presa da articoli.xlsx.

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
            )
    }


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
    ]

    response = chiama_openai(

        input_data=input_data,

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
            righe.append(
                riga
            )

    return righe


# ============================================================
# VICTORIA - LISTINO
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
            "OpenAI non configurata."
        )

    pdf_bytes = carica_listino()

    if not pdf_bytes:

        raise RuntimeError(
            "Il file listino.pdf non è presente."
        )

    # Upload del listino una sola volta
    # per questa esecuzione.
    file_obj = client.files.create(

        file=(
            "listino.pdf",
            io.BytesIO(pdf_bytes)
        ),

        purpose="user_data"
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
- Se una informazione non è presente nel listino,
  dichiaralo chiaramente.
- Non utilizzare clienti.xlsx.
- Non utilizzare articoli.xlsx.
- Rispondi sempre in italiano.
- Rispondi in modo professionale e sintetico.
- Se ti chiedono chi ti ha creata o sviluppata,
  rispondi che sei stata creata da Andrea Uzzardi.
- Non parlare spontaneamente di API,
  programmazione o dettagli tecnici.
"""

    input_data = [

        {

            "role": "user",

            "content": [

                {

                    "type": "input_file",

                    "file_id":
                        file_obj.id
                },

                {

                    "type": "input_text",

                    "text": domanda
                }
            ]
        }
    ]

    response = chiama_openai(

        input_data=input_data,

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
                    "content": domanda
                }
            )

            try:

                with st.spinner(
                    "Victoria sta consultando il listino..."
                ):

                    risposta = (
                        chiedi_a_victoria(
                            domanda
                        )
                    )

            except Exception as e:

                if errore_rate_limit(e):

                    risposta = (
                        "Il servizio è momentaneamente "
                        "sovraccarico. Riprova tra poco."
                    )

                elif errore_server(e):

                    risposta = (
                        "OpenAI ha restituito un errore "
                        "temporaneo del server. "
                        "Riprova tra qualche secondo."
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
                    f"OpenAI non configurata. "
                    f"{client_error or ''}"
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

                        if errore_server(e):

                            st.error(
                                "OpenAI ha restituito un "
                                "errore temporaneo del server. "
                                "Riprova tra qualche secondo."
                            )

                        elif errore_rate_limit(e):

                            st.error(
                                "Limite temporaneo OpenAI "
                                "raggiunto. Riprova tra poco."
                            )

                        else:

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
                f"OpenAI non configurata. "
                f"{client_error or ''}"
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


colonne = [
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

        cliente = (
            mappa_codici_cliente.get(
                normalizza_chiave(
                    codice
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

    # --------------------------------------------------------
    # PRIORITÀ 1:
    # CODICE → DESCRIZIONE
    # --------------------------------------------------------

    if codice:

        articolo = (
            encontra_artigo_por_codigo(
                codice
            )
        )

        if artigo_valido(articolo):

            riga["COD_ARTICOLO"] = (
                articolo["codice"]
            )

            riga["DESCRIZIONE"] = (
                articolo["descrizione"]
            )

            return riga

    # --------------------------------------------------------
    # PRIORITÀ 2:
    # DESCRIZIONE → CODICE
    # --------------------------------------------------------

    if descrizione:

        articolo = trova_articolo(
            descrizione=descrizione
        )

        if artigo_valido(articolo):

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

    edited_df[
        "QUANTITA"
    ] = edited_df[
        "QUANTITA"
    ].apply(
        normalizza_quantita
    )

    edited_df[
        "DATA_CONSEGNA"
    ] = edited_df[
        "DATA_CONSEGNA"
    ].apply(
        normalizza_data
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

    # --------------------------------------------------------
    # OPENAI
    # --------------------------------------------------------

    if client:

        st.success(
            "🟢 OpenAI API configurata"
        )

    else:

        st.error(
            "🔴 OpenAI API non configurata"
        )

        if client_error:

            st.caption(
                f"Dettaglio: {client_error}"
            )

    # --------------------------------------------------------
    # CLIENTI
    # --------------------------------------------------------

    if not df_clienti.empty:

        st.caption(
            f"✓ clienti.xlsx: "
            f"{len(df_clienti)} righe"
        )

    else:

        st.warning(
            "clienti.xlsx non trovato"
        )

    # --------------------------------------------------------
    # ARTICOLI
    # --------------------------------------------------------

    if not df_articoli.empty:

        st.caption(
            f"✓ articoli.xlsx: "
            f"{len(df_articoli)} righe"
        )

    else:

        st.warning(
            "articoli.xlsx non trovato"
        )

    # --------------------------------------------------------
    # LISTINO
    # --------------------------------------------------------

    if FILE_LISTINO.exists():

        st.caption(
            f"✓ Listino trovato: "
            f"{FILE_LISTINO.name}"
        )

    else:

        st.warning(
            "listino.pdf non trovato"
        )