#!/bin/bash
# ============================================================
# 화장품 규제 & 원료 데이터 수집 시스템 - n8n 워크플로우 관리
# KPROS / C-Auto / COCHING 연동
# ============================================================

# ── 설정 (본인 환경에 맞게 수정) ─────────────────────────
N8N_URL="${N8N_URL:-http://localhost:5678}"
N8N_API_KEY="${N8N_API_KEY:-your-n8n-api-key-here}"
GEMINI_API_KEY="${GEMINI_API_KEY:-your-gemini-api-key}"
CF_ACCOUNT_ID="${CF_ACCOUNT_ID:-your-cf-account-id}"
CF_API_TOKEN="${CF_API_TOKEN:-your-cf-api-token}"
WORKFLOW_DIR="$(cd "$(dirname "$0")" && pwd)/workflows"

# 색상
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; NC='\033[0m'

# ── 유틸 함수 ────────────────────────────────────────────
log()  { echo -e "${GREEN}[✓]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
err()  { echo -e "${RED}[✗]${NC} $1"; }
info() { echo -e "${CYAN}[i]${NC} $1"; }

check_env() {
  if [ "$N8N_API_KEY" = "your-n8n-api-key-here" ]; then
    err "N8N_API_KEY가 설정되지 않았습니다."
    info "export N8N_API_KEY=<your-key> 또는 .env 파일에 추가하세요"
    info "n8n Settings > API > Create API Key 에서 발급"
    return 1
  fi
  # n8n 연결 확인
  local status=$(curl -s -o /dev/null -w "%{http_code}" \
    -H "X-N8N-API-KEY: $N8N_API_KEY" \
    "$N8N_URL/api/v1/workflows?limit=1" 2>/dev/null)
  if [ "$status" != "200" ]; then
    err "n8n 연결 실패 (HTTP $status). N8N_URL과 API_KEY를 확인하세요."
    return 1
  fi
  log "n8n 연결 성공: $N8N_URL"
}

# .env 파일 로드
[ -f "$(dirname "$0")/.env" ] && source "$(dirname "$0")/.env"

# ── n8n API 래퍼 ─────────────────────────────────────────
n8n_api() {
  local method=$1 endpoint=$2 data=$3
  curl -s -X "$method" \
    -H "X-N8N-API-KEY: $N8N_API_KEY" \
    -H "Content-Type: application/json" \
    ${data:+-d "$data"} \
    "$N8N_URL/api/v1$endpoint"
}

# ── 워크플로우 목록 조회 ──────────────────────────────────
list_workflows() {
  info "n8n 워크플로우 목록:"
  echo ""
  n8n_api GET "/workflows?limit=50" | \
    python3 -c "
import json,sys
data=json.load(sys.stdin)
for w in data.get('data',[]):
  status='🟢' if w.get('active') else '🔴'
  print(f\"  {status} [{w['id']}] {w['name']}\")
" 2>/dev/null || n8n_api GET "/workflows?limit=50"
}

# ── 워크플로우 생성 ──────────────────────────────────────
create_workflow() {
  local json_file=$1
  if [ ! -f "$json_file" ]; then
    err "파일을 찾을 수 없습니다: $json_file"
    return 1
  fi
  local name=$(python3 -c "import json;print(json.load(open('$json_file'))['name'])" 2>/dev/null)
  info "워크플로우 생성 중: $name"
  local result=$(n8n_api POST "/workflows" "@$json_file")
  local wf_id=$(echo "$result" | python3 -c "import json,sys;print(json.load(sys.stdin).get('id',''))" 2>/dev/null)
  if [ -n "$wf_id" ] && [ "$wf_id" != "None" ]; then
    log "생성 완료: ID=$wf_id, Name=$name"
    echo "  → $N8N_URL/workflow/$wf_id"
  else
    err "생성 실패: $result"
  fi
}

# ── 워크플로우 활성화/비활성화 ────────────────────────────
activate_workflow() {
  local wf_id=$1
  n8n_api PATCH "/workflows/$wf_id" '{"active":true}' > /dev/null
  log "워크플로우 $wf_id 활성화됨"
}

deactivate_workflow() {
  local wf_id=$1
  n8n_api PATCH "/workflows/$wf_id" '{"active":false}' > /dev/null
  log "워크플로우 $wf_id 비활성화됨"
}

# ── 워크플로우 삭제 ──────────────────────────────────────
delete_workflow() {
  local wf_id=$1
  read -p "워크플로우 $wf_id 삭제하시겠습니까? (y/N): " confirm
  [ "$confirm" = "y" ] || return
  n8n_api DELETE "/workflows/$wf_id" > /dev/null
  log "워크플로우 $wf_id 삭제됨"
}

# ── 워크플로우 내보내기 ──────────────────────────────────
export_workflow() {
  local wf_id=$1 output=${2:-"workflow_${wf_id}.json"}
  n8n_api GET "/workflows/$wf_id" | python3 -m json.tool > "$output"
  log "내보내기 완료: $output"
}

# ── 전체 워크플로우 JSON 생성 ─────────────────────────────
generate_all_workflows() {
  mkdir -p "$WORKFLOW_DIR"
  info "워크플로우 JSON 생성 중..."

  # ── 1. US/FDA 규제 수집
  cat > "$WORKFLOW_DIR/01_regulation_us_fda.json" << 'WORKFLOW_END'
{
  "name": "[규제수집] US/FDA - GEMINI_US",
  "nodes": [
    {
      "parameters": { "rule": { "interval": [{ "field": "hours", "hoursInterval": 12 }] } },
      "id": "schedule-1",
      "name": "Schedule (12시간)",
      "type": "n8n-nodes-base.scheduleTrigger",
      "typeVersion": 1.2,
      "position": [0, 0]
    },
    {
      "parameters": {
        "url": "https://www.federalregister.gov/api/v1/documents.json",
        "qs": {
          "conditions[agencies][]": "food-and-drug-administration",
          "conditions[term]": "cosmetic OR cosmetics",
          "per_page": "10",
          "order": "newest"
        },
        "options": { "response": { "response": { "responseFormat": "json" } } }
      },
      "id": "http-fed-register",
      "name": "Federal Register API",
      "type": "n8n-nodes-base.httpRequest",
      "typeVersion": 4.2,
      "position": [250, -100]
    },
    {
      "parameters": {
        "url": "https://www.fda.gov/cosmetics",
        "options": { "response": { "response": { "responseFormat": "text" } } }
      },
      "id": "http-fda-page",
      "name": "FDA Cosmetics Page",
      "type": "n8n-nodes-base.httpRequest",
      "typeVersion": 4.2,
      "position": [250, 100]
    },
    {
      "parameters": {
        "jsCode": "// Federal Register 결과 파싱\nconst items = $input.all();\nconst results = [];\n\nfor (const item of items) {\n  const data = item.json;\n  if (data.results) {\n    for (const doc of data.results) {\n      results.push({\n        json: {\n          source: 'federal_register',\n          title: doc.title,\n          abstract: doc.abstract || '',\n          url: doc.html_url,\n          published_at: doc.publication_date,\n          document_type: doc.type,\n          region: 'US',\n          gemini_tag: 'GEMINI_US'\n        }\n      });\n    }\n  }\n}\n\nreturn results.length ? results : [{ json: { skip: true } }];"
      },
      "id": "code-parse",
      "name": "Parse Results",
      "type": "n8n-nodes-base.code",
      "typeVersion": 2,
      "position": [500, 0]
    },
    {
      "parameters": {
        "conditions": { "options": { "caseSensitive": true, "leftValue": "", "typeValidation": "strict" },
          "conditions": [{ "id": "skip-check", "leftValue": "={{ $json.skip }}", "rightValue": true, "operator": { "type": "boolean", "operation": "notEqual" } }]
        }
      },
      "id": "filter-skip",
      "name": "Skip Empty",
      "type": "n8n-nodes-base.filter",
      "typeVersion": 2,
      "position": [700, 0]
    },
    {
      "parameters": {
        "url": "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent",
        "authentication": "genericCredentialType",
        "genericAuthType": "httpQueryAuth",
        "sendBody": true,
        "specifyBody": "json",
        "jsonBody": "={\n  \"contents\": [{\n    \"parts\": [{\n      \"text\": \"다음 화장품 규제 문서를 분석해주세요.\\n\\n제목: {{ $json.title }}\\n내용: {{ $json.abstract }}\\n\\n다음 JSON 형식으로 응답:\\n{\\n  \\\"summary_ko\\\": \\\"한글 요약 (2-3문장)\\\",\\n  \\\"category\\\": \\\"new_rule|amendment|guidance|recall|other\\\",\\n  \\\"affected_ingredients\\\": [\\\"INCI명 배열\\\"],\\n  \\\"severity\\\": \\\"high|medium|low\\\",\\n  \\\"keywords\\\": [\\\"키워드 배열\\\"]\\n}\"\n    }]\n  }]\n}",
        "options": {}
      },
      "id": "gemini-analyze",
      "name": "Gemini 분석",
      "type": "n8n-nodes-base.httpRequest",
      "typeVersion": 4.2,
      "position": [900, 0],
      "notes": "GEMINI_API_KEY를 Query Auth 크레덴셜에 key=key로 설정"
    },
    {
      "parameters": {
        "jsCode": "// Gemini 응답 파싱 + 원본 데이터 병합\nconst items = $input.all();\nconst results = [];\n\nfor (const item of items) {\n  try {\n    const geminiResp = item.json;\n    const text = geminiResp?.candidates?.[0]?.content?.parts?.[0]?.text || '{}';\n    const jsonStr = text.replace(/```json\\n?|```/g, '').trim();\n    const analysis = JSON.parse(jsonStr);\n    \n    results.push({\n      json: {\n        ...item.json,\n        analysis,\n        gemini_tag: 'GEMINI_US',\n        collected_at: new Date().toISOString()\n      }\n    });\n  } catch(e) {\n    results.push({\n      json: { ...item.json, analysis: { error: e.message }, collected_at: new Date().toISOString() }\n    });\n  }\n}\n\nreturn results;"
      },
      "id": "code-merge",
      "name": "분석결과 병합",
      "type": "n8n-nodes-base.code",
      "typeVersion": 2,
      "position": [1100, 0]
    },
    {
      "parameters": {
        "operation": "appendOrUpdate",
        "documentId": { "__rl": true, "value": "", "mode": "url" },
        "sheetName": { "__rl": true, "value": "규제수집_US", "mode": "name" },
        "columns": {
          "mappingMode": "autoMapInputData",
          "value": {}
        },
        "options": {}
      },
      "id": "gsheet-save",
      "name": "Google Sheets 저장",
      "type": "n8n-nodes-base.googleSheets",
      "typeVersion": 4.5,
      "position": [1300, -100],
      "notes": "스프레드시트 ID와 시트명을 설정하세요"
    },
    {
      "parameters": {
        "conditions": { "options": {},
          "conditions": [{ "id": "severity-check", "leftValue": "={{ $json.analysis?.severity }}", "rightValue": "high", "operator": { "type": "string", "operation": "equals" } }]
        }
      },
      "id": "filter-alert",
      "name": "긴급 필터",
      "type": "n8n-nodes-base.filter",
      "typeVersion": 2,
      "position": [1300, 100]
    },
    {
      "parameters": {
        "fromEmail": "alert@kpros.kr",
        "toEmail": "",
        "subject": "=🚨 [US/FDA 규제 알림] {{ $json.title }}",
        "emailType": "html",
        "html": "=<h2>{{ $json.title }}</h2>\n<p><strong>분류:</strong> {{ $json.analysis?.category }}</p>\n<p><strong>요약:</strong> {{ $json.analysis?.summary_ko }}</p>\n<p><strong>영향 원료:</strong> {{ $json.analysis?.affected_ingredients?.join(', ') }}</p>\n<p><a href=\"{{ $json.url }}\">원문 보기</a></p>\n<hr>\n<small>GEMINI_US | {{ $json.collected_at }}</small>"
      },
      "id": "email-alert",
      "name": "긴급 알림 발송",
      "type": "n8n-nodes-base.emailSend",
      "typeVersion": 2.1,
      "position": [1500, 100],
      "notes": "SMTP 크레덴셜 설정 필요 (Hiworks 등)"
    }
  ],
  "connections": {
    "Schedule (12시간)": { "main": [[{ "node": "Federal Register API", "type": "main", "index": 0 }, { "node": "FDA Cosmetics Page", "type": "main", "index": 0 }]] },
    "Federal Register API": { "main": [[{ "node": "Parse Results", "type": "main", "index": 0 }]] },
    "FDA Cosmetics Page": { "main": [[{ "node": "Parse Results", "type": "main", "index": 0 }]] },
    "Parse Results": { "main": [[{ "node": "Skip Empty", "type": "main", "index": 0 }]] },
    "Skip Empty": { "main": [[{ "node": "Gemini 분석", "type": "main", "index": 0 }]] },
    "Gemini 분석": { "main": [[{ "node": "분석결과 병합", "type": "main", "index": 0 }]] },
    "분석결과 병합": { "main": [[{ "node": "Google Sheets 저장", "type": "main", "index": 0 }, { "node": "긴급 필터", "type": "main", "index": 0 }]] },
    "긴급 필터": { "main": [[{ "node": "긴급 알림 발송", "type": "main", "index": 0 }]] }
  },
  "settings": { "executionOrder": "v1" },
  "tags": [{ "name": "규제수집" }, { "name": "US" }, { "name": "GEMINI_US" }]
}
WORKFLOW_END
  log "01_regulation_us_fda.json 생성"

  # ── 2. JP 규제 수집
  cat > "$WORKFLOW_DIR/02_regulation_jp.json" << 'WORKFLOW_END'
{
  "name": "[규제수집] JP/厚労省 - GEMINI_JP",
  "nodes": [
    {
      "parameters": { "rule": { "interval": [{ "field": "hours", "hoursInterval": 24 }] } },
      "id": "schedule-jp",
      "name": "Schedule (24시간)",
      "type": "n8n-nodes-base.scheduleTrigger",
      "typeVersion": 1.2,
      "position": [0, 0]
    },
    {
      "parameters": {
        "url": "https://www.mhlw.go.jp/stf/seisakunitsuite/bunya/kenkou_iryou/iyakuhin/cosmetics/index.html",
        "options": { "response": { "response": { "responseFormat": "text" } } }
      },
      "id": "http-mhlw",
      "name": "MHLW 화장품 페이지",
      "type": "n8n-nodes-base.httpRequest",
      "typeVersion": 4.2,
      "position": [250, -50]
    },
    {
      "parameters": {
        "url": "https://www.pmda.go.jp/safety/info-services/drugs/calling-attention/safety-info/0001.html",
        "options": { "response": { "response": { "responseFormat": "text" } } }
      },
      "id": "http-pmda",
      "name": "PMDA 안전성정보",
      "type": "n8n-nodes-base.httpRequest",
      "typeVersion": 4.2,
      "position": [250, 150]
    },
    {
      "parameters": {
        "jsCode": "// HTML에서 최신 공지 추출\nconst items = $input.all();\nconst results = [];\n\nfor (const item of items) {\n  const html = item.json.data || item.json.body || '';\n  // 간단한 링크/제목 추출 (Cheerio 없이)\n  const linkRegex = /<a[^>]+href=\"([^\"]+)\"[^>]*>([^<]+)<\\/a>/gi;\n  let match;\n  let count = 0;\n  while ((match = linkRegex.exec(html)) && count < 10) {\n    const url = match[1];\n    const title = match[2].trim();\n    if (title.length > 10 && (title.includes('化粧') || title.includes('cosmetic') || title.includes('薬') || title.includes('通知'))) {\n      results.push({\n        json: {\n          source: item.json.url?.includes('pmda') ? 'pmda' : 'mhlw',\n          title,\n          url: url.startsWith('http') ? url : `https://www.mhlw.go.jp${url}`,\n          region: 'JP',\n          gemini_tag: 'GEMINI_JP'\n        }\n      });\n      count++;\n    }\n  }\n}\n\nreturn results.length ? results : [{ json: { skip: true, region: 'JP' } }];"
      },
      "id": "code-parse-jp",
      "name": "JP 결과 파싱",
      "type": "n8n-nodes-base.code",
      "typeVersion": 2,
      "position": [500, 0]
    },
    {
      "parameters": {
        "url": "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent",
        "authentication": "genericCredentialType",
        "genericAuthType": "httpQueryAuth",
        "sendBody": true,
        "specifyBody": "json",
        "jsonBody": "={\n  \"contents\": [{\n    \"parts\": [{\n      \"text\": \"다음 일본 화장품/의약부외품 규제 문서를 분석해주세요.\\n\\n제목: {{ $json.title }}\\nURL: {{ $json.url }}\\n\\nJSON 응답:\\n{\\n  \\\"summary_ko\\\": \\\"한글 요약\\\",\\n  \\\"category\\\": \\\"new_rule|amendment|guidance|recall|safety_alert\\\",\\n  \\\"is_quasi_drug\\\": true/false,\\n  \\\"affected_ingredients\\\": [],\\n  \\\"severity\\\": \\\"high|medium|low\\\"\\n}\"\n    }]\n  }]\n}",
        "options": {}
      },
      "id": "gemini-jp",
      "name": "Gemini JP 분석",
      "type": "n8n-nodes-base.httpRequest",
      "typeVersion": 4.2,
      "position": [750, 0]
    },
    {
      "parameters": {
        "operation": "appendOrUpdate",
        "documentId": { "__rl": true, "value": "", "mode": "url" },
        "sheetName": { "__rl": true, "value": "규제수집_JP", "mode": "name" },
        "columns": { "mappingMode": "autoMapInputData", "value": {} },
        "options": {}
      },
      "id": "gsheet-jp",
      "name": "Sheets 저장 (JP)",
      "type": "n8n-nodes-base.googleSheets",
      "typeVersion": 4.5,
      "position": [1000, 0]
    }
  ],
  "connections": {
    "Schedule (24시간)": { "main": [[{ "node": "MHLW 화장품 페이지", "type": "main", "index": 0 }, { "node": "PMDA 안전성정보", "type": "main", "index": 0 }]] },
    "MHLW 화장품 페이지": { "main": [[{ "node": "JP 결과 파싱", "type": "main", "index": 0 }]] },
    "PMDA 안전성정보": { "main": [[{ "node": "JP 결과 파싱", "type": "main", "index": 0 }]] },
    "JP 결과 파싱": { "main": [[{ "node": "Gemini JP 분석", "type": "main", "index": 0 }]] },
    "Gemini JP 분석": { "main": [[{ "node": "Sheets 저장 (JP)", "type": "main", "index": 0 }]] }
  },
  "settings": { "executionOrder": "v1" },
  "tags": [{ "name": "규제수집" }, { "name": "JP" }, { "name": "GEMINI_JP" }]
}
WORKFLOW_END
  log "02_regulation_jp.json 생성"

  # ── 3. CN 규제 수집
  cat > "$WORKFLOW_DIR/03_regulation_cn.json" << 'WORKFLOW_END'
{
  "name": "[규제수집] CN/NMPA - GEMINI_CN",
  "nodes": [
    {
      "parameters": { "rule": { "interval": [{ "field": "hours", "hoursInterval": 12 }] } },
      "id": "schedule-cn",
      "name": "Schedule (12시간)",
      "type": "n8n-nodes-base.scheduleTrigger",
      "typeVersion": 1.2,
      "position": [0, 0]
    },
    {
      "parameters": {
        "url": "https://cosmetic.chemlinked.com/news",
        "options": { "response": { "response": { "responseFormat": "text" } } }
      },
      "id": "http-chemlinked",
      "name": "ChemLinked News",
      "type": "n8n-nodes-base.httpRequest",
      "typeVersion": 4.2,
      "position": [250, -50]
    },
    {
      "parameters": {
        "url": "https://www.nmpa.gov.cn/xxgk/ggtg/index.html",
        "options": { "response": { "response": { "responseFormat": "text" } } }
      },
      "id": "http-nmpa",
      "name": "NMPA 공고",
      "type": "n8n-nodes-base.httpRequest",
      "typeVersion": 4.2,
      "position": [250, 150]
    },
    {
      "parameters": {
        "jsCode": "const items = $input.all();\nconst results = [];\n\nfor (const item of items) {\n  const html = item.json.data || item.json.body || '';\n  const linkRegex = /<a[^>]+href=\"([^\"]+)\"[^>]*>([^<]+)<\\/a>/gi;\n  let match;\n  let count = 0;\n  while ((match = linkRegex.exec(html)) && count < 10) {\n    const title = match[2].trim();\n    if (title.length > 5 && (title.includes('化妆品') || title.includes('cosmetic') || title.includes('化妆') || title.includes('原料'))) {\n      results.push({\n        json: {\n          source: item.json.url?.includes('nmpa') ? 'nmpa' : 'chemlinked',\n          title,\n          url: match[1].startsWith('http') ? match[1] : `https://www.nmpa.gov.cn${match[1]}`,\n          region: 'CN',\n          gemini_tag: 'GEMINI_CN'\n        }\n      });\n      count++;\n    }\n  }\n}\n\nreturn results.length ? results : [{ json: { skip: true, region: 'CN' } }];"
      },
      "id": "code-parse-cn",
      "name": "CN 결과 파싱",
      "type": "n8n-nodes-base.code",
      "typeVersion": 2,
      "position": [500, 0]
    },
    {
      "parameters": {
        "url": "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent",
        "authentication": "genericCredentialType",
        "genericAuthType": "httpQueryAuth",
        "sendBody": true,
        "specifyBody": "json",
        "jsonBody": "={\n  \"contents\": [{\n    \"parts\": [{\n      \"text\": \"다음 중국 화장품 규제 문서를 분석해주세요 (중문/영문 모두 가능).\\n\\n제목: {{ $json.title }}\\nURL: {{ $json.url }}\\n\\nJSON 응답:\\n{\\n  \\\"summary_ko\\\": \\\"한글 요약\\\",\\n  \\\"category\\\": \\\"new_rule|amendment|new_ingredient|recall|guidance\\\",\\n  \\\"nmpa_type\\\": \\\"일반화장품|특수화장품|신원료\\\",\\n  \\\"affected_ingredients\\\": [],\\n  \\\"severity\\\": \\\"high|medium|low\\\"\\n}\"\n    }]\n  }]\n}",
        "options": {}
      },
      "id": "gemini-cn",
      "name": "Gemini CN 분석",
      "type": "n8n-nodes-base.httpRequest",
      "typeVersion": 4.2,
      "position": [750, 0]
    },
    {
      "parameters": {
        "operation": "appendOrUpdate",
        "documentId": { "__rl": true, "value": "", "mode": "url" },
        "sheetName": { "__rl": true, "value": "규제수집_CN", "mode": "name" },
        "columns": { "mappingMode": "autoMapInputData", "value": {} },
        "options": {}
      },
      "id": "gsheet-cn",
      "name": "Sheets 저장 (CN)",
      "type": "n8n-nodes-base.googleSheets",
      "typeVersion": 4.5,
      "position": [1000, 0]
    }
  ],
  "connections": {
    "Schedule (12시간)": { "main": [[{ "node": "ChemLinked News", "type": "main", "index": 0 }, { "node": "NMPA 공고", "type": "main", "index": 0 }]] },
    "ChemLinked News": { "main": [[{ "node": "CN 결과 파싱", "type": "main", "index": 0 }]] },
    "NMPA 공고": { "main": [[{ "node": "CN 결과 파싱", "type": "main", "index": 0 }]] },
    "CN 결과 파싱": { "main": [[{ "node": "Gemini CN 분석", "type": "main", "index": 0 }]] },
    "Gemini CN 분석": { "main": [[{ "node": "Sheets 저장 (CN)", "type": "main", "index": 0 }]] }
  },
  "settings": { "executionOrder": "v1" },
  "tags": [{ "name": "규제수집" }, { "name": "CN" }, { "name": "GEMINI_CN" }]
}
WORKFLOW_END
  log "03_regulation_cn.json 생성"

  # ── 4. ASEAN 규제 수집
  cat > "$WORKFLOW_DIR/04_regulation_asean.json" << 'WORKFLOW_END'
{
  "name": "[규제수집] ASEAN - GEMINI_ASEAN",
  "nodes": [
    {
      "parameters": { "rule": { "interval": [{ "field": "days", "daysInterval": 3 }] } },
      "id": "schedule-asean",
      "name": "Schedule (3일)",
      "type": "n8n-nodes-base.scheduleTrigger",
      "typeVersion": 1.2,
      "position": [0, 0]
    },
    {
      "parameters": {
        "url": "https://www.fda.moph.go.th/sites/Cosmetic/SitePages/Main.aspx",
        "options": { "response": { "response": { "responseFormat": "text" } } }
      },
      "id": "http-thai-fda",
      "name": "Thai FDA",
      "type": "n8n-nodes-base.httpRequest",
      "typeVersion": 4.2,
      "position": [250, -50]
    },
    {
      "parameters": {
        "url": "https://www.hsa.gov.sg/cosmetic-products",
        "options": { "response": { "response": { "responseFormat": "text" } } }
      },
      "id": "http-hsa",
      "name": "HSA Singapore",
      "type": "n8n-nodes-base.httpRequest",
      "typeVersion": 4.2,
      "position": [250, 150]
    },
    {
      "parameters": {
        "jsCode": "const items = $input.all();\nconst results = [];\nfor (const item of items) {\n  results.push({\n    json: {\n      source: item.json.url?.includes('hsa') ? 'hsa_sg' : 'thai_fda',\n      raw_html: (item.json.data || '').substring(0, 3000),\n      url: item.json.url || '',\n      region: 'ASEAN',\n      gemini_tag: 'GEMINI_ASEAN'\n    }\n  });\n}\nreturn results;"
      },
      "id": "code-parse-asean",
      "name": "ASEAN 파싱",
      "type": "n8n-nodes-base.code",
      "typeVersion": 2,
      "position": [500, 0]
    },
    {
      "parameters": {
        "url": "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent",
        "authentication": "genericCredentialType",
        "genericAuthType": "httpQueryAuth",
        "sendBody": true,
        "specifyBody": "json",
        "jsonBody": "={\n  \"contents\": [{\n    \"parts\": [{\n      \"text\": \"다음 ASEAN 지역 화장품 규제 페이지를 분석해주세요.\\n\\nSource: {{ $json.source }}\\nHTML 일부: {{ $json.raw_html }}\\n\\n화장품 관련 최신 공지/규제 변경사항이 있다면 JSON 응답:\\n{\\n  \\\"has_updates\\\": true/false,\\n  \\\"updates\\\": [{\\n    \\\"title\\\": \\\"제목\\\",\\n    \\\"summary_ko\\\": \\\"한글 요약\\\",\\n    \\\"category\\\": \\\"new_rule|amendment|guidance\\\",\\n    \\\"severity\\\": \\\"high|medium|low\\\"\\n  }]\\n}\"\n    }]\n  }]\n}",
        "options": {}
      },
      "id": "gemini-asean",
      "name": "Gemini ASEAN 분석",
      "type": "n8n-nodes-base.httpRequest",
      "typeVersion": 4.2,
      "position": [750, 0]
    },
    {
      "parameters": {
        "operation": "appendOrUpdate",
        "documentId": { "__rl": true, "value": "", "mode": "url" },
        "sheetName": { "__rl": true, "value": "규제수집_ASEAN", "mode": "name" },
        "columns": { "mappingMode": "autoMapInputData", "value": {} },
        "options": {}
      },
      "id": "gsheet-asean",
      "name": "Sheets 저장 (ASEAN)",
      "type": "n8n-nodes-base.googleSheets",
      "typeVersion": 4.5,
      "position": [1000, 0]
    }
  ],
  "connections": {
    "Schedule (3일)": { "main": [[{ "node": "Thai FDA", "type": "main", "index": 0 }, { "node": "HSA Singapore", "type": "main", "index": 0 }]] },
    "Thai FDA": { "main": [[{ "node": "ASEAN 파싱", "type": "main", "index": 0 }]] },
    "HSA Singapore": { "main": [[{ "node": "ASEAN 파싱", "type": "main", "index": 0 }]] },
    "ASEAN 파싱": { "main": [[{ "node": "Gemini ASEAN 분석", "type": "main", "index": 0 }]] },
    "Gemini ASEAN 분석": { "main": [[{ "node": "Sheets 저장 (ASEAN)", "type": "main", "index": 0 }]] }
  },
  "settings": { "executionOrder": "v1" },
  "tags": [{ "name": "규제수집" }, { "name": "ASEAN" }, { "name": "GEMINI_ASEAN" }]
}
WORKFLOW_END
  log "04_regulation_asean.json 생성"

  # ── 5. EWG 등급 수집
  cat > "$WORKFLOW_DIR/05_ewg_score_collector.json" << 'WORKFLOW_END'
{
  "name": "[원료DB] EWG Skin Deep 등급 수집",
  "nodes": [
    {
      "parameters": { "rule": { "interval": [{ "field": "days", "daysInterval": 7 }] } },
      "id": "schedule-ewg",
      "name": "Schedule (주 1회)",
      "type": "n8n-nodes-base.scheduleTrigger",
      "typeVersion": 1.2,
      "position": [0, 0]
    },
    {
      "parameters": {
        "jsCode": "// 수집 대상 원료 목록 (INCI명)\n// 실제 운영 시 Google Sheets나 DB에서 가져오기\nconst ingredients = [\n  'PHENOXYETHANOL',\n  'SALICYLIC ACID',\n  'NIACINAMIDE',\n  'RETINOL',\n  'TOCOPHEROL',\n  'GLYCERIN',\n  'BUTYLENE GLYCOL',\n  'SODIUM HYALURONATE',\n  'TITANIUM DIOXIDE',\n  'ZINC OXIDE',\n  'ETHYLHEXYL METHOXYCINNAMATE',\n  'BENZOPHENONE-3',\n  'METHYLISOTHIAZOLINONE',\n  'DIMETHICONE',\n  'CETEARYL ALCOHOL',\n  'SODIUM LAURYL SULFATE',\n  'PROPYLPARABEN',\n  'METHYLPARABEN',\n  'FRAGRANCE',\n  'TRICLOSAN'\n];\n\nreturn ingredients.map(name => ({\n  json: {\n    inci_name: name,\n    search_url: `https://www.ewg.org/skindeep/search/?search=${encodeURIComponent(name)}`\n  }\n}));"
      },
      "id": "code-ingredient-list",
      "name": "원료 목록",
      "type": "n8n-nodes-base.code",
      "typeVersion": 2,
      "position": [250, 0]
    },
    {
      "parameters": {
        "url": "={{ $json.search_url }}",
        "options": {
          "response": { "response": { "responseFormat": "text" } },
          "timeout": 10000
        }
      },
      "id": "http-ewg-search",
      "name": "EWG 검색",
      "type": "n8n-nodes-base.httpRequest",
      "typeVersion": 4.2,
      "position": [500, 0],
      "notes": "Rate limit 주의: 배치 간 1-2초 딜레이 권장"
    },
    {
      "parameters": {
        "jsCode": "// EWG 검색 결과에서 등급 추출\nconst items = $input.all();\nconst results = [];\n\nfor (const item of items) {\n  const html = item.json.data || item.json.body || '';\n  const inci = item.json.inci_name;\n  \n  // EWG 등급 패턴 매칭 (HTML에서)\n  const scoreMatch = html.match(/data-score=\"(\\d+)\"/i) ||\n                     html.match(/hazard-score[^>]*>(\\d+)/i) ||\n                     html.match(/score-(\\d+)/i);\n  \n  const score = scoreMatch ? parseInt(scoreMatch[1]) : null;\n  \n  results.push({\n    json: {\n      inci_name: inci,\n      ewg_score: score,\n      ewg_url: item.json.search_url,\n      raw_available: html.length > 0,\n      collected_at: new Date().toISOString()\n    }\n  });\n}\n\nreturn results;"
      },
      "id": "code-parse-ewg",
      "name": "EWG 등급 파싱",
      "type": "n8n-nodes-base.code",
      "typeVersion": 2,
      "position": [750, 0]
    },
    {
      "parameters": {
        "url": "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent",
        "authentication": "genericCredentialType",
        "genericAuthType": "httpQueryAuth",
        "sendBody": true,
        "specifyBody": "json",
        "jsonBody": "={\n  \"contents\": [{\n    \"parts\": [{\n      \"text\": \"화장품 원료 '{{ $json.inci_name }}'에 대해 EWG Skin Deep 등급과 안전성 정보를 알려주세요.\\n\\nJSON 응답:\\n{\\n  \\\"ewg_score_estimated\\\": 1-10,\\n  \\\"concerns\\\": [\\\"주요 우려사항\\\"],\\n  \\\"common_usage\\\": \\\"일반적 용도\\\",\\n  \\\"max_conc_eu\\\": \\\"EU 최대농도 (알려진 경우)\\\",\\n  \\\"restriction_notes\\\": \\\"규제 참고사항\\\"\\n}\"\n    }]\n  }]\n}",
        "options": {}
      },
      "id": "gemini-ewg-supplement",
      "name": "Gemini 보완 분석",
      "type": "n8n-nodes-base.httpRequest",
      "typeVersion": 4.2,
      "position": [1000, 0],
      "notes": "스크래핑 실패 시 Gemini로 보완"
    },
    {
      "parameters": {
        "operation": "appendOrUpdate",
        "documentId": { "__rl": true, "value": "", "mode": "url" },
        "sheetName": { "__rl": true, "value": "원료DB_EWG", "mode": "name" },
        "columns": { "mappingMode": "autoMapInputData", "value": {} },
        "options": {}
      },
      "id": "gsheet-ewg",
      "name": "Sheets 저장 (EWG)",
      "type": "n8n-nodes-base.googleSheets",
      "typeVersion": 4.5,
      "position": [1250, 0]
    }
  ],
  "connections": {
    "Schedule (주 1회)": { "main": [[{ "node": "원료 목록", "type": "main", "index": 0 }]] },
    "원료 목록": { "main": [[{ "node": "EWG 검색", "type": "main", "index": 0 }]] },
    "EWG 검색": { "main": [[{ "node": "EWG 등급 파싱", "type": "main", "index": 0 }]] },
    "EWG 등급 파싱": { "main": [[{ "node": "Gemini 보완 분석", "type": "main", "index": 0 }]] },
    "Gemini 보완 분석": { "main": [[{ "node": "Sheets 저장 (EWG)", "type": "main", "index": 0 }]] }
  },
  "settings": { "executionOrder": "v1" },
  "tags": [{ "name": "원료DB" }, { "name": "EWG" }]
}
WORKFLOW_END
  log "05_ewg_score_collector.json 생성"

  # ── 6. 원료별 최대농도 수집
  cat > "$WORKFLOW_DIR/06_ingredient_max_concentration.json" << 'WORKFLOW_END'
{
  "name": "[원료DB] 국가별 최대농도 수집",
  "nodes": [
    {
      "parameters": { "rule": { "interval": [{ "field": "days", "daysInterval": 7 }] } },
      "id": "schedule-conc",
      "name": "Schedule (주 1회)",
      "type": "n8n-nodes-base.scheduleTrigger",
      "typeVersion": 1.2,
      "position": [0, 0]
    },
    {
      "parameters": {
        "jsCode": "// CosIng API로 EU 제한물질 목록 조회\nconst targetIngredients = [\n  'SALICYLIC ACID', 'PHENOXYETHANOL', 'BENZOPHENONE-3',\n  'TITANIUM DIOXIDE', 'ZINC OXIDE', 'RETINOL',\n  'METHYLISOTHIAZOLINONE', 'TRICLOSAN', 'SODIUM LAURYL SULFATE',\n  'ETHYLHEXYL METHOXYCINNAMATE', 'PROPYLPARABEN', 'METHYLPARABEN'\n];\n\nreturn targetIngredients.map(name => ({\n  json: { inci_name: name }\n}));"
      },
      "id": "code-target-ingredients",
      "name": "대상 원료",
      "type": "n8n-nodes-base.code",
      "typeVersion": 2,
      "position": [250, 0]
    },
    {
      "parameters": {
        "url": "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent",
        "authentication": "genericCredentialType",
        "genericAuthType": "httpQueryAuth",
        "sendBody": true,
        "specifyBody": "json",
        "jsonBody": "={\n  \"contents\": [{\n    \"parts\": [{\n      \"text\": \"화장품 원료 '{{ $json.inci_name }}'의 국가별 규제와 최대 허용 농도를 조사해주세요.\\n\\n반드시 아래 JSON 형식으로 응답:\\n{\\n  \\\"inci_name\\\": \\\"{{ $json.inci_name }}\\\",\\n  \\\"cas_number\\\": \\\"CAS번호\\\",\\n  \\\"regulations\\\": {\\n    \\\"EU\\\": {\\n      \\\"status\\\": \\\"allowed|restricted|banned\\\",\\n      \\\"annex\\\": \\\"해당 Annex\\\",\\n      \\\"max_concentration\\\": \\\"최대농도%\\\",\\n      \\\"conditions\\\": \\\"사용조건\\\"\\n    },\\n    \\\"US\\\": {\\n      \\\"status\\\": \\\"allowed|restricted|banned\\\",\\n      \\\"regulation_ref\\\": \\\"규제 근거\\\",\\n      \\\"max_concentration\\\": \\\"최대농도%\\\",\\n      \\\"notes\\\": \\\"비고\\\"\\n    },\\n    \\\"JP\\\": {\\n      \\\"status\\\": \\\"allowed|restricted|banned\\\",\\n      \\\"max_concentration\\\": \\\"최대농도%\\\",\\n      \\\"quasi_drug\\\": true/false,\\n      \\\"notes\\\": \\\"비고\\\"\\n    },\\n    \\\"CN\\\": {\\n      \\\"status\\\": \\\"allowed|restricted|banned\\\",\\n      \\\"max_concentration\\\": \\\"최대농도%\\\",\\n      \\\"notes\\\": \\\"비고\\\"\\n    },\\n    \\\"ASEAN\\\": {\\n      \\\"status\\\": \\\"allowed|restricted|banned\\\",\\n      \\\"max_concentration\\\": \\\"최대농도%\\\",\\n      \\\"notes\\\": \\\"비고\\\"\\n    }\\n  },\\n  \\\"cir_assessment\\\": \\\"CIR 평가 결과\\\",\\n  \\\"primary_function\\\": \\\"주요 기능\\\"\\n}\"\n    }]\n  }]\n}",
        "options": {}
      },
      "id": "gemini-conc",
      "name": "Gemini 최대농도 조회",
      "type": "n8n-nodes-base.httpRequest",
      "typeVersion": 4.2,
      "position": [500, 0]
    },
    {
      "parameters": {
        "jsCode": "const items = $input.all();\nconst results = [];\n\nfor (const item of items) {\n  try {\n    const text = item.json?.candidates?.[0]?.content?.parts?.[0]?.text || '{}';\n    const jsonStr = text.replace(/```json\\n?|```/g, '').trim();\n    const data = JSON.parse(jsonStr);\n    results.push({ json: { ...data, collected_at: new Date().toISOString() } });\n  } catch(e) {\n    results.push({ json: { error: e.message, raw: item.json } });\n  }\n}\nreturn results;"
      },
      "id": "code-parse-conc",
      "name": "결과 파싱",
      "type": "n8n-nodes-base.code",
      "typeVersion": 2,
      "position": [750, 0]
    },
    {
      "parameters": {
        "operation": "appendOrUpdate",
        "documentId": { "__rl": true, "value": "", "mode": "url" },
        "sheetName": { "__rl": true, "value": "원료DB_최대농도", "mode": "name" },
        "columns": { "mappingMode": "autoMapInputData", "value": {} },
        "options": {}
      },
      "id": "gsheet-conc",
      "name": "Sheets 저장 (최대농도)",
      "type": "n8n-nodes-base.googleSheets",
      "typeVersion": 4.5,
      "position": [1000, 0]
    }
  ],
  "connections": {
    "Schedule (주 1회)": { "main": [[{ "node": "대상 원료", "type": "main", "index": 0 }]] },
    "대상 원료": { "main": [[{ "node": "Gemini 최대농도 조회", "type": "main", "index": 0 }]] },
    "Gemini 최대농도 조회": { "main": [[{ "node": "결과 파싱", "type": "main", "index": 0 }]] },
    "결과 파싱": { "main": [[{ "node": "Sheets 저장 (최대농도)", "type": "main", "index": 0 }]] }
  },
  "settings": { "executionOrder": "v1" },
  "tags": [{ "name": "원료DB" }, { "name": "최대농도" }]
}
WORKFLOW_END
  log "06_ingredient_max_concentration.json 생성"

  echo ""
  log "총 6개 워크플로우 JSON 생성 완료"
  info "위치: $WORKFLOW_DIR/"
  ls -la "$WORKFLOW_DIR/"
}

# ── 전체 배포 ─────────────────────────────────────────────
deploy_all() {
  check_env || return 1
  
  info "전체 워크플로우 배포 시작..."
  echo ""
  
  for f in "$WORKFLOW_DIR"/*.json; do
    [ -f "$f" ] || continue
    create_workflow "$f"
    sleep 1
  done
  
  echo ""
  log "전체 배포 완료!"
  list_workflows
}

# ── 도움말 ────────────────────────────────────────────────
show_help() {
  echo ""
  echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
  echo -e "${CYAN}  화장품 규제 수집 시스템 - n8n 워크플로우 관리${NC}"
  echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
  echo ""
  echo -e "  ${GREEN}사전 준비:${NC}"
  echo "    export N8N_URL=http://localhost:5678"
  echo "    export N8N_API_KEY=<your-api-key>"
  echo "    export GEMINI_API_KEY=<your-gemini-key>"
  echo ""
  echo -e "  ${GREEN}사용법:${NC} ./manage.sh <command>"
  echo ""
  echo -e "  ${YELLOW}generate${NC}     워크플로우 JSON 파일 6개 생성"
  echo -e "  ${YELLOW}deploy${NC}       전체 워크플로우를 n8n에 배포"
  echo -e "  ${YELLOW}list${NC}         n8n 워크플로우 목록 조회"
  echo -e "  ${YELLOW}create${NC} <f>   JSON 파일로 워크플로우 1개 생성"
  echo -e "  ${YELLOW}activate${NC} <id>   워크플로우 활성화"
  echo -e "  ${YELLOW}deactivate${NC} <id> 워크플로우 비활성화"
  echo -e "  ${YELLOW}export${NC} <id>     워크플로우 JSON 내보내기"
  echo -e "  ${YELLOW}delete${NC} <id>     워크플로우 삭제"
  echo -e "  ${YELLOW}status${NC}       n8n 연결 상태 확인"
  echo -e "  ${YELLOW}help${NC}         이 도움말"
  echo ""
  echo -e "  ${GREEN}워크플로우 구성:${NC}"
  echo "    01. [규제수집] US/FDA      - GEMINI_US / FDA_SEED (12h)"
  echo "    02. [규제수집] JP/厚労省   - GEMINI_JP (24h)"
  echo "    03. [규제수집] CN/NMPA     - GEMINI_CN (12h)"
  echo "    04. [규제수집] ASEAN       - GEMINI_ASEAN (3일)"
  echo "    05. [원료DB]  EWG 등급     - 스크래핑+Gemini (주1회)"
  echo "    06. [원료DB]  최대농도     - Gemini 조회 (주1회)"
  echo ""
  echo -e "  ${GREEN}VS Code 터미널 빠른 실행:${NC}"
  echo "    bash manage.sh generate   # JSON 먼저 생성"
  echo "    bash manage.sh deploy     # n8n에 전체 배포"
  echo "    bash manage.sh list       # 상태 확인"
  echo ""
}

# ── 메인 ─────────────────────────────────────────────────
case "${1:-help}" in
  generate)    generate_all_workflows ;;
  deploy)      deploy_all ;;
  list)        check_env && list_workflows ;;
  create)      check_env && create_workflow "$2" ;;
  activate)    check_env && activate_workflow "$2" ;;
  deactivate)  check_env && deactivate_workflow "$2" ;;
  export)      check_env && export_workflow "$2" "$3" ;;
  delete)      check_env && delete_workflow "$2" ;;
  status)      check_env ;;
  help|*)      show_help ;;
esac
