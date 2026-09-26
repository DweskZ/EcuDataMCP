import pytest
from fpdf import FPDF

from helpers import centrosur_cortes_client
from helpers.centrosur_cortes_pdf import _split_place, parse_pdf
from helpers.eeq_cortes_pdf import parse_horario

# Synthetic PDFs reproducing the positions and font sizes measured on the
# real Centrosur files (Oct 2023 tables, Apr 2024 infographic).
_W, _H = 842, 1191


def _pdf(pages: list[list[tuple[float, float, float, str]]], w=_W, h=_H) -> bytes:
    pdf = FPDF(unit="pt", format=(w, h))
    pdf.set_auto_page_break(False)
    for items in pages:
        pdf.add_page()
        for x, y, size, text in items:
            pdf.set_font("Helvetica", size=size)
            pdf.text(x, h - y, text)  # fpdf measures y from the top
    return bytes(pdf.output())


_TABLE_2023 = [
    (109, 1084, 35.5, "Programación"),
    (54, 935, 21.6, "Viernes, 27 de octubre de 2023"),
    (54, 907, 21.6, "De 15:00 - 18:00"),
    (87, 886, 8.4, "PROVINCIA CANTÓN ZONA DE CORTE SECTORES"),
    # Row with its own province/canton/zone labels.
    (101, 860, 6.6, "AZUAY CUENCA GAPAL"),
    (479, 866, 6.6, "AV. 24 DE MAYO ENTRE 5 DE JUNIO Y GAPAL, CIRCUNVALACION SUR,"),
    (479, 857, 6.6, "UDA, ESCUELA FE Y ALEGRIA."),
    # Two rows under a canton printed once as a merged cell.
    (238, 790, 6.6, "GUALACEO"),
    (330, 810, 6.6, "GUALACEO CENTRO"),
    (479, 810, 6.6, "GUALACEO CENTRO, AYALOMA, VIA QUIMZH, PARCULOMA, BULLCAY"),
    (330, 770, 6.6, "MERCADO 25 DE JUNIO"),
    (479, 770, 6.6, "MERCADO 25 DE JUNIO, CALLE COLON, CALLE GRAN COLOMBIA"),
]

_INFOGRAPHIC_2024 = [
    (793, 8052, 27.2, "Jueves 18 y viernes 19"),
    (793, 8024, 27.2, "de abril del 2024"),
    (36, 8050, 40.1, "Programación"),
    (793, 7957, 45.7, "00:00 a 05:00"),
    (62, 7895, 11.0, "CANTÓN ZONA DE CORTE  SECTORES"),
    (57, 7861, 11.4, "CUENCA QUINTA CHICA"),
    (
        359,
        7869,
        11.4,
        "AV AMERICAS ENTRE INDEPENDENCIA Y GONZALEZ SUAREZ, QUINTA CHICA,",
    ),
    (359, 7853, 11.4, "PASEO MILCHICHIG ENTRE AV ESPAÑA Y HUANCAVILCAS"),
    (804, 7751, 50.2, "02:00 a 06:00"),
    (69, 7699, 11.0, "CANTÓN ZONA DE CORTE  SECTORES"),
    (57, 7650, 11.4, "SANTA ISABEL"),
    (150, 7650, 11.4, "JUBONES"),
    (359, 7658, 11.4, "JUBONES, CAÑARIBAMBA, PEÑA BLANCA, COCHA SECA, ÑUGRO,"),
    (359, 7642, 11.4, "AZHIDEL"),
]


def test_parse_horario_accepts_unicode_hyphen():
    # Centrosur's 2023 PDFs use U+2010 between the two times.
    assert parse_horario("08:00 ‐ 12:00") == ["08:00-12:00"]


def test_split_place_reads_province_canton_and_zone():
    assert _split_place("AZUAY CUENCA GAPAL") == ("Azuay", "Cuenca", "GAPAL")
    assert _split_place("MORONA SANTIAGO MÉNDEZ VÍA GUARUMALES") == (
        "Morona Santiago",
        "Santiago",
        "VÍA GUARUMALES",
    )
    assert _split_place("PLAZA DE LAS AMÉRICAS") == (
        None,
        None,
        "PLAZA DE LAS AMÉRICAS",
    )


def test_parse_table_2023():
    result = parse_pdf(_pdf([_TABLE_2023]))

    assert result["formato"] == "tabla"
    filas = result["filas"]
    assert [f["zona"] for f in filas] == [
        "GAPAL",
        "GUALACEO CENTRO",
        "MERCADO 25 DE JUNIO",
    ]
    assert all(f["horario"] == ["15:00-18:00"] for f in filas)
    assert filas[0]["fecha_texto"] == "Viernes, 27 de octubre de 2023"
    assert (filas[0]["provincia"], filas[0]["canton"]) == ("Azuay", "Cuenca")
    assert filas[0]["canton_inferido"] is False
    assert filas[0]["sectores"].endswith("UDA, ESCUELA FE Y ALEGRIA.")

    # The merged "GUALACEO" cell covers both rows below it; the province
    # comes from the canton, and the canton is flagged as inferred where
    # the cell isn't level with the row.
    assert {f["canton"] for f in filas[1:]} == {"Gualaceo"}
    assert {f["provincia"] for f in filas[1:]} == {"Azuay"}


def test_parse_infographic_2024_time_sections():
    filas = parse_pdf(_pdf([_INFOGRAPHIC_2024], w=1080, h=8096))["filas"]

    assert [(f["horario"], f["canton"], f["zona"]) for f in filas] == [
        (["00:00-05:00"], "Cuenca", "QUINTA CHICA"),
        (["02:00-06:00"], "Santa Isabel", "JUBONES"),
    ]
    assert filas[1]["canton_inferido"] is False
    assert filas[1]["sectores"].endswith("AZHIDEL")
    assert filas[0]["fecha_texto"] == "Jueves 18 y viernes 19 de abril del 2024"


def test_image_only_pdf_is_reported_not_parsed():
    result = parse_pdf(_pdf([[]]))

    assert result["formato"] == "imagen"
    assert result["filas"] == []
    assert "OCR" in result["nota"]


async def test_get_centrosur_cortes_horarios_filters_by_query(httpx_mock):
    centrosur_cortes_client._horarios_cache.clear()
    url = "https://www.centrosur.gob.ec/wp-content/uploads/2023/10/Desconexion-de-15-a-18-horas.pdf"
    httpx_mock.add_response(
        url=url,
        content=_pdf([_TABLE_2023]),
        headers={"Content-Type": "application/pdf"},
    )

    result = await centrosur_cortes_client.get_centrosur_cortes_horarios(
        url, query="gualaceo"
    )

    assert result["total"] == 2
    assert result["total_en_archivo"] == 3


async def test_get_centrosur_cortes_horarios_rejects_foreign_url():
    with pytest.raises(ValueError, match="centrosur"):
        await centrosur_cortes_client.get_centrosur_cortes_horarios(
            "https://example.com/x.pdf"
        )
