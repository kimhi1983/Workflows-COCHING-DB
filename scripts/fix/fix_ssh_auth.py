import sqlite3, json
db = sqlite3.connect("/home/kpros/.n8n/database.sqlite")

rows = db.execute("""
    SELECT id, name, nodes FROM workflow_entity
    WHERE name LIKE '%v2.3%' OR name LIKE '%카피%'
""").fetchall()

for wf_id, wf_name, nodes_json in rows:
    nodes = json.loads(nodes_json)
    changed = False
    for i, n in enumerate(nodes):
        if n.get("type") == "n8n-nodes-base.ssh":
            params = n.get("parameters", {})
            if params.get("authentication") != "privateKey":
                nodes[i]["parameters"]["authentication"] = "privateKey"
                nodes[i]["alwaysOutputData"] = True
                nodes[i]["onError"] = "continueRegularOutput"
                changed = True
                print(f"  Fixed: [{wf_name}] {n['name']}")
    if changed:
        db.execute("UPDATE workflow_entity SET nodes=? WHERE id=?", [json.dumps(nodes), wf_id])
        # Also update published version
        db.execute("""
            UPDATE workflow_history SET nodes=?
            WHERE versionId=(SELECT activeVersionId FROM workflow_entity WHERE id=?)
        """, [json.dumps(nodes), wf_id])

db.commit()
db.close()
print("Done!")
