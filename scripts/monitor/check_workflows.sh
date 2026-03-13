#!/usr/bin/env bash
# =============================================================
#  COCHING 워크플로우 모니터 — WSL 크론 실행 셸 스크립트
#  역할: Python 모니터를 실행하고 로그와 HTML 리포트를 저장
#
#  crontab 등록 예시 (30분마다 + 매일 08:00 HTML):
#    */30 * * * * /home/kpros/scripts/check_workflows.sh >> /home/kpros/logs/monitor.log 2>&1
#    0 8  * * *  /home/kpros/scripts/check_workflows.sh html >> /home/kpros/logs/monitor.log 2>&1
#
#  직접 실행:
#    bash check_workflows.sh          # 텍스트 출력
#    bash check_workflows.sh html     # HTML 리포트 생성
#    bash check_workflows.sh json     # JSON 저장
# =============================================================

set -euo pipefail

# ── 경로 설정 ──────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# WSL 내부에서 Windows 경로를 그대로 쓸 수 없으므로 wslpath 변환 또는
# 실제 WSL 마운트 경로로 접근
WIN_SCRIPT="E:\\COCHING-WORKFLOW\\scripts\\monitor\\workflow_monitor.py"
WSL_SCRIPT="/mnt/e/COCHING-WORKFLOW/scripts/monitor/workflow_monitor.py"

LOG_DIR="/home/kpros/logs/monitor"
JSON_DIR="/home/kpros/logs/monitor/json"
TIMESTAMP="$(date '+%Y%m%d_%H%M%S')"

# ── 파라미터 처리 ──────────────────────────────────────────
FORMAT="${1:-text}"

# ── 디렉토리 생성 ──────────────────────────────────────────
mkdir -p "${LOG_DIR}"
mkdir -p "${JSON_DIR}"

# ── Python 경로 확인 ──────────────────────────────────────
PYTHON="$(which python3 2>/dev/null || which python 2>/dev/null || echo '')"
if [[ -z "${PYTHON}" ]]; then
    echo "[오류] Python3 를 찾을 수 없습니다." >&2
    exit 1
fi

echo "=================================================="
echo " COCHING 워크플로우 모니터 시작: $(date '+%Y-%m-%d %H:%M:%S')"
echo " 포맷: ${FORMAT}"
echo " Python: ${PYTHON}"
echo "=================================================="

# ── 스크립트 존재 확인 ────────────────────────────────────
if [[ ! -f "${WSL_SCRIPT}" ]]; then
    echo "[오류] 모니터 스크립트를 찾을 수 없습니다: ${WSL_SCRIPT}" >&2
    exit 1
fi

# ── 실행 ──────────────────────────────────────────────────
if [[ "${FORMAT}" == "json" ]]; then
    # JSON 모드: 파일로 저장 + stdout 출력
    JSON_OUT="${JSON_DIR}/monitor_${TIMESTAMP}.json"
    "${PYTHON}" "${WSL_SCRIPT}" --format json | tee "${JSON_OUT}"
    echo ""
    echo "[JSON 저장] ${JSON_OUT}"

    # 오래된 JSON 파일 정리 (30개 초과 시 삭제)
    JSON_COUNT="$(ls -1 "${JSON_DIR}"/*.json 2>/dev/null | wc -l)"
    if [[ "${JSON_COUNT}" -gt 30 ]]; then
        ls -1t "${JSON_DIR}"/*.json | tail -n +31 | xargs rm -f
        echo "[정리] 오래된 JSON 스냅샷 삭제 완료"
    fi

elif [[ "${FORMAT}" == "html" ]]; then
    # HTML 모드: Windows 경로에 저장 (Python 스크립트가 직접 저장)
    "${PYTHON}" "${WSL_SCRIPT}" --format html
    echo "[HTML 리포트] /mnt/e/COCHING-WORKFLOW/reports/monitor_report.html"

else
    # TEXT 모드: stdout + 일별 로그 파일
    LOG_FILE="${LOG_DIR}/monitor_${TIMESTAMP}.txt"
    "${PYTHON}" "${WSL_SCRIPT}" --format text | tee "${LOG_FILE}"

    # 오래된 텍스트 로그 정리 (7일치 초과 시 삭제)
    find "${LOG_DIR}" -maxdepth 1 -name "monitor_*.txt" -mtime +7 -delete 2>/dev/null || true
fi

EXIT_CODE="${PIPESTATUS[0]:-$?}"

echo ""
echo "=================================================="
echo " 완료: $(date '+%Y-%m-%d %H:%M:%S')  종료코드: ${EXIT_CODE}"
echo "=================================================="

# ── 알림: 크리티컬 감지 시 텔레그램/슬랙 연동 확장 가능 지점 ──
# 아래 주석을 해제하고 TOKEN/CHAT_ID 를 설정하면 Telegram 알림 발송
#
# if [[ "${EXIT_CODE}" -ne 0 ]] || grep -q "CRITICAL" "${LOG_FILE:-/dev/null}" 2>/dev/null; then
#     TG_TOKEN="YOUR_TELEGRAM_BOT_TOKEN"
#     TG_CHAT="YOUR_CHAT_ID"
#     MSG="[COCHING] CRITICAL 알림 감지 — $(date '+%Y-%m-%d %H:%M')"
#     curl -s -X POST "https://api.telegram.org/bot${TG_TOKEN}/sendMessage" \
#          -d "chat_id=${TG_CHAT}&text=${MSG}" > /dev/null
# fi

exit "${EXIT_CODE}"
