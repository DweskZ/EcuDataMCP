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
publica o no se pueden inferir sin inventar datos. El esquema MCP de cada
herramienta sigue declarando su resultado como texto porque `format="text"`
y `format="json"` se mantienen por compatibilidad; `metadatos.esquema`
describe la forma semántica del JSON que recibe un agente.
