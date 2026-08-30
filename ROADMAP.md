# Roadmap

Lista corta y accionable de lo que falta, lo que está hecho, y lo que se
decidió no hacer. Para el porqué de cada ítem — hallazgos, cifras
verificadas, dominios investigados, dead ends confirmados — ver
[RESEARCH.md](RESEARCH.md).

Leyenda: `[ ]` sin empezar · `[~]` parcial · `[x]` hecho

## Dirección de producto: portable y usable desde móvil

- [ ] **Separar cliente y despliegue** — mantener `stdio` para uso local, pero
      ofrecer una imagen Docker multi-arquitectura (`linux/amd64` y
      `linux/arm64`) y una configuración solo por variables de entorno. El
      agente del teléfono no debe instalar Python, descargar datos ni guardar
      una base de datos: debe consumir un único endpoint MCP remoto por HTTPS.
- [ ] **Endpoint remoto para agentes** — publicar una instancia estable detrás
      de HTTPS, autenticación (token inicialmente; OAuth si el cliente móvil lo
      exige), límite por usuario/IP, health check y logs con `request_id`. El
      endpoint público no debe depender de `localhost`, del disco del
      desarrollador ni de una terminal abierta.
- [ ] **Persistencia portable** — separar el proceso MCP del almacenamiento:
      volumen/objeto persistente para cachés y artefactos grandes, backups,
      restauración y una ruta de actualización reproducible. El servidor debe
      poder recrearse desde la imagen sin perder el estado actualizado.
- [ ] **Contrato de respuesta para agentes** — completar `outputSchema`,
      incluir siempre fuente, URL, fecha de publicación/corte, fecha de
      consulta y nivel de frescura, y mantener respuestas pequeñas para uso
      móvil. Los archivos grandes deben quedarse en el servidor; el agente debe
      recibir resultados paginados o enlaces, no cientos de megabytes.
- [ ] **Operación 24/7** — añadir una tarea programada separada del proceso MCP,
      reintentos, alertas cuando una fuente cambie de esquema o deje de
      responder, y una prueba de humo periódica desde fuera del servidor.

## Nuevas conexiones de datos

