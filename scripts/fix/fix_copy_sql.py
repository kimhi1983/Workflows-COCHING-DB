#!/usr/bin/env python3
"""
제품카피 v1.0 SQL 저장 노드를 파라미터 바인딩 방식으로 완전 교체
문제: guide_data JSON에 작은따옴표가 포함되어 SQL syntax error
해결: PostgreSQL $1 파라미터 바인딩 사용
"""
import sqlite3, json

DB = '/home/kpros/.n8n/database.sqlite'
COPY_ID = 'a0670dfdacb34ce887a3'

conn = sqlite3.connect(DB)
cur = conn.cursor()

cur.execute('SELECT name, nodes FROM workflow_entity WHERE id=?', (COPY_ID,))
row = cur.fetchone()
if not row:
    print("Workflow not found")
    exit()

wf_name, nodes_json = row
nodes = json.loads(nodes_json)
changed = False

for node in nodes:
    name = node.get('name', '')

    # 카피가이드 저장 노드 수정
    if '카피가이드 저장' in name or ('저장' in name and 'guide_cache_copy' in node.get('parameters', {}).get('query', '')):
        print(f"\n=== {name} ===")
        params = node.get('parameters', {})
        old_query = params.get('query', '')
        print(f"Old query:\n{old_query[:300]}")

        # 완전히 새 쿼리로 교체 — $1~$10 파라미터 바인딩
        new_query = """INSERT INTO guide_cache_copy
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

        params['query'] = new_query
        params['options'] = params.get('options', {})
        # n8n PostgreSQL v2.5: queryReplacement으로 파라미터 전달
        params['options']['queryReplacement'] = '={{ [$json.source_product_id, $json.source, $json.prod_name, $json.formula_name, JSON.stringify($json.guide_data || $json.guideJson || {}), $json.total_wt_percent || 0, $json.wt_valid || false, $json.estimated_ph || null, $json.confidence || "medium"] }}'

        node['parameters'] = params
        changed = True
        print(f"\nNew query:\n{new_query[:300]}")
        print(f"\nQuery params: $1~$9 binding via queryReplacement")

    # 파싱 노드 확인 — guide_data가 제대로 전달되는지
    if '파싱' in name and '검증' in name:
        js = node.get('parameters', {}).get('jsCode', '')
        # guide_data 출력 필드 확인
        if 'guide_data:' in js:
            # guideJson이 그대로 전달되는지 확인
            lines = js.split('\n')
            for i, line in enumerate(lines):
                if 'guide_data' in line and i < len(lines):
                    print(f"\nParsing node line {i}: {line.strip()[:150]}")

if changed:
    cur.execute(
        'UPDATE workflow_entity SET nodes=?, updatedAt=datetime("now") WHERE id=?',
        (json.dumps(nodes, ensure_ascii=False), COPY_ID)
    )
    conn.commit()
    print("\n✅ 저장 완료")
else:
    print("\n⚠️ 변경사항 없음")

conn.close()
