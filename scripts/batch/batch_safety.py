#!/usr/bin/env python3
"""원료 안전성 강화 배치 — Gemini로 5개국 규제 조회 → regulation_cache 저장"""
import json, subprocess, sys, time, re, os, urllib.request

GEMINI_KEY = "AIzaSyBxMGCU97ghOR8BgZOaZ2DH8YTAtNB0zqk"
BATCH_SIZE = 5
ROUNDS = int(sys.argv[1]) if len(sys.argv) > 1 else 50
DELAY = 4

DB_ENV = {**os.environ, "PGPASSWORD": "coching2026!"}
DB_CMD = ["psql", "-h", "127.0.0.1", "-U", "coching_user", "-d", "coching_db", "-t", "-A"]

def run_sql(sql, params=None):
    if params:
        for p in params:
            safe = str(p).replace("'", "''") if p else ""
            sql = sql.replace("%s", f"'{safe}'", 1)
    r = subprocess.run(DB_CMD + ["-c", sql], capture_output=True, text=True, env=DB_ENV)
    return r.stdout.strip()

def call_gemini(prompt):
    body = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 2048}
    }).encode("utf-8")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_KEY}"
    req = urllib.request.Request(url, data=body, headers={
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0"
    }, method="POST")
    try:
        resp = urllib.request.urlopen(req, timeout=60)
        return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return {"error": {"message": str(e)}}

def process_ingredient(inci, korean, cas):
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
        text = re.sub(r"```json\n?|```", "", text).strip()
        m = re.search(r"\{[\s\S]*\}", text)
        raw = m.group(0) if m else text
        # Gemini JSON 오류 보정
        raw = re.sub(r'//.*$', '', raw, flags=re.MULTILINE)  # 주석 제거
        raw = re.sub(r',\s*}', '}', raw)  # trailing comma
        raw = re.sub(r',\s*]', ']', raw)
        # 멀티라인 문자열 → 한 줄로
        lines = raw.split('\n')
        fixed = []
        for line in lines:
            fixed.append(line.rstrip())
        raw = '\n'.join(fixed)
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            # 더 공격적 보정: 줄바꿈 제거 후 재시도
            raw2 = re.sub(r'\n\s*', ' ', raw)
            raw2 = re.sub(r'"\s+"', '" "', raw2)  # split strings
            try:
                data = json.loads(raw2)
            except json.JSONDecodeError:
                # 최후: 필드별 추출
                data = {}
                for key in ["ewg_score", "primary_function", "cir_assessment"]:
                    m2 = re.search(rf'"{key}"\s*:\s*"([^"]*)"', raw)
                    if m2:
                        data[key] = m2.group(1)
                    else:
                        m2 = re.search(rf'"{key}"\s*:\s*(\d+)', raw)
                        if m2:
                            data[key] = int(m2.group(1))
                # regulations 블록 추출
                regs = {}
                for country in ["KR", "EU", "US", "JP", "CN"]:
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
                # concerns
                cm = re.search(r'"concerns"\s*:\s*\[([^\]]*)\]', raw)
                if cm:
                    data["concerns"] = [s.strip().strip('"') for s in cm.group(1).split(',')]
                if not data.get("regulations"):
                    return False, "JSON 복구 실패"
    except Exception as e:
        return False, f"파싱: {str(e)[:80]}"

    regs = data.get("regulations", {})
    saved = 0
    ingredient_name = korean if korean else inci

    for country in ["KR", "EU", "US", "JP", "CN"]:
        reg = regs.get(country)
        if not reg:
            continue

        restriction = json.dumps({
            "country": country, "status": reg.get("status", ""),
            "annex": reg.get("annex"), "note": reg.get("note"),
            "ewg_score": data.get("ewg_score"),
            "concerns": data.get("concerns"),
            "primary_function": data.get("primary_function"),
            "cir_assessment": data.get("cir_assessment")
        }, ensure_ascii=False)
        max_conc = str(reg.get("max_concentration") or "")

        sql = """INSERT INTO regulation_cache (source, ingredient, inci_name, max_concentration, restriction, updated_at)
VALUES (%s, %s, %s, %s, %s, NOW())
ON CONFLICT (source, ingredient)
DO UPDATE SET inci_name=EXCLUDED.inci_name, max_concentration=EXCLUDED.max_concentration, restriction=EXCLUDED.restriction, updated_at=NOW();"""
        run_sql(sql, ["GEMINI_SAFETY", ingredient_name, inci, max_conc, restriction])
        saved += 1

    return True, f"{saved}개국"

# === 메인 ===
print(f"=== 원료 안전성 배치 시작 ===")
print(f"목표: {ROUNDS}라운드 × {BATCH_SIZE}개 = {ROUNDS * BATCH_SIZE}개 원료\n")

total_ok, total_fail = 0, 0

for r in range(1, ROUNDS + 1):
    rows = run_sql(f"""
        SELECT im.inci_name || '|' || COALESCE(im.korean_name,'') || '|' || COALESCE(im.cas_number,'')
        FROM ingredient_master im
        LEFT JOIN regulation_cache rc ON rc.inci_name = im.inci_name AND rc.source = 'GEMINI_SAFETY'
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

    print(f"  → 누적: 성공 {total_ok} | 실패 {total_fail}")

print(f"\n=== 완료: 성공 {total_ok} | 실패 {total_fail} ===")
count = run_sql("SELECT COUNT(*) FROM regulation_cache WHERE source='GEMINI_SAFETY';")
print(f"regulation_cache (GEMINI_SAFETY): {count}건")
