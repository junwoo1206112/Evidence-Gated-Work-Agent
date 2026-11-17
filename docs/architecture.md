# 아키텍처와 정책 불변조건

## 1. 데이터 흐름

```text
POST /api/runs
  └─ WorkflowService.create_run
       ├─ validate_request (길이·민감정보·지시 우회)
       ├─ Retriever.search (결정론, 네트워크 없음)
       ├─ EvidenceGate.evaluate (순수 정책)
       │    ├─ 실패 → GateResult(passed=False)
       │    └─ 통과 → GatePass(frozen, private seal)
       ├─ Planner.build_plan(GatePass) (제한 JSON + canonical hash)
       └─ 단일 TX: run/evidence/plan/audit + 상태 전이
```

승인·실행은 **재검색하지 않는다**. 생성 시 저장한 `evidence.snapshot_json`과 `runs.evidence_fingerprint`만 재검증한다. 코퍼스·설정이 바뀌면 hash 비교에서 409로 차단한다.

## 2. 상태 머신

```text
DRAFT
  → RETRIEVING
      → EVIDENCE_INSUFFICIENT        (terminal, 계획 없음)
      → PENDING_APPROVAL
            → REJECTED               (terminal)
            → APPROVED
                  → EXECUTING
                        → EXECUTED   (terminal)
                        → FAILED
                              → RETRYING
                                    → EXECUTED (terminal)
                                    → FAILED   (terminal)
```

- 전이표는 `app/domain/state.py`의 `TRANSITIONS` 하나뿐이다. 라우트나 UI는 상태를 직접 쓰지 않는다.
- `EXECUTING`은 설계서 원안에 없지만, 동시 실행과 크래시 복구를 표현하기 위해 추가했다.
- `FAILED`는 attempt 1 실패 직후에는 `RETRYING`으로 이어지고, attempt 2까지 실패하면 terminal로 남는다.
- `reconcile_stale_runs()`는 시작 시 5분 이상 `EXECUTING`/`RETRYING`에 머문 run을 `FAILED`로 종결하고 `RECONCILED_INTERRUPTED` 감사를 남긴다.
- 검색은 요청 트랜잭션 전에 수행하므로 `RETRIEVING`은 영속 상태로 오래 남지 않는다. 감사에는 `DRAFT→RETRIEVING` 전이가 남는다.

## 3. Evidence Gate

### 3.1 후보 판정

각 후보는 아래를 모두 통과해야 `citation_valid=true`다.

| 검사 | 규칙 | 실패 코드 |
|---|---|---|
| 점수 | `score >= 0.42` (절대값) | `below_min_score` |
| URL | `https`, 허용 호스트, credentials/IP/비기본 포트 금지 | `missing_source_url`, `url_*` |
| 발췌 | NFC·공백 정규화, 40자 이상, 말줄임표 금지, 본문 부분일치 | `excerpt_*` |
| 유효기간 | `effective_from <= as_of <= effective_to` | `not_yet_effective`, `superseded` |
| 등급 | `public_summary` 또는 `synthetic_fixture` | `invalid_source_tier` |
| 정책 메타 | `policy_key`가 있으면 `scope`/`value` 필수 | `invalid_policy_metadata` |
| 중복 | 같은 `document_id`는 1회만 | `duplicate_document` |

### 3.2 통과 조건

1. **공개 문서** 유효 인용이 2개 이상 (`min_valid_citations`, `min_public_citations`).
   - 합성 fixture는 유효해도 최소 인용 수에 포함하지 않는다.
   - `UNIQUE(run_id, document_id)`로 같은 문서의 중복 카운트를 막는다.
2. 상충이 없어야 한다.
3. `category=None`이어야 한다.

### 3.3 상충

