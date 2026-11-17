# 전문가 A/B/C 인터뷰·교차 검증 원장

> 작성일: 2026-11-17  
> 방식: Ouroboros `interview` 스킬의 게이트(모호성 원장, Refine, Seed-ready Acceptance Guard)를 이 저장소 문맥에 적용. MCP 서버가 없는 환경이므로 Path B(직접 인터뷰)로 진행했다.  
> 사용자 위임: “전문가 A/B/C 교차 검증 후 권장 구현을 페이즈별로 순차 진행”이라는 요청에 따라, 설계서에 이미 명시된 범위 안에서는 권장 기본값을 자동 채택했다. 범위를 바꾸는 결정은 하지 않았다.

## 1. 목표 한 문장

**공개 규정 근거가 게이트를 통과해야만 제한된 계획이 생성되고, 사람 승인 전에는 서버가 실행을 거절하며, 승인 뒤에도 결정론적 mock만 멱등 실행되고 그 전 과정이 변조 탐지 가능한 감사 이력으로 남는 Agent 데모를, 네트워크·API 키 없이 재현한다.**

## 2. 모호성 원장 (Ambiguity Ledger)

| Track | 확정 결정 | 남은 모호성 | 검증 방법 |
|---|---|---:|---|
| Scope | 검색→게이트→계획→승인→mock 실행→감사 단일 흐름 | 낮음 | 2분 데모 + E2E |
| Evidence | 공개 요약 10 + 합성 fixture 4, 최소 공개 인용 2 | 중간(법적 최신성 아님) | `SOURCES.md`, 게이트 단위 테스트 |
| Gate | 절대 점수 0.42, URL/발췌/유효기간/상충 | 중간(임계값 튜닝) | EG-01~06, ablation |
| Approval | `demo-reviewer` 고정, plan hash 결속, 중복 409 | 낮음(실인증 아님) | EG-07/08/13/14 |
| Execution | mock 2종, 자동 1회 재시도, attempt≤2, 멱등 key | 낮음 | EG-09/10/11, 동시성 |
| Persistence | SQLite, WAL, `BEGIN IMMEDIATE`, 감사 append-only | 높음(공개 호스팅 소실) | DB 테스트, README 고지 |
| Verification | pytest + EG-01~14, 오프라인 | 낮음 | 151 tests, 14/14 |
| Honesty | LLM 없음, 실제 조달 실행 없음, 품질 비주장 | 낮음 | README/UI 상시 고지 |

## 3. 전문가 A — 채용·포트폴리오 관점

**1차 판정: pass-with-fixes (P0 3건)**

| 심각도 | 지적 | 채택한 개선 | 증거 |
|---|---|---|---|
| P0 | “Agent + RAG” 라벨 대비 LLM이 없음을 뒤에 숨기면 신뢰 손실 | README 첫 문단과 UI 헤더에 “LLM 없음·결정론” 명시 | README, `index.html` |
| P0 | 라이브 데모 콜드스타트가 2분 리뷰를 잡아먹음 | 1차 증거를 로컬 `pytest`/`docker compose`로 고정, 호스팅 한계 별도 고지 | README 검증 절차 |
| P0 | “상충”을 일반 의미 모순으로 읽히게 하면 반례 하나로 붕괴 | `policy_key`/`scope`/`value`가 태그된 문서로 범위 축소, 합성 fixture 명시 | `docs/architecture.md`, EG-06 |
| P1 | 게이트가 화면 비활성화로만 보임 | “승인 전 실행 시도 (409 확인)” 버튼으로 서버 409 JSON을 화면에 노출 | `app.js`, EG-07 |
| P1 | 12문항·임계값 동시 튜닝의 순환 평가 위험 | EG를 dev 8 / holdout 6으로 분리, 점수는 코퍼스 단위 probe로 보정 | `evals/cases.json`, `evals/results.json` |
| P1 | 한국어 토크나이저 근거 부재 | 조사 제거 + 음절 bigram + 절대 점수, ablation 문서화 | `docs/retrieval.md` |
| P1 | append-only 감사를 DB 제약 없이 주장 | UPDATE/DELETE trigger + hash chain + seq | `test_database.py` |
| P1 | 실패 주입이 하드코딩이면 가짜 신뢰성 | `demo_mode=fail_once/fail_twice`를 명시적 API 필드·audit에 기록 | `app/api/schemas.py` |
| P1 | 브라우저 없이 검증 불가 | curl 예시, API 통합 테스트, 선택적 Playwright 스크립트 | README, `scripts/e2e_browser.py` |
| P1 | Render 재시작 시 타임라인 공백 | “ephemeral SQLite” 상시 고지, 시드 스크립트 제공 | README, `scripts/seed_demo.py` |
| P2 | 세 번째 저장소가 “같은 데모 3번”으로 보임 | 기존 두 프로젝트 대비 delta 표, 역할 분리 | README |

