import pytest

from helpers import anda_client


@pytest.mark.asyncio
async def test_search_catalog(httpx_mock):
    httpx_mock.add_response(
        url="https://anda.inec.gob.ec/anda5/index.php/api/catalog?ps=10&sk=empleo",
        json={
            "result": {
                "found": "1",
                "rows": [
                    {
                        "id": "1319",
                        "idno": "ECU-INEC-EMPLEO-2025",
                        "title": "Encuesta de Empleo 2025",
                        "year_start": "2025",
                        "authoring_entity": "INEC",
                        "form_model": "direct",
                        "url": "https://anda.inec.gob.ec/anda5/index.php/catalog/1319",
                    }
                ],
            }
        },
    )
    result = await anda_client.search_catalog(query="empleo", limit=10)
    assert result["found"] == "1"
    assert result["rows"][0]["idno"] == "ECU-INEC-EMPLEO-2025"


@pytest.mark.asyncio
async def test_search_catalog_no_query(httpx_mock):
    httpx_mock.add_response(
        url="https://anda.inec.gob.ec/anda5/index.php/api/catalog?ps=5",
        json={"result": {"found": "437", "rows": []}},
    )
    result = await anda_client.search_catalog(limit=5)
    assert result["found"] == "437"


def test_has_microdata_direct():
    assert anda_client.has_microdata({"form_model": "direct"}) is True


def test_has_microdata_aggregate_only():
    assert anda_client.has_microdata({"form_model": "data_na"}) is False


def test_has_microdata_from_detail_field():
    assert anda_client.has_microdata({"data_access_type": "direct"}) is True
    assert anda_client.has_microdata({"data_access_type": "data_na"}) is False


def test_has_microdata_defaults_false_when_fields_missing():
    assert anda_client.has_microdata({}) is False


@pytest.mark.asyncio
async def test_get_survey(httpx_mock):
    httpx_mock.add_response(
        url="https://anda.inec.gob.ec/anda5/index.php/api/catalog/ECU-INEC-EMPLEO-2025",
        json={
            "status": "success",
            "dataset": {
                "id": "1319",
                "idno": "ECU-INEC-EMPLEO-2025",
                "title": "Encuesta de Empleo 2025",
                "data_access_type": "direct",
                "varcount": "150",
            },
        },
    )
    dataset = await anda_client.get_survey("ECU-INEC-EMPLEO-2025")
    assert dataset["id"] == "1319"
    assert dataset["varcount"] == "150"


@pytest.mark.asyncio
async def test_get_survey_not_found(httpx_mock):
    base = "https://anda.inec.gob.ec/anda5/index.php/api/catalog"
    httpx_mock.add_response(
        url=f"{base}/NOPE",
        status_code=400,
        json={"status": "failed", "message": "IDNO-NOT-FOUND"},
    )
    # The id fallback looks for the idno (search, then a whole-catalog scan)
    # before giving up; neither finds it.
    httpx_mock.add_response(
        url=f"{base}?ps=100&sk=NOPE", json={"result": {"found": "0", "rows": []}}
    )
    httpx_mock.add_response(
        url=f"{base}?ps=100",
        json={"result": {"found": "1", "rows": [{"id": "7", "idno": "OTHER"}]}},
    )
    with pytest.raises(ValueError, match="No se encontró"):
        await anda_client.get_survey("NOPE")


@pytest.mark.asyncio
async def test_get_survey_falls_back_to_the_catalog_id_when_the_idno_route_misses(
    httpx_mock,
):
    # Live ANDA answers IDNO-NOT-FOUND for some idnos with spaces in every
    # encoding, while the same study answers by its numeric id.
    base = "https://anda.inec.gob.ec/anda5/index.php/api/catalog"
    idno = "ECU-INEC-DIES-ENEMDU JUNIO 2011 RONDA XXXII - 2012 - v1.0"
    httpx_mock.add_response(
        url=f"{base}/{idno.replace(' ', '%20')}",
        status_code=400,
        json={"status": "failed", "message": "IDNO-NOT-FOUND"},
    )
    httpx_mock.add_response(
        url=f"{base}?ps=100&sk={idno.replace(' ', '%20')}",
        json={
            "result": {
                "found": "2",
                "rows": [
                    {"id": "101", "idno": "ECU-INEC-DIES-ENEMDU JUNIO 2011 - v1.0"},
                    {"id": "102", "idno": idno},
                ],
            }
        },
    )
    httpx_mock.add_response(
        url=f"{base}/102?id_format=id",
        json={"status": "success", "dataset": {"id": "102", "idno": idno}},
    )

    dataset = await anda_client.get_survey(idno)

    assert dataset["id"] == "102"
    assert dataset["idno"] == idno


