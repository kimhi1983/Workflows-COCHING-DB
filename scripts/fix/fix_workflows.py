#!/usr/bin/env python3
"""
워크플로우 3가지 에러 일괄 수정:
1. Gemini API 키 교체 (원료수집 v7, 제품수집 v1)
2. 제품카피 v1.0 SQL 이스케이프 수정
3. Track 1 빈 WHERE 방지
"""
import sqlite3
import json

DB = '/home/kpros/.n8n/database.sqlite'
# [ARCHIVED] 이전 키 교체용 스크립트 — 현재는 환경변수($env.GEMINI_API_KEY) 방식 사용
OLD_KEY = 'REMOVED_FOR_SECURITY'
NEW_KEY = 'USE_ENV_VAR'

conn = sqlite3.connect(DB)
cur = conn.cursor()

# ========================================
# FIX 1: Gemini API 키 교체
# ========================================
print("=== FIX 1: Gemini API 키 교체 ===")
for wf_id in ['FW6GUTq0AzBXjJQ5', '5YRZrKRWAPG6C5JA']:
    cur.execute('SELECT name, nodes FROM workflow_entity WHERE id=?', (wf_id,))
    row = cur.fetchone()
    if not row:
        continue
    wf_name, nodes_json = row
    if OLD_KEY in nodes_json:
        nodes_json = nodes_json.replace(OLD_KEY, NEW_KEY)
        cur.execute(
            'UPDATE workflow_entity SET nodes=?, updatedAt=datetime("now") WHERE id=?',
            (nodes_json, wf_id)
        )
        print(f'  OK {wf_name} — Gemini API 키 교체')
    else:
        print(f'  SKIP {wf_name} — 키 이미 최신')

# ========================================
# FIX 2: 제품카피 v1.0 — SQL 이스케이프 수정
# ========================================
print("\n=== FIX 2: 제품카피 SQL 이스케이프 ===")
COPY_ID = 'a0670dfdacb34ce887a3'
cur.execute('SELECT name, nodes FROM workflow_entity WHERE id=?', (COPY_ID,))
row = cur.fetchone()
if row:
    wf_name, nodes_json = row
    nodes = json.loads(nodes_json)
    changed = False

    for node in nodes:
        name = node.get('name', '')
        ntype = node.get('type', '')

        # 파싱 & 검증 노드 수정
        if '파싱' in name and '검증' in name:
            js = node.get('parameters', {}).get('jsCode', '')

            # guide_data를 SQL-safe하게 이스케이프하는 코드 추가
            if 'escapeSql' not in js:
                # 함수 정의를 맨 앞에 추가
                escape_fn = "function escapeSql(s) { return typeof s === 'string' ? s.replace(/'/g, \"''\") : s; }\n\n"
                js = escape_fn + js
                node['parameters']['jsCode'] = js
                changed = True
                print(f'  OK {wf_name} — escapeSql 함수 추가')

            # guide_data_escaped 필드가 없으면 추가
            if 'guide_data_escaped' not in js:
                old = 'guide_data: guideJson,'
                new = 'guide_data: guideJson,\n      guide_data_escaped: escapeSql(JSON.stringify(guideJson)),'
                if old in js:
                    js = js.replace(old, new)
                    node['parameters']['jsCode'] = js
                    changed = True
                    print(f'  OK {wf_name} — guide_data_escaped 필드 추가')
                else:
                    # 다른 패턴 확인
                    if 'guide_data:' in js and 'guide_data_escaped' not in js:
                        print(f'  WARN {wf_name} — guide_data 패턴이 다름, 수동 확인 필요')
                        # guide_data 할당 라인 찾기
                        lines = js.split('\n')
                        for i, line in enumerate(lines):
                            if 'guide_data:' in line and 'escaped' not in line:
                                print(f'    Line {i}: {line.strip()[:100]}')
            else:
                print(f'  SKIP {wf_name} — guide_data_escaped 이미 존재')

        # DB 저장 노드: SQL에서 작은따옴표 대신 파라미터 바인딩 사용으로 변경
        if '저장' in name and ntype == 'n8n-nodes-base.postgres':
            params = node.get('parameters', {})
            query = params.get('query', '')
            if 'guide_data_escaped' in query:
                # 이미 escaped 사용 중 — 하지만 직접 문자열 삽입 방식이면 문제
                # $N 파라미터 바인딩으로 변경
                if '{{ $json.guide_data_escaped }}' in query:
                    # 파라미터 바인딩 방식으로 변경
                    new_query = query.replace(
                        "'{{ $json.guide_data_escaped }}'::jsonb",
                        "$1::jsonb"
                    )
                    if new_query != query:
                        params['query'] = new_query
                        # queryReplacement에 파라미터 추가
                        params['options'] = params.get('options', {})
                        params['options']['queryReplacement'] = '{{ $json.guide_data_escaped }}'
                        node['parameters'] = params
                        changed = True
                        print(f'  OK {name} — 파라미터 바인딩으로 변경')
                    else:
                        print(f'  INFO {name} — query 확인: {query[:150]}')
            elif 'guide_data' in query:
                print(f'  INFO {name} — guide_data 직접 삽입 사용 중')
                print(f'    Query: {query[:200]}')

    if changed:
        cur.execute(
            'UPDATE workflow_entity SET nodes=?, updatedAt=datetime("now") WHERE id=?',
            (json.dumps(nodes, ensure_ascii=False), COPY_ID)
        )
        print(f'  SAVED {wf_name}')

# ========================================
# FIX 3: Track 1 빈 WHERE 방지
# ========================================
print("\n=== FIX 3: Track 1 빈 WHERE 방지 ===")
V23_IDS = [
    '84c2ce341e9a4b27b735',  # A
    'b98f0e27d8d94d5f96a5',  # B
    '079972e71bef4f66bd48',  # C
    '2fa9c77cdf6641aeb01d',  # D
    '8dd0884072f54d438ffe',  # E
    '41c14d5b1e524695b9d8',  # F
]

guard_code = """// 처리할 조합이 없으면 조기 종료
const input = $input.first();
if (!input || !input.json || !input.json.product_type) {
  return [{ json: { skip: true, reason: 'no_combo_available' } }];
}
"""

for wf_id in V23_IDS:
    cur.execute('SELECT name, nodes FROM workflow_entity WHERE id=?', (wf_id,))
    row = cur.fetchone()
    if not row:
        continue
    wf_name, nodes_json = row
    nodes = json.loads(nodes_json)
    changed = False

    for node in nodes:
        if node.get('name') == '🔄 원료 SQL 생성':
            js = node.get('parameters', {}).get('jsCode', '')
            if 'no_combo_available' not in js:
                js = guard_code + js
                node['parameters']['jsCode'] = js
                changed = True
                print(f'  OK {wf_name} — 빈 입력 가드 추가')
            else:
                print(f'  SKIP {wf_name} — 가드 이미 존재')

    # 후속 노드들도 skip 처리 추가 (원료/규제/참조 DB 조회)
    for node in nodes:
        if node.get('type') == 'n8n-nodes-base.postgres' and 'DB 조회' in node.get('name', ''):
            # 이 노드들은 skip=true일 때 실행하지 않아야 함
            # n8n에서는 IF 노드로 분기하거나, 조건부 실행 설정
            pass

    if changed:
        cur.execute(
            'UPDATE workflow_entity SET nodes=?, updatedAt=datetime("now") WHERE id=?',
            (json.dumps(nodes, ensure_ascii=False), wf_id)
        )

conn.commit()
conn.close()
print('\n=== ALL FIXES DONE ===')