- 상충 비교는 `policy_key`/`policy_scope`/`policy_value`가 태그된 문서에만 적용한다.
- 같은 `(policy_key, policy_scope)`에서 `normalize_policy_value`가 다른 값이 2개 이상이면 `category="conflict"`.
- `10%`와 `100분의 10`은 같은 값으로 정규화한다.
- 상충 스캔은 **검색에서 정책 키가 드러난 경우 코퍼스 전체**를 대상으로 한다. 점수 하한(기본 0.30) 이상으로 검색된 tagged 후보가 트리거이며, 비교 대상은 점수와 무관하게 URL·발췌·유효기간이 구조적으로 유효한 문서다. 이로써 top-k/점수 미달로 상충 문서가 숨는 경로를 막는다.
- **한계:** 태그되지 않은 문서의 의미적 모순은 탐지하지 않는다. `scope` 계층(문서<기관<공고)과 precedence는 구현하지 않았다.

### 3.4 점수

```text
coverage = Σ IDF(matched query term) / Σ IDF(all query terms)
bm25_signal = min(1, BM25 / 12)
score = 0.85 * coverage + 0.15 * bm25_signal
```

- min-max 정규화를 사용하지 않는다. 코퍼스가 작아도 모든 후보가 1.0이 되지 않는다.
- 한국어 조사는 제거하고, BM25는 음절 bigram을 포함한다.
- 단일 음절 문서 토큰이 긴 질의어에 포함되는 오탐을 막는다.
- 상세와 ablation은 `docs/retrieval.md`.

## 4. GatePass와 Planner

```python
@dataclass(frozen=True)
class GatePass:
    run_id: str
    document_ids: tuple[str, ...]
    evidence_fingerprint: str
    config_hash: str
    corpus_sha256: str
    as_of: str
    _seal: object  # module-private sentinel
```

- `GatePass`는 module-private sentinel을 가진 frozen dataclass이며, 생성 함수도 `_make_gate_pass`로 비공개 처리했다. `EvidenceGate.make_pass()`만 정상 경로다. 라우트·플래너가 게이트를 건너뛰는 사고를 막는 **타입 수준의 방어**이며, Python 런타임의 완전한 capability 보안 경계는 아니다.
- `Planner.build_plan()`은 `isinstance(gate_pass, GatePass)`를 확인한다. 라우트가 planner를 직접 호출해 게이트를 우회할 수 없다.
- 계획은 `steps`, `required_evidence_ids`, `risk_level`, `allowed_action`, `simulation`, `limits`, `gate`만 포함한다. 자유 텍스트 필드는 `goal`/`summary`로 제한한다.
- `allowed_action`은 `create_demo_draft` 또는 `simulate_notification`만 허용한다.
- `simulation.max_attempts`는 설정값(기본 2, 최대 2)을 따르며, `max_attempts=1`이면 자동 재시도 없이 1차 실패로 종결한다.

## 5. Plan hash

```text
plan_hash = sha256(canonical_json(plan_payload))
canonical_json = NFC + sorted keys + compact separators + UTF-8 + float 6자리
```

- 타임스탬프를 포함하지 않아 재시작·다른 프로세스에서도 동일하다.
- `evidence_fingerprint`, `gate_config_hash`, `corpus_sha256`을 payload에 포함해 근거·설정·코퍼스 교체를 탐지한다.
- `hash_scheme="egwa-plan-v1"`로 향후 마이그레이션 여지를 남긴다.
- 승인 시 `approvals.plan_hash`에 결속하고, 실행 시 `plans.plan_json`을 재해시해 `plans.plan_hash`·`approvals.plan_hash`와 비교한다. 하나라도 다르면 `E_PLAN_HASH_MISMATCH`.
- 생성 시 `PLAN_CREATED` 감사 이벤트의 payload에도 `plan_hash`를 앵커로 남긴다. 승인·실행은 **감사 hash chain이 유효하고 앵커 hash가 현재 계획 hash와 일치**해야 진행한다. `plans.plan_json`과 `plans.plan_hash`를 함께 고치는 사전 변조도 차단된다.
- 계획의 `run_id`가 현재 run과 같은지, `required_evidence_ids`가 현재 유효한 공개 인용의 부분집합인지도 확인한다.

## 6. 승인

