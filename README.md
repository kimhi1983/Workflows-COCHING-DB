# COCHING Workflow — 워크플로우 개발/보완 전용

> n8n 워크플로우 + 스킬 파이프라인 + DB 관리 + 자동화 스크립트

## 구조

```
coching-workflow/
├── scripts/           # 워크플로우 Python 스크립트
│   ├── migrate_legacy_db.py
│   ├── update_workflow_skills.py
│   ├── update_workflow_compound_db.py
│   ├── daily_workflow_report.py
│   └── auto_backup_db.py
├── skills/            # 6단계 스킬 파이프라인
│   ├── formulation.md
│   ├── compound-expansion.md
│   ├── precision-arithmetic.md
│   ├── ingredients.md
│   ├── regulation.md
│   └── qa-validation.md
├── n8n-backup/        # n8n 워크플로우 JSON 백업
├── reports/           # 작업 리포트
└── data/              # 학습 데이터, Excel 리포트
```

## 워크플로우 현황

### 2-Track 병렬 가이드 생성 시스템

| Track | 워크플로우 | 상태 |
|-------|-----------|------|
| Track 1 | v2.3-A~F (카테고리×피부타입) | 215/215 완료 |
| Track 2 | 제품카피 v1.0 | 10/2,511+ 진행중 |

### DB 현황

| 테이블 | 건수 |
|--------|------|
| ingredient_master | 25,520 |
| product_master | 16,026 |
| regulation_cache | 3,523 |
| compound_master | 15 |
| guide_cache | 215 |
| guide_cache_copy | 10 |

## 병렬 세션 규칙
- 이 폴더는 **오른쪽 세션 (워크플로우 담당)** 이 관리
- 메인 앱 코드 (Vue/Spring Boot)는 왼쪽 세션이 관리
- 같은 Git 저장소 내 영역 분리로 충돌 방지
