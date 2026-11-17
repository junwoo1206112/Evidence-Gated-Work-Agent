from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.templating import Jinja2Templates

from app.errors import AppError
from app.version import APP_NAME, APP_VERSION, DEMO_NOTICE, HONEST_FRAMING

router = APIRouter(tags=["pages"])
ROOT = Path(__file__).resolve().parents[2]


def _templates(request: Request) -> Jinja2Templates:
    return request.app.state.templates


@router.get("/", response_class=HTMLResponse)
def home(request: Request):
    return _templates(request).TemplateResponse(
        request,
        "index.html",
        {
            "run_id": "",
            "app_name": APP_NAME,
            "app_version": APP_VERSION,
            "demo_notice": DEMO_NOTICE,
            "honest_framing": HONEST_FRAMING,
        },
    )


@router.get("/runs/{run_id}", response_class=HTMLResponse)
def run_page(run_id: str, request: Request):
    try:
        request.app.state.service.get_run(run_id)
    except AppError as exc:
        if exc.status_code == 404:
            return _templates(request).TemplateResponse(
                request,
                "not_found.html",
                {"run_id": run_id, "app_name": APP_NAME, "app_version": APP_VERSION, "demo_notice": DEMO_NOTICE},
                status_code=404,
            )
        raise
    return _templates(request).TemplateResponse(
        request,
        "index.html",
        {
            "run_id": run_id,
            "app_name": APP_NAME,
            "app_version": APP_VERSION,
            "demo_notice": DEMO_NOTICE,
            "honest_framing": HONEST_FRAMING,
        },
    )


@router.get("/docs/verification", response_class=PlainTextResponse)
def verification_doc():
    path = ROOT / "docs" / "verification.md"
    return PlainTextResponse(path.read_text(encoding="utf-8"))


@router.get("/health")
def health(request: Request):
    db_health = request.app.state.db.health()
    corpus = request.app.state.corpus
    settings = request.app.state.settings
    healthy = bool(db_health.get("ok")) and len(corpus.documents) >= 5
    body = {
        "status": "ok" if healthy else "degraded",
        "app": APP_NAME,
        "version": APP_VERSION,
        "demo_notice": DEMO_NOTICE,
        "db": db_health,
        "corpus": {
            "version": corpus.version,
            "sha256": corpus.sha256,
            "documents": len(corpus.documents),
            "public_documents": len(corpus.public_documents),
        },
        "gate_config_hash": settings.gate_config_hash(),
        "llm_calls": False,
        "network_dependencies": False,
    }
    return JSONResponse(status_code=200 if healthy else 503, content=body)