**A가 요구한 첫 2분의 3장면**은 모두 구현됐다: (1) README 최상단의 정직한 프레이밍과 검증 명령, (2) 부족/상충에서 죽는 승인·실행 버튼과 서버 409, (3) run_id·plan hash·승인자·attempt 1 실패→2 성공이 한 타임라인에 이어지는 화면.

## 4. 전문가 B — Agent·RAG 아키텍처/보안 관점

**1차 판정: pass-with-fixes (P0 6건)**

| 심각도 | 지적 | 채택한 개선 | 증거 |
|---|---|---|---|
| P0 | 게이트 통과가 관례에 의존, planner 직접 호출 가능 | `GatePass` frozen dataclass + private seal. Planner가 타입을 강제 | `domain/models.py`, `planner.py`, `test_gate.py` |
| P0 | `EXECUTING` 부재 + idempotency 검사 순서 미정의 | 상태 추가, key 조회→상태 CAS→실행 순서 고정, 동시 실행 테스트 | `workflow.py`, `test_concurrency.py` |
| P0 | SQLite 전역 연결·PRAGMA 누락·읽기 트랜잭션 밖 경합 | 연결 팩토리, `foreign_keys`, `busy_timeout`, WAL, 호출별 연결, `BEGIN IMMEDIATE` | `db.py`, `test_database.py` |
| P0 | 감사가 성공 로그가 될 위험 | `UNIQUE(run_id, seq)`, append-only trigger, 거부 이벤트 감사(상한 20), hash chain | `db.py`, `audit.py` |
| P0 | “유효 인용 2개”가 한 문서의 중복 청크로 충족 | `UNIQUE(run_id, document_id)`, 공개 문서만 카운트, 합성 fixture 제외 | `db.py`, `evidence_gate.py` |
| P0 | min-max 정규화 + 양방향 부분일치로 점수 게이밍 | 절대 IDF coverage, 단일 음절 제외, 도메인 외 질의 음성 케이스 | `retrieval.py`, `test_retrieval.py` |
| P1 | plan hash 정규화 미정의, 근거 교체 미탐지 | NFC·정렬·구분자 고정, `evidence_fingerprint`/config/corpus hash 결속, 타임스탬프 제외 | `planner.py`, `test_planner.py` |
| P1 | 승인/실행 시 재검색 TOCTOU | 저장된 evidence snapshot만 재검증, 재검색 금지 테스트 | `_revalidate_for_action`, `test_api_flows.py` |
| P1 | retry/attempt 계약 모호 | attempt 서버 산출 1..2, `(run,key,attempt)` unique, 3번째 409 | `db.py`, `workflow.py`, EG-09/10 |
| P1 | 충돌 탐지 FP/FN | percentage 정규화, 동일 key+scope만 비교, 한계 명시 | `normalize_policy_value`, `docs/architecture.md` |
| P1 | URL 검증이 SSRF/구조 검사에 머묾 | https·allowlist·credentials/IP/port 거부, 런타임 fetch 금지 | `evidence_gate.py`, `corpus.py` |
| P1 | 발췌 최소 길이·유일성 없음 | 40자 이상, 말줄임표 거부, 코퍼스 내 유일성, 본문 부분일치 | `corpus.py`, `test_corpus.py` |
| P1 | 무인증·요청 상한 부재 | 8KB body limit, IP rate limit, 128-bit run_id, 목록 API 없음 | `main.py` |
| P1 | 상태기계 불완전 | `REJECTED`, `EXECUTING`, terminal `FAILED`, interrupted reconcile | `state.py`, `workflow.py` |
| P2 | 저장형 XSS | JS는 `textContent`만 사용, CSP `self`, `innerHTML` 금지 | `app.js`, `test_ui.py` |
| P2 | 민감정보 영구 저장 | 이메일·전화·주민번호·지시 우회 패턴 422 거부 | `workflow.py`, `test_api_flows.py` |

