"""Published output schemas for the MCP tools, one per family of result.

Every tool returns a ``CallToolResult`` built by ``render_structured``. The
SDK publishes an ``outputSchema`` and validates ``structuredContent`` against
it when the return annotation is ``Annotated[CallToolResult, Model]``
(mcp/server/mcpserver/utilities/func_metadata.py), so each tool is annotated
with the model of its family below. Six families cover every tool
(docs/MCP_ARCHITECTURE.md § Fase 5).

The schemas are deliberately loose about the body: each family names the
keys its tools share, all optional, and allows extra keys, because the list
key differs per source (``companias``, ``indicadores``, ``archivos``...) and
a strict schema would turn a harmless new field into a failed call. The one
part every response is guaranteed to carry is ``metadatos``
(helpers/response_contract.ensure_response_metadata).
"""

from __future__ import annotations

from typing import Annotated, Any, Required

from pydantic import ConfigDict, Field, with_config
from typing_extensions import TypedDict


@with_config(ConfigDict(extra="allow"))
class Esquema(TypedDict, total=False):
    nombre: Annotated[str | None, Field(description="Nombre estable del esquema, p. ej. ecudatamcp.search_ranking")]
    campos_principales: Annotated[list[str], Field(description="Claves de primer nivel de la respuesta")]


@with_config(ConfigDict(extra="allow"))
class Metadatos(TypedDict, total=False):
    contrato: Annotated[str, Field(description="Versión del contrato, hoy ecudatamcp.response.v1")]
    fuente: Annotated[str | None, Field(description="Institución o sistema de origen")]
    url_fuente: Annotated[str | None, Field(description="URL oficial consultada")]
    consultado_en: Annotated[str | None, Field(description="Momento de la consulta, ISO 8601 UTC")]
    fecha_publicacion: Annotated[str | None, Field(description="Fecha de publicación del dato, si la fuente la da")]
    fecha_corte: Annotated[str | None, Field(description="Fecha de corte del dato, si la fuente la da")]
    frescura: Annotated[str | None, Field(description="Cadencia de actualización, p. ej. daily_bulk o boletin_mensual")]
    esquema: Esquema
    truncado: Annotated[dict[str, Any], Field(description="Presente si se omitieron filas por tamaño")]
    paginacion: Annotated[dict[str, Any], Field(description="Dónde está la página siguiente, si la respuesta pagina")]
    respuesta_obsoleta: Annotated[dict[str, Any], Field(description="Presente si la fuente falló y se usó la última copia buena")]


@with_config(ConfigDict(extra="allow"))
class _Base(TypedDict, total=False):
    metadatos: Required[Metadatos]
    source: Annotated[Any, Field(description="Nombre legible de la fuente")]
    url_fuente: Annotated[Any, Field(description="URL oficial de origen")]


@with_config(ConfigDict(extra="allow"))
class ResultadoBusqueda(_Base, total=False):
    """Búsqueda paginada: una lista de coincidencias más total y offset."""

    total: Annotated[Any, Field(description="Coincidencias totales antes de paginar")]
    offset: Annotated[Any, Field(description="Desplazamiento de la página devuelta")]


@with_config(ConfigDict(extra="allow"))
class ResultadoListado(_Base, total=False):
    """Listado de opciones de un catálogo cerrado (secciones, series, capas)."""

    total: Annotated[Any, Field(description="Elementos en el catálogo")]
    fuente: Annotated[Any, Field(description="Fuente del catálogo listado")]


@with_config(ConfigDict(extra="allow"))
class ResultadoArchivos(_Base, total=False):
    """Archivos descargables: nombre, URL y formato, sin el contenido."""

    total: Annotated[Any, Field(description="Archivos encontrados")]
    archivos: Annotated[Any, Field(description="Archivos con su URL directa")]


@with_config(ConfigDict(extra="allow"))
class ResultadoSerie(_Base, total=False):
    """Serie temporal o indicador: observaciones por período."""


@with_config(ConfigDict(extra="allow"))
class ResultadoTabla(_Base, total=False):
    """Filas tabulares: preview, consulta o tabla de un reporte."""

    columnas: Annotated[Any, Field(description="Columnas de la tabla")]
    filas: Annotated[Any, Field(description="Filas devueltas")]


@with_config(ConfigDict(extra="allow"))
class ResultadoFicha(_Base, total=False):
    """Ficha o documento de una entidad: un registro, un informe, un PDF."""
