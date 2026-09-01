import io
import json
import os
import pandas as pd
import streamlit as st
from google.genai import Client, types

# ==============================================================================
# 1. CONFIGURAZIONE PAGINA E STILE
# ==============================================================================
st.set_page_config(page_title="Target ERP - Smart Order & Quote Hub", layout="wide")

st.markdown(
    """
<style>
footer, #MainMenu, header, [data-testid="stHeader"], [data-testid="stToolbar"],
[data-testid="stStatusWidget"], [data-testid="stActionButtonIcon"],
div[class*="viewerBadge"], div[class*="styles_viewerBadge"], a[class*="viewerBadge"] {
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
# 2. INIZIALIZZAZIONE CLIENT GOOGLE GENAI (SICURA)
# ==============================================================================
@st.cache_resource
def get_client():
  api_key = None
  try:
    if "GOOGLE_API_KEY" in st.secrets:
      api_key = st.secrets["GOOGLE_API_KEY"]
  except Exception:
    pass

  if not api_key:
    api_key = os.environ.get("GOOGLE_API_KEY")

  if not api_key:
    st.error(
        "⚠️ **API Key mancante!** Assicurati di aver inserito `GOOGLE_API_KEY`"
        " nei Secrets di Streamlit o nelle variabili d'ambiente."
    )
    return None

  try:
    return Client(api_key=api_key)
  except Exception as e:
    st.error(f"Errore nella configurazione delle API Key: {e}")
    return None


client = get_client()


def genera_contenuto_con_fallback(contents, json_mode=False):
  if not client:
    raise Exception("Client API non disponibile.")

  config = {"response_mime_type": "application/json"} if json_mode else {}
  try:
    return client.models.generate_content(
        model="gemini-3.6-flash", contents=contents, config=config
    )
  except Exception as e:
    err_str = str(e)
    # Gestione automatica sia del sovraccarico (503 / UNAVAILABLE) che del limite di richieste (429)
    if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str or "503" in err_str or "UNAVAILABLE" in err_str:
      return client.models.generate_content(
          model="gemini-3.6-flash", contents=contents, config=config
      )
    else:
      raise e


# ==============================================================================
# 3. BARRA LATERALE: GESTIONE LISTINI E GOOGLE DRIVE
# ==============================================================================
st.sidebar.title("📁 Gestione Listini")
folder_id_input = st.sidebar.text_input(
    "ID Cartella Google Drive",
    value="1Eq1Et_riXqsoU0JNzdXhQlSXGYF4D0LG",
    help="ID della cartella Google Drive con i cataloghi",
)

st.sidebar.info(
    "💡 *Nota:* Puoi usare la cartella Drive collegata o caricare i cataloghi"
    " pesanti direttamente qui sotto per Victoria."
)

uploaded_files = st.sidebar.file_uploader(
    "Carica listini per Victoria",
    type=["pdf", "xlsx", "csv"],
    accept_multiple_files=True,
)

if uploaded_files:
  st.sidebar.success(f"Caricati {len(uploaded_files)} file con successo!")
  st.session_state["listini_caricati"] = uploaded_files
else:
  if "listini_caricati" not in st.session_state:
    st.session_state["listini_caricati"] = []

# ==============================================================================
# 4. CARICAMENTO ANAGRAFICHE EXCEL LOCALI
# ==============================================================================
@st.cache_data
def carica_anagrafica(nome_file):
  try:
    df = pd.read_excel(nome_file)
    df.columns = df.columns.astype(str).str.strip()
    return df
  except Exception:
    return pd.DataFrame()


df_clienti = carica_anagrafica("clienti.xlsx")
df_articoli = carica_anagrafica("articoli.xlsx")

col_rag_trovata = None
col_cod_cli_trovato = None
lista_opzioni_clienti = []

if not df_clienti.empty:
  for col in df_clienti.columns:
    c_upper = col.upper().strip()
    if c_upper in ["RAGIONE_SOCIALE", "RAGIONE SOCIALE", "CLIENTE", "NOME"]:
      col_rag_trovata = col
    elif c_upper in ["COD_CLIENTE", "CODICE", "CODICE CLIENTE"]:
      col_cod_cli_trovato = col
  if col_rag_trovata:
    lista_opzioni_clienti = [
        str(x).strip()
        for x in df_clienti[col_rag_trovata].dropna().unique()
        if str(x).strip()
    ]

col_art_trovata = "Codart" if "Codart" in df_articoli.columns else None
col_desc_trovata = (
    "Descrizione articolo" if "Descrizione articolo" in df_articoli.columns else None
)

if not col_art_trovata and not df_articoli.empty:
  for col in df_articoli.columns:
    if col.lower().strip() in ["codart", "cod_articolo", "codice"]:
      col_art_trovata = col
      break

if not col_desc_trovata and not df_articoli.empty:
  for col in df_articoli.columns:
    if "descrizione" in col.lower():
      col_desc_trovata = col
      break

lista_opzioni_articoli = (
    [
        str(x).strip()
        for x in df_articoli[col_art_trovata].dropna().unique()
        if str(x).strip()
    ]
    if col_art_trovata
    else []
)
lista_opzioni_descrizioni = (
    [
        str(x).strip()
        for x in df_articoli[col_desc_trovata].dropna().unique()
        if str(x).strip()
    ]
    if col_desc_trovata
    else []
)

elenco_ragioni_sociali = json.dumps(lista_opzioni_clienti, ensure_ascii=False)
elenco_codici_articoli = json.dumps(lista_opzioni_articoli, ensure_ascii=False)


def trova_ragione_sociale_valida(testo_estratto):
  if not testo_estratto or testo_estratto in ["N/D", ""]:
    return ""
  if testo_estratto in lista_opzioni_clienti:
    return testo_estratto

  def pulisci(s):
    return re.sub(r"[^a-zA-Z0-9]", "", str(s)).upper()

  testo_clean = pulisci(testo_estratto)
  for opt in lista_opzioni_clienti:
    opt_clean = pulisci(opt)
    if testo_clean and (
        testo_clean in opt_clean or opt_clean in testo_clean
    ):
      return opt
  return ""


# ==============================================================================
# 5. LAYOUT PRINCIPALE & CHAT VICTORIA
# ==============================================================================
col_titolo, col_chat = st.columns([3, 1])

with col_titolo:
  st.title("📦 Target ERP — Smart Order & Quote Hub")

with col_chat:
  with st.popover("💬 Chat con Victoria", use_container_width=True):
    st.subheader("🤖 Victoria — Target ERP")
    st.caption("Chiedi informazioni sui prodotti.")

    chat_container = st.container(height=250)

    if "messages" not in st.session_state:
      st.session_state.messages = []

    with chat_container:
      for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
          st.markdown(msg["content"])

    if prompt := st.chat_input("Chiedi info sui prodotti..."):
      st.session_state.messages.append({"role": "user", "content": prompt})

      with chat_container:
        with st.chat_message("user"):
          st.markdown(prompt)

        with st.chat_message("assistant"):
          with st.spinner("Victoria sta elaborando la risposta..."):
            system_instruction = (
                "Sei Victoria, l'assistente virtuale ufficiale del software"
                " Target ERP. Rispondi in modo professionale, chiaro e"
                " sintetico. Se ti chiedono chi ti ha creata o sviluppata,"
                " rispondi che sei stata creata da Andrea Uzzardi. Non"
                " menzionare mai Google, Gemini o di essere un'IA generica."
            )

            contenuto_messaggio = []

            if (
                "listini_caricati" in st.session_state
                and st.session_state["listini_caricati"]
            ):
              for file_caricato in st.session_state["listini_caricati"]:
                try:
                  file_caricato.seek(0)
                  file_bytes = file_caricato.read()
                  mime = (
                      "application/pdf"
                      if file_caricato.name.endswith(".pdf")
                      else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                  )
                  file_obj = client.files.upload(
                      file=io.BytesIO(file_bytes),
                      config={
                          "display_name": file_caricato.name,
                          "mime_type": mime,
                      },
                  )
                  contenuto_messaggio.append(file_obj)
                except Exception as e:
                  pass

            contenuto_messaggio.append(prompt)

            try:
              chat = client.chats.create(
                  model="gemini-3.6-flash",
                  config={"system_instruction": system_instruction},
              )
              response = chat.send_message(contenuto_messaggio)
              risposta = response.text
            except Exception as e:
              err_str = str(e)
              if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str or "503" in err_str or "UNAVAILABLE" in err_str:
                try:
                  chat_fallback = client.chats.create(
                      model="gemini-3.6-flash",
                      config={"system_instruction": system_instruction},
                  )
                  response = chat_fallback.send_message(contenuto_messaggio)
                  risposta = response.text
                except Exception as err_fallback:
                  risposta = (
                      "I server sono temporaneamente sovraccarichi (503). "
                      "Riprova tra qualche istante."
                  )
              else:
                risposta = f"Si è verificato un errore: {e}"

            st.markdown(risposta)

      st.session_state.messages.append(
          {"role": "assistant", "content": risposta}
      )

# ==============================================================================
# 6. SELEZIONE DOCUMENTO & INPUT (FILE / EMAIL)
# ==============================================================================
doc_type = st.radio(
    "Seleziona il tipo di documento:",
    ["🛒 Ordine Cliente", "📋 Offerta"],
    horizontal=True,
)

tab_upload, tab_text = st.tabs(["📄 Carica PDF / Immagine", "✉️ Incolla Testo Email"])

prompt_base_estrazione = f"""
Analizza la richiesta per un documento di tipo: {doc_type}.

ELENCO RAGIONI SOCIALI CLIENTE VALIDE:
{elenco_ragioni_sociali}

ELENCO CODICI ARTICOLI VALIDI (Codart):
{elenco_codici_articoli}

ISTRUZIONI PER L'ESTRAZIONE:
1. Trova l'intestazione o il nome del cliente nel documento.
2. Confronta il nome trovato con l'ELENCO RAGIONI SOCIALI CLIENTE VALIDE e seleziona il valore ESATTO corrispondente. Se non lo trovi, restituisci "".
3. Per ogni riga articolo trovata, assegna il COD_ARTICOLO ESATTO dal campo Codart dell'elenco articoli.
4. Estrai la DESCRIZIONE dell'articolo, la QUANTITA (numero intero) e la DATA_CONSEGNA.

Restituisci ESCLUSIVAMENTE un JSON (lista di oggetti) con le chiavi:
"COD_CLIENTE", "RAGIONE_SOCIALE", "COD_ARTICOLO", "DESCRIZIONE", "QUANTITA", "DATA_CONSEGNA".
Per RAGIONE_SOCIALE se non la trovi usa "". Per gli altri campi non trovati usa "N/D".
"""

with tab_upload:
  uploaded_files = st.file_uploader(
      "Trascina file (PDF o Immagine)",
      type=["pdf", "jpg", "png", "jpeg"],
      accept_multiple_files=True,  # <--- ABILITA IL CARICAMENTO MULTIPLO
      label_visibility="collapsed",
  )
  if uploaded_files and st.button(
      "⚡ Analizza File ed Inserisci in Tabella", type="primary"
  ):
    with st.spinner("Lettura ed estrazione dati dai file in corso..."):
      try:
        if "dati" not in st.session_state:
          st.session_state.dati = []

        totale_aggiunti = 0
        for uploaded_file in uploaded_files:
          file_bytes = uploaded_file.read()
          mime_type = uploaded_file.type

          res = genera_contenuto_con_fallback(
              [
                  types.Part.from_bytes(data=file_bytes, mime_type=mime_type),
                  prompt_base_estrazione,
              ],
              json_mode=True,
          )

          nuovi_dati = json.loads(res.text)
          for riga in nuovi_dati:
            riga["RAGIONE_SOCIALE"] = trova_ragione_sociale_valida(
                riga.get("RAGIONE_SOCIALE", "")
            )

          st.session_state.dati.extend(nuovi_dati)
          totale_aggiunti += len(nuovi_dati)

        st.success(
            f"Elaborati {len(uploaded_files)} file! Aggiunte {totale_aggiunti}"
            " righe alla tabella."
        )
        st.rerun()

      except Exception as e:
        st.error(f"Errore durante l'analisi dei file: {e}")
# ==============================================================================
# 7. TABELLA PRINCIPALE DI GESTIONE
# ==============================================================================
st.subheader("Gestione Ordini e Articoli")

if "dati" not in st.session_state:
  st.session_state.dati = []

colonne_tabella = [
    "COD_CLIENTE",
    "RAGIONE_SOCIALE",
    "COD_ARTICOLO",
    "DESCRIZIONE",
    "QUANTITA",
    "DATA_CONSEGNA",
]

if st.session_state.dati:
  df = pd.DataFrame(st.session_state.dati)
  for col in colonne_tabella:
    if col not in df.columns:
      df[col] = ""
else:
  df = pd.DataFrame(columns=colonne_tabella)

if not df.empty:
  if not df_clienti.empty and col_rag_trovata and col_cod_cli_trovato:
    df_c = df_clienti.copy()
    df_c[col_rag_trovata] = df_c[col_rag_trovata].astype(str).str.strip()
    df_c[col_cod_cli_trovato] = df_c[col_cod_cli_trovato].astype(str).str.strip()
    mappa_cli = dict(zip(df_c[col_rag_trovata], df_c[col_cod_cli_trovato]))
    df["COD_CLIENTE"] = (
        df["RAGIONE_SOCIALE"]
        .astype(str)
        .str.strip()
        .map(mappa_cli)
        .fillna(df["COD_CLIENTE"])
    )

  if not df_articoli.empty and col_art_trovata and col_desc_trovata:
    df_a = df_articoli.copy()
    df_a[col_art_trovata] = df_a[col_art_trovata].astype(str).str.strip()
    df_a[col_desc_trovata] = df_a[col_desc_trovata].astype(str).str.strip()
    mappa_art_desc = dict(zip(df_a[col_art_trovata], df_a[col_desc_trovata]))
    desc_mappata = (
        df["COD_ARTICOLO"].astype(str).str.strip().map(mappa_art_desc)
    )
    df["DESCRIZIONE"] = (
        df["DESCRIZIONE"]
        .replace(["N/D", "", None], pd.NA)
        .fillna(desc_mappata)
        .fillna("N/D")
    )

column_config = {}
if lista_opzioni_clienti:
  column_config["RAGIONE_SOCIALE"] = st.column_config.SelectboxColumn(
      "RAGIONE_SOCIALE", options=lista_opzioni_clienti, required=False
  )
if lista_opzioni_articoli:
  column_config["COD_ARTICOLO"] = st.column_config.SelectboxColumn(
      "COD_ARTICOLO (Codart)", options=lista_opzioni_articoli, required=False
  )
if lista_opzioni_descrizioni:
  column_config["DESCRIZIONE"] = st.column_config.SelectboxColumn(
      "DESCRIZIONE", options=lista_opzioni_descrizioni, required=False
  )

edited_df = st.data_editor(
    df,
    column_config=column_config,
    use_container_width=True,
    num_rows="dynamic",
    key="editor_tabella",
)

richiede_aggiornamento = False
if (
    not edited_df.empty
    and not df_articoli.empty
    and col_art_trovata
    and col_desc_trovata
):
  df_a = df_articoli.copy()
  df_a[col_art_trovata] = df_a[col_art_trovata].astype(str).str.strip()
  df_a[col_desc_trovata] = df_a[col_desc_trovata].astype(str).str.strip()

  mappa_cod_to_desc = dict(zip(df_a[col_art_trovata], df_a[col_desc_trovata]))
  mappa_desc_to_cod = dict(zip(df_a[col_desc_trovata], df_a[col_art_trovata]))

  if not df_clienti.empty and col_rag_trovata and col_cod_cli_trovato:
    df_c = df_clienti.copy()
    df_c[col_rag_trovata] = df_c[col_rag_trovata].astype(str).str.strip()
    df_c[col_cod_cli_trovato] = df_c[col_cod_cli_trovato].astype(str).str.strip()
    mappa_cli = dict(zip(df_c[col_rag_trovata], df_c[col_cod_cli_trovato]))
    nuovi_codici_cli = (
        edited_df["RAGIONE_SOCIALE"].astype(str).str.strip().map(mappa_cli)
    )
    if "COD_CLIENTE" in edited_df.columns and not edited_df[
        "COD_CLIENTE"
    ].equals(nuovi_codici_cli.fillna(edited_df["COD_CLIENTE"])):
      edited_df["COD_CLIENTE"] = nuovi_codici_cli.fillna(
          edited_df["COD_CLIENTE"]
      )
      richiede_aggiornamento = True

  nuove_desc = (
      edited_df["COD_ARTICOLO"].astype(str).str.strip().map(mappa_cod_to_desc)
  )
  cond_cod_changed = (~nuove_desc.isna()) & (
      edited_df["DESCRIZIONE"] != nuove_desc
  )
  if cond_cod_changed.any():
    edited_df.loc[cond_cod_changed, "DESCRIZIONE"] = nuove_desc[
        cond_cod_changed
    ]
    richiede_aggiornamento = True

  nuovi_codici_art = (
      edited_df["DESCRIZIONE"].astype(str).str.strip().map(mappa_desc_to_cod)
  )
  cond_desc_changed = (~nuovi_codici_art.isna()) & (
      edited_df["COD_ARTICOLO"] != nuovi_codici_art
  )
  if cond_desc_changed.any():
    edited_df.loc[cond_desc_changed, "COD_ARTICOLO"] = nuovi_codici_art[
        cond_desc_changed
    ]
    richiede_aggiornamento = True

st.session_state.dati = edited_df.to_dict(orient="records")

if richiede_aggiornamento:
  st.rerun()

csv_data = edited_df.to_csv(index=False).encode("utf-8")
st.download_button(
    label="📥 Esporta CSV Tabella",
    data=csv_data,
    file_name="gestione_ordini.csv",
    mime="text/csv",
)