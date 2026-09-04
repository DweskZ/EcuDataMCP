# Roadmap

Lista corta y accionable de lo que falta, lo que está parcial, y lo que se
decidió no hacer. Las fuentes de datos ya completadas al 100% se sacaron de
aquí para no inflar la lista — viven en [SOURCES.md](SOURCES.md). Para el
porqué de cada ítem — hallazgos, cifras verificadas, dominios investigados,
dead ends confirmados — ver [RESEARCH.md](RESEARCH.md).

Leyenda: `[ ]` sin empezar · `[~]` parcial · `[x]` hecho

## Dirección de producto: portable y usable desde móvil

- [ ] **Separar cliente y despliegue** — mantener `stdio` para uso local, pero
      ofrecer una imagen Docker multi-arquitectura (`linux/amd64` y
      `linux/arm64`) y una configuración solo por variables de entorno. El
      agente del teléfono no debe instalar Python, descargar datos ni guardar
      una base de datos: debe consumir un único endpoint MCP remoto por HTTPS.
- [~] **Endpoint remoto para agentes** — el proceso ya admite autenticación Bearer,
      HTTPS directo mediante certificados Uvicorn, límite global y límite por
      cliente/IP, además de `/health`. Sigue pendiente publicar la instancia
      estable detrás de un proxy HTTPS, con DNS, secretos y operación real.
      El endpoint público no debe depender de `localhost`, del disco del
      desarrollador ni de una terminal abierta.
- [ ] **Persistencia portable** — separar el proceso MCP del almacenamiento:
      volumen/objeto persistente para cachés y artefactos grandes, backups,
      restauración y una ruta de actualización reproducible. El servidor debe
      poder recrearse desde la imagen sin perder el estado actualizado.
- [~] **Contrato de respuesta para agentes** — BCEData/IEM ya incluyen el
      bloque estable `metadatos` con fuente, URL, fecha de publicación/corte,
      fecha de consulta, frescura y esquema semántico, sin romper los campos
      históricos. Falta extender el contrato a las demás fuentes y migrar los
      resultados MCP nativos desde texto dual (`format=text|json`) a schemas
      estructurados completos. Los archivos grandes deben quedarse en el
      servidor; el agente debe recibir resultados paginados o enlaces, no
      cientos de megabytes.
- [~] **Operación 24/7** — `.github/workflows/smoke.yml` corre
      `scripts/smoke_e2e.py` diariamente contra un servidor recién
      levantado (~39/68 tools cubiertos), separado de `ci.yml`.
      Pendiente: alertas específicas de cambio de esquema. → RESEARCH.md
      § Infraestructura operativa

## Nuevas conexiones de datos

### Mapa de datos de alta frecuencia, aportado por Daniel 2026-08-31

Tabla de candidatos de alta frecuencia que Daniel trajo de su propia
investigación — cruzada contra el estado real de este roadmap, no
copiada tal cual:

| Fuente | Frecuencia | Qué mide | Estado en este proyecto |
|---|---|---|---|
| BCE, producción petrolera | Diaria | Barriles producidos | [x] hecho — `datos_hid.json` vía `get_bce_indicador_diario`, ver SOURCES.md § BCE |
| BCE, riesgo país | Diaria | EMBI Ecuador | [x] hecho — `datos_formulario.json`, el hallazgo que arrancó esta familia de indicadores |
| BCE, oro/WTI/Dow Jones/SOFR | Diaria | Mercados y precios internacionales | [x] hecho — `datos_diarios.json` |
| CENACE, Información Operativa | Horaria/diaria | Demanda eléctrica, generación, despacho | [x] hecho — `get_cenace_tablero`, snapshot en vivo (no serie histórica), ver SOURCES.md § Sector eléctrico |
| SIPA/MAG, precios mayoristas | Diaria o quincenal según producto | Precios mayoristas de alimentos | [ ] Descartado como fuente de alta frecuencia — solo boletines PDF mensuales y un documento regulatorio de piso/techo de precio sin historia. App móvil "cgsin.precios" sin explorar. → RESEARCH.md § Duodécima pasada |
| INAMHI, Geoportal | Horaria/diaria | Lluvia, temperatura, caudales, estaciones | [x] hecho parcial (`geoservicios.inamhi.gob.ec`) — 222 capas WMS catalogadas, 199 con datos WFS reales; ver SOURCES.md § INAMHI. Sin capa de estaciones puntuales. |
| IG-EPN, sismos | Casi tiempo real | Sismos, magnitud, ubicación, profundidad | [x] hecho — `search_sismos`, la única fuente genuinamente de alta frecuencia ya integrada antes de esta pasada |
| DGAC/IFIS | Diaria | Vuelos y movimientos por aeropuerto | [x] METAR/NOTAM/SIGMET hecho (`ais.aviacioncivil.gob.ec`, ver SOURCES.md § Aviación civil) — pero la fila de Daniel apunta más bien a estadísticas de movimientos/vuelos por aeropuerto, que puede ser una sección distinta del mismo sitio (IFIS) sin explorar todavía; no asumir que es la misma sub-fuente que METAR/NOTAM/SIGMET. |

