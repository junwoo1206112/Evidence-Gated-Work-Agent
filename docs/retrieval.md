# 한국어 검색 설계와 ablation

> 이 문서는 “검색이 좋다”를 주장하지 않는다. **왜 임베딩 없이 결정론 검색을 선택했고, 어떤 실패를 막는지**를 재현 가능한 근거로 남긴다.

## 1. 선택

| 선택 | 이유 | 포기한 것 |
|---|---|---|
| lexical BM25 + coverage | 모델 다운로드·GPU·캐시 없이 오프라인 재현 | 동의어·문맥 유사도 |
| 한국어 조사 제거 | “계약보증금과” 같은 실제 질의 형태 대응 | 완전한 형태소 분석 |
| 음절 bigram | 조사·활용형이 달라도 부분 일치 | 빠른 인덱스 크기(코퍼스가 작아 무시 가능) |
| 절대 점수 | min-max 정규화로 얇은 코퍼스의 모든 후보가 1.0이 되는 문제 방지 | 코퍼스별 점수 스케일 자동 보정 |
| top-k = 5 | 2분 데모에서 후보와 차단 사유를 모두 보여줌 | 대규모 검색 지연 최적화 |

## 2. 토크나이저

```text
normalize_text: NFC → zero-width 제거 → NBSP→공백 → 공백 축약
words: [가-힣]+ | [a-z0-9]+
stopwords: 문법 조사 + 요청 동사(확인해/작성해줘/알림/초안 등)
strip_particle: 으로/에서/에게/까지/부터/보다/처럼/만큼/을/를/은/는/이/가/과/와/로/에/의/도/만
index tokens: 단어(길이≥2) + 한글 음절 bigram
```

예:

- `계약보증금과` → `계약보증금`
- `지연배상금을` → `지연배상금`
- `기준으로` → `기준`
- `계약보증금` → `계약, 약보, 보증, 증금`

## 3. 점수

```text
coverage(term) = Σ IDF(matched query terms) / Σ IDF(all query terms)
bm25_signal = min(1, BM25(query tokens, doc tokens) / 12)
score = 0.85 * coverage + 0.15 * bm25_signal
```

- 점수는 0..1 절대값이지만 **코퍼스 전체의 min-max 정규화를 하지 않는다**. 상위 문서가 1.0이어도 2위는 0.53처럼 남는다.
- 문서 매칭은 (a) 질의어가 문서 텍스트에 포함, (b) 문서 단어(길이≥2)가 질의어에 포함일 때 성립한다. 단일 음절 문서 토큰은 제외해 `"제"`가 `"제출서류"`에 걸리는 오탐을 막는다.
- 게이트 임계값은 `0.42`. 데모 질의의 실측 상위 점수는 아래와 같다.

| 질의 | 상위 결과 | 점수 | 결과 |
|---|---|---:|---|
| 충분 근거 | `pps-facility-contract-delay`, `...guarantee` | 1.00, 0.53 | 통과 |
| 상충 근거 | `fixture-goods-guarantee-10/5` | 1.00, 1.00 | conflict 차단 |
| 실패→재시도 | `...delay`, `...guarantee` | 0.75, 0.61 | 통과 |
| 부족 근거 | `pps-foreign-purchase` 등 | ≤ 0.16 | low_score 차단 |
| 낮은 점수 | `...guarantee` 등 | ≤ 0.17 | low_score 차단 |
| URL 누락 | `fixture-missing-url` | 1.00 | invalid_citation 차단 |

## 4. Micro-ablation (18 질의)

`python scripts/ablation.py`로 재생성한다. 동일 코퍼스·동일 gold 문서 ID에서 세 변형을 비교했다.

| 변형 | Recall@3 | MRR@3 |
|---|---:|---:|
| `word_exact` (조사 제거 없음, 단어 BM25) | 0.861 | 0.852 |
| `particle` (조사 제거, 단어 BM25) | 0.972 | 0.963 |
| `particle+bigram` (현재) | **1.000** | **1.000** |

전체 표는 [`retrieval-ablation.md`](retrieval-ablation.md).

해석:

- 조사가 붙은 질의(“계약보증금과”, “비축물자의 공급을”)에서 exact match는 top-3에 gold를 올리지 못했다.
- bigram은 단어 토큰이 놓친 활용형을 보완해 순위를 개선했다.
- **한계:** 18개 수작업 질의, 14문서, 정답 ID를 아는 조건이다. 실제 조달 질의 분포나 대규모 성능을 대표하지 않는다. 이 수치를 “RAG 품질”로 인용하면 안 된다.

## 5. 실패 모드

| 실패 | 현재 동작 | 다음 단계 |
|---|---|---|
| 동의어(“보증금” vs “담보금”) | 매칭 실패 → 근거 부족 | 동의어 사전/임베딩 adapter (정책 계층 유지) |
| 문서가 긴 경우 | 상위 5개만 노출 | 조항 단위 청킹 |
| 한국어 복합명사 | bigram으로 부분 완화 | 형태소 분석기 옵션 |
| 질의에 요청 동사가 많음 | stopword로 제거 | 사용자별 어휘 보정 |
| 도메인 밖 질의 | 후보 없음/낮은 점수 → 차단 | 그대로 유지(안전 기본값) |
| 상충 의미 판정 | tagged policy key만 | 별도 claim 비교 과제 |

## 6. 재현

```powershell
python scripts/ablation.py
python -m evals.run_evals
```

- 코퍼스 SHA-256과 gold ID는 `docs/retrieval-ablation.md`에 고정된다.
- 네트워크·임베딩 모델·API 키를 사용하지 않는다.