- `PENDING_APPROVAL`에서만 가능하며, `approve`/`reject`만 허용한다.
- `approved_by`는 서버가 `demo-reviewer`로 고정한다. 클라이언트가 보낸 필드는 `extra="forbid"`로 422.
- `approvals.run_id`는 UNIQUE라 중복 승인이 불가능하다.
- 승인 전 실행은 `E_STATE_CONFLICT` 409이고, `DENIED_EXECUTION` 감사가 남는다.
- 반려는 terminal `REJECTED`이며 실행할 수 없다.

## 7. 멱등 실행과 재시도

### 7.1 검사 순서 (고정)

1. idempotency key 형식 검증
2. run 존재 확인
3. 기존 실행 이력 조회 (`run_id`, `key`)
4. 상태 CAS: `APPROVED → EXECUTING`
5. 승인·plan hash·근거 지문·설정/코퍼스 hash 재검증
6. 실행 + `executions` insert + 상태 전이 + 감사 (트랜잭션)

### 7.2 계약

| 상황 | 결과 |
|---|---|
| 승인 전 | `409 E_STATE_CONFLICT`, executions 0 |
| 같은 key, 실행 완료 | `200` + 기존 결과, `meta.replayed=true`, 신규 행/감사 없음 |
| 같은 key, terminal 실패 | `200` + 기존 실패 결과, `meta.replayed=true` |
| 다른 key, 실행 완료 | `409 E_ALREADY_EXECUTED` |
| 다른 key, terminal 실패 | `409 E_RETRY_LIMIT` |
| 실행 중 | `409 E_IN_PROGRESS` |
| attempt 1 실패 | `EXECUTING→FAILED→RETRYING`, attempt 2 자동 (`max_attempts=2`일 때) |
| attempt 2 실패 | terminal `FAILED` |
| `max_attempts=1` | attempt 1 실패 시 즉시 terminal `FAILED`, RETRYING 없음 |
| plan/근거 변조 | `409 E_PLAN_HASH_MISMATCH` 또는 `E_EVIDENCE_STALE` |
| 설정/코퍼스 변경 | `409 E_CONFIG_CHANGED` / `E_CORPUS_CHANGED` |

### 7.3 동시성

- 호출마다 새 `sqlite3` 연결을 만들고 PRAGMA(`foreign_keys`, `busy_timeout=5000`, `synchronous=NORMAL`)를 적용한다.
- 모든 상태 검사·변경·감사는 `BEGIN IMMEDIATE` 안에서 수행한다.
- `UNIQUE(run_id, idempotency_key, attempt)`와 상태 CAS로 중복 실행을 막는다.
- 동시 실행 테스트는 4스레드에서 정확히 1회 실행을 확인한다.

## 8. 감사

- `audit_events`는 `UNIQUE(run_id, seq)`이며, seq는 같은 트랜잭션에서 `MAX+1`로 계산한다.
- `BEFORE UPDATE`/`BEFORE DELETE` trigger가 수정·삭제를 `RAISE(ABORT)`한다.
- 각 이벤트는 `prev_hash`와 `event_hash`를 갖는다.

```text
event_hash = sha256(prev_hash | run_id | seq | event_type | payload_json | occurred_at)
```

- `GET /api/runs/{id}`는 run/evidence/plan/approval/executions/audit을 **하나의 읽기 트랜잭션**에서 읽고, 그 스냅샷으로 `audit_chain.valid`를 계산한다. UI가 “승인됨”과 “실행 완료 감사”를 동시에 보는 불일치를 막는다.
- 승인·실행은 감사 chain과 `PLAN_CREATED` 앵커를 검증한다. chain이 깨지면 `E_AUDIT_CHAIN_INVALID`로 차단한다.
- 거부 요청(409)은 `DENIED_APPROVAL`/`DENIED_EXECUTION`으로 남기되, run당 20건 상한으로 감사 증폭 DoS를 막는다.
- hash chain은 우발적 변조·부분 편집을 탐지하는 보조 수단이다. DB 전체를 가진 관리자의 재작성까지 막는 tamper-proof 설계가 아니다.

## 9. SQLite 스키마

