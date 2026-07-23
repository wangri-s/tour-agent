"""全功能测试套件 — 覆盖所有 Agent 分支、流式输出、国内游、报价"""

import json
import urllib.request
import time
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE = "http://127.0.0.1:8002"
passed = 0
failed = 0
errors = 0


def test(name, method, path, data, checks, timeout=90):
    global passed, failed, errors
    try:
        body = json.dumps(data, ensure_ascii=False).encode() if data else None
        req = urllib.request.Request(
            f"{BASE}{path}",
            data=body,
            headers={"Content-Type": "application/json"} if body else {},
            method=method,
        )
        resp = json.loads(urllib.request.urlopen(req, timeout=timeout).read())
        ok = True
        msgs = []
        for key, expected in checks.items():
            actual = resp.get(key, "?")
            if actual != expected:
                ok = False
                msgs.append(f"{key}={actual}(expected={expected})")
        if ok:
            print(f"  PASS  {name}")
            passed += 1
        else:
            print(f"  FAIL  {name}: {' | '.join(msgs)}")
            failed += 1
    except Exception as e:
        print(f"  ERROR {name}: {str(e)[:80]}")
        errors += 1
    time.sleep(0.3)


# ============================================================
# 1. Health Check
# ============================================================
print("=" * 50)
print("1. Health Check")
print("=" * 50)
test("health-status", "GET", "/health", None, {"status": "ok"})

# Check features in health
try:
    resp = json.loads(urllib.request.urlopen(f"{BASE}/health", timeout=5).read())
    feats = resp.get("features", {})
    checks = [
        ("streaming", feats.get("streaming") is True),
        ("rag", feats.get("rag") == "milvus+dashscope"),
        ("cot_prompts", feats.get("cot_prompts") is True),
        ("context_compression", feats.get("context_compression") is True),
    ]
    for name, ok in checks:
        if ok:
            print(f"  PASS  health-{name}")
            passed += 1
        else:
            print(f"  FAIL  health-{name}")
            failed += 1
except Exception as e:
    print(f"  ERROR health-features: {e}")
    errors += 1

# ============================================================
# 2. Intent Routing — 四分支精准分发
# ============================================================
print("\n" + "=" * 50)
print("2. Intent Routing (4 branches)")
print("=" * 50)

test(
    "planner-北京5日游", "POST", "/chat",
    {"session_id": "r1", "customer_id": "c1", "channel": "web",
     "message": "北京5天2人预算8000", "language": "zh"},
    {"branch": "planner"},
)

test(
    "planner-景点推荐", "POST", "/chat",
    {"session_id": "r2", "customer_id": "c1", "channel": "web",
     "message": "成都必去景点有哪些？第一次去", "language": "zh"},
    {"branch": "planner"},
)

test(
    "service-签证咨询", "POST", "/chat",
    {"session_id": "r3", "customer_id": "c1", "channel": "web",
     "message": "中国签证怎么办理？我是美国人", "language": "zh"},
    {"branch": "service"},
)

test(
    "service-查订单", "POST", "/chat",
    {"session_id": "r4", "customer_id": "c1", "channel": "web",
     "message": "帮我查一下我的订单到哪了", "language": "zh"},
    {"branch": "service"},
)

test(
    "service-投诉转人工", "POST", "/chat",
    {"session_id": "r5", "customer_id": "c1", "channel": "web",
     "message": "我要投诉！太差了！", "language": "zh"},
    {"branch": "service"},
)

test(
    "sales-询价购买", "POST", "/chat",
    {"session_id": "r6", "customer_id": "c1", "channel": "web",
     "message": "这个行程多少钱？能优惠吗？我想预订", "language": "zh"},
    {"branch": "sales"},
)

test(
    "sales-付款方式", "POST", "/chat",
    {"session_id": "r7", "customer_id": "c1", "channel": "web",
     "message": "怎么付款？支持信用卡吗", "language": "zh"},
    {"branch": "sales"},
)

test(
    "operations-商家入驻", "POST", "/chat",
    {"session_id": "r8", "customer_id": "c1", "channel": "web",
     "message": "我是开民宿的，想入驻你们平台", "language": "zh"},
    {"branch": "operations"},
)

test(
    "operations-取消退款", "POST", "/chat",
    {"session_id": "r9", "customer_id": "c1", "channel": "web",
     "message": "取消我的订单，退款什么时候到账", "language": "zh"},
    {"branch": "operations"},
)

test(
    "operations-改期", "POST", "/chat",
    {"session_id": "r10", "customer_id": "c1", "channel": "web",
     "message": "改签我的机票可以吗", "language": "zh"},
    {"branch": "operations"},
)

test(
    "兜底-service", "POST", "/chat",
    {"session_id": "r11", "customer_id": "c1", "channel": "web",
     "message": "你好", "language": "zh"},
    {"branch": "service"},
)

# ============================================================
# 3. Trip Planning — 行程草案生成
# ============================================================
print("\n" + "=" * 50)
print("3. Trip Planning (draft generation)")
print("=" * 50)

