#!/usr/bin/env python3
"""ingredient_master 기능 분류 배치 — Gemini로 화장품 원료 기능 분류 → ingredient_master.ingredient_type 업데이트
대상: ingredient_type = 'single' (미분류 원료)
분류 결과: HUMECTANT, EMOLLIENT, EMULSIFIER, SURFACTANT, PRESERVATIVE,
           ANTIOXIDANT, UV_FILTER, THICKENER, FILM_FORMER, CHELATING,
           PH_ADJUSTER, COLORANT, FRAGRANCE, ACTIVE, OTHER
"""
import json, subprocess, sys, time, re, os, urllib.request, io

# Windows cp949 인코딩 문제 방지
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace", line_buffering=True)

GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
if not GEMINI_KEY:
    print("ERROR: GEMINI_API_KEY 환경변수를 설정하세요. (set GEMINI_API_KEY=키값)")
    sys.exit(1)

BATCH_SIZE = 10   # 한 번에 10개씩 분류 (비용 절감)
ROUNDS = int(sys.argv[1]) if len(sys.argv) > 1 else 100
DELAY = 4

VALID_TYPES = {
    "HUMECTANT", "EMOLLIENT", "EMULSIFIER", "SURFACTANT", "PRESERVATIVE",
    "ANTIOXIDANT", "UV_FILTER", "THICKENER", "FILM_FORMER", "CHELATING",
    "PH_ADJUSTER", "COLORANT", "FRAGRANCE", "ACTIVE", "OTHER"
}

DB_ENV = {**os.environ, "PGPASSWORD": "coching2026!"}
PSQL = os.environ.get("PSQL_PATH", r"C:\Program Files\PostgreSQL\17\bin\psql.exe")
DB_CMD = [PSQL, "-h", "172.21.144.1", "-U", "coching_user", "-d", "coching_db", "-t", "-A"]


def run_sql(sql):
    r = subprocess.run(DB_CMD, input=sql, capture_output=True, text=True, env=DB_ENV, encoding="utf-8")
    return r.stdout.strip()


def run_sql_params(sql, params):
    escaped = []
    for p in params:
        if p is None:
            escaped.append("NULL")
        else:
            safe = str(p).replace("\\", "\\\\").replace("'", "''")
            escaped.append(f"'{safe}'")
    result_sql = sql
    for e in escaped:
        result_sql = result_sql.replace("%s", e, 1)
    r = subprocess.run(DB_CMD, input=result_sql, capture_output=True, text=True, env=DB_ENV, encoding="utf-8")
    if r.returncode != 0:
        print(f"    [SQL ERR] rc={r.returncode} {r.stderr[:150]}")
    return r.stdout.strip()


def call_gemini(prompt, retries=2):
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


def parse_classifications(text, batch):
    """Gemini 응답에서 INCI명→type 매핑 추출 — 다단계 폴백"""
    text = re.sub(r"```json\n?|```", "", text).strip()
    result = {}

    # 1단계: 전체 JSON 배열 파싱
    m = re.search(r"\[[\s\S]*\]", text)
    if m:
        raw = m.group(0)
        for attempt in [raw, re.sub(r'\n\s*', ' ', raw)]:
            try:
                items = json.loads(attempt)
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    inci = item.get("inci")
                    itype = item.get("type", "").upper()
                    if inci and itype in VALID_TYPES:
                        result[inci] = itype
                if result:
                    return result
            except json.JSONDecodeError:
                pass

    # 2단계: 개별 {"inci": ..., "type": ...} 패턴 추출 (불완전한 JSON 대응)
    for m2 in re.finditer(r'"inci"\s*:\s*"([^"]+)"\s*,\s*"type"\s*:\s*"([^"]+)"', text):
        inci, itype = m2.group(1), m2.group(2).upper()
        if itype in VALID_TYPES:
            result[inci] = itype
    if result:
        return result

    # 3단계: "type" 먼저인 순서 대응
    for m2 in re.finditer(r'"type"\s*:\s*"([^"]+)"\s*[,}].*?"inci"\s*:\s*"([^"]+)"', text):
        itype, inci = m2.group(1).upper(), m2.group(2)
        if itype in VALID_TYPES:
            result[inci] = itype

    return result


