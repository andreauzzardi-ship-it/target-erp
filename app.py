import json
import re
import pandas as pd
import streamlit as st
from google.genai import Client, types

# --- 1. CONFIGURAZIONE PAGINA E CSS ---
st.set_page_config(page_title="Target ERP - Smart Order & Quote Hub", layout="wide")

st.markdown("""
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
""", unsafe_allow_html=True)

# --- 2. INIZIALIZZAZIONE CLIENT GOOGLE GENAI ---
@st.cache_resource
def get_client():
    try:
        return Client(api_key=st.secrets["GOOGLE_API_KEY"])
    except Exception as e:
        st.error(f"Errore nella configurazione delle API Key: {e}")
        return None

client = get_client()

# --- 3. CARICAMENTO ANAGRAFICHE EXCEL ---
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

# Identificazione colonne CLIENTE
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
        lista_opzioni_clienti = [str(x).strip() for x in df_clienti[col_rag_trovata].dropna().unique() if str(x).strip()]

# Identificazione colonne ARTICOLI
col_art_trovata = "Codart" if "Codart" in df_articoli.columns else None
col_desc_trovata = "Descrizione articolo" if "Descrizione articolo" in df_articoli.columns else None

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

lista_opzioni_articoli = []
lista_opzioni_descrizioni = []

if col_art_trovata:
    lista_opzioni_articoli = [str(x).strip() for x in df_articoli[col_art_trovata].dropna().unique() if str(x).strip()]

if col_desc_trovata:
    lista_opzioni_descrizioni = [str(x).strip() for x in df_articoli[col_desc_trovata].dropna().unique() if str(x).strip()]

elenco_ragioni_sociali = json.dumps(lista_opzioni_clienti, ensure_ascii=False)
elenco_codici_articoli = json.dumps(lista_opzioni_articoli, ensure_ascii=False)

def trova_ragione_sociale_valida(testo_estratto):
    if not testo_estratto or testo_estratto in ["N/D", ""]:
        return ""
    if testo_estratto in lista_opzioni_clienti:
        return testo_estratto
    
    def pulisci(s):
        return re.sub(r'[^a-zA-Z0-9]', '', str(s)).upper()

    testo_clean = pulisci(testo_estratto)
    for opt in lista_opzioni_clienti:
        opt_clean = pulisci(opt)
        if testo_clean and (testo_clean in opt_clean or opt_clean in testo_clean):
            return opt
    return ""

# --- 4. INTESTAZIONE E TIPO DOCUMENTO ---
st.title("📦 Target ERP — Smart Order & Quote Hub")

st.write("Seleziona il tipo di documento:")
doc_type = st.radio(
    "Seleziona il tipo di documento:", 
    ["🛒 Ordine Cliente", "📋 Offerta"], 
    horizontal=True, 
    label_visibility="collapsed"
)

st.divider()

# --- 5. GESTIONE TABELLA PRINCIPALE ---
st.subheader("Gestione Ordini e Articoli")

if "dati" not in st.session_state:
    st.session_state.dati = []

colonne_tabella = ["COD_CLIENTE", "RAGIONE_SOCIALE", "COD_ARTICOLO", "DESCRIZIONE", "QUANTITA", "DATA_CONSEGNA"]

if st.session_state.dati:
    df = pd.DataFrame(st.session_state.dati)
    for col in colonne_tabella:
        if col not in df.columns:
            df[col] = ""
else:
    df = pd.DataFrame(columns=colonne_tabella)

# Sincronizzazione automatica iniziale con i dati Excel
if not df.empty:
    if not df_clienti.empty and col_rag_trovata and col_cod_cli_trovato:
        df_c = df_clienti.copy()
        df_c[col_rag_trovata] = df_c[col_rag_trovata].astype(str).str.strip()
        df_c[col_cod_cli_trovato] = df_c[col_cod_cli_trovato].astype(str).str.strip()
        mappa_cli = dict(zip(df_c[col_rag_trovata], df_c[col_cod_cli_trovato]))
        df["COD_CLIENTE"] = df["RAGIONE_SOCIALE"].astype(str).str.strip().map(mappa_cli).fillna(df["COD_CLIENTE"])

    if not df_articoli.empty and col_art_trovata and col_desc_trovata:
        df_a = df_articoli.copy()
        df_a[col_art_trovata] = df_a[col_art_trovata].astype(str).str.strip()
        df_a[col_desc_trovata] = df_a[col_desc_trovata].astype(str).str.strip()
        mappa_art_desc = dict(zip(df_a[col_art_trovata], df_a[col_desc_trovata]))
        
        desc_mappata = df["COD_ARTICOLO"].astype(str).str.strip().map(mappa_art_desc)
        df["DESCRIZIONE"] = df["DESCRIZIONE"].replace(["N/D", "", None], pd.NA).fillna(desc_mappata).fillna("N/D")

column_config = {}
if lista_opzioni_clienti:
    column_config["RAGIONE_SOCIALE"] = st.column_config.SelectboxColumn("RAGIONE_SOCIALE", options=lista_opzioni_clienti, required=False)
if lista_opzioni_articoli:
    column_config["COD_ARTICOLO"] = st.column_config.SelectboxColumn("COD_ARTICOLO (Codart)", options=lista_opzioni_articoli, required=False)
if lista_opzioni_descrizioni:
    column_config["DESCRIZIONE"] = st.column_config.SelectboxColumn("DESCRIZIONE", options=lista_opzioni_descrizioni, required=False)

edited_df = st.data_editor(
    df, 
    column_config=column_config,
    use_container_width=True, 
    num_rows="dynamic",
    key="editor_tabella"
)

# Sincronizzazione dinamica nella tabella
richiede_aggiornamento = False
if not edited_df.empty and not df_articoli.empty and col_art_trovata and col_desc_trovata:
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
        
        nuovi_codici_cli = edited_df["RAGIONE_SOCIALE"].astype(str).str.strip().map(mappa_cli)
        if "COD_CLIENTE" in edited_df.columns and not edited_df["COD_CLIENTE"].equals(nuovi_codici_cli.fillna(edited_df["COD_CLIENTE"])):
            edited_df["COD_CLIENTE"] = nuovi_codici_cli.fillna(edited_df["COD_CLIENTE"])
            richiede_aggiornamento = True

    nuove_desc = edited_df["COD_ARTICOLO"].astype(str).str.strip().map(mappa_cod_to_desc)
    cond_cod_changed = (~nuove_desc.isna()) & (edited_df["DESCRIZIONE"] != nuove_desc)
    if cond_cod_changed.any():
        edited_df.loc[cond_cod_changed, "DESCRIZIONE"] = nuove_desc[cond_cod_changed]
        richiede_aggiornamento = True

    nuovi_codici_art = edited_df["DESCRIZIONE"].astype(str).str.strip().map(mappa_desc_to_cod)
    cond_desc_changed = (~nuovi_codici_art.isna()) & (edited_df["COD_ARTICOLO"] != nuovi_codici_art)
    if cond_desc_changed.any():
        edited_df.loc[cond_desc_changed, "COD_ARTICOLO"] = nuovi_codici_art[cond_desc_changed]
        richiede_aggiornamento = True

st.session_state.dati = edited_df.to_dict(orient="records")

if richiede_aggiornamento:
    st.rerun()

# Pulsante Download CSV
csv_data = edited_df.to_csv(index=False).encode('utf-8')
st.download_button(
    label="📥 Esporta CSV Tabella",
    data=csv_data,
    file_name="gestione_ordini.csv",
    mime="text/csv"
)