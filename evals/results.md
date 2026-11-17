# 고정 평가 결과

- 앱 버전: `0.1.0`
- 코퍼스 SHA-256: `9cecefc55c61f43391f08f0afd0fbd50310151ae5c2affecbd9252d30b4b16a9`
- 게이트 설정 hash: `200ec1ef92c818f69b32904733cb6403220ca0eece18aa4de55f1740712b6f9d`
- 케이스 파일 SHA-256: `946e9ebf563dd4d49a0defb6a745710c3f3ddaad1e537fda342f9b409efe589d`
- 환경: Python 3.12.10 / Windows-11-10.0.26200-SP0
- 실행 시간: 633.8 ms

## 요약: 14/14 통과

| ID | 구분 | 결과 | 제목 | 실패 항목 |
|---|---|---|---|---|
| EG-01 | dev | PASS | 충분한 근거 → 계획 생성, 승인 대기 | - |
| EG-02 | dev | PASS | 부족한 근거 → 계획 없음 | - |
| EG-03 | dev | PASS | 빈 질의 → 검증 오류, run 생성 없음 | - |
| EG-04 | dev | PASS | URL 없는 인용 → 게이트 차단 | - |
| EG-05 | dev | PASS | 낮은 검색 점수 → 게이트 차단 | - |
| EG-06 | dev | PASS | 상충 근거 → 보류 및 사유 기록 | - |
| EG-07 | dev | PASS | 승인 전 실행 → 409, execution 없음 | - |
| EG-08 | dev | PASS | 승인 뒤 mock 실행 → EXECUTED, 감사 기록 | - |
| EG-09 | holdout | PASS | mock 2회 실패 → FAILED, 오류 사유 기록 | - |
| EG-10 | holdout | PASS | 1회 실패 → 자동 재시도 → EXECUTED, attempt 증가 | - |
| EG-11 | holdout | PASS | 중복 idempotency key → 기존 결과 반환 | - |
| EG-12 | holdout | PASS | 계획 변조 → plan hash 불일치로 실행 차단 | - |
| EG-13 | holdout | PASS | 중복 승인 → 409, approval 1건 유지 | - |
| EG-14 | holdout | PASS | 반려 → REJECTED, 실행 차단 | - |

## 해석 한계

- 이 평가는 LLM 생성 품질이나 실제 조달 정확도를 측정하지 않는다.
- 검색·게이트·상태 전이·멱등 실행 계약의 회귀 여부만 검증한다.
- 공개 문서 본문은 검토용 요약이며, 합성 fixture는 실제 기준이 아니다.
