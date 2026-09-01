import json
import re
from difflib import SequenceMatcher
from pathlib import Path

import pandas as pd
import streamlit as st

try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None
    types = None


# ============================================================
# CONFIGURAZIONE
# ============================================================

st.set_page_config(
    page_title="Target ERP - Lettore Ordini",
    layout="wide"
)

BASE_DIR = Path(__file__).resolve().parent

FILE_CLIENTI = BASE_DIR / "clienti.xlsx"
FILE_ARTICOLI = BASE_DIR / "articoli.xlsx"

MODELLO_GEMINI = "gemini-2.5-flash"


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
    [data-testid="stStatusWidget"] {
        display: none !important;
    }

    .match-ok {
        padding: 8px;
        border-radius: 6px;
        background-color: #dff6e4;
    }

    .match-warning {
        padding: 8px;
        border-radius: 6px;
        background-color: #fff3cd;
    }

    .match-error {
        padding: 8px;
        border-radius: 6px;
        background-color: #f8d7da;
    }
    </style>
    """,
    unsafe_allow_html=True
)


# ============================================================
# CLIENT GEMINI
# ============================================================

@st.cache_resource
def get_gemini_client():
    if genai is None:
        return None

    api_key = st.secrets.get("GEMINI_API_KEY", "")

    if not api_key:
        return None

    try:
        return genai.Client(api_key=api_key)
    except Exception:
        return None


client = get_gemini_client()


# ============================================================
# FUNZIONI GENERALI
# ============================================================

def pulisci_testo(value):
    if value is None:
        return ""

    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass

    return re.sub(r"\s+", " ", str(value).strip())


def normalizza_chiave(value):
    value = pulisci_testo(value).upper()

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
        value = value.replace(vecchio, nuovo)

    return re.sub(r"[^A-Z0-9]", "", value)


def similarita(a, b):
    a = normalizza_chiave(a)
    b = normalizza_chiave(b)

    if not a or not b:
        return 0.0

    if a == b:
        return 1.0

    return SequenceMatcher(None, a, b).ratio()


# ============================================================
# CARICAMENTO EXCEL
# ============================================================

@st.cache_data
def carica_excel(percorso):
    percorso = Path(percorso)

    if not percorso.exists():
        return pd.DataFrame()

    try:
        df = pd.read_excel(percorso)

        if df.empty:
            return pd.DataFrame()

        df.columns = [
            str(colonna).strip()
            for colonna in df.columns
        ]

        return df

    except Exception:
        return pd.DataFrame()


df_clienti = carica_excel(FILE_CLIENTI)
df_articoli = carica_excel(FILE_ARTICOLI)


# ============================================================
# RICERCA COLONNE EXCEL
# ============================================================

def trova_colonna(df, possibili):
    if df.empty:
        return None

    possibili_normalizzati = {
        normalizza_chiave(x)
        for x in possibili
    }

    for colonna in df.columns:
        if normalizza_chiave(colonna) in possibili_normalizzati:
            return colonna

    return None


COL_RAGIONE_SOCIALE = trova_colonna(
    df_clienti,
    [
        "RAGIONE_SOCIALE",
        "RAGIONE SOCIALE",
        "RAGIONE SOCIALE CLIENTE",
        "CLIENTE",
        "NOME",
    ],
)

COL_CODICE_CLIENTE = trova_colonna(
    df_clienti,
    [
        "COD_CLIENTE",
        "CODICE CLIENTE",
        "CODICE",
        "CODCLI",
    ],
)

COL_CODICE_ARTICOLO = trova_colonna(
    df_articoli,
    [
        "CODART",
        "COD_ARTICOLO",
        "CODICE ARTICOLO",
        "CODICE",
    ],
)

COL_DESCRIZIONE_ARTICOLO = trova_colonna(
    df_articoli,
    [
        "DESCRIZIONE ARTICOLO",
        "DESCRIZIONE",
    ],
)


# ============================================================
# CREAZIONE ANAGRAFICHE
# ============================================================

def crea_clienti():
    clienti = []

    if df_clienti.empty:
        return clienti

    if not COL_RAGIONE_SOCIALE:
        return clienti

    for _, riga in df_clienti.iterrows():

        ragione = pulisci_testo(
            riga.get(COL_RAGIONE_SOCIALE, "")
        )

        if not ragione:
            continue

        codice = ""

        if COL_CODICE_CLIENTE:
            codice = pulisci_testo(
                riga.get(COL_CODICE_CLIENTE, "")
            )

        clienti.append(
            {
                "codice": codice,
                "ragione": ragione,
            }
        )

    return clienti


def crea_articoli():
    articoli = []

    if df_articoli.empty:
        return articoli

    if not COL_CODICE_ARTICOLO:
        return articoli

    for _, riga in df_articoli.iterrows():

        codice = pulisci_testo(
            riga.get(COL_CODICE_ARTICOLO, "")
        )

        if not codice:
            continue

        descrizione = ""

        if COL_DESCRIZIONE_ARTICOLO:
            descrizione = pulisci_testo(
                riga.get(COL_DESCRIZIONE_ARTICOLO, "")
            )

        articoli.append(
            {
                "codice": codice,
                "descrizione": descrizione,
            }
        )

    return articoli


CLIENTI = crea_clienti()
ARTICOLI = crea_articoli()


# ============================================================
# MAPPE VELOCI
# ============================================================

MAPPA_CLIENTI = {}

for cliente in CLIENTI:

    chiave = normalizza_chiave(
        cliente["ragione"]
    )

    if chiave:
        MAPPA_CLIENTI[chiave] = cliente


MAPPA_CODICI_CLIENTE = {}

for cliente in CLIENTI:

    chiave = normalizza_chiave(
        cliente["codice"]
    )

    if chiave:
        MAPPA_CODICI_CLIENTE[chiave] = cliente


MAPPA_ARTICOLI = {}

for articolo in ARTICOLI:

    chiave = normalizza_chiave(
        articolo["codice"]
    )

    if chiave:
        MAPPA_ARTICOLI[chiave] = articolo


# ============================================================
# RICERCA CLIENTE
# ============================================================

def cerca_cliente(valore):
    valore = pulisci_testo(valore)

    if not valore:
        return None, []


    chiave = normalizza_chiave(valore)


    # MATCH ESATTO
    if chiave in MAPPA_CLIENTI:

        cliente = MAPPA_CLIENTI[chiave]

        return cliente, [
            (cliente, 1.0)
        ]


    # MATCH CODICE CLIENTE
    if chiave in MAPPA_CODICI_CLIENTE:

        cliente = MAPPA_CODICI_CLIENTE[chiave]

        return cliente, [
            (cliente, 1.0)
        ]


    # MATCH CONTENUTO
    candidati = []

    for cliente in CLIENTI:

        nome = normalizza_chiave(
            cliente["ragione"]
        )

        if (
            chiave in nome
            or nome in chiave
        ):
            candidati.append(
                (
                    cliente,
                    0.95
                )
            )


    if candidati:

        candidati.sort(
            key=lambda x: x[1],
            reverse=True
        )

        return candidati[0][0], candidati[:5]


    # FUZZY MATCH
    for cliente in CLIENTI:

        score = similarita(
            valore,
            cliente["ragione"]
        )

        if score >= 0.55:

            candidati.append(
                (
                    cliente,
                    score
                )
            )


    candidati.sort(
        key=lambda x: x[1],
        reverse=True
    )


    if candidati and candidati[0][1] >= 0.88:

        return candidati[0][0], candidati[:5]


    return None, candidati[:5]


# ============================================================
# RICERCA ARTICOLO
# ============================================================

def cerca_articolo(
    codice="",
    descrizione=""
):

    codice = pulisci_testo(codice)
    descrizione = pulisci_testo(descrizione)


    # ========================================================
    # 1. CODICE ESATTO
    # ========================================================

    if codice:

        chiave = normalizza_chiave(codice)

        if chiave in MAPPA_ARTICOLI:

            articolo = MAPPA_ARTICOLI[chiave]

            return articolo, [
                (articolo, 1.0)
            ]


    # ========================================================
    # 2. DESCRIZIONE
    # ========================================================

    candidati = []

    if descrizione:

        for articolo in ARTICOLI:

            descrizione_excel = articolo["descrizione"]

            if not descrizione_excel:
                continue

            score = similarita(
                descrizione,
                descrizione_excel
            )

            if score >= 0.55:

                candidati.append(
                    (
                        articolo,
                        score
                    )
                )


    candidati.sort(
        key=lambda x: x[1],
        reverse=True
    )


    # Match molto sicuro
    if candidati and candidati[0][1] >= 0.92:

        return (
            candidati[0][0],
            candidati[:5]
        )


    return None, candidati[:5]


# ============================================================
# NORMALIZZA QUANTITÀ
# ============================================================

def normalizza_quantita(value):

    value = pulisci_testo(value)

    if not value:
        return ""

    match = re.search(
        r"\d+(?:[.,]\d+)?",
        value
    )

    if not match:
        return ""

    try:

        numero = float(
            match.group().replace(",", ".")
        )

        if numero.is_integer():
            return int(numero)

        return numero

    except Exception:
        return ""


# ============================================================
# NORMALIZZA DATA
# ============================================================

def normalizza_data(value):

    value = pulisci_testo(value)

    if not value:
        return ""

    try:

        data = pd.to_datetime(
            value,
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
# SCHEMA JSON GEMINI
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
                    },

                },

                "required": [
                    "COD_CLIENTE",
                    "RAGIONE_SOCIALE",
                    "COD_ARTICOLO",
                    "DESCRIZIONE",
                    "QUANTITA",
                    "DATA_CONSEGNA",
                ],

                "additionalProperties": False,
            },
        }
    },

    "required": [
        "righe"
    ],

    "additionalProperties": False,
}


# ============================================================
# PROMPT GEMINI
# ============================================================

PROMPT_ESTRAZIONE = """
Sei il lettore documentale di Target ERP.

