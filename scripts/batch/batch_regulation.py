#!/usr/bin/env python3
"""다국가 규제 모니터링 배치 v2 — US FDA 화장품 규제 문서 수집 → Gemini 분석 → regulation_cache 저장
v2 변경사항:
  - Federal Register topics=cosmetics 필터 추가
  - 비화장품 카테고리 자동 제외 (drug_*, tobacco_*, food_*)
  - 데이터 품질 게이트 (저장 전 검증)
  - SQL 파라미터 이스케이프 강화
"""
import json, subprocess, sys, time, re, os, urllib.request, urllib.parse

GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
if not GEMINI_KEY:
    print("ERROR: GEMINI_API_KEY 환경변수를 설정하세요. (set GEMINI_API_KEY=키값)")
    sys.exit(1)
DELAY = 4

DB_ENV = {**os.environ, "PGPASSWORD": "coching2026!"}
PSQL = os.environ.get("PSQL_PATH", r"C:\Program Files\PostgreSQL\17\bin\psql.exe")
DB_CMD = [PSQL, "-h", "172.21.144.1", "-U", "coching_user", "-d", "coching_db", "-t", "-A"]
# Windows: -c 인자는 cp949 인코딩 → stdin으로 SQL 전달해야 UTF-8 유지

# 비화장품 카테고리 — 이 카테고리로 분류된 문서는 저장하지 않음
EXCLUDED_CATEGORIES = {
    "drug_withdrawal", "drug_regulation", "drug_patent",
    "drug_disposal_guidance", "drug_guidance",
    "tobacco_regulation", "tobacco_guidance",
    "food_regulation", "food_safety",
    "not_relevant", "not_applicable_to_cosmetics",
    "patent_extension", "veterinary",
}


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
        print(f"    [SQL ERR] rc={r.returncode} {r.stderr[:200]}")
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
    raw = re.sub(r'//.*$', '', raw, flags=re.MULTILINE)
    raw = re.sub(r',\s*}', '}', raw)
    raw = re.sub(r',\s*]', ']', raw)

    m = re.search(r"\[[\s\S]*\]", raw)
    target = m.group(0) if m else raw

    try:
        return json.loads(target)
    except json.JSONDecodeError:
        flat = re.sub(r'\n\s*', ' ', target)
        try:
            return json.loads(flat)
        except json.JSONDecodeError:
            pass

    results = []
    for obj_m in re.finditer(r'\{[^{}]*\}', raw):
        try:
            obj = json.loads(obj_m.group(0))
            if "summary_ko" in obj or "index" in obj:
                results.append(obj)
        except json.JSONDecodeError:
            block = obj_m.group(0)
            idx = re.search(r'"index"\s*:\s*(\d+)', block)
            summary = re.search(r'"summary_ko"\s*:\s*"([^"]*)"', block)
            cat = re.search(r'"category"\s*:\s*"([^"]*)"', block)
            sev = re.search(r'"severity"\s*:\s*"([^"]*)"', block)
            if summary:
                results.append({
                    "index": int(idx.group(1)) if idx else len(results) + 1,
                    "summary_ko": summary.group(1),
                    "category": cat.group(1) if cat else "other",
                    "affected_ingredients": [],
                    "severity": sev.group(1) if sev else "low",
                    "keywords": []
                })
    return results if results else None


def is_cosmetic_relevant(title, abstract):
    """제목/초록에서 화장품 관련성 1차 판단"""
    text = (title + " " + (abstract or "")).lower()
    # 화장품 긍정 키워드
    cosmetic_terms = ["cosmetic", "skin care", "sunscreen", "color additive",
                      "fragrance", "personal care", "beauty", "topical",
                      "dermatologic", "moisturizer", "shampoo", "soap"]
    # 비화장품 부정 키워드
    exclude_terms = ["abbreviated new drug", "anda", "nda approval",
                     "tobacco", "nicotine", "e-cigarette", "vape",
                     "veterinary", "animal drug", "food additive"]

    for term in exclude_terms:
        if term in text:
            return False
    for term in cosmetic_terms:
        if term in text:
            return True
    return False  # 불확실하면 제외


# === 1. US Federal Register 수집 ===
print("=== 다국가 규제 모니터링 배치 v2 시작 ===\n")

