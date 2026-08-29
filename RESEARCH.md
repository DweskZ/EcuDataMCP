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
IESS; necesitaría `download_resource` o un tope más alto, no
`preview_resource_data` tal cual). Y eso es solo un módulo — el sitio
además tiene "Cifras Agroproductivas" y "Cifras Territoriales" (tableros
dinámicos, probablemente Power BI, sin confirmar), boletines nacionales
(Panorama Agroestadístico, Precios Mayoristas, Precios Internacionales,
Precios Productor), boletines situacionales por cultivo (ej. papa), un
Panorama Agroeconómico anual, y un geoportal propio de ortofotos
(`geoportal.agricultura.gob.ec`) — más geoespacial, sin explorar. Esto
reemplaza por completo la cobertura actual de `detect_series_pattern`/
cacao vía MPCEIP: es la fuente real y mucho más rica para todo lo
agropecuario. Candidato de máxima prioridad para una integración nueva.

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

**Investigado 2026-08-29,** pedido explícito de Daniel: Observatorio
Legislativo, Observatorio de los GADs, Observatorio de Gasto Público "y
otros observatorios de la misma organización/fundación".

**Nota de alcance:** este proyecto se describe (CLAUDE.md) como datos *del
gobierno* ecuatoriano vía CKAN/gob.ec/SRI/BCE/etc. — estas fuentes son de
una fundación de sociedad civil, no del Estado. Investigado igual porque se
pidió explícitamente, pero decidir si integrarlas es una decisión de
alcance del proyecto, no solo técnica.

**Fundación Ciudadanía y Desarrollo (FCD)** es la organización detrás de
todos los observatorios que Daniel nombró. Mantiene una red de
observatorios temáticos, cada uno con su propio dominio: **Observatorio
Legislativo** (`observatoriolegislativo.ec`, monitorea la Asamblea
Nacional, miembro de la Red Latinoamericana de Transparencia Legislativa),
**Observatorio Judicial** (`observatoriojudicial.ec`, control ciudadano a
la Función Judicial), **Observatorio de Gasto Público**
(`gastopublico.org`, presupuesto/gasto/déficit fiscal, incluye análisis del
gasto municipal de Quito/Guayaquil/Cuenca — esto parece cubrir lo que
Daniel busca como "Observatorio de los GADs", no se encontró un
observatorio de GADs con dominio propio y separado), más observatorios de
anticorrupción y de financiamiento político (sin dominio propio
confirmado, viven dentro de `ciudadaniaydesarrollo.org`).

**Naturaleza del contenido:** son informes de análisis (PDF narrativos) y
notas de prensa, no datasets tabulares descargables —
`gastopublico.org/indicadores` no tiene ningún archivo `.csv/.xlsx/.pdf`
enlazado directo (confirmado revisando el HTML), así que el valor está en
la interpretación/narrativa, no en datos crudos reutilizables
programáticamente. Distinto en naturaleza a todo lo demás en este
documento.

**Grupo FARO** (`grupofaro.org`) — think tank de política pública más
grande de Ecuador en este espacio, calcula el Índice de Presupuesto
Abierto de Ecuador (Open Budget Survey), más de 200 publicaciones en 15
años. Mismo perfil que FCD: análisis e investigación, no un catálogo de
datos crudos.

**"Gobierno Abierto Ecuador"** (`gobiernoabierto.ec`) — portal multi-actor
(aparece firmando compromisos junto a CNE y FCD) — mencionado en la
búsqueda pero no visitado.

**Conclusión:** estas fuentes son reales y de buena reputación (FCD es el
punto de contacto nacional de Transparencia Internacional), pero en esta
investigación no se encontraron datasets tabulares crudos comparables a
SIPA, la IEM del BCE, o Contraloría — es contenido editorial/analítico
sobre datos gubernamentales, no una fuente primaria alternativa. Si el
interés es citarlos como análisis/contexto (no como fuente de datos
estructurados), valdría la pena un tool tipo `search_analisis_civico` más
adelante — pero eso es una decisión de producto distinta a "encontrar más
datos", y toca decidir si encaja con el alcance de "datos abiertos de
gobierno" que define este proyecto hoy.

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

## Notas históricas

**Corrección de diagnóstico (2026-08-13):** el 403 de CKAN que se creía un
bloqueo geográfico/upstream era en realidad un bug de vhost — el apex
`datosabiertos.gob.ec` y el subdominio `presidencia` resuelven a la misma
IP pero devuelven 403; solo `www.datosabiertos.gob.ec` está conectado. Ya
corregido en el repo; los 38 tools funcionan.
