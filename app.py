````python
import io
import json
import re
import time
import urllib.request
from pathlib import Path
from difflib import SequenceMatcher

import pandas as pd
import streamlit as st
from google import genai
from google.genai import types


# ==============================================================================
# CONFIGURAZIONE
# ==============================================================================

st.set_page_config(
    page_title="Target ERP - Smart Order & Quote Hub",
    layout="wide"
)


# ==============================================================================
# COSTANTI
# ==============================================================================

MODEL_PRIMARY = "gemini-3.5-flash"
MODEL_FALLBACK = "gemini-3.5-flash-lite"

BASE_DIR = Path(__file__).resolve().parent
LISTINI_DIR = BASE_DIR / "listini"

CLIENTI_FILE = BASE_DIR / "clienti.xlsx"
ARTICOLI_FILE = BASE_DIR / "articoli.xlsx"

# Puoi lasciare vuoto per usare automaticamente i PDF presenti in /listini.
#
# Se vuoi usare Google Drive, inserisci SOLO il link al SINGOLO FILE PDF.
#
# Esempio:
# https://drive.google.com/file/d/XXXXXXXXXXXX/view
#
URL_LISTINO_PDF = ""

COLONNE_TABELLA = [
    "COD_CLIENTE",
    "RAGIONE_SOCIALE",
    "COD_ARTICOLO",
    "DESCRIZIONE",
    "QUANTITA",
    "DATA_CONSEGNA",
]


# ==============================================================================
# CSS
# ==============================================================================

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
    unsafe_allow_html=True,
)


# ==============================================================================
# CLIENT GEMINI
# ==============================================================================

@st.cache_resource
def get_client():
    """
    Crea il client Gemini una sola volta.
    """
    try:
        api_key = st.secrets.get("GOOGLE_API_KEY")

        if not api_key:
            return None

        return genai.Client(api_key=api_key)

    except Exception:
        return None


client = get_client()


# ==============================================================================
# FUNZIONI UTILI
# ==============================================================================

def normalizza_testo(value):
    """
    Normalizzazione robusta per confrontare stringhe.
    """
    if value is None:
        return ""

    text = str(value).strip()

    if text.lower() in {"nan", "none", "nat", "n/a", "n.d.", "n/d"}:
        return ""

    text = re.sub(r"\s+", " ", text)

    return text


