"""Real-stack check, run inside a GPU container with --network host: adapter vs transformers (last-token pooling, L2)."""
import json, sys, time, urllib.request, torch
from transformers import AutoTokenizer, AutoModel
URL = sys.argv[1]; D = "/models/embed"
tok = AutoTokenizer.from_pretrained(D); m = AutoModel.from_pretrained(D, dtype=torch.bfloat16).cuda().eval()
texts = ["Thông tư quy định về quản lý kho dữ liệu của cơ quan nhà nước.",
         "Hà Nội là thủ đô của Việt Nam, nằm ở đồng bằng sông Hồng.", "def add(a, b):\n    return a + b",
         "Văn bản số 12/2024 ban hành ngày 05/03/2024 về hướng dẫn thi hành.", "The quick brown fox jumps over the lazy dog.",
         "Kho tang tai lieu khong dau de kiem tra.", " ".join(["quản lý hồ sơ văn bản"] * 150)]
def post(path, body):
    return json.loads(urllib.request.urlopen(urllib.request.Request(URL + path, json.dumps(body).encode(), {"Content-Type": "application/json"}), timeout=600).read())
def ref(t):
    x = tok(t, return_tensors="pt", truncation=True, max_length=32768).to("cuda")
    with torch.no_grad(): h = m(**x).last_hidden_state[0, -1].float()
    return torch.nn.functional.normalize(h, dim=0).cpu()
out = post("/api/v1/embed", {"texts": texts})
print("dimension", out["dimension"], "model", out["model"])
cos = [float(torch.dot(ref(t), torch.tensor(e))) for t, e in zip(texts, out["embeddings"])]
print("cosine adapter vs transformers:", [round(c, 5) for c in cos], "min", round(min(cos), 5))
q = post("/api/v1/embed", {"texts": ["quy trình tiếp nhận hồ sơ"], "input_type": "query"})["embeddings"][0]
qref = ref("Instruct: Given a web search query, retrieve relevant passages that answer the query\nQuery: quy trình tiếp nhận hồ sơ")
print("query-path cosine", round(float(torch.dot(qref, torch.tensor(q))), 5))
big = " ".join(["quản lý hồ sơ văn bản nhà nước"] * 5200)
n = len(tok(big)["input_ids"]); t0 = time.time(); e = post("/api/v1/embed", {"texts": [big]})["embeddings"][0]
print(f"one text of {n} tokens: {time.time()-t0:.2f} s; cosine vs transformers {float(torch.dot(ref(big), torch.tensor(e))):.5f}")
mid = " ".join(["quản lý hồ sơ văn bản"] * 200); n2 = len(tok(mid)["input_ids"]); t0 = time.time()
post("/api/v1/embed", {"texts": [mid + str(i) for i in range(32)]}); print(f"batch 32 x {n2} tokens: {time.time()-t0:.2f} s")
