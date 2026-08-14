from helpers.csv_reader import normalize_eu_decimal_columns, strip_geometry_columns


def test_strip_geometry_columns_by_name():
    headers = ["id", "nombre", "geom"]
    rows = [["1", "Quito", "POLYGON((-78.5 -0.2, -78.4 -0.1, -78.5 -0.2))"]]

    new_headers, new_rows, dropped = strip_geometry_columns(headers, rows)

    assert new_headers == ["id", "nombre"]
    assert new_rows == [["1", "Quito"]]
    assert dropped == ["geom"]


def test_strip_geometry_columns_by_content():
    headers = ["id", "the_shape"]
    rows = [
        ["1", "MULTIPOLYGON(((-78.5 -0.2, -78.4 -0.1, -78.5 -0.2)))"],
        ["2", "MULTIPOLYGON(((-79.5 -1.2, -79.4 -1.1, -79.5 -1.2)))"],
    ]

    new_headers, new_rows, dropped = strip_geometry_columns(headers, rows)

    assert new_headers == ["id"]
    assert new_rows == [["1"], ["2"]]
    assert dropped == ["the_shape"]


def test_strip_geometry_columns_no_geometry():
    headers = ["id", "nombre"]
    rows = [["1", "Quito"]]

    new_headers, new_rows, dropped = strip_geometry_columns(headers, rows)

    assert new_headers == headers
    assert new_rows == rows
    assert dropped == []


def test_normalize_eu_decimal_columns():
    headers = ["provincia", "monto"]
    rows = [["Pichincha", "7.760,2"], ["Guayas", "168,15"]]

    new_rows, converted = normalize_eu_decimal_columns(headers, rows)

    assert converted == ["monto"]
    assert new_rows == [["Pichincha", "7760.2"], ["Guayas", "168.15"]]


def test_normalize_eu_decimal_columns_negative_value():
    headers = ["variacion"]
    rows = [["-1.234,5"]]

    new_rows, converted = normalize_eu_decimal_columns(headers, rows)

    assert converted == ["variacion"]
    assert new_rows == [["-1234.5"]]


def test_normalize_eu_decimal_columns_leaves_ambiguous_columns():
    headers = ["fecha", "id"]
    rows = [["2026-01-01", "100"], ["2026-01-02", "200"]]

    new_rows, converted = normalize_eu_decimal_columns(headers, rows)

    assert converted == []
    assert new_rows == rows
