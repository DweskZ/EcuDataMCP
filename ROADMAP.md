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
- [~] **Operación 24/7** — construido 2026-08-31: `.github/workflows/smoke.yml`
      ejecuta diariamente `scripts/smoke_e2e.py` (ahora con ~39 de 68 tools
      cubiertos, antes 13, más 3 cadenas dinámicas list→get que descubren un
      ID real en vivo para SUT/Superbancos/IG-EPN en vez de fijar uno que
      pueda quedar obsoleto) contra un servidor recién levantado, separado de
      `ci.yml` (que solo corre tests unitarios con HTTP mockeado en cada
      push). GitHub avisa por correo a quienes ven el repo cuando una
      ejecución programada falla — sin infraestructura de alertas nueva.
      Cubre la "prueba de humo periódica desde fuera del servidor" del ítem
      original. Desde 2026-08-31 reintenta fuentes externas conocidas y
      distingue `degraded` (CKAN con bloqueo regional o TLS de CENACE) de un
      fallo duro del servidor; el resumen de Actions muestra las fuentes
      afectadas. Pendiente: alertas específicas de cambio de esquema.

## Nuevas conexiones de datos

### Mapa de datos de alta frecuencia, aportado por Daniel 2026-08-31

Tabla de candidatos de alta frecuencia que Daniel trajo de su propia
investigación — cruzada contra el estado real de este roadmap, no
copiada tal cual:

| Fuente | Frecuencia | Qué mide | Estado en este proyecto |
|---|---|---|---|
| BCE, producción petrolera | Diaria | Barriles producidos | [x] hecho — `datos_hid.json` vía `get_bce_indicador_diario`, ver más abajo |
| BCE, riesgo país | Diaria | EMBI Ecuador | [x] hecho — `datos_formulario.json`, el hallazgo que arrancó esta familia de indicadores |
| BCE, oro/WTI/Dow Jones/SOFR | Diaria | Mercados y precios internacionales | [x] hecho — `datos_diarios.json` |
| CENACE, Información Operativa | Horaria/diaria | Demanda eléctrica, generación, despacho | [x] hecho — `get_cenace_tablero`, snapshot en vivo (no serie histórica), ver más abajo |
| SIPA/MAG, precios mayoristas | Diaria o quincenal según producto | Precios mayoristas de alimentos | [ ] **Descartado como fuente de alta frecuencia, 2026-08-31.** Dos páginas revisadas, ninguna es diaria/quincenal: "Precios Mayoristas" (boletines PDF mensuales) y `precios-referenciales` — el "api"/"json" en su HTML era solo el token CSRF de Joomla, falso positivo. `precios-referenciales` en realidad enlaza a "Mercado Mayorista Quito/Guayaquil/Cuenca", cada uno un PDF embebido (`descargas/mercados/precios_referenciales/{ciudad}_precios_referenciales_2026.pdf`) con los rangos de precio del Decreto Nº1438 vigentes — un documento regulatorio de piso/techo de precio, con fecha de emisión y vigencia mensual (confirmado: "Fecha de emisión: 4 de agosto de 2026", vigente desde el 4 de septiembre), no una serie de observaciones diarias de mercado. El archivo se sobreescribe en el mismo nombre cada vez — sin historia. Bajo valor como para priorizarlo (3 PDFs, una foto del mes, sin serie), pero real y fácil si algún día se justifica. La app móvil "cgsin.precios" sigue sin explorar — podría ser la fuente diaria real detrás de escena, no confirmado. |
| INAMHI, Geoportal | Horaria/diaria | Lluvia, temperatura, caudales, estaciones | [ ] ya en el roadmap (`geoservicios.inamhi.gob.ec`) — GeoServer WMS confirmado, sin listar capas ni confirmar datos tabulares de estaciones todavía |
| IG-EPN, sismos | Casi tiempo real | Sismos, magnitud, ubicación, profundidad | [x] hecho — `search_sismos`, la única fuente genuinamente de alta frecuencia ya integrada antes de esta pasada |
| DGAC/IFIS | Diaria | Vuelos y movimientos por aeropuerto | [ ] ya en el roadmap como "Aviación civil" (`ais.aviacioncivil.gob.ec`) bajo METAR/NOTAM/SIGMET — la fila de Daniel apunta más bien a estadísticas de movimientos/vuelos por aeropuerto, que puede ser una sección distinta del mismo sitio (IFIS) sin explorar todavía; no asumir que es la misma sub-fuente que METAR/NOTAM/SIGMET sin confirmar. |

### Objetivo prioritario: cobertura completa del BCEData y del IEM

“Completa” aquí significa que el servidor descubre automáticamente todo lo
que la fuente expone, no que solo conozca los indicadores más conocidos. La
integración debe poder demostrar qué grupos, series, frecuencias, unidades,
fechas, boletines y archivos encontró, y cuáles no pudo leer.

- [~] **BCEData completo — catálogo y series**: cubrir todos los nodos hoja de
      `/tree`, el metadata de cada `/bundle/{id_grupo}` y todos los valores
      disponibles en `/grid`; conservar etiquetas, rutas, secciones,
      frecuencias, unidades, rango de fechas y revisiones. La búsqueda debe
      encontrar tanto grupos como series internas y la consulta debe permitir
      seleccionar explícitamente cualquier frecuencia, unidad y período. El
      descubrimiento de grupos/series y la consulta de cualquier combinación ya
      están implementados; `auditar_grid=true` prueba un período reciente por
      cada combinación frecuencia/unidad, con reporte persistente separado y
      límite de 500 combinaciones. Sigue pendiente comprobar cambios de
      revisión cuando el endpoint los exponga explícitamente. La auditoría ya
      registra si existe un marcador explícito (campo de revisión/version o
      `ETag`/`Last-Modified`); comprobación en vivo 2026-08-31: BCEData responde
      200, pero no publica ninguno, así que la comparación por contenido es la
      única evidencia disponible hoy. Auditoría viva 2026-09-01: 78/78 grupos
      y 2.360 series sí cargaron; 108/154 combinaciones frecuencia/unidad
      devolvieron valores y 46 recibieron una página HTML de rechazo por la
      propia política de seguridad del BCE con HTTP 200. No tratarlas como
      datos ausentes ni como error JSON del servidor.
- [x] **BCEData completo — verificación de cobertura**: `audit_bce_catalog`
      consulta el árbol y los metadatos de todos los grupos, registra cuántos
      grupos y series fueron descubiertos, qué solicitudes fallaron y cuándo
      se consultó la API. `guardar_snapshot=true` conserva cada intento,
      promueve solo auditorías completas a `latest-valid.json`, y
      `comparar_anterior=true` detecta grupos nuevos, retirados y modificados,
      incluidas series nuevas/retiradas. `scripts/audit_bce_catalog.py` deja
      el mismo flujo listo para cron/scheduler. No depende de una lista fija
      de IDs.
