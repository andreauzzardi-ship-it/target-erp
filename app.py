import json
import re
import time
from difflib import SequenceMatcher
from pathlib import Path

import pandas as pd
import streamlit as st

from google import genai
from google.genai import types


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

MODELLO_GEMINI = "gemini-3.7-flash"


# ============================================================
# CLIENT GEMINI
# ============================================================

@st.cache_resource
def get_gemini_client():

    try:

        api_key = st.secrets.get("GEMINI_API_KEY")

        if not api_key:
            return None

        return genai.Client(
            api_key=api_key
        )

    except Exception:
        return None


client = get_gemini_client()


# ============================================================
# UTILITÀ
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
        "na"
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
        "È": "E",
        "É": "E",
        "Ì": "I",
        "Í": "I",
        "Ò": "O",
        "Ó": "O",
        "Ù": "U",
        "Ú": "U"
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

    return any(
        parola in testo
        for parola in [
            "429",
            "RESOURCE_EXHAUSTED",
            "RATE LIMIT",
            "QUOTA",
            "TOO MANY REQUESTS"
        ]
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
# TROVA COLONNA
# ============================================================

def trova_colonna(
    df,
    nomi
):

    if df.empty:
        return None

    nomi_normalizzati = {
        normalizza_chiave(nome)
        for nome in nomi
    }

    for colonna in df.columns:

        if normalizza_chiave(
            colonna
        ) in nomi_normalizzati:

            return colonna

    return None


# ============================================================
# COLONNE CLIENTI
# ============================================================

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


# ============================================================
# COLONNE ARTICOLI
# ============================================================

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

    # Match esatto
    if chiave in mappa_clienti:

        return mappa_clienti[
            chiave
        ]

    # Match codice cliente
    if chiave in mappa_codici_cliente:

        return mappa_codici_cliente[
            chiave
        ]

    # Match contenuto
    for cliente in anagrafica_clienti:

        nome = normalizza_chiave(
            cliente["ragione_sociale"]
        )

        if (
            chiave in nome
            or nome in chiave
        ):

            return cliente

    # Fuzzy
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
    # CODICE
    # ========================================================

    if codice:

        chiave = normalizza_chiave(
            codice
        )

        if chiave in mappa_articoli:

            return mappa_articoli[
                chiave
            ]

    # ========================================================
    # DESCRIZIONE ESATTA
    # ========================================================

    if descrizione:

        chiave_descrizione = (
            normalizza_chiave(
                descrizione
            )
        )

        for articolo in anagrafica_articoli:

            if (
                normalizza_chiave(
                    articolo["descrizione"]
                )
                == chiave_descrizione
            ):

                return articolo

        # ====================================================
        # FUZZY
        # ====================================================

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
# NORMALIZZA QUANTITÀ
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

def prompt_estrazione(
    tipo_documento
):

    return f"""
Sei il motore di estrazione documentale
di Target ERP.

TIPO DOCUMENTO:
{tipo_documento}

Devi analizzare il documento allegato.

ESTRAI TUTTE LE RIGHE ARTICOLO.

Per ogni riga restituisci:

COD_CLIENTE
RAGIONE_SOCIALE
COD_ARTICOLO
DESCRIZIONE
QUANTITA
DATA_CONSEGNA

REGOLE IMPORTANTI:

1. NON INVENTARE DATI.

2. Se un dato non è leggibile,
   restituisci una stringa vuota.

3. COPIA IL CODICE ARTICOLO ESATTAMENTE
   come appare nel documento.

4. Se nel documento è presente una descrizione,
   copiala.

5. Non creare codici che non esistono
   nel documento.

6. Ogni articolo deve essere una riga separata.

7. Non sommare articoli diversi.

8. Non eliminare righe.

9. La quantità deve essere quella indicata
   nel documento.

10. La data consegna deve essere quella
    indicata nel documento.

11. Non aggiungere spiegazioni.

12. Restituisci esclusivamente JSON.

JSON:

{{
    "righe": [
        {{
            "COD_CLIENTE": "",
            "RAGIONE_SOCIALE": "",
            "COD_ARTICOLO": "",
            "DESCRIZIONE": "",
            "QUANTITA": "",
            "DATA_CONSEGNA": ""
        }}
    ]
}}
"""


# ============================================================
# CHIAMATA GEMINI
# ============================================================

def chiama_gemini(
    contenuti,
    system_instruction=None
):

    if not client:

        raise RuntimeError(
            "GEMINI_API_KEY non configurata."
        )

    config = types.GenerateContentConfig(
        temperature=0,
        system_instruction=(
            system_instruction
            if system_instruction
            else None
        )
    )

    tentativi = 3

    ultimo_errore = None

    for tentativo in range(
        tentativi
    ):

        try:

            response = (
                client.models.generate_content(
                    model=MODELLO_GEMINI,
                    contents=contenuti,
                    config=config
                )
            )

            return response

        except Exception as e:

            ultimo_errore = e

            if errore_rate_limit(e):

                if tentativo < tentativi - 1:

                    time.sleep(
                        4 * (tentativo + 1)
                    )

                    continue

            raise

    raise ultimo_errore


# ============================================================
# ESTRAZIONE JSON
# ============================================================

def estrai_json(testo):

    testo = testo.strip()

    # Caso JSON diretto
    try:

        return json.loads(
            testo
        )

    except Exception:
        pass

    # Cerca blocco JSON
    match = re.search(
        r"\{.*\}",
        testo,
        re.DOTALL
    )

    if match:

        try:

            return json.loads(
                match.group()
            )

        except Exception:
            pass

    raise ValueError(
        "Gemini non ha restituito "
        "un JSON valido."
    )


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

    codice_cliente_raw = (
        normalizza_testo(
            record.get(
                "COD_CLIENTE",
                ""
            )
        )
    )

    codice_articolo_raw = (
        normalizza_testo(
            record.get(
                "COD_ARTICOLO",
                ""
            )
        )
    )

    descrizione_raw = (
        normalizza_testo(
            record.get(
                "DESCRIZIONE",
                ""
            )
        )
    )

    quantita_raw = (
        normalizza_testo(
            record.get(
                "QUANTITA",
                ""
            )
        )
    )

    data_raw = (
        normalizza_testo(
            record.get(
                "DATA_CONSEGNA",
                ""
            )
        )
    )

    # ========================================================
    # CLIENTE
    # ========================================================

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
        # IMPORTANTISSIMO
        #
        # La descrizione NON viene presa da Gemini.
        #
        # Se il codice esiste in articoli.xlsx,
        # la descrizione ufficiale arriva direttamente
        # dall'anagrafica.
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
            )
    }