### Objetivo prioritario: cobertura completa del BCEData y del IEM

“Completa” aquí significa que el servidor descubre automáticamente todo lo
que la fuente expone, no que solo conozca los indicadores más conocidos. La
integración debe poder demostrar qué grupos, series, frecuencias, unidades,
fechas, boletines y archivos encontró, y cuáles no pudo leer.

- [~] **BCEData completo — catálogo y series**: cubrir todos los nodos hoja de
      `/tree`, el metadata de cada `/bundle/{id_grupo}` y todos los valores
      disponibles en `/grid`, con búsqueda de grupos y series internas y
      consulta explícita de cualquier frecuencia/unidad/período. Descubrimiento
      y consulta ya implementados; `auditar_grid=true` prueba un período
      reciente por combinación (límite 500, reporte persistente separado).
      Sigue pendiente comprobar cambios de revisión — el endpoint no expone
      ningún marcador explícito hoy, así que la comparación por contenido es
      la única evidencia disponible. → RESEARCH.md § Duodécima pasada
- [x] **BCEData completo — verificación de cobertura**: `audit_bce_catalog`
      consulta el árbol y metadatos de todos los grupos, registra qué falló y
      cuándo. `guardar_snapshot=true`/`comparar_anterior=true` detectan
      grupos/series nuevos, retirados o modificados. `scripts/audit_bce_catalog.py`
      deja el flujo listo para cron/scheduler. No depende de una lista fija de IDs.
- [~] **IEM completo — archivo y archivos fuente**: `search_bce_iem`
      reconcilia el índice, "Últimas publicaciones" y el archivo oficial
      `iem-publicaciones/` (367 boletines, No. 1727–2093, 1996–2026). El
      archivo completo cubre **tres eras** con lectores distintos: XLSX
      individuales (No. 1976–2093), ZIP de `.xls` legado por tabla (No.
      1854–1975) y HTML de frameset pre-moderno parseado a grilla (No.
      1727–1853). Pendiente: hashing masivo del histórico y confirmar que
      las 126 secciones más viejas siguen todas la misma forma (solo
      muestreado). → RESEARCH.md § Decimotercera pasada
- [x] **IEM completo — lectura de tablas**: valores buscables de todas las
      tablas individuales (formas ancha, larga, matriz), no solo títulos;
      normaliza meses numéricos/español, trimestres y tablas sin unidad
      explícita; vista fiel del original cuando no es seguro normalizar.
      Barrido en vivo: 98.7% de las tablas del boletín vigente se extraen
      ya en forma semántica; los `vista` restantes son tablas legadas con
      jerarquías de encabezado genuinamente irregulares, no una familia
      repetible. → RESEARCH.md § Duodécima pasada, § Decimotercera pasada
- [~] **BCEData ↔ IEM — mapa de equivalencias**: `compare_bce_sources` genera
      coincidencias candidatas por etiquetas normalizadas, confianza y
      campos pendientes de revisión; `guardar_revision=true` y
      `scripts/audit_bce_equivalence.py` persisten una cola revisable. Dos
      candidatos confirmados manualmente con datos en vivo (uno de
      equivalencia directa, uno de cobertura parcial tabla↔grupo); el
      resto no se trata como duplicado confirmado sin revisar valores y
      metodología. → RESEARCH.md § Duodécima pasada, § Decimotercera pasada
