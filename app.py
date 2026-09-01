import json
import re
from difflib import SequenceMatcher
from pathlib import Path

import pandas as pd
import streamlit as st

from google import genai
from google.genai import types

from pydantic import BaseModel, Field

# ============================================================

# CONFIGURAZIONE PAGINA

# ============================================================

st.set_page_config(
page_title="Target ERP - Lettore Ordini",
layout="wide"
)

# ============================================================

# CSS

# ============================================================

st.markdown(
""" <style>

```
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
}

</style>
""",
unsafe_allow_html=True
```

)

# ============================================================

# FILE

# ============================================================

BASE_DIR = Path(**file**).resolve().parent

FILE_CLIENTI = BASE_DIR / "clienti.xlsx"
FILE_ARTICOLI = BASE_DIR / "articoli.xlsx"

MODELLO_GEMINI = "gemini-3.1-flash-lite"

# ============================================================

# CLIENT GEMINI

# ============================================================

@st.cache_resource
def get_gemini_client():

```
try:

    api_key = st.secrets.get("GEMINI_API_KEY")

    if not api_key:
        return None

    return genai.Client(
        api_key=api_key
    )

except Exception:

    return None
```

client = get_gemini_client()

# ============================================================

# MODELLI PYDANTIC

# ============================================================

class RigaOrdine(BaseModel):

```
COD_CLIENTE: str = Field(
    default="",
    description="Codice cliente presente nel documento"
)

RAGIONE_SOCIALE: str = Field(
    default="",
    description="Ragione sociale del cliente"
)

COD_ARTICOLO: str = Field(
    default="",
    description="Codice articolo presente nel documento"
)

DESCRIZIONE: str = Field(
    default="",
    description="Descrizione articolo presente nel documento"
)

QUANTITA: str = Field(
    default="",
    description="Quantità ordinata"
)

DATA_CONSEGNA: str = Field(
    default="",
    description="Data di consegna richiesta"
)
```

class RisultatoOrdine(BaseModel):

```
righe: list[RigaOrdine] = Field(
    default_factory=list
)
```

# ============================================================

# UTILITÀ

# ============================================================

def normalizza_testo(valore):

```
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
```

def normalizza_chiave(valore):

```
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
```

def similarita(a, b):

```
a = normalizza_chiave(a)
b = normalizza_chiave(b)

if not a or not b:
    return 0.0

if a == b:
    return 1.0

return SequenceMatcher(
    None,
    a,
    b
).ratio()
```

# ============================================================

# CARICAMENTO EXCEL

# ============================================================

@st.cache_data
def carica_excel(percorso):

```
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
```

df_clienti = carica_excel(
FILE_CLIENTI
)

df_articoli = carica_excel(
FILE_ARTICOLI
)

# ============================================================

# RICERCA COLONNE

# ============================================================

def trova_colonna(
df,
nomi
):

```
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
```

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

```
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
```

# ============================================================

# ANAGRAFICA ARTICOLI

# ============================================================

def costruisci_anagrafica_articoli():

```
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
```

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

```
chiave = normalizza_chiave(
    cliente["ragione_sociale"]
)

if chiave:

    mappa_clienti[chiave] = cliente
```

mappa_codici_cliente = {}

for cliente in anagrafica_clienti:

```
chiave = normalizza_chiave(
    cliente["codice_cliente"]
)

if chiave:

    mappa_codici_cliente[chiave] = cliente
```

mappa_articoli = {}

for articolo in anagrafica_articoli:

```
chiave = normalizza_chiave(
    articolo["codice"]
)

if chiave:

    mappa_articoli[chiave] = articolo
```

# ============================================================

# SUGGERIMENTI CLIENTE

# ============================================================

def suggerimenti_cliente(
valore,
massimo=3
):

```
valore = normalizza_testo(
    valore
)

if not valore:
    return []

risultati = []

for cliente in anagrafica_clienti:

    score_nome = similarita(
        valore,
        cliente["ragione_sociale"]
    )

    score_codice = similarita(
        valore,
        cliente["codice_cliente"]
    )

    score = max(
        score_nome,
        score_codice
    )

    if score >= 0.55:

        risultati.append(
            (
                score,
                cliente
            )
        )

risultati.sort(
    key=lambda x: x[0],
    reverse=True
)

return resultados_unicos_clienti(
    resultados=risultati,
    massimo=massimo
)
```

def resultados_unicos_clienti(
resultados,
massimo
):

```
output = []

viste = set()

for score, cliente in resultados:

    chiave = normalizza_chiave(
        cliente["ragione_sociale"]
    )

    if chiave in viste:
        continue

    viste.add(
        chiave
    )

    output.append(
        {
            "score": score,
            "cliente": cliente
        }
    )

    if len(output) >= massimo:
        break

return output
```

# ============================================================

# SUGGERIMENTI ARTICOLO

# ============================================================

def suggerimenti_articolo(
codice="",
descrizione="",
massimo=3
):

```
codice = normalizza_testo(
    codice
)

descrizione = normalizza_testo(
    descrizione
)

risultati = []

for articolo in anagrafica_articoli:

    score_codice = 0.0
    score_descrizione = 0.0

    if codice:

        score_codice = similarita(
            codice,
            articolo["codice"]
        )

    if descrizione:

        score_descrizione = similarita(
            descrizione,
            articolo["descrizione"]
        )

    if codice and descrizione:

        score = max(
            score_codice,
            score_descrizione
        )

    elif codice:

        score = score_codice

    else:

        score = score_descrizione

    if score >= 0.55:

        risultati.append(
            (
                score,
                articolo
            )
        )

risultati.sort(
    key=lambda x: x[0],
    reverse=True
)

output = []

viste = set()

for score, articolo in risultati:

    chiave = normalizza_chiave(
        articolo["codice"]
    )

    if chiave in viste:
        continue

    viste.add(
        chiave
    )

    output.append(
        {
            "score": score,
            "articolo": articolo
        }
    )

    if len(output) >= massimo:
        break

return output
```

# ============================================================

# TROVA CLIENTE ESATTO

# ============================================================

def trova_cliente(
ragione_sociale="",
codice_cliente=""
):

```
ragione_sociale = normalizza_testo(
    ragione_sociale
)

codice_cliente = normalizza_testo(
    codice_cliente
)

if codice_cliente:

    chiave = normalizza_chiave(
        codice_cliente
    )

    if chiave in mappa_codici_cliente:

        return mappa_codici_cliente[
            chiave
        ]

if ragione_sociale:

    chiave = normalizza_chiave(
        ragione_sociale
    )

    if chiave in mappa_clienti:

        return mappa_clienti[
            chiave
        ]

return None
```

# ============================================================

# TROVA ARTICOLO ESATTO

# ============================================================

def trova_articolo(
codice="",
descrizione=""
):

```
codice = normalizza_testo(
    codice
)

descrizione = normalizza_testo(
    descrizione
)

if codice:

    chiave = normalizza_chiave(
        codice
    )

    if chiave in mappa_articoli:

        return mappa_articoli[
            chiave
        ]

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

return None
```

# ============================================================

# NORMALIZZA QUANTITÀ

# ============================================================

def normalizza_quantita(
valore
):

```
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
```

# ============================================================

# NORMALIZZA DATA

# ============================================================

def normalizza_data(
valore
):

```
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
```

# ============================================================

# PROMPT

# ============================================================

PROMPT_ORDINE = """

Sei il lettore automatico degli ordini di Target ERP.

Devi analizzare il documento allegato.

ESTRAI TUTTE LE RIGHE DI ARTICOLI.

Per ogni riga estrai:

COD_CLIENTE
RAGIONE_SOCIALE
COD_ARTICOLO
DESCRIZIONE
QUANTITA
DATA_CONSEGNA

REGOLE IMPORTANTI:

1. Non inventare informazioni.

2. Copia il codice articolo esattamente come
   appare nel documento.

3. Copia la descrizione esattamente come appare
   nel documento, quando è presente.

4. Non correggere autonomamente i codici.

5. Se un dato non è presente lascia il campo vuoto.

6. Ogni articolo deve essere una riga separata.

7. Non sommare articoli diversi.

8. Se ci sono più quantità dello stesso articolo
   in righe diverse, mantieni le righe separate.

9. La quantità deve essere estratta dalla riga
   corrispondente.

10. La data consegna deve essere quella associata
    alla riga o all'ordine.

11. Se il documento contiene intestazioni,
    note, totali o condizioni commerciali,
    NON trattarle come articoli.

12. Restituisci esclusivamente i dati strutturati.
    """

# ============================================================

# ANALISI PDF / IMMAGINE

# ============================================================

def analizza_file(
uploaded_file
):

```
if client is None:

    raise RuntimeError(
        "Client Gemini non disponibile."
    )

file_bytes = uploaded_file.getvalue()

if not file_bytes:

    raise ValueError(
        "Il file è vuoto."
    )

mime_type = uploaded_file.type

if not mime_type:

    nome = uploaded_file.name.lower()

    if nome.endswith(".pdf"):

        mime_type = "application/pdf"

    elif nome.endswith(".png"):

        mime_type = "image/png"

    elif nome.endswith(".jpg"):

        mime_type = "image/jpeg"

    elif nome.endswith(".jpeg"):

        mime_type = "image/jpeg"

    elif nome.endswith(".webp"):

        mime_type = "image/webp"

    else:

        raise ValueError(
            "Formato file non supportato."
        )

file_part = types.Part.from_bytes(
    data=file_bytes,
    mime_type=mime_type
)

response = client.models.generate_content(

    model=MODELLO_GEMINI,

    contents=[
        file_part,
        PROMPT_ORDINE
    ],

    config=types.GenerateContentConfig(

        response_mime_type="application/json",

        response_schema=RisultatoOrdine
    )
)

if not response.text:

    raise ValueError(
        "Gemini non ha restituito alcun risultato."
    )

risultato = RisultatoOrdine.model_validate_json(
    response.text
)

return resultado_a_righe(
    resultado=risultato
)
```

# ============================================================

# ANALISI EMAIL

# ============================================================

def analizza_email(
testo_email
):

```
if client is None:

    raise RuntimeError(
        "Client Gemini non disponibile."
    )

if not testo_email.strip():

    return []

prompt = PROMPT_ORDINE + """
```

ANALIZZA IL SEGUENTE TESTO DI EMAIL:

---

""" + testo_email + """

---

Individua tutte le righe articolo presenti.
"""

```
response = client.models.generate_content(

    model=MODELLO_GEMINI,

    contents=prompt,

    config=types.GenerateContentConfig(

        response_mime_type="application/json",

        response_schema=RisultatoOrdine
    )
)

if not response.text:

    raise ValueError(
        "Gemini non ha restituito alcun risultato."
    )

risultato = RisultatoOrdine.model_validate_json(
    response.text
)

return resultado_a_righe(
    resultado=risultato
)
```

# ============================================================

# CONVERSIONE RISULTATO

# ============================================================

def resultado_a_righe(
resultado
):

```
righe = []

for record in resultado.righe:

    codice_cliente = normalizza_testo(
        record.COD_CLIENTE
    )

    ragione_sociale = normalizza_testo(
        record.RAGIONE_SOCIALE
    )

    codice_articolo = normalizza_testo(
        record.COD_ARTICOLO
    )

    descrizione = normalizza_testo(
        record.DESCRIZIONE
    )

    quantita = normalizza_quantita(
        record.QUANTITA
    )

    data_consegna = normalizza_data(
        record.DATA_CONSEGNA
    )

    # ----------------------------------------------------
    # CLIENTE
    # ----------------------------------------------------

    cliente = trova_cliente(
        ragione_sociale=ragione_sociale,
        codice_cliente=codice_cliente
    )

    suggerimenti_cliente_riga = []

    if cliente:

        codice_cliente = cliente[
            "codice_cliente"
        ]

        ragione_sociale = cliente[
            "ragione_sociale"
        ]

    else:

        suggerimenti_cliente_riga = (
            suggerimenti_cliente(
                ragione_sociale
                if ragione_sociale
                else codice_cliente
            )
        )

    # ----------------------------------------------------
    # ARTICOLO
    # ----------------------------------------------------

    articolo = trova_articolo(
        codice=codice_articolo,
        descrizione=descrizione
    )

    suggerimenti_articolo_riga = []

    if articolo:

        codice_articolo = articolo[
            "codice"
        ]

        descrizione = articolo[
            "descrizione"
        ]

    else:

        suggerimenti_articolo_riga = (
            suggerimenti_articolo(
                codice=codice_articolo,
                descrizione=descrizione
            )
        )

    # ----------------------------------------------------
    # TESTO SUGGERIMENTI
    # ----------------------------------------------------

    suggerimenti = []

    if suggerimenti_cliente_riga:

        cliente_testo = []

        for item in suggerimenti_cliente_riga:

            cliente = item["cliente"]

            percentuale = round(
                item["score"] * 100
            )

            nome = cliente[
                "ragione_sociale"
            ]

            codice = cliente[
                "codice_cliente"
            ]

            if codice:

                cliente_testo.append(
                    f"{nome} "
                    f"({codice}) "
                    f"{percentuale}%"
                )

            else:

                cliente_testo.append(
                    f"{nome} "
                    f"{percentuale}%"
                )

        suggerimenti.append(
            "CLIENTE: "
            + " | ".join(
                cliente_testo
            )
        )

    if suggerimenti_articolo_riga:

        articolo_testo = []

        for item in suggerimenti_articolo_riga:

            articolo = item["articolo"]

            percentuale = round(
                item["score"] * 100
            )

            articolo_testo.append(
                f'{articolo["codice"]} - '
                f'{articolo["descrizione"]} '
                f'({percentuale}%)'
            )

        suggerimenti.append(
            "ARTICOLO: "
            + " | ".join(
                articolo_testo
            )
        )

    righe.append(
        {
            "COD_CLIENTE": codice_cliente,

            "RAGIONE_SOCIALE": ragione_sociale,

            "COD_ARTICOLO": codice_articolo,

            "DESCRIZIONE": descrizione,

            "QUANTITA": quantita,

            "DATA_CONSEGNA": data_consegna,

            "SUGGERIMENTI": (
                "\n".join(
                    suggerimenti
                )
            )
        }
    )

return righe
```

# ============================================================

# SESSION STATE

# ============================================================

if "dati" not in st.session_state:

```
st.session_state.dati = []
```

# ============================================================

# HEADER

# ============================================================

st.title(
"📦 Target ERP — Lettore Ordini"
)

st.caption(
"Importa un ordine PDF o il testo di un'email. "
"Il sistema estrarrà automaticamente cliente e articoli "
"e proporrà le corrispondenze più simili quando necessario."
)

# ============================================================

# TABS

# ============================================================

tab_pdf, tab_email = st.tabs(
[
"📄 PDF / Immagine",
"✉️ Email"
]
)

# ============================================================

# PDF

# ============================================================

with tab_pdf:

```
uploaded_file = st.file_uploader(

    "Carica ordine PDF o immagine",

    type=[
        "pdf",
        "jpg",
        "jpeg",
        "png",
        "webp"
    ]
)

if uploaded_file:

    st.caption(
        f"File selezionato: {uploaded_file.name}"
    )

    if st.button(
        "⚡ Leggi ordine",
        type="primary",
        use_container_width=True
    ):

        if client is None:

            st.error(
                "Client Gemini non disponibile."
            )

        else:

            try:

                with st.spinner(
                    "Gemini sta leggendo l'ordine..."
                ):

                    nuove_righe = analizza_file(
                        uploaded_file
                    )

                if nuove_righe:

                    st.session_state.dati.extend(
                        nuove_righe
                    )

                    st.success(
                        f"{len(nuove_righe)} "
                        "righe trovate."
                    )

                    st.rerun()

                else:

                    st.warning(
                        "Non sono state trovate "
                        "righe articolo."
                    )

            except Exception as e:

                st.error(
                    "Errore durante la lettura:"
                )

                st.code(
                    str(e)
                )
```

# ============================================================

# EMAIL

# ============================================================

with tab_email:

```
testo_email = st.text_area(

    "Incolla qui il testo dell'email o dell'ordine",

    height=250,

    placeholder=(
        "Esempio:\n"
        "Buongiorno,\n"
        "confermiamo il seguente ordine...\n"
        "Codice ABC123 quantità 4..."
    )
)

if st.button(
    "⚡ Leggi email",
    type="primary",
    use_container_width=True
):

    if not testo_email.strip():

        st.warning(
            "Inserisci prima il testo dell'email."
        )

    else:

        try:

            with st.spinner(
                "Gemini sta analizzando l'email..."
            ):

                nuove_righe = analizza_email(
                    testo_email
                )

            if nuove_righe:

                st.session_state.dati.extend(
                    nuove_righe
                )

                st.success(
                    f"{len(nuove_righe)} "
                    "righe trovate."
                )

                st.rerun()

            else:

                st.warning(
                    "Non sono state trovate "
                    "righe articolo."
                )

        except Exception as e:

            st.error(
                "Errore durante la lettura:"
            )

            st.code(
                str(e)
            )
```

# ============================================================

# TABELLA

# ============================================================

st.divider()

st.subheader(
"📋 Ordine importato"
)

if st.session_state.dati:

```
df = pd.DataFrame(
    st.session_state.dati
)
```

else:

```
df = pd.DataFrame(
    columns=[
        "COD_CLIENTE",
        "RAGIONE_SOCIALE",
        "COD_ARTICOLO",
        "DESCRIZIONE",
        "QUANTITA",
        "DATA_CONSEGNA",
        "SUGGERIMENTI"
    ]
)
```

# ============================================================

# GARANTISCE COLONNE

# ============================================================

colonne = [
"COD_CLIENTE",
"RAGIONE_SOCIALE",
"COD_ARTICOLO",
"DESCRIZIONE",
"QUANTITA",
"DATA_CONSEGNA",
"SUGGERIMENTI"
]

for colonna in colonne:

```
if colonna not in df.columns:

    df[colonna] = ""
```

df = df[colonne]

# ============================================================

# SINCRONIZZAZIONE MANUALE

# ============================================================

def sincronizza_riga(
riga
):

```
codice_cliente = normalizza_testo(
    riga["COD_CLIENTE"]
)

ragione = normalizza_testo(
    riga["RAGIONE_SOCIALE"]
)

codice_articolo = normalizza_testo(
    riga["COD_ARTICOLO"]
)

descrizione = normalizza_testo(
    riga["DESCRIZIONE"]
)

suggerimenti = []

# --------------------------------------------------------
# CLIENTE
# --------------------------------------------------------

cliente = trova_cliente(
    ragione_sociale=ragione,
    codice_cliente=codice_cliente
)

if cliente:

    riga["COD_CLIENTE"] = (
        cliente["codice_cliente"]
    )

    riga["RAGIONE_SOCIALE"] = (
        cliente["ragione_sociale"]
    )

else:

    alternative = suggerimenti_cliente(
        ragione
        if ragione
        else codice_cliente
    )

    for item in alternative:

        cliente_alt = item["cliente"]

        percentuale = round(
            item["score"] * 100
        )

        codice_alt = (
            cliente_alt["codice_cliente"]
        )

        nome_alt = (
            cliente_alt["ragione_sociale"]
        )

        suggerimenti.append(
            "CLIENTE: "
            f"{nome_alt} "
            f"({codice_alt}) "
            f"{percentuale}%"
        )

# --------------------------------------------------------
# ARTICOLO
# --------------------------------------------------------

articolo = trova_articolo(
    codice=codice_articolo,
    descrizione=descrizione
)

if articolo:

    riga["COD_ARTICOLO"] = (
        articolo["codice"]
    )

    riga["DESCRIZIONE"] = (
        articolo["descrizione"]
    )

else:

    alternative = suggerimenti_articolo(
        codice=codice_articolo,
        descrizione=descrizione
    )

    if alternative:

        testi = []

        for item in alternative:

            articolo_alt = (
                item["articolo"]
            )

            percentuale = round(
                item["score"] * 100
            )

            testi.append(
                f'{articolo_alt["codice"]} - '
                f'{articolo_alt["descrizione"]} '
                f'({percentuale}%)'
            )

        suggerimenti.append(
            "ARTICOLO: "
            + " | ".join(testi)
        )

riga["SUGGERIMENTI"] = (
    "\n".join(
        suggerimenti
    )
)

return riga
```

# ============================================================

# SINCRONIZZAZIONE

# ============================================================

if not df.empty:

```
df = df.apply(
    sincronizza_riga,
    axis=1
)
```

# ============================================================

# CONFIGURAZIONE TABELLA

# ============================================================

column_config = {

```
"COD_CLIENTE":
    st.column_config.TextColumn(
        "COD_CLIENTE"
    ),

"RAGIONE_SOCIALE":
    st.column_config.TextColumn(
        "RAGIONE SOCIALE"
    ),

"COD_ARTICOLO":
    st.column_config.TextColumn(
        "COD_ARTICOLO"
    ),

"DESCRIZIONE":
    st.column_config.TextColumn(
        "DESCRIZIONE",
        width="large"
    ),

"QUANTITA":
    st.column_config.NumberColumn(
        "QUANTITA",
        min_value=0,
        step=1
    ),

"DATA_CONSEGNA":
    st.column_config.TextColumn(
        "DATA CONSEGNA"
    ),

"SUGGERIMENTI":
    st.column_config.TextColumn(
        "⚠️ SUGGERIMENTI / CORRISPONDENZE",
        width="large",
        help=(
            "Quando il sistema non trova una "
            "corrispondenza esatta, mostra qui "
            "le alternative più simili."
        )
    )
```

}

# ============================================================

# EDITOR

# ============================================================

edited_df = st.data_editor(

```
df,

column_config=column_config,

use_container_width=True,

num_rows="dynamic",

hide_index=True,

key="editor_ordini"
```

)

# ============================================================

# NORMALIZZAZIONE DOPO MODIFICA

# ============================================================

if not edited_df.empty:

```
edited_df = edited_df.apply(
    sincronizza_riga,
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
```

st.session_state.dati = (
edited_df
.to_dict(
orient="records"
)
)

# ============================================================

# ESPORTAZIONE

# ============================================================

st.divider()

if not edited_df.empty:

```
csv_data = (
    edited_df
    .to_csv(
        index=False,
        encoding="utf-8-sig"
    )
    .encode("utf-8-sig")
)

st.download_button(

    label="📥 Esporta ordine CSV",

    data=csv_data,

    file_name="ordine_target_erp.csv",

    mime="text/csv",

    type="primary"
)
```

# ============================================================

# STATO SISTEMA

# ============================================================

st.divider()

with st.expander(
"ℹ️ Stato sistema"
):

```
col1, col2, col3 = st.columns(3)

with col1:

    st.metric(
        "Clienti",
        len(anagrafica_clienti)
    )

with col2:

    st.metric(
        "Articoli",
        len(anagrafica_articoli)
    )

with col3:

    st.metric(
        "Righe ordine",
        len(edited_df)
    )

if client:

    st.success(
        "✓ Gemini configurato"
    )

else:

    st.error(
        "✗ Gemini non configurato"
    )

if not df_clienti.empty:

    st.caption(
        f"✓ clienti.xlsx — "
        f"{len(df_clienti)} righe"
    )

else:

    st.warning(
        "clienti.xlsx non trovato"
    )

if not df_articoli.empty:

    st.caption(
        f"✓ articoli.xlsx — "
        f"{len(df_articoli)} righe"
    )

else:

    st.warning(
        "articoli.xlsx non trovato"
    )

