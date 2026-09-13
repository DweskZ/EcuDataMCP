# Contrato de respuesta para agentes

Las herramientas BCEData e IEM conservan sus campos históricos para mantener
compatibilidad. Cuando se solicita `format="json"`, además incluyen
`metadatos`, un bloque estable para agentes:

```json
{
  "metadatos": {
    "contrato": "ecudatamcp.response.v1",
    "fuente": "Nombre de la fuente oficial",
    "url_fuente": "https://...",
    "consultado_en": "2026-08-31T00:00:00+00:00",
    "fecha_publicacion": "2026-07",
    "fecha_corte": null,
    "frescura": "boletin_mensual",
    "esquema": {
      "nombre": "bce_iem_catalogo_v1",
      "campos_principales": ["boletin", "total", "tablas", "historico"]
    }
  }
}
```

`fecha_publicacion` y `fecha_corte` quedan en `null` cuando la fuente no las
publica o no se pueden inferir sin inventar datos. `format="text"` y
`format="json"` se mantienen por compatibilidad; `metadatos.esquema`
describe la forma semántica del JSON que recibe un agente.

## `structuredContent` (Fase 3 de docs/MCP_ARCHITECTURE.md)

Las 113 tools del servidor devuelven ahora, además del texto de siempre
(`format="text"`/`format="json"`, sin cambios), el mismo payload como
`structuredContent` MCP nativo — un cliente que lee salida estructurada no
necesita volver a parsear el bloque de texto. El tipo de retorno declarado
es `dict[str, Any]` (`helpers/format_out.py::render_structured`), así que
el `outputSchema` publicado es genérico (`{"type": "object",
"additionalProperties": true}`) en vez de un esquema Pydantic propio por
tool — suficiente para que un cliente MCP sepa que hay contenido
estructurado, no una validación fuerte de forma.

Un error real (excepción de red, de la API fuente, validación de
argumentos, límites de tamaño, etc.) ya no se devuelve como una cadena con
forma de éxito: se relanza como `mcp.server.mcpserver.exceptions.ToolError`,
que el servidor convierte en un resultado MCP con `isError: true`. Un
resultado vacío legítimo (por ejemplo, "no hay datos para ese id_grupo",
"no se encontraron datasets para 'x'") sigue siendo una respuesta exitosa
normal — la distinción es entre "la consulta falló" y "no hubo
resultados", no entre "hubo datos" y "no hubo datos". Ver
`docs/MCP_ARCHITECTURE.md` § Fase 3 para el detalle completo de qué se
convirtió a `ToolError` en cada tool y qué se dejó como resultado legítimo.

El contrato `metadatos` en sí (fuente, url_fuente, fechas, frescura,
esquema) sigue presente solo en las tools que ya lo tenían antes de esta
fase — no se agregó a las demás. Una tool sin `metadatos` todavía tiene
`structuredContent` (el payload que ya construía), solo que sin ese
envoltorio de procedencia; enriquecerlo caso por caso queda como trabajo
futuro opcional.

Siete tools (`list_ineval_familias`, `list_sut_indicadores`,
`list_bce_indicadores_diarios`, `list_contraloria_informes`,
`list_seps_secciones`, `list_sipa_modulos`,
`list_superbancos_secciones`) tenían un payload `list[dict]` en vez de
`dict` — `structuredContent` debe ser un objeto JSON, no un arreglo, así
que se envolvieron en `{"total": N, "<nombre>": [...]}`. Es un cambio de
forma en la salida `format="json"` de esas 7 tools específicamente (el
texto de `format="text"` no cambió).
