"""Tests for web/scripts/refresh_answers.py with the tool layer replaced by fakes.

Run from web/: ``uv run --with pytest pytest tests``. Nothing here touches the
network or imports the MCP server.
"""

from __future__ import annotations

import asyncio
import copy
import json
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WEB / "scripts"))

import refresh_answers as ra

NOW = datetime(2026, 11, 8, 23, 40, tzinfo=ra.ECUADOR_TZ)
CTX = ra.Ctx(NOW)


def run(coro):
    return asyncio.run(coro)


# --------------------------------------------------------------------------
# Canned tool results (shapes copied from real structured responses)
# --------------------------------------------------------------------------


def ev(id_, mag, depth, lat, lon, local, loc):
    return {
        "id": id_, "magnitud": mag, "profundidad_km": depth, "latitud": lat,
        "longitud": lon, "tiempo_local": local, "tiempo_utc": local,
        "localizacion": loc, "url": f"https://www.igepn.edu.ec/e/{id_}",
    }  # fmt: skip


SISMOS = {
    "total": 6,
    "url_fuente": "https://www.igepn.edu.ec/portal/eventos/www/events.csv",
    "events": [
        ev("a1", 4.83, 2.4, -1.8484, -81.1302, "2026-11-07T17:17:39-05:00", "a 45.66 km de Salinas, Santa Elena"),
        ev("a2", 3.73, 6.0, -3.385, -79.7426, "2026-11-07T07:27:16-05:00", "a 9.59 km de Pasaje, El Oro"),
        ev("a3", 3.75, 27.7, -3.4359, -81.8108, "2026-11-06T12:36:50-05:00", "a 140.53 km de Talara, Piura"),
        ev("a4", 3.53, 75.8, -3.1473, -79.0356, "2026-11-04T13:54:50-05:00", "a 27.53 km de Cuenca, Azuay"),
        ev("a5", 5.95, 24.6, 3.9312, -75.6696, "2026-11-03T09:13:20-05:00", "a 30.8 km de Chaparral, Tolima"),
        ev("a6", 5.86, 20.0, -9.3344, -78.7974, "2026-11-02T15:28:26-05:00", "a 36.44 km de Chimbote, Ancash"),
    ],
}  # fmt: skip

TRAMITES = {
    "total": 2,
    "results": [
        {"tramite_id": "11762", "nombre": "Emisión de Pasaporte ... para menores de 18 años", "url": "u-minor"},
        {"tramite_id": "11761", "nombre": "Emisión de Pasaporte ... para mayores de 18 años", "url": "https://www.gob.ec/adult"},
    ],
}  # fmt: skip
TRAMITE_INFO = {
    "tramite_id": "11761",
    "url": "https://www.gob.ec/adult",
    "requisitos_obligatorios": (
        "1. Comprobante de pago (original) bajo todas las modalidades:\n- pago en línea:  "
        "mediante agencia virtual de registro civil.\n- banco corresponsal\n- banca interna "
        "(en agencia presencial)\n2. Cédula de Identidad física o digital vigente y legible.\n"
        "4. En renovación, presentar el pasaporte anterior"
    ),
    "procedimiento": (
        "1.Realizar el pago\nNota:\n2. En las agencias que cuentan con puntos de impresión: "
        "Agencias de Matriz Quito, Gobierno Zonal Guayaquil y San Blas Cuenca, se entregará "
        "el documento oficial de viaje el mismo día, en el resto de las agencias, el "
        "pasaporte se entregará de 24 a 72 horas  posterior a la toma de datos."
    ),
}  # fmt: skip


def bce_series(vals: dict[str, float]):
    return {
        "series": [
            {"label": "Remesas de trabajadores", "ruta": "x\\débito\\y", "valores": {"2025-I": 1.0}},
            {"label": "Remesas de trabajadores", "ruta": "x\\crédito\\y", "valores": vals},
        ]
    }


REMESAS_VALS = {
    "2024-I": 1393.7, "2024-II": 1611.1, "2024-III": 1748.5, "2024-IV": 1786.5,
    "2025-I": 1724.35, "2025-II": 2000.47, "2025-III": 1987.66, "2025-IV": 2015.52,
    "2026-I": 1856.72, "2026-II": 2041.26,
}  # fmt: skip

