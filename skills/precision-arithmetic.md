# PRECISION-ARITHMETIC SKILL — 정수 연산 + 밸런스 역산

> COCHING AI 가이드처방 파이프라인 Step 3/6
> 부동소수점 오차 방지를 위한 정수 연산 체계 + 밸런스 역산 + 3단계 검증

---

## 1. 핵심 원칙

**소수점 직접 합산 절대 금지** — 모든 wt%를 정수(×100)로 변환 후 연산.

```
❌ 금지: 0.85 + 0.30 + 0.30 = 1.4500000000000002 (부동소수점 오차)
✅ 필수: 85 + 30 + 30 = 145 → 145/100 = 1.45% (정확)
```

## 2. 정수 변환 규칙

```
int_value = round(wt_percent × 100)

예시:
  38.00% → 3800
   0.85% →   85
   0.05% →    5
  15.00% → 1500
```

- 모든 wt%는 소수점 둘째 자리까지 (0.01% 단위)
- int_value는 항상 정수 (반올림)
- 총합 목표: **10000** (= 100.00%)

## 3. 밸런스 역산

정제수(Aqua)는 밸런스 성분으로 역산한다.

```
balance_excluded_sum = sum(Aqua 제외 모든 성분의 int_value)
aqua_int = 10000 - balance_excluded_sum
aqua_wt_percent = aqua_int / 100
```

### 복합성분 내 Aqua 처리
```
복합 전개 Aqua ≠ 밸런스 Aqua

처리 순서:
  1. 복합 전개 Aqua를 별도 변수(compound_aqua_int)로 관리
  2. 밸런스 역산 시 compound_aqua_int를 balance_excluded_sum에 포함
  3. balance_aqua_int = 10000 - balance_excluded_sum
  4. 전성분 출력 시: total_aqua = balance_aqua_int + compound_aqua_int
```

## 4. 3단계 검증

```
# 검증1: 정수합 = 10000
assert sum(all_int_values) == 10000

# 검증2: wt%합 = 100.00
assert sum(all_int_values) / 100 == 100.00

# 검증3: 역산 교차 검증
assert aqua_int == 10000 - sum(non_aqua_int_values)
```

3단계 모두 통과해야만 다음 스킬로 진행.

## 5. Largest Remainder Method (반올림 오차 보정)

복합성분 전개 시 반올림으로 합계가 ±1 차이날 때 적용.

```
절차:
  1. 각 성분의 정수 변환값과 원래값의 차이(remainder) 계산
  2. 차이값을 내림차순 정렬
  3. 부족분만큼 remainder가 큰 성분부터 +1 조정
  4. 초과분만큼 remainder가 작은 성분부터 -1 조정

예시:
  성분A: 4.25% → int=425, remainder=0.00 → 425
  성분B: 0.50% → int= 50, remainder=0.00 →  50
  성분C: 0.26% → int= 26, remainder=0.00 →  26 (실제 0.255 → 반올림)
  합계: 501 (목표 500) → 성분C에서 -1 → 25
```

## 6. 출력 형식

```
| INCI Name | wt% | int_value | 비고 |
|-----------|-----|-----------|------|
| Water (Aqua) | 38.00 | 3800 | 밸런스 역산 |
| Zinc Oxide | 15.00 | 1500 | |
| ... | ... | ... | |
| 합계 | 100.00 | 10000 | ✅ 3단계 검증 통과 |
```

## 7. 다음 스킬
→ `ingredients.md` (성분 안전성 분석)
