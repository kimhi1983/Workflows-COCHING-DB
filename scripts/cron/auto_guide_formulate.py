#!/usr/bin/env python3
"""
COCHING 가이드처방 자동 생성 스크립트
- 30분마다 cron으로 실행
- 제품유형 × 피부타입 조합을 순환하며 1건씩 생성
- 결과는 AI 서버가 자동으로 이중 백업 저장
"""
import json, os, sys, time
import urllib.request
from datetime import datetime

AI_SERVER = "http://localhost:8420"

# 제품유형 목록
PRODUCT_TYPES = [
    "수분크림", "토너", "에센스", "세럼", "로션",
    "클렌저", "선크림", "샴푸", "마스크팩", "아이크림", "립밤",
]

# 피부타입 목록
SKIN_TYPES = ["건성", "지성", "복합성", "민감성", "all"]

# 상태 파일 (마지막으로 생성한 인덱스 저장)
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "guide_state.json")


def load_state():
    """마지막 실행 인덱스 로드"""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {"product_idx": 0, "skin_idx": 0}


def save_state(state):
    """인덱스 저장"""
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)


def check_server():
    """AI 서버 상태 확인"""
    try:
        req = urllib.request.Request(f"{AI_SERVER}/health")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            return data.get("status") == "ok"
    except Exception as e:
        print(f"서버 연결 실패: {e}")
        return False


def generate_guide(product_type, skin_type):
    """가이드처방 생성 API 호출"""
    payload = json.dumps({
        "product_type": product_type,
        "skin_type": skin_type,
        "use_gemini": True,
        "use_cache": True,
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{AI_SERVER}/api/v1/guide-formulate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode())
            return data
    except Exception as e:
        print(f"가이드처방 생성 실패: {e}")
        return None


def main():
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    print(f"=== 가이드처방 자동 생성 [{ts}] ===")

    # 서버 확인
    if not check_server():
        print("AI 서버 미응답 — 건너뜀")
        sys.exit(1)

    # 상태 로드 (순환 인덱스)
    state = load_state()
    p_idx = state["product_idx"] % len(PRODUCT_TYPES)
    s_idx = state["skin_idx"] % len(SKIN_TYPES)

    product_type = PRODUCT_TYPES[p_idx]
    skin_type = SKIN_TYPES[s_idx]

    print(f"생성: {product_type} / {skin_type}")

    start = time.time()
    result = generate_guide(product_type, skin_type)
    elapsed = time.time() - start

    if result:
        model = result.get("model_used", "?")
        db_count = result.get("db_ingredients_count", 0)
        print(f"완료: 모델={model}, DB원료={db_count}건, {elapsed:.1f}초")
    else:
        print(f"실패: {elapsed:.1f}초")

    # 다음 인덱스로 이동 (피부타입 순환 → 제품유형 순환)
    s_idx += 1
    if s_idx >= len(SKIN_TYPES):
        s_idx = 0
        p_idx += 1
        if p_idx >= len(PRODUCT_TYPES):
            p_idx = 0

    save_state({"product_idx": p_idx, "skin_idx": s_idx})
    print(f"다음 예정: {PRODUCT_TYPES[p_idx % len(PRODUCT_TYPES)]} / {SKIN_TYPES[s_idx % len(SKIN_TYPES)]}")
    print("===")


if __name__ == "__main__":
    main()
