#!/usr/bin/env python3
"""다국가 규제 모니터링 배치 — US FDA 규제 문서 수집 → Gemini 분석 → regulation_cache 저장"""
import json, subprocess, sys, time, re, os, urllib.request, urllib.parse

GEMINI_KEY = "AIzaSyBxMGCU97ghOR8BgZOaZ2DH8YTAtNB0zqk"
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
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 4096}
    }).encode("utf-8")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_KEY}"
    req = urllib.request.Request(url, data=body, headers={
        "Content-Type": "application/json", "User-Agent": "Mozilla/5.0"
    }, method="POST")
    try:
        resp = urllib.request.urlopen(req, timeout=60)
        return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return {"error": {"message": str(e)}}

def robust_json_parse(raw):
    """Gemini JSON 응답을 견고하게 파싱"""
    raw = re.sub(r"```json\n?|```", "", raw).strip()
    # 주석 제거, trailing comma 제거
    raw = re.sub(r'//.*$', '', raw, flags=re.MULTILINE)
    raw = re.sub(r',\s*}', '}', raw)
    raw = re.sub(r',\s*]', ']', raw)

    # 배열 추출 시도
    m = re.search(r"\[[\s\S]*\]", raw)
    target = m.group(0) if m else raw

    try:
        return json.loads(target)
    except json.JSONDecodeError:
        # 줄바꿈 제거 후 재시도
        flat = re.sub(r'\n\s*', ' ', target)
        try:
            return json.loads(flat)
        except json.JSONDecodeError:
            pass

    # 개별 객체 추출
    results = []
    for obj_m in re.finditer(r'\{[^{}]*\}', raw):
        try:
            obj = json.loads(obj_m.group(0))
            if "summary_ko" in obj or "index" in obj:
                results.append(obj)
        except:
            # regex로 필드 추출
            block = obj_m.group(0)
            idx = re.search(r'"index"\s*:\s*(\d+)', block)
            summary = re.search(r'"summary_ko"\s*:\s*"([^"]*)"', block)
            cat = re.search(r'"category"\s*:\s*"([^"]*)"', block)
            sev = re.search(r'"severity"\s*:\s*"([^"]*)"', block)
            if summary:
                results.append({
                    "index": int(idx.group(1)) if idx else len(results)+1,
                    "summary_ko": summary.group(1),
                    "category": cat.group(1) if cat else "other",
                    "affected_ingredients": [],
                    "severity": sev.group(1) if sev else "low",
                    "keywords": []
                })
    return results if results else None

# === 1. US Federal Register 수집 ===
print("=== 다국가 규제 모니터링 배치 시작 ===\n")

search_terms = [
    "cosmetic OR cosmetics",
    "skin care ingredient",
    "sunscreen regulation",
    "color additive cosmetic",
    "fragrance allergen"
]

all_docs = []
seen_titles = set()

for term in search_terms:
    print(f"🔍 검색: {term}")
    params = urllib.parse.urlencode({
        "conditions[agencies][]": "food-and-drug-administration",
        "conditions[term]": term,
        "per_page": "10",
        "order": "newest"
    })
    url = f"https://www.federalregister.gov/api/v1/documents.json?{params}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        resp = urllib.request.urlopen(req, timeout=15)
        data = json.loads(resp.read())
        results = data.get("results", [])
        for doc in results:
            title = doc.get("title", "")
            if title in seen_titles:
                continue
            seen_titles.add(title)
            all_docs.append({
                "region": "US", "source": "federal_register",
                "title": title,
                "abstract": doc.get("abstract", ""),
                "url": doc.get("html_url", ""),
                "published_at": doc.get("publication_date", "")
            })
        print(f"  → {len(results)}건 (누적: {len(all_docs)}건)")
    except Exception as e:
        print(f"  ✗ 실패: {e}")
    time.sleep(1)