FAVORITA = {
    "companias": [
        {
            "ruc": "1790016919001", "nombre": "CORPORACION FAVORITA C.A.", "situacion_legal": "ACTIVA",
            "fecha_constitucion": "30/11/1957", "tipo": "ANÓNIMA", "ciudad": "QUITO",
            "representante": "PEÑAHERRERA WRIGHT ALFREDO RICARDO", "capital_suscrito": "900.000.000,00",
            "ciiu_nivel_6": "G4711.01", "ultimo_balance": "2025",
        }
    ]
}  # fmt: skip

COMPRAS = {
    "total_en_fuente": 253, "parcial": False, "monto_total": 36177176.02, "procesos_con_monto": 212,
    "compradores": [
        {"comprador": "GOBIERNO AUTONOMO DESCENTRALIZADO MUNICIPAL DEL CANTON MANTA", "monto_total": 10946510.8},
        {"comprador": "HOSPITAL GENERAL MANTA", "monto_total": 17981481.91},
        {"comprador": "OTRA ENTIDAD", "monto_total": 100.0},
    ],
}  # fmt: skip


def cortes_row(fecha, horario, sectores):
    return {"fecha_texto": fecha, "horario": [horario], "sectores": sectores, "motivo": "X"}


CORTES = {
    "total": 5,
    "url": "https://www.eeasa.com.ec/trabajos-programados/",
    "filas": [
        cortes_row("domingo, 08 - noviembre - 2026", "06:00-10:00", "CALLES X DE HUACHI SAN FRANCISCO DEL CANTÓN AMBATO."),
        cortes_row("martes, 10 - noviembre - 2026", "10:00-14:00", "PROVINCIA: PASTAZA, CANTÓN: PASTAZA, PARROQUIA: PUYO, BARRIO LA LIBERTAD, CALLE ARAJUNO"),
        cortes_row("lunes, 09 - noviembre - 2026", "09:00-14:00", "BARRIO CALLATE SAN ANTONIO DEL CANTÓN PILLARO"),
        cortes_row("miércoles, 11 - noviembre - 2026", "09:00-10:00", "PROVINCIA PASTAZA, CANTÓN PASTAZA, PARROQUIA FÁTIMA, EN LA VÍA"),
        cortes_row("domingo, 08 - noviembre - 2026", "03:00-06:00", "SECTORES: TERREMOTO"),
    ],
}  # fmt: skip

ARCHIVOS = {
    "url_fuente": "https://www.censoecuador.gob.ec/resultados-censo/",
    "archivos": [
        {"url": "https://www.censoecuador.gob.ec/wp-content/uploads/2023/12/03_2022_CPV_TIC.xlsx"},
        {"url": "https://www.censoecuador.gob.ec/wp-content/uploads/2023/12/03_2022_CPV_TIC.zip"},
    ],
}  # fmt: skip


class FakeTools:
    """Dispatches by tool name; ``overrides`` replace a result or raise it."""

    def __init__(self, **overrides):
        self.calls: list[tuple[str, dict]] = []
        self.table = {
            "search_tramites": TRAMITES,
            "get_tramite_info": TRAMITE_INFO,
            "search_sismos": SISMOS,
            "search_indicadores_bce": {
                "indicadores": [{"id_grupo": 2, "series_coincidentes": ["Remesas de trabajadores"]}]
            },
            "get_indicador_bce": bce_series(REMESAS_VALS),
            "search_companias": FAVORITA,
            "get_resumen_compras": COMPRAS,
            "search_cortes": {"total": 1, "archivos": [{"archivo": "vigentes"}], "url_fuente": CORTES["url"]},
            "get_cortes_horarios": CORTES,
            "search_archivos": ARCHIVOS,
            "search_anda": {
                "results": [
                    {
                        "idno": "ECU-INEC-CTIMA-CPV-2022-V1.6",
                        "titulo": "VIII Censo de Población y VII de Vivienda 2022",
                        "tipo_acceso": "enlace_externo",
                    }
                ]
            },
            "download_anda_microdata": {
                "tipo_acceso": "enlace_externo",
                "enlaces_externos": [{"url": "https://www.censoecuador.gob.ec/data-censo-ecuador/"}],
            },
        }
        self.table.update(overrides)

    async def __call__(self, name, **args):
        self.calls.append((name, args))
        result = self.table[name]
        if isinstance(result, Exception):
            raise result
        return copy.deepcopy(result)