# ============================================================
# ANALIZZA FILE
# ============================================================

def analizza_file(
    uploaded_file,
    tipo_documento
):

    file_bytes = (
        uploaded_file.getvalue()
    )

    if not file_bytes:

        raise ValueError(
            "Il file è vuoto."
        )

    # ========================================================
    # CREA FILE TEMPORANEO
    # ========================================================

    estensione = (
        Path(
            uploaded_file.name
        ).suffix
        or ".pdf"
    )

    temp_path = (
        BASE_DIR
        / f"_temp_upload{estensione}"
    )

    try:

        temp_path.write_bytes(
            file_bytes
        )

        # ====================================================
        # UPLOAD FILE GEMINI
        # ====================================================

        file_gemini = (
            client.files.upload(
                file=str(temp_path)
            )
        )

        # ====================================================
        # PROMPT
        # ====================================================

        prompt = (
            prompt_estrazione(
                tipo_documento
            )
        )

        response = chiama_gemini(
            [
                file_gemini,
                prompt
            ]
        )

        risultato = estrai_json(
            response.text
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

    finally:

        try:

            if temp_path.exists():
                temp_path.unlink()

        except Exception:
            pass


# ============================================================
# ANALIZZA EMAIL
# ============================================================

def analizza_email(
    testo_email,
    tipo_documento
):

    prompt = (
        prompt_estrazione(
            tipo_documento
        )
        + """

TESTO EMAIL:

"""
        + testo_email
    )

    response = chiama_gemini(
        prompt
    )

    risultato = estrai_json(
        response.text
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


def chiedi_a_victoria(
    domanda
):

    if not client:

        raise RuntimeError(
            "GEMINI_API_KEY non configurata."
        )

    pdf_bytes = (
        carica_listino()
    )

    if not pdf_bytes:

        raise RuntimeError(
            "listino.pdf non trovato."
        )

    temp_path = (
        BASE_DIR
        / "_temp_listino.pdf"
    )

    try:

        temp_path.write_bytes(
            pdf_bytes
        )

        file_gemini = (
            client.files.upload(
                file=str(temp_path)
            )
        )

        istruzioni = """
Sei Victoria, l'assistente virtuale
ufficiale del software Target ERP.

Devi rispondere esclusivamente utilizzando
il listino PDF allegato.

REGOLE:

- Non inventare prezzi.
- Non inventare codici.
- Non inventare caratteristiche.
- Se una informazione non è presente
  nel listino, dichiaralo chiaramente.
- Non utilizzare clienti.xlsx.
- Non utilizzare articoli.xlsx.
- Rispondi sempre in italiano.
- Rispondi in modo professionale e sintetico.
- Se ti chiedono chi ti ha creata o sviluppata,
  rispondi che sei stata creata da Andrea Uzzardi.
- Non parlare spontaneamente di dettagli tecnici.
"""

        response = chiama_gemini(
            [
                file_gemini,
                domanda
            ],
            system_instruction=istruzioni
        )

        return response.text.strip()

    finally:

        try:

            if temp_path.exists():
                temp_path.unlink()

        except Exception:
            pass


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
                        "Gemini ha temporaneamente "
                        "raggiunto il limite gratuito. "
                        "Attendi qualche secondo e riprova."
                    )

                else:

                    risposta = (
                        f"Errore: {e}"
                    )

            st.session_state.messages.append(
                {
                    "role": "assistant",
                    "content": risposta
                }
            )

            st.rerun()


# ============================================================
# STATO API
# ============================================================

if not client:

    st.warning(
        "⚠️ GEMINI_API_KEY non configurata. "
        "Inseriscila nei Secrets di Streamlit."
    )


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
                    "GEMINI_API_KEY non configurata."
                )

            else:

                with st.spinner(
                    "Victoria sta leggendo il documento..."
                ):

                    try:

                        nuove_righe = (
                            analizza_file(
                                uploaded_file,
                                tipo_documento
                            )
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
                                "Nessuna riga articolo trovata."
                            )

                    except Exception as e:

                        if errore_rate_limit(e):

                            st.error(
                                "Gemini ha raggiunto "
                                "temporaneamente il limite "
                                "del Free Tier. "
                                "Attendi qualche secondo "
                                "e riprova."
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
                "GEMINI_API_KEY non configurata."
            )

        else:

            with st.spinner(
                "Gemini sta analizzando l'email..."
            ):

                try:

                    nuove_righe = (
                        analizza_email(
                            testo_email,
                            tipo_documento
                        )
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
                            "Nessuna riga articolo trovata."
                        )

                except Exception as e:

                    if errore_rate_limit(e):

                        st.error(
                            "Gemini ha raggiunto "
                            "temporaneamente il limite "
                            "del Free Tier."
                        )

                    else:

                        st.error(
                            f"Errore durante l'analisi: {e}"
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


colonne = [
    "COD_CLIENTE",
    "RAGIONE_SOCIALE",
    "COD_ARTICOLO",
    "DESCRIZIONE",
    "QUANTITA",
    "DATA_CONSEGNA"
]


for colonna in colonne:

    if colonna not in df.columns:

        df[colonna] = ""


df = df[colonne]


# ============================================================
# SINCRONIZZAZIONE CLIENTE
# ============================================================

def sincronizza_cliente_riga(
    riga
):

    ragione = normalizza_testo(
        riga["RAGIONE_SOCIALE"]
    )

    codice = normalizza_testo(
        riga["COD_CLIENTE"]
    )

    cliente = trova_cliente(
        ragione
    )

    if (
        not cliente
        and codice
    ):

        cliente = (
            mappa_codici_cliente.get(
                normalizza_chiave(
                    codice
                )
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

def sincronizza_articolo_riga(
    riga
):

    codice = normalizza_testo(
        riga["COD_ARTICOLO"]
    )

    descrizione = normalizza_testo(
        riga["DESCRIZIONE"]
    )

    # ========================================================
    # CODICE → ANAGRAFICA
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
    # DESCRIZIONE → ANAGRAFICA
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
# SINCRONIZZAZIONE
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
# CONFIGURAZIONE COLONNE
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
# SINCRONIZZAZIONE POST MODIFICA
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
        .apply(
            normalizza_quantita
        )
    )

    edited_df["DATA_CONSEGNA"] = (
        edited_df["DATA_CONSEGNA"]
        .apply(
            normalizza_data
        )
    )


edited_df = edited_df.fillna("")


st.session_state.dati = (
    edited_df.to_dict(
        orient="records"
    )
)


# ============================================================
# EXPORT CSV
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
            "Gemini API configurata"
        )

    else:

        st.error(
            "GEMINI_API_KEY non configurata"
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
            f"✓ listino.pdf trovato"
        )

    else:

        st.warning(
            "listino.pdf non trovato"
        )