- [x] SRI — datasets page (`search_sri_datasets`).
- [x] BCE — indicadores vía BCEData (`search_indicadores_bce`/`get_indicador_bce`).
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
- [x] IG-EPN — catálogo sísmico (`search_sismos`).
- [x] Cuenca en Datos — CKAN municipal vía `source="cuenca"` en los tools genéricos.
- [~] Registro Civil / demográfico-salud — cobertura CKAN sólida, pero **corregido 2026-08-29**: "sin gaps" era incorrecto — `registrocivil.gob.ec` publica un dataset propio de defunciones a nivel de registro individual (2020-2025, `.xlsb`, con diccionario de variables) que no está en ninguno de los 6 datasets CKAN de la organización. `.xlsb` no está soportado hoy por `helpers/csv_reader.py`. → RESEARCH.md § Séptima pasada
- [x] Ecuador en Cifras / INEC — `search_inec_estadisticas`/`get_inec_estadistica_files` (~75 temas: boletines + series históricas agregadas) + `search_biinec_extras` (lista curada de los 2-3 registros de BIINEC que sí son exclusivos — desechos peligrosos en salud, módulos ambientales ENEMDU/ECV; no un cliente genérico, ver análisis de costo/beneficio en RESEARCH.md). → RESEARCH.md § Ecuador en Cifras
- [~] IESS — boletines/auditorías/actuariales scrapeables y confirmados, sin construir tool nuevo. → RESEARCH.md § IESS
- [~] SENESCYT/Educación Superior — cubierto vía CKAN; registro de títulos bloqueado por captcha (no automatizable). → RESEARCH.md § SENESCYT
- [~] BCE — Información Estadística Mensual (IEM/IEEM), boletín mensual mucho más rico que BCEData. `search_bce_iem` indexa en vivo las tablas XLSX individuales del boletín vigente y, con `historico=true` o un rango de años, agrupa versiones de la misma tabla en el archivo mensual. `get_bce_iem_table` devuelve series con filtro anual cuando detecta el formato tabular ancho, y reconoce también tablas largas; si no, preserva una vista segura sin inventar columnas. Pendiente: normalizadores dedicados y la comparación explícita con BCEData. **Profundizado 2026-08-29**: cada boletín (archivo completo desde ene-1996) tiene ~60+ XLSX individuales por tabla, no solo el ZIP. → RESEARCH.md § Séptima pasada
- [ ] BCE — **búsqueda ampliada y mapa completo de fuentes**: revisar más allá de BCEData e IEM el sitio institucional, publicaciones temáticas, catálogos, archivos históricos y descargas por sector. Inventariar cada fuente, su cobertura, frecuencia, formato, API/archivo y traslape con lo ya integrado; priorizar únicamente tablas que añadan detalle ecuatoriano verificable, no duplicados de una misma serie. El resultado debe ser un mapa de cobertura y una lista corta de integraciones justificadas.
- [x] SIPA (Ministerio de Agricultura) — `list_sipa_modulos`/`get_sipa_modulo_archivos`, 30 archivos Excel reales en 4 módulos (económico/productivo/social/censos), verificado en vivo. → RESEARCH.md § Sitios de ministerios individuales
- [x] Contraloría General del Estado — `list_contraloria_informes`/`get_contraloria_informe`, CSV trimestrales reales de informes de auditoría aprobados a cualquier institución pública, verificado en vivo. De paso corrigió un bug real en el sniffing de delimitador CSV compartido (`helpers/csv_reader.py`). → RESEARCH.md § Sitios de ministerios individuales
- [ ] Contraloría — "Plan anual de control", mismo patrón `WFDescarga.aspx` ya implementado en `helpers/contraloria_client.py` (solo cambia `tipo`) — esfuerzo casi nulo, se puede sumar al cliente ya existente. → RESEARCH.md § Séptima pasada
- [ ] SRI — `estadisticas-generales-de-recaudacion-sri`, reportes XLSX mensuales de recaudación por provincia/cantón/sector, separado y complementario a `/datasets` ya cubierto. → RESEARCH.md § Séptima pasada
- [ ] gob.ec — `tramites-transparencia/{tramite_id}`, serie mensual real de atenciones/quejas por trámite desde 2021, sin auth; hay que pedirla trámite por trámite (no hay endpoint masivo). → RESEARCH.md § Séptima pasada
- [ ] Sector eléctrico (CENACE/ARCONEL/CNEL) — **dominio nuevo, pedido explícito de Daniel 2026-08-29, profundizado el mismo día**. CENACE (45), CNEL EP (40), ARCONEL/ARCERNNR (1 dataset pero 54 recursos BNEE), e IIGE (19, tangencial) ya tienen organización CKAN, alcanzables hoy sin código nuevo. `reportes.arconel.gob.ec` **descifrado técnicamente** — ASP.NET ReportViewer, 3 POSTs secuenciales con replay de ViewState + un POST final renderiza tablas HTML reales, sin login, cubre 1998-2026 por parroquia/empresa/mes — la fuente más rica de todo el proyecto, ya no falta investigar cómo, solo construir el scraper stateful. CENACE Biblioteca tiene documentos de planificación sin tocar (Plan Maestro de Electricidad 2023-2032, Planes Operativos Anuales, factores de emisión CO₂, informes de indisponibilidad de transmisión). EEQ/Centrosur/EERSA/EEASA sin organización CKAN propia; Centrosur tiene 2 PDFs reales + Power BI. `sisdatbi.arconel.gob.ec` es un sistema BI interno con login, descartado. → RESEARCH.md § Octava pasada
- [ ] Sector eléctrico — **archivo histórico de cortes de luz programados, crisis sep-dic 2024** (ítem distinto al de arriba: es un registro de incidente histórico, no una fuente continua). EEQ (Quito) sigue sirviendo en vivo los PDFs originales barrio/hora de la crisis (`eeq.com.ec/documents/d/empresa-electrica-quito/{slug}`, confirmado descargando uno real de oct-2024) — no hace falta Wayback Machine, solo enumerar los slugs (naming manual/inconsistente). CNEL (Guayaquil/costa, el objetivo más grande) probablemente perdió el archivo de su sitio en vivo — reintentar con Wayback Machine (caído durante esta investigación) o adivinar rutas `wp-content/uploads/2024/09-12/`. CENACE/ARCONEL solo publicaron la capa regulatoria, no horarios por barrio. → RESEARCH.md § Octava pasada
- [ ] CNT/ARCOTEL (telecomunicaciones) — **dominio nuevo**. ARCOTEL ya tiene org CKAN (9 datasets, pero congelada desde 2021/2022) y CNT también (2 datasets, frescos). El hallazgo real está fuera de CKAN: Reportes Estadísticos Mensuales de ARCOTEL (PDF, serie completa 2023-2026, ~4 meses de rezago) — solo PDF, sin CSV/API. → RESEARCH.md § Octava pasada
- [ ] IG-EPN — `servicios/busqueda-informes`, buscador de informes sísmicos y volcánicos filtrable por tipo/volcán/fecha, sin login visible (distinto de `descarga-de-datos`, que sí requiere cuenta y queda descartado). → RESEARCH.md § Séptima pasada
- [ ] SGR — archivo de "Informes de Situación" (SITREP, 2016-2026) y "Biblioteca" (mapas de amenaza/vulnerabilidad, rutas de evacuación) en `gestionderiesgos.gob.ec`, fuera del snapshot ArcGIS ya integrado. Formato exacto por confirmar. → RESEARCH.md § Séptima pasada
- [ ] SIPA — geoportal (`geoportal.agricultura.gob.ec`, solo HTTP) corre un backend GeoServer WMS completo (uso de suelo, suelos, riesgos agroclimáticos, catastro rural), mucho más allá de las ortofotos ya anotadas — falta confirmar si expone WFS para exportar vectores, no solo teselas de mapa. Los boletines nacionales (Panorama Agroestadístico y similares) son PDFs directos, sin fricción. Los tableros "Cifras Agroproductivas/Territoriales" están confirmados rotos en producción — no perseguir. → RESEARCH.md § Séptima pasada
- [ ] Ministerio de Salud Pública (`salud.gob.ec`) — dominio confirmado vivo con contenido real (barrido de endpoints 2026-08-29), sección de transparencia/LOTAIP presente, pero sin sección de estadísticas/datos abiertos visible en la portada — no se profundizó más allá de confirmar que el sitio está vivo, falta una pasada de contenido completa. → RESEARCH.md § Séptima pasada
- [ ] Registro Oficial (gaceta oficial) — candidato de alta prioridad para búsqueda por fecha; posiblemente no relevante, ver nota de alcance. → RESEARCH.md § Datos legislativos
- [ ] INEVAL — exámenes nacionales (Ser Bachiller/ENES, Ser Estudiante, Ser Maestro...), archivo real sin login/captcha. → RESEARCH.md § INEVAL
- [ ] Superbancos — **escaneado a fondo 2026-08-29** (`www.superbancos.gob.ec`, sin org CKAN). Listo para construir sin fricción: Boletines Financieros Mensuales (1997-hoy, ZIP) y Servicios Financieros (tarjetas/cajeros, ZIP), mismo patrón de scraper que SIPA; Calendario Estadístico (XLSX) como añadido trivial. Sin resolver, probablemente lo más valioso: Balances Generales/Patrimonio Técnico/indicadores de morosidad-liquidez-solvencia (detrás de una herramienta de consulta, necesita browser) y Resoluciones y Circulares (AJAX-gated). Catastro de Compañías bloqueado por login, descartado. → RESEARCH.md § Séptima pasada
- [ ] MEF — workbook fiscal (recaudación arancelaria y series GFSM 2013-2026, actualizado mensualmente). → RESEARCH.md § Recaudación arancelaria
- [ ] MINEDEC — registro histórico de matrícula básica 2009-2025. → RESEARCH.md § Sitios de ministerios individuales
- [ ] SEPS — boletines de calificadoras de riesgo (`estadisticas.seps.gob.ec`, subdominio alcanzable aunque el sitio principal bloquea bots). → RESEARCH.md § Sitios de ministerios individuales
- [ ] CNIG — matriz de femicidios (actualización semanal), sin confirmar link exacto de descarga. → RESEARCH.md § Sitios de ministerios individuales
- [ ] Permisos y portales municipales — sin investigar, alcance grande (~221 GADs). → RESEARCH.md § Permisos municipales
- [ ] IGM Geoportal — cartografía gated tras registro/login, no automatizable tal cual. → RESEARCH.md § Sitios de ministerios individuales
- [ ] Fuentes externas de sociedad civil (FCD, FARO) — corregido: sí hay datasets tabulares reales (votaciones de la Asamblea, declaraciones patrimoniales de funcionarios, ordenanzas municipales de Quito/Guayaquil), verificados en vivo; decisión de alcance sigue pendiente (no es "gobierno"). FARO en sí no tiene portal de datos. `cuentasclaras.org` está comprometido con spam, no tocar. → RESEARCH.md § Fuentes externas
- [ ] Gremios privados (AEADE, ASOBANCA, FEDEXPOR) — AEADE y FEDEXPOR confirmados y descargables; ASOBANCA Datalab sin resolver extracción (SPA). → RESEARCH.md § Gremios
- [ ] **CORDES — Corporación de Estudios para el Desarrollo** — investigar su [base de variables macroeconómicas y entregas periódicas](https://www.cordes.org/): cobertura histórica, frecuencia, acceso descargable/API, definiciones y traslape con BCE/INEC. El sitio tiene protección anti-bot, así que primero hay que confirmar qué parte es automatizable y qué parte queda como publicación/documento. CORDES aparece también entre los participantes de la Encuesta de Expertos, pero no asumir que ambos productos son la misma fuente. → RESEARCH.md § Fuentes externas
- [ ] **Nowcast / Encuesta de Expertos — Previsiones de la Economía del Ecuador** — investigar e integrar, si el acceso y la licencia lo permiten, las previsiones/nowcasts de PIB, empleo adecuado, desempleo e inflación. Separar claramente estimación de dato observado y conservar fecha de publicación, horizonte, metodología, participantes y revisiones. El [sitio público de Nowcast](https://www.expertoseconomia.org/es/) presenta estos cuatro indicadores mediante visualizaciones Datawrapper; sus páginas anuales incluyen además déficit fiscal, riesgo país y precio del petróleo. → RESEARCH.md § Fuentes externas
- [ ] Vivienda MIDUVI — dominio caído a nivel TLS, sin reemplazo encontrado; CKAN cubre parcialmente. → RESEARCH.md § Vivienda
- [ ] Prensa — SECOM/Presidencia y Fundamedios, sin profundizar. → RESEARCH.md § Prensa
- [ ] Datos legislativos/normativos (jurisprudencia, proyectos de ley) — investigado a fondo; **Daniel señaló que puede no ser relevante** para el alcance del proyecto. → RESEARCH.md § Datos legislativos
- [ ] Fuentes internacionales con foco Ecuador — investigar **CEPAL/CEPALSTAT**, agencias de la **ONU** y, cuando tengan datos específicamente útiles para Ecuador, Banco Mundial, OIT, FAO, OMS/OPS, UNESCO, OIM y organismos regionales. Para cada fuente: confirmar acceso real (API/bulk/archivo), indicador y desagregación disponibles para Ecuador, historia, frecuencia, licencia, fecha de actualización y duplicación frente a INEC/BCE/ministerios. Integrar solo lo que aporte una serie o corte que la fuente ecuatoriana no publique; conservar siempre fuente y definición original. CEPAL sigue como primer candidato. → RESEARCH.md § Fuentes externas
- Confirmados sin acción posible (bloqueos reales, no falta de esfuerzo): CNE y micrositio de Interior (WAF Incapsula), Aduana/SENAE comercio exterior (no publicado, solo por oficio — FEDEXPOR cubre el hueco), Fiscalía (sin dataset agregado propio), Supercías Valores/Seguros (login-gated, casi todo, un solo PDF estático encontrado), SERCOP catálogo/órdenes de compra (CAPTCHA), IG-EPN `descarga-de-datos` (cuenta obligatoria), Superbancos Catastro de Compañías (login obligatorio). → RESEARCH.md § Sitios de ministerios individuales / § Séptima pasada
- ANDA — reconfirmado 2026-08-29: cobertura completa (437 encuestas, coincide con lo ya documentado), sin gap real, solo una limitación menor de UX (no se puede filtrar por tema del lado del servidor). → RESEARCH.md § Séptima pasada
- Ministerio del Trabajo/SUT — investigado 2026-08-29: sin gap, el SUT es la fuente declarada de los 5 datasets ya en la organización CKAN `ministerio-del-trabajo`. `trabajo.gob.ec` tiene un patrón de falla nuevo (páginas dinámicas nunca responden, timeout 45s+; archivos estáticos bajo `/wp-content/uploads/` sí cargan) — anotado para futuras auditorías de otros ministerios que compartan hosting. → RESEARCH.md § Octava pasada
- [ ] Salarios mínimos sectoriales (tablas salariales por rama de actividad) — **a considerar, pedido por Daniel 2026-08-29**. Ya se investigó una vez (ver Trabajo/SUT arriba) y salió débil: no hay dominio propio del Consejo de Salarios (`consejosalarios.gob.ec` no resuelve), las tablas se publican como PDFs sueltos del ministerio con URLs impredecibles, y no se publicó tabla 2026 según cobertura de prensa (queda vigente la de 2025 por inacción). No descartado del todo — vale la pena una pasada dedicada a enumerar todos los PDFs históricos encontrables (por año/rama) antes de decidir si es viable como serie. → RESEARCH.md § Octava pasada

## Cabos operativos sueltos

- [x] Renovación de certificado TLS.

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

- [ ] `outputSchema` en los tools MCP.
- [ ] Manejo geoespacial (WKT/GeoJSON más allá del stripping actual).
- [ ] Tool de investigación "one-shot" (una sola llamada que combine búsqueda + preview + detección de serie).
- [x] Protección HTTP base — `/mcp` admite Bearer token opcional, el bind local
      es loopback por defecto y existe un límite global de concurrencia; `/health`
      queda libre para health checks.
- [ ] Rate limiting por usuario/IP y proxy HTTPS — complementar el límite
      global con cuotas por cliente, TLS terminado delante de Uvicorn y una
      política explícita para el endpoint remoto que consumirán agentes móviles.
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