def load_real():
    return ra.load_all()


# --------------------------------------------------------------------------
# Formatting
# --------------------------------------------------------------------------


def test_number_and_money_formats_per_locale():
    assert ra.fmt_usd_millions(7727.99, 0, "es") == "US$ 7.728 millones"
    assert ra.fmt_usd_millions(7727.99, 0, "en") == "US$ 7,728 million"
    assert ra.fmt_usd_millions(36.17717602, 1, "es") == "US$ 36,2 millones"
    assert ra.fmt_usd_millions(36.17717602, 1, "en") == "US$ 36.2 million"
    assert ra.fmt_usd_millions(1.0, 0, "es") == "US$ 1 millón"
    assert ra.fmt_percent(18.24, 1, "es") == "18,2 %"
    assert ra.fmt_percent(18.24, 1, "en") == "18.2%"
    assert ra.fmt_number(0.25, 1, "es") == "0,3"  # half up, not banker's rounding
    assert ra.fmt_number(2.4, 1, "en") == "2.4"


def test_dates_use_month_names_of_each_language():
    d = date(1957, 11, 30)
    assert ra.fmt_date_long(d, "es") == "30 de noviembre de 1957"
    assert ra.fmt_date_long(d, "en") == "November 30, 1957"
    assert ra.fmt_day_month(date(2026, 3, 1), "es") == "1 de marzo"
    assert ra.fmt_day_month(date(2026, 3, 1), "en") == "March 1"


# --------------------------------------------------------------------------
# Template rendering with fixed inputs
# --------------------------------------------------------------------------


def test_render_remesas_es_en():
    facts = {
        "year": 2025, "total": 7727.99, "prev_year": 2024, "prev_total": 6539.9,
        "pct": 18.2, "last_year": 2026, "last_quarter": 2, "last_value": 2041.26,
    }  # fmt: skip
    assert ra.render_remesas(facts, "es")["answer"] == (
        "En 2025 ingresaron US$ 7.728 millones en remesas, 18,2 % más que en 2024 "
        "(US$ 6.540 millones). En el segundo trimestre de 2026 llegaron US$ 2.041 millones."
    )
    assert ra.render_remesas(facts, "en")["answer"] == (
        "In 2025, remittances reached US$ 7,728 million, 18.2% more than in 2024 "
        "(US$ 6,540 million). In the second quarter of 2026, US$ 2,041 million arrived."
    )
    down = {**facts, "pct": -3.0}
    assert "3,0 % menos que en 2024" in ra.render_remesas(down, "es")["answer"]
    assert "3.0% less than in 2024" in ra.render_remesas(down, "en")["answer"]


def test_fetch_remesas_uses_credit_series_and_last_complete_year():
    f = run(ra.fetch_remesas(FakeTools(), CTX))
    assert f["year"] == 2025 and f["prev_year"] == 2024
    assert round(f["total"]) == 7728 and round(f["prev_total"]) == 6540
    assert round(f["pct"], 1) == 18.2
    assert (f["last_year"], f["last_quarter"]) == (2026, 2)


def test_fetch_remesas_ignores_incomplete_year():
    vals = {**REMESAS_VALS}
    del vals["2025-IV"]  # 2025 now incomplete -> 2024 is the last complete year, no previous
    with pytest.raises(ra.RefreshError):
        run(ra.fetch_remesas(FakeTools(get_indicador_bce=bce_series(vals)), CTX))


def test_render_favorita_never_includes_the_legal_representative():
    f = run(ra.fetch_favorita(FakeTools(), CTX))
    assert "representante" not in f and "PEÑAHERRERA" not in json.dumps(f, default=str)
    es, en = ra.render_favorita(f, "es")["answer"], ra.render_favorita(f, "en")["answer"]
    assert es == (
        "RUC 1790016919001. Sociedad anónima activa, constituida el 30 de noviembre de "
        "1957 en Quito, con capital suscrito de US$ 900 millones. Actividad: comercio al "
        "por menor (CIIU G4711.01). Último balance presentado: 2025."
    )
    assert en == (
        "RUC 1790016919001. Active corporation (sociedad anónima), incorporated on "
        "November 30, 1957 in Quito, with subscribed capital of US$ 900 million. "
        "Activity: retail trade (CIIU G4711.01). Latest balance sheet filed: 2025."
    )
    assert "Peñaherrera" not in es + en


