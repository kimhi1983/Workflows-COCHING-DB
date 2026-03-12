# COCHING AI 가이드처방 스킬 파이프라인

> 6단계 순차 실행. 각 스킬은 이전 스킬의 출력을 입력으로 받는다.

```
[처방 요청]
    │
    ▼
[1] formulation.md          ← 처방 설계 (투입 원료 선정 + wt% 배분)
    │
    ▼
[2] compound-expansion.md   ← 복합성분 전개 + INCI 합산
    │
    ▼
[3] precision-arithmetic.md ← 정수 연산 + 밸런스 역산 + 3단계 검증
    │
    ▼
[4] ingredients.md          ← 성분 안전성 분석
    │
    ▼
[5] regulation.md           ← 규제 적합성 검토 (한국/EU/FDA)
    │
    ▼
[6] qa-validation.md        ← 17개 자동 체크 + 최종 출력 승인
    │
    ▼
[출력] 처방서(제조용) + 전성분(규제용)
```

## 슬래시 커맨드
- `/guide-formula <제품설명>` — 6단계 파이프라인 자동 실행