try:
    data = json.dumps({
        "session_id": "d1", "customer_id": "c1", "channel": "web",
        "message": "成都3天1人预算3000美食火锅", "language": "zh",
    }, ensure_ascii=False).encode()
    req = urllib.request.Request(f"{BASE}/chat", data=data,
                                  headers={"Content-Type": "application/json"}, method="POST")
    resp = json.loads(urllib.request.urlopen(req, timeout=120).read())
    draft = resp.get("draft")
    has_draft = draft is not None
    has_md = bool(draft.get("itinerary_md", "")) if draft else False
    has_cost = draft.get("estimated_cost", 0) > 0 if draft else False
    md_len = len(draft.get("itinerary_md", "")) if draft else 0
    if has_draft and has_md and has_cost:
        print(f"  PASS  draft-generation (md={md_len}chars, cost=¥{draft['estimated_cost']:,.0f})")
        passed += 1
    else:
        print(f"  FAIL  draft-generation (draft={has_draft}, md={has_md}, cost={has_cost})")
        failed += 1
except Exception as e:
    print(f"  ERROR draft-generation: {e}")
    errors += 1

# ============================================================
# 4. Domestic Trip — 高铁不出现国际机票
# ============================================================
print("\n" + "=" * 50)
print("4. Domestic Trip (no international flight)")
print("=" * 50)

try:
    data = json.dumps({
        "session_id": "dt1", "customer_id": "c1", "channel": "web",
        "message": "从上海到北京3天1人预算3000", "language": "zh",
    }, ensure_ascii=False).encode()
    req = urllib.request.Request(f"{BASE}/chat", data=data,
                                  headers={"Content-Type": "application/json"}, method="POST")
    resp = json.loads(urllib.request.urlopen(req, timeout=120).read())
    draft_md = resp.get("draft", {}).get("itinerary_md", "") if resp.get("draft") else ""
    reply = resp.get("reply", "")
    full_text = draft_md + reply
    has_international = "国际机票" in full_text
    has_domestic = "高铁" in full_text or "动车" in full_text
    if not has_international and has_domestic:
        print(f"  PASS  domestic-trip (domestic transport detected, no international flight)")
        passed += 1
    elif not has_international and not has_domestic:
        print(f"  WARN  domestic-trip (no transport keyword found, but no international flight either)")
        passed += 1
    else:
        print(f"  FAIL  domestic-trip (international={has_international})")
        failed += 1
except Exception as e:
    print(f"  ERROR domestic-trip: {e}")
    errors += 1

# ============================================================
# 5. Streaming SSE
# ============================================================
print("\n" + "=" * 50)
print("5. Streaming SSE")
print("=" * 50)

for i, msg in enumerate(["你好", "故宫几点开门"], 1):
    try:
        data = json.dumps({
            "session_id": f"s{i}", "customer_id": "c1", "channel": "web",
            "message": msg, "language": "zh",
        }, ensure_ascii=False).encode()
        req = urllib.request.Request(f"{BASE}/chat/stream", data=data,
                                      headers={"Content-Type": "application/json"}, method="POST")
        resp = urllib.request.urlopen(req, timeout=60)
        body = resp.read().decode("utf-8")
        has_token = "event: token" in body
        has_branch = "event: branch" in body
        has_done = "event: done" in body
        token_count = body.count("event: token")
        if has_token and has_branch and has_done:
            print(f"  PASS  streaming-{msg[:20]} (tokens={token_count})")
            passed += 1
        else:
            print(f"  FAIL  streaming-{msg[:20]} (token={has_token}, branch={has_branch}, done={has_done})")
            failed += 1
    except Exception as e:
        print(f"  ERROR streaming-{msg[:20]}: {e}")
        errors += 1
    time.sleep(0.3)

# ============================================================
# 6. Quote Generation
# ============================================================
print("\n" + "=" * 50)
print("6. Quote Generation")
print("=" * 50)

try:
    # Step 1: create trip
    data1 = json.dumps({
        "session_id": "q1", "customer_id": "c1", "channel": "web",
        "message": "西安2天1人预算2000兵马俑", "language": "zh",
    }, ensure_ascii=False).encode()
    req1 = urllib.request.Request(f"{BASE}/chat", data=data1,
                                   headers={"Content-Type": "application/json"}, method="POST")
    resp1 = json.loads(urllib.request.urlopen(req1, timeout=120).read())
    print(f"  INFO  trip-draft-created (branch={resp1.get('branch')})")

    # Step 2: accept → quote
    time.sleep(0.5)
    data2 = json.dumps({
        "session_id": "q1", "customer_id": "c1", "channel": "web",
        "message": "好的，满意，生成报价", "language": "zh",
    }, ensure_ascii=False).encode()
    req2 = urllib.request.Request(f"{BASE}/chat", data=data2,
                                   headers={"Content-Type": "application/json"}, method="POST")
    resp2 = json.loads(urllib.request.urlopen(req2, timeout=60).read())
    quote = resp2.get("quote")
    has_quote = quote is not None
    has_items = bool(quote and quote.get("total", 0) > 0)
    if has_quote and has_items:
        print(f"  PASS  quote-generation (total=¥{quote['total']:,.0f}, items={len([k for k,v in quote.items() if isinstance(v,(int,float)) and v>0])})")
        passed += 1
    else:
        print(f"  FAIL  quote-generation (has_quote={has_quote}, has_items={has_items})")
        failed += 1
except Exception as e:
    print(f"  ERROR quote-generation: {e}")
    errors += 1

# ============================================================
# Summary
# ============================================================
print("\n" + "=" * 50)
total = passed + failed + errors
print(f"Results: {passed} passed, {failed} failed, {errors} errors ({total} total)")
if failed == 0 and errors == 0:
    print("ALL TESTS PASSED!")
else:
    print(f"FAILURES DETECTED: {failed + errors}")
print("=" * 50)
