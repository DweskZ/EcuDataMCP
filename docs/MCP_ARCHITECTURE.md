# Revisión de arquitectura MCP

Revisión iniciada el 2026-08-31 para decidir si EcuDataMCP debe simplificar,
armonizar o reducir su número de tools. Es una guía de diseño, no implica que
todos los cambios deban hacerse de una sola vez — ver "Plan de ejecución" al
final para el orden real.

## Historial de conteos

El número de tools registradas creció durante toda la vida de esta revisión.
Cada fila refleja el conteo exacto verificado en esa fecha — no se
reescriben retroactivamente cuando el total sube después.

| Fecha | Total | Qué cambió |
|---|---|---|
| 2026-08-31 | 74 | Revisión original. |
| 2026-09-04 | 103 | Recalculado contra el repo actual; diagnóstico y diseño siguen válidos, sin duplicación nueva entre las 29 tools agregadas. Bug de versión fija en `list_capabilities` corregido (`helpers/version.py` es ahora la única fuente de verdad). |
| 2026-09-05 | 100 | Se removieron 3 tools de SRI Saiku (`srienlinea.sri.gob.ec` confirmado inalcanzable desde tres entornos distintos). |
| 2026-09-05 | 102 | Se agregaron 2 tools de ARCSA (`list_arcsa_categorias`, `get_arcsa_categoria_archivos`). |
| 2026-09-10 | 115 | +13: BCE Cuentas Nacionales (2), calendario de publicaciones BCE (1), SENESCYT SIAU + Biblioteca (3), CEPALSTAT (2), Gacetas de Inmunoprevenibles del MSP (1). Ver auditoría 2026-09-11 abajo para la verificación directa contra el código, no solo un barrido nombre por nombre. |

**Patrón ya en uso para no agregar tools por fuente nueva:** la ampliación
de `source=` a `"iadb"` en los tools CKAN genéricos existentes, y el nuevo
parámetro `query` en `get_organization_info` (en vez de tools nuevos
por-organización para SRI/MEF genéricos) — ver docs/RESEARCH.md § Vigésimo
sexta pasada. Es exactamente la recomendación de "preferir una tool
parametrizada sobre duplicar la superficie pública" ya aplicada dos veces.

## Conclusión corta

El número bruto no es, por sí solo, un problema de MCP: `tools/list` admite
paginación y la especificación no fija un máximo pequeño. El problema real es
la forma de describir y devolver esas tools — todas aceptan `format: str` y
devuelven `str`, sin `title`, sin anotaciones, sin schema de entrada
tipado, y sin distinguir una tool de solo-lectura de una que escribe
artefactos locales.

**Sobre si 115 es demasiado (pregunta directa de Daniel, 2026-09-11):**
auditoría dirigida contra el código (no solo un barrido nombre-por-nombre)
encontró **exactamente 2 duplicados reales**, sin cambios respecto a la
revisión original. 115 tools cubriendo 115 endpoints genuinamente distintos
de un panorama de datos gubernamentales fragmentado es, hasta donde se pudo
verificar, un conteo honesto — no hay una bolsa grande de redundancia
escondida. La recomendación sigue siendo la misma: mantener las capacidades
específicas de cada fuente, reducir solo donde hay duplicación clara, y
resolver la fatiga de navegación con perfiles + mejores descripciones, no
con una purga arbitraria.

## Auditoría de redundancia real (2026-09-11)

Daniel pidió verificar directamente, no confiar en el resumen de la
revisión anterior. Se re-auditó el cluster más grande (BCE, 14 tools) leyendo
el código y RESEARCH.md directamente, más un barrido de nombres sobre las
115 tools completas.

**Los 2 duplicados reales ya identificados siguen siendo los únicos:**
1. `search_datasets` / `list_recent_datasets` — mismo catálogo, la segunda
   solo cambia el criterio de orden.
2. `list_capabilities` — repite información ya disponible en el recurso
   `ecuador://fuentes`.

**Cluster BCE (14 tools) — la superposición aparente está resuelta con
evidencia dura, no es descuido:**

