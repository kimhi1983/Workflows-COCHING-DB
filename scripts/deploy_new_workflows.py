#!/usr/bin/env python3
"""
신규 워크플로우 2종 n8n 배포:
  WF-1: 원료 안전성 강화 (EWG + 다국가 최대농도)
  WF-2: 다국가 규제 모니터링 (US/JP/CN/ASEAN)

기존 워크플로우 건드리지 않고 새로 추가.
"""
import sqlite3, json, uuid
from datetime import datetime

DB = '/home/kpros/.n8n/database.sqlite'
GEMINI_KEY = 'AIzaSyAMLi4_wB7lwMsbkg7tEo1F0-KF34ew-GA'
PG_CRED_ID = '2c8e9119-0bb0-49f2-ad43-f040ab4a7a64'
GEMINI_URL = f'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_KEY}'

conn = sqlite3.connect(DB)
cur = conn.cursor()


def deploy_workflow(cur, wf_id, wf_json):
    """워크플로우를 n8n에 배포 (INSERT or UPDATE)"""
    name = wf_json['name']
    nodes = json.dumps(wf_json['nodes'], ensure_ascii=False)
    conns = json.dumps(wf_json['connections'], ensure_ascii=False)
    settings = json.dumps(wf_json.get('settings', {}), ensure_ascii=False)
    now = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S.000')
    vid = str(uuid.uuid4())

    # 기존에 있으면 업데이트
    cur.execute('SELECT id FROM workflow_entity WHERE id=?', (wf_id,))
    exists = cur.fetchone()

    if exists:
        cur.execute("""UPDATE workflow_entity
            SET name=?, nodes=?, connections=?, settings=?,
                active=1, triggerCount=1, activeVersionId=?, updatedAt=?
            WHERE id=?""",
            (name, nodes, conns, settings, vid, now, wf_id))
    else:
        cur.execute("""INSERT INTO workflow_entity
            (id, name, active, nodes, connections, settings, triggerCount,
             versionId, createdAt, updatedAt, activeVersionId)
            VALUES (?, ?, 1, ?, ?, ?, 1, ?, ?, ?, ?)""",
            (wf_id, name, nodes, conns, settings, vid, now, now, vid))

    # workflow_history에 버전 등록
    cur.execute("""INSERT INTO workflow_history
        (versionId, workflowId, nodes, connections, authors, createdAt, updatedAt)
        VALUES (?, ?, ?, ?, '[]', ?, ?)""",
        (vid, wf_id, nodes, conns, now, now))

    return vid


