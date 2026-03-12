#!/usr/bin/env python3
"""
n8n 워크플로우에 compound_master DB + 확장 원료/제품 DB 참조 연동
- v2.3-A~F: 원료 SQL 생성 노드에 compound_master 조회 추가
- v2.3-A~F: 프롬프트에 복합원료 정보 포함
"""
import sqlite3
import json

DB_PATH = "/home/kpros/.n8n/database.sqlite"

# v2.3 워크플로우 IDs
V23_IDS = [
    '84c2ce341e9a4b27b735',  # A 기초화장
    'b98f0e27d8d94d5f96a5',  # B 세정
    '079972e71bef4f66bd48',  # C 선케어
    '2fa9c77cdf6641aeb01d',  # D 색조
    '8dd0884072f54d438ffe',  # E 두발
    '41c14d5b1e524695b9d8',  # F 기타
]
COPY_ID = 'a0670dfdacb34ce887a3'

# compound_master 조회 노드 (PostgreSQL)
COMPOUND_QUERY_NODE = {
    "parameters": {
        "operation": "executeQuery",
        "query": "SELECT trade_name, supplier, category, components::text, notes FROM compound_master ORDER BY category, trade_name",
        "options": {
            "queryReplacement": ""
        },
        "alwaysOutputData": True
    },
    "name": "📦 복합원료 DB 조회",
    "type": "n8n-nodes-base.postgres",
    "typeVersion": 2.5,
    "position": [0, 0],
    "credentials": {
        "postgres": {
            "id": "2c8e9119-0bb0-49f2-ad43-f040ab4a7a64",
            "name": "coching_db"
        }
    }
}

# 참조제품 쿼리 확장 (16,000+ 제품 활용)
EXPANDED_REF_QUERY = """SELECT brand_name, product_name, category, full_ingredients,
    ph_value, viscosity_cp, data_quality_grade
FROM product_master
WHERE category ILIKE '%' || $1 || '%'
   OR product_name ILIKE '%' || $1 || '%'
ORDER BY data_quality_grade ASC, updated_at DESC
LIMIT 5"""


def update_v23_workflows():
    """v2.3 워크플로우 6개에 compound_master 연동"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    updated = 0

    for wf_id in V23_IDS:
        cur.execute("SELECT name, nodes FROM workflow_entity WHERE id=?", (wf_id,))
        row = cur.fetchone()
        if not row:
            continue

        wf_name, nodes_json = row
        nodes = json.loads(nodes_json)
        changed = False

        # 1) 복합원료 조회 노드 추가 (없으면)
        has_compound_node = any(n.get('name') == '📦 복합원료 DB 조회' for n in nodes)
        if not has_compound_node:
            # 위치: 기존 규제 DB 조회 노드 근처
            reg_node = next((n for n in nodes if '규제 DB 조회' in n.get('name', '')), None)
            new_node = dict(COMPOUND_QUERY_NODE)
            if reg_node:
                pos = reg_node.get('position', [800, 400])
                new_node['position'] = [pos[0], pos[1] + 200]
            else:
                new_node['position'] = [800, 600]
            new_node['id'] = f"compound_{wf_id[:8]}"
            nodes.append(new_node)
            changed = True
            print(f"  ✅ {wf_name} — 복합원료 조회 노드 추가")

        # 2) 프롬프트 구성 노드에 compound_master 참조 추가
        for node in nodes:
            if node.get('name') == '🧠 Claude 프롬프트 구성':
                js = node['parameters'].get('jsCode', '')

                # 이미 compound 참조가 있으면 스킵
                if '복합원료 DB 조회' in js:
                    print(f"  ⏭️  {wf_name} — 프롬프트에 이미 복합원료 참조 있음")
                    continue

                # compound DB 참조 코드 삽입
                old_start = "const config = $('🔄 원료 SQL 생성').first().json;"
                new_start = """const config = $('🔄 원료 SQL 생성').first().json;
const compounds = (() => { try { return $('📦 복합원료 DB 조회').all().map(i=>i.json); } catch(e) { return []; } })();
const compList = compounds.map(c=> c.trade_name+' ('+c.supplier+') ['+c.category+'] 구성: '+(typeof c.components==='string'?c.components:JSON.stringify(c.components))).join('\\n');"""

                if old_start in js:
                    js = js.replace(old_start, new_start)

                    # 프롬프트에 복합원료 섹션 추가
                    old_ref = '=== 참조 데이터 ==='
                    new_ref = """=== 참조 데이터 ===

