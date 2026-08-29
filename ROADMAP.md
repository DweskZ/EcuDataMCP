# Roadmap

Pendientes definidos para `EcuDataMCP`, reconstruidos de sesiones previas de
diseño e instalación (no existía este archivo hasta ahora).

Leyenda de estado: **[ ]** sin empezar · **[~]** parcial · **[x]** hecho

---

## Nuevas conexiones de datos

- [x] **Página de datasets del SRI** (`https://www.sri.gob.ec/datasets`) —
      hecho: tool `search_sri_datasets` + `helpers/sri_client.py`. Verificado
      en vivo (2026-08-16, con acceso real al portal): 130 enlaces directos
      (71 CSV, 46 ZIP, 13 XLSX — el desglose por formato cambió un poco vs.
      la cifra original de este ítem, pero el total ronda igual ~130; el
      portal se actualiza con nuevos años). La página es un CMS Liferay sin
      API — cada archivo vive en un `<p>` con una etiqueta corta junto al
      link de descarga; **ojo:** el agrupamiento por sección
      (`data-analytics-asset-title`) no es confiable — la sección de
      Recaudación real está mal titulada "Prueba" en el HTML — así que el
      parser indexa cada archivo por su propia etiqueta/URL en vez de
      confiar en el título de la sección que lo contiene. Caché de 6h.
- [x] **Banco Central del Ecuador (BCE)** — hecho: tools
      `search_indicadores_bce`/`get_indicador_bce` + `helpers/bce_client.py`
      sobre la API pública sin autenticación de BCEData
      (`contenido.bce.fin.ec/wp-json/bcedata/v1/`), no documentada
      oficialmente pero confirmada con `curl` plano.
- [x] **Superintendencia de Compañías (Supercías)** — hecho: directorio de
      compañías (`search_companias`/`get_compania_info`, 226k+ compañías,
      actualizado a diario, parseado desde el export Excel estático del
      portal), ranking financiero (`search_ranking`/`get_financials`, ~38
      ratios financieros por compañía y año fiscal, sobre un SQLite local
      construido de antemano con `scripts/build_supercias_financials_db.py`)
      y registro de auditores externos
      (`search_auditores`/`get_auditor_info`).
- [x] **Instituto Geofísico (IG-EPN)** — hecho: tool `search_sismos` sobre el
      catálogo sísmico público, con caché TTL y parseo tolerante del CSV.
