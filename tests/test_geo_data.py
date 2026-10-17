from helpers import geo_data
from helpers.geo_data import (
    find_cantones,
    find_parroquias,
    find_parroquias_urbanas,
    find_provincias,
    list_cantones,
    list_parroquias,
    list_parroquias_urbanas,
    list_provincias,
)


def test_list_provincias_has_24():
    items = list_provincias()
    assert len(items) == 24
    assert items[0]["codigo"] == "01"


def test_find_by_name_and_capital():
    assert find_provincias("pichincha")[0]["codigo"] == "17"
    assert find_provincias("guayaquil")[0]["codigo"] == "09"
    assert find_provincias("09")[0]["nombre"] == "Guayas"


def test_filter_region():
    costa = find_provincias(region="Costa")
    assert all(p["region"] == "Costa" for p in costa)
    assert len(costa) >= 6


def test_cantones_loaded():
    items = list_cantones()
    assert len(items) >= 220
    cuenca = find_cantones("cuenca")
    assert cuenca
    assert cuenca[0]["codigo"].startswith("01")


def test_cantones_by_province():
    pichincha = find_cantones(provincia="Pichincha")
    assert pichincha
    assert all(c["provincia_codigo"] == "17" for c in pichincha)


def test_parroquias_loaded():
    items = list_parroquias()
    assert len(items) >= 1000
    assert items[0]["codigo"]


def test_find_parroquia_tumbaco():
    rows = find_parroquias("tumbaco")
    assert rows
    assert any(r["nombre"].lower() == "tumbaco" for r in rows)
    assert rows[0]["provincia_codigo"] == "17"


def test_parroquias_by_canton():
    rows = find_parroquias(canton="Quito")
    assert len(rows) >= 10
    assert all("quito" in r["canton"].lower() for r in rows)


def test_urban_parishes_guayaquil_include_tarqui():
    rows = geo_data.find_parroquias_urbanas(canton="Guayaquil", provincia="Guayas")
    tarqui = next(r for r in rows if r["nombre"] == "Tarqui")
    assert tarqui["codigo_parroquia_urbana"] == "090112"
    assert tarqui["codigo"] == "090150"
    assert tarqui["clasificador_anio"] == geo_data.CLASIFICADOR_ANIO


def test_urban_parishes_have_numeric_codes_and_names():
    # Two rows of the INEC classifier export (Cayambe 170250, Sansahuari
    # 210355) came through with codigo " " and an empty nombre; the data
    # file must only carry real urban parishes.
    for row in list_parroquias_urbanas():
        assert row["codigo_parroquia_urbana"].isdigit(), row
        assert len(row["codigo_parroquia_urbana"]) == 6, row
        assert row["nombre"].strip(), row
        assert row["codigo"].isdigit() and row["canton_codigo"].isdigit(), row


def test_numeric_province_filter_matches_code_exactly():
    # "1" used to substring-match provinces 01, 10-19 and 21 (127 cantons).
    azuay = find_cantones(provincia="01")
    assert len(azuay) == 15
    assert find_cantones(provincia="1") == azuay
    assert all(c["provincia_codigo"] == "01" for c in find_cantones(provincia="1"))
    assert find_cantones(provincia="Azuay") == azuay


def test_numeric_canton_and_province_filters_for_parroquias():
    quito = find_parroquias(canton="1701")
    assert quito
    assert all(r["canton_codigo"] == "1701" for r in quito)
    # The name filter stays a substring match ("Quito" also hits Puerto Quito).
    assert set(map(str, quito)) < set(map(str, find_parroquias(canton="Quito")))
    assert find_parroquias(provincia="17") == find_parroquias(provincia="Pichincha")
    assert {r["provincia_codigo"] for r in find_parroquias(provincia="9")} == {"09"}
    urbanas = find_parroquias_urbanas(canton="901")
    assert urbanas and all(r["canton_codigo"] == "0901" for r in urbanas)
