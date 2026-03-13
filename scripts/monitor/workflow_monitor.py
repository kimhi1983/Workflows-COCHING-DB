#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
COCHING 워크플로우 모니터링 스크립트
=====================================
n8n 워크플로우 실행 상태 + PostgreSQL DB 성장 + 크론 백업 상태를
종합적으로 점검하고, 텍스트/HTML/JSON 형식으로 리포트를 출력한다.

실행:
    python workflow_monitor.py [--format text|html|json]

작성: 2026-03-13
"""

import argparse
import json
import os
import subprocess
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, Union


# ─────────────────────────────────────────────
# 경로 상수
# ─────────────────────────────────────────────
SCRIPT_DIR    = Path(__file__).parent
STATE_FILE    = SCRIPT_DIR / "monitor_state.json"
REPORT_DIR    = Path(r"E:\COCHING-WORKFLOW\reports")
REPORT_FILE   = REPORT_DIR / "monitor_report.html"

# ─────────────────────────────────────────────
# n8n 설정
# ─────────────────────────────────────────────
N8N_BASE_URL  = "http://localhost:5678/api/v1"

# 감시할 활성 워크플로우 (이름, ID, 예상 실행 간격(분))
WORKFLOWS = [
    {"name": "제품카피 가이드 v1.0",    "id": "a0670dfdacb34ce887a3", "interval_min": 2},
    {"name": "원료 수집 v7",            "id": "FW6GUTq0AzBXjJQ5",    "interval_min": 180},
    {"name": "제품 수집 v1",            "id": "5YRZrKRWAPG6C5JA",    "interval_min": 180},
    {"name": "원료 안전성 강화 v1",     "id": "wf_safety_enhance_v1","interval_min": 1440},
    {"name": "다국가 규제 모니터링 v1", "id": "wf_regulation_monitor_v1", "interval_min": 1440},
]

# ─────────────────────────────────────────────
# PostgreSQL 설정
# ─────────────────────────────────────────────
PG_HOST     = "127.0.0.1"
PG_USER     = "coching_user"
PG_PASS     = "coching2026!"
PG_DB       = "coching_db"
PG_TABLES   = [
    "ingredient_master",
    "product_master",
    "regulation_cache",
    "guide_cache",
    "guide_cache_copy",
    "product_ingredients",
]

# ─────────────────────────────────────────────
# 백업 경로 (WSL 기준)
# ─────────────────────────────────────────────
BACKUP_PATHS_WSL = [
    "/mnt/e/COCHING-WORKFLOW/backup/db-json",
    "/mnt/e/COCHING-WORKFLOW/backup/pgdump",
    "/mnt/e/COCHING-WORKFLOW/backup/excel",
    "/mnt/e/COCHING-WORKFLOW/backup/formulations",
]


# ══════════════════════════════════════════════
# ANSI 컬러 헬퍼 (텍스트 모드 전용)
# ══════════════════════════════════════════════
class C:
    RESET  = "\033[0m"
    BOLD   = "\033[1m"
    RED    = "\033[91m"
    GREEN  = "\033[92m"
    YELLOW = "\033[93m"
    CYAN   = "\033[96m"
    WHITE  = "\033[97m"
    GRAY   = "\033[90m"

def ok(s):      return f"{C.GREEN}{s}{C.RESET}"
def warn(s):    return f"{C.YELLOW}{s}{C.RESET}"
def crit(s):    return f"{C.RED}{s}{C.RESET}"
def info(s):    return f"{C.CYAN}{s}{C.RESET}"
def bold(s):    return f"{C.BOLD}{s}{C.RESET}"
def gray(s):    return f"{C.GRAY}{s}{C.RESET}"


# ══════════════════════════════════════════════
# 유틸리티
# ══════════════════════════════════════════════
def now_kst() -> datetime:
    """현재 KST(UTC+9) 시각 반환"""
    return datetime.now(timezone(timedelta(hours=9)))


def parse_iso(s: str) -> Optional[datetime]:
    """ISO 8601 문자열을 datetime(aware)으로 변환"""
    if not s:
        return None
    try:
        # Python 3.11+ fromisoformat 가 Z 처리 가능
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def minutes_ago(dt: Optional[datetime]) -> Optional[float]:
    """dt 가 몇 분 전인지 반환. None 이면 None."""
    if dt is None:
        return None
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (now - dt).total_seconds() / 60


def load_state() -> dict:
    """이전 실행 스냅샷 로드"""
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_state(state: dict):
    """현재 스냅샷 저장"""
    STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


# ══════════════════════════════════════════════
# n8n API 키 조회
# ══════════════════════════════════════════════
def get_n8n_api_key() -> str:
    """WSL sqlite3 로 n8n API 키 조회"""
    cmd = [
        "wsl", "-u", "kpros", "--",
        "bash", "-c",
        'sqlite3 /home/kpros/.n8n/database.sqlite "SELECT \\"apiKey\\" FROM user_api_keys LIMIT 1;"'
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=15, encoding="utf-8"
        )
        key = result.stdout.strip()
        if key:
            return key
    except Exception as e:
        pass
    return ""


# ══════════════════════════════════════════════
# n8n REST API 호출
# ══════════════════════════════════════════════
def n8n_get(path: str, api_key: str) -> Optional[Union[dict, list]]:
    """n8n REST API GET 요청"""
    url = f"{N8N_BASE_URL}{path}"
    req = urllib.request.Request(url, headers={"X-N8N-API-KEY": api_key})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return {"_error": f"HTTP {e.code}: {e.reason}"}
    except Exception as e:
        return {"_error": str(e)}


def fetch_workflow_info(wf_id: str, api_key: str) -> dict:
    """워크플로우 기본 정보 조회"""
    return n8n_get(f"/workflows/{wf_id}", api_key) or {}


def fetch_executions(wf_id: str, api_key: str, limit: int = 5) -> list:
    """워크플로우 최근 N 건 실행 내역 조회"""
    data = n8n_get(
        f"/executions?workflowId={wf_id}&limit={limit}&includeData=false",
        api_key
    )
    if isinstance(data, dict) and "data" in data:
        return data["data"]
    return []


# ══════════════════════════════════════════════
# 워크플로우 상태 분석
# ══════════════════════════════════════════════
def analyze_workflow(wf: dict, api_key: str) -> dict:
    """단일 워크플로우 분석 결과 반환"""
    wf_id       = wf["id"]
    wf_name     = wf["name"]
    interval    = wf["interval_min"]

    result = {
        "id":           wf_id,
        "name":         wf_name,
        "interval_min": interval,
        "active":       None,
        "executions":   [],
        "success_count":0,
        "error_count":  0,
        "last_run":     None,
        "last_run_ago_min": None,
        "last_error":   None,
        "consecutive_failures": 0,
        "alerts":       [],
        "status":       "UNKNOWN",  # OK / WARNING / CRITICAL / UNKNOWN
    }

    # 워크플로우 활성 여부
    info_data = fetch_workflow_info(wf_id, api_key)
    if "_error" in info_data:
        result["alerts"].append(f"워크플로우 정보 조회 실패: {info_data['_error']}")
        result["status"] = "UNKNOWN"
        return result

    result["active"] = info_data.get("active", False)

    # 실행 내역
    execs = fetch_executions(wf_id, api_key, limit=5)
    result["executions"] = execs

    for ex in execs:
        finished = ex.get("finished", False)
        status   = ex.get("status", "")          # "success" | "error" | "running" | "waiting"
        if status == "success":
            result["success_count"] += 1
        elif status == "error":
            result["error_count"] += 1

    # 마지막 실행 시각
    if execs:
        last_ex   = execs[0]
        start_at  = last_ex.get("startedAt") or last_ex.get("createdAt", "")
        result["last_run"] = start_at
        result["last_run_ago_min"] = minutes_ago(parse_iso(start_at))

        # 마지막 에러 메시지
        if last_ex.get("status") == "error":
            err_data = last_ex.get("data", {}) or {}
            result_data = err_data.get("resultData", {}) or {}
            run_data    = result_data.get("runData", {}) or {}
            # 오류 메시지 추출 (첫 번째 노드 에러)
            for node_name, node_runs in run_data.items():
                if isinstance(node_runs, list):
                    for run in node_runs:
                        err = run.get("error", {}) or {}
                        msg = err.get("message", "")
                        if msg:
                            result["last_error"] = f"[{node_name}] {msg}"
                            break
                if result["last_error"]:
                    break

    # 연속 실패 횟수 (최근 실행 기준)
    consec = 0
    for ex in execs:
        if ex.get("status") == "error":
            consec += 1
        else:
            break
    result["consecutive_failures"] = consec

    # ── 알림 판정 ──────────────────────────────
    if consec >= 3:
        result["alerts"].append(f"연속 {consec}회 실패 — CRITICAL")
        result["status"] = "CRITICAL"
    elif result["last_run_ago_min"] is not None and result["last_run_ago_min"] > interval * 3:
        result["alerts"].append(
            f"마지막 실행 {result['last_run_ago_min']:.0f}분 전 (예상 주기 {interval}분 × 3 초과) — WARNING"
        )
        result["status"] = "WARNING"
    elif result["error_count"] > 0:
        result["status"] = "WARNING"
    else:
        result["status"] = "OK"

    return result


# ══════════════════════════════════════════════
# PostgreSQL DB 행 수 조회
# ══════════════════════════════════════════════
def run_psql(sql: str) -> str:
    """WSL 경유 psql 실행 후 stdout 반환"""
    cmd = [
        "wsl", "-u", "kpros", "--",
        "bash", "-c",
        f"PGPASSWORD={PG_PASS} psql -h {PG_HOST} -U {PG_USER} -d {PG_DB} -t -A -c '{sql}'"
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30, encoding="utf-8"
        )
        return result.stdout.strip()
    except Exception as e:
        return f"ERROR:{e}"


def fetch_table_counts() -> dict:
    """모든 감시 테이블의 현재 행 수 반환"""
    counts = {}
    for table in PG_TABLES:
        raw = run_psql(f"SELECT COUNT(*) FROM {table};")
        try:
            counts[table] = int(raw)
        except Exception:
            counts[table] = None  # 조회 실패
    return counts


def analyze_db(prev_state: dict) -> dict:
    """DB 성장 분석"""
    current_counts = fetch_table_counts()
    prev_counts     = prev_state.get("db_counts", {})

    growth = {}
    alerts = []

    for table, cur in current_counts.items():
        prev = prev_counts.get(table)
        if cur is None:
            delta = None
        elif prev is None:
            delta = None  # 이전 스냅샷 없음
        else:
            delta = cur - prev

        growth[table] = {
            "current": cur,
            "previous": prev,
            "delta": delta,
        }

        # 행 수 감소 감지
        if delta is not None and delta < 0:
            alerts.append(f"{table} 행 수 감소: {prev} → {cur} ({delta:+d}) — WARNING")

    return {
        "counts": current_counts,
        "growth": growth,
        "alerts": alerts,
        "timestamp": now_kst().isoformat(),
    }


# ══════════════════════════════════════════════
# 크론 백업 상태 점검
# ══════════════════════════════════════════════
def check_backup_freshness(path_wsl: str, max_age_hours: int = 25) -> dict:
    """WSL 경로의 가장 최근 파일 수정 시각 확인"""
    cmd = [
        "wsl", "-u", "kpros", "--",
        "bash", "-c",
        # find로 최근 파일 mtime(epoch) 조회
        f"find {path_wsl} -maxdepth 1 -type f -printf '%T@\\n' 2>/dev/null | sort -n | tail -1"
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=15, encoding="utf-8"
        )
        epoch_str = result.stdout.strip()
        if epoch_str:
            epoch = float(epoch_str)
            last_dt = datetime.fromtimestamp(epoch, tz=timezone.utc)
            ago_hours = (datetime.now(timezone.utc) - last_dt).total_seconds() / 3600
            return {
                "path": path_wsl,
                "last_file_time": last_dt.isoformat(),
                "hours_ago": round(ago_hours, 1),
                "ok": ago_hours <= max_age_hours,
            }
    except Exception as e:
        pass
    return {"path": path_wsl, "last_file_time": None, "hours_ago": None, "ok": False}


def analyze_cron() -> dict:
    """크론 백업 상태 종합 분석"""
    results = []
    alerts  = []

    for path in BACKUP_PATHS_WSL:
        info = check_backup_freshness(path)
        results.append(info)
        if not info["ok"]:
            age_str = f"{info['hours_ago']}시간" if info["hours_ago"] is not None else "알 수 없음"
            alerts.append(f"백업 오래됨: {path} (마지막: {age_str} 전) — WARNING")

    # crontab 확인
    cmd = ["wsl", "-u", "kpros", "--", "bash", "-c", "crontab -l 2>/dev/null"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=10, encoding="utf-8")
        crontab = r.stdout.strip()
    except Exception:
        crontab = ""

    return {
        "backup_paths": results,
        "alerts": alerts,
        "crontab_preview": crontab[:800] if crontab else "(없음)",
    }


# ══════════════════════════════════════════════
# 리포트 포맷터 — TEXT
# ══════════════════════════════════════════════
STATUS_ICON = {
    "OK":       "✓",
    "WARNING":  "⚠",
    "CRITICAL": "✗",
    "UNKNOWN":  "?",
}
STATUS_COLOR = {
    "OK":       ok,
    "WARNING":  warn,
    "CRITICAL": crit,
    "UNKNOWN":  gray,
}

def format_text(report: dict) -> str:
    lines = []
    ts = report["generated_at"]

    lines.append(bold("=" * 60))
    lines.append(bold("  COCHING 워크플로우 모니터링 리포트"))
    lines.append(bold(f"  생성: {ts}"))
    lines.append(bold("=" * 60))

    # ── n8n 워크플로우 ──
    lines.append("")
    lines.append(info("[ n8n 워크플로우 상태 ]"))
    lines.append("-" * 60)

    for wf in report["workflows"]:
        status  = wf["status"]
        icon    = STATUS_ICON.get(status, "?")
        color_fn = STATUS_COLOR.get(status, gray)

        lines.append(
            f"  {color_fn(icon)} {bold(wf['name'])}  "
            f"[{color_fn(status)}]"
            + (f"  활성: {'예' if wf['active'] else gray('아니오')}" if wf['active'] is not None else "")
        )

        # 마지막 실행
        if wf["last_run"]:
            ago = wf["last_run_ago_min"]
            ago_str = f"{ago:.0f}분 전" if ago is not None else "?"
            lines.append(f"      마지막 실행: {wf['last_run'][:19]}  ({ago_str})")
        else:
            lines.append(f"      마지막 실행: {gray('기록 없음')}")

        # 성공/실패 카운트 (최근 5건)
        s = wf["success_count"]
        e = wf["error_count"]
        lines.append(
            f"      최근 5건: 성공 {ok(s)}  실패 {(crit if e > 0 else gray)(e)}"
            f"  (연속 실패: {(crit if wf['consecutive_failures'] >= 3 else gray)(wf['consecutive_failures'])})"
        )

        # 마지막 에러
        if wf["last_error"]:
            lines.append(f"      {crit('마지막 오류')}: {wf['last_error'][:100]}")

        # 알림
        for alert in wf["alerts"]:
            lines.append(f"      {warn('⚑')} {alert}")

    # ── DB ──
    lines.append("")
    lines.append(info("[ PostgreSQL DB 현황 ]"))
    lines.append("-" * 60)

    db = report["db"]
    for table, g in db["growth"].items():
        cur   = g["current"]
        delta = g["delta"]

        if cur is None:
            row_str = crit("조회 실패")
        else:
            row_str = f"{cur:,}건"

        if delta is None:
            delta_str = gray("(이전 스냅샷 없음)")
        elif delta > 0:
            delta_str = ok(f"+{delta:,}")
        elif delta < 0:
            delta_str = crit(f"{delta:,}")
        else:
            delta_str = gray("±0")

        lines.append(f"  {table:<25} {row_str:<12} {delta_str}")

    for alert in db["alerts"]:
        lines.append(f"  {warn('⚑')} {alert}")

    # ── 크론/백업 ──
    lines.append("")
    lines.append(info("[ 크론 백업 상태 ]"))
    lines.append("-" * 60)

    cron = report["cron"]
    for bp in cron["backup_paths"]:
        path_short = bp["path"].split("/")[-1] or bp["path"]
        if bp["ok"]:
            status_str = ok(f"최근 {bp['hours_ago']}시간 전")
        else:
            hours = f"{bp['hours_ago']}시간" if bp["hours_ago"] is not None else "파일 없음"
            status_str = warn(f"{hours} — 오래됨")
        lines.append(f"  {bp['path']:<40} {status_str}")

    for alert in cron["alerts"]:
        lines.append(f"  {warn('⚑')} {alert}")

    lines.append("")
    lines.append(gray("  crontab 미리보기 (상위 10줄):"))
    for cline in cron["crontab_preview"].splitlines()[:10]:
        lines.append(f"    {gray(cline)}")

    # ── 전체 요약 ──
    lines.append("")
    lines.append(bold("=" * 60))
    all_alerts = report["all_alerts"]
    if not all_alerts:
        lines.append(ok("  전체 상태: 정상 — 알림 없음"))
    else:
        lines.append(warn(f"  전체 알림: {len(all_alerts)}건"))
        for a in all_alerts:
            lines.append(f"    {warn('⚑')} {a}")
    lines.append(bold("=" * 60))

    return "\n".join(lines)


# ══════════════════════════════════════════════
# 리포트 포맷터 — JSON
# ══════════════════════════════════════════════
def format_json(report: dict) -> str:
    return json.dumps(report, ensure_ascii=False, indent=2, default=str)


# ══════════════════════════════════════════════
# 리포트 포맷터 — HTML
# ══════════════════════════════════════════════
def _status_badge(status: str) -> str:
    color = {
        "OK":       "#28a745",
        "WARNING":  "#ffc107",
        "CRITICAL": "#dc3545",
        "UNKNOWN":  "#6c757d",
    }.get(status, "#6c757d")
    return (
        f'<span style="background:{color};color:#fff;padding:2px 8px;'
        f'border-radius:4px;font-size:.8em;font-weight:700;">{status}</span>'
    )


def format_html(report: dict) -> str:
    ts = report["generated_at"]
    all_alerts = report["all_alerts"]
    overall_color = "#28a745" if not all_alerts else (
        "#dc3545" if any("CRITICAL" in a for a in all_alerts) else "#ffc107"
    )

    # ── 워크플로우 행 ──
    wf_rows = ""
    for wf in report["workflows"]:
        last_run = wf["last_run"][:19] if wf["last_run"] else "-"
        ago = f"{wf['last_run_ago_min']:.0f}분 전" if wf["last_run_ago_min"] is not None else "-"
        err_cell = f'<span style="color:#dc3545;">{wf["last_error"][:80]}</span>' if wf["last_error"] else "-"
        alerts_cell = "<br>".join(
            f'<span style="color:#b8860b;">⚑ {a}</span>' for a in wf["alerts"]
        ) or "-"
        wf_rows += f"""
        <tr>
          <td>{wf['name']}</td>
          <td>{'활성' if wf['active'] else '<span style="color:#999">비활성</span>'}</td>
          <td>{_status_badge(wf['status'])}</td>
          <td>{last_run}<br><small style="color:#888">{ago}</small></td>
          <td style="text-align:center">
            <span style="color:#28a745">✓{wf['success_count']}</span> /
            <span style="color:#dc3545">✗{wf['error_count']}</span>
          </td>
          <td style="color:#dc3545;font-size:.85em">{wf['consecutive_failures']}</td>
          <td style="font-size:.82em">{err_cell}</td>
          <td style="font-size:.82em">{alerts_cell}</td>
        </tr>"""

    # ── DB 행 ──
    db = report["db"]
    db_rows = ""
    for table, g in db["growth"].items():
        cur   = f"{g['current']:,}" if g["current"] is not None else "조회 실패"
        delta = g["delta"]
        if delta is None:
            delta_str = '<span style="color:#888">-</span>'
        elif delta > 0:
            delta_str = f'<span style="color:#28a745">+{delta:,}</span>'
        elif delta < 0:
            delta_str = f'<span style="color:#dc3545">{delta:,}</span>'
        else:
            delta_str = '<span style="color:#888">±0</span>'
        db_rows += f"<tr><td>{table}</td><td>{cur}</td><td>{delta_str}</td></tr>"

    # ── 백업 행 ──
    bk_rows = ""
    for bp in report["cron"]["backup_paths"]:
        ok_str = (
            f'<span style="color:#28a745">최근 {bp["hours_ago"]}시간 전</span>'
            if bp["ok"] else
            f'<span style="color:#ffc107">{"%.1f시간 전" % bp["hours_ago"] if bp["hours_ago"] else "파일 없음"}</span>'
        )
        bk_rows += f"<tr><td>{bp['path']}</td><td>{ok_str}</td></tr>"

    # ── 알림 목록 ──
    alert_html = ""
    if all_alerts:
        items = "".join(f"<li>{a}</li>" for a in all_alerts)
        alert_html = f"""
        <div style="background:#fff3cd;border-left:4px solid #ffc107;padding:12px 16px;margin:16px 0;border-radius:4px;">
          <strong>⚑ 알림 {len(all_alerts)}건</strong>
          <ul style="margin:8px 0 0 0">{items}</ul>
        </div>"""
    else:
        alert_html = '<div style="background:#d4edda;border-left:4px solid #28a745;padding:12px 16px;margin:16px 0;border-radius:4px;">모든 시스템 정상</div>'

    crontab_escaped = report["cron"]["crontab_preview"].replace("<", "&lt;").replace(">", "&gt;")

    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>COCHING 워크플로우 모니터</title>
<style>
  body {{ font-family: 'Segoe UI', sans-serif; background:#f5f6fa; color:#222; margin:0; padding:20px; }}
  h1 {{ color:{overall_color}; margin-bottom:4px; }}
  .ts {{ color:#888; font-size:.9em; margin-bottom:20px; }}
  h2 {{ border-bottom:2px solid #dee2e6; padding-bottom:6px; margin-top:28px; }}
  table {{ border-collapse:collapse; width:100%; background:#fff; border-radius:6px; overflow:hidden; box-shadow:0 1px 4px rgba(0,0,0,.08); margin-bottom:20px; }}
  th {{ background:#495057; color:#fff; padding:10px 12px; text-align:left; font-size:.85em; }}
  td {{ padding:9px 12px; border-bottom:1px solid #f0f0f0; font-size:.88em; vertical-align:top; }}
  tr:last-child td {{ border-bottom:none; }}
  tr:hover td {{ background:#f8f9ff; }}
  pre {{ background:#1e1e2e; color:#cdd6f4; padding:14px; border-radius:6px; font-size:.82em; overflow-x:auto; }}
</style>
</head>
<body>
<h1>COCHING 워크플로우 모니터링</h1>
<div class="ts">생성: {ts}</div>
{alert_html}

<h2>n8n 워크플로우 상태</h2>
<table>
  <tr>
    <th>워크플로우</th><th>활성</th><th>상태</th>
    <th>마지막 실행</th><th>성공/실패(5건)</th>
    <th>연속실패</th><th>마지막 오류</th><th>알림</th>
  </tr>
  {wf_rows}
</table>

<h2>PostgreSQL DB 현황</h2>
<table>
  <tr><th>테이블</th><th>현재 행 수</th><th>증감</th></tr>
  {db_rows}
</table>

<h2>크론 백업 상태</h2>
<table>
  <tr><th>백업 경로</th><th>마지막 파일</th></tr>
  {bk_rows}
</table>

<h2>crontab 미리보기</h2>
<pre>{crontab_escaped}</pre>

</body>
</html>"""
    return html


