#!/bin/bash
# ============================================================
# 화해(Hwahae) 스크래퍼 - Apify 연동 + 직접 스크래핑
# VS Code 터미널에서 실행
# ============================================================

# ── 설정 ─────────────────────────────────────────────────
APIFY_TOKEN="${APIFY_TOKEN:-}"
OUTPUT_DIR="$(cd "$(dirname "$0")" && pwd)/output"
mkdir -p "$OUTPUT_DIR"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; NC='\033[0m'

log()  { echo -e "${GREEN}[✓]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
err()  { echo -e "${RED}[✗]${NC} $1"; }
info() { echo -e "${CYAN}[i]${NC} $1"; }

[ -f "$(dirname "$0")/.env" ] && source "$(dirname "$0")/.env"

# ── Apify 검색 스크래퍼 ──────────────────────────────────
apify_search() {
  local query="${1:-크림}"
  local max="${2:-10}"

  if [ -z "$APIFY_TOKEN" ]; then
    err "APIFY_TOKEN이 설정되지 않았습니다."
    info "export APIFY_TOKEN=<your-token>"
    info "또는 .env 파일에 추가하세요"
    info ""
    info "Apify 토큰 발급:"
    info "  1. https://apify.com 가입 (무료)"
    info "  2. Settings > Integrations > API tokens"
    return 1
  fi

  info "화해 검색: '$query' (최대 ${max}개)"
  echo ""

  local result=$(curl -s -X POST \
    "https://api.apify.com/v2/acts/kitschy_marigold~hwahae-search-scraper/run-sync-get-dataset-items?token=$APIFY_TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"query\": \"$query\", \"maxProducts\": $max}" \
    --max-time 120)

  if [ -z "$result" ] || [ "$result" = "[]" ]; then
    err "결과 없음 또는 타임아웃"
    return 1
  fi

  # 파일 저장
  local filename="$OUTPUT_DIR/hwahae_search_${query}_$(date +%Y%m%d_%H%M%S).json"
  echo "$result" | python3 -m json.tool > "$filename" 2>/dev/null

  if [ $? -eq 0 ]; then
    log "결과 저장: $filename"
    echo ""

    # 결과 요약 출력
    python3 << PYEOF
import json, sys

try:
    data = json.loads('''$result''')
except:
    with open('$filename') as f:
        data = json.load(f)

if not isinstance(data, list):
    data = [data]

print(f"  📦 수집된 제품: {len(data)}개")
print(f"  {'─' * 50}")

for i, item in enumerate(data[:5]):
    title = item.get('title') or item.get('name') or item.get('productName', '?')
    brand = item.get('brand') or item.get('brandName', '?')
    price = item.get('price', '?')
    image = item.get('imageUrl') or item.get('thumbnail') or item.get('image', '')
    ingredients = item.get('ingredients') or item.get('ingredientList', [])

    print(f"\n  [{i+1}] {brand} - {title}")
    print(f"      가격: {price}")
    print(f"      이미지: {'✅ 있음' if image else '❌ 없음'} {image[:60] + '...' if image and len(image) > 60 else image}")

    if isinstance(ingredients, list) and len(ingredients) > 0:
        print(f"      전성분: ✅ {len(ingredients)}개")
        print(f"      상위 3개: {', '.join(str(x) for x in ingredients[:3])}")
    elif isinstance(ingredients, str) and len(ingredients) > 0:
        print(f"      전성분: ✅ (텍스트)")
        print(f"      미리보기: {ingredients[:80]}...")
    else:
        print(f"      전성분: ❌ 없음 (상세 페이지 스크래핑 필요)")

print(f"\n  {'─' * 50}")
print(f"  📋 전체 필드 목록:")
if data:
    keys = list(data[0].keys())
    for k in keys:
        v = data[0].get(k)
        vtype = type(v).__name__
        preview = str(v)[:50] if v else 'null'
        print(f"      • {k} ({vtype}): {preview}")
PYEOF
  else
    warn "JSON 파싱 실패. 원본 저장합니다."
    echo "$result" > "$filename"
  fi
}

# ── Apify 랭킹 스크래퍼 ──────────────────────────────────
apify_ranking() {
  if [ -z "$APIFY_TOKEN" ]; then
    err "APIFY_TOKEN이 설정되지 않았습니다."
    return 1
  fi

  info "화해 랭킹 수집 중..."
  echo ""

  local result=$(curl -s -X POST \
    "https://api.apify.com/v2/acts/kitschy_marigold~hwahae-ranking-scraper/run-sync-get-dataset-items?token=$APIFY_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{}' \
    --max-time 180)

  local filename="$OUTPUT_DIR/hwahae_ranking_$(date +%Y%m%d_%H%M%S).json"
  echo "$result" | python3 -m json.tool > "$filename" 2>/dev/null

  if [ $? -eq 0 ]; then
    log "랭킹 결과 저장: $filename"
    local count=$(python3 -c "import json;print(len(json.loads(open('$filename').read())))" 2>/dev/null)
    info "수집된 제품: ${count}개"
  else
    echo "$result" > "$filename"
    warn "원본 저장 완료"
  fi
}

# ── 화해 웹 직접 스크래핑 (Apify 없이) ────────────────────
direct_scrape() {
  local query="${1:-선크림}"

  info "화해 웹 직접 스크래핑: '$query'"
  info "Node.js 스크립트 실행..."

  # Node.js가 있는지 확인
  if ! command -v node &>/dev/null; then
    err "Node.js가 필요합니다. 설치 후 다시 시도하세요."
    return 1
  fi

  node "$(dirname "$0")/scraper.mjs" "$query" "$OUTPUT_DIR"
}

# ── 결과 CSV 변환 ─────────────────────────────────────────
to_csv() {
  local json_file=$1

  if [ ! -f "$json_file" ]; then
    err "파일을 찾을 수 없습니다: $json_file"
    return 1
  fi

  local csv_file="${json_file%.json}.csv"

  python3 << PYEOF
import json, csv, sys

with open('$json_file') as f:
    data = json.load(f)

if not isinstance(data, list):
    data = [data]

if not data:
    print("데이터가 비어있습니다")
    sys.exit(1)

keys = list(data[0].keys())

with open('$csv_file', 'w', newline='', encoding='utf-8-sig') as f:
    writer = csv.DictWriter(f, fieldnames=keys)
    writer.writeheader()
    for row in data:
        # 리스트 필드는 문자열로 변환
        flat = {}
        for k, v in row.items():
            if isinstance(v, (list, dict)):
                flat[k] = json.dumps(v, ensure_ascii=False)
            else:
                flat[k] = v
        writer.writerow(flat)

print(f"CSV 변환 완료: $csv_file")
print(f"행: {len(data)}, 열: {len(keys)}")
PYEOF

  log "CSV 저장: $csv_file"
}

# ── 결과 파일 목록 ─────────────────────────────────────────
list_results() {
  info "수집 결과 파일:"
  echo ""
  if [ -d "$OUTPUT_DIR" ] && [ "$(ls -A $OUTPUT_DIR 2>/dev/null)" ]; then
    ls -lh "$OUTPUT_DIR"/ 2>/dev/null | grep -v "^total" | while read line; do
      echo "  $line"
    done
  else
    warn "아직 수집된 파일이 없습니다."
  fi
}

# ── 도움말 ────────────────────────────────────────────────
show_help() {
  echo ""
  echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
  echo -e "${CYAN}  화해(Hwahae) 스크래퍼 - 이미지 + 전성분 수집${NC}"
  echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
  echo ""
  echo -e "  ${GREEN}사전 준비:${NC}"
  echo "    1. https://apify.com 가입 (무료 $5 크레딧)"
  echo "    2. Settings > Integrations > Personal API tokens"
  echo "    3. export APIFY_TOKEN=<your-token>"
  echo "       또는 .env 파일에 APIFY_TOKEN=xxx 추가"
  echo ""
  echo -e "  ${GREEN}사용법:${NC} bash hwahae.sh <command> [options]"
  echo ""
  echo -e "  ${YELLOW}search${NC} <키워드> [개수]    Apify로 화해 검색"
  echo -e "     예: bash hwahae.sh search 선크림 20"
  echo -e "     예: bash hwahae.sh search 토너 10"
  echo -e "     예: bash hwahae.sh search 레티놀 5"
  echo ""
  echo -e "  ${YELLOW}ranking${NC}                  Apify로 화해 랭킹 수집"
  echo -e "     예: bash hwahae.sh ranking"
  echo ""
  echo -e "  ${YELLOW}direct${NC} <키워드>          Node.js 직접 스크래핑"
  echo -e "     예: bash hwahae.sh direct 니아신아마이드"
  echo ""
  echo -e "  ${YELLOW}csv${NC} <json파일>           JSON → CSV 변환"
  echo -e "     예: bash hwahae.sh csv output/hwahae_search_크림_20260312.json"
  echo ""
  echo -e "  ${YELLOW}list${NC}                     수집 결과 파일 목록"
  echo -e "  ${YELLOW}help${NC}                     이 도움말"
  echo ""
  echo -e "  ${GREEN}수집 데이터:${NC}"
  echo "    • 제품명, 브랜드, 가격"
  echo "    • 제품 이미지 URL"
  echo "    • 전성분 리스트 (INCI명 + 한글명)"
  echo "    • EWG 등급 (있는 경우)"
  echo ""
  echo -e "  ${GREEN}빠른 테스트:${NC}"
  echo "    bash hwahae.sh search 크림 5"
  echo ""
}

# ── 메인 ─────────────────────────────────────────────────
case "${1:-help}" in
  search)   apify_search "$2" "$3" ;;
  ranking)  apify_ranking ;;
  direct)   direct_scrape "$2" ;;
  csv)      to_csv "$2" ;;
  list)     list_results ;;
  help|*)   show_help ;;
esac
