import asyncio
from datetime import UTC, datetime
from unicodedata import category, normalize

from mcp.server.fastmcp import FastMCP

from helpers import ckan_client, gobec_client, sercop_client, sgr_client
from helpers.format_out import render_output
from helpers.gobec_client import _clean_html
from helpers.logging import log_tool


def _strip_accents(text: str) -> str:
    nfkd = normalize("NFKD", text or "")
    return "".join(c for c in nfkd if category(c) != "Mn")


def register_search_ecuador_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def search_ecuador(query: str, limit: int = 5, format: str = "text") -> str:
        """
        Unified search across Ecuador open data, trámites, regulations, contracts
        and risk events.

        Use this as the first step for broad questions. Then drill down with
        get_dataset_info, query_resource_data, get_tramite_info, get_regulacion_info,
        get_contrato_info or search_eventos_riesgo.

        Args:
            query: Search terms in Spanish (e.g. "salud", "RUC", "medicinas")
            limit: Max results per section (default 5, max 10)
            format: text | json
        """
        query = (query or "").strip()
        if not query:
            return render_output(
                {"error": "query_vacio"},
                format,
                text_builder=lambda _: (
                    "Error: proporciona un query (ej. 'salud', 'pasaporte', 'INEC')."
                ),
            )

        limit = min(max(limit, 1), 10)

        async def _datasets() -> dict | Exception:
            try:
                return await ckan_client.search_datasets(query=query, rows=limit)
            except Exception as e:
                return e

        async def _orgs() -> list | Exception:
            try:
                return await ckan_client.list_organizations(query=query, limit=limit)
            except Exception as e:
                return e

        async def _tramites() -> list | Exception:
            try:
                words = [_strip_accents(w.lower()) for w in query.split() if len(w) >= 2]
                batch = await gobec_client.search_tramites(page=0)
                if not words:
                    return batch[:limit]

                def matches(t: dict) -> bool:
                    blob = _strip_accents(
                        f"{t.get('nombre', '')} {t.get('codigo', '')} "
                        f"{t.get('descripcion', '')}".lower()
                    )
                    return all(w in blob for w in words)

                return [t for t in batch if matches(t)][:limit]
            except Exception as e:
                return e

        async def _regulaciones() -> list | Exception:
            try:
                return await gobec_client.find_regulaciones(query, max_pages=2)
            except Exception as e:
                return e

        async def _contratos() -> dict | Exception:
            if len(query) < 3:
                return ValueError("query corto para SERCOP")
            try:
                return await sercop_client.search_contracts(
                    search=query,
                    year=datetime.now(UTC).year,
                    page=1,
                    fallback_years=2,
                )
            except Exception as e:
                return e

        async def _riesgos() -> dict | Exception:
            try:
                return await sgr_client.list_risk_events(query=query, limit=limit)
            except Exception as e:
                return e

        datasets_r, orgs_r, tramites_r, regs_r, contratos_r, riesgos_r = await asyncio.gather(
            _datasets(),
            _orgs(),
            _tramites(),
            _regulaciones(),
            _contratos(),
            _riesgos(),
        )

        payload = {
            "query": query,
            "datasets": datasets_r
            if not isinstance(datasets_r, Exception)
            else {"error": str(datasets_r)},
            "organizations": orgs_r
            if not isinstance(orgs_r, Exception)
            else {"error": str(orgs_r)},
            "tramites": tramites_r
            if not isinstance(tramites_r, Exception)
            else {"error": str(tramites_r)},
            "regulaciones": regs_r
            if not isinstance(regs_r, Exception)
            else {"error": str(regs_r)},
            "contratos": contratos_r
            if not isinstance(contratos_r, Exception)
            else {"error": str(contratos_r)},
            "riesgos": riesgos_r
            if not isinstance(riesgos_r, Exception)
            else {"error": str(riesgos_r)},
        }

        def to_text(_: dict) -> str:
            parts = [f"Búsqueda unificada en Ecuador para: '{query}'", ""]

            parts.append("=== Datasets (datos abiertos) ===")
            if isinstance(datasets_r, Exception):
                parts.append(f"Error: {datasets_r}")
            else:
                results = datasets_r.get("results") or []
                count = datasets_r.get("count", len(results))
                if not results:
                    parts.append("Sin resultados.")
                else:
                    parts.append(f"Encontrados: {count} (mostrando {len(results)})")
                    for i, ds in enumerate(results, 1):
                        title = ds.get("title") or ds.get("name", "Sin título")
                        name = ds.get("name") or ds.get("id", "")
                        org = (ds.get("organization") or {}).get("title", "")
                        parts.append(f"{i}. {title}")
                        parts.append(f"   ID: {name}")
                        if org:
                            parts.append(f"   Org: {org}")
            parts.append("")

            parts.append("=== Instituciones publicadoras (CKAN) ===")
            if isinstance(orgs_r, Exception):
                parts.append(f"Error: {orgs_r}")
            elif not orgs_r:
                parts.append("Sin resultados.")
            else:
                for i, org in enumerate(orgs_r[:limit], 1):
                    title = org.get("title") or org.get("display_name") or org.get("name")
                    name = org.get("name", "")
                    parts.append(f"{i}. {title} (ID: {name})")
            parts.append("")

            parts.append("=== Trámites (gob.ec) ===")
            if isinstance(tramites_r, Exception):
                parts.append(f"Error: {tramites_r}")
            elif not tramites_r:
                parts.append(
                    "Sin resultados en la primera página. "
                    "Prueba search_tramites con institution_id."
                )
            else:
                for i, t in enumerate(tramites_r, 1):
                    parts.append(f"{i}. {t.get('nombre', 'Sin nombre')}")
                    parts.append(f"   ID: {t.get('tramite_id', '?')}")
            parts.append("")

            parts.append("=== Regulaciones (gob.ec) ===")
            if isinstance(regs_r, Exception):
                parts.append(f"Error: {regs_r}")
            elif not regs_r:
                parts.append("Sin resultados. Prueba search_regulaciones.")
            else:
                for i, reg in enumerate(regs_r[:limit], 1):
                    title = _clean_html(reg.get("regulacion", "Sin título")).strip('"')
                    parts.append(f"{i}. {title}")
                    parts.append(f"   ID: {reg.get('regulacion_id', '?')}")
            parts.append("")

            parts.append("=== Contratos públicos (SERCOP/OCDS) ===")
            if isinstance(contratos_r, Exception):
                parts.append(
                    f"No disponible ahora: {contratos_r}. "
                    "Usa search_contratos (la API a veces rate-limita)."
                )
            else:
                data = contratos_r.get("data") or []
                total = contratos_r.get("total", len(data))
                if not data:
                    parts.append(
                        "Sin resultados este año. Prueba search_contratos con otro year."
                    )
                else:
                    parts.append(
                        f"Encontrados: {total} (mostrando {min(len(data), limit)})"
                    )
                    for i, item in enumerate(data[:limit], 1):
                        parts.append(f"{i}. {item.get('title') or item.get('ocid')}")
                        if item.get("ocid"):
                            parts.append(f"   OCID: {item['ocid']}")
                        if item.get("buyerName"):
                            parts.append(f"   Comprador: {item['buyerName']}")
            parts.append("")

            parts.append("=== Eventos de riesgo (SGR COE) ===")
            if isinstance(riesgos_r, Exception):
                parts.append(f"No disponible ahora: {riesgos_r}")
            else:
                events = riesgos_r.get("events") or []
                total = riesgos_r.get("total", len(events))
                if not events:
                    parts.append("Sin coincidencias. Prueba search_eventos_riesgo.")
                else:
                    parts.append(f"Coincidencias: {total} (mostrando {len(events)})")
                    for i, ev in enumerate(events, 1):
                        parts.append(
                            f"{i}. {ev.get('Evento', 'Evento')} — "
                            f"{ev.get('Provincia', '?')}/{ev.get('Canton', '?')} "
                            f"({ev.get('EstadoDelEvento', '?')})"
                        )
            parts.append("")
            parts.append(
                "Siguiente paso: get_dataset_info / query_resource_data / "
                "get_tramite_info / get_regulacion_info / get_contrato_info / "
                "search_eventos_riesgo."
            )
            return "\n".join(parts)

        return render_output(payload, format, text_builder=to_text)
