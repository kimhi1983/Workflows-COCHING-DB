#!/usr/bin/env python3
"""
COCHING DB 수집 데이터 자동 이중 백업 스크립트
- PostgreSQL → JSON + CSV 백업
- WSL2 /home/kpros/backup/ + E:\COCHING\backup\db\ 이중 저장
- 30분마다 cron으로 실행
"""
import json, os, csv
from datetime import datetime

DB_PASS = os.environ.get("COCHING_DB_PASS", "")
DB_USER = os.environ.get("COCHING_DB_USER", "coching_user")
DB_NAME = os.environ.get("COCHING_DB_NAME", "coching_db")
DB_HOST = os.environ.get("COCHING_DB_HOST", "127.0.0.1")

# 백업 경로 (이중)
BACKUP_WSL = "/home/kpros/backup/db"
BACKUP_WIN = "/mnt/e/COCHING/backup/db"

TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M")

def run_query(query):
    """psql로 쿼리 실행 후 결과 반환"""
    import subprocess
    env = os.environ.copy()
    env["PGPASSWORD"] = DB_PASS
    cmd = [
        "psql", "-h", DB_HOST, "-U", DB_USER, "-d", DB_NAME,
        "-t", "-A", "-F", "\t", "-c", query
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    return result.stdout.strip()


def export_table_csv(table_name, columns, backup_dir):
    """테이블을 CSV로 내보내기"""
    import subprocess
    env = os.environ.copy()
    env["PGPASSWORD"] = DB_PASS
    filepath = os.path.join(backup_dir, f"{table_name}_{TIMESTAMP}.csv")
    copy_cmd = f"\\copy {table_name} ({','.join(columns)}) TO '{filepath}' WITH CSV HEADER ENCODING 'UTF8'"
    cmd = ["psql", "-h", DB_HOST, "-U", DB_USER, "-d", DB_NAME, "-c", copy_cmd]
    subprocess.run(cmd, env=env, capture_output=True)
    return filepath


def export_table_json(table_name, backup_dir):
    """테이블을 JSON으로 내보내기"""
    import subprocess
    env = os.environ.copy()
    env["PGPASSWORD"] = DB_PASS
    query = f"SELECT json_agg(t) FROM {table_name} t"
    cmd = ["psql", "-h", DB_HOST, "-U", DB_USER, "-d", DB_NAME, "-t", "-A", "-c", query]
    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    data = result.stdout.strip()
    if data and data != "":
        filepath = os.path.join(backup_dir, f"{table_name}_{TIMESTAMP}.json")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(data)
        return filepath
    return None


def cleanup_old_backups(backup_dir, keep_days=7):
    """오래된 백업 정리 (7일 이상)"""
    import time
    now = time.time()
    cutoff = now - (keep_days * 86400)
    if not os.path.exists(backup_dir):
        return
    for f in os.listdir(backup_dir):
        fp = os.path.join(backup_dir, f)
        if os.path.isfile(fp) and os.path.getmtime(fp) < cutoff:
            os.remove(fp)
            print(f"  삭제: {f}")


def main():
    print(f"=== COCHING DB 이중 백업 시작 [{TIMESTAMP}] ===")

    # 백업 디렉토리 생성
    for d in [BACKUP_WSL, BACKUP_WIN]:
        os.makedirs(d, exist_ok=True)

    tables = [
        "ingredient_master",
        "product_master",
        "regulation_cache",
        "coching_knowledge_base",
        "ingredient_properties",
        "ingredient_functions",
        "workflow_log",
        "collection_progress",
        "cosmetics_company",
    ]

    for table in tables:
        for backup_dir in [BACKUP_WSL, BACKUP_WIN]:
            path = export_table_json(table, backup_dir)
            if path:
                # 파일 크기 확인
                size = os.path.getsize(path)
                print(f"  {table} → {backup_dir} ({size:,} bytes)")

    # 통계 요약
    stats = run_query("""
        SELECT 'ingredient_master: ' || count(*) FROM ingredient_master
        UNION ALL SELECT 'product_master: ' || count(*) FROM product_master
        UNION ALL SELECT 'regulation_cache: ' || count(*) FROM regulation_cache
        UNION ALL SELECT 'knowledge_base: ' || count(*) FROM coching_knowledge_base
        UNION ALL SELECT 'collection_progress: ' || count(*) FROM collection_progress
        UNION ALL SELECT 'cosmetics_company: ' || count(*) FROM cosmetics_company
    """)

    summary = {
        "timestamp": TIMESTAMP,
        "stats": stats,
        "backup_locations": [BACKUP_WSL, BACKUP_WIN],
    }

    for d in [BACKUP_WSL, BACKUP_WIN]:
        with open(os.path.join(d, f"backup_summary_{TIMESTAMP}.json"), "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)

    # 오래된 백업 정리
    for d in [BACKUP_WSL, BACKUP_WIN]:
        cleanup_old_backups(d, keep_days=7)

    print(f"=== 백업 완료 ===\n{stats}")


if __name__ == "__main__":
    main()
