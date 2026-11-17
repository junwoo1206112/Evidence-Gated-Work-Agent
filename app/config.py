from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable

from app.textutil import canonical_json, sha256_text


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class Settings:
    """Runtime settings.

    The object is immutable so the gate configuration hash stays stable for the
    lifetime of an application instance. Tests replace it with a deterministic
    clock and a temporary database.
    """

    db_path: Path
    corpus_path: Path
    min_valid_citations: int = 2
    min_public_citations: int = 2
    min_citation_score: float = 0.42
    conflict_scan_floor: float = 0.30
    min_excerpt_chars: int = 40
    max_request_chars: int = 500
    top_k: int = 5
    max_attempts: int = 2
    rate_limit_per_minute: int = 60
    trust_proxy_headers: bool = False
    max_body_bytes: int = 8192
    demo_reviewer: str = "demo-reviewer"
    allowed_hosts: tuple[str, ...] = ("law.go.kr", "www.law.go.kr", "example.com")
    clock: Callable[[], datetime] = field(default=utc_now, repr=False, compare=False)

    def now(self) -> datetime:
        value = self.clock()
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def today(self) -> date:
        return self.now().date()

    def gate_config_payload(self) -> dict:
        return {
            "min_valid_citations": self.min_valid_citations,
            "min_public_citations": self.min_public_citations,
            "min_citation_score": round(float(self.min_citation_score), 6),
            "conflict_scan_floor": round(float(self.conflict_scan_floor), 6),
            "min_excerpt_chars": self.min_excerpt_chars,
            "allowed_hosts": sorted(self.allowed_hosts),
            "top_k": self.top_k,
            "max_request_chars": self.max_request_chars,
            "max_attempts": self.max_attempts,
        }

    def gate_config_hash(self) -> str:
        return sha256_text(canonical_json(self.gate_config_payload()))

    def with_clock(self, clock: Callable[[], datetime]) -> "Settings":
        return replace(self, clock=clock)

    @classmethod
    def from_env(cls) -> "Settings":
        root = Path(__file__).resolve().parents[1]
        db_path = Path(os.environ.get("EGWA_DB_PATH", str(root / "data" / "evidence_gated.db")))
        corpus_path = Path(
            os.environ.get("EGWA_CORPUS_PATH", str(root / "data" / "public_corpus" / "documents.json"))
        )
        return cls(
            db_path=db_path,
            corpus_path=corpus_path,
            min_citation_score=float(os.environ.get("EGWA_MIN_SCORE", "0.42")),
            rate_limit_per_minute=int(os.environ.get("EGWA_RATE_LIMIT", "60")),
            trust_proxy_headers=os.environ.get("EGWA_TRUST_PROXY", "0").lower() in {"1", "true", "yes"},
            demo_reviewer=os.environ.get("EGWA_REVIEWER", "demo-reviewer"),
        )
