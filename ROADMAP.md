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

### Objetivo prioritario: cobertura completa del BCEData y del IEM

“Completa” aquí significa que el servidor descubre automáticamente todo lo
que la fuente expone, no que solo conozca los indicadores más conocidos. La
integración debe poder demostrar qué grupos, series, frecuencias, unidades,
fechas, boletines y archivos encontró, y cuáles no pudo leer.

- [ ] **BCEData completo — catálogo y series**: cubrir todos los nodos hoja de
      `/tree`, el metadata de cada `/bundle/{id_grupo}` y todos los valores
      disponibles en `/grid`; conservar etiquetas, rutas, secciones,
      frecuencias, unidades, rango de fechas y revisiones. La búsqueda debe
      encontrar tanto grupos como series internas y la consulta debe permitir
      seleccionar explícitamente cualquier frecuencia, unidad y período.
- [~] **BCEData completo — verificación de cobertura**: `audit_bce_catalog`
      ya consulta el árbol y los metadatos de todos los grupos, y registra
      cuántos grupos y series fueron descubiertos, qué solicitudes fallaron y
      cuándo se consultó la API. Pendiente: persistir snapshots y comparar
      automáticamente grupos nuevos, retirados o modificados. No depender de
      una lista fija de IDs.
- [ ] **IEM completo — archivo y archivos fuente**: descubrir todos los
      boletines desde enero de 1996 hasta el más reciente, reconciliando el
      índice histórico con “Últimas publicaciones”; catalogar cada XLSX,
      además del PDF y ZIP completos, con boletín, fecha, sección, título, URL
      y hash/fecha de consulta.
- [ ] **IEM completo — lectura de tablas**: hacer buscables los valores de
      todas las tablas individuales, no solo sus títulos. Añadir lectores para
      las familias de formatos que difieren del diseño común; conservar también
      una copia/vista fiel del archivo original cuando no sea seguro
      normalizarlo. Una vista de las primeras filas cuenta como diagnóstico,
      no como cobertura completa.
- [ ] **BCEData ↔ IEM — mapa de equivalencias**: identificar qué tabla IEM
      duplica una serie BCEData, cuál la amplía y cuál existe solo en una de las
      dos fuentes. Mantener la definición original, unidad, frecuencia, fecha
      de corte y notas de revisión para evitar combinar series incompatibles.
- [ ] **BCE — prueba de completitud y frescura**: ejecutar una comprobación
      programada que compare el catálogo descubierto con el anterior, confirme
      que el boletín más reciente está presente y deje visible el último período
      disponible por fuente. Un fallo de la web no debe borrar la última versión
      válida.

