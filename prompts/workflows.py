from mcp.server.fastmcp import FastMCP


def register_workflow_prompts(mcp: FastMCP) -> None:
    @mcp.prompt(
        name="explorar_datos",
        title="Explorar datos abiertos",
        description="Guía para encontrar y previsualizar datasets del portal CKAN de Ecuador.",
    )
    def explorar_datos(tema: str = "salud") -> str:
        """Prompt para explorar datasets abiertos por tema."""
        return (
            f"Quiero explorar datos abiertos de Ecuador sobre '{tema}'.\n"
            "1) Usa search_ecuador o search_datasets con ese tema.\n"
            "2) Elige el dataset más relevante y llama get_dataset_info.\n"
            "3) Lista recursos con list_dataset_resources.\n"
            "4) Si hay CSV/JSON/XLSX, usa query_resource_data (DataStore) "
            "o preview_resource_data y resume hallazgos clave con cifras.\n"
            "Responde en español, cita IDs y URLs útiles."
        )

    @mcp.prompt(
        name="consultar_tramite",
        title="Consultar un trámite",
        description="Guía para requisitos, costo y pasos de un trámite en gob.ec.",
    )
    def consultar_tramite(tramite: str = "RUC") -> str:
        """Prompt para consultar trámites gubernamentales."""
        return (
            f"Necesito los requisitos para el trámite '{tramite}' en Ecuador.\n"
            "1) Usa search_tramites (con institution_id si lo conoces: "
            "SRI=8, Registro Civil=23, ANT=62, Cancillería=16, IESS=5).\n"
            "2) Toma el tramite_id más relevante y llama get_tramite_info.\n"
            "3) Resume requisitos, costo, tiempo, canales y regulaciones vinculadas.\n"
            "Responde en español, claro y accionable para un ciudadano."
        )

    @mcp.prompt(
        name="investigar_contrato",
        title="Investigar contrato público",
        description="Guía para buscar contrataciones SERCOP/OCDS por palabra clave.",
    )
    def investigar_contrato(tema: str = "medicinas", anio: str = "0") -> str:
        """Prompt para investigación de compras públicas."""
        year_hint = (
            f"Usa year={anio}."
            if anio and anio != "0"
            else "Si no hay resultados este año, deja year=0 para probar años previos."
        )
        return (
            f"Investiga contrataciones públicas de Ecuador sobre '{tema}'.\n"
            f"1) Usa search_contratos(query='{tema}'). {year_hint}\n"
            "2) Elige 1–3 OCIDs relevantes y llama get_contrato_info.\n"
            "3) Resume comprador, proveedor, montos, tipo de procedimiento y estado.\n"
            "Responde en español; si la API rate-limita (429), indícalo y reintenta."
        )

    @mcp.prompt(
        name="buscar_regulacion",
        title="Buscar regulación",
        description="Guía para encontrar normas y referencias de Registro Oficial.",
    )
    def buscar_regulacion(tema: str = "datos personales") -> str:
        """Prompt para buscar regulaciones en gob.ec."""
        return (
            f"Busca regulaciones ecuatorianas relacionadas con '{tema}'.\n"
            "1) Usa search_regulaciones con ese tema.\n"
            "2) Detalla 1–3 con get_regulacion_info (tipo, R.O., PDF).\n"
            "3) Si aplica a un trámite concreto, sugiere search_tramites / get_tramite_info.\n"
            "Responde en español con referencias claras al Registro Oficial."
        )

    @mcp.prompt(
        name="monitorear_riesgos",
        title="Monitorear riesgos / emergencias",
        description="Guía para consultar eventos SGR COE y estaciones SAT tsunami.",
    )
    def monitorear_riesgos(lugar: str = "Pichincha", evento: str = "") -> str:
        """Prompt para riesgos y emergencias."""
        evento_line = (
            f"Filtra evento='{evento}'."
            if evento
            else "Si aplica, filtra por evento (Deslizamiento, Inundación, Aluvión, etc.)."
        )
        return (
            f"Revisa eventos de riesgo en Ecuador para '{lugar}'.\n"
            "1) Usa lookup_ubicacion para confirmar provincia/cantón/parroquia.\n"
            f"2) Llama search_eventos_riesgo(provincia o canton='{lugar}', "
            f"estado='Seguimiento'). {evento_line}\n"
            "3) Resume eventos activos, impactos y descripción.\n"
            "4) Si el usuario pregunta por tsunami/SAT, usa list_sat_tsunami.\n"
            "5) Si pregunta por sismos/temblores recientes, usa search_sismos "
            f"(IG-EPN), p. ej. search_sismos(query='{lugar}', dias=7).\n"
            "Aclara que es información pública de apoyo, no un canal oficial de alerta."
        )
