# 한국어 검색 소규모 ablation

> 18개 수작업 질의·동일 코퍼스·동일 gold 문서 ID. 성능 벤치마크가 아니라 설계 선택의 회귀 근거다.

- 코퍼스: `documents.json` (14문서, SHA-256 `9cecefc55c61f43391f08f0afd0fbd50310151ae5c2affecbd9252d30b4b16a9`)
- 지표: Recall@3, MRR@3
- `word_exact`: 조사 제거 없음, 단어 BM25만
- `particle`: 조사 제거, 단어 BM25만
- `particle+bigram (current)`: 조사 제거 + 음절 bigram BM25 + 절대 coverage

## 요약

| 변형 | Recall@3 | MRR@3 |
|---|---:|---:|
| word_exact | 0.861 | 0.852 |
| particle | 0.972 | 0.963 |
| particle+bigram (current) | 1.000 | 1.000 |

## 질의별 결과

| 질의 | gold | word_exact | particle | current |
|---|---|---|---|---|
| 계약보증금 징수 기준 | pps-facility-contract-guarantee | R@3=1.00, MRR=0.33<br>`fixture-goods-guarantee-5, fixture-goods-guarantee-10, pps-facility-contract-guarantee` | R@3=1.00, MRR=0.33<br>`fixture-goods-guarantee-5, fixture-goods-guarantee-10, pps-facility-contract-guarantee` | R@3=1.00, MRR=1.00<br>`pps-facility-contract-guarantee, fixture-goods-guarantee-5, fixture-goods-guarantee-10` |
| 지연배상금 산정 | pps-facility-contract-delay | R@3=1.00, MRR=1.00<br>`pps-facility-contract-delay, pps-price-survey, pps-facility-qualification` | R@3=1.00, MRR=1.00<br>`pps-facility-contract-delay, pps-price-survey, pps-facility-qualification` | R@3=1.00, MRR=1.00<br>`pps-facility-contract-delay, pps-price-survey, pps-facility-qualification` |
| 물가변동 사전검토 자료 | pps-price-change | R@3=1.00, MRR=1.00<br>`pps-price-change` | R@3=1.00, MRR=1.00<br>`pps-price-change` | R@3=1.00, MRR=1.00<br>`pps-price-change, pps-stockpile-operation, pps-foreign-purchase` |
| 입찰참가자격 등록 서류 | pps-registration-team | R@3=1.00, MRR=1.00<br>`pps-registration-team` | R@3=1.00, MRR=1.00<br>`pps-registration-team` | R@3=1.00, MRR=1.00<br>`pps-registration-team, pps-foreign-purchase, pps-facility-qualification` |
| 비축물자 공급 신청 | pps-stockpile-operation | R@3=1.00, MRR=1.00<br>`pps-stockpile-operation` | R@3=1.00, MRR=1.00<br>`pps-stockpile-operation` | R@3=1.00, MRR=1.00<br>`pps-stockpile-operation, pps-registration-team` |
| 외자구매 입찰 절차 | pps-foreign-purchase | R@3=1.00, MRR=1.00<br>`pps-foreign-purchase` | R@3=1.00, MRR=1.00<br>`pps-foreign-purchase` | R@3=1.00, MRR=1.00<br>`pps-foreign-purchase, pps-registration-team, pps-design-competition` |
| 적격심사 평가 항목 | pps-facility-qualification | R@3=1.00, MRR=1.00<br>`pps-facility-qualification, pps-design-competition, pps-foreign-purchase` | R@3=1.00, MRR=1.00<br>`pps-facility-qualification, pps-design-competition, pps-foreign-purchase` | R@3=1.00, MRR=1.00<br>`pps-facility-qualification, pps-design-competition, pps-facility-safety` |
| 설계공모 심사위원 | pps-design-competition | R@3=1.00, MRR=1.00<br>`pps-design-competition` | R@3=1.00, MRR=1.00<br>`pps-design-competition` | R@3=1.00, MRR=1.00<br>`pps-design-competition, pps-facility-qualification` |
| 안전점검 수행기관 지정 | pps-facility-safety | R@3=1.00, MRR=1.00<br>`pps-facility-safety` | R@3=1.00, MRR=1.00<br>`pps-facility-safety` | R@3=1.00, MRR=1.00<br>`pps-facility-safety, pps-foreign-purchase, pps-price-change` |
| 가격조사 예정가격 | pps-price-survey | R@3=1.00, MRR=1.00<br>`pps-price-survey` | R@3=1.00, MRR=1.00<br>`pps-price-survey` | R@3=1.00, MRR=1.00<br>`pps-price-survey, pps-stockpile-operation` |
| 물품 계약보증금 비율 | fixture-goods-guarantee-10, fixture-goods-guarantee-5 | R@3=1.00, MRR=1.00<br>`fixture-goods-guarantee-5, fixture-goods-guarantee-10, fixture-goods-guarantee-old` | R@3=1.00, MRR=1.00<br>`fixture-goods-guarantee-5, fixture-goods-guarantee-10, fixture-goods-guarantee-old` | R@3=1.00, MRR=1.00<br>`fixture-goods-guarantee-10, fixture-goods-guarantee-5, fixture-goods-guarantee-old` |
| 무효 URL 테스트 조항 | fixture-missing-url | R@3=1.00, MRR=1.00<br>`fixture-missing-url` | R@3=1.00, MRR=1.00<br>`fixture-missing-url` | R@3=1.00, MRR=1.00<br>`fixture-missing-url` |
| 계약보증금과 지연배상금을 확인 | pps-facility-contract-guarantee, pps-facility-contract-delay | R@3=0.50, MRR=1.00<br>`pps-facility-contract-delay` | R@3=0.50, MRR=1.00<br>`pps-facility-contract-delay, fixture-goods-guarantee-5, fixture-goods-guarantee-10` | R@3=1.00, MRR=1.00<br>`pps-facility-contract-delay, pps-facility-contract-guarantee, fixture-goods-guarantee-5` |
| 물가변동으로 | pps-price-change | R@3=0.00, MRR=0.00<br>`` | R@3=1.00, MRR=1.00<br>`pps-price-change` | R@3=1.00, MRR=1.00<br>`pps-price-change, pps-stockpile-operation` |
| 비축물자의 공급을 | pps-stockpile-operation | R@3=1.00, MRR=1.00<br>`pps-stockpile-operation` | R@3=1.00, MRR=1.00<br>`pps-stockpile-operation` | R@3=1.00, MRR=1.00<br>`pps-stockpile-operation` |
| 외자구매를 | pps-foreign-purchase | R@3=1.00, MRR=1.00<br>`pps-foreign-purchase` | R@3=1.00, MRR=1.00<br>`pps-foreign-purchase` | R@3=1.00, MRR=1.00<br>`pps-foreign-purchase` |
| 설계공모를 | pps-design-competition | R@3=1.00, MRR=1.00<br>`pps-design-competition` | R@3=1.00, MRR=1.00<br>`pps-design-competition` | R@3=1.00, MRR=1.00<br>`pps-design-competition` |
| 안전점검을 | pps-facility-safety | R@3=0.00, MRR=0.00<br>`` | R@3=1.00, MRR=1.00<br>`pps-facility-safety` | R@3=1.00, MRR=1.00<br>`pps-facility-safety, pps-foreign-purchase` |

## 해석과 한계

- 이 표는 같은 14문서 안에서 두 구현 선택이 gold 문서를 top-3에 올리는지 비교한 것이다.
- 코퍼스가 작아 ID/paths가 기억되기 쉽고, 실제 조달 질의 분포를 대표하지 않는다.
- `particle+bigram`은 조사가 붙은 한국어 질의에서 단어 exact match보다 높은 Recall을 보이도록 설계했지만, 이 18개 질의에서는 차이가 작을 수 있다.
- LLM/RAG 품질, 문서 수가 큰 환경의 성능, 법적 정확성을 주장하지 않는다.