**B의 핵심 한 줄** — “게이트는 코드 경로가 아니라 생성 불가능한 타입 + DB 제약으로 강제” — 을 `GatePass` seal, `UNIQUE` 제약, trigger, fingerprint 재검증으로 반영했다.

## 5. 전문가 C — 검증·운영 관점

**1차 판정: pass-with-fixes (P0 4건)**

| 심각도 | 지적 | 채택한 개선 | 증거 |
|---|---|---|---|
| P0 | EG-06 상충 판정 규칙 부재 | `gate_reason`에 `goods_contract_guarantee_rate`, conflict detail 고정 | EG-06, `test_gate.py` |
| P0 | EG-10 재시도 주체·소진 케이스 미정의 | 자동 1회, fail_once→2 attempts, fail_twice→FAILED, 재요청 409 | EG-09/10, `test_api_flows.py` |
| P0 | EG-11 “거절 또는 기존 결과” 이분법 | `200 + 동일 execution`으로 단일화, `replayed` meta | EG-11, `test_api_flows.py` |
| P0 | check-then-act 경쟁 | `BEGIN IMMEDIATE` + unique + 동시 approve/execute 테스트 | `test_concurrency.py` |
| P1 | EG-12 변조 표면 미정의 | DB plan 재해시 vs 승인 hash 비교, `PLAN_TAMPERED` 감사 | EG-12 |
| P1 | plan hash 재시작·dict 순서 flakiness | canonical JSON, 타임스탬프 제외, stable hash 테스트 | `test_planner.py` |
| P1 | “URL 존재”를 네트워크 HEAD로 오해 | 구조·allowlist·부분일치로 정의, 런타임 fetch 없음 | `docs/architecture.md` |
| P1 | EG-03/04/05 주입 seam 없음 | 코퍼스에 합성 fixture를 넣어 HTTP 경로로 도달 가능 | EG-03/04/05 |
| P1 | 중복 승인·거절 후 승인 미커버 | EG-13/14 + 409 매트릭스 | `evals/cases.json` |
| P1 | 시간·정렬 flakiness | UTC·`seq` 기준 단언, 고정 clock 평가 | `evals/run_evals.py` |
| P1 | 전역 store로 테스트 오염 | `create_app(settings)` 팩토리 + tmp DB fixture | `tests/conftest.py` |
| P1 | UI/API 불일치·XSS 미검증 | `capabilities` 서버 산출, `textContent`, XSS/마크업 테스트 | `test_ui.py` |
| P1 | `/health` 무의미, migration 아님 | schema_version fail-fast, DB 실패 시 503 | `test_health.py` |
| P1 | Render ephemeral 오해 | README/UI/Render 주석에 소실 고지 | README, `render.yaml` |
| P2 | 컨테이너 root·HEALTHCHECK 부재 | non-root UID, HEALTHCHECK, compose healthcheck | `Dockerfile`, `docker-compose.yml` |
| P2 | 접근성 미검증 | label, role=alert/status, focus-visible, skip link | `index.html`, CSS |

**C의 Phase exit 기준**에 맞춰 “명령 + 산출물 + 음성 테스트”를 남겼다. 예: `pytest` 151 passed, `evals/results.json` 14/14, `plans/approvals/executions=0` 단언.

## 6. 실시간 개선 기록 (설계 → 코드)

| 시점 | 발견 | 즉시 수정 | 재검증 |
|---|---|---|---|
| Phase 2 | 충분 질의 상위 점수 0.47 < 임계값 0.55 | 조사 제거·요청 동사 stopword·절대 점수 재보정(0.42) | EG-01 통과 |
| Phase 2 | 합성 fixture 발췌 35자로 코퍼스 로드 실패 | 발췌 40자 이상으로 보강, 로더 fail-fast 유지 | `test_corpus.py` |
| Phase 2 | `example.com`이 공개 문서 allowlist에 섞임 | 공개 문서에서 example.com 금지, 합성 전용으로 분리 | `test_corpus.py` |
| Phase 3 | 재시도 1차 실패 시 상태가 EXECUTING에 고착 가능 | `EXECUTING→FAILED→RETRYING→…` 트랜잭션 분리 + reconcile | EG-10, `test_database.py` |
| Phase 3 | 동시 실행 테스트가 barrier로 교착 | 실행 지연만 주입하고 barrier 제거 | `test_concurrency.py` |
| Phase 4 | 서버 HTML만 검사하는 UI 테스트가 JS 렌더링과 불일치 | 서버 셸/정적 JS 계약을 분리 검증 | `test_ui.py` |
| Phase 5 | 감사 chain을 “변조 방지”로 오해할 여지 | append-only trigger + hash chain + README 한계 문구 | `test_database.py` |
| Phase 6 | Docker 엔진 미기동·호스트 8000 포트 충돌 | 엔진 기동, `EGWA_PORT` 오버라이드 추가, 8010으로 E2E | healthy·non-root·API 7단계 통과 |