def test_favorita_fails_on_unmapped_type_or_missing_ruc():
    bad = copy.deepcopy(FAVORITA)
    bad["companias"][0]["tipo"] = "FUNDACION RARA"
    with pytest.raises(ra.RefreshError):
        run(ra.fetch_favorita(FakeTools(search_companias=bad), CTX))
    with pytest.raises(ra.RefreshError):
        run(ra.fetch_favorita(FakeTools(search_companias={"companias": []}), CTX))


def test_compras_year_is_previous_full_year_and_top_two_buyers_sorted():
    tools = FakeTools()
    f = run(ra.fetch_compras(tools, CTX))
    assert tools.calls == [("get_resumen_compras", {"comprador": "Manta", "year": 2025})]
    assert [n for n, _ in f["buyers"]] == ["HOSPITAL GENERAL MANTA", "GOBIERNO AUTONOMO DESCENTRALIZADO MUNICIPAL DEL CANTON MANTA"]
    es, en = ra.render_compras(f, "es"), ra.render_compras(f, "en")
    assert es["question"] == "¿Cuánto contrató el sector público en Manta en 2025?"
    assert es["answer"] == (
        "253 procesos por US$ 36,2 millones (valor adjudicado o estimado de 212 procesos "
        "con monto). Los mayores compradores fueron el Hospital General Manta "
        "(US$ 18,0 millones) y el Municipio de Manta (US$ 10,9 millones)."
    )
    assert en["answer"] == (
        "253 procedures worth US$ 36.2 million (awarded or estimated value of 212 "
        "procedures with an amount). The largest buyers were the Manta General Hospital "
        "(US$ 18.0 million) and the Municipality of Manta (US$ 10.9 million)."
    )


def test_compras_partial_result_is_rejected():
    with pytest.raises(ra.RefreshError):
        run(ra.fetch_compras(FakeTools(get_resumen_compras={**COMPRAS, "parcial": True}), CTX))


def test_render_pasaporte_es_en():
    f = run(ra.fetch_pasaporte(FakeTools(), CTX))
    assert f["tramite_id"] == "11761" and f["has_minors"]
    assert ra.render_pasaporte(f, "es")["answer"] == (
        "Si eres mayor de 18 años: comprobante de pago (en línea, banco corresponsal o en "
        "la agencia) y cédula física o digital vigente; si renuevas, el pasaporte anterior. "
        "En Quito, Guayaquil y Cuenca lo entregan el mismo día; en otras agencias, en 24 a 72 horas."
    )
    assert ra.render_pasaporte(f, "en")["answer"] == (
        "If you are over 18: proof of payment (online, at a partner bank, or at the office) "
        "and a valid physical or digital ID card; if you are renewing, your previous passport. "
        "In Quito, Guayaquil and Cuenca it is issued the same day; at other offices, within 24 to 72 hours."
    )


def test_pasaporte_requires_the_expected_phrases():
    info = {**TRAMITE_INFO, "procedimiento": "sin entrega el mismo dia"}
    with pytest.raises(ra.RefreshError):
        run(ra.fetch_pasaporte(FakeTools(get_tramite_info=info), CTX))


# --------------------------------------------------------------------------
# Sismos
# --------------------------------------------------------------------------


def test_sismo_filter_excludes_peru_and_colombia():
    flags = {e["id"]: ra.sismo_in_ecuador(e) for e in SISMOS["events"]}
    assert flags == {"a1": True, "a2": True, "a3": False, "a4": True, "a5": False, "a6": False}


