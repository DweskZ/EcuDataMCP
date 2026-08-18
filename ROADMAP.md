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
- [ ] **Superintendencia de Compañías (Supercías)** — el portal CKAN solo
      publica 1 dataset; tiene portal propio sin investigar.
- [ ] **Instituto Geofísico (IG-EPN)** — pedido explícitamente por Daniel.
      Verificar qué cubren ya `search_organizations`, `list_instituciones`,
      `search_eventos_riesgo` y `list_sat_tsunami`, y si falta, diseñar una
      conexión dedicada. Búsqueda quedada interrumpida sin retomar.
- [ ] **Ecuador en Cifras / portal BI del INEC** — sin investigar todavía.
- [ ] **Cuenca en Datos** (`https://cuencaendatos.cuenca.gob.ec`) — CKAN 2.9.6,
      92 datasets, portal municipal independiente del nacional. Sin probar.
- [ ] **Sitios de ministerios individuales** — sin alcance definido; falta
      decidir cuáles justifican una conexión propia en vez de depender del
      portal CKAN central.

---

## Cabos operativos sueltos

- [ ] **Revisar renovación del certificado TLS** de
      `www.datosabiertos.gob.ec` (venció 2026-07-28). El fallback
      `CKAN_INSECURE_TLS` que desactiva la verificación quedó documentado como
      temporal — apagar el default inseguro en cuanto el gobierno renueve el
      certificado.
- [ ] **Borrar la rama ya mergeada `fix/ckan-domain-and-readme`** (local y en
      el fork) — el intento quedó bloqueado por el classifier de seguridad;
      sigue viva sin necesidad.
- [ ] **Decidir sobre los dos `Manual de Usuarios Portal.pdf` duplicados** en
      `reference-docs/` del fork de Daniel (395 KB vs 2.5 MB) — nunca se
      aclaró si son versiones distintas o si uno sobra.

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
- [ ] **Prompts de flujo de trabajo adicionales** (`@mcp.prompt()`) — hoy solo
      hay uno; falta al menos un segundo prompt guiado para exploración
      temática (ej. "explorar_tema").
- [ ] **Descartar columnas de geometría/WKT** antes de renderizar previews de
      GeoJSON/CSV — una sola columna de polígono puede inundar el contexto de
      un preview. `preview_json`/`preview_csv` no lo hacen hoy.
- [ ] **Parseo de decimales en formato europeo** (`7.760,2` = 7760.20) —
      común en varios recursos del portal; falta detectarlo y ofrecer
      conversión, no solo advertir.
- [ ] **Soporte `.rar`** — decisión pendiente: implementarlo (necesita binario
      `unrar`) o documentar el rechazo como definitivo.
- [ ] **Recursos sin extensión** — requieren sniffing de content-type; sin
      implementar ni probar.
- [ ] **Soporte `.xls` legacy** — hoy `preview_resource_data` lo rechaza
      explícitamente; decidir si vale la pena soportarlo.

## Verificación end-to-end pendiente

Cifras de referencia contra el mismo portal (`www.datosabiertos.gob.ec`),
para confirmar que los tools devuelven los números correctos, no solo que no
truenan:

- [ ] **SRI** `contribuyentes-activos-catastro-2025` → 2,904,355
      contribuyentes en el mes más reciente vía `sum(TOTAL)`, **no**
      `count(*)` (que da 405,794).
- [ ] **IESS** `base-de-datos-seguro-desempleo`, junio 2026 → 2,561
      beneficiarios, USD 836,716.99, excluyendo la fila `TOTAL:` embebida en
      el archivo (incluirla da exactamente el doble).
- [ ] **MPCEIP** cacao → junio 2026, Grado 1 semanal: 174.77 / 168.15 /
      166.28 / 188.07, usando solo el archivo más reciente.
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
corregido en el repo; los 27 tools funcionan.

**Repo hermano:** [`datosec-mcp`](../datosec-mcp) es un MCP propio de Daniel
sobre la misma fuente de datos (portal CKAN de Ecuador). Su `ROADMAP.md`
(2026-08-13) era mucho más extenso porque partía de cero: incluía trámites,
SERCOP, ANDA, SAT tsunami, eventos de riesgo y ubicaciones DPA, que aquí en
EcuDataMCP ya están resueltos y por eso no se repiten en esta lista. Todo lo
demás que sí seguía pendiente ahí — búsqueda semántica, expansión de
consultas, detección acumulado/incremental, formatos de archivo, verificación
end-to-end y arquitectura — se consolidó arriba en este archivo el
2026-08-13, y el `ROADMAP.md` de `datosec-mcp` se eliminó para no mantener dos
listas por separado. Este archivo es ahora la única fuente de pendientes para
ambos.
