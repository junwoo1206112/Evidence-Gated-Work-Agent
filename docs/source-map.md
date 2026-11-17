# 소스 맵과 라이선스 확인

> 기준일: 2026-11-17  
> 목적: 새 저장소가 기존 두 프로젝트를 어떻게 참고했고, 무엇을 복사하지 않았는지 감사 가능하게 남긴다.

## 1. 기준 저장소

| 저장소 | 기준 HEAD (설계서 기재) | 검토한 범위 | 재사용한 것 | 복사하지 않은 것 |
|---|---|---|---:|---|
| [AI-WorkPilot](https://github.com/junwoo1206112/AI-WorkPilot) | `2f7ea7b53d72ada78e775ee6aa2590347147b52d` | README, `app/workflow-core.mjs`, `app/api/runs/route.ts`, `db/schema.ts`, OpenSpec/인터뷰 문서 | 승인 상태·실행·재시도·감사 **개념**, 상태 전이 아이디어, 20초 요약 형식 | Next.js/React/D1/Drizzle 코드, UI 컴포넌트, 프롬프트 |
| [Procurement Rules RAG Copilot](https://github.com/junwoo1206112/procurement-rules-rag-copilot) | `056fa89d60719d338a972ab4de234d6c5cf7b02a` | README, `app/retrieval.py`, `app/answering.py`, `app/schemas.py`, `app/store.py`, `tests/`, `data/procurement-rules-manifest.json` | 공개 규정의 문서명·URL·이용 근거, BM25/coverage **개념**, insufficient evidence 아이디어, 평가 케이스 유형 | 수집 원문, 임베딩 모델, 외부 API 수집기, FastAPI 라우트/프론트 코드 |

## 2. 라이선스 확인 결과

- 두 기준 저장소 모두 루트에 `LICENSE` 파일이 없었다. `package.json`에도 `license` 필드가 없었다(검토 시점).
- 따라서 **소스 코드를 한 줄도 복사하지 않았다**. 코드는 새로 작성했고, 참고한 것은 공개 README/문서의 구조와 테스트 아이디어, 공개 메타데이터뿐이다.
- 이 저장소의 새 코드는 `LICENSE`의 MIT License를 따른다.
- 공개 행정규칙 본문은 재배포하지 않았다. 제목·URL·검토용 요약만 `data/public_corpus/`에 수록했고, 이용 근거는 `SOURCES.md`에 기록했다.

> 이 확인은 법률 자문이 아니다. 공개 배포 전에는 각 원문의 최신 이용 조건과 저작권법 제7조 적용 범위를 별도로 검토해야 한다.

## 3. 파일 단위 매핑

| 새 파일 | 참고한 아이디어 | 새로 결정한 것 |
|---|---|---|
| `app/domain/state.py` | AI-WorkPilot `nextState` 표 | `EXECUTING`/`REJECTED` 추가, 10개 상태 전수 테스트 |
| `app/domain/models.py` | 승인·실행·감사 레코드 | `GatePass` seal, evidence snapshot/fingerprint |
| `app/services/retrieval.py` | Procurement `HybridRetriever`의 BM25·coverage | 임베딩 제거, 조사 제거·bigram, 절대 점수, min-max 폐기 |
| `app/services/evidence_gate.py` | Procurement의 citation validation/insufficient | 점수·URL·발췌·유효기간·상충·공개/합성 분리 |
| `app/services/planner.py` | AI-WorkPilot의 deterministic plan | 자유 텍스트 금지, `allowed_action` allowlist, canonical hash |
| `app/services/execution.py` | AI-WorkPilot의 mock tool | `create_demo_draft`/`simulate_notification`만, 실패 주입 |
| `app/services/audit.py` | AI-WorkPilot timeline | seq·prev_hash·event_hash, append-only trigger, 거부 감사 |
| `app/db.py` | D1 스키마 개념 | SQLite WAL/PRAGMA/`BEGIN IMMEDIATE`, unique 제약, trigger |
| `app/templates/`, `app/static/` | 두 프로젝트의 단일 흐름 UI | 외부 CDN 없는 vanilla JS, CSP, `textContent`, 409 인라인 노출 |
| `evals/` | Procurement의 고정 평가 | EG-01~14, dev/holdout 분리, 실행형 JSON DSL |
| `tests/` | 두 프로젝트의 테스트 문화 | negative-path 우선, 동시성·변조·오프라인·문서 계약 |

## 4. 의도적으로 재사용하지 않은 것

- Procurement의 실제 수집 코퍼스/청크(`collected-chunks.json` 등)와 원문 PDF/HWPX: 저장소에 없고, 이용 조건 재확인이 필요하다.
- 임베딩(`sentence-transformers`), Ollama, LLM 답변 생성: 이 프로젝트의 비목표이며, 재현성·비용·환경 의존성을 제거했다.
- AI-WorkPilot의 Next.js/D1/React UI: 스택을 Python/FastAPI/SQLite로 단순화해 2분 리뷰와 오프라인 실행을 우선했다.
- 두 저장소의 Git 이력/브랜치: 새 저장소는 별도 이력으로 시작한다. 기준 저장소는 `references/`에만 두고 `.gitignore`로 새 저장소에서 제외한다.

## 5. 검증

- 코퍼스 해시: `data/public_corpus/SOURCES.md`와 `evals/results.json`의 `corpus_sha256`이 일치해야 한다.
- `tests/test_docs.py`가 README 고지, SOURCES 해시, 문서 존재, 비밀정보 패턴 부재를 검사한다.
- `tests/test_evals.py`가 EG-01~14 전체 통과와 결과 파일의 코퍼스/설정 hash를 검사한다.
- 기준 저장소는 `references/` 아래 읽기 전용 사본이며, 이 프로젝트의 실행·테스트 경로에서 import하지 않는다.
