#!/usr/bin/env python3
"""ingredient_master 기능 분류 배치 v3 — Ollama (Qwen 2.5 14B) 로컬 LLM 버전
대상: ingredient_type = 'single' (미분류 원료)
분류 결과: HUMECTANT, EMOLLIENT, EMULSIFIER, SURFACTANT, PRESERVATIVE,
           ANTIOXIDANT, UV_FILTER, THICKENER, FILM_FORMER, CHELATING,
           PH_ADJUSTER, COLORANT, FRAGRANCE, ACTIVE, OTHER
특징: API 키 불필요, DELAY=0, 로컬 GPU 가속 (RTX 4070 Super 12GB)
"""
import json, subprocess, sys, time, re, os, io
import urllib.request

# Windows 인코딩 문제 방지
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:14b")
BATCH_SIZE = int(os.environ.get("BATCH_SIZE", "20"))   # 로컬이라 20개씩
ROUNDS = int(sys.argv[1]) if len(sys.argv) > 1 else 500
DELAY = 0   # 로컬 LLM — API 제한 없음

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


def call_ollama(prompt, retries=3):
    """Ollama API 호출 (로컬 LLM)"""
    body = json.dumps({
        "model": MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.1,
            "num_predict": 4096,   # 로컬이라 넉넉하게
            "num_ctx": 8192
        }
    }).encode("utf-8")
    url = f"{OLLAMA_URL}/api/generate"
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    for attempt in range(retries):
        try:
            resp = urllib.request.urlopen(req, timeout=120)
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("response", "")
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(2)
                continue
            print(f"  [Ollama ERR] {e}")
            return ""


def parse_classifications(text):
    """다단계 폴백 파싱 — JSON 배열 → 개별 패턴 → type-first 패턴"""
    text = re.sub(r"```json\n?|```", "", text).strip()
    result = {}

    # 1단계: 전체 JSON 배열
    m = re.search(r"\[[\s\S]*\]", text)
    if m:
        raw = m.group(0)
        for attempt in [raw, re.sub(r'\n\s*', ' ', raw)]:
            try:
                items = json.loads(attempt)
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    inci = item.get("inci") or item.get("INCI") or item.get("name")
                    itype = str(item.get("type", "")).upper()
                    if inci and itype in VALID_TYPES:
                        result[inci] = itype
                if result:
                    return result
            except json.JSONDecodeError:
                pass

    # 2단계: 개별 {"inci": ..., "type": ...} 패턴
    for m2 in re.finditer(r'"inci"\s*:\s*"([^"]+)"\s*,\s*"type"\s*:\s*"([^"]+)"', text):
        inci, itype = m2.group(1), m2.group(2).upper()
        if itype in VALID_TYPES:
            result[inci] = itype
    if result:
        return result

    # 3단계: type 먼저인 순서
    for m2 in re.finditer(r'"type"\s*:\s*"([^"]+)"[^}]*?"inci"\s*:\s*"([^"]+)"', text, re.DOTALL):
        itype, inci = m2.group(1).upper(), m2.group(2)
        if itype in VALID_TYPES:
            result[inci] = itype

    return result


def check_ollama():
    """Ollama 서버 및 모델 확인"""
    try:
        req = urllib.request.Request(f"{OLLAMA_URL}/api/tags")
        resp = urllib.request.urlopen(req, timeout=5)
        data = json.loads(resp.read())
        models = [m["name"] for m in data.get("models", [])]
        if not any(MODEL.split(":")[0] in m for m in models):
            print(f"ERROR: 모델 '{MODEL}'이 없습니다. 먼저 실행하세요:")
            print(f"  ollama pull {MODEL}")
            sys.exit(1)
        print(f"Ollama OK — 모델: {MODEL}, 사용 가능 모델: {models}")
    except Exception as e:
        print(f"ERROR: Ollama 서버 연결 실패 ({OLLAMA_URL}): {e}")
        print("  ollama serve 를 먼저 실행하세요.")
        sys.exit(1)


# === 메인 ===
check_ollama()
print(f"=== ingredient_master 기능 분류 v3 (로컬 LLM) ===")
print(f"모델: {MODEL} | 배치: {BATCH_SIZE}개 | 라운드: {ROUNDS}")

single_count = run_sql("SELECT COUNT(*) FROM ingredient_master WHERE ingredient_type = 'single';")
print(f"미분류 잔존: {single_count}건\n")

total_ok, total_skip = 0, 0
start_time = time.time()

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
        print(f"[{r}] 미분류 원료 없음. 완료!")
        break

    lines = [l.strip() for l in rows.strip().split("\n") if l.strip()]
    elapsed = time.time() - start_time
    rate = total_ok / max(elapsed / 60, 0.01)
    print(f"[{r}/{ROUNDS}] {len(lines)}개 | 총 {total_ok}건 | {rate:.0f}건/분", end=" ... ")

    doc_list = "\n".join([f"- {inci}" for inci in lines])
    prompt = f"""다음 화장품 원료 목록의 주요 기능을 분류하세요.

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

    text = call_ollama(prompt)
    if not text:
        print("✗ API 오류")
        continue

    classifications = parse_classifications(text)
    if not classifications:
        print(f"✗ 파싱 실패 ({repr(text[:100])})")
        continue

    batch_ok = 0
    for inci, itype in classifications.items():
        if itype == "OTHER":
            total_skip += 1
            continue
        run_sql_params(
            "UPDATE ingredient_master SET ingredient_type = %s WHERE inci_name = %s AND ingredient_type = 'single';",
            [itype, inci]
        )
        batch_ok += 1

    total_ok += batch_ok
    print(f"✓ {batch_ok}/{len(lines)}개")

elapsed_total = time.time() - start_time
print(f"\n=== 완료: {total_ok}건 분류 | {elapsed_total/60:.1f}분 소요 ===")

# 최종 현황
for itype in ["HUMECTANT", "EMOLLIENT", "EMULSIFIER", "SURFACTANT", "PRESERVATIVE",
              "ANTIOXIDANT", "UV_FILTER", "THICKENER", "FILM_FORMER", "ACTIVE", "COLORANT"]:
    cnt = run_sql(f"SELECT COUNT(*) FROM ingredient_master WHERE ingredient_type = '{itype}';")
    print(f"  {itype}: {cnt}건")
single = run_sql("SELECT COUNT(*) FROM ingredient_master WHERE ingredient_type = 'single';")
print(f"  미분류(single): {single}건")