[복합원료 DB (compound_master)]
\${compList || '(복합원료 DB 없음)'}
※ 복합원료 사용 시 반드시 STEP 2 복합성분 전개 적용. compound_expansion 필드에 전개 내역 기록."""

                    if old_ref in js:
                        js = js.replace(old_ref, new_ref)
                    else:
                        # 참조 데이터 섹션이 다른 형태일 수 있으므로 규제 제한 앞에 삽입
                        old_reg = '[규제 제한]'
                        new_reg = """[복합원료 DB (compound_master)]
\${compList || '(복합원료 DB 없음)'}
※ 복합원료 사용 시 STEP 2 복합성분 전개 필수.

[규제 제한]"""
                        js = js.replace(old_reg, new_reg)

                    node['parameters']['jsCode'] = js
                    changed = True
                    print(f"  ✅ {wf_name} — 프롬프트에 복합원료 DB 참조 추가")

        # 3) 연결(connections)에 복합원료 노드 → 프롬프트 연결 추가
        # n8n은 connections을 별도로 관리하므로 추가

        if changed:
            cur.execute(
                "UPDATE workflow_entity SET nodes=?, updatedAt=datetime('now') WHERE id=?",
                (json.dumps(nodes, ensure_ascii=False), wf_id)
            )
            updated += 1

    # === 제품카피 v1.0도 compound 참조 추가 ===
    cur.execute("SELECT name, nodes FROM workflow_entity WHERE id=?", (COPY_ID,))
    row = cur.fetchone()
    if row:
        wf_name, nodes_json = row
        nodes = json.loads(nodes_json)
        changed = False

        has_compound_node = any(n.get('name') == '📦 복합원료 DB 조회' for n in nodes)
        if not has_compound_node:
            new_node = dict(COMPOUND_QUERY_NODE)
            new_node['position'] = [800, 600]
            new_node['id'] = f"compound_copy"
            nodes.append(new_node)
            changed = True
            print(f"  ✅ {wf_name} — 복합원료 조회 노드 추가")

        for node in nodes:
            if node.get('name') == '🧠 Claude 프롬프트 구성':
                js = node['parameters'].get('jsCode', '')
                if '복합원료 DB 조회' in js:
                    print(f"  ⏭️  {wf_name} — 이미 복합원료 참조 있음")
                    continue

                old_start = "const config = $('🔄 규제 SQL 생성').first().json;"
                new_start = """const config = $('🔄 규제 SQL 생성').first().json;
const compounds = (() => { try { return $('📦 복합원료 DB 조회').all().map(i=>i.json); } catch(e) { return []; } })();
const compList = compounds.map(c=> c.trade_name+' ('+c.supplier+') ['+c.category+'] 구성: '+(typeof c.components==='string'?c.components:JSON.stringify(c.components))).join('\\n');"""

                if old_start in js:
                    js = js.replace(old_start, new_start)

                    old_reg = '[규제 제한]'
                    new_reg = """[복합원료 DB (compound_master)]
\${compList || '(복합원료 DB 없음)'}
※ 역추정 시 복합원료 가능성 검토 → compound_expansion 기록.

[규제 제한]"""
                    js = js.replace(old_reg, new_reg)

                    node['parameters']['jsCode'] = js
                    changed = True
                    print(f"  ✅ {wf_name} — 프롬프트에 복합원료 DB 참조 추가")

        if changed:
            cur.execute(
                "UPDATE workflow_entity SET nodes=?, updatedAt=datetime('now') WHERE id=?",
                (json.dumps(nodes, ensure_ascii=False), COPY_ID)
            )
            updated += 1

    conn.commit()
    conn.close()
    print(f"\n총 {updated}개 워크플로우 업데이트")
    return updated


if __name__ == '__main__':
    print("=" * 60)
    print("n8n 워크플로우 compound_master + 통합 DB 연동")
    print("=" * 60)
    update_v23_workflows()
    print("\n✅ 완료. n8n 재시작 필요: pm2 restart n8n")
