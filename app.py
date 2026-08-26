# Funzione per cercare articoli simili usando Gemini (Ricerca Semantica / Intelligente)
def cerca_articoli_simili(query, max_risultati=10):
    if df_articoli.empty or not col_desc_trovata or not col_art_trovata:
        return []
    
    # Estraiamo l'elenco dei prodotti dall'Excel (Codice e Descrizione)
    catalogo_ridotto = []
    for _, row in df_articoli.iterrows():
        cod = str(row[col_art_trovata]).strip()
        desc = str(row[col_desc_trovata]).strip()
        if desc and desc != "nan":
            catalogo_ridotto.append({"codice": cod, "descrizione": desc})
    
    if not catalogo_ridotto:
        return []

    prompt_ricerca = f"""
    L'utente sta cercando informazioni o prodotti correlati a: "{query}".
    
    Analizza il seguente catalogo prodotti e individua i {max_risultati} articoli più pertinenti, 
    tenendo conto di abbreviazioni (es. "cott" per "cottura", "induz" per "induzione", "piano" per "piano cottura"), 
    sinonimi, misure, varianti o abbinamenti logici.

    CATALOGO PRODOTTI:
    {json.dumps(catalogo_ridotto[:1500], ensure_ascii=False)}

    Restituisci ESCLUSIVAMENTE un array JSON con gli oggetti trovati, mantenendo i campi "codice" e "descrizione".
    Esempio output:
    [
        {{"codice": "123", "descrizione": "PIANO COTT A INDUZ 60CM"}},
        ...
    ]
    """

    try:
        # Usa il generatore con fallback automatico
        res = genera_contenuto_con_fallback(prompt_ricerca, json_mode=True)
        risultati = json.loads(res.text)
        return risultati
    except Exception as e:
        # Fallback manuale tollerante a parole chiave in caso di errore API
        parole = [p.lower() for p in re.findall(r'\w+', query) if len(p) > 2]
        risultati_fallback = []
        for item in catalogo_ridotto:
            desc_lower = item["descrizione"].lower()
            cod_lower = item["codice"].lower()
            if any(p[:4] in desc_lower or p[:4] in cod_lower for p in parole):
                risultati_fallback.append(item)
                if len(risultati_fallback) >= max_risultati:
                    break
        return risultati_fallback