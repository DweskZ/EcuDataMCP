# Roadmap

Pendientes definidos para `EcuDataMCP`, reconstruidos de sesiones previas de
diseño e instalación (no existía este archivo hasta ahora).

Leyenda de estado: **[ ]** sin empezar · **[~]** parcial · **[x]** hecho

---

## Nuevas conexiones de datos

- [ ] **Página de datasets del SRI** (`https://www.sri.gob.ec/datasets`) — 131
      enlaces directos a archivos (93 CSV, 24 ZIP, 13 XLSX) más diccionarios
      `*_DD.xlsx`, en una sola página estable. Mejor relación valor/esfuerzo de
      la lista: el SRI hoy solo aparece parcialmente vía el portal CKAN
      genérico.
- [ ] **Banco Central del Ecuador (BCE)** — el portal CKAN solo publica 4
      datasets del BCE; su data real vive en su propio sistema de
      estadísticas. Requiere un diseño de conexión aparte (API/sistema propio
      del BCE, no CKAN).
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
- [~] **Soporte `.rar`** — todavía sin preview como tabla (necesitaría el
      binario `unrar` como dependencia externa; puerta abierta si el volumen
      de casos lo justifica). Mientras tanto, `preview_resource_data` señala
      el caso explícitamente (`rar_no_soportado`) y ahora hay un tool nuevo,
      `download_resource(resource_id)`, que baja el archivo completo
      (base64, hasta 5 MB) para que se pueda usar fuera del MCP.
- [ ] **Recursos sin extensión** — requieren sniffing de content-type; sin
      implementar ni probar.
- [~] **Soporte `.xls` legacy** — `preview_resource_data` sigue sin parsear
      `.xls` como tabla (`xls_no_soportado`), pero ahora se puede bajar el
      archivo completo con `download_resource(resource_id)` para abrirlo
      localmente. Preview real (vía `xlrd`, que es pura Python, sin binario
      externo) queda como posible siguiente paso si hace falta.

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
