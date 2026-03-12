#!/usr/bin/env python3
"""
신규 워크플로우 스케줄 변경: 1일 1회로 통일
- 원료 안전성 강화 v1: 6시간 → 24시간
- 다국가 규제 모니터링 v1: 7일 → 24시간
적용일: 2026-03-12
"""
import sqlite3, json, uuid
from datetime import datetime

DB = "/home/kpros/.n8n/database.sqlite"
conn = sqlite3.connect(DB)
cur = conn.cursor()

changes = {
    "wf_safety_enhance_v1": {
        "new_rule": {"interval": [{"field": "hours", "hoursInterval": 24}]}
    },
    "wf_regulation_monitor_v1": {
        "new_rule": {"interval": [{"field": "hours", "hoursInterval": 24}]}
    }
}

NEW_TRIGGER_NAME = "\u23f0 1\uc77c 1\ud68c \uc790\ub3d9\uc2e4\ud589"

for wf_id, cfg in changes.items():
    cur.execute("SELECT name, nodes, connections FROM workflow_entity WHERE id=?", (wf_id,))
    row = cur.fetchone()
    if not row:
        print(f"[SKIP] {wf_id} not found")
        continue

    wf_name, nodes_str, conns_str = row
    nodes = json.loads(nodes_str)
    conns = json.loads(conns_str)

    for node in nodes:
        if node.get("type") == "n8n-nodes-base.scheduleTrigger" and not node.get("disabled"):
            old_name = node["name"]
            print(f"[{wf_name}]")
            print(f"  OLD: {old_name} -> {json.dumps(node['parameters'].get('rule', {}), ensure_ascii=False)}")
            node["parameters"]["rule"] = cfg["new_rule"]
            node["name"] = NEW_TRIGGER_NAME
            print(f"  NEW: {node['name']} -> {json.dumps(node['parameters']['rule'], ensure_ascii=False)}")

            # Update connections
            if old_name != NEW_TRIGGER_NAME and old_name in conns:
                conns[NEW_TRIGGER_NAME] = conns.pop(old_name)

            now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S.000")
            vid = str(uuid.uuid4())
            nodes_json = json.dumps(nodes, ensure_ascii=False)
            conns_json = json.dumps(conns, ensure_ascii=False)

            cur.execute("""UPDATE workflow_entity
                SET nodes=?, connections=?, activeVersionId=?, updatedAt=?, versionId=?
                WHERE id=?""",
                (nodes_json, conns_json, vid, now, vid, wf_id))

            cur.execute("""INSERT INTO workflow_history
                (versionId, workflowId, nodes, connections, authors, createdAt, updatedAt)
                VALUES (?, ?, ?, ?, '[]', ?, ?)""",
                (vid, wf_id, nodes_json, conns_json, now, now))
            break

conn.commit()
conn.close()
print("\nDone! Both schedules changed to daily (24h)")
