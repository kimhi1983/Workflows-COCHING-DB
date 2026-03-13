#!/usr/bin/env python3
"""
원료수집 v7 — 식약처→원료DB 노드 파라미터 바인딩 수정
문제: description 필드에 작은따옴표(')가 포함되면 SQL 구문 오류
해결: 직접 문자열 삽입 → $1,$2,$3,$4 파라미터 바인딩
적용일: 2026-03-12
"""
import sqlite3, json, uuid
from datetime import datetime

DB = "/home/kpros/.n8n/database.sqlite"
WF_ID = "FW6GUTq0AzBXjJQ5"

conn = sqlite3.connect(DB)
cur = conn.cursor()

cur.execute("SELECT nodes, connections FROM workflow_entity WHERE id=?", (WF_ID,))
row = cur.fetchone()
nodes = json.loads(row[0])
connections = row[1]

fixed = False
for node in nodes:
    if node.get("name") == "\U0001f4be \uc2dd\uc57d\ucc98\u2192\uc6d0\ub8ccDB":
        old_query = node["parameters"]["query"]
        print(f"OLD query:\n{old_query[:300]}\n")

        new_query = """INSERT INTO ingredient_master
  (inci_name, korean_name, cas_number, description, source)
SELECT $1, $2, $3, $4, 'mfds_korea'
WHERE length($1) > 0
  AND NOT EXISTS (
    SELECT 1 FROM ingredient_master WHERE inci_name = $1
  )"""

        node["parameters"]["query"] = new_query
        node["parameters"]["options"] = {
            "queryReplacement": "={{ [$json.inci_name, $json.korean_name, $json.cas_number || '', $json.description || ''] }}"
        }

        print(f"NEW query:\n{new_query}\n")
        fixed = True
        break

if fixed:
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S.000")
    vid = str(uuid.uuid4())
    nodes_json = json.dumps(nodes, ensure_ascii=False)

    cur.execute("""UPDATE workflow_entity
        SET nodes=?, activeVersionId=?, updatedAt=?, versionId=?
        WHERE id=?""",
        (nodes_json, vid, now, vid, WF_ID))

    cur.execute("""INSERT INTO workflow_history
        (versionId, workflowId, nodes, connections, authors, createdAt, updatedAt)
        VALUES (?, ?, ?, ?, '[]', ?, ?)""",
        (vid, WF_ID, nodes_json, connections, now, now))

    conn.commit()
    print("FIXED! Parameter binding applied to 식약처→원료DB node")
else:
    print("Node not found!")

conn.close()
