# Research Notes

Investigation trail behind [ROADMAP.md](ROADMAP.md): live verifications, dead
ends, corrections, and the reasoning behind each open item. ROADMAP.md is the
tight checklist — read it first for current status. Come here for the "why"
and the evidence. Organized by topic, most-recent findings first within each
topic where the investigation happened over multiple passes.

---

## Fuentes de datos investigadas

### SRI — página de datasets

Hecho: tool `search_sri_datasets` + `helpers/sri_client.py`. Verificado en
vivo (2026-08-16, con acceso real al portal): 130 enlaces directos (71 CSV,
46 ZIP, 13 XLSX — el desglose por formato cambió un poco vs. la cifra
original de este ítem, pero el total ronda igual ~130; el portal se
actualiza con nuevos años). La página es un CMS Liferay sin API — cada
archivo vive en un `<p>` con una etiqueta corta junto al link de descarga;
**ojo:** el agrupamiento por sección (`data-analytics-asset-title`) no es
confiable — la sección de Recaudación real está mal titulada "Prueba" en el
HTML — así que el parser indexa cada archivo por su propia etiqueta/URL en
vez de confiar en el título de la sección que lo contiene. Caché de 6h.

**Cobertura vía CKAN (2026-08-29):** `organization=sri-servicio-de-rentas-
internas` tiene **127 datasets** (recaudación de impuestos por año
2017-2024, prestadores de servicios digitales, catastro de agregadores de
pago, autorizados para facturación electrónica...) — aparte del scraper
propio arriba. Puede haber traslape, pero el catálogo CKAN es rico por sí
solo y ya reachable con los tools genéricos.

### Banco Central del Ecuador (BCE)

Hecho: tools `search_indicadores_bce`/`get_indicador_bce` +
`helpers/bce_client.py` sobre la API pública sin autenticación de BCEData
(`contenido.bce.fin.ec/wp-json/bcedata/v1/`), no documentada oficialmente
pero confirmada con `curl` plano.

**Remesas de trabajadores — `search_bce_remesas`
(`helpers/bce_remesas_client.py`).** Cubre resultados agregados, serie
histórica y bases mensuales de remesas, incluida la desagregación por
entidad remisora/receptora disponible desde julio de 2025
(`https://contenido.bce.fin.ec/series-de-datos-remesas-de-trabajadores/`).
Ojo con el corte metodológico: la serie "Histórica" (pre-cambio de
metodología) y la serie "BDD" (post-cambio) no son directamente
comparables — son dos series distintas, no una continuación simple una de
la otra.

**Hallazgo grande (2026-08-29): la "Información Estadística Mensual"
(IEM/IEEM)**, el boletín insignia del Banco Central, mucho más allá de lo
que cubre la API BCEData ya integrada.
`contenido.bce.fin.ec/documentos/informacioneconomica/PublicacionesGenerales/IndiceIEM.html`
lista los boletines desde hace décadas (numerados; No. 2087-2092 =
enero-junio 2026, uno por mes, confirmado en vivo — es exactamente el
"catálogo con publicaciones mensuales" que motivó esta búsqueda). Cada
boletín (`.../IEMensual/m{n}/IEM{n}.zip`, patrón de URL predecible por
número) es un ZIP real y descargable — confirmado el de junio 2026 (No.
2092): **11.5 MB**, contiene docenas de cuadros: estadísticas monetarias y
financieras (M1/M2, tasas de interés, reservas internacionales, balance
sectorial por tipo de entidad), finanzas públicas (operaciones del SPNF,
base devengado, % del PIB), y más secciones no leídas todavía (sector
externo, cuentas nacionales, precios, sector real). Mucho más rico que los
indicadores curados de BCEData. También hay un PDF de la publicación
completa por boletín (`IEM{n}.pdf`). Candidato real y fuerte para una
integración nueva (`helpers/bce_iem_client.py` o similar) — el volumen de
cuadros por boletín es grande, no trivial, pero el acceso en sí no tiene
fricción (sin registro, sin captcha).

### Superintendencia de Compañías (Supercías)

Hecho: directorio de compañías (`search_companias`/`get_compania_info`,
226k+ compañías, actualizado a diario, parseado desde el export Excel
estático del portal), ranking financiero (`search_ranking`/`get_financials`,
~38 ratios financieros por compañía y año fiscal, sobre un SQLite local
construido de antemano con `scripts/build_supercias_financials_db.py`) y
registro de auditores externos (`search_auditores`/`get_auditor_info`).

### Instituto Geofísico (IG-EPN)

Hecho: tool `search_sismos` sobre el catálogo sísmico público, con caché TTL
y parseo tolerante del CSV.

### Ecuador en Cifras / portal BI del INEC

**Construido 2026-08-29:** `helpers/inec_client.py` +
`search_inec_estadisticas`/`get_inec_estadistica_files`. Confirmado en vivo
que cada página de tema (~75 en total) es HTML plano de WordPress, sin JS —
los links a boletín/metodología/series históricas están directamente en el
HTML servido (`<a href=".../documentos/web-inec/.../archivo.pdf">`, a veces
envolviendo solo un `<img>` de ícono, sin texto — por eso las etiquetas se
derivan del nombre de archivo, no del texto del link).

**Sin API ni sitemap de temas — se usa el menú de navegación en su lugar.**
Cada página de tema trae embebido el mismo menú "mega-menu" de ~75 links
(`<a class="mega-menu-link" href="...">Nombre</a>`), así que basta con
descargar *cualquier* página de tema para extraer la lista completa; se
usó la del IPC (`indice-de-precios-al-consumidor`) como semilla por ser un
tema insignia poco probable de renombrarse. **Importante — ni la raíz del
dominio ni `/estadisticas/` sirven para esto, confirmado en vivo:**
- `https://www.ecuadorencifras.gob.ec/` sirve un shell de meta-refresh
  (`<meta http-equiv="Refresh" content="0; url=.../institucional/home/">`)
  cacheado por W3 Total Cache **desde 2021-06-16** — un `GET` plano (sin
  navegador) nunca ve el sitio real, solo ese shell viejo.
- `https://www.ecuadorencifras.gob.ec/estadisticas/` sirve una vista
  Liferay completamente distinta y no relacionada (`generator 2018.1.1.386`,
  clase `nojs`) — un navegador real termina mostrando el home moderno ahí
  (probablemente por JS del lado del cliente), pero un `GET` plano solo ve
  el shell viejo, igual que la raíz.
- Las páginas de tema individuales (`/actividades-y-recursos-de-salud/`,
  `/indice-de-precios-al-consumidor/`, etc.) sí son 100% reales y frescas
  vía `GET` plano — el problema es específico de esas dos URLs "índice",
  no del sitio en general.

**Comparado contra ANDA, 2026-08-29 (pedido de Daniel: "analiza contra
ANDA").** `/estadisticas/` no es redundante con ANDA (`helpers/anda_client.py`,
ya construido) — son capas distintas de lo que publica el INEC:

- **IPC** está catalogado en ANDA para cada año 2020-2026, pero cada entrada
  dice explícitamente `microdatos disponibles: no (solo agregados)` — es un
  registro de metadata sin nada descargable detrás. Lo que sí existe —
  boletín técnico, metodología, y sobre todo la serie histórica completa en
  Excel/CSV — vive únicamente en `/estadisticas/`. Confirmado en vivo vía
  `search_anda(query="indice precios consumidor")` contra el servidor MCP en
  producción.
- Esto generaliza a cualquier operación de tipo índice/agregado (comercio
  exterior, cuentas nacionales, construcción...): ANDA cataloga la operación
  como referencia bibliográfica pero no carga microdatos porque no los hay
  por diseño — el agregado publicado es el dato en sí, y ese agregado solo
  está en `/estadisticas/`.
- **Conclusión: `/estadisticas/` sigue siendo el objetivo correcto y de
  mayor prioridad** para `helpers/inec_client.py` — es la única fuente para
  el tipo de contenido que ANDA estructuralmente no puede tener (series
  agregadas publicadas + boletines/metodología), no algo que se pueda cubrir
  ampliando ANDA.

**Banco de Datos Abiertos (BIINEC), aportado por Daniel 2026-08-29:**
`aplicaciones3.ecuadorencifras.gob.ec/BIINEC-war/index.xhtml` — una
aplicación JSF/PrimeFaces separada de las páginas `/estadisticas/` de abajo,
con su propio catálogo categorizado: tres ramas (Sociodemográficas y
Sociales, Económicas, Ambiente y Otras Estadísticas), cada una con un árbol
de temas (Población y Migración, Pobreza, Trabajo, Educación, Salud,
Ingresos y Consumo, Protección Social, Asentamientos Humanos y Viviendas,
Justicia y Crimen, Condiciones de Vida y Problemas Sociales, Uso del
Tiempo...). Cada tema lista sus "operaciones estadísticas" (p. ej. bajo
Salud: ENSANUT, ENDI, Camas Hospitalarias, Egresos Hospitalarios, Registro
de Recursos y Actividades de Salud); cada operación tiene un selector de
año y luego de período (ANUAL en los casos probados), y al fijar ambos
aparece la lista de archivos descargables (Base de Datos STATA, Datos
Abiertos CSV, a veces XLSX/ZIP/PDF según el ícono de tipo) con su peso en
MB, un rating en estrellas y un contador de descargas acumuladas por año
(confirmado en vivo: ENSANUT 2019 con 3,420 descargas, "Datos Abiertos CSV"
de 30.8 MB). La barra lateral "Top Descargas" del home ya adelanta los
datasets más pedidos (ENEMDU 2018/2019, ECV 2014...).

**Fricción real:** a diferencia de los links planos `<a href>` de
`/estadisticas/`, el botón "Descargar" aquí es un `p:commandButton
ajax="false"` de PrimeFaces (`PrimeFaces.monitorDownload` +
`PrimeFaces.bcn`) — el clic hace un POST a `index.xhtml` que arrastra el
`javax.faces.ViewState` de la sesión y el árbol de selección acumulado
(rama → tema → operación → año → período), no una URL fija reusable.
Replicar esto sin browser requeriría reconstruir esa secuencia de POSTs con
`httpx` (cookie de sesión + ViewState re-leído en cada paso), no un simple
`GET` a una URL de archivo — bastante más fricción que el resto del
catálogo de `ecuadorencifras.gob.ec`. Sin confirmar todavía si el
ViewState es estable entre pasos o cambia por cada postback (lo normal en
JSF es que cambie), lo cual determinaría si vale la pena automatizarlo.
Candidato interesante por el volumen y la organización taxonómica, pero
requiere una investigación de sesión aparte antes de decidir construir
`helpers/inec_client.py` contra este endpoint en vez de (o además de)
`/estadisticas/`.

**BIINEC contra ANDA, 2026-08-29:** en su mayoría es redundante. Probado en
vivo contra el servidor MCP en producción:

- "Camas Hospitalarias" + "Egresos Hospitalarios" (dos temas separados en
  BIINEC) ya están en ANDA como una sola serie combinada "Estadísticas
  Hospitalarias Camas y Egresos", con microdatos sí disponibles, 2015-2024
  completo.
- ENDI (desnutrición infantil) ya está en ANDA, 2022 y 2023-2024.
- ENSANUT solo está en ANDA para 2018; el desplegable de año en BIINEC solo
  ofrecía 2014 y 2019 — mismo censo/encuesta, cero años en común entre las
  dos fuentes. Ninguna es superconjunto de la otra.
- Donde el contenido se solapa, ANDA se descarga con un link directo sin
  sesión; BIINEC exige repetir la secuencia de POSTs con ViewState de JSF
  (ver fricción arriba) para llegar al mismo archivo.

**Veredicto:** no vale la pena construir contra BIINEC para las operaciones
que se solapan con ANDA. Lo único potencialmente útil sería perseguir casos
puntuales de años faltantes (como ENSANUT 2014/2019) uno por uno, no una
integración completa del catálogo BIINEC.

**Análisis a fondo, 2026-08-29 (pedido explícito de Daniel: "analiza a
fondo si el otro sitio de banco de datos abiertos es útil").** Se revisó
en vivo la sesión JSF real (no solo se asumió), y se recorrieron a fondo
las tres ramas (Sociodemográficas, Económicas, Ambiente) para buscar
contenido genuinamente exclusivo, no solo repetir la comparación de la
pasada anterior.

1. **El flujo JSF resultó más simple de lo asumido — corrección a la nota
   de fricción de arriba.** Inspeccionando la respuesta real del POST del
   selector de año: no es un ajax parcial de PrimeFaces (XML
   `<partial-response>`), es un **postback completo clásico de JSF** — cada
   cambio de dropdown reenvía el formulario entero y el servidor devuelve
   la página HTML completa de nuevo, con un `javax.faces.ViewState` nuevo
   embebido (formato `-652696757013912769:-2931437765435945654`, sesión
   server-side vía `JSESSIONID`). Esto es mecánicamente idéntico al patrón
   ya implementado para ANDA (`list_microdata_files`: GET por el token,
   POST para aceptar) salvo que en vez de 1 paso son ~4 (rama → tema →
   año → período → botón "Descargar"), cada uno reanalizando el HTML
   completo (~70-80 KB) para extraer los campos ocultos y el ViewState del
   siguiente paso. Es más código que ANDA o `/estadisticas/`, pero no es
   un problema exótico — es un "JSF form walker" genérico, factible en una
   sesión de trabajo si algún día se justifica por el contenido.

2. **Rama Sociodemográficas (Salud) y Económicas (Cuentas Económicas):
   solapamiento casi total confirmado, cero contenido nuevo.** Las
   operaciones bajo "Cuentas Económicas" en BIINEC (Cuentas Satélite de
   Trabajo No Remunerado, de Educación, de Salud) son exactamente las
   mismas 3 páginas ya cubiertas por `/estadisticas/`. La taxonomía de
   BIINEC es, en la práctica, un espejo de la de `/estadisticas/` — mismo
   INEC, mismas operaciones, dos apps distintas exponiendo el mismo
   catálogo.

3. **Rama Ambiente y Otras Estadísticas — aquí sí aparece contenido que no
   está ni en ANDA ni en `/estadisticas/`.** De 10 operaciones listadas
   bajo "Ambiente", la mayoría vuelve a solaparse (Encuesta de Información
   Ambiental Económica en Empresas → "Módulo de Información Económica
   Ambiental en Empresas" en ANDA; GAD Municipales/Provinciales, ESPAC,
   Censo Agropecuario → ya cubiertos). Pero dos no aparecieron en ninguna
   búsqueda de ANDA ni en los 74 temas de `/estadisticas/` ya scrapeados:
   - **"Módulo de Desechos Peligrosos en Establecimientos de Salud –
     Registro Administrativo de Salud"** — confirmado real y vivo:
     seleccionando 2020 aparecen archivos reales (Base de Datos SPSS 703
     KB, Tabulados y series históricas 185 KB, Formularios 685 KB) y "119
     descargas para el año seleccionado". Es un registro chico y de nicho
     (bajo volumen de descargas), pero es un dataset real que no vive en
     ningún otro lado ya integrado.
   - **"Información Ambiental en Hogares"** — dos variantes, una atada a
     ENEMDU (años 2010-2025) y otra a ECV (solo 2014); son módulos
     ambientales anexos a esas encuestas, no encontrados como entidad
     propia en ANDA ni en `/estadisticas/`. No se confirmó el contenido de
     archivos (no se llegó a expandir el período), pero el patrón de años
     disponibles sugiere que es real, igual que el caso anterior.

4. **Diferenciadores de metadata que ningún otro tool expone:** BIINEC
   muestra un contador de descargas por año-operación (útil como señal de
   popularidad — ej. ENEMDU 2018 lidera con 15,160 descargas de un total
   sitewide de 365,374) y clasifica cada archivo con el esquema
   internacional de "5 estrellas de datos abiertos" (Tim Berners-Lee: 1★
   PDF/DOC/JPG con licencia abierta, 2★ XLS, 3★ CSV/XML no propietario...).
   Ninguna de las dos cosas es contenido de datos en sí, pero son señales
   que ni ANDA ni `/estadisticas/` exponen.

**Veredicto final:** BIINEC como integración *completa* sigue sin
justificarse — el grueso de su contenido duplica ANDA o `/estadisticas/`
tras una capa de scraping más cara. Pero no es "inútil" sin matices: la
rama Ambiente tiene un puñado de registros administrativos genuinamente
exclusivos (desechos peligrosos en salud, módulos ambientales de
ENEMDU/ECV). Si en algún momento hay interés específico en datos
ambientales/de residuos, vale la pena un scraper puntual y chico para esas
2-3 operaciones (no un cliente genérico de todo BIINEC) — el costo de
construirlo ya no es "requiere investigación de sesión aparte" como se dijo
antes, es conocido y acotado (~4 pasos de postback JSF por archivo).

**Construido 2026-08-29 (pedido de Daniel: versión "targeted", con aviso de
búsqueda manual si no se encuentra):** en vez de ese scraper de sesión,
`helpers/biinec_extras.py` + `helpers/data/biinec_extras.json` +
`search_biinec_extras` — una lista pequeña y verificada a mano (sin llamada
HTTP, mismo patrón que `lookup_ubicacion`/`geo_data.py`) con los 3 registros
confirmados como exclusivos. Costo real de la alternativa completa vs. esto:
la versión JSF completa hubiera sido varios días de trabajo frágil (IDs de
componente PrimeFaces generados por fila, sesión con cookies, 5 POSTs
encadenados por archivo) para desbloquear ~3 datasets de bajo tráfico (119
descargas/año el más grande) que nadie ha pedido todavía — la versión
curada cuesta una fracción de eso y dice explícitamente "no encontrado en
este conjunto pequeño, busca manualmente" en vez de fingir cobertura
completa. `buscar_inec` (prompt) ahora llama a este tool en su paso 3 en vez
de solo mencionar BIINEC en prosa.

**Corrección 2026-08-28:** una conclusión anterior el mismo día ("callejón
sin salida") era falsa. El primer pase entró por
`ecuadorencifras.gob.ec/institucional/home/` (un subsitio institucional
viejo con navegación de ~2017) y por `inec.gob.ec` sin `www` (dominio
distinto, nunca fue el sitio real) — ninguno de los dos es el portal real,
y de ahí salió la conclusión errónea de que el dominio estaba abandonado.

**Re-investigado con más cuidado:** `www.ecuadorencifras.gob.ec` es el sitio
oficial del INEC, activo y publicando en 2026 (confirmado con búsqueda web y
en vivo — última publicación al momento de revisar: "IPCO - julio 2026",
21/08/2026). La página `/estadisticas/` es un catálogo enorme y
genuinamente vivo: decenas de temas (IPC, ENEMDU, ENSANUT, pobreza,
comercio exterior, cuentas nacionales, construcción, REBPE...), cada uno
con su propia página. Por ejemplo, la del IPC
(`/indice-de-precios-al-consumidor-ipc/`) linkea, para julio 2026, boletín
técnico en PDF, presentación de resultados en PDF, metodología en PDF, y
series históricas completas en Excel y CSV
(`Tabulados_y_series_historicas_CSV.zip`) — todos son links HTML planos,
sin JS de por medio, confirmado bajando el PDF y el ZIP directo con `httpx`
sin browser. Candidato fuerte para una integración real
(`helpers/inec_client.py` + tools de búsqueda/descarga), simplemente no se
construyó nada todavía porque el alcance (decenas de categorías × años de
histórico) es más grande que una sesión de investigación.

### LOTAIP como fuente transversal

**Candidato, 2026-08-28,** encontrado investigando IESS (ver nota de
Transparencia más abajo). Ley Orgánica de Transparencia y Acceso a la
Información Pública: obligatoria para toda institución pública
ecuatoriana, cada una publica su propio portal LOTAIP (resoluciones,
contratación, balances, exámenes de Contraloría...). Si la estructura
resulta suficientemente uniforme entre instituciones, podría ser una fuente
transversal reutilizable en vez de una integración por institución. Sin
investigar más allá de confirmar que existe en IESS — falta revisar si el
formato/URL se repite en otras instituciones antes de decidir si vale la
pena.

### IESS (Instituto Ecuatoriano de Seguridad Social)

**Agregado 2026-08-16, pedido por Daniel: tienen boletines/reportes en PDF
en su propio portal.** Ya reachable hoy vía CKAN genérico
(`organization="instituto-ecuatoriano-de-seguridad-social"`) — 3 datasets:
afiliados activos del Seguro General Obligatorio y Régimen Especial
Voluntario, pagos y beneficiarios del Seguro de Desempleo (verificado en la
sección de verificación e2e de abajo), encuesta familiar del Seguro Social
Campesino.

**PDFs confirmados 2026-08-28:** una revisión anterior con HTTP plano no
encontró links `.pdf` porque el navegador real primero renderiza JS; con el
browser real se encontró la sección "Boletines Estadísticos"
(`iess.gob.ec/es/estadisticas`), con boletines anuales desde 2006 hasta
2024 (el más reciente: 142 páginas, 4.16 MB). Cada entrada es una vista
Liferay `document_library_display` (HTML, no el PDF en sí); el PDF real
vive en `iess.gob.ec/documents/10162/<id>/<nombre>.pdf`, extraído del
`href` en esa página. `read_pdf` lo lee correctamente — 40 caracteres de
texto en la portada, confirmado en vivo.

**Investigación más a fondo del portal, 2026-08-28** (pedido explícito de
Daniel: "investigar boletines del IESS y otro material más allá de los
portales que tenemos"):

- **Estudios Actuariales** (`iess.gob.ec/estudios-actuariales/`) — mismo
  patrón Liferay que los boletines (vista `guest/estudios-actuariales-
  {año}`, PDF real en `iess.gob.ec/documents/10162/...`). Confirmados sets
  completos para 2010, 2013, 2018 y 2020 — el de 2020 solo trae 14 PDFs
  reales (valuación actuarial y su aprobación por fondo: IVM, Salud,
  Riesgos del Trabajo, Seguro Social Campesino, Cesantía, Desempleo, más
  tablas de mortalidad). **Bug real encontrado y corregido en el mismo
  pase:** el PDF de valuación del fondo IVM pesa 14.6 MB, casi 3× el tope
  de 5 MB de `read_pdf` — la descarga truncada producía un mensaje
  engañoso ("está corrupto") en vez de explicar que se cortó a la mitad.
  Corregido: `read_pdf` ahora detecta la descarga truncada *antes* de
  intentar parsear (mismo patrón que `.zip`/`.tar.gz` truncados) y da un
  mensaje accionable. El resto de PDFs del set 2020 (0.29–1.7 MB) están
  dentro del tope y se leen bien — verificado en vivo.
- **Informes de Auditoría** (`iess.gob.ec/es/informes-de-auditoria`) —
  archivo real y grande: carpetas por año 2007–2025, entre 1 y 42
  documentos por año (~344 documentos en total). El listado de carpetas,
  el listado de documentos dentro de cada carpeta, y la página de detalle
  de cada documento son HTML servido por el servidor — confirmado con
  `httpx` plano, sin browser, en los tres niveles. **Corrección 2026-08-28
  (mismo día):** una nota anterior decía que el link al PDF real "solo
  aparece después de JS" y que haría falta un browser headless — eso era
  un falso negativo: el primer intento buscaba únicamente URLs que
  terminan en `.pdf`, pero el link real no tiene extensión en la URL
  (`iess.gob.ec/documents/10162/25751514/DNA7-SySS-0001-2024?version=1.0`,
  `Content-Type: application/pdf` confirmado por header, 9.2 MB). Con un
  regex que no exige extensión, el link aparece directo en el HTML plano
  de la página de detalle. Conclusión correcta: los 344 documentos son
  enumerables y descargables sin ningún browser, headless o no —
  candidato real para un tool de búsqueda/lectura
  (`search_iess_auditorias` o similar) encadenado con `read_pdf`. No
  construido todavía; ya no hay ninguna barrera técnica identificada.
- **Transparencia / LOTAIP** (`iess.gob.ec/transparencia/`) — confirmado:
  IESS publica su portal LOTAIP (resoluciones, exámenes de Contraloría,
  contratación pública, balance financiero del BIESS, etc.). LOTAIP es
  obligatorio por ley para *toda* institución pública ecuatoriana, no solo
  IESS — si este patrón resulta automatizable en algún portal,
  probablemente se repite en decenas de instituciones.

**Construido 2026-09-04** (`helpers/iess_client.py`,
`tools/list_iess_colecciones.py`, `tools/get_iess_archivos.py`): las tres
colecciones documentadas arriba (Boletines Estadísticos, Estudios
Actuariales, Informes de Auditoría) quedaron cubiertas por dos tools —
`list_iess_colecciones` (catálogo: qué años/conteos tiene cada colección) y
`get_iess_archivos(coleccion, anio=None, query="")` (documentos resueltos a
URL directa, filtrables por colección/año/texto). Antes de escribir el
parser se re-verificó en vivo la estructura exacta de las tres páginas con
`httpx`/`curl` plano (sin browser) — varias correcciones reales a las notas
de arriba:

- **Boletines: 26 confirmados, no ~19.** La nota de 2026-08-28 sólo revisó
  la primera página de la lista (20 filas) y concluyó "2006-2024". La lista
  está paginada (`cur2`/`delta2`, requiere además los parámetros de ruteo
  de portlet Liferay `p_p_id=110_INSTANCE_zIm8&p_p_lifecycle=0&...` — un
  `cur2` "pelado" sin esos parámetros re-sirve la página 1 en silencio, un
  bug real que se encontró y corrigió en el mismo pase). La página 2 trae 6
  boletines más, hasta "BOLETIN ESTADISTICO 01" de **1978** — el archivo
  real cubre 1978-2024, no solo 2006-2024.
- **Estudios Actuariales: 4 años confirmados en vivo, no solo mencionados.**
  El índice (`iess.gob.ec/estudios-actuariales/`) enlaza hoy exactamente
  2010, 2013, 2018 y 2020 (confirmado además que `-2007` a `-2025` dan 404
  salvo esos tres años con sufijo; el "2013" es un caso especial: su enlace
  visible dice "Estudios Actuariales 2013" pero apunta a la URL *base* sin
  sufijo de año, `estudios-actuariales` sin `-2013` — no es un typo, es
  como está publicado). El scraper descubre estos años leyendo el índice en
  vivo (no están hardcodeados), así que un año nuevo que IESS agregue
  aparece sin cambio de código. 47 documentos totales resueltos (7 en el
  set base/2013, 8 en 2010, 13 en 2018, 14 en 2020 — coincide con el conteo
  de 14 ya documentado arriba). Dos formas de página confirmadas: 2018/2020
  (y el set base) enlazan directo a `documents/10162/<carpeta>/<archivo>`;
  2010 usa una ruta estática completamente distinta,
  `iess.gob.ec/informacion/Estudios_Actuariales_2010/<archivo>.pdf` — no es
  el patrón Liferay en absoluto, hay que soportar ambas formas.
- **Informes de Auditoría: 325 documentos confirmados en 20 carpetas
  (2007-2026), no ~344 en 2007-2025.** La cifra de "~344" de la nota
  anterior venía de una revisión parcial; la tabla de carpetas por año
  (columna "Número de documentos" de la página índice) suma exactamente
  325 en vivo. Además ya existe una carpeta 2026 (vacía, 0 documentos) que
  no existía cuando se escribió la nota original. El bug de "el link real
  no tiene extensión `.pdf`" que la nota de arriba ya había corregido se
  resolvió aquí de forma distinta a lo sugerido (`Content-Type` por
  request): la página de detalle de cada documento (patrón Liferay
  `document_library_display`, compartido con Boletines) trae un enlace
  "Descargar" cuyo ícono (`file_system/large/<ext>.png`) declara el
  formato real sin necesidad de una petición `HEAD`/`Content-Type` por
  documento — confirmado en vivo con el ejemplo exacto de la nota
  (`DNA7-SySS-0001-2024`, ícono `large/pdf.png`, URL sin `.pdf`). El mismo
  patrón de ícono resuelve Boletines y (donde aplica) los enlaces sin
  extensión de Estudios Actuariales 2018 ("Seguro Riesgos del Trabajo",
  "Seguro Desempleo" — confirmado antes con `Content-Type: application/pdf`
  vía header, y ahora también coherente con el ícono).
- **Paginación dentro de un año**: un año con más de 20 documentos (ej.
  2009, 42 documentos, el máximo confirmado) pagina con
  `_110_INSTANCE_vu7F_cur2=N&_110_INSTANCE_vu7F_delta2=20` sobre la misma
  URL amigable `.../document_library_display/vu7F/view/<carpeta>` — sin
  necesitar los parámetros `p_p_id` completos que sí hacen falta en la
  página raíz de Boletines/Informes (esas son rutas Liferay "amigables"
  con el portlet ya codificado en el path, a diferencia de la página
  índice que se sirve por query string). Verificado en vivo: 2009 pagina a
  3 páginas (20+20+2) y las 42 URLs distintas coinciden con el conteo de
  la tabla de carpetas.
- **Caché**: las tres colecciones son archivos históricos/append-only (un
  boletín o año de auditoría nuevo aparece a lo sumo unas pocas veces al
  año), TTL de 6 horas (21600s) igual que `helpers/sgr_publicaciones_client.py`.
  `get_iess_archivos(coleccion="informes_auditoria")` exige `anio` (a
  diferencia de las otras dos colecciones, que siempre se resuelven
  completas): un año puede traer hasta 42 documentos, cada uno con su
  propia petición a la página de detalle para resolver la URL real, así
  que no hay una llamada barata de "todos los años" — `list_iess_colecciones`
  expone el catálogo de años/conteos primero para que el llamador elija.
- Verificado en vivo con las funciones reales del MCP (no solo con
  `httpx`/`curl` sueltos): `list_iess_colecciones`,
  `get_iess_archivos(coleccion="boletines", anio=2024)`,
  `get_iess_archivos(coleccion="estudios_actuariales", anio=2020)`,
  `get_iess_archivos(coleccion="informes_auditoria", anio=2025)` (carpeta
  de 1 solo documento) y el caso de error cuando falta `anio` para
  `informes_auditoria` — todos devuelven datos reales y URLs que resuelven
  a `documents/10162/...`.

### SENESCYT / Educación Superior / MINEDEC

Pedido explícitamente por Daniel. Datos de educación superior, becas,
registro de títulos. **Revisado 2026-08-16: ya reachable hoy, sin código
nuevo,** vía los tools CKAN genéricos
(`organization="secretaria-de-educacion-superior-ciencia-tecnologia-e-innovacion-senescyt"`
en `datosabiertos.gob.ec`) — 13 datasets: matrícula de universidades
particulares (UEP) 2015-2023, docentes de UEP 2015-2022, oferta académica
de las IES, artículos en revistas indexadas, y varias versiones fechadas de
la base de becarios (agosto 2024, marzo 2024, diciembre 2023, agosto 2023,
sin fecha ×2) — esta última con versiones repetidas sugiere que conviene
usar solo la más reciente o investigar si son acumulativas. Ojo, no cubre
registro de títulos (lo pedido explícitamente por Daniel) — ese dato no
aparece en el CKAN.

Portal propio también encontrado, "Portal de Indicadores de Educación
Superior" (SIAU,
`https://siau.senescyt.gob.ec/portal-de-indicadores-de-educacion-superior/`)
— WordPress con 5 secciones temáticas (Estudiantes, Oferta Académica,
Docentes, Títulos, Becas), pero cada sección es un dashboard de Power BI
embebido, no una API ni archivos descargables — mismo problema visual-only
ya visto en varios portales de este repo (nota: la comparación original con
Superbancos ya no aplica — Superbancos sí tiene boletines reales
descargables, ver más abajo).

**Corrección 2026-08-28 (mismo día):** una nota anterior decía "sigue sin
haber una fuente para registro de títulos" después de solo mirar de nuevo
la página principal del SIAU — conclusión apresurada, no una investigación
real. **Investigado a fondo con búsqueda web:** SENESCYT como marca
prácticamente desapareció — `senescyt.gob.ec/web/guest/consultas` redirige
hoy a `titulos-edusuperior.minedec.gob.ec` (Ministerio de Educación,
Deporte y Cultura — MINEDEC), lo que sugiere una fusión o renombramiento
institucional. Esa URL sí es el portal oficial de "Consulta de Títulos
Registrados": busca por apellidos + cédula/pasaporte, cita el Reglamento
General a la LOES (Art. 56) como único medio oficial de verificación.
Confirmado en vivo que es real y funcional. **Por qué sigue sin ser
candidato a tool:** el formulario exige un captcha ("Ingrese los
caracteres") antes de buscar — completar o evadir captchas está
explícitamente prohibido para este asistente (no es una limitación técnica
de scraping, es una regla operativa). La conclusión de fondo cambia de "no
existe" a "existe, es real, pero está detrás de un captcha por diseño
(verificación de identidad uno-a-uno, no un dataset masivo)" — no
automatizable bajo ninguna circunstancia. El dato de la organización CKAN
sigue funcionando sin cambios pese al renombramiento.

**Investigación adicional, mismo día** (Daniel: "investigate elsewhere, and
see what other senescyt data we can find"): la Educación Superior pasó a
ser un **Viceministerio dentro de `educacion.gob.ec`**
(`educacionsuperior.gob.ec` redirige a `educacion.gob.ec/edusuperior/`) —
confirma la fusión institucional apuntada arriba. Su página "Biblioteca"
(`educacion.gob.ec/edusuperior/biblioteca/`) es un archivo real y enorme:
**1,259 documentos descargables**, en un árbol de categorías anidadas por
año/tema desde 2013 hasta 2025 (PAC, Exámenes Especiales/auditoría,
Normativa, LOES, SNNA, Acuerdos, Indicadores ACTI, y una sección completa
"Dirección de Registro de Títulos" con manuales de proceso para títulos
nacionales/extranjeros y codificación SNIESE). Todo servido por el
servidor, sin JS — el acordeón visual está colapsado por CSS
(`display:none`), pero el HTML completo con los 1,259 links reales (plugin
WordPress `download-monitor`) ya está en la respuesta de `httpx` plano;
confirmado descargando uno (Indicadores de Ciencia, Tecnología e Innovación
del Ecuador (ACTI), PDF real). Mismo patrón que la Transparencia/LOTAIP de
IESS (PAC, exámenes de auditoría, normativa) pero en una plataforma
totalmente distinta (WordPress vs. Liferay de IESS) — refuerza la
hipótesis de que estas categorías se repiten entre instituciones no por
compartir tecnología sino porque las exige la ley (LOTAIP, PAC), así que un
scraper genérico "categorías legales comunes" podría generalizar mejor que
uno por-institución.

Sobre el registro de títulos específicamente: la carpeta correspondiente
contiene manuales/instructivos/acuerdos sobre *cómo funciona* el proceso de
registro, no una base descargable de títulos individuales — coherente con
que ese dato es personal/sensible y por eso solo se expone vía la consulta
captcha uno-a-uno de arriba, no como dataset masivo. Sin explorar:
`eod-prett.senescyt.gob.ec` (linkeado desde la página del Viceministerio,
propósito no investigado).

**Segundo archivo real, 2026-08-29, aparte de la "Biblioteca" ya
documentada:**
`siau.senescyt.gob.ec/estadisticas-de-educacion-superior-ciencia-tecnologia-e-innovacion/`
tiene su propio archivo de reportes reales (mismo patrón WordPress
`download-monitor`): Reporte PND, indicadores de educación superior/CTI,
índice de competitividad del Ecuador, inventario de indicadores CTI y
saberes ancestrales, caracterización de la demanda laboral — algunos
enlazan a instancias Nextcloud propias (`cloud-00.senescyt.gob.ec`,
`cloud-pro.senescyt.gob.ec`), igual que el manual del Geoportal del IGM. No
se encontró una sección específica de resultados del examen ENES/SNNA por
nombre en este archivo — ver INEVAL más abajo, que sí resultó ser la fuente
real para eso.

**Construido, 2026-09-10:** el archivo de reportes de SIAU descrito arriba
se confirmó en vivo otra vez y se construyó como `search_senescyt_estadisticas`
(`helpers/senescyt_client.py`). La página mezcla dos mecanismos de descarga
reales en el mismo acordeón WPBakery ("w-tabs", 10 pestañas): 8 paquetes
WordPress Download Manager (título propio + badges Size/Last Updated + un
link `data-downloadurl=".../download/<slug>/?wpdmdl=ID&refresh=..."`, real
pero sin extensión visible en el HTML — `formato` queda "DESCONOCIDO", igual
que la Biblioteca de SGR) y 4 botones "Descargar" directos en 3 pestañas más
(un `.zip` propio con extensión real, y 3 enlaces a instancias Nextcloud del
propio SENESCYT — `cloud-00`/`cloud-pro.senescyt.gob.ec` — también sin
extensión visible). Total 12 archivos confirmados en vivo, no los 557/1260
de otras fuentes de este proyecto — es un archivo curado, no una base masiva.
Una pestaña ("Reporte de indicadores año 2021") anida dos paquetes WPDM
distintos bajo un solo título de acordeón ("Productos intermedios", "Reporte
de indicadores"); otra ("Reporte de indicadores año 2024") anida dos links
directos ("Primera parte", "Segunda parte") — ambos casos reales, confirmados
leyendo el markup crudo, no duplicados del parser.

**Bloqueado y luego resuelto el mismo día, 2026-09-10:** `educacion.gob.ec`
(el dominio de la Biblioteca y de `search_minedec_matricula`) estuvo
inalcanzable en la primera pasada de hoy (`SSL: UNEXPECTED_EOF_WHILE_READING`
con `httpx`, y timeout de conexión en un segundo intento) — mismo síntoma
documentado para MIDUVI, y consistente con una caída temporal del lado del
servidor (no bloqueo geográfico ni WAF: no hubo redirect ni challenge, la
conexión TLS simplemente no completó). Daniel confirmó estar conectado por
VPN; un reintento bajo esa VPN conectó sin problema (`educacion.gob.ec/` y
`search_minedec_matricula` ambos funcionando de nuevo) — sugiere que el corte
era específico de la ruta de red usada en el primer intento, no del
servidor. **Construido en el mismo pase, ya con el dominio alcanzable:**
`list_senescyt_biblioteca_categorias`/`get_senescyt_biblioteca_categoria_archivos`
(`helpers/senescyt_biblioteca_client.py`), reutilizando exactamente el
mismo parser de `helpers/sgr_publicaciones_client.py`/
`helpers/arcsa_client.py` (`ul.ul-downloads`, `li.li-gray1` con `id="cat-N"`,
pares "ver"/"Descargar" `download.php?id=N&force=0/1`), retargeteado a
`educacion.gob.ec/edusuperior/biblioteca/`. Confirmado en vivo: 17 categorías
de primer nivel, 1.259 entradas en el documento completo (coincide
exactamente con la cifra de la pasada del 2026-08-28), 1.258 tras deduplicar
por categoría (2 ids se repiten — una vez dentro de la misma categoría,
correctamente deduplicada; otra vez across dos categorías distintas,
mantenida en ambas a propósito, igual que SGR/ARCSA). Categorías de primer
nivel confirmadas: Insumos Construcción Diagnóstico PND-ETN 2025-2029,
Consejo Ciudadano Sectorial del SNES y SNCTI, PAC SENESCYT 2023/2024/2025
(una categoría por año, no anidadas bajo un "PAC" compartido), El Concurso
de Méritos y Oposición, Indicadores ACTI, Mecanismo de Participación
Ciudadana, Dirección Administrativa, Consejo de Participación Ciudadana,
Participación Ciudadana, Exámenes Especiales, Publicaciones, Normativa,
LOES, SNNA, y Acuerdos (694 de las 1.259 entradas por sí sola). **Nesting
más profundo que cualquier instancia previa del patrón:** confirmado en vivo
hasta 3 niveles bajo Normativa (Normativa > "Reglamento de Servicios de
Registro de Títulos" > "a. Documento inicial" > archivo real) — la sección
"Dirección de Registro de Títulos" que la pasada del 2026-08-28 describió
como aparentemente propia vive en realidad anidada ahí, no como categoría de
primer nivel. `get_biblioteca_categoria_archivos` sigue sin construir un
breadcrumb completo (mismo diseño deliberado de SGR/ARCSA): para una ruta de
3 niveles, "subgrupo" queda como el encabezado más cercano únicamente.

**IEPI/SENADI (2026-08-29):** IEPI se convirtió en SENADI en 2018 (bajo el
paraguas de SENESCYT). Su dominio real y vivo es
`derechosintelectuales.gob.ec` (`propiedadintelectual.gob.ec` redirige
ahí). **Corrección el mismo día, a raíz de que Daniel preguntó
específicamente por patentes:** una nota anterior decía que el único
dataset de SENADI estaba mal catalogado bajo el instituto geológico —
resultó ser una búsqueda incompleta. `search_datasets(query="patentes")`
encuentra 4 resultados: 2 sí están mal catalogados bajo
`instituto-de-investigacion-geologico-y-energetico-iige` (el instituto
geológico), pero los otros 2 ("Número de solicitudes de Patentes de
Invención", con una versión con corte a jun-2022) están correctamente bajo
su propia organización, `servicio-nacional-de-derechos-intelectuales-
senadi`, con 8 datasets en total — ya alcanzable con los tools genéricos.
Patentes de invención específicamente ya cubiertas. La página de
estadísticas propia de SENADI encontrada antes es un artículo de noticia de
2017, no un portal de datos vivo — sin confirmar si existe uno más actual,
pero ya no hace falta para patentes.

### Cuenca en Datos

**Hecho 2026-08-28.** Verificado en vivo: CKAN 2.9.6, 92 datasets, 13
categorías temáticas, un solo publicador (GAD Municipal del cantón Cuenca).
Mismo shape de API que el portal nacional
(`package_search`/`package_show`/`resource_show`/...), así que en vez de un
cliente/tools nuevos y paralelos, los ~10 tools CKAN genéricos
(`search_datasets`, `list_recent_datasets`, `get_dataset_info`,
`list_dataset_resources`, `get_resource_info`, `preview_resource_data`,
`download_resource`, `query_resource_data`, `search_organizations`,
`get_organization_info`, `list_categories`, `get_category_info`, y
`detect_series_pattern`) ahora aceptan `source="nacional"|"cuenca"`.
`helpers/ckan_client.py` resuelve la URL base según `source`
(`_resolve_source`/`_ckan_url`/`site_url`, nuevos), con caché de categorías
separada por fuente (`group_list:{source}`) para no mezclar las categorías
de ambos portales. Nuevas variables de entorno opcionales
`CUENCA_API_URL`/`CUENCA_SITE_URL`.

Verificado en vivo end-to-end: `search_datasets`, `list_categories`,
`search_organizations`, `get_dataset_info`, `list_dataset_resources`,
`get_resource_info` y `preview_resource_data` (CSV real: actas de sesiones
del Concejo Cantonal) devuelven datos correctos contra `source="cuenca"`;
confirmado también que una búsqueda `source` nacional no encuentra
contenido específico de Cuenca (los catálogos están genuinamente separados,
no es un fallback silencioso). Gap encontrado y cerrado 2026-08-28: varios
recursos de Cuenca son `.ods` — ver ítem `.ods` en "Formatos y tipos de
recursos" en ROADMAP.md.

Cuenca (el cantón) tiene además un portal propio de transparencia,
`transparencia.cuenca.gob.ec/es/datos-abiertos`, **distinto** del CKAN
"Cuenca en Datos" ya integrado — sin visitar, podría complementar o
solapar con lo que ya se tiene.

---

## Sitios de ministerios individuales — barrido completo

**Investigado 2026-08-29** en seis pasadas el mismo día, pedido de Daniel:
justicia/seguridad (Fiscalía, Judicatura, Ministerio de Gobierno, Policía,
ECU911) → SEPS, Defensa/cartografía, ambiente, salud → insistir en
Fiscalía, agregar Superbancos, revisar si las organizaciones CKAN ya
confirmadas tienen además sitios propios → Educación, Aduana, Ministerio de
Gobierno, Ministerio del Interior (dominio real), BCE más allá de BCEData →
Industria/Producción, Ambiente, Agricultura → Contraloría a fondo,
desnutrición, PGE, CNE, SRI, ENES, IEPI, cultura, mujeres.

**Resultado principal:** la gran mayoría ya está cubierta por el portal
CKAN nacional que este proyecto ya integra — no hacía falta ninguna
conexión nueva para confirmarlo, solo verificar que la organización CKAN
existe y tiene contenido real. Ver también nota de alcance: a partir de la
tercera pasada, Daniel pidió explícitamente enfocarse en portales/páginas
propias más allá de CKAN, no en confirmar membresía CKAN.

### Primera y segunda pasada — cobertura CKAN confirmada

- **Consejo de la Judicatura** (`organization=cj`) — causas
  ingresadas/resueltas/en trámite por materia, provincia, cantón, desde
  2017, en ODS/XLSX, actualizado dic. 2025. También tiene su propio "Portal
  de Estadística Judicial"
  (`fsweb.funcionjudicial.gob.ec/estadisticas/datoscj/portalestadistica.html`)
  — revisado y parece roto o mal configurado (página casi en blanco, sin
  iframe ni contenido visible). El dataset CKAN sigue siendo el camino
  real.
- **Ministerio del Interior / Ministerio de Gobierno**
  (`organization=ministerio-del-interior`) — homicidios intencionales,
  personas desaparecidas, detenidos/aprehendidas, armas incautadas, trata
  de personas.
- **ECU911** (`organization=ecu-911`) — bases de emergencias mensuales
  (CSV/ODS), con recursos hasta al menos febrero 2025.
- **IGM / Ministerio de Defensa** (`organization=igm`) — 25 datasets.
  Además tiene su propio Geoportal (`geoportaligm.gob.ec`) con cartografía
  descargable — ver detalle de fricción de acceso más abajo.
- **MAATE** (`organization=ministerio-del-ambiente-agua-y-transicion-ecologica`)
  — indicadores ambientales y de recurso hídrico (SINIAS), CSV/ODS,
  actualizado jul. 2025.
- **Ministerio de Salud Pública** (`organization=ministerio-de-salud-publica`)
  — 8 datasets (defunciones generales, matrimonios, divorcios y más vía
  Registro Civil).
- **SEPS** (Superintendencia de Economía Popular y Solidaria) — el sitio
  principal `seps.gob.ec` bloquea activamente las conexiones automatizadas
  (título "Blocked" al navegar, 404 vía `httpx` plano — distinto del 403
  "fuera de Latinoamérica" ya documentado para `datosabiertos.gob.ec`,
  posiblemente por huella de bot). Pero el subdominio
  `estadisticas.seps.gob.ec` sí es alcanzable (200 vía `httpx` plano) y
  tiene boletines reales (calificadoras de riesgo de cooperativas, PDF,
  hasta dic. 2025).
- **Fiscalía General del Estado** — revisado de nuevo (pedido explícito de
  Daniel de incluirla igual). No tiene organización CKAN propia —
  confirmado con `search_datasets` directo (0 resultados relevantes). Su
  sección "Estadísticas FGE" (violencia de género, robos) está abandonada
  desde 2021 (última entrada: "Cifras femicidio corte 07 de noviembre
  2021"); su "Analítica cifras de robo" es un dashboard Power BI embebido,
  visual-only. Su "Consulta de Noticias del Delito"
  (`gestiondefiscalias.gob.ec/siaf/...`) es real y funcional, pero es una
  búsqueda de un caso a la vez por nombre/placa/número de denuncia —
  aunque no tiene captcha, no encaja como tool de este proyecto: es una
  herramienta de consulta de expedientes personales, no un dataset
  agregado, y automatizarla como búsqueda de personas se sale del
  propósito de este servidor. Sí se encontró algo real y útil, adyacente a
  Fiscalía: el organismo forense que trabaja con ella tiene su propia
  organización CKAN, `servicio-nacional-de-medicina-legal-y-ciencias-
  forenses` (10 datasets, incl. "Pericias realizadas en Ciencias Forenses
  y Medicina Legal 2024") — ya alcanzable.
- **Policía Nacional** — tiene una página "Conjunto de datos"
  (`policia.gob.ec/wpfd_file/conjunto-de-datos/`) pero el único archivo
  real ahí es un CSV de contactos LOTAIP, no datos operativos. Los datos
  de seguridad reales de Policía viven en el CKAN de Ministerio del
  Interior, no en el sitio propio de la Policía.
- **Superintendencia de Bancos** — corrección a una nota anterior que la
  comparaba con SENESCYT como "visual-only": eso era cierto solo para sus
  "Visualizadores" (Power BI), pero el sitio tiene un Portal Estadístico
  separado (`superbancos.gob.ec/estadisticas/portalestudios/`) con
  boletines financieros mensuales reales en `.zip`, con histórico completo
  desde 1997 (`BOL_FIN_BCOS_{año}.zip`, confirmado descargando el de 2003,
  2.8 MB real). Sin organización CKAN propia. El boletín del mes/año
  actual se sirve vía un widget OneDrive embebido (requiere JS), pero el
  archivo histórico completo (1997 en adelante) son links estáticos. Ojo:
  este subdominio necesita `verify=False` en la descarga — certificado TLS
  mal configurado.
- **Trabajo, Turismo, Producción/Comercio Exterior/Pesca** — las tres
  tienen organización CKAN propia y ya alcanzable: `ministerio-del-trabajo`
  (5 datasets), `ministerio-de-turismo` (5 datasets),
  `ministerio-de-produccion-comercio-exterior-inversiones-y-pesca-mpceip`
  (8 datasets — el mismo MPCEIP que ya motivó `detect_series_pattern` con
  los precios de cacao).

### Tercera pasada — portales propios más allá de CKAN

Daniel pidió explícitamente enfocarse en portales/páginas de estadísticas
propias, no en cobertura CKAN.

- **MAATE — hallazgo real e inesperado:** su dominio histórico
  `ambiente.gob.ec` ya no le pertenece — redirige a `atencionintegral.gob.ec`,
  el sitio del **SNAI** (Servicio Nacional de Atención Integral a Personas
  Privadas de la Libertad, el sistema penitenciario), una institución
  totalmente distinta. El sitio real actual del ministerio es
  `ambienteyenergia.gob.ec` — confirma que el ministerio se renombró (o se
  fusionó con Energía). Su Transparencia/LOTAIP (mismo patrón WordPress
  `download-monitor`) reveló algo nuevo: Minería está ahora bajo el mismo
  ministerio ("Viceministerio de Minas"), con "Reportes Semanales Sector
  Minero" — datos reales, de periodicidad semanal, sin explorar más a
  fondo. `sinias.ambiente.gob.ec` (el sistema de indicadores ambientales)
  resultó ser una página de bienvenida por defecto de JBoss sin aplicación
  desplegada — infraestructura muerta.
- **`turismo.gob.ec` tiene el mismo problema de redirección** — también
  termina en `atencionintegral.gob.ec`. Probablemente un vhost por defecto
  mal configurado en hosting compartido (mismo tipo de bug ya documentado
  para `datosabiertos.gob.ec`), no una fuente de datos real; no se
  encontró el dominio actual real de Turismo.
- **ECU911** (`ecu911.gob.ec/Datos/`, sin `www`) — solo un dashboard Power
  BI embebido. Curiosamente la página expone en HTML plano un
  usuario/contraseña de acceso compartido al reporte — irrelevante de
  todos modos, porque incluso con acceso solo es un visor de reporte, no
  una API. Nada más allá de CKAN.
- **Ministerio de Salud** — `datos-abiertos-2/` es solo un texto
  promocional que apunta de vuelta a `datosabiertos.gob.ec`;
  `salud-en-cifras/` resultó ser una categoría de noticias/boletines de
  prensa, no un repositorio de datos, pese al nombre; `geosalud-en-cifras/`
  ya no existe (redirige al inicio). Nada más allá de CKAN.
- **Ministerio de Gobierno** y **Ministerio de Defensa** — revisados, sin
  páginas de estadísticas/datos propias más allá de lo que ya enlazan
  directo a `datosabiertos.gob.ec`. Defensa además ofrece un formulario de
  "Transparencia Colaborativa" para pedir información puntual
  (`servicios.midena.gob.ec/Transparencia/`), no un dataset descargable.
- **Geoportal del IGM** — investigado más a fondo: la cartografía de libre
  acceso está detrás de un formulario de registro
  (`geoportaligm.gob.ec/formulario3/...`), y los datos GNSS/red
  gravimétrica requieren crear una cuenta gratuita para poder descargar
  (login real, no solo un captcha). Ambos caen en la misma categoría que
  el registro de títulos: no son gratuitos en el sentido de "sin
  fricción", y crear cuentas no es algo que este asistente haga — pendiente
  real (arquitectura geoespacial), no algo bloqueado por falta de
  esfuerzo, pero tampoco automatizable tal cual está.
- **Producción** (`produccion.gob.ec`) — nada de estadísticas propias en
  la navegación principal, pero enlaza a `aduana.gob.ec`/ECUAPASS — ver
  hallazgo de comercio exterior más abajo.

### Cuarta pasada — BCE/IEM, Interior vs. Gobierno, MINEDEC, Aduana

Daniel pidió específicamente: Educación, Aduana, Ministerio de Gobierno,
Ministerio del Interior (investigar su dominio real), y más de BCE más allá
de BCEData; mencionó interés en un catálogo con publicaciones mensuales
(resultó ser la IEM del BCE, ver arriba).

- **Ministerio del Interior vs. Ministerio de Gobierno — son dos sitios
  reales y distintos, no un simple renombramiento** (a diferencia de
  SENESCYT→MINEDEC). `ministeriodelinterior.gob.ec` y
  `ministeriodegobierno.gob.ec` ambos resuelven, ambos responden 200, con
  títulos y contenido distintos. Interior tiene su propio "Micrositio de
  Estadísticas de Seguridad" (`cifras.ministeriodelinterior.gob.ec`) — una
  app Angular real (necesita JS, `httpx` plano solo devuelve el shell
  vacío) protegida por **Incapsula** (WAF anti-bot). Una vez renderizada
  muestra "Visualizadores" para homicidios, armas ilícitas, desaparecidos,
  trata de personas, detenidos — exactamente las mismas categorías que ya
  están en el CKAN de `ministerio-del-interior`, sin links de descarga
  visibles (solo visualizadores) — duplicado del dato ya cubierto, no una
  fuente nueva. Ministerio de Gobierno: su página de "Indicador PND
  2025-2029 MAPIs" (violencia de género) solo tiene documentos
  metodológicos/normativos — no la serie de datos en sí. Ninguno de los
  dos aporta algo descargable más allá de CKAN.
- **Educación básica / MINEDEC — hallazgo real:**
  `educacion.gob.ec/datos-abiertos-minedec/` tiene un registro
  administrativo histórico de matrícula 2009-2025 en Excel real
  (`Registro-Administrativo-Historico_2009-202X-{Inicio,Fin}.xlsx`, más
  diccionario de datos y metadatos, actualizado abril 2026, confirmado con
  `HEAD` real). Esto es más rico que los 2 datasets que ya tiene
  `organization=ministerio-de-educacion` en CKAN — candidato real a mirar
  más de cerca si se decide un tool de educación básica.
- **Aduana/comercio exterior — dead end confirmado, no solo supuesto.**
  Tanto `aduana.gob.ec/estadisticas/` como `produccion.gob.ec/boletines-
  mensuales-de-comercio-exterior/` son páginas reales pero vacías (la de
  Producción muestra pestañas por año 2021-2026 sin ningún archivo real
  detrás, confirmado buscando enlaces `.pdf/.xlsx/.zip` en el HTML plano:
  cero). La búsqueda web confirma por qué: las estadísticas de comercio
  exterior de SENAE se piden por oficio o correo al Service Desk, no se
  publican en un portal abierto. No es una limitación técnica de
  scraping — el dato simplemente no está publicado así. (Ver más abajo:
  el sector privado, FEDEXPOR, sí publica esto.)

### Quinta pasada — SIPA, MDEP, Contraloría (primer contacto)

Daniel: "investigar aún más profundo, no queremos perdernos nada" —
Ministerio de Industria/Producción, Ambiente, Agricultura, y lo que
aparezca.

**SIPA (Sistema de Información Pública Agropecuaria) — el hallazgo más
grande de toda esta investigación.** `sipa.agricultura.gob.ec`, del
**Ministerio de Agricultura, Ganadería y Pesca** (`agricultura.gob.ec`,
real, vivo, **distinto de MPCEIP** — Agricultura y Comercio
Exterior/Producción son dos ministerios separados, no uno solo pese al
traslape de "Pesca" en ambos nombres). Solo el módulo económico
(`sipa-estadisticas/estadisticas-descargas/estadisticas-economicas`) tiene
**12 archivos Excel reales y de descarga directa, sin registro ni login**:
valor agregado bruto agropecuario, comercio exterior agropecuario/
agroindustrial, crédito público y privado agropecuario, sector silvícola,
precios productor ponderado, precios mercados mayoristas, precios
agroindustria, precios pecuarios, precios internacionales, precios
agroquímicos/fertilizantes, IPC alimentos/inflación, índices de sector.
Confirmado descargando uno real: `precios-productor-ponderado.xlsx`, **41.4
MB** — muy por encima del tope de 5 MB que usan los tools de preview de
este proyecto (mismo problema de escala que el PDF actuarial de 14.6 MB de
IESS). Y eso es solo un módulo — el sitio además tiene "Cifras
Agroproductivas" y "Cifras Territoriales" (tableros dinámicos,
probablemente Power BI, sin confirmar), boletines nacionales (Panorama
Agroestadístico, Precios Mayoristas, Precios Internacionales, Precios
Productor), boletines situacionales por cultivo (ej. papa), un Panorama
Agroeconómico anual, y un geoportal propio de ortofotos
(`geoportal.agricultura.gob.ec`) — más geoespacial, sin explorar. Esto
reemplaza por completo la cobertura actual de `detect_series_pattern`/
cacao vía MPCEIP: es la fuente real y mucho más rica para todo lo
agropecuario.

**Integrado 2026-08-29** (`helpers/sipa_client.py`,
`tools/list_sipa_modulos.py`, `tools/get_sipa_modulo_archivos.py`). No solo
el módulo económico tiene descargas directas — los otros tres
("estadisticas-productivas", "estadisticas-social",
"censos-y-registros-administrativos") comparten exactamente la misma
página Joomla + acordeón UIKit, así que se cubrieron los 4 de una vez: **30
archivos reales verificados en vivo** (13 económico, 9 productivo, 4
social, 4 censos). Cada módulo es una página fija (no hay que buscarla,
son 4 URLs hardcodeadas) con items `<div class="el-item">` — título
numerado, descripción opcional, link de descarga directo — confirmado por
scraping en vivo, no solo mirando el HTML. **Gotcha real encontrado
recién al verificar los 4 módulos en vivo (no solo el económico que ya
estaba documentado arriba):** el módulo de censos tiene items sin párrafo
de descripción — un regex que asumía la descripción como obligatoria
matcheaba 0 archivos ahí silenciosamente. Corregido parseando cada item
por separado (split en `el-item`) con descripción opcional en vez de un
regex secuencial estricto; cubierto por test. Los archivos no se
descargan a través de este MCP (varios superan los 41 MB) — los tools
solo devuelven metadata + URL directa, igual que
`get_inec_estadistica_files`.

**Ministerio de Finanzas se fusionó/renombró** — otro caso como
SENESCYT→MINEDEC. `finanzas.gob.ec` redirige a `economicoproductivo.gob.ec`,
el "Ministerio de Desarrollo Económico y Productivo" (MDEP) — sugiere que
Finanzas, Producción/Industrias (`industrias.gob.ec` ya no resuelve por
DNS, consistente con que se fusionó para acá) y quizás más quedaron bajo un
solo ministerio nuevo. Tiene una página real "Estadísticas Fiscales"
(`finanzas.gob.ec/estadisticas-fiscales/`, las URLs internas siguen con el
dominio viejo) con calendario de publicación de estadísticas de finanzas
públicas 2026 y documentos de deuda pública. (Resuelto más a fondo en la
investigación de recaudación arancelaria, ver más abajo — esta es la misma
fuente que tiene la serie fiscal completa 2013-2026.)

**Contraloría General del Estado — primer contacto, resuelto luego en la
sexta pasada.** Su página "Datos Abiertos" (`contraloria.gob.ec/Portal/24287`)
aloja "Informes aprobados", un archivo trimestral de *todos* los informes
de auditoría aprobados a *cualquier* institución pública del país
(enero-marzo 2023 en adelante) — mucho más amplio que el archivo de
auditorías que ya se encontró solo para IESS. También hay "Consulta de
declaraciones patrimoniales" y "Plan anual de control".

**Patrón sistémico confirmado de dominios `.gob.ec` viejos redirigiendo al
mismo lugar equivocado:** además de `ambiente.gob.ec` y `turismo.gob.ec`,
`arcsa.gob.ec` (regulador de medicamentos/alimentos) también redirige a
`atencionintegral.gob.ec` (SNAI) — tercer caso confirmado. Fuerte indicio
de un vhost por defecto mal configurado en infraestructura de hosting
compartida del Estado, no una serie de coincidencias. No vale la pena
seguir intentando adivinar el dominio real de cada uno uno por uno — mejor
buscar el dominio correcto por separado cuando haga falta una institución
específica.

**Dos sitios más protegidos por Incapsula**, además del micrositio de
Interior: **CNE** (Consejo Nacional Electoral, `cne.gob.ec`, 403 directo a
`httpx` con firma Incapsula en el body — confirmado con un segundo método
en la sexta pasada, `cne.gob.ec/estadisticas/bases-de-datos/` da página en
blanco también vía el browser real, no solo `httpx`) — datos electorales
quedan fuera de alcance sin resolver el WAF. **MIDUVI**
(`miduvi.gob.ec`) falla directo a nivel TLS
(`SSL: UNEXPECTED_EOF_WHILE_READING`) tanto con `httpx` como con el
browser real — no es un problema de geografía ni de WAF, el sitio
simplemente no responde bien. No se encontró un dominio alternativo
vigente en la búsqueda web — a diferencia de SENESCYT→MINEDEC y
Finanzas→MDEP, no hay evidencia de que MIDUVI se haya renombrado, solo de
que su sitio está caído.

### Sexta pasada — Contraloría resuelto, desnutrición, PGE, SRI, SENADI, cultura, género

Daniel: profundizar Contraloría "no queremos perdernos nada", más
desnutrición/INEC/Presupuesto General del Estado/CNE, luego
SRI/ENES/IEPI/cultura/mujeres.

**Contraloría — resuelto de punta a punta.** El botón de descarga de
"Informes aprobados" llama a una función JS (`down('pesdoc', 67)`) que
arma la URL `contraloria.gob.ec/WFDescarga.aspx?id={id}&tipo=pesdoc&op=d` —
confirmado real, sin necesidad de browser: descargué el de enero-marzo 2023
y es un **CSV real de 155 KB**, no un PDF — columnas `Unidad de Control;
Entidad; Diligencia; Periodo Desde; Periodo Hasta; Tipo de informe; N°
Informe; Fecha Aprobación`, una fila por informe de auditoría aprobado a
*cualquier* institución pública del país. Totalmente scrapeable con
`httpx` una vez que se conoce el patrón de URL (falta solo mapear los `id`
de cada trimestre, visibles en el HTML de la página). Probablemente el
hallazgo más *inmediatamente accionable* de toda la investigación — sin
JS, sin login, sin captcha, datos estructurados de verdad.

**Integrado 2026-08-29** (`helpers/contraloria_client.py`,
`tools/list_contraloria_informes.py`, `tools/get_contraloria_informe.py`).
El `id`/`tipo` de cada trimestre se scrapea en vivo desde
`contraloria.gob.ec/Portal/24287` (no hardcodeado, a diferencia de SIPA —
aquí sí se agrega un trimestre nuevo cada ~3 meses, confirmado por el
propio historial: 9 documentos disponibles a la fecha, del rango
ene-mar-2023 a abr-jun-2024). La descarga+parseo reutiliza
`helpers/csv_reader.preview_csv` en vez de reimplementar el manejo de CSV.

**Bug real encontrado y corregido de paso, en infraestructura
compartida:** `helpers/csv_reader.py`'s `_parse_csv_bytes` adivinaba el
delimitador contando ocurrencias de `,`/`;`/tab/`|` en los primeros 2000
caracteres del archivo — funciona para la mayoría de CSVs, pero **falla
en vivo contra los CSV reales de Contraloría**: sus columnas `Diligencia`
son prosa en español ("Examen sobre procesos, contratos, convenios...")
con varias comas por fila, y en una muestra de ~5 filas el conteo de comas
(30) superó por poco al de punto y coma (29, el delimitador real),
partiendo cada fila en un solo campo gigante en vez de 9 columnas. Se
reemplazó por `csv.Sniffer` (que pondera consistencia entre filas, no solo
conteo bruto) con fallback a contar solo en la primera línea (encabezado)
si Sniffer no logra decidir. Corregido y verificado en vivo — este bug
afecta a `preview_csv`/`preview_resource_data` en general, no solo a
Contraloría, así que cualquier CSV de otra fuente con texto libre
comma-heavy en las primeras filas se beneficia de la corrección.

**Desnutrición — ya cubierta, confirmado que no hay gap.** La Secretaría
Técnica "Ecuador Crece Sin Desnutrición Infantil" (`organization=stecsdi`
en CKAN, 3 datasets de alertas cantonales en tiempo real) no tiene sitio
propio (opera vía redes sociales y páginas de MSP/MEF) — su organización
CKAN es el único punto de acceso real. `search_datasets(query="desnutricion")`
además encuentra ENSANUT 2012/2018, ECV, y "MSP_Nutrición" — 8 datasets en
total, todos ya reachable.

**Presupuesto General del Estado — ya cubierto, muy a fondo.**
`organization=ministerio-de-economia-y-finanzas` en CKAN tiene **97
datasets**, incluyendo ejecución presupuestaria mensual a nivel de Unidad
de Administración Financiera. El slug CKAN conserva el nombre viejo del
ministerio pese a la fusión a "Desarrollo Económico y Productivo" —
mismo patrón de rezago que otros casos.

**SRI** — ver sección propia arriba (127 datasets CKAN).

**Cultura** — `organization=mcyp` (Ministerio de Cultura y Patrimonio) ya
tiene 6 datasets reales en CKAN (visitantes de museos, usuarios de
bibliotecas/archivos históricos, beneficiarios de fondos de patrimonio
cultural, Registro Único de Artistas y Gestores Culturales - RUAC). Ya
reachable, sin gap identificado.

**Mujeres/Género — hallazgo real.** El **Consejo Nacional para la
Igualdad de Género (CNIG)**, `igualdadgenero.gob.ec`, tiene una sección
"Violencia" con el mismo patrón de acordeón `download-monitor` ya
confirmado scrapeable en otros sitios: "Femicidios y Homicidios
Intencionales de Mujeres" (según búsqueda web, una "Matriz de Femicidios"
actualizada **semanalmente** desde agosto 2014 — la periodicidad más alta
encontrada en toda esta investigación) y series de violencia de género
desagregadas por provincia, etnia, discapacidad, edad y quintil de
ingreso. También coordina con INEC la encuesta ENVIGMU (2019, ya en CKAN)
y publica la serie "Mujeres y Hombres en Cifras". No se confirmó el link
de descarga exacto de la matriz de femicidios (no se llegó a expandir el
acordeón), pero el patrón ya probado en otros sitios da alta confianza de
que es real y accesible sin fricción.

---

## Fuentes externas de sociedad civil (no gubernamentales)

**Investigado 2026-08-29, corregido y profundizado 2026-08-29** (misma
fecha, segunda pasada) tras pedido explícito de Daniel: Observatorio
Legislativo, Observatorio de los GADs, Observatorio de Gasto Público "y
otros observatorios de la misma organización/fundación".

**Nota de alcance:** este proyecto se describe (CLAUDE.md) como datos *del
gobierno* ecuatoriano vía CKAN/gob.ec/SRI/BCE/etc. — estas fuentes son de
una fundación de sociedad civil, no del Estado. Investigado igual porque se
pidió explícitamente, pero decidir si integrarlas es una decisión de
alcance del proyecto, no solo técnica.

**Corrección importante:** la primera pasada de esta investigación
concluyó "no hay datasets tabulares, solo análisis narrativo" a partir de
revisar únicamente `gastopublico.org/indicadores`. Esa conclusión era
incorrecta como generalización — se aplicaba a `gastopublico.org`, pero no
se había visitado ninguno de los otros ocho dominios de la red FCD. Daniel
señaló directamente que el Observatorio Legislativo sí tabula las
votaciones de la Asamblea, lo cual llevó a una segunda pasada visitando
cada dominio de la red y probando en vivo cada botón de descarga/API
encontrado (no solo mirando el HTML).

### Fundación Ciudadanía y Desarrollo (FCD) — mapa completo de la red

FCD mantiene **nueve dominios propios**, todos enlazados desde
`ciudadaniaydesarrollo.org/iniciativas/`:

| Dominio | Tema | Datos tabulares reales |
|---|---|---|
| `observatoriolegislativo.ec` | Asamblea Nacional | **Sí — verificado en vivo** |
| `observatoriojudicial.ec` | Función Judicial | Sí, pero congelado desde 2019 |
| `radiografiapolitica.org` | Declaraciones patrimoniales de funcionarios | **Sí — verificado en vivo** |
| `judicial.radiografiapolitica.org` | Ídem, alcance judicial | Sí (misma plataforma) |
| `ojoalconcejo.org` | Concejos de Quito/Guayaquil/Cuenca | **Sí — verificado en vivo** |
| `contratostransparentes.ec` | Contratación pública (banderas rojas) | Parcial — app Shiny, no HTTP simple |
| `observatorioanticorrupcion.ec` | Casos de corrupción | Botón real, endpoint roto (500) |
| `gastopublico.org` | Gasto público / fiscal | No — solo cifras puntuales |
| `cuentasclaras.org` | Financiamiento político | **⚠️ sitio comprometido, ver abajo** |
| `libertadesciudadanas.org` | Alertas de derechos civiles | No — solo notas narrativas |

**Patrón técnico común:** varios de estos sitios (Legislativo, Judicial,
Radiografía Política, Ojo al Concejo) comparten el mismo desarrollador y
la misma arquitectura WordPress: un plugin custom que expone descargas via
`wp-admin/admin-ajax.php?action=<nombre>` (CSV/XLS generados
server-side) y, en dos casos, una página "Datos Abiertos" dedicada con
endpoints REST bajo `/api/<formato>-<dataset>`. Vale la pena tenerlo en
cuenta: si se encuentra un dataset interesante en un dominio de este grupo
que aún no se ha revisado a fondo, buscar primero un botón "Descargar
Excel/CSV" o una página "Datos Abiertos" antes de asumir que no hay nada
— el HTML estático a veces ni siquiera contiene el link correcto (ver bug
de dominio truncado abajo), hay que mirar el JS.

**Observatorio Legislativo (`observatoriolegislativo.ec`) — hallazgo
grande, corrige la conclusión anterior.**
`/analisis-de-voto/` es un registro voto-por-voto del pleno de la Asamblea
Nacional: **408 votaciones** (a la fecha de verificación) con texto de la
moción/proyecto, sesión, fecha, resultado (Aprobado/Rechazado), filtrable
por año, ~90 etiquetas temáticas y tipo de votación (aprobación de leyes,
resoluciones, fiscalización, etc.). Tiene botones CSV/XLS reales:
verificado en vivo contra
`wp-admin/admin-ajax.php?action=ol_generate_csv_general_votaciones` → 200,
`text/csv;charset=UTF-8`, ~143 KB (UTF-16). Columnas: Fecha, Sesión,
Votación, Nombre corto, Tema, Subtema, Categorías Generales. Además,
`/perfil/` (nav "Asambleístas") lista los 151 legisladores actuales,
filtrable por provincia/distrito, género, bancada y comisión, con su
propio export CSV/XLS verificado
(`action=ol_generate_csv_legisladores` → 200, ~42 KB). **No confirmado:**
un desglose de voto individual por asambleísta (quién votó sí/no/abstención
por moción) — se revisó el perfil de una asambleísta y la pestaña "Análisis
del voto" ahí está vacía (solo un título, sin contenido cargado); el
mecanismo real para comparar votos parece ser seleccionar 2+ votaciones en
el archivo y enviarlas a un formulario de análisis, no una descarga directa
por persona. Si se persigue integración, el registro agregado de
votaciones ya es un dataset sólido por sí solo.

**Radiografía Política (`radiografiapolitica.org` +
`judicial.radiografiapolitica.org`) — hallazgo nuevo, no estaba en el mapa
de "Iniciativas" leído la primera vez.** Base de datos de **381+
funcionarios públicos** (Ejecutivo, Legislativo, Judicial, Electoral,
Transparencia y Control Social, otras instituciones) con perfil individual:
patrimonio declarado, activos/pasivos, número de casas/carros/compañías,
formación académica, declaración de impuesto a la renta (SRI), género.
Tiene una página `/datos-abiertos` con API REST real, **verificada en
vivo:** `GET /api/json-patrimonio` → 200, `application/json`, ~119 KB,
estructura `{metaDatos, datosPatrimonioPersona: [{patrimonio, activos,
pasivos, numero_casas, numero_carros, numero_companias,
fecha_declaracion, nombres_persona, apellidos_persona, cargo, ...}]}`.
También expone `/api/json-genero`, `/api/json-sri`, `/api/json-estudio`.
**Bug de UI:** el HTML de la página `/datos-abiertos` muestra los links
como texto plano con el dominio truncado
(`https://radiografiapolitica/api/...`, sin `.org` ni `www`) — hay que
construir la URL real (`https://www.radiografiapolitica.org/api/...`) a
mano o extraerla del DOM (`<a href>`), no copiar el texto visible. El
subdominio `judicial.radiografiapolitica.org/datos-abiertos` replica
exactamente la misma estructura de API, con alcance acotado a funcionarios
del sector justicia — mismo bug de dominio truncado en el texto visible.
Licencia declarada: CC-BY-SA-4.0. Sin fecha de última actualización visible
en los metadatos (a diferencia de Judicial, que si la declara). Este es
probablemente el hallazgo más valioso de toda la red FCD para este
proyecto: no hay ninguna otra fuente ya integrada con declaraciones
patrimoniales de funcionarios públicos.

**Ojo al Concejo (`ojoalconcejo.org`) — confirma la hipótesis de "GADs".**
Monitorea los concejos municipales de **Quito, Guayaquil y Cuenca**
(Cuenca ya cubierto vía CKAN `source="cuenca"`, pero con datos distintos
— aquí es seguimiento legislativo municipal, no datasets generales del
GAD). Cada ciudad tiene páginas de "Proyectos de ordenanza" y "Proyectos
de resolución", filtrables por tema/organización política/comisión/estado
del trámite/fecha, con el mismo patrón de exportación
`admin-ajax.php?action=oda_generate_csv_listado_ordenanzas&city={id}` —
**verificado en vivo:** 200, `text/csv;charset=UTF-8` (con `city=1`
devolvió CSV vacío de 157 bytes, así que falta identificar el `city id`
correcto por ciudad — probablemente 1/2/3 o un slug, no se determinó cuál
mapea a Quito). La página "Tu Concejo en cifras" de Quito devolvió un
error crítico de WordPress al visitarla (sitio parcialmente roto, no solo
esa página — riesgo de que otras secciones también fallen intermitente).
Empezar por Quito si se integra, dado que Guayaquil es el otro grande sin
cobertura y Cuenca ya tiene una vía alterna.

**Observatorio Judicial (`observatoriojudicial.ec`) — real pero
congelado.** Tiene una página "Datos Abiertos"
(`/datos-abiertos-observatorio-judicial`) con 6 datasets vía API REST:
movimiento de causas en la Corte Nacional de Justicia, destituciones de
jueces/servidores judiciales, estándares de accesibilidad en edificios,
consultorios jurídicos gratuitos, número de funcionarios/establecimientos
de acceso a la justicia. **Verificado en vivo:**
`GET /api/json-movimientos-causas-consolidado` → 200, `application/json`,
6.2 KB, con metadatos embebidos (`fecha_modificacion: "2019-10-23"`). Solo
los endpoints `json-*` están vivos — los `excel-*` correspondientes
devuelven 404 (el HTML los muestra como texto, no como links reales,
mismo patrón de "domain truncado" que Radiografía Política). **La fecha de
modificación de 2019 es real y coincide con lo que se ve**: esto es un
dataset histórico congelado, no una fuente que se actualice — útil como
snapshot puntual, no como serie viva.

**Contratación pública (`contratostransparentes.ec`) — dato derivado
valioso, pero difícil de extraer.** Observatorio de Contratación Pública:
calcula un score de "banderas rojas" (transparencia, temporalidad,
trazabilidad, competitividad, confiabilidad) por entidad contratante a
partir de datos OCDS de SERCOP, usando una herramienta propia llamada
"Flagfetti" (código en
`github.com/datasketch/banderas-ecuador-back` — es el pipeline/motor de
reglas, no un dataset; requiere ElasticSearch y un feed de contratos OCDS
para correr, no sirve como fuente de datos en sí). La página de inicio
incrusta un ranking top-10 estático por año (2022/2023/2024) en el HTML
— visible sin fricción. El explorador completo ("Ver todas las
entidades") es un **iframe de una app R Shiny**
(`services.datasketch.co/banderas-app/`, confirmado por el patrón SockJS
+ Highcharts + Selectize en las peticiones de red) — mismo problema que
ASOBANCA Datalab en el roadmap: sin API REST limpia, solo websocket de
Shiny, extracción no trivial. Si el interés es solo el ranking anual
top-10, ya está en el HTML estático de la home; para el dataset completo
habría que replicar la lógica de Flagfetti sobre datos de SERCOP
directamente (que este proyecto ya tiene vía `search_contratos`) en vez de
depender del sitio de FCD.

**Observatorio Anticorrupción (`observatorioanticorrupcion.ec`) — botón
real, backend roto.** Rastrea 42 casos de corrupción con desglose por
función del Estado (Ejecutiva: 22, IESS: 7, Legislativa: 5, GAD: 4,
Judicial: 3, mixta: 1) y etapa procesal (sentencia, archivo, sobreseimiento,
etc.), con un botón "Descargar Excel" apuntando a
`/estadisticas/excel`. **Verificado en vivo: devuelve HTTP 500** —
el mecanismo existe en el frontend pero el backend está caído. No hay
fallback (no se probó JSON directo, no existe una página "Datos Abiertos"
separada en este dominio).

**⚠️ Cuentas Claras (`cuentasclaras.org`) — sitio comprometido, no
integrar sin antes verificar con Daniel.** Observatorio de financiamiento
político (Fondo Partidario Permanente, Fondo de Promoción Electoral,
patrimonio de candidatos). Al extraer el texto de la página de inicio
aparecen, mezclados con el contenido real, varios párrafos de **spam de
casinos/apuestas en línea en holandés, ruso, árabe, eslovaco, húngaro y
español** (ej. "casino zonder cruks", "hondubet liga", enlaces a dominios
de apuestas) — patrón clásico de inyección SEO en un WordPress
comprometido. No se navegó más allá de la portada para evitar interactuar
con contenido inyectado. **Recomendación: reportarle esto a FCD si se
tiene contacto, y no construir ningún tool sobre este dominio hasta que se
confirme que está limpio.**

**Observatorio a las Libertades Ciudadanas (`libertadesciudadanas.org`) —
sin datos tabulares.** Feed de alertas narrativas sobre amenazas a
derechos civiles y políticos (prensa, libertad de expresión, presos
políticos, etc.) más informes en PDF. Confirmado: no tiene sección de
datos abiertos ni exports, mismo perfil que Gasto Público.

**Gasto Público (`gastopublico.org`) — conclusión original confirmada,
esta vez revisando también `/visualizaciones` y tráfico de red.** Las
tarjetas de `/indicadores` (Deuda Pública, PIB Nominal, saldo de deuda
interna/externa, etc.) son cifras puntuales sin click-through ni archivo
asociado — confirmado que ninguna tarjeta tiene `href` ni `onclick`. La
página `/visualizaciones` promete un "set de visualizaciones interactivas"
pero no renderiza ninguna (contenido vacío/roto). El sitio es server-side
render tradicional (no SPA), sin llamadas a una API JSON detectables en
las peticiones de red — a diferencia de otros dominios FCD, aquí no había
un mecanismo oculto por encontrar.

### Grupo FARO

`grupofaro.org` — confirmado de nuevo: sin nav de datos/estadísticas, solo
"Quiénes somos / Áreas de acción / Publicaciones / Equipo / Contacto".
Calcula el Índice de Presupuesto Abierto de Ecuador (Open Budget Survey),
pero no aloja un portal de datos propio — es la fuente primaria detrás del
índice (International Budget Partnership) la que tendría los
microdatos, no FARO directamente. Mismo perfil que la primera pasada:
análisis e investigación, no catálogo de datos crudos. No se investigó a
fondo la iniciativa "Ecuador Decide" mencionada en su home (posible
proyecto de datos electorales) — queda pendiente si se retoma esta línea.

**"Gobierno Abierto Ecuador"** (`gobiernoabierto.ec`) — portal multi-actor
(aparece firmando compromisos junto a CNE y FCD) — mencionado en la
búsqueda pero no visitado en ninguna de las dos pasadas.

### Conclusión revisada

A diferencia de la primera pasada, **sí existen datasets tabulares reales
y descargables sin fricción** dentro de la red FCD — la generalización
"todo es análisis narrativo" era incorrecta. Los tres candidatos sólidos
son: **votaciones de la Asamblea** (Observatorio Legislativo),
**declaraciones patrimoniales de funcionarios** (Radiografía Política, sin
comparable en ninguna otra fuente ya integrada) y **ordenanzas/resoluciones
municipales de Quito/Guayaquil** (Ojo al Concejo). Judicial aporta un
snapshot histórico útil pero congelado en 2019. Contratación pública y
Anticorrupción tienen mecanismos reales pero rotos o de difícil extracción
(Shiny, 500). Gasto Público, Libertades Ciudadanas y FARO siguen sin
datasets tabulares — ahí sí se sostiene la conclusión original. Cuentas
Claras necesita atención de seguridad antes de cualquier otra cosa. Sigue
pendiente la decisión de alcance: son fuentes de sociedad civil, no de
gobierno, así que integrarlas implica ampliar lo que CLAUDE.md define como
el alcance del proyecto — pero técnicamente, a diferencia de lo que se
pensó inicialmente, sí hay con qué construir tools reales aquí.

---

## Datos legislativos/normativos para uso legal profesional

**Investigado 2026-08-29,** pedido de Daniel desde la perspectiva de un
profesional del derecho: regulaciones, circulares y similares. **Nota
explícita de Daniel el mismo día: posible que este dominio completo
(legislación/normativa/Registro Oficial/jurisprudencia) termine no siendo
relevante para el proyecto.** Todo lo de abajo quedó investigado porque se
pidió explícitamente, no porque haya una decisión de construir nada.

**`search_regulaciones`/`get_regulacion_info` ya cubren mucho más de lo
documentado hasta ahora.** Conteo real de `tipo` sobre ~2000 regulaciones
del endpoint gob.ec (confirmado en vivo): Resolución (575), Acuerdo
ministerial (442), Ordenanza municipal (394), Decreto ejecutivo (169), Ley
orgánica (164), Ley ordinaria (73), Norma internacional (69), Reglamento
de ley (58), Código Orgánico (52), Carta Suprema (4). Es decir, la
legislación primaria (leyes) ya está cubierta, no solo normativa del
ejecutivo — confirmado descargando una Ley Orgánica real (Ley Orgánica de
Eficiencia Económica y Generación de Empleo, R.O. 461, PDF real). `read_pdf`
ya puede leer estos archivos. Lo único que falta: "Circular" no aparece
como `tipo` — no está en este endpoint.

**Hallazgo grande: el Registro Oficial real y completo, gratis, sin
paywall.** `registroficial.gob.ec` es el sitio oficial de la Corte
Constitucional que edita la Gaceta Oficial de Ecuador. Publica una edición
diaria (confirmado: Nº 357, viernes 28 de agosto de 2026, 43 páginas — el
día hábil más reciente), archivo completo por año desde 2001, cada edición
con botón de descarga real. Confirmado descargando una edición real: PDF
gratis, sin ningún paywall (a pesar de que fuentes de terceros mencionan
una "suscripción anual" para la edición digital fuera de Quito/Guayaquil —
no aplicó en la prueba real). El sitio mismo describe su contenido como
"leyes, decretos, resoluciones, acuerdos, **circulares**, comunicados,
proclamas y despachos de los ministerios" — esto sí incluye circulares, a
diferencia del endpoint de regulaciones de gob.ec. Es la fuente más
completa y canónica posible: todo lo que se publica oficialmente en
Ecuador pasa por aquí. También tiene Suplemento, Edición Especial, Edición
Constitucional, Edición Jurídica, e Índice Mensual — sin explorar cada una
todavía. Candidato de altísima prioridad: un tool
`search_registro_oficial(fecha)` o similar, ligado a `read_pdf`, cubriría
de punta a punta el caso de uso "¿qué se publicó/qué circular/qué
resolución salió tal día", algo que ningún tool actual resuelve bien (la
búsqueda de `search_regulaciones` es por palabra clave sobre un índice
curado, no por fecha de gaceta).

**Circulares por institución** — no investigado a fondo más allá de
confirmar que el Registro Oficial las incluye. Si se necesitan indexadas
por institución emisora (ej. circulares tributarias del SRI, circulares de
Superbancos/SEPS/BCE) en vez de solo por fecha de gaceta, haría falta
revisar la sección de "Normativa" propia de cada regulador.

**Jurisprudencia** — categoría real y separada de "normativa", confirmada.
La Corte Constitucional tiene un buscador de sentencias real
(`buscador.corteconstitucional.gob.ec`, más de 91,406 sentencias, cada una
con URL propia por número de causa, ej.
`.../fichaSentencia?numero=001-14-PJO-CC`). La Corte Nacional de Justicia
(justicia ordinaria, distinta de la Constitucional) tiene su propio
buscador separado (`busquedasentencias.cortenacional.gob.ec`). Ninguno de
los dos se exploró a fondo (estructura de resultados, si hay API o solo
HTML) — confirmado que existen y son reales, no más.

**Proyectos de ley (proceso legislativo en curso)** — confirmado real y
separado de las leyes ya aprobadas. La Asamblea Nacional tiene "Consulta
de Proyectos de Ley" (`proyectosdeley.asambleanacional.gob.ec/report`,
sistema propio con su subdominio) y una página aparte de "Leyes aprobadas
(publicadas en el Registro Oficial)" — el matiz correcto es que
`search_regulaciones` (y el Registro Oficial) cubren leyes *ya aprobadas y
publicadas*, no el trámite legislativo en curso (primer/segundo debate,
comisiones). Sin explorar la estructura del sistema de proyectos de ley.

**Gremios/asociaciones privadas** — ver sección propia más abajo.

---

## Gremios/asociaciones privadas con datos sectoriales

Pedido de Daniel ("car salesmen", bancos, "cualquier otro que valga la
pena"), en tres rondas el 2026-08-29.

**AEADE** (Asociación de Empresas Automotrices del Ecuador, `aeade.net`) —
**confirmado real con archivo real:** "Boletines de prensa: venta de
vehículos" tiene un boletín mensual real y vigente (Julio 2026, el mes más
reciente al momento de revisar, PDF de 9.76 MB, descargado y confirmado,
patrón de URL `aeade.net/?sdm_process_download=1&download_id={id}`, plugin
WordPress "Simple Download Monitor"). El sitio tiene además: **Anuarios**
(informes anuales reales desde 2016), **Boletín de facturación del sector
automotor**, **Informe Macroeconómico Ecuador**, **Aranceles vigentes**,
homologación vehicular, mapa de puntos de carga para vehículos eléctricos —
un archivo genuinamente rico, mismo patrón de descarga en todos (sin
verificar cada uno individualmente, pero con alta confianza dado el
mecanismo ya confirmado).

**ASOBANCA** (Asociación de Bancos Privados del Ecuador) — **Datalab**
(`datalab.asobanca.org.ec/datalab/home.html`) es una SPA real y extensa:
categorías completas para Bancos, Cooperativas, Tasas de Interés,
Servicios Financieros, Sistema Internacional, Sector Real — con
sub-secciones explícitamente llamadas "Base de datos - Cuentas", "Base de
datos - Indicadores", "Base de datos - Tasas de Interés", "Base de Datos -
Sistema Financiero" (PIB por componentes/industrias, inflación por
ciudad/división de consumo/histórica, tarjetas de crédito/débito, cajeros,
puntos de venta). Navegación 100% vía JS (anchors `#`, sin URLs propias
por sección) — no se llegó a rastrear el endpoint de datos real detrás de
la SPA (se revisaron network requests tras un clic y solo se vieron assets
estáticos, no una llamada a API/JSON identificable en el tiempo
disponible). Contenido real y rico confirmado, mecanismo de extracción
todavía sin resolver.

**FEDEXPOR (Federación Ecuatoriana de Exportadores) — hallazgo real y
directamente relevante:** "Reporte Estadístico Expordata"
(`fedexpor.com/inteligencia-comercial/reporte-expordata/`) es un reporte
mensual de comercio exterior, real y vigente — la edición de agosto 2026
(el mes actual al momento de revisar) ya está publicada, con histórico
completo mes a mes desde al menos 2022. Alojado en Google Drive (links
`drive.google.com/file/d/.../view`, no en el propio dominio), sin login ni
suscripción para ver/descargar — confirmado navegando directo al link de
agosto 2026. Esto llena exactamente el hueco que dejó Aduana/SENAE
(comercio exterior no publicado en portal abierto, solo por oficio) — el
sector privado sí lo publica, mensualmente, gratis. Candidato real fuerte
si el interés en comercio exterior sigue en pie.

**CAMICON** (Cámara de la Industria de la Construcción) — revisado, sin
hallazgo propio. La búsqueda web indica que el índice de
confianza/expectativas del sector construcción que se le suele atribuir en
prensa en realidad lo publica el BCE (Índice de Expectativas Económicas) y
el INEC (Índice de Precios de la Construcción, ya visto vía
`datosabiertos.gob.ec` e IPCO de INEC) — CAMICON aparece citando/analizando
esos datos, no publicándolos como fuente primaria propia. No se encontró
una sección de estadísticas/descargas en su sitio.

Todos privados/gremiales, no gobierno — mismo matiz de alcance que los
observatorios de FCD.

---

## INEVAL (Instituto Nacional de Evaluación Educativa)

**Hallazgo grande, 2026-08-29,** a partir de un link que Daniel dio
directamente (`evaluaciones.evaluacion.gob.ec/BI/historico-ser-bachiller/`)
preguntando si ya se había encontrado la data del examen ENES de SENESCYT —
no se había encontrado; es una institución totalmente distinta de
SENESCYT/MINEDEC. INEVAL administra "Ser Bachiller" (examen de grado, se
fusionó con el ENES en 2017 para el proceso de admisión a educación
superior, corrió 2013-2020) y toda una familia de evaluaciones nacionales:
Ser Estudiante (+ variantes "en la Infancia", "en la Mitad del Mundo",
"Galápagos"), Ser Maestro (+ Recategorización), Ser Profesional, más la
evaluación internacional LLECE. Cada evaluación tiene una página con
acordeón por año lectivo (mismo patrón Bootstrap ya confirmado scrapeable
en otros sitios — contenido ya en el DOM, solo colapsado por CSS) con
múltiples archivos reales por año
(`evaluaciones.evaluacion.gob.ec/BI/download/{id}/`, confirmado descargando
uno: ZIP real de 79.5 KB para el año lectivo 2018-2019 de Ser Bachiller —
10 archivos solo para ese año). Sin login, sin captcha. Candidato real y
directo para responder exactamente el tipo de pregunta que motivó esta
búsqueda ("¿dónde están los resultados históricos del examen de admisión a
la universidad?") — mucho más específico y rico que cualquier cosa
encontrada hasta ahora en SENESCYT/Educación Superior para ese propósito
puntual.

**Páginas extra confirmadas en el mismo dominio:** `evaluacion.gob.ec` (el
sitio institucional, distinto del subdominio
`evaluaciones.evaluacion.gob.ec` del Banco de Información) tiene su propia
sección "Resoluciones del Ineval" — mismo patrón de archivo real, vigente
hasta 2026 — pero es normativa/administrativa, no datos de exámenes.

**Construido 2026-09-02/03.** `evaluaciones.evaluacion.gob.ec/BI/` — 9
familias reales con datos descargables (Ser Bachiller, Ser Estudiante +3
variantes, Ser Maestro +Recategorización, Ser Profesional, Llece/ERCE-
SERCE-TERCE), cada una un acordeón Bootstrap estático (sin JS) con paneles
por año lectivo/calendario y tablas de enlaces por dataset×formato — 557
enlaces de descarga confirmados en total, sin login/CAPTCHA.

**Corrección a la investigación previa:** el slug de navegación
`historico-ser-bachiller` (el mismo que motivó el hallazgo original de
arriba) es una página informativa señuelo sin descargas; la página real de
datos usa un slug distinto (`ser-bachiller-2`), solo descubrible desde el
hub "Categoría Bases de Datos" del sitio — cada familia se verificó
independientemente así. Gotcha real: `ser-maestro-2` esconde una fila
`<tr>` obsoleta dentro de un comentario HTML, idéntica a la fila vigente —
el parser descarta comentarios antes de procesar. Construido como
`list_ineval_familias`/`get_ineval_familia_archivos` (`helpers/ineval_client.py`).

---

## Recaudación arancelaria / tributos aduaneros

**Investigado a fondo 2026-08-29,** pedido explícito de Daniel de
profundizar en Aduana específicamente para ingresos por aranceles. Dos
fuentes reales, con un matiz importante entre ellas:

**`aduana.gob.ec/de-interes/tributos-recaudados/`** — página propia de
SENAE, acordeón con el mismo patrón WordPress `download-monitor` ya
confirmado en otros sitios. Desglosa por **ADVALOREM** (el arancel
propiamente dicho), **FODINFA**, IVA, ICE, OTROS, y TOTALES — 60 archivos
Excel reales confirmados (descargado uno: ADVALOREM 2020, 67 KB real).
Pero está desactualizada: solo cubre 2012-2021, nada más reciente (mismo
patrón de abandono ya visto en la página de boletines de comercio exterior
de Producción). La página propia de "Rendición de Cuentas 2024" de SENAE
existe pero está vacía, sin informe adjunto.

**Ministerio de Economía y Finanzas (ahora bajo MDEP) — la fuente
realmente vigente.** `finanzas.gob.ec/estadistica-nueva-metodologia-
2017-2022/` (URL vieja, contenido real dice "2013 – 2026") tiene un
archivo Excel real y actualizado mensualmente hasta mayo 2026 ("Operaciones
de Ingresos y Gastos SPNF 2013-2026", descargado y confirmado real, 2.4
MB), con la metodología GFSM del FMI (misma que usa el BCE en su IEM). En
la hoja "GC" (Gobierno Central), fila `1214 Arancelarios` (dentro de `121
Ingresos tributarios`), serie anual completa 2013-2025 más desglose
trimestral: **2023 = USD 1,180.4M, 2024 = USD 1,117.3M, 2025 = USD
1,231.4M.**

**Ojo con la diferencia de alcance:** esta cifra ("Arancelarios") es
*solo* el arancel/derecho aduanero propiamente dicho — más chica que los
~USD 3,776M que cita la prensa para "recaudación aduanera" 2024, porque
esa cifra de prensa (y la de SENAE) suma también IVA e ICE cobrados en
frontera, no solo el arancel. Para "ingresos por aranceles" en sentido
estricto, la cifra de Finanzas es la correcta; para "todo lo que recauda
Aduana" (arancel + IVA + ICE + FODINFA + otros), la serie histórica de
SENAE (aunque desactualizada) tiene el desglose completo por tipo.

---

## Registro Civil y datos demográficos/salud

**Revisado 2026-08-29, cobertura ya sólida, sin gaps encontrados.**
`organization=registro-civil` en CKAN, 6 datasets reales (transacciones de
cedulación, pasaportes electrónicos, copias de actas registrales, catálogo
de agencias, certificado de firma electrónica). INEC aparte publica
registros estadísticos anuales de matrimonios y divorcios (2022-2024,
confirmados). Sumado a lo ya encontrado en pasadas anteriores (ENSANUT,
MSP_Nutrición, ECV, desnutrición vía `stecsdi`), la cobertura
demográfica/salud vía CKAN es ya bastante completa — no se encontró ningún
portal propio con datos que falten ahí.

---

## Vivienda (MIDUVI)

Confirmado que el dominio está caído: `miduvi.gob.ec` falla a nivel TLS
tanto con `httpx` como con el browser real — no es un problema de
geografía ni de WAF, el sitio simplemente no responde bien. Los datos ya
alcanzables sin código nuevo: `organization=miduvi` en CKAN, 5 datasets
reales (proyectos de vivienda financiados por BID, Banco de Desarrollo de
China, Banco de Desarrollo del Ecuador). No se encontró un dominio
alternativo vigente en la búsqueda web — a diferencia de otros casos
(SENESCYT→MINEDEC, Finanzas→MDEP), no hay evidencia de que MIDUVI se haya
renombrado, solo de que su sitio está caído.

---

## Prensa

Dos fuentes reales, sin profundizar. Del lado gubernamental, SECOM
(Secretaría Nacional de Comunicación) fue eliminada en 2018 y sus
funciones pasaron a la Secretaría General de Comunicación de la
Presidencia (`comunicacion.gob.ec`), que publica boletines de prensa
descargables. Del lado de sociedad civil, Fundamedios
(`fundamedios.org.ec`) lleva 17 años monitoreando agresiones a la libertad
de prensa/expresión en Ecuador, con reportes anuales reales (231
agresiones y 6 periodistas asesinados en 2025, según su reporte). Ninguno
de los dos visitado a fondo para confirmar si hay datasets descargables o
solo boletines/reportes narrativos — mismo patrón que se vio en los
observatorios de FCD.

---

## Permisos y portales municipales

Sin investigar, alcance grande. Pedido de Daniel, no resuelto en esta
sesión. Cuenca (vía `source="cuenca"`) es el único GAD municipal integrado
hoy; permisos de construcción/uso de suelo y portales de otros municipios
grandes (Quito, Guayaquil, y los ~221 GADs municipales restantes) no se
investigaron — cada uno probablemente tiene su propio sitio y formato, así
que esto es una investigación (y posible integración) bastante más grande
que cualquier ítem individual de este documento. Empezar por Quito y
Guayaquil si se decide perseguir esto, dado su tamaño relativo.

---

## Verificaciones técnicas de calidad

### Búsqueda semántica

`search_datasets` pasa directo a búsqueda por palabra clave de CKAN, que
en general es débil frente al catálogo completo (consultas de una sola
palabra sin sinónimos ni relación semántica con el contenido real).
**Corrección 2026-08-27:** el ejemplo original de este ítem ("cacao"
devuelve muy pocos resultados) no se reprodujo verificando de nuevo contra
el portal real — `search_datasets(query="cacao")` y
`search_datasets(query="MPCEIP")` devuelven correctamente los 3 y 8
datasets relevantes respectivamente, incluyendo el dataset de precios FOB
de cacao del MPCEIP. La afirmación de que esta consulta específica fallaba
había quedado desactualizada (o nunca se verificó correctamente) y de paso
se repitió sin verificar en las notas de `detect_series_pattern` — corregido
ahí también. El problema de fondo (búsqueda por palabra clave sin
comprensión semántica) sigue siendo real y motiva el ítem en ROADMAP.md,
solo que sin este ejemplo concreto.

### `detect_series_pattern` — verificación end-to-end

Agregado 2026-08-27: nuevo tool `detect_series_pattern`. Toma el grupo de
recursos con nombre de serie periódica que ya detecta
`list_dataset_resources` (`possible_periodic_series`), descarga los dos
más recientes (hasta 500 filas c/u), busca una columna de fecha/período
por nombre de encabezado (`fecha`, `mes`, `año`, `periodo`, `semana`, ...)
y compara qué valores de período aparecen en ambos archivos. Solapamiento
alto → `acumulado` (el archivo nuevo ya incluye los períodos del anterior,
basta con leer el más reciente); solapamiento casi nulo → `incremental`
(cada archivo cubre un período distinto, hay que combinarlos); si no hay
solapamiento claro o no se detecta ninguna columna de período, devuelve
`indeterminado` en vez de adivinar.

**Verificado 2026-08-27 contra el portal real**
(`base-de-datos-seguro-desempleo` de IESS) — encontrados y corregidos dos
bugs reales durante la verificación, no solo confirmación:

1. Los CSV de IESS traen 1-3 filas de título/banner antes del encabezado
   real (ej. `Monto pagado y numero de beneficiarios 2026` en la fila 1,
   encabezado real `Mes,Monto pagado,...` en la fila 2). `preview_csv`
   siempre trata la fila 0 como encabezado, así que la columna de período
   quedaba invisible. Nueva función `_locate_header_row` escanea las
   primeras filas buscando una que luzca a encabezado real y contenga una
   palabra clave de período.
2. **Hallazgo más serio:** recursos con nombre casi idéntico (`Pagos
   Desempleo Marzo/Abril/Mayo/Junio 2026`) cambian de formato interno
   entre meses sin aviso — unos meses traen el detalle por
   provincia/género (`Mes,Tipo Pago,Provincia,Genero,...`, mes como código
   numérico `"5"`), otros el resumen mensual acumulado
   (`Mes,Monto pagado,...`, mes como palabra `"junio"`). Comparar
   períodos entre dos archivos así da 0% de solapamiento — la heurística
   original lo hubiera reportado como `incremental` con confianza, una
   conclusión técnicamente calculada pero engañosa (el problema real es
   que no son el mismo tipo de reporte, no que cubran períodos
   distintos). Nueva función `_schema_mismatch` compara el conjunto de
   encabezados de ambos archivos antes de confiar en el solapamiento de
   períodos; si comparten menos de la mitad de sus columnas, la
   clasificación se fuerza a `indeterminado` con motivo
   `esquema_distinto_entre_archivos` en vez de adivinar.

**Verificado también contra MPCEIP cacao** (el otro caso motivador),
dataset `96f97d5c-394f-4be6-8046-3266d0cd5711` ("Precios referenciales FOB
para la exportación de cacao en grano"). **Nota de corrección:** durante
esta verificación se afirmó por error que `search_datasets` no encontraba
este dataset ni con "cacao" ni con "MPCEIP" — resultó ser un bug en el
script de diagnóstico usado (indexaba un `result` extra que no existe en
lo que ya devuelve `ckan_client.search_datasets`), no un problema real del
tool. Re-verificado: `search_datasets(query="cacao")` y
`search_datasets(query="MPCEIP")` encuentran este dataset correctamente
entre sus resultados. Comparando los recursos reales `MPCEIP_PRECIO
FOB_EXPORTACIONES CACAO_2023_AGOSTO.csv` vs `..._2023_SEPTIEMBRE.csv`:
`detect_series_pattern` encontró la columna de período compuesta (AÑO,
MES, SEMANA, FECHAS) y clasificó correctamente como `acumulado` (34/34
períodos de agosto = 100% también en septiembre) — coincide exactamente
con la nota de verificación e2e (el archivo de junio 2026 ya trae las 4
semanas de junio *y* los meses previos del año). Primera confirmación real
de que la clasificación en sí (no solo el rechazo seguro a adivinar)
acierta contra el portal real.

**Dos limitaciones reales de auto-detección, encontradas y corregidas en
la misma sesión de verificación:**

1. `detect_periodic_series` agrupaba solo por plantilla de dígitos, así
   que no agrupaba `..._AGOSTO.csv`/`..._SEPTIEMBRE.csv` (difieren en una
   palabra, no en un número) — hubo que pasar
   `resource_id_new`/`resource_id_old` explícitos en la primera
   verificación. Corregido: los nombres de mes en español ahora se
   normalizan al mismo placeholder que los dígitos antes de agrupar.
2. Con el agrupamiento ya corregido, `_pick_pair` (para elegir "los dos
   más recientes" del grupo) ordenaba por `last_modified` de CKAN, que
   resultó no ser confiable: el recurso de enero 2023 tenía un
   `last_modified` *posterior* al de septiembre 2023 (probable
   corrección/re-subida), así que el auto-pick elegía enero como "más
   reciente" — 8 meses al revés. Corregido: nueva función
   `period_sort_key` (en `list_dataset_resources.py`, pública para
   reutilizarse) extrae año/mes del propio nombre del recurso y ordena
   por eso primero, usando el timestamp de CKAN solo como desempate.

Con ambos fixes, `detect_series_pattern(dataset_id=...)` sin argumentos
adicionales ya funciona de punta a punta contra los dos datasets reales
que motivaron este tool: MPCEIP cacao (AGOSTO→SEPTIEMBRE 2023, `acumulado`,
34/34 períodos) e IESS desempleo (Junio→Julio 2026, `acumulado`, 13/13
períodos) — ambos auto-detectados y clasificados correctamente sin pasar
IDs a mano.

Sigue siendo una heurística de nombre de columna + solapamiento de
valores; no garantiza acierto en datasets con columnas de período con
nombres atípicos (ej. meses abreviados como "JUN"/"ABR" en vez de
"junio"/"abril", vistos en recursos MPCEIP más recientes y aún sin
cubrir), y no detecta cambios de esquema más sutiles que el umbral de 50%
de columnas en común.

---

## Verificación end-to-end de cifras (`www.datosabiertos.gob.ec`)

Cifras de referencia contra el portal, para confirmar que los tools
devuelven los números correctos, no solo que no truenan.

### SRI

`contribuyentes-activos-catastro-2025` → 2,904,355 contribuyentes en el
mes más reciente vía `sum(TOTAL)`, no `count(*)` (que da 405,794).
**Verificado 2026-08-16 contra el portal real (con VPN a LatAm, ver nota
de bloqueo geográfico):** cifras exactas — noviembre (mes más reciente)
`sum(TOTAL)` = 2,904,355, `count(*)` total = 405,794. **Hallazgo nuevo:**
el único recurso CSV del dataset (`sri_activos_2025.csv`) en realidad se
descarga como `sri_activos_2025.tar.gz` (5.4 MB comprimido) —
`preview_resource_data` ahora lo detecta correctamente (ver ítem `.tar.gz`
en ROADMAP.md), pero todavía no lo previsualiza como tabla, solo lo
ofrece vía `download_resource`.

### IESS

`base-de-datos-seguro-desempleo`, junio 2026 → 2,561 beneficiarios, USD
836,716.99, excluyendo la fila `TOTAL:` embebida en el archivo (incluirla
da exactamente el doble). **Verificado 2026-08-16:** cifras exactas.
**Hallazgo nuevo:** el dataset tiene *dos* recursos distintos con nombres
casi idénticos para el mismo mes ("Pagos Desempleo Junio 2026" y "Numero
de beneficiarios y montos pagados... a Junio 2026") — el primero es un
resumen mensual acumulado del año completo (una fila por mes desde enero),
el segundo es el detalle por provincia/género con la fila `TOTAL:` real.
Mismo tipo de ambigüedad de nombres que ya motivó el pendiente de
detección acumulado-vs-incremental — confirma que ese pendiente sigue
siendo necesario, no es un caso aislado.

### MPCEIP

Cacao → junio 2026, Grado 1 semanal: 174.77 / 168.15 / 166.28 / 188.07,
usando solo el archivo más reciente. **Verificado 2026-08-16:** cifras
exactas contra `6.-MPCEIP_PRECIO_FOB_EXPORTACIONES-CACAO_JUN_2026.xlsx`.
**Hallazgo nuevo:** ese recurso está declarado `format: CSV` en la
metadata de CKAN pero la URL real es `.xlsx`. **Corrección 2026-08-17:** a
pesar de lo que decía esta nota antes, `preview_resource_data` *no*
resolvía esto — el `format` declarado (`CSV`) se evaluaba antes que la
extensión de la URL, así que este recurso también terminaba en el parser
de CSV en vez del de XLSX. Mismo fix que el caso `.tar.gz` del SRI: ahora
la extensión de URL tiene prioridad. Confirma que confiar solo en el campo
`format` de CKAN no alcanza.

### `.xls`/`.zip` en vivo

**Verificado 2026-08-26 contra el portal real:** `.xls` funciona limpio —
`agrocalidad_centros-de-faenamiento-certificados-con-mabio_dd_2021.xls`
(resource `4d756998-8f91-4bf9-9edd-6395bac99dfe`) se previsualiza con
acentos correctamente decodificados (`ó` = `0xf3`, confirmado a nivel de
code point — lo que parecía verse mal era solo la consola de Windows, no
un bug de decodificación real). Tres hallazgos reales de `.zip` que
llevaron a fixes, no solo confirmación:

1. Un `.zip` real de 17 MB (`organizacion-territorial-cantonal.zip` y
   `mag_estimacionesprimerperiodo_2020.zip`) truncado a los 5 MB de
   descarga falla *por completo* al abrir (`zipfile.BadZipFile: File is
   not a zip file`), no de forma parcial — el directorio central de un
   `.zip` vive al final del archivo. Antes esto daba un genérico "está
   corrupto o incompleto"; ahora `preview_zip`/`preview_targz` detectan la
   verdad (`truncated=True` de la descarga) *antes* de intentar parsear y
   dan un mensaje específico apuntando a `download_resource`.
2. Un `.zip` real sin ningún archivo tabular
   (`mag_carbonoorganico_2021junio.zip`: solo `.lyr`/`.tif`/`.tif.aux.xml`,
   paquete GIS raster) hacía que `_pick_member` cayera de vuelta al primer
   archivo del `.zip` y lo forzara al parser de CSV, crasheando con un
   `csv.Error` crudo sin capturar. `_pick_member` ya no cae a "el primero
   que sea"; devuelve `None` cuando ningún miembro parece tabular, y ambos
   previews dan un mensaje claro listando los archivos reales
   encontrados.
3. `_parse_csv_bytes` no capturaba `csv.Error` en absoluto (repro real: un
   `\r` suelto sin comillas dentro de un campo) — ahora se captura y se
   traduce a un `ValueError` accionable en vez de una excepción cruda de
   Python.

### Degradación cuando el portal no responde

**Confirmado y corregido 2026-08-26:** un
`httpx.ConnectTimeout`/`ConnectError` real se puede stringificar como `""`
o `"timed out"`, sin mencionar el host — confirmado con
`str(httpx.ConnectTimeout(...))`. `helpers/ckan_client._fetch_json` ahora
distingue `HTTPStatusError` (ya trae URL+status vía `raise_for_status()`)
de `RequestError` (fallos de conexión/timeout), y en el segundo caso
levanta un `RuntimeError` que sí nombra el host y el tipo de fallo.

---

## Séptima pasada — Superbancos, electricidad, y revisión de fuentes ya integradas

**Investigado 2026-08-29,** pedido de Daniel: escaneo profundo de
Superbancos ("dep scan de todo el material que tienen") más una segunda
mirada a *todas* las fuentes ya integradas como cliente propio (excepto
INEC, ya investigado a fondo) para ver si hay más material del que se
capturó la primera vez — con Registro Civil como ejemplo explícito de algo
que se había dado por "sin gaps" sin mirar más allá de CKAN. Después
Daniel agregó CENACE y el sector eléctrico como dominio nuevo. Todo lo de
abajo se verificó en vivo (fetch real, no solo lectura de un menú).

### Superbancos — el hallazgo más grande de esta pasada

Dominio real y funcionando: `www.superbancos.gob.ec` (no hace falta
redirect, a diferencia de MAATE/SENESCYT/Finanzas). Dos sitios conviven
en el mismo dominio: el institucional (`/bancos/`) y un portal
estadístico separado (`/estadisticas/portalestudios/`, otra instancia
WordPress). Hay además un subdominio `catastrocompanias.superbancos.gob.ec`
(app JSF aparte).

**Boletines Financieros Mensuales — confirmado real, el ítem que ya
estaba en el roadmap.** `estadisticas/portalestudios/bancos/` lista un ZIP
por año desde 1997. Ojo: la URL no sigue una fórmula limpia — el path usa
la carpeta de *fecha de subida* del WordPress, no el año de los datos
(`BOL_FIN_BCOS_2007.zip` vive en `.../2018/03/`, no `.../2019/03/` como
sugeriría un patrón ingenuo) — hay que scrapear la página índice, no
adivinar la URL. Descargas confirmadas: 1997 (5.2 MB), 2007 (6.2 MB), 2008
(6.7 MB), todas `application/zip`, sin login. El boletín del mes/año
actual carga vía un widget AJAX aparte en la misma página (dinámico, no
en la lista estática) — revisar por separado si importa la actualidad.

**Servicios Financieros — hallazgo nuevo, mismo patrón.**
`estadisticas/portalestudios/servicios-financieros/` — ZIPs mensuales de
estadísticas de tarjetas de crédito/débito y de cajeros/oficinas/
corresponsales no bancarios, desde ~2011-2015 según la serie. Confirmado
en vivo: `tarjetas-mar-2021.zip` (1.47 MB). Mismo esquema de URL
(carpeta de fecha de subida) que los boletines financieros.

**Calendario Estadístico — hallazgo menor, útil como índice.** Los links
de "descarga" (`.../download/8970/`, `/9817/`) no son PDF como sugiere la
etiqueta — son XLSX reales (confirmado por `Content-Type`), 93.7 KB. Sirve
como índice legible de qué se publica y cuándo.

**Balances Generales / Patrimonio Técnico / Sistema Financiero Público y
Privado — probablemente el contenido más rico, pero no resuelto.** Estas
tres secciones (que cubren exactamente lo pedido: indicadores de
morosidad/liquidez/solvencia por institución) no son listas de archivos
estáticos — cada página apunta a una herramienta de consulta externa cuya
URL real no apareció en el HTML plano (probablemente cargada por JS o
requiere parámetros de formulario). Necesita una pasada con browser real
antes de saber si es extraíble.

**Resoluciones y Circulares — bloqueado por AJAX, no resuelto.** La
página muestra tres placeholders "Cargando…" que se llenan vía
`admin-ajax.php` (confirmado en el HTML crudo — tokens `ajax`/`iframe`
presentes, página Elementor) — la lista de documentos no está en el HTML
plano. Hace falta el nombre de la acción AJAX/nonce, o un browser, para
enumerar. Relacionado: las resoluciones de la Junta de Política y
Regulación Financiera y Monetaria viven en el sitio del BCE
(`bce.fin.ec/junta-de-politica-y-regulacion-financiera-y-monetaria/resoluciones/`).

**Visualizadores — sospecha de dashboard JS, sin confirmar.** Es un índice
de "reportes dinámicos" (inclusión/uso financiero, protección al
consumidor) — no se encontró iframe/Power BI en el HTML de esta pasada,
pero la etiqueta sugiere que el dashboard real está un click más adentro.
Tratar como sospechoso de SPA hasta verificar con browser.

**Catastro Público / Catastro de Compañías — mixto.** El catastro público
(`bancos/catastro-publico/`) lista bancos por categoría en HTML plano
(nombres solamente, sin metadata), y dice que el detalle completo
(oficinas, representantes legales, directorio, accionistas, auditores)
está en una herramienta interactiva no resuelta. El subdominio separado
`catastrocompanias.superbancos.gob.ec/catastro/` es una **app JSF con
login obligatorio** ("Usuario/Contraseña") — mismo patrón que el
Geoportal del IGM y el registro de títulos de SENESCYT ya documentados
como no automatizables.

**Entidades No Autorizadas — real pero de bajo valor.** Listas por año
(2017-2026, 44-90 nombres/año) de entidades advertidas — solo nombres, sin
fecha ni motivo por entrada, sin archivo descargable. Fácil de scrapear
como HTML si algún día vale la pena, pero poco valor como dato
estructurado.

**Sin datos abiertos ni API.** No hay sección "datos abiertos" en ningún
nav (sitio principal ni portal estadístico), y **Superbancos no tiene
organización en CKAN** (a diferencia de SRI/IESS/SENESCYT).

**Ranking de qué construir primero:** (1) Boletines Financieros Mensuales
+ (2) Servicios Financieros — mismo scraper de página-índice, mismo patrón
ya usado en SIPA; (3) Calendario Estadístico como añadido trivial; (4)
Entidades No Autorizadas / Catastro Público como HTML scrapes de bajo
esfuerzo y bajo valor; (5) Resoluciones y Circulares y (6) Balances
Generales/indicadores necesitan una pasada con browser antes de decidir
si son viables — probablemente lo más valioso del sitio, pero no
verificado; (7) Visualizadores, sospecha de Power BI/JS, despriorizar; (8)
Catastro de Compañías, bloqueado por login, no automatizable.

### Revisión de fuentes ya integradas — ¿qué más tienen?

**SRI — un gap real más allá de `/datasets`.**
`sri.gob.ec/estadisticas-generales-de-recaudacion-sri` es una página de
"Estadísticas de Recaudación" separada de `/datasets` (ya cubierta por
`helpers/sri_client.py`): reportes XLSX mensuales pre-agregados por
impuesto/provincia/cantón y por actividad económica, actualizados cada
mes (verificado con la edición de julio 2026), más una "Bitácora de
control y registro estadístico", un ZIP de indicadores históricos (2025),
boletín técnico anual en PDF, e infografías. Es un nivel de agregación
distinto (resumen geográfico/sectorial) al de los CSV de declaración cruda
por año que ya scrapea `/datasets` — no es un duplicado.
`sri.gob.ec/estudios-investigaciones-e-indicadores` es otro hub aparte,
pero todo en PDF (gasto tributario, presión fiscal, brechas tributarias,
radiografía económica) — necesitaría extracción de PDF, no CSV. Hay
también un portal OLAP en vivo (`srienlinea.sri.gob.ec/saiku-ui`) — no es
una fuente de datos para este proyecto, ver notas de la sesión
2026-08-31 fuera de este repositorio.

**BCE — el IEM es más rico de lo que decía el roadmap.** Confirmado en
vivo: cada boletín mensual del IEM (índice completo desde el No. 1727 de
enero 1996 hasta el No. 2092 de junio 2026 — 30 años de archivo) tiene, además
del ZIP/PDF completo, **~60+ archivos XLSX individuales por tabla**
(`IEM-XXX-e.xlsx`, ej. `IEM-431-e.xlsx` = PIB por enfoque del gasto,
confirmado descargando uno real de 100 KB). Cubre balanza de pagos,
posición de inversión internacional, deuda externa, PIB por los tres
enfoques, previsiones macroeconómicas — series mucho más granulares que
las ~78 que expone BCEData hoy. Candidato fuerte para scrapear tabla por
tabla en vez de solo el ZIP monolítico. Ojo: el índice del boletín de
junio 2026 apuntaba todavía a la carpeta de mayo — puede ser rezago de
publicación o plantilla desactualizada, revisar antes de construir sobre
ello. Aparte, BCE tiene una organización CKAN con solo 4 datasets
(espejo rezagado de un subconjunto del IEM) — ya alcanzable con los tools
genéricos existentes, sin valor agregado.

**Supercías — casi todo lo demás es un callejón sin salida.** El Anuario
Estadístico de Mercado de Valores dejó de publicarse en 2015 (no es una
fuente viva). Valores y Seguros (que esta superintendencia también
regula desde 2015) son dominios reales pero casi todo vive detrás de apps
ZK/JSF con login obligatorio (`appscvsmovil`, `seguros.supercias.gob.ec`).
Único archivo estático encontrado: un PDF de reaseguradores extranjeros
registrados, actualizado (junio 2026), sin poder enumerar archivos
hermanos (el listado de carpeta da 403). Sanciones/resoluciones existen
como sistema real pero vía apps ZK con ViewState — mismo tipo de fricción
que BIINEC, que este proyecto sí llegó a scrapear, pero no es un quick
win.

**SERCOP — nada nuevo aprovechable, con una pregunta abierta.** RUP es
solo FAQ. "Contratación Pública en Cifras" es un PDF estático + un
dashboard Power BI embebido. El catálogo electrónico es navegable pero
sin precios ni API. La consulta de órdenes de compra del catálogo está
bloqueada por **CAPTCHA** — descartado. La única pista real: un formulario
legado (`EmpReporteIncumplidos.cpe`, sistema SOCE viejo) para consultar
proveedores incumplidos/adjudicatarios fallidos — dato que no existe en
los registros OCDS ya integrados — pero no se probó si acepta POST sin
sesión/captcha; queda como pregunta abierta, no confirmado ni descartado.

**SGR — hay un archivo histórico real fuera del snapshot ArcGIS ya
integrado.** El sitio principal (`gestionderiesgos.gob.ec`, WordPress,
separado del backend ArcGIS que ya usa `helpers/sgr_client.py`) tiene un
archivo de "Informes de Situación" (SITREP) 2016-2026 — terremotos,
incendios forestales, temporada de lluvias, actividad volcánica — y una
"Biblioteca" con mapas de amenaza/vulnerabilidad, rutas de evacuación por
tsunami, y planes de contingencia volcánica por cantón. Contenido real,
multi-año, no tocado por el snapshot COE2 actual (que solo tiene eventos
recientes/en curso). Formato exacto por confirmar en una pasada
siguiente.

**IG-EPN — la data profunda está bloqueada, pero hay un buscador de
boletines que parece abierto.** `igepn.edu.ec/descarga-de-datos` (catálogos
sísmicos completos, registros acelerográficos, mecanismos focales, mapas
de amenaza volcánica por volcán) **requiere crear cuenta/login** — mismo
patrón que el Geoportal del IGM, descartado. Pero
`igepn.edu.ec/servicios/busqueda-informes` es un formulario de búsqueda
real (confirmado interactuando con él) para el archivo de informes
sísmicos y volcánicos, filtrable por tipo/volcán/fecha, **sin login
visible** — el candidato más prometedor de esta pasada para IG-EPN,
formato de resultado (PDF vs. página) sin confirmar todavía. También hay
un catálogo histórico "Sismicidad Tectónica de 1587 a 2021" bajo "Mapas
Interactivos", no explorado a fondo.

**gob.ec — un endpoint de transparencia real y sin explotar.**
`www.gob.ec/api/v1/tramites-transparencia/{tramite_id}` devuelve una
serie mensual real (atenciones/quejas por trámite) desde 2021, en vivo,
sin auth (confirmado con el trámite de Cédula de Identidad: 63 meses de
serie, mayo 2021 → julio 2026, con 253,729 atenciones / 6 quejas en el mes
más reciente). No es un dataset masivo — hay que
pedirlo trámite por trámite, no existe un endpoint masivo — pero es dato
de uso/satisfacción real que hoy no expone ningún tool. El resto de la
API (`tramites-canales`, `tramites-costo`, `tramites-categorias`,
`retroalimentacion`, `planificacion-estado`) o ya está embebido en lo que
`get_tramite_info` devuelve, o es de bajo valor. El "catálogo de datos
abiertos" en la home de gob.ec resulta ser solo un link directo a la
misma CKAN de `datosabiertos.gob.ec` que este proyecto ya integra por
separado — no hay catálogo propio escondido.

**ANDA — cobertura confirmada completa, sin gap.** El catálogo en vivo
tiene 437 entradas, coincide exacto con lo que ya documenta
`search_anda`. Hay facetas de UI (colección temática, rango de año) no
expuestas como parámetro de búsqueda hoy, pero es una limitación de UX
menor (no se puede filtrar por tema del lado del servidor), no un gap de
cobertura — nada es inalcanzable, solo no filtrable por tema.

**SIPA — más boletines reales, un geoportal más rico de lo pensado, y dos
dashboards confirmados rotos.** "Cifras Agroproductivas"/"Cifras
Territoriales" (los tableros dinámicos mencionados en la integración
original) están **confirmados rotos en producción** — cero peticiones de
red se disparan en 8+ segundos de observación, no es JS-renderizado-pero-
alcanzable, simplemente no cargan nada. Ídem se sospecha (no verificado
uno por uno) del resto de tableros bajo la misma sección (Indicadores
Sectoriales, Soberanía Alimentaria, Seguro Agropecuario, etc.). En
cambio, los "Boletines nacionales" (Panorama Agroestadístico, Precios
Mayoristas/Internacionales/Productor, Comercio Exterior,
Agroquímicos/Fertilizantes, Crédito Público/Privado) sí son PDFs
mensuales reales y directos (`sipa.agricultura.gob.ec/boletines/.../pdf`,
confirmado 2016-2026 para Panorama Agroestadístico), y los "Boletines
Situacionales" (por provincia/cultivo/sector) existen con el mismo
patrón de sitio. El "Panorama Agroeconómico" anual está atrapado en un
flipbook JS, sin link directo a PDF encontrado. El hallazgo más grande:
`geoportal.agricultura.gob.ec` (solo `http://`, `https://` no carga —
brecha real de protocolo) corre un **backend GeoServer WMS completo** con
workspaces reales (`registros`, `demarcacion`, `infraestructura`,
`tematicas`, `cobertura`, `fisiografia`, `sigtierras` — incluyendo
**catastro rural** —, `agroestadistica` con riesgos agroclimáticos) mucho
más allá de las ortofotos ya anotadas — pero falta confirmar si expone
WFS `GetFeature` (necesario para exportar datos vectoriales reales, no
solo teselas de mapa). RENAGRO-EC es solo una página informativa, sin
dato ni descarga.

**Contraloría — un ítem casi gratis, uno bloqueado por verificación de
identidad, uno inalcanzable por ahora.** "Plan anual de control" usa el
**mismo patrón `WFDescarga.aspx?id={id}&tipo=doc`** ya implementado en
`helpers/contraloria_client.py` (ahí con `tipo=pesdoc`) — IDs confirmados
para 2025 (`id=2812`) y 2024 (`id=2775`) — esfuerzo casi nulo, mismo
cliente ya sirve. "Consulta de declaraciones patrimoniales" es un lookup
real por funcionario, pero está detrás de verificación de identidad
(cédula + email + código enviado al correo) antes de mostrar resultados —
mismo tipo de brecha estructural que `radiografiapolitica.org` (que sí
tiene bulk export vía JSON, esta versión de Contraloría no). "Resoluciones
confirmadas" vive en un subdominio distinto
(`servicios.contraloria.gob.ec`) que falló las 3 veces que se intentó
alcanzar (mientras `www.contraloria.gob.ec` respondía sin problema) — falla
de conectividad/SSL real en ese subdominio específico, vale la pena
reintentar más adelante en vez de descartarlo. "Órdenes de trabajo" es
alcanzable pero es un formulario HTML con un dropdown de cientos de
unidades de control — más fricción que el CSV de un solo click ya
integrado, mecanismo de envío (GET simple vs. ASP.NET postback) sin
confirmar.

**Registro Civil — el "sin gaps" del roadmap era incorrecto.** La primera
conclusión ("cobertura sólida vía CKAN, sin gaps") se basaba solo en
revisar la organización CKAN (6 datasets: cedulación, pasaportes
electrónicos, copias de actas, certificados de agencia, catálogo de
agencias, certificados de firma electrónica) sin mirar el sitio propio de
la institución. `registrocivil.gob.ec/registro-civil-del-ecuador-cifras-
de-defunciones/` publica un dataset real a nivel de registro individual:
**"Defunciones Generales" 2020-05-2025, archivo `.xlsb` de 9.3 MB**
(confirmado por HEAD: `Content-Type:
application/vnd.ms-excel.sheet.binary.macroEnabled.12`,
`Last-Modified: 2025-05-12`), acompañado de un diccionario de variables y
una ficha de metadatos — tratado como una publicación de datos formal, no
un boletín de prensa. No está en ninguno de los 6 datasets CKAN
(confirmado consultando la API de CKAN en vivo). Distinto de lo que INEC
ya publica (matrimonios/divorcios anuales *agregados*, 2022-2024) — esto
es defunciones, a nivel de registro individual, publicado por el propio
Registro Civil. **Corrección pendiente en ROADMAP.md.** Nota técnica: el
formato `.xlsb` (Excel Binary Workbook) no está soportado hoy por
`helpers/csv_reader.py` (que maneja XLSX/XLS/ODS pero no XLSB) — haría
falta agregar soporte para ese formato antes de poder previsualizarlo
como tabla, o como mínimo exponerlo como descarga directa igual que SIPA
hace con archivos grandes.

### Sector eléctrico (CENACE, ARCONEL/ARCERNNR, Ministerio de
Ambiente y Energía) — dominio completamente nuevo para el proyecto

**Pedido explícito de Daniel** tras el escaneo de fuentes ya integradas.
Sin ninguna mención previa en este documento.

**CENACE** (Operador Nacional de Electricidad) — dominio real
`cenace.gob.ec` (no `.org.ec`). **Ya tiene organización en CKAN** (`cenace`,
**45 datasets**: producción del parque generador, potencia efectiva,
exportaciones de energía, potencia despachada, actualizado hasta agosto
2026) — alcanzable hoy con los tools genéricos, sin necesidad de cliente
nuevo para eso. Aparte, un dashboard en tiempo real
(`cenace.gob.ec/info-operativa/InformacionOperativa.htm`) con 5 pestañas
(producción/demanda en tiempo real, diaria, acumulada mensual/anual) —
confirmado que **los datos vienen embebidos como JSON de Plotly
(`Plotly.newPlot(...)`) directo en el HTML**, sin llamada a API separada,
extraíble con regex, sin login — pero "Acumulada Anual" solo muestra el
año en curso, el histórico profundo vive en los datasets CKAN. El
Boletín/Estadística Mensual de Transacciones Comerciales (costos
marginales, enero 2019 - junio 2026) está atrapado en un flipbook
FlipHTML5 de terceros — mismo tipo de fricción que otros embeds JS ya
documentados, sin archivo estático encontrado.

**ARCONEL/ARCERNNR** — el sitio en vivo sigue en `arconel.gob.ec` y
sigue branding "Agencia de Regulación y Control de Electricidad";
`arcernnr.gob.ec` no resuelve — la fusión/renombre a ARCERNNR (Energía y
Recursos Naturales No Renovables) existe a nivel legal/institucional pero
el dominio operativo no cambió. **Ya tiene organización CKAN** (slug largo
`agencia-de-regulacion-y-control-de-energia-y-recursos-naturales-no-
renovables`, 1 dataset: Balance Nacional de Energía Eléctrica en ODS/XLS/
CSV, actualizado agosto 2025) — alcanzable ya. Más allá de eso, archivos
estáticos reales confirmados en el patrón WordPress
`wp-content/uploads/downloads/YYYY/MM/` ya visto en otros ministerios:
BNEE mensual en XLS, "Cobertura 2015-2024" en un solo XLSX, anuarios
estadísticos del sector eléctrico 2011-2025 en PDF (detrás de un
acordeón por año). El hallazgo más profundo:
**`reportes.arconel.gob.ec`**, un sistema de reportes parametrizados (por
parroquia: medidores/facturación/subsidio Tarifa Dignidad; por
infraestructura: centrales/transformadores/líneas; transacciones: balance
de energía/pérdidas; indicadores: reclamos/calidad de servicio) con
**selector de año 1998-2026** — la fuente más profunda y granular
encontrada en todo el sector, pero es una app ASP.NET WebForms +
SSRS ReportViewer (`__VIEWSTATE`/`__EVENTVALIDATION`), necesita un flujo
de scraping por POST de formulario, no un GET simple — sin login, pero
con fricción técnica real. "Pérdidas de energía eléctrica por
distribuidora" está en un dashboard Power BI embebido — mismo patrón de
fricción visto en Contratación Pública/ASOBANCA. `sisdatbi.arconel.gob.ec`
existe (nombre sugiere otro dashboard BI) — no explorado a fondo, marcar
para una pasada futura. `arconel.gob.ec/tarifas-del-sector-electrico/`
dio 403 a un fetch simple pero cargó bien en browser real — probable
filtro de User-Agent, no un bloqueo real; un scraper necesitaría headers
realistas.

**Balance Energético Nacional (BEN)** — el antiguo Ministerio de
Electricidad y Energía Renovable ya no existe como sitio propio
(`historico.energia.gob.ec` es un remanente archivado, claramente
etiquetado como histórico); la competencia se fusionó al actual
Ministerio de Ambiente y Energía
(`ambienteyenergia.gob.ec`/`recursosyenergia.gob.ec`, ambos activos y
sirviendo el mismo ministerio fusionado — confirma y extiende el hallazgo
ya anotado sobre MAATE en la investigación de dominios perdidos). El BEN
(balance energético nacional, todas las fuentes de energía, no solo
electricidad) se publica como PDFs directos por capítulo
(`ambienteyenergia.gob.ec/wp-content/uploads/.../BEN_24-CAPITULO_N.pdf`),
con archivo histórico desde 2012 — mismo patrón WordPress ya visto en
otros ministerios, pero en PDF (necesitaría extracción de texto/tablas,
no CSV/XLSX directo).

**Ranking de qué construir primero en electricidad:** (1) archivos
estáticos sin fricción — BNEE mensual XLS de ARCONEL, Cobertura XLSX,
anuarios PDF, más los datasets CKAN de CENACE/ARCONEL que ya son
alcanzables hoy sin código nuevo; (2) dashboard en tiempo real de CENACE
(JSON de Plotly embebido, extraíble pero solo año en curso) y
`reportes.arconel.gob.ec` (1998-2026 de profundidad, pero formulario
ASP.NET postback, más esfuerzo); (3) boletín de transacciones de CENACE
(flipbook) y pérdidas de energía (Power BI) — baja prioridad, mismo tipo
de fricción JS ya visto repetidamente en este proyecto. Ningún bloqueo
por login/captcha se encontró en todo el sector — toda la fricción es de
renderizado JS o formularios ASP.NET, no de autenticación.

---

## Octava pasada — Trabajo/SUT, electricidad a fondo, CNT/ARCOTEL, archivo de cortes 2024, endpoints muertos

**Investigado 2026-08-29 (misma fecha, tercera pasada del día),** pedido
de Daniel: Ministerio del Trabajo/SUT, profundizar más el sector
eléctrico ("cenace arconel y similares"), CNT/telefonía, un archivo real
de los cortes de luz programados de la crisis de fines de 2024 (nivel
barrio/semana), y un barrido de endpoints "muertos" o renombrados sin
avisar entre ministerios/Presidencia/Vicepresidencia/Asamblea/Judicatura/
TCE. Todo verificado en vivo.

### Ministerio del Trabajo / SUT — sin gap, ya cubierto vía CKAN

El SUT (`sut.trabajo.gob.ec`, app JSF con dashboards públicos de
indicadores) es la **fuente declarada** de los 5 datasets que ya existen
bajo la organización CKAN `ministerio-del-trabajo` (verificado en vivo vía
`get_dataset_info`): Contratos Vigentes en el SUT (CSV, actualizado
2026-08-17), tres CSV de Red Socio Empleo (registrados/colocados/
capacitados), Estrategias para la Empleabilidad, Denuncias del Sector
Público, y Servidores Públicos Registrados (SIITH). Todo CSV/ODS
estático, ya alcanzable con `search_datasets`/`download_resource`. **No
hace falta ningún cliente nuevo.**

**Patrón nuevo de falla, distinto al de dominio renombrado:**
`www.trabajo.gob.ec` resuelve y acepta la conexión TCP, pero sus páginas
dinámicas (home, `/salario-basico/`, `/tablas-sectoriales/`) **nunca
responden** — timeout de 45s+ sin datos, confirmado repetidas veces con
WebFetch y curl crudo. En cambio, archivos estáticos bajo
`/wp-content/uploads/...` cargan rápido y confiable (1.2-1.8s). Conclusión
práctica: el sitio solo sirve para bajar un PDF específico ya conocido
(vía buscador), no para navegar/scrapear su propio menú.

**Dead ends confirmados:** registro de organizaciones sindicales (trámite
presencial/Quipux, sin registro público agregable), inspecciones
laborales/sanciones (notificación individual por caso, mismo patrón que
Fiscalía ya documentado como fuera de alcance), Consejo Nacional de
Salarios (`consejosalarios.gob.ec` no resuelve, NXDOMAIN), tablas
salariales sectoriales (PDFs sueltos con URLs impredecibles, sin tabla
2026 publicada según cobertura de prensa — el ministerio simplemente no
actualizó). Las cifras de empleo/desempleo que aparecen en PDFs del
ministerio son downstream de la ENEMDU de INEC, no una encuesta propia —
confirma que es un duplicado, no un gap.

**Pasada adicional 2026-08-30 (pedido explícito de Daniel: profundizar
más allá de CKAN sobre `sut.trabajo.gob.ec` mismo, no solo confirmar que
es "la fuente declarada").** Se navegó en vivo el propio portal SUT (app
JSF, `/mrl/contenido/...`) en vez de solo leer los metadatos de CKAN.
Las 8 páginas de "Indicadores" del menú
(`indiContratos`, `indiDenunciasPublico`, `indiEstrategiasEmpleabilidad`,
`indiCapacitacionCertificacion`, `indiEncuentraEmpleo`,
`indiEncuestaDemandaLaboral`, `indiPlanNacionalDesarrollo`,
`indiSentencia`) son, sin excepción, un iframe embebido de Power BI
público (`app.powerbi.com/view?r=...`) — visualización interactiva, no
tabla exportable ni CSV/API detrás del embed. Los tres nombres que
corresponden 1:1 a datasets CKAN existentes (Contratos, Denuncias del
Sector Público, Estrategias de Empleabilidad) confirman que el dashboard
visualiza el mismo dato que ya se exporta a CKAN, no uno adicional.
`indiEncuestaDemandaLaboral` e `indiPlanNacionalDesarrollo` son los únicos
nombres sin equivalente CKAN evidente, pero también son solo Power BI —
sin exportación posible sin las credenciales/API del propio Power BI
(mismo patrón ya descartado para Centrosur). Las páginas `mediacion.xhtml`
e `instituciones.xhtml` (sin nombre CKAN equivalente) no tienen iframe
pero tampoco contenido tabular estático — cascarón JS vacío en la
respuesta cruda. `desarrollohumano.gob.ec` (el dominio nuevo de
MIES-fusionado ya anotado en la Séptima pasada) sigue sin responder
—mismo timeout de hosting compartido confirmado de nuevo, no es un
problema transitorio—, así que su portal "InfoDH" sigue sin poder
auditarse.

**CORRECCIÓN el mismo 2026-08-30: la conclusión de arriba ("sin gap,
mismo dato que CKAN") era incorrecta — Daniel preguntó explícitamente
"do we have monthly level SUT contratos by industry" y la respuesta
correcta es no, no con lo ya integrado.** El error: solo se miró la URL
del iframe (`app.powerbi.com/view?r=...`) sin abrir el dashboard real. Al
abrirlo en un browser (`indiContratos` → "Contratos MDT v1"), la página 2
de 3 ("Evolución mensual y acumulada de contratos") tiene una serie
**mensual real desde enero 2015 hasta el mes vigente**, confirmada
extrayendo la tabla subyacente vía el menú contextual "Show as a table"
del propio Power BI (clic derecho sobre la visualización → grilla real
`Año, Mes | Cantidad de Contratos`, ej. 2015-ene: 92,306; 2015-feb:
55,571; ...). La página 1 tiene filtros compuestos: rango de fechas
(Desde/Hasta), grupo etario, Rama de actividad (CIIU), provincia y
cantón, género, estado del contrato (Vigente/Finalizado) y discapacidad
— es decir, la fuente real sí tiene profundidad mensual y por industria,
simplemente no está expuesta así en CKAN.

El recurso CKAN `mdt_contratosvigentessistemaunicotrabajo_2026Agosto`
(mismo resource_id desde 2021, sobreescrito cada mes) es solo una
**foto del stock de contratos "Vigentes" al momento de la consulta** —
sin columna de fecha ni historia — desagregada por género/provincia/tipo
de contrato/rama de actividad, pero de un solo corte temporal. El
dashboard Power BI, en cambio, cubre **Vigente + Finalizado** desde 2015,
es decir contratos históricos que el CSV de "vigentes" nunca mostró.

**No resuelto:** extraer esto como serie estructurada (mes × industria)
requeriría automatizar el propio embed de Power BI — aplicar el filtro
"Rama de actividad" por cada categoría y leer la tabla subyacente vía
"Show as a table" para cada una (o encontrar el endpoint `querydata`
interno que arma esas tablas; no capturado en esta pasada, la
inspección de red del browser solo registró la carga inicial del
reporte, no las llamadas posteriores a interacciones). Mismo nivel de
dificultad que el widget OneDrive de Superbancos — no es scraping HTML
estático, es automatizar un cliente de BI. Pendiente como ítem propio en
ROADMAP.md, no como "sin gap".

### Sector eléctrico — segunda pasada, mucho más profunda

**CNEL EP tiene 40 datasets en CKAN** (org `cnel-ep`, verificado vía la
API del propio MCP desplegado del proyecto) — no los 5 que mostraba una
vista filtrada. Cubre facturación/venta de energía (MWh+USD),
infraestructura eléctrica, reclamos, expansión de alumbrado público,
información financiera/contable, actas de directorio, trámites
ciudadanos. Es, con diferencia, la mejor fuente del lado distribución —
ya alcanzable hoy sin código nuevo.

**`reportes.arconel.gob.ec` — descifrado.** La pasada anterior lo dejó
como "necesita browser". Esta vez se llegó al mecanismo completo: es
ASP.NET WebForms con un control **Microsoft ReportViewer 11.0.3452.0**.
Cada dropdown (Tipo de Reporte / Año / Grupo Empresa) dispara su propio
`__doPostBack` → POST AJAX a un `UpdatePanel` con `__VIEWSTATE` fresco;
hay que enviarlos **secuencialmente** (uno invalida el estado del
siguiente, no se pueden mandar en paralelo). Después de fijar los tres,
"Generar Reporte" renderiza el reporte SSRS como una **tabla HTML real en
el DOM** — no hace falta tocar el export. Verificado de punta a punta en
vivo: Tipo=`Balance Energía`, Año=2023, Grupo=`Todos` → tabla mensual real
(Id Empresa, Empresa, Año, Mes, Energía Recibida MEM MWh, Recibida de
Terceros...) para cada distribuidora, paginada. El dropdown de exportar
(Excel/PDF/Word) existe pero sus links son `javascript:void(0)` — dispara
otro postback completo, no hay atajo de URL estática tipo
`&rs:Format=EXCEL`. Un scraper necesita: `requests.Session()`, GET para
sembrar `__VIEWSTATE`/`__EVENTVALIDATION`, tres POST secuenciales
imitando cada `onchange`, POST del botón generar, parsear la tabla HTML.
La matriz es grande (~30 tipos de reporte × 29 años × 3 filtros de grupo,
algunos también piden mes) pero cada celda es dato limpio, cero login/
captcha. **Sigue siendo la fuente más rica de todo el proyecto, y ahora
está resuelta técnicamente, solo falta construirla.**
`sisdatbi.arconel.gob.ec` resultó ser un sistema BI interno **con login**
(`sisdat.soporte@controlelectrico.gob.ec`) — sistema distinto, no una
puerta alterna a los reportes públicos, descartar.

**CENACE — Biblioteca revela documentos de planificación no
documentados antes:** Plan Maestro de Electricidad 2023-2032 (link roto
por mismatch de certificado TLS — el host `recursosyenergia.gob.ec` no
está en el SAN del certificado que sí cubre `ambienteyenergia.gob.ec` y
~25 ministerios más; reintentar bajo `www.ambienteyenergia.gob.ec`
directamente), Planes Operativos Anuales 2016-2026, Plan Estratégico
Institucional 2015-2029, factores de emisión CO₂ 2011-2024, informes
semestrales de indisponibilidad de transmisión 2018-2026. También un
índice pequeño y útil: `cenace.gob.ec/wp-content/plugins/ez-addons/
data/boletines.xlsx` (14 KB) mapea cada boletín mensual (ene-2019 a hoy)
a su link individual de `fliphtml5.com` — sirve para enumerar los ~90
boletines programáticamente, pero no resuelve la fricción del flipbook
por boletín. Confirmado de nuevo (esta vez inspeccionando la red del
browser durante la carga): el dashboard en tiempo real no dispara **ni
una sola petición XHR/JSON** — los datos están en el HTML servido por el
servidor, ni siquiera es "Plotly JSON embebido", es más directo que eso.

**Otras organizaciones CKAN nuevas encontradas en el sector:** ARCERNNR
(BNEE) es en realidad **1 dataset pero 54 recursos** — más rico de lo que
sugería "1 dataset". **IIGE** (Instituto de Investigación Geológico y
Energético), org `instituto-de-investigacion-geologico-y-energetico-iige`,
**19 datasets** — investigación geológica/energética y portafolios de
patentes, tangencial pero real, no catalogada antes. **Ministerio de
Energía y Minas** (org separada, `ministerio-de-energia`, 14 datasets) es
data **legacy de petróleo/minería** (precios de crudo, perforación de
pozos) — no confundir con el ministerio fusionado de Ambiente y Energía
que cubre electricidad hoy.

**Distribuidoras sin presencia CKAN propia:** EEQ, Centrosur, EERSA,
EEASA — cero. EEQ tiene "EEQ en Cifras" pero es solo prosa/HTML (99.30%
cobertura, 1.25M cuentas), sin archivo descargable. Centrosur
(`centrosur.gob.ec/estadisticas-centrosur/`) sí tiene 2 PDFs reales
(`Estadistica-2023.pdf`, `Informacion_pagina_web_2025_3T.pdf`) más un
Power BI de generación distribuida (mismo patrón de fricción ya visto en
ASOBANCA/SERCOP) y un geoportal ArcGIS. EERSA dio 403 a un fetch simple
(posible filtro de User-Agent, sin confirmar con browser real). EEASA sin
explorar más allá del redirect. **Tarifa de la Dignidad**: no hay dataset
estructurado en el ministerio fusionado — la fuente estructurada real es
el reporte "Subsidio Tarifa Dignidad" (por parroquia/año/mes) dentro de
`reportes.arconel.gob.ec`, no un archivo separado del MAE.

**Ranking actualizado:** (1) `reportes.arconel.gob.ec` — descifrado,
máxima profundidad histórica (1998-2026), necesita un scraper con replay
de ViewState; (2) los datasets CKAN ya vivos — CNEL EP (40), CENACE (45),
ARCONEL BNEE (54 recursos); (3) PDFs estáticos de Centrosur/CNEL y los
documentos de planificación de la Biblioteca de CENACE (Plan Maestro,
indisponibilidad, factores CO₂); (4) geoportales/Power BI de EEQ/
Centrosur, misma fricción JS de siempre, baja prioridad; (5)
`sisdatbi.arconel.gob.ec`, login-gated, descartar. Ningún bloqueo por
login/captcha en todo el sector excepto ese último — toda la fricción
sigue siendo renderizado JS o formularios ASP.NET postback, no
autenticación.

### CNT / ARCOTEL (telecomunicaciones) — dominio nuevo

**ARCOTEL** ya tiene organización CKAN (`arcotel`, 9 datasets CSV/ODS:
líneas activas por tecnología, densidad/participación de mercado,
portabilidad numérica, internet fijo/móvil, TV paga, cable submarino,
satélite) — pero **congelada desde nov-2021/nov-2022**, sin recursos
nuevos desde entonces (gap de frescura, no de existencia). El hallazgo
real está en el sitio institucional (`www.arcotel.gob.ec`, fuera de
CKAN): **Reportes Estadísticos Mensuales** (`/reportes-estadisticos-
mensuales/`), PDF, serie mensual completa 2023-2026 con ~4 meses de
rezago (el más actual y accionable), y **Boletines Estadísticos**
(anuales, hasta 2015). Ambos solo PDF, sin CSV/XLSX ni API, sin login/
captcha. **CNT EP** (dominio comercial real es `cnt.com.ec`, no
`cnt.gob.ec`) tiene su propia organización CKAN (`cntep`, solo 2 datasets
pero frescos, feb-2026: ubicaciones de centros de atención, cobertura
móvil por provincia) — como operador comercial (aunque estatal) publica
mucho menos que el regulador, como se esperaba. Portal LOTAIP de CNT no
se pudo verificar (parece SPA/JS, WebFetch devolvió vacío). Sin API
abierta en ninguno de los dos.

### Archivo histórico de cortes de luz programados (crisis sep-dic 2024)

**Pedido explícito de Daniel:** un registro estructurado real (barrio ×
semana × horas sin luz) de la crisis eléctrica de fines de 2024. Este es
un tipo de dato distinto a todo lo demás en este documento — no es una
fuente que se publique continuamente, es un incidente histórico que hay
que rescatar antes de que desaparezca.

**EEQ (Quito) — el hallazgo grande: el archivo sigue vivo, no hace falta
Wayback Machine.** El CMS documental de EEQ
(`eeq.com.ec/documents/d/empresa-electrica-quito/{slug}`) **todavía sirve
los PDFs de la crisis en vivo**, confirmado descargando uno real:
`.../04-al-06-oct` — PDF de 5 páginas, "Programación cortes del servicio
de energía eléctrica," viernes 4 a domingo 6 de octubre de 2024,
estructura exacta subestación → lista exhaustiva de calles/sectores →
bloque horario (ej. `04:00-08:00 / 18:00-19:00`). Exactamente la
granularidad barrio/hora pedida. Otros slugs confirmados existentes:
`23-al-29-09-24`, `26-04-2024`, `29_04_2024`, `mf-09-10-nov` (abril a
noviembre 2024). **Problema:** el naming de los slugs es manual e
inconsistente, no hay patrón de fecha predecible — hay que enumerarlos
vía búsqueda (Google `site:eeq.com.ec/documents`, o una API de búsqueda
del propio CMS si existe) en vez de adivinar URLs. Un espejo de tercero
(`ecuador221.com.ec`, un medio local) también aloja copias de al menos un
PDF (29 nov - 1 dic 2024) — útil como respaldo si algún slug de EEQ no es
descubrible. Los PDFs están además co-marcados "Ministerio de Energía y
Minas" — vale la pena revisar si el ministerio también los espeja en su
propio sitio.

**CNEL (Guayaquil/costa, el objetivo más grande y más difícil) —
probablemente perdido del sitio en vivo.** El archivo por tag
(`/tag/corte-de-energia/`) hoy solo muestra artículos de 2026, nada de
2024 — la página fue sobrescrita. CNEL usa el mismo patrón WordPress
`wp-content/uploads/{año}/{mes}/` que EEQ para otros documentos actuales,
así que los PDFs de sep-dic 2024 podrían seguir en rutas adivinables
`wp-content/uploads/2024/09-12/...` — no confirmado, vale una pasada
dirigida. CNEL también publicó links cortos (t.co) desde su cuenta
oficial de X con PDFs separados por "Unidad de Negocio" (provincia) —
no se pudieron resolver (X devolvió 402, paywall).

**CENACE/ARCONEL — como se esperaba, solo la capa regulatoria/de
coordinación, no horarios por barrio.** ARCONEL emitió la Resolución
006/2024 (8-sep-2024, marco técnico-comercial para generadores de
emergencia bajo racionamiento); CENACE determinó y comunicó los períodos
de déficit/racionamiento a nivel de sistema (vigente desde 16-oct-2023)
pero delegó a cada distribuidora decidir quién pierde luz cuándo. Nada
que rescatar aquí más allá de lo ya documentado.

**Wayback Machine — no disponible en esta sesión** (web.archive.org
devolvió "Temporarily Offline" tanto a fetch directo como a browser) —
una caída real del servicio, no un bloqueo. Baja prioridad reintentar
dado que el archivo de EEQ ya cubre el período sin necesidad de archive;
más relevante para CNEL una vez que el servicio vuelva.

**Prensa (Primicias, La República "Datos LR")** cubrió el período casi a
diario, pero republicando los mismos PDFs de CNEL/EEQ en prosa, sin
construir su propio tracker estructurado — confirma el formato de tabla
PDF pero no aporta dato independiente.

**Conclusión:** esto es más rescatable de lo esperado. EEQ es el caso
fuerte (archivo en vivo, sin arqueología necesaria); CNEL es el caso
difícil (probablemente hay que combinar reintento de Wayback + adivinar
rutas de upload + rescatar los links de X). Vale la pena tratarlo como un
ítem de roadmap distinto al del sector eléctrico general — es un registro
de un incidente histórico, no una fuente de datos continua.

### Barrido de endpoints muertos o renombrados sin avisar

**Pedido explícito de Daniel,** extendiendo el patrón ya documentado
varias veces (SENESCYT→MINEDEC, Finanzas→MDEP, MAATE hijackeado por
SNAI, MIDUVI muerto a nivel TLS, `industrias.gob.ec` sin DNS) a
instituciones no auditadas individualmente todavía: ministerios
restantes, Presidencia, Vicepresidencia, Asamblea Nacional (sitio propio),
Consejo de la Judicatura, TCE.

**Dos renombres nuevos confirmados, ambos vía falla TLS (no redirect):**

- **Transporte y Obras Públicas → MIT.** `obraspublicas.gob.ec` muere por
  mismatch de certificado (host no está en el SAN del servidor). Sucesor
  real: `mit.gob.ec`, "Ministerio de Infraestructura y Tecnología",
  confirmado vivo, referencia explícitamente su branding anterior de
  "Transporte y Obras Públicas".
- **MIES → fusionado en "Ministerio de Trabajo y Desarrollo Humano".**
  `inclusion.gob.ec` muere por certificado expirado; `mies.gob.ec` ni
  siquiera resuelve. Sucesor real: `www.desarrollohumano.gob.ec`,
  confirmado vivo, referencia a MIES directamente, y tiene un **"InfoDH"
  — Portal de Información Estadística** sin explorar todavía (pendiente
  de pasada de contenido).

**Un redirect nuevo, correcto (no es el bug de vhost por defecto):**
Planificación (`planificacion.gob.ec`) → 301 a
`planificacion.presidencia.gob.ec` ("Ex Secretaría Nacional de
Planificación"), portal LOTAIP real con matrices mensuales por año
(presupuestos, personal, contratos, auditorías).

**Confirmación directa del bug de hosting compartido, por primera vez
sin inferencia:** el error de certificado de `obraspublicas.gob.ec` filtró
la lista completa de SAN del certificado compartido. Dominios que
comparten ese certificado (todos bajo `www.<nombre>.gob.ec`):
agricultura, ambienteyenergia, atencionintegral (SNAI), codigopostal,
comunicacion, consejodiscapacidades, controlsanitario, defensa,
desarrollohumano, economiasolidaria, finanzas, geoenergia,
gestionderiesgos, gobiernoabierto, igualdad, igualdadgenero,
ministeriodegobierno, ministeriodelinterior, **mit**, presidencia,
produccion, salud, secretariadelamazonia, softwarepublico,
telecomunicaciones, vicepresidencia. Nota: `obraspublicas` y `mies`/
`inclusion` **no** están en esa lista aunque sus instituciones siguen
operando bajo otro nombre (`mit`, `desarrollohumano`) — es decir, los
dominios viejos simplemente se sacaron del certificado compartido en vez
de redirigirse, por eso fallan en el TLS handshake en lugar de servir
contenido equivocado como los casos de hijack de SNAI.

**Todo lo demás confirmado vivo con contenido real, sin dominio
muerto/hijackeado:** Salud Pública (`salud.gob.ec`), Cancillería
(`cancilleria.gob.ec`), Defensa (`defensa.gob.ec`), Telecomunicaciones
(`telecomunicaciones.gob.ec`), Presidencia (`presidencia.gob.ec`),
Vicepresidencia (`vicepresidencia.gob.ec`), Asamblea Nacional — sitio
propio (`asambleanacional.gob.ec`, distinto de observatoriolegislativo.ec),
Consejo de la Judicatura (`funcionjudicial.gob.ec`), TCE (`tce.gob.ec`,
alcanzable, a diferencia de CNE que sigue bloqueado por WAF Incapsula).

**Pistas nuevas marcadas para una pasada de contenido futura (dominio
confirmado vivo, contenido sin verificar todavía):** "Estadísticas de
proceso de regularización" en Cancillería (migración); "Observatorio
Ecuador Digital" en Telecomunicaciones; "InfoDH — Portal de Información
Estadística" en Desarrollo Humano/MIES; "VISOCIAL" (Sistema de
Visualización Social) en Vicepresidencia, que también menciona un
"Sistema Nacional de Información (SNI)"; "Sistema de Consulta de Datos
Parlamentarios" y sección "ESTADO ABIERTO"/"PARLAMENTO ABIERTO" en el
sitio propio de la Asamblea Nacional (contraparte oficial del dataset de
votaciones de FCD ya documentado); "Portal de Estadísticas Judiciales" en
Consejo de la Judicatura (podría ser el mismo `fsweb.funcionjudicial.
gob.ec/estadisticas/...` que RESEARCH.md ya encontró roto/en blanco, o
uno distinto — falta confirmar).

---

## Novena pasada — ENEMDU 2024-2026 y bug de paginación en `get_organization`

**Investigado 2026-08-30, pedido de Daniel:** un agente externo usando una
versión anterior de este servidor reportó que ANDA no tenía todavía la
ENEMDU anual 2025. Daniel dudó que el archivo hubiera llegado a CKAN;
verificado en vivo (con VPN a LatAm, ya que `datosabiertos.gob.ec` bloquea
IPs fuera de la región) que tenía razón, pero el hallazgo real es otro:
**INEC nunca dejó de publicar ENEMDU — dejó de actualizar la página
estática de tema que este proyecto scrapea, y ahora solo anuncia los
boletines nuevos vía su sección de Noticias.**

Verificado en vivo, en orden:

1. **ANDA** (`anda_client.search_catalog(query="ENEMDU")`): la edición más
   reciente es 2023 (`ECU-INEC-CGTPE-DIES-ENEMDU-2023-v1.3`). Nada de 2024
   o 2025.
2. **`ecuadorencifras.gob.ec/empleo-marzo-2018/`** (la página de tema que
   `search_inec_estadisticas`/`get_inec_estadistica_files` indexa vía el
   menú del sitio): su propio `<title>` dice "Estadísticas Laborales —
   abril 2023" y el archivo más nuevo listado es de abril 2023. Confirmado
   con un fetch independiente de la página (no solo vía nuestro scraper).
   Existe una segunda entrada del menú, "Trabajo" →
   `sistema-estadisticas-laborales-empresariales/`, que también cubre
   ENEMDU pero está más vieja todavía (julio 2022, y es un visualizador
   interactivo, no una página de archivos).
3. **CKAN** (`instituto-nacional-de-estadisticas-y-censos`, 94 datasets):
   buscar "ENEMDU"/"empleo"/"mercado laboral" solo devuelve datasets de
   2021 o antes. La organización sí tiene actividad reciente real (mayo
   2026: registros de entradas/salidas internacionales, defunciones,
   nacidos vivos), pero ninguna en la familia ENEMDU desde 2021 — INEC
   simplemente no alimenta ese dataset específico a CKAN.
4. **La sección de Noticias sí tiene el boletín vigente.**
   `ecuadorencifras.gob.ec/institucional/noticias/` (paginada, ~43 links
   por página) tiene un comunicado real: "Ecuador registra 86 mil personas
   menos en situación de desempleo en mayo de 2026 frente a mayo de 2025",
   que enlaza `documentos/web-inec/EMPLEO/2026/Mayo_2026/
   202605_MercadoLaboral.pdf` — mismo patrón de ruta
   (`EMPLEO/{año}/{Mes}_{año}/...`) que los boletines antiguos ya
   conocidos de la página de tema. El boletín de mayo 2026 es real y
   descargable; el problema es puramente de descubrimiento, no de que la
   fuente haya dejado de publicar.

**Implicación para el roadmap:** el patrón "página de tema estática +
menú del sitio" que `inec_client.py` usa para descubrir contenido puede
quedar desactualizado por tema sin que el sitio lo señale de ninguna
forma — la página de Empleo simplemente dejó de recibir enlaces nuevos
mientras el propio INEC seguía publicando el boletín mensual real, solo
que anunciado por otro canal.

**Auditadas las 74 páginas de tema completas (pedido explícito de Daniel:
"ayúdame a completar los scrapes del INEC"), no solo Empleo.** Script
puntual: para cada tema, `get_topic_files` + año más reciente mencionado
en cualquier label/URL de archivo. Resultado:

- **26 de 74 temas devuelven 0 archivos.** Leyendo el HTML crudo de varios
  (Estadísticas Macroeconómicas, Cuentas económicas, Comercio
  internacional y balanza de pagos, Finanzas públicas/fiscales, Precios,
  Estadísticas sectoriales, Estadísticas de las empresas, Ambiente y
  Agropecuario, Ciencia tecnología e innovación, Sociedad de la
  información - TIC, Eventos extremos y desastres, Anuarios Estadísticos,
  Censo Nacional Económico, Censo Nacional Agropecuario, Trabajo,
  Requerimiento de Información, entre otros): son páginas "hub" que
  **repiten exactamente el mismo menú de ~100 links del sitio entero**, sin
  ningún archivo propio — no es un fallo de nuestro regex, la página en sí
  no tiene contenido descargable. Cada una de estas categorías del menú
  superior parece ser solo un contenedor visual para sus subtemas reales
  (ej. "Precios" no tiene archivos propios, pero "Índice de Precios al
  Consumidor" — un tema separado en la misma lista — sí tiene 17 archivos
  actualizados a 2026).
- **De los 48 temas restantes que sí tienen archivos**, la mayoría está
  razonablemente al día (IPC/INPP/Precios de la Construcción: 2026;
  Ingresos y Gastos, ESPAC, Edificaciones, Entradas y Salidas
  Internacionales: 2025), pero varios llevan años sin tocarse mientras el
  sitio sigue vivo en general: Alquileres (2013), Educación y
  Asentamientos humanos y vivienda (2017), Protección social (2018),
  Trabajo Infantil/Encuesta Multipropósito/Uso del Tiempo/Violencia de
  Género/ACTI/Índice de Industria Manufacturera/Comercio
  Interno/Manufactura y Minería/Hoteles-Restaurantes-Servicios (todos
  2020), Empleo (2023, ver arriba).
- **`/institucional/noticias/` sí tiene boletines reales y recientes**
  fuera del caso de Empleo: inflación (IPC) de julio 2026, Índice Nacional
  de Precios Productor de julio 2026, resultados de la ENIGHUR 2024-2025,
  todos con PDF/XLSX adjuntos bajo el mismo patrón de ruta
  `documentos/web-inec/{TEMA}/{año}/{Mes}_{año}/...`. Confirma que el
  mecanismo de publicación real de INEC hoy es Noticias, no las páginas de
  tema — el gap de Empleo no es un caso aislado, es el mismo patrón que
  aplica (en menor o mayor grado) a buena parte del sitio.
- **Descartado un atajo:** existe también `/institucional/boletines/`,
  que suena como el índice general que necesitábamos, pero resultó ser
  exclusivamente la campaña de prensa del Censo de Población y Vivienda
  2022 (comunicados de socialización por provincia) — no sirve como fuente
  genérica de boletines mensuales.
- **Hipótesis sin confirmar sobre las 4 categorías "macro" vacías**
  (Estadísticas Macroeconómicas, Cuentas económicas, Comercio
  internacional y balanza de pagos, Finanzas públicas/fiscales): a
  diferencia de Empleo/Precios (que sí tienen contenido real, solo mal
  enlazado), estas 4 podrían estar vacías *por diseño* — Cuentas
  Nacionales y Balanza de Pagos son responsabilidad del BCE en el sistema
  estadístico ecuatoriano (ya cubierto por `search_indicadores_bce`/IEM en
  este mismo proyecto), así que es plausible que INEC nunca haya publicado
  nada propio ahí. No confirmado contra Noticias todavía — pendiente antes
  de asumir que es el mismo bug que Empleo.

**Bug real encontrado de pasada:** `helpers/ckan_client.get_organization`
usaba `organization_show?include_datasets=true`, cuyo campo `packages`
resultó estar *capado por el tamaño de página por defecto del portal* —
confirmado en vivo devolviendo solo 10 de 94 datasets reales para
`instituto-nacional-de-estadisticas-y-censos`, con `get_organization_info`
mostrando además un "Total de datasets: 94" contradictorio con
"Datasets publicados (10)" en el mismo texto. Corregido: ahora usa
`package_search?fq=organization:{id}&rows=1000&sort=metadata_modified
desc` para el listado real de paquetes, verificado devolviendo 94/94 en
vivo. Afecta a cualquier organización con más datasets que el tamaño de
página del portal, no solo a INEC.

**Corrección importante (mismo día, mismo pedido): la conclusión "INEC
solo anuncia ENEMDU vía Noticias" de arriba estaba mal — Daniel aportó
URLs reales que la refutaron.** `estadisticas-laborales-enemdu/`,
`enemdu-trimestral/` y `enemdu-anual/` son páginas reales y vigentes en
`ecuadorencifras.gob.ec` que **no estaban en la lista de 74 temas** que
usa `search_inec_estadisticas`, y tienen ENEMDU mensual hasta mayo 2026,
trimestral hasta 2026-I, y **el anual 2025 completo** (BDD SPSS/CSV,
boletín técnico, tabulados) — es decir, ENEMDU 2025 sí está publicado en
el sitio principal de INEC, sin necesidad de Noticias. El motivo de que
nuestro scraper no las encontrara: **el mega-menú del sitio no es el
mismo en cada página.** La página `estadisticas-laborales-enemdu/` tiene
su propio menú de ~109 links (incluye las 3 URLs de arriba más
`enemdu-telefonica/`, `empleo-y-condicion-de-actividad/`,
`trabajo-y-empleo/`, `matrices-de-transicion-laboral/`, ninguna
alcanzable desde la página semilla `indice-de-precios-al-consumidor/`
que usa `_fetch_topics()`). No hay `sitemap.xml`/`wp-sitemap.xml` en el
dominio (confirmado, 404 en los tres paths estándar), pero sí existe
`/wp-json/wp/v2/posts` — la **API REST pública de WordPress**, sin
autenticación: `X-WP-Total: 1707`, post más nuevo del 2026-08-25,
soporta `search`/`orderby`/paginación, y el HTML de cada post
(`content.rendered`) trae los enlaces a archivos directamente —
confirmado extrayendo 11 archivos reales del post `enemdu-anual-2024`
consultando solo `GET /wp-json/wp/v2/posts?slug=enemdu-anual-2024`, sin
tocar ninguna página HTML. `/institucional/noticias/` y
`/institucional/boletines/` son solo vistas filtradas por categoría de
esta misma colección de posts — la API es la fuente de verdad real, y
reemplaza la necesidad de un scraper de Noticias aparte. Ver el ítem
corregido en ROADMAP.md.

**`censoecuador.gob.ec`** (enlazado por Daniel el mismo día): micrositio
propio de INEC para el Censo 2022, WordPress, mismo patrón de certificado
TLS que otros `.gob.ec` (necesita `verify=False`). Su página
`/data-y-resultados/` devuelve HTTP 404 pero sirve 163 KB de contenido
real (bug de plugin/tema, no ausencia de contenido) con enlaces reales a
microdatos censales por sector/cantón/manzana en CSV/SPSS/REDATAM,
diccionarios de variables, y los censos 2010 y 2001 re-codificados a la
geografía 2022. Verificado con HEAD sobre 3 archivos de muestra (un XLSX
y dos ZIP): status 200, content-type correcto en los tres. Todos los
archivos reales viven en `ecuadorencifras.gob.ec/documentos/web-inec/
bd-censo/...` — mismo dominio principal, solo una ruta que ningún tema de
los 74 alcanza. Mucho más completo que el tema "Censo de Población y
Vivienda" ya indexado (16 archivos, 2024).

**Las 4 categorías "macro" vacías: confirmado que son BCE, no INEC
(2026-08-30).** Búsqueda dirigida vía `search_inec_publicaciones` con
"cuentas nacionales", "cuentas económicas", "PIB producto interno bruto",
"balanza de pagos", "comercio exterior", "finanzas públicas",
"estadísticas macroeconómicas" y "deuda pública": en cada caso los únicos
resultados relevantes son las páginas hub vacías mismas (fechadas
2016-09-15, categoría "Sin categoría") o contenido tangencial
(certificaciones de calidad, historia institucional, comisiones). El
único contenido económico real bajo la categoría "Estadísticas
Económicas" son las Cuentas Satélite (Salud 2007-2023, Educación
2007-2023, Trabajo No Remunerado 2016-2017, Energía) y el Registro
Estadístico de Empresas — nunca Cuentas Nacionales (PIB), Balanza de
Pagos ni deuda pública. Confirma la hipótesis: esa es responsabilidad del
BCE en el sistema estadístico ecuatoriano (ya cubierto por
`search_indicadores_bce`/IEM), no un gap de descubrimiento como ENEMDU.

**Verificación de varias encuestas específicas, pedido de Daniel
2026-08-30 (probando el tool nuevo con casos reales conocidos):**

- **ENEMDU histórico**: patrón de nomenclatura mapeado probando slugs
  directos — 2017-2020 usa `enemdu-YYYY` (`enemdu-2017/`: 52 archivos
  reales), 2021-2024 usa `enemdu-anual-YYYY` (`enemdu-anual-2021/` a
  `-2024/`: 11 archivos cada uno), 2025+ vive en la página evergreen
  `enemdu-anual/` sin sufijo de año. **No existe un anual 2020
  consolidado**: `enemdu-2020/` es en realidad una nota metodológica que
  explica el cambio de diseño muestral por COVID (desde 2020 hasta mayo
  2021) y remite a las ediciones mensuales (`enemdu-septiembre-2020/`,
  `empleo-dic-2020/`, ambas con 22 archivos reales) en vez de un
  consolidado anual.
- **Encuesta Nacional Multipropósito de Hogares**: sin ronda nueva
  confirmada — ni en `search_inec_publicaciones` (buscado "multiproposito
  2021/2023/2024", "ENM 2023/2024") ni en ANDA. El tema y la última
  ronda en ANDA siguen en diciembre 2020/2019.
- **SABE (Salud, Bienestar y Envejecimiento)**: **2 rondas, ambas de
  2009**, empaquetadas en un solo archivo (`SABE1_SABE2_2009.zip`, en la
  página de tema "Encuesta de Salud, Bienestar del Adulto Mayor"). ANDA
  la cataloga como `SABE I-2012` (año de catalogación 2012, año de
  encuesta 2009). Sin SABE III ni ronda posterior encontrada.
- **REESS (Registro Estadístico de Empleo en la Seguridad Social)**: bien
  cubierto, cadencia mensual real confirmada hasta abril 2026 (publicado
  2026-07-29), con archivos BDD en tres niveles de madurez
  (`PROVISIONALES`, `SEMIDEFINITIVAS`, y un histórico `DEFINITIVAS` que
  cubre 200901-202412, 15+ años). La página de tema estática va un mes
  detrás de la publicación más reciente encontrada vía
  `search_inec_publicaciones` — mismo patrón ya documentado arriba.
  El ZIP `DEFINITIVAS` es genuinamente grande: no terminó de descargar
  los primeros 100 MB en 60 segundos en una prueba en vivo, muy por
  encima del cap de 5 MB usado en el resto del proyecto — ver el ítem de
  ROADMAP.md sobre falta de preview para archivos grandes de INEC.
- **ENSANUT**: confirmado sin rondas nuevas desde 2018 (coincide con lo
  que Daniel ya sabía) — la página de tema solo tiene archivos
  `ENSANUT_2018`, y buscar "ensanut 2023/2024/ii" no encontró nada
  relevante más nuevo.

`search_censo_recursos` cataloga **36 archivos reales** de
`censoecuador.gob.ec` (metadata + URL directa, sin descarga a través de
este MCP, mismo patrón que `get_inec_estadistica_files`).

**Construido 2026-08-30: `search_censo_recursos` (censoecuador.gob.ec) y
descubrimiento del Clasificador Geográfico vía la infraestructura ya
existente.** El Clasificador no necesitó un cliente nuevo — solo dos
arreglos a `inec_client.py`: agregarlo a `_EXTRA_TOPICS` (no está en el
menú de ningún seed) y corregir `_FILE_LINK_RE` para tolerar el doble
slash real que usa el sitio (`.ec//documentos/...`), lo que llevó los
archivos encontrados en esa página de 19 a 115.

El censo sí necesitó cliente nuevo (`helpers/censo_client.py`) por dos
problemas reales de host, ambos resueltos en `helpers/tls.py`/
`helpers/csv_reader.py` en vez de en el cliente: el chain TLS de
`www.censoecuador.gob.ec` verifica contra el almacén del SO pero no
contra `certifi` (confirmado con un handshake `ssl.create_default_context()`
crudo que sí funciona) — nuevo nivel `should_retry_with_os_trust`/
`os_trust_context`, sin perder verificación real, a diferencia del
reintento inseguro existente; y `/data-y-resultados/` devuelve HTTP 404
con contenido real (bug de plugin) — `download_bytes` gana
`raise_for_status=False`, opt-in, default `True` sin tocar ningún otro
caller.

**Drift real encontrado y corregido en `helpers/data/{cantones,parroquias}.json`
comparando contra `CLASIFICADOR_GEOGRAFICO_2026.zip` (el oficial, recién
publicado):** La Concordia estaba con el código viejo `0808`/Esmeraldas;
el oficial la tiene como `2302`/Santo Domingo de los Tsáchilas desde hace
años (la reasignación de provincia es un hecho ya resuelto, no algo en
disputa). Faltaba por completo el cantón `1413` Sevilla Don Bosco
(Morona Santiago), creado por la Asamblea Nacional el 2024-11-05 — el
cantón más nuevo de Ecuador (área 2,246.35 km², población 18,647 según
censo 2022; fuentes: Asamblea Nacional, El Universo, Primicias). Antes
solo existía como parroquia de Morona (código `140157`), que el
clasificador oficial ya no lista — retirada correctamente al crear el
nuevo cantón. Total de cantones pasó de 224 a 225 (222 con provincia
real + 3 "zona en estudio"), coincidiendo con la cifra pública citada de
Sevilla Don Bosco como "cantón 222 de Ecuador".

**Zona 90 (zonas en disputa territorial), investigado a fondo 2026-08-30 —
no fue un simple reemplazo de códigos.** La discrepancia inicial
(`9001`/`9003`/`9004` nuestros vs `9006`/`9009` del clasificador 2026) se
investigó caso por caso en vez de asumir que "lo oficial reemplaza lo
nuestro":

- **`9006` Juval** (disputa real Cañar-Chimborazo, con código propio desde
  un decreto de 2017 según registro oficial): confirmado como zona
  legítima y activa, con su propia parroquia en el clasificador
  (`900651`). Agregado a nuestros datos — la única adición real.
- **`9009` "Morona"** en el clasificador: casi seguro un error de captura
  de la propia hoja de cálculo oficial — su columna de provincia dice
  "MORONA SANTIAGO", no "ZONA EN ESTUDIO" (inconsistente con su propio
  código 90), no tiene ninguna parroquia listada, y "Morona" ya existe
  como cantón real y consolidado (`1401`) en la misma provincia. No
  agregado.
- **`9001` Las Golondrinas**: búsqueda externa confirma que se resolvió a
  favor de Cotacachi/Imbabura por consulta popular en 2026 — pero el
  propio clasificador oficial 2026 todavía no le asigna ningún código de
  parroquia bajo Cotacachi (búsqueda de texto completo por "GOLONDRINA"
  en las hojas CANTONES y PARROQUIAS del clasificador: cero resultados).
  La resolución política es más reciente que la publicación estadística
  formal — no se puede inventar un código que INEC mismo no ha asignado
  todavía. Dejado sin cambios.
- **`9003` Manga Del Cura y `9004` El Piedrero**: búsqueda externa confirma
  que ambas siguen genuinamente en disputa/sin resolver a la fecha
  (fuentes de 2024: un decreto de 2017 que asignaba El Piedrero a Guayas
  "quedó en el papel", nunca se implementó). Su ausencia en la hoja
  CANTONES del clasificador no es evidencia de que se resolvieron —
  aparentemente nunca recibieron un código formal de cantón como sí lo
  tuvo Juval (una vía administrativa distinta, no necesariamente ligada
  al estado de la disputa). Dejadas sin cambios.

Lección: cuando una fuente "oficial" nueva no coincide con un dato
existente, la corrección correcta no siempre es "usar la fuente nueva" —
a veces la fuente nueva tiene sus propios errores de captura (Morona) o
simplemente no cubre casos que la fuente vieja sí cubre por una razón
administrativa distinta (Manga Del Cura, El Piedrero), o la realidad
política va más rápido que la codificación estadística formal
(Las Golondrinas).

---

## Décima pasada — SUT Power BI descifrado, MIES/Ministerio de Desarrollo Humano

### SUT — protocolo Power BI descifrado, gap real resuelto

**2026-08-30/31.** Continuación directa de la corrección de arriba
("do we have monthly level SUT contratos by industry" refutó el "sin
gap" anterior). En vez de quedarse en "esto necesita automatizar un
embed de BI, no es HTML estático" como límite, se llegó al protocolo
real conduciendo el dashboard en un browser real y capturando su
tráfico de red (`window.fetch`/`XMLHttpRequest` hookeados desde
`javascript_tool`):

1. **Descubrimiento del endpoint de esquema.** El HTML de
   `app.powerbi.com/view?r=<token>` referencia
   `getConceptualSchemaUrl` y variables de bootstrap; el endpoint real
   resultó ser `GET /public/reports/{resource_key}/modelsAndExploration`
   contra `wabi-south-central-us-c-primary-api.analysis.windows.net`,
   con el header `X-PowerBI-ResourceKey: {resource_key}` (el `resource_key`
   es el campo `k` del JSON que decodifica el parámetro `r=` del embed —
   público, no requiere login). Esta llamada devuelve, sin tocar ningún
   visual: `reportId`, `modelId`, el `datasetId` (`models[0].dbName`), y
   el layout completo del reporte (`exploration.sections[].visualContainers[]`),
   donde el `config` de cada visual trae su propio `prototypeQuery` — la
   query DAX exacta que ese gráfico ejecuta. Catalogar los campos de las 8
   dashboards de SUT se hizo leyendo estos `prototypeQuery`, sin abrir
   ninguno en el navegador.
2. **Descubrimiento del endpoint de consulta.** `POST
   /public/reports/querydata?synchronous=true` (mismo host, mismo header)
   acepta un `SemanticQueryDataShapeCommand` arbitrario — cualquier
   combinación de columnas/medidas del modelo, no solo lo que un visual
   ya muestra. Trampa real encontrada: una consulta SIN el header
   `X-PowerBI-ResourceKey` puede devolver 200 si por casualidad coincide
   byte-a-byte con una consulta que una sesión real ya ejecutó (una
   caché de borde/CDN keyed por cuerpo de la solicitud) — esto engañó la
   primera prueba dando una falsa sensación de "acceso abierto sin auth".
   Con el header presente, cualquier consulta nueva funciona (401 sin
   él). Confirmado con una consulta mes × industria × conteo que ningún
   visual del dashboard muestra combinada así.
3. **Formato de respuesta (DSR).** El campo `dsr` de la respuesta es la
   codificación compacta "Data Shape Result" de Power BI: la primera
   entrada de cada lista `DM0` trae `"S"` (el esquema de columnas, con
   `"DN"` apuntando a `ValueDicts` para columnas categóricas); cada
   entrada siguiente es una fila que solo declara los valores que
   cambiaron desde la fila anterior — `"C"` trae esos valores en el
   orden del esquema, `"R"` es una máscara de bits (bit i activo =
   columna i repite el valor de la fila anterior, no aporta nada a
   "C"), `"Ø"` es la máscara equivalente para valor nulo. Implementado
   en `helpers/sut_powerbi_client._decode_dsr` y **validado contra
   verdad de terreno**: se leyó manualmente "enero 2015 = 92,306
   contratos" directamente de la tabla que el propio Power BI genera
   vía su menú contextual "Show as a table", y el decoder reproduce
   exactamente ese número (y todos los meses siguientes) antes de
   confiar en él para nada más.

**Resultado:** `helpers/sut_powerbi_client.py` +
`list_sut_indicadores`/`get_sut_indicador_schema`/`query_sut_indicador`,
un cliente genérico (no 8 clientes por-dashboard) que aplica a las 8
dashboards por igual. Catálogo de campos por dashboard (descubierto en
vivo, sin adivinar):

- **contratos** (`Contratos MDT v1`) — contratos SUT: mensual desde
  2015, por rama de actividad (CIIU), cantón/provincia, género,
  discapacidad, tipo de contrato, estado (Vigente/Finalizado); además un
  hallazgo dentro del mismo modelo no visible en la navegación pública
  del embed (solo 3 páginas mostradas, el modelo tiene 6): **actas de
  finiquito legalizadas** (`public acta_finiquito`) — fecha de
  finiquito/legalización, cantón, rama de actividad, motivo de salida.
- **encuesta_demanda_laboral** — encuesta a EMPLEADORES (no a
  trabajadores): contrataciones, vacantes y brecha de habilidades
  (externa e interna), requisitos/canales de reclutamiento, capacitación
  por tamaño de empresa — por ciudad y categoría/industria. Único
  dataset de este grupo con la perspectiva de demanda laboral, no oferta.
- **sentencia_genero** (`SENTENCIA_V2`) — el más grande: PEA, tasas de
  desempleo/empleo adecuado, ingreso laboral, brecha salarial y de
  puestos directivos por género, denuncias, trabajo no remunerado,
  cuidado (MIES), presupuesto e inversión en política de género, más un
  "Manual de Ambientes Laborales" institucional (salas de lactancia,
  centros infantiles, teletrabajo) por período.
- **capacitacion_certificacion** — capacitaciones y certificaciones del
  MDT vía SETEC (Servicio Ecuatoriano de Capacitación Profesional):
  conteos CI/OCC/OEC por provincia, mensual/anual, con metas KPI 2025.
- **plan_nacional_desarrollo** — indicadores laborales del Plan Nacional
  de Desarrollo por provincia y año desde 2018: brecha de empleo
  adecuado y salarial por género, desempleo juvenil, tasa de desempleo,
  tasa de empleo adecuado.
- **estrategias_empleabilidad** — Emprende EC / Fortalece Empleo (7
  campos catalogados).
- **denuncias_publico**, **encuentra_empleo** — **resueltos 2026-08-31**
  (pedido explícito de Daniel, "do SUT now"). Confirmado por qué
  `modelsAndExploration` no devolvía campos: sus visualContainers son de
  verdad minimalistas (`{id,x,y,z,width,height,objectName}`, sin
  `config` en absoluto — no un bug del parser, el reporte no expone el
  layout así). Recuperados conduciendo cada dashboard en un browser real
  con `window.fetch`/`XMLHttpRequest` hookeados y forzando una query
  nueva (cambiando un filtro de año/provincia), igual que reveló mes ×
  industria en `contratos`. **denuncias_publico** (tabla `REGISTROS`):
  fecha de ingreso al MDT (jerarquía Año/Mes), motivo de la denuncia,
  regional asignada, estado, año de ingreso, fecha de carga, medida
  "Cantidad denuncias". **encuentra_empleo** (tabla `CONSOLIDADO`,
  Dirección de Servicio Público de Empleo): fecha de corte (jerarquía
  Año/Mes/**Día** — la única granularidad diaria vista en SUT), columna
  categórica "Encuentra Empleo" con valores REGISTRADOS/COLOCADOS/
  CAPACITADOS, provincia, año, fecha de carga, y un tipo de campo nuevo
  no visto en los otros 6 dashboards: "Número de Personas" es una
  columna agregada con `SUM()` en tiempo de consulta
  (`{"Aggregation":{...,"Function":0}}`), no una medida DAX prearmada —
  confirmado también `Function:4` = Min en la misma sesión (usado para
  "última fecha de carga"). Verificado en vivo con datos reales:
  REGISTRADOS enero-2023 = 26,033 personas. Ambos ahora en
  `_MANUAL_CAMPOS` (`helpers/sut_powerbi_client.py`), fusionados con el
  descubrimiento automático — **los 8 dashboards de SUT quedan
  completamente cubiertos.**

### BCE — familia de indicadores diarios/mensuales fuera de BCEData e IEM

**2026-08-31, pedido explícito de Daniel ("Riesgo Pais needs to be covered
specifically... investigate").** `search_indicadores_bce`/BCEData solo
tenía Riesgo País (EMBI) como agregado **mensual** (id_grupo 8, fin de
período) — para un indicador que el propio BCE, según cobertura de
prensa contemporánea (Infobae, El Universo, Bloomberg Línea, agosto
2026), publica **todos los días hábiles**. Ni el buscador interno de
`bce.fin.ec` ni el catálogo BCEData tienen una página o serie dedicada a
"riesgo país" — la búsqueda en el sitio solo encontró una licitación
para contratar Bloomberg/Moody's/PRS Group como proveedores de datos de
riesgo crediticio internacional, lo que sugiere (incorrectamente, ver
abajo) que el dato diario no se republica.

**Hallazgo real:** un agregador financiero de terceros
(tagline-soluciones.com) citaba como fuente
`https://contenido.bce.fin.ec/estadisticas-de-publicaciones-generales/`
— una página que el buscador del sitio principal (`bce.fin.ec`) nunca
superficia porque vive en el subdominio de contenido
(`contenido.bce.fin.ec`), el mismo que ya se usa para BCEData/IEM. Esa
página incrusta varios widgets Highcharts, uno por indicador
(`data-dd-title="Riesgo País"` etc.), cada uno cargando su HTML propio
desde `wp-content/uploads/ESTADISTICAS-ECONOMICAS/indicadores/{Nombre}.html`.
Cada página de widget declara una variable JS `archivo` (o
`ARCHIVO_JSON`) con el nombre de un archivo JSON plano — sin
autenticación, sin API key, confirmado descargándolo con `curl` puro.
Varios widgets comparten el mismo archivo (ej. Riesgo País y Precio del
Oro viven ambos en `datos_formulario.json`).

**Confirmado en vivo, con `Periodicidad` explícita en cada fila del
JSON** (no una suposición sobre la frecuencia real):

| Archivo | Indicador | Periodicidad | Rango | Filas |
|---|---|---|---|---|
| `datos_formulario.json` | Riesgo País (pb) | D | 2004-07-29 → hoy | 7369 |
| `datos_formulario.json` | Precio del Oro (USD/oz) | D | 1999-01-01 → hoy | 7213 |
| `datos_diarios.json` | Petróleo WTI (USD/barril) | D | 2015-01-02 → hoy | 3868 |
| `datos_diarios.json` | Índice Dow Jones | D | 2018-01-17 → hoy | 3087 |
| `datos_diarios.json` | Tasa LIBOR | D | 2013-09-26 → 2024-09-30 (discontinuada) | 3289 |
| `datos_diarios.json` | Tasa SOFR | D | 2022-01-01 → hoy | 1700 |
| `datos_bonos_soberanos.json` | Bonos Ecuador 2030/2035/2040 (% valor nominal) | D | 2020-09-02 → hoy | ~6300 |
| `datos_pagos.json` | SPI, SCI, SPL, CCC, Monto Recaudado | M | 2010-01-01 → hoy | 882 (agregado) |
| `datos_hid.json` | **Producción Petrolera Nacional (barriles)** | D | 2018-01-01 → hoy | 3154 |
| `datos_hid.json` | Precio Petróleo Crudo Ecuatoriano | M | 2000-01-01 → hoy | 318 |
| `datos_ipc.json`, `datos_tes.json`, `datos_icc.json`, `datos_cna.json` | Inflación, desempleo, confianza consumidor, PIB | M/T/A | varía | varía |

La página `estadisticas-del-sector-medios-y-sistemas-de-pagos/` resuelve
por sí sola el ítem del roadmap "medios y sistemas de pago" que llevaba
mucho tiempo marcado como "si el acceso automatizable se confirma" — sí
se confirma, mismo patrón. La página `estadisticas-del-sector-real/`
aportó el segundo hallazgo genuinamente diario más valioso
(Producción Petrolera Nacional, clave para la posición fiscal del país)
además de duplicados mensuales/anuales de series que probablemente ya
están en BCEData. La página `estadisticas-del-sector-externo-d/`
(nótese la "-d" en la URL, no la ruta "limpia" que se esperaría — un
detalle que hay que preservar al construir el cliente) repite Riesgo
País, Precio del Oro y WTI y añade balanza comercial/exportaciones/
importaciones/remesas/tipo de cambio efectivo real, probablemente
duplicados de BCEData también.

**No exhaustivo:** se probaron 4 páginas del patrón
`estadisticas-de-*`/`estadisticas-del-*` de las cuales 3 tenían
widgets; no se recorrió el mega-menú completo de "Estadísticas" del
sitio (bloqueado por un menú que solo se expande con JS, no con fetch
crudo) — es razonable esperar más páginas con el mismo patrón sin
descubrir todavía. Pendiente de construir: un cliente
(`helpers/bce_indicadores_diarios_client.py` o similar) que parsee estos
JSON directamente — sin necesidad de ningún truco de scraping, el mismo
nivel de esfuerzo que cualquier cliente basado en archivo estático de
este proyecto (SIPA, Superbancos estático).

### Ministerio del Trabajo — más allá de SUT y CKAN

**2026-08-31.** `trabajo.gob.ec` (dominio raíz, no `sut.` ni
`desarrollohumano.`) reconfirma el patrón ya documentado: páginas
dinámicas mueren en timeout (`/direccion-de-investigacion-y-estudios-laborales/`
probado explícitamente, timeout total), pero archivos estáticos bajo
`/wp-content/uploads/` cargan sin problema. Una búsqueda web (no
navegación directa, imposible por el timeout) encontró dos ediciones
reales del **"Boletín Estadístico Anual: El Mercado Laboral en el
Ecuador"** — No. 3 (2022) y una edición 2020 — ambas confirmadas vivas
con `curl -I` (PDF real, ~4 MB cada una, `Content-Type: application/pdf`).
El boletín 2022 declara explícitamente que sus cifras derivan de la
ENEMDU de INEC (referencia diciembre 2022) — es un producto derivado/
análisis, no una encuesta propia del ministerio, coherente con el
patrón ya documentado en la Octava pasada. Los nombres de archivo no
siguen un patrón adivinable (`Boletin-Anual-2022-1_compressed.pdf` vs.
`BoletinAnual2020ok.pdf`), así que no hay forma de listar ediciones de
otros años sin acceder al índice real — bloqueado por el mismo timeout
de siempre. Candidato para una pasada futura con Wayback Machine sobre
la página índice.

### SUT (`sut.trabajo.gob.ec`) — nav completo re-verificado, sin dashboards adicionales

**2026-08-31, tercera pasada sobre el mismo portal.** Navegado el resto
del árbol de navegación del portal (no solo la sección "Indicadores" ya
cubierta) con un browser real. El menú "Datos Abiertos" del propio
portal — la etiqueta más directa posible de "esto es un dataset" — solo
lista dos ítems: "Contratos registrados en el Sistema Único de Trabajo"
y "Sentencia Nro. 3-19-JP/20 y acumulados", ambos ya cubiertos por
`sut_powerbi_client` (indicadores `contratos` y `sentencia_genero`). No
hay un tercer dataset escondido bajo esa etiqueta. El resto del menú
("Mediación laboral" → nueva solicitud / seguimiento de una solicitud;
"Sustitutos"; "Capacitaciones" → catálogo de cursos de autoinscripción
para Seguridad y Salud, Encuentra Empleo y Capacitaciones Internas MDT)
son herramientas transaccionales de caso-por-caso o portales de
autoservicio, no fuentes de datos agregados — mismo patrón ya
descartado para trámites individuales en otras instituciones (Fiscalía,
inspecciones laborales). **Conclusión: no queda ningún dashboard o
sección de datos sin explorar en `sut.trabajo.gob.ec`** más allá de los
8 ya catalogados en `helpers/sut_powerbi_client.py`.

### ARCSA (Agencia Nacional de Regulación, Control y Vigilancia Sanitaria)

**Investigado 2026-08-31, pedido explícito de Daniel.** Organización CKAN
real (`agencia-nacional-de-regulacion-control-y-vigilancia-sanitaria-arcsa...`)
con solo 4 datasets, todos sobre registros sanitarios/permisos de
funcionamiento **suspendidos o cancelados** de medicamentos —
actualización semestral, ya alcanzable con
`search_organizations`/`list_dataset_resources` sin cliente nuevo.

El dato realmente valioso — el registro sanitario completo *vigente* (no
solo lo cancelado), confirmado por búsqueda web como "Base de Registros
Emitidos" en `controlsanitario.gob.ec/base-de-datos/` (productos
naturales, medicamentos homeopáticos, actualizado a junio 2026) — **no se
pudo verificar**: `www.controlsanitario.gob.ec` está caído (reset de
conexión TLS tras renegociación, confirmado con `curl` y con `httpx` en
Python — mismo patrón exacto que `inclusion.gob.ec`, no es un problema del
cliente). Un subdominio sí vive
(`permisosfuncionamiento.controlsanitario.gob.ec/consultorciudadano/`,
"ARCSA-Notificaciones") pero es un formulario de login real, sin acceso de
invitado visible — mismo patrón de bloqueo ya descartado para Superbancos
Catastro/SENESCYT. Pendiente: reintentar `controlsanitario.gob.ec` más
adelante (podría ser una caída transitoria, a diferencia de
`inclusion.gob.ec` que lleva meses muerto) antes de descartar la "Base de
Registros Emitidos" del todo.

### Superbancos — los 3 widgets OneDrive de `servicios_financieros`

**2026-08-31.** El tercer widget de la página (sin encabezado identificable
en la primera pasada) resultó tener uno real, "Estadísticas Generales" —
solo hacía falta ampliar la ventana de búsqueda hacia atrás de 3000 a
5000 caracteres. Su árbol es mucho más profundo que el de boletines: 9
categorías numeradas (A06 Servicios Financieros Reportados, A09
Adquirencia, A10 Avances en Efectivo, A12 Tarjetas, A13 POS, C71 Puntos
de Atención, Gestión de Cobranzas, Recaudación de Pagos a Terceros,
Retiros de Dinero), cada una con su propia carpeta "Otros Años" y, en
algunos casos, sub-subcarpetas por año o por tipo de canal (ej. "Puntos
de Atención" → "Otros Años" → Cajeros/Corresponsales/Oficinas). Es la
consolidación real "Estadísticas Puntos de Atención" que la página ya
mencionaba en su nota de mayo 2021.

Confirmado en vivo (no asumido): la llamada raíz del widget devuelve el
**árbol completo** con punteros a padre en una sola respuesta, no solo
los hijos inmediatos — se pudo construir el breadcrumb completo de cada
carpeta sin llamadas adicionales, solo con el campo `parent` de cada
nodo. El costo real está en listar los ARCHIVOS de cada carpeta, no en
descubrir la estructura: ~40 llamadas HTTP para los 3 widgets combinados
(ejecutadas en paralelo con `asyncio.gather`, no en serie).

**Bug real encontrado por discrepancia entre "archivos esperados" y
"archivos devueltos", no por un error explícito:** el primer intento
devolvió 111 archivos pero registró 172 advertencias de "no matcheó el
patrón esperado" — una proporción demasiado alta para ignorar. La causa:
el enlace que el parser usaba (`entry_link entry_action_download`) solo
existe con esa clase exacta para archivos que OneDrive NO puede
previsualizar (los ZIP de boletines). Para tipos previsualizables —la
mayoría de archivos en `servicios_financieros` son XLSX— esa misma
posición usa `entry_link ilightbox-group` en su lugar. La solución no fue
añadir una segunda variante de clase al regex, sino cambiar de ancla por
completo: cada entrada de archivo también tiene un botón de descarga
dedicado (`class='entry_action_download '`, sin el prefijo "entry_link"),
presente y con la misma forma para cualquier tipo de archivo, con su
propio atributo `download='...'` dando el nombre con extensión
directamente — más simple y más robusto que perseguir cada variante de
clase que OneDrive pueda usar. Total final: 312 archivos en
`servicios_financieros` (frente a 111 con el bug, y ~68 solo con las
tablas estáticas antes de conectar OneDrive). → ROADMAP.md

### MIES/Ministerio de Desarrollo Humano, portal `infoMIES`

**Investigado 2026-08-30, pedido explícito de Daniel** después de haber
perdido confianza en la pasada anterior de SUT ("I'm starting to doubt
you a little"). Verificado en vivo con fetches reales, no por inferencia
de nombres de dataset. **Conclusión: sí hay un gap real, y es grande —
distinto del caso SUT.**

**Dominios comprobados de nuevo, en vivo:**
- `mies.gob.ec` — NXDOMAIN, reconfirmado.
- `inclusion.gob.ec` — conecta en el puerto 443, negocia TLS, pero la
  conexión se resetea después de enviar el `GET` (`schannel: server
  closed abruptly` / `Connection was reset`) — peor que "certificado
  expirado" como decía la nota anterior, pero el efecto práctico es el
  mismo: inutilizable.
- `desarrollohumano.gob.ec` y `www.desarrollohumano.gob.ec` — timeout de
  60s+ reconfirmado en la raíz, mismo patrón de hosting compartido ya
  documentado para `trabajo.gob.ec`.

**El hallazgo real estaba en un subdominio que ninguna pasada anterior
probó: `info.desarrollohumano.gob.ec`** ("infoMIES — información
estadística y geográfica", sitio Joomla, HTTP 200 en <2s en cada
página probada). Se llegó a él leyendo el campo "Fuente original" de un
dataset CKAN real (`get_dataset_info` sobre
`mdt-datos-abiertos-segundo-trimestre-2026-usuarios-de-unidad-de-atencion`),
que apunta a `https://info.desarrollohumano.gob.ec/index.php/informacion`
— el mismo patrón que ya había funcionado para encontrar `sut.trabajo.gob.ec`
en la fuente declarada de un dataset. Confirma otra vez la lección de la
Séptima pasada: el campo "fuente original" de un dataset CKAN es más
confiable que adivinar subdominios.

**Organización CKAN existente (`ministerio-de-inclusion-economica-y-social`,
mostrada como "Ministerio de Desarrollo Humano", 27 datasets, activa,
última actualización 2026-07-17):** dos series **trimestrales** —
"Bonos y Pensiones" y "Usuarios de Unidad de Atención" — desde el
Cuarto Trimestre 2023 hasta el Segundo Trimestre 2026. Ya alcanzable
hoy con `search_organizations`/`get_organization_info`/
`list_dataset_resources`/`preview_resource_data`, sin cliente nuevo.

**Lo que el portal `info.desarrollohumano.gob.ec` tiene y CKAN NO
tiene — confirmado descargando cabeceras reales, no solo listando
enlaces:**

1. **Bases de datos MENSUALES, no trimestrales**, para las mismas dos
   series de arriba, bajo un sistema de descargas Joomla
   (`?download=ID:slug`), un año por página:
   - Aseguramiento No Contributivo (inclusión económica):
     `/index.php/usuarios-de-inclusion-economica/usuarios-externos-ie/{año}-bdd-anc`,
     años 2019-2026 confirmados, con enero-julio 2026 ya publicados.
   - Usuarios de Unidad de Atención del SIIMIES (inclusión social):
     `/index.php/usuarios-y-unidades-de-inclusion-social/usuarios-externos-is/{año}-externos-is`,
     años 2020-2026 confirmados, mismo patrón mensual.
   - Verificado con `curl -I` real sobre un enlace de julio 2026:
     `2026_BASES_ASEGURAMIENTO_NO_CONTRIBUTIVO_JULIO_EXTERNO.rar`,
     **109.8 MB**, `Content-Type: application/x-rar-compressed`. El
     formato `.rar` ya está descartado explícitamente en este proyecto
     (riesgo de subprocess/CVE, ver sección "Formatos y tipos de
     recursos") — pero eso solo bloquea la *lectura* del contenido, no
     el catalogar metadata + URL directa, igual que SIPA/Superbancos con
     archivos grandes.
2. **Boletines Zonales**, un archivo real y aparentemente discontinuado:
   9 zonas (`zona-1-bz` … `zona-9-bz`), cada una con años 2017-2021 (no
   más recientes, a diferencia de las BDD de arriba) y ~11-12 boletines
   mensuales por año-zona vía el mismo sistema `?download=ID:slug`
   (confirmado en `zona-1-bz/2021-bz1`: 11 meses, enero-noviembre).
   Con 9 zonas × 5 años × ~11 meses, un archivo potencial de várias
   centenas de reportes — sin confirmar el formato exacto de archivo
   (no se descargó ninguno, solo se contaron los enlaces).
3. **Dos dashboards Power BI embebidos, sin exportación directa** (mismo
   patrón ya documentado para SUT y Superbancos): uno en
   `/index.php/sinepidpam` (tenant Power BI `dbc77c07-...`, distinto del
   tenant de SUT) y otro enlazado desde `/index.php/informacion` bajo
   "reportes-dinamicos" (mismo tenant). No abiertos con browser en esta
   pasada — solo confirmada la presencia del iframe, no su contenido.
4. **Sin explorar todavía en esta pasada:** `geoportal.desarrollohumano.gob.ec`
   (geoportal propio, enlazado desde el nav — visualizador de mapas, sin
   confirmar si expone WFS/descarga de vectores como el geoportal de
   SIPA), `/index.php/biblioteca`, `/index.php/documentos-metodologicos`,
   `/index.php/estudios` (contenido no inspeccionado más allá de
   confirmar que las páginas cargan).

**Diferencia clave con el caso SUT:** en SUT, el "gap" resultó ser una
serie histórica real *pero solo visualizable* (Power BI, sin descarga
directa) — automatizarlo requiere reproducir el propio embed. Acá, la
serie mensual real *sí tiene un enlace de descarga directo* (Joomla
`?download=`, sin JS, sin AJAX) — mucho más parecido en dificultad a
SIPA/Superbancos que al caso SUT. Construir un cliente para esto es
factible con el mismo patrón ya usado en el proyecto (scraping de
páginas índice + metadata/URL, sin descargar los `.rar`).

Lección repetida una tercera vez en este proyecto (Registro Civil,
Superbancos, ahora MIES): un dominio institucional "caído" no significa
que el ministerio no tiene datos vivos — casi siempre hay un subdominio
o portal separado que sigue funcionando, y el campo "fuente original" de
un dataset CKAN real es la forma más confiable de encontrarlo, más que
adivinar patrones de URL.

### CENACE — `info-operativa`, confirmado snapshot-only, cliente construido

Continuación directa de la Octava pasada, que había dejado la URL
confirmada pero sin decidir si había una serie histórica detrás. Esta vez
se manejó el browser en vivo por las 5 pestañas (Producción/Demanda
Tiempo Real, Información Operativa Diaria, Acumulada Mensual, Acumulada
Anual) mirando `read_network_requests` en cada clic: cero llamadas
AJAX/JSON en todo el recorrido, solo la carga inicial del HTML y una
imagen de logo. Los 5 tableros están todos ya presentes en el DOM desde
la primera carga (confirmado viendo el heading "INFORMACIÓN OPERATIVA
DIARIA" en el árbol de accesibilidad antes de haber clicado esa pestaña)
— JS solo alterna visibilidad, no hace fetch.

Contenido real de cada tablero, confirmado con texto visible:
- **Producción Tiempo Real**: instante actual (ej. domingo 30-ago,
  Producción Total 97 995 MWh acumulados del día corriendo).
- **Demanda Tiempo Real**: instante actual, con mapa de Ecuador por
  empresa distribuidora (CNEL Guayaquil, E.E. Quito, etc.).
- **Información Operativa Diaria**: el día completo *anterior* (jueves
  27-ago cuando se probó un domingo 30), no el día en curso.
- **Acumulada Mensual**: mes a la fecha ("Agosto de 2026, hasta el día
  27").
- **Acumulada Anual**: año a la fecha ("2026, hasta el día 27 de
  agosto"), incluye "Demanda máxima histórica: miércoles 15 de julio de
  2026" como único dato que asoma algo más allá del año en curso, pero
  sigue sin ser una serie consultable.

Conclusión: **no hay serie histórica ni selector de fecha en ninguna
pestaña** — cada una es una vista "a este instante" distinta (ahora/
ayer/mes a la fecha/año a la fecha), no una base de datos con historia
consultable. Confirma la sospecha de la Octava pasada, ahora con
evidencia directa en vez de inferencia por ausencia de enlaces de
descarga.

Construido `helpers/cenace_client.py` (`get_cenace_tablero`) igual: el
snapshot en sí es información real y sin duplicado en el resto del MCP
(mezcla de generación eléctrica y demanda nacional en vivo). El HTML
descargado con un GET plano (~260 KB) contiene:
- Los 6 números de resumen por tablero en `<div class="resumen-box
  CLASE"><div>ETIQUETA</div><div>VALOR</div></div>` — separador de miles
  con U+00A0 (NBSP), no espacio normal (`"97\xa0995"`), hay que limpiar
  ambos o el `int()` revienta.
- El desglose por distribuidora (19 entidades CNEL/empresa eléctrica) en
  `demanda_tiempo_real` vive en dos sitios redundantes: un mapa SVG con
  `<title>NOMBRE&#10;NNN MW</title>` por región, y un gráfico de barras
  Plotly con los mismos datos en un array `"text"` de strings tipo
  "1011 MW (25.0%)". Se usó el SVG por ser trivial de regexear; el Plotly
  necesitaría decodificar un array `bdata` float64 en base64 para lo
  mismo, sin ganancia real.
- El desglose por planta/tipo de combustible (Coca Codo, Paute, Mazar,
  Gas Natural, etc.) y la curva de generación de 24h SÍ existen en la
  página, pero solo dentro de `Plotly.newPlot(...)` — cada gráfico trae
  su propio blob de +15 KB con el tema/colorscale completo de Plotly
  antes de llegar al array de datos real. Deliberadamente no se scrapeó
  esto: los 6 números de resumen ya cubren el valor real del tablero: si
  hace falta el desglose por planta en el futuro, hay que aislar el
  primer `[{...}]` después de cada `Plotly.newPlot("ID",` y antes de
  `,{"template"`.

`www.cenace.gob.ec` falló con `CERTIFICATE_VERIFY_FAILED` contra el
bundle certifi de httpx — mismo patrón exacto ya visto en
`censoecuador.gob.ec` y `superbancos.gob.ec` (falta una CA intermedia en
certifi, no un certificado roto/expirado). Añadido a
`_OS_TRUST_HOST_SUFFIXES` en `helpers/tls.py`, mismo fix, verificación
completa intacta.

### SRI — búsqueda de RUC por razón social, API moderna sin CAPTCHA

Pedido explícito de Daniel: agregar búsqueda por nombre de empresa/razón
social al lookup de RUC exacto ya construido (`get_sri_ruc_info`). El
formulario de búsqueda por nombre "clásico"
(`/facturacion-internet/consultas/publico/ruc_consulta.jsp`, el mismo
dominio legacy que sirve el lookup por RUC exacto) sí existe, pero trae un
widget `visualcaptcha` (`codigoCaptcha`/`j_captcha_response`) — completar
CAPTCHAs está fuera de los límites de este proyecto, así que esa ruta
quedó descartada sin construir nada sobre ella.

Manejando el browser sobre la app Angular actual de srienlinea.sri.gob.ec
(`/sri-en-linea/SriRucWeb/ConsultaRuc/Consultas/consultaRuc`, a la que la
página legacy redirige por JS) se encontró la ruta real: una API REST en
JSON completamente distinta, sin CAPTCHA, confirmada con `curl` plano:

1. `sri-catastro-sujeto-servicio-internet/rest/ConsolidadoContribuyente/cantidadObtenidaPorRazonSocial?razonSocial=X`
2. `.../numerosRucPorRazonSocialToken?razonSocial=X`
3. `.../obtenerPorNumerosRuc?ruc=A&ruc=B&...` (lote completo en una sola llamada)

Confirmado en vivo que el lookup por RUC exacto de la app moderna usa la
misma familia de API (`obtenerPorNumerosRuc` con un solo `ruc=`) — es
decir, la API moderna cubre ambos casos (RUC exacto y búsqueda por
nombre) con datos más ricos que el scrape HTML legacy (régimen,
representantes legales, agente de retención, contribuyente
especial/fantasma/con transacciones inexistentes). No se migró
`get_sri_ruc_info` a esta API porque ya estaba construido y probado sobre
el scrape legacy — `search_sri_ruc` (nuevo) usa la API moderna solo para
el caso de búsqueda por nombre, que es lo que realmente pedía el gap.

El servidor limita ambos pasos 1 y 2 a 100 coincidencias (confirmado en
vivo con "BANCO" y con "SA", dos términos deliberadamente amplios: ambos
devolvieron exactamente 100) — así que un conteo de 100 se reporta como
"al menos 100", nunca como un total exacto.

---

## Undécima pasada — IG-EPN Búsqueda de Informes

**Pedido de Daniel:** construir el ítem del roadmap marcado como "el más
simple" de la lista de pendientes. Resultó serlo mucho menos de lo que su
propia descripción sugería.

**Lo que se sabía antes de esta pasada** (Séptima pasada): que
`igepn.edu.ec/servicios/busqueda-informes` era "un formulario de búsqueda
real... filtrable por tipo/volcán/fecha, sin login visible", sin haber
confirmado el formato de resultado.

**Lo que se descubrió al construirlo:**

1. **No es la página que parece.** `www.igepn.edu.ec/servicios/busqueda-informes`
   solo incrusta un `<iframe>` — el formulario real vive en un subdominio y
   una app completamente distintos: `informes.igepn.edu.ec/igepn-registro-web/pages/public/Informes.jsf`,
   una app JSF/PrimeFaces con su propia sesión.
2. **Sin URL estable por documento**, a diferencia de cualquier otra fuente
   ya integrada en este proyecto. El flujo real: GET inicial (cookie de
   sesión + `javax.faces.ViewState`, un token opaco de estado guardado en
   el servidor) → POST AJAX del botón "Buscar" (`Faces-Request:
   partial/ajax`, responde con XML `partial-response` que re-renderiza
   todo el formulario, incluida la lista de resultados y un ViewState
   nuevo) → POST plano (sin AJAX; en el browser real esto se ve como
   `net::ERR_ABORTED` porque el navegador lo trata como descarga de
   archivo, no como navegación) del botón "Descargar Informe" de una fila
   específica, reusando la misma sesión y el ViewState de la búsqueda.
   Confirmado real de punta a punta: PDF de 137 KB descargado y con texto
   extraíble (el informe diario del volcán Sangay del 31-dic-2022).
3. **Los filtros "Tipo de informe" y "Volcán" del propio sitio no acotan
   resultados en el servidor — bug real de la aplicación, no error de
   scraping.** Se confirmó de la forma más rigurosa posible: se abrió la
   página en un browser real, se hizo un hook a `jQuery.ajax` para capturar
   el payload exacto que el propio widget envía al elegir un volcán y
   pulsar "Buscar", y se repitió ese payload byte-a-byte vía `httpx` —
   incluidos los campos de rango de fechas que el tab "AÑO" deja con
   valores por defecto ocultos (`fechaInicioId`/`fechaFinId`, últimos 365
   días desde hoy) que no eran obvios sin capturar el tráfico real. Aun así,
   `volcanId_input=83` (Tungurahua) devolvía una mezcla de Cotopaxi, El
   Reventador, Sangay, Cuicocha... Probado también con departamento +
   volcán sin tipo, con tipo + volcán, con año distinto — mismo resultado
   en todos los casos. Solo "Tipo" (`departamentoId`, Sísmico=78/Volcánico=79)
   y "Año" filtran de verdad.
4. **Decisión de diseño resultante:** `search_informes_igepn` solo envía
   Tipo y Año al servidor (los dos únicos filtros reales), pide la página
   más reciente (hasta 30 filas, orden descendente por fecha de
   publicación — confirmado, no asumido) y filtra "Volcán"/texto libre
   client-side sobre esa página, con el mismo enfoque de "reciente y no
   exhaustivo" que ya usa `search_sismos` sobre el feed CSV de sismos — no
   una promesa de cobertura completa del archivo histórico.
5. **Nombres de informe duplicados el mismo día.** Los informes diarios
   volcánicos de una misma fecha pueden compartir exactamente el mismo
   "Nombre" para volcanes distintos (ej. "Informe Diario 2022-365" para
   El Reventador y para Sangay el mismo día) — `get_informe_igepn` exige
   `volcan` para desambiguar cuando eso ocurre, en vez de descargar el
   primero que encuentre silenciosamente.
6. **Reutilización de código:** `helpers/pdf_reader.py` no tenía forma de
   extraer texto de bytes ya descargados (todo pasaba por `download_bytes`
   con una URL) — se separó `extract_text_from_bytes()` de `read_pdf()`
   para que `get_informe_igepn` reutilice el manejo de pypdf/rangos de
   página en vez de duplicarlo, ya que aquí no hay URL que descargar con
   `download_bytes`.

---

## Duodécima pasada — Superbancos boletines OneDrive, sistema de índices editoriales del BCE, catálogo BCEData y archivo IEM (2026-08-30/2026-09-01)

### SIPA/MAG — precios mayoristas descartados como fuente de alta frecuencia (2026-08-31)

Daniel trajo una tabla propia de candidatos de alta frecuencia; cruzada
contra el estado real del proyecto, "precios mayoristas" de SIPA/MAG no
calificó. Dos páginas revisadas, ninguna es diaria/quincenal: "Precios
Mayoristas" (boletines PDF mensuales, ya cubiertos como uno de los 12
archivos del módulo económico) y `precios-referenciales` — el "api"/"json"
que aparecía en su HTML era solo el token CSRF de Joomla, falso positivo.
`precios-referenciales` en realidad enlaza a "Mercado Mayorista Quito/
Guayaquil/Cuenca", cada uno un PDF embebido
(`descargas/mercados/precios_referenciales/{ciudad}_precios_referenciales_2026.pdf`)
con los rangos de precio del Decreto Nº1438 vigentes — un documento
regulatorio de piso/techo de precio, con fecha de emisión y vigencia
mensual (confirmado: "Fecha de emisión: 4 de agosto de 2026", vigente desde
el 4 de septiembre), no una serie de observaciones diarias de mercado. El
archivo se sobreescribe en el mismo nombre cada vez — sin historia. Bajo
valor como para priorizarlo (3 PDFs, una foto del mes, sin serie), pero
real y fácil si algún día se justifica. La app móvil "cgsin.precios" sigue
sin explorar — podría ser la fuente diaria real detrás de escena, no
confirmado.

### Superbancos — widget OneDrive de Boletines Financieros descifrado (2026-08-30, pedido explícito de Daniel: "fix!")

El diagnóstico inicial de la Séptima pasada ("URLs firmadas de corta
duración, no descifrable sin más") era incorrecto. Se resolvió conduciendo
el widget real en un browser (`mcp__Claude_Browser__*`), capturando el POST
que dispara (`wp-admin/admin-ajax.php`,
`action=shareonedrive-get-filelist`) con `listtoken`/`account_id`/
`drive_id` (atributos `data-*` del propio widget) y `_ajax_nonce`
(`ShareoneDrive_vars.refresh_nonce` inline en la página) — los cuatro
valores están en el HTML estático de la página, sin sesión ni cookies,
confirmado replicando la llamada con `httpx.post` puro. Las URLs de
descarga que devuelve son un proxy same-site
(`action=shareonedrive-download`) estable, no un token de Microsoft Graph
de corta duración — otra suposición incorrecta corregida.

`boletines_financieros` ahora trae **224 archivos verificados en vivo**:
1997-2008 desde la tabla estática + carpetas "Año 2009"…"Año 2026" (12
boletines/año, 2026 con los meses publicados hasta la fecha) desde
OneDrive, con nombre, tamaño y fecha de modificación reales. Un bug real de
extracción (el nombre se tomaba del `data-name` del `<div>` contenedor, que
no lleva extensión, en vez del `data-name` del propio `<a>` de descarga) se
detectó revisando la salida real end-to-end, no solo por los tests, y se
corrigió antes de cerrar el ítem.

### BCE — BCEData: auditoría viva de cobertura, resultado del primer barrido completo (2026-09-01)

`audit_bce_catalog` corrió por primera vez sobre el catálogo completo:
**78/78 grupos y 2.360 series cargaron correctamente**; de 154
combinaciones frecuencia/unidad probadas por `auditar_grid=true`, 108
devolvieron valores y **46 recibieron una página HTML de rechazo por la
propia política de seguridad del BCE, con HTTP 200** — no hay que tratar
esas 46 como datos ausentes ni como error JSON del servidor, es un
bloqueo explícito del origen disfrazado de éxito HTTP. La auditoría
también registra si existe algún marcador explícito de revisión
(campo de revisión/version, `ETag`/`Last-Modified`); comprobación en vivo
2026-08-31: BCEData responde 200 pero no publica ninguno, así que la
comparación por contenido sigue siendo la única evidencia disponible.

### BCE — sistema genérico de páginas "índice" editorial, descubierto 2026-09-01

Investigando el ítem de paquetes sectoriales, se encontró que BCE publica
~35 páginas cuyo slug termina en "-indice(s)" (localizadas vía su propio
`wp-sitemap-posts-page-1.xml`), cada una un archivo histórico completo (año
por año, algunas desde 2004-2010, o semana por semana) para una serie de
publicación con nombre propio: boletines sectoriales, índices de precios/
confianza, compra y venta de divisas, balanza de pagos, boletín monetario
semanal, remesas, etc. Dos formas de widget, ambas estáticas (sin AJAX,
todo presente en el HTML inicial — confirmado comparando bytes crudos vs.
DOM del navegador): `.bce-gi` (pestañas por año → tarjetas con período +
formato) y `.bce-gi-weekly` (tarjetas de año → meses → enlaces con número
de semana + fecha).

**Construido:** `search_bce_indices`/`get_bce_indice_archivo`
(`helpers/bce_indices_client.py`). El catálogo se construye descubriendo
las páginas candidatas en el sitemap y leyendo cada una una vez (cacheado
6h); `search_bce_indices` devuelve solo resúmenes (para no inflar la
respuesta), `get_bce_indice_archivo` lee los archivos ya cacheados de una
página, con filtro por año y tope de resultados.

Verificado en vivo extremo a extremo: 30 de 36 páginas candidatas exponen
realmente el widget (las otras 6, p. ej. `memoria-anual-indice`, solo
cargan el CSS del plugin pero no tienen contenido publicado con este
sistema — se omiten del catálogo, no son un bug). Dos bugs reales de
parseo corregidos durante la verificación en vivo: (1) el lookahead que
separa un panel de año del siguiente confundía `bce-gi-panel` con
`bce-gi-panelhead` (prefijo compartido) y devolvía cuerpos vacíos; (2) en
`.bce-gi-weekly`, todo panel de año que no es el activo lleva un atributo
`hidden` en vez de cerrar el tag con `>` a secas — el regex original solo
aceptaba la forma activa y silenciosamente perdía 7 de los 8 años de
boletín monetario semanal hasta corregirlo.

### BCE — paquetes sectoriales resueltos vía el sistema de índices (2026-09-01)

4 de 5 paquetes sectoriales quedaron resueltos por el sistema de índices de
arriba: petróleo (`boletin-analitico-del-sector-petrolero-indice`, 67
archivos, 2006-2026), minería (`boletin-analitico-del-sector-minero-indice`,
26, 2016-2026), cemento (`estadisticas-de-cemento-indice`, 11, 2025-2026) y
compra/venta de divisas (3 páginas índice distintas, mensual y trimestral,
2010-2026). Sigue pendiente agricultura — no se encontró ninguna página BCE
dedicada (ni en el sitemap de índices ni en el menú de "Estadísticas");
probablemente vive en otra institución (MAG/INEC), no en BCE.

### BCE — Estudio Mensual de Opinión Empresarial y coyuntura, resuelto parcialmente (2026-09-01)

Vía el sistema de índices de arriba: expectativas económicas
(`indice-de-expectativas-de-la-economia-indice`, 43 archivos, 2023-2026),
confianza del consumidor
(`indice-de-confianza-al-consumidor-icc-indice`, 198, 2009-2026), inflación
(`boletin-mensual-de-inflacion-indice`, 268, 2004-2026) y ciclo económico
(`reporte-de-indicadores-del-ciclo-economico-...-indice`). Sigue pendiente
mercado laboral y pobreza/desigualdad — ninguna página índice encontrada
para esos dos, no investigado más allá del sistema de índices.

### BCE — catálogo de "Últimas Publicaciones" (construido 2026-09-01)

`search_bce_publicaciones` (`helpers/bce_publicaciones_client.py`).
Confirmado en vivo: la página renderiza una sola tabla HTML estática vía un
shortcode (`bce-ultimas-publicaciones`) — sin AJAX, sin ruta `wp-json`
propia, sin paginación. Extrae fecha (texto español largo, parseado a
ISO), título, URL directa y formato — el formato se deriva de la extensión
de la URL, no del ícono decorativo de la fila (confirmado en vivo: dos
filas con el mismo formato real HTML usan íconos `file-web` distintos
según criterio editorial, uno de ellos genérico "gráfico"). Verificado en
vivo extremo a extremo contra la página real: 30/30 filas parseadas
correctamente, cero fechas o formatos sin reconocer. Límite real, no
solucionable desde esta página: solo expone su ventana rodante (~30
publicaciones más recientes), sin parámetro de fecha ni paginación — no es
un archivo histórico completo. Sigue pendiente: Cifras Económicas del
Ecuador y cualquier calendario de publicaciones futuras viven en páginas
distintas, no investigadas todavía.

### BCE — IEM: lectura de tablas, barrido en vivo sobre 78 tablas del boletín vigente y 4 boletines de la era ZIP (2026-09-01)

Sobre las 78 tablas del boletín vigente: 77 (98.7 %) se extraen ya como
`series_ancho`/`tabla_larga`/`series_matriz`; la única `vista`
(`iem-1111-e`, "Encaje Legal") es de periodicidad semanal con columnas
Año/Mes/Rango dispersas y una hoja de cálculo interna del BCE — un caso
genuinamente único, no una familia recurrente.

Repetido sobre 4 boletines de la era ZIP (No. 1854, 1900, 1950, 1975):
encontró un bug real, no una forma de tabla nueva — 4 miembros del ZIP del
boletín No. 1975 (`IEM-316b/312b/315a/322a.xls`) resultaban en `ValueError`
porque son en realidad XLSX modernos (contenedor ZIP OOXML) con extensión
`.xls` heredada; `xlrd.open_workbook` fallaba directo. Corregido con
sniffing de bytes (`raw.startswith(b"PK")`) en vez de confiar en la
extensión, igual que la regla ya documentada en `CLAUDE.md` para el campo
`format` de CKAN — ver `_open_legacy_zip_member` en
`helpers/bce_iem_client.py`. Tras la corrección, cero errores en los 4
boletines muestreados; los 4-7 `vista` restantes por boletín son tablas
legadas con jerarquías de encabezado genuinamente irregulares (tasas por
semana, PIB por industria con encabezados fusionados a varios niveles), no
una familia repetible. No se identificó ninguna familia de formato
adicional que justifique un normalizador dedicado; la combinación actual
de extractores + vista honesta ya cubre el archivo.

### BCE — BCEData ↔ IEM, primer barrido de candidatos (2026-09-01)

`compare_bce_sources` corrió por primera vez sobre el boletín disponible:
77 candidatos, una tabla IEM sin traslape y 2.352 etiquetas solo BCEData;
72 son posibles componentes de tabla, cuatro posibles tabla/grupo y solo
una posible equivalencia directa. Ninguna se trató como duplicado
confirmado sin revisar valores y metodología primero — ver la revisión
manual del 2026-09-02 más abajo.

---

## Decimotercera pasada — fronteras exactas del archivo IEM, equivalencias BCEData↔IEM confirmadas, INAMHI, aviación civil, SEPS, CNIG, indicadores diarios ampliados (2026-09-02)

### BCE — IEM: las tres eras del archivo histórico 1996-2026, fronteras exactas por búsqueda binaria en vivo

El archivo completo del boletín IEM (No. 1727-2093, enero 1996 - hoy)
resulta ser **tres eras**, no dos, encontradas por búsqueda binaria en vivo
por boletín:

- **No. 1976-2093 (octubre 2016→hoy, ~118 boletines, ~32 %).** XLSX
  individuales por tabla. Ya cubierto antes de esta pasada.
- **No. 1854-1975 (agosto 2006 - septiembre 2016, ~122 boletines, ~33 %),
  construido 2026-09-02.** La página no linkea XLSX individuales, pero sí
  un ZIP de la publicación completa (`archivos_completos`, tipo `zip`) que
  ya trae un archivo por tabla con el mismo esquema `IEM-{numero}`, solo
  que en `.xls` legado (no `.xlsx`) — confirmado en vivo con
  `list_zip_contents` sobre `IEM1975.zip` antes de construir nada.
  `_fetch_legacy_zip_tables` lista los miembros del ZIP como tablas
  (`table_id` con prefijo `iem-legado-` porque la numeración 1:1 contra la
  era moderna no está confirmada — vistos `IEM-315a.xls`,
  `5_SectorPetrolero.xls`, `7_GraficosIDEAC.xls` sin equivalente obvio
  hoy); `get_table` lee el miembro con `xlrd` (`.xls` legado) a través de
  un adaptador (`_XlsSheetAdapter`) que reutiliza sin cambios los mismos
  `_extract_wide_series`/`_extract_long_table`/`_extract_matrix_series` ya
  probados contra XLSX moderno. Encontrado y corregido en el proceso: xlrd
  no distingue int de float (todo número es float), así que un encabezado
  de año como `2025.0` rompía la regex de 4 dígitos de `_period_key`
  (`"2025.0"` → `.replace(".", "")` → `"20250"`) — el adaptador ahora
  normaliza floats enteros a `int`, igual que openpyxl. Verificado en vivo
  extremo a extremo contra boletines reales (No. 1975, No. 1900, No. 1950),
  no solo con mocks. 8 tests nuevos.
- **No. 1727-1853 (enero 1996 - julio 2006, ~126 boletines, ~34 %),
  construido 2026-09-02.** Confirmado en vivo (No. 1800, No. 1780) que
  estas páginas usan HTML pre-moderno de framesets — `<A HREF = ...
  TARGET="_top">` en mayúsculas y sin comillas — que enlazan páginas `.htm`
  por sección (`m{boletin}_{k}.htm`, ~60 por boletín). El dato en sí no
  está en ningún archivo descargable — vive como una `<TABLE>` HTML cruda
  embebida directamente en cada página de sección, con encabezados
  multinivel de ROWSPAN/COLSPAN genuinamente irregulares y contenido en
  `cp1252`. `_TableGridParser` (subclase de `html.parser.HTMLParser`, sin
  dependencia nueva — el mismo patrón ya usado en `sri_ruc_client.py`,
  adaptado porque esta era no cierra `</TR>`/`</TH>`/`</TD>`, así que el
  cierre implícito se infiere por el siguiente tag de apertura, no por
  `handle_endtag`) captura las celdas con su rowspan/colspan reales;
  `_expand_table_grid` las resuelve al algoritmo estándar de grilla
  rectangular. `table_id` se deriva del texto de sección
  (`_legacy_frameset_table_id`, ej. "1.1 Principales Indicadores
  Monetarios"), no del índice `k`, que no está confirmado estable. Expuesto
  siempre como vista de grilla (`formato: "vista"`, mismo contrato que
  `_inspect_xlsx`/`_inspect_legacy_xls`) — nunca se intenta wide/long/matrix
  aquí: la jerarquía de encabezados es irregular a propósito de sección en
  sección, adivinar una forma semántica sería menos honesto que mostrar la
  grilla real. **Verificado en vivo extremo a extremo contra el boletín No.
  1800 real**: 63 tablas descubiertas, valores de una fila de datos real
  (diciembre 1999, tabla "1.1 Principales Indicadores Monetarios") coinciden
  exactamente con el HTML fuente, celda por celda. 6 tests nuevos.

Con estas tres fronteras, el archivo completo 1996-2026 (367 boletines) es
legible hoy — sin hashing masivo confirmado todavía para las porciones
ZIP/frameset, y sin garantía de que cada una de las 126 secciones del
tramo más viejo tenga exactamente esta forma (no se revisaron los 126
boletines uno por uno, solo una muestra).

### BCE — BCEData ↔ IEM, dos equivalencias confirmadas con datos en vivo (revisión manual 2026-09-02)

1. **Confirmada — equivalencia directa.** `id_grupo=101` (BCEData, "4.1.4
   Ingresos y egresos por comercialización interna de derivados
   importados") ↔ `iem-414-e` (misma sección/título). Las 8 series de
   BCEData (4 productos × precio importación/venta nacional) igualan los
   valores de `iem-414-e` mes a mes hasta ~13 cifras significativas
   (ene-2025 verificado en las 4 líneas de producto). Es la misma tabla,
   republicada por dos rutas.
2. **Confirmada parcial — tabla↔grupo.** `id_grupo=65` ↔ `iem-423-e`
   ("Salario Básico Unificado y Componentes Salariales"): la serie
   "SALARIO REAL PROMEDIO" de BCEData iguala exactamente la segunda fila de
   `iem-423-e` (ene-2025: 122.414726663655 en ambas). Pero `id_grupo=65`
   solo expone esa fila — el SBU nominal (fila 1 de la tabla IEM,
   548.2638888888889 constante) no aparece bajo ninguna unidad de ese
   id_grupo. Confirma que la clasificación
   "posible_correspondencia_tabla_grupo" del tool es correcta aquí:
   cobertura parcial, no equivalencia completa.

Los otros tres candidatos "tabla↔grupo" (riesgo país↔producción petrolera,
derivados↔IPC, salario↔IPP) son falsos positivos por similitud de
etiqueta — sin relación real, no revisados en detalle más allá de notar
que los títulos no corresponden.

### BCE — indicadores diarios: barrido completo del mega-menú, 4 archivos nuevos (2026-09-02)

Solo 4 de las 7 secciones de nivel superior de "Estadísticas" se habían
revisado en la Décima pasada. Las 2 no revisadas
(`estadisticas-del-sector-monetario-d-2`, `estadisticas-del-sector-fiscal`)
sí tenían el widget, y `estadisticas-del-sector-externo-d` — ya "revisada"
— tenía 7 widgets más que el barrido original no encontró por seguir solo
los que compartían archivo con indicadores ya conocidos. 4 archivos nuevos:

- `datos.json` (`view_ind_monetario`): Reservas Internacionales, Liquidez
  Total M2, Crédito al Sector Privado (empresas y hogares), Captaciones
  OSD (Total), Tasa Activa/Pasiva Referencial — mensual, 2000/2003/2015→hoy.
- `datos_fiscales.json` (`view_ind_fiscales`): Total Ingresos SPNF, Total
  Erogaciones SPNF, Resultado Global SPNF (% del PIB), Saldo Deuda Pública
  Interna — mensual, 2000→hoy.
- `datos_bpa.json` (`view_ind_externo_bpa`): Cuenta Corriente, Remesas de
  Trabajadores Recibidas (trimestral, 2016→hoy), Índice Tipo de Cambio
  Efectivo Real (mensual, 1995→hoy).
- `datos_cxt.json` (`view_ind_externo_cxt`): Saldo Balanza Comercial,
  Balanza Comercial no Petrolera, Exportaciones de Bienes, Importaciones
  de Bienes — mensual, 1990→hoy. Usa "Código Variable Dinámica" como los 9
  archivos originales, no "id_serie".

Los 3 archivos nuevos "id_serie" (`datos.json`/`datos_fiscales.json`/
`datos_bpa.json`) no tienen "Código Variable Dinámica" — el código de serie
es un int en `id_serie`, y añaden un campo "Grupo" que los 9 archivos
originales no tienen. `_codigo()` unifica ambos esquemas detrás de una
sola interfaz string. Catálogo total: 49 series (antes 29). Verificado
completo contra la página de inicio de `contenido.bce.fin.ec`, que agrega
los widgets de todas las secciones en un solo lugar (40 `data-dd-title`
distintos) — los 40 resuelven ahora a un archivo conocido.

### BCE — índices de precios de comercio exterior (IPX/IPM/ITI), resuelto 2026-09-02

BCEData (`id_grupo=134`, "3.5.3 Índices IPX - IPM - ITI") ya cubre las tres
series *agregadas* (1990-01→2026-06). De las tres páginas dedicadas (fuera
del sistema de índices porque su slug no termina en "-indice(s)"):
`serie-historica-indices-de-precios-...` resultó un duplicado exacto de esa
misma serie (cruzado en vivo, ITI jun-2026 = 90.2604172608485 en ambos) —
descartada. `indices-de-precios-de-importacion` e
`indices-de-precios-de-exportacion` sí aportan detalle real y ausente en
BCEData: precios/valor/volumen desagregados por categoría de uso económico
(importaciones — combustibles, materias primas, bienes de consumo/capital)
y por producto individual (exportaciones — petróleo, camarón, banano,
cacao, oro, rosas, etc.). Las tres páginas usan un widget distinto al
`.bce-gi`/`.bce-gi-weekly` de `bce_indices_client.py` (un solo archivo
vigente por página, sin archivo por año), así que se construyó
`search_bce_precios_comex` (`helpers/bce_precios_comex_client.py`), con las
dos páginas útiles hardcodeadas (mismo patrón que `_EXTRA_TOPICS` en
`helpers/inec_client.py`) y cada archivo real scrapeado en vivo.

### INAMHI — `geoservicios.inamhi.gob.ec` resuelto (2026-09-02)

WMS GetCapabilities expone 222 capas (workspace `geonode`): normales
climáticas de precipitación 1985-2015, ~180 composites diarios de
anomalías de lluvia, grillas del modelo WRF (precipitación/temperatura/
humedad/presión/viento), límites de cuencas/provincias/cantones/
parroquias. WFS confirma 199/222 con datos de atributos reales vía
GetFeature (JSON); las 23 restantes (grillas de normales y WRF) son solo
ráster, verificado con un GetFeature que devuelve error. TLS limpio con
httpx/certifi. Sin organización CKAN propia para INAMHI en ningún lugar
del proyecto — este cliente es la única cobertura automatizable hoy.
Limitación real: no existe una capa de estaciones con observaciones
puntuales de precipitación/temperatura/caudal — todo lo disponible vía WFS
son productos agregados por polígono (zonal stats, límites), no series de
estación cruda. Construido como `search_inamhi_capas`/
`get_inamhi_capa_datos` (`helpers/inamhi_client.py`).

### Aviación civil — IFIS (`www.ais.aviacioncivil.gob.ec`) resuelto (2026-09-02)

`/metar/{icao}`, `/notam?designador={icao}` y `/sigmet` son públicos sin
sesión — el link "Entrar" existe pero solo `/fpl/*` exige login; verificado
contra SEQM (Quito) y capturado en vivo un SIGMET activo de ceniza
volcánica del Reventador. El formato es HTML servidor (no texto de ancho
fijo ni JSON) — el texto crudo ICAO viene embebido en
`<div>`/`<td class="codificacion">` junto a una tabla de campos
decodificados en español, extraída de forma genérica campo→valor porque
cada campo lleva un sufijo numérico opaco que cambia por request. SIGMET
es a nivel de FIR completo (Ecuador tiene un solo FIR, SEFG) sin parámetro
de aeródromo. Un ICAO desconocido no da error: METAR devuelve "No existe
registro..." y NOTAM una tabla vacía. Construido como
`get_metar`/`get_notam`/`get_sigmet` (`helpers/aviacion_client.py`).

### SEPS — `estadisticas.seps.gob.ec` resuelto (2026-09-02)

Confirmado en vivo: sitio WordPress normal (200 vía httpx plano, sin
problema TLS), sin organización CKAN propia. 26 secciones reales entre
`estadisticas-sfps/` (22, cinco pestañas: Situación Financiera, Depósitos,
Cartera de crédito, Tasas de interés, Inclusión financiera) y
`estadisticas-eps/` (4) — cada una una lista de períodos con PDF/ZIP
directo o redirect `?sdm_process_download`/`?smd_process_download` (dos
grafías inconsistentes en la misma página, no un bug). Incluye
`sfps_reportes_calificacion_de_riesgos`, el objetivo original: boletines
PDF anuales 2020-2025 más corte a marzo 2026, 112 entidades calificadas.
Construido como `list_seps_secciones`/`get_seps_seccion_archivos`
(`helpers/seps_client.py`), mismo patrón que Superbancos. Al menos una
sección (Alivio Financiero) tiene un período listado sin archivo
todavía — manejado como 0 archivos, no como error.

### CNIG — matriz de femicidios resuelto (2026-09-02)

`igualdadgenero.gob.ec` es el Consejo Nacional para la Igualdad de
*Género* confirmado (no confundir con Fiscalía, que publica cifras de
femicidios por separado, ni con los otros Consejos Nacionales para la
Igualdad). Su página "Violencia" (`/violencia/`) tiene 20 tablas
estadísticas en PDF vía WordPress download-monitor, incluida "Femicidios y
Homicidios Intencionales de Mujeres" — confirmado vivo, sin login ni
CAPTCHA. Gotcha real: el dominio raíz cierra la conexión TLS a
`curl`/`httpx` sin un User-Agent identificable (parecía caído); responde
200 con el User-Agent propio del proyecto — mismo patrón de filtrado ya
visto en `seps.gob.ec`. El PDF dice actualizarse "semanalmente" con datos
de Judicatura, Fiscalía e Interior, pero el archivo publicado hoy tiene
corte real al 09-abr-2023 y los 20 archivos comparten el mismo
Last-Modified (22-feb-2025, timestamp de migración) — "semanal" es la
intención declarada del indicador, no la cadencia real de lo publicado
ahora mismo. Construido como `search_cnig_femicidios`
(`helpers/cnig_client.py`).

---

## Decimocuarta pasada — ARCOTEL, SGR, SIPA geoportal y resumen de indicadores, MEF/SENAE, MINEDEC, y correcciones a boletín laboral anual/infoMIES/salarios sectoriales (2026-09-03)

### ARCOTEL — reportes estadísticos mensuales y boletín estadístico resueltos

Confirmado en vivo: `www.arcotel.gob.ec` es HTML estático plano (tema
WordPress "Sitio-32", sin JS/acordeón). **Reportes Estadísticos
Mensuales** (`/reportes-estadisticos-mensuales/`): serie ene-2017 a
jun-2026, ~2 meses de rezago (mejor que el ~4 estimado en la Octava
pasada). **Boletín Estadístico** (`/boletines-estadisticos/`, URL no
confirmada en el pase anterior — `/boletin-estadistico/` redirige aquí):
serie anual/temática 2015-2024. Ambas solo PDF, sin login/captcha.
Construido como `search_arcotel_reportes_mensuales`/
`search_arcotel_boletines` (`helpers/arcotel_client.py`).

### SGR — Informes de Situación (SITREP) y Biblioteca resueltos

`gestionderiesgos.gob.ec` (sitio WordPress, distinto del backend ArcGIS de
`helpers/sgr_client.py`) tiene un índice plano de 54 eventos adversos
2016-2026 con estado (EN CURSO/CERRADO/EN OBSERVACIÓN) — cada evento
enlaza a su propia página con los PDFs SITREP reales, organizados por
encabezados Nacional/Provincial/Cantonal (el evento "Época Lluviosa 2026",
aún abierto, tiene 700+ PDFs). Biblioteca (`/biblioteca/`) es un acordeón
`download-monitor` (mismo patrón de `helpers/cnig_client.py`) con
anidamiento real: 19 categorías de primer nivel, varias con subcategorías
por provincia, ~1660 documentos — resoluciones, planes de contingencia,
mapas de amenaza y rutas de evacuación por tsunami. Hallazgo real: una
parte de los enlaces de Biblioteca da 404 en vivo, sin patrón claro por
rango de id ni categoría — se expone como catálogo candidato, no garantía
de descarga; el formato se reporta desconocido porque `download.php` no
lleva extensión. Construido como `search_sgr_sitreps`/
`get_sgr_sitrep_archivos`/`list_sgr_biblioteca_categorias`/
`get_sgr_biblioteca_categoria_archivos` (`helpers/sgr_publicaciones_client.py`).

### SIPA — geoportal GeoServer (WMS/WFS) resuelto

El GeoServer real no vive en `/geoserver/*` (eso da 404 genuino de
Apache) sino en 24 endpoints "virtuales" por workspace
(`/<categoria>/<store>/wms|wfs`), descubiertos leyendo la config del
propio visor oficial (`/geovisor/config/dataconfig.js`). 277 capas WMS
confirmadas en vivo, 257 con WFS `GetFeature` real (una consulta devolvió
724.971 features con 20+ atributos reales por polígono — zonificación
agroecológica). `https://` sigue fallando en el handshake TLS,
reconfirmado. 20 capas son solo-WMS en 4 stores, incluyendo
`sigtierras/catastro_rural` (predios/construcciones, la más valiosa según
investigación previa) — WFS está deshabilitado explícitamente en el
servidor ahí ("Service WFS is disabled"). Gotcha real: el `<Name>` WMS va
sin prefijo pero el `<Name>` WFS lleva el prefijo del *store*, no de la
categoría — el cliente empareja por nombre base. Construido como
`search_sipa_geoportal_capas`/`get_sipa_geoportal_capa_datos`
(`helpers/sipa_geoportal_client.py`), mismo patrón que
`helpers/inamhi_client.py`.

### SIPA — Resumen de Indicadores Sectoriales resuelto, los otros 6 ítems del tablero son callejones sin salida

De los siete ítems nombrados bajo "tablero-dinámico/indicadores-sectoriales"
(hallazgo de 2026-08-31), seis resultaron callejones sin salida:
"Indicador Agroeconómico", "Indicador Agrosocial" y el tablero de
"Rendimientos Objetivos" son embeds genuinos de **Tableau Server**
(`bi.mag.gob.ec`, vía `servicios.mag.gob.ec/tableros/...` con JWT firmado)
— reproducirlo exige decodificar el protocolo de Tableau, esfuerzo
comparable al de `helpers/sut_powerbi_client.py`, fuera de alcance.
"Panorama Agroeconómico", "Atlas Agroeconómico" y "Hoja de Balance de
Alimentos" están cada uno atrapados en un flipbook JS de `fliphtml5.com`
con `bookConfig` codificado — confirmado en vivo para los tres. Pero la
misma página tiene un séptimo ítem no nombrado originalmente, **"Resumen
de Indicadores"**, que sí es real: una página Joomla estática con PDFs
mensuales directos, 2018-2026 confirmado en vivo (convención de nombre de
archivo distinta en 2018 vs. 2019+, cada año en su propia URL). Construido
como `get_sipa_resumen_indicadores`
(`helpers/sipa_resumen_indicadores_client.py`).

### MEF/SENAE — archivo fiscal corriente y recaudación aduanera resueltos

`finanzas.gob.ec/estadistica-nueva-metodologia-2017-2022/` redirige a
`www.economicoproductivo.gob.ec/...` (el host viejo presenta un
certificado TLS para el dominio nuevo, mismatch real). No es un solo
workbook como asumía el pase de la Quinta pasada — es un archivo corriente
de 76 XLSX reales (Ingresos y Gastos, Activos y Pasivos, BLL, Financiamiento
SPNF), publicaciones 2025-01 a 2026-09, metodología GFSM. Se agregó también
SENAE (`www.aduana.gob.ec/de-interes/tributos-recaudados/` — sin `www` no
resuelve): 60 archivos confirmados, sin cambios desde el pase anterior
(2012-2021, ADVALOREM/FODINFA/IVA/ICE/OTROS TRIBUTOS/TOTALES) — incluido
pese a estar desactualizado porque es la única fuente con desglose por
tipo de gravamen. Ambos expuestos vía `search_mef_fiscal(fuente="mef"|"senae")`
(`helpers/mef_fiscal_client.py`). Ojo con el alcance:
"Arancelarios"/"ADVALOREM" son solo el arancel, más chico que la
"recaudación aduanera" total que cita la prensa.

### MINEDEC — registro histórico de matrícula resuelto

`educacion.gob.ec/datos-abiertos-minedec/` (WordPress/Elementor, no CKAN)
expone 5 archivos reales, no los 2 implicados por el patrón de nombre
asumido antes: dos registros XLSX grandes
(`...2009-202X-Inicio.xlsx` ~139 MB — "202X" es un placeholder literal en
el nombre real, no un año — y `...2009-2024-Fin.xlsx` ~31 MB), un metadato
por cada uno y un diccionario de datos compartido, todos con
`Last-Modified` 2026-04/05 — vigente. El archivo de metadato "Fin" tiene
dos inconsistencias reales en su propio nombre (dice "MINEDUC" en vez de
"MINEDEC", y el rango de años está truncado). Distinto de la cobertura
CKAN ya existente de SENESCYT/educación superior. Construido como
`search_minedec_matricula` (`helpers/minedec_client.py`).

### Ministerio del Trabajo — Boletín Estadístico Anual, corrección al diagnóstico de "timeout"

El diagnóstico previo de "timeout" era impreciso: la página índice
(`trabajo.gob.ec/direccion-de-investigacion-y-estudios-laborales/`) viola
HTTP/1.1 con cabeceras `Transfer-Encoding` duplicadas (httpx/h11 la
rechaza correctamente por seguridad; `curl` la tolera) — un bug real del
WAF del origen (Citrix NetScaler), no un timeout. El dominio raíz
`trabajo.gob.ec` además falla por certificado (`*.trabajo.gob.ec` no cubre
el apex; usar `www.`). Con la página en vivo inutilizable, un snapshot de
Wayback Machine de enero 2024 (accesible esta pasada) reveló una tercera
edición (2021) y reconfirmó el nombre exacto de 2020 — las tres
(2020/2021/2022) reverificadas en vivo hoy. La página índice actual solo
enlaza ya la edición 2022, aunque 2020/2021 siguen descargables. No se
halló ninguna edición 2023-2025 pese a búsqueda en la API REST del propio
sitio y variantes de nombre de archivo plausibles — cobertura marcada
explícitamente como incompleta (3 ediciones, no la serie completa).
Construido como `search_trabajo_boletin_anual`
(`helpers/trabajo_boletin_anual_client.py`, lista fija sin scraping en
vivo).

### MIES/infoMIES — correcciones a "bases mensuales" y nueva serie de boletines zonales consolidados

"Bases mensuales" solo aplica al año en curso — todo año cerrado
(2019-2025) tiene un único archivo (diciembre), no 12, confirmado
reverificando en vivo cada año de ambas series (Aseguramiento No
Contributivo, Usuarios del SIIMIES). Se encontró además una serie nueva no
vista antes, "Reporte Boletines Zonales"
(`reportes-boletines-zonales-{año}`), un XLSX consolidado por año,
2021-2026, **aún actualizándose** (a diferencia de los boletines zonales
por zona, descontinuados desde 2021 y confirmados `.rar` vía HEAD). La URL
real de los boletines zonales por zona difiere de la adivinada en el pase
anterior. Construido como `search_infomies_bases_mensuales`/
`search_infomies_boletines_zonales` (`helpers/infomies_client.py`).

### Salarios mínimos sectoriales — veredicto "débil" de la Octava pasada revertido

El hallazgo nuevo: `trabajo.gob.ec/biblioteca/` (a diferencia de
`/salario-basico/` y `/tablas-sectoriales/`, que siguen sin responder) sí
carga — una página estática de ~2.3 MB con toda la biblioteca legal del
ministerio, cada documento real con un enlace estable
`download.php?id=<N>`, lo que sí permite enumerar por texto del título.
Confirmado en vivo: una entrada por año 2020-2025 (la mayoría con
XLS/XLSX y PDF del anexo firmado), nada antes de 2020, y sin tabla 2026 —
el Acuerdo MDT-2025-195 (2025-12-15) solo fijó el SBU en USD 482, la tabla
sectorial de 2025 sigue vigente por inacción según prensa (El Universo, El
Diario). Construido como `search_salarios_sectoriales`
(`helpers/salarios_sectoriales_client.py`).

---

## Infraestructura operativa

### Smoke test diario end-to-end (`.github/workflows/smoke.yml`, construido 2026-08-31)

`.github/workflows/smoke.yml` ejecuta diariamente `scripts/smoke_e2e.py`
(~39 de 68 tools cubiertos, antes 13, más 3 cadenas dinámicas list→get que
descubren un ID real en vivo para SUT/Superbancos/IG-EPN en vez de fijar
uno que pueda quedar obsoleto) contra un servidor recién levantado,
separado de `ci.yml` (que solo corre tests unitarios con HTTP mockeado en
cada push). GitHub avisa por correo a quienes ven el repo cuando una
ejecución programada falla — sin infraestructura de alertas nueva. Desde
2026-08-31 reintenta fuentes externas conocidas y distingue `degraded`
(CKAN con bloqueo regional o TLS de CENACE) de un fallo duro del servidor;
el resumen de Actions muestra las fuentes afectadas. Pendiente: alertas
específicas de cambio de esquema.

### `helpers/tls.py` — fallback "OS trust store" reemplazado por CA intermedia embebida (2026-09-02)

El smoke test diario falló en vivo (`get_cenace_tablero`, ejecución del
2026-09-02T13:38 en GitHub Actions) con `CERTIFICATE_VERIFY_FAILED`.
Diagnóstico con `openssl s_client`: `cenace.gob.ec`/`censoecuador.gob.ec`
(Sectigo "Public Server Authentication CA DV R36") y `superbancos.gob.ec`
(mismo emisor, variante "OV R36") nunca envían su CA intermedia en el
handshake — un error real de configuración del servidor, no un
certificado roto. El fallback anterior (`ssl.create_default_context()` sin
`cafile`, "OS trust store") funcionaba en una máquina de desarrollo
(Windows/macOS completan la cadena automáticamente vía la extensión AIA)
pero fallaba igual en un runner Linux limpio de GitHub Actions, que no
hace ese fetch. Corregido: las dos CAs intermedias (confirmado que ambas
encadenan a la misma raíz ya confiable en certifi, "Sectigo Public Server
Authentication Root R46") se descargaron y se embebieron en
`helpers/certs/sectigo_public_server_auth_intermediates.pem`;
`os_trust_context()` ahora construye el contexto desde `certifi.where()` +
ese bundle, determinista en cualquier plataforma. Verificado en vivo
contra los tres hosts tras el cambio. `certifi` pasó a dependencia
explícita (antes solo transitiva vía `httpx`).

---

## Decimoquinta pasada — `sisdatbi.arconel.gob.ec` confirmado login-gated, CELEC EP evaluado y descartado

**Pedido de Daniel 2026-08-30/2026-09-04:** revisitar los dos ítems abiertos
del sector eléctrico marcados "sin profundizar" en la Octava pasada.

### `sisdatbi.arconel.gob.ec` — confirmado con VPN, sigue descartado

Desde la red normal de este entorno, el host da **timeout TCP puro** en los
puertos 80 y 443 (`curl` exit 28, sin handshake TLS, sin respuesta HTTP) —
parecía caído o renombrado. Con VPN activada (2026-09-04) el host responde
de inmediato: **es un bloqueo geográfico/por rango de IP del lado del
servidor, no una caída real ni un dominio movido.** `arconel.gob.ec/
estadistica-del-sector-electrico/` sigue enlazando `sisdatbi.arconel.gob.ec`
como "SisdatBI" bajo "Consultas de Infraestructura y Transacciones", junto a
`reportes.arconel.gob.ec` (ya descifrado, ítem separado) bajo "Bases de
datos" — confirma que es el mismo enlace vigente, no un dominio obsoleto.

Con VPN: HTTP responde 301 a HTTPS; HTTPS sirve `<title>SISDAT - BI</title>`,
`<body id="login">`, plantilla AdminLTE, con un único `<form
class="form-signin">` que pide solo un campo `<input type="password"
name="txtupass">` (sin campo de usuario visible, sin rol de invitado, sin
iframe/embed público en el HTML servido). Es una aplicación PHP propia con
login obligatorio de punta a punta, no un dashboard tipo Power BI con modo
`reportEmbed` público. **Confirmado, no solo sospechado: descartar
definitivamente**, sin contenido alcanzable sin credenciales.

### CELEC EP — transparencia/rendición de cuentas evaluado, no se recomienda construir

Las páginas genéricas de transparencia (`celec.gob.ec/lotaip/` y los
reportes de gestión/financieros/plan-anual a nivel corporativo) son solo
shells de navegación con 1-5 links cada una. Las páginas sector-específicas
("Balance Energético Nacional", "Plan Maestro de Electricidad") tienen 1-2
PDFs estáticos, aparentemente los mismos documentos que CENACE Biblioteca ya
expone (Plan Maestro de Electricidad 2023-2032 ya catalogado ahí, ver
Octava pasada) — probable duplicado, no contenido nuevo.

El contenido real y sustancial vive en las páginas LOTAIP **por unidad de
negocio** (13 unidades: celecsur, cocacodo, electroguayas, hidroagoyan,
gensur, hidroazogues, hidronacion, hidrotoapi, termoesmeraldas,
termogasmachala, termomanabi, termopichincha, transelectric), cada una con
subpáginas por año. Confirmado en vivo: `celec.gob.ec/celecsur/lotaip/
transparencia-2023/` sola tiene 227 links reales a archivos XLS/XLSX/PDF.
Pero sigue la estructura literal LOTAIP estándar (organigramas, escalas
salariales, contratos, auditorías, presupuestos) — la misma que publica
cualquier institución pública ecuatoriana bajo la Ley Orgánica de
Transparencia y Acceso a la Información Pública, no información específica
del sector eléctrico. La cobertura es además inconsistente entre unidades
(`transelectric/lotaip/` solo tenía 1 link vs. 227 de celecsur).

**Recomendación: no construir.** Un scraper aquí sería de alcance similar a
SGR Biblioteca (13 unidades × ~6 años × ~20 literales) pero catalogando
cumplimiento administrativo genérico, no datos del sector eléctrico —
inconsistente con el criterio del proyecto de integrar solo fuentes que
aportan detalle sectorial real, no repetir filings de cumplimiento LOTAIP
que ya existen en cualquier institución.

---

## Decimosexta pasada — otras instancias CKAN municipales, geoportales de "Municipios Abiertos"

**Pedido de Daniel 2026-09-04:** buscar otros portales CKAN ecuatorianos más
allá de `datosabiertos.gob.ec` (nacional) y `cuencaendatos.cuenca.gob.ec`
(municipal, ya integrado como `source="cuenca"`).

### `datosabiertos.latacunga.gob.ec` — "Data Mashca", CKAN real confirmado

Encontrado vía búsqueda web ("CKAN Ecuador datos abiertos municipio").
Confirmado en vivo con la API estándar de CKAN
(`/api/3/action/package_list`): **15 datasets** — atenciones médicas
(incluida la del Patronato), catastro predial rural/urbano, adopción y
esterilización de mascotas 2025, emprendimientos en ferias, graduados del
CIEDES, inventario de establecimientos turísticos, ordenanzas vigentes
(marzo 2026), puntos wifi gratuitos, rutas de recolección de desechos,
sitios patrimoniales arquitectónicos, sitios seguros de evacuación. Mismo
patrón exacto que Cuenca. **Construido el mismo día**: tercera entrada en
`helpers/ckan_client._SOURCES` (`source="latacunga"`) más las URLs
correspondientes en `helpers/env_config.py` — ningún cliente nuevo, los
tools genéricos (`search_datasets`, `list_dataset_resources`,
`preview_resource_data`, etc.) ya soportaban múltiples fuentes CKAN vía el
parámetro `source`, así que solo hizo falta extender el diccionario de
fuentes y las 13 docstrings que enumeran los valores válidos de `source`.
Verificado en vivo extremo a extremo (`search_datasets(query="catastro",
source="latacunga")` → 3 resultados reales).

### Municipios que NO tienen CKAN en el patrón `datosabiertos.<ciudad>.gob.ec`

Probado en vivo (`curl` contra `/api/3/action/package_list`, timeout 10s):
Riobamba, Portoviejo, Ambato, Guayaquil, Loja, Ibarra, Machala,
Esmeraldas — los ocho dieron timeout de conexión (sin servidor en ese
subdominio), no un error HTTP. No se puede descartar que tengan un CKAN
en otra URL, pero no siguen el patrón de Cuenca/Latacunga.

### `municipiosabiertos.gob.ec` — directorio de "buenas prácticas" de gobierno abierto municipal

Sitio WordPress (Fundación Datalat + AME + FCD + apoyo USAID/NED, parte
del 2do Plan de Acción de Gobierno Abierto Ecuador). Expone un custom post
type `buenas-practicas` vía su API REST
(`/wp-json/wp/v2/buenas-practicas?per_page=100`, confirmado `X-WP-Total:
20`, una sola página) — catálogo completo de 20 iniciativas municipales de
gobierno abierto/datos abiertos, útil como directorio para futuras pasadas
en vez de tener que descubrir cada portal por separado. Ninguna de las
entradas trae un link directo al portal en el HTML (`href` ausente en casi
todos los posts) — el nombre de cada práctica hay que resolverlo a mano a
una URL real. Relevantes, pero **ninguno es CKAN** — son geoportales
(GeoServer/ArcGIS, mismo patrón ya usado para INAMHI/SIPA) o páginas
WordPress descriptivas sin catálogo real detrás:

- **Geoportal Quito** — geovisualizador + descargas + ráster + mapoteca,
  cobertura política-administrativa/ambiente/riesgos/movilidad/turismo/
  cultura. `gobiernoabierto.quito.gob.ec` (el portal "Gobierno Abierto
  Quito" enlazado desde el directorio) es WordPress puro, sin catálogo
  CKAN ni API propia — solo páginas descriptivas del modelo de gobierno
  abierto y un enlace de salida al geoportal real. Quito declara haber
  tenido "la primera plataforma de datos abiertos del país" en 2014, pero
  no se encontró un catálogo vivo en la URL esperada
  (`datosabiertos.quito.gob.ec`/`datos.quito.gob.ec`: ambas sin DNS) —
  posible plataforma descontinuada o migrada a otra URL no descubierta
  todavía.
- **Geoportal Riobamba**, **Fénix Geoportal** (Portoviejo, ligado a la
  Ordenanza Plan Portoviejo 2035), **Geoportal Servicios Virtuales**
  (Ambato — catastro predial, POT/PUGS, contenedores, rutas de buses,
  gestión de riesgos, obras públicas) — mismo patrón: visor geoespacial
  municipal, sin más detalle de URL confirmado en esta pasada.
- **Visor georeferenciado de obras públicas** — sin institución identificada
  en el título, contenido describe búsqueda por zona/parroquia/barrio/
  estado de obra.
- Cuatro entradas de "Gobierno Abierto"/"Portal de Gobierno Abierto" (Quito
  x2, Riobamba, Cuenca) son solo páginas institucionales sobre el modelo de
  gestión (ordenanzas, comités, planes de acción), no fuentes de datos.

**Conclusión:** el único hallazgo CKAN nuevo y accionable de esta pasada es
Latacunga. Los geoportales municipales (Quito/Riobamba/Portoviejo/Ambato)
son candidatos reales pero de un tipo distinto (WMS/WFS, no CKAN) — cada
uno necesitaría su propia pasada de investigación (confirmar URL exacta del
GeoServer/ArcGIS REST, capas disponibles) antes de decidir si vale la pena
construirlos, siguiendo el mismo patrón que `helpers/inamhi_client.py`/
`helpers/sipa_geoportal_client.py`.

---

## Decimoséptima pasada — soporte de lectura `.xlsb`

**Pedido de Daniel 2026-09-04:** cerrar el pendiente técnico anotado en la
Séptima pasada — `.xlsb` (Excel Binary Workbook) no estaba soportado por
`helpers/csv_reader.py`.

**Construido:** `preview_xlsb()` (vía `pyxlsb`), siguiendo el mismo patrón
que `preview_xls`. Verificado en vivo extremo a extremo contra el archivo
real que motivó el pendiente
(`registrocivil.gob.ec/wp-content/uploads/downloads/2025/05/
Defunciones_Generales_act_11_MAY_2025.xlsb`, 9.3 MB, descargado y parseado
completo fuera del límite del preview para confirmar la lectura): hoja
única `DEFUNCIONES`, encabezados reales (`ZONA`, `PROVINCIA`, `CANTÓN`,
`PARROQUIA`, `FECHA DEFUNCIÓN`, `MES`, `DÍA`, ...), primera fila de datos
real (`ZONA 8`, `GUAYAS`, `PEDRO CARBO`, ...). Fechas llegan como número de
serie de Excel crudo (44114.0), sin convertir — mismo comportamiento que
`preview_xls` ya tiene para fechas, no una regresión nueva.

**Hallazgo real, no anticipado en la nota original:** `.xlsb` es en
realidad un contenedor ZIP (registros BIFF12 en vez de XML, pero mismo
formato de contenedor que XLSX) — así que hereda exactamente el mismo modo
de falla que un `.zip` truncado: el índice central del ZIP vive al final
del archivo, así que una descarga cortada en el límite de 5 MB no puede
abrirse en absoluto (`zipfile.BadZipFile: File is not a zip file`),
confirmado en vivo recortando el archivo real de 9.3 MB a 5 MB. Se agregó
el mismo chequeo de truncamiento *antes* de intentar parsear que ya existe
para `.zip` (`preview_zip`), con el mismo mensaje accionable.

**Resuelto el mismo día (segunda parte del pedido):** el dataset de
defunciones que motivó todo el pendiente seguía sin poder previsualizarse
—9.3 MB superaba el límite de descarga de 5 MB, que hasta ahora era único
para todo el proyecto. Como `.xlsx`/`.xlsb`/`.ods` son los tres contenedores
ZIP del proyecto (índice central al final del archivo), truncar su
descarga no es una degradación útil como en un CSV — es una falla total
garantizada. Se agregó un parámetro `max_bytes` explícito a
`download_bytes()`/`_download()` (por defecto sigue en `MAX_DOWNLOAD_BYTES`,
5 MB, para todo lo demás) y los tres previsualizadores de contenedor ZIP
ahora piden `_MAX_DECOMPRESSED_BYTES` (20 MB — el mismo techo que ya usaba
`_gunzip_capped` para límite de descompresión, reutilizado como techo de
descarga en vez de inventar un número nuevo). **Verificado en vivo
extremo a extremo contra el archivo real de 9.3 MB**: ahora se
previsualiza con datos reales (`DEFUNCIONES`, encabezados y primera fila
reales, 20 filas devueltas). `download_resource` sigue siendo la vía para
bajar el archivo completo si hiciera falta más de una previsualización.

Wired en los tres puntos de despliegue por formato que existen en el
proyecto (`tools/preview_resource_data.py`, `tools/investigate_dataset.py`,
`tools/detect_series_pattern.py`) — cada uno mantiene su propio dict de
despacho por `kind`. De paso se encontró que `detect_series_pattern.py`
nunca tuvo `ODS` en su propio dispatch (aunque `classify_resource_format`
sí lo reconoce) — un `KeyError` crudo pendiente desde antes, no introducido
en esta pasada; se corrigió con el mismo guard defensivo que ahora protege
cualquier formato reconocido-pero-no-despachado, en vez de agregar soporte
completo de ODS a ese archivo específico (fuera de alcance de este
pendiente).

---

## Decimoctava pasada — LDLE agregado a INEC, SRI Saiku removido (2026-09-05)

**LDLE.** Pedido de Daniel: investigar varias siglas de fuentes nuevas
(CEAACES/CES cierre y planes de contingencia, SNIESE, RAS, LDLE, y una
quinta pedida como "acess registration" que resultó ser el registro
sanitario de ARCSA). De las cinco:

- **RAS** = "Recursos y Actividades de Salud" de INEC — ya cubierto sin
  código nuevo: `search_inec_estadisticas(query="salud")` ya lo lista y
  `get_inec_estadistica_files` ya devuelve sus 15 archivos reales
  (SPSS/R/XLSX/ZIP, metodología, formulario).
- **LDLE** ("Laboratorio de Dinámica Laboral y Empresarial", INEC+IESS,
  `ecuadorencifras.gob.ec/laboratorio-de-dinamica-laboral-y-empresarial/`)
  **no** aparecía en `search_inec_estadisticas` (0 resultados para
  "laboratorio"/"dinamica") pese a que `get_inec_estadistica_files` ya
  parseaba su página correctamente al recibir la URL directa — el gap era
  puramente de descubrimiento (no está linkeada desde ninguno de los dos
  menús semilla de `_SEED_PAGE_URLS`), no de parsing. Agregada a
  `_EXTRA_TOPICS` en `helpers/inec_client.py`, mismo patrón que el
  Geoportal DPA ya existente ahí. El total de temas pasa de ~90 a ~91.
- **SNIESE** — sin dataset masivo propio (es un registro interno). El
  contenido real es `educacion.gob.ec/edusuperior/biblioteca/` (1,259
  documentos WordPress `download-monitor`, ya documentado en la sección
  SENESCYT/MINEDEC de este archivo) — reachable pero nunca construido
  como tool; queda pendiente.
- **CEAACES/CES cierre y contingencia** — resuelto a
  `ces.gob.ec/lotaip/AAAA/Mes/...` (resoluciones RPC-SO-XX-No.XXX,
  patrón LOTAIP-por-categoría-legal ya visto en IESS/Contraloría); queda
  pendiente.
- **"acess registration"** = registro sanitario de ARCSA. Confirmado en
  vivo: `controlsanitario.gob.ec/base-de-datos/` responde 200 (el ROADMAP
  lo tenía marcado "caído" desde la Décima pasada) — la falla anterior era
  un `curl`/`httpx` sin User-Agent identificable, no una caída real del
  dominio: con `helpers.user_agent.USER_AGENT` responde 200 sin problema.
  **Construido el mismo día:** `helpers/arcsa_client.py` +
  `list_arcsa_categorias`/`get_arcsa_categoria_archivos`, reutilizando
  literalmente la misma lógica de parsing que
  `helpers/sgr_publicaciones_client.py`'s Biblioteca (`ul-downloads`/
  `li-gray1`/`download-monitor`, confirmado byte a byte que es el mismo
  plugin WordPress) — solo cambia el dominio verificado
  (`controlsanitario.gob.ec`). Confirmado en vivo contra la página real:
  27 categorías top-level, 77 archivos, 9 sub-categorías anidadas un nivel
  (la mayoría por año, ej. "Inspecciones en Establecimientos
  Farmacéuticos Controlados" > 2016-2023), 2 categorías vacías (0
  archivos, listadas igual por ser parte genuina de la estructura de la
  página). Un nombre de categoría se reproduce tal cual viene en el HTML
  aunque parezca un typo: "+NotiAlertas - Farmacovigilancia" trae un "+"
  literal en el texto, aparte del ícono "+" que antecede a toda categoría
  — confirmado leyendo el markup crudo, no es un artefacto del parser.

**SRI Saiku removido.** Pedido de Daniel: reverificar en vivo el pendiente
de la Décima pasada ("falta verificación contra el endpoint vivo"). Falló
de forma consistente (2 intentos con horas de diferencia) desde **tres**
entornos independientes: el servidor MCP desplegado
(`list_sri_saiku_cubes` → "Server disconnected without sending a
response"), `curl` local contra `srienlinea.sri.gob.ec/saiku/rest/saiku/
session` (`schannel: server closed abruptly`), y navegación de browser
real contra el dominio raíz `srienlinea.sri.gob.ec/` (denegada/fallida).
No es el gap de conectividad puntual que se sospechaba antes — el dominio
completo parece inalcanzable en este momento, no solo la ruta de Saiku.
Por indicación explícita de Daniel ("try again, then if not, remove"), se
removieron `helpers/sri_saiku_client.py`, los tres tools
(`list_sri_saiku_cubes`, `describe_sri_saiku_cube`,
`query_sri_saiku_aggregate`), su registro en `tools/__init__.py`, sus
menciones en `resources/catalog.py`/`tools/list_capabilities.py`/
`docs/TOOLS.md`, y se actualizó el conteo de tools (103→100) en
`CLAUDE.md` y `docs/MCP_ARCHITECTURE.md` (con nota fechada en vez de
reescribir los conteos históricos de esa página). Si el dominio vuelve a
responder más adelante, reconstruir desde este mismo punto — la lógica de
sesión anónima/discovery/query ya estaba resuelta, el bloqueo es
puramente de alcanzabilidad de red.

## Decimonovena pasada — CNE reevaluado, WAF caracterizado a fondo (2026-09-06)

Pedido explícito de Daniel del 2026-09-04 (registrado en el ROADMAP):
reevaluar si el bloqueo de Incapsula en `cne.gob.ec` aplica a todo el
dominio o solo al micrositio de resultados marcado en la Sexta pasada, y
si hay datasets alcanzables fuera de la zona bloqueada.

**El bloqueo es de todo el dominio, a nivel de challenge JS de Incapsula —
no de un micrositio ni de un simple filtro de User-Agent.** Confirmado con
tres clientes:

- `curl` (build de Windows/schannel de este entorno) falla el *handshake*
  TLS contra `cne.gob.ec` con `SEC_E_ILLEGAL_MESSAGE`/
  `CRYPT_E_NO_REVOCATION_CHECK` — pero el segundo error también aparece
  contra `google.com` y `datosabiertos.gob.ec`, así que es una limitación
  de este entorno con OCSP, no evidencia de bloqueo específico de CNE.
- `httpx` (Python, sin necesidad de TLS especial) sí conecta, y recibe
  consistentemente un 403 con el cuerpo característico de Incapsula
  (`<script src="/_Incapsula_Resource?...">` + iframe "Request
  unsuccessful. Incapsula incident ID: ...") — probado contra `/`,
  `/estadisticas/bases-de-datos/`, y directamente contra un enlace de
  descarga real (`/download/segunda-vuelta-2/?wpdmdl=57399`). Se repitió
  con un User-Agent de Chrome completo y headers `Accept`/
  `Accept-Language` realistas — sin diferencia, sigue siendo 403. Es un
  challenge JS que un cliente sin motor de JavaScript no puede resolver,
  no una verificación de cabecera.
- El navegador real (`mcp__Claude_Browser`, Chromium con JS) sí logra
  pasar el challenge — pero de forma inconsistente: la primera navegación
  a `cne.gob.ec` devolvió el mismo iframe de Incapsula ("Request
  unsuccessful") que ve `httpx`; una segunda navegación a una URL interna
  (`/estadisticas/bases-de-datos/`) cargó la página completa sin
  problema. Consistente con un WAF que puntúa por reputación de IP/sesión
  en vez de bloquear de forma binaria — no hay una URL "segura" fija.

**Contenido real confirmado detrás del challenge, vía navegador.** La
página `/estadisticas/bases-de-datos/` es un WordPress con el plugin WP
Download Manager (WPDM), con un acordeón de un nivel superior por proceso
electoral (Elecciones Generales 2025, Referéndum 2024, ... hasta
Elecciones Generales 2002 — 19 procesos listados). Cada proceso es a su
vez una categoría WPDM con subcategorías; para "Elecciones Generales
2025" las subcategorías son Diccionarios, Organizaciones Políticas,
Registro Electoral y Resultados, y "Resultados" lista archivos reales
descargables (ej. "Segunda Vuelta", 703.80 KB, con contador de
1,245 descargas).

**El acordeón está roto para cualquier visitante, no solo para scraping —
hallazgo colateral.** El sitio se queda en "Loading…" indefinidamente
porque el propio parche JS de CNE (comentario inline "CNE WPDM FIX
v1.0.2") que dispara la carga AJAX solo se activa si la URL contiene
`/informacion-publica-lotaip` o `/secretaria/orden-del-dia`, o si el DOM
tiene los selectores `.accordion-groups .accord-handle`/
`.w3eden .accord-handle` — ninguna de esas condiciones se cumple en
`/estadisticas/bases-de-datos/`, así que el fix nunca corre ahí. El
endpoint WPDM nativo que ese parche llama sí funciona igual reproducido a
mano, sin el fix:

```
GET https://www.cne.gob.ec/?wpdmactask=listsub&orderby=date&order=DESC
    &acccount=1&sac=default&linktpl=link-template-default-wdc&showsub=1
    &__wpdmacn=<nonce>&parent=<id_categoria_wpdm>
```

El `<nonce>` (`__wpdmacn`) se extrae de un `<script>` inline de la página
ya cargada (patrón `__wpdmacn=([a-zA-Z0-9]+)`); `parent` es el `rel` del
enlace del acordeón (ej. `8325` para "Elecciones Generales 2025", que a su
vez devuelve subcategorías con sus propios `rel` como `8329` para
"Resultados"). Esta llamada solo se pudo ejecutar dentro de la sesión del
navegador real (mismo origen, cookies de Incapsula ya resueltas) — no se
probó ni se espera que funcione contra `httpx` sin pasar antes el
challenge.

**Veredicto: sigue fuera de alcance para un backend Python puro.** El
403/challenge de Incapsula cubre el dominio completo, incluyendo el
enlace de descarga final, no solo el HTML de listado — confirmado que
`httpx` recibe el mismo challenge contra `?wpdmdl=57399` directamente. Sin
un navegador real ejecutando JS (Playwright o similar) no hay forma de
obtener las cookies de sesión que el WAF exige, y este proyecto no tiene
esa dependencia en ningún otro helper (todos usan `httpx`, ver
`CLAUDE.md`). Agregar Playwright solo para CNE es una dependencia pesada
y nueva para el proyecto — decisión pendiente de Daniel antes de
construir `helpers/cne_client.py`. Si se decide seguir, la estructura de
datos (procesos electorales 2002-2025 × subcategorías × archivos WPDM) y
el endpoint `wpdmactask=listsub` ya están mapeados en esta pasada, listos
para reutilizar.

## Vigésima pasada — `reportes.arconel.gob.ec` mapeado a nivel de protocolo, pendiente construir (2026-09-06)

Pedido de Daniel: avanzar el sector eléctrico, específicamente
`reportes.arconel.gob.ec` (marcado "descifrado, falta construir" desde la
Séptima pasada). Esta pasada fue solo de reconocimiento en vivo (browser
real, instrumentando `XMLHttpRequest.prototype.send` para capturar el
payload exacto de cada postback) — **no se escribió código todavía**, por
decisión explícita de Daniel al final de la pasada (ver "Decisión" al
final de esta sección).

**Flujo de sesión completo, confirmado byte a byte.** Es un ASP.NET
WebForms clásico con `ScriptManager`/`UpdatePanel` (MS AJAX, no JSF como
BIINEC/IG-EPN) más un control **Microsoft ReportViewer 11.0.3452.0**. Los
tres filtros (`ctl00$dpTipo`, `ctl00$dpAnio`, `ctl00$dpGrupoEmpresa`) y el
opcional `ctl00$dpMes` disparan `__doPostBack` en su `onchange`; cada uno
debe enviarse como un POST separado y secuencial a `https://reportes.
arconel.gob.ec/` (no hay atajo para fijar los cuatro de una sola vez) con
este cuerpo (URL-encoded):

```
ctl00$ScriptManager1=ctl00$UpdatePanel1|<campo_que_cambió>
ctl00$dpTipo=<texto exacto de la opción, ej. "Balance Energía">
ctl00$dpAnio=<año o "0">
ctl00$dpMes=<mes 1-12 o "0">
ctl00$dpGrupoEmpresa=<"0"|"1" Todos|"2" CNEL|"3" Empresas Eléctricas>
ctl00$txtObservacion=
ctl00$contenidoCentro$ReportViewer1$ctl03$ctl00=
ctl00$contenidoCentro$ReportViewer1$ctl03$ctl01=
ctl00$contenidoCentro$ReportViewer1$ctl10=
ctl00$contenidoCentro$ReportViewer1$ctl11=standards
ctl00$contenidoCentro$ReportViewer1$AsyncWait$HiddenCancelField=False
ctl00$contenidoCentro$ReportViewer1$ToggleParam$store=
ctl00$contenidoCentro$ReportViewer1$ToggleParam$collapse=false
ctl00$contenidoCentro$ReportViewer1$ctl08$ClientClickedId=
ctl00$contenidoCentro$ReportViewer1$ctl07$store=
ctl00$contenidoCentro$ReportViewer1$ctl07$collapse=false
ctl00$contenidoCentro$ReportViewer1$ctl09$VisibilityState$ctl00=None
ctl00$contenidoCentro$ReportViewer1$ctl09$ScrollPosition=
ctl00$contenidoCentro$ReportViewer1$ctl09$ReportControl$ctl02=
ctl00$contenidoCentro$ReportViewer1$ctl09$ReportControl$ctl03=
ctl00$contenidoCentro$ReportViewer1$ctl09$ReportControl$ctl04=100
__EVENTTARGET=ctl00$<campo_que_cambió>
__EVENTARGUMENT=
__LASTFOCUS=
__VIEWSTATE=<del paso anterior>
__VIEWSTATEGENERATOR=<constante de la sesión>
__EVENTVALIDATION=<del paso anterior>
__ASYNCPOST=true
```

Todos los campos deben reenviarse en cada POST (incluido `ctl00$dpMes`
aunque esté `disabled` — el control ReportViewer arma el body iterando
`form.elements` a mano, no vía `FormData` del navegador, así que sí lo
incluye incluso deshabilitado). El GET inicial a `/` siembra
`__VIEWSTATE`/`__VIEWSTATEGENERATOR`/`__EVENTVALIDATION` desde atributos
`value="..."` normales en el HTML; de ahí en adelante **cada respuesta
llega en el formato "delta" de MS AJAX**, no HTML de página completa:
bloques `<largoEnBytes>|<tipo>|<id>|<contenido>|` concatenados sin
separador fijo entre bloques (el largo es el delimitador real, no buscar
un cierre). Los bloques `hiddenField` traen como `id` el nombre exacto del
campo (`__VIEWSTATE`, `__EVENTVALIDATION`, etc.) y como contenido su valor
nuevo — alcanza con parsear estos bloques genéricamente para tener todo lo
necesario para el siguiente POST, sin tocar HTML para eso. Confirmado
parseable sin `BeautifulSoup`/`lxml` (que este proyecto no usa en ningún
helper, ver `igepn_informes_client.py`) con un parser de bloques por
longitud, no regex sobre el HTML.

**`dpMes` cambia de habilitado/deshabilitado según el tipo de reporte,
confirmado en vivo con dos casos reales:** deshabilitado para "Balance
Energía" (reporte ya anual/mensual embebido en la tabla vía columna "Mes",
no filtrable), habilitado para "Medidores Catastro". Un cliente tiene que
detectar esto leyendo el HTML del `UpdatePanel1` devuelto tras el postback
de `dpTipo` (buscar `disabled="disabled"` junto a `id="dpMes"`), no
asumirlo fijo por nombre de reporte.

**"Generar Reporte" es un botón `type="submit"` normal, sin `onclick`**
— dispara el mismo tipo de postback delta (sin `__EVENTTARGET`, en cambio
se incluye `ctl00$contenidoCentro$brtGenerar=Generar Reporte` en el body).
La respuesta a este POST trae varios bloques `updatePanel` a la vez,
incluido uno enorme (`ctl00_contenidoCentro_ReportViewer1_ctl09_
ReportArea`, ~220 KB en la prueba real) con la tabla del reporte ya
renderizada como HTML por el motor SSRS del lado servidor.

**La tabla real está enterrada bajo envoltorios 1×1, no es el primer
`<table>` del fragmento.** Estructura confirmada navegando el DOM real:
`table > tr > td > table` (envoltorio, 1 fila×1 celda) → recién en el
segundo nivel aparece la grilla real (50 filas × 37 celdas en la prueba de
"Balance Energía" 2023/Todos). La primera fila de la grilla real es un
separador vacío (todas las celdas ""), la segunda es el encabezado real
("Id Empresa", "Empresa", "Tipo Empresa", "Año", "Id Mes", "Mes", más ~30
columnas de energía/pérdidas), y de ahí en adelante los datos (ej. fila
real: `E.E. Ambato, Distribuidora, 2023, 1, Ene, 64769,242139, ...`). Los
valores numéricos usan coma decimal sin separador de miles (ej.
`5,1664676821650855`), igual que el resto de fuentes ecuatorianas ya
documentadas. Este anidamiento se puede recorrer de forma genérica sin
`BeautifulSoup`: extraer bloques de nivel superior de una etiqueta dada
(contando apertura/cierre de esa misma etiqueta, ignorando qué hay
adentro) y bajar un nivel mientras la fila tope tenga exactamente 1 celda
y esa celda tenga exactamente 1 tabla anidada adentro — el mismo truco
sirve para cualquier tipo de reporte, no es específico de "Balance
Energía".

**Hallazgo nuevo que la Séptima pasada no había marcado: el reporte está
paginado (SSRS ReportViewer, "página X de Y"), no todo llega en una sola
respuesta.** Confirmado en vivo: "Balance Energía" 2023/Todos mostró
"de 2 ?" páginas (el "?" es el propio ReportViewer indicando que todavía
no terminó de contar el total exacto). Pasar de página es otro postback
del mismo tipo, con un botón `<input type="image" name="ctl00$
contenidoCentro$ReportViewer1$ctl05$ctl00$Next$ctl00$ctl01">` (necesita
sufijos `.x`/`.y` como cualquier image-submit de ASP.NET) — mismo
mecanismo que "Generar Reporte", nada nuevo que aprender ahí. **Lo que
falta confirmar en vivo antes de construir:** el criterio de "última
página" (¿el botón Next aparece `disabled` en el HTML cuando ya no hay
más, o hay que comparar el número de página actual contra `TotalPages`
sabiendo que ese total puede llegar como "N ?" -- incierto -- en vez de un
número cerrado?). Sin esto confirmado, un cliente corre el riesgo real de
cortar el reporte a la mitad sin avisar, o de loopear de más; cualquier
implementación futura debe resolver esto primero, no asumirlo.

**Decisión de Daniel al cierre de esta pasada: documentar el mecanismo,
no construir el helper todavía.** Se ofrecieron tres alcances (build
completo con paginación, MVP de una sola página con límite documentado, o
solo documentar) y se eligió la tercera. Queda como el próximo paso
natural para `helpers/arconel_reportes_client.py`: toda la mecánica de
sesión/postback/delta/anidamiento de tabla ya está resuelta y verificada
en vivo arriba; lo único pendiente de verificar antes de escribir código
es el criterio de fin de paginación.

---

## Vigésimo primera pasada — AIP Ecuador (eAIP público en IFIS3), y "movimientos por aeropuerto" descartado (2026-09-06)

Pedido de Daniel: seguir buscando fuentes más allá de la integración CKAN
del sector eléctrico recién cerrada. Se exploró el dominio ya integrado
`ais.aviacioncivil.gob.ec` (base de `helpers/aviacion_client.py`,
METAR/NOTAM/SIGMET) más allá de las tres secciones ya cubiertas.

**"Movimientos/vuelos por aeropuerto" (el ítem que estaba en el
roadmap como "sin explorar") — descartado, no existe como sección
pública.** El menú principal del IFIS solo expone Aeródromos,
NOTAM/METAR/SIGMET, Cámaras y AIP sin sesión; cualquier estadística de
movimientos/vuelos vive detrás de "Planes de vuelo" (`/fpl/*`), que
`aviacion_client.py` ya documenta como la única sección que exige login.
No hay una sección de estadísticas de tráfico aéreo separada y pública en
este dominio.

**Hallazgo real: `/ifis3/` es un eAIP completo, público, servido como
HTML server-rendered (no SPA, no login) — dominio de datos nuevo y
sustancial dentro de un host ya confiable.** Confirmado en vivo con
`curl --ssl-no-revoke` (el intento inicial vía navegador con `navigate`
directo a la URL falló porque `/ifis3/` enruta client-side desde la
página raíz, pero una petición HTTP directa a cualquier ruta interna
sirve HTML completo sin necesitar la sesión del navegador):

```
GET https://www.ais.aviacioncivil.gob.ec/ifis3/aip/AD%202%20SEQM   -> 200, 172 846 bytes
GET https://www.ais.aviacioncivil.gob.ec/ifis3/aip/GEN%204.1       -> 200, 137 988 bytes
```

Estructura confirmada, generada por un motor tipo MediaWiki (anclas
`#SEQM_AD_2.1_...`, tabla de contenidos automática): tres partes AIP
estándar OACI —

- **GEN** (generalidades): autoridades, entrada/tránsito/salida de
  aeronaves y pasajeros, tablas de códigos/abreviaturas/símbolos,
  servicios (AIS, cartas, ATS, comunicaciones, MET, búsqueda y
  salvamento), derechos por uso de aeródromos (GEN 4.1).
- **ENR** (en ruta): reglas de vuelo VFR/IFR, clasificación del espacio
  aéreo ATS, procedimientos de espera/aproximación/salida, rutas ATS
  (inferiores/superiores/RNAV), radioayudas, zonas prohibidas/
  restringidas/peligrosas.
- **AD** (aeródromos): una página **AD 2.x por cada aeródromo/helipuerto
  del país** (confirmados: SEGU Guayaquil, SELT Latacunga, SEMT Manta,
  SEQM Quito como internacionales; más ~15 aeródromos nacionales — SEJD
  Ahuano, SEAM Ambato, SEGS Baltra, SECA Catamayo, SECO Coca, SECU
  Cuenca, SEBZ Cumbaratza, SEII Isabela, SEMC Macas, SENL Nueva Loja,
  SERB Riobamba, SESA Salinas, SEST San Cristóbal, SESV San Vicente,
  entre otros).

**Cada página AD 2.x trae datos estructurados en tablas numeradas
(formato ICAO Anexo 15 estándar), no solo prosa** — confirmado en el
contenido real de SEQM: AD 2.1 (indicador de lugar), AD 2.2 (coordenadas
ARP en grados/min/seg, dirección/distancia desde la ciudad, elevación/
temperatura de referencia, ondulación geoidal, variación magnética con
tasa de cambio anual, administración/teléfonos/AFS del aeródromo, tipos
de tránsito IFR/VFR permitido), AD 2.3 (horas de funcionamiento por
dependencia: aduanas, sanidad, AIS, MET, ATS, combustible), y continúa
hasta ~AD 2.20+ (instalaciones de pasajeros, servicio de salvamento y
extinción de incendios/categoría RFF, remoción de obstáculos estacional,
plataforma/calles de rodaje, señales, obstáculos, datos meteorológicos
suministrados, características físicas de pista, distancias declaradas,
luces de aproximación/pista, ayudas radioeléctricas de navegación y
aterrizaje, reglamentación local de tránsito, procedimientos de
atenuación de ruido, procedimientos de vuelo, información suplementaria).
Esto es, en esencia, la ficha técnica completa y oficial de cada
aeródromo ecuatoriano — coordenadas, pista, frecuencias, tarifas, horas
de operación — en un solo lugar público.

Pestañas adicionales del mismo sistema, sin explorar en detalle esta
pasada: **AMDT** (registro de enmiendas AIP), **SUP** (suplementos AIP),
**AIC** (circulares de información aeronáutica) — probablemente PDFs
descargables por edición/fecha, complementarios al contenido HTML de
AIP/GEN/ENR/AD.

**Por qué no se construyó ya:** el AIP completo es grande (GEN+ENR+AD
decenas de subsecciones × ~20 aeródromos) y cada subsección tiene su
propio layout de tabla; conviene decidir alcance (¿todo el árbol, o solo
AD 2.x por aeródromo, que es la parte con mayor valor inmediato para un
caller tipo LLM?) antes de escribir el parser. Candidato fuerte para
`helpers/aip_client.py` + `tools/get_aip_aerodromo.py` (y opcionalmente
`search_aip`/`get_aip_seccion` genérico para GEN/ENR), reutilizando
`download_bytes` y el mismo patrón de limpieza HTML que
`aviacion_client.py` ya tiene. Nada bloqueante encontrado: sin login, sin
JS, sin WAF, mismo dominio ya en la allowlist operativa del proyecto.

---

## Vigésimo segunda pasada — BCE Cuentas Nacionales construido; mercado laboral y pobreza/desigualdad aclarados; verificación en vivo del archivo IEM frameset; revisiones de BCEData descartadas (2026-09-09)

**Pedido de Daniel:** "implementemos mercado laboral, pobreza y cuentas
nacionales completas" — los tres ítems que EMOE y coyuntura (Duodécima
pasada) había dejado pendientes. Investigación en vivo de los tres, no
solo lectura de HTML.

### Mercado laboral — ya cubierto, sin código nuevo

`search_indicadores_bce("mercado laboral")` devuelve 4 grupos reales bajo
"4.2 Precios, Salarios y Mercado Laboral" del propio catálogo BCEData:
id_grupo 64 (salario unificado sector privado), 65 (SBU nominal/real), 68
("Indicadores del mercado laboral nacional, urbano y rural") y 102
("Indicadores del mercado laboral ecuatoriano: Cuenca, Guayaquil, Quito,
Machala y Ambato"). Verificado en vivo: id_grupo 102 trae series
trimestrales 2020-IV a 2026-I (empleo global, empleo adecuado/pleno, empleo
no clasificado, por nivel nacional/urbano/rural y por ciudad) — datos reales
y ricos, no un stub. La nota de la Duodécima pasada ("sin página índice
encontrada para mercado laboral") era correcta pero incompleta: se refería
solo al sistema de páginas "-indice(s)" (`bce_indices_client.py`), no a
BCEData, que sí lo tiene y ya es accesible con las tools existentes. **No
hay gap real aquí** — se documenta para cerrar el ítem del roadmap, sin
tocar código.

### Pobreza y desigualdad — confirmado que no es BCE, ya cubierto vía INEC

`search_indicadores_bce("pobreza")` y `("desigualdad")` devuelven 0
resultados — confirmado en vivo que BCE no publica nada de esto (coherente
con el hallazgo de la Novena pasada: pobreza es responsabilidad de INEC en
el sistema estadístico ecuatoriano, no del BCE). La página estática de INEC
para "Pobreza" (`search_inec_estadisticas("pobreza")` →
`ecuadorencifras.gob.ec/pobreza2/`) está vacía (0 archivos) — mismo patrón
de página de tema desactualizada ya documentado para Empleo en la Novena
pasada. La fuente viva real es `search_inec_publicaciones("pobreza y
desigualdad")`: página landing vigente
(`pobreza-y-desigualdad-2/`, 2026-06-19) más una serie completa de
boletines anuales "Pobreza por Ingresos – Resultados" 2019-2025. **Ya
accesible con la tool genérica existente** — no se construyó nada nuevo,
solo se verificó y documenta la ruta real.

### BCE Cuentas Nacionales — construido: `search_bce_cuentas_nacionales`/`get_bce_cuentas_nacionales_archivo`

Investigación del sitemap de `contenido.bce.fin.ec` (mismo
`wp-sitemap-posts-page-1.xml` que usa `bce_indices_client.py`) encontró 18
páginas bajo el árbol "Cuentas Nacionales": anuales, trimestrales,
regionales, base fija 2007=100, matrices especiales, TOU/CEI/MEI
independientes, MIP, MCS, cuentas temáticas (bioeconomía), documentos
metodológicos e IMAEC.

**Por qué no encajan en el sistema de índices existente.** Un barrido
inicial ingenuo (`t.includes("bce-gi")` sobre dos páginas) sugería
falsamente que usaban el mismo widget `.bce-gi` que `bce_indices_client.py`
ya sabe leer — la señal real era solo que el plugin carga su CSS/JS en la
página (`bce-gi-public-css`/`bce-gi-public-js`), no que el widget esté
presente en el HTML. Un barrido correcto (regex sobre `class="bce-gi..."`,
ejecutado vía `httpx` desde dentro del proyecto — un script en `scripts/`
en vez de un archivo suelto en `/tmp`, porque `uv run python /tmp/archivo.py`
resulta en un entorno "script mode" distinto al del proyecto que rompe la
importación de `httpcore`/`h11` con un `AttributeError` en `inspect.signature`
no relacionado con el código en sí) confirmó **0 páginas de Cuentas
Nacionales usan `.bce-gi`** — cada una renderiza su propio widget bespoke,
con su propio prefijo de clases CSS (`cna-`/`cnr-`/`cnt-` para las
tabuladas por año/vintage, o simples `<a>` sueltos dentro de `.card-body`
para las de serie única como MEI/TOU/CEI/FBKF/MIP). No hay una convención
de CSS compartida entre ellas — confirmado inspeccionando doce páginas una
por una.

**Lo que sí generaliza:** cada descarga real es un `<a href="...">` que
apunta a `/documentos/.../archivo.{xlsx,xls,pdf,csv,zip,docx}`, sin
excepción, en las 18 páginas verificadas (desde 3 enlaces en las páginas
simples hasta 80 en el boletín trimestral). `_extract_archivos` en
`helpers/bce_cuentas_nacionales_client.py` parsea sobre ese hecho
estructural (extensión + prefijo de ruta), no sobre las clases CSS
específicas de cada página — así una sola función cubre las 18 páginas
pese a que no comparten marcado. Igual que `_EXTRA_TOPICS` en
`inec_client.py` y `_PAGINAS` en `bce_precios_comex_client.py`, el conjunto
de 18 páginas está hardcodeado (no hay patrón de slug ni convención de
sitemap que las identifique como grupo) — se dejaron fuera deliberadamente
"cuentas-nacionales-anuales"/"cuentas-nacionales-trimestrales" y sus
"-definicion" (cáscaras de navegación sin enlaces `/documentos/` propios,
mismo caso que `memoria-anual-indice` en la Duodécima pasada).

**Verificado en vivo extremo a extremo:** 18/18 páginas responden 200,
244 archivos reales extraídos en total (22 a 80 por página según el
tamaño real de cada paquete). Contenido real confirmado: serie histórica
del PIB desde 1965 (`retropolacion_1965_2024p.xlsx`), cuentas trimestrales
hasta el IT 2026, cuentas regionales/provinciales 2007-2024, matrices
insumo-producto y de contabilidad social en base fija 2007 y base móvil,
la cuenta satélite temática de bioeconomía, y resultados IMAEC — este
último con una limitación real: solo expone el mes más reciente (mismo
patrón de ventana rodante ya documentado para
`search_bce_publicaciones`), no un archivo histórico. Bug de codificación
descartado en el proceso: un `print()` en consola de Windows mostraba
"Presentaci�n" en vez de "Presentación" — verificado que el dato real
(escrito a un archivo JSON con `ensure_ascii=False`) está correctamente en
UTF-8; era un artefacto de la consola, no del cliente.

6 tests nuevos (`tests/test_bce_cuentas_nacionales_client.py`), con
`_PAGINAS` reemplazado vía `monkeypatch` a un catálogo de 2 páginas de
prueba para no tener que mockear las 18 reales. Tool count: 106 → 108.

### BCEData — detección de cambios de revisión, descartada explícitamente

Pedido de Daniel: dejar este ítem fuera de alcance. Ya estaba documentado
que BCEData no expone ningún marcador de revisión (`ETag`/`Last-Modified`
ausentes, confirmado en la Duodécima pasada) — la única vía posible es
comparación de contenido bajo demanda, que ya existe vía
`audit_bce_catalog`. Movido de Pendiente a Descartado en ROADMAP.md; no
requiere código.

### IEM — verificación en vivo de los 127 boletines de la era frameset (1996-2006)

Pedido de Daniel: "iem, verify" — cerrar el ítem "confirmar que las
secciones más viejas siguen la misma forma (solo muestreado)" dejado
pendiente en la Decimotercera pasada, que solo había verificado 3
boletines (No. 1800, 1780, y el celda-larga de No. 1820) a mano.

**Método.** Un script puntual (`scripts/_scratch_iem_frameset_verify.py`,
descartado tras esta pasada — no es una tool ni un artefacto permanente)
llamó a `_fetch_bulletins()` + `_fetch_tables_for_bulletin()` — el mismo
código de producción que usa `get_bce_iem_table`, no un parser aparte —
sobre los 127 boletines descubiertos con `numero` entre 1727 y 1853
(confirmado: `_fetch_bulletins()` los descubre todos, sin huecos en el
índice), con concurrencia 10. Corrida completa: ~20 minutos (cada boletín
hace ~60 fetches secuenciales de página de sección, sin concurrencia
interna — ver `_fetch_legacy_frameset_tables`).

**Resultado: 122/127 boletines parsean con la misma forma** confirmada en
la Decimotercera pasada — 100 % `formato_origen: "html_frameset"`, entre
57 y 86 tablas por boletín (promedio 67.1), consistente con las 63 tablas
ya verificadas manualmente para el No. 1800. Sin ninguna tabla con 0 filas
ni con un `formato_origen` inesperado (que habría indicado una caída
silenciosa al parser equivocado).

**2 excepciones reales, no bugs de este proyecto:**

1. **No. 1727-1730 (enero-abril 1996, los 4 primeros boletines del archivo
   completo) están rotos en el propio servidor del BCE.** El índice del
   BCE los lista, pero la página del boletín en sí devuelve HTTP 404 —
   confirmado con una petición nueva e independiente (`m1727011996.htm` →
   404; el boletín inmediatamente siguiente, `m1731051996.htm`, mayo 1996,
   → 200 normal). No es un problema de rate-limit ni de user-agent: es un
   enlace muerto permanente del lado del BCE, en el extremo más viejo del
   archivo. `_fetch_tables_for_bulletin` ya falla con un mensaje claro
   (404 del propio `httpx`) en vez de devolver datos vacíos o incorrectos
   — no se necesita ningún cambio de código.
2. **No. 1853 (julio 2006, el último boletín antes de que empiece la era
   ZIP en el No. 1854/agosto 2006) es una tercera forma, genuinamente
   única, no antes documentada.** No es un frameset con enlaces a
   secciones ni un ZIP — es un export crudo de Microsoft Excel
   (`meta name=ProgId content=Excel.Sheet`, namespaces
   `urn:schemas-microsoft-com:office:excel`), la hoja completa embebida
   como un único documento HTML. `_fetch_legacy_frameset_tables` no
   encuentra enlaces de sección (porque no los hay) y falla con "no
   expuso tablas XLSX individuales" — confirmado que es un caso aislado
   exactamente en la frontera de era, no el inicio de una familia nueva:
   los boletines inmediatamente anteriores (No. 1851 mayo 2006, No. 1852
   junio 2006) sí son frameset normal (66 y 67 tablas respectivamente).
   Coherente con la filosofía ya aplicada a `iem-1111-e` ("Encaje Legal")
   en la Decimotercera pasada: un caso genuinamente único no justifica un
   normalizador dedicado.

**Conclusión:** la forma "frameset" está confirmada uniforme en 122 de 127
boletines (96 %); las 5 excepciones son reales, están documentadas, y ya
fallan de forma clara en vez de silenciosa — no se requiere ningún cambio
de código en `bce_iem_client.py`.

### IEM — bug real corregido en `hash_catalog_tables`; hashing masivo del histórico completo descartado

Al revisar la infraestructura de hashing existente (`hash_catalog_tables`,
ya expuesta vía `search_bce_iem(hash_archivos=true)` y
`scripts/audit_bce_iem.py --hash-xlsx`, pero nunca corrida a fondo ni
cubierta por tests) se encontró un bug real, no solo la falta de una
corrida: cada miembro de un ZIP legado (era 2006-2016) comparte la misma
URL — `_fetch_legacy_zip_tables` le asigna la URL del ZIP completo a cada
uno de sus ~60-90 archivos `.xls` — así que hashear "por tabla" en vez de
"por URL única" descargaba y hasheaba el mismo ZIP entre 60 y 90 veces por
boletín. Corregido: `hash_catalog_tables` ahora deduplica por URL antes de
descargar, hashea cada URL única una sola vez, y aplica el resultado a
todas las entradas de tabla que comparten esa URL — `max_files` ahora
acota descargas reales (URLs únicas), no el conteo de entradas de tabla,
que puede ser mucho mayor. 3 tests nuevos
(`test_hash_catalog_tables_downloads_shared_url_only_once`,
`..._reports_errors_without_failing_others`,
`..._caps_by_unique_url_not_table_count`).

Pedido explícito de Daniel: no ejecutar la corrida masiva real. Estimado
en vivo: ~17.000-18.000 URLs únicas en total entre las tres eras (era
frameset ~8.500 páginas de sección, era ZIP ~122 archivos tras la
corrección de deduplicación, era moderna ~9.200 XLSX), muy por encima del
límite de 5.000 archivos por llamada — requeriría varias corridas
encadenadas por rango de años y varias horas de carga sostenida contra el
servidor del BCE, sin que ninguna parte del proyecto dependa hoy de tener
ese manifiesto de hashes. La capacidad queda lista para usarse cuando se
necesite (ver ROADMAP.md § Descartado), sin necesidad de más código.

### Sistema de índices — 4 páginas nuevas encontradas fuera del filtro de slug, incluida Cifras Económicas del Ecuador

Barrido sitewide real (no un muestreo): se descargó cada una de las 221
URLs del sitemap de `contenido.bce.fin.ec` y se buscó la clase CSS propia
del widget (`class="bce-gi..."`) directamente en el HTML, en vez de confiar
en que el slug termine en "-indice(s)" como hace `_discover_paginas` hoy.
Resultado: 36 páginas totales con el widget real (30 ya cubiertas por el
filtro de slug — coincide exactamente con lo confirmado en la Duodécima
pasada — más 6 nuevas fuera de ese filtro).

De las 6, 2 son duplicados confirmados, no candidatos nuevos:
- `reporte-monetario-semanal` — mismo conteo de archivos y mismo rango de
  años (349, 2020-2026) que `reporte-monetario-semanal-indices`, ya en el
  catálogo. Mismo contenido, segunda URL.
- `iem-publicaciones` — es el propio archivo de boletines IEM (367,
  1996-2026) que `helpers/bce_iem_client.py` ya usa como
  `IEM_ARCHIVE_URL`; `search_bce_iem`/`get_bce_iem_table` ya exponen su
  contenido desglosado en tablas individuales, con más detalle que esta
  página (solo enlaces al boletín completo).

Las otras 4 son adiciones reales, verificadas en vivo, sin superposición
con ningún catálogo existente (confirmado buscando "coyuntural",
"interbancario", "tasas maximas", "cifras economicas" contra el catálogo
de índices ya construido — cero resultados antes de este cambio):

- **Mercado Interbancario** (`tasas-de-interes-menu-tab`): 264 archivos,
  2000-2026, mensual.
- **Entorno Macroeconómico** (`presentacion-coyuntural`): 201 archivos,
  2009-2026, mensual.
- **Cifras Económicas del Ecuador** (`cifras-economicas-del-ecuador`): 243
  archivos, 2005-2025, mensual — cierra el ítem puntual que ROADMAP.md
  dejaba pendiente bajo "Catálogo de publicaciones y calendario".
- **Información Histórica de Tasas Máximas y Referenciales**
  (`informacion-historica-de-tasas-maximas-y-referenciales`): 229
  archivos, 2007-2026, mensual.

Las 4 ya renderizan el mismo widget `.bce-gi` que `_parse_pagina` ya sabe
leer — no se necesitó ningún parser nuevo, solo agregar sus slugs a un
`_EXTRA_SLUGS` hardcodeado (mismo patrón que `_EXTRA_TOPICS` en
`inec_client.py`) y que `_discover_paginas` busque su entrada en el
sitemap junto a las que sí matchean por slug. Repetir el barrido completo
de 221 URLs en cada request sería demasiado costoso, así que no se
generaliza la detección — se deja como una lista chica, verificada a mano.
Catálogo total: 30 → 34 páginas. 2 tests nuevos.

### BCEData ↔ IEM — revisión manual de los 75 candidatos restantes, descartada

Pedido explícito de Daniel: no seguir revisando a mano. De los 77
candidatos que `compare_bce_sources` señala por similitud de etiqueta,
solo 2 fueron confirmados como equivalencia real con datos en vivo
(Decimotercera pasada) — de los primeros 5 revisados en esa misma pasada,
3 resultaron falsos positivos (riesgo país↔producción petrolera,
derivados↔IPC, salario↔IPP), así que la tasa de acierto real es baja y no
hay atajo: cada candidato exige comparar valores y metodología uno por
uno, sin garantía de que la mayoría termine siendo una equivalencia real.
Movido de Pendiente a Descartado en ROADMAP.md — `compare_bce_sources`
sigue exponiendo la cola completa de 77 candidatos tal cual, sin tratar
ninguno de los 75 restantes como duplicado confirmado.

### BCE — calendario de publicaciones futuras: construido (`search_bce_calendario`)

Cierra el ítem "falta el calendario de publicaciones futuras" que
`search_bce_publicaciones` (Duodécima pasada) había dejado pendiente.

**Hallazgo.** La página `calendario-estadistico/` del menú de BCE no es
en sí misma el dato — solo embebe un `<iframe>` apuntando a
`/documentos/CalendarioEstadistico/ConsultaCalendario.html`, una app de
una sola página (JS + CSS estáticos) que a su vez carga todo su contenido
desde un CSV plano:
`/documentos/CalendarioEstadistico/calendario_publicaciones.csv`. No hace
falta ejecutar JS ni simular la app — el CSV es la fuente de verdad
completa, verificada en vivo: 523 filas, fechas cubriendo el año
calendario 2026 completo (2026-01-05 a 2026-12-31), 162 de ellas
genuinamente futuras al momento de esta pasada (2026-09-09) — el
programa de publicación oficial del BCE para IEM, Cuentas Nacionales,
IMAEc, balanza de pagos, tasas de interés, reservas internacionales, y
más, con categoría/periodicidad/período de referencia y enlace directo a
la página de cada publicación.

**Detalles de parseo reales, no solo teóricos:**
- El CSV es UTF-8 con BOM — decodificarlo como `cp1252` (el fallback más
  común en este proyecto para archivos legados del BCE) produce texto
  corrompido tipo "PUBLICACIÃ“N"; `utf-8-sig` lo decodifica limpio.
  Confirmado comparando ambos decodificadores contra el mismo archivo.
- Las fechas vienen como `D/M/YYYY` sin cero a la izquierda (`"14/1/2026"`,
  no `"14/01/2026"`) — `datetime.strptime(..., "%d/%m/%Y")` las acepta
  igual, sin necesitar normalización previa.
- El archivo no lleva año en el nombre (`calendario_publicaciones.csv` a
  secas) — presumiblemente el BCE lo sobrescribe en el mismo lugar cuando
  arma el calendario del año siguiente, en vez de publicar un archivo
  nuevo por año. No confirmado todavía con un segundo año real.

**Decisión de privacidad, no solo de diseño.** El CSV real trae columnas
`RESPONSABLE`/`CORREO DEL RESPONSABLE` — nombre y correo institucional del
funcionario del BCE asignado a cada publicación. `helpers/bce_calendario_client.py`
las descarta explícitamente al parsear: son identificadores directos de
una persona real, sin ninguna relación con la pregunta que este tool
responde ("¿cuándo se publica X?"). El resto de columnas (fechas, nombre,
tipo, periodicidad, categoría, período de referencia, enlace,
observaciones) se exponen tal cual.

Construido `helpers/bce_calendario_client.py` + `search_bce_calendario`
(`query`, `categoria`, `periodicidad`, `desde`/`hasta`, `solo_proximas`).
5 tests nuevos. Tool count: 108 → 109.

---

## Vigésimo tercera pasada — barrido del catálogo CKAN nacional (98+ organizaciones) buscando fuentes de alto valor sin explorar (2026-09-09)

**Pedido de Daniel:** "un scan de datos ecuatorianos útiles o importantes, ¿qué hay por ahí?" — no un pedido de construir nada todavía, sino de mapear el terreno. Método: `search_organizations` (herramienta genérica CKAN ya construida) con página vacía y `page_size=100` para listar organizaciones por número de paquetes, más `search_datasets`/`list_dataset_resources` y `WebFetch`/`WebSearch` dirigidos para verificar en vivo (no solo el conteo de paquetes) los candidatos más prometedores. La lista de organizaciones devolvió `"posiblemente_hay_mas": true` con 100 resultados — el portal declara "más de 98 instituciones" en su propia página de bienvenida, así que este barrido cubrió la primera página completa pero no está confirmado que sea exhaustivo; una pasada futura debería paginar hasta agotar el listado.

### Hallazgo principal: ya hay contenido rico y sin explorar dentro del catálogo CKAN genérico, no fuera de él

El patrón repetido en este proyecto (INEC, BCE, Superbancos) es que CKAN es solo "la punta" y el valor real vive en el portal propio de cada institución. Este barrido encontró el caso inverso en varios casos: organizaciones con **decenas o cientos de paquetes CKAN genuinos, actualizados, y nunca antes buscados por este proyecto** porque nadie había preguntado por ellas específicamente. Ya son accesibles hoy con las tools genéricas existentes (`search_datasets`, `list_dataset_resources`, `preview_resource_data`, `download_resource`) — no hace falta ningún cliente nuevo, solo saber que existen.

**Autoridad Portuaria de Puerto Bolívar (APPB) — 246 paquetes, el conteo más alto de todo el barrido.** Verificado en vivo (`WebFetch` sobre la página de la organización): reportes mensuales reales de tráfico de buques (internacional, nacional, cruceros), carga de importación/exportación (general y contenedorizada), productos principales importados/exportados con país de origen/destino y tonelaje métrico, y obras de inversión de operadores privados — patrón de ~6 reportes estandarizados por mes, en ODS/CSV/XLSX, con fechas de actualización progresando cronológicamente hasta agosto de 2026. Es información de comercio exterior/logística portuaria que ninguna otra fuente de este proyecto cubre (BCE cubre comercio exterior agregado a nivel de país, no tráfico portuario). No mencionado en ningún lugar del roadmap hasta ahora.

**Ministerio del Interior — Homicidios Intencionales, ya reachable hoy, verificado con la tool real.** `search_datasets(query="homicidios intencionales")` (la tool MCP de producción, no una simulación) devuelve el dataset completo: 4 archivos XLSX — el acumulado mensual 2026 (enero-julio), la serie histórica 2014-2025, y dos diccionarios de variables (uno de ellos de 93 MB, microdatos 2014-2024) — `metadata_modified` 2026-08-19, organización `ministerio-del-interior`. Actualizado mensualmente y con historial real. Dato de seguridad ciudadana genuinamente valioso, cero código nuevo necesario.

**Otras organizaciones con conteo de paquetes alto y sin buscar antes en este proyecto** (conteo de paquetes vía `search_organizations`, contenido no verificado archivo por archivo todavía — candidatos para una pasada futura, no confirmados como valiosos más allá del conteo):
- SRI-Servicio de Rentas Internas (CKAN genérico): 127 — separado del scraper dedicado `search_sri_datasets`/`search_sri_estadisticas_recaudacion`; podría tener contenido no cubierto por esos dos.
- Ministerio de Economía y Finanzas (CKAN genérico): 97 — separado del scraper dedicado `search_mef_fiscal` (76 XLSX); mismo caso.
- Instituto Nacional de Economía Popular y Solidaria (IEPS): 106 — nunca buscado.
- Corporación del Seguro de Depósitos, Fondo de Liquidez y Fondo de Seguros Privados (COSEDE): 88 — estabilidad financiera, ángulo que ninguna otra fuente del proyecto cubre.
- Instituto Público de Investigación Acuicultura y Pesca (IPAIP): 70 — investigación pesquera/acuícola, nunca buscado.
- Ministerio de Agricultura y Ganadería (CKAN genérico): 69 — separado de SIPA (el portal propio de MAG ya cubierto); podría tener contenido no cubierto por SIPA.
- CENACE (45) y CNEL EP (40) — ya cubiertos vía datasets CKAN genéricos, confirmado en el roadmap existente (Hecho, sector eléctrico).

### Instituciones con portal propio más rico que su presencia en CKAN — candidatos reales a construir

**Consejo de la Judicatura — solo 1 paquete en CKAN, pero un portal de estadística judicial real y sin explorar.** Verificado en vivo (`WebFetch` sobre `fsweb.funcionjudicial.gob.ec/estadisticas/datoscj/portalestadistica.html`): un dashboard público, sin login visible, con actualización mensual, cubriendo causas, audiencias, productividad de jueces, violencia/femicidio, medidas de protección, mediación, servicios notariales, remates judiciales, causas laborales por juez. No se confirmaron formatos de descarga (CSV/XLSX) desde el texto extraído — parece ser un dashboard interactivo (posible Power BI o visor propio), así que antes de construir haría falta una pasada con browser real para encontrar el mecanismo de exportación real, mismo patrón que se usó para desencriptar los widgets Power BI de `search_sut_indicadores` (Ministerio del Trabajo). No mencionado en el roadmap hasta ahora — dato de justicia/gobernanza genuinamente valioso.

**Ministerio de Salud Pública — 8 paquetes en CKAN, portal propio con más detalle.** `salud.gob.ec/datos-abiertos/` (plataforma de datos COVID-19 con casos por semana epidemiológica) y `salud.gob.ec/direccion-nacional-de-vigilancia-epidemiologica-gaceta-epidemiologica/` (Gacetas de Indicadores, archivo 2012-2026) y `salud.gob.ec/geosalud-en-cifras/`. Ya estaba en el roadmap como "sin pasada de contenido completa" (Séptima pasada); este barrido confirma sub-objetivos concretos (gacetas epidemiológicas con archivo histórico) en vez de solo "dominio vivo".

**Ministerio de Turismo — 5 paquetes en CKAN (catastro turístico), portal "Turismo en Cifras" con más detalle.** `servicios.turismo.gob.ec/turismo-en-cifras/` — entradas/salidas internacionales de turistas por nacionalidad, actualización mensual, cuatro segmentos (indicadores económicos OMT, inteligencia de mercado, oferta turística, boletines estadísticos). Nunca mencionado en el roadmap.

### Candidatos de menor prioridad, evaluados y descartados de este barrido (no del proyecto)

- **SENAGUA/agua.gob.ec** — solo 1 dataset real en CKAN ("Autorizaciones del Recurso Hídrico"); la organización CKAN antigua `senagua-insteliminada` tiene 0 paquetes (eliminada/fusionada en ARCA, la Agencia de Regulación y Control del Agua). Bajo volumen, nicho.
- **MPCEIP (Ministerio de Producción, Comercio Exterior, Inversiones y Pesca)** — 8 paquetes CKAN (registro de artesanos/emprendedores) más boletines PDF de comercio exterior que ya reutilizan cifras del BCE. Solapamiento alto con lo que el proyecto ya cubre (BCE precios comex, SENAE recaudación aduanera); bajo valor incremental.

Ninguno de los hallazgos de esta pasada se construyó todavía — es un mapeo, no una implementación. Ver ROADMAP.md § Otras fuentes por explorar para las filas nuevas.

---

## Vigésimo cuarta pasada — revisión en vivo de todos los ítems pendientes de "Otras fuentes por explorar" (2026-09-09)

**Pedido explícito de Daniel: "investiga los ítems de investigación pendientes en los documentos, no omitas nada."** Esta pasada recorre uno por uno los ítems de la tabla "Otras fuentes por explorar" y "Otros ítems parciales" de ROADMAP.md, con verificación en vivo (`WebSearch`/`WebFetch`, y las tools CKAN genéricas de producción donde aplica) — no solo relectura de las notas existentes. Se documenta cada ítem, incluidos los que no cambiaron de estado, para que quede explícito qué se revisó y qué no.

### Correcciones reales a notas existentes

**IGM Geoportal — la nota "gated tras registro/login" está desactualizada o era parcial.** Verificado en vivo (`WebFetch` sobre `geoportaligm.gob.ec/portal/index.php/descargas/cartografia-de-libre-acceso/registro/`): la Cartografía Base Continua a escala 1:1'000.000 (2024) es de **acceso libre y gratuito, sin mención de registro obligatorio para la descarga**, en GeoPackage y Shapefile, con archivos de simbología (.qml/.lyr) y catálogo de objetos. El geoportal también expone **geoservicios WMS/WFS/WMTS** — el mismo patrón ya usado para INAMHI/SIPA en este proyecto. Limitación real que sí se confirma: la escala 1:1.000.000 es de nivel país, no catastral/detallada — puede que la cartografía de mayor resolución (la que originalmente motivó la nota de "gated") sí requiera registro, no se confirmó por separado. Antes de construir, verificar en vivo el endpoint WMS/WFS real (GetCapabilities) para confirmar que es tan directo como INAMHI.

**Cancillería — ya reachable hoy, no es un dominio sin explorar.** `search_organizations` (tool de producción) confirma la organización CKAN `ministerio-de-relaciones-exteriores-y-movilidad-humana` con **13 paquetes reales**: Apostillas y Legalizaciones, Visas, estadísticas de movilidad humana (anonimizadas por ley de protección de datos). Accesible hoy con las tools CKAN genéricas — la nota anterior ("sin pasada de contenido dedicada") ya no aplica; lo que falta, si acaso, es documentarlo como fuente conocida, no investigarlo.

**Calidad del aire de Quito — encontrado el archivo histórico real, pero bloqueado por la decisión ya tomada contra `.rar`.** La página `ambiente.quito.gob.ec/red-metropolitana-de-monitoreo-de-la-calidad-del-aire/` es solo un hub que enlaza a tres apps separadas: `aireambiente.quito.gob.ec` (el dashboard en tiempo real, probablemente SPA, sin confirmar), `iuv.quito.gob.ec` (índice UV) y **`datosambiente.quito.gob.ec`** — este último resultó ser el hallazgo real: un **archivo histórico de descarga directa** (no un dashboard ni un catálogo CKAN) con CO, NO2, O3, PM2.5, PM10, SO2 y datos meteorológicos (viento, humedad, presión, temperatura, radiación solar/UV, precipitación) **2004-2025**, más un documento de marco QA/QC. El obstáculo real no es técnico (no hace falta browser para esta parte) sino que **los archivos están en formato `.rar`** — exactamente el formato que este proyecto ya descartó explícitamente por riesgo de subprocess/CVE (ver Descartado). El dashboard en tiempo real (`aireambiente.quito.gob.ec`) sigue sin confirmar si necesita browser real.

**Vivienda MIDUVI — el dominio nuevo también falla, mismo patrón que el viejo.** El ministerio parece haberse renombrado a "Ministerio del Hábitat y Vivienda" con dominio `habitatyvivienda.gob.ec`; verificado en vivo que **también falla a nivel TLS**, pero de una forma reveladora: el certificado presentado es uno compartido que cubre otros ~25 dominios `.gob.ec` (agricultura, ambienteyenergia, defensa, salud, etc.) pero **no incluye `habitatyvivienda.gob.ec` en su lista de nombres alternativos** — un dominio mal configurado en la infraestructura TLS compartida del gobierno, no un servidor caído. Confirma que el problema documentado en la Séptima pasada no era específico del dominio viejo `miduvi.gob.ec`, sino algo más amplio en cómo este ministerio gestiona su TLS. Entidad relacionada `viviendaydesarrollourbano.gob.ec` ("Vivienda y Desarrollo Urbano EP") mencionada en las búsquedas pero no verificada en vivo todavía.

### Sub-objetivos concretos encontrados dentro de ítems ya conocidos

**SENESCYT — portal de estadísticas de educación superior no mencionado antes.** Además del registro de títulos bloqueado por captcha (ya documentado), `siau.senescyt.gob.ec/estadisticas-de-educacion-superior-ciencia-tecnologia-e-innovacion/` tiene contenido real descargable: fichas metodológicas, reportes de indicadores 2021/2022/2024, índice de competitividad, inventario de indicadores de ciencia/tecnología/innovación/saberes ancestrales, análisis de demanda laboral, y un estudio de impacto COVID-19 en educación superior — todos con fecha y tamaño de archivo visibles. Candidato real para ampliar la cobertura de SENESCYT más allá de CKAN + biblioteca.

**Superbancos — ubicado el área correcta para Balances/Solidez Financiera, mecanismo de extracción aún sin confirmar.** La búsqueda anterior (Séptima pasada) no tenía la URL exacta; esta pasada la ubica: `superbancos.gob.ec/estadisticas/portalestudios/` tiene una sección "Indicadores de Solidez Financiera" (`volumen-de-credito-2/` y páginas hermanas) con **series históricas desde enero de 2003**, catálogo financiero estandarizado desde 2015. Todavía no confirmado si es una lista de archivos estáticos (como Boletines Financieros Mensuales, ya cubierto) o una herramienta de consulta que exige parámetros de institución/fecha (como se sospechaba) — hace falta una pasada con browser real sobre esa URL específica antes de decidir.

**Datos legislativos — FCD tiene dos portales dedicados, no solo un interés temático.** `observatoriolegislativo.ec` (monitoreo de la Asamblea Nacional) y `ojoalconcejo.org` (monitoreo de concejos municipales) son propiedad y operación de la Fundación Ciudadanía y Desarrollo — plataformas reales, no solo informes PDF. No cambia la decisión de alcance de Daniel (sigue "puede no ser relevante"), pero si el alcance cambiara, estos dos son el punto de entrada concreto, no la Asamblea Nacional directamente.

**Fuentes internacionales — dos APIs concretas confirmadas, no solo nombres de instituciones.** CEPALSTAT tiene un **Open Data API** documentado en `estadisticas.cepal.org/cepalstat/web_cepalstat/openDataAPI.asp`. El FMI tiene una API SDMX 2.1/3.0 moderna y bien documentada en `data.imf.org` (Swagger, `datahelp@imf.org` como soporte) cubriendo International Financial Statistics (194 países, incluido Ecuador) — tipo de cambio, balanza de pagos, liquidez internacional, dinero y banca, tasas de interés, precios. Ambas mucho más concretas que la mención genérica "CEPALSTAT/FMI" que tenía el roadmap antes.

**Gremios privados — ASOBANCA Datalab confirmado como app Qlik, no una SPA genérica.** La URL real trae un parámetro `QlikTicket=` — es una aplicación **QlikView/QlikSense embebida** ("Clicstat"), con más de 30 indicadores internacionales y datos de 24 bancos privados/74 cooperativas, fuentes primarias declaradas (Superbancos, BCE, SEPS, INEC, FELABAN). Extraerla exigiría o bien la API del motor Qlik (WebSocket) o encontrar un endpoint de exportación — no confirmado en esta pasada, pero ahora se sabe exactamente qué tecnología hay que vencer.

### Confirmado sin cambios de fondo (revisado, sin hallazgo nuevo que amerite actualizar la nota existente)

- **CNE** — sin evidencia de que el bloqueo Incapsula haya cambiado; decisión sigue pendiente de Daniel (Playwright sí o no).
- **CORDES** — confirmado que es un think tank privado (fundado 1984) que publica libros/PDFs, sin evidencia de una base de datos pública o API. Bajo valor confirmado, no solo sospechado.
- **Nowcast / Encuesta de Expertos (BCE)** — confirmado que el BCE solo publica PIB trimestral con ~3 meses de rezago; no se encontró un producto de datos de "nowcast" oficial y en vivo (existen papers académicos de modelos de nowcasting para Ecuador, pero no son un dato que el BCE publique). El EMOE (`indice-de-expectativas-de-la-economia-indice`, ya cubierto vía `search_bce_indices`) es lo más cercano a una "encuesta de expectativas" real que existe hoy.
- **Prensa** — Fundamedios es real y activo (informe semestral 2026: 100 agresiones enero-junio, histórico desde 2007), pero su contenido es informes narrativos en PDF, no datasets estructurados descargables — encaja mejor con `read_pdf` puntual que con un tool de datos dedicado. SECOM parece ser una oficina de comunicación/relaciones con prensa, no un publicador de datos.
- **Permisos y portales municipales / Geoportales municipales** — `municipiosabiertos.gob.ec` confirma el marco de 221 GADs y que Cuenca, Quito y Riobamba son los más avanzados (Cuenca ya cubierto); no se encontró ninguna URL de GeoServer/ArcGIS nueva para Quito/Riobamba/Portoviejo/Ambato más allá de lo ya documentado en la Decimosexta pasada.
- **Registro Oficial** — confirmada la estructura del sitio (`registroficial.gob.ec`: ediciones ordinarias, suplementos, ediciones especiales, edición constitucional, edición jurídica, índice mensual, buscador visible), pero no se confirmó el mecanismo exacto de descarga por fecha ni si requiere login — sigue necesitando una pasada con browser real antes de decidir.
- **Sector eléctrico (`reportes.arconel.gob.ec`) y AIP GEN/ENR/AMDT** — no se revisaron de nuevo en esta pasada: ya están completamente mapeados y lo único pendiente es construir, no investigar (ver Vigésima y Vigésimo primera pasadas).
- **Archivo histórico de cortes de luz, SENESCYT registro de títulos, INEC preview de archivos grandes, CEPAL geoportal del censo** — no se encontró información nueva más allá de lo ya documentado; notas existentes se mantienen sin cambios.

---

## Vigésimo quinta pasada — CEPALSTAT, IADB Latin Macro Watch y World Bank/IADB DPI verificados en vivo (2026-09-09)

**Contexto:** Daniel citó un extracto de un paper que usa IFS (FMI), Latin Macro Watch (IADB) y la Database of Political Institutions (Banco Mundial/IADB) — preguntando si son fuentes reales y viables. Verificación en vivo de las tres, más CEPALSTAT (ya mencionado como pendiente de verificar en la Vigésimo cuarta pasada).

**CEPALSTAT — API REST pública real, confirmada con una llamada de datos completa.** `api-cepalstat.cepal.org/apispec_1.json` es un spec OpenAPI 3 real (`CEPALSTAT API - Public`, sin `securityDefinitions` — confirmado sin autenticación). Endpoints bajo `/cepalstat/api/v1/`: `thematic-tree` (árbol completo de áreas/indicadores, 375 KB), e `indicator/{id}/{areas,data,dimensions,footnotes,metadata,publications,records,sources}`. Probado en vivo contra el indicador 4788 ("Total population, by sex"): `/areas` devuelve las áreas temáticas donde vive el indicador; `/data` devuelve un payload real de 2.5 MB con metadata completa (unidad, definición, metodología de cálculo) y los datos 1950-2100 para todos los países de la región. El endpoint `/data` acepta `lang` (en/es), `format` (json/xml/yaml/csv/excel) y `members` (para acotar por dimensión/país) — confirmado en el spec, no probado con un `indicator_id` de Ecuador específico todavía. Necesita un cliente dedicado (no es CKAN).

**IADB Latin Macro Watch — confirmado que vive en un portal CKAN estándar, no en una herramienta propietaria.** `data.iadb.org` responde a `/api/3/action/package_search` exactamente igual que `datosabiertos.gob.ec` (692 datasets totales en el portal, confirmado con una llamada real). El paquete `latin-macro-watch-dataset` tiene **665 recursos CSV**: desempleo, IPC, tipo de cambio nominal bilateral con USD, precios de importación/exportación, y (según los resultados de búsqueda) ingresos/gastos/balance fiscal por nivel de gobierno (gobierno central, gobierno general, sector público no financiero), en moneda local y USD, mensual/trimestral/anual desde 1990, para 26 países prestatarios del BID incluido Ecuador — exactamente el tipo de panel fiscal trimestral que cita el paper de Daniel.

**World Bank/IADB Database of Political Institutions (DPI) — mismo portal CKAN, dataset pequeño y manejable.** El paquete `the-database-of-political-institutions-dpi-2023` tiene solo 3 recursos: el codebook en PDF, y los datos completos en XLSX y CSV — ~180 países, 1975-2023, con fechas de elecciones, medidas de pesos y contrapesos, afiliación/ideología partidaria, y fragmentación de oposición y gobierno en el legislativo. Originalmente compilado por el Banco Mundial (2000), ahora alojado y mantenido por el BID en el mismo portal que Latin Macro Watch.

**Implicación de arquitectura:** como ambos datasets de IADB viven en un CKAN genuino, se podrían exponer agregando `source="iadb"` al cliente CKAN ya existente en este proyecto (mismo patrón que `source="cuenca"`/`"latacunga"` para los portales municipales) — sin necesidad de ningún scraper nuevo, solo apuntar el cliente genérico a una base URL distinta. CEPALSTAT, al ser una API REST propia (no CKAN), sí necesitaría un cliente dedicado nuevo, aunque más simple que la mayoría de los ya construidos en este proyecto (JSON limpio, sin autenticación, sin HTML que parsear).

Nada de esto se construyó todavía — verificación de viabilidad solicitada explícitamente por Daniel, no una implementación.

**Construido, 2026-09-10:** los dos candidatos IADB y CEPALSTAT, siguiendo
exactamente la implicación de arquitectura de arriba.

- **IADB (`source="iadb"`):** agregado a `_SOURCES` en
  `helpers/ckan_client.py` junto con `helpers/env_config.py`
  (`https://data.iadb.org/api/3/action/`) — los 15 tools CKAN genéricos
  existentes (`search_datasets`, `get_dataset_info`,
  `list_dataset_resources`, etc.) funcionan contra este source sin ningún
  código nuevo por tool, solo el docstring de cada uno actualizado para
  mencionarlo. **Hallazgo nuevo no anticipado en la pasada anterior:** el
  perfil CKAN de `data.iadb.org` (esquema IDB DataCatalog) devuelve
  `title`/`notes`/`description` a nivel de paquete como un dict
  multilingüe (`{"es": ..., "en": ..., "fr": ..., "pt_BR": ...}`) en vez de
  un string plano — confirmado en vivo contra `package_show` del dataset
  `latin-macro-watch-dataset`. Los campos a nivel de recurso (`name`,
  `format`, `url`) siguen siendo strings planos. Sin normalizar, todas las
  tools existentes habrían impreso el dict crudo de Python donde esperaban
  un título. Resuelto con `_localize()`/`_localize_result()` en
  `ckan_client.py`, aplicado dentro de `_fetch_json` — colapsa a
  es→en→primer valor disponible, no-op para cualquier otro source donde el
  campo ya es un string. Verificado en vivo: `latin-macro-watch-dataset`
  (665 recursos) y el dataset DPI 2023 (3 recursos) ambos confirmados con
  el título en español correctamente resuelto.
- **CEPALSTAT (`search_cepalstat_indicadores`, `get_cepalstat_indicador`,
  `helpers/cepalstat_client.py`):** confirmado en vivo el endpoint
  `/thematic-tree` (2.059 indicadores, no 2.059 de memoria — contado en
  vivo) y, contra el indicador 4788, que `members=<id>` acepta un solo id
  (no exige uno por dimensión) — pasar solo el id de país filtra
  correctamente sin restringir año/sexo, bajando el payload de 2.5 MB a
  ~85 KB. Cada fila de datos cruda llega como pares opacos
  `dim_<dimension_id>: <member_id>`; decodificados a etiquetas legibles
  (`"Sexo": "Mujeres"`) usando el bloque `dimensions` de esa misma
  respuesta, que lista todos los miembros de cada dimensión del indicador,
  no solo los que coinciden con el filtro. El nombre de dimensión trae un
  sufijo interno de esquema de clasificación ("País__ESTANDAR") que se
  recorta para mostrar solo "País". `download_bytes` (mismo límite de 5 MB
  que el resto del proyecto) en vez de un `httpx.get` sin límite, porque
  CEPALSTAT no tiene su propio mecanismo de límite de tamaño y un indicador
  sin filtrar puede superar unos pocos MB.

---

## Vigésimo sexta pasada — verificación de duplicados antes de documentar Homicidios/Puerto Bolívar/Cancillería como "ya reachable" (2026-09-10)

**Contexto:** Daniel preguntó explícitamente si estas tres ya tenían cobertura por otro portal del proyecto antes de marcarlas como Hecho — verificación de duplicados, no investigación desde cero.

**Homicidios Intencionales vs. `search_cnig_femicidios` — no es duplicado.** El docstring de `search_cnig_femicidios` ya advertía que el PDF de CNIG "states its figures are compiled from ... Ministerio del Interior source data" — señal real de posible superposición. Confirmado que no lo es: CNIG publica un snapshot PDF fechado (contenido cortado en abril 2023) de un subconjunto específico, "Femicidios y Homicidios Intencionales **de Mujeres**" — solo víctimas mujeres. El dataset de Interior (`ministerio-del-interior`, organización CKAN con 6 paquetes confirmados en vivo) es el total nacional por todas las víctimas, en XLSX nativo, con mensual 2026 + histórico 2014-2025 + microdatos 2014-2024 (93 MB) — más amplio, más actual, y en mejor formato. Complementario, no redundante.

**Puerto Bolívar vs. cualquier otra fuente — no hay superposición, pero sí una fuente nueva encontrada sin buscarla.** `list_organizations(query="puerto")`/`query="bolivar")` solo devuelve `autoridad-portuaria-de-puerto-bolivar-appb`. Pero `query="portuaria"` reveló dos organizaciones más, nunca documentadas: `autoridad-portuaria-de-guayaquil-apg` (6 paquetes: distributivo de personal, remuneración mensual, buques por muelle, tonelaje y contenedores de importación/exportación) y `apm` (11 paquetes) — que resultó ser la **Autoridad Portuaria de Manta**, no APM Terminals como sugiere el slug (confirmado por el campo `title` real de la organización): buques arribados, TEUs, carga, vehículos, turistas. Las tres autoridades portuarias principales del país tienen organización CKAN real, no solo Puerto Bolívar.

**Cancillería vs. `search_tramites`/`get_tramite_estadisticas` — adyacente, no duplicado.** `tools/search_tramites.py` ya mapea la institución "16" (Ministerio de Relaciones Exteriores) para pasaporte/apostilla/visa — señal real de posible superposición. Confirmado que no lo es: esas tools dan tiempos de atención y quejas por trámite individual (métricas de servicio de gob.ec), no los registros administrativos en sí. La organización CKAN (`ministerio-de-relaciones-exteriores-y-movilidad-humana`, 13 paquetes confirmados en vivo) es más rica de lo documentado en la Vigésimo cuarta pasada: 9 paquetes de "Registro Movilidad Humana" desagregados (Visas, Apostillas y Legalizaciones, Órdenes de Cedulación, Actos Notariales, Pasaportes de Emergencia, Certificado de Migrante Retornado, Naturalizaciones, Solicitantes de Refugio, Histórico Refugiados Anuales), más Autorización de salida de menores, Presupuesto de Misiones Diplomáticas y Ayuda y financiamiento internacional — datos administrativos reales, no estadísticas de servicio.

**Conclusión:** las tres fuentes quedan confirmadas como Hecho sin cliente dedicado (ver ROADMAP.md), con la adyacencia a tools existentes documentada explícitamente para que no se confunda con duplicación en una lectura futura. Bono: dos organizaciones portuarias nuevas (APG, APM/Manta) encontradas sin haber sido buscadas explícitamente.

**SRI genérico y MEF genérico — mismo chequeo, confirmados no duplicados.** `sri-servicio-de-rentas-internas` (127 paquetes) no se superpone con `search_sri_datasets`/`search_sri_estadisticas_recaudacion` (RUC por provincia, catastro de contribuyentes, comprobantes CEL, vehículos, índice de actividad empresarial — contenido distinto); único solape posible sin confirmar es el nivel de agregación de "Recaudación de Impuestos - YYYY" (anual) contra el mensual ya cubierto. `ministerio-de-economia-y-finanzas` (97 paquetes) no se superpone con `search_mef_fiscal` (metodología GFSM) — cubre ejecución de nóminas/PGE/distributivo de remuneraciones, un ángulo de nómina que `search_mef_fiscal` no toca; aparenta desactualizado desde mediados de 2025.

**IEPS, COSEDE, IPAIP — confirmados no duplicados, mismo chequeo.** IEPS (106 paquetes) es una institución distinta de SEPS (fomento vs. regulación). COSEDE (88 paquetes, seguro de depósitos) no se superpone con Superbancos ni SEPS. IPAIP (70 paquetes) es un índice de publicaciones científicas por especie — no hay ninguna otra fuente de pesca/acuicultura en el proyecto.

**MAG genérico — las dos preguntas abiertas, resueltas con evidencia directa (2026-09-10, mismo día).** Descargado el contenido completo de dos paquetes representativos:

- **Precios de agroindustrias — NO contradice la decisión "Descartado" de la Duodécima pasada.** Esa decisión evaluó específicamente "precios mayoristas" de SIPA (Mercado Mayorista Quito/Guayaquil/Cuenca, documentos regulatorios de piso/techo sin historia, sobreescritos cada vez). El paquete `mag` "Precios promedio mensuales de agroindustrias correspondientes a extractoras de aceite" es un producto completamente distinto: precios pagados por plantas procesadoras a productores (aceite, cacao, café, granos, azúcar), con nota explícita "Datos desde el año 2012" y recursos reales por mes confirmados desde 2022 hasta agosto 2026 (16-22 recursos por paquete, no una sola instantánea). Los dos conceptos de precio (mayorista/minorista vs. productor/planta) no son la misma serie — la decisión anterior queda intacta porque nunca evaluó esta.
- **Los mapas SÍ duplican el Geoportal de SIPA — confirmado con coincidencias de título exactas, no solo con un host compartido.** Verificación inicial (un solo recurso de "Zonificación Agroecológica del cultivo de Aguacate Hass" apuntando a `geoportal.agricultura.gob.ec/geonetwork/...`) extendida a los 54 paquetes tipo "mapa" del catálogo `mag`: 49 de 54 (91%) tienen al menos un recurso cuya URL apunta a ese mismo geoportal. Un primer intento de cruce por coincidencia de substring exacto contra las 277 capas reales de `search_sipa_geoportal_capas` dio 0 coincidencias — **resultó ser un bug en la lógica de comparación (substring demasiado estricto), no evidencia de que no haya solape.** Repetido con búsquedas por palabra clave directamente contra el catálogo real de SIPA, aparecen coincidencias exactas de título: "Mapa de Susceptibilidad a Inundaciones Ecuador Continental, escala 1:25.000, 2024" (idéntico palabra por palabra en ambos catálogos), "Zonificación agroecológica del Aguacate Hass", "Capacidad de uso de las tierras", "Conflictos de uso de las tierras", "Cobertura y uso de la tierra", "Aptitud biofísica para el uso de maquinaria agrícola" — y toda la familia "Zonificación agroecológica del [cultivo]" existe en ambos catálogos, cultivo por cultivo (confirmado para banano, aguacate, y más). Construir un scraper separado para estos paquetes CKAN duplicaría contenido ya servido en vivo por el geoportal; los XLSX/CSV descargables de estos paquetes son, en el mejor caso, un export estático de la misma capa, no dato nuevo.

Con esto, MAG genérico queda documentado en ROADMAP.md con ambas respuestas resueltas, no como pregunta abierta.

**`get_organization_info` ganó un parámetro `query` (2026-09-10).** Pedido explícito de Daniel ("include them in the MCP") tras verificar SRI/MEF/IEPS/COSEDE genéricos: el tool ya existía y ya los cubría técnicamente, pero truncaba a 25 datasets incluso en `format=json` — insuficiente para navegar una organización de 97-127 paquetes sin adivinar. Ahora filtra por texto (accent-insensitive) contra el título de cada dataset, y `format=json` devuelve el total real sin truncar; `format=text` sigue capado (60) con aviso de cuántos más hay. No se construyeron tools dedicados por-ministerio para SRI/MEF genéricos — habría duplicado este mismo tool con un `organization_id` fijo, contra el objetivo explícito del proyecto de reducir duplicación en la superficie pública (ver MCP_ARCHITECTURE.md).

**Gacetas de Inmunoprevenibles del MSP — construido (2026-09-10).** Investigación inicial disparada por Daniel preguntando específicamente por "gacetas inmunoprevenibles". Confirmado en vivo: `salud.gob.ec` expone la API REST estándar de WordPress (`/wp-json/wp/v2/posts`, sin auth) — buscar "inmunoprevenibles" devuelve los 28 resultados reales en una sola página (`X-WP-Total: 28`, `X-WP-TotalPages: 1` con `per_page=100`), de los cuales filtrar por slug con prefijo `gacetas-inmunoprevenibles` da exactamente las páginas de archivo reales: 9 páginas (2019, 2021, "2022-2", 2023, 2024, 2025, 2026, la página sin sufijo ≈2020-2021, y una página "-2" vacía sin PDFs). Cada página de archivo es una tabla Gutenberg plana con links `<a href="...pdf">` — más simple que el patrón download-monitor usado en otras fuentes de este proyecto. Confirmado en vivo: 362 PDFs tras deduplicar por URL (las páginas se solapan en los bordes de año, p. ej. SE-52/53 aparecen en la página saliente y en la entrante bajo nombres de archivo distintos). **El nombre de archivo cambió al menos 5 veces** a lo largo del archivo (`INMUNO_NN_YYYY.pdf` → `INMUNO-SE-NN.pdf` → `Inmunoprevenibles-SE-NN.pdf` → `GACETA-GENERAL-INMUNOPREVENIBLES-SE-NN.pdf` → `Eventos-Inmunoprevenibles-CT_-DNVE-SE-NN.pdf` → `Gaceta-EPV-SE-NN.pdf`) — `semana` se extrae con una regex "SE" tolerante a todos estos; `anio`/`mes` vienen de la ruta `/uploads/YYYY/MM/`, que se mantuvo estable aunque el nombre de archivo no. Desde 2024 algunas semanas traen un reporte complementario por enfermedad específica (confirmado: "tosferina"), detectado por palabra clave en el nombre de archivo, no asumido como el único caso posible. Construido como `search_gacetas_inmunoprevenibles` (`helpers/msp_gacetas_inmunoprevenibles_client.py`), con descubrimiento de páginas dinámico (vía la API REST, no una lista de años hardcodeada) para que los años futuros aparezcan solos. **Descubrimiento colateral, no perseguido:** el MSP publica otras series de gacetas semanales en paralelo bajo el mismo patrón — "gacetas-vectoriales-2026", "gacetas-de-enfermedades-de-la-piel-o-reemergentes-2026", "gaceta-indicadores-2026", y una serie más amplia "Gacetas Epidemiológicas" (`gacetas-epidemiologicas-2`) distinta de inmunoprevenibles — ninguna construida todavía, documentadas como pendiente en ROADMAP.md.

---

## Notas históricas

**Corrección de diagnóstico (2026-08-13):** el 403 de CKAN que se creía un
bloqueo geográfico/upstream era en realidad un bug de vhost — el apex
`datosabiertos.gob.ec` y el subdominio `presidencia` resuelven a la misma
IP pero devuelven 403; solo `www.datosabiertos.gob.ec` está conectado. Ya
corregido en el repo; los 38 tools funcionan.
