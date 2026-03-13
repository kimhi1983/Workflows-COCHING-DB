#!/usr/bin/env python3
"""최근 제품카피 에러 상세 확인"""
import sqlite3, json

DB = '/home/kpros/.n8n/database.sqlite'
conn = sqlite3.connect(DB)
cur = conn.cursor()

# 최근 에러 실행 ID
cur.execute("""
    SELECT ee.id, ee.status, ee.startedAt
    FROM execution_entity ee
    WHERE ee.workflowId = 'a0670dfdacb34ce887a3'
      AND ee.status = 'error'
    ORDER BY ee.startedAt DESC LIMIT 1
""")
row = cur.fetchone()
if not row:
    print("No error found")
    exit()

eid, status, started = row
print(f"Execution ID: {eid}, Status: {status}, Started: {started}")

# 에러 데이터 추출
cur.execute("SELECT data FROM execution_data WHERE executionId = ?", (eid,))
data_row = cur.fetchone()
if not data_row:
    print("No execution data")
    exit()

arr = json.loads(data_row[0])
print(f"\nTotal flatted items: {len(arr)}")
print("\n=== Error-related items ===")
for i, item in enumerate(arr):
    if isinstance(item, str) and len(item) > 15 and len(item) < 3000:
        low = item.lower()
        if 'error' in low or 'syntax' in low or 'fail' in low or 'insert into' in low:
            print(f"[{i}]: {item[:500]}")

conn.close()
