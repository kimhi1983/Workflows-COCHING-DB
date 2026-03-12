#!/usr/bin/env python3
"""
워크플로우 최종 수정 v3:
1. Gemini API 키 교체 (새 유효 키)
2. 제품카피 source_product_id null 문제 수정
"""
import sqlite3, json, uuid
from datetime import datetime

DB = '/home/kpros/.n8n/database.sqlite'
OLD_KEY = 'AIzaSyBBFQlkFXHJPD75eNlWfjIWzXoKm9CgZss'
NEW_KEY = 'AIzaSyAMLi4_wB7lwMsbkg7tEo1F0-KF34ew-GA'
# 이전 키도 교체
OLD_KEY2 = 'AIzaSyAXhVn-G1r9XuMDOm__AP_gt5Do9lrXHtk'

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
# FIX 1: Gemini API 키 교체
# ========================================
print("=== FIX 1: Gemini API 키 교체 ===")
for wf_id in ['FW6GUTq0AzBXjJQ5', '5YRZrKRWAPG6C5JA']:
    cur.execute('SELECT name, nodes FROM workflow_entity WHERE id=?', (wf_id,))
    row = cur.fetchone()
    if not row:
        continue
    wf_name, nodes_json = row
    changed = False
    if OLD_KEY in nodes_json:
        nodes_json = nodes_json.replace(OLD_KEY, NEW_KEY)
        changed = True
    if OLD_KEY2 in nodes_json:
        nodes_json = nodes_json.replace(OLD_KEY2, NEW_KEY)
        changed = True
    if changed:
        cur.execute('UPDATE workflow_entity SET nodes=?, updatedAt=datetime("now") WHERE id=?',
                    (nodes_json, wf_id))
        vid = publish_workflow(cur, wf_id)
        print(f'  OK {wf_name} — 키 교체 + version: {vid[:8]}')
    else:
        print(f'  SKIP {wf_name}')

# ========================================
# FIX 2: 제품카피 source_product_id null 수정
# ========================================
print("\n=== FIX 2: 제품카피 source_product_id null 수정 ===")
COPY_ID = 'a0670dfdacb34ce887a3'
cur.execute('SELECT name, nodes FROM workflow_entity WHERE id=?', (COPY_ID,))
row = cur.fetchone()
if row:
    wf_name, nodes_json = row
    nodes = json.loads(nodes_json)
    changed = False

    for node in nodes:
        name = node.get('name', '')

        # 파싱 & 검증 노드에서 source_product_id 필드 확인
        if '파싱' in name and '검증' in name:
            js = node.get('parameters', {}).get('jsCode', '')

            # source_product_id가 어떻게 설정되는지 확인
            if 'source_product_id' in js:
                # 이미 있으면 확인
                lines = js.split('\n')
                for i, line in enumerate(lines):
                    if 'source_product_id' in line:
                        print(f'  Line {i}: {line.strip()[:150]}')
            else:
                print(f'  WARN: source_product_id 필드 없음 — 추가 필요')

            # $json에서 source_product_id를 가져오는 로직 확인
            # 파싱 노드의 입력은 SSH 노드 출력 → Claude 응답
            # source_product_id는 프롬프트 구성 노드에서 설정됨
            # 파싱 노드에서 원본 입력 데이터를 참조해야 함

            # source_product_id가 null인 이유: 파싱 노드가 SSH 출력만 받고
            # 원본 product_id를 전달받지 못함
            # 수정: $('⚙️ 대상 설정') 또는 $('🔍 미카피 제품 찾기')에서 가져오기

            if 'source_product_id' not in js or "source_product_id: null" in js or "source_product_id: $json.source_product_id" in js:
                # SSH 출력에는 source_product_id가 없을 수 있음
                # 이전 노드에서 가져오는 코드 추가
                old_marker = "const rawOutput = $json"
                if old_marker not in js:
                    # 다른 패턴 찾기
                    if "const rawOutput" in js:
                        print(f'  Found rawOutput pattern')
                    elif "$json.response" in js or "$json.stdout" in js:
                        print(f'  Found $json.response/stdout pattern')

            print(f'\n  JS code first 500 chars:')
            print(f'  {js[:500]}')
            print(f'  ...')
            print(f'  JS code source_product_id area:')
            for i, line in enumerate(js.split('\n')):
                if 'source' in line.lower() or 'product_id' in line.lower() or 'prod_id' in line.lower():
                    print(f'  L{i}: {line.strip()[:150]}')

    # 프롬프트 구성 노드도 확인
    for node in nodes:
        name = node.get('name', '')
        if '프롬프트 구성' in name:
            js = node.get('parameters', {}).get('jsCode', '')
            print(f'\n  === {name} - source 관련 ===')
            for i, line in enumerate(js.split('\n')):
                if 'source' in line.lower() or 'prod_id' in line.lower() or 'product_id' in line.lower():
                    print(f'  L{i}: {line.strip()[:150]}')

conn.commit()
conn.close()
print('\nDone')