- [x] ~~BCE — prueba de completitud y frescura~~ **Descartado 2026-09-02**:
      requiere un scheduler con almacenamiento persistente de snapshots, que
      Daniel decidió no construir. `audit_bce_catalog`/`audit_bce_iem` ya
      hacen la comparación bajo demanda (no programada) cuando se invocan
      con `guardar_snapshot=true`/`guardar_catalogo=true`.

- [~] BCE — indicadores vía BCEData (`search_indicadores_bce`/`get_indicador_bce`).
      La cobertura confirmada es el catálogo BCEData que expone sus cuatro
      secciones principales (monetaria/financiera, finanzas públicas, sector
      externo y sector real); no debe describirse como todo el sistema de
      información del BCE.
- [~] Supercías — compañías, ranking financiero, auditores. La integración
      funciona, pero el ranking financiero todavía depende de una base SQLite
      local construida manualmente; la portabilidad y actualización automática
      quedan en los ítems específicos de abajo.
- [ ] **Supercías: pipeline financiero actualizable** — usar como fuente de
      datos masiva la página oficial de [Ranking de Compañías](https://appscvsmovil.supercias.gob.ec/ranking/reporte.html), que expone
      `bi_ranking.csv`, las tablas auxiliares y rankings anuales, y declara que
      sus archivos se actualizan cada 24 horas. Separar descarga, validación,
      transformación y publicación; no descargar los ~356 MB dentro de una
      solicitud MCP.
- [ ] **Supercías: refresh seguro y reproducible** — implementar un comando de
      actualización idempotente que compruebe metadatos/huella del archivo,
      descargue a staging, valide esquema, tamaño, filas, años, duplicados,
      nulos y tasas de conversión, construya índices SQLite y haga un reemplazo
      atómico solo después de pasar la validación. Guardar `source_url`,
      `fetched_at`, `source_last_modified` si existe y el hash de cada insumo.
- [ ] **Supercías: actualización diaria fuera del MCP** — ejecutar el refresh
      con cron, GitHub Actions o un scheduler del servidor; conservar la última
      base válida si la descarga falla y exponer su estado en `/health` o en un
      recurso de diagnóstico. El almacenamiento debe ser un volumen persistente
      o un artefacto remoto, no el filesystem efímero del contenedor.
- [ ] **Supercías: conservar toda la historia disponible** — dejar de eliminar
      automáticamente los años anteriores al último bloque de cinco. Construir
      una base histórica completa (la fuente actual documenta `bi_ranking.csv`
      desde 2008), con retención configurable (`all` o un número de años) y una
      tabla/recurso que informe exactamente qué años y variables están
      disponibles después de cada refresh.
- [ ] **Supercías: consultas históricas sin respuestas gigantes** — mantener
      cinco años como valor por defecto para una respuesta móvil, pero añadir
      filtros explícitos `desde`, `hasta` y `anio` para pedir cualquier período.
      Para análisis largos, añadir consultas resumidas por año, compañía, CIIU y
      métrica (crecimiento, promedio, máximo/mínimo), además de paginación para
      rankings; nunca enviar toda la historia de miles de compañías a un agente.
- [ ] **Supercías: almacenamiento histórico por capas** — usar SQLite completo
      e indexado para búsquedas por expediente/RUC y rankings pequeños; conservar
      los archivos fuente comprimidos por año como respaldo; evaluar Parquet o
      DuckDB solo para agregaciones grandes. La primera versión debe seguir
      funcionando en Docker sin exigir una base externa.
- [ ] **Supercías: comparabilidad entre años** — conservar columnas que hayan
      desaparecido como `null`, registrar cambios de esquema y documentar cuándo
      una razón financiera no es comparable entre años. No rellenar valores
      faltantes ni comparar silenciosamente definiciones distintas de CIIU,
      estados financieros o indicadores.
- [ ] **Supercías: distinguir diario de tiempo real** — etiquetar
      `search_ranking`/`get_financials` como `daily_bulk` con año fiscal y fecha
      de corte. Investigar aparte una consulta bajo demanda al Portal de
      Información oficial para una compañía concreta; usarla solo como
      `live_lookup` cuando el portal responda, con timeout, trazabilidad y
      fallback explícito a la última descarga válida. Nunca presentar el CSV
      diario como información en tiempo real.
- [~] Registro Civil / demográfico-salud — cobertura CKAN sólida, pero **corregido 2026-08-29**: "sin gaps" era incorrecto — `registrocivil.gob.ec` publica un dataset propio de defunciones a nivel de registro individual (2020-2025, `.xlsb`, con diccionario de variables) que no está en ninguno de los 6 datasets CKAN de la organización. `.xlsb` no está soportado hoy por `helpers/csv_reader.py`. → RESEARCH.md § Séptima pasada
- [~] IESS — boletines/auditorías/actuariales scrapeables y confirmados, sin construir tool nuevo. → RESEARCH.md § IESS
- [~] SENESCYT/Educación Superior — cubierto vía CKAN; registro de títulos bloqueado por captcha (no automatizable). → RESEARCH.md § SENESCYT
- [~] BCE — IEM/IEEM: mismo ítem que "IEM completo — archivo y archivos
      fuente" arriba (`search_bce_iem`/`get_bce_iem_table`), duplicado
      histórico de este roadmap. → RESEARCH.md § Séptima pasada
- [x] BCE — mismo ítem que "BCEData completo — verificación de cobertura"
      arriba (`audit_bce_catalog`). Conectarlo a un scheduler persistente
      fue descartado — Daniel decidió no construir esa infraestructura.
- [~] BCE — mismo ítem que "IEM completo — archivo y archivos fuente"
      arriba (catálogo histórico vía `guardar_catalogo=true`/
      `scripts/audit_bce_iem.py`).
- [ ] BCE — **búsqueda ampliada y mapa completo de fuentes**: revisar más allá de BCEData e IEM el sitio institucional, publicaciones temáticas, catálogos, archivos históricos y descargas por sector. Inventariar cada fuente, su cobertura, frecuencia, formato, API/archivo y traslape con lo ya integrado; priorizar únicamente tablas que añadan detalle ecuatoriano verificable, no duplicados de una misma serie. El resultado debe ser un mapa de cobertura y una lista corta de integraciones justificadas.
- [ ] BCE — **Cuentas Nacionales completas**: investigar los paquetes anual, trimestral y regional, retropolación, Tabla Oferta-Utilización, Cuadro Económico Integrado y Matriz de Empleo e Ingresos. IEM/BCEData pueden contener partes, pero la integración debe conservar la metodología de base móvil, revisiones, frecuencia y carácter provisional/definitivo. → https://contenido.bce.fin.ec/estadisticas-de-cuentas-nacionales/
- [~] BCE — **EMOE y coyuntura**: resuelto parcialmente vía el sistema de
  índices — expectativas económicas, confianza del consumidor, inflación y
  ciclo económico. Sigue pendiente: mercado laboral y pobreza/desigualdad,
  sin página índice encontrada para ninguno de los dos. → RESEARCH.md
  § Duodécima pasada
- [~] BCE — **catálogo de publicaciones, calendario y archivo histórico**:
  `search_bce_publicaciones` (`helpers/bce_publicaciones_client.py`) cubre
  "Últimas Publicaciones", pero solo expone su ventana rodante (~30 más
  recientes), sin parámetro de fecha ni paginación. Sigue pendiente: Cifras
  Económicas del Ecuador y el calendario de publicaciones futuras, en
  páginas distintas no investigadas todavía. → RESEARCH.md § Duodécima pasada
- [ ] Sector eléctrico (CENACE/ARCONEL/CNEL) — **dominio nuevo, pedido explícito
      de Daniel 2026-08-29**. CENACE (45), CNEL EP (40), ARCONEL/ARCERNNR (1
      dataset pero 54 recursos BNEE), e IIGE (19) ya tienen organización CKAN,
      alcanzables hoy. `reportes.arconel.gob.ec` **descifrado técnicamente**
      (ASP.NET ReportViewer, 3 POSTs con replay de ViewState + un POST final
      renderiza tablas HTML reales, sin login, 1998-2026 por parroquia/
      empresa/mes) — falta solo construir el scraper stateful; la fuente más
      rica del proyecto. CENACE Biblioteca tiene documentos de planificación
      sin tocar. EEQ/Centrosur/EERSA/EEASA sin organización CKAN propia.
      → RESEARCH.md § Octava pasada
- [ ] Sector eléctrico — **archivo histórico de cortes de luz programados,
      crisis sep-dic 2024** (registro de incidente histórico, no fuente
      continua). EEQ (Quito) sigue sirviendo en vivo los PDFs originales
      barrio/hora de la crisis — solo hace falta enumerar los slugs. CNEL
      (Guayaquil/costa, el objetivo más grande) probablemente perdió el
      archivo de su sitio en vivo; reintentar con Wayback Machine. → RESEARCH.md
      § Octava pasada
- [ ] Ministerio de Salud Pública (`salud.gob.ec`) — dominio confirmado vivo con contenido real (barrido de endpoints 2026-08-29), sección de transparencia/LOTAIP presente, pero sin sección de estadísticas/datos abiertos visible en la portada — no se profundizó más allá de confirmar que el sitio está vivo, falta una pasada de contenido completa. → RESEARCH.md § Séptima pasada
- [ ] Registro Oficial (gaceta oficial) — candidato de alta prioridad para búsqueda por fecha; posiblemente no relevante, ver nota de alcance. → RESEARCH.md § Datos legislativos
- [ ] Superbancos — Balances Generales/Patrimonio Técnico/indicadores de
      morosidad-liquidez-solvencia siguen sin resolver — viven detrás de una
      herramienta de consulta propia, no de un widget OneDrive; necesitan una
      pasada con browser. Catastro de Compañías bloqueado por login,
      descartado. → RESEARCH.md § Séptima pasada
- [ ] Permisos y portales municipales — sin investigar, alcance grande (~221 GADs). → RESEARCH.md § Permisos municipales
- [ ] IGM Geoportal — cartografía gated tras registro/login, no automatizable tal cual. → RESEARCH.md § Sitios de ministerios individuales
- [ ] Fuentes externas de sociedad civil (FCD, FARO) — corregido: sí hay datasets tabulares reales (votaciones de la Asamblea, declaraciones patrimoniales de funcionarios, ordenanzas municipales de Quito/Guayaquil), verificados en vivo; decisión de alcance sigue pendiente (no es "gobierno"). FARO en sí no tiene portal de datos. `cuentasclaras.org` está comprometido con spam, no tocar. → RESEARCH.md § Fuentes externas
- [ ] Gremios privados (AEADE, ASOBANCA, FEDEXPOR) — AEADE y FEDEXPOR confirmados y descargables; ASOBANCA Datalab sin resolver extracción (SPA). → RESEARCH.md § Gremios
- [ ] **CORDES — Corporación de Estudios para el Desarrollo** — investigar su [base de variables macroeconómicas y entregas periódicas](https://www.cordes.org/): cobertura histórica, frecuencia, acceso descargable/API, definiciones y traslape con BCE/INEC. El sitio tiene protección anti-bot, así que primero hay que confirmar qué parte es automatizable y qué parte queda como publicación/documento. CORDES aparece también entre los participantes de la Encuesta de Expertos, pero no asumir que ambos productos son la misma fuente. → RESEARCH.md § Fuentes externas
- [ ] **Nowcast / Encuesta de Expertos — Previsiones de la Economía del Ecuador** — investigar e integrar, si el acceso y la licencia lo permiten, las previsiones/nowcasts de PIB, empleo adecuado, desempleo e inflación. Separar claramente estimación de dato observado y conservar fecha de publicación, horizonte, metodología, participantes y revisiones. El [sitio público de Nowcast](https://www.expertoseconomia.org/es/) presenta estos cuatro indicadores mediante visualizaciones Datawrapper; sus páginas anuales incluyen además déficit fiscal, riesgo país y precio del petróleo. → RESEARCH.md § Fuentes externas
- [ ] **Calidad del aire de Quito — `aireambiente.quito.gob.ec`.** El dominio
      responde pero sin contenido en el HTML crudo — parece SPA que renderiza
      todo por JS (probablemente la red REMMAQ); necesita una pasada con
      browser real o encontrar su API subyacente.
- [ ] **Cancillería y embajadas — dominio(s) sin identificar, pedido explícito de Daniel 2026-08-31** ("cancilleria, embajadas, etc."). Sin investigar: `cancilleria.gob.ec` ya aparece mencionado de pasada en la Séptima pasada como uno de los dominios vivos del hosting compartido del Estado, pero nunca se hizo una pasada de contenido dedicada — trámites consulares, apostillas, estadísticas migratorias, o datos de la red de embajadas/consulados son candidatos sin confirmar.
- [~] **ARCSA** — 4 datasets CKAN reales, pero solo registros
      suspendidos/cancelados. El dato valioso (registro sanitario *vigente*,
      "Base de Registros Emitidos" en `controlsanitario.gob.ec`) no se pudo
      verificar: el dominio está caído (reset TLS). Pendiente: reintentar
      más adelante antes de descartarlo del todo. → RESEARCH.md § Décima
      pasada
- [ ] Vivienda MIDUVI — dominio caído a nivel TLS, sin reemplazo encontrado; CKAN cubre parcialmente. → RESEARCH.md § Vivienda
- [ ] Prensa — SECOM/Presidencia y Fundamedios, sin profundizar. → RESEARCH.md § Prensa
- [ ] Datos legislativos/normativos (jurisprudencia, proyectos de ley) — investigado a fondo; **Daniel señaló que puede no ser relevante** para el alcance del proyecto. → RESEARCH.md § Datos legislativos
- [ ] Fuentes internacionales con foco Ecuador — investigar **CEPAL/CEPALSTAT**, el **FMI/IMF** (pedido explícito de Daniel 2026-08-30: variables macro trimestrales — candidatos concretos son IFS/International Financial Statistics para series trimestrales de balanza de pagos/reservas/tipo de cambio, el WEO database para proyecciones, y los Article IV Staff Reports para el análisis narrativo con series propias), agencias de la **ONU** y, cuando tengan datos específicamente útiles para Ecuador, Banco Mundial, OIT, FAO, OMS/OPS, UNESCO, OIM y organismos regionales. Para cada fuente: confirmar acceso real (API/bulk/archivo — el FMI tiene una API REST pública para IFS/WEO sin key, por confirmar cobertura y campos exactos para Ecuador), indicador y desagregación disponibles para Ecuador, historia, frecuencia, licencia, fecha de actualización y duplicación frente a INEC/BCE/ministerios. Integrar solo lo que aporte una serie, corte o frecuencia (ej. trimestral cuando BCE solo publica mensual/anual) que la fuente ecuatoriana no publique; conservar siempre fuente y definición original — el valor de estas fuentes suele ser la comparabilidad internacional y la metodología armonizada, no un dato más nuevo que el de BCE/INEC. CEPAL y FMI son los primeros candidatos. → RESEARCH.md § Fuentes externas
- Confirmados sin acción posible (bloqueos reales, no falta de esfuerzo): CNE y micrositio de Interior (WAF Incapsula), Aduana/SENAE comercio exterior (no publicado, solo por oficio — FEDEXPOR cubre el hueco), Fiscalía (sin dataset agregado propio), Supercías Valores/Seguros (login-gated, casi todo, un solo PDF estático encontrado), SERCOP catálogo/órdenes de compra (CAPTCHA), IG-EPN `descarga-de-datos` (cuenta obligatoria), Superbancos Catastro de Compañías (login obligatorio). → RESEARCH.md § Sitios de ministerios individuales / § Séptima pasada
- [~] **SRI Saiku — `list_sri_saiku_cubes`, `describe_sri_saiku_cube`, `query_sri_saiku_aggregate`**: construidos como superficie anónima, de solo lectura y limitada a una dimensión/medida y 100 filas. La sesión, descubrimiento y metadatos se validan antes de consultar; no se permite MDX arbitrario, drill-through, exportación ni escritura. Pendiente: verificación contra el endpoint vivo desde un entorno con conectividad; la sesión actual no pudo alcanzar el host SRI.
- ANDA — reconfirmado 2026-08-29: cobertura completa (437 encuestas, coincide con lo ya documentado), sin gap real, solo una limitación menor de UX (no se puede filtrar por tema del lado del servidor). **Corregido 2026-08-29 (segunda revisión, pedido de Daniel): "sin gap real" era incorrecto para ENEMDU específicamente** — ver el ítem nuevo de abajo (ENEMDU/mercado laboral post-2023 sin cubrir en ningún tool actual). → RESEARCH.md § Séptima pasada / § Novena pasada
- [x] `read_pdf` ahora valida extensión/Content-Type antes de descargar (2026-08-30) — rechaza extensiones conocidas no-PDF (.zip/.xlsx/.csv/...) sin hacer ninguna petición, y cuando la URL no tiene extensión reconocible cae a un sniff de Content-Type (solo headers, sin cuerpo) antes de comprometerse a la descarga completa. Antes bajaba hasta 5 MB de un ZIP grande inútilmente antes de fallar con "no es un PDF válido".
- [~] **INEC (y en general): no hay preview de archivos grandes (ZIP/BDD), a
      diferencia de CKAN.** `get_inec_publicacion_archivos`/`get_topic_files`
      solo devuelven metadata (label/url/formato) por diseño (igual que
      SIPA). **Hecho:** `list_zip_contents` lee solo el directorio central
      del ZIP vía HTTP Range para listar miembros sin descargar todo (no
      soporta ZIP64). Decidido en contra: un índice local pre-construido por
      dataset (solo si se justifica por uso repetido) y cualquier mecanismo
      general de transferencia de archivo completo — la respuesta correcta
      para una descarga puntual sigue siendo la URL directa.
- [~] **CEPAL — geoportal del Censo Ecuador (`geo.cepal.org/censo-ecuador/`).**
      9 capas reales de Ecuador vía `geoportal.cepal.org/api/v2/datasets/`,
      pero derivadas del Clasificador Geográfico de INEC (fuente primaria,
      ver SOURCES.md § INEC / Ecuador en Cifras) — bajo valor salvo que
      interese la geometría ya lista para mapas. `geodata.cepal.org/api/v1`
      seguía devolviendo 502.

## Cabos operativos sueltos

- [x] Renovación de certificado TLS.
- [x] **`helpers/tls.py` — fallback "OS trust store" reemplazado por CA
      intermedia embebida.** El smoke test diario falló en un runner Linux
      limpio (`CERTIFICATE_VERIFY_FAILED`) porque el fallback anterior
      dependía de la extensión AIA de Windows/macOS. Las dos CAs intermedias
      faltantes (Sectigo) se embebieron en
      `helpers/certs/sectigo_public_server_auth_intermediates.pem`, y
      `os_trust_context()` construye el contexto de forma determinista en
      cualquier plataforma. → RESEARCH.md § Infraestructura operativa

## Calidad de búsqueda y detección de series

- [x] Expansión de siglas/acrónimos en búsqueda.
- [x] `detect_series_pattern` — clasifica acumulado/incremental/indeterminado, verificado en vivo contra IESS y MPCEIP. → RESEARCH.md § detect_series_pattern
- [ ] Búsqueda semántica sobre el catálogo completo (hoy es solo keyword de CKAN).

## Formatos y tipos de recursos

- [x] `read_pdf`, prompts, stripping de geometría/WKT, decimales europeos, `.ods`, recursos sin extensión, `.tar.gz`, `.xls` legacy, `.zip` (truncado / sin miembro tabular / CSV malformado).
- [x] `.rar` — decidido explícitamente en contra (riesgo de subprocess/CVE), no implementar.

## Verificación end-to-end

- [x] Cifras reales verificadas contra el portal: SRI, IESS, MPCEIP, `.xls`/`.zip`, degradación cuando el portal no responde. → RESEARCH.md § Verificación end-to-end de cifras

## Arquitectura, más adelante

- [ ] **Simplificar y armonizar la arquitectura MCP** — reducir duplicaciones
      en la superficie pública, separar las herramientas de mantenimiento,
      conservar nombres existentes por compatibilidad y migrar gradualmente a
      esquemas, resultados y errores estructurados. El diagnóstico, el diseño
      propuesto y los criterios para decidir qué fusionar están en
      [docs/MCP_ARCHITECTURE.md](docs/MCP_ARCHITECTURE.md).
- [ ] `outputSchema` en los tools MCP.
- [ ] Manejo geoespacial (WKT/GeoJSON más allá del stripping actual).
- [x] Tool de investigación "one-shot" — `investigate_dataset`, construido 2026-08-31. Encadena `search_datasets` → `list_dataset_resources` → `preview_resource_data` en una sola llamada (toma el dataset mejor rankeado y previsualiza su primer recurso en un formato legible, saltando `.rar`/desconocidos en vez de previsualizar ciegamente lo primero de la lista) y avisa cuando el dataset parece publicar una serie periódica, señalando `detect_series_pattern` en vez de reimplementar esa heurística.
- [x] Protección HTTP base — `/mcp` admite Bearer token opcional, el bind local
      es loopback por defecto y existe un límite global de concurrencia; `/health`
      queda libre para health checks.
- [~] Rate limiting por usuario/IP y proxy HTTPS — el servidor ya aplica cuotas
      por cliente/IP además del límite global, exige token cuando
      `MCP_REQUIRE_AUTH=1` y puede terminar TLS directamente con Uvicorn.
      Sigue pendiente configurar el proxy HTTPS, DNS y la política operativa
      del endpoint remoto real.
- [ ] Type-checking en CI (mypy/pyright) — ruff cubre estilo/imports pero no
      errores de tipo; el repo ya está tipado casi en su totalidad. Riesgo:
      podría destapar errores preexistentes en los 40+ archivos que
      necesitarían triage antes de que CI pase en verde — no es un cambio
      chico, evaluar alcance antes de prender el gate.

## Notas

- 2026-08-13: el 403 de CKAN que parecía bloqueo geográfico era un bug de vhost (`www.datosabiertos.gob.ec` es el único subdominio conectado) — ya corregido.
- 2026-08-29: la conclusión "FCD/FARO son solo análisis narrativo, sin datos crudos" era incorrecta — se basaba en revisar un solo dominio (`gastopublico.org`) de los nueve que tiene FCD. Daniel señaló que el Observatorio Legislativo sí tabula las votaciones de la Asamblea; verificado en vivo, y de paso se encontraron datasets reales en otros tres dominios de la red. → RESEARCH.md § Fuentes externas
- 2026-08-29: escaneo profundo de Superbancos + segunda pasada sobre toda fuente ya integrada (menos INEC) + sector eléctrico como dominio nuevo. Patrón que se repite: una conclusión "sin gaps" o "ya cubierto" basada en revisar un solo lugar (CKAN, o un solo scraper) casi siempre se equivoca — Registro Civil es el ejemplo más claro (dataset real de defunciones fuera de CKAN). Lección para futuras pasadas: siempre revisar el sitio propio de la institución, no solo su organización CKAN. → RESEARCH.md § Séptima pasada
- 2026-08-29: barrido de endpoints muertos/renombrados en ministerios y funciones del Estado no auditados antes. Dos renombres nuevos confirmados vía falla de certificado TLS (no redirect): Transporte y Obras Públicas → MIT (`mit.gob.ec`), MIES → fusionado en "Ministerio de Trabajo y Desarrollo Humano" (`desarrollohumano.gob.ec`, tiene un portal "InfoDH" sin explorar). Un redirect correcto nuevo: Planificación → Presidencia. Se confirmó directamente (por primera vez, no por inferencia) la lista completa de dominios que comparten el certificado TLS del hosting compartido del Estado — ~26 dominios. Todo lo demás revisado (Salud, Cancillería, Defensa, Telecomunicaciones, Presidencia, Vicepresidencia, Asamblea sitio propio, Judicatura, TCE) está vivo con contenido real. → RESEARCH.md § Octava pasada
