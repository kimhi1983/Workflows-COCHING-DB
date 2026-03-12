# 화장품 규제 & 원료 데이터 수집 시스템

## 빠른 시작 (VS Code 터미널)

```bash
# 1. 환경 설정
cp .env.example .env
# .env 파일 편집하여 API 키 입력

# 2. 워크플로우 JSON 생성
bash manage.sh generate

# 3. n8n에 전체 배포
bash manage.sh deploy

# 4. 상태 확인
bash manage.sh list
```

## 워크플로우 구성

| # | 이름 | 태그 | 주기 | 소스 |
|---|------|------|------|------|
| 01 | US/FDA 규제 | GEMINI_US / FDA_SEED | 12시간 | Federal Register API, FDA.gov |
| 02 | JP/厚労省 규제 | GEMINI_JP | 24시간 | MHLW, PMDA |
| 03 | CN/NMPA 규제 | GEMINI_CN | 12시간 | NMPA, ChemLinked |
| 04 | ASEAN 규제 | GEMINI_ASEAN | 3일 | Thai FDA, HSA |
| 05 | EWG 등급 수집 | EWG | 주 1회 | EWG Skin Deep |
| 06 | 최대농도 수집 | 최대농도 | 주 1회 | Gemini (CosIng/CIR/SCCS 기반) |

## n8n 크레덴셜 사전 설정

배포 전 n8n에서 아래 크레덴셜을 먼저 생성해야 합니다:

1. **HTTP Query Auth** — name: `Gemini API`, key: `key`, value: `<GEMINI_API_KEY>`
2. **Google Sheets OAuth2** — Google Cloud Console에서 OAuth 설정
3. **SMTP** — Hiworks 또는 Gmail SMTP 설정 (알림 발송용)

## 명령어 전체 목록

```bash
bash manage.sh generate          # JSON 파일 생성
bash manage.sh deploy            # 전체 배포
bash manage.sh list              # 목록 조회
bash manage.sh create <file>     # 단일 워크플로우 생성
bash manage.sh activate <id>     # 활성화
bash manage.sh deactivate <id>   # 비활성화
bash manage.sh export <id>       # JSON 내보내기
bash manage.sh delete <id>       # 삭제
bash manage.sh status            # 연결 확인
```

## 구조

```
cosmetics-regulation/
├── manage.sh              # 메인 관리 스크립트
├── .env.example           # 환경 변수 템플릿
├── .env                   # 실제 환경 변수 (gitignore)
├── README.md
└── workflows/
    ├── 01_regulation_us_fda.json
    ├── 02_regulation_jp.json
    ├── 03_regulation_cn.json
    ├── 04_regulation_asean.json
    ├── 05_ewg_score_collector.json
    └── 06_ingredient_max_concentration.json
```

## 배포 후 체크리스트

- [ ] 각 워크플로우에서 Google Sheets 노드의 스프레드시트 ID 설정
- [ ] Gemini API 크레덴셜 연결 확인
- [ ] SMTP 크레덴셜 설정 (알림 워크플로우)
- [ ] 테스트 실행 후 Google Sheets에 데이터 저장 확인
- [ ] 필요 시 EWG 원료 목록 확장 (05번 워크플로우 Code 노드)
- [ ] 최대농도 수집 대상 원료 추가 (06번 워크플로우 Code 노드)
