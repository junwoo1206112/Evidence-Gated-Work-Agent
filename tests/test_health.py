from __future__ import annotations

from app.version import APP_VERSION


def test_health_reports_corpus_and_db(client) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["version"] == APP_VERSION
    assert body["db"]["ok"] is True
    assert body["db"]["schema_version"] == "1"
    assert body["corpus"]["documents"] == 14
    assert body["corpus"]["public_documents"] == 10
    assert body["llm_calls"] is False
    assert body["network_dependencies"] is False
    assert response.headers["cache-control"] == "no-store"


def test_health_returns_503_when_db_check_fails(client, app) -> None:
    app.state.db.health = lambda: {"ok": False, "error": "forced"}
    response = client.get("/health")
    assert response.status_code == 503
    assert response.json()["status"] == "degraded"


def test_health_returns_503_when_schema_version_is_missing(client, service) -> None:
    with service.db.transaction() as connection:
        connection.execute("DELETE FROM schema_meta")
    response = client.get("/health")
    assert response.status_code == 503
    assert response.json()["db"]["ok"] is False
    assert response.json()["db"]["error"] == "schema_version_mismatch"


def test_security_headers_are_present(client) -> None:
    response = client.get("/")
    assert response.headers["content-security-policy"].startswith("default-src 'self'")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert "noindex" in response.headers["x-robots-tag"]


def test_openapi_is_available_but_interactive_docs_are_disabled(client) -> None:
    assert client.get("/docs").status_code == 404
    assert client.get("/redoc").status_code == 404
    spec = client.get("/api/openapi.json")
    assert spec.status_code == 200
    assert spec.json()["info"]["title"] == "Evidence-Gated Work Agent"


def test_static_files_are_served_with_security_headers(client) -> None:
    css = client.get("/static/styles.css")
    assert css.status_code == 200
    assert css.headers["x-content-type-options"] == "nosniff"
    js = client.get("/static/app.js")
    assert js.status_code == 200


def test_verification_doc_is_served(client) -> None:
    response = client.get("/docs/verification")
    assert response.status_code == 200
    assert "156 passed" in response.text
    assert "Docker E2E" in response.text
