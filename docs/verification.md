# 검증 기록

> 실행일: 2026-11-17  
> 환경: Windows, Python 3.12.10, Docker 29.9.3 (Desktop Linux engine)  
> 테스트/평가는 네트워크·API 키 없이 실행된다. Playwright 브라우저 설치와 Docker 이미지 빌드는 최초 1회 네트워크를 사용했다.

## 1. 테스트

```powershell
python -m pytest -o addopts="" -p no:cacheprovider
```

```text
151 passed (약 7초)
```

구성:

| 파일 | 테스트 수 | 성격 |
|---|---:|---|
| `test_api_flows.py` | 33 | EG-01~14 + 409/보안/멱등/변조 |
| `test_gate.py` | 22 | 점수/URL/발췌/유효기간/상충/중복 |
| `test_corpus.py` | 15 | 출처 등급/URL/발췌/정책 메타 |
| `test_retrieval.py` | 10 | 조사 제거/점수/도달성/도메인 외 |
| `test_database.py` | 9 | schema/trigger/hash chain/rollback/reconcile |
| `test_planner.py` | 10 | GatePass/구조/hash/NFC/max_attempts |
| `test_ui.py` | 10 | 고지/프리셋/XSS/라벨/threshold |
| `test_docs.py` | 9 | README/해시/문서/비밀정보 |
| `test_executor.py` | 7 | mock allowlist/실패 모드 |
| `test_health.py` | 7 | 200/503/schema/헤더/OpenAPI |
| `test_state_machine.py` | 5 | 명시적 전이 행렬 |
| `test_limits.py` | 4 | 413/429/chunked/XFF |
| `test_concurrency.py` | 4 | 동시 실행/승인/감사 seq |
| `test_evals.py` | 4 | 14/14 및 결과 계약 |
| `test_config.py` | 2 | 설정 hash/기본 임계값 |

## 2. 고정 평가

```powershell
python -m evals.run_evals
```

```text
14/14 passed
```

| 구분 | 통과 |
|---|---:|
| dev | 8/8 |
| holdout | 6/6 |

산출물: `evals/results.json`, `evals/results.md`. 코퍼스 SHA-256과 게이트 설정 hash가 결과에 고정된다.

## 3. 검색 ablation

```powershell
python scripts/ablation.py
```

| 변형 | Recall@3 | MRR@3 |
|---|---:|---:|
| word_exact | 0.861 | 0.852 |
| particle | 0.972 | 0.963 |
| particle+bigram (current) | 1.000 | 1.000 |

18질의 micro-ablation이며 벤치마크가 아니다. 상세는 `docs/retrieval-ablation.md`.

## 4. 브라우저 E2E

```powershell
python -m playwright install chromium
python -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8020
$env:EGWA_BASE_URL="http://127.0.0.1:8020"; python scripts/e2e_browser.py
```

결과:

```text
browser e2e passed
```

검증한 DOM 흐름:

1. `① 충분 근거` 클릭 → `승인 대기` 표시
2. 승인 패널의 `승인 전 실행 시도 (409 확인)` 클릭 → `E_STATE_CONFLICT · HTTP 409` 표시, executions 0
3. `승인` 클릭 → `승인됨`
4. `모의 실행` 클릭 → `모의 실행 완료`, attempt 1건
5. `같은 키로 재요청 (멱등 확인)` 클릭 → 기존 결과 반환, `replayed` 안내

산출물: `docs/demo-approval-409.png`, `docs/demo-execution.png`.

## 5. Docker E2E

```powershell
$env:EGWA_PORT="8010"
docker compose up --build -d
```

검증 결과:

| 항목 | 결과 |
|---|---|
| 빌드 | 성공 (`python:3.12-slim`, pip install) |
| 컨테이너 상태 | `Up ... (healthy)` |
| 사용자 | `uid=10001(appuser)` (non-root) |
| `/health` | HTTP 200, `schema_version=1`, `journal_mode=wal`, 14문서 |
| `POST /api/runs` (충분) | 201, `PENDING_APPROVAL`, public valid 2 |
| 승인 전 실행 | 409 `E_STATE_CONFLICT` |
| 승인 | 200 `APPROVED` |
| mock 실행 | 200 `EXECUTED`, attempts 1 |
| 같은 key 재요청 | 200 `replayed=true`, attempts 1 |
| 부족 근거 | 201 `EVIDENCE_INSUFFICIENT`, plan null |
| 상충 근거 | 201 `EVIDENCE_INSUFFICIENT`, category conflict |
| `/` `/static/app.js` `/static/styles.css` | 200 |
| `/docs/verification` | 200 |

> 호스트 8000 포트가 다른 로컬 서비스와 충돌해 `EGWA_PORT=8010`으로 검증했다. `docker-compose.yml`은 기본 8000이며 `EGWA_PORT`로 덮어쓸 수 있다.

종료:

```powershell
docker compose down
```

## 6. 오프라인·보안 검증

- `test_no_network_calls_during_full_flow`: outbound `connect`/`connect_ex`/`create_connection`을 막고 전체 흐름 통과.
- `test_approval_and_execution_do_not_rerun_retrieval`: 승인·실행 중 retriever 호출 금지.
- `test_docs.py::test_no_secret_material_in_public_files`: `sk-*`, `AKIA*`, private key, `LAW_API_OC` 환경변수 대입, `api_key=` 패턴 부재.
- CSP, `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Cache-Control: no-store`.
- 이메일·전화번호·주민번호·지시 우회·`<script>` 입력은 422로 거부되고 run이 생성되지 않음.

## 7. 실행하지 못한 것 / 주장하지 않는 것

| 항목 | 상태 | 이유 |
|---|---|---|
| Render Free 라이브 배포 | 완료 | https://evidence-gated-work-agent.onrender.com/ — `/health` 200, 충분 근거·승인 전 409·승인 뒤 mock 실행·근거 부족 차단을 공개 URL에서 확인 |
| GitHub push / commit | 완료 | `adce011 feat: evidence-gated work agent 초기 구현`을 `main`에 푸시했고 GitHub Actions `verify` 성공 |
| 실제 조달/메일/결재/파일 실행 | 없음(의도) | mock executor만 존재 |
| LLM/RAG 품질 수치 | 없음(의도) | 결정론 계약 회귀만 평가 |
| SQLite 영속 감사 | 없음(의도) | Render/Compose 모두 ephemeral, volume 미사용 |
| 실제 신원 인증 | 없음(의도) | `demo-reviewer` 고정, 공개 데모 한계 |

## 8. 재현 순서

```powershell
python -m pip install -e ".[dev]"
python -m pytest -o addopts="" -p no:cacheprovider
python -m evals.run_evals
python scripts/ablation.py
python -m uvicorn app.main:create_app --factory --reload
# http://127.0.0.1:8000
```

Docker:

```powershell
docker compose up --build -d
# http://127.0.0.1:8000/health
# 8000 충돌 시: $env:EGWA_PORT="8010"; docker compose up -d
```
