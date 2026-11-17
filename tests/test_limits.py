from __future__ import annotations

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from tests.conftest import CORPUS_PATH, SUFFICIENT_REQUEST


def make_client(tmp_path, **overrides):
    settings = Settings(
        db_path=tmp_path / "limits.db",
        corpus_path=CORPUS_PATH,
        **overrides,
    )
    app = create_app(settings)
    return TestClient(app)


def test_rate_limit_returns_429_with_retry_after(tmp_path) -> None:
    with make_client(tmp_path, rate_limit_per_minute=1) as client:
        first = client.get("/api/runs/run_missing")
        assert first.status_code == 404
        second = client.get("/api/runs/run_missing")
        assert second.status_code == 429
        assert second.json()["error"]["code"] == "E_RATE_LIMITED"
        assert int(second.headers["retry-after"]) >= 1


def test_proxy_header_rate_limit_uses_forwarded_client(tmp_path) -> None:
    with make_client(tmp_path, rate_limit_per_minute=1, trust_proxy_headers=True) as client:
        # The right-most address is the trusted proxy. Clients sharing that
        # proxy must still receive separate rate-limit buckets.
        headers_a = {"X-Forwarded-For": "198.51.100.10, 203.0.113.5"}
        headers_b = {"X-Forwarded-For": "198.51.100.20, 203.0.113.5"}
        assert client.get("/api/runs/run_missing", headers=headers_a).status_code == 404
        assert client.get("/api/runs/run_missing", headers=headers_a).status_code == 429
        # A different forwarded client must get its own bucket.
        assert client.get("/api/runs/run_missing", headers=headers_b).status_code == 404


def test_body_size_limit_rejects_large_content_length(tmp_path) -> None:
    with make_client(tmp_path, rate_limit_per_minute=0, max_body_bytes=50) as client:
        response = client.post(
            "/api/runs",
            json={"request": SUFFICIENT_REQUEST, "demo_mode": "none"},
        )
        assert response.status_code == 413
        assert response.json()["error"]["code"] == "E_BODY_TOO_LARGE"


def test_body_size_limit_counts_chunked_body_without_content_length() -> None:
    import asyncio

    from app.main import BodySizeLimitMiddleware

    async def app(scope, receive, send):
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                break
            if not message.get("more_body", False):
                break
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-type", b"text/plain")],
            }
        )
        await send({"type": "http.response.body", "body": b"ok"})

    middleware = BodySizeLimitMiddleware(app, max_bytes=50)
    chunks = [b"a" * 40, b"b" * 40]
    index = 0

    async def receive():
        nonlocal index
        if index >= len(chunks):
            return {"type": "http.disconnect"}
        body = chunks[index]
        index += 1
        return {"type": "http.request", "body": body, "more_body": index < len(chunks)}

    sent = []

    async def send(message):
        sent.append(message)

    scope = {
        "type": "http",
        "method": "POST",
        "headers": [],  # no Content-Length
        "path": "/api/runs",
    }
    asyncio.run(middleware(scope, receive, send))
    assert sent[0]["type"] == "http.response.start"
    assert sent[0]["status"] == 413
    assert b"E_BODY_TOO_LARGE" in sent[1]["body"]
