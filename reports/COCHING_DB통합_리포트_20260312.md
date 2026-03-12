# COCHING AI — 기존 DB 자료 통합 리포트

> 작업일: 2026-03-12
> 작업자: Claude Code (CTO)

---

## 1. 작업 목표

기존 coching 스키마의 레거시 DB(t_coos_prod 16,138건, t_coos_ingd 25,643건)와
복합원료 마스터 데이터를 워크플로우 DB(public 스키마)에 통합하여
가이드 처방 생성 시 전체 데이터를 참조할 수 있도록 한다.

```
변경 전:
  워크플로우 DB (public)              기존 DB (coching 스키마)
  ├── ingredient_master (430건)      ├── t_coos_ingd (25,643건) ← 격리
  ├── product_master (20건)          ├── t_coos_prod (16,138건) ← 격리
  └── regulation_cache (609건)       └── t_hw_prod_dic          ← 미사용

변경 후:
  워크플로우 DB (public) — 통합 완료
  ├── ingredient_master (25,520건)   ← 25,090건 이관 통합
  ├── product_master (16,026건)      ← 16,006건 이관 통합
  ├── regulation_cache (3,523건)     ← 1,457건 규제정보 추가
  ├── compound_master (15건)         ← 신규 생성
  ├── guide_cache (215건)
  └── guide_cache_copy (10건)
```

---

## 2. 신규 테이블: compound_master

### 스키마
```sql
CREATE TABLE compound_master (
    id              SERIAL PRIMARY KEY,
    trade_name      VARCHAR(255) NOT NULL UNIQUE,
    supplier        VARCHAR(255),
    category        VARCHAR(100),
    total_fraction  NUMERIC(5,3) DEFAULT 1.000,
    components      JSONB NOT NULL,    -- [{inci, fraction, korean}]
    notes           TEXT,
    source          VARCHAR(50) DEFAULT 'manual',
    created_at      TIMESTAMP DEFAULT now(),
    updated_at      TIMESTAMP DEFAULT now()
);
```

### 등록된 복합원료 (15건)

| # | 상품명 | 공급사 | 카테고리 | 구성 성분 수 |
|---|--------|--------|----------|-------------|
| 1 | Bentone Gel MIO | Elementis | 실리콘 겔베이스 | 3 |
| 2 | DC 9040 Silicone Elastomer | Dow | 실리콘 에멀전 | 2 |
| 3 | Olivem 1000 | Hallstar | O/W 유화제 | 2 |
| 4 | Emulsimousse | Gattefossé | O/W 유화제 | 3 |
| 5 | Euxyl PE 9010 | Schülke | 방부제 블렌드 | 2 |
| 6 | Optiphen Plus | Ashland | 방부제 블렌드 | 3 |
| 7 | Tinosorb M | BASF | 자외선차단 분산체 | 3 |
| 8 | Sepigel 305 | Seppic | 증점 유화제 | 3 |
| 9 | Lanol 99 | Seppic | 에스터 오일 블렌드 | 2 |
| 10 | Montanov 68 | Seppic | O/W 유화제 | 2 |
| 11 | Simulgel EG | Seppic | 증점 안정제 | 3 |
| 12 | Tego Care PBS 6 | Evonik | W/S 유화제 | 2 |
| 13 | Dermofeel PA-3 | Evonik | 킬레이트제 | 3 |
| 14 | Sharomix 705 | Sharon | 방부제 블렌드 | 2 |
| 15 | Easynov | Seppic | W/O 유화제 | 3 |

---

## 3. 데이터 이관 결과

### ingredient_master (원료 마스터)
| source | 건수 | 비고 |
|--------|------|------|
| coching_legacy | 25,090 | t_coos_ingd에서 이관 |
| GEMINI_COLLECT | 429 | n8n 워크플로우 수집 |
| mfds_korea | 1 | 식약처 |
| **합계** | **25,520** | |

이관 데이터: INCI명, 한글명, CAS번호, AI 설명문

### product_master (제품 마스터)
| source | 건수 | 비고 |
|--------|------|------|
| coching_legacy | 16,006 | t_coos_prod에서 이관 |
| gemini_search | 20 | n8n 워크플로우 수집 |
| **합계** | **16,026** | |

이관 데이터: 브랜드, 제품명, 카테고리, 전성분(INCI), mappedINCIs

