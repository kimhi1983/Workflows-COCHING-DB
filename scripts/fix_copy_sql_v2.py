#!/usr/bin/env python3
"""
제품카피 v1.0 + Track 1 비활성화 — activeVersionId 포함 완전 수정
"""
import sqlite3, json, uuid
from datetime import datetime

DB = '/home/kpros/.n8n/database.sqlite'

conn = sqlite3.connect(DB)
cur = conn.cursor()

def publish_workflow(cur, wf_id):
    """workflow_history에 새 버전 생성 + activeVersionId 설정"""
    cur.execute('SELECT nodes, connections FROM workflow_entity WHERE id=?', (wf_id,))
    row = cur.fetchone()
    if not row:
        return
    nodes_json, conns_json = row

    version_id = str(uuid.uuid4())
    now = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S.000')

    cur.execute("""
        INSERT INTO workflow_history (versionId, workflowId, nodes, connections, authors, createdAt, updatedAt)
        VALUES (?, ?, ?, ?, '[]', ?, ?)
    """, (version_id, wf_id, nodes_json, conns_json, now, now))

    cur.execute("""
        UPDATE workflow_entity SET activeVersionId=?, updatedAt=? WHERE id=?
    """, (version_id, now, wf_id))

    return version_id


# ========================================
# FIX: 제품카피 v1.0 — 카피가이드 저장 노드 SQL 교체
# ========================================
COPY_ID = 'a0670dfdacb34ce887a3'
cur.execute('SELECT name, nodes FROM workflow_entity WHERE id=?', (COPY_ID,))
row = cur.fetchone()
if row:
    wf_name, nodes_json = row
    nodes = json.loads(nodes_json)
    changed = False

    for node in nodes:
        name = node.get('name', '')

        if name == '💾 카피가이드 저장':
            params = node.get('parameters', {})
            old_query = params.get('query', '')
            print(f"Old query:\n{old_query[:200]}\n")

            # 완전히 새 쿼리로 교체 — $1~$9 파라미터 바인딩
            params['query'] = """INSERT INTO guide_cache_copy
  (source_product_id, source, original_product_name, formula_name,
   guide_data, total_wt_percent, wt_valid, estimated_ph, confidence, created_at)
VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7, $8, $9, NOW())
ON CONFLICT (source_product_id, source)
DO UPDATE SET
  original_product_name = EXCLUDED.original_product_name,
  formula_name = EXCLUDED.formula_name,
  guide_data = EXCLUDED.guide_data,
  total_wt_percent = EXCLUDED.total_wt_percent,
  wt_valid = EXCLUDED.wt_valid,
  estimated_ph = EXCLUDED.estimated_ph,
  confidence = EXCLUDED.confidence,
  updated_at = NOW()"""

            params['options'] = params.get('options', {})
            params['options']['queryReplacement'] = '={{ [$json.source_product_id, $json.source, $json.prod_name, $json.formula_name, JSON.stringify($json.guide_data || $json.guideJson || {}), $json.total_wt_percent || 0, $json.wt_valid || false, $json.estimated_ph || null, $json.confidence || "medium"] }}'

            node['parameters'] = params
            changed = True
            print("✅ 카피가이드 저장 — 파라미터 바인딩으로 교체")

    if changed:
        cur.execute(
            'UPDATE workflow_entity SET nodes=?, updatedAt=datetime("now") WHERE id=?',
            (json.dumps(nodes, ensure_ascii=False), COPY_ID)
        )
        vid = publish_workflow(cur, COPY_ID)
        print(f"✅ {wf_name} — activeVersionId: {vid}")

# ========================================
# Track 1 비활성화 확인 + activeVersionId 갱신
# ========================================
V23_IDS = [
    '84c2ce341e9a4b27b735',
    'b98f0e27d8d94d5f96a5',
    '079972e71bef4f66bd48',
    '2fa9c77cdf6641aeb01d',
    '8dd0884072f54d438ffe',
    '41c14d5b1e524695b9d8',
]

print("\n=== Track 1 비활성화 ===")
for wf_id in V23_IDS:
    cur.execute('SELECT name, active FROM workflow_entity WHERE id=?', (wf_id,))
    row = cur.fetchone()
    if row:
        wf_name, active = row
        if active != 0:
            cur.execute('UPDATE workflow_entity SET active=0, updatedAt=datetime("now") WHERE id=?', (wf_id,))
            print(f"  ✅ {wf_name} — 비활성화")
        else:
            print(f"  ✓ {wf_name} — 이미 비활성(active=0)")
        # 버전도 갱신
        vid = publish_workflow(cur, wf_id)
        print(f"    activeVersionId: {vid}")

conn.commit()

# 검증
print("\n=== 최종 상태 ===")
cur.execute("SELECT name, active, activeVersionId FROM workflow_entity WHERE active=1 ORDER BY name")
for row in cur.fetchall():
    print(f"  ON: {row[0]} (version: {row[2][:8] if row[2] else 'none'}...)")

cur.execute("SELECT name, active FROM workflow_entity WHERE active=0 ORDER BY name")
for row in cur.fetchall():
    print(f"  OFF: {row[0]}")

conn.close()
print("\n✅ 완료. pm2 restart n8n 필요")
