# Tasks: Build Evidence-Gated Work Agent

## Phase 0 — 범위 고정과 베이스라인

- [x] 새 저장소 디렉터리와 패키지 구조 생성
- [x] 기준 저장소 두 개를 읽기 전용으로 검토하고 `docs/source-map.md` 작성
- [x] LICENSE 부재 확인, 코드 미복사 원칙 기록
- [x] 공개 코퍼스 10건·합성 fixture 4건과 `SOURCES.md` 작성
- [x] README 상단 목적·비목표·한계 고지

## Phase 1 — 도메인·SQLite·상태 전이

- [x] Run/Evidence/Plan/Approval/Execution/Audit 모델
- [x] `schema_version=1`, WAL, foreign_keys, busy_timeout
- [x] 단일 전이표 + CAS + `BEGIN IMMEDIATE`
- [x] 상태 변경과 감사 이벤트 동일 트랜잭션 rollback 테스트
- [x] append-only trigger, `UNIQUE(run_id, seq)`, hash chain

## Phase 2 — Retrieval + Evidence Gate

- [x] 한국어 조사 제거·stopword·음절 bigram
- [x] 절대 점수(coverage + BM25), min-max 정규화 제거
- [x] URL https/allowlist/credentials/IP/port 검사
- [x] 발췌 40자·부분일치·말줄임표·유일성 검사
- [x] 유효기간, 공개/합성 분리, tagged policy conflict
- [x] 충분/부족/상충/URL/저점수 케이스 테스트

## Phase 3 — 계획·승인·실행

- [x] `GatePass` seal + planner 타입 강제
- [x] canonical plan hash + evidence/config/corpus 결속
- [x] 승인 plan hash 결속, 중복 승인 409, 반려 terminal
- [x] 승인 전 실행 409 + `DENIED_EXECUTION` 감사
- [x] mock action allowlist, 결정론 결과
- [x] 자동 1회 재시도, attempt 2, terminal 실패, 멱등 replay
- [x] 동시 실행/승인 테스트

## Phase 4 — FastAPI UI

- [x] 요청 → 근거 → Gate → 계획 → 승인 → 실행 → 감사 단일 흐름
- [x] 4개 데모 프리셋(충분/부족/상충/실패→재시도)
- [x] 승인 전 실행 409 인라인 노출
- [x] capabilities 서버 산출, UI/API 상태 일치
- [x] CSP, `textContent`, label, focus, skip link
- [x] 개인정보/API 키 입력 필드 없음

## Phase 5 — 평가·테스트·문서

- [x] EG-01~EG-14 `evals/cases.json`
- [x] dev 8 / holdout 6 분리
- [x] `evals/run_evals.py` + `results.json`/`results.md`
- [x] pytest unit/integration/concurrency 151개
- [x] README 2분 요약·아키텍처·평가·한계·소스 맵
- [x] 18질의 retrieval ablation
- [x] 전문가 A/B/C 인터뷰 원장

## Phase 6 — 컨테이너·공개 데모

- [x] Dockerfile non-root + HEALTHCHECK
- [x] docker-compose (volume 없음, ephemeral 고지)
- [x] `/health` DB·코퍼스·설정 hash
- [x] `docker compose up --build` 실제 검증 (Docker 29.9.3, healthy, non-root, API 흐름 통과)
- [ ] Render Free 배포 (선택, 사용자 승인 필요)
- [ ] 포트폴리오 사이트 카드 링크 (별도 저장소 작업)

## Verification

- [x] `pytest` 151 passed
- [x] `python -m evals.run_evals` 14/14
- [x] `python scripts/ablation.py` 결과 문서화
- [x] `SOURCES.md` hash = `evals/results.json` corpus hash
- [x] Docker E2E
- [ ] 공개 URL 스모크
