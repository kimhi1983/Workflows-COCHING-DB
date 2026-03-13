#!/usr/bin/env python3
"""Ollama Qwen 2.5 14B 연결 테스트 + 화장품 원료 분류 샘플"""
import json, urllib.request, sys, io, time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

OLLAMA_URL = "http://localhost:11434"
MODEL = "qwen2.5:14b"

# 1. 서버 확인
print("1. Ollama 서버 확인...")
try:
    resp = urllib.request.urlopen(f"{OLLAMA_URL}/", timeout=5)
    print(f"   OK: {resp.read().decode()}")
except Exception as e:
    print(f"   FAIL: {e}")
    sys.exit(1)

# 2. 모델 목록
print("\n2. 설치된 모델:")
resp = urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=5)
data = json.loads(resp.read())
for m in data.get("models", []):
    size_gb = m.get("size", 0) / 1024**3
    print(f"   {m['name']} ({size_gb:.1f}GB)")

# 3. 실제 분류 테스트
print("\n3. 화장품 원료 분류 테스트 (10개)...")
test_ingredients = [
    "Glycerin", "Niacinamide", "Retinol", "Zinc Oxide",
    "Sodium Lauryl Sulfate", "Hyaluronic Acid", "Tocopherol",
    "Phenoxyethanol", "Titanium Dioxide", "Dimethicone"
]

prompt = f"""다음 화장품 원료 목록의 주요 기능을 분류하세요.

{chr(10).join(['- ' + i for i in test_ingredients])}

반드시 JSON 배열만 출력:
[
  {{"inci": "INCI명", "type": "HUMECTANT"}}
]

type: HUMECTANT, EMOLLIENT, EMULSIFIER, SURFACTANT, PRESERVATIVE,
      ANTIOXIDANT, UV_FILTER, THICKENER, FILM_FORMER, CHELATING,
      PH_ADJUSTER, COLORANT, FRAGRANCE, ACTIVE, OTHER"""

body = json.dumps({
    "model": MODEL, "prompt": prompt, "stream": False,
    "options": {"temperature": 0.1, "num_predict": 1024}
}).encode()

req = urllib.request.Request(f"{OLLAMA_URL}/api/generate", data=body,
                              headers={"Content-Type": "application/json"}, method="POST")
t0 = time.time()
resp = urllib.request.urlopen(req, timeout=120)
elapsed = time.time() - t0

result = json.loads(resp.read())
text = result.get("response", "")
print(f"   응답 시간: {elapsed:.1f}초")
print(f"   응답:\n{text}")
print(f"\n완료! tokens/sec: {result.get('eval_count', 0) / max(result.get('eval_duration', 1) / 1e9, 0.001):.1f}")
