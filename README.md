# COCHING Workflow — 워크플로우 개발/보완/백업 통합 저장소

> n8n 워크플로우 + 스킬 파이프라인 + DB 백업 + 크롤러 + 자동화 스크립트

## 폴더 구조

```
E:\COCHING-WORKFLOW\
├── backup/                    # 백업 데이터 (크론 자동 생성)
│   ├── db-json/               # DB 테이블별 JSON 스냅샷 (30분마다)
│   ├── pgdump/                # PostgreSQL 전체 덤프 (매일 03:00, 15:00)
│   ├── excel/                 # Excel 누적 리포트 (30분마다)
│   ├── formulations/          # 가이드 처방 JSON 백업
│   └── n8n-workflows/         # n8n 워크플로우 JSON 내보내기
├── scripts/                   # 자동화 스크립트
│   ├── batch/                 # 배치 처리 (Gemini 대량 조회)
│   ├── cron/                  # 크론 작업 (백업, Excel, 리포트)
│   ├── deploy/                # 배포/마이그레이션 (워크플로우 업데이트)
│   └── fix/                   # 워크플로우 에러 수정
├── crawlers/                  # 웹 크롤러
│   ├── hwahae-playwright/     # 화해 크롤러 (Playwright, 전성분 추출)
│   ├── hwahae-shell/          # 화해 크롤러 (Shell/cURL 버전)
│   └── regulation-monitor/    # 화장품 규제 모니터링 (다국가)
├── skills/                    # 6단계 스킬 파이프라인
│   ├── formulation.md         # 처방 생성
│   ├── compound-expansion.md  # 화합물 확장
│   ├── precision-arithmetic.md# 정밀 산술
│   ├── ingredients.md         # 성분 조회
│   ├── regulation.md          # 규제 확인
│   └── qa-validation.md       # QA 검증
├── reports/                   # 작업 리포트 (일일/에러수정)
└── data/                      # 학습 데이터
```

## 워크플로우 현황 (2026-03-13)

### 활성 워크플로우 (5개)
| 워크플로우 | ID | 주기 | 비고 |
|---|---|---|---|
| 제품카피 가이드 v1.0 | a0670dfd | 2분 | guide_cache_copy 생성 |
| 원료 수집 v7 | FW6GUTq0 | 3시간 | 식약처 → ingredient_master |
| 제품 수집 v1 | 5YRZrKRW | 3시간 | 화장품 제품 수집 |
| 원료 안전성 강화 v1 | wf_safety | 1일 1회 | 5개국 규제 → regulation_cache |
| 다국가 규제 모니터링 v1 | wf_regulation | 1일 1회 | US FDA → regulation_cache |

### DB 현황
| 테이블 | 건수 |
|--------|------|
| ingredient_master | 25,595+ |
| product_master | 16,044+ |
| regulation_cache | 3,700+ |
| guide_cache | 215 |
| guide_cache_copy | 538+ |
| product_ingredients | 412 |

## 크론 작업 (WSL2)
| 작업 | 주기 | 스크립트 |
|------|------|---------|
| pg_dump 백업 | 매일 03:00, 15:00 | `scripts/cron/coching_backup.sh` |
| DB JSON 백업 | 30분마다 | `scripts/cron/auto_backup_db.py` |
| Excel 리포트 | 30분마다 | `scripts/cron/auto_excel_export.py` |
| 일일 리포트 | 매일 08:00 | `scripts/cron/daily_workflow_report.py` |

## 배치 스크립트
| 스크립트 | 용도 | 사용법 |
|----------|------|--------|
| `scripts/batch/batch_safety.py` | 원료 5개국 규제 대량 조회 | `python3 batch_safety.py [라운드수]` |
| `scripts/batch/batch_regulation.py` | US FDA 규제 문서 수집/분석 | `python3 batch_regulation.py` |