- `search_bce_indices` cubre remesas, precios de comercio exterior y
  boletines monetarios semanales *por nombre* entre sus ~35 páginas
  "índice" — a primera vista se solapa con `search_bce_remesas`,
  `search_bce_precios_comex` y `search_bce_publicaciones`. Investigado a
  fondo en cada caso:
  - Remesas: la página índice es un *boletín analítico* (comentario,
    distinto artefacto), no la serie cruda que `search_bce_remesas` ya
    expone. Mantenidos separados a propósito.
  - Precios de comercio exterior: `search_bce_precios_comex` fue
    construido tras confirmar en vivo que sus dos páginas fuente no
    aparecen en el descubrimiento de `search_bce_indices` (sus slugs no
    terminan en "-indice(s)") y exponen desagregación por producto que no
    existe en ningún otro lado del proyecto. Una tercera página candidata
    (serie histórica IPX/IPM/ITI) fue investigada y **descartada
    explícitamente** tras cruzar valores exactos en vivo con BCEData
    (ITI, IPX idénticos salvo ruido de precisión de punto flotante) —
    hubiera sido un duplicado puro.
  - Boletines monetarios semanales: `bce_indices_client.py` ya excluyó
    activamente una página duplicada (`reporte-monetario-semanal`,
    mismo conteo de archivos y rango de años que
    `reporte-monetario-semanal-indices`). El solape restante entre
    `search_bce_indices` (archivo histórico completo de una serie) y
    `search_bce_publicaciones` (ventana rodante de ~30 publicaciones
    recientes de tipos mixtos) es un solape de *contenido*, no de
    *tool* — ambas herramientas sirven propósitos distintos (archivo
    completo de una serie vs. panorama de qué se publicó últimamente) y
    la misma publicación puede aparecer en ambas legítimamente. No hay
    nada que fusionar aquí sin perder una de las dos funciones.
- Ningún otro tool de BCE se superpone: BCEData, IEM, indicadores
  diarios/mensuales y Cuentas Nacionales están explícitamente delimitados en
  sus propios docstrings contra los otros tres.

**Dos candidatos de fusión nuevos, encontrados en esta pasada — no son
duplicados, son hermanos con la misma forma de parámetros:**

| Candidato | Forma actual | Fusión posible |
|---|---|---|
| `get_metar(designador)`, `get_notam(designador)`, `get_sigmet()` | 3 tools DGAC, firma casi idéntica | `get_reporte_aeronautico(tipo, designador=None)` |
| `search_arcotel_boletines(query)`, `search_arcotel_reportes_mensuales(query)` | 2 tools ARCOTEL, firma idéntica | `search_arcotel(tipo, query="")` |

Ejecutar estas dos fusiones bajaría el conteo en hasta 3 (115 → 112), sumado
a las 2 reducciones ya planeadas (→ 110). Es un ahorro real pero modesto —
no cambia la conclusión de que la cantidad bruta no es el problema central.

**Un tercer candidato investigado y descartado, por completitud:**
`search_infomies_bases_mensuales` (`serie`, `anio`) vs.
`search_infomies_boletines_zonales` (`modo`, `zona`, `anio`) — parámetros
genuinamente distintos. Fusionarlos produciría exactamente el patrón que la
regla 4 más abajo ya prohíbe: argumentos opcionales según el caso y
respuestas de forma variable. Se mantienen separados.

## Arquitectura propuesta

Un solo repositorio puede contener dos perfiles del mismo servidor:

```text
Perfil público
  Herramientas de búsqueda y consulta de datos
  Solo lectura para el usuario final

Perfil de mantenimiento
  audit_bce_catalog
  compare_bce_sources
  Otras herramientas operativas futuras
```

Los dos perfiles comparten `helpers/`, clientes, pruebas y modelos. Solo cambia
qué tools se registran en cada instancia `FastMCP`.

En producción podrían ser dos servicios del mismo contenedor:

```text
mcp-public       → endpoint público
mcp-maintenance  → endpoint local o protegido para el operador
```

La separación no borra ni duplica la lógica. Evita que una persona que busca un
dataset tenga que ver herramientas que auditan catálogos o guardan snapshots.
Además, `audit_bce_catalog` y `compare_bce_sources` pueden escribir artefactos
locales, por lo que no deben tratarse igual que una consulta pública.

## Reducciones recomendadas

### 1. Retirar `list_capabilities` de la superficie pública

Trasladar las instrucciones generales a `FastMCP(instructions=...)` y conservar
`ecuador://fuentes` como catálogo estructurado. Para no romper clientes viejos,
se puede mantener el tool como alias durante una versión y después retirarlo.

### 2. Integrar datasets recientes en `search_datasets`

Usar una sola tool con un criterio de orden explícito, por ejemplo:

```text
search_datasets(query="", sort="recent")
```

La respuesta debería tener el mismo formato en ambos casos. Esto elimina una
duplicación real, no solo dos nombres parecidos.

### 3. Separar las tools de mantenimiento