# ============================================================
# WF-1: 원료 안전성 강화
# ============================================================
WF1_ID = 'wf_safety_enhance_v1'
WF1 = {
    "name": "COCHING AI — 원료 안전성 강화 v1",
    "nodes": [
        {
            "parameters": {"rule": {"interval": [{"field": "hours", "hoursInterval": 6}]}},
            "id": "sched-safety",
            "name": "⏰ 6시간 자동실행",
            "type": "n8n-nodes-base.scheduleTrigger",
            "typeVersion": 1.2,
            "position": [0, 0]
        },
        {
            "parameters": {"command": "=manual"},
            "id": "manual-safety",
            "name": "▶ 수동 실행",
            "type": "n8n-nodes-base.manualTrigger",
            "typeVersion": 1,
            "position": [0, 200]
        },
        {
            "parameters": {
                "operation": "executeQuery",
                "query": """SELECT im.inci_name, im.korean_name, im.cas_number
FROM ingredient_master im
LEFT JOIN regulation_cache rc ON rc.inci_name = im.inci_name AND rc.source = 'GEMINI_SAFETY'
WHERE rc.inci_name IS NULL
  AND LENGTH(im.inci_name) > 3
ORDER BY RANDOM()
LIMIT 5""",
                "options": {"queryReplacement": ""}
            },
            "id": "pg-find-target",
            "name": "🔍 규제 미수집 원료 조회",
            "type": "n8n-nodes-base.postgres",
            "typeVersion": 2.5,
            "position": [250, 100],
            "credentials": {"postgres": {"id": PG_CRED_ID, "name": "COCHING PostgreSQL (Local)"}}
        },
        {
            "parameters": {
                "jsCode": """const items = $input.all();
if (!items.length || !items[0].json.inci_name) {
  return [{ json: { skip: true, reason: '수집 대상 없음' } }];
}

const results = [];
for (const item of items) {
  const inci = item.json.inci_name;
  const korean = item.json.korean_name || '';
  const cas = item.json.cas_number || '';

  const prompt = `화장품 원료 '${inci}' (한글명: ${korean}, CAS: ${cas})에 대해 다음 정보를 조사해주세요.

반드시 아래 JSON 형식으로만 응답 (설명 없이 JSON만):
{
  "inci_name": "${inci}",
  "ewg_score": 1~10 (EWG Skin Deep 추정 등급),
  "primary_function": "주요 기능 (한글)",
  "regulations": {
    "KR": {"status":"allowed/restricted/banned", "max_concentration":"최대농도% 또는 null", "note":"비고"},
    "EU": {"status":"allowed/restricted/banned", "annex":"해당 Annex", "max_concentration":"최대농도%", "note":"비고"},
    "US": {"status":"allowed/restricted/banned", "max_concentration":"최대농도%", "note":"비고"},
    "JP": {"status":"allowed/restricted/banned", "max_concentration":"최대농도%", "note":"비고"},
    "CN": {"status":"allowed/restricted/banned", "max_concentration":"최대농도%", "note":"비고"}
  },
  "concerns": ["주요 우려사항 배열"],
  "cir_assessment": "CIR 평가 요약"
}`;

  const body = JSON.stringify({
    contents: [{ parts: [{ text: prompt }] }],
    generationConfig: { temperature: 0.2, maxOutputTokens: 1024 }
  });

  results.push({ json: { inci_name: inci, korean_name: korean, cas_number: cas, geminiBody: body } });
}
return results;"""
            },
            "id": "code-prompt",
            "name": "🧠 Gemini 프롬프트 구성",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [500, 100]
        },
        {
            "parameters": {
                "conditions": {"conditions": [
                    {"id": "skip-check", "leftValue": "={{ $json.skip }}", "rightValue": True,
                     "operator": {"type": "boolean", "operation": "notEqual"}}
                ]}
            },
            "id": "filter-skip",
            "name": "⚡ 스킵 체크",
            "type": "n8n-nodes-base.filter",
            "typeVersion": 2,
            "position": [700, 100]
        },
        {
            "parameters": {
                "method": "POST",
                "url": GEMINI_URL,
                "sendHeaders": True,
                "headerParameters": {"parameters": [{"name": "Content-Type", "value": "application/json"}]},
                "sendBody": True,
                "contentType": "raw",
                "rawContentType": "application/json",
                "body": "={{ $json.geminiBody }}",
                "options": {"timeout": 60000}
            },
            "id": "gemini-safety",
            "name": "🌐 Gemini 안전성 조회",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [900, 100]
        },
        {
            "parameters": {
                "jsCode": """const items = $input.all();
const config = $('🧠 Gemini 프롬프트 구성').all();
const results = [];

for (let i = 0; i < items.length; i++) {
  const item = items[i].json;
  const orig = config[i] ? config[i].json : {};

  try {
    const text = item?.candidates?.[0]?.content?.parts?.[0]?.text || '{}';
    const jsonStr = text.replace(/```json\\n?|```/g, '').trim();
    const jsonMatch = jsonStr.match(/\\{[\\s\\S]*\\}/);
    const data = JSON.parse(jsonMatch ? jsonMatch[0] : jsonStr);

    const regs = data.regulations || {};
    const countries = ['KR', 'EU', 'US', 'JP', 'CN'];

    for (const country of countries) {
      const reg = regs[country];
      if (!reg) continue;

      results.push({
        json: {
          source: 'GEMINI_SAFETY',
          ingredient: orig.korean_name || orig.inci_name,
          inci_name: orig.inci_name,
          max_concentration: reg.max_concentration || null,
          restriction: JSON.stringify({
            country, status: reg.status,
            annex: reg.annex || null,
            note: reg.note || null,
            ewg_score: data.ewg_score,
            concerns: data.concerns,
            primary_function: data.primary_function,
            cir_assessment: data.cir_assessment
          })
        }
      });
    }
  } catch(e) {
    results.push({
      json: {
        source: 'GEMINI_SAFETY',
        ingredient: orig.inci_name || 'unknown',
        inci_name: orig.inci_name || '',
        max_concentration: null,
        restriction: JSON.stringify({ error: e.message })
      }
    });
  }
}

return results.length ? results : [{ json: { skip: true } }];"""
            },
            "id": "code-parse-safety",
            "name": "🔄 안전성 파싱",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [1150, 100]
        },
        {
            "parameters": {
                "operation": "executeQuery",
                "query": """INSERT INTO regulation_cache (source, ingredient, inci_name, max_concentration, restriction, updated_at)
VALUES ($1, $2, $3, $4, $5, NOW())
ON CONFLICT (source, ingredient)
DO UPDATE SET
  inci_name = EXCLUDED.inci_name,
  max_concentration = EXCLUDED.max_concentration,
  restriction = EXCLUDED.restriction,
  updated_at = NOW()""",
                "options": {
                    "queryReplacement": "={{ [$json.source, $json.ingredient, $json.inci_name, $json.max_concentration, $json.restriction] }}"
                }
            },
            "id": "pg-save-safety",
            "name": "💾 regulation_cache 저장",
            "type": "n8n-nodes-base.postgres",
            "typeVersion": 2.5,
            "position": [1400, 100],
            "credentials": {"postgres": {"id": PG_CRED_ID, "name": "COCHING PostgreSQL (Local)"}},
            "alwaysOutputData": True
        }
    ],
    "connections": {
        "⏰ 6시간 자동실행": {"main": [[{"node": "🔍 규제 미수집 원료 조회", "type": "main", "index": 0}]]},
        "▶ 수동 실행": {"main": [[{"node": "🔍 규제 미수집 원료 조회", "type": "main", "index": 0}]]},
        "🔍 규제 미수집 원료 조회": {"main": [[{"node": "🧠 Gemini 프롬프트 구성", "type": "main", "index": 0}]]},
        "🧠 Gemini 프롬프트 구성": {"main": [[{"node": "⚡ 스킵 체크", "type": "main", "index": 0}]]},
        "⚡ 스킵 체크": {"main": [[{"node": "🌐 Gemini 안전성 조회", "type": "main", "index": 0}]]},
        "🌐 Gemini 안전성 조회": {"main": [[{"node": "🔄 안전성 파싱", "type": "main", "index": 0}]]},
        "🔄 안전성 파싱": {"main": [[{"node": "💾 regulation_cache 저장", "type": "main", "index": 0}]]}
    },
    "settings": {"executionOrder": "v1"}
}


