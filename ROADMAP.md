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
      mismo problema que Superbancos: visual-only, sin endpoint consultable
      programáticamente. Si el registro de títulos vive en algún lado
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
- [ ] **Sitios de ministerios individuales** — sin alcance definido; falta
      decidir cuáles justifican una conexión propia en vez de depender del
      portal CKAN central.

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
