#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
COCHING 워크플로우 모니터링 — Windows GUI
==========================================
tkinter 기반 데스크톱 모니터. 자동/수동 새로고침 + 시스템 트레이 알림.
더블클릭으로 실행하거나 run_monitor.bat gui 로 실행.

작성: 2026-03-13
"""

import json
import os
import subprocess
import sys
import threading
import time
import urllib.request
import urllib.error
import webbrowser
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, Union

try:
    import tkinter as tk
    from tkinter import ttk, messagebox, scrolledtext
except ImportError:
    print("tkinter가 설치되어 있지 않습니다.")
    sys.exit(1)


# ─────────────────────────────────────────────
# 상수
# ─────────────────────────────────────────────
SCRIPT_DIR   = Path(__file__).parent
STATE_FILE   = SCRIPT_DIR / "monitor_state.json"
REPORT_DIR   = Path(r"E:\COCHING-WORKFLOW\reports")
N8N_BASE_URL = "http://localhost:5678/api/v1"

WORKFLOWS = [
    {"name": "제품카피 가이드 v1.0",    "id": "a0670dfdacb34ce887a3", "interval_min": 2},
    {"name": "원료 수집 v7",            "id": "FW6GUTq0AzBXjJQ5",    "interval_min": 180},
    {"name": "제품 수집 v1",            "id": "5YRZrKRWAPG6C5JA",    "interval_min": 180},
    {"name": "원료 안전성 강화 v1",     "id": "wf_safety_enhance_v1", "interval_min": 1440},
    {"name": "다국가 규제 모니터링 v1", "id": "wf_regulation_monitor_v1", "interval_min": 1440},
]

PG_HOST   = "127.0.0.1"
PG_USER   = "coching_user"
PG_PASS   = "coching2026!"
PG_DB     = "coching_db"
PG_TABLES = [
    "ingredient_master", "product_master", "regulation_cache",
    "guide_cache", "guide_cache_copy", "product_ingredients",
]

BACKUP_PATHS_WSL = [
    "/mnt/e/COCHING-WORKFLOW/backup/db-json",
    "/mnt/e/COCHING-WORKFLOW/backup/pgdump",
    "/mnt/e/COCHING-WORKFLOW/backup/excel",
    "/mnt/e/COCHING-WORKFLOW/backup/formulations",
]

# 색상 테마 (다크)
BG         = "#1e1e2e"
BG_CARD    = "#2a2a3c"
BG_HEADER  = "#313244"
FG         = "#cdd6f4"
FG_DIM     = "#6c7086"
GREEN      = "#a6e3a1"
YELLOW     = "#f9e2af"
RED        = "#f38ba8"
BLUE       = "#89b4fa"
TEAL       = "#94e2d5"

AUTO_REFRESH_MS = 60_000  # 1분마다 자동 새로고침


# ─────────────────────────────────────────────
# 유틸리티
# ─────────────────────────────────────────────
def now_kst() -> datetime:
    return datetime.now(timezone(timedelta(hours=9)))


def parse_iso(s: str) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def minutes_ago(dt: Optional[datetime]) -> Optional[float]:
    if dt is None:
        return None
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (now - dt).total_seconds() / 60


def format_ago(minutes: Optional[float]) -> str:
    if minutes is None:
        return "-"
    if minutes < 1:
        return "방금"
    if minutes < 60:
        return f"{minutes:.0f}분 전"
    if minutes < 1440:
        return f"{minutes/60:.1f}시간 전"
    return f"{minutes/1440:.1f}일 전"


# ─────────────────────────────────────────────
# 데이터 수집 (모두 백그라운드 스레드에서 실행)
# ─────────────────────────────────────────────
def get_n8n_api_key() -> str:
    try:
        r = subprocess.run(
            ["wsl", "-u", "kpros", "--", "bash", "-c",
             '/usr/bin/sqlite3 /home/kpros/.n8n/database.sqlite "SELECT \\"apiKey\\" FROM user_api_keys LIMIT 1;"'],
            capture_output=True, text=True, timeout=15, encoding="utf-8"
        )
        return r.stdout.strip()
    except Exception:
        return ""


def n8n_get(path: str, api_key: str) -> Optional[Union[dict, list]]:
    url = f"{N8N_BASE_URL}{path}"
    req = urllib.request.Request(url, headers={"X-N8N-API-KEY": api_key})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return {"_error": f"HTTP {e.code}: {e.reason}"}
    except Exception as e:
        return {"_error": str(e)}


def fetch_all_workflows(api_key: str) -> list:
    results = []
    for wf in WORKFLOWS:
        r = {
            "id": wf["id"], "name": wf["name"],
            "interval_min": wf["interval_min"],
            "active": None, "status": "UNKNOWN",
            "success": 0, "error": 0,
            "last_run": None, "last_run_ago": None,
            "consecutive_failures": 0,
            "last_error_msg": None, "alerts": [],
        }

        info = n8n_get(f"/workflows/{wf['id']}", api_key)
        if isinstance(info, dict) and "_error" not in info:
            r["active"] = info.get("active", False)

        execs_data = n8n_get(
            f"/executions?workflowId={wf['id']}&limit=5&includeData=false",
            api_key
        )
        execs = execs_data.get("data", []) if isinstance(execs_data, dict) else []

        for ex in execs:
            if ex.get("status") == "success":
                r["success"] += 1
            elif ex.get("status") == "error":
                r["error"] += 1

        if execs:
            start_at = execs[0].get("startedAt") or execs[0].get("createdAt", "")
            r["last_run"] = start_at[:19] if start_at else None
            r["last_run_ago"] = minutes_ago(parse_iso(start_at))

        consec = 0
        for ex in execs:
            if ex.get("status") == "error":
                consec += 1
            else:
                break
        r["consecutive_failures"] = consec

        # 에러 메시지 (마지막 에러 실행에서)
        for ex in execs:
            if ex.get("status") == "error":
                # includeData=false라 상세 에러 없을 수 있음
                r["last_error_msg"] = "에러 발생 (상세 내용은 n8n UI 확인)"
                break

        # 상태 판정
        if consec >= 3:
            r["status"] = "CRITICAL"
            r["alerts"].append(f"연속 {consec}회 실패")
        elif r["last_run_ago"] and r["last_run_ago"] > wf["interval_min"] * 3:
            r["status"] = "WARNING"
            r["alerts"].append("예상 주기 초과")
        elif r["error"] > 0:
            r["status"] = "WARNING"
        else:
            r["status"] = "OK"

        results.append(r)
    return results


def run_psql(sql: str) -> str:
    try:
        r = subprocess.run(
            ["wsl", "-u", "kpros", "--", "bash", "-c",
             f"PGPASSWORD={PG_PASS} psql -h {PG_HOST} -U {PG_USER} -d {PG_DB} -t -A -c '{sql}'"],
            capture_output=True, text=True, timeout=30, encoding="utf-8"
        )
        return r.stdout.strip()
    except Exception as e:
        return ""


def fetch_db_counts() -> dict:
    counts = {}
    for t in PG_TABLES:
        raw = run_psql(f"SELECT COUNT(*) FROM {t};")
        try:
            counts[t] = int(raw)
        except Exception:
            counts[t] = None
    return counts


def check_backups() -> list:
    results = []
    for path in BACKUP_PATHS_WSL:
        try:
            r = subprocess.run(
                ["wsl", "-u", "kpros", "--", "bash", "-c",
                 f"find {path} -maxdepth 1 -type f -printf '%T@\\n' 2>/dev/null | sort -n | tail -1"],
                capture_output=True, text=True, timeout=15, encoding="utf-8"
            )
            epoch_str = r.stdout.strip()
            if epoch_str:
                epoch = float(epoch_str)
                last_dt = datetime.fromtimestamp(epoch, tz=timezone.utc)
                ago_h = (datetime.now(timezone.utc) - last_dt).total_seconds() / 3600
                results.append({
                    "path": path.split("/")[-1],
                    "ago_hours": round(ago_h, 1),
                    "ok": ago_h <= 25,
                })
            else:
                results.append({"path": path.split("/")[-1], "ago_hours": None, "ok": False})
        except Exception:
            results.append({"path": path.split("/")[-1], "ago_hours": None, "ok": False})
    return results


# ─────────────────────────────────────────────
# 이전 상태 저장/로드
# ─────────────────────────────────────────────
def load_prev_counts() -> dict:
    if STATE_FILE.exists():
        try:
            data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            return data.get("db_counts", {})
        except Exception:
            pass
    return {}


def save_state(counts: dict):
    STATE_FILE.write_text(
        json.dumps({"timestamp": now_kst().isoformat(), "db_counts": counts},
                    ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


# ══════════════════════════════════════════════
# GUI 앱
# ══════════════════════════════════════════════
class MonitorApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("COCHING 워크플로우 모니터")
        self.root.geometry("980x720")
        self.root.configure(bg=BG)
        self.root.minsize(800, 600)

        # 아이콘 설정 (없으면 무시)
        try:
            self.root.iconbitmap(default="")
        except Exception:
            pass

        self.api_key = ""
        self.auto_refresh_id = None
        self.is_loading = False

        self._build_ui()
        self._start_refresh()

    # ── UI 구성 ──────────────────────────────
    def _build_ui(self):
        # 상단 헤더
        header = tk.Frame(self.root, bg=BG_HEADER, pady=8, padx=16)
        header.pack(fill="x")

        tk.Label(header, text="COCHING 워크플로우 모니터", font=("Segoe UI", 16, "bold"),
                 bg=BG_HEADER, fg=FG).pack(side="left")

        self.lbl_time = tk.Label(header, text="", font=("Segoe UI", 10),
                                  bg=BG_HEADER, fg=FG_DIM)
        self.lbl_time.pack(side="right", padx=(0, 8))

        self.lbl_status = tk.Label(header, text="  로딩 중...  ", font=("Segoe UI", 10, "bold"),
                                    bg=YELLOW, fg="#1e1e2e", padx=8, pady=2)
        self.lbl_status.pack(side="right", padx=4)

        # 버튼 바
        btn_bar = tk.Frame(self.root, bg=BG, pady=6, padx=16)
        btn_bar.pack(fill="x")

        self.btn_refresh = tk.Button(
            btn_bar, text="  즉시 새로고침  ", font=("Segoe UI", 10, "bold"),
            bg=BLUE, fg="#1e1e2e", activebackground="#b4befe", relief="flat",
            cursor="hand2", command=self._start_refresh, padx=12, pady=4
        )
        self.btn_refresh.pack(side="left")

        self.btn_html = tk.Button(
            btn_bar, text="  HTML 리포트 생성  ", font=("Segoe UI", 10),
            bg=BG_CARD, fg=FG, activebackground=BG_HEADER, relief="flat",
            cursor="hand2", command=self._generate_html, padx=12, pady=4
        )
        self.btn_html.pack(side="left", padx=8)

        self.btn_n8n = tk.Button(
            btn_bar, text="  n8n 열기  ", font=("Segoe UI", 10),
            bg=BG_CARD, fg=FG, activebackground=BG_HEADER, relief="flat",
            cursor="hand2", command=lambda: webbrowser.open("http://localhost:5678"), padx=12, pady=4
        )
        self.btn_n8n.pack(side="left")

        self.lbl_auto = tk.Label(btn_bar, text="자동 새로고침: 1분", font=("Segoe UI", 9),
                                  bg=BG, fg=FG_DIM)
        self.lbl_auto.pack(side="right")

        # 스크롤 가능한 메인 영역
        container = tk.Frame(self.root, bg=BG)
        container.pack(fill="both", expand=True, padx=16, pady=(4, 16))

        canvas = tk.Canvas(container, bg=BG, highlightthickness=0)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        self.scroll_frame = tk.Frame(canvas, bg=BG)

        self.scroll_frame.bind("<Configure>",
                               lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # 마우스 휠 스크롤
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)
        self.canvas = canvas

        # 초기 로딩 표시
        self.lbl_loading = tk.Label(self.scroll_frame, text="데이터를 불러오는 중...",
                                     font=("Segoe UI", 12), bg=BG, fg=FG_DIM)
        self.lbl_loading.pack(pady=40)

    # ── 데이터 새로고침 ──────────────────────
    def _start_refresh(self):
        if self.is_loading:
            return
        self.is_loading = True
        self.btn_refresh.configure(state="disabled", text="  로딩 중...  ")
        self.lbl_status.configure(text="  갱신 중...  ", bg=YELLOW)

        thread = threading.Thread(target=self._fetch_data, daemon=True)
        thread.start()

    def _fetch_data(self):
        try:
            self.api_key = get_n8n_api_key()
            wf_data = fetch_all_workflows(self.api_key)
            db_counts = fetch_db_counts()
            prev_counts = load_prev_counts()
            backups = check_backups()
            save_state(db_counts)

            self.root.after(0, self._render, wf_data, db_counts, prev_counts, backups)
        except Exception as e:
            self.root.after(0, self._render_error, str(e))

    def _render_error(self, msg: str):
        self.is_loading = False
        self.btn_refresh.configure(state="normal", text="  즉시 새로고침  ")
        self.lbl_status.configure(text="  오류  ", bg=RED)
        self.lbl_time.configure(text=now_kst().strftime("%H:%M:%S"))

        for w in self.scroll_frame.winfo_children():
            w.destroy()

        tk.Label(self.scroll_frame, text=f"데이터 수집 오류:\n{msg}",
                 font=("Segoe UI", 11), bg=BG, fg=RED, wraplength=700, justify="left").pack(pady=40)

        self._schedule_auto_refresh()

    def _render(self, wf_data: list, db_counts: dict, prev_counts: dict, backups: list):
        self.is_loading = False
        self.btn_refresh.configure(state="normal", text="  즉시 새로고침  ")
        self.lbl_time.configure(text=now_kst().strftime("%H:%M:%S"))

        # 전체 상태 판정
        all_alerts = []
        for wf in wf_data:
            all_alerts.extend(wf["alerts"])

        has_critical = any(wf["status"] == "CRITICAL" for wf in wf_data)
        has_warning = any(wf["status"] == "WARNING" for wf in wf_data)

        if has_critical:
            self.lbl_status.configure(text="  CRITICAL  ", bg=RED, fg="#1e1e2e")
        elif has_warning:
            self.lbl_status.configure(text="  WARNING  ", bg=YELLOW, fg="#1e1e2e")
        else:
            self.lbl_status.configure(text="  ALL OK  ", bg=GREEN, fg="#1e1e2e")

        # 기존 위젯 제거
        for w in self.scroll_frame.winfo_children():
            w.destroy()

        # ── 워크플로우 섹션 ──
        self._section_title("n8n 워크플로우 상태")

        for wf in wf_data:
            self._workflow_card(wf)

        # ── DB 섹션 ──
        self._section_title("PostgreSQL DB 현황")
        self._db_table(db_counts, prev_counts)

        # ── 백업 섹션 ──
        self._section_title("크론 백업 상태")
        self._backup_table(backups)

        # 스크롤 리셋
        self.canvas.yview_moveto(0)
        self._schedule_auto_refresh()

    def _schedule_auto_refresh(self):
        if self.auto_refresh_id:
            self.root.after_cancel(self.auto_refresh_id)
        self.auto_refresh_id = self.root.after(AUTO_REFRESH_MS, self._start_refresh)

    # ── UI 컴포넌트 ──────────────────────────
    def _section_title(self, text: str):
        frame = tk.Frame(self.scroll_frame, bg=BG)
        frame.pack(fill="x", pady=(16, 6))
        tk.Label(frame, text=text, font=("Segoe UI", 13, "bold"),
                 bg=BG, fg=TEAL).pack(side="left")
        ttk.Separator(frame).pack(side="left", fill="x", expand=True, padx=(12, 0))

    def _workflow_card(self, wf: dict):
        status = wf["status"]
        border_color = {
            "OK": GREEN, "WARNING": YELLOW, "CRITICAL": RED, "UNKNOWN": FG_DIM
        }.get(status, FG_DIM)

        card = tk.Frame(self.scroll_frame, bg=BG_CARD, highlightbackground=border_color,
                        highlightthickness=2, padx=14, pady=10)
        card.pack(fill="x", pady=3)

        # 첫 줄: 이름 + 상태 뱃지
        row1 = tk.Frame(card, bg=BG_CARD)
        row1.pack(fill="x")

        status_icon = {"OK": "OK", "WARNING": "!", "CRITICAL": "X", "UNKNOWN": "?"}.get(status, "?")
        status_bg = {"OK": GREEN, "WARNING": YELLOW, "CRITICAL": RED}.get(status, FG_DIM)

        tk.Label(row1, text=f" {status_icon} ", font=("Segoe UI", 10, "bold"),
                 bg=status_bg, fg="#1e1e2e", padx=6).pack(side="left")

        tk.Label(row1, text=f"  {wf['name']}", font=("Segoe UI", 11, "bold"),
                 bg=BG_CARD, fg=FG).pack(side="left")

        active_text = "활성" if wf["active"] else "비활성"
        active_fg = GREEN if wf["active"] else FG_DIM
        tk.Label(row1, text=active_text, font=("Segoe UI", 9),
                 bg=BG_CARD, fg=active_fg).pack(side="right")

        # 둘째 줄: 상세 정보
        row2 = tk.Frame(card, bg=BG_CARD)
        row2.pack(fill="x", pady=(4, 0))

        info_parts = [
            f"마지막 실행: {wf['last_run'] or '-'}  ({format_ago(wf['last_run_ago'])})",
            f"성공: {wf['success']}  실패: {wf['error']}",
            f"연속실패: {wf['consecutive_failures']}",
        ]
        tk.Label(row2, text="   |   ".join(info_parts),
                 font=("Segoe UI", 9), bg=BG_CARD, fg=FG_DIM).pack(side="left")

        # 알림 행
        for alert in wf["alerts"]:
            alert_row = tk.Frame(card, bg=BG_CARD)
            alert_row.pack(fill="x", pady=(2, 0))
            tk.Label(alert_row, text=f"  >> {alert}",
                     font=("Segoe UI", 9, "bold"), bg=BG_CARD, fg=RED).pack(side="left")

    def _db_table(self, counts: dict, prev: dict):
        frame = tk.Frame(self.scroll_frame, bg=BG_CARD, padx=14, pady=10)
        frame.pack(fill="x", pady=3)

        # 헤더
        hdr = tk.Frame(frame, bg=BG_HEADER)
        hdr.pack(fill="x")
        for col, w in [("테이블", 25), ("현재 건수", 12), ("증감", 12)]:
            tk.Label(hdr, text=col, font=("Segoe UI", 9, "bold"), bg=BG_HEADER, fg=FG,
                     width=w, anchor="w", padx=6, pady=4).pack(side="left")

        # 행
        for table in PG_TABLES:
            cur = counts.get(table)
            prv = prev.get(table)

            row = tk.Frame(frame, bg=BG_CARD)
            row.pack(fill="x")

            tk.Label(row, text=table, font=("Consolas", 9), bg=BG_CARD, fg=FG,
                     width=25, anchor="w", padx=6, pady=3).pack(side="left")

            cur_text = f"{cur:,}" if cur is not None else "오류"
            tk.Label(row, text=cur_text, font=("Consolas", 9), bg=BG_CARD, fg=FG,
                     width=12, anchor="w", padx=6).pack(side="left")

            if cur is not None and prv is not None:
                delta = cur - prv
                if delta > 0:
                    d_text, d_fg = f"+{delta:,}", GREEN
                elif delta < 0:
                    d_text, d_fg = f"{delta:,}", RED
                else:
                    d_text, d_fg = "0", FG_DIM
            else:
                d_text, d_fg = "-", FG_DIM

            tk.Label(row, text=d_text, font=("Consolas", 9, "bold"), bg=BG_CARD, fg=d_fg,
                     width=12, anchor="w", padx=6).pack(side="left")

    def _backup_table(self, backups: list):
        frame = tk.Frame(self.scroll_frame, bg=BG_CARD, padx=14, pady=10)
        frame.pack(fill="x", pady=3)

        for bp in backups:
            row = tk.Frame(frame, bg=BG_CARD)
            row.pack(fill="x")

            tk.Label(row, text=bp["path"], font=("Consolas", 9), bg=BG_CARD, fg=FG,
                     width=25, anchor="w", padx=6, pady=3).pack(side="left")

            if bp["ok"]:
                text = f"{bp['ago_hours']}시간 전"
                fg = GREEN
            elif bp["ago_hours"] is not None:
                text = f"{bp['ago_hours']}시간 전 (오래됨)"
                fg = YELLOW
            else:
                text = "파일 없음"
                fg = RED

            tk.Label(row, text=text, font=("Segoe UI", 9), bg=BG_CARD, fg=fg,
                     padx=6).pack(side="left")

    def _generate_html(self):
        """CLI 버전의 HTML 출력을 실행"""
        monitor_py = SCRIPT_DIR / "workflow_monitor.py"
        try:
            subprocess.Popen(
                [sys.executable, str(monitor_py), "--format", "html"],
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            )
            report_path = REPORT_DIR / "monitor_report.html"
            # 잠시 후 브라우저 열기
            self.root.after(2000, lambda: webbrowser.open(str(report_path)))
        except Exception as e:
            messagebox.showerror("오류", f"HTML 생성 실패:\n{e}")


# ══════════════════════════════════════════════
# 진입점
# ══════════════════════════════════════════════
if __name__ == "__main__":
    root = tk.Tk()

    # 고해상도 스케일링
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    app = MonitorApp(root)
    root.mainloop()