@pytest.mark.asyncio
async def test_get_survey_scans_the_whole_catalog_when_the_search_misses(httpx_mock):
    base = "https://anda.inec.gob.ec/anda5/index.php/api/catalog"
    httpx_mock.add_response(
        url=f"{base}/A%20B", status_code=400, json={"status": "failed", "message": "IDNO-NOT-FOUND"}
    )
    httpx_mock.add_response(
        url=f"{base}?ps=100&sk=A%20B", json={"result": {"found": "0", "rows": []}}
    )
    httpx_mock.add_response(
        url=f"{base}?ps=100",
        json={"result": {"found": "2", "rows": [{"id": "1", "idno": "C"}, {"id": "9", "idno": "a b"}]}},
    )
    httpx_mock.add_response(
        url=f"{base}/9?id_format=id", json={"status": "success", "dataset": {"id": "9"}}
    )

    # The idno match ignores case and surrounding whitespace.
    dataset = await anda_client.get_survey(" A B ")

    assert dataset["id"] == "9"


@pytest.mark.asyncio
async def test_get_survey_numeric_id_not_found_does_not_search(httpx_mock):
    httpx_mock.add_response(
        url="https://anda.inec.gob.ec/anda5/index.php/api/catalog/999?id_format=id",
        status_code=400,
        json={"status": "failed", "message": "IDNO-NOT-FOUND"},
    )

    with pytest.raises(ValueError, match="No se encontró"):
        await anda_client.get_survey("999")


@pytest.mark.asyncio
async def test_list_microdata_files(httpx_mock):
    get_microdata_url = "https://anda.inec.gob.ec/anda5/index.php/catalog/1153/get-microdata"
    httpx_mock.add_response(
        method="GET",
        url=get_microdata_url,
        html='<form><input type="hidden" name="ncsrf" value="abc123def456" /></form>',
    )
    httpx_mock.add_response(
        method="POST",
        url=get_microdata_url,
        html=(
            '<a href="https://anda.inec.gob.ec/anda5/index.php/catalog/1153/download/1" '
            'title="archivo_a.zip">a</a>'
            '<a href="https://anda.inec.gob.ec/anda5/index.php/catalog/1153/download/2" '
            'title="archivo_b.zip">b</a>'
        ),
    )
    files = await anda_client.list_microdata_files("1153")
    assert files == [
        {
            "filename": "archivo_a.zip",
            "url": "https://anda.inec.gob.ec/anda5/index.php/catalog/1153/download/1",
        },
        {
            "filename": "archivo_b.zip",
            "url": "https://anda.inec.gob.ec/anda5/index.php/catalog/1153/download/2",
        },
    ]


@pytest.mark.asyncio
async def test_list_microdata_files_no_csrf_token(httpx_mock):
    httpx_mock.add_response(
        method="GET",
        url="https://anda.inec.gob.ec/anda5/index.php/catalog/1/get-microdata",
        html="<p>no form here</p>",
    )
    # A blocked or redesigned page must not read as "this survey has no files".
    with pytest.raises(ValueError, match="token CSRF"):
        await anda_client.list_microdata_files("1")


@pytest.mark.asyncio
async def test_get_survey_by_numeric_id_uses_id_format(httpx_mock):
    httpx_mock.add_response(
        url="https://anda.inec.gob.ec/anda5/index.php/api/catalog/190?id_format=id",
        json={"status": "success", "dataset": {"id": "190", "idno": "A B"}},
    )
    dataset = await anda_client.get_survey("190")
    assert dataset["id"] == "190"


@pytest.mark.asyncio
async def test_get_survey_url_encodes_idno_with_spaces(httpx_mock):
    httpx_mock.add_response(
        url="https://anda.inec.gob.ec/anda5/index.php/api/catalog/ECU%20DEF%202007",
        json={"status": "success", "dataset": {"id": "190"}},
    )
    dataset = await anda_client.get_survey("ECU DEF 2007")
    assert dataset["id"] == "190"


@pytest.mark.asyncio
async def test_search_catalog_all_pages_until_found(httpx_mock):
    base = "https://anda.inec.gob.ec/anda5/index.php/api/catalog"
    httpx_mock.add_response(
        url=f"{base}?ps=100&sk=x",
        json={"result": {"found": "3", "rows": [{"id": "1"}, {"id": "2"}]}},
    )
    httpx_mock.add_response(
        url=f"{base}?ps=100&page=2&sk=x",
        json={"result": {"found": "3", "rows": [{"id": "3"}]}},
    )
    rows = await anda_client.search_catalog_all("x")
    assert [r["id"] for r in rows] == ["1", "2", "3"]
