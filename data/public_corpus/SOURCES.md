# 공개 코퍼스 출처와 사용 조건

> 코퍼스 버전: `1.0.0`  
> 파일: `data/public_corpus/documents.json`  
> SHA-256: `9cecefc55c61f43391f08f0afd0fbd50310151ae5c2affecbd9252d30b4b16a9`  
> 문서 수: 14 (공개 행정규칙 요약 10, 합성 fixture 4)

## 1. 수록 원칙

- 원문 문서를 복제하지 않는다. 공개 행정규칙은 **제목·발행기관·원문 URL**과 작성자가 정리한 **검토용 요약 발췌**만 수록한다.
- 요약 발췌는 법적 효력을 주장하지 않는다. 실제 기준은 반드시 원문과 최신 시행일을 확인해야 한다.
- 공개 문서의 이용 조건이 불명확한 자료, 개인정보, API 키, 수집 원문은 저장소에 넣지 않는다.
- 상충·실패·누락 URL 같은 게이트 검증용 자료는 `source_tier=synthetic_fixture`로 명시하고, 실제 조달 기준이 아님을 문서와 UI에 표시한다.

## 2. 공개 행정규칙 요약 (10)

| document_id | 문서명 | 조항 | 원문 URL | 이용 근거 |
|---|---|---|---|---|
| `pps-facility-contract-guarantee` | 조달청 시설공사 계약업무 처리규정 | 계약보증금 | https://www.law.go.kr/LSW/admRulLsInfoP.do?admRulSeq=2100000281276 | 저작권법 제7조 제2호 |
| `pps-facility-contract-delay` | 조달청 시설공사 계약업무 처리규정 | 지연배상금 | https://www.law.go.kr/LSW/admRulLsInfoP.do?admRulSeq=2100000281276 | 저작권법 제7조 제2호 |
| `pps-price-change` | 조달청 시설분야 물가변동 사전검토 처리규정 | 물가변동 사전검토 | https://www.law.go.kr/LSW/admRulLsInfoP.do?admRulSeq=2100000274820 | 저작권법 제7조 제2호 |
| `pps-registration-team` | 조달등록팀 운영규정 | 입찰참가자격 등록 | https://www.law.go.kr/LSW/admRulLsInfoP.do?admRulSeq=2100000275710 | 저작권법 제7조 제2호 |
| `pps-stockpile-operation` | 조달청 비축사업 운영규정 | 비축물자 공급 | https://www.law.go.kr/LSW/admRulLsInfoP.do?admRulSeq=2100000274846 | 저작권법 제7조 제2호 |
| `pps-foreign-purchase` | 조달청 외자구매업무 처리규정 | 외자구매 절차 | https://www.law.go.kr/LSW/admRulLsInfoP.do?admRulSeq=2100000276276 | 저작권법 제7조 제2호 |
| `pps-facility-qualification` | 조달청 시설공사 적격심사세부기준 | 적격심사 | https://www.law.go.kr/LSW/admRulLsInfoP.do?admRulSeq=2100000281312 | 저작권법 제7조 제2호 |
| `pps-design-competition` | 조달청 건축 설계공모 운영기준 | 설계공모 심사 | https://www.law.go.kr/LSW/admRulLsInfoP.do?admRulSeq=2100000264852 | 저작권법 제7조 제2호 |
| `pps-facility-safety` | 조달청 시설공사 안전점검 수행기관 지정 세부기준 | 안전점검 수행기관 지정 | https://www.law.go.kr/LSW/admRulLsInfoP.do?admRulSeq=2100000248956 | 저작권법 제7조 제2호 |
| `pps-price-survey` | 조달청 가격조사 업무규정 | 가격조사 | https://www.law.go.kr/LSW/admRulLsInfoP.do?admRulSeq=2100000226962 | 저작권법 제7조 제2호 |

### 확인 절차

1. 기준 저장소 `procurement-rules-rag-copilot`의 `data/procurement-rules-manifest.json`에서 문서명·원문 URL·이용 근거를 확인했다.
2. 원문은 내려받아 저장하지 않았고, 요약 발췌만 새로 작성했다.
3. `law.go.kr` 도메인과 `https` 스킴만 공개 출처로 인정하도록 게이트의 URL 검증 규칙을 고정했다.
4. 요약 내용의 정확성·최신성은 이 데모의 보증 범위가 아니다. README와 UI에 "검토용 요약"임을 표시한다.

## 3. 합성 fixture (4)

| document_id | 목적 | 공개 문서 여부 |
|---|---|---|
| `fixture-goods-guarantee-10` | 동일 주제·동일 범위에서 값이 다른 상충 근거 A | **아님** (합성) |
| `fixture-goods-guarantee-5` | 동일 주제·동일 범위에서 값이 다른 상충 근거 B | **아님** (합성) |
| `fixture-goods-guarantee-old` | 유효기간이 지난 근거 제외 검증 | **아님** (합성) |
| `fixture-missing-url` | 출처 URL 누락 인용 차단 검증 | **아님** (합성) |

합성 fixture의 `source_url`은 `example.com` 예약 도메인을 사용한다. URL 형식 검증은 통과하지만 `source_tier`와 UI 배지로 공개 근거가 아님을 구분한다. 합성 fixture의 수치(10%, 5%, 7%)는 실제 조달 기준이 아니다.

## 4. 사용 조건 재확인 결과

- 기준 저장소 두 개(`AI-WorkPilot`, `procurement-rules-rag-copilot`)에는 검토 시점 기준 `LICENSE` 파일이 없었다. 따라서 **소스 코드를 복사하지 않았고**, 공개 문서·구조·테스트 아이디어만 참고했다. 자세한 내용은 `docs/source-map.md`를 따른다.
- 이 저장소의 새 코드는 별도로 작성했으며, 원문 행정규칙의 본문을 재배포하지 않는다.
- 공개 데모에서 수집·저장하는 사용자 입력은 업무 요청 텍스트뿐이며, 민감정보 패턴은 API에서 거부한다.

## 5. 코퍼스 변경 규칙

코퍼스를 수정하면 다음을 함께 갱신한다.

1. `documents.json`의 `corpus_version`
2. 이 문서의 SHA-256과 문서 수
3. `evals/results.json`의 `corpus_sha256` (재실행 시 자동 기록)
4. `docs/source-map.md`의 참조 설명

게이트의 URL 허용 도메인은 `app/config.py`에서 관리한다.
