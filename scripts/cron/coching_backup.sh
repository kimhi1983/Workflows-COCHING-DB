#!/bin/bash
# ============================================================
# COCHING DB 이중 백업 스크립트
# 1차: WSL2 로컬 (/home/kpros/backup/)
# 2차: Windows E: 드라이브 (/mnt/e/COCHING/backup/db/)
# ============================================================

set -euo pipefail

# --- 설정 ---
DB_NAME="coching_db"
DB_USER="coching_user"
DB_HOST="127.0.0.1"
DB_PORT="5432"

LOCAL_BACKUP_DIR="/home/kpros/backup/pgdump"
WIN_BACKUP_DIR="/mnt/e/COCHING/backup/pgdump"
PGPASSFILE_TMP="/tmp/pgpass_backup"

# 보관 기간 (일)
KEEP_DAYS=30

# 타임스탬프
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_NAME="${DB_NAME}_${TIMESTAMP}"

# 로그
LOG_FILE="/home/kpros/backup/logs/pgdump.log"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

# --- 사전 체크 ---
mkdir -p "$LOCAL_BACKUP_DIR" "$WIN_BACKUP_DIR" 2>/dev/null || true

# pgpass 설정
printf '%s:%s:%s:%s:%s\n' "$DB_HOST" "$DB_PORT" "$DB_NAME" "$DB_USER" "${COCHING_DB_PASS}" > "$PGPASSFILE_TMP"
chmod 600 "$PGPASSFILE_TMP"
export PGPASSFILE="$PGPASSFILE_TMP"

log "========== 백업 시작: ${BACKUP_NAME} =========="

# --- 1단계: pg_dump (SQL 형식) ---
DUMP_FILE="${LOCAL_BACKUP_DIR}/${BACKUP_NAME}.sql"

log "[1/5] pg_dump 실행 중..."
if pg_dump -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" \
    --no-owner --no-privileges --if-exists --clean \
    -f "$DUMP_FILE" 2>>"$LOG_FILE"; then
    DUMP_SIZE=$(du -h "$DUMP_FILE" | cut -f1)
    log "[1/5] pg_dump 완료 (${DUMP_SIZE})"
else
    log "[1/5] ERROR: pg_dump 실패!"
    rm -f "$PGPASSFILE_TMP"
    exit 1
fi

# --- 2단계: gzip 압축 ---
log "[2/5] 압축 중..."
gzip -f "$DUMP_FILE"
GZ_FILE="${DUMP_FILE}.gz"
GZ_SIZE=$(du -h "$GZ_FILE" | cut -f1)
log "[2/5] 압축 완료 (${GZ_SIZE})"

# --- 3단계: 체크섬 생성 ---
log "[3/5] 체크섬 생성..."
sha256sum "$GZ_FILE" > "${GZ_FILE}.sha256"

# --- 4단계: Windows E: 드라이브로 복사 (2중 백업) ---
log "[4/5] E: 드라이브로 복사 중..."
if cp "$GZ_FILE" "${WIN_BACKUP_DIR}/" && cp "${GZ_FILE}.sha256" "${WIN_BACKUP_DIR}/"; then
    # 복사 검증
    LOCAL_HASH=$(cat "${GZ_FILE}.sha256" | awk '{print $1}')
    WIN_HASH=$(sha256sum "${WIN_BACKUP_DIR}/${BACKUP_NAME}.sql.gz" | awk '{print $1}')
    if [ "$LOCAL_HASH" = "$WIN_HASH" ]; then
        log "[4/5] E: 드라이브 복사 완료 + 무결성 검증 OK"
    else
        log "[4/5] WARNING: 체크섬 불일치! 로컬=${LOCAL_HASH} vs E:=${WIN_HASH}"
    fi
else
    log "[4/5] WARNING: E: 드라이브 복사 실패 (로컬 백업은 유지)"
fi

# --- 5단계: 오래된 백업 정리 ---
log "[5/5] ${KEEP_DAYS}일 이상 된 백업 정리..."
find "$LOCAL_BACKUP_DIR" -name "${DB_NAME}_*.sql.gz*" -mtime +${KEEP_DAYS} -delete 2>/dev/null || true
find "$WIN_BACKUP_DIR" -name "${DB_NAME}_*.sql.gz*" -mtime +${KEEP_DAYS} -delete 2>/dev/null || true

# 현재 백업 현황
LOCAL_COUNT=$(ls -1 "${LOCAL_BACKUP_DIR}"/${DB_NAME}_*.sql.gz 2>/dev/null | wc -l)
WIN_COUNT=$(ls -1 "${WIN_BACKUP_DIR}"/${DB_NAME}_*.sql.gz 2>/dev/null | wc -l)

log "========== 백업 완료 =========="
log "  로컬: ${GZ_FILE} (${GZ_SIZE})"
log "  E:드라이브: ${WIN_BACKUP_DIR}/${BACKUP_NAME}.sql.gz"
log "  보관 현황: 로컬 ${LOCAL_COUNT}개 / E: ${WIN_COUNT}개"
log ""

# 정리
rm -f "$PGPASSFILE_TMP"

# JSON 출력 (n8n 연동용)
cat <<EOF
{
  "status": "success",
  "timestamp": "${TIMESTAMP}",
  "local_path": "${GZ_FILE}",
  "win_path": "${WIN_BACKUP_DIR}/${BACKUP_NAME}.sql.gz",
  "size": "${GZ_SIZE}",
  "local_count": ${LOCAL_COUNT},
  "win_count": ${WIN_COUNT}
}
EOF
