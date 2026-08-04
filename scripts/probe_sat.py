import httpx

sat = "https://sgrportal.gestionderiesgos.gob.ec/server/rest/services/SAT/MapServer/0"
with httpx.Client(
    timeout=40.0, headers={"User-Agent": "ecuador-mcp/0.3.2"}, follow_redirects=True
) as client:
    meta = client.get(sat, params={"f": "pjson"})
    print("meta", meta.status_code)
    print(meta.text[:2500])
    q = client.get(
        sat + "/query",
        params={
            "where": "1=1",
            "outFields": "*",
            "returnGeometry": "true",
            "f": "json",
            "resultRecordCount": 5,
        },
    )
    print("query", q.status_code)
    print(q.text[:3000])
