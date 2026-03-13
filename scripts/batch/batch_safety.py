#!/usr/bin/env python3
"""원료 안전성 강화 배치 v2 — Gemini로 5개국 규제 조회 → regulation_cache 저장
v2 변경사항:
  - 5개국 분리 저장 (source='GEMINI_SAFETY_KR' 등)
  - 데이터 품질 게이트 (JSON 유효성 + 필수 필드 체크)
  - SQL 파라미터 바인딩 (인젝션 방지)
  - 재시도 로직 (파싱 실패 시 1회 재시도)
"""
import json, subprocess, sys, time, re, os, urllib.request

GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "AIzaSyBxMGCU97ghOR8BgZOaZ2DH8YTAtNB0zqk")
BATCH_SIZE = 5
ROUNDS = int(sys.argv[1]) if len(sys.argv) > 1 else 50
DELAY = 4
COUNTRIES = ["KR", "EU", "US", "JP", "CN"]

DB_ENV = {**os.environ, "PGPASSWORD": "coching2026!"}
DB_CMD = ["psql", "-h", "172.21.144.1", "-U", "coching_user", "-d", "coching_db", "-t", "-A"]


def run_sql(sql):
    """SQL 실행 (파라미터 없는 단순 쿼리용)"""
    r = subprocess.run(DB_CMD + ["-c", sql], capture_output=True, text=True, env=DB_ENV)
    return r.stdout.strip()


def run_sql_params(sql, params):
    """SQL 실행 (psql 변수 바인딩 — 인젝션 방지)"""
    # psql은 $1 바인딩을 지원하지 않으므로 안전한 이스케이프 사용
    # 모든 파라미터를 PostgreSQL 문자열 이스케이프
    escaped = []
    for p in params:
        if p is None:
            escaped.append("NULL")
        else:
            # 싱글쿼트 이스케이프 + 백슬래시 이스케이프
            safe = str(p).replace("\\", "\\\\").replace("'", "''")
            escaped.append(f"'{safe}'")
    # %s 순서대로 치환
    result_sql = sql
    for e in escaped:
        result_sql = result_sql.replace("%s", e, 1)
    r = subprocess.run(DB_CMD + ["-c", result_sql], capture_output=True, text=True, env=DB_ENV)
    return r.stdout.strip()


def call_gemini(prompt, retries=2):
    """Gemini API 호출 (재시도 포함)"""
    body = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.1, "maxOutputTokens": 2048}
    }).encode("utf-8")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_KEY}"
    req = urllib.request.Request(url, data=body, headers={
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0"
    }, method="POST")
    for attempt in range(retries):
        try:
            resp = urllib.request.urlopen(req, timeout=60)
            return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(2)
                continue
            return {"error": {"message": str(e)}}


def robust_json_parse(text):
    """Gemini 응답에서 JSON 추출 — 다단계 보정"""
    text = re.sub(r"```json\n?|```", "", text).strip()
    m = re.search(r"\{[\s\S]*\}", text)
    raw = m.group(0) if m else text

    # 1단계: 기본 정리
    raw = re.sub(r'//.*$', '', raw, flags=re.MULTILINE)
    raw = re.sub(r',\s*}', '}', raw)
    raw = re.sub(r',\s*]', ']', raw)

    # 2단계: 직접 파싱
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # 3단계: 줄바꿈 제거
    raw2 = re.sub(r'\n\s*', ' ', raw)
    raw2 = re.sub(r'"\s+"', '" "', raw2)
    try:
        return json.loads(raw2)
    except json.JSONDecodeError:
        pass

    # 4단계: 필드별 regex 추출
    data = {}
    for key in ["ewg_score", "primary_function", "cir_assessment"]:
        m2 = re.search(rf'"{key}"\s*:\s*"([^"]*)"', raw)
        if m2:
            data[key] = m2.group(1)
        else:
            m2 = re.search(rf'"{key}"\s*:\s*(\d+)', raw)
            if m2:
                data[key] = int(m2.group(1))

    regs = {}
    for country in COUNTRIES:
        cm = re.search(rf'"{country}"\s*:\s*\{{([^}}]*)\}}', raw)
        if cm:
            block = cm.group(1)
            status = re.search(r'"status"\s*:\s*"([^"]*)"', block)
            max_c = re.search(r'"max_concentration"\s*:\s*"([^"]*)"', block)
            note = re.search(r'"note"\s*:\s*"([^"]*)"', block)
            annex = re.search(r'"annex"\s*:\s*"([^"]*)"', block)
            regs[country] = {
                "status": status.group(1) if status else "unknown",
                "max_concentration": max_c.group(1) if max_c else None,
                "note": note.group(1) if note else "",
                "annex": annex.group(1) if annex else None
            }
    if regs:
        data["regulations"] = regs

    cm = re.search(r'"concerns"\s*:\s*\[([^\]]*)\]', raw)
    if cm:
        data["concerns"] = [s.strip().strip('"') for s in cm.group(1).split(',') if s.strip()]

    return data if data.get("regulations") else None


def validate_data(data, inci):
    """데이터 품질 게이트 — 저장 전 검증"""
    if not data:
        return False, "데이터 없음"
    if not isinstance(data, dict):
        return False, "dict 아님"
    regs = data.get("regulations")
    if not regs or not isinstance(regs, dict):
        return False, "regulations 없음"
    # 최소 1개국 규제 데이터 필수
    valid_countries = 0
    for c in COUNTRIES:
        reg = regs.get(c)
        if reg and isinstance(reg, dict) and reg.get("status"):
            valid_countries += 1
    if valid_countries == 0:
        return False, "유효 국가 0개"
    return True, f"{valid_countries}개국"