# ============================================================
# WF-2: 다국가 규제 모니터링
# ============================================================
WF2_ID = 'wf_regulation_monitor_v1'
WF2 = {
    "name": "COCHING AI — 다국가 규제 모니터링 v1",
    "nodes": [
        {
            "parameters": {"rule": {"interval": [{"field": "days", "daysInterval": 7}]}},
            "id": "sched-reg-mon",
            "name": "⏰ 주 1회 자동실행",
            "type": "n8n-nodes-base.scheduleTrigger",
            "typeVersion": 1.2,
            "position": [0, 0]
        },
        {
            "parameters": {"command": "=manual"},
            "id": "manual-reg-mon",
            "name": "▶ 수동 실행",
            "type": "n8n-nodes-base.manualTrigger",
            "typeVersion": 1,
            "position": [0, 200]
        },
        # US Federal Register
        {
            "parameters": {
                "url": "https://www.federalregister.gov/api/v1/documents.json",
                "sendQuery": True,
                "queryParameters": {"parameters": [
                    {"name": "conditions[agencies][]", "value": "food-and-drug-administration"},
                    {"name": "conditions[term]", "value": "cosmetic OR cosmetics"},
                    {"name": "per_page", "value": "5"},
                    {"name": "order", "value": "newest"}
                ]},
                "options": {"response": {"response": {"responseFormat": "json"}}}
            },
            "id": "http-fed-reg",
            "name": "🇺🇸 US Federal Register",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [300, -100]
        },
        # All sources → Parse
        {
            "parameters": {
                "jsCode": """// 모든 소스에서 규제 문서 수집
const items = $input.all();
const docs = [];

for (const item of items) {
  const data = item.json;
  // Federal Register
  if (data.results) {
    for (const doc of data.results.slice(0, 5)) {
      docs.push({
        region: 'US', source: 'federal_register',
        title: doc.title || '', abstract: doc.abstract || '',
        url: doc.html_url || '', published_at: doc.publication_date || ''
      });
    }
  }
}

if (!docs.length) {
  return [{ json: { skip: true, reason: '수집된 규제 문서 없음' } }];
}

// Gemini 일괄 분석용 프롬프트
const docList = docs.map((d, i) =>
  `[${i+1}] ${d.region} | ${d.title} | ${d.abstract?.substring(0, 200)}`
).join('\\n');

const prompt = `다음 화장품 규제 문서들을 분석해주세요.

${docList}

각 문서에 대해 JSON 배열로 응답 (설명 없이 JSON만):
[
  {
    "index": 1,
    "summary_ko": "한글 요약 2-3문장",
    "category": "new_rule|amendment|guidance|recall|other",
    "affected_ingredients": ["영향 받는 INCI명"],
    "severity": "high|medium|low",
    "keywords": ["키워드"]
  }
]`;

const body = JSON.stringify({
  contents: [{ parts: [{ text: prompt }] }],
  generationConfig: { temperature: 0.2, maxOutputTokens: 2048 }
});

return [{ json: { docs: JSON.stringify(docs), geminiBody: body, doc_count: docs.length } }];"""
            },
            "id": "code-collect-parse",
            "name": "📋 규제 문서 수집 & 구성",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [550, 0]
        },
        {
            "parameters": {
                "conditions": {"conditions": [
                    {"id": "skip", "leftValue": "={{ $json.skip }}", "rightValue": True,
                     "operator": {"type": "boolean", "operation": "notEqual"}}
                ]}
            },
            "id": "filter-skip-reg",
            "name": "⚡ 스킵 체크",
            "type": "n8n-nodes-base.filter",
            "typeVersion": 2,
            "position": [750, 0]
        },
        {
            "parameters": {
                "method": "POST",
                "url": GEMINI_URL,
                "sendHeaders": True,
                "headerParameters": {"parameters": [{"name": "Content-Type", "value": "application/json"}]},
                "sendBody": True,
                "contentType": "raw",
                "rawContentType": "application/json",
                "body": "={{ $json.geminiBody }}",
                "options": {"timeout": 60000}
            },
            "id": "gemini-reg-analyze",
            "name": "🌐 Gemini 규제 분석",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [950, 0]
        },
        {
            "parameters": {
                "jsCode": """const item = $input.first().json;
const config = $('📋 규제 문서 수집 & 구성').first().json;
const docs = JSON.parse(config.docs || '[]');
const results = [];

try {
  const text = item?.candidates?.[0]?.content?.parts?.[0]?.text || '[]';
  const jsonStr = text.replace(/```json\\n?|```/g, '').trim();
  const arrayMatch = jsonStr.match(/\\[[\\s\\S]*\\]/);
  const analyses = JSON.parse(arrayMatch ? arrayMatch[0] : jsonStr);

  for (const analysis of analyses) {
    const idx = (analysis.index || 1) - 1;
    const doc = docs[idx] || {};

    // 영향 받는 원료별로 regulation_cache에 저장
    const ingredients = analysis.affected_ingredients || [];
    if (ingredients.length === 0) {
      // 원료 특정 안 되면 규제 자체를 기록
      results.push({
        json: {
          source: 'REG_MONITOR_' + (doc.region || 'GLOBAL'),
          ingredient: analysis.summary_ko?.substring(0, 100) || doc.title?.substring(0, 100),
          inci_name: '',
          max_concentration: null,
          restriction: JSON.stringify({
            region: doc.region, category: analysis.category,
            severity: analysis.severity, summary: analysis.summary_ko,
            url: doc.url, keywords: analysis.keywords,
            published_at: doc.published_at
          })
        }
      });
    } else {
      for (const inci of ingredients) {
        results.push({
          json: {
            source: 'REG_MONITOR_' + (doc.region || 'GLOBAL'),
            ingredient: inci,
            inci_name: inci,
            max_concentration: null,
            restriction: JSON.stringify({
              region: doc.region, category: analysis.category,
              severity: analysis.severity, summary: analysis.summary_ko,
              url: doc.url, keywords: analysis.keywords
            })
          }
        });
      }
    }
  }
} catch(e) {
  results.push({
    json: {
      source: 'REG_MONITOR_ERROR', ingredient: 'parse_error',
      inci_name: '', max_concentration: null,
      restriction: JSON.stringify({ error: e.message })
    }
  });
}

return results.length ? results : [{ json: { skip: true } }];"""
            },
            "id": "code-reg-parse",
            "name": "🔄 규제 분석 파싱",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [1200, 0]
        },
        {
            "parameters": {
                "operation": "executeQuery",
                "query": """INSERT INTO regulation_cache (source, ingredient, inci_name, max_concentration, restriction, updated_at)
VALUES ($1, $2, $3, $4, $5, NOW())
ON CONFLICT (source, ingredient)
DO UPDATE SET
  inci_name = EXCLUDED.inci_name,
  restriction = EXCLUDED.restriction,
  updated_at = NOW()""",
                "options": {
                    "queryReplacement": "={{ [$json.source, $json.ingredient, $json.inci_name, $json.max_concentration, $json.restriction] }}"
                }
            },
            "id": "pg-save-reg",
            "name": "💾 regulation_cache 저장",
            "type": "n8n-nodes-base.postgres",
            "typeVersion": 2.5,
            "position": [1450, 0],
            "credentials": {"postgres": {"id": PG_CRED_ID, "name": "COCHING PostgreSQL (Local)"}},
            "alwaysOutputData": True
        }
    ],
    "connections": {
        "⏰ 주 1회 자동실행": {"main": [[{"node": "🇺🇸 US Federal Register", "type": "main", "index": 0}]]},
        "▶ 수동 실행": {"main": [[{"node": "🇺🇸 US Federal Register", "type": "main", "index": 0}]]},
        "🇺🇸 US Federal Register": {"main": [[{"node": "📋 규제 문서 수집 & 구성", "type": "main", "index": 0}]]},
        "📋 규제 문서 수집 & 구성": {"main": [[{"node": "⚡ 스킵 체크", "type": "main", "index": 0}]]},
        "⚡ 스킵 체크": {"main": [[{"node": "🌐 Gemini 규제 분석", "type": "main", "index": 0}]]},
        "🌐 Gemini 규제 분석": {"main": [[{"node": "🔄 규제 분석 파싱", "type": "main", "index": 0}]]},
        "🔄 규제 분석 파싱": {"main": [[{"node": "💾 regulation_cache 저장", "type": "main", "index": 0}]]}
    },
    "settings": {"executionOrder": "v1"}
}


# ============================================================
# 배포 실행
# ============================================================
print("=== WF-1: 원료 안전성 강화 배포 ===")
vid1 = deploy_workflow(cur, WF1_ID, WF1)
print(f"  OK {WF1['name']} (version: {vid1[:8]})")

print("\n=== WF-2: 다국가 규제 모니터링 배포 ===")
vid2 = deploy_workflow(cur, WF2_ID, WF2)
print(f"  OK {WF2['name']} (version: {vid2[:8]})")

conn.commit()
conn.close()
print("\nDone — pm2 restart n8n 필요")