# === 메인 ===
print(f"=== ingredient_master 기능 분류 배치 시작 ===")
print(f"목표: {ROUNDS}라운드 × {BATCH_SIZE}개 = {ROUNDS * BATCH_SIZE}개 원료\n")

total_ok, total_skip = 0, 0

for r in range(1, ROUNDS + 1):
    rows = run_sql(f"""
        SELECT inci_name
        FROM ingredient_master
        WHERE ingredient_type = 'single'
          AND LENGTH(inci_name) > 2
          AND inci_name ~ '[A-Za-z]'
        ORDER BY RANDOM()
        LIMIT {BATCH_SIZE};
    """)

    if not rows.strip():
        print(f"[{r}] 미분류 원료 없음. 종료.")
        break

    lines = [l.strip() for l in rows.strip().split("\n") if l.strip()]
    print(f"[{r}/{ROUNDS}] {len(lines)}개 분류 중...")

    doc_list = "\n".join([f"- {inci}" for inci in lines])
    prompt = f"""다음 화장품 원료 목록의 주요 기능을 분류해주세요.

{doc_list}

반드시 JSON 배열만 출력 (설명 없이):
[
  {{"inci": "INCI명", "type": "HUMECTANT"}}
]

type 옵션 (하나만 선택):
HUMECTANT (보습/수분공급), EMOLLIENT (유연/피부연화), EMULSIFIER (유화제),
SURFACTANT (계면활성제/세정), PRESERVATIVE (방부제), ANTIOXIDANT (항산화),
UV_FILTER (자외선차단), THICKENER (점도증가), FILM_FORMER (피막형성),
CHELATING (킬레이트), PH_ADJUSTER (pH조절), COLORANT (색소),
FRAGRANCE (향료), ACTIVE (기능성활성성분), OTHER (기타/불명확)"""

    resp = call_gemini(prompt)
    if not resp or "error" in resp:
        err = resp.get("error", {}).get("message", "?") if resp else "no resp"
        print(f"  ✗ API: {err[:80]}")
        time.sleep(DELAY)
        continue

    try:
        text = resp["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError):
        print("  ✗ 응답 형식 오류")
        time.sleep(DELAY)
        continue

    classifications = parse_classifications(text, lines)
    if not classifications:
        print(f"  ✗ 파싱 실패 (raw: {repr(text[:150])})")
        time.sleep(DELAY)
        continue

    batch_ok = 0
    for inci, itype in classifications.items():
        if itype == "OTHER":
            # OTHER는 업데이트하지 않고 건너뜀 (재분류 대상 유지)
            total_skip += 1
            continue
        run_sql_params(
            "UPDATE ingredient_master SET ingredient_type = %s WHERE inci_name = %s AND ingredient_type = 'single';",
            [itype, inci]
        )
        batch_ok += 1

    total_ok += batch_ok
    success_rate = total_ok / max(total_ok + total_skip, 1) * 100
    print(f"  ✓ {batch_ok}/{len(lines)}개 분류 (OTHER 제외: {total_skip}개 누적) → 총 {total_ok}개 업데이트")
    time.sleep(DELAY)

print(f"\n=== 완료: {total_ok}개 분류 업데이트 ===")
for itype in ["HUMECTANT", "EMOLLIENT", "EMULSIFIER", "SURFACTANT", "PRESERVATIVE",
              "ANTIOXIDANT", "UV_FILTER", "THICKENER", "FILM_FORMER"]:
    cnt = run_sql(f"SELECT COUNT(*) FROM ingredient_master WHERE ingredient_type = '{itype}';")
    print(f"  {itype}: {cnt}건")
single = run_sql("SELECT COUNT(*) FROM ingredient_master WHERE ingredient_type = 'single';")
print(f"  미분류(single): {single}건")