## 7. 2차 코드 리뷰 (구현 후 교차 검증)

1차 리뷰가 설계를 검증한 뒤, 구현된 코드·테스트·문서를 같은 전문가 A/B/C가 다시 읽었다.

### 7.1 전문가 A — 채용/패키징

**판정: shortlist (yes, 조건부).** “2분 안에 핵심 주장을 보는 경로”가 약하다는 지적을 즉시 반영했다.

| 지적 | 수정 |
|---|---|
| README 첫 줄이 “공개 규정 14건”으로 과대 (실제 10+4) | “공개 요약 10건 + 합성 fixture 4건”으로 수정 |
| 409 버튼이 실행 카드 아래 3~4화면에 있고 승인 후 사라짐 | 승인 패널 안, 승인 버튼 위로 이동 |
| 점수 하한 0.42가 화면에 없음 | 미터에 42% 눈금 + “기준 0.42” 라벨 |
| 내부 enum(`mode: none`, `category: none`) 노출 | 한국어 라벨(`정상`, `차단 없음`)로 매핑 |
| 실행 후에도 idempotency key 편집 가능 | 실행 이력이 있으면 `readOnly`, 변경 시 409 안내 |
| 화면에 검증 수치 없음 | footer에 `pytest 151 · eval 14/14 · Docker healthy` + 검증 링크 |
| 라이브 데모/GIF 없음 | Docker 원라이너를 첫 실행 경로로 올리고, Playwright 스크린샷 2장을 README에 삽입 |
| 실패 시나리오 셀렉트가 첫 화면을 지배 | `고급: 실패 시나리오` details로 이동 |
| 미실행 Playwright 스크립트 | Chromium 설치 후 실제 실행, `browser e2e passed`와 스크린샷 확보 |

남은 A의 지적: 라이브 URL은 사용자 계정/배포 승인 없이는 만들 수 없다. README는 “Docker 1회 로컬 실행 + 스크린샷”으로 증거를 낮춰 주장한다.

### 7.2 전문가 B — 아키텍처/보안

**판정: pass-with-fixes (P0 없음, P1 5건).** 코드로 닫히지 않은 5곳을 수정했다.

| 지적 | 수정 | 증거 |
|---|---|---|
| `Content-Length`만 검사해 chunked 업로드 우회 | 순수 ASGI 바이트 카운터로 스트리밍 검사 | `test_limits.py` 413/chunked |
| XFF 미설정 시 Render 프록시 IP 하나로 rate limit 공유 | `EGWA_TRUST_PROXY` 옵션 + 첫 번째 클라이언트 홉 사용, 빈 버킷 축출 | `test_limits.py` XFF 2버킷 |
| 점수 미달 상충 문서가 top-k에서 숨음 | tagged 정책 키가 0.30 이상으로 드러나면 **코퍼스 전체** 구조 유효 문서 스캔 | `test_conflict_scan_is_not_limited_to_valid_top_k` |
| 승인 전 `plan_json`+`plan_hash` 동시 변조 가능 | `PLAN_CREATED` 감사 이벤트 hash 앵커 + chain 검증 | `test_plan_tampering_before_approval_is_rejected` |
| run/audit을 다른 트랜잭션에서 읽어 UI 불일치 가능 | `get_run`이 하나의 읽기 트랜잭션에서 run+audit을 읽고 chain 계산 | 코드 경로 + 기존 UI/API 테스트 |
| `max_attempts` 설정이 해시만 바꾸고 동작은 하드코딩 | planner/executor가 설정값 사용, `max_attempts=1`은 재시도 없음 | `test_max_attempts_one_stops_after_first_failure` |
| 손상 JSON 한 행이 GET을 영구 500으로 만듦 | `_safe_json` + `integrity_warning`, 승인·실행 차단 | `test_corrupt_gate_json_does_not_500`, `test_corrupt_plan_json_does_not_500_and_blocks_actions` |
| terminal 실패가 영구 미종결로 표시 | `is_terminal(status, attempts)`로 2차 실패 종결 표현 | `test_state_machine.py` |

