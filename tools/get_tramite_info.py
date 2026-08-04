from mcp.server.fastmcp import FastMCP

from helpers import gobec_client
from helpers.format_out import render_output
from helpers.gobec_client import _clean_html
from helpers.logging import log_tool


def register_get_tramite_info_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def get_tramite_info(tramite_id: str, format: str = "text") -> str:
        """
        Get detailed information about a specific government procedure (trámite).

        Returns the procedure name, description, requirements, beneficiaries,
        cost, and the institution responsible. Get the tramite_id from search_tramites.

        Args:
            tramite_id: The procedure ID (e.g. "18009")
            format: text | json
        """
        try:
            t = await gobec_client.get_tramite(tramite_id)
        except Exception as e:
            return render_output(
                {"error": str(e)},
                format,
                text_builder=lambda d: f"Error al obtener trámite: {d['error']}",
            )

        if not t:
            return render_output(
                {"error": "not_found", "tramite_id": tramite_id},
                format,
                text_builder=lambda d: (
                    f"No se encontró el trámite con ID '{d['tramite_id']}'."
                ),
            )

        try:
            regs = await gobec_client.get_tramite_regulaciones(tramite_id)
        except Exception:
            regs = []

        payload = {
            "tramite_id": t.get("tramite_id", tramite_id),
            "nombre": t.get("nombre"),
            "codigo": t.get("codigo"),
            "url": t.get("url"),
            "institucion_id": t.get("institucion_id"),
            "descripcion": _clean_html(t.get("descripcion", "")),
            "beneficiarios": _clean_html(t.get("beneficiarios", "")),
            "requisitos_obligatorios": _clean_html(t.get("requisitos_obligatorios", "")),
            "requisitos_opcionales": _clean_html(t.get("requisitos_opcionales", "")),
            "procedimiento": _clean_html(t.get("procedimiento", "")),
            "costo": _clean_html(t.get("costo", "")),
            "tiempo_estimado": _clean_html(t.get("tiempo_estimado", t.get("tiempo", ""))),
            "canales_atencion": _clean_html(t.get("canales_atencion", "")),
            "regulaciones": [
                {
                    "regulacion_id": r.get("regulacion_id"),
                    "regulacion": _clean_html(
                        r.get("regulacion") or r.get("nombre") or ""
                    ).strip('"'),
                    "registro_oficial_numero": r.get("registro_oficial_numero"),
                }
                for r in regs[:8]
            ],
        }

        def to_text(data: dict) -> str:
            parts = [f"Trámite: {data.get('nombre') or 'Desconocido'}", ""]
            parts.append(f"ID: {data.get('tramite_id')}")
            if data.get("codigo"):
                parts.append(f"Código: {data['codigo']}")
            if data.get("url"):
                parts.append(f"URL: {data['url']}")
            if data.get("institucion_id"):
                parts.append(f"Institución ID: {data['institucion_id']}")
            for label, key in (
                ("Descripción", "descripcion"),
                ("Beneficiarios", "beneficiarios"),
                ("Requisitos obligatorios", "requisitos_obligatorios"),
                ("Requisitos opcionales", "requisitos_opcionales"),
                ("Procedimiento", "procedimiento"),
                ("Costo", "costo"),
                ("Tiempo estimado", "tiempo_estimado"),
                ("Canales de atención", "canales_atencion"),
            ):
                val = data.get(key) or ""
                if val:
                    parts.append("")
                    parts.append(f"{label}:\n{val}" if "\n" in val or len(val) > 80 else f"{label}: {val}")
            regs_list = data.get("regulaciones") or []
            if regs_list:
                parts.append("")
                parts.append(f"Regulaciones relacionadas ({len(regs_list)}):")
                for i, reg in enumerate(regs_list, 1):
                    parts.append(
                        f"{i}. {reg.get('regulacion') or 'Regulación'} "
                        f"(ID: {reg.get('regulacion_id', '?')})"
                    )
                    if reg.get("registro_oficial_numero"):
                        parts.append(f"   R.O.: {reg['registro_oficial_numero']}")
                parts.append(
                    "Tip: Usa get_regulacion_info(regulacion_id='...') para el detalle/PDF."
                )
            return "\n".join(parts)

        return render_output(payload, format, text_builder=to_text)