search_terms = [
    "cosmetic safety",
    "cosmetic ingredient regulation",
    "sunscreen monograph",
    "color additive cosmetic",
    "fragrance allergen cosmetic"
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
        added = 0
        for doc in results:
            title = doc.get("title", "")
            abstract = doc.get("abstract", "")
            if title in seen_titles:
                continue
            seen_titles.add(title)

            # ★ v2: 1차 화장품 관련성 필터
            if not is_cosmetic_relevant(title, abstract):
                continue

            all_docs.append({
                "region": "US", "source": "federal_register",
                "title": title,
                "abstract": abstract,
                "url": doc.get("html_url", ""),
                "published_at": doc.get("publication_date", "")
            })
            added += 1
        print(f"  → {added}/{len(results)}건 통과 (누적: {len(all_docs)}건)")
    except Exception as e:
        print(f"  ✗ 실패: {e}")
    time.sleep(1)

print(f"\n총 {len(all_docs)}건 화장품 관련 규제 문서 수집\n")
if not all_docs:
    print("수집된 문서 없음. 종료.")
    sys.exit(0)

# === 2. Gemini 분석 (소량 배치) ===
batch_size = 5
saved_total = 0
skipped_total = 0

for i in range(0, len(all_docs), batch_size):
    batch = all_docs[i:i + batch_size]
    batch_num = i // batch_size + 1
    print(f"[배치 {batch_num}] {len(batch)}건 분석 중...")

    doc_list = "\n".join([
        f"[{j + 1}] {d['region']} | {d['title'][:100]} | {(d['abstract'] or '')[:150]}"
        for j, d in enumerate(batch)
    ])

    prompt = f"""다음 화장품 관련 규제 문서들을 분석하세요.
화장품과 직접 관련 없는 문서는 category를 "not_relevant"로 표시하세요.

{doc_list}

반드시 JSON 배열만 출력 (설명, 마크다운 없이):
[
  {{"index": 1, "summary_ko": "한글 요약", "category": "new_rule", "affected_ingredients": ["INCI명"], "severity": "low", "keywords": ["키워드"]}}
]

category 옵션: new_rule, guidance, amendment, enforcement_action, regulatory_notice, information_collection, not_relevant"""

    resp = call_gemini(prompt)
    if not resp or "error" in resp:
        err = resp.get("error", {}).get("message", "?") if resp else "no response"
        print(f"  ✗ API: {err[:80]}")
        time.sleep(DELAY)
        continue

    try:
        text = resp["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError):
        print("  ✗ 응답 형식 오류")
        time.sleep(DELAY)
        continue

    analyses = robust_json_parse(text)
    if not analyses:
        print("  ✗ JSON 파싱 실패")
        time.sleep(DELAY)
        continue

    batch_saved = 0
    batch_skipped = 0
    for analysis in analyses:
        if not isinstance(analysis, dict):
            continue

        category = analysis.get("category", "other")

        # ★ v2: 비화장품 카테고리 제외
        if category in EXCLUDED_CATEGORIES:
            batch_skipped += 1
            continue

        idx = (analysis.get("index", 1)) - 1
        doc = batch[idx] if 0 <= idx < len(batch) else batch[0]
        source = f"REG_MONITOR_{doc.get('region', 'GLOBAL')}"

        restriction_base = json.dumps({
            "region": doc.get("region"),
            "category": category,
            "severity": analysis.get("severity"),
            "summary": analysis.get("summary_ko"),
            "url": doc.get("url"),
            "keywords": analysis.get("keywords"),
            "published_at": doc.get("published_at")
        }, ensure_ascii=False)

        ingredients = analysis.get("affected_ingredients", [])
        if not ingredients:
            name = (analysis.get("summary_ko") or doc.get("title", ""))[:100]
            run_sql_params(
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
                run_sql_params(
                    """INSERT INTO regulation_cache (source, ingredient, inci_name, max_concentration, restriction, updated_at)
                    VALUES (%s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (source, ingredient) DO UPDATE SET inci_name=EXCLUDED.inci_name, restriction=EXCLUDED.restriction, updated_at=NOW();""",
                    [source, inci, inci, "", restriction_base]
                )
                batch_saved += 1

    saved_total += batch_saved
    skipped_total += batch_skipped
    print(f"  ✓ 저장 {batch_saved}건 | 제외 {batch_skipped}건 (누적: {saved_total}건)")
    time.sleep(DELAY)

print(f"\n=== 규제 모니터링 v2 완료 ===")
print(f"저장: {saved_total}건 | 제외(비화장품): {skipped_total}건")
count = run_sql("SELECT COUNT(*) FROM regulation_cache WHERE source LIKE 'REG_MONITOR%';")
print(f"regulation_cache (REG_MONITOR): {count}건")
total = run_sql("SELECT COUNT(*) FROM regulation_cache;")
print(f"regulation_cache (전체): {total}건")