`GatePass`는 Python 런타임의 완전한 capability가 아니라 **사고 방지용 타입**임을 문서에 명시했다. 감사 hash chain은 승인·실행 게이트에서 실제로 강제된다.

### 7.3 전문가 C — QA/운영

**판정: pass-with-fixes (P0 없음, P1 6건).**

| 지적 | 수정 | 증거 |
|---|---|---|
| terminal 실패에서 같은 key가 replay되지 않음 | `FAILED` + same key → 200 cached failure, 다른 key → 409 | `test_fail_twice_is_terminal_and_same_key_replays_cached_failure` |
| `/health`가 schema 손상 시 200 | schema_version 불일치/누락 → 503 | `test_health_returns_503_when_schema_version_is_missing` |
| 커밋된 eval 결과가 최신 실행과 비교되지 않음 | cases/checks/actual/corpus/config/cases_sha 비교 | `test_committed_results_match_fresh_run` |
| ablation 질의 수가 12/16/18로 불일치 | 18로 통일, 테스트가 스크립트 `len(QUERIES)`와 대조 | `test_retrieval_docs_include_ablation` |
| 승인 사유에 PII 저장 가능 | 요청과 동일한 민감정보 패턴으로 422 | `test_approval_reason_rejects_pii` |
| UI/API 일치가 200 확인뿐 | 실제 Playwright DOM 흐름 + 스크린샷 | `scripts/e2e_browser.py` |
| 413/429 테스트 부재 | chunked 413, Content-Length 413, 429, XFF 테스트 추가 | `test_limits.py` |
| 전이표 테스트가 동어반복 | 테스트 소유의 명시적 10×10 기대 행렬로 교체 | `test_state_machine.py` |
| EG-12의 `null` expectation이 항상 통과 | 제거, runner가 알 수 없는 expectation을 실패 처리 | `evals/cases.json` |

### 7.4 2차 리뷰 후에도 남는 한계

- 공개 URL 배포는 하지 않았다. `render.yaml`과 Docker 로컬 실행만 검증했다.
- 인증·권한·CSRF는 없다. `demo-reviewer`는 신원 인증이 아니다.
- SQLite는 ephemeral이며 hash chain은 tamper-proof가 아니다.
- 상충은 tagged policy key에 한정되고, 의미적 모순은 탐지하지 않는다.
- 14문서/18질의 평가는 회귀 계약이며 RAG 품질 벤치마크가 아니다.
- GitHub 공개 저장소와 별도 Git 이력으로 관리한다. 기준 저장소는 `references/`에만 보관하며 새 저장소에는 포함하지 않는다.

## 8. Restate Gate

**goal:** 공개 규정 근거가 통과해야만 계획이 생성되고, 승인 전 실행은 409로 거절되며, 승인 뒤 결정론적 mock 실행이 멱등·재시도 정책과 hash chain 감사로 재현되는 Agent 데모를, LLM·네트워크·API 키 없이 제공한다.

이 문장은 원 요청(설계서의 목표·비목표·DoD)과 충돌하지 않는다. 사용자가 구현을 위임했으므로 별도 승인 턴을 만들지 않고, 범위 변경이 필요한 항목(실제 조달 연동, LLM 품질 평가, 인증)은 **비목표로 유지**했다.

## 9. 잔여 위험과 다음 결정

| 위험 | 현재 처리 | 다음 단계(범위 밖) |
|---|---|---|
| 공개 요약의 법적 최신성 | 원문 URL·이용 근거·요약임을 명시 | 원문 API 연동 + 시행일 동기화 |
| 상충 탐지의 의미적 한계 | tagged policy key만 | LLM/규칙 기반 claim 비교는 별도 과제 |
| SQLite 소실 | ephemeral 고지 | Postgres + 마이그레이션 + 보존 정책 |
| 무인증 승인 | 128-bit run_id + rate limit + `demo-reviewer` 고지 | OIDC/세션, CSRF, 권한 분리 |
| 검색 성능 일반화 | 14문서 ablation만 | 공개 RFP 코퍼스 확장 평가 |
| plan hash의 장기 호환 | `hash_scheme=egwa-plan-v1` | 스키마 버전·마이그레이션 정책 |
