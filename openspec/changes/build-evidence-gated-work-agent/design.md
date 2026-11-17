# Design: Evidence-Gated Work Agent

## Context

두 기준 저장소는 각각 승인·실행(AI WorkPilot)과 근거 검증·보류(Procurement RAG)를 증명했지만, **근거가 계획 생성을 통제하는 결합부**는 별도로 구현되지 않았다. 이 change는 그 결합부를 최소 스택으로 구현한다.

## Goals

- 근거 부족/상충이면 `plans`/`approvals`/`executions` 0행.
- 승인 전 실행은 API 409.
- 승인 후에도 허용된 mock action만 실행.
- 같은 idempotency key는 중복 실행하지 않고, 실패는 1회만 자동 재시도.
- 모든 상태 변화와 거부를 감사에 남기고, 재시작 후에도 plan hash가 동일.

## Decisions

### D1. GatePass 타입으로 게이트 우회 차단

- `GatePass`는 module-private sentinel을 가진 frozen dataclass.
- `EvidenceGate.make_pass()`만 생성 가능.
- `Planner.build_plan()`은 `GatePass`를 요구한다.

**대안:** 라우트에서 `if gate.passed` 검사 — 호출 경로가 늘면 우회 가능. 기각.

### D2. 절대 점수 + 조사 제거 + bigram

- min-max 정규화는 얇은 코퍼스에서 모든 후보를 1.0으로 만든다.
- `score = 0.85*IDF coverage + 0.15*BM25 signal`.
- 한국어 조사 제거, 음절 bigram, 단일 음절 토큰 제외.
- 16질의 micro-ablation에서 Recall@3 0.861 → 1.000.

**대안:** 임베딩 검색 — 모델 다운로드·캐시·GPU 비용, 오프라인 재현성 저하. 비목표.

### D3. 계획 hash canonicalization

- NFC, sorted keys, compact separators, float 6자리, 타임스탬프 제외.
- payload에 `evidence_fingerprint`, `gate_config_hash`, `corpus_sha256` 포함.
- `hash_scheme="egwa-plan-v1"`.

**대안:** JSON 원문 hash — dict 순서/로케일/재시작에 취약. 기각.

### D4. 상태 머신 + CAS

- `DRAFT → RETRIEVING → EVIDENCE_INSUFFICIENT | PENDING_APPROVAL`
- `PENDING_APPROVAL → APPROVED | REJECTED`
- `APPROVED → EXECUTING → EXECUTED | FAILED`
- `FAILED → RETRYING → EXECUTED | FAILED`
- 전이표는 한 곳, `UPDATE ... WHERE status=?` CAS.

### D5. Idempotency와 재시도

- 검사 순서: key 형식 → run 404 → 기존 이력 → 상태 CAS → hash/근거 재검증 → 실행.
- `UNIQUE(run_id, idempotency_key, attempt)`.
- attempt는 서버가 1..2로 산출.
- 같은 key 완료 → 200 cached, 다른 key → 409, 소진 → 409.

### D6. 감사

- `UNIQUE(run_id, seq)`, `MAX+1`, append-only trigger, hash chain.
- 거부 요청도 `DENIED_*`로 기록하되 run당 20건 상한.
- hash chain은 tamper-evident 보조이며 tamper-proof 아님.

### D7. SQLite

- 호출별 연결, `foreign_keys=ON`, `busy_timeout=5000`, `synchronous=NORMAL`, WAL.
- 상태 검사·변경·감사는 `BEGIN IMMEDIATE` 단일 트랜잭션.
- `schema_meta` 불일치 시 기동 실패. `RETRIEVING`은 영속하지 않는다.

### D8. Public vs synthetic

- 공개 요약 10건은 `law.go.kr`만 허용.
- 합성 fixture 4건은 `example.com`만 허용하고 최소 인용 수에서 제외.
- UI/문서에 배지와 한계 고지.

## Migration Plan

- 새 저장소이므로 데이터 마이그레이션 없음.
- `schema_version=1`; 이후 변경은 `schema_meta`와 명시적 migration으로 처리.

## Risks / Trade-offs

- 공개 요약은 원문 최신성을 보장하지 않는다.
- 상충은 태그된 metadata에 한정된다.
- 인증이 없어 실제 승인 권한을 증명하지 않는다.
- SQLite는 공개 호스팅에서 소실될 수 있다.
- 14문서/16질의 평가는 성능 벤치마크가 아니다.

## Open Questions

- 실제 운영 전 OIDC/세션·CSRF·권한 분리 도입 시점
- Postgres 전환과 감사 보존 기간
- 공개 RFP 코퍼스 확장 시 이용 조건 검사기
- LLM/RAG 품질 평가를 별도 change로 분리할지
