from __future__ import annotations

from app.config import Settings


def test_gate_config_hash_is_stable() -> None:
    first = Settings(db_path=__import__("pathlib").Path("x.db"), corpus_path=__import__("pathlib").Path("corpus.json"))
    second = Settings(db_path=__import__("pathlib").Path("y.db"), corpus_path=__import__("pathlib").Path("other.json"))
    assert first.gate_config_hash() == second.gate_config_hash()
    assert len(first.gate_config_hash()) == 64


def test_env_defaults_match_demo_threshold(monkeypatch) -> None:
    for key in [
        "EGWA_MIN_SCORE",
        "EGWA_RATE_LIMIT",
        "EGWA_REVIEWER",
        "EGWA_DB_PATH",
        "EGWA_CORPUS_PATH",
        "EGWA_TRUST_PROXY",
    ]:
        monkeypatch.delenv(key, raising=False)
    settings = Settings.from_env()
    assert settings.min_citation_score == 0.42
    assert settings.min_valid_citations == 2
    assert settings.min_public_citations == 2
    assert settings.max_attempts == 2
    assert "law.go.kr" in settings.allowed_hosts
    assert "example.com" in settings.allowed_hosts
