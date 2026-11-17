# Evidence-Gated Work Agent — 인수용 구현 설계서

> 작성일: 2026-11-17  
> 목적: `AI-WorkPilot`의 사람 승인·실행·감사 흐름과 `procurement-rules-rag-copilot`의 근거 검색·인용 검증·보류 정책을 **실제로 연결**한 별도 대표 프로젝트를 구현한다.  
> 범위: 공개 규정 코퍼스와 결정론적 모의 실행만 사용한다. 실제 조달 시스템, 외부 업무 API, 고객·사내 데이터, 운영 성과는 구현하거나 주장하지 않는다.

## 1. 결정 기록과 교차 검증

### 1.1 전문가 A — 채용·포트폴리오 관점

- 기존 두 저장소를 합쳐 없애지 않는다. 각각의 단일 책임과 구현 이력을 유지한다.
- 새 저장소는 화면을 병렬로 배치하는 프로젝트가 아니라, **근거가 통과해야만 승인 가능한 계획을 생성하는 Agent**를 증명해야 한다.
- 포트폴리오에는 이 프로젝트를 Agent·RAG 대표 카드로 올리고, 기존 두 프로젝트는 기반 프로젝트로 링크한다.

### 1.2 전문가 B — Agent·RAG 아키텍처 관점

- 최소 스택은 Python, FastAPI, SQLite, 체크인된 소형 공개 코퍼스, 결정론적 모의 실행이다.
- 검색 결과의 문서 ID·조항·URL·점수·인용 검증 결과가 계획 생성 입력으로 전달돼야 한다.
- `근거 부족`과 `승인 전 실행`을 UI만이 아니라 서비스 계층 정책 가드에서 차단한다.
- 처음부터 LangGraph, 외부 벡터 DB, LLM API 키, 실제 외부 실행을 넣지 않는다. 복잡도·비용·재현 위험만 늘어난다.

### 1.3 전문가 C — 검증·운영 관점

- 대표 고정 질문 10~15개로 충분 근거, 부족 근거, 인용 실패, 승인 차단, 승인 뒤 실행, 실패 뒤 재시도를 자동 검증한다.
- 감사 이력은 `run_id`, 질의, evidence, plan hash, 승인, 실행, 재시도를 같은 run에서 연결한다.
- 공개 데모의 SQLite는 재시작 시 초기화될 수 있으므로 영속 운영 DB처럼 설명하지 않는다.

### 1.4 교차 검증 결론

`Evidence-Gated Work Agent`를 별도 GitHub 저장소로 만든다. 기존 `AI-WorkPilot`과 `procurement-rules-rag-copilot`은 수정·병합하지 않고 참조 구현으로 유지한다.

## 2. 목표·비목표·완료 기준

### 목표

```text
업무 요청
  → 공개 규정 코퍼스 검색
  → 인용 URL·근거 충족 검사
  → 부족하면 계획 생성 없이 보류와 사유 기록
  → 충분하면 제한된 형식의 실행 계획 생성
  → 사람 승인
  → 승인 후 결정론적 모의 실행
  → 성공·실패·재시도와 감사 이력 표시
```

### 비목표

- 실제 조달, 결재, 메일, 파일 삭제, API 호출을 실행하지 않는다.
- 일반 지식 질의에 대한 범용 챗봇, 자율 Agent, 실제 LLM 성능 비교를 만들지 않는다.
- 비공개 문서, 개인정보, API 키, 현장 운영 데이터는 저장하지 않는다.
- Render 등 무료 호스팅의 SQLite 데이터를 영구 감사 저장소로 주장하지 않는다.

### Definition of Done

1. 근거가 충족되지 않으면 계획·승인·실행으로 진행되지 않는다.
2. 근거가 충족되면 인용을 포함한 계획이 생성되지만, 승인 전 실행 요청은 서버에서 `409`로 거절된다.
3. 승인 뒤 안전한 모의 실행만 가능하며, 이벤트가 SQLite 감사 이력에 남는다.
4. 실패한 실행은 정책에 맞게 한 번 재시도되며, 동일 idempotency key로 중복 실행되지 않는다.
5. 고정 평가와 단위·통합 테스트가 모두 통과하고, README/UI에서 데모 한계를 고지한다.

## 3. 기준 저장소와 인수 전 확인