def test_sismo_filter_text_beats_coordinates_and_bbox_is_only_a_fallback():
    # Peruvian label with coordinates that fall inside Ecuador's box: text wins.
    border = ev("b", 4.0, 5.0, -4.5, -80.0, "2026-11-01T00:00:00-05:00", "a 10 km de Sullana, Piura")
    assert not ra.sismo_in_ecuador(border)
    # No region in the text: coordinates decide.
    inside = ev("c", 4.0, 5.0, -1.0, -78.0, "2026-11-01T00:00:00-05:00", "Costa afuera")
    outside = ev("d", 4.0, 5.0, 4.0, -75.0, "2026-11-01T00:00:00-05:00", "Costa afuera")
    assert ra.sismo_in_ecuador(inside) and not ra.sismo_in_ecuador(outside)
    galapagos = ev("e", 4.0, 5.0, -0.5, -90.5, "2026-11-01T00:00:00-05:00", "a 50 km de Puerto Ayora, Galápagos")
    assert ra.sismo_in_ecuador(galapagos)


def test_sismos_picks_strongest_inside_ecuador_and_renders_both_languages():
    f = run(ra.fetch_sismos(FakeTools(), CTX))
    assert f["total"] == 6 and f["inside"] == 3
    assert f["strongest"]["id"] == "a1" and f["second"]["id"] == "a2"  # not the M5.95 in Colombia
    assert ra.render_sismos(f, "es")["answer"] == (
        "El más fuerte en territorio ecuatoriano fue de magnitud 4,8, a 45,7 km de Salinas "
        "(Santa Elena), el 7 de noviembre a las 17:17, a 2,4 km de profundidad. "
        "También hubo uno de 3,7 cerca de Pasaje (El Oro)."
    )
    assert ra.render_sismos(f, "en")["answer"] == (
        "The strongest within Ecuadorian territory was magnitude 4.8, 45.7 km from Salinas "
        "(Santa Elena), on November 7 at 17:17, at a depth of 2.4 km. "
        "There was also a 3.7 near Pasaje (El Oro)."
    )


def test_sismos_no_events_template():
    for events in ([], [SISMOS["events"][2], SISMOS["events"][4]]):  # none at all / only Peru+Colombia
        tools = FakeTools(search_sismos={**SISMOS, "total": len(events), "events": events})
        f = run(ra.fetch_sismos(tools, CTX))
        assert f["strongest"] is None
        assert ra.render_sismos(f, "es")["answer"] == (
            "No hubo sismos de magnitud 3,5 o más dentro de Ecuador en los últimos 7 días, "
            "según el catálogo del IG-EPN."
        )
        assert ra.render_sismos(f, "en")["answer"] == (
            "There were no earthquakes of magnitude 3.5 or higher within Ecuador in the "
            "last 7 days, according to the IG-EPN catalog."
        )


def test_sismos_single_event_has_no_second_sentence():
    tools = FakeTools(search_sismos={**SISMOS, "total": 1, "events": SISMOS["events"][:1]})
    text = ra.render_sismos(run(ra.fetch_sismos(tools, CTX)), "es")["answer"]
    assert "También" not in text


def test_sismos_truncated_result_is_rejected():
    with pytest.raises(ra.RefreshError):
        run(ra.fetch_sismos(FakeTools(search_sismos={**SISMOS, "total": 40}), CTX))


# --------------------------------------------------------------------------
# Cortes EEASA
# --------------------------------------------------------------------------


def test_cortes_examples_skip_finished_notices_and_render():
    f = run(ra.fetch_cortes(FakeTools(), CTX))  # now = Nov 8, 23:40
    assert f["count"] == 5
    assert [e["fecha"] for e in f["examples"]] == ["2026-11-09", "2026-11-10"]
    assert ra.render_cortes(f, "es")["answer"] == (
        "Sí, 5 avisos vigentes. Por ejemplo: lunes 9 de noviembre, de 09:00 a 14:00, en el "
        "barrio Callate San Antonio (Píllaro); martes 10, de 10:00 a 14:00, en el barrio "
        "La Libertad (Puyo)."
    )
    assert ra.render_cortes(f, "en")["answer"] == (
        "Yes, 5 active notices. For example: Monday, November 9, from 09:00 to 14:00, in the "
        "Callate San Antonio neighborhood (Píllaro); Tuesday, November 10, from 10:00 to "
        "14:00, in the La Libertad neighborhood (Puyo)."
    )


def test_cortes_no_notices_template():
    tools = FakeTools(search_cortes={"total": 0, "archivos": [], "url_fuente": CORTES["url"]})
    f = run(ra.fetch_cortes(tools, CTX))
    assert f["count"] == 0 and ("get_cortes_horarios" not in [c[0] for c in tools.calls])
    assert ra.render_cortes(f, "es")["answer"].startswith("No hay avisos de trabajos programados vigentes")
    assert ra.render_cortes(f, "en")["answer"].startswith("There are no active scheduled-work notices")


