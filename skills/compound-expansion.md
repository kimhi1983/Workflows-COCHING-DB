# COMPOUND-EXPANSION SKILL — 복합성분 전개

> COCHING AI 가이드처방 파이프라인 Step 2/6
> 복합성분 블렌드를 구성 INCI로 전개하고 동일 INCI 합산
> 원본: SKILL20260309.md (v1.0, 2026-03-09)

---

## 1. 왜 필요한가?

화장품 제조 현장에서는 단일 INCI 대신 **복합성분 블렌드(Compound/Blend)** 원료를 투입한다.
복합성분 전개 없이 처방서를 그대로 전성분으로 출력하면 **동일 INCI 중복·누락 오류** 발생.

```
[문제 상황]
처방서 투입 기준 (제조용)          전성분 표기 기준 (규제/소비자용)
─────────────────────────────    ──────────────────────────────────
Bentone Gel MIO        5.00%  →  Cyclopentasiloxane        4.25%
                               →  Disteardimonium Hectorite  0.50%
                               →  Propylene Carbonate        0.25%

Cyclopentasiloxane    15.00%  →  Cyclopentasiloxane       15.00%
                                                           ────────
                                  최종 전성분 표기          19.25%  ← 합산 필수!
```

## 2. 처리 흐름

```
Step 1: 처방서 로드 (투입 원료 기준)
Step 2: 복합성분 감지 (DB 조회 또는 TDS 기반)
Step 3: 복합성분 전개 — 구성 INCI × 투입량 계산
Step 4: INCI 합산 — 동일 INCI 중복 처리
Step 5: PRECISION-ARITHMETIC 연계 — 정수 변환 + 역산 + 3단계 검증
Step 6: 전성분 출력 (표기 기준)
```

## 3. 전개 계산 규칙

### 규칙 A — 전개 공식
```
구성_INCI_wt% = 복합원료_투입wt% × 구성_INCI_비율(fraction)
```

**예시 — Bentone Gel MIO 5.00% 투입 시**

| 구성 INCI | 비율 (fraction) | 전개 wt% |
|---|---|---|
| Cyclopentasiloxane | 0.850 | 5.00 × 0.850 = **4.25%** |
| Disteardimonium Hectorite | 0.100 | 5.00 × 0.100 = **0.50%** |
| Propylene Carbonate | 0.050 | 5.00 × 0.050 = **0.25%** |
| **소계** | **1.000** | **5.00%** ✅ |

> 구성 INCI 비율의 합계는 반드시 **1.000 (100%)** 이어야 한다.

### 규칙 B — INCI 합산 처리
동일 INCI가 여러 원료에서 발생하면 **전부 합산 후 단일 항목으로 처리**.

```
단일 투입   Cyclopentasiloxane  15.00%
복합 전개   Cyclopentasiloxane   4.25%  ← Bentone Gel MIO에서
복합 전개   Cyclopentasiloxane   2.00%  ← Dow Corning 9040에서
──────────────────────────────────────
합산 결과   Cyclopentasiloxane  21.25%  ← 전성분 표기는 이 값
```

### 규칙 C — 정수 연산 필수 (PRECISION-ARITHMETIC 연계)
```python
# ✅ 올바른 방법: 정수로 변환 후 합산
inci_sum_int = {}
for ingredient in formula:
    if ingredient.is_compound:
        for component in ingredient.components:
            ratio_int = round(component.fraction * ingredient.int_value)
            inci_sum_int[component.inci] = inci_sum_int.get(component.inci, 0) + ratio_int
    else:
        inci_sum_int[ingredient.inci] = inci_sum_int.get(ingredient.inci, 0) + ingredient.int_value

# ❌ 금지: 소수점 직접 합산 → 부동소수점 오차 누적
```

## 4. 복합성분 DB (등록 목록)

| # | 상품명 | 공급사 | 구성 성분 |
|---|--------|--------|-----------|
| 1 | Bentone Gel MIO | Elementis | Cyclopentasiloxane(0.850), Disteardimonium Hectorite(0.100), Propylene Carbonate(0.050) |
| 2 | Dow Corning 9040 | Dow | 실리콘 에멀전 (2종) |
| 3 | Olivem 1000 | Hallstar | O/W 유화제 (2종) |
| 4 | Emulsimousse | Gattefossé | O/W 유화제 (3종) |
| 5 | Euxyl PE 9010 | Schülke | 방부제 블렌드 (2종) |
| 6 | Optiphen Plus | Ashland | 방부제 블렌드 (3종) |
| 7 | Tinosorb M | BASF | 자외선차단 분산체 (3종) |
| 8 | Sepigel 305 | Seppic | 증점 유화제 (3종) |
| 9 | Lanol 99 | Seppic | 에스터 오일 블렌드 (2종) |
| 10 | 향료 (Fragrance) | — | 단일 표기 처리 |

> DB 미등록 복합성분 → 리서치 트리거 (TDS 기반 구성 비율 확인)

## 5. 주의사항

### 향료 처리
- Fragrance/Parfum은 전개하지 않음 → 단일 항목 표기
- EU 알레르기 유발 향료 26종은 별도 표기 의무

### 물(Aqua) 포함 복합성분
- 복합성분에서 전개된 Aqua는 밸런스 Aqua와 **별도 관리**
- 밸런스 역산은 **복합 전개 Aqua 제외 후** 실행
- 전성분 출력 시에만 합계 표시

### 동일 INCI 다른 등급
- Dimethicone 5cSt + Dimethicone 350cSt → "Dimethicone" 합산

### 반올림 오차 조정
- 전개 시 구성 성분 합이 int_value와 ±1 차이 가능
- → 가장 큰 비율의 구성 성분에 차이값 조정 (Largest Remainder Method)

## 6. 다음 스킬
→ `precision-arithmetic.md` (정수 연산 + 밸런스 역산 + 3단계 검증)
