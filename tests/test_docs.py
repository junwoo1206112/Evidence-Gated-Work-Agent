from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def text(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_readme_contains_honest_framing_and_evidence() -> None:
    readme = text("README.md")
    assert "LLM 없이 결정론적으로 동작하는" in readme
    assert "실제 조달" in readme
    assert "151 passed" in readme
    assert "14/14" in readme
    assert "SQLite" in readme
    assert "소실" in readme or "ephemeral" in readme


def test_sources_hash_matches_corpus_file() -> None:
    sources = text("data/public_corpus/SOURCES.md")
    digest = hashlib.sha256((ROOT / "data/public_corpus/documents.json").read_bytes()).hexdigest()
    assert digest in sources
    assert "합성 fixture" in sources
    assert "저작권법 제7조" in sources


def test_source_map_records_license_check() -> None:
    source_map = text("docs/source-map.md")
    assert "LICENSE" in source_map
    assert "복사하지 않았다" in source_map
    assert "AI-WorkPilot" in source_map
    assert "procurement-rules-rag-copilot" in source_map


def test_interview_ledger_records_experts() -> None:
    ledger = text("docs/interview-decisions.md")
    for expert in ["전문가 A", "전문가 B", "전문가 C"]:
        assert expert in ledger
    assert "GatePass" in ledger
    assert "Restate Gate" in ledger
    assert "151" in ledger


def test_architecture_documents_invariants() -> None:
    architecture = text("docs/architecture.md")
    for phrase in ["BEGIN IMMEDIATE", "E_EVIDENCE_STALE", "GatePass", "hash chain", "ephemeral"]:
        assert phrase in architecture, phrase


def test_retrieval_docs_include_ablation() -> None:
    from scripts.ablation import QUERIES

    retrieval = text("docs/retrieval.md")
    ablation = text("docs/retrieval-ablation.md")
    assert "Recall@3" in retrieval
    assert "0.861" in retrieval
    assert "Recall@3" in ablation
    assert f"{len(QUERIES)}개" in ablation
    assert f"({len(QUERIES)} 질의)" in retrieval


def test_openspec_artifacts_exist() -> None:
    base = ROOT / "openspec" / "changes" / "build-evidence-gated-work-agent"
    for relative in [
        "proposal.md",
        "design.md",
        "tasks.md",
        "specs/evidence-gated-workflow/spec.md",
        "specs/deterministic-retrieval/spec.md",
        "specs/auditable-execution/spec.md",
    ]:
        assert (base / relative).exists(), relative
    proposal = text("openspec/changes/build-evidence-gated-work-agent/proposal.md")
    assert "Non-goals" in proposal
    assert "SHALL" in text("openspec/changes/build-evidence-gated-work-agent/specs/evidence-gated-workflow/spec.md")


def test_eval_results_are_current() -> None:
    results = json.loads(text("evals/results.json"))
    digest = hashlib.sha256((ROOT / "data/public_corpus/documents.json").read_bytes()).hexdigest()
    assert results["corpus_sha256"] == digest
    assert results["summary"]["all_passed"] is True
    assert results["summary"]["total"] == 14


def test_no_secret_material_in_public_files() -> None:
    patterns = [
        re.compile(r"sk-[A-Za-z0-9]{20,}"),
        re.compile(r"AKIA[0-9A-Z]{16}"),
        re.compile(r"BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY"),
        re.compile(r"LAW_API_OC\s*="),
        re.compile(r"api[_-]?key\s*=\s*[\"'][^\"']+[\"']", re.IGNORECASE),
    ]
    roots = ["app", "docs", "evals", "scripts", "tests", "data", "openspec"]
    files = [ROOT / "README.md", ROOT / "Dockerfile", ROOT / "render.yaml"]
    for folder in roots:
        files.extend((ROOT / folder).rglob("*"))
    for path in files:
        if not path.is_file() or path.suffix not in {".py", ".md", ".json", ".js", ".css", ".yaml", ".yml", ".html"}:
            continue
        if "results.json" in path.name:
            continue
        content = path.read_text(encoding="utf-8", errors="ignore")
        for pattern in patterns:
            assert not pattern.search(content), f"potential secret in {path}"
