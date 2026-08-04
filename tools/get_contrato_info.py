from mcp.server.fastmcp import FastMCP

from helpers import sercop_client
from helpers.env_config import get_base_url
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
    async def get_contrato_info(ocid: str) -> str:
        """
        Get the full OCDS record for a public procurement procedure (SERCOP).

        Returns buyer, tender, awards, contracts and useful links when available.
        Get the ocid from search_contratos.

        Args:
            ocid: Open Contracting ID, e.g. "ocds-5wno2w-001-LICO-GPLR-2020-2805"
        """
        ocid = (ocid or "").strip()
        if not ocid:
            return "Error: ocid es obligatorio."

        try:
            package = await sercop_client.get_contract_record(ocid)
        except Exception as e:
            return (
                f"Error al obtener contrato '{ocid}': {e}. "
                "Si es 429, reintenta en unos segundos."
            )

        records = package.get("records") or []
        if not records:
            return f"No se encontró el proceso con OCID '{ocid}'."

        record = records[0]
        releases = record.get("releases") or []
        release = releases[-1] if releases else {}

        site = get_base_url("sercop_site").rstrip("/")
        parts = [
            "Proceso de contratación (OCDS)",
            f"OCID: {record.get('ocid', ocid)}",
            f"Portal: {site}/procedimientos",
        ]
        if package.get("license"):
            parts.append(f"Licencia: {package['license']}")

        buyer = release.get("buyer") or {}
        if buyer:
            parts.append("")
            parts.append(f"Comprador: {buyer.get('name', '?')}")
            if buyer.get("id"):
                parts.append(f"Buyer ID: {buyer['id']}")

        tender = release.get("tender") or {}
        if tender:
            parts.append("")
            parts.append(f"Licitación: {tender.get('title') or tender.get('id', '')}")
            if tender.get("status"):
                parts.append(f"Estado: {tender['status']}")
            if tender.get("procurementMethodDetails") or tender.get("procurementMethod"):
                parts.append(
                    f"Método: {tender.get('procurementMethodDetails') or tender.get('procurementMethod')}"
                )
            value = tender.get("value") or {}
            if value.get("amount") is not None:
                parts.append(
                    f"Valor estimado: {_money(value.get('amount'), value.get('currency', 'USD'))}"
                )
            desc = (tender.get("description") or "").strip()
            if desc:
                parts.append(f"Descripción: {desc[:600]}")

        awards = release.get("awards") or []
        if awards:
            parts.append("")
            parts.append(f"Adjudicaciones ({len(awards)}):")
            for i, award in enumerate(awards[:5], 1):
                parts.append(f"{i}. {award.get('title') or award.get('id', 'Adjudicación')}")
                if award.get("status"):
                    parts.append(f"   Estado: {award['status']}")
                aval = award.get("value") or {}
                if aval.get("amount") is not None:
                    parts.append(
                        f"   Monto: {_money(aval.get('amount'), aval.get('currency', 'USD'))}"
                    )
                suppliers = award.get("suppliers") or []
                for s in suppliers[:3]:
                    parts.append(f"   Proveedor: {s.get('name', '?')}")

        contracts = release.get("contracts") or []
        if contracts:
            parts.append("")
            parts.append(f"Contratos ({len(contracts)}):")
            for i, contract in enumerate(contracts[:5], 1):
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

        tags = release.get("tag") or []
        if tags:
            parts.append("")
            parts.append(f"Etapas OCDS: {', '.join(tags)}")

        if release.get("date"):
            parts.append(f"Fecha release: {release['date']}")

        return "\n".join(parts)