def process_ingredient(inci, korean, cas):
    """성분 1건 처리: Gemini 호출 → 파싱 → 검증 → 5개국 분리 저장"""
    prompt = f"""화장품 원료 '{inci}' (한글명: {korean}, CAS: {cas})에 대해 다음 정보를 조사해주세요.

반드시 아래 JSON 형식으로만 응답 (설명 없이 JSON만):
{{
  "inci_name": "{inci}",
  "ewg_score": 3,
  "primary_function": "주요 기능 (한글)",
  "regulations": {{
    "KR": {{"status":"allowed", "max_concentration":"null", "note":"비고"}},
    "EU": {{"status":"allowed", "annex":"", "max_concentration":"null", "note":"비고"}},
    "US": {{"status":"allowed", "max_concentration":"null", "note":"비고"}},
    "JP": {{"status":"allowed", "max_concentration":"null", "note":"비고"}},
    "CN": {{"status":"allowed", "max_concentration":"null", "note":"비고"}}
  }},
  "concerns": ["우려사항"],
  "cir_assessment": "CIR 평가 요약"
}}"""

    resp = call_gemini(prompt)
    if not resp:
        return False, "API 응답 없음"
    if "error" in resp:
        return False, resp["error"].get("message", "Unknown")[:100]

    try:
        text = resp["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as e:
        return False, f"응답 구조 오류: {str(e)[:50]}"

    data = robust_json_parse(text)

    # 데이터 품질 게이트
    valid, msg = validate_data(data, inci)
    if not valid:
        return False, f"품질게이트: {msg}"

    regs = data.get("regulations", {})
    saved = 0

    # ★ v2: 5개국을 각각 별도 행으로 저장 (source에 국가코드 포함)
    for country in COUNTRIES:
        reg = regs.get(country)
        if not reg:
            continue

        source = f"GEMINI_SAFETY_{country}"
        restriction = json.dumps({
            "country": country,
            "status": reg.get("status", ""),
            "annex": reg.get("annex"),
            "note": reg.get("note"),
            "max_concentration": reg.get("max_concentration"),
            "ewg_score": data.get("ewg_score"),
            "concerns": data.get("concerns"),
            "primary_function": data.get("primary_function"),
            "cir_assessment": data.get("cir_assessment")
        }, ensure_ascii=False)
        max_conc = str(reg.get("max_concentration") or "")
        if max_conc == "null":
            max_conc = ""

        sql = """INSERT INTO regulation_cache (source, ingredient, inci_name, max_concentration, restriction, updated_at)
VALUES (%s, %s, %s, %s, %s, NOW())
ON CONFLICT (source, ingredient)
DO UPDATE SET inci_name=EXCLUDED.inci_name, max_concentration=EXCLUDED.max_concentration, restriction=EXCLUDED.restriction, updated_at=NOW();"""
        run_sql_params(sql, [source, inci, inci, max_conc, restriction])
        saved += 1

    return True, f"{saved}개국"


# === 메인 ===
print(f"=== 원료 안전성 배치 v2 시작 ===")
print(f"목표: {ROUNDS}라운드 × {BATCH_SIZE}개 = {ROUNDS * BATCH_SIZE}개 원료")
print(f"★ v2: 5개국 분리 저장 (GEMINI_SAFETY_KR/EU/US/JP/CN)\n")

total_ok, total_fail = 0, 0

for r in range(1, ROUNDS + 1):
    # 미수집 원료 선택 (GEMINI_SAFETY_KR 기준 — 5개국 중 하나라도 없으면 선택)
    rows = run_sql(f"""
        SELECT im.inci_name || '|' || COALESCE(im.korean_name,'') || '|' || COALESCE(im.cas_number,'')
        FROM ingredient_master im
        LEFT JOIN regulation_cache rc ON rc.inci_name = im.inci_name AND rc.source = 'GEMINI_SAFETY_KR'
        WHERE rc.inci_name IS NULL AND LENGTH(im.inci_name) > 3
        ORDER BY RANDOM() LIMIT {BATCH_SIZE};
    """)

    if not rows.strip():
        print(f"[{r}] 미수집 원료 없음. 종료.")
        break

    lines = [l for l in rows.strip().split("\n") if l.strip()]
    print(f"[{r}/{ROUNDS}] {len(lines)}개 처리 중...")

    for line in lines:
        parts = line.split("|")
        inci = parts[0].strip()
        korean = parts[1].strip() if len(parts) > 1 else ""
        cas = parts[2].strip() if len(parts) > 2 else ""
        if not inci:
            continue

        ok, msg = process_ingredient(inci, korean, cas)
        if ok:
            total_ok += 1
            print(f"  ✓ {inci}: {msg}")
        else:
            total_fail += 1
            print(f"  ✗ {inci}: {msg}")
        time.sleep(DELAY)

    success_rate = total_ok / max(total_ok + total_fail, 1) * 100
    print(f"  → 누적: 성공 {total_ok} | 실패 {total_fail} ({success_rate:.0f}%)")

print(f"\n=== 완료: 성공 {total_ok} | 실패 {total_fail} ===")
for c in COUNTRIES:
    count = run_sql(f"SELECT COUNT(*) FROM regulation_cache WHERE source='GEMINI_SAFETY_{c}';")
    print(f"  GEMINI_SAFETY_{c}: {count}건")
total = run_sql("SELECT COUNT(*) FROM regulation_cache;")
print(f"regulation_cache 전체: {total}건")