def test_cortes_all_notices_in_the_past():
    late = ra.Ctx(datetime(2026, 12, 1, 8, 0, tzinfo=ra.ECUADOR_TZ))
    f = run(ra.fetch_cortes(FakeTools(), late))
    assert f["count"] == 5 and f["examples"] == []
    assert "ya pasaron" in ra.render_cortes(f, "es")["answer"]
    assert "already passed" in ra.render_cortes(f, "en")["answer"]


# --------------------------------------------------------------------------
# Census checks and transcripts
# --------------------------------------------------------------------------


def test_censo_checks_fail_when_tabulado_disappears():
    other = {**ARCHIVOS, "archivos": [{"url": "https://x.gob.ec/otro.xlsx"}]}
    with pytest.raises(ra.RefreshError):
        run(ra.fetch_manta_internet(FakeTools(search_archivos=other), CTX))
    assert run(ra.fetch_manta_internet(FakeTools(), CTX)) == {"xlsx": "03_2022_CPV_TIC.xlsx"}


def test_censo_requires_external_link_shape():
    with pytest.raises(ra.RefreshError):
        run(ra.fetch_censo(FakeTools(download_anda_microdata={"tipo_acceso": "direct"}), CTX))


# --------------------------------------------------------------------------
# End-to-end refresh over the repo's real JSON, with canned tools
# --------------------------------------------------------------------------


def test_refresh_updates_answers_transcripts_dates_and_version():
    data = load_real()
    res = run(ra.refresh(data, FakeTools(), ra.Ctx(datetime(2026, 11, 20, 10, 0, tzinfo=ra.ECUADOR_TZ)), "9.9.9"))
    assert [r.status for r in res.results].count("kept-previous") == 0
    for lang in ("es", "en"):
        a = res.data[f"{lang}_answers"]
        assert (a["extracted_at"], a["server_version"]) == ("2026-11-20", "9.9.9")
    es = {x["id"]: x for x in res.data["es_answers"]["answers"]}
    assert "magnitud 4,8" in es["sismos"]["answer"]
    assert "US$ 7.728 millones en remesas, 18,2 % más" in es["remesas"]["answer"]
    steps = {t["id"]: t["steps"] for t in res.data["es_transcripts"]}
    sismo_answer = next(s for s in steps["sismos"] if s["kind"] == "answer")
    assert sismo_answer["text"].startswith("El más fuerte en Ecuador fue de **magnitud 4,8**")
    assert sismo_answer["cite"] == "igepn.edu.ec · evento a1"
    assert steps["sismos"][1]["result"] == "6 eventos · catálogo IG-EPN"
    assert next(s for s in steps["pasaporte"] if s.get("tool") == "search_tramites")["result"] == (
        "2 trámites · mayores y menores de 18 años"
    )
    en_steps = {t["id"]: t["steps"] for t in res.data["en_transcripts"]}
    assert en_steps["sismos"][1]["result"] == "6 events · IG-EPN catalog"
    assert "**magnitude 4.8**" in next(s for s in en_steps["sismos"] if s["kind"] == "answer")["text"]
    # input is never mutated
    assert data == load_real()


def test_failed_call_keeps_previous_answer_and_transcript_untouched():
    data = load_real()
    before_es = copy.deepcopy(data["es_answers"]["answers"][1])  # sismos
    tools = FakeTools(search_sismos=RuntimeError("IG-EPN down"))
    res = run(ra.refresh(data, tools, ra.Ctx(datetime(2026, 11, 20, tzinfo=ra.ECUADOR_TZ)), "9.9.9"))
    by = {r.unit: r for r in res.results}
    assert by["sismos"].status == "kept-previous" and "IG-EPN down" in by["sismos"].detail
    assert by["remesas"].status in {"updated", "unchanged"}
    es = {x["id"]: x for x in res.data["es_answers"]["answers"]}
    kept = {k: v for k, v in es["sismos"].items() if k != "extracted_at"}
    assert kept == before_es
    # honest per-answer date for the stale one, none for refreshed ones
    assert es["sismos"]["extracted_at"] == data["es_answers"]["extracted_at"]
    assert "extracted_at" not in es["remesas"]
    assert res.data["es_transcripts"][1] == data["es_transcripts"][1]
    assert res.data["en_transcripts"][1] == data["en_transcripts"][1]
    assert res.data["es_answers"]["extracted_at"] == "2026-11-20"