| 테이블 | 핵심 제약 |
|---|---|
| `runs` | status/demo_mode CHECK, config/corpus/evidence hash |
| `evidence` | `UNIQUE(run_id, document_id)`, snapshot_json |
| `plans` | run_id PK, plan_hash, evidence_fingerprint |
| `approvals` | `UNIQUE(run_id)`, decision CHECK |
| `executions` | `UNIQUE(run_id, idempotency_key, attempt)`, attempt 1..2, status CHECK |
| `audit_events` | `UNIQUE(run_id, seq)`, append-only trigger, hash chain |
| `schema_meta` | `schema_version=1`, 불일치 시 기동 실패 |

## 10. API 오류 계약

모든 오류는 아래 형태다.

```json
{"error":{"code":"E_STATE_CONFLICT","message":"...","run_id":"run_...","server_state":"PENDING_APPROVAL","details":{}}}
```

| HTTP | 코드 | 의미 |
|---|---|---|
| 404 | `E_NOT_FOUND` | run 없음 |
| 409 | `E_STATE_CONFLICT` | 허용되지 않은 상태/중복 승인 |
| 409 | `E_PLAN_HASH_MISMATCH` | 계획 변조/손상/감사 앵커 불일치 |
| 409 | `E_AUDIT_CHAIN_INVALID` | 감사 hash chain 손상 |
| 409 | `E_EVIDENCE_STALE` | 근거 snapshot/지문 불일치 |
| 409 | `E_CONFIG_CHANGED` | 게이트 설정 변경 |
| 409 | `E_CORPUS_CHANGED` | 코퍼스 변경 |
| 409 | `E_ALREADY_EXECUTED` | 다른 key로 실행 완료 |
| 409 | `E_RETRY_LIMIT` | 재시도 소진 |
| 409 | `E_IN_PROGRESS` | 실행 중 |
| 422 | `E_VALIDATION` / `E_SENSITIVE_INPUT` | 입력 검증/민감정보 |
| 413 | `E_BODY_TOO_LARGE` | 8KB 초과 |
| 429 | `E_RATE_LIMITED` | IP rate limit |
| 500 | `E_INTERNAL` | 내부 오류(상세 비노출) |

## 11. 보안·프라이버시

- CSP `default-src 'self'`, `script-src 'self'`, `style-src 'self'`, `frame-ancestors 'none'`.
- JS는 사용자 데이터를 `textContent`로만 삽입한다. `innerHTML`/`eval`/`document.write` 없음.
- Jinja autoescape, `|safe` 없음.
- 이메일·전화번호·주민번호·지시 우회·`<script>` 패턴은 요청과 **승인/반려 사유 모두에서** 422로 거부하고 저장하지 않는다.
- API 키 입력 필드가 없다. `.env`도 사용하지 않는다.
- `run_id`는 `uuid4` 128-bit이며 목록 API를 두지 않는다.
- 요청 본문 상한은 `Content-Length` fast-path와 **스트리밍 바이트 카운트**를 모두 적용해 chunked 업로드 우회를 막는다.
- rate limit은 기본적으로 `request.client.host`를 쓰며, `EGWA_TRUST_PROXY=1`일 때만 `X-Forwarded-For`의 **첫 번째 비어 있지 않은 값**(원래 클라이언트 IP)을 신뢰한다. 이 옵션은 Render처럼 신뢰할 수 있는 역방향 프록시 뒤에서만 켠다.
- 공개 데모에는 인증이 없다. `demo-reviewer`는 신원 인증이 아니며, 실제 운영 전 OIDC/세션/CSRF/권한 분리가 필요하다.

## 12. 알려진 한계

1. 공개 요약은 원문의 최신성을 보장하지 않는다.
2. 상충 탐지는 태그된 `policy_key`에 한정된다.
3. URL 검증은 구조 검사이며 원문 fetch가 아니다.
4. SQLite는 Render Free에서 소실될 수 있다(ephemeral).
5. 14문서 회귀 평가는 검색·정책 계약이지 LLM/RAG 품질 측정이 아니다.
6. 실제 조달·메일·결재·파일 시스템 어댑터는 없다.
