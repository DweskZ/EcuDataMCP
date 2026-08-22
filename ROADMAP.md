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
- [ ] **Ecuador en Cifras / portal BI del INEC** — sin investigar todavía.
- [~] **IESS (Instituto Ecuatoriano de Seguridad Social)** — **agregado
      2026-08-16, pedido por Daniel: tienen boletines/reportes en PDF en su
      propio portal.** Ya reachable hoy vía CKAN genérico
      (`organization="instituto-ecuatoriano-de-seguridad-social"`) — 3
      datasets: afiliados activos del Seguro General Obligatorio y Régimen
      Especial Voluntario, pagos y beneficiarios del Seguro de Desempleo
      (verificado en la sección de verificación e2e de abajo), encuesta
      familiar del Seguro Social Campesino. **Sin confirmar todavía:** los
      PDFs (boletines estadísticos) que Daniel menciona — una revisión
      rápida de `iess.gob.ec/es/estadisticas` no encontró links `.pdf` en el
      HTML plano (puede ser contenido cargado por JS, o vivir en otra
      sección del sitio); falta investigar a fondo dónde están y si tienen
      suficiente valor estructurado como para justificar un
      `read_pdf`/extracción dedicada, o si conviene esperar al pendiente
      general de `read_pdf(url, pages)`.
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
      resuelve.
- [ ] **Cuenca en Datos** (`https://cuencaendatos.cuenca.gob.ec`) — CKAN 2.9.6,
      92 datasets, portal municipal independiente del nacional. Sin probar.
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
      palabra clave de CKAN, que es débil frente al catálogo completo (ejemplo
      real contra el mismo portal: "cacao" devuelve muy pocos resultados).
      Falta una capa de similitud/embeddings que mejore el recall sin
      reemplazar la búsqueda en vivo.
- [ ] **Expansión de siglas/acrónimos en la consulta** — los usuarios escriben
      "ENEMDU", "ENSANUT", "RUC"; el catálogo los tiene deletreados completos
      en los metadatos. Falta expandir la consulta antes de buscar (por
      keyword o por embeddings).
- [ ] **Detección real acumulado-vs-incremental** entre archivos de un mismo
      dataset — cuando un dataset publica un archivo por período (ej. precios
      semanales de cacao del MPCEIP), falta distinguir si cada archivo nuevo
      reemplaza a los anteriores (acumulado, solo hay que leer el más
      reciente) o los complementa (incremental, hay que sumarlos todos).
      Confundirlo trunca o duplica una serie silenciosamente. Hoy no hay
      ninguna heurística para esto.

## Formatos y tipos de recursos

- [ ] **Tool `read_pdf(url, pages)`** — no hay soporte para leer PDFs del
      portal. Pocos casos hoy, pero es el desbloqueo para fuentes curadas más
      adelante.
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
- [~] **Soporte `.rar`** — todavía sin preview como tabla (necesitaría una
      dependencia/backend externo para extracción RAR, p. ej. `rarfile` con
      `unrar`/`unar`/7-Zip/`bsdtar`; puerta abierta si el volumen de casos
      lo justifica). Mientras tanto, `preview_resource_data` señala el caso
      explícitamente (`rar_no_soportado`) y ahora hay un tool nuevo,
      `download_resource(resource_id, format="json")`, que baja el archivo
      completo (base64, hasta 5 MB) para que se pueda usar fuera del MCP.
- [ ] **Recursos sin extensión** — requieren sniffing de content-type; sin
      implementar ni probar.
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
- [ ] Cobertura real de formatos: `.xls`, `.zip`, `.rar` y una URL sin
      extensión, probados de punta a punta.
- [ ] Degradación cuando el portal no responde — confirmar que el error que
      recibe el modelo es accionable (indica el host correcto), no genérico.

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
