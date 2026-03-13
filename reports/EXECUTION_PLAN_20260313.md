# COCHING 마이랩 로드맵 — 실행 계획서
**작성일**: 2026-03-13
**기준**: 통합 로드맵 v1.1 검토 결과

---

## 현재 상태 진단

### 이미 확보된 것 (강점)
| 자산 | 건수/상태 | 활용도 |
|---|---|---|
| **AI 서버 v2.4** (ai-server/main.py) | 운영 중 | Purpose Gate 통합 대상 |
| **6단계 스킬 파이프라인** | 문서화 완료 | 처방 생성 엔진 |
| **MyLab-Studio** (Vue 3, 독립 프로젝트) | 11개 위젯 완성 | Phase 5 프론트엔드 |
| **마스터플랜 v5** (VPS+PC 아키텍처) | 설계 확정 | 배포 가이드 |
| ingredient_master (INCI, 한글명, CAS) | 25,612건 | Phase 1 씨앗 데이터 |
| regulation_cache (5개 소스) | 3,903건 | 규제 검증 즉시 가능 |
| coching_knowledge_base (EWG/규제 상세) | 512건 | 검증 엔진 참조용 |
| guide_cache + guide_cache_copy | 829건 | 유사 처방 검색 시드 |
| product_master + product_ingredients | 16,456건 | 시판 제품 분석 |
| n8n 워크플로우 5개 (모두 정상) | 가동 중 | 데이터 자동 축적 |
| ingredient_master.ingredient_type | 487건 분류 | Purpose Gate 씨앗 |
| Prompt Caching | 구현됨 | 90% 비용 절감 |

### 아직 없는 것 (Gap)
| 항목 | 로드맵 가정 | 현실 | Gap |
|---|---|---|---|
| purpose_ingredient_map | MFDS 자동 매핑 3,000~5,000건 | 테이블 미존재 | Phase 1에서 생성 |
| ingredient_master.purpose | 21,696건 | **207건만** (0.8%) | 대부분 비어있음 |
| coching_knowledge_base | 21,696건 (MFDS) | **512건** | 로드맵 SQL 수정 필요 |
| product_categories (43개) | 정의만 | 미존재 | Phase 1에서 생성 |
| AI 서버 (Purpose Gate) | purpose_gate.py | 미존재 | Phase 1에서 구현 |
| 검증 엔진 | 8개 검증기 | 미존재 | Phase 2에서 구현 |
| 로컬 LLM | ollama + llama3.1 | 미설치 | Phase 3에서 설치 |
| 벡터 DB | ChromaDB | 미설치 | Phase 3에서 구축 |

---

## 로드맵 수정 사항

### 수정 1: MFDS 자동 매핑 SQL 현실화

로드맵의 가정:
```
coching_knowledge_base에서 MFDS 21,696건의 기능 분류를 추출
→ purpose_ingredient_map 자동 매핑
```

**현실**: coching_knowledge_base는 512건뿐. MFDS 원시 데이터는 ingredient_master에 있으나 `purpose` 필드가 207건만 채워져 있음.

**수정 방안**:
1. ingredient_master.ingredient_type (487건 분류)을 씨앗으로 활용
2. GEMINI_SAFETY의 primary_function (325건)을 추가 매핑
3. n8n 원료 수집 v7에서 수집 시 기능 분류를 함께 저장하도록 개선
4. Claude Code로 ingredient_master 25,612건의 기능 분류 배치 작업

### 수정 2: Phase 순서 재조정

원래: Phase 0 → 1 → 2 → 3 → 4 → 5 → 6
수정: **Phase 0 → 1A(DB) → 1B(데이터충전) → 2 → 3 → 4 → 5 → 6**

Phase 1A와 1B를 분리하는 이유:
- 1A (테이블 생성 + 구조): 1~2일이면 완료
- 1B (데이터 충전): 수천 건 매핑은 며칠~주 소요
- 1B는 n8n 배치로 자동화하면서 Phase 2와 병행 가능

---

## 즉시 실행 계획 (오늘~이번 주)

### Step 1: Phase 0 완료 확인 (30분)

```
[✓] DB 인벤토리 — 완료 (위 진단)
[✓] n8n 워크플로우 5개 정상 — 완료
[✓] Gemini 크론 비활성화 — 완료
[ ] N8N_HOST=0.0.0.0 설정 확인 (Tailscale 원격)
[ ] PostgreSQL 스키마 백업 (pg_dump --schema-only)
```

