from fastapi.testclient import TestClient

from app.main import app


def _client():
    return TestClient(app)


def test_health_uses_unified_body():
    with _client() as client:
        res = client.get("/health")
    assert res.status_code == 200
    body = res.json()
    assert body["code"] == 200
    assert body["msg"] == "ok"
    assert body["data"]["status"] == "ok"
    assert body["data"]["app"]


def test_validation_error_uses_unified_body():
    with _client() as client:
        res = client.post("/api/analyze", json={})
    assert res.status_code == 422
    body = res.json()
    assert body["code"] == 422
    assert body["data"] is None
    assert "url" in body["msg"]
    assert "detail" not in body


def test_missing_task_uses_unified_body():
    with _client() as client:
        res = client.get("/api/tasks/missing-task")
    assert res.status_code == 404
    body = res.json()
    assert body["code"] == 404
    assert body["msg"] == "任务不存在或已过期"
    assert body["data"] is None


def test_unknown_route_uses_unified_body():
    with _client() as client:
        res = client.get("/no-such-route")
    assert res.status_code == 404
    body = res.json()
    assert set(body) == {"code", "msg", "data"}
    assert body["code"] == 404
    assert body["data"] is None


def test_delete_task_uses_unified_body():
    with _client() as client:
        res = client.delete("/api/tasks/missing-task")
    assert res.status_code == 200
    body = res.json()
    assert body == {"code": 200, "msg": "ok", "data": {"ok": True}}


def test_export_bad_format_uses_unified_body():
    with _client() as client:
        res = client.post("/api/export", json={"title": "书", "format": "xml", "chapters": []})
    assert res.status_code == 400
    body = res.json()
    assert body["code"] == 400
    assert body["data"] is None
    assert "format" in body["msg"]


def test_export_txt_stays_a_file():
    with _client() as client:
        res = client.post(
            "/api/export",
            json={
                "title": "书名",
                "format": "txt",
                "chapters": [{
                    "order": 1,
                    "title": "第一章",
                    "url": "https://example.com/1",
                    "content": "正文",
                }],
            },
        )
    assert res.status_code == 200
    disposition = res.headers["content-disposition"]
    assert disposition.startswith("attachment;")
    assert "filename*=UTF-8''" in disposition
    assert "第一章" in res.text


def test_request_and_response_fields_are_camel_case(monkeypatch):
    seen: list[bool] = []

    async def fake_analyze(url, use_playwright=False):
        seen.append(use_playwright)
        return {
            "url": url,
            "container_selector": "#list",
            "item_selector": "a",
            "next_url": None,
            "next_text": None,
            "confidence": 1.0,
            "sample_chapters": [{"title": "第一章", "url": "https://example.com/1.html"}],
        }

    monkeypatch.setattr("app.api.analyze.analyze", fake_analyze)
    with _client() as client:
        camel = client.post(
            "/api/analyze",
            json={"url": "https://example.com/book/1/", "usePlaywright": False},
        )
        snake = client.post(
            "/api/analyze",
            json={"url": "https://example.com/book/1/", "use_playwright": True},
        )
    assert seen == [False, True]
    for res in (camel, snake):
        assert res.status_code == 200
        data = res.json()["data"]
        assert data["containerSelector"] == "#list"
        assert data["itemSelector"] == "a"
        assert data["sampleChapters"][0]["title"] == "第一章"
        assert "container_selector" not in data
        assert "sample_chapters" not in data

    schema = app.openapi()
    fields = schema["components"]["schemas"]["AnalyzeResponse"]["properties"]
    assert "containerSelector" in fields
    assert "container_selector" not in fields
    params = schema["paths"]["/api/tasks/{task_id}/chapters"]["get"]["parameters"]
    assert "withContent" in {item["name"] for item in params}


def test_openapi_success_and_validation_share_fields():
    schema = app.openapi()
    analyze = schema["paths"]["/api/analyze"]["post"]
    ok_ref = analyze["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
    ok_name = ok_ref.rsplit("/", 1)[-1]
    ok_schema = schema["components"]["schemas"][ok_name]
    assert set(ok_schema["properties"]) == {"code", "msg", "data"}
    assert set(ok_schema["required"]) == {"code", "msg", "data"}

    err = analyze["responses"]["422"]["content"]["application/json"]["schema"]
    assert set(err["properties"]) == {"code", "msg", "data"}
    assert "HTTPValidationError" not in schema["components"]["schemas"]