| 대상 | URL | 기준 HEAD (2026-11-17 확인) | 재사용 대상 |
|---|---|---:|---|
| AI WorkPilot | https://github.com/junwoo1206112/AI-WorkPilot | `2f7ea7b53d72ada78e775ee6aa2590347147b52d` | 승인 상태, 실행·재시도 UI/정책, 감사 이력 표현 |
| Procurement Rules RAG Copilot | https://github.com/junwoo1206112/procurement-rules-rag-copilot | `056fa89d60719d338a972ab4de234d6c5cf7b02a` | 공개 코퍼스, 검색·인용 검증, insufficient evidence 평가 |

인수자는 Phase 0에서 실제 파일 구조·라이선스·코퍼스 사용 조건을 재확인해야 한다. 코드를 무단 복사하기보다, 각 저장소의 공개 구성과 테스트 아이디어를 참고해 새 저장소에 필요한 최소 코드를 작성한다.

## 4. 권장 구조

```text
evidence-gated-work-agent/
  app/
    api/                 # FastAPI routes
    domain/              # 상태·정책·계획 데이터 모델
    services/
      retrieval.py       # 소형 공개 코퍼스 검색 adapter
      evidence_gate.py   # 인용·점수·출처 검증
      planner.py         # 결정론적 제한 계획 생성
      execution.py       # 안전한 mock executor
      audit.py           # SQLite 이력 저장·조회
    templates/           # 단일 흐름 데모 화면
    static/
  data/public_corpus/    # 출처 URL·라이선스를 포함한 체크인 데이터
  evals/cases.json       # 고정 평가 10~15개
  tests/
  Dockerfile
  docker-compose.yml
  render.yaml            # 선택: 공개 데모
  README.md
```

### 핵심 상태

```text
DRAFT
  → RETRIEVING
  → EVIDENCE_INSUFFICIENT (종료: 계획 없음)
  또는 PENDING_APPROVAL
       → APPROVED
       → EXECUTED
       또는 FAILED → RETRYING → EXECUTED / FAILED
```

상태 전이는 도메인 서비스 한 곳에서 검증한다. 클라이언트가 상태 값을 직접 바꾸는 방식은 금지한다.

### 최소 감사 스키마

| 테이블 | 주요 필드 | 목적 |
|---|---|---|
| `runs` | run_id, user_request, status, created_at | 하나의 업무 흐름 식별 |
| `evidence` | run_id, document_id, excerpt, source_url, retrieval_score, citation_valid, gate_reason | 검색 근거와 보류 사유 |
| `plans` | run_id, plan_version, plan_json, plan_hash | 근거 기반 계획의 재현성 |
| `approvals` | run_id, approved_by, decision, decided_at, reason | 사람 승인 기록 |
| `executions` | run_id, idempotency_key, attempt, status, result_json, error_reason, executed_at | 모의 실행과 재시도 |
| `audit_events` | run_id, event_type, payload_json, occurred_at | 시간순 감사 타임라인 |

`approved_by`는 공개 데모에서 로그인 사용자가 아니라 `demo-reviewer`처럼 고정된 비개인 식별자로만 처리한다.

## 5. 페이즈별 구현 계획

### Phase 0 — 범위 고정과 베이스라인 확보

**목표**: 새 저장소의 경계와 검증 기준을 확정한다.

- `C:\AI\evidence-gated-work-agent`에 새 저장소를 생성한다.
- 기준 저장소 두 개를 읽기 전용으로 검토하고, 참고한 기능·파일·라이선스를 `docs/source-map.md`에 기록한다.
- 공개 코퍼스 후보와 각 문서 URL·사용 조건을 `data/public_corpus/SOURCES.md`에 기록한다.
- README 첫 부분에 목적·비목표·한계 고지를 작성한다.

**체크포인트**

- [ ] 기존 저장소는 수정하지 않았다.
- [ ] 실제 외부 실행·실서비스라는 표현이 없다.
- [ ] 코퍼스의 출처와 사용 조건을 확인했다.

**인수 기준**: `README.md`, `docs/source-map.md`, `SOURCES.md`가 리뷰 가능한 상태다.

### Phase 1 — 도메인 모델·SQLite·상태 전이

**목표**: UI와 무관하게 안전한 흐름을 먼저 만든다.

