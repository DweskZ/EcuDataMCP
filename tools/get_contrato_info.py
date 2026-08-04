from mcp.server.fastmcp import FastMCP

from helpers import sercop_client
from helpers.env_config import get_base_url
from helpers.format_out import render_output
from helpers.logging import log_tool


def _money(amount: object, currency: str = "") -> str:
    try:
        val = float(amount)  # type: ignore[arg-type]
        text = f"{val:,.2f}"
    except (TypeError, ValueError):
        text = str(amount)
    return f"{text} {currency}".strip()


def register_get_contrato_info_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def get_contrato_info(ocid: str, format: str = "text") -> str:
        """
        Get the full OCDS record for a public procurement procedure (SERCOP).

        Returns buyer, tender, awards, contracts and useful links when available.
        Get the ocid from search_contratos.

        Args:
            ocid: Open Contracting ID, e.g. "ocds-5wno2w-001-LICO-GPLR-2020-2805"
            format: text | json
        """
        ocid = (ocid or "").strip()
        if not ocid:
            return render_output(
                {"error": "ocid_requerido"},
                format,
                text_builder=lambda _: "Error: ocid es obligatorio.",
            )

        try:
            package = await sercop_client.get_contract_record(ocid)
        except Exception as e:
            return render_output(
                {"error": str(e), "ocid": ocid},
                format,
                text_builder=lambda d: (
                    f"Error al obtener contrato '{d['ocid']}': {d['error']}. "
                    "Si es 429, reintenta en unos segundos."
                ),
            )

        records = package.get("records") or []
        if not records:
            return render_output(
                {"error": "not_found", "ocid": ocid},
                format,
                text_builder=lambda d: (
                    f"No se encontró el proceso con OCID '{d['ocid']}'."
                ),
            )

        record = records[0]
        releases = record.get("releases") or []
        release = releases[-1] if releases else {}
        site = get_base_url("sercop_site").rstrip("/")

        buyer = release.get("buyer") or {}
        tender = release.get("tender") or {}
        awards = release.get("awards") or []
        contracts = release.get("contracts") or []
        tags = release.get("tag") or []

        payload = {
            "ocid": record.get("ocid", ocid),
            "portal": f"{site}/procedimientos",
            "license": package.get("license"),
            "buyer": {"name": buyer.get("name"), "id": buyer.get("id")}
            if buyer
            else None,
            "tender": {
                "id": tender.get("id"),
                "title": tender.get("title"),
                "status": tender.get("status"),
                "method": tender.get("procurementMethodDetails")
                or tender.get("procurementMethod"),
                "value": tender.get("value"),
                "description": (tender.get("description") or "").strip() or None,
            }
            if tender
            else None,
            "awards": [
                {
                    "id": a.get("id"),
                    "title": a.get("title"),
                    "status": a.get("status"),
                    "value": a.get("value"),
                    "suppliers": [
                        {"name": s.get("name"), "id": s.get("id")}
                        for s in (a.get("suppliers") or [])[:5]
                    ],
                }
                for a in awards[:10]
            ],
            "contracts": [
                {
                    "id": c.get("id"),
                    "title": c.get("title"),
                    "status": c.get("status"),
                    "value": c.get("value"),
                }
                for c in contracts[:10]
            ],
            "tags": tags,
            "date": release.get("date"),
        }

        def to_text(data: dict) -> str:
            parts = [
                "Proceso de contratación (OCDS)",
                f"OCID: {data['ocid']}",
                f"Portal: {data['portal']}",
            ]
            if data.get("license"):
                parts.append(f"Licencia: {data['license']}")
            buyer_d = data.get("buyer") or {}
            if buyer_d:
                parts.append("")
                parts.append(f"Comprador: {buyer_d.get('name', '?')}")
                if buyer_d.get("id"):
                    parts.append(f"Buyer ID: {buyer_d['id']}")
            tender_d = data.get("tender") or {}
            if tender_d:
                parts.append("")
                parts.append(
                    f"Licitación: {tender_d.get('title') or tender_d.get('id', '')}"
                )
                if tender_d.get("status"):
                    parts.append(f"Estado: {tender_d['status']}")
                if tender_d.get("method"):
                    parts.append(f"Método: {tender_d['method']}")
                value = tender_d.get("value") or {}
                if value.get("amount") is not None:
                    parts.append(
                        f"Valor estimado: {_money(value.get('amount'), value.get('currency', 'USD'))}"
                    )
                if tender_d.get("description"):
                    parts.append(f"Descripción: {str(tender_d['description'])[:600]}")
            if data.get("awards"):
                parts.append("")
                parts.append(f"Adjudicaciones ({len(data['awards'])}):")
                for i, award in enumerate(data["awards"][:5], 1):
                    parts.append(
                        f"{i}. {award.get('title') or award.get('id', 'Adjudicación')}"
                    )
                    if award.get("status"):
                        parts.append(f"   Estado: {award['status']}")
                    aval = award.get("value") or {}
                    if aval.get("amount") is not None:
                        parts.append(
                            f"   Monto: {_money(aval.get('amount'), aval.get('currency', 'USD'))}"
                        )
                    for s in (award.get("suppliers") or [])[:3]:
                        parts.append(f"   Proveedor: {s.get('name', '?')}")
            if data.get("contracts"):
                parts.append("")
                parts.append(f"Contratos ({len(data['contracts'])}):")
                for i, contract in enumerate(data["contracts"][:5], 1):
                    parts.append(
                        f"{i}. {contract.get('title') or contract.get('id', 'Contrato')}"
                    )
                    if contract.get("status"):
                        parts.append(f"   Estado: {contract['status']}")
                    cval = contract.get("value") or {}
                    if cval.get("amount") is not None:
                        parts.append(
                            f"   Monto: {_money(cval.get('amount'), cval.get('currency', 'USD'))}"
                        )
            if data.get("tags"):
                parts.append("")
                parts.append(f"Etapas OCDS: {', '.join(data['tags'])}")
            if data.get("date"):
                parts.append(f"Fecha release: {data['date']}")
            return "\n".join(parts)

        return render_output(payload, format, text_builder=to_text)