- [ ] **Ecuador en Cifras / portal BI del INEC** — **corrección 2026-08-28:
      la conclusión anterior de este mismo día ("callejón sin salida") era
      falsa.** El primer pase entró por `ecuadorencifras.gob.ec/institucional/home/`
      (un subsitio institucional viejo con navegación de ~2017) y por
      `inec.gob.ec` sin `www` (dominio distinto, nunca fue el sitio real) —
      ninguno de los dos es el portal real, y de ahí salió la conclusión
      errónea de que el dominio estaba abandonado. **Re-investigado con
      más cuidado:** `www.ecuadorencifras.gob.ec` es el sitio oficial del
      INEC, activo y publicando en 2026 (confirmado con búsqueda web y en
      vivo — última publicación al momento de revisar: "IPCO - julio
      2026", 21/08/2026). La página `/estadisticas/` es un catálogo
      enorme y genuinamente vivo: decenas de temas (IPC, ENEMDU, ENSANUT,
      pobreza, comercio exterior, cuentas nacionales, construcción,
      REBPE...), cada uno con su propia página. Por ejemplo, la del IPC
      (`/indice-de-precios-al-consumidor-ipc/`) linkea, para julio 2026,
      boletín técnico en PDF, presentación de resultados en PDF,
      metodología en PDF, y series históricas completas en Excel y CSV
      (`Tabulados_y_series_historicas_CSV.zip`) — **todos son links HTML
      planos, sin JS de por medio**, confirmado bajando el PDF y el ZIP
      directo con `httpx` sin browser. Esto es exactamente el tipo de
      fuente pública, estructurada y automatizable que motivó este ítem
      originalmente — candidato fuerte para una integración real (`helpers/inec_client.py`
      + tools de búsqueda/descarga), simplemente no se construyó nada
      todavía porque el alcance (decenas de categorías × años de
      histórico) es más grande que una sesión de investigación. Reabierto
      como pendiente, ya no cerrado.
- [ ] **LOTAIP como fuente transversal** — **candidato nuevo, 2026-08-28,**
      encontrado investigando IESS (ver nota de Transparencia más abajo).
      Ley Orgánica de Transparencia y Acceso a la Información Pública:
      obligatoria para toda institución pública ecuatoriana, cada una
      publica su propio portal LOTAIP (resoluciones, contratación,
      balances, exámenes de Contraloría...). Si la estructura resulta
      suficientemente uniforme entre instituciones, podría ser una fuente
      transversal reutilizable en vez de una integración por institución.
      Sin investigar más allá de confirmar que existe en IESS — falta
      revisar si el formato/URL se repite en otras instituciones antes de
      decidir si vale la pena.
- [x] **IESS (Instituto Ecuatoriano de Seguridad Social)** — **agregado
      2026-08-16, pedido por Daniel: tienen boletines/reportes en PDF en su
      propio portal.** Ya reachable hoy vía CKAN genérico
      (`organization="instituto-ecuatoriano-de-seguridad-social"`) — 3
      datasets: afiliados activos del Seguro General Obligatorio y Régimen
      Especial Voluntario, pagos y beneficiarios del Seguro de Desempleo
      (verificado en la sección de verificación e2e de abajo), encuesta
      familiar del Seguro Social Campesino. **PDFs confirmados 2026-08-28:**
      una revisión anterior con HTTP plano no encontró links `.pdf` porque
      el navegador real primero renderiza JS; con el browser real se
      encontró la sección "Boletines Estadísticos"
      (`iess.gob.ec/es/estadisticas`), con boletines anuales desde 2006
      hasta 2024 (el más reciente: 142 páginas, 4.16 MB). Cada entrada es
      una vista Liferay `document_library_display` (HTML, no el PDF en sí);
      el PDF real vive en `iess.gob.ec/documents/10162/<id>/<nombre>.pdf`,
      extraído del `href` en esa página. `read_pdf` (ver más abajo) lo lee
      correctamente — 40 caracteres de texto en la portada, confirmado en
      vivo.

      **Investigación más a fondo del portal, 2026-08-28** (pedido
      explícito de Daniel: "investigar boletines del IESS y otro material
      más allá de los portales que tenemos"):
      - **Estudios Actuariales** (`iess.gob.ec/estudios-actuariales/`) —
        mismo patrón Liferay que los boletines (vista `guest/estudios-
        actuariales-{año}`, PDF real en `iess.gob.ec/documents/10162/...`).
        Confirmados sets completos para 2010, 2013, 2018 y 2020 — el de
        2020 solo trae 14 PDFs reales (valuación actuarial y su
        aprobación por fondo: IVM, Salud, Riesgos del Trabajo, Seguro
        Social Campesino, Cesantía, Desempleo, más tablas de mortalidad).
        **Bug real encontrado y corregido en el mismo pase:** el PDF de
        valuación del fondo IVM pesa 14.6 MB, casi 3× el tope de 5 MB de
        `read_pdf` — la descarga truncada producía un mensaje engañoso
        ("está corrupto") en vez de explicar que se cortó a la mitad.
        Corregido: `read_pdf` ahora detecta la descarga truncada *antes*
        de intentar parsear (mismo patrón que `.zip`/`.tar.gz` truncados)
        y da un mensaje accionable. El resto de PDFs del set 2020 (0.29–1.7
        MB) están dentro del tope y se leen bien — verificado en vivo.
      - **Informes de Auditoría** (`iess.gob.ec/es/informes-de-auditoria`)
        — archivo real y grande: carpetas por año 2007–2025, entre 1 y 42
        documentos por año (~344 documentos en total). El listado de
        carpetas, el listado de documentos dentro de cada carpeta, **y la
        página de detalle de cada documento son HTML servido por el
        servidor** — confirmado con `httpx` plano, sin browser, en los
        tres niveles. **Corrección 2026-08-28 (mismo día):** una nota
        anterior decía que el link al PDF real "solo aparece después de
        JS" y que haría falta un browser headless — eso era un falso
        negativo: el primer intento buscaba únicamente URLs que terminan
        en `.pdf`, pero el link real no tiene extensión en la URL
        (`iess.gob.ec/documents/10162/25751514/DNA7-SySS-0001-2024?version=1.0`,
        `Content-Type: application/pdf` confirmado por header, 9.2 MB).
        Con un regex que no exige extensión, el link aparece directo en
        el HTML plano de la página de detalle. **Conclusión correcta: los
        344 documentos son enumerables y descargables sin ningún browser,
        headless o no** — candidato real para un tool de búsqueda/lectura
        (`search_iess_auditorias` o similar) encadenado con `read_pdf`.
        No construido todavía en esta sesión (el volumen — año → carpeta
        → documento → versión — es más que una verificación puntual),
        pero ya no hay ninguna barrera técnica identificada.
      - **Transparencia / LOTAIP** (`iess.gob.ec/transparencia/`) —
        confirmado: IESS publica su portal LOTAIP (Ley Orgánica de
        Transparencia y Acceso a la Información Pública) con secciones de
        resoluciones, exámenes de Contraloría, contratación pública,
        balance financiero del BIESS, etc. **Nota importante:** LOTAIP es
        obligatorio por ley para *toda* institución pública ecuatoriana,
        no solo IESS — si este patrón resulta automatizable en algún
        portal, probablemente se repite en decenas de instituciones. No
        investigado más a fondo esta sesión (fuera del pedido específico
        sobre IESS); candidato a su propio ítem de investigación si se
        decide perseguirlo.
- [~] **SENESCYT** — pedido explícitamente por Daniel. Datos de educación
      superior, becas, registro de títulos. **Revisado 2026-08-16: ya
      reachable hoy, sin código nuevo,** vía los tools CKAN genéricos
      (`organization="secretaria-de-educacion-superior-ciencia-tecnologia-e-innovacion-senescyt"`
      en `datosabiertos.gob.ec`) — 13 datasets: matrícula de universidades
      particulares (UEP) 2015-2023, docentes de UEP 2015-2022, oferta
      académica de las IES, artículos en revistas indexadas, y varias
      versiones fechadas de la base de becarios (agosto 2024, marzo 2024,
      diciembre 2023, agosto 2023, sin fecha ×2) — esta última con
      versiones repetidas sugiere que conviene usar solo la más reciente o
      investigar si son acumulativas. **Ojo, no cubre registro de títulos**
      (lo pedido explícitamente por Daniel) — ese dato no aparece en el
      CKAN. Portal propio también encontrado, "Portal de Indicadores de
      Educación Superior" (SIAU,
      `https://siau.senescyt.gob.ec/portal-de-indicadores-de-educacion-superior/`)
      — WordPress con 5 secciones temáticas (Estudiantes, Oferta Académica,
      Docentes, Títulos, Becas, ej. `/indicador-docentes/`), pero **cada
      sección es un dashboard de Power BI embebido**
      (`app.powerbi.com/view?r=...`), no una API ni archivos descargables —
      mismo problema visual-only ya visto en varios portales de este
      repo (nota: la comparación original con Superbancos ya no aplica —
      ver corrección 2026-08-29 en "Sitios de ministerios individuales",
      Superbancos sí tiene boletines reales descargables). Si el registro
      de títulos vive en algún lado
      estructurado, probablemente sea ahí (sección "Títulos" del SIAU) o en
      un portal de verificación de títulos aparte, todavía sin identificar
      — pendiente investigar específicamente eso, ya que el CKAN no lo
      resuelve. **Corrección 2026-08-28 (mismo día):** una nota anterior
      decía "sigue sin haber una fuente para registro de títulos" después
      de solo mirar de nuevo la página principal del SIAU — conclusión
      apresurada, no una investigación real. **Investigado a fondo con
      búsqueda web:** SENESCYT como marca prácticamente desapareció —
      `senescyt.gob.ec/web/guest/consultas` redirige hoy a
      `titulos-edusuperior.minedec.gob.ec` (Ministerio de Educación,
      Deporte y Cultura — MINEDEC), lo que sugiere una fusión o
      renombramiento institucional no reflejado hasta ahora en este repo.
      Esa URL **sí es el portal oficial de "Consulta de Títulos
      Registrados"** que motivó este ítem desde el principio: busca por
      apellidos + cédula/pasaporte, cita el Reglamento General a la LOES
      (Art. 56) como único medio oficial de verificación. Confirmado en
      vivo que es real y funcional. **Por qué sigue sin ser candidato a
      tool:** el formulario exige un captcha ("Ingrese los caracteres")
      antes de buscar — completar o evadir captchas está explícitamente
      prohibido para este asistente (no es una limitación técnica de
      scraping, es una regla operativa). La conclusión de fondo cambia de
      "no existe" a "existe, es real, pero está detrás de un captcha por
      diseño (verificación de identidad uno-a-uno, no un dataset
      masivo)" — no automatizable bajo ninguna circunstancia, no por
      falta de esfuerzo. El dato de la organización CKAN (`organization=
      "secretaria-de-educacion-superior..."`, 13 datasets) sigue
      funcionando sin cambios pese al renombramiento — confirmado en
      vivo.

      **Investigación adicional, mismo día** (Daniel: "investigate elsewhere,
      and see what other senescyt data we can find"): la Educación Superior
      pasó a ser un **Viceministerio dentro de `educacion.gob.ec`**
      (`educacionsuperior.gob.ec` redirige a `educacion.gob.ec/edusuperior/`)
      — confirma la fusión institucional apuntada arriba. Su página
      "Biblioteca" (`educacion.gob.ec/edusuperior/biblioteca/`) es un
      **archivo real y enorme: 1,259 documentos descargables**, en un árbol
      de categorías anidadas por año/tema desde 2013 hasta 2025 (PAC,
      Exámenes Especiales/auditoría, Normativa, LOES, SNNA, Acuerdos,
      Indicadores ACTI, y una sección completa "Dirección de Registro de
      Títulos" con manuales de proceso para títulos nacionales/extranjeros
      y codificación SNIESE). **Todo servido por el servidor, sin JS** — el
      acordeón visual está colapsado por CSS (`display:none`), pero el HTML
      completo con los 1,259 links reales (plugin WordPress
      `download-monitor`) ya está en la respuesta de `httpx` plano;
      confirmado descargando uno (`Indicadores de Ciencia, Tecnología e
      Innovación del Ecuador (ACTI)`, PDF real). **Mismo patrón que la
      Transparencia/LOTAIP de IESS** (PAC, exámenes de auditoría, normativa)
      pero en una plataforma totalmente distinta (WordPress vs. Liferay de
      IESS) — refuerza la hipótesis de que estas categorías se repiten
      entre instituciones no por compartir tecnología sino porque las
      exige la ley (LOTAIP, PAC), así que un scraper genérico "categorías
      legales comunes" podría generalizar mejor que uno por-institución.
      **Sobre el registro de títulos específicamente:** la carpeta
      correspondiente contiene manuales/instructivos/acuerdos sobre *cómo
      funciona* el proceso de registro (ej. "ACUERDO NO. 2015-106
      INSTRUCTIVO PARA LA CODIFICACIÓN DE TÍTULOS... DENTRO DEL SNIESE",
      "Manual de procesos gestión de títulos extranjeros"), no una base
      descargable de títulos individuales — coherente con que ese dato es
      personal/sensible y por eso solo se expone vía la consulta captcha
      uno-a-uno de arriba, no como dataset masivo. Confirma (con evidencia
      real esta vez, no solo ausencia de un link) que no existe un dataset
      masivo de títulos, sin cerrar la puerta a que la documentación de
      proceso en sí sea útil como referencia.
      **Sin explorar todavía:** `eod-prett.senescyt.gob.ec` (linkeado desde
      la página del Viceministerio, propósito no investigado).
- [x] **Cuenca en Datos** (`https://cuencaendatos.cuenca.gob.ec`) — **hecho
      2026-08-28.** Verificado en vivo: CKAN 2.9.6, 92 datasets, 13
      categorías temáticas, un solo publicador (GAD Municipal del cantón
      Cuenca). Mismo shape de API que el portal nacional
      (`package_search`/`package_show`/`resource_show`/...), así que en vez
      de un cliente/tools nuevos y paralelos, los ~10 tools CKAN genéricos
      (`search_datasets`, `list_recent_datasets`, `get_dataset_info`,
      `list_dataset_resources`, `get_resource_info`, `preview_resource_data`,
      `download_resource`, `query_resource_data`, `search_organizations`,
      `get_organization_info`, `list_categories`, `get_category_info`, y
      `detect_series_pattern`) ahora aceptan `source="nacional"|"cuenca"`.
      `helpers/ckan_client.py` resuelve la URL base según `source`
      (`_resolve_source`/`_ckan_url`/`site_url`, nuevos), con caché de
      categorías separada por fuente (`group_list:{source}`) para no
      mezclar las categorías de ambos portales. Nuevas variables de entorno
      opcionales `CUENCA_API_URL`/`CUENCA_SITE_URL`.
      Verificado en vivo end-to-end: `search_datasets`, `list_categories`,
      `search_organizations`, `get_dataset_info`, `list_dataset_resources`,
      `get_resource_info` y `preview_resource_data` (CSV real: actas de
      sesiones del Concejo Cantonal) devuelven datos correctos contra
      `source="cuenca"`; confirmado también que una búsqueda `source`
      nacional no encuentra contenido específico de Cuenca (los catálogos
      están genuinamente separados, no es un fallback silencioso). **Gap
      encontrado y cerrado 2026-08-28:** varios recursos de Cuenca son
      `.ods` (OpenDocument spreadsheet) — ahora soportado, ver ítem `.ods`
      en "Formatos y tipos de recursos" más abajo.
- [~] **Sitios de ministerios individuales** — **investigado 2026-08-29**
      (pedido de Daniel: justicia/seguridad — Fiscalía, Judicatura,
      Ministerio de Gobierno, Policía, ECU911 — y luego SEPS, Defensa/
      cartografía, ambiente, salud; **segunda pasada el mismo día:**
      insistir en Fiscalía, agregar Superbancos, seguir el barrido, y
      revisar si las organizaciones CKAN ya confirmadas tienen además
      sitios propios con datos que no están en CKAN). Resultado
      principal: **la gran mayoría ya está cubierta por el portal CKAN
      nacional que este proyecto ya integra** — no hacía falta ninguna
      conexión nueva para
      confirmarlo, solo verificar que la organización CKAN existe y tiene
      contenido real:
      - **Consejo de la Judicatura** (`organization=cj`) — causas
        ingresadas/resueltas/en trámite por materia, provincia, cantón,
        desde 2017, en ODS/XLSX, actualizado dic. 2025. El soporte `.ods`
        agregado esta misma sesión aplica directo aquí. También tiene su
        propio "Portal de Estadística Judicial"
        (`fsweb.funcionjudicial.gob.ec/estadisticas/datoscj/portalestadistica.html`)
        — revisado y **parece roto o mal configurado** (página casi en
        blanco, sin iframe ni contenido visible). El dataset CKAN sigue
        siendo el camino real.
      - **Ministerio del Interior / Ministerio de Gobierno**
        (`organization=ministerio-del-interior`; el ministerio ya se
        renombró a "Ministerio de Gobierno" en su sitio propio
        `ministeriodegobierno.gob.ec`, pero el slug de CKAN sigue con el
        nombre viejo — mismo patrón de rezago que SENESCYT/MINEDEC) —
        homicidios intencionales, personas desaparecidas, detenidos/
        aprehendidas, armas incautadas, trata de personas.
      - **ECU911** (`organization=ecu-911`) — bases de emergencias
        mensuales (CSV/ODS), con recursos hasta al menos febrero 2025.
      - **IGM / Ministerio de Defensa** (`organization=igm`) — 25
        datasets. Además tiene su propio Geoportal
        (`geoportaligm.gob.ec`) con cartografía descargable — la primera
        fuente real y concreta que motivaría el pendiente de "Manejo
        geoespacial de recursos" (arquitectura, más abajo), sin explorar
        a fondo todavía.
      - **MAATE (Ambiente, Agua y Transición Ecológica)**
        (`organization=ministerio-del-ambiente-agua-y-transicion-ecologica`)
        — indicadores ambientales y de recurso hídrico (SINIAS), CSV/ODS,
        actualizado jul. 2025.
      - **Ministerio de Salud Pública**
        (`organization=ministerio-de-salud-publica`) — 8 datasets
        (defunciones generales, matrimonios, divorcios y más vía
        Registro Civil). También tiene su propio
        `salud.gob.ec/datos-abiertos-2/` y dashboards "Salud en Cifras"/
        "GeoSalud en Cifras" (sin confirmar si son API o solo visuales).

      **Casos que sí necesitan un sitio propio** (no cubiertos por CKAN,
      con contenido real confirmado fuera de él):
      - **SEPS** (Superintendencia de Economía Popular y Solidaria) — el
        sitio principal `seps.gob.ec` **bloquea activamente** las
        conexiones automatizadas (título "Blocked" al navegar, 404 vía
        `httpx` plano — a diferencia del 403 "fuera de Latinoamérica" ya
        documentado para `datosabiertos.gob.ec`, este parece un bloqueo
        distinto, posiblemente por huella de bot). Pero el subdominio
        **`estadisticas.seps.gob.ec` sí es alcanzable** (200 vía `httpx`
        plano) y tiene boletines reales (calificadoras de riesgo de
        cooperativas, PDF, hasta dic. 2025).
      - **Fiscalía General del Estado** — **revisado de nuevo 2026-08-29**
        (pedido explícito de Daniel de incluirla igual). No tiene
        organización CKAN propia — confirmado con `search_datasets`
        directo contra el portal (0 resultados relevantes), no solo por
        ausencia de link en su sitio. Su sección "Estadísticas FGE"
        (violencia de género, robos) sigue **abandonada desde 2021**
        (última entrada: "Cifras femicidio corte 07 de noviembre 2021");
        su "Analítica cifras de robo" es un dashboard Power BI embebido,
        visual-only. Su "Consulta de Noticias del Delito"
        (`gestiondefiscalias.gob.ec/siaf/...`) es real y funcional, pero
        es una **búsqueda de un caso a la vez por nombre/placa/número de
        denuncia** — aunque no tiene captcha, no encaja como tool de este
        proyecto por la misma razón que un registro de títulos
        individual: es una herramienta de consulta de expedientes
        personales, no un dataset agregado, y automatizarla como
        búsqueda de personas se sale del propósito de este servidor
        (datos abiertos/estadísticas, no investigación de individuos).
        **Sí se encontró algo real y útil, adyacente a Fiscalía:** el
        organismo forense que trabaja con ella tiene su propia
        organización CKAN, `servicio-nacional-de-medicina-legal-y-
        ciencias-forenses` (10 datasets, incl. "Pericias realizadas en
        Ciencias Forenses y Medicina Legal 2024") — ya alcanzable con
        los tools genéricos existentes, sin código nuevo.
      - **Policía Nacional** — tiene una página "Conjunto de datos"
        (`policia.gob.ec/wpfd_file/conjunto-de-datos/`) pero el único
        archivo real ahí es un CSV de contactos LOTAIP (responsables de
        acceso a información pública), no datos operativos. Los datos de
        seguridad reales de Policía viven en el CKAN de Ministerio del
        Interior de arriba, no en el sitio propio de la Policía.
      - **Superintendencia de Bancos** — **corrección 2026-08-29 a una
        nota anterior en este mismo archivo** que la comparaba con
        SENESCYT como "visual-only, sin endpoint consultable": eso era
        cierto solo para sus "Visualizadores" (Power BI), pero el sitio
        tiene un **Portal Estadístico separado**
        (`superbancos.gob.ec/estadisticas/portalestudios/`) con
        **boletines financieros mensuales reales en `.zip`, con
        histórico completo desde 1997** (`BOL_FIN_BCOS_{año}.zip`,
        confirmado descargando el de 2003, 2.8 MB real). Sin
        organización CKAN propia (confirmado con `search_datasets`). El
        boletín del mes/año actual se sirve vía un widget OneDrive
        embebido (requiere JS), pero el archivo histórico completo
        (1997 en adelante) son links estáticos, alcanzables con `httpx`
        plano. **Ojo:** este subdominio necesita `verify=False` en la
        descarga — certificado TLS mal configurado, mismo tipo de
        problema (no el mismo host) que ya maneja `helpers/tls.py` para
        `datosabiertos.gob.ec`.
      - **Trabajo, Turismo, Producción/Comercio Exterior/Pesca** — las
        tres tienen organización CKAN propia y ya alcanzable:
        `ministerio-del-trabajo` (5 datasets), `ministerio-de-turismo`
        (5 datasets), `ministerio-de-produccion-comercio-exterior-
        inversiones-y-pesca-mpceip` (8 datasets — el mismo MPCEIP que ya
        motivó `detect_series_pattern` con los precios de cacao). Sin
        código nuevo.

      **Tercera pasada, mismo día** (Daniel: explícitamente no le
      interesa qué instituciones tienen organización CKAN — le interesa
      identificar *portales y páginas de estadísticas propias, más allá
      de lo que ya está en CKAN*):
      - **MAATE — hallazgo real e inesperado:** su dominio histórico
        `ambiente.gob.ec` **ya no le pertenece** — redirige a
        `atencionintegral.gob.ec`, el sitio del **SNAI** (Servicio
        Nacional de Atención Integral a Personas Privadas de la
        Libertad, el sistema penitenciario), una institución totalmente
        distinta. El sitio real actual del ministerio es
        **`ambienteyenergia.gob.ec`** — confirma que el ministerio se
        renombró (o se fusionó con Energía) sin que este repo lo supiera
        todavía. Su Transparencia/LOTAIP (mismo patrón WordPress
        `download-monitor` ya visto en IESS y el Viceministerio de
        Educación Superior) reveló algo nuevo: **Minería está ahora bajo
        el mismo ministerio** ("Viceministerio de Minas"), con
        "Reportes Semanales Sector Minero" — datos reales, de
        periodicidad semanal, sin explorar más a fondo todavía.
        `sinias.ambiente.gob.ec` (el sistema de indicadores ambientales
        mencionado en la pasada anterior) resultó ser una **página de
        bienvenida por defecto de JBoss sin aplicación desplegada** —
        infraestructura muerta, no una fuente real.
      - **`turismo.gob.ec` tiene el mismo problema de redirección** que
        `ambiente.gob.ec` — también termina en `atencionintegral.gob.ec`.
        Probablemente un vhost por defecto mal configurado en hosting
        compartido (mismo tipo de bug de vhost ya documentado en este
        repo para `datosabiertos.gob.ec`), no una fuente de datos real;
        no investigado más a fondo — no se encontró el dominio actual
        real de Turismo en esta pasada.
      - **ECU911** (`ecu911.gob.ec/Datos/`, sin `www`) — solo un
        dashboard Power BI embebido (`app.powerbi.com/reportEmbed`).
        Curiosamente la página expone en HTML plano un usuario/contraseña
        de acceso compartido al reporte — irrelevante de todos modos,
        porque incluso con acceso solo es un visor de reporte, no una
        API. Nada más allá de lo que ya está en CKAN.
      - **Ministerio de Salud** — revisadas las tres páginas propias
        encontradas antes: `datos-abiertos-2/` es solo un texto
        promocional que apunta de vuelta a `datosabiertos.gob.ec` (nada
        adicional); `salud-en-cifras/` resultó ser una **categoría de
        noticias/boletines de prensa**, no un repositorio de datos, pese
        al nombre; `geosalud-en-cifras/` ya no existe (redirige al
        inicio). Nada más allá de CKAN.
      - **Ministerio de Gobierno** (`ministeriodegobierno.gob.ec`) y
        **Ministerio de Defensa** (`defensa.gob.ec`) — revisados, sin
        páginas de estadísticas/datos propias más allá de lo que ya
        enlazan directo a `datosabiertos.gob.ec`. Defensa además ofrece
        un formulario de "Transparencia Colaborativa" para pedir
        información puntual (`servicios.midena.gob.ec/Transparencia/`),
        no un dataset descargable.
      - **Geoportal del IGM** — investigado más a fondo: la cartografía
        de libre acceso está detrás de un **formulario de registro**
        (`geoportaligm.gob.ec/formulario3/...`), y los datos GNSS/red
        gravimétrica requieren **crear una cuenta gratuita** para poder
        descargar (login real, no solo un captcha). Ambos caen en la
        misma categoría que el registro de títulos: no son gratuitos en
        el sentido de "sin fricción", y crear cuentas no es algo que
        este asistente haga — así que sigue siendo un pendiente real
        (arquitectura geoespacial), no algo bloqueado por falta de
        esfuerzo, pero tampoco automatizable tal cual está.
      - **Producción** (`produccion.gob.ec`) — nada de estadísticas
        propias en la navegación principal, pero enlaza a
        **`aduana.gob.ec`/ECUAPASS** (la Ventanilla Única de Comercio
        Exterior) — ver hallazgo de comercio exterior más abajo.

      **Cuarta pasada, mismo día** (Daniel pidió específicamente:
      Educación, Aduana, Ministerio de Gobierno, Ministerio del Interior
      — investigar su dominio real —, y más de BCE más allá de BCEData;
      mencionó que hay interés en el catálogo IEEM con publicaciones
      mensuales):
      - **BCE — hallazgo grande: la "Información Estadística Mensual"
        (IEM/IEEM)**, el boletín insignia del Banco Central, mucho más
        allá de lo que cubre la API BCEData ya integrada.
        `contenido.bce.fin.ec/documentos/informacioneconomica/
        PublicacionesGenerales/IndiceIEM.html` lista los boletines desde
        hace décadas (numerados; No. 2087-2092 = enero-junio 2026, uno
        por mes, confirmado en vivo — **es exactamente el "catálogo con
        publicaciones mensuales" que Daniel pidió encontrar**). Cada
        boletín (`.../IEMensual/m{n}/IEM{n}.zip`, patrón de URL
        predecible por número) es un ZIP real y descargable — confirmado
        el de junio 2026 (No. 2092): **11.5 MB**, contiene docenas de
        cuadros: estadísticas monetarias y financieras (M1/M2, tasas de
        interés, reservas internacionales, balance sectorial por tipo de
        entidad), finanzas públicas (operaciones del SPNF, base
        devengado, % del PIB), y más secciones no leídas todavía
        (probablemente sector externo, cuentas nacionales, precios,
        sector real — el índice truncó antes de listarlas todas). Mucho
        más rico que los indicadores curados de BCEData. También hay un
        PDF de la publicación completa por boletín
        (`IEM{n}.pdf`). Candidato real y fuerte para una integración
        nueva (`helpers/bce_iem_client.py` o similar) — el volumen de
        cuadros por boletín es grande, no es trivial, pero el acceso en
        sí no tiene fricción (sin registro, sin captcha).
      - **Ministerio del Interior vs. Ministerio de Gobierno — son dos
        sitios reales y distintos, no un simple renombramiento** (a
        diferencia de SENESCYT→MINEDEC). `ministeriodelinterior.gob.ec`
        y `ministeriodegobierno.gob.ec` **ambos resuelven, ambos
        responden 200, con títulos y contenido distintos** — confirmado
        en vivo, no es un caso de dominio viejo redirigiendo al nuevo.
        Interior tiene su propio **"Micrositio de Estadísticas de
        Seguridad"** (`cifras.ministeriodelinterior.gob.ec`) — una app
        Angular real (necesita JS, `httpx` plano solo devuelve el shell
        vacío) protegida por **Incapsula** (WAF anti-bot). Una vez
        renderizada muestra "Visualizadores" para homicidios, armas
        ilícitas, desaparecidos, trata de personas, detenidos —
        **exactamente las mismas categorías que ya están en el CKAN de
        `ministerio-del-interior`**, sin links de descarga visibles (solo
        visualizadores) — duplicado del dato ya cubierto, no una fuente
        nueva. Ministerio de Gobierno, revisado a fondo: su página de
        "Indicador PND 2025-2029 MAPIs" (MAPIs = Medidas de Amparo o
        Protección Inmediata, violencia de género) solo tiene documentos
        metodológicos/normativos (norma jurídica, manual, ficha
        metodológica) — no la serie de datos en sí. Ninguno de los dos
        aporta algo descargable más allá de CKAN.
      - **Educación básica / MINEDEC — hallazgo real:**
        `educacion.gob.ec/datos-abiertos-minedec/` tiene un **registro
        administrativo histórico de matrícula 2009-2025** en Excel real
        (`Registro-Administrativo-Historico_2009-202X-{Inicio,Fin}.xlsx`,
        más diccionario de datos y metadatos, actualizado abril 2026,
        confirmado con `HEAD` real). Esto es más rico que los 2 datasets
        que ya tiene `organization=ministerio-de-educacion` en CKAN —
        candidato real a mirar más de cerca si se decide un tool de
        educación básica.
      - **Aduana/comercio exterior — dead end confirmado, no solo
        supuesto.** Tanto `aduana.gob.ec/estadisticas/` como
        `produccion.gob.ec/boletines-mensuales-de-comercio-exterior/`
        son páginas reales pero **vacías** (la de Producción muestra
        pestañas por año 2021-2026 sin ningún archivo real detrás,
        confirmado buscando enlaces `.pdf/.xlsx/.zip` en el HTML plano:
        cero). La búsqueda web confirma por qué: las estadísticas de
        comercio exterior de SENAE **se piden por oficio o correo al
        Service Desk**, no se publican en un portal abierto. No es una
        limitación técnica de scraping — el dato simplemente no está
        publicado así.

      **Conclusión:** para este dominio (justicia/seguridad + ambiente +
      salud + trabajo/turismo/producción + educación básica + banca
      central), la estrategia correcta no es "conexión nueva por
      institución" sino **verificar cobertura CKAN primero** — la mayoría
      ya está ahí, sin código nuevo. Los candidatos reales a conexión
      propia, en orden de valor: **BCE/IEM** (el hallazgo más grande de
      esta ronda — boletín mensual completo, sin fricción de acceso),
      **Superbancos** (boletines `.zip` reales desde 1997), **SEPS** (vía
      el subdominio de estadísticas), el **"Reportes Semanales Sector
      Minero"** de Ambiente y Energía, y el **registro histórico de
      matrícula de MINEDEC**. El **Geoportal del IGM** sigue siendo un
      candidato real para el pendiente geoespacial, pero requiere
      resolver primero el registro/login que no se puede automatizar sin
      intervención humana. **Descartado con evidencia, no por
      abandono:** comercio exterior/Aduana (no se publica abiertamente,
      confirmado).

      **Quinta pasada, mismo día** (Daniel: "investigar aún más profundo,
      no queremos perdernos nada" — Ministerio de Industria/Producción,
      Ambiente, Agricultura, y lo que aparezca):
      - **SIPA (Sistema de Información Pública Agropecuaria) — el
        hallazgo más grande de toda esta investigación.**
        `sipa.agricultura.gob.ec`, del **Ministerio de Agricultura,
        Ganadería y Pesca** (`agricultura.gob.ec`, real, vivo, **distinto
        de MPCEIP** — Agricultura y Comercio Exterior/Producción son dos
        ministerios separados, no uno solo pese al traslape de "Pesca"
        en ambos nombres). Solo el módulo económico
        (`sipa-estadisticas/estadisticas-descargas/estadisticas-
        economicas`) tiene **12 archivos Excel reales y de descarga
        directa, sin registro ni login**: valor agregado bruto
        agropecuario, comercio exterior agropecuario/agroindustrial,
        crédito público y privado agropecuario, sector silvícola,
        precios productor ponderado, precios mercados mayoristas,
        precios agroindustria, precios pecuarios, precios
        internacionales, precios agroquímicos/fertilizantes, IPC
        alimentos/inflación, índices de sector. **Confirmado
        descargando uno real: `precios-productor-ponderado.xlsx`, 41.4
        MB** — muy por encima del tope de 5 MB que usan los tools de
        preview de este proyecto (mismo problema de escala que el PDF
        actuarial de 14.6 MB de IESS; necesitaría `download_resource` o
        un tope más alto, no `preview_resource_data` tal cual). Y eso es
        solo un módulo — el sitio además tiene "Cifras Agroproductivas"
        y "Cifras Territoriales" (tableros dinámicos, probablemente
        Power BI, sin confirmar), boletines nacionales (Panorama
        Agroestadístico, Precios Mayoristas, Precios Internacionales,
        Precios Productor), boletines situacionales por cultivo (ej.
        papa), un Panorama Agroeconómico anual, y un geoportal propio de
        ortofotos (`geoportal.agricultura.gob.ec`) — más geoespacial,
        sin explorar. Esto reemplaza por completo la cobertura actual de
        `detect_series_pattern`/cacao vía MPCEIP: **es la fuente real y
        mucho más rica** para todo lo agropecuario. Candidato de máxima
        prioridad para una integración nueva.
      - **Ministerio de Finanzas se fusionó/renombró** — otro caso como
        SENESCYT→MINEDEC. `finanzas.gob.ec` redirige a
        `economicoproductivo.gob.ec`, el **"Ministerio de Desarrollo
        Económico y Productivo" (MDEP)** — sugiere que Finanzas,
        Producción/Industrias (`industrias.gob.ec` ya no resuelve por
        DNS, consistente con que se fusionó para acá) y quizás más
        quedaron bajo un solo ministerio nuevo. Tiene una página real
        **"Estadísticas Fiscales"** (`finanzas.gob.ec/estadisticas-
        fiscales/`, las URLs internas siguen con el dominio viejo) con
        calendario de publicación de estadísticas de finanzas públicas
        2026 y documentos de deuda pública — confirmé el calendario y la
        estrategia de deuda como PDFs/XLS reales, pero no llegué a
        confirmar si hay series de tiempo fiscales descargables ahí
        mismo o si redirige a otro lado (sin terminar de revisar).
      - **Contraloría General del Estado — hallazgo real y grande:** su
        página "Datos Abiertos" (`contraloria.gob.ec/Portal/24287`) aloja
        **"Informes aprobados"**, un archivo trimestral de *todos* los
        informes de auditoría aprobados a *cualquier* institución
        pública del país (enero-marzo 2023 en adelante, confirmado en
        vivo) — mucho más amplio que el archivo de auditorías que ya se
        encontró solo para IESS. También hay "Consulta de declaraciones
        patrimoniales" (declaraciones patrimoniales de funcionarios
        públicos) y "Plan anual de control". **Sin confirmar todavía:**
        los links de "Informes aprobados" no exponen un `href` de
        archivo directo en el HTML — parecen abrirse vía JS/visor de
        documentos, no confirmé si son escalables con `httpx` plano o
        necesitan browser. Pendiente de profundizar.
      - **Patrón sistémico confirmado de dominios `.gob.ec` viejos
        redirigiendo al mismo lugar equivocado:** además de
        `ambiente.gob.ec` y `turismo.gob.ec` (pasada anterior),
        **`arcsa.gob.ec` (regulador de medicamentos/alimentos) también
        redirige a `atencionintegral.gob.ec`** (SNAI, sistema
        penitenciario) — tercer caso confirmado. Fuerte indicio de un
        vhost por defecto mal configurado en infraestructura de hosting
        compartida del Estado, no una serie de coincidencias. No vale la
        pena seguir intentando adivinar el dominio real de cada uno uno
        por uno — mejor buscar el dominio correcto por separado cuando
        haga falta una institución específica.
      - **Dos sitios más protegidos por Incapsula (WAF anti-bot),** además
        del micrositio de Interior ya visto: **CNE** (Consejo Nacional
        Electoral, `cne.gob.ec`, 403 directo a `httpx` con firma
        Incapsula en el body) — datos electorales quedan fuera de
        alcance sin resolver el WAF. **MIDUVI** (`miduvi.gob.ec`) falla
        directo a nivel TLS (`SSL: UNEXPECTED_EOF_WHILE_READING`),
        síntoma distinto, tampoco resuelto.

      **Conclusión:** el hallazgo que más cambia el mapa de este barrido
      es **SIPA** — una fuente agropecuaria real, rica, y sin fricción de
      acceso, que debería ser la prioridad número uno si se decide
      construir una integración nueva a partir de esta investigación,
      por delante de BCE/IEM, Superbancos y SEPS. Segundo en la lista:
      **Contraloría** (archivo nacional de auditorías, alcance
      transversal a todo el Estado) — **resuelto en la sexta pasada, ver
      abajo.**

      **Sexta pasada, mismo día** (Daniel: profundizar Contraloría "no
      queremos perdernos nada", más desnutrición/INEC/Presupuesto
      General del Estado/CNE, luego SRI/ENES/IEPI/cultura/mujeres):
      - **Contraloría — resuelto de punta a punta.** El botón de
        descarga de "Informes aprobados" llama a una función JS
        (`down('pesdoc', 67)`) que arma la URL
        `contraloria.gob.ec/WFDescarga.aspx?id={id}&tipo=pesdoc&op=d` —
        **confirmado real, sin necesidad de browser**: descargué el de
        enero-marzo 2023 y es un **CSV real de 155 KB**, no un PDF —
        columnas `Unidad de Control; Entidad; Diligencia; Periodo Desde;
        Periodo Hasta; Tipo de informe; N° Informe; Fecha Aprobación`,
        una fila por informe de auditoría aprobado a *cualquier*
        institución pública del país. Totalmente scrapeable con `httpx`
        una vez que se conoce el patrón de URL (falta solo mapear los
        `id` de cada trimestre, visibles en el HTML de la página). Este
        es probablemente el hallazgo más *inmediatamente accionable* de
        toda la investigación — sin JS, sin login, sin captcha, datos
        estructurados de verdad.
      - **Desnutrición — ya cubierta, confirmado que no hay gap.** La
        Secretaría Técnica "Ecuador Crece Sin Desnutrición Infantil"
        (`organization=stecsdi` en CKAN, 3 datasets de alertas
        cantonales en tiempo real) no tiene sitio propio (opera vía
        redes sociales y páginas de MSP/MEF) — su organización CKAN es
        el único punto de acceso real, y ya es alcanzable. `search_datasets(query="desnutricion")`
        además encuentra ENSANUT 2012/2018, ECV, y "MSP_Nutrición" — 8
        datasets en total, todos ya reachable.
      - **Presupuesto General del Estado — ya cubierto, muy a fondo.**
        `organization=ministerio-de-economia-y-finanzas` en CKAN tiene
        **97 datasets** (confirmado en vivo), incluyendo ejecución
        presupuestaria mensual a nivel de Unidad de Administración
        Financiera. El slug CKAN conserva el nombre viejo del ministerio
        pese a la fusión a "Desarrollo Económico y Productivo" ya
        documentada — mismo patrón de rezago que otros casos.
      - **CNE — sigue bloqueado, confirmado con un segundo método.**
        `cne.gob.ec/estadisticas/bases-de-datos/` da página en blanco
        también vía el browser real (no solo `httpx`) — el WAF Incapsula
        bloquea ambos caminos. Datos electorales quedan genuinamente
        fuera de alcance sin resolver eso.
      - **SRI — CKAN tiene mucho más de lo que ya scrapea este proyecto.**
        `organization=sri-servicio-de-rentas-internas` tiene **127
        datasets** (recaudación de impuestos por año 2017-2024,
        prestadores de servicios digitales, catastro de agregadores de
        pago, autorizados para facturación electrónica...) — esto es
        aparte del scraper propio de `search_sri_datasets` (que lee la
        página Liferay `sri.gob.ec/datasets` directamente, ~130
        archivos). Puede haber traslape, pero el catálogo CKAN es rico
        por sí solo y ya reachable con los tools genéricos.
      - **SENESCYT/Educación Superior — un segundo archivo real, aparte
        de la "Biblioteca" ya documentada.**
        `siau.senescyt.gob.ec/estadisticas-de-educacion-superior-ciencia-tecnologia-e-innovacion/`
        tiene su propio archivo de reportes reales (mismo patrón
        WordPress `download-monitor`): Reporte PND, indicadores de
        educación superior/CTI, índice de competitividad del Ecuador,
        inventario de indicadores CTI y saberes ancestrales,
        caracterización de la demanda laboral — algunos enlazan a
        instancias Nextcloud propias (`cloud-00.senescyt.gob.ec`,
        `cloud-pro.senescyt.gob.ec`), igual que el manual del Geoportal
        del IGM. No encontré una sección específica de resultados del
        examen ENES/SNNA por nombre — puede estar dentro de estos
        reportes agregados, sin confirmar.
      - **IEPI se convirtió en SENADI en 2018** (bajo el paraguas de
        SENESCYT). Su dominio real y vivo es
        `derechosintelectuales.gob.ec` (`propiedadintelectual.gob.ec`
        redirige ahí). Existe un dataset CKAN real
        ("Base de datos de propiedad intelectual aprobadas y
        solicitadas a la SENADI") pero está **mal catalogado bajo la
        organización equivocada** (`instituto-de-investigacion-
        geologico-y-energetico-iige`, el instituto geológico — no
        SENADI) — un defecto de calidad de datos del portal en sí, no
        del scraping. La página de estadísticas propia de SENADI que
        encontré es un artículo de noticia de 2017, no un portal de
        datos vivo — sin confirmar si existe uno más actual.
      - **Cultura** — `organization=mcyp` (Ministerio de Cultura y
        Patrimonio) ya tiene 6 datasets reales en CKAN (visitantes de
        museos, usuarios de bibliotecas/archivos históricos,
        beneficiarios de fondos de patrimonio cultural, Registro Único
        de Artistas y Gestores Culturales - RUAC). Ya reachable, sin
        gap identificado.
      - **Mujeres/Género — hallazgo real.** El **Consejo Nacional para
        la Igualdad de Género (CNIG)**, `igualdadgenero.gob.ec`, tiene
        una sección "Violencia" con el mismo patrón de acordeón
        `download-monitor` ya confirmado scrapeable en otros sitios:
        "Femicidios y Homicidios Intencionales de Mujeres" (según
        búsqueda web, una "Matriz de Femicidios" actualizada
        **semanalmente** desde agosto 2014 — la periodicidad más alta
        encontrada en toda esta investigación) y series de violencia de
        género desagregadas por provincia, etnia, discapacidad, edad y
        quintil de ingreso. También coordina con INEC la encuesta
        ENVIGMU (2019, ya en CKAN) y publica la serie "Mujeres y
        Hombres en Cifras". No confirmé el link de descarga exacto de
        la matriz de femicidios (no llegué a expandir el acordeón), pero
        el patrón ya probado en otros sitios da alta confianza de que es
        real y accesible sin fricción.

      **Conclusión de esta pasada:** el hallazgo más *inmediatamente
      accionable* es **Contraloría** — patrón de URL resuelto
      completamente, CSV real, sin ninguna barrera técnica. **CNIG**
      (femicidios semanales) es el segundo más prometedor por
      periodicidad. Todo lo demás en la lista de Daniel (desnutrición,
      PGE, SRI, Cultura) ya estaba cubierto por el CKAN nacional, sin
      gaps reales encontrados. CNE sigue siendo el único bloqueo genuino
      y confirmado dos veces. Sin explorar todavía: el patrón exacto de
      `id` en las descargas de Contraloría para los demás trimestres, el
      link real de la matriz de femicidios de CNIG, si ENES/SNNA tiene
      una sección de resultados propia dentro de los reportes de SIAU,
      el dominio real y actual de **Turismo**, el resto de las secciones
      del boletín IEM del BCE, y los tableros dinámicos de SIPA. Marcado
      como parcial, no cerrado.

---

## Cabos operativos sueltos

- [x] **Renovación del certificado TLS** de `www.datosabiertos.gob.ec` (había
      vencido 2026-07-28). **Confirmado 2026-08-22 contra el portal real:**
      certificado renovado (Let's Encrypt, válido 2026-08-07 a 2026-11-05).
      `CKAN_INSECURE_TLS` ya vuelve a su default seguro (`0`, desactivado) —
      ver `helpers/tls.py`. Próximo corte de renovación: antes de
      2026-11-05.

---

## Calidad de búsqueda y detección de series

- [ ] **Búsqueda semántica** — `search_datasets` pasa directo a búsqueda por
      palabra clave de CKAN, que en general es débil frente al catálogo
      completo (consultas de una sola palabra sin sinónimos ni relación
      semántica con el contenido real). Falta una capa de
      similitud/embeddings que mejore el recall sin reemplazar la búsqueda
      en vivo. **Corrección 2026-08-27:** el ejemplo original de este ítem
      ("cacao" devuelve muy pocos resultados) no se reprodujo verificando
      de nuevo contra el portal real — `search_datasets(query="cacao")` y
      `search_datasets(query="MPCEIP")` devuelven correctamente los 3 y 8
      datasets relevantes respectivamente, incluyendo el dataset de precios
      FOB de cacao del MPCEIP. La afirmación de que esta consulta específica
      fallaba había quedado desactualizada (o nunca se verificó
      correctamente) y de paso se repitió sin verificar en las notas de
      `detect_series_pattern` más abajo — corregido ahí también. El
      problema de fondo (búsqueda por palabra clave sin comprensión
      semántica) sigue siendo real y motiva el ítem, solo que sin este
      ejemplo concreto.
- [x] **Expansión de siglas/acrónimos en la consulta** — hecho:
      `helpers/acronyms.expand_acronyms` reconoce ~13 siglas comunes
      (ENEMDU, ENSANUT, ENIGHUR, ECV, RUC, IESS, SRI, INEC, BCE, SERCOP,
      SENESCYT, SUPERCIAS, SGR) y agrega el nombre completo a la consulta
      antes de mandarla a CKAN. El operador por default de Solr en CKAN es
      OR entre términos, así que agregar palabras solo amplía el recall, no
      lo restringe — un documento que matchea la sigla, el nombre completo,
      o ambos, sigue apareciendo. Aplicado en `ckan_client.search_datasets`.
- [x] **Detección real acumulado-vs-incremental** entre archivos de un mismo
      dataset — **agregado 2026-08-27:** nuevo tool `detect_series_pattern`.
      Toma el grupo de recursos con nombre de serie periódica que ya detecta
      `list_dataset_resources` (`possible_periodic_series`), descarga los dos
      más recientes (hasta 500 filas c/u), busca una columna de
      fecha/período por nombre de encabezado (`fecha`, `mes`, `año`,
      `periodo`, `semana`, ...) y compara qué valores de período aparecen en
      ambos archivos. Solapamiento alto → `acumulado` (el archivo nuevo ya
      incluye los períodos del anterior, basta con leer el más reciente);
      solapamiento casi nulo → `incremental` (cada archivo cubre un período
      distinto, hay que combinarlos); si no hay solapamiento claro o no se
      detecta ninguna columna de período, devuelve `indeterminado` en vez de
      adivinar. **Verificado 2026-08-27 contra el portal real**
      (`base-de-datos-seguro-desempleo` de IESS) — encontrados y corregidos
      dos bugs reales durante la verificación, no solo confirmación:
      1. Los CSV de IESS traen 1-3 filas de título/banner antes del
         encabezado real (ej. `Monto pagado y numero de beneficiarios 2026`
         en la fila 1, encabezado real `Mes,Monto pagado,...` en la fila 2).
         `preview_csv` siempre trata la fila 0 como encabezado, así que la
         columna de período quedaba invisible. Nueva función
         `_locate_header_row` escanea las primeras filas buscando una que
         luzca a encabezado real y contenga una palabra clave de período.
      2. **Hallazgo más serio:** recursos con nombre casi idéntico
         (`Pagos Desempleo Marzo/Abril/Mayo/Junio 2026`) cambian de formato
         interno entre meses sin aviso — unos meses traen el detalle por
         provincia/género (`Mes,Tipo Pago,Provincia,Genero,...`, mes como
         código numérico `"5"`), otros el resumen mensual acumulado
         (`Mes,Monto pagado,...`, mes como palabra `"junio"`). Comparar
         períodos entre dos archivos así da 0% de solapamiento — la
         heurística original lo hubiera reportado como `incremental` con
         confianza, una conclusión técnicamente calculada pero engañosa
         (el problema real es que no son el mismo tipo de reporte, no que
         cubran períodos distintos). Nueva función `_schema_mismatch`
         compara el conjunto de encabezados de ambos archivos antes de
         confiar en el solapamiento de períodos; si comparten menos de la
         mitad de sus columnas, la clasificación se fuerza a
         `indeterminado` con motivo `esquema_distinto_entre_archivos` en
         vez de adivinar.

      **Verificado también contra MPCEIP cacao (el otro caso motivador),**
      dataset `96f97d5c-394f-4be6-8046-3266d0cd5711` ("Precios
      referenciales FOB para la exportación de cacao en grano"). **Nota de
      corrección:** durante esta verificación se afirmó por error que
      `search_datasets` no encontraba este dataset ni con "cacao" ni con
      "MPCEIP" — resultó ser un bug en el script de diagnóstico usado
      (indexaba un `result` extra que no existe en lo que ya devuelve
      `ckan_client.search_datasets`), no un problema real del tool.
      Re-verificado: `search_datasets(query="cacao")` y
      `search_datasets(query="MPCEIP")` encuentran este dataset
      correctamente entre sus resultados. El dataset se ubicó originalmente
      vía el endpoint CKAN `resource_search` directo mientras se investigaba
      el falso problema — dato irrelevante ya para el resultado final, pero
      documentado por transparencia. Comparando los recursos reales
      `MPCEIP_PRECIO FOB_EXPORTACIONES
      CACAO_2023_AGOSTO.csv` vs `..._2023_SEPTIEMBRE.csv`:
      `detect_series_pattern` encontró la columna de período compuesta
      (AÑO, MES, SEMANA, FECHAS) y clasificó correctamente como `acumulado`
      (34/34 períodos de agosto = 100% también en septiembre) — coincide
      exactamente con la nota de verificación e2e de más abajo (el archivo
      de junio 2026 ya trae las 4 semanas de junio *y* los meses previos
      del año, "usando solo el archivo más reciente"). Primera confirmación
      real de que la clasificación en sí (no solo el rechazo seguro a
      adivinar) acierta contra el portal real.

      **Dos limitaciones reales de auto-detección, encontradas y corregidas
      en la misma sesión de verificación:**
      1. `detect_periodic_series` agrupaba solo por plantilla de dígitos,
         así que no agrupaba `..._AGOSTO.csv`/`..._SEPTIEMBRE.csv`
         (difieren en una palabra, no en un número) — hubo que pasar
         `resource_id_new`/`resource_id_old` explícitos en la primera
         verificación. Corregido: los nombres de mes en español ahora se
         normalizan al mismo placeholder que los dígitos antes de agrupar.
      2. Con el agrupamiento ya corregido, `_pick_pair` (para elegir "los
         dos más recientes" del grupo) ordenaba por `last_modified` de
         CKAN, que resultó no ser confiable: el recurso de enero 2023 tenía
         un `last_modified` *posterior* al de septiembre 2023 (probable
         corrección/re-subida), así que el auto-pick elegía enero como "más
         reciente" — 8 meses al revés. Corregido: nueva función
         `period_sort_key` (en `list_dataset_resources.py`, pública para
         reutilizarse) extrae año/mes del propio nombre del recurso y
         ordena por eso primero, usando el timestamp de CKAN solo como
         desempate.

      **Con ambos fixes, `detect_series_pattern(dataset_id=...)` sin
      argumentos adicionales ya funciona de punta a punta contra los dos
      datasets reales que motivaron este ítem:** MPCEIP cacao
      (AGOSTO→SEPTIEMBRE 2023, `acumulado`, 34/34 períodos) e IESS
      desempleo (Junio→Julio 2026, `acumulado`, 13/13 períodos) — ambos
      auto-detectados y clasificados correctamente sin pasar IDs a mano.

      Sigue siendo una heurística de nombre de columna + solapamiento de
      valores; no garantiza acierto en datasets con columnas de período con
      nombres atípicos (ej. meses abreviados como "JUN"/"ABR" en vez de
      "junio"/"abril", vistos en recursos MPCEIP más recientes y aún sin
      cubrir), y no detecta cambios de esquema más sutiles que el umbral de
      50% de columnas en común.

## Formatos y tipos de recursos

- [x] **Tool `read_pdf(url, pages)`** — hecho 2026-08-28: extrae texto de un
      PDF vía `pypdf` (pura Python), `pages` como rango 1-indexado ("1-5",
      "3", "1,4,9"), tope de 20 páginas por llamada. Sin OCR. Verificado en
      vivo contra dos fuentes reales: un PDF del Registro Oficial linkeado
      desde `get_regulacion_info` (77 páginas) y un boletín estadístico del
      IESS (142 páginas) — ver detalle en la nota de IESS más abajo.
- [x] **Prompts de flujo de trabajo adicionales** (`@mcp.prompt()`) — agregado
      `explorar_tema`, guía transversal a todas las fuentes (datasets,
      trámites, regulaciones, contratos, riesgos) en una sola pasada.
- [x] **Descartar columnas de geometría/WKT** antes de renderizar previews de
      GeoJSON/CSV — ya hecho (ver CHANGELOG 0.5.1): `preview_json`/`preview_csv`
      descartan columnas de geometría/WKT detectadas por nombre o contenido.
      Este ítem había quedado desactualizado en el roadmap.
- [x] **Parseo de decimales en formato europeo** (`7.760,2` = 7760.20) — ya
      hecho (ver CHANGELOG 0.5.1): se detecta y convierte a notación estándar
      en CSV. Este ítem había quedado desactualizado en el roadmap.
- [x] **Soporte `.ods`** (OpenDocument Spreadsheet) — hecho 2026-08-28:
      `preview_resource_data` previsualiza `.ods` como tabla vía `odfpy`
      (pura Python, sin binario externo), mismo patrón que
      `preview_xls`/`preview_xlsx`. `helpers/csv_reader.preview_ods` filtra
      el padding de columnas/filas vacías repetidas que ODS usa para
      rellenar la grilla fija de la hoja. Verificado en vivo contra un
      recurso real de Cuenca en Datos (actas del Concejo Cantonal,
      `gadcuenca_actas_pm_2026julio.ods`): headers y filas correctos,
      tildes incluidas.
- [x] **Soporte `.rar`** — **decidido en contra, 2026-08-28.** A diferencia
      de CSV/XLS/XLSX/ODS/ZIP/TAR.GZ (todos parseables con una librería
      Python pura sobre bytes en memoria), RAR usa compresión propietaria
      sin decodificador Python — la única forma de abrirlo es invocar un
      binario externo (`unrar`/`unar`/`bsdtar`) como subproceso sobre un
      archivo descargado de una fuente no confiable. Eso es una categoría
      de riesgo distinta a la que tiene el resto del proyecto, no solo más
      código: una imagen Docker más pesada, una dependencia de sistema que
      mantener, y superficie de ataque de un binario de extracción con
      CVEs históricos reales, todo para un tool de solo-lectura. Se llegó a
      implementar (`preview_rar` vía `rarfile`) y se revirtió antes de
      mergear. `download_resource(resource_id, format="json")` ya cubre el
      caso de uso real: baja el archivo `.rar` completo (base64, hasta
      5 MB) para que se abra con las herramientas que ya tenga quien esté
      usando el cliente MCP, sin correr nada en el servidor.
      `preview_resource_data` sigue señalando el caso explícitamente
      (`rar_no_soportado`) y apuntando a `download_resource`.
- [x] **Recursos sin extensión** — hecho: cuando ni la extensión de URL ni el
      `format` declarado por CKAN son reconocibles, `preview_resource_data`
      hace un sniff best-effort del header HTTP `Content-Type`
      (`helpers/csv_reader.sniff_content_type`, solo lee headers, no baja el
      body) antes de rendirse con `formato_no_soportado`. Solo se activa
      cuando la clasificación normal da `UNKNOWN` — un `format` vacío ya
      caía en el default histórico de "asumir CSV", así que el sniff cubre
      el caso más angosto de un `format` declarado pero irreconocible
      (ej. `PDF`) combinado con una URL sin extensión.
- [x] **Detección de `.tar.gz`** — encontrado real durante la verificación
      e2e (2026-08-16): el dataset `contribuyentes-activos-catastro-2025`
      del SRI (declarado formato CSV en CKAN) en realidad se descarga como
      `sri_activos_2025.tar.gz`. **Corregido 2026-08-17:** el bug real era
      que `preview_resource_data` confiaba en el `format` declarado por
      CKAN *antes* que en la extensión de la URL, así que un `.tar.gz`
      declarado CSV terminaba enviado al parser de CSV en vez de cualquier
      mensaje de error. Ahora la extensión de URL (cuando es reconocible)
      tiene prioridad sobre el `format` declarado, y `.tar.gz` tiene su
      propio caso. **Previsualización de contenido agregada:**
      `preview_resource_data` descomprime el `.tar.gz` (`tarfile` + `zlib`,
      stdlib, sin dependencia nueva) y muestra el CSV/TSV/TXT interno como
      tabla — si hay varios archivos dentro, prioriza `.csv` > `.tsv` >
      `.txt` en vez del primero del archivo (evita que un `readme.txt`
      empaquetado gane sobre el dato real). La descompresión tiene un tope
      de 20 MB para acotar el impacto de un archivo diseñado para expandirse
      desproporcionadamente al descomprimirlo.
- [x] **Soporte `.xls` legacy** — hecho: `preview_resource_data` previsualiza
      `.xls` como tabla vía `xlrd` (pura Python, sin binario externo). Antes
      solo devolvía `xls_no_soportado` con un puntero a `download_resource`;
      ahora usa `helpers/csv_reader.preview_xls`, misma forma que
      `preview_xlsx`.
- [x] **Soporte `.zip`** — hecho: `preview_resource_data` descomprime el
      `.zip` (`zipfile`, stdlib, sin dependencia nueva) y muestra el
      CSV/TSV/TXT interno como tabla, con la misma prioridad `.csv` > `.tsv`
      > `.txt` que `.tar.gz`. A diferencia de `.tar.gz`, el directorio
      central de un `.zip` lista los miembros sin descomprimir nada, así que
      no hace falta un paso de descompresión con tope por adelantado —
      basta con acotar la lectura del único miembro elegido para evitar que
      un archivo diseñado para expandirse desproporcionadamente agote
      memoria. Lógica de selección de miembro compartida con `.tar.gz` vía
      `helpers/csv_reader._pick_member`.

## Verificación end-to-end pendiente

Cifras de referencia contra el mismo portal (`www.datosabiertos.gob.ec`),
para confirmar que los tools devuelven los números correctos, no solo que no
truenan:

- [x] **SRI** `contribuyentes-activos-catastro-2025` → 2,904,355
      contribuyentes en el mes más reciente vía `sum(TOTAL)`, **no**
      `count(*)` (que da 405,794). **Verificado 2026-08-16 contra el portal
      real (con VPN a LatAm, ver nota de bloqueo geográfico):** cifras
      exactas — noviembre (mes más reciente) `sum(TOTAL)` = 2,904,355,
      `count(*)` total = 405,794. **Hallazgo nuevo:** el único recurso CSV
      del dataset (`sri_activos_2025.csv`) en realidad se descarga como
      `sri_activos_2025.tar.gz` (5.4 MB comprimido) — `preview_resource_data`
      ahora lo detecta correctamente (ver ítem `.tar.gz` arriba), pero
      todavía no lo previsualiza como tabla, solo lo ofrece vía
      `download_resource`.
- [x] **IESS** `base-de-datos-seguro-desempleo`, junio 2026 → 2,561
      beneficiarios, USD 836,716.99, excluyendo la fila `TOTAL:` embebida en
      el archivo (incluirla da exactamente el doble). **Verificado
      2026-08-16:** cifras exactas. **Hallazgo nuevo:** el dataset tiene
      *dos* recursos distintos con nombres casi idénticos para el mismo mes
      ("Pagos Desempleo Junio 2026" y "Numero de beneficiarios y montos
      pagados... a Junio 2026") — el primero es un resumen mensual acumulado
      del año completo (una fila por mes desde enero), el segundo es el
      detalle por provincia/género con la fila `TOTAL:` real. Mismo tipo de
      ambigüedad de nombres que ya motivó el pendiente de detección
      acumulado-vs-incremental — confirma que ese pendiente sigue siendo
      necesario, no es un caso aislado.
- [x] **MPCEIP** cacao → junio 2026, Grado 1 semanal: 174.77 / 168.15 /
      166.28 / 188.07, usando solo el archivo más reciente. **Verificado
      2026-08-16:** cifras exactas contra
      `6.-MPCEIP_PRECIO_FOB_EXPORTACIONES-CACAO_JUN_2026.xlsx`. **Hallazgo
      nuevo:** ese recurso está declarado `format: CSV` en la metadata de
      CKAN pero la URL real es `.xlsx`. **Corrección 2026-08-17:** a pesar
      de lo que decía esta nota antes, `preview_resource_data` *no*
      resolvía esto — el `format` declarado (`CSV`) se evaluaba antes que
      la extensión de la URL, así que este recurso también terminaba en el
      parser de CSV en vez del de XLSX. Mismo fix que el caso `.tar.gz` del
      SRI arriba: ahora la extensión de URL tiene prioridad. Confirma que
      confiar solo en el campo `format` de CKAN no alcanza.
- [x] **Cobertura real de formatos contra el portal en vivo: `.xls`/`.zip`.**
      **Verificado 2026-08-26 contra el portal real:** `.xls` funciona limpio
      — `agrocalidad_centros-de-faenamiento-certificados-con-mabio_dd_2021.xls`
      (resource `4d756998-8f91-4bf9-9edd-6395bac99dfe`) se previsualiza con
      acentos correctamente decodificados (`ó` = `0xf3`, confirmado a nivel
      de code point — lo que parecía verse mal era solo la consola de
      Windows, no un bug de decodificación real). **Tres hallazgos reales de
      `.zip` que llevaron a fixes, no solo confirmación:**
      1. Un `.zip` real de 17 MB (`organizacion-territorial-cantonal.zip` y
         `mag_estimacionesprimerperiodo_2020.zip`) truncado a los 5 MB de
         descarga falla *por completo* al abrir (`zipfile.BadZipFile: File
         is not a zip file`), no de forma parcial — el directorio central de
         un `.zip` vive al final del archivo. Antes esto daba un genérico
         "está corrupto o incompleto"; ahora `preview_zip`/`preview_targz`
         detectan la verdad (`truncated=True` de la descarga) *antes* de
         intentar parsear y dan un mensaje específico apuntando a
         `download_resource`.
      2. Un `.zip` real sin ningún archivo tabular
         (`mag_carbonoorganico_2021junio.zip`: solo `.lyr`/`.tif`/`.tif.aux.xml`,
         paquete GIS raster) hacía que `_pick_member` cayera de vuelta al
         primer archivo del `.zip` y lo forzara al parser de CSV, crasheando
         con un `csv.Error` crudo sin capturar. `_pick_member` ya no cae a
         "el primero que sea"; devuelve `None` cuando ningún miembro parece
         tabular, y ambos previews dan un mensaje claro listando los
         archivos reales encontrados.
      3. `_parse_csv_bytes` no capturaba `csv.Error` en absoluto (repro real:
         un `\r` suelto sin comillas dentro de un campo) — ahora se captura
         y se traduce a un `ValueError` accionable en vez de una excepción
         cruda de Python.
- [x] **Degradación cuando el portal no responde.** **Confirmado y
      corregido 2026-08-26:** un `httpx.ConnectTimeout`/`ConnectError` real
      se puede stringificar como `""` o `"timed out"`, sin mencionar el host
      — confirmado con `str(httpx.ConnectTimeout(...))`. `helpers/ckan_client._fetch_json`
      ahora distingue `HTTPStatusError` (ya trae URL+status vía
      `raise_for_status()`) de `RequestError` (fallos de conexión/timeout),
      y en el segundo caso levanta un `RuntimeError` que sí nombra el host y
      el tipo de fallo.

## Arquitectura, más adelante

- [ ] **Salidas estructuradas vía `outputSchema` de MCP** — hoy todos los
      tools devuelven texto o un string JSON; falta usar salida estructurada
      real del protocolo donde aplique.
- [ ] **Manejo geoespacial de recursos** — sin diseñar.
- [ ] **Tool `research` de una sola llamada** que encadene
      descubrimiento → selección → consulta en un solo round trip, para
      reducir la cantidad de llamadas que necesita el modelo en una
      exploración típica.

---

## Notas

**Corrección de diagnóstico (2026-08-13):** el 403 de CKAN que se creía un
bloqueo geográfico/upstream era en realidad un bug de vhost — el apex
`datosabiertos.gob.ec` y el subdominio `presidencia` resuelven a la misma IP
pero devuelven 403; solo `www.datosabiertos.gob.ec` está conectado. Ya
corregido en el repo; los 38 tools funcionan.
