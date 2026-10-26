# OCR (Peppercorn v3): dịch vụ chạy theo lô

**Trạng thái: đã chạy thử, hoạt động trên vLLM 0.32.0 thuần** (không cần plugin `vllm_student` của v1/v2).

- Checkpoint: `runs/v3-main/d48sh-muon` (bước 126000, `Qwen3_5ForConditionalGeneration`, ~0.3B, `model.safetensors` 623 MB).
  Chưa biết bản `ema/` hay bản gốc mới là bản cuối chính thức: đã dùng bản gốc theo chỉ định của người dùng.
- `models/ocr-peppercorn-v3-d48sh-muon/` chỉ chứa phần phục vụ (weights, config, tokenizer, processor, `vocab_map.json`),
  hard link tới checkpoint gốc, **không** có `trainer_state.pt` (3 GB) hay log huấn luyện. Thư mục `models/` bị `.gitignore` chặn.
- Cờ theo `peppercorn-v3/bench/infer.py` (kind "qwen35"): một ảnh mỗi request, thinking tắt, `--no-enable-prefix-caching`,
  `--mm-processor-cache-gb 0`. OCR không cần prefix cache vì mỗi trang là một ảnh khác nhau; vLLM vẫn cấp KV cache cho
  phần giải mã (khoảng 2.6 GiB, 308k token).
- Thử với một trang tiếng Việt công khai (2048 px, 2894 token vào, 850 token ra): 2.7 s, kết quả tiếng Việt đúng dấu,
  gọi lần hai cho cùng kết quả (greedy). Chưa đo chất lượng hay thông lượng nhiều trang: đó là việc của bên Peppercorn.

Cách dùng: một trang một request tới `/v1/chat/completions` (chỉ có ảnh trang, không kèm văn bản), `temperature 0`,
ảnh thu nhỏ về cạnh dài tối đa 2048 px phía client. Chạy theo lô: `scripts/up.sh ocr` khi có tệp scan, `scripts/down.sh ocr` khi xong.

**Dữ liệu nội bộ:** checkpoint được huấn luyện từ tài liệu nội bộ của QK. Giữ cục bộ, không upload, không commit, không push
(kể cả khi repo này có remote). `.gitignore` chặn `*.safetensors`, `*.pt`, `*.bin` và `models/`.
