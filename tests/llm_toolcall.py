import json, urllib.request, sys, time
URL = "http://127.0.0.1:8201"
def post(body):
    req = urllib.request.Request(URL + "/v1/chat/completions", json.dumps(body).encode(), {"Content-Type": "application/json"})
    try:
        return json.loads(urllib.request.urlopen(req, timeout=300).read())
    except urllib.error.HTTPError as e:
        return {"HTTP_ERROR": e.code, "body": e.read().decode()[:400]}
tools = [
 {"type": "function", "function": {"name": "search_docs", "description": "Search the document index", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
 {"type": "function", "function": {"name": "read_doc", "description": "Read a document by id", "parameters": {"type": "object", "properties": {"doc_id": {"type": "string"}}, "required": ["doc_id"]}}},
]
sysmsg = "Ban la tro ly tra cuu van ban. Hay goi tool de tra cuu, co the goi nhieu tool song song."
q = "Tim giup toi thong tu ve quan ly kho tang va doc van ban so 12/2024; goi ca hai tool cung luc."
def show(tag, r):
    if "HTTP_ERROR" in r: print(tag, "HTTP", r); return None
    m = r["choices"][0]["message"]
    print(f"--- {tag}: finish={r['choices'][0]['finish_reason']} usage={r['usage']}")
    print("  reasoning_content:", (m.get("reasoning_content") or m.get("reasoning") or "")[:150].replace("\n", " "))
    print("  content:", (m.get("content") or "")[:150].replace("\n", " "))
    print("  tool_calls:", [(c["function"]["name"], c["function"]["arguments"]) for c in (m.get("tool_calls") or [])])
    return m
base = {"model": "qwen3.6-35b-a3b", "tools": tools, "temperature": 0.6, "max_tokens": 1500}
msgs = [{"role": "system", "content": sysmsg}, {"role": "user", "content": q}]
# A: thinking on (default)
a = post(dict(base, messages=msgs)); ma = show("A thinking on", a)
# B: thinking off
b = post(dict(base, messages=msgs, chat_template_kwargs={"enable_thinking": False})); mb = show("B thinking off", b)
# C: summary call without tools, thinking off
c = post({"model": "qwen3.6-35b-a3b", "messages": [{"role": "user", "content": "Tom tat 1 cau: kho du lieu la gi?"}], "max_tokens": 200, "chat_template_kwargs": {"enable_thinking": False}}); show("C no tools, thinking off", c)
# D: second turn with history, including tool results, check prompt cache + whether old reasoning is kept
if ma and ma.get("tool_calls"):
    hist = msgs + [{"role": "assistant", "content": ma.get("content") or "", "tool_calls": ma["tool_calls"],
                    **({"reasoning_content": ma["reasoning_content"]} if ma.get("reasoning_content") else {})}]
    for tc in ma["tool_calls"]:
        hist.append({"role": "tool", "tool_call_id": tc["id"], "content": "Ket qua: Thong tu 03/2024 quy dinh quan ly kho tang; Van ban 12/2024 ban hanh ngay 05/03/2024."})
    d = post(dict(base, messages=hist, extra_body=None) if False else dict(base, messages=hist)); show("D second turn (with reasoning in history)", d)
    hist2 = [dict(m) for m in hist]
    for m in hist2:
        m.pop("reasoning_content", None)
    d2 = post(dict(base, messages=hist2)); show("D2 second turn (reasoning stripped)", d2)