- [x] SRI — datasets page (`search_sri_datasets`).
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
- [x] IG-EPN — catálogo sísmico (`search_sismos`).
- [x] Cuenca en Datos — CKAN municipal vía `source="cuenca"` en los tools genéricos.
- [~] Registro Civil / demográfico-salud — cobertura CKAN sólida, pero **corregido 2026-08-29**: "sin gaps" era incorrecto — `registrocivil.gob.ec` publica un dataset propio de defunciones a nivel de registro individual (2020-2025, `.xlsb`, con diccionario de variables) que no está en ninguno de los 6 datasets CKAN de la organización. `.xlsb` no está soportado hoy por `helpers/csv_reader.py`. → RESEARCH.md § Séptima pasada
- [x] Ecuador en Cifras / INEC — `search_inec_estadisticas`/`get_inec_estadistica_files` (~75 temas: boletines + series históricas agregadas) + `search_biinec_extras` (lista curada de los 2-3 registros de BIINEC que sí son exclusivos — desechos peligrosos en salud, módulos ambientales ENEMDU/ECV; no un cliente genérico, ver análisis de costo/beneficio en RESEARCH.md). → RESEARCH.md § Ecuador en Cifras
- [~] IESS — boletines/auditorías/actuariales scrapeables y confirmados, sin construir tool nuevo. → RESEARCH.md § IESS
- [~] SENESCYT/Educación Superior — cubierto vía CKAN; registro de títulos bloqueado por captcha (no automatizable). → RESEARCH.md § SENESCYT
- [~] BCE — Información Estadística Mensual (IEM/IEEM), boletín mensual mucho más rico que BCEData. `search_bce_iem` indexa en vivo las tablas XLSX individuales del boletín vigente y, con `historico=true` o un rango de años, agrupa versiones de la misma tabla en el archivo mensual. `get_bce_iem_table` devuelve series con filtro anual cuando detecta el formato tabular ancho, y reconoce también tablas largas; si no, preserva una vista segura sin inventar columnas. **Auditoría 2026-08-29**: la lógica cubre correctamente las páginas y tablas que encuentra, pero el índice maestro visible del BCE llega al IEM 2092 (junio 2026), mientras que el IEM 2093 (julio 2026) ya existe en una página de índice enlazada desde “Últimas publicaciones”; hay que hacer el descubrimiento resistente a índices atrasados. Pendiente: normalizadores dedicados, comparación explícita con BCEData y catálogo histórico completo. **Profundizado 2026-08-29**: cada boletín (archivo completo desde ene-1996) tiene ~60+ XLSX individuales por tabla, no solo el ZIP. → RESEARCH.md § Séptima pasada
- [ ] BCE — **BCEData: auditoría viva de cobertura y metadatos**: comparar periódicamente `/tree`, cada `/bundle/{id_grupo}` y las series devueltas por `/grid` con el catálogo visible del BCE; detectar grupos nuevos, grupos retirados, cambios de nombre, rangos de fechas, frecuencias y unidades. Mantener la búsqueda por etiquetas de series y documentar que esta API pública no está formalmente documentada por el BCE.
- [ ] BCE — **IEM: descubrimiento y catálogo histórico resistente**: no depender únicamente de `IndiceIEM.html`; reconciliarlo con “Últimas publicaciones”, detectar boletines nuevos no listados, comprobar que cada boletín tenga sus XLSX individuales, registrar boletines faltantes y añadir normalizadores para las familias de tablas de mayor valor. No presentar el IEM más reciente encontrado como “actual” sin informar su fecha de corte.
- [ ] BCE — **búsqueda ampliada y mapa completo de fuentes**: revisar más allá de BCEData e IEM el sitio institucional, publicaciones temáticas, catálogos, archivos históricos y descargas por sector. Inventariar cada fuente, su cobertura, frecuencia, formato, API/archivo y traslape con lo ya integrado; priorizar únicamente tablas que añadan detalle ecuatoriano verificable, no duplicados de una misma serie. El resultado debe ser un mapa de cobertura y una lista corta de integraciones justificadas.
- [ ] BCE — **Remesas de trabajadores**: investigar e integrar el portal específico con resultados agregados, serie histórica y bases mensuales, incluida la desagregación por entidad disponible desde julio de 2025. Mantener separadas las series anteriores y posteriores al cambio metodológico y conservar las notas de comparabilidad. → https://contenido.bce.fin.ec/series-de-datos-remesas-de-trabajadores/
- [ ] BCE — **medios y sistemas de pago**: integrar, si el acceso automatizable se confirma, SPI, SCI, SPL, cámara de cheques y recaudación de recursos públicos, con montos, número de operaciones, frecuencia, historia y unidad. Es una colección separada de BCEData/IEM y no debe confundirse con “pagos” en otras instituciones. → https://contenido.bce.fin.ec/estadisticas-del-sector-medios-y-sistemas-de-pagos/
- [ ] BCE — **Cuentas Nacionales completas**: investigar los paquetes anual, trimestral y regional, retropolación, Tabla Oferta-Utilización, Cuadro Económico Integrado y Matriz de Empleo e Ingresos. IEM/BCEData pueden contener partes, pero la integración debe conservar la metodología de base móvil, revisiones, frecuencia y carácter provisional/definitivo. → https://contenido.bce.fin.ec/estadisticas-de-cuentas-nacionales/
- [ ] BCE — **EMOE y coyuntura**: investigar el Estudio Mensual de Opinión Empresarial, metodologías, expectativas económicas, confianza del consumidor, ciclo económico, inflación, mercado laboral, pobreza/desigualdad y crédito. Reutilizar BCEData/IEM cuando ya sean la misma serie; añadir solo archivos, cortes o metadatos que falten. → https://contenido.bce.fin.ec/documentos/PublicacionesNotas/Indicador_coy.html
- [ ] BCE — **paquetes sectoriales**: auditar por separado petróleo, minería, cemento, agricultura y compra/venta de divisas. Para cada uno, decidir si basta BCEData/IEM o si hace falta un cliente de publicaciones/archivos; conservar frecuencia, fecha de corte y revisión. → https://contenido.bce.fin.ec/ultimas-publicaciones/
- [ ] BCE — **índices de precios de comercio exterior**: verificar si las series IPX/IPM/ITI que aparecen en BCEData tienen la misma cobertura que la página dedicada; integrar la metodología, series históricas y archivos de exportación/importación solo si aportan detalle adicional. → https://contenido.bce.fin.ec/estadisticas-de-indice-de-precios-de-comercio-exterior/
- [ ] BCE — **catálogo de publicaciones, calendario y archivo histórico**: añadir búsqueda de “Últimas publicaciones”, Cifras Económicas del Ecuador, boletines monetarios/financieros, informes y metodologías, con fecha de publicación, período cubierto, formato y URL. Esto complementa las series de BCEData y las tablas IEM. → https://contenido.bce.fin.ec/ultimas-publicaciones/
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
- [ ] Fuentes internacionales con foco Ecuador — investigar **CEPAL/CEPALSTAT**, el **FMI/IMF** (pedido explícito de Daniel 2026-08-30: variables macro trimestrales — candidatos concretos son IFS/International Financial Statistics para series trimestrales de balanza de pagos/reservas/tipo de cambio, el WEO database para proyecciones, y los Article IV Staff Reports para el análisis narrativo con series propias), agencias de la **ONU** y, cuando tengan datos específicamente útiles para Ecuador, Banco Mundial, OIT, FAO, OMS/OPS, UNESCO, OIM y organismos regionales. Para cada fuente: confirmar acceso real (API/bulk/archivo — el FMI tiene una API REST pública para IFS/WEO sin key, por confirmar cobertura y campos exactos para Ecuador), indicador y desagregación disponibles para Ecuador, historia, frecuencia, licencia, fecha de actualización y duplicación frente a INEC/BCE/ministerios. Integrar solo lo que aporte una serie, corte o frecuencia (ej. trimestral cuando BCE solo publica mensual/anual) que la fuente ecuatoriana no publique; conservar siempre fuente y definición original — el valor de estas fuentes suele ser la comparabilidad internacional y la metodología armonizada, no un dato más nuevo que el de BCE/INEC. CEPAL y FMI son los primeros candidatos. → RESEARCH.md § Fuentes externas
- Confirmados sin acción posible (bloqueos reales, no falta de esfuerzo): CNE y micrositio de Interior (WAF Incapsula), Aduana/SENAE comercio exterior (no publicado, solo por oficio — FEDEXPOR cubre el hueco), Fiscalía (sin dataset agregado propio), Supercías Valores/Seguros (login-gated, casi todo, un solo PDF estático encontrado), SERCOP catálogo/órdenes de compra (CAPTCHA), IG-EPN `descarga-de-datos` (cuenta obligatoria), Superbancos Catastro de Compañías (login obligatorio). → RESEARCH.md § Sitios de ministerios individuales / § Séptima pasada
- ANDA — reconfirmado 2026-08-29: cobertura completa (437 encuestas, coincide con lo ya documentado), sin gap real, solo una limitación menor de UX (no se puede filtrar por tema del lado del servidor). **Corregido 2026-08-29 (segunda revisión, pedido de Daniel): "sin gap real" era incorrecto para ENEMDU específicamente** — ver el ítem nuevo de abajo (ENEMDU/mercado laboral post-2023 sin cubrir en ningún tool actual). → RESEARCH.md § Séptima pasada / § Novena pasada
- [x] **`search_inec_publicaciones`/`get_inec_publicacion_archivos` — nuevos tools sobre la API REST pública de WordPress (`/wp-json/wp/v2/posts`), en vez de depender solo del scraping de páginas de tema.** Construido 2026-08-30. Corrección importante que motivó esto (Daniel aportó URLs reales que refutaron el diagnóstico anterior de este mismo roadmap): `search_inec_estadisticas`/`get_inec_estadistica_files` derivaban su lista de "temas" del menú (mega-menu) de una sola página semilla — pero **el menú no es el mismo en cada página del sitio**. La página `estadisticas-laborales-enemdu/` tiene su propio submenú con `enemdu-anual/`, `enemdu-trimestral/`, `enemdu-telefonica/`, `matrices-de-transicion-laboral/`, ninguno alcanzable desde la página semilla original — y `enemdu-anual/` tenía el ENEMDU anual 2025 completo (BDD SPSS/CSV, boletín técnico, tabulados) todo el tiempo. Dos arreglos, no uno solo:
  1. `search_topics`/`get_topic_files` (la capa vieja) ahora fusiona **dos** páginas semilla y captura también los ítems de submenú desplegable (`<li class="menu-item...">`, markup distinto del `mega-menu-link` de nivel superior) — de 74 a 89 temas descubiertos, incluyendo las 4 páginas de ENEMDU que faltaban. Reduce el problema, no lo elimina del todo (sigue dependiendo de qué semillas se usen).
  2. **Capa nueva, autoritativa:** `search_inec_publicaciones`/`get_inec_publicacion_archivos` consumen directamente `/wp-json/wp/v2/posts` (API REST pública de WordPress, sin auth) — 1,707 posts totales confirmados en vivo, el más nuevo a días de la consulta, con búsqueda de texto completo real (confirmado: "subempleo" encuentra posts cuyo título no contiene la palabra), `orderby`/`offset` para paginación honesta, y el HTML de cada post trae los enlaces a archivos directamente. Noticias y Boletines (`/institucional/...`) resultaron ser solo vistas filtradas por categoría de esta misma colección — no hizo falta el scraper de Noticias planeado originalmente. Verificado extremo a extremo en vivo a través del tool MCP real (`main.mcp.call_tool`), no solo la capa de helper: `get_inec_publicacion_archivos("https://www.ecuadorencifras.gob.ec/enemdu-anual/")` devuelve los 11 archivos reales del ENEMDU anual 2025, el mismo archivo que arrancó toda esta investigación. 15 tests nuevos (`tests/test_inec_client.py`), 288 tests totales pasando. → RESEARCH.md § Novena pasada