### Step 2: Phase 1A — DB 테이블 4개 생성 (이 세션에서 가능)

```sql
-- 1. product_categories (43개 제품 타입)
-- 2. formulation_purposes (14개 처방 목적)
-- 3. purpose_ingredient_map (핵심 매핑 테이블)
-- 4. category_purpose_link (연결 테이블)

실행: 이 세션에서 SQL 생성 + 실행
소요: ~1시간
```

### Step 3: Phase 1B — 데이터 충전 (배치 자동화)

```
접근법: 3단계로 나눠서 점진적 충전

1단계 (즉시): ingredient_master.ingredient_type 기반 매핑
   - ACTIVE → 해당 목적의 REQUIRED
   - HUMECTANT → MOISTURIZING의 RECOMMENDED
   - EMULSIFIER → 공통 ALLOWED
   - PRESERVATIVE → 공통 ALLOWED
   - 등등 15개 type → 14개 purpose 매핑
   → 예상: ~487건

2단계 (오늘~내일): GEMINI_SAFETY primary_function 기반 매핑
   - primary_function 필드에서 기능 키워드 추출
   - "보습" → MOISTURIZING, "미백" → WHITENING 등
   → 예상: ~300건 추가

3단계 (이번 주): Claude Code 배치로 나머지 대량 매핑
   - ingredient_master 25,612건을 1,000건씩 배치
   - Claude가 INCI명+한글명으로 기능 분류
   - purpose_ingredient_map에 ALLOWED로 저장
   → 예상: ~5,000~10,000건
```

### Step 4: 마이랩 연동 포인트 정의

```
마이랩 팀이 Phase 1 완료 후 연동할 API:

GET  /api/v1/categories              — 43개 카테고리 목록
GET  /api/v1/purposes                — 14개 목적 목록
GET  /api/v1/purposes/:code/ingredients — 목적별 성분 풀
POST /api/v1/detect-category         — 제품명 → 카테고리 판별
POST /api/v1/detect-purpose          — 제품명 → 목적 추출
```

---

## 전체 실행 타임라인 (수정)

```
이번 주 (3/13~3/14):
  ✅ Phase 0 완료 확인
  → Phase 1A: DB 4개 테이블 생성
  → Phase 1B-1단계: ingredient_type 기반 자동 매핑 (~487건)
  → Phase 1B-2단계: GEMINI_SAFETY 기반 매핑 (~300건)

다음 주 (3/17~3/21):
  → Phase 1B-3단계: Claude 배치 대량 매핑 (~5,000건)
  → Phase 1: system-prompt 게이트 규칙 추가
  → Phase 1: AI 서버 PurposeGate 클래스 구현
  → Phase 1 테스트

3~4주차 (3/24~4/4):
  → Phase 2: 검증 모드 (파일 파서 + 8개 검증기)
  → Phase 1B 배치 계속 (목표 10,000건)

5~6주차:
  → Phase 3: 로컬 LLM (ollama + ChromaDB)

7~8주차:
  → Phase 4: 데이터 플라이휠 + WF3~5 구현

9~10주차:
  → Phase 5: 프론트엔드 통합
```

---

## 리스크 및 대응

| 리스크 | 영향 | 대응 |
|---|---|---|
| ingredient_master 기능 분류 부족 | Purpose Gate 정확도 저하 | Claude 배치로 대량 분류 |
| Gemini JSON 파싱 실패율 43% | 데이터 품질 | 파싱 로직 개선 + 재시도 |
| RTX 4070 SUPER 미확인 | Phase 3 지연 | CPU 모드 폴백 가능 |
| n8n WF3~5 구현 복잡도 | Phase 4 지연 | 기존 WF 패턴 재활용 |

---

## 우선순위 결론

**지금 바로 해야 할 것**:
1. Phase 1A: DB 4개 테이블 생성 ← **이 세션에서 실행 가능**
2. Phase 1B-1: ingredient_type 기반 자동 매핑
3. Phase 1B-2: GEMINI_SAFETY 기반 매핑

**다음에 할 것**:
4. Phase 1B-3: Claude 배치 대량 매핑
5. Phase 1: AI 서버 Purpose Gate 구현
6. Phase 2: 검증 모드

> Phase 1A(DB 테이블 생성)부터 바로 진행할까요?