print(f"\n총 {len(all_docs)}건 규제 문서 수집\n")
if not all_docs:
    print("수집된 문서 없음. 종료.")
    sys.exit(0)

# === 2. 개별 문서별 Gemini 분석 (소량 배치) ===
batch_size = 5  # 더 작은 배치
saved_total = 0

for i in range(0, len(all_docs), batch_size):
    batch = all_docs[i:i+batch_size]
    batch_num = i // batch_size + 1
    print(f"[배치 {batch_num}] {len(batch)}건 분석 중...")

    doc_list = "\n".join([
        f"[{j+1}] {d['region']} | {d['title'][:100]} | {(d['abstract'] or '')[:150]}"
        for j, d in enumerate(batch)
    ])

    prompt = f"""다음 화장품 관련 규제 문서들을 분석하세요.

{doc_list}

반드시 JSON 배열만 출력 (설명, 마크다운 없이):
[
  {{"index": 1, "summary_ko": "한글 요약", "category": "new_rule", "affected_ingredients": ["INCI명"], "severity": "low", "keywords": ["키워드"]}}
]"""

    resp = call_gemini(prompt)
    if not resp or "error" in resp:
        err = resp.get("error", {}).get("message", "?") if resp else "no response"
        print(f"  ✗ API: {err[:80]}")
        time.sleep(DELAY)
        continue

    try:
        text = resp["candidates"][0]["content"]["parts"][0]["text"]
    except:
        print("  ✗ 응답 형식 오류")
        time.sleep(DELAY)
        continue

    analyses = robust_json_parse(text)
    if not analyses:
        print("  ✗ JSON 파싱 실패")
        time.sleep(DELAY)
        continue

    batch_saved = 0
    for analysis in analyses:
        if not isinstance(analysis, dict):
            continue
        idx = (analysis.get("index", 1)) - 1
        doc = batch[idx] if 0 <= idx < len(batch) else batch[0]
        source = f"REG_MONITOR_{doc.get('region', 'GLOBAL')}"

        restriction_base = json.dumps({
            "region": doc.get("region"), "category": analysis.get("category"),
            "severity": analysis.get("severity"), "summary": analysis.get("summary_ko"),
            "url": doc.get("url"), "keywords": analysis.get("keywords"),
            "published_at": doc.get("published_at")
        }, ensure_ascii=False)

        ingredients = analysis.get("affected_ingredients", [])
        if not ingredients:
            name = (analysis.get("summary_ko") or doc.get("title", ""))[:100]
            run_sql(
                """INSERT INTO regulation_cache (source, ingredient, inci_name, max_concentration, restriction, updated_at)
                VALUES (%s, %s, %s, %s, %s, NOW())
                ON CONFLICT (source, ingredient) DO UPDATE SET restriction=EXCLUDED.restriction, updated_at=NOW();""",
                [source, name, "", "", restriction_base]
            )
            batch_saved += 1
        else:
            for inci in ingredients:
                if not isinstance(inci, str):
                    continue
                run_sql(
                    """INSERT INTO regulation_cache (source, ingredient, inci_name, max_concentration, restriction, updated_at)
                    VALUES (%s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (source, ingredient) DO UPDATE SET inci_name=EXCLUDED.inci_name, restriction=EXCLUDED.restriction, updated_at=NOW();""",
                    [source, inci, inci, "", restriction_base]
                )
                batch_saved += 1

    saved_total += batch_saved
    print(f"  ✓ {batch_saved}건 저장 (누적: {saved_total}건)")
    time.sleep(DELAY)

print(f"\n=== 규제 모니터링 완료: {saved_total}건 저장 ===")
count = run_sql("SELECT COUNT(*) FROM regulation_cache WHERE source LIKE 'REG_MONITOR%';")
print(f"regulation_cache (REG_MONITOR): {count}건")
total = run_sql("SELECT COUNT(*) FROM regulation_cache;")
print(f"regulation_cache (전체): {total}건")