- [x] Las 4 categorías "macro" del menú de INEC (Estadísticas Macroeconómicas, Cuentas económicas, Comercio internacional y balanza de pagos, Finanzas públicas/fiscales) — **confirmado 2026-08-30 que están vacías por diseño, no por el mismo bug de descubrimiento que ENEMDU.** Buscadas en vivo vía `/wp-json/wp/v2/posts?search=` con "cuentas nacionales", "PIB", "balanza de pagos", "finanzas públicas", "deuda pública", "estadísticas macroeconómicas": ningún resultado es una publicación propia de INEC sobre esos temas — todo lo que existe bajo "Estadísticas Económicas" son las Cuentas Satélite (Salud, Educación, Trabajo No Remunerado, Energía) y el Registro Estadístico de Empresas, nunca Cuentas Nacionales/Balanza de Pagos/deuda. Confirma la hipótesis: esa responsabilidad es del BCE (ya cubierto por `search_indicadores_bce`/IEM), INEC nunca publicó nada propio ahí. → RESEARCH.md § Novena pasada
- [x] `read_pdf` ahora valida extensión/Content-Type antes de descargar (2026-08-30) — rechaza extensiones conocidas no-PDF (.zip/.xlsx/.csv/...) sin hacer ninguna petición, y cuando la URL no tiene extensión reconocible cae a un sniff de Content-Type (solo headers, sin cuerpo) antes de comprometerse a la descarga completa. Antes bajaba hasta 5 MB de un ZIP grande inútilmente antes de fallar con "no es un PDF válido".
- [ ] **INEC (y en general): no hay preview de archivos grandes (ZIP/BDD), a diferencia de CKAN.** `get_inec_publicacion_archivos`/`get_topic_files` solo devuelven metadata (label/url/formato) — nunca descargan el archivo, por diseño (igual que SIPA). Pero a diferencia de los recursos CKAN, que tienen `preview_zip`/`preview_targz` para ver una muestra de filas sin bajar todo, **no existe ningún tool que muestre una vista previa de un ZIP/BDD de INEC** (ej. el REESS `200901_202412_REESS_MENSUAL_BDD_DEFINITIVAS.zip`, confirmado en vivo: no terminó de bajar los primeros 100 MB en 60s, claramente muy por encima del cap de 5 MB). Un agente que reciba solo `{label, url, formato}` no tiene forma de inspeccionar el contenido sin salir del MCP.

  Plan por niveles (conversación 2026-08-30):
  1. **Ganancia concreta, prioridad alta:** extender `preview_zip`/`preview_targz` (o un wrapper específico) para que acepten una URL directa, no solo un `resource_id` de CKAN — leyendo solo el directorio central del ZIP vía HTTP Range al final del archivo (donde vive siempre en el formato ZIP) para listar nombres/tamaños/tamaños comprimidos de los miembros sin descargar el archivo completo. Limitación real a documentar: previsualizar filas de un miembro específico sigue requiriendo descomprimir desde el offset de ese miembro en adelante, que puede seguir siendo grande si el miembro está cerca del final de un archivo enorme — el listado es barato, la vista de contenido no siempre lo es.
  2. **Solo si se justifica por uso repetido:** un índice local pre-construido (mismo patrón que `scripts/build_supercias_financials_db.py`) para un dataset específico que se consulte seguido (ej. REESS o ENEMDU por provincia/mes). No vale la pena como mecanismo general, es inversión por dataset.
  3. **Para el resto, no hay nada que arreglar:** las respuestas de un tool MCP son texto/JSON hacia el contexto del modelo, no un canal de transferencia de archivos — para una descarga puntual de un archivo enorme, la respuesta correcta sigue siendo devolver la URL directa y que el agente la baje con su propia capacidad de fetch, fuera de este servidor.
  → conversación 2026-08-30
