import re

from mcp.server.fastmcp import FastMCP

from helpers import gobec_client
from helpers.format_out import render_output
from helpers.logging import log_tool

_TIME_TAG_RE = re.compile(r"<[^>]+>")


def _clean_modificado(value: str) -> str:
    """gob.ec wraps the last-updated timestamp in a <time datetime=...> tag."""
    return _TIME_TAG_RE.sub("", value or "").strip()


def _periodo(anio, mes) -> str:
    """"YYYY-MM", zero-padding mes only when it actually parsed as an int --
    an unexpected non-numeric value from the API should show as-is rather
    than crash the whole response on a format-spec error."""
    if isinstance(mes, int):
        return f"{anio}-{mes:02d}"
    return f"{anio}-{mes}"


def register_get_tramite_estadisticas_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def get_tramite_estadisticas(tramite_id: str, format: str = "text") -> str:
        """
        Monthly usage/complaint stats (atenciones/quejas) for one trámite.

        A separate transparency series from get_tramite_info: how many people
        were actually attended each month, and how many complaints were filed,
        since gob.ec started publishing this (mid-2021). Get tramite_id from
        search_tramites. There is no bulk endpoint -- this fetches one
        trámite's series at a time (currently a few dozen months, oldest and
        newest bounds returned as-is, no pagination needed).

        Args:
            tramite_id: The procedure ID (e.g. "11752")
            format: text | json
        """
        try:
            rows = await gobec_client.get_tramite_estadisticas(tramite_id)
        except Exception as e:
            return render_output(
                {"error": str(e)},
                format,
                text_builder=lambda d: f"Error al obtener estadísticas del trámite: {d['error']}",
            )

        if not rows:
            return render_output(
                {"tramite_id": tramite_id, "meses": []},
                format,
                text_builder=lambda d: (
                    f"No se encontraron estadísticas de transparencia para el "
                    f"trámite '{d['tramite_id']}'."
                ),
            )

        meses = [
            {
                "anio": int(r["ano"]) if str(r.get("ano", "")).isdigit() else r.get("ano"),
                "mes": int(r["mes"]) if str(r.get("mes", "")).isdigit() else r.get("mes"),
                "atenciones": int(r["atenciones"])
                if str(r.get("atenciones", "")).isdigit()
                else r.get("atenciones"),
                "quejas": int(r["quejas"]) if str(r.get("quejas", "")).isdigit() else r.get("quejas"),
                "modificado": _clean_modificado(r.get("modificado", "")),
            }
            for r in rows
        ]
        # gob.ec returns newest-first; a monthly series reads more naturally
        # oldest-first, and this also makes the "most recent" row obvious
        # without depending on the API never changing its order. Sort key
        # coerces defensively so one malformed row (non-numeric anio/mes)
        # can't crash the whole response by comparing str to int.
        def _sort_key(m: dict) -> tuple[int, int]:
            anio = m["anio"] if isinstance(m["anio"], int) else 0
            mes = m["mes"] if isinstance(m["mes"], int) else 0
            return (anio, mes)

        meses.sort(key=_sort_key)

        payload = {"tramite_id": tramite_id, "meses": meses}

        def to_text(data: dict) -> str:
            rows = data["meses"]
            primero = _periodo(rows[0]["anio"], rows[0]["mes"])
            ultimo = _periodo(rows[-1]["anio"], rows[-1]["mes"])
            parts = [
                (
                    f"Estadísticas de transparencia del trámite {data['tramite_id']} "
                    f"({len(rows)} meses, {primero} a {ultimo}):"
                ),
                "",
            ]
            for m in rows:
                parts.append(
                    f"{_periodo(m['anio'], m['mes'])}: {m['atenciones']} atenciones, "
                    f"{m['quejas']} quejas"
                )
            return "\n".join(parts)

        return render_output(payload, format, text_builder=to_text)
