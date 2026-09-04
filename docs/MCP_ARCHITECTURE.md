# Revisión de arquitectura MCP

Revisión realizada el 2026-08-31 para decidir si EcuDataMCP debe simplificar,
armonizar o reducir su número de tools. Este documento es una guía de diseño;
no implica que todos los cambios deban hacerse de una sola vez.

> **Cifras desactualizadas (nota 2026-09-04):** este documento cuenta 74
> tools registradas al 2026-08-31; hoy son 103. El diagnóstico y el diseño
> propuesto (perfil público vs. perfil de mantenimiento) probablemente
> siguen siendo válidos, pero las cifras concretas de esta página (74, "~69
> visibles") no se recalcularon — tratarlas como orientativas, no exactas,
> hasta una revisión completa.

## Conclusión corta

El servidor tiene 74 tools registradas. Ese número no es, por sí solo, un
problema de MCP: `tools/list` admite paginación y la especificación no fija un
máximo pequeño. El problema actual es la forma de describir y devolver esas
tools.

La recomendación es mantener las capacidades específicas de cada fuente, pero
reducir la superficie pública solo donde existe una duplicación clara. El
objetivo inicial razonable es aproximadamente 69 tools visibles para usuarios,
con 2 o 3 tools de mantenimiento en un perfil separado.

## Evidencia del repositorio

- Hay 74 módulos en `tools/` y 74 decoradores `@mcp.tool()` registrados.
- Las 74 tools aceptan `format: str`, normalmente con los valores `text` o
  `json`.
- Las 74 declaran retorno `str`. Con el SDK MCP 1.29.0 usado por el entorno,
  `tools/list` las presenta con un output schema equivalente a un resultado
  textual (`result: string`), aunque muchas internamente construyen objetos
  JSON dentro de una cadena.
- Ninguna tool define actualmente `title` ni anotaciones MCP.
- No hay `Annotated`, `Field`, `Literal`, `BaseModel` o `TypedDict` en las
  firmas públicas de las tools.
- `list_capabilities` repite información del recurso `ecuador://fuentes` y
  además tiene la versión fija `0.8.2`, mientras el servidor actual es `0.8.5`.
- `search_datasets` y `list_recent_datasets` consultan el mismo catálogo y
  entidad; la segunda cambia principalmente el criterio de orden.

Esto indica que el mayor problema no es la cantidad bruta, sino que el cliente
debe escoger entre muchos nombres y luego interpretar respuestas textuales.

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
particular para SIPA, Superbancos, Contraloría, SRI Saiku y BCEData/IEM.

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
la fuente primero, como `bce.search_indicators` o `sri.query_saiku`. No se debe
renombrar toda la API actual en un solo cambio.

Cada tool nueva debería tener un `title` legible en español y una descripción
que indique qué hace, cuándo usarla, qué no devuelve y cuáles son sus límites.

## Esquemas de entrada

Las firmas deben ayudar al cliente a construir una llamada válida, no aceptar
cualquier texto y corregirlo solo después. La migración debería usar:

- `Literal["nacional", "cuenca"]` para fuentes cerradas.
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
el modelo puede distinguir “no hubo resultados” de “la consulta falló” y
corregir sus argumentos.

## Orden de implementación

1. **Primero:** títulos, descripciones, límites de entrada, anotaciones y
   pruebas de `tools/list`.
2. **Después:** quitar `list_capabilities` del perfil público e integrar
   `list_recent_datasets` en `search_datasets` con compatibilidad temporal.
3. **Luego:** crear el perfil público y el perfil de mantenimiento en el mismo
   repositorio.
4. **Finalmente:** migrar resultados a modelos estructurados y retirar
   gradualmente `format`.

Antes de retirar más tools conviene medir llamadas reales, errores de selección
y herramientas que nunca se usan. No se debe reducir la superficie únicamente
para alcanzar un número arbitrario.

## Fuentes oficiales consultadas

- [MCP Tools, especificación 2025-11-25](https://modelcontextprotocol.io/specification/2025-11-25/server/tools)
- [MCP Schema: instrucciones del servidor](https://modelcontextprotocol.io/specification/2025-11-25/schema)
- [MCP Server overview: tools, resources y prompts](https://modelcontextprotocol.io/specification/2025-11-25/server/index)
- [Documentación del SDK oficial de Python sobre tools y schemas](https://github.com/modelcontextprotocol/python-sdk/blob/main/docs/servers/tools.md)
- [Server instructions, blog oficial de MCP](https://blog.modelcontextprotocol.io/posts/2025-11-03-using-server-instructions/)