def test_unparsable_value_keeps_previous_instead_of_half_filling():
    data = load_real()
    broken = bce_series({**REMESAS_VALS, "2026-II": "n/a"})
    res = run(ra.refresh(data, FakeTools(get_indicador_bce=broken), CTX, "9.9.9"))
    by = {r.unit: r for r in res.results}
    assert by["remesas"].status == "kept-previous"
    es = {x["id"]: x for x in res.data["es_answers"]["answers"]}
    old = {x["id"]: x for x in data["es_answers"]["answers"]}
    assert es["remesas"]["answer"] == old["remesas"]["answer"]


def test_when_everything_fails_nothing_changes_and_exit_code_is_3(tmp_path, monkeypatch, capsys):
    paths = {}
    for key, src in ra.FILES.items():
        dst = tmp_path / f"{key}.json"
        dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        paths[key] = dst

    async def boom(name, **args):
        raise ConnectionError("offline")

    original = {k: p.read_bytes() for k, p in paths.items()}
    monkeypatch.setattr(ra, "FILES", paths)
    code = ra.main([], call=boom)
    assert code == 3
    assert {k: p.read_bytes() for k, p in paths.items()} == original
    assert capsys.readouterr().out.count("[kept-previous]") == len(ra.UNITS)


def test_dry_run_prints_diff_and_writes_nothing(tmp_path, monkeypatch, capsys):
    paths = {}
    for key, src in ra.FILES.items():
        dst = tmp_path / f"{key}.json"
        dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        paths[key] = dst
    original = {k: p.read_bytes() for k, p in paths.items()}
    monkeypatch.setattr(ra, "FILES", paths)
    code = ra.main(["--dry-run", "--today", "2026-12-01"], call=FakeTools())
    out = capsys.readouterr().out
    assert code == 0
    assert "extracted_at" in out and out.count("@@") >= 1
    assert {k: p.read_bytes() for k, p in paths.items()} == original


# --------------------------------------------------------------------------
# ES/EN parity and file layout
# --------------------------------------------------------------------------


def test_repo_data_has_es_en_parity_of_ids_urls_and_tools():
    ra.check_parity(load_real())


def test_parity_check_catches_a_diverging_url_or_id():
    data = load_real()
    data["en_answers"]["answers"][0]["url"] = "https://example.org/other"
    with pytest.raises(ValueError, match="url"):
        ra.check_parity(data)
    data = load_real()
    data["en_answers"]["answers"].reverse()
    with pytest.raises(ValueError, match="ids"):
        ra.check_parity(data)


def test_refresh_keeps_parity_even_when_urls_come_from_tools():
    res = run(ra.refresh(load_real(), FakeTools(), CTX, "9.9.9"))
    ra.check_parity(res.data)


def test_serializers_round_trip_the_hand_formatted_files_byte_for_byte():
    data = load_real()
    for key, path in ra.FILES.items():
        assert ra.render_files(data)[key] == path.read_text(encoding="utf-8"), key


def test_decimal_helpers_do_not_use_float_artifacts():
    assert ra.fmt_number(Decimal("2.675"), 2, "en") == "2.68"
    assert ra.parse_capital("900.000.000,00") == Decimal("900000000.00")
    with pytest.raises(ra.RefreshError):
        ra.parse_capital("abc")


def test_buyer_names_are_readable_in_both_languages():
    long = (
        "EMPRESA PUBLICA MUNICIPAL DE AGUA POTABLE, ALCANTARILLADO, MANEJO PLUVIAL Y "
        "DEPURACION DE RESIDUOS LIQUIDOS DEL CANTON MANTA"
    )
    assert ra.buyer_name(long, "es") == "Empresa Pública Municipal de Agua Potable"
    assert ra.buyer_name("IESS HOSPITAL X", "en") == "IESS Hospital X"
    assert ra.buyer_name("HOSPITAL GENERAL MANTA", "en") == "the Manta General Hospital"
