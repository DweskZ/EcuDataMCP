import pytest

from helpers import arconel_reportes_client as client

# Fixtures below are trimmed but structurally faithful copies of what
# reportes.arconel.gob.ec returned on 2026-09-25: the MS AJAX delta format,
# the filter <select>s inside UpdatePanel1, SSRS's 1x1 layout tables around
# the data grid, and the ToolBarUpdate script literal.

_TIPO_OPTIONS = (
    '<option value="---------------------- Transacciones ----------------------">'
    "---------------------- Transacciones ----------------------</option>"
    '<option value="Balance Energía">Balance Energ&#237;a</option>'
    '<option value="Pérdidas">P&#233;rdidas</option>'
    '<option value="---------------------- Infraestructura ----------------------">'
    "---------------------- Infraestructura ----------------------</option>"
    '<option value="Subestaciones">Subestaciones</option>'
)


def _form(mes_disabled: bool = True) -> str:
    disabled = ' disabled="disabled"' if mes_disabled else ""
    return (
        f'<select name="ctl00$dpTipo" id="dpTipo">{_TIPO_OPTIONS}</select>'
        '<select name="ctl00$dpAnio" id="dpAnio"><option value="0">-- AÑO --</option>'
        '<option value="2024">2024</option><option value="2023">2023</option></select>'
        f'<select name="ctl00$dpMes" id="dpMes"{disabled}><option value="0">--</option>'
        '<option value="1">Enero</option></select>'
        '<select name="ctl00$dpGrupoEmpresa" id="dpGrupoEmpresa">'
        '<option value="0">--</option><option value="1">Todos</option>'
        '<option value="2">01 CNEL</option><option value="3">02 EE</option></select>'
    )


_INITIAL_PAGE = (
    "<html><form>"
    '<input type="hidden" name="__VIEWSTATE" id="__VIEWSTATE" value="vs0" />'
    '<input type="hidden" name="__VIEWSTATEGENERATOR" id="__VIEWSTATEGENERATOR" value="CA0B0334" />'
    '<input type="hidden" name="__EVENTVALIDATION" id="__EVENTVALIDATION" value="ev0" />'
    f"{_form()}</form></html>"
)


def _delta(*blocks: tuple[str, str, str]) -> str:
    return "".join(f"{len(c)}|{t}|{i}|{c}|" for t, i, c in blocks)


def _hidden(n: int) -> list[tuple[str, str, str]]:
    return [
        ("hiddenField", "__VIEWSTATE", f"vs{n}"),
        ("hiddenField", "__EVENTVALIDATION", f"ev{n}"),
    ]


def _grid(rows: list[list[str]]) -> str:
    body = "".join(
        "<tr>" + "".join(f"<td><div>{c}</div></td>" for c in r) + "</tr>" for r in rows
    )
    # Real SSRS output: the grid sits two 1x1 layout tables deep.
    return f"<table><tr><td><table><tr><td><table>{body}</table></td></tr></table></td></tr></table>"


def _page(rows: list[list[str]], current: int, total: int, estimate: bool) -> str:
    toolbar = (
        f"\"ToolBarUpdate\":{{'CurrentPage':{current},'TotalPages':{total},"
        f"'IsEstimatePageCount':{'true' if estimate else 'false'},'TotalPagesString':'{total}'}}"
    )
    return _delta(
        *_hidden(10 + current),
        (
            "updatePanel",
            "ctl00_contenidoCentro_ReportViewer1_ctl09_ReportArea",
            _grid(rows),
        ),
        ("scriptStartupBlock", "ScriptContentNoTags", f"$create(X, {{{toolbar}}});"),
    )


_HEADER = [
    "",
    "Id Empresa",
    "Empresa",
    "Año",
    "Mes",
    "Pérdidas Sistema MWh",
    "Observaciones",
]
_PAGE1 = [
    [""] * 7,
    _HEADER,
    ["", "11", "E.E. Ambato", "2023", "Ene", "2919,235959", ""],
    ["", "11", "E.E. Ambato", "2023", "Feb", "2801,5", ""],
]
_PAGE2 = [[""] * 7, ["", "193", "E.E. Sur", "2023", "Dic", "3240,00781", "revisado"]]


@pytest.fixture(autouse=True)
def clear_cache():
    client._reportes_cache.clear()
    client._catalogo_cache.clear()
    yield
    client._reportes_cache.clear()
    client._catalogo_cache.clear()


