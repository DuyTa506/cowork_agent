# qk3-serving

Phục vụ mô hình cho agent QK3 trên một GPU (RTX PRO 6000 Blackwell, 95.6 GiB): LLM, embedding, rerank và OCR.
Chạy hoàn toàn offline: mọi model nạp từ đường dẫn cục bộ, không kéo gì từ Internet lúc chạy (cần sẵn image
`vllm/vllm-openai:v0.32.0`).

| dịch vụ | model | cổng | giao thức |
|---|---|---:|---|
| LLM | Qwen3.6-35B-A3B NVFP4 (`/opt/intramind/models/llm/...-v1`), tên `qwen3.6-35b-a3b` | 8201 | OpenAI `/v1/chat/completions`, tool calling `qwen3_coder`, reasoning `qwen3`, thinking bật |
| embedding | `microsoft/harrier-oss-v1-270m`, 640 chiều, 32,768 token | 8204 (adapter) | `POST /api/v1/embed {texts, input_type}` |
| rerank | `BAAI/bge-reranker-v2-m3`, 8,192 token | 8204 (adapter) | `POST /api/v1/rerank {query, documents, top_k}` |
| OCR (theo lô) | Peppercorn v3 (`d48sh-muon`), tên `peppercorn-v3` | 8205 | OpenAI `/v1/chat/completions`, ảnh trang |

Cổng 8202, 8203 là backend vLLM của embedding và rerank (chỉ nghe trên 127.0.0.1). Adapter (`adapter/app.py`) nói đúng hợp đồng
của tầng `mta-ai-serving-intramind` :5003, nên QK3 không phải đổi code.

## Chạy

```bash
cp .env.example .env        # sửa đường dẫn, cổng, tỉ lệ GPU nếu cần
scripts/up.sh all           # llm -> embedding -> rerank -> adapter (thứ tự quan trọng: vLLM kiểm bộ nhớ trống lúc khởi động)
scripts/up.sh ocr           # OCR chạy riêng, theo lô; cần OCR_DIR trong .env (xem ocr/README.md)
scripts/health.sh           # tình trạng từng dịch vụ + bộ nhớ GPU
scripts/down.sh all         # tắt hết (chỉ container qk3-*, không đụng container khác)
scripts/selftest.sh         # kiểm tra hợp đồng adapter, không cần GPU
```

Cần quyền docker (script tự dùng `sg docker` nếu shell hiện tại chưa thuộc nhóm docker). LLM mất khoảng 5-6 phút để lên.
Mặc định chỉ nghe trên `127.0.0.1`; đổi `BIND_ADDR=0.0.0.0` trong `.env` nếu QK3 chạy ở máy khác, và chỉ làm vậy trong mạng nội bộ tin cậy
vì chưa đặt API key.

## Bộ nhớ GPU (đo thật bằng nvidia-smi)

| thành phần | MiB | GiB | cấu hình |
|---|---:|---:|---|
| LLM | 78,026 | 76.2 | `LLM_GPU_UTIL=0.78`, 3.37M token KV, 25.7 phiên 131k đồng thời |
| embedding | 4,146 | 4.05 | `EMBED_GPU_UTIL=0.04` |
| rerank | 2,564 | 2.5 | `RERANK_GPU_UTIL=0.04` |
| OCR (khi bật) | ~4,140 | ~4.0 | `OCR_GPU_UTIL=0.05`, 308k token KV |
| **tổng khi bật cả bốn** | **88,608** | **86.5** | còn trống khoảng 9.3 GiB |

- Độ dài tối đa không làm tăng bộ nhớ: embedding 32,768 token và 4,096 token chiếm gần như như nhau (bộ nhớ do
  `*_GPU_UTIL` quyết định, không do độ dài).
- Sau khi chạy test nặng (văn bản ~41k token, batch 32 x 1,200 token) bộ nhớ tăng thêm khoảng 1 GiB, nên giữ đệm.
- Muốn LLM nhẹ hơn: `LLM_GPU_UTIL=0.65` còn 18.6 phiên 131k (KV 2.44M token), 0.50 còn 10.4 phiên.

## Điền vào QK3 (Quản trị → Hệ thống)

| mục | giá trị (thay `HOST` bằng địa chỉ máy này) |
|---|---|
| LLM base_url | `http://HOST:8201/v1` |
| LLM model | `qwen3.6-35b-a3b` |
| Embedding | loại `intramind`, địa chỉ `http://HOST:8204` (route `/api/v1/embed`) |
| Rerank | địa chỉ `http://HOST:8204` (route `/api/v1/rerank`) |
| OCR base_url / model | `http://HOST:8205/v1` / `peppercorn-v3` |

## Lưu ý đã kiểm

- vLLM 0.32 trả suy luận ở trường **`reasoning`** (không phải `reasoning_content`); harness của QK3 đọc được cả hai.
- Tool calling song song hoạt động; `chat_template_kwargs.enable_thinking=false` chạy được, không báo lỗi 400.
- Thinking bật làm lượt hai tốn nhiều token suy luận (cả hai lần thử với `max_tokens=1500` đều hết hạn mức); để `max_tokens` đủ lớn.
- Prompt ngắn hơn một khối cache (2176 token) không được prefix cache với model hybrid này. `--prefix-match-unit 16`
  (đặt trong `LLM_EXTRA_ARGS`) cho cache mịn hơn nhưng mới kiểm trên cấu hình khác và có cái giá riêng (ít phiên nhàn rỗi được giữ lại hơn).
- Embedding qua adapter so với transformers: cosine >= 0.99988; reranker khớp điểm transformers (lệch tối đa 0.0002).
  Adapter cắt (không từ chối) khi vượt giới hạn, và trả `{"results": []}` ngay khi không có tài liệu.
- Adapter không hiện thực header `X-Intramind-Attempt-ID` / `Expected-Revision` của tầng intramind.

## Chưa làm

- Offload KV sang RAM (`--kv-offloading-size`): chưa bật vì chưa biết số phiên nhàn rỗi thật; cần tầng RAM chứa trọn working set (13.3 KB mỗi token).
- Soak test dài; bge-reranker chưa nằm trong `/opt/intramind/models/rerank` (chạy `scripts/stage_rerank.sh` một lần để chép vào).
- Chưa đo chất lượng OCR và thông lượng nhiều trang.

Nguồn cấu hình LLM: github.com/DuyTa506/sm120-vllm-kernels (`CONFIG=next`); các file vá nằm trong `vllm_patches/`.
Dữ liệu nội bộ: không commit weights hay checkpoint (xem `.gitignore`); repo này chưa có remote.
