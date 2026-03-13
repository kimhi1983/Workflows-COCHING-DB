#!/usr/bin/env python3
"""
Fix two errors in v2.3 and product copy workflows:
1. Track 1: SQL query has 'im.' alias prefix but no alias defined → remove 'im.' prefix
2. Track 2: SSH node uses sshPassword credential type → change to sshPrivateKey
"""
import sqlite3, json

db = sqlite3.connect("/home/kpros/.n8n/database.sqlite")

# ===== Fix 1: Track 1 SQL alias error =====
rows = db.execute("""
    SELECT id, name, nodes FROM workflow_entity
    WHERE name LIKE '%v2.3%'
""").fetchall()

for wf_id, wf_name, nodes_json in rows:
    nodes = json.loads(nodes_json)
    changed = False

    for i, n in enumerate(nodes):
        name = n.get("name", "")

        # Fix Code nodes that generate SQL with 'im.' prefix
        if "jsCode" in n.get("parameters", {}):
            code = n["parameters"]["jsCode"]
            if "im.inci_name" in code or "im.korean_name" in code:
                code = code.replace("im.inci_name", "inci_name")
                code = code.replace("im.korean_name", "korean_name")
                code = code.replace("im.cas_number", "cas_number")
                code = code.replace("im.description", "description")
                nodes[i]["parameters"]["jsCode"] = code
                changed = True
                print(f"  Fixed SQL alias in [{wf_name}] node: {name}")

        # Also check PostgreSQL query nodes
        if "query" in n.get("parameters", {}):
            query = n["parameters"]["query"]
            if "im." in query and "ingredient_master" in query:
                query = query.replace("im.inci_name", "inci_name")
                query = query.replace("im.korean_name", "korean_name")
                query = query.replace(" im WHERE", " WHERE")
                query = query.replace(" im\nWHERE", "\nWHERE")
                nodes[i]["parameters"]["query"] = query
                changed = True
                print(f"  Fixed SQL in [{wf_name}] node: {name}")

    if changed:
        db.execute("UPDATE workflow_entity SET nodes=? WHERE id=?", [json.dumps(nodes), wf_id])


# ===== Fix 2: Track 2 SSH credential type =====
rows2 = db.execute("""
    SELECT id, name, nodes FROM workflow_entity
    WHERE name LIKE '%카피%'
""").fetchall()

SSH_CRED = {"sshPrivateKey": {"id": "uK4wQlmywxsEwHyU", "name": "Claude Code WSL2 SSH"}}

for wf_id, wf_name, nodes_json in rows2:
    nodes = json.loads(nodes_json)
    changed = False

    for i, n in enumerate(nodes):
        if n.get("type") == "n8n-nodes-base.ssh":
            current_creds = n.get("credentials", {})
            if "sshPassword" in current_creds or current_creds != SSH_CRED:
                nodes[i]["credentials"] = SSH_CRED
                changed = True
                print(f"  Fixed SSH creds in [{wf_name}] node: {n['name']}")

    if changed:
        db.execute("UPDATE workflow_entity SET nodes=? WHERE id=?", [json.dumps(nodes), wf_id])


# ===== Update workflow_history for published versions =====
for row in db.execute("""
    SELECT wf.id, wf.activeVersionId, wf.nodes, wf.connections, wf.name
    FROM workflow_entity wf
    WHERE (wf.name LIKE '%v2.3%' OR wf.name LIKE '%카피%') AND wf.activeVersionId IS NOT NULL
""").fetchall():
    wf_id, version_id, nodes, connections, name = row
    db.execute("""
        UPDATE workflow_history
        SET nodes=?, connections=?
        WHERE versionId=?
    """, [nodes, connections, version_id])
    print(f"  Updated history for: {name}")

db.commit()
db.close()
print("\nDone!")
