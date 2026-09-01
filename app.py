import json
import re
from difflib import SequenceMatcher
from pathlib import Path

import pandas as pd
import streamlit as st

try:
from google import genai
except ImportError:
genai = None

# ============================================================

# CONFIGURAZIONE

# ============================================================

st.set_page_config(
page_title="Target ERP - Lettore Ordini",
layout="wide"
)

BASE_DIR = Path(**file**).resolve().parent

FILE_CLIENTI = BASE_DIR / "clienti.xlsx"
FILE_ARTICOLI = BASE_DIR / "articoli.xlsx"

MODELLO_GEMINI = "gemini-3.7-flash"

# ============================================================

# CSS

# ============================================================

st.markdown(
""" <style>
footer,
#MainMenu,
header,
[data-testid="stHeader"],
[data-testid="stToolbar"],
[data-testid="stStatusWidget"] {
display: none !important;
}

```
.stDataFrame {
    width: 100%;
}

.stAlert {
    border-radius: 8px;
}
</style>
""",
unsafe_allow_html=True
```

)

# ============================================================

# CLIENT GEMINI

# ============================================================

@st.cache_resource
def get_gemini_client():

```
if genai is None:
    return None

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

# FUNZIONI TESTO

# ============================================================

def pulisci_testo(valore):

```
if valore is None:
    return ""

try:
    if pd.isna(valore):
        return ""
except Exception:
    pass

testo = str(valore).strip()

testo = re.sub(
    r"\s+",
    " ",
    testo
)

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

return testo
```

def chiave(valore):

```
testo = pulisci_testo(
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
a = chiave(a)
b = chiave(b)

if not a or not b:
    return 0

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

# TROVA COLONNA

# ============================================================

def trova_colonna(
df,
possibili
):

```
if df.empty:
    return None

possibili_norm = {
    chiave(x)
    for x in possibili
}

for colonna in df.columns:

    if chiave(colonna) in possibili_norm:
        return colonna

return None
```

# ============================================================

# COLONNE CLIENTI

# ============================================================

COL_RAGIONE = trova_colonna(
df_clienti,
[
"RAGIONE_SOCIALE",
"RAGIONE SOCIALE",
"RAGIONE SOCIALE CLIENTE",
"CLIENTE",
"NOME"
]
)

COL_COD_CLIENTE = trova_colonna(
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

COL_COD_ARTICOLO = trova_colonna(
df_articoli,
[
"CODART",
"COD_ARTICOLO",
"CODICE ARTICOLO",
"CODICE"
]
)

COL_DESCRIZIONE = trova_colonna(
df_articoli,
[
"DESCRIZIONE ARTICOLO",
"DESCRIZIONE",
"DESCART"
]
)

# ============================================================

# COSTRUZIONE CLIENTI

# ============================================================

def costruisci_clienti():

```
risultati = []

if df_clienti.empty:
    return risultati

if not COL_RAGIONE:
    return risultati

for _, riga in df_clienti.iterrows():

    ragione = pulisci_testo(
        riga.get(
            COL_RAGIONE,
            ""
        )
    )

    if not ragione:
        continue

    codice = ""

    if COL_COD_CLIENTE:

        codice = pulisci_testo(
            riga.get(
                COL_COD_CLIENTE,
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

# COSTRUZIONE ARTICOLI

# ============================================================

def costruisci_articoli():

```
risultati = []

if df_articoli.empty:
    return risultati

if not COL_COD_ARTICOLO:
    return risultati

for _, riga in df_articoli.iterrows():

    codice = pulisci_testo(
        riga.get(
            COL_COD_ARTICOLO,
            ""
        )
    )

    if not codice:
        continue

    descrizione = ""

    if COL_DESCRIZIONE:

        descrizione = pulisci_testo(
            riga.get(
                COL_DESCRIZIONE,
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

clienti = costruisci_clienti()
articoli = costruisci_articoli()

# ============================================================

# MAPPE

# ============================================================

MAPPA_CLIENTI = {
chiave(x["ragione_sociale"]): x
for x in clienti
if chiave(x["ragione_sociale"])
}

MAPPA_CODICI_CLIENTE = {
chiave(x["codice_cliente"]): x
for x in clienti
if chiave(x["codice_cliente"])
}

MAPPA_ARTICOLI = {
chiave(x["codice"]): x
for x in articoli
if chiave(x["codice"])
}

# ============================================================

# CANDIDATI CLIENTE

# ============================================================

def candidati_cliente(
valore,
massimo=3
):

```
valore = pulisci_testo(
    valore
)

if not valore:
    return []

risultati = []

for cliente in clienti:

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

    if score > 0:

        risultati.append(
            {
                "valore": cliente[
                    "ragione_sociale"
                ],
                "codice": cliente[
                    "codice_cliente"
                ],
                "score": score
            }
        )

risultati.sort(
    key=lambda x: x["score"],
    reverse=True
)

return risultati[:massimo]
```

# ============================================================

# CANDIDATI ARTICOLO

# ============================================================

def candidati_articolo(
codice,
descrizione,
massimo=3
):

```
codice = pulisci_testo(
    codice
)

descrizione = pulisci_testo(
    descrizione
)

risultati = []

for articolo in articoli:

    score_codice = 0

    score_descrizione = 0

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

    score = max(
        score_codice,
        score_descrizione
    )

    if score > 0:

        risultati.append(
            {
                "codice": articolo[
                    "codice"
                ],
                "descrizione": articolo[
                    "descrizione"
                ],
                "score": score
            }
        )

risultati.sort(
    key=lambda x: x["score"],
    reverse=True
)

return risultati[:massimo]
```

# ============================================================

# VALIDAZIONE CLIENTE

# ============================================================

def valida_cliente(
cliente_estratto,
codice_estratto
):

```
cliente_estratto = pulisci_testo(
    cliente_estratto
)

codice_estratto = pulisci_testo(
    codice_estratto
)

# MATCH ESATTO NOME

if cliente_estratto:

    trovato = MAPPA_CLIENTI.get(
        chiave(cliente_estratto)
    )

    if trovato:

        return {
            "codice_cliente":
                trovato["codice_cliente"],

            "ragione_sociale":
                trovato["ragione_sociale"],

            "stato":
                "OK",

            "candidati":
                []
        }

# MATCH ESATTO CODICE

if codice_estratto:

    trovato = MAPPA_CODICI_CLIENTE.get(
        chiave(codice_estratto)
    )

    if trovato:

        return {
            "codice_cliente":
                trovato["codice_cliente"],

            "ragione_sociale":
                trovato["ragione_sociale"],

            "stato":
                "OK",

            "candidati":
                []
        }

# CANDIDATI

candidati = candidati_cliente(
    cliente_estratto or codice_estratto
)

if candidati:

    migliore = candidati[0]

    if migliore["score"] >= 0.90:

        return {
            "codice_cliente":
                migliore["codice"],

            "ragione_sociale":
                migliore["valore"],

            "stato":
                "VERIFICA",

            "candidati":
                candidati
        }

    return {
        "codice_cliente": "",
        "ragione_sociale": cliente_estratto,
        "stato": "NON TROVATO",
        "candidati": candidati
    }

return {
    "codice_cliente": "",
    "ragione_sociale": cliente_estratto,
    "stato": "NON TROVATO",
    "candidati": []
}
```

# ============================================================

# VALIDAZIONE ARTICOLO

# ============================================================

def valida_articolo(
codice_estratto,
descrizione_estratta
):

```
codice_estratto = pulisci_testo(
    codice_estratto
)

descrizione_estratta = pulisci_testo(
    descrizione_estratta
)

# --------------------------------------------------------
# MATCH ESATTO CODICE
# --------------------------------------------------------

if codice_estratto:

    trovato = MAPPA_ARTICOLI.get(
        chiave(codice_estratto)
    )

    if trovato:

        return {
            "codice":
                trovato["codice"],

            "descrizione":
                trovato["descrizione"],

            "stato":
                "OK",

            "candidati":
                []
        }

# --------------------------------------------------------
# MATCH ESATTO DESCRIZIONE
# --------------------------------------------------------

if descrizione_estratta:

    for articolo in articoli:

        if (
            chiave(
                articolo["descrizione"]
            )
            ==
            chiave(
                descrizione_estratta
            )
        ):

            return {
                "codice":
                    articolo["codice"],

                "descrizione":
                    articolo["descrizione"],

                "stato":
                    "OK",

                "candidati":
                    []
            }

# --------------------------------------------------------
# CANDIDATI
# --------------------------------------------------------

candidati = candidati_articolo(
    codice_estratto,
    descrizione_estratta
)

if candidati:

    migliore = candidati[0]

    if migliore["score"] >= 0.92:

        return {
            "codice":
                migliore["codice"],

            "descrizione":
                migliore["descrizione"],

            "stato":
                "VERIFICA",

            "candidati":
                candidati
        }

    return {
        "codice":
            codice_estratto,

        "descrizione":
            descrizione_estratta,

        "stato":
            "NON TROVATO",

        "candidati":
            candidati
    }

return {
    "codice":
        codice_estratto,

    "descrizione":
        descrizione_estratta,

    "stato":
        "NON TROVATO",

    "candidati":
        []
}
```

# ============================================================

# NORMALIZZA QUANTITÀ

# ============================================================

def normalizza_quantita(
valore
):

```
valore = pulisci_testo(
    valore
)

if not valore:
    return ""

match = re.search(
    r"\d+(?:[.,]\d+)?",
    valore
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
valore = pulisci_testo(
    valore
)

if not valore:
    return ""

try:

    data = pd.to_datetime(
        valore,
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

# PROMPT GEMINI

# ============================================================

PROMPT_BASE = """
Sei il lettore documentale di Target ERP.

Devi leggere un ordine cliente.

ESTRAI ESCLUSIVAMENTE le informazioni realmente
presenti nel documento.

NON devi inventare codici.

NON devi correggere i codici.

NON devi scegliere un codice dal tuo ragionamento.

Se il codice è poco leggibile, riportalo esattamente
per quanto possibile.

Per ogni riga articolo estrai:

* COD_CLIENTE
* RAGIONE_SOCIALE
* COD_ARTICOLO
* DESCRIZIONE
* QUANTITA
* DATA_CONSEGNA

IMPORTANTE:

Se ci sono 10 articoli, devi restituire 10 righe.

Non sommare articoli diversi.

Non eliminare righe duplicate.

Se un'informazione non è presente,
restituisci una stringa vuota.

Restituisci esclusivamente JSON nel seguente formato:

{
"righe": [
{
"COD_CLIENTE": "",
"RAGIONE_SOCIALE": "",
"COD_ARTICOLO": "",
"DESCRIZIONE": "",
"QUANTITA": "",
"DATA_CONSEGNA": ""
}
]
}
"""

# ============================================================

# PARSING JSON GEMINI

# ============================================================

def estrai_json(
testo
):

````
testo = testo.strip()

# Rimuove eventuali markdown

testo = re.sub(
    r"^```json\s*",
    "",
    testo,
    flags=re.IGNORECASE
)

testo = re.sub(
    r"\s*```$",
    "",
    testo
)

try:

    return json.loads(
        testo
    )

except Exception:

    inizio = testo.find(
        "{"
    )

    fine = testo.rfind(
        "}"
    )

    if (
        inizio >= 0
        and fine > inizio
    ):

        return json.loads(
            testo[
                inizio:fine + 1
            ]
        )

raise ValueError(
    "Gemini non ha restituito "
    "un JSON valido."
)
````

# ============================================================

# ANALISI PDF

# ============================================================

def analizza_pdf(
uploaded_file
):

```
if not client:

    raise RuntimeError(
        "GEMINI_API_KEY non configurata."
    )

file_bytes = uploaded_file.getvalue()

if not file_bytes:

    raise ValueError(
        "Il PDF è vuoto."
    )

# Upload tramite Files API
# Metodo ufficiale Gemini per i PDF.

file_gemini = client.files.upload(
    file=uploaded_file
)

response = client.models.generate_content(
    model=MODELLO_GEMINI,
    contents=[
        PROMPT_BASE,
        file_gemini
    ]
)

return estrai_json(
    response.text
)
```

# ============================================================

# ANALISI EMAIL

# ============================================================

def analizza_email(
testo_email
):

```
if not client:

    raise RuntimeError(
        "GEMINI_API_KEY non configurata."
    )

prompt = (
    PROMPT_BASE
    + "\n\nTESTO DELL'EMAIL:\n"
    + testo_email
)

response = client.models.generate_content(
    model=MODELLO_GEMINI,
    contents=prompt
)

return estrai_json(
    response.text
)
```

# ============================================================

# ELABORAZIONE RIGHE

# ============================================================

def elabora_righe(
risultato
):

```
righe = risultato.get(
    "righe",
    []
)

risultati = []

for indice, riga in enumerate(
    righe,
    start=1
):

    if not isinstance(
        riga,
        dict
    ):
        continue

    cliente = valida_cliente(
        riga.get(
            "RAGIONE_SOCIALE",
            ""
        ),
        riga.get(
            "COD_CLIENTE",
            ""
        )
    )

    articolo = valida_articolo(
        riga.get(
            "COD_ARTICOLO",
            ""
        ),
        riga.get(
            "DESCRIZIONE",
            ""
        )
    )

    stato_cliente = cliente[
        "stato"
    ]

    stato_articolo = articolo[
        "stato"
    ]

    if (
        stato_cliente == "OK"
        and stato_articolo == "OK"
    ):

        stato = "✅ OK"

    elif (
        stato_cliente == "NON TROVATO"
        or stato_articolo == "NON TROVATO"
    ):

        stato = "❌ DA VERIFICARE"

    else:

        stato = "⚠️ POSSIBILE CORRISPONDENZA"

    risultati.append(
        {
            "RIGA":
                indice,

            "COD_CLIENTE":
                cliente[
                    "codice_cliente"
                ],

            "RAGIONE_SOCIALE":
                cliente[
                    "ragione_sociale"
                ],

            "COD_ARTICOLO":
                articolo[
                    "codice"
                ],

            "DESCRIZIONE":
                articolo[
                    "descrizione"
                ],

            "QUANTITA":
                normalizza_quantita(
                    riga.get(
                        "QUANTITA",
                        ""
                    )
                ),

            "DATA_CONSEGNA":
                normalizza_data(
                    riga.get(
                        "DATA_CONSEGNA",
                        ""
                    )
                ),

            "STATO":
                stato,

            "_CANDIDATI_CLIENTE":
                cliente[
                    "candidati"
                ],

            "_CANDIDATI_ARTICOLO":
                articolo[
                    "candidati"
                ]
        }
    )

return risultati
```

# ============================================================

# SESSION STATE

# ============================================================

if "righe" not in st.session_state:
st.session_state.righe = []

if "dati_analisi" not in st.session_state:
st.session_state.dati_analisi = []

# ============================================================

# HEADER

# ============================================================

st.title(
"📦 Target ERP — Lettore Ordini"
)

st.caption(
"Importa un ordine PDF oppure incolla "
"il testo dell'email."
)

# ============================================================

# STATO SISTEMA

# ============================================================

with st.expander(
"ℹ️ Stato sistema",
expanded=False
):

```
c1, c2, c3 = st.columns(3)

with c1:

    st.metric(
        "Clienti",
        len(clienti)
    )

with c2:

    st.metric(
        "Articoli",
        len(articoli)
    )

with c3:

    if client:

        st.success(
            "Gemini configurato"
        )

    else:

        st.error(
            "Gemini non configurato"
        )

if df_clienti.empty:

    st.warning(
        "clienti.xlsx non trovato."
    )

else:

    st.caption(
        f"clienti.xlsx: "
        f"{len(df_clienti)} righe"
    )

if df_articoli.empty:

    st.warning(
        "articoli.xlsx non trovato."
    )

else:

    st.caption(
        f"articoli.xlsx: "
        f"{len(df_articoli)} righe"
    )
```

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
    "Carica ordine",
    type=[
        "pdf",
        "jpg",
        "jpeg",
        "png",
        "webp"
    ]
)

if uploaded_file:

    st.info(
        f"File selezionato: "
        f"**{uploaded_file.name}**"
    )

if uploaded_file and st.button(
    "⚡ Leggi ordine",
    type="primary",
    use_container_width=True
):

    if not client:

        st.error(
            "GEMINI_API_KEY non configurata. "
            "Controlla Streamlit → Settings → Secrets."
        )

    else:

        with st.spinner(
            "Sto leggendo l'ordine..."
        ):

            try:

                risultato = analizza_pdf(
                    uploaded_file
                )

                righe = elabora_righe(
                    risultato
                )

                st.session_state.righe = (
                    righe
                )

                st.session_state.dati_analisi = (
                    righe
                )

                st.success(
                    f"Lettura completata: "
                    f"{len(righe)} righe trovate."
                )

            except Exception as e:

                st.error(
                    f"Errore durante la lettura: {e}"
                )
```

# ============================================================

# EMAIL

# ============================================================

with tab_email:

```
testo_email = st.text_area(
    "Incolla qui l'email dell'ordine",
    height=250,
    placeholder=(
        "Incolla qui il testo ricevuto "
        "dal cliente..."
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

    elif not client:

        st.error(
            "GEMINI_API_KEY non configurata."
        )

    else:

        with st.spinner(
            "Sto analizzando l'ordine..."
        ):

            try:

                risultato = analizza_email(
                    testo_email
                )

                righe = elabora_righe(
                    risultato
                )

                st.session_state.righe = (
                    righe
                )

                st.session_state.dati_analisi = (
                    righe
                )

                st.success(
                    f"Lettura completata: "
                    f"{len(righe)} righe trovate."
                )

            except Exception as e:

                st.error(
                    f"Errore durante l'analisi: {e}"
                )
```

# ============================================================

# TABELLA RISULTATI

# ============================================================

st.divider()

st.subheader(
"📋 Risultato dell'ordine"
)

if not st.session_state.righe:

```
st.info(
    "Carica un ordine PDF oppure "
    "incolla un'email per iniziare."
)
```

else:

```
df_risultati = pd.DataFrame(
    st.session_state.righe
)

colonne_visibili = [
    "RIGA",
    "COD_CLIENTE",
    "RAGIONE_SOCIALE",
    "COD_ARTICOLO",
    "DESCRIZIONE",
    "QUANTITA",
    "DATA_CONSEGNA",
    "STATO"
]

df_visibile = df_risultati[
    colonne_visibili
].copy()

st.data_editor(
    df_visibile,
    use_container_width=True,
    hide_index=True,
    disabled=[
        "RIGA",
        "COD_CLIENTE",
        "RAGIONE_SOCIALE",
        "COD_ARTICOLO",
        "DESCRIZIONE",
        "QUANTITA",
        "DATA_CONSEGNA",
        "STATO"
    ]
)


# ========================================================
# VERIFICA RIGHE
# ========================================================

st.subheader(
    "🔎 Controllo corrispondenze"
)

for indice, riga in enumerate(
    st.session_state.righe
):

    stato = riga["STATO"]

    if stato == "✅ OK":
        continue

    with st.expander(
        f"{stato}  Riga {riga['RIGA']} — "
        f"{riga['COD_ARTICOLO'] or 'codice non riconosciuto'}"
    ):

        st.write(
            "**Informazioni estratte:**"
        )

        c1, c2 = st.columns(2)

        with c1:

            st.write(
                f"**Cliente:** "
                f"{riga['RAGIONE_SOCIALE'] or 'Non trovato'}"
            )

            st.write(
                f"**Codice cliente:** "
                f"{riga['COD_CLIENTE'] or 'Non trovato'}"
            )

        with c2:

            st.write(
                f"**Codice articolo:** "
                f"{riga['COD_ARTICOLO'] or 'Non trovato'}"
            )

            st.write(
                f"**Descrizione:** "
                f"{riga['DESCRIZIONE'] or 'Non trovata'}"
            )


        candidati_art = riga[
            "_CANDIDATI_ARTICOLO"
        ]

        candidati_cli = riga[
            "_CANDIDATI_CLIENTE"
        ]


        # ------------------------------------------------
        # CANDIDATI ARTICOLO
        # ------------------------------------------------

        if candidati_art:

            st.write(
                "**Possibili articoli:**"
            )

            dati_candidati = []

            for candidato in candidati_art:

                dati_candidati.append(
                    {
                        "Codice":
                            candidato[
                                "codice"
                            ],

                        "Descrizione":
                            candidato[
                                "descrizione"
                            ],

                        "Somiglianza":
                            f"{candidato['score'] * 100:.1f}%"
                    }
                )

            st.dataframe(
                pd.DataFrame(
                    dati_candidati
                ),
                use_container_width=True,
                hide_index=True
            )


        # ------------------------------------------------
        # CANDIDATI CLIENTE
        # ------------------------------------------------

        if candidati_cli:

            st.write(
                "**Possibili clienti:**"
            )

            dati_clienti = []

            for candidato in candidati_cli:

                dati_clienti.append(
                    {
                        "Ragione sociale":
                            candidato[
                                "valore"
                            ],

                        "Codice cliente":
                            candidato[
                                "codice"
                            ],

                        "Somiglianza":
                            f"{candidato['score'] * 100:.1f}%"
                    }
                )

            st.dataframe(
                pd.DataFrame(
                    dati_clienti
                ),
                use_container_width=True,
                hide_index=True
            )
```

# ============================================================

# ESPORTAZIONE

# ============================================================

if st.session_state.righe:

```
st.divider()

df_export = pd.DataFrame(
    st.session_state.righe
)

df_export = df_export[
    colonne_visibili
]

csv = df_export.to_csv(
    index=False,
    encoding="utf-8-sig"
).encode(
    "utf-8-sig"
)

st.download_button(
    "📥 Esporta ordine CSV",
    data=csv,
    file_name="ordine_letto.csv",
    mime="text/csv",
    type="primary"
)