- [~] **IEM completo — archivo y archivos fuente**: `search_bce_iem` ahora
      reconcilia el índice, “Últimas publicaciones” y el archivo oficial
      `iem-publicaciones/`. Este último enumera 367 boletines consecutivos,
      No. 1727–2093 (1996–2026), y el auditor conserva esa evidencia aunque
      una página no tenga tablas legibles. Los XLSX se catalogan con boletín,
      fecha, sección, título, URL y fecha de consulta; el hash es opt-in,
      concurrente y acotado. Verificación viva 2026-09-01: los siete boletines
      disponibles de 2026 expusieron 84 tablas XLSX; la muestra de 1996 reveló
      cuatro enlaces 404 y ocho páginas sin XLSX individuales. Por tanto, el
      índice histórico está cubierto, pero todavía no se puede declarar lectura
      ni hashing completos de 1996–2026.
      **Fronteras exactas encontradas 2026-09-02** (búsqueda binaria en vivo
      por boletín): resultan ser **tres eras**, no dos.
      - **No. 1976–2093 (octubre 2016→hoy, ~118 boletines, ~32%):** XLSX
        individuales por tabla. Ya cubierto.
      - **No. 1854–1975 (agosto 2006 – septiembre 2016, ~122 boletines,
        ~33%): construido 2026-09-02.** La página no linkea XLSX
        individuales, pero sí un ZIP de la publicación completa
        (`archivos_completos`, tipo `zip`) que ya trae un archivo por tabla
        con el mismo esquema `IEM-{numero}`, solo que en `.xls` legado (no
        `.xlsx`) — confirmado en vivo con `list_zip_contents` sobre
        `IEM1975.zip` antes de construir nada. `_fetch_legacy_zip_tables`
        lista los miembros del ZIP como tablas (`table_id` con prefijo
        `iem-legado-` porque la numeración 1:1 contra la era moderna no
        está confirmada — vistos `IEM-315a.xls`, `5_SectorPetrolero.xls`,
        `7_GraficosIDEAC.xls` sin equivalente obvio hoy); `get_table` lee
        el miembro con `xlrd` (`.xls` legado) a través de un adaptador
        (`_XlsSheetAdapter`) que reutiliza sin cambios los mismos
        `_extract_wide_series`/`_extract_long_table`/`_extract_matrix_series`
        ya probados contra XLSX moderno. Encontrado y corregido en el
        proceso: xlrd no distingue int de float (todo número es float), así
        que un encabezado de año como `2025.0` rompía la regex de 4 dígitos
        de `_period_key` (`"2025.0"` → `.replace(".", "")` → `"20250"`) —
        el adaptador ahora normaliza floats enteros a `int`, igual que
        openpyxl. Verificado en vivo extremo a extremo contra boletines
        reales (No. 1975, No. 1900, No. 1950), no solo con mocks. 8 tests
        nuevos.
      - **No. 1727–1853 (enero 1996 – julio 2006, ~126 boletines, ~34%):
        construido 2026-09-02.** Confirmado en vivo (No. 1800, No. 1780)
        que estas páginas usan HTML pre-moderno de framesets —
        `<A HREF = ... TARGET="_top">` en mayúsculas y sin comillas — que
        enlazan páginas `.htm` por sección (`m{boletin}_{k}.htm`, ~60 por
        boletín). El dato en sí no está en ningún archivo descargable —
        vive como una `<TABLE>` HTML cruda embebida directamente en cada
        página de sección, con encabezados multinivel de ROWSPAN/COLSPAN
        genuinamente irregulares y contenido en `cp1252`. `_TableGridParser`
        (subclase de `html.parser.HTMLParser`, sin dependencia nueva —
        el mismo patrón ya usado en `sri_ruc_client.py`, adaptado porque
        esta era no cierra `</TR>`/`</TH>`/`</TD>`, así que el cierre
        implícito se infiere por el siguiente tag de apertura, no por
        `handle_endtag`) captura las celdas con su rowspan/colspan reales;
        `_expand_table_grid` las resuelve al algoritmo estándar de grilla
        rectangular. `table_id` se deriva del texto de sección
        (`_legacy_frameset_table_id`, ej. "1.1 Principales Indicadores
        Monetarios"), no del índice `k`, que no está confirmado estable.
        Expuesto siempre como vista de grilla (`formato: "vista"`, mismo
        contrato que `_inspect_xlsx`/`_inspect_legacy_xls`) — nunca se
        intenta wide/long/matrix aquí: la jerarquía de encabezados es
        irregular a propósito de sección en sección, adivinar una forma
        semántica sería menos honesto que mostrar la grilla real.
        **Verificado en vivo extremo a extremo contra el boletín No. 1800
        real**: 63 tablas descubiertas, valores de una fila de datos real
        (diciembre 1999, tabla "1.1 Principales Indicadores Monetarios")
        coinciden exactamente con el HTML fuente, celda por celda. 6 tests
        nuevos.
      Con estas tres fronteras, el archivo completo 1996–2026 (367
      boletines) es legible hoy — sin hashing masivo confirmado todavía
      para las porciones ZIP/frameset, y sin garantía de que cada una de
      las 126 secciones del tramo más viejo tenga exactamente esta forma
      (no se revisaron los 126 boletines uno por uno, solo una muestra).
- [x] **IEM completo — lectura de tablas**: hacer buscables los valores de
      todas las tablas individuales, no solo sus títulos. Añadir lectores para
      las familias de formatos que difieren del diseño común; conservar también
      una copia/vista fiel del archivo original cuando no sea seguro
      normalizarlo. Las formas ancha y larga comunes, y la vista segura, ya
      están cubiertas. Ahora también normaliza meses numéricos, nombres de meses en
      español, trimestres, tablas sin bloque de unidad explícito y matrices con
      varias columnas descriptivas. Una vista de las primeras filas cuenta como
      diagnóstico, no como cobertura completa.
      **Barrido en vivo 2026-09-01** sobre las 78 tablas del boletín vigente:
      77 (98.7 %) se extraen ya como `series_ancho`/`tabla_larga`/`series_matriz`;
      la única `vista` (`iem-1111-e`, "Encaje Legal") es de periodicidad
      semanal con columnas Año/Mes/Rango dispersas y una hoja de cálculo
      interna del BCE — un caso genuinamente único, no una familia recurrente.
      Repetido sobre 4 boletines de la era ZIP (No. 1854, 1900, 1950, 1975):
      encontró un bug real, no una forma de tabla nueva — 4 miembros del ZIP
      del boletín No. 1975 (`IEM-316b/312b/315a/322a.xls`) resultaban en
      `ValueError` porque son en realidad XLSX modernos (contenedor ZIP OOXML)
      con extensión `.xls` heredada; `xlrd.open_workbook` fallaba directo.
      Corregido con sniffing de bytes (`raw.startswith(b"PK")`) en vez de
      confiar en la extensión, igual que la regla ya documentada en
      `CLAUDE.md` para el campo `format` de CKAN — ver `_open_legacy_zip_member`
      en `helpers/bce_iem_client.py`. Tras la corrección, cero errores en los
      4 boletines muestreados; los 4-7 `vista` restantes por boletín son
      tablas legadas con jerarquías de encabezado genuinamente irregulares
      (tasas por semana, PIB por industria con encabezados fusionados a varios
      niveles), no una familia repetible. No se identificó ninguna familia de
      formato adicional que justifique un normalizador dedicado; la
      combinación actual de extractores + vista honesta ya cubre el archivo.
- [~] **BCEData ↔ IEM — mapa de equivalencias**: `compare_bce_sources` genera
      coincidencias candidatas por etiquetas normalizadas, alternativas,
      confianza y campos pendientes de revisión; `guardar_revision=true` y
      `scripts/audit_bce_equivalence.py` persisten una cola revisable. Sigue
      pendiente confirmar manualmente definición, unidad, frecuencia, fecha de
      corte, revisión y valores antes de declarar una equivalencia metodológica.
      Barrido vivo 2026-09-01 sobre el boletín disponible: 77 candidatos, una
      tabla IEM sin traslape y 2.352 etiquetas solo BCEData; 72 son posibles
      componentes de tabla, cuatro posibles tabla/grupo y solo una posible
      equivalencia directa. Ninguna se trata como duplicado confirmado hasta
      revisar valores y metodología.
      **Revisión manual 2026-09-02, dos candidatos confirmados con datos
      en vivo:**
      1. **Confirmada — equivalencia directa.** `id_grupo=101` (BCEData,
         "4.1.4 Ingresos y egresos por comercialización interna de
         derivados importados") ↔ `iem-414-e` (misma sección/título). Las
         8 series de BCEData (4 productos × precio importación/venta
         nacional) igualan los valores de `iem-414-e` mes a mes hasta ~13
         cifras significativas (ene-2025 verificado en las 4 líneas de
         producto). Es la misma tabla, republicada por dos rutas.
      2. **Confirmada parcial — tabla↔grupo.** `id_grupo=65` ↔ `iem-423-e`
         ("Salario Básico Unificado y Componentes Salariales"): la serie
         "SALARIO REAL PROMEDIO" de BCEData iguala exactamente la segunda
         fila de `iem-423-e` (ene-2025: 122.414726663655 en ambas). Pero
         `id_grupo=65` solo expone esa fila — el SBU nominal (fila 1 de la
         tabla IEM, 548.2638888888889 constante) no aparece bajo ninguna
         unidad de ese id_grupo. Confirma que la clasificación
         "posible_correspondencia_tabla_grupo" del tool es correcta aquí:
         cobertura parcial, no equivalencia completa.
      Los otros tres candidatos "tabla↔grupo" (riesgo país↔producción
      petrolera, derivados↔IPC, salario↔IPP) son falsos positivos por
      similitud de etiqueta — sin relación real, no revisados en detalle
      más allá de notar que los títulos no corresponden.
- [x] ~~BCE — prueba de completitud y frescura~~ **Descartado 2026-09-02**:
      requiere un scheduler con almacenamiento persistente de snapshots, que
      Daniel decidió no construir. `audit_bce_catalog`/`audit_bce_iem` ya
      hacen la comparación bajo demanda (no programada) cuando se invocan
      con `guardar_snapshot=true`/`guardar_catalogo=true`.

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
- [~] BCE — Información Estadística Mensual (IEM/IEEM), boletín mensual mucho más rico que BCEData. `search_bce_iem` indexa en vivo las tablas XLSX individuales del boletín vigente y, con `historico=true` o un rango de años, agrupa versiones de la misma tabla en el archivo mensual. Ahora reconcilia el índice histórico con “Últimas publicaciones”, reporta el rango/números faltantes detectados y cataloga también los enlaces PDF/ZIP completos de cada boletín. `get_bce_iem_table` devuelve series con filtro anual cuando detecta el formato tabular ancho, reconoce tablas largas, conserva una vista segura sin inventar columnas y devuelve el SHA-256 del XLSX leído. Pendiente: normalizadores dedicados, comparación explícita con BCEData y catalogación persistente de todo el archivo histórico. **Profundizado 2026-08-29**: cada boletín (archivo completo desde ene-1996) tiene ~60+ XLSX individuales por tabla, no solo el ZIP. → RESEARCH.md § Séptima pasada
- [x] BCE — **BCEData: auditoría viva de cobertura y metadatos**: `audit_bce_catalog` y `scripts/audit_bce_catalog.py` comparan `/tree` y cada `/bundle/{id_grupo}` bajo demanda, detectan grupos/series modificados, conservan el último snapshot completo y pueden probar valores `/grid` seleccionados por frecuencia/unidad. **Descartado 2026-09-02**: conectarlo a un scheduler con almacenamiento persistente — Daniel decidió no construir esa infraestructura; el flujo bajo demanda ya cubre lo que se necesita hoy. Comprobar cambios de revisión sigue sin aplicar porque la API no expone ningún marcador de revisión. Mantener la búsqueda por etiquetas de series y documentar que esta API pública no está formalmente documentada por el BCE.
- [~] BCE — **IEM: descubrimiento y catálogo histórico resistente**: ya no depende únicamente de `IndiceIEM.html`: reconcilia “Últimas publicaciones”, detecta boletines nuevos no listados, registra números faltantes, comprueba tablas XLSX individuales y expone la fecha de catalogación. `guardar_catalogo=true` y `scripts/audit_bce_iem.py` persisten el catálogo completo construido. La lectura normaliza tablas anchas/largas, meses numéricos y nombres de meses en español, incluso sin unidad explícita; siguen pendientes más familias específicas y hashes masivos de archivos. No presenta el IEM más reciente encontrado como “actual” sin informar su boletín.
- [ ] BCE — **búsqueda ampliada y mapa completo de fuentes**: revisar más allá de BCEData e IEM el sitio institucional, publicaciones temáticas, catálogos, archivos históricos y descargas por sector. Inventariar cada fuente, su cobertura, frecuencia, formato, API/archivo y traslape con lo ya integrado; priorizar únicamente tablas que añadan detalle ecuatoriano verificable, no duplicados de una misma serie. El resultado debe ser un mapa de cobertura y una lista corta de integraciones justificadas.
- [x] BCE — **Remesas de trabajadores** (`search_bce_remesas`, `helpers/bce_remesas_client.py`): resultados agregados, serie histórica y bases mensuales, incluida la desagregación por entidad disponible desde julio de 2025. Metadata y URL directa solamente (mismo patrón que SIPA); el tool deja explícito que "histórica" (pre-cambio) y "BDD" (post-cambio) son series metodológicamente distintas, según la nota de comparabilidad de la propia página. → https://contenido.bce.fin.ec/series-de-datos-remesas-de-trabajadores/
- [x] BCE — **familia de "indicadores en línea" construida 2026-08-31: `list_bce_indicadores_diarios`/`get_bce_indicador_diario` (`helpers/bce_indicadores_diarios_client.py`).** Descubierta y confirmada en vivo 2026-08-30/31, pedido explícito de Daniel ("investiga más y más", luego "Do all remaining BCE"). Varias páginas de `contenido.bce.fin.ec` (`estadisticas-de-publicaciones-generales`, `estadisticas-del-sector-medios-y-sistemas-de-pagos`, `estadisticas-del-sector-real`, `estadisticas-del-sector-externo-d`) incrustan un widget Highcharts por indicador (`wp-content/uploads/ESTADISTICAS-ECONOMICAS/indicadores/{Nombre}.html`), cada uno apuntando a un archivo JSON plano compartido entre varios widgets — sin auth, sin API key, confirmado con `curl` puro. Resuelve de una vez el ítem de abajo ("medios y sistemas de pago") — SPI/SCI/SPL/CCC/Monto Recaudado sí son automatizables, mensuales desde 2010 (`datos_pagos.json`). Catálogo confirmado por archivo:
  - `datos_formulario.json` (4.4 MB): **Riesgo País** (D, 2004-07-29→hoy, 7369 filas) y **Precio del Oro** (D, 1999-01-01→hoy, 7213 filas). Riesgo País es el hallazgo que motivó la búsqueda — Daniel pidió cubrirlo específicamente después de que `search_indicadores_bce`/BCEData solo devolviera un agregado mensual (id_grupo 8) para algo que el propio BCE republica diariamente.
  - `datos_diarios.json` (3.5 MB): Precio Petróleo WTI (D, 2015→hoy), Índice Dow Jones (D, 2018→hoy), Tasa LIBOR (D, 2013-2024, discontinuada), Tasa SOFR (D, 2022→hoy).
  - `datos_bonos_soberanos.json` (2.1 MB): precios diarios de los bonos soberanos Ecuador 2030/2035/2040 (% del valor nominal, D, 2020-09-02→hoy).
  - `datos_pagos.json` (285 KB): SPI, SCI, SPL, CCC, Monto Recaudado Servicios Básicos — mensuales desde 2010 (más dos series SPI/PIB y SCI/PIB anuales).
  - `datos_hid.json` (1.4 MB): **Producción Petrolera Nacional** (D, 2018-01-01→hoy, 3154 filas — genuinamente diaria, valiosa por la dependencia fiscal del petróleo) y Precio Petróleo Crudo Ecuatoriano (M).
  - `datos_ipc.json`, `datos_tes.json`, `datos_icc.json`, `datos_cna.json`: inflación, desempleo, confianza del consumidor y PIB — mensual/trimestral/anual, probablemente duplican BCEData pero en un formato más limpio de consultar.
  Ninguno de estos archivos aparece en el buscador del propio sitio bce.fin.ec ni en BCEData — se llegó a ellos seleccionando "riesgo país" en un agregador financiero de terceros que citaba `contenido.bce.fin.ec/estadisticas-de-publicaciones-generales/` como fuente, y desde ahí leyendo el HTML del widget para encontrar su archivo de datos. **Construido:** el catálogo se descubre en vivo desde los datos mismos (no hardcoded — un "código" solo significa algo dentro de su propio archivo), confirmado con las 29 series reales encontradas en los 9 archivos (incluye 2 bonos soberanos, 2034/2039, que no se habían visto en la investigación original). `get_bce_indicador_diario` nunca devuelve la serie completa (Riesgo País tiene 7369+ filas) — solo una ventana acotada (últimos N o rango de fechas explícito, tope 366) más el rango completo como metadata.
  **Barrido completo del mega-menú, 2026-09-02.** Solo 4 de las 7 secciones de nivel superior de "Estadísticas" se habían revisado. Las 2 no revisadas (`estadisticas-del-sector-monetario-d-2`, `estadisticas-del-sector-fiscal`) sí tenían el widget, y `estadisticas-del-sector-externo-d` — ya "revisada" — tenía 7 widgets más que el barrido original no encontró por seguir solo los que compartían archivo con indicadores ya conocidos. 4 archivos nuevos:
  - `datos.json` (`view_ind_monetario`): Reservas Internacionales, Liquidez Total M2, Crédito al Sector Privado (empresas y hogares), Captaciones OSD (Total), Tasa Activa/Pasiva Referencial — mensual, 2000/2003/2015→hoy.
  - `datos_fiscales.json` (`view_ind_fiscales`): Total Ingresos SPNF, Total Erogaciones SPNF, Resultado Global SPNF (% del PIB), Saldo Deuda Pública Interna — mensual, 2000→hoy.
  - `datos_bpa.json` (`view_ind_externo_bpa`): Cuenta Corriente, Remesas de Trabajadores Recibidas (trimestral, 2016→hoy), Índice Tipo de Cambio Efectivo Real (mensual, 1995→hoy).
  - `datos_cxt.json` (`view_ind_externo_cxt`): Saldo Balanza Comercial, Balanza Comercial no Petrolera, Exportaciones de Bienes, Importaciones de Bienes — mensual, 1990→hoy. Usa "Código Variable Dinámica" como los 9 archivos originales, no "id_serie".
  Los 3 archivos nuevos "id_serie" (`datos.json`/`datos_fiscales.json`/`datos_bpa.json`) no tienen "Código Variable Dinámica" — el código de serie es un int en `id_serie`, y añaden un campo "Grupo" que los 9 archivos originales no tienen. `_codigo()` unifica ambos esquemas detrás de una sola interfaz string. Catálogo total: 49 series (antes 29). Verificado completo contra la página de inicio de `contenido.bce.fin.ec`, que agrega los widgets de todas las secciones en un solo lugar (40 `data-dd-title` distintos) — los 40 resuelven ahora a un archivo conocido.
- [ ] BCE — **Cuentas Nacionales completas**: investigar los paquetes anual, trimestral y regional, retropolación, Tabla Oferta-Utilización, Cuadro Económico Integrado y Matriz de Empleo e Ingresos. IEM/BCEData pueden contener partes, pero la integración debe conservar la metodología de base móvil, revisiones, frecuencia y carácter provisional/definitivo. → https://contenido.bce.fin.ec/estadisticas-de-cuentas-nacionales/
- [ ] BCE — **EMOE y coyuntura**: investigar el Estudio Mensual de Opinión Empresarial, metodologías, expectativas económicas, confianza del consumidor, ciclo económico, inflación, mercado laboral, pobreza/desigualdad y crédito. Reutilizar BCEData/IEM cuando ya sean la misma serie; añadir solo archivos, cortes o metadatos que falten. → https://contenido.bce.fin.ec/documentos/PublicacionesNotas/Indicador_coy.html
- [ ] BCE — **paquetes sectoriales**: auditar por separado petróleo, minería, cemento, agricultura y compra/venta de divisas. Para cada uno, decidir si basta BCEData/IEM o si hace falta un cliente de publicaciones/archivos; conservar frecuencia, fecha de corte y revisión. → https://contenido.bce.fin.ec/ultimas-publicaciones/
- [ ] BCE — **índices de precios de comercio exterior**: verificar si las series IPX/IPM/ITI que aparecen en BCEData tienen la misma cobertura que la página dedicada; integrar la metodología, series históricas y archivos de exportación/importación solo si aportan detalle adicional. → https://contenido.bce.fin.ec/estadisticas-de-indice-de-precios-de-comercio-exterior/
- [~] BCE — **catálogo de publicaciones, calendario y archivo histórico**: añadir búsqueda de “Últimas publicaciones”, Cifras Económicas del Ecuador, boletines monetarios/financieros, informes y metodologías, con fecha de publicación, período cubierto, formato y URL. Esto complementa las series de BCEData y las tablas IEM. → https://contenido.bce.fin.ec/ultimas-publicaciones/
  **Construido 2026-09-01 para "Últimas Publicaciones"**: `search_bce_publicaciones`
  (`helpers/bce_publicaciones_client.py`). Confirmado en vivo: la página renderiza
  una sola tabla HTML estática vía un shortcode (`bce-ultimas-publicaciones`) — sin
  AJAX, sin ruta `wp-json` propia, sin paginación. Extrae fecha (texto español
  largo, parseado a ISO), título, URL directa y formato — el formato se deriva de
  la extensión de la URL, no del ícono decorativo de la fila (confirmado en vivo:
  dos filas con el mismo formato real HTML usan íconos `file-web` distintos según
  criterio editorial, uno de ellos genérico "gráfico"). Verificado en vivo
  extremo a extremo contra la página real: 30/30 filas parseadas correctamente,
  cero fechas o formatos sin reconocer. Límite real, no solucionable desde esta
  página: solo expone su ventana rodante (~30 publicaciones más recientes), sin
  parámetro de fecha ni paginación — no es un archivo histórico completo.
  **Sigue pendiente**: Cifras Económicas del Ecuador y cualquier calendario de
  publicaciones futuras viven en páginas distintas, no investigadas todavía.
- [x] SIPA (Ministerio de Agricultura) — `list_sipa_modulos`/`get_sipa_modulo_archivos`, 30 archivos Excel reales en 4 módulos (económico/productivo/social/censos), verificado en vivo. → RESEARCH.md § Sitios de ministerios individuales
- [x] Contraloría General del Estado — `list_contraloria_informes`/`get_contraloria_informe`, CSV trimestrales reales de informes de auditoría aprobados a cualquier institución pública, verificado en vivo. De paso corrigió un bug real en el sniffing de delimitador CSV compartido (`helpers/csv_reader.py`). → RESEARCH.md § Sitios de ministerios individuales
- [x] Contraloría — "Plan anual de control", mismo patrón `WFDescarga.aspx` ya implementado en `helpers/contraloria_client.py` (solo cambia `tipo`, más un segundo seed page `Portal/Sistema/PlanAnualControl`). `get_contraloria_informe` distingue el `tipo` no-CSV y devuelve metadata + puntero a `read_pdf` en vez de intentar `preview_csv`. → RESEARCH.md § Séptima pasada
- [x] SRI — `estadisticas-generales-de-recaudacion-sri` (`search_sri_estadisticas_recaudacion`), reportes XLSX mensuales de recaudación por provincia/cantón/sector, separado y complementario a `/datasets` ya cubierto. Etiquetas derivadas del nombre de archivo (la página usa una librería documental Liferay Alfresco con texto de enlace genérico). → RESEARCH.md § Séptima pasada
- [x] gob.ec — `tramites-transparencia/{tramite_id}` (`get_tramite_estadisticas`, construido 2026-09-01): serie mensual real de atenciones/quejas por trámite desde 2021 (confirmado en vivo: 63 meses para Cédula de Identidad, may-2021→jul-2026), sin auth. Sigue sin haber endpoint masivo — se pide trámite por trámite, igual que `get_tramite_info`. → RESEARCH.md § Séptima pasada
- [ ] Sector eléctrico (CENACE/ARCONEL/CNEL) — **dominio nuevo, pedido explícito de Daniel 2026-08-29, profundizado el mismo día**. CENACE (45), CNEL EP (40), ARCONEL/ARCERNNR (1 dataset pero 54 recursos BNEE), e IIGE (19, tangencial) ya tienen organización CKAN, alcanzables hoy sin código nuevo. `reportes.arconel.gob.ec` **descifrado técnicamente** — ASP.NET ReportViewer, 3 POSTs secuenciales con replay de ViewState + un POST final renderiza tablas HTML reales, sin login, cubre 1998-2026 por parroquia/empresa/mes — la fuente más rica de todo el proyecto, ya no falta investigar cómo, solo construir el scraper stateful. CENACE Biblioteca tiene documentos de planificación sin tocar (Plan Maestro de Electricidad 2023-2032, Planes Operativos Anuales, factores de emisión CO₂, informes de indisponibilidad de transmisión). EEQ/Centrosur/EERSA/EEASA sin organización CKAN propia; Centrosur tiene 2 PDFs reales + Power BI. `sisdatbi.arconel.gob.ec` es un sistema BI interno con login, descartado. → RESEARCH.md § Octava pasada
- [ ] Sector eléctrico — **archivo histórico de cortes de luz programados, crisis sep-dic 2024** (ítem distinto al de arriba: es un registro de incidente histórico, no una fuente continua). EEQ (Quito) sigue sirviendo en vivo los PDFs originales barrio/hora de la crisis (`eeq.com.ec/documents/d/empresa-electrica-quito/{slug}`, confirmado descargando uno real de oct-2024) — no hace falta Wayback Machine, solo enumerar los slugs (naming manual/inconsistente). CNEL (Guayaquil/costa, el objetivo más grande) probablemente perdió el archivo de su sitio en vivo — reintentar con Wayback Machine (caído durante esta investigación) o adivinar rutas `wp-content/uploads/2024/09-12/`. CENACE/ARCONEL solo publicaron la capa regulatoria, no horarios por barrio. → RESEARCH.md § Octava pasada
- [ ] Sector eléctrico — **`sisdatbi.arconel.gob.ec` (SISDAT BI), revisitar**. Descartado en la Octava pasada como "sistema BI interno con login", pero no se profundizó más allá de la pantalla de login — pedido explícito de Daniel 2026-08-30: confirmar si hay un modo público/embed (dashboards Power BI a veces exponen un `reportEmbed`/iframe público sin credenciales, o un rol de "invitado"), si el login es realmente obligatorio para todo contenido o solo para ciertos tableros, y si hay una API REST detrás del BI que no requiera la sesión del portal. Tratar como sospecha sin confirmar, no como bloqueo definitivo.
- [ ] Sector eléctrico — **CELEC EP: reportes propios de transparencia/rendición de cuentas**, pedido explícito de Daniel 2026-08-30. CELEC (generación) es distinta de CENACE/ARCONEL/CNEL, ya evaluadas; no se ha confirmado todavía si sus informes de rendición de cuentas/LOTAIP están en `celec.gob.ec` como PDFs sueltos, en un portal de transparencia separado, o si ya están cubiertos indirectamente por la organización CKAN de CENACE. Investigar desde cero: URL del portal, formato, frecuencia, y si duplica algo de lo que ya expone CENACE Biblioteca.
- [x] Sector eléctrico — **CENACE: `www.cenace.gob.ec/info-operativa/InformacionOperativa.htm`** → `helpers/cenace_client.py`, `get_cenace_tablero`. Confirmado con browser (network tab vacío en los 5 cambios de pestaña): la página entera es server-rendered en una sola carga, sin AJAX — 5 tableros fijos (produccion_tiempo_real, demanda_tiempo_real, operativa_diaria, acumulada_mensual, acumulada_anual), cada uno un snapshot "a este instante" (hoy/ayer/mes a la fecha/año a la fecha) sin selector de fecha y sin serie histórica real detrás — confirmado que no la hay, no solo "sin confirmar". Extrae los 6 números de resumen (producción total/exportación/importación/hidráulica/térmica/renovable no convencional, o el equivalente de demanda) desde `<div class="resumen-box">`, más el desglose por distribuidora (19 empresas eléctricas/CNEL) desde los `<title>` del mapa SVG en demanda_tiempo_real. Deliberadamente no se extrae el desglose por planta/tipo de combustible ni la curva horaria de 24h — ambos solo viven dentro de blobs `Plotly.newPlot(...)` envueltos en una plantilla de tema compartida de 15+ KB; los 6 números de resumen ya cubren el valor real del tablero (mezcla de generación y demanda en vivo). `www.cenace.gob.ec` necesitó el mismo fallback OS-trust-store que `censoecuador.gob.ec`/`superbancos.gob.ec` (cadena de certificado le falta una CA intermedia en el bundle de certifi, no un cert roto). TTL de caché corto (180s) porque el tablero "tiempo real" cambia constantemente.
- [ ] CNT/ARCOTEL (telecomunicaciones) — **dominio nuevo**. ARCOTEL ya tiene org CKAN (9 datasets, pero congelada desde 2021/2022) y CNT también (2 datasets, frescos). El hallazgo real está fuera de CKAN: Reportes Estadísticos Mensuales de ARCOTEL (PDF, serie completa 2023-2026, ~4 meses de rezago) — solo PDF, sin CSV/API. → RESEARCH.md § Octava pasada
- [x] IG-EPN — `servicios/busqueda-informes` (`search_informes_igepn`/`get_informe_igepn`, `helpers/igepn_informes_client.py`), construido 2026-08-31. Resultó ser bastante más complejo de lo que sugería la descripción original ("buscador filtrable por tipo/volcán/fecha, sin login visible"): la página es una app JSF/PrimeFaces separada en `informes.igepn.edu.ec`, sin URL estable por documento — cada descarga requiere una sesión (`javax.faces.ViewState` + cookie), un POST AJAX de "Buscar" que re-renderiza la lista con un ViewState nuevo, y un POST plano del botón "Descargar Informe" de esa fila reusando la misma sesión. Confirmado en vivo extremo a extremo, incluida una descarga PDF real y extracción de texto. Hallazgo real durante la construcción: los filtros "Tipo de informe" y "Volcán" del propio sitio **no acotan resultados en el servidor** — confirmado repitiendo el payload AJAX exacto de un browser real capturado con un hook a `jQuery.ajax`, byte a byte, y aun así obteniendo resultados mezclados de todos los volcanes. Solo "Tipo" (Sísmico/Volcánico) y "Año" filtran de verdad; `search_informes_igepn` solo envía esos dos y filtra el resto client-side sobre la página más reciente (mismo patrón de `search_sismos`: reciente y no exhaustivo, no una cobertura completa), documentándolo en la propia respuesta. `helpers/pdf_reader.py` ganó `extract_text_from_bytes()` (separado de `read_pdf`) para no duplicar el manejo de pypdf en un flujo que, a diferencia de cualquier otro PDF de este proyecto, nunca tuvo URL.
- [ ] SGR — archivo de "Informes de Situación" (SITREP, 2016-2026) y "Biblioteca" (mapas de amenaza/vulnerabilidad, rutas de evacuación) en `gestionderiesgos.gob.ec`, fuera del snapshot ArcGIS ya integrado. Formato exacto por confirmar. → RESEARCH.md § Séptima pasada
- [ ] SIPA — geoportal (`geoportal.agricultura.gob.ec`, solo HTTP) corre un backend GeoServer WMS completo (uso de suelo, suelos, riesgos agroclimáticos, catastro rural), mucho más allá de las ortofotos ya anotadas — falta confirmar si expone WFS para exportar vectores, no solo teselas de mapa. Los boletines nacionales (Panorama Agroestadístico y similares) son PDFs directos, sin fricción. Los tableros "Cifras Agroproductivas/Territoriales" están confirmados rotos en producción — no perseguir. → RESEARCH.md § Séptima pasada
- [ ] SIPA — **`sipa.agricultura.gob.ec/index.php/sipa-estadisticas/tablero-dinamico/indicadores-sectoriales`, encontrado 2026-08-31**, distinto de los 4 módulos "estadisticas-descargas" ya cubiertos por `helpers/sipa_client.py`. Página real (título "Indicadores Sectoriales"), con nav propio hacia "Indicador Agroeconómico", "Indicador Agrosocial", "Informe de Rendimientos Objetivos" (arroz), "Hoja de Balance de Alimentos", "Atlas Agroeconómico del Ecuador", "Panorama Agroeconómico" — sin confirmar todavía si son PDFs directos (como los boletines ya cubiertos) o un tablero interactivo tipo Power BI/Tableau que necesitaría el mismo tipo de descifrado que SUT.
- [ ] Ministerio de Salud Pública (`salud.gob.ec`) — dominio confirmado vivo con contenido real (barrido de endpoints 2026-08-29), sección de transparencia/LOTAIP presente, pero sin sección de estadísticas/datos abiertos visible en la portada — no se profundizó más allá de confirmar que el sitio está vivo, falta una pasada de contenido completa. → RESEARCH.md § Séptima pasada
- [ ] Registro Oficial (gaceta oficial) — candidato de alta prioridad para búsqueda por fecha; posiblemente no relevante, ver nota de alcance. → RESEARCH.md § Datos legislativos
- [ ] INEVAL — exámenes nacionales (Ser Bachiller/ENES, Ser Estudiante, Ser Maestro...), archivo real sin login/captcha. → RESEARCH.md § INEVAL
- [x] Superbancos — `list_superbancos_secciones`/`get_superbancos_seccion_archivos` (`helpers/superbancos_client.py`), construido 2026-08-30. Cubre Boletines Financieros Mensuales, Servicios Financieros, Información Histórica (comportamiento financiero anual + Reporte de Estabilidad Financiera) y Calendario Estadístico.
- [x] Superbancos — **widget OneDrive de Boletines Financieros, descifrado 2026-08-30 (pedido explícito de Daniel: "fix!").** El diagnóstico inicial de "URLs firmadas de corta duración, no descifrable sin más" era incorrecto — se resolvió conduciendo el widget real en un browser (`mcp__Claude_Browser__*`), capturando el POST que dispara (`wp-admin/admin-ajax.php`, `action=shareonedrive-get-filelist`) con `listtoken`/`account_id`/`drive_id` (atributos `data-*` del propio widget) y `_ajax_nonce` (`ShareoneDrive_vars.refresh_nonce` inline en la página) — los cuatro valores están en el HTML estático de la página, sin sesión ni cookies, confirmado replicando la llamada con `httpx.post` puro. Las URLs de descarga que devuelve son un proxy same-site (`action=shareonedrive-download`) estable, no un token de Microsoft Graph de corta duración — otra suposición incorrecta corregida. `boletines_financieros` ahora trae 224 archivos verificados en vivo: 1997-2008 desde la tabla estática + carpetas "Año 2009"…"Año 2026" (12 boletines/año, 2026 con los meses publicados hasta la fecha) desde OneDrive, con nombre, tamaño y fecha de modificación reales. Un bug real de extracción (el nombre se tomaba del `data-name` del `<div>` contenedor, que no lleva extensión, en vez del `data-name` del propio `<a>` de descarga) se detectó revisando la salida real end-to-end, no solo por los tests, y se corrigió antes de cerrar el ítem.
- [x] **Superbancos — `servicios_financieros` sus 3 widgets OneDrive conectados 2026-08-31, pedido explícito de Daniel ("Let's do 1").** El tercer widget sin encabezado identificado resultó ser "Estadísticas Generales" (encabezado real, hallado ampliando la ventana de búsqueda a 5000 caracteres) — 9 categorías numeradas (A06, A09, A10, A12, POS/A13, Puntos de Atención/C71, Gestión de Cobranzas, Recaudación de Pagos a Terceros, Retiros de Dinero), cada una organizada por año. Es la consolidación "Estadísticas Puntos de Atención" que la propia página dice reemplazó las tablas estáticas desde mayo 2021. Los otros dos widgets también resueltos: "Solicitudes de Servicios Financieros, Canales y Medios de Pago" (plantillas de formularios de registro, no series) y "Resoluciones de Servicios Financieros, Tarjetas y Canales" — **esto cierra el ítem de abajo, "Resoluciones y Circulares AJAX-blocked", que llevaba mucho tiempo marcado sin resolver.** A diferencia de boletines (carpetas planas "Año NNNN"), la llamada raíz del widget aquí ya devuelve el árbol COMPLETO con punteros a padre (confirmado en vivo) — se generalizó el crawler (`_wpcp_crawl_tree`) para recorrer cualquier profundidad en vez de asumir un solo nivel, y cada resultado lleva el breadcrumb completo como `grupo` (varias categorías reutilizan nombres de subcarpeta como "Otros Años", así que el nombre solo sin el camino completo sería ambiguo). Total: 312 archivos en `servicios_financieros` (antes ~68 solo estático). **Bug real encontrado y corregido en el proceso** (detectado revisando la salida real, no solo que el regex matcheara): el enlace "entry_link" que el parser usaba cambia de clase según si OneDrive puede previsualizar el archivo en línea (`entry_action_download` para ZIP, `ilightbox-group` para XLSX/PDF) — como casi todo en este widget es XLSX, el regex anterior (anclado a una sola variante) descartaba silenciosamente ~35% de los archivos reales con una advertencia fácil de pasar por alto. Corregido apuntando al botón de descarga dedicado (`class='entry_action_download '`, sin prefijo "entry_link"), presente y con la misma forma para cualquier tipo de archivo — también más simple, su propio atributo `download='...'` da el nombre con extensión directamente. → RESEARCH.md § Décima pasada
- [ ] Superbancos — Balances Generales/Patrimonio Técnico/indicadores de morosidad-liquidez-solvencia siguen sin resolver — a diferencia de Resoluciones (arriba, ya resuelto), estos viven detrás de una herramienta de consulta propia, no de un widget OneDrive, y probablemente necesitan una pasada con browser para confirmar si son automatizables. Catastro de Compañías bloqueado por login, descartado. → RESEARCH.md § Séptima pasada
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
- [ ] **INAMHI — `geoservicios.inamhi.gob.ec`, dominio nuevo, pedido explícito de Daniel 2026-08-31.** Confirmado vivo, corre un backend GeoServer real (`geoserver/wms` visible en el HTML) — probablemente capas de precipitación, temperatura, estaciones hidrometeorológicas, alertas. Sin profundizar más allá de confirmar que el servidor existe: falta el listado de capas (GetCapabilities de WMS/WFS), si hay datos tabulares de estaciones descargables además de los mapas, y si INAMHI tiene organización CKAN propia (sin verificar todavía).
- [ ] **Calidad del aire de Quito — `aireambiente.quito.gob.ec`, dominio nuevo, pedido explícito de Daniel 2026-08-31.** Confirmado que el dominio responde (HTTP 200) pero sin `<title>` ni contenido en el HTML crudo — parece ser una aplicación de una sola página (SPA) que renderiza todo por JS, así que monitoreo de calidad del aire en tiempo real (probablemente la red de estaciones REMMAQ) necesitará una pasada con browser real o encontrar su API subyacente antes de saber si es automatizable.
- [ ] **Aviación civil — `www.ais.aviacioncivil.gob.ec` (IFIS: Internet Flight Information System), dominio nuevo, pedido explícito de Daniel 2026-08-31.** Confirmado vivo con secciones públicas reales: `/metar` (reportes meteorológicos de aeródromo), `/notam` (avisos a aviadores), `/sigmet` (alertas meteorológicas significativas), `/aerodromo/show` — todos genuinamente de alta frecuencia (METAR se actualiza cada 30-60 min por aeródromo). Los planes de vuelo (`/fpl/*`) están detrás de `/usuario/login`, descartados. Sin confirmar todavía: si `/metar`/`/notam`/`/sigmet` son de acceso público sin cuenta, y en qué formato (HTML/texto plano/XML) — el estándar aeronáutico internacional para estos tres es texto plano de ancho fijo, generalmente sí público sin autenticación en portales AIS oficiales, pero no verificado en este caso concreto.
- [ ] **Cancillería y embajadas — dominio(s) sin identificar, pedido explícito de Daniel 2026-08-31** ("cancilleria, embajadas, etc."). Sin investigar: `cancilleria.gob.ec` ya aparece mencionado de pasada en la Séptima pasada como uno de los dominios vivos del hosting compartido del Estado, pero nunca se hizo una pasada de contenido dedicada — trámites consulares, apostillas, estadísticas migratorias, o datos de la red de embajadas/consulados son candidatos sin confirmar.
- [~] **ARCSA (Agencia Nacional de Regulación, Control y Vigilancia Sanitaria) — investigado 2026-08-31, pedido explícito de Daniel.** Organización CKAN real (`agencia-nacional-de-regulacion-control-y-vigilancia-sanitaria-arcsa...`) con solo 4 datasets, todos sobre registros sanitarios/permisos de funcionamiento **suspendidos o cancelados** de medicamentos — actualización semestral, ya alcanzable con `search_organizations`/`list_dataset_resources` sin cliente nuevo. El dato realmente valioso — el registro sanitario completo *vigente* (no solo lo cancelado), confirmado por búsqueda web como "Base de Registros Emitidos" en `controlsanitario.gob.ec/base-de-datos/` (productos naturales, medicamentos homeopáticos, actualizado a junio 2026) — **no se pudo verificar**: `www.controlsanitario.gob.ec` está caído (reset de conexión TLS tras renegociación, confirmado con `curl` y con `httpx` en Python — mismo patrón exacto que `inclusion.gob.ec`, no es un problema del cliente). Un subdominio sí vive (`permisosfuncionamiento.controlsanitario.gob.ec/consultorciudadano/`, "ARCSA-Notificaciones") pero es un formulario de login real, sin acceso de invitado visible — mismo patrón de bloqueo ya descartado para Superbancos Catastro/SENESCYT. Pendiente: reintentar `controlsanitario.gob.ec` más adelante (podría ser una caída transitoria, a diferencia de `inclusion.gob.ec` que lleva meses muerto) antes de descartar la "Base de Registros Emitidos" del todo.
- [ ] Vivienda MIDUVI — dominio caído a nivel TLS, sin reemplazo encontrado; CKAN cubre parcialmente. → RESEARCH.md § Vivienda
- [ ] Prensa — SECOM/Presidencia y Fundamedios, sin profundizar. → RESEARCH.md § Prensa
- [ ] Datos legislativos/normativos (jurisprudencia, proyectos de ley) — investigado a fondo; **Daniel señaló que puede no ser relevante** para el alcance del proyecto. → RESEARCH.md § Datos legislativos
- [ ] Fuentes internacionales con foco Ecuador — investigar **CEPAL/CEPALSTAT**, el **FMI/IMF** (pedido explícito de Daniel 2026-08-30: variables macro trimestrales — candidatos concretos son IFS/International Financial Statistics para series trimestrales de balanza de pagos/reservas/tipo de cambio, el WEO database para proyecciones, y los Article IV Staff Reports para el análisis narrativo con series propias), agencias de la **ONU** y, cuando tengan datos específicamente útiles para Ecuador, Banco Mundial, OIT, FAO, OMS/OPS, UNESCO, OIM y organismos regionales. Para cada fuente: confirmar acceso real (API/bulk/archivo — el FMI tiene una API REST pública para IFS/WEO sin key, por confirmar cobertura y campos exactos para Ecuador), indicador y desagregación disponibles para Ecuador, historia, frecuencia, licencia, fecha de actualización y duplicación frente a INEC/BCE/ministerios. Integrar solo lo que aporte una serie, corte o frecuencia (ej. trimestral cuando BCE solo publica mensual/anual) que la fuente ecuatoriana no publique; conservar siempre fuente y definición original — el valor de estas fuentes suele ser la comparabilidad internacional y la metodología armonizada, no un dato más nuevo que el de BCE/INEC. CEPAL y FMI son los primeros candidatos. → RESEARCH.md § Fuentes externas
- Confirmados sin acción posible (bloqueos reales, no falta de esfuerzo): CNE y micrositio de Interior (WAF Incapsula), Aduana/SENAE comercio exterior (no publicado, solo por oficio — FEDEXPOR cubre el hueco), Fiscalía (sin dataset agregado propio), Supercías Valores/Seguros (login-gated, casi todo, un solo PDF estático encontrado), SERCOP catálogo/órdenes de compra (CAPTCHA), IG-EPN `descarga-de-datos` (cuenta obligatoria), Superbancos Catastro de Compañías (login obligatorio). → RESEARCH.md § Sitios de ministerios individuales / § Séptima pasada
- [~] **SRI Saiku — `list_sri_saiku_cubes`, `describe_sri_saiku_cube`, `query_sri_saiku_aggregate`**: construidos como superficie anónima, de solo lectura y limitada a una dimensión/medida y 100 filas. La sesión, descubrimiento y metadatos se validan antes de consultar; no se permite MDX arbitrario, drill-through, exportación ni escritura. Pendiente: verificación contra el endpoint vivo desde un entorno con conectividad; la sesión actual no pudo alcanzar el host SRI.
- ANDA — reconfirmado 2026-08-29: cobertura completa (437 encuestas, coincide con lo ya documentado), sin gap real, solo una limitación menor de UX (no se puede filtrar por tema del lado del servidor). **Corregido 2026-08-29 (segunda revisión, pedido de Daniel): "sin gap real" era incorrecto para ENEMDU específicamente** — ver el ítem nuevo de abajo (ENEMDU/mercado laboral post-2023 sin cubrir en ningún tool actual). → RESEARCH.md § Séptima pasada / § Novena pasada
- [x] **`search_inec_publicaciones`/`get_inec_publicacion_archivos` — nuevos tools sobre la API REST pública de WordPress (`/wp-json/wp/v2/posts`), en vez de depender solo del scraping de páginas de tema.** Construido 2026-08-30. Corrección importante que motivó esto (Daniel aportó URLs reales que refutaron el diagnóstico anterior de este mismo roadmap): `search_inec_estadisticas`/`get_inec_estadistica_files` derivaban su lista de "temas" del menú (mega-menu) de una sola página semilla — pero **el menú no es el mismo en cada página del sitio**. La página `estadisticas-laborales-enemdu/` tiene su propio submenú con `enemdu-anual/`, `enemdu-trimestral/`, `enemdu-telefonica/`, `matrices-de-transicion-laboral/`, ninguno alcanzable desde la página semilla original — y `enemdu-anual/` tenía el ENEMDU anual 2025 completo (BDD SPSS/CSV, boletín técnico, tabulados) todo el tiempo. Dos arreglos, no uno solo:
  1. `search_topics`/`get_topic_files` (la capa vieja) ahora fusiona **dos** páginas semilla y captura también los ítems de submenú desplegable (`<li class="menu-item...">`, markup distinto del `mega-menu-link` de nivel superior) — de 74 a 89 temas descubiertos, incluyendo las 4 páginas de ENEMDU que faltaban. Reduce el problema, no lo elimina del todo (sigue dependiendo de qué semillas se usen).
  2. **Capa nueva, autoritativa:** `search_inec_publicaciones`/`get_inec_publicacion_archivos` consumen directamente `/wp-json/wp/v2/posts` (API REST pública de WordPress, sin auth) — 1,707 posts totales confirmados en vivo, el más nuevo a días de la consulta, con búsqueda de texto completo real (confirmado: "subempleo" encuentra posts cuyo título no contiene la palabra), `orderby`/`offset` para paginación honesta, y el HTML de cada post trae los enlaces a archivos directamente. Noticias y Boletines (`/institucional/...`) resultaron ser solo vistas filtradas por categoría de esta misma colección — no hizo falta el scraper de Noticias planeado originalmente. Verificado extremo a extremo en vivo a través del tool MCP real (`main.mcp.call_tool`), no solo la capa de helper: `get_inec_publicacion_archivos("https://www.ecuadorencifras.gob.ec/enemdu-anual/")` devuelve los 11 archivos reales del ENEMDU anual 2025, el mismo archivo que arrancó toda esta investigación. 15 tests nuevos (`tests/test_inec_client.py`), 288 tests totales pasando. → RESEARCH.md § Novena pasada
- [x] Las 4 categorías "macro" del menú de INEC (Estadísticas Macroeconómicas, Cuentas económicas, Comercio internacional y balanza de pagos, Finanzas públicas/fiscales) — **confirmado 2026-08-30 que están vacías por diseño, no por el mismo bug de descubrimiento que ENEMDU.** Buscadas en vivo vía `/wp-json/wp/v2/posts?search=` con "cuentas nacionales", "PIB", "balanza de pagos", "finanzas públicas", "deuda pública", "estadísticas macroeconómicas": ningún resultado es una publicación propia de INEC sobre esos temas — todo lo que existe bajo "Estadísticas Económicas" son las Cuentas Satélite (Salud, Educación, Trabajo No Remunerado, Energía) y el Registro Estadístico de Empresas, nunca Cuentas Nacionales/Balanza de Pagos/deuda. Confirma la hipótesis: esa responsabilidad es del BCE (ya cubierto por `search_indicadores_bce`/IEM), INEC nunca publicó nada propio ahí. → RESEARCH.md § Novena pasada
- [x] `read_pdf` ahora valida extensión/Content-Type antes de descargar (2026-08-30) — rechaza extensiones conocidas no-PDF (.zip/.xlsx/.csv/...) sin hacer ninguna petición, y cuando la URL no tiene extensión reconocible cae a un sniff de Content-Type (solo headers, sin cuerpo) antes de comprometerse a la descarga completa. Antes bajaba hasta 5 MB de un ZIP grande inútilmente antes de fallar con "no es un PDF válido".
- [~] **INEC (y en general): no hay preview de archivos grandes (ZIP/BDD), a diferencia de CKAN.** `get_inec_publicacion_archivos`/`get_topic_files` solo devuelven metadata (label/url/formato) — nunca descargan el archivo, por diseño (igual que SIPA). A diferencia de los recursos CKAN, que tienen `preview_zip`/`preview_targz` para ver una muestra de filas sin bajar todo, no había ningún tool que mostrara una vista previa de un ZIP/BDD de INEC (ej. el REESS `200901_202412_REESS_MENSUAL_BDD_DEFINITIVAS.zip`, confirmado en vivo: no terminó de bajar los primeros 100 MB en 60s, claramente muy por encima del cap de 5 MB).

  Plan por niveles (conversación 2026-08-30):
  1. **Hecho:** `list_zip_contents` (tool nuevo) + `helpers/csv_reader.list_zip_contents` — acepta una URL directa (no un `resource_id` de CKAN) y lee solo el directorio central del ZIP vía HTTP Range al final del archivo para listar nombres/tamaños/tamaños comprimidos de los miembros sin descargar el archivo completo. No soporta ZIP64; requiere que el host respete Range requests (falla explícito si no). Limitación real documentada en el propio docstring: previsualizar filas de un miembro específico sigue requiriendo descomprimir desde el offset de ese miembro en adelante, que puede seguir siendo grande si el miembro está cerca del final de un archivo enorme — el listado es barato, la vista de contenido no siempre lo es (para eso sigue existiendo `preview_zip`, con su cap de 5 MB).
  2. **Solo si se justifica por uso repetido:** un índice local pre-construido (mismo patrón que `scripts/build_supercias_financials_db.py`) para un dataset específico que se consulte seguido (ej. REESS o ENEMDU por provincia/mes). No vale la pena como mecanismo general, es inversión por dataset.
  3. **Para el resto, no hay nada que arreglar:** las respuestas de un tool MCP son texto/JSON hacia el contexto del modelo, no un canal de transferencia de archivos — para una descarga puntual de un archivo enorme, la respuesta correcta sigue siendo devolver la URL directa y que el agente la baje con su propia capacidad de fetch, fuera de este servidor.
- [~] **CEPAL — geoportal del Censo Ecuador (`geo.cepal.org/censo-ecuador/`).** Filtro correcto encontrado 2026-08-30: `filter{keywords.slug.in}=geoportal_inec` sobre `geoportal.cepal.org/api/v2/datasets/` (el GeoNode público de CEPAL) acota correctamente a 9 capas reales de Ecuador (`cantones`, `parroquias_ecuador`, `cantones_del_ecuador0`, `sec_anoni_ecu` — sectores censales anonimizados, mallas preliminares). No integrado: estas capas son claramente derivadas del propio Clasificador Geográfico de INEC (ver ítem de abajo, la fuente primaria), así que el valor de sumar CEPAL aquí es bajo salvo que interese la geometría ya lista para mapas (GeoJSON/Shapefile vía GeoNode) sin tener que procesar los SHP.zip de INEC directamente. `geodata.cepal.org/api/v1` (datos estadísticos, no solo geometría) seguía devolviendo 502 en la última prueba. → conversación 2026-08-30
- [x] **INEC — micrositio de Geografía Estadística con el Clasificador Geográfico oficial, integrado 2026-08-30.** Ya es descubrible vía `search_inec_estadisticas`/`get_inec_estadistica_files` (agregado a `_EXTRA_TOPICS`, no está en ningún menú). De paso se encontró y corrigió un bug real en `_FILE_LINK_RE`: muchos links reales del sitio tienen doble slash (`.ec//documentos/...`), que el regex con un solo `/` no capturaba — la página del geoportal pasó de 19 a 115 archivos encontrados con el fix (afecta a cualquier página de tema, no solo esta). **Drift real confirmado contra `CLASIFICADOR_GEOGRAFICO_2026.zip` y corregido en `helpers/data/{cantones,parroquias}.json`:**
  - La Concordia estaba codificada como cantón `0808` de Esmeraldas; el clasificador oficial 2026 la tiene como `2302` de Santo Domingo de los Tsáchilas (la reasignación de provincia es real y ya resuelta hace años — nuestro dato tenía el código viejo). Corregido el cantón y sus 4 parroquias.
  - Faltaba el cantón `1413` "Sevilla Don Bosco" (Morona Santiago) por completo — creado por la Asamblea Nacional el 2024-11-05, el cantón más nuevo de Ecuador (área/población de Wikipedia, con fuentes primarias de Asamblea Nacional/El Universo citadas). Antes solo existía como parroquia de Morona (código `140157`, ya retirado en el clasificador oficial); ahora tiene su propio cantón y su parroquia cabecera (`141350`).
  - **Resuelto 2026-08-30 (investigado a fondo, no fue un simple reemplazo de códigos):** de los cantones "zona 90" que no coincidían, solo `9006 Juval` (disputa real Cañar-Chimborazo, con código oficial propio desde un decreto de 2017) era una adición legítima — agregado. `9009 Morona` en el oficial es casi seguro un error de captura de la propia hoja de cálculo (etiquetado con provincia "MORONA SANTIAGO" en vez de "ZONA EN ESTUDIO", sin ninguna parroquia debajo, y "Morona" ya existe como cantón real 1401) — no agregado. Nuestros `9001 Las Golondrinas`/`9003 Manga Del Cura`/`9004 El Piedrero` se dejaron intactos tras investigar cada uno por separado: Las Golondrinas se resolvió a favor de Cotacachi/Imbabura por consulta popular en 2026, pero el propio clasificador oficial todavía no le asigna un código de parroquia (no se puede inventar uno); Manga Del Cura y El Piedrero siguen genuinamente en disputa/sin resolver hoy (confirmado con fuentes de 2024) — su ausencia en la hoja CANTONES del clasificador no es evidencia de que se resolvieron, es que nunca recibieron un código formal de cantón como sí lo tuvo Juval.
  - Total de cantones ahora 225 (222 con provincia asignada + 3 zona en estudio), coincide con la cifra pública de "Sevilla Don Bosco es el cantón 222 de Ecuador".
  → conversación 2026-08-30, RESEARCH.md § Novena pasada
  → conversación 2026-08-30
- [x] **`censoecuador.gob.ec` — integrado 2026-08-30 vía `search_censo_recursos`.** Nuevo `helpers/censo_client.py`, solo metadata + URL (nunca contenido, igual que SIPA/Supercías financials — los BDD son multi-cientos-de-MB). Dos problemas reales del host resueltos de forma centralizada, no ad hoc en el cliente: (1) TLS — el chain de `www.censoecuador.gob.ec` verifica contra el almacén de certificados del SO pero no contra el bundle `certifi` de httpx (una CA intermedia faltante en certifi, no un cert roto) — `helpers/tls.py` gana un tercer nivel de reintento (`should_retry_with_os_trust`/`os_trust_context`), separado del reintento inseguro existente porque este **sí mantiene la verificación completa**, no es un downgrade de seguridad. (2) HTTP status — `/data-y-resultados/` devuelve 404 real con contenido real (bug de plugin/tema) — `download_bytes` gana un parámetro `raise_for_status=False`, por defecto `True` para no afectar ningún otro caller. 36 archivos reales encontrados en vivo. → RESEARCH.md § Novena pasada
- [x] **Ministerio del Trabajo/SUT — Power BI "Indicadores" descifrado 2026-08-30/31, `list_sut_indicadores`/`get_sut_indicador_schema`/`query_sut_indicador` (`helpers/sut_powerbi_client.py`).** El gap identificado abajo (serie mensual de contratos por industria) resultó ser genuinely extraíble: el protocolo AJAX de Power BI (`public/reports/{resource_key}/modelsAndExploration` para el esquema completo sin tocar la UI, `public/reports/querydata` con header `X-PowerBI-ResourceKey` para queries arbitrarias) es público y sin sesión — el resource_key sale del propio embed URL. El formato de respuesta (DSR, codificación delta con bitmasks R/Ø) se decodificó y se validó contra cifras leídas directamente del dashboard en vivo (enero 2015 = 92,306 contratos, exacto). El mismo mecanismo generaliza a los 8 dashboards de SUT sin código por-dashboard: 6/8 exponen su catálogo de campos completo automáticamente (contratos, capacitación/SETEC, encuesta de demanda laboral, sentencia de género, estrategias de empleabilidad, plan nacional de desarrollo). **Los 2 restantes (denuncias_publico, encuentra_empleo) resueltos 2026-08-31, pedido explícito de Daniel ("do SUT now"):** sus visualContainers usan un formato de reporte más antiguo (`{id,x,y,z,width,height,objectName}`, sin `config`) que `modelsAndExploration` no expone — se recuperaron sus campos reales conduciendo cada dashboard en un browser real, capturando las queries que Power BI mismo dispara al cambiar un filtro (mismo método que descubrió mes×industria en `contratos`), y guardándolos como un override manual (`_MANUAL_CAMPOS`) que se fusiona con el descubrimiento automático. `encuentra_empleo` reveló además un tipo de campo nuevo — "Número de Personas" es una columna agregada con `SUM()` en tiempo de consulta (`Aggregation`/`Function:0`), no una medida DAX prearmada como en los otros dashboards — soportado ahora como `kind="aggregated_sum"`. **Los 8 dashboards de SUT quedan completamente cubiertos.** **Navegación de `sut.trabajo.gob.ec` reconfirmada a fondo 2026-08-31** (pedido explícito de Daniel): el menú "Datos Abiertos" del propio portal solo etiqueta 2 de los 8 dashboards como tal (Contratos, Sentencia) — coinciden exactamente con 2 de los ya cubiertos, no hay un tercero escondido ahí. "Mediación laboral" y "Sustitutos" son formularios de trámite individual (solicitud/seguimiento de caso), no fuentes de datos agregados. "Capacitaciones" es un catálogo de cursos de autoinscripción (Seguridad y Salud, Encuentra Empleo, Capacitaciones Internas MDT) — página informativa, no dataset. No se encontró ningún noveno dashboard ni sección de datos sin explorar en el resto del nav. → RESEARCH.md § Décima pasada
- [ ] **Ministerio del Trabajo — Boletín Estadístico Anual "El Mercado Laboral en el Ecuador", encontrado 2026-08-31 vía búsqueda web** (la página índice `trabajo.gob.ec/direccion-de-investigacion-y-estudios-laborales/` sigue con el mismo timeout de siempre, así que no se pudo navegar el listado real). Dos ediciones confirmadas vivas por URL directa (`curl -I`, PDF real ~4 MB cada uno): No. 3 (2022, `wp-content/uploads/2024/01/Boletin-Anual-2022-1_compressed.pdf`) y la edición 2020 (`BoletinAnual2020ok.pdf`) — nombres de archivo inconsistentes entre sí, no se puede adivinar el patrón para otros años. El propio boletín 2022 declara que sus cifras derivan de la ENEMDU de INEC (referencia diciembre 2022), es decir, es un análisis derivado, no una encuesta propia del ministerio — mismo patrón ya documentado para las cifras de empleo/desempleo del ministerio. Sin confirmar: si existen ediciones 2021/2023/2024/2025, y si hay una versión más reciente que 2022. Pendiente de una pasada con Wayback Machine sobre la página índice para recuperar el listado completo de años.
  Historia del hallazgo: investigado 2026-08-29 y "profundizado" el 2026-08-30 con una conclusión de "sin gap" que resultó **incorrecta** — Daniel la refutó preguntando directamente "do we have monthly level SUT contratos by industry". El único recurso CKAN existente (`mdt_contratosvigentessistemaunicotrabajo_2026Agosto`) es solo una foto del stock de "Vigentes" al mes de consulta, sin fecha ni historia — no es la misma fuente que el dashboard pese a compartir nombre. **Lección: verificar el contenido real de un iframe de BI antes de concluir "mismo dato", no solo su URL/nombre — y antes de concluir "no se puede automatizar", capturar el tráfico de red real en vez de asumir.** `trabajo.gob.ec` (páginas dinámicas) sigue sin responder — mismo timeout de hosting compartido, reconfirmado. → RESEARCH.md § Octava pasada
- [ ] **MIES/Ministerio de Desarrollo Humano — portal `info.desarrollohumano.gob.ec` ("infoMIES"), gap real confirmado 2026-08-30**, pedido explícito de Daniel tras la corrección de SUT. `mies.gob.ec`/`inclusion.gob.ec`/`desarrollohumano.gob.ec` siguen muertos (NXDOMAIN, conexión reseteada, timeout — cada uno con su propio modo de falla, reconfirmado en vivo), pero `info.desarrollohumano.gob.ec` (encontrado vía el campo "fuente original" de un dataset CKAN real, mismo truco que reveló `sut.trabajo.gob.ec`) está vivo y responde en <2s. Tiene bases de datos **mensuales** (no trimestrales como CKAN) para Aseguramiento No Contributivo (2019-2026) y Usuarios del SIIMIES (2020-2026) vía descargas Joomla directas (`?download=ID:slug`, sin JS/AJAX) — confirmado con `curl -I` real sobre un archivo de julio 2026: 109.8 MB, `.rar`. El `.rar` ya está descartado como formato legible en este proyecto, pero eso solo bloquea el contenido, no catalogar metadata + URL (mismo patrón que SIPA/Superbancos con archivos grandes). También tiene "Boletines Zonales" (9 zonas × 2017-2021, ~11 meses/año-zona, aparentemente discontinuado) y dos dashboards Power BI sin explorar. Mucho más fácil de construir que el caso SUT — es scraping de página índice + Joomla download links, no automatizar un embed de BI. Sin explorar aún: geoportal propio, biblioteca, documentos metodológicos, estudios. → RESEARCH.md § Décima pasada
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