- Pydantic/dataclass 모델로 Run, Evidence, Plan, Approval, Execution을 정의한다.
- SQLite migration 또는 명시적 schema 초기화를 만든다.
- 상태 전이 함수를 구현한다. 허용되지 않은 전이는 예외로 처리한다.
- `audit_events`를 모든 전이에서 남긴다.

**체크포인트**

- [ ] `DRAFT → PENDING_APPROVAL`은 evidence gate 통과 뒤에만 가능하다.
- [ ] `PENDING_APPROVAL → EXECUTED` 직접 전이는 불가하다.
- [ ] 감사 이벤트가 상태 변화와 같은 트랜잭션 범위에서 기록된다.

**인수 기준**: 상태 전이 단위 테스트와 SQLite 저장·조회 테스트가 통과한다.

### Phase 2 — Retrieval adapter와 Evidence Gate

**목표**: RAG 근거가 계획 생성을 실제로 통제하게 한다.

- 기존 RAG의 공개 문서 구조를 참고해 소형 로컬 코퍼스와 keyword/BM25 등 결정론적 검색을 구현한다.
- 검색 결과에 `document_id`, 인용문, 원문 URL, 점수, URL 유효성 값을 포함한다.
- Gate 조건을 설정 파일로 분리한다. 예: 최소 유효 인용 2개, 점수 하한, URL 존재, 상충 문서 없음.
- 조건 미충족 시 `EVIDENCE_INSUFFICIENT`와 사람이 이해할 수 있는 사유를 반환한다.

**체크포인트**

- [ ] 근거 부족 시 `plans` 레코드가 생성되지 않는다.
- [ ] 잘못된 URL·빈 인용·낮은 점수는 통과하지 않는다.
- [ ] 인용이 고정 평가 질문의 기대 문서와 일치한다.

**인수 기준**: 충분/부족/인용실패 고정 사례가 각각 기대 상태로 종료한다.

### Phase 3 — 제한 계획·승인 정책·모의 실행

**목표**: Agent 통제 흐름을 서버 정책으로 증명한다.

- 계획은 자유 텍스트 대신 `steps`, `required_evidence_ids`, `risk_level`, `allowed_action`의 제한 JSON으로 만든다.
- 계획 hash를 저장하고, 승인 후 변조되지 않게 한다.
- 승인 API는 `PENDING_APPROVAL` 상태와 통과한 evidence를 재확인한다.
- 실행 API는 `APPROVED` 상태·승인된 plan hash·idempotency key 없이는 `409`를 반환한다.
- executor는 `create_demo_draft` 또는 `simulate_notification`처럼 부작용 없는 mock만 제공한다.
- 정해진 failure scenario를 통해 재시도를 검증하고, 동일 키 중복 실행을 막는다.

**체크포인트**

- [ ] 승인 전 실행은 UI 우회 요청에도 실패한다.
- [ ] 승인 후에도 허용된 mock action 외에는 실행되지 않는다.
- [ ] 실패 → 재시도 이벤트와 attempt 수가 감사 이력에 남는다.

**인수 기준**: API 통합 테스트에서 정상·차단·실패·재시도가 모두 통과한다.

### Phase 4 — FastAPI 데모 UI

**목표**: 면접관이 하나의 흐름을 2분 안에 확인할 수 있게 한다.

- 화면을 `요청 → 근거 → Gate 결과 → 계획 → 승인 → 모의 실행 → 감사 타임라인` 순서로 고정한다.
- 근거 부족일 때는 승인·실행 버튼을 비활성화하고, 차단 사유와 인용 부족 정보를 표시한다.
- 충분 근거 데모와 부족 근거 데모 버튼을 제공한다.
- 상단과 footer에 다음 고지를 표시한다: “공개 문서 기반 로컬 검증·결정론적 모의 실행 데모이며, 실제 조달·외부 업무 시스템을 실행하지 않습니다.”

**체크포인트**

- [ ] 계획에서 인용을 클릭해 출처 URL을 볼 수 있다.
- [ ] UI 상태와 API 상태가 불일치하지 않는다.
- [ ] 개인정보 입력 필드와 API 키 입력 필드가 없다.

**인수 기준**: Playwright 또는 동등 E2E 테스트로 두 대표 흐름을 재현한다.

### Phase 5 — 평가·테스트·문서화

