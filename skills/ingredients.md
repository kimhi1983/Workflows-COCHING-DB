# INGREDIENTS SKILL — 성분 안전성 분석

> COCHING AI 가이드처방 파이프라인 Step 4/6
> 처방 내 성분별 안전성·자극성·호환성 검증

---

## 1. 트리거 조건
- precision-arithmetic 검증 통과 후 자동 실행
- 처방 내 모든 INCI 성분에 대해 순회 검사

## 2. 검사 항목

### 2.1 배합 한도 확인
```
각 성분별 한국 식약처 / EU / FDA 배합 한도 검증:
  - 자외선 차단제: ZnO ≤25%, TiO2 ≤25%, 유기자차 각 성분별 한도
  - 방부제: Phenoxyethanol ≤1.0%, Methylparaben ≤0.4% 등
  - 색소: 허용 색소 목록 및 부위별 사용 제한
  - 기능성 원료: 배합 농도 범위 (예: Niacinamide 2-5%)
```

### 2.2 피부타입별 적합성
```
민감성:
  ✅ 권장: 무기자차, Centella, Allantoin, Bisabolol, Ceramide
  ❌ 회피: 알코올(고농도), 강한 계면활성제, 합성 향료, 레티놀(고농도)

지성:
  ✅ 권장: Niacinamide, Salicylic Acid, 경량 오일, Zinc PCA
  ❌ 회피: 중질 오일(Mineral Oil 고농도), 코메도제닉 성분

건성:
  ✅ 권장: Ceramide, Squalane, Shea Butter, Hyaluronic Acid
  ❌ 회피: 알코올(탈수), 강한 세정제

복합성:
  ✅ 권장: 경-중 오일 혼합, Hyaluronic Acid, Niacinamide
  ❌ 회피: 극단적 보습/탈지 성분
```

### 2.3 성분 간 호환성
```
비호환 조합 체크:
  - Vitamin C (Ascorbic Acid) + Niacinamide: pH 충돌 주의 (pH 3.5 vs 5-7)
  - Retinol + AHA/BHA: 과도한 자극 위험
  - Vitamin C + 금속 이온: 산화 촉진
  - 양이온 계면활성제 + 음이온 계면활성제: 침전
```

### 2.4 알레르기 유발 성분
```
EU 26종 알레르기 유발 향료 감지:
  Limonene, Linalool, Citronellol, Geraniol, Citral,
  Eugenol, Coumarin, ... (26종)
  → 감지 시 별도 표기 안내
```

## 3. 출력
- 성분별 안전성 등급 (SAFE / CAUTION / RESTRICT)
- 배합 한도 초과 경고
- 피부타입 부적합 성분 경고
- 비호환 조합 경고

## 4. 다음 스킬
→ `regulation.md` (규제 적합성 검토)
