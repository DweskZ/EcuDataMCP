from helpers.bce_equivalence import build_equivalence_map


def test_build_equivalence_map_marks_label_matches_as_candidates():
    result = build_equivalence_map(
        {
            "grupos": [
                {
                    "id_grupo": 10,
                    "descripcion": "Producto Interno Bruto",
                    "nombre": "PIB",
                    "series": ["PIB total"],
                    "frecuencias": ["Anual"],
                    "unidades": {"Anual": ["Millones de USD"]},
                    "rango": {},
                    "bundle_ok": True,
                }
            ]
        },
        {
            "tablas": [
                {
                    "table_id": "iem-431-e",
                    "titulo": "Producto Interno Bruto (PIB)",
                    "seccion": "Cuentas nacionales",
                    "url": "https://example.test/iem-431-e.xlsx",
                    "boletin_numero": 2092,
                },
                {
                    "table_id": "iem-999-e",
                    "titulo": "Tema exclusivo del IEM",
                    "seccion": "Otro",
                },
            ]
        },
    )

    assert result["equivalencias_candidatas"][0]["iem"]["table_id"] == "iem-431-e"
    assert result["equivalencias_candidatas"][0]["relacion"]
    assert result["iem_solo_por_etiquetas"][0]["table_id"] == "iem-999-e"
