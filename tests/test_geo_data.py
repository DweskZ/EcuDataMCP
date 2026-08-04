from helpers.geo_data import (
    find_cantones,
    find_provincias,
    list_cantones,
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