# ══════════════════════════════════════════════
# 메인
# ══════════════════════════════════════════════
def main():
    # Windows 콘솔 UTF-8 강제
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="COCHING 워크플로우 모니터")
    parser.add_argument(
        "--format", choices=["text", "html", "json"],
        default="text", help="출력 형식 (기본: text)"
    )
    args = parser.parse_args()

    prev_state = load_state()

    # ── 1. n8n API 키 조회 ──
    api_key = get_n8n_api_key()
    if not api_key:
        print(crit("[오류] n8n API 키를 가져올 수 없습니다. WSL/sqlite3 연결을 확인하세요."), file=sys.stderr)

    # ── 2. 워크플로우 분석 ──
    wf_results = []
    for wf in WORKFLOWS:
        r = analyze_workflow(wf, api_key)
        wf_results.append(r)

    # ── 3. DB 분석 ──
    db_result = analyze_db(prev_state)

    # ── 4. 크론/백업 분석 ──
    cron_result = analyze_cron()

    # ── 5. 전체 알림 수집 ──
    all_alerts = []
    for wf in wf_results:
        all_alerts.extend(wf["alerts"])
    all_alerts.extend(db_result["alerts"])
    all_alerts.extend(cron_result["alerts"])

    # ── 6. 리포트 조립 ──
    report = {
        "generated_at": now_kst().strftime("%Y-%m-%d %H:%M:%S KST"),
        "workflows":    wf_results,
        "db":           db_result,
        "cron":         cron_result,
        "all_alerts":   all_alerts,
    }

    # ── 7. 상태 저장 (다음 실행 비교용) ──
    new_state = {
        "timestamp":  now_kst().isoformat(),
        "db_counts":  db_result["counts"],
    }
    save_state(new_state)

    # ── 8. 출력 ──
    if args.format == "text":
        print(format_text(report))

    elif args.format == "json":
        print(format_json(report))

    elif args.format == "html":
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        html_content = format_html(report)
        REPORT_FILE.write_text(html_content, encoding="utf-8")
        print(f"HTML 리포트 저장 완료: {REPORT_FILE}")
        # 텍스트 요약도 stdout 출력
        print(format_text(report))


if __name__ == "__main__":
    main()