Mover `audit_bce_catalog` y `compare_bce_sources` a la instancia de
mantenimiento. Siguen disponibles en el repositorio y para el operador, pero
no aparecen en el menú público.

### 4. No fusionar todos los pares `list`/`get`

Estos pares suelen representar un flujo lógico de dos pasos:

```text
list_sipa_modulos() → get_sipa_modulo_archivos("economico")
```

Fusionarlos normalmente produce una tool con argumentos opcionales, respuestas
de varios tipos y reglas difíciles de explicar. Se mantienen separados, en
particular para SIPA, Superbancos, Contraloría y BCEData/IEM.

### 5. (Opcional, bajo impacto) Fusionar hermanos de forma idéntica

Ver la tabla de la auditoría 2026-09-11 arriba: aviación (METAR/NOTAM/SIGMET)
y ARCOTEL (boletines/reportes mensuales) son candidatos porque comparten
firma exacta, no porque haya evidencia de fusión previa. A diferencia de la
regla 4, esto no es un flujo de dos pasos — es la misma pregunta
("dame el reporte de tipo X") repetida tres o dos veces. Evaluar caso por
caso si el nombre específico (ej. `get_metar`, término estándar de aviación
que un modelo reconoce sin ayuda) vale más que el ahorro de una tool.

## Armonización de nombres

Los nombres existentes deben conservarse para no romper clientes. Para tools
nuevas, usar una convención consistente y orientada a la tarea:

```text
search   → descubrir
list     → enumerar opciones
get      → obtener un elemento identificado
query    → consultar valores
preview  → leer una muestra
download → obtener un archivo
audit    → revisar el estado del sistema
```

También conviene definir una convención para tools nuevas, preferiblemente con
la fuente primero, como `bce.search_indicators` o `sri.search_ruc`. No se debe
renombrar toda la API actual en un solo cambio.

Cada tool nueva debería tener un `title` legible en español y una descripción
que indique qué hace, cuándo usarla, qué no devuelve y cuáles son sus límites.

## Esquemas de entrada

Las firmas deben ayudar al cliente a construir una llamada válida, no aceptar
cualquier texto y corregirlo solo después. La migración debería usar:

- `Literal["nacional", "cuenca", "latacunga", "iadb"]` para fuentes cerradas
  (el conjunto real ya creció a 4 valores — ver Historial de conteos).
- `Literal["text", "json"]` mientras exista compatibilidad con `format`.
- `Annotated` y `Field` para describir y limitar `limit`, `rows`, `page_size` y
  otros parámetros numéricos.
- Modelos tipados para argumentos complejos, como filtros de consultas.

Los límites deben seguir existiendo en el código aunque estén declarados en el
schema. El schema ayuda a la IA; la validación del servidor sigue siendo la
protección real.

## Resultados y contrato de respuesta

El contrato actual de `metadatos` es un buen punto de partida, pero está dentro
de respuestas textuales. La migración recomendada es:

1. Definir modelos de resultado con `TypedDict`, dataclasses o Pydantic.
2. Devolver objetos JSON estructurados con `outputSchema` y
   `structuredContent`.
3. Mantener una representación textual compatible durante la transición.
4. Retirar gradualmente `format` cuando los clientes ya consuman el resultado
   estructurado.

Cada resultado debería conservar, cuando corresponda, fuente, URL, fecha de
consulta, fecha de corte, frescura, cobertura, límites y nombre del esquema.

## Anotaciones MCP y errores

Las tools de consulta pública deberían indicar que son de solo lectura y, en
general, trabajan sobre catálogos cerrados. Las tools que guardan snapshots o
colas de revisión deben tener un tratamiento distinto y permanecer en el perfil
de mantenimiento. Las anotaciones son pistas para el cliente, no sustituyen la
seguridad.

Los errores de API, validación y límites deben llegar como errores de ejecución
MCP (`isError: true`), no como una cadena que parece una respuesta exitosa. Así
el modelo puede distinguir "no hubo resultados" de "la consulta falló" y
corregir sus argumentos.

## Plan de ejecución

Cuatro fases, cada una entregable de forma independiente — no es necesario
completar una fase entera antes de que el proyecto obtenga valor de ella.
Cada fase lista qué cambia, en qué archivos, y cómo se verifica.

### Fase 0 — Reducciones de bajo riesgo (1-2 sesiones)

La única fase que borra o fusiona tools. Todo lo demás es aditivo (schemas,
anotaciones) y no rompe nada existente.

