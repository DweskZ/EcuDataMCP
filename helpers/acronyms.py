import re

# Common Ecuadorian survey/institution acronyms users type, spelled out the
# way CKAN's own metadata titles/descriptions actually spell them (verified
# against INEC/institution naming, not guessed). CKAN's search underperforms
# on a bare acronym because the catalog text rarely contains the acronym
# itself, only the full name.
_ACRONYM_EXPANSIONS: dict[str, str] = {
    "enemdu": "encuesta nacional de empleo desempleo y subempleo",
    "ensanut": "encuesta nacional de salud y nutricion",
    "enighur": "encuesta nacional de ingresos y gastos de los hogares urbanos y rurales",
    "ecv": "encuesta de condiciones de vida",
    "ruc": "registro unico de contribuyentes",
    "iess": "instituto ecuatoriano de seguridad social",
    "sri": "servicio de rentas internas",
    "inec": "instituto nacional de estadistica y censos",
    "bce": "banco central del ecuador",
    "sercop": "servicio nacional de contratacion publica",
    "senescyt": "secretaria de educacion superior ciencia tecnologia e innovacion",
    "supercias": "superintendencia de companias valores y seguros",
    "sgr": "servicio nacional de gestion de riesgos y emergencias",
}

_WORD_RE = re.compile(r"\w+", re.UNICODE)


def expand_acronyms(query: str) -> str:
    """Append full-term expansions for known Ecuadorian acronyms in `query`.

    CKAN's default Solr query operator is OR across terms, so appending
    expansion words broadens recall without narrowing the original match —
    a document matching only the acronym, only the full name, or both, all
    still come back.
    """
    query_lower = query.lower()
    words = _WORD_RE.findall(query_lower)
    expansions = [
        _ACRONYM_EXPANSIONS[w]
        for w in dict.fromkeys(words)  # dedupe, preserve order
        if w in _ACRONYM_EXPANSIONS and _ACRONYM_EXPANSIONS[w] not in query_lower
    ]
    if not expansions:
        return query
    return f"{query} {' '.join(expansions)}"