- [ ] **`censoecuador.gob.ec` — micrositio dedicado del Censo 2022 con microdatos completos, sin integrar todavía.** Dominio propio de INEC (WordPress, mismo certificado/patrón TLS que otros sitios .gob.ec — necesita `verify=False`), enlazado desde Daniel 2026-08-30. La página `/data-y-resultados/` (devuelve HTTP 404 pero sirve 163 KB de contenido real — plugin/tema que no setea el status code correctamente, ojo con esto al construir el cliente) enlaza microdatos reales por sector/cantón/manzana en CSV, SPSS y REDATAM, con diccionarios de variables y los censos 2010 y 2001 re-codificados a la geografía 2022 para comparabilidad — todo alojado en `ecuadorencifras.gob.ec/documentos/web-inec/bd-censo/...` y `dicc-censo/...`. Verificado en vivo (HEAD, status 200 + content-type correcto) sobre 3 archivos de muestra. El tema "Censo de Población y Vivienda" que ya indexa `search_inec_estadisticas` solo tiene 16 archivos (2024) — mucho menos que lo que hay aquí. Pendiente: confirmar tamaños reales de los ZIP (probablemente >5 MB, el patrón de este proyecto para archivos grandes es devolver metadata + URL, no el contenido, igual que Supercías financials/SIPA) antes de decidir la forma del tool. → RESEARCH.md § Novena pasada
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