1. Retirar `list_capabilities` del perfil público (regla 1). Mantener como
   alias una versión, luego retirar. Archivos: `tools/list_capabilities.py`,
   `tools/__init__.py`.
2. Fusionar `list_recent_datasets` en `search_datasets(sort="recent")`
   (regla 2). Archivos: `helpers/ckan_client.py`, `tools/search_datasets.py`;
   retirar `tools/list_recent_datasets.py` tras el período de alias.
3. (Opcional, decisión de Daniel) Fusionar el trío de aviación y el par
   ARCOTEL (regla 5) si el ahorro de 3 tools justifica perder los nombres
   específicos.
4. Verificación: `uv run pytest`, conteo de tools antes/después en
   `docs/MCP_ARCHITECTURE.md` (nueva fila en Historial de conteos), smoke
   test manual de los tools fusionados.

Resultado esperado: 115 → 113 (o 110 si se ejecuta el paso 3 opcional).

### Fase 1 — Perfiles público / mantenimiento (1 sesión)

1. Mover `audit_bce_catalog` y `compare_bce_sources` a un segundo
   `register_tools`-equivalente que solo se registra en una instancia
   `FastMCP` de mantenimiento (regla 3). No se toca `helpers/` ni la lógica.
2. Decidir el mecanismo de exposición: segundo proceso (`mcp-maintenance`)
   vs. flag de arranque en el mismo proceso — impacto en `main.py` y
   `docker-compose.yml`/`Dockerfile` si se elige proceso separado.
3. Verificación: `tools/list` del perfil público ya no incluye las 2 tools
   de mantenimiento; siguen funcionando vía el perfil de mantenimiento.

### Fase 2 — Metadatos de tool (2-3 sesiones, incremental por fuente)

No requiere tocar lógica de negocio — solo las firmas y docstrings de
`tools/*.py`. Puede hacerse fuente por fuente sin bloquear el resto.

1. Agregar `title` legible en español a cada tool.
2. Migrar `source: str` a `Literal["nacional", "cuenca", "latacunga", "iadb"]`
   (y equivalentes para cualquier otro parámetro con un conjunto cerrado de
   valores) sin cambiar el comportamiento en runtime.
3. Agregar anotaciones MCP (solo-lectura vs. escribe artefactos) — todas
   las tools públicas son solo-lectura salvo que se documente lo contrario.
4. Verificación: `tools/list` expone `title` y anotaciones para el 100% de
   las tools públicas; test de regresión que falla si una tool nueva no
   declara `title`.

### Fase 3 — Contrato de respuesta estructurado (varias sesiones, la más grande)

La migración de mayor alcance — tocar cada `tools/*.py` para devolver
`structuredContent` además de texto. Diseñada para hacerse en paralelo con
trabajo de fuentes nuevas, no como un bloque dedicado.

1. Definir el modelo base de resultado (fuente, URL, fecha de consulta,
   fecha de corte, límites) como un `TypedDict`/dataclass compartido en
   `helpers/format_out.py` o un módulo nuevo.
2. Migrar una fuente piloto completa (sugerido: BCE, ya tiene el contrato
   `metadatos` más maduro) a `outputSchema` + `structuredContent`,
   manteniendo `format="text"` como salida legada.
3. Reemplazar errores de aplicación devueltos como string por errores de
   ejecución MCP (`isError: true`) — empezar por la misma fuente piloto.
4. Repetir por fuente, sin fecha límite fija — cada fuente migrada es una
   mejora entregada, no depende de que las demás también migren.
5. Retirar `format` (o dejarlo como alias de solo-texto) solo después de
   que los clientes reales del proyecto confirmen que consumen el resultado
   estructurado.

Antes de retirar más tools en cualquier fase conviene medir llamadas reales,
errores de selección y herramientas que nunca se usan. No se debe reducir la
superficie únicamente para alcanzar un número arbitrario.

## Fuentes oficiales consultadas

- [MCP Tools, especificación 2025-11-25](https://modelcontextprotocol.io/specification/2025-11-25/server/tools)
- [MCP Schema: instrucciones del servidor](https://modelcontextprotocol.io/specification/2025-11-25/schema)
- [MCP Server overview: tools, resources y prompts](https://modelcontextprotocol.io/specification/2025-11-25/server/index)
- [Documentación del SDK oficial de Python sobre tools y schemas](https://github.com/modelcontextprotocol/python-sdk/blob/main/docs/servers/tools.md)
- [Server instructions, blog oficial de MCP](https://blog.modelcontextprotocol.io/posts/2025-11-03-using-server-instructions/)
