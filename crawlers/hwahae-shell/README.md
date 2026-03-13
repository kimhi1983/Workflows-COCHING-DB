# 화해(Hwahae) 스크래퍼 - 이미지 + 전성분 수집

## 빠른 시작

```bash
# 1. Apify 토큰 설정
cp .env.example .env
# .env에 APIFY_TOKEN 입력

# 2. 테스트 (5개만)
bash hwahae.sh search 크림 5

# 3. 더 많이 수집
bash hwahae.sh search 선크림 50

# 4. CSV로 변환
bash hwahae.sh csv output/hwahae_search_크림_xxx.json
```

## 명령어

| 명령어 | 설명 | 예시 |
|--------|------|------|
| `search <키워드> [개수]` | Apify로 검색 수집 | `bash hwahae.sh search 토너 20` |
| `ranking` | 랭킹 제품 수집 | `bash hwahae.sh ranking` |
| `direct <키워드>` | Node.js 직접 스크래핑 | `bash hwahae.sh direct 세럼` |
| `csv <파일>` | JSON → CSV 변환 | `bash hwahae.sh csv output/xxx.json` |
| `list` | 수집 결과 목록 | `bash hwahae.sh list` |

## Apify 토큰 발급

1. https://apify.com 가입 (무료 $5 크레딧)
2. 로그인 → Settings → Integrations → Personal API tokens
3. Create token → 복사
4. `.env` 파일에 붙여넣기

## 수집 데이터

- 제품명, 브랜드, 가격
- 제품 이미지 URL
- 전성분 리스트 (INCI + 한글)
- EWG 등급 (있는 경우)
- 리뷰 수, 평점

## 구조

```
hwahae-scraper/
├── hwahae.sh       # 메인 스크립트 (bash)
├── scraper.mjs     # Node.js 직접 스크래퍼 (Apify 없이)
├── .env.example    # 환경변수 템플릿
├── .env            # 실제 환경변수
└── output/         # 수집 결과 (JSON, CSV)
```

## 전성분 데이터가 안 나올 때

Apify Search Scraper가 목록만 반환하는 경우:
1. `bash hwahae.sh direct <키워드>` 로 직접 스크래핑 시도
2. 그래도 안 되면 → Playwright 기반 크롤러 필요 (SPA 렌더링)
