import json, time, sys, urllib.request
URL = sys.argv[1]
def post(path, body):
    return json.loads(urllib.request.urlopen(urllib.request.Request(URL + path, json.dumps(body).encode(), {"Content-Type": "application/json"}), timeout=600).read())
q = "quy trình tiếp nhận hồ sơ"
docs = ["Hồ sơ được tiếp nhận tại bộ phận một cửa và cấp biên nhận cho người nộp.", "Hà Nội là thủ đô của Việt Nam.",
        "Thông tư hướng dẫn quản lý kho dữ liệu.", "Công dân nộp hồ sơ trực tuyến qua cổng dịch vụ công, cơ quan xác nhận đã nhận."]
r = post("/api/v1/rerank", {"query": q, "documents": docs, "top_k": 3}); print("rerank top3:", r["results"])
assert r["results"][0]["index"] == 0 and len(r["results"]) == 3
t0 = time.time(); r = post("/api/v1/rerank", {"query": q, "documents": (docs * 8)[:30]}); print("30 pairs: %.3f s, %d results" % (time.time() - t0, len(r["results"])))
long_doc = " ".join(["quản lý hồ sơ văn bản nhà nước"] * 1500)
t0 = time.time(); r = post("/api/v1/rerank", {"query": q, "documents": [long_doc, docs[0]]}); print("long doc (about 8k tokens, truncated by the model limit): %.3f s" % (time.time() - t0), r["results"])
print("empty:", post("/api/v1/rerank", {"query": q, "documents": []}))
