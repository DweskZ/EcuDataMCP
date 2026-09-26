from fpdf import FPDF

from helpers import eeq_cortes_client
from helpers.eeq_cortes_pdf import parse_horario, parse_pdf

# Synthetic PDFs that reproduce the positions and font sizes measured on
# the real EEQ slides (2000-pt-wide pages): header text >= 30pt, the
# "Sectores" column header at x=441, substations at x~120 (23pt, 2024) or
# x~235 (17pt, 2023), sectors at x=442 (18pt), 2023 time stack at x~80.
_W, _H = 2000, 1262


def _pdf(pages: list[list[tuple[float, float, float, str]]]) -> bytes:
    pdf = FPDF(unit="pt", format=(_W, _H))
    pdf.set_auto_page_break(False)
    for items in pages:
        pdf.add_page()
        for x, y, size, text in items:
            pdf.set_font("Helvetica", size=size)
            pdf.text(x, _H - y, text)  # fpdf measures y from the top
    return bytes(pdf.output())


_HEADER_2024 = [
    (92, 1159, 66, "Programación"),
    (1711, 1175, 71, "Lunes 29"),
    (1614, 1125, 59, "de abril de 2024"),
    (1624, 1038, 67, "07:30 - 10:30 / 18h00 - 19h00"),
    (441, 928, 21, "SectoresSubestaciones"),
    (1855, 67, 13.6, "Ministerio de"),
]

_PAGE_2024 = _HEADER_2024 + [
    # Row 1: two lines, label top-aligned.
    (122, 883, 23, "LULUNCOTO"),
    (442, 885, 18, "PASTEURIZADORA Y ALREDEDORES, CHIMBACALLE,"),
    (442, 864, 18, "CALLES RÍO CHAMBO"),
    # Row 2 after a blank line, label wrapped over two lines.
    (122, 830, 23, "SANTA"),
    (122, 808, 23, "ROSA"),
    (442, 822, 18, "LA LIBERTAD, YAGUACHI"),
    # Compact rows (no blank line between them), labels centered on
    # their own rows: split at the midpoint between the two labels.
    (122, 756, 23, "SAN ROQUE"),
    (442, 780, 18, "MERCADO DE SAN ROQUE,"),
    (442, 759, 18, "TEMPLO DE LA PATRIA,"),
    (442, 738, 18, "LA RECOLETA"),
    (442, 717, 18, "CALLES BOLIVIA Y RITTER,"),
    (442, 696, 18, "LA GASCA"),
    (122, 703, 23, "MIRAFLORES"),
    # Notice in the left column, outside the grid.
    (122, 500, 23, "IMPORTANTE"),
]

_PAGE_2023 = [
    (1766, 1109, 65, "Lunes,"),
    (1678, 1066, 42.7, "30 de octubre"),
    (90, 972, 21.3, "Hora"),
    (441, 972, 21.3, "SectoresSubestaciones"),
    (80, 900, 28, "08:00"),
    (111, 871, 28, "a"),
    (83, 842, 28, "10:00"),
    (235, 919, 17, "OLÍMPICO"),
    (442, 929, 17, "ANA LUISA, CAMPO ALEGRE,"),
    (442, 908, 17, "BELLAVISTA ALTO."),
    (235, 866, 17, "Barrionuevo"),
    (442, 866, 17, "ATAHUALPA E, BARRIONUEVO"),
    (80, 700, 30, "10:00"),
    (111, 671, 30, "a"),
    (83, 642, 30, "12:00"),
    (235, 680, 17, "CONOCOTO"),
    (442, 680, 17, "LA ARMENIA, COLLACOTO"),
]


def test_parse_horario_normalizes_variants():
    assert parse_horario("04:00 - 08:00 / 18:00 - 19:00") == [
        "04:00-08:00",
        "18:00-19:00",
    ]
    assert parse_horario("10h30 - 14h00") == ["10:30-14:00"]
    assert parse_horario("De 7:00 a 9:30") == ["07:00-09:30"]


def test_parse_pdf_2024_layout():
    result = parse_pdf(_pdf([_PAGE_2024]))

    filas = result["filas"]
    assert [f["subestacion"] for f in filas] == [
        "LULUNCOTO",
        "SANTA ROSA",
        "SAN ROQUE",
        "MIRAFLORES",
    ]
    assert filas[0]["sectores"] == (
        "PASTEURIZADORA Y ALREDEDORES, CHIMBACALLE, CALLES RÍO CHAMBO"
    )
    assert (
        filas[2]["sectores"] == "MERCADO DE SAN ROQUE, TEMPLO DE LA PATRIA, LA RECOLETA"
    )
    assert filas[3]["sectores"] == "CALLES BOLIVIA Y RITTER, LA GASCA"
    assert all(f["horario"] == ["07:30-10:30", "18:00-19:00"] for f in filas)
    assert filas[0]["fecha_texto"] == "Lunes 29 de abril de 2024"
    assert filas[0]["pagina"] == 1
    assert result["filas_sin_subestacion"] == 0


def test_parse_pdf_2023_layout_time_column():
    filas = parse_pdf(_pdf([_PAGE_2023]))["filas"]

    by_sub = {f["subestacion"]: f for f in filas}
    assert set(by_sub) == {"OLÍMPICO", "Barrionuevo", "CONOCOTO"}
    assert by_sub["OLÍMPICO"]["horario"] == ["08:00-10:00"]
    assert by_sub["Barrionuevo"]["horario"] == ["08:00-10:00"]
    # The second stack is 30pt, the header-size cutoff: still a time.
    assert by_sub["CONOCOTO"]["horario"] == ["10:00-12:00"]
    assert by_sub["OLÍMPICO"]["fecha_texto"] == "Lunes, 30 de octubre"


def test_industrial_banner_is_a_flag_not_part_of_the_date():
    page = [c for c in _PAGE_2024 if c[3] != "de abril de 2024"] + [
        (1614, 1125, 59, "SECTOR INDUSTRIAL"),
        (1614, 1090, 40, "AV1"),
        (1614, 1060, 40, "Lunes 29"),
    ]
    filas = parse_pdf(_pdf([page]))["filas"]

    assert filas[0]["sector_industrial"] is True
    assert filas[0]["fecha_texto"] == "Lunes 29"


async def test_get_eeq_cortes_horarios_filters_by_query(httpx_mock):
    eeq_cortes_client._horarios_cache.clear()
    httpx_mock.add_response(
        url=f"{eeq_cortes_client._DOC_BASE}/29_04_2024",
        content=_pdf([_PAGE_2024]),
        headers={"Content-Type": "application/pdf"},
    )

    result = await eeq_cortes_client.get_eeq_cortes_horarios(
        "29_04_2024", query="templo"
    )

    assert result["total"] == 1
    assert result["total_en_archivo"] == 4
    assert result["filas"][0]["subestacion"] == "SAN ROQUE"


async def test_get_eeq_cortes_horarios_rejects_bad_slug():
    import pytest

    with pytest.raises(ValueError, match="slug"):
        await eeq_cortes_client.get_eeq_cortes_horarios("vsd?x=1")
