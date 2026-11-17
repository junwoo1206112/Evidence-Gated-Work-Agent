# Change: Build Evidence-Gated Work Agent

## Why

AI WorkPilot의 승인·실행·감사 흐름과 Procurement Rules RAG Copilot의 근거 검증·보류 정책을 **하나의 서버 정책**으로 결합해, “근거가 통과해야만 계획이 생성되고 승인 전에는 실행되지 않는” Agent 역량을 재현 가능하게 증명한다.

## What Changes

- 공개 행정규칙 요약 10건과 명시적 합성 fixture 4건을 체크인해 네트워크 없이 검색·게이트를 재현한다.
- Evidence Gate는 점수·https/도메인·발췌 부분일치·유효기간·상충을 검사하고, 통과 시에만 `GatePass`를 발급한다.
- Planner는 `GatePass` 없이는 호출할 수 없으며, 제한 JSON 계획과 canonical hash를 생성한다.
- 승인은 계획 hash에 결속되고, 승인 전 실행은 서버가 409로 거절한다.
- Mock Executor는 결정론적 초안/알림만 수행하며, 자동 1회 재시도와 idempotency key 멱등성을 갖는다.
- SQLite 감사 로그는 append-only trigger와 hash chain으로 연결한다.
- EG-01~EG-14 고정 평가와 124개 테스트를 오프라인으로 실행한다.
- FastAPI 단일 흐름 UI에서 부족·상충·승인 전 실행 차단을 2분 안에 확인할 수 있다.

## Non-goals

- 실제 조달·메일·결재·파일 시스템 실행
- LLM 생성 품질, 임베딩 검색 성능, 실제 업무 자동화 성과 주장
- 비공개 문서·개인정보·API 키 저장
- OIDC/세션 인증, 조직 권한, 영속 운영 DB
- Render Free SQLite를 영속 감사 저장소로 사용

## Impact

- 새 저장소 `evidence-gated-work-agent`
- 신규 Python 패키지: FastAPI, Jinja2, Pydantic, Uvicorn (dev: pytest, httpx)
- SQLite 스키마 1.0 (`schema_meta.schema_version=1`)
- 기존 두 저장소는 수정하지 않는다.

## Risks

| 위험 | 완화 |
|---|---|
| 공개 요약의 최신성 | 원문 URL·이용 근거·요약 고지, “법적 효력 없음” 명시 |
| 상충 탐지 오해 | tagged `policy_key`/`scope`만 비교, 합성 fixture 배지 |
| URL 검증 오해 | 구조 검사이며 live fetch 아님을 README/architecture에 명시 |
| SQLite 소실 | ephemeral 고지, volume 미사용, hash chain 한계 명시 |
| 무인증 공개 데모 | 128-bit run_id, rate limit, `demo-reviewer` 고지 |
| 임계값 과적합 | dev/holdout 분리, ablation, 회귀 계약으로 한정 |