### regulation_cache (규제 정보)
| source | 건수 | 비고 |
|--------|------|------|
| 기존 | 609 | n8n 워크플로우 수집 |
| coching_legacy | 1,457 | t_coos_ingd EU 규제정보 이관 |
| 기타 | 1,457 | |
| **합계** | **3,523** | |

---

## 4. 전체 DB 현황 (통합 후)

| 테이블 | 건수 | 용도 |
|--------|------|------|
| **ingredient_master** | **25,520** | 원료 마스터 (INCI, 한글, CAS) |
| **product_master** | **16,026** | 제품 마스터 (브랜드, 전성분) |
| **regulation_cache** | **3,523** | 규제 정보 (배합한도, 금지성분) |
| **compound_master** | **15** | 복합원료 (블렌드 구성 비율) |
| **guide_cache** | **215** | 카테고리×피부타입 가이드 처방 |
| **guide_cache_copy** | **10** | 제품카피 역처방 |
| **coching_knowledge_base** | **461** | AI 지식베이스 |
| 합계 | **45,770** | |

---

## 5. 워크플로우 연동

### 변경된 워크플로우 (7개)

| 워크플로우 | 복합원료 노드 | 프롬프트 연동 |
|-----------|-------------|-------------|
| v2.3-A 기초화장 | ✅ 추가 | ✅ compound_master 참조 |
| v2.3-B 세정 | ✅ 추가 | ✅ compound_master 참조 |
| v2.3-C 선케어 | ✅ 추가 | ✅ compound_master 참조 |
| v2.3-D 색조 | ✅ 추가 | ✅ compound_master 참조 |
| v2.3-E 두발 | ✅ 추가 | ✅ compound_master 참조 |
| v2.3-F 기타 | ✅ 추가 | ✅ compound_master 참조 |
| 제품카피 v1.0 | ✅ 추가 | ✅ compound_master 참조 |

### 워크플로우 데이터 흐름 (변경 후)

```
[n8n 스케줄 트리거]
    │
    ├─→ 📦 원료 DB 조회 (ingredient_master: 25,520건)
    ├─→ 📋 규제 DB 조회 (regulation_cache: 3,523건)
    ├─→ 📦 참조제품 조회 (product_master: 16,026건)
    ├─→ 📦 복합원료 DB 조회 (compound_master: 15건)  ← NEW
    │
    ▼
[🧠 Claude 프롬프트 구성]
    — 6단계 스킬 파이프라인 적용
    — 복합원료 DB 참조 포함
    │
    ▼
[🧠 Claude 처방 생성 (SSH)]
    │
    ▼
[🔄 처방 파싱 & 검증]
    — 정수 연산 검증 (int_sum == 10000)
    — skill_pipeline 메타데이터 삽입
    │
    ├─→ 💾 guide_cache / guide_cache_copy 저장
    ├─→ 💾 학습파일 저장 (ai-server/data/learning/)
    └─→ 💾 백업 저장 (backup/formulations/)
```

---

## 6. 자동 백업 업데이트

백업 대상 테이블 (30분마다):
```
기존: ingredient_master, product_master, regulation_cache,
      coching_knowledge_base, ingredient_properties,
      ingredient_functions, workflow_log,
      collection_progress, cosmetics_company

추가: compound_master, guide_cache, guide_cache_copy
```

---

## 7. 실행 스크립트

| 스크립트 | 위치 | 용도 |
|---------|------|------|
| migrate_legacy_db.py | backup/scripts/ | 레거시 DB → public 스키마 이관 |
| update_workflow_compound_db.py | backup/scripts/ | 워크플로우에 compound_master 연동 |
| update_workflow_skills.py | backup/scripts/ | 6단계 스킬 파이프라인 적용 (이전 작업) |

---

## 8. 데이터 활용 효과

| 항목 | 변경 전 | 변경 후 |
|------|---------|---------|
| 원료 참조 DB | 430건 | **25,520건** (×59배) |
| 제품 참조 DB | 20건 | **16,026건** (×801배) |
| 규제 정보 | 609건 | **3,523건** (×5.8배) |
| 복합원료 DB | 없음 | **15건 (신규)** |
| 가이드 처방 시 참조 범위 | 제한적 | **전체 DB 통합 참조** |