def normalizza_chiave(value):
    """
    Normalizzazione aggressiva utilizzata per il matching.
    """
    text = normalizza_testo(value).upper()

    # Rimuove accenti comuni
    replacements = {
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

    for old, new in replacements.items():
        text = text.replace(old, new)

    return re.sub(r"[^A-Z0-9]", "", text)


def similarita(a, b):
    """
    Similarità tra due stringhe.
    """
    a = normalizza_chiave(a)
    b = normalizza_chiave(b)

    if not a or not b:
        return 0.0

    if a == b:
        return 1.0

    return SequenceMatcher(None, a, b).ratio()


def is_rate_limit_error(error):
    text = str(error).upper()

    return (
        "429" in text
        or "RESOURCE_EXHAUSTED" in text
        or "RATE LIMIT" in text
        or "QUOTA" in text
    )


def is_not_found_error(error):
    text = str(error).upper()

    return (
        "404" in text
        or "NOT_FOUND" in text
        or "NOT FOUND" in text
    )


# ==============================================================================
# CARICAMENTO EXCEL
# ==============================================================================

@st.cache_data
def carica_excel(path_string):
    """
    Carica un Excel e normalizza i nomi delle colonne.
    """
    path = Path(path_string)

    if not path.exists():
        return pd.DataFrame()

    try:
        df = pd.read_excel(path)

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


df_clienti = carica_excel(str(CLIENTI_FILE))
df_articoli = carica_excel(str(ARTICOLI_FILE))


# ==============================================================================
# IDENTIFICAZIONE COLONNE CLIENTI
# ==============================================================================

def trova_colonna(df, candidati):
    if df.empty:
        return None

    candidati_norm = {
        normalizza_chiave(x)
        for x in candidati
    }

    for col in df.columns:
        if normalizza_chiave(col) in candidati_norm:
            return col

    return None


col_rag_trovata = trova_colonna(
    df_clienti,
    [
        "RAGIONE_SOCIALE",
        "RAGIONE SOCIALE",
        "RAGIONE SOCIALE CLIENTE",
        "CLIENTE",
        "NOME",
    ],
)

col_cod_cli_trovato = trova_colonna(
    df_clienti,
    [
        "COD_CLIENTE",
        "CODICE",
        "CODICE CLIENTE",
        "CODCLI",
    ],
)


# ==============================================================================
# IDENTIFICAZIONE COLONNE ARTICOLI
# ==============================================================================

col_art_trovata = trova_colonna(
    df_articoli,
    [
        "Codart",
        "CODART",
        "COD_ARTICOLO",
        "CODICE ARTICOLO",
        "CODICE",
    ],
)

col_desc_trovata = trova_colonna(
    df_articoli,
    [
        "Descrizione articolo",
        "DESCRIZIONE",
        "DESCRIZIONE ARTICOLO",
    ],
)


# ==============================================================================
# PREPARAZIONE ANAGRAFICHE
# ==============================================================================

def costruisci_anagrafica_clienti():
    risultati = []

    if df_clienti.empty or not col_rag_trovata:
        return risultati

    for _, row in df_clienti.iterrows():
        ragione = normalizza_testo(row.get(col_rag_trovata, ""))

        if not ragione:
            continue

        codice = ""

        if col_cod_cli_trovato:
            codice = normalizza_testo(
                row.get(col_cod_cli_trovato, "")
            )

        risultati.append(
            {
                "ragione_sociale": ragione,
                "codice_cliente": codice,
            }
        )

    return risultati


def costruisci_anagrafica_articoli():
    risultati = []

    if df_articoli.empty or not col_art_trovata:
        return risultati

    for _, row in df_articoli.iterrows():

        codice = normalizza_testo(
            row.get(col_art_trovata, "")
        )

        if not codice:
            continue

        descrizione = ""

        if col_desc_trovata:
            descrizione = normalizza_testo(
                row.get(col_desc_trovata, "")
            )

        risultati.append(
            {
                "codice": codice,
                "descrizione": descrizione,
            }
        )

    return risultati


anagrafica_clienti = costruisci_anagrafica_clienti()
anagrafica_articoli = costruisci_anagrafica_articoli()

lista_opzioni_clienti = sorted(
    list(
        {
            x["ragione_sociale"]
            for x in anagrafica_clienti
            if x["ragione_sociale"]
        }
    )
)

lista_opzioni_articoli = sorted(
    list(
        {
            x["codice"]
            for x in anagrafica_articoli
            if x["codice"]
        }
    )
)

lista_opzioni_descrizioni = sorted(
    list(
        {
            x["descrizione"]
            for x in anagrafica_articoli
            if x["descrizione"]
        }
    )
)


# ==============================================================================
# MAPPE RAPIDE
# ==============================================================================

mappa_clienti_per_nome = {}

for cliente in anagrafica_clienti:
    chiave = normalizza_chiave(cliente["ragione_sociale"])

    if chiave:
        mappa_clienti_per_nome[chiave] = cliente


mappa_clienti_per_codice = {}

for cliente in anagrafica_clienti:
    codice = normalizza_chiave(cliente["codice_cliente"])

    if codice:
        mappa_clienti_per_codice[codice] = cliente


mappa_articoli_per_codice = {}

for articolo in anagrafica_articoli:
    chiave = normalizza_chiave(articolo["codice"])

    if chiave:
        mappa_articoli_per_codice[chiave] = articolo


# ==============================================================================
# MATCHING CLIENTI
# ==============================================================================

def trova_cliente_valido(testo):
    """
    Restituisce SEMPRE un cliente presente nell'Excel.
    Se non trova una corrispondenza affidabile restituisce None.
    """

    testo = normalizza_testo(testo)

    if not testo:
        return None

    chiave = normalizza_chiave(testo)

    # Match esatto
    if chiave in mappa_clienti_per_nome:
        return mappa_clienti_per_nome[chiave]

    # Match per codice cliente
    if chiave in mappa_clienti_per_codice:
        return mappa_clienti_per_codice[chiave]

    # Match contenuto
    for cliente in anagrafica_clienti:

        nome = normalizza_chiave(
            cliente["ragione_sociale"]
        )

        if not nome:
            continue

        if (
            chiave in nome
            or nome in chiave
        ):
            return cliente

    # Fuzzy matching
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

    # Soglia abbastanza conservativa
    if migliore and miglior_score >= 0.88:
        return migliore

    return None


# ==============================================================================
# MATCHING ARTICOLI
# ==============================================================================

def trova_articolo_valido(codice="", descrizione=""):
    """
    Cerca l'articolo nell'anagrafica reale.

    Priorità:
    1. codice esatto
    2. descrizione esatta
    3. descrizione molto simile

    NON inventa mai un codice.
    """

    codice = normalizza_testo(codice)
    descrizione = normalizza_testo(descrizione)

    # ----------------------------------------------------------
    # 1. CODICE
    # ----------------------------------------------------------

    if codice:

        key = normalizza_chiave(codice)

        if key in mappa_articoli_per_codice:
            return mappa_articoli_per_codice[key]

    # ----------------------------------------------------------
    # 2. DESCRIZIONE ESATTA
    # ----------------------------------------------------------

    if descrizione:

        desc_key = normalizza_chiave(descrizione)

        candidati = [
            articolo
            for articolo in anagrafica_articoli
            if normalizza_chiave(
                articolo["descrizione"]
            ) == desc_key
        ]

        # Se una descrizione è duplicata non possiamo
        # inventare quale codice sia corretto.
        if len(candidati) == 1:
            return candidati[0]

    # ----------------------------------------------------------
    # 3. FUZZY MATCH
    # ----------------------------------------------------------

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

        if migliore and miglior_score >= 0.92:
            return migliore

    return None


# ==============================================================================
# LISTINI PDF
# ==============================================================================

def estrai_file_id_google_drive(url):
    """
    Estrae l'ID da un URL di un singolo file Google Drive.
    """

    patterns = [
        r"/file/d/([a-zA-Z0-9_-]+)",
        r"[?&]id=([a-zA-Z0-9_-]+)",
    ]

    for pattern in patterns:

        match = re.search(pattern, url)

        if match:
            return match.group(1)

    return None


def scarica_pdf_da_url(url):
    """
    Scarica un PDF da URL diretto o Google Drive.
    """

    if not url:
        return None, None

    # ----------------------------------------------------------
    # BLOCCA URL DI CARTELLE GOOGLE DRIVE
    # ----------------------------------------------------------

    if "drive.google.com/drive/folders/" in url:

        raise ValueError(
            "Hai configurato un link a una cartella Google Drive. "
            "Inserisci il link al singolo file PDF oppure metti il PDF "
            "nella cartella locale 'listini'."
        )

    download_url = url

    if "drive.google.com" in url:

        file_id = estrai_file_id_google_drive(url)

        if not file_id:
            raise ValueError(
                "Link Google Drive non valido. "
                "Usa il link del singolo file PDF."
            )

        download_url = (
            "https://drive.google.com/uc"
            f"?export=download&id={file_id}"
        )

    request = urllib.request.Request(
        download_url,
        headers={
            "User-Agent": "Mozilla/5.0"
        },
    )

    with urllib.request.urlopen(
        request,
        timeout=30,
    ) as response:

        data = response.read()

    if not data.startswith(b"%PDF"):
        raise ValueError(
            "Il contenuto scaricato non è un PDF valido."
        )

    return data, "application/pdf"


def trova_pdf_locale():
    """
    Cerca automaticamente il PDF nella cartella listini.
    """

    if not LISTINI_DIR.exists():
        return None

    pdfs = sorted(
        LISTINI_DIR.glob("*.pdf"),
        key=lambda x: x.stat().st_mtime,
        reverse=True,
    )

    if not pdfs:
        return None

    return pdfs[0]


@st.cache_resource
def carica_listino_gemini(url_configurato):
    """
    Carica il PDF una sola volta su Gemini.

    Priorità:
    1. URL configurato
    2. PDF locale in /listini
    """

    if client is None:
        return None, "Client Gemini non configurato."

    try:

        # ------------------------------------------------------
        # URL
        # ------------------------------------------------------

        if url_configurato.strip():

            pdf_bytes, mime_type = scarica_pdf_da_url(
                url_configurato.strip()
            )

            nome_file = "Listino_Ufficiale.pdf"

            file_obj = client.files.upload(
                file=io.BytesIO(pdf_bytes),
                config={
                    "display_name": nome_file,
                    "mime_type": mime_type,
                },
            )

            return file_obj, nome_file

        # ------------------------------------------------------
        # FILE LOCALE
        # ------------------------------------------------------

        pdf_path = trova_pdf_locale()

        if not pdf_path:

            return (
                None,
                "Nessun PDF trovato nella cartella 'listini'.",
            )

        file_obj = client.files.upload(
            file=str(pdf_path),
            config={
                "display_name": pdf_path.name,
                "mime_type": "application/pdf",
            },
        )

        return file_obj, pdf_path.name

    except Exception as e:

        return (
            None,
            f"Errore caricamento listino: {e}",
        )


# ==============================================================================
# CHIAMATA GEMINI
# ==============================================================================

def genera_contenuto_con_fallback(
    contents,
    json_mode=False,
):
    """
    Chiamata Gemini con fallback automatico.
    """

    if client is None:
        raise RuntimeError(
            "Client Gemini non configurato. "
            "Controlla GOOGLE_API_KEY nei Secrets di Streamlit."
        )

    config = {}

    if json_mode:
        config["response_mime_type"] = "application/json"

    try:

        return client.models.generate_content(
            model=MODEL_PRIMARY,
            contents=contents,
            config=config,
        )

    except Exception as first_error:

        if not is_rate_limit_error(first_error):
            raise

        time.sleep(1)

        return client.models.generate_content(
            model=MODEL_FALLBACK,
            contents=contents,
            config=config,
        )


# ==============================================================================
# JSON SICURO
# ==============================================================================

def estrai_json_da_risposta(text):
    """
    Gestisce eventuali ```json ... ``` restituiti dal modello.
    """

    if not text:
        raise ValueError(
            "Gemini ha restituito una risposta vuota."
        )

    text = text.strip()

    # JSON normale
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Markdown code fence
    match = re.search(
        r"```(?:json)?\s*(.*?)\s*```",
        text,
        flags=re.DOTALL | re.IGNORECASE,
    )

    if match:

        try:
            return json.loads(
                match.group(1)
            )
        except json.JSONDecodeError:
            pass

    raise ValueError(
        "La risposta dell'AI non contiene un JSON valido."
    )


# ==============================================================================
# NORMALIZZAZIONE RECORD ESTRATTI
# ==============================================================================

def normalizza_quantita(value):
    """
    Converte la quantità in intero positivo.
    """

    if value is None:
        return ""

    text = normalizza_testo(value)

    if not text:
        return ""

    match = re.search(
        r"\d+",
        text.replace(",", "."),
    )

    if not match:
        return ""

    try:
        numero = int(match.group())

        if numero < 0:
            return ""

        return numero

    except Exception:
        return ""


def normalizza_data(value):
    """
    Normalizza la data in YYYY-MM-DD quando possibile.
    """

    if value is None:
        return ""

    text = normalizza_testo(value)

    if not text:
        return ""

    if text.upper() in {
        "N/D",
        "ND",
        "NON DISPONIBILE",
    }:
        return ""

    # Già ISO
    match = re.fullmatch(
        r"(\d{4})-(\d{2})-(\d{2})",
        text,
    )

    if match:
        return text

    # DD/MM/YYYY o DD-MM-YYYY
    match = re.fullmatch(
        r"(\d{1,2})[\/\-.](\d{1,2})[\/\-.](\d{4})",
        text,
    )

    if match:

        giorno = int(match.group(1))
        mese = int(match.group(2))
        anno = int(match.group(3))

        try:
            return (
                f"{anno:04d}-"
                f"{mese:02d}-"
                f"{giorno:02d}"
            )
        except Exception:
            return ""

    # Ultimo tentativo Pandas
    try:

        data = pd.to_datetime(
            text,
            dayfirst=True,
            errors="coerce",
        )

        if pd.isna(data):
            return ""

        return data.strftime("%Y-%m-%d")

    except Exception:
        return ""


def normalizza_record_ai(record):
    """
    Trasforma il risultato Gemini in un record sicuro.
    """

    if not isinstance(record, dict):
        return None

    cliente_raw = record.get(
        "RAGIONE_SOCIALE",
        "",
    )

    codice_cliente_raw = record.get(
        "COD_CLIENTE",
        "",
    )

    codice_articolo_raw = record.get(
        "COD_ARTICOLO",
        "",
    )

    descrizione_raw = record.get(
        "DESCRIZIONE",
        "",
    )

    quantita_raw = record.get(
        "QUANTITA",
        "",
    )

    data_raw = record.get(
        "DATA_CONSEGNA",
        "",
    )

    # ----------------------------------------------------------
    # CLIENTE
    # ----------------------------------------------------------

    cliente = trova_cliente_valido(
        cliente_raw
    )

    if cliente:

        ragione_sociale = cliente[
            "ragione_sociale"
        ]

        cod_cliente = cliente[
            "codice_cliente"
        ]

    else:

        # Se Gemini ha trovato un codice cliente
        # proviamo a usarlo solo se esiste realmente.
        cliente_da_codice = None

        if codice_cliente_raw:

            cliente_da_codice = (
                mappa_clienti_per_codice.get(
                    normalizza_chiave(
                        codice_cliente_raw
                    )
                )
            )

        if cliente_da_codice:

            ragione_sociale = (
                cliente_da_codice[
                    "ragione_sociale"
                ]
            )

            cod_cliente = (
                cliente_da_codice[
                    "codice_cliente"
                ]
            )

        else:

            ragione_sociale = ""
            cod_cliente = ""

    # ----------------------------------------------------------
    # ARTICOLO
    # ----------------------------------------------------------

    articolo = trova_articolo_valido(
        codice=codice_articolo_raw,
        descrizione=descrizione_raw,
    )

    if articolo:

        cod_articolo = articolo["codice"]

        descrizione = articolo[
            "descrizione"
        ]

    else:

        cod_articolo = ""
        descrizione = (
            normalizza_testo(
                descrizione_raw
            )
        )

    # ----------------------------------------------------------
    # QUANTITÀ
    # ----------------------------------------------------------

    quantita = normalizza_quantita(
        quantita_raw
    )

    # ----------------------------------------------------------
    # DATA
    # ----------------------------------------------------------

    data_consegna = normalizza_data(
        data_raw
    )

    return {
        "COD_CLIENTE": cod_cliente,
        "RAGIONE_SOCIALE": ragione_sociale,
        "COD_ARTICOLO": cod_articolo,
        "DESCRIZIONE": descrizione,
        "QUANTITA": quantita,
        "DATA_CONSEGNA": data_consegna,
    }


# ==============================================================================
# PROMPT ESTRAZIONE
# ==============================================================================

def crea_prompt_estrazione(doc_type):
    """
    Prompt che NON chiede a Gemini di inventare codici.
    """

    return f"""
Sei un motore di estrazione dati per Target ERP.

Il documento è di tipo:
{doc_type}

Devi analizzare il documento e restituire le righe articolo.

IMPORTANTE:
- Non inventare dati.
- Non inventare codici cliente.
- Non inventare codici articolo.
- Se un dato non è chiaramente leggibile restituisci "".
- Il codice articolo deve essere quello eventualmente stampato
  nel documento, se presente.
- La validazione definitiva dei codici viene effettuata
  successivamente dal software.

Per ogni riga estrai:

- RAGIONE_SOCIALE
- COD_CLIENTE
- COD_ARTICOLO
- DESCRIZIONE
- QUANTITA
- DATA_CONSEGNA

Regole:

1. RAGIONE_SOCIALE:
   estrai il nome del cliente così come appare nel documento.

2. COD_CLIENTE:
   estrailo solo se realmente presente nel documento.
   Non dedurlo.

3. COD_ARTICOLO:
   estrailo solo se realmente presente nel documento.
   Non inventarlo.

4. DESCRIZIONE:
   estrai la descrizione del prodotto.

5. QUANTITA:
   restituisci un numero intero.

6. DATA_CONSEGNA:
   restituisci la data così come appare.
   Se non presente restituisci "".

7. Se trovi più articoli restituisci un elemento
   per ogni riga articolo.

8. Se non trovi articoli restituisci una lista vuota.

Restituisci ESCLUSIVAMENTE un JSON nel seguente formato:

[
  {{
    "COD_CLIENTE": "",
    "RAGIONE_SOCIALE": "",
    "COD_ARTICOLO": "",
    "DESCRIZIONE": "",
    "QUANTITA": "",
    "DATA_CONSEGNA": ""
  }}
]
"""


# ==============================================================================
# ESTRAZIONE DA FILE
# ==============================================================================

def analizza_file(uploaded_file, doc_type):

    if client is None:
        raise RuntimeError(
            "API Gemini non configurata."
        )

    file_bytes = uploaded_file.getvalue()

    if not file_bytes:
        raise ValueError(
            "Il file caricato è vuoto."
        )

    mime_type = uploaded_file.type

    if not mime_type:
        mime_type = "application/octet-stream"

    prompt = crea_prompt_estrazione(
        doc_type
    )

    response = genera_contenuto_con_fallback(
        [
            types.Part.from_bytes(
                data=file_bytes,
                mime_type=mime_type,
            ),
            prompt,
        ],
        json_mode=True,
    )

    dati = estrai_json_da_risposta(
        response.text
    )

    if not isinstance(dati, list):
        raise ValueError(
            "Il modello non ha restituito una lista JSON."
        )

    risultati = []

    for record in dati:

        normalizzato = normalizza_record_ai(
            record
        )

        if normalizzato:
            risultati.append(
                normalizzato
            )

    return risultati


# ==============================================================================
# ESTRAZIONE DA TESTO
# ==============================================================================

def analizza_testo(email_text, doc_type):

    if client is None:
        raise RuntimeError(
            "API Gemini non configurata."
        )

    testo = normalizza_testo(
        email_text
    )

    if not testo:
        raise ValueError(
            "Il testo è vuoto."
        )

    prompt = (
        crea_prompt_estrazione(doc_type)
        + "\n\n"
        + "TESTO DEL DOCUMENTO:\n"
        + testo
    )

    response = genera_contenuto_con_fallback(
        prompt,
        json_mode=True,
    )

    dati = estrai_json_da_risposta(
        response.text
    )

    if not isinstance(dati, list):
        raise ValueError(
            "Il modello non ha restituito una lista JSON."
        )

    risultati = []

    for record in dati:

        normalizzato = normalizza_record_ai(
            record
        )

        if normalizzato:
            risultati.append(
                normalizzato
            )

    return risultati


# ==============================================================================
# STATO SESSIONE
# ==============================================================================

if "dati" not in st.session_state:
    st.session_state.dati = []

if "victoria_messages" not in st.session_state:
    st.session_state.victoria_messages = []

if "victoria_history" not in st.session_state:
    st.session_state.victoria_history = []


# ==============================================================================
# TITOLO
# ==============================================================================

col_titolo, col_chat = st.columns(
    [3, 1]
)

with col_titolo:

    st.title(
        "📦 Target ERP — Smart Order & Quote Hub"
    )

    if df_clienti.empty:
        st.warning(
            "⚠️ clienti.xlsx non trovato o non leggibile."
        )

    if df_articoli.empty:
        st.warning(
            "⚠️ articoli.xlsx non trovato o non leggibile."
        )


# ==============================================================================
# VICTORIA
# ==============================================================================

with col_chat:

    with st.popover(
        "💬 Chat con Victoria",
        use_container_width=True,
    ):

        st.subheader(
            "🤖 Victoria — Target ERP"
        )

        st.caption(
            "Assistente del listino prezzi."
        )

        # ------------------------------------------------------
        # CARICAMENTO LISTINO
        # ------------------------------------------------------

        pdf_listino_file, listino_status = (
            carica_listino_gemini(
                URL_LISTINO_PDF
            )
        )

        if pdf_listino_file:

            st.caption(
                f"📕 Listino attivo: {listino_status}"
            )

        else:

            st.warning(
                f"⚠️ {listino_status}"
            )

        # ------------------------------------------------------
        # CRONOLOGIA
        # ------------------------------------------------------

        chat_container = st.container(
            height=350
        )

        with chat_container:

            for msg in st.session_state.victoria_messages:

                with st.chat_message(
                    msg["role"]
                ):

                    st.markdown(
                        msg["content"]
                    )

        # ------------------------------------------------------
        # INPUT
        # ------------------------------------------------------

        prompt = st.chat_input(
            "Chiedi informazioni sul listino..."
        )

        if prompt:

            prompt = prompt.strip()

            st.session_state.victoria_messages.append(
                {
                    "role": "user",
                    "content": prompt,
                }
            )

            system_instruction = """
Sei Victoria, l'assistente virtuale ufficiale
del software Target ERP.

Il tuo compito è rispondere alle domande
relative esclusivamente al listino PDF fornito.

REGOLE IMPORTANTI:

1. Usa il PDF come fonte principale.
2. Non inventare prezzi, codici, caratteristiche
   o disponibilità.
3. Se un'informazione non è presente nel PDF,
   dichiara chiaramente che non è disponibile
   nel listino.
4. Non utilizzare file Excel o anagrafiche clienti.
5. Rispondi in italiano.
6. Sii professionale, sintetica e precisa.
7. Se l'utente chiede chi ti ha creata,
   rispondi:
   "Sono stata creata da Andrea Uzzardi."
8. Non parlare spontaneamente dell'implementazione
   tecnica, del modello AI o delle API.
"""

            try:

                if client is None:
                    raise RuntimeError(
                        "API Gemini non configurata."
                    )

                if pdf_listino_file is None:

                    raise RuntimeError(
                        "Il listino PDF non è disponibile."
                    )

                # --------------------------------------------------
                # COSTRUZIONE DELLA CRONOLOGIA
                # --------------------------------------------------

                contents = []

                # Il PDF viene fornito come fonte documentale.
                contents.append(
                    pdf_listino_file
                )

                # Conversazione precedente
                for message in st.session_state.victoria_history:

                    role = message["role"]
                    text = message["content"]

                    contents.append(
                        types.Content(
                            role=role,
                            parts=[
                                types.Part.from_text(
                                    text=text
                                )
                            ],
                        )
                    )

                # Nuova domanda
                contents.append(
                    types.Content(
                        role="user",
                        parts=[
                            types.Part.from_text(
                                text=prompt
                            )
                        ],
                    )
                )

                response = genera_contenuto_con_fallback(
                    contents,
                    json_mode=False,
                )

                risposta = (
                    response.text.strip()
                    if response.text
                    else "Non ho trovato una risposta nel listino."
                )

                # --------------------------------------------------
                # SALVA CRONOLOGIA
                # --------------------------------------------------

                st.session_state.victoria_history.append(
                    {
                        "role": "user",
                        "content": prompt,
                    }
                )

                st.session_state.victoria_history.append(
                    {
                        "role": "model",
                        "content": risposta,
                    }
                )

            except Exception as e:

                if is_rate_limit_error(e):

                    risposta = (
                        "Il servizio è momentaneamente "
                        "sovraccarico. Riprova tra qualche secondo."
                    )

                else:

                    risposta = (
                        "Non riesco a consultare il listino "
                        "in questo momento."
                    )

                # Non salviamo gli errori come parte della
                # memoria conversazionale.

            st.session_state.victoria_messages.append(
                {
                    "role": "assistant",
                    "content": risposta,
                }
            )

            st.rerun()


# ==============================================================================
# TIPO DOCUMENTO
# ==============================================================================

st.write(
    "Seleziona il tipo di documento:"
)

doc_type = st.radio(
    "Seleziona il tipo di documento:",
    [
        "🛒 Ordine Cliente",
        "📋 Offerta",
    ],
    horizontal=True,
    label_visibility="collapsed",
)


# ==============================================================================
# INPUT
# ==============================================================================

tab_upload, tab_text = st.tabs(
    [
        "📄 Carica PDF / Immagine",
        "✉️ Incolla Testo Email",
    ]
)


# ==============================================================================
# UPLOAD FILE
# ==============================================================================

with tab_upload:

    uploaded_file = st.file_uploader(
        "Trascina file (PDF o Immagine)",
        type=[
            "pdf",
            "jpg",
            "png",
            "jpeg",
        ],
        label_visibility="collapsed",
    )

    if uploaded_file:

        if st.button(
            "⚡ Analizza File ed Inserisci in Tabella",
            type="primary",
            key="btn_analizza_file",
        ):

            with st.spinner(
                "Lettura ed estrazione dati..."
            ):

                try:

                    nuovi_dati = analizza_file(
                        uploaded_file,
                        doc_type,
                    )

                    if not nuovi_dati:

                        st.warning(
                            "Non sono state trovate righe articolo."
                        )

                    else:

                        st.session_state.dati.extend(
                            nuovi_dati
                        )

                        st.success(
                            f"{len(nuovi_dati)} righe estratte "
                            "e aggiunte alla tabella."
                        )

                        st.rerun()

                except Exception as e:

                    st.error(
                        f"Errore durante l'analisi: {e}"
                    )


# ==============================================================================
# INPUT TESTO
# ==============================================================================

with tab_text:

    email_text = st.text_area(
        "Incolla qui il testo dell'email o del documento...",
        height=160,
        key="email_text_input",
    )

    if st.button(
        "⚡ Analizza Email ed Inserisci in Tabella",
        type="primary",
        key="btn_analizza_email",
    ):

        if not email_text.strip():

            st.warning(
                "Incolla il testo prima di procedere."
            )

        else:

            with st.spinner(
                "Estrazione dati dall'email..."
            ):

                try:

                    nuovi_dati = analizza_testo(
                        email_text,
                        doc_type,
                    )

                    if not nuovi_dati:

                        st.warning(
                            "Non sono state trovate righe articolo."
                        )

                    else:

                        st.session_state.dati.extend(
                            nuovi_dati
                        )

                        st.success(
                            f"{len(nuovi_dati)} righe estratte "
                            "e aggiunte alla tabella."
                        )

                        st.rerun()

                except Exception as e:

                    st.error(
                        f"Errore durante l'estrazione: {e}"
                    )


# ==============================================================================
# TABELLA
# ==============================================================================

st.divider()

st.subheader(
    "Gestione Ordini e Articoli"
)


# ==============================================================================
# DATAFRAME
# ==============================================================================

if st.session_state.dati:

    df = pd.DataFrame(
        st.session_state.dati
    )

else:

    df = pd.DataFrame(
        columns=COLONNE_TABELLA
    )


# Assicura tutte le colonne
for col in COLONNE_TABELLA:

    if col not in df.columns:

        df[col] = ""


# Ordine colonne
df = df[
    COLONNE_TABELLA
]


# ==============================================================================
# PULIZIA E SINCRONIZZAZIONE INIZIALE
# ==============================================================================

def sincronizza_dataframe(df):
    """
    Sincronizzazione deterministica.

    Non usa cicli codice -> descrizione -> codice.
    Il codice articolo è la chiave primaria.
    """

    result = df.copy()

    # ----------------------------------------------------------
    # CLIENTI
    # ----------------------------------------------------------

    if anagrafica_clienti:

        def aggiorna_cliente(row):

            cliente = trova_cliente_valido(
                row.get(
                    "RAGIONE_SOCIALE",
                    "",
                )
            )

            if cliente:

                row["RAGIONE_SOCIALE"] = (
                    cliente["ragione_sociale"]
                )

                row["COD_CLIENTE"] = (
                    cliente["codice_cliente"]
                )

            return row

        result = result.apply(
            aggiorna_cliente,
            axis=1,
        )

    # ----------------------------------------------------------
    # ARTICOLI
    # ----------------------------------------------------------

    if anagrafica_articoli:

        def aggiorna_articolo(row):

            articolo = trova_articolo_valido(
                codice=row.get(
                    "COD_ARTICOLO",
                    "",
                ),
                descrizione=row.get(
                    "DESCRIZIONE",
                    "",
                ),
            )

            if articolo:

                row["COD_ARTICOLO"] = (
                    articolo["codice"]
                )

                if articolo["descrizione"]:

                    row["DESCRIZIONE"] = (
                        articolo["descrizione"]
                    )

            return row

        result = result.apply(
            aggiorna_articolo,
            axis=1,
        )

    return result


df = sincronizza_dataframe(
    df
)


# ==============================================================================
# EDITOR
# ==============================================================================

column_config = {}


if lista_opzioni_clienti:

    column_config[
        "RAGIONE_SOCIALE"
    ] = st.column_config.SelectboxColumn(
        "RAGIONE SOCIALE",
        options=lista_opzioni_clienti,
        required=False,
    )


if lista_opzioni_articoli:

    column_config[
        "COD_ARTICOLO"
    ] = st.column_config.SelectboxColumn(
        "COD_ARTICOLO",
        options=lista_opzioni_articoli,
        required=False,
    )


if lista_opzioni_descrizioni:

    column_config[
        "DESCRIZIONE"
    ] = st.column_config.SelectboxColumn(
        "DESCRIZIONE",
        options=lista_opzioni_descrizioni,
        required=False,
    )


column_config[
    "COD_CLIENTE"
] = st.column_config.TextColumn(
    "COD_CLIENTE",
    disabled=True,
)


column_config[
    "QUANTITA"
] = st.column_config.NumberColumn(
    "QUANTITA",
    min_value=0,
    step=1,
    format="%d",
)


column_config[
    "DATA_CONSEGNA"
] = st.column_config.TextColumn(
    "DATA CONSEGNA",
    help="Formato consigliato: YYYY-MM-DD",
)


edited_df = st.data_editor(
    df,
    column_config=column_config,
    use_container_width=True,
    num_rows="dynamic",
    key="editor_tabella",
)


# ==============================================================================
# NORMALIZZAZIONE POST-EDITOR
# ==============================================================================

edited_df = edited_df.copy()


# --------------------------------------------------------------
# CLIENTE
# --------------------------------------------------------------

def aggiorna_riga_cliente(row):

    cliente = trova_cliente_valido(
        row.get(
            "RAGIONE_SOCIALE",
            "",
        )
    )

    if cliente:

        row["RAGIONE_SOCIALE"] = (
            cliente["ragione_sociale"]
        )

        row["COD_CLIENTE"] = (
            cliente["codice_cliente"]
        )

    else:

        # Se il cliente non esiste nell'anagrafica,
        # non permettiamo un codice inventato.
        row["COD_CLIENTE"] = ""

    return row


if not edited_df.empty:

    edited_df = edited_df.apply(
        aggiorna_riga_cliente,
        axis=1,
    )


# --------------------------------------------------------------
# ARTICOLO
# --------------------------------------------------------------

def aggiorna_riga_articolo(row):

    codice = normalizza_testo(
        row.get(
            "COD_ARTICOLO",
            "",
        )
    )

    descrizione = normalizza_testo(
        row.get(
            "DESCRIZIONE",
            "",
        )
    )

    # Se è stato scelto un codice valido,
    # il codice ha priorità.
    if codice:

        articolo = trova_articolo_valido(
            codice=codice
        )

        if articolo:

            row["COD_ARTICOLO"] = (
                articolo["codice"]
            )

            if articolo["descrizione"]:

                row["DESCRIZIONE"] = (
                    articolo["descrizione"]
                )

            return row

    # Se non c'è codice, proviamo dalla descrizione.
    if descrizione:

        articolo = trova_articolo_valido(
            descrizione=descrizione
        )

        if articolo:

            row["COD_ARTICOLO"] = (
                articolo["codice"]
            )

            if articolo["descrizione"]:

                row["DESCRIZIONE"] = (
                    articolo["descrizione"]
                )

    return row


if not edited_df.empty:

    edited_df = edited_df.apply(
        aggiorna_riga_articolo,
        axis=1,
    )


# --------------------------------------------------------------
# QUANTITÀ
# --------------------------------------------------------------

if "QUANTITA" in edited_df.columns:

    edited_df["QUANTITA"] = (
        edited_df["QUANTITA"]
        .apply(normalizza_quantita)
    )


# --------------------------------------------------------------
# DATA
# --------------------------------------------------------------

if "DATA_CONSEGNA" in edited_df.columns:

    edited_df["DATA_CONSEGNA"] = (
        edited_df["DATA_CONSEGNA"]
        .apply(normalizza_data)
    )


# --------------------------------------------------------------
# ORDINE COLONNE
# --------------------------------------------------------------

edited_df = edited_df[
    COLONNE_TABELLA
]


# ==============================================================================
# SALVATAGGIO SESSION STATE
# ==============================================================================

st.session_state.dati = (
    edited_df
    .fillna("")
    .to_dict(
        orient="records"
    )
)


# ==============================================================================
# ESPORTAZIONE CSV
# ==============================================================================

st.divider()

csv_data = (
    edited_df
    .to_csv(
        index=False,
        encoding="utf-8-sig",
    )
    .encode("utf-8-sig")
)


st.download_button(
    label="📥 Esporta CSV Tabella",
    data=csv_data,
    file_name="gestione_ordini.csv",
    mime="text/csv",
    type="primary",
)


# ==============================================================================
# INFO TECNICHE
# ==============================================================================

with st.expander(
    "ℹ️ Stato sistema"
):

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric(
            "Clienti caricati",
            len(anagrafica_clienti),
        )

    with col2:
        st.metric(
            "Articoli caricati",
            len(anagrafica_articoli),
        )

    with col3:
        st.metric(
            "Righe in tabella",
            len(edited_df),
        )

    if not df_clienti.empty:

        st.caption(
            f"✓ clienti.xlsx: {len(df_clienti)} righe"
        )

    else:

        st.caption(
            "✗ clienti.xlsx non disponibile"
        )

    if not df_articoli.empty:

        st.caption(
            f"✓ articoli.xlsx: {len(df_articoli)} righe"
        )

    else:

        st.caption(
            "✗ articoli.xlsx non disponibile"
        )

    if LISTINI_DIR.exists():

        pdf_count = len(
            list(
                LISTINI_DIR.glob("*.pdf")
            )
        )

        st.caption(
            f"✓ PDF nella cartella listini: {pdf_count}"
        )

    else:

        st.caption(
            "✗ Cartella listini non trovata"
        )
````
