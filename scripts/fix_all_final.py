#!/usr/bin/env python3
"""
워크플로우 최종 수정:
1. 제품카피 v1.0 — source_product_id null 수정 (prod_id → source_product_id 매핑)
2. 제품카피 v1.0 — SQL 이스케이프 강화 (파라미터 바인딩)
3. Track 1 (v2.3-A~F) — 완료된 워크플로우 비활성화
"""
import sqlite3, json, uuid
from datetime import datetime

DB = '/home/kpros/.n8n/database.sqlite'

conn = sqlite3.connect(DB)
cur = conn.cursor()

def publish_workflow(cur, wf_id):
    cur.execute('SELECT nodes, connections FROM workflow_entity WHERE id=?', (wf_id,))
    row = cur.fetchone()
    if not row:
        return None
    nodes_json, conns_json = row
    version_id = str(uuid.uuid4())
    now = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S.000')
    cur.execute("""
        INSERT INTO workflow_history (versionId, workflowId, nodes, connections, authors, createdAt, updatedAt)
        VALUES (?, ?, ?, ?, '[]', ?, ?)
    """, (version_id, wf_id, nodes_json, conns_json, now, now))
    cur.execute("UPDATE workflow_entity SET activeVersionId=?, updatedAt=? WHERE id=?",
                (version_id, now, wf_id))
    return version_id


# ========================================
# FIX 1: 제품카피 — source_product_id + SQL escape
# ========================================
print("=== FIX 1: 제품카피 v1.0 수정 ===")
COPY_ID = 'a0670dfdacb34ce887a3'
cur.execute('SELECT name, nodes FROM workflow_entity WHERE id=?', (COPY_ID,))
row = cur.fetchone()
if row:
    wf_name, nodes_json = row
    nodes = json.loads(nodes_json)
    changed = False

    for node in nodes:
        name = node.get('name', '')

        # 파싱 & 검증 노드 수정
        if '파싱' in name and '검증' in name:
            js = node.get('parameters', {}).get('jsCode', '')

            # source_product_id: config.source_product_id → config.prod_id
            if 'config.source_product_id' in js:
                js = js.replace('config.source_product_id', 'config.prod_id')
                print(f'  OK source_product_id -> prod_id 매핑 수정')
                changed = True

            # SQL 이스케이프 강화: guide_data에 작은따옴표 처리
            # escapeSql 함수가 있는지 확인
            if 'escapeSql' not in js:
                # 함수 추가
                escape_fn = "function escapeSql(s) { return typeof s === 'string' ? s.replace(/'/g, \"''\") : s; }\n\n"
                js = escape_fn + js
                print(f'  OK escapeSql 함수 추가')
                changed = True

            node['parameters']['jsCode'] = js

        # DB 저장 노드 — 파라미터 바인딩으로 전환
        if 'guide_cache_copy' in node.get('name', '') or ('저장' in name and 'DB' in name):
            params = node.get('parameters', {})
            query = params.get('query', '')
            if 'guide_cache_copy' in query and '{{ $json' in query:
                # 템플릿 리터럴 방식을 파라미터 바인딩으로 교체
                new_query = """INSERT INTO guide_cache_copy
  (source_product_id, source, original_product_name, formula_name,
   guide_data, total_wt_percent, wt_valid, estimated_ph, confidence, created_at)
VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7, $8, $9, NOW())
ON CONFLICT (source_product_id, source) DO UPDATE SET
  guide_data = EXCLUDED.guide_data,
  total_wt_percent = EXCLUDED.total_wt_percent,
  wt_valid = EXCLUDED.wt_valid,
  confidence = EXCLUDED.confidence,
  updated_at = NOW()"""
                params['query'] = new_query
                params['options'] = {'queryReplacement': '={{ [$json.source_product_id, $json.source, $json.prod_name, $json.formula_name, $json.guide_data_json, $json.total_wt_percent, $json.wt_valid, $json.estimated_ph, $json.confidence] }}'}
                node['parameters'] = params
                print(f'  OK {name} — 파라미터 바인딩 전환')
                changed = True

    # 파싱 노드에서 guide_data_json 필드 추가 (JSON string for $5)
    for node in nodes:
        name = node.get('name', '')
        if '파싱' in name and '검증' in name:
            js = node.get('parameters', {}).get('jsCode', '')
            if 'guide_data_json' not in js and 'guide_data' in js:
                # guide_data_json: JSON.stringify(guideJson) 추가
                js = js.replace(
                    'guide_data: guideJson,',
                    'guide_data: guideJson,\n      guide_data_json: JSON.stringify(guideJson),'
                )
                # guide_data_escaped도 이미 있으면 유지
                node['parameters']['jsCode'] = js
                if 'guide_data_json' in js:
                    print(f'  OK guide_data_json 필드 추가')
                    changed = True

    if changed:
        cur.execute('UPDATE workflow_entity SET nodes=?, updatedAt=datetime("now") WHERE id=?',
                    (json.dumps(nodes, ensure_ascii=False), COPY_ID))
        vid = publish_workflow(cur, COPY_ID)
        print(f'  OK {wf_name} — version: {vid[:8]}')

# ========================================
# FIX 2: Track 1 (v2.3-A~F) 비활성화
# ========================================
print("\n=== FIX 2: Track 1 완료 워크플로우 비활성화 ===")
V23_IDS = [
    '84c2ce341e9a4b27b735',  # A
    'b98f0e27d8d94d5f96a5',  # B
    '079972e71bef4f66bd48',  # C
    '2fa9c77cdf6641aeb01d',  # D
    '8dd0884072f54d438ffe',  # E
    '41c14d5b1e524695b9d8',  # F
]

for wf_id in V23_IDS:
    cur.execute('SELECT name, active FROM workflow_entity WHERE id=?', (wf_id,))
    row = cur.fetchone()
    if not row:
        continue
    wf_name, active = row
    if active:
        cur.execute('UPDATE workflow_entity SET active=0, updatedAt=datetime("now") WHERE id=?', (wf_id,))
        print(f'  OK {wf_name} — 비활성화 (215/215 완료)')
    else:
        print(f'  SKIP {wf_name} — 이미 비활성')

conn.commit()
conn.close()
print('\nAll fixes applied.')