Devi leggere un ordine cliente o una richiesta commerciale.

Devi estrarre TUTTE le righe articolo presenti.

Per ogni riga estrai:

COD_CLIENTE
RAGIONE_SOCIALE
COD_ARTICOLO
DESCRIZIONE
QUANTITA
DATA_CONSEGNA

REGOLE IMPORTANTI:

1. Non inventare dati.

2. Se un dato non è presente o non è leggibile,
   restituisci una stringa vuota.

3. Il codice articolo deve essere copiato
   esattamente come appare nel documento.

4. La descrizione deve essere copiata
   esattamente dal documento quando disponibile.

5. Non confondere il codice cliente con il codice articolo.

6. Non confondere il numero dell'ordine con il codice articolo.

7. Ogni articolo deve essere una riga separata.

8. Non sommare articoli diversi.

9. Se ci sono 10 articoli devi restituire 10 righe.

10. Restituisci esclusivamente il JSON richiesto.
"""


# ============================================================
# ANALISI FILE
# ============================================================

def analizza_file(uploaded_file):

    if client is None:

        raise RuntimeError(
            "Gemini non è configurato. "
            "Controlla GEMINI_API_KEY nei Secrets di Streamlit."
        )


    file_bytes = uploaded_file.getvalue()

    if not file_bytes:

        raise ValueError(
            "Il file caricato è vuoto."
        )


    mime_type = (
        uploaded_file.type
        or "application/octet-stream"
    )


    if mime_type == "application/pdf":

        parte_file = types.Part.from_bytes(
            data=file_bytes,
            mime_type="application/pdf"
        )

    elif mime_type.startswith("image/"):

        parte_file = types.Part.from_bytes(
            data=file_bytes,
            mime_type=mime_type
        )

    else:

        raise ValueError(
            "Formato file non supportato."
        )


    response = client.models.generate_content(

        model=MODELLO_GEMINI,

        contents=[
            PROMPT_ESTRAZIONE,
            parte_file,
        ],

        config=types.GenerateContentConfig(

            response_mime_type="application/json",

            response_schema=SCHEMA_ESTRAZIONE,
        ),
    )


    testo_risposta = response.text


    try:

        risultato = json.loads(
            testo_risposta
        )

    except Exception as exc:

        raise ValueError(
            "Gemini non ha restituito "
            f"un JSON valido: {exc}"
        )


    return elabora_righe(
        risultato.get(
            "righe",
            []
        )
    )


# ============================================================
# ANALISI EMAIL
# ============================================================

def analizza_email(testo_email):

    if client is None:

        raise RuntimeError(
            "Gemini non è configurato. "
            "Controlla GEMINI_API_KEY nei Secrets di Streamlit."
        )


    testo_email = pulisci_testo(
        testo_email
    )


    if not testo_email:

        raise ValueError(
            "Il testo dell'email è vuoto."
        )


    response = client.models.generate_content(

        model=MODELLO_GEMINI,

        contents=[
            PROMPT_ESTRAZIONE,
            "TESTO DELL'ORDINE:\n"
            + testo_email,
        ],

        config=types.GenerateContentConfig(

            response_mime_type="application/json",

            response_schema=SCHEMA_ESTRAZIONE,
        ),
    )


    try:

        risultato = json.loads(
            response.text
        )

    except Exception as exc:

        raise ValueError(
            "Gemini non ha restituito "
            f"un JSON valido: {exc}"
        )


    return elabora_righe(
        risultato.get(
            "righe",
            []
        )
    )


# ============================================================
# ELABORAZIONE RIGHE
# ============================================================

def elabora_righe(righe):

    risultati = []


    for record in righe:

        if not isinstance(
            record,
            dict
        ):
            continue


        # ====================================================
        # DATI GREZZI GEMINI
        # ====================================================

        ragione_gemini = pulisci_testo(
            record.get(
                "RAGIONE_SOCIALE",
                ""
            )
        )


        codice_cliente_gemini = pulisci_testo(
            record.get(
                "COD_CLIENTE",
                ""
            )
        )


        codice_articolo_gemini = pulisci_testo(
            record.get(
                "COD_ARTICOLO",
                ""
            )
        )


        descrizione_gemini = pulisci_testo(
            record.get(
                "DESCRIZIONE",
                ""
            )
        )


        quantita_gemini = normalizza_quantita(
            record.get(
                "QUANTITA",
                ""
            )
        )


        data_gemini = normalizza_data(
            record.get(
                "DATA_CONSEGNA",
                ""
            )
        )


        # ====================================================
        # CLIENTE
        # ====================================================

        cliente, clienti_simili = cerca_cliente(
            ragione_gemini
        )


        if cliente is None:

            cliente, clienti_simili = cerca_cliente(
                codice_cliente_gemini
            )


        if cliente:

            codice_cliente = cliente["codice"]
            ragione_sociale = cliente["ragione"]

            conf_cliente = (
                clienti_simili[0][1]
                if clienti_simili
                else 1.0
            )

        else:

            codice_cliente = codice_cliente_gemini
            ragione_sociale = ragione_gemini
            conf_cliente = (
                clienti_simili[0][1]
                if clienti_simili
                else 0.0
            )


        # ====================================================
        # ARTICOLO
        # ====================================================

        articolo, articoli_simili = cerca_articolo(

            codice=codice_articolo_gemini,

            descrizione=descrizione_gemini
        )


        if articolo:

            codice_articolo = articolo["codice"]

            # IMPORTANTE:
            # quando troviamo il codice nell'anagrafica,
            # la descrizione ufficiale viene presa
            # direttamente da articoli.xlsx.

            descrizione = articolo["descrizione"]

            conf_articolo = (
                articoli_simili[0][1]
                if articoli_simili
                else 1.0
            )

        else:

            codice_articolo = codice_articolo_gemini

            descrizione = descrizione_gemini

            conf_articolo = (
                articoli_simili[0][1]
                if articoli_simili
                else 0.0
            )


        risultati.append(
            {
                "COD_CLIENTE":
                    codice_cliente,

                "RAGIONE_SOCIALE":
                    ragione_sociale,

                "COD_ARTICOLO":
                    codice_articolo,

                "DESCRIZIONE":
                    descrizione,

                "QUANTITA":
                    quantita_gemini,

                "DATA_CONSEGNA":
                    data_gemini,

                "_CONF_CLIENTE":
                    conf_cliente,

                "_CONF_ARTICOLO":
                    conf_articolo,

                "_CLIENTI_SIMILI":
                    clienti_simili,

                "_ARTICOLI_SIMILI":
                    articoli_simili,
            }
        )


    return risultati


# ============================================================
# SESSION STATE
# ============================================================

if "dati" not in st.session_state:

    st.session_state.dati = []


# ============================================================
# HEADER
# ============================================================

st.title(
    "📦 Target ERP — Smart Order Reader"
)

st.caption(
    "Lettura automatica di ordini PDF e email "
    "con confronto intelligente con le anagrafiche."
)


# ============================================================
# STATO GEMINI
# ============================================================

if client is None:

    st.error(
        "Gemini non configurato. "
        "Controlla GEMINI_API_KEY nei Secrets di Streamlit "
        "e google-genai nel requirements.txt."
    )


# ============================================================
# TABS
# ============================================================

tab_pdf, tab_email = st.tabs(
    [
        "📄 PDF / Immagine",
        "✉️ Email",
    ]
)


# ============================================================
# PDF
# ============================================================

with tab_pdf:

    uploaded_file = st.file_uploader(

        "Carica l'ordine",

        type=[
            "pdf",
            "png",
            "jpg",
            "jpeg",
            "webp",
        ],

        label_visibility="collapsed",
    )


    if uploaded_file:

        st.caption(
            f"File selezionato: {uploaded_file.name}"
        )


        if st.button(
            "⚡ Leggi ordine",
            type="primary",
            key="leggi_pdf",
        ):

            if client is None:

                st.error(
                    "GEMINI_API_KEY non configurata."
                )

            else:

                with st.spinner(
                    "Gemini sta leggendo l'ordine..."
                ):

                    try:

                        nuove_righe = analizza_file(
                            uploaded_file
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


                    except Exception as exc:

                        st.error(
                            f"Errore durante la lettura: {exc}"
                        )


# ============================================================
# EMAIL
# ============================================================

with tab_email:

    testo_email = st.text_area(

        "Incolla qui il testo dell'ordine",

        height=220,

        placeholder=(
            "Incolla qui il contenuto "
            "dell'email del cliente..."
        ),
    )


    if st.button(
        "⚡ Leggi email",
        type="primary",
        key="leggi_email",
    ):

        if client is None:

            st.error(
                "GEMINI_API_KEY non configurata."
            )

        elif not testo_email.strip():

            st.warning(
                "Incolla prima il testo dell'ordine."
            )

        else:

            with st.spinner(
                "Gemini sta leggendo l'email..."
            ):

                try:

                    nuove_righe = analizza_email(
                        testo_email
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


                except Exception as exc:

                    st.error(
                        f"Errore durante la lettura: {exc}"
                    )


# ============================================================
# TABELLA
# ============================================================

st.divider()

st.subheader(
    "📋 Ordine estratto"
)


colonne_tabella = [
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
        columns=colonne_tabella
    )


for colonna in colonne_tabella:

    if colonna not in df.columns:

        df[colonna] = ""


df_visibile = df[
    colonne_tabella
].copy()


# ============================================================
# DATA EDITOR
# ============================================================

edited_df = st.data_editor(

    df_visibile,

    use_container_width=True,

    num_rows="dynamic",

    key="editor_ordini",

    column_config={

        "COD_CLIENTE":
            st.column_config.TextColumn(
                "COD_CLIENTE"
            ),

        "RAGIONE_SOCIALE":
            st.column_config.SelectboxColumn(

                "RAGIONE SOCIALE",

                options=sorted(
                    {
                        cliente["ragione"]
                        for cliente in CLIENTI
                    }
                ),

                required=False,
            ),

        "COD_ARTICOLO":
            st.column_config.SelectboxColumn(

                "COD_ARTICOLO",

                options=sorted(
                    {
                        articolo["codice"]
                        for articolo in ARTICOLI
                    }
                ),

                required=False,
            ),

        "DESCRIZIONE":
            st.column_config.TextColumn(
                "DESCRIZIONE"
            ),

        "QUANTITA":
            st.column_config.NumberColumn(

                "QUANTITA",

                min_value=0,

                step=1,
            ),

        "DATA_CONSEGNA":
            st.column_config.TextColumn(

                "DATA CONSEGNA",

                help="Formato GG/MM/AAAA",
            ),
    },
)


# ============================================================
# SALVATAGGIO MODIFICHE
# ============================================================

if st.session_state.dati:

    dati_originali = st.session_state.dati

    nuovi_dati = []

    for indice, riga in edited_df.iterrows():

        record = riga.to_dict()

        if indice < len(dati_originali):

            vecchio_record = dati_originali[indice]

            record["_CONF_CLIENTE"] = (
                vecchio_record.get(
                    "_CONF_CLIENTE",
                    1.0
                )
            )

            record["_CONF_ARTICOLO"] = (
                vecchio_record.get(
                    "_CONF_ARTICOLO",
                    1.0
                )
            )

            record["_CLIENTI_SIMILI"] = (
                vecchio_record.get(
                    "_CLIENTI_SIMILI",
                    []
                )
            )

            record["_ARTICOLI_SIMILI"] = (
                vecchio_record.get(
                    "_ARTICOLI_SIMILI",
                    []
                )
            )

        nuovi_dati.append(record)


    st.session_state.dati = nuovi_dati


# ============================================================
# CONTROLLO CORRISPONDENZE
# ============================================================

if st.session_state.dati:

    st.subheader(
        "🔎 Controllo corrispondenze"
    )


    almeno_un_avviso = False


    for indice, riga in enumerate(
        st.session_state.dati
    ):

        conf_cliente = riga.get(
            "_CONF_CLIENTE",
            1.0
        )

        conf_articolo = riga.get(
            "_CONF_ARTICOLO",
            1.0
        )


        clienti_simili = riga.get(
            "_CLIENTI_SIMILI",
            []
        )


        articoli_simili = riga.get(
            "_ARTICOLI_SIMILI",
            []
        )


        if (
            conf_cliente < 0.88
            and clienti_simili
        ):

            almeno_un_avviso = True

            with st.expander(
                f"🟡 Cliente riga {indice + 1}"
            ):

                st.write(
                    "Cliente letto dal documento:"
                )

                st.write(
                    riga.get(
                        "RAGIONE_SOCIALE",
                        ""
                    )
                )


                st.write(
                    "Possibili clienti:"
                )


                for cliente, score in clienti_simili[:5]:

                    st.write(
                        f"• {cliente['ragione']} "
                        f"— Codice: {cliente['codice']} "
                        f"— Corrispondenza: {score:.0%}"
                    )


        if (
            conf_articolo < 0.92
            and articoli_simili
        ):

            almeno_un_avviso = True

            with st.expander(
                f"🟡 Articolo riga {indice + 1}"
            ):

                st.write(
                    "Articolo letto dal documento:"
                )

                st.write(
                    f"Codice: "
                    f"{riga.get('COD_ARTICOLO', '')}"
                )

                st.write(
                    f"Descrizione: "
                    f"{riga.get('DESCRIZIONE', '')}"
                )


                st.write(
                    "Possibili articoli:"
                )


                for articolo, score in articoli_simili[:5]:

                    st.write(
                        f"• {articolo['codice']} "
                        f"— {articolo['descrizione']} "
                        f"— Corrispondenza: {score:.0%}"
                    )


    if not almeno_un_avviso:

        st.success(
            "✓ Tutte le corrispondenze sono considerate sicure."
        )


# ============================================================
# ESPORTAZIONE CSV
# ============================================================

st.divider()


if st.session_state.dati:

    df_export = pd.DataFrame(
        st.session_state.dati
    )


    for colonna in colonne_tabella:

        if colonna not in df_export.columns:

            df_export[colonna] = ""


    df_export = df_export[
        colonne_tabella
    ]


else:

    df_export = pd.DataFrame(
        columns=colonne_tabella
    )


csv_data = df_export.to_csv(
    index=False,
    encoding="utf-8-sig"
).encode("utf-8-sig")


st.download_button(

    label="📥 Esporta CSV",

    data=csv_data,

    file_name="ordine_estratto.csv",

    mime="text/csv",

    type="primary",
)


if st.button(
    "🗑️ Svuota tabella"
):

    st.session_state.dati = []

    st.rerun()


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
            len(CLIENTI)
        )


    with col2:

        st.metric(
            "Articoli caricati",
            len(ARTICOLI)
        )


    with col3:

        st.metric(
            "Righe in tabella",
            len(st.session_state.dati)
        )


    if client:

        st.success(
            "✓ Gemini configurato"
        )

    else:

        st.error(
            "✗ Gemini non configurato"
        )


    if df_clienti.empty:

        st.warning(
            "clienti.xlsx non trovato "
            "o non leggibile."
        )

    else:

        st.caption(
            f"✓ clienti.xlsx — "
            f"{len(df_clienti)} righe"
        )


    if df_articoli.empty:

        st.warning(
            "articoli.xlsx non trovato "
            "o non leggibile."
        )

    else:

        st.caption(
            f"✓ articoli.xlsx — "
            f"{len(df_articoli)} righe"
        )