def _mock_report(httpx_mock, pages: list[str], mes_disabled: bool = True) -> None:
    # Catalog GET, then the report session's own GET.
    httpx_mock.add_response(method="GET", url=client._URL, text=_INITIAL_PAGE)
    httpx_mock.add_response(method="GET", url=client._URL, text=_INITIAL_PAGE)
    for n in range(3):  # dpTipo, dpAnio, dpGrupoEmpresa
        httpx_mock.add_response(
            method="POST",
            url=client._URL,
            text=_delta(
                *_hidden(n + 1), ("updatePanel", "UpdatePanel1", _form(mes_disabled))
            ),
        )
    httpx_mock.add_response(
        method="POST", url=client._URL, text=_delta(*_hidden(5))
    )  # Generar
    for page in pages:
        httpx_mock.add_response(method="POST", url=client._URL, text=page)


def test_parse_delta_uses_length_not_separator():
    text = _delta(("updatePanel", "p1", "a|b|c"), ("hiddenField", "__VIEWSTATE", "xyz"))
    assert client.parse_delta(text) == [
        ("updatePanel", "p1", "a|b|c"),
        ("hiddenField", "__VIEWSTATE", "xyz"),
    ]


def test_extract_grid_unwraps_layout_tables():
    grid = client.extract_grid(_grid(_PAGE1))
    assert len(grid) == 4
    assert grid[1][1] == "Id Empresa"


async def test_list_arconel_reportes_groups_by_section(httpx_mock):
    httpx_mock.add_response(method="GET", url=client._URL, text=_INITIAL_PAGE)

    result = await client.list_arconel_reportes()

    assert result["tipos"] == [
        {"tipo": "Balance Energía", "seccion": "Transacciones"},
        {"tipo": "Pérdidas", "seccion": "Transacciones"},
        {"tipo": "Subestaciones", "seccion": "Infraestructura"},
    ]
    assert result["anios"] == ["2024", "2023"]


async def test_get_reporte_follows_pages_until_count_is_final(httpx_mock):
    _mock_report(httpx_mock, [_page(_PAGE1, 1, 2, True), _page(_PAGE2, 2, 2, False)])

    result = await client.get_arconel_reporte("balance energia", 2023)

    assert result["completo"] is True
    assert result["paginas_leidas"] == 2
    assert result["paginas_total"] == "2"
    assert result["columnas"] == _HEADER[1:]
    assert result["total_filas"] == 3
    first, last = result["filas"][0], result["filas"][-1]
    assert first["Id Empresa"] == 11
    assert first["Pérdidas Sistema MWh"] == pytest.approx(2919.235959)
    assert first["Observaciones"] is None
    assert last["Empresa"] == "E.E. Sur"
    assert last["Observaciones"] == "revisado"

    next_post = httpx_mock.get_requests(method="POST")[-1]
    assert b"Next%24ctl00" in next_post.content
    assert b"VisibilityState%24ctl00=ReportPage" in next_post.content


async def test_get_reporte_stops_at_max_paginas(httpx_mock):
    _mock_report(httpx_mock, [_page(_PAGE1, 1, 2, True)])

    result = await client.get_arconel_reporte("Balance Energía", 2023, max_paginas=1)

    assert result["completo"] is False
    assert result["paginas_total"] == "2 ?"
    assert result["total_filas"] == 2


async def test_get_reporte_detects_pagination_stuck_on_page_one(httpx_mock):
    # A malformed Next postback makes the server silently resend page 1.
    _mock_report(httpx_mock, [_page(_PAGE1, 1, 2, True), _page(_PAGE1, 1, 2, True)])

    with pytest.raises(client.ArconelError, match="desincronizada"):
        await client.get_arconel_reporte("Balance Energía", 2023)


async def test_get_reporte_rejects_month_on_report_without_month_filter(httpx_mock):
    httpx_mock.add_response(method="GET", url=client._URL, text=_INITIAL_PAGE)
    httpx_mock.add_response(method="GET", url=client._URL, text=_INITIAL_PAGE)
    for n in range(2):
        httpx_mock.add_response(
            method="POST",
            url=client._URL,
            text=_delta(*_hidden(n + 1), ("updatePanel", "UpdatePanel1", _form(True))),
        )

    with pytest.raises(client.ArconelError, match="no se filtra por mes"):
        await client.get_arconel_reporte("Balance Energía", 2023, mes=3)


async def test_get_reporte_rejects_unknown_tipo(httpx_mock):
    httpx_mock.add_response(method="GET", url=client._URL, text=_INITIAL_PAGE)

    with pytest.raises(client.ArconelError, match="desconocido"):
        await client.get_arconel_reporte("Energía Nuclear", 2023)


async def test_server_error_block_raises(httpx_mock):
    httpx_mock.add_response(method="GET", url=client._URL, text=_INITIAL_PAGE)
    httpx_mock.add_response(method="GET", url=client._URL, text=_INITIAL_PAGE)
    httpx_mock.add_response(method="POST", url=client._URL, text="0|error|500||")

    with pytest.raises(client.ArconelError, match="error"):
        await client.get_arconel_reporte("Balance Energía", 2023)