**목표**: 기능 시연이 아니라 검증 가능한 Agent/RAG 사례로 완성한다.

- 기존 RAG의 고정 평가 중 공개·재현 가능한 10~15개를 새 `evals/cases.json`으로 선정한다.
- 다음 분류를 모두 포함한다: 충분 근거, 부족 근거, 인용 실패, 상충 근거, 승인 전 실행, 승인 뒤 실행, 실패 재시도, 중복 요청.
- `pytest`에서 unit/integration/e2e를 구분한다.
- README는 2분 요약, 아키텍처, 실행 방법, 평가 결과, 한계, 소스 맵 순서로 간결하게 쓴다.

**체크포인트**

- [ ] 평가 기대값이 상태·인용 문서·차단 사유까지 검증한다.
- [ ] 테스트가 네트워크·비공개 키 없이 통과한다.
- [ ] 한계가 결과보다 눈에 잘 보이게 명시된다.

**인수 기준**: 깨끗한 환경에서 `pytest`와 컨테이너 실행이 성공한다.

### Phase 6 — 컨테이너·공개 데모·포트폴리오 연결

**목표**: 외부 검토자가 안전하게 재현할 수 있게 한다.

- Dockerfile, docker-compose, `/health` endpoint를 만든다.
- 필요할 때만 Render Free에 배포한다. cold start, 15분 유휴 종료, SQLite 비영속성을 README에 표시한다.
- 라이브 데모가 준비되면 포트폴리오 사이트에 `라이브 데모 (공개 문서·모의 실행)` 버튼을 추가하고 GitHub 소스 링크를 함께 제공한다.

**체크포인트**

- [ ] `docker compose up --build` 뒤 `/health`가 성공한다.
- [ ] 배포 URL에서 두 대표 데모를 수행할 수 있다.
- [ ] 외부 실행·운영 성과로 오해될 문구가 없다.

**인수 기준**: 라이브 URL, GitHub README, 포트폴리오 카드가 서로 일관된다.

## 6. 고정 평가 초안

| ID | 유형 | 기대 결과 |
|---|---|---|
| EG-01 | 충분한 근거 | 유효 인용 2개 이상, `PENDING_APPROVAL`, 계획 생성 |
| EG-02 | 부족 근거 | `EVIDENCE_INSUFFICIENT`, 계획 없음 |
| EG-03 | 빈 질의 | 검증 오류, 실행 없음 |
| EG-04 | URL 없는 인용 | evidence gate 차단 |
| EG-05 | 낮은 검색 점수 | evidence gate 차단 |
| EG-06 | 상충 근거 | 보류 및 상충 사유 기록 |
| EG-07 | 승인 전 실행 | HTTP 409, execution 없음 |
| EG-08 | 승인 뒤 mock 실행 | `EXECUTED`, audit event 기록 |
| EG-09 | mock 실패 | `FAILED`, 오류 사유 기록 |
| EG-10 | 허용된 재시도 | `RETRYING → EXECUTED`, attempt 증가 |
| EG-11 | 중복 idempotency key | 두 번째 실행 거절 또는 기존 결과 반환 |
| EG-12 | 계획 변조 | plan hash 불일치로 승인·실행 차단 |

## 7. 인수자 작업 순서

1. Phase 0 체크포인트를 PR로 먼저 검토받는다.
2. Phase 1~3은 API·테스트 우선으로 구현하고, UI는 그 뒤에 붙인다.
3. 매 Phase 종료 시 상태 전이·감사 이력·차단 정책을 회귀 테스트한다.
4. Phase 5 테스트 결과와 Phase 6 공개 데모 한계 고지를 검토한 뒤에만 포트폴리오 카드에 추가한다.

## 8. 리스크와 즉시 중단 조건

- 공개 문서의 이용 조건이 불명확하면 해당 코퍼스를 포함하지 않는다.
- API 키 또는 실제 업무 시스템 자격 증명이 필요해지면 범위에서 제외하고 mock으로 대체한다.
- 근거 부족인데 계획을 생성하는 경로가 발견되면 Phase 3 이후 작업을 멈추고 evidence gate부터 수정한다.
- 배포 환경에서 SQLite 영속성을 보장할 수 없으면 이를 기능·이력 보존으로 설명하지 않는다.
