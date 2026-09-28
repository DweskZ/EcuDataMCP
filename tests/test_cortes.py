"""search_cortes/get_cortes_horarios route EEQ and Centrosur by distribuidora."""

from tools import cortes


async def test_search_exposes_each_utilitys_file_id_as_archivo(monkeypatch):
    async def fake_eeq(query=""):
        return {"total": 1, "archivos": [{"slug": "22-abril", "url": "https://eeq/22-abril.pdf"}]}

    async def fake_centrosur(query=""):
        return {"total": 1, "archivos": [{"titulo": "Cortes", "url": "https://centrosur/c.pdf"}]}

    monkeypatch.setattr(cortes.eeq_cortes_client, "search_eeq_cortes", fake_eeq)
    monkeypatch.setattr(cortes.centrosur_cortes_client, "search_centrosur_cortes", fake_centrosur)

    eeq = await cortes._search("eeq", "")
    centrosur = await cortes._search("centrosur", "")
    assert eeq["archivos"][0]["archivo"] == "22-abril"
    assert centrosur["archivos"][0]["archivo"] == "https://centrosur/c.pdf"


async def test_get_horarios_passes_archivo_to_the_right_client(monkeypatch):
    calls = []

    async def fake_eeq(slug, query=""):
        calls.append(("eeq", slug))
        return {"filas": []}

    async def fake_centrosur(url, query=""):
        calls.append(("centrosur", url))
        return {"filas": []}

    monkeypatch.setattr(cortes.eeq_cortes_client, "get_eeq_cortes_horarios", fake_eeq)
    monkeypatch.setattr(cortes.centrosur_cortes_client, "get_centrosur_cortes_horarios", fake_centrosur)

    await cortes._get_horarios("eeq", "22-abril", "")
    result = await cortes._get_horarios("centrosur", "https://centrosur/c.pdf", "")
    assert calls == [("eeq", "22-abril"), ("centrosur", "https://centrosur/c.pdf")]
    assert result["distribuidora"] == "centrosur"
