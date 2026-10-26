"""What can be configured: the catalogue of settings sections and their fields.

This module is data, not behaviour. Adding a configurable thing means adding a `Field` here; storage, validation, secret
handling, the API and the admin UI all derive from this catalogue.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.core import config


@dataclass(frozen=True)
class Field:
    """One configurable value.

    Attributes:
        name: Key in the stored record and in API payloads.
        label: Vietnamese label for the admin UI.
        kind: ``str | int | float | bool | choice | url``. A ``url`` must be http(s) and is checked for being private.
        default: Value (or callable returning it) used until an administrator saves one; usually read from the environment.
        secret: Stored encrypted and never returned by the API (only whether it is set).
        verbatim: Keep the text exactly as typed (no stripping); for prefixes where whitespace is meaningful.
    """

    name: str
    label: str
    kind: str = "str"
    default: Callable[[], Any] | Any = ""
    secret: bool = False
    choices: tuple[str, ...] = ()
    minimum: float | None = None
    maximum: float | None = None
    help: str = ""
    verbatim: bool = False

    def default_value(self) -> Any:
        """The default, evaluated now (environment-backed defaults are read lazily so tests can change the environment)."""
        return self.default() if callable(self.default) else self.default


@dataclass(frozen=True)
class Section:
    """A group of related fields, edited and tested together (for example everything about the embedding model).

    ``sends_document_text`` marks sections whose endpoints receive document content; an endpoint outside the private network
    in such a section needs the administrator's explicit confirmation before it is accepted.
    """

    key: str
    label: str
    description: str
    fields: tuple[Field, ...]
    sends_document_text: bool = False
    used_by: str = ""

    def field(self, name: str) -> Field:
        """The field called `name`; raises `KeyError` for an unknown one."""
        for candidate in self.fields:
            if candidate.name == name:
                return candidate
        raise KeyError(name)


SECTIONS: dict[str, Section] = {
    section.key: section
    for section in (
        Section(
            "llm", "Mô hình hội thoại (LLM)",
            "Mô hình trả lời, tóm tắt và soạn thảo của trợ lý. Máy chủ tương thích OpenAI (vLLM, SGLang...).",
            (
                Field("base_url", "Địa chỉ máy chủ", "url", lambda: config.LLM_BASE_URL, help="Ví dụ http://10.0.0.5:8000/v1"),
                Field("model", "Tên model", "str", lambda: config.LLM_MODEL),
                Field("api_key", "API key", "str", lambda: config.LLM_API_KEY, secret=True, help="Để trống nếu máy chủ không yêu cầu."),
                Field("context_window", "Cửa sổ ngữ cảnh (token)", "int", 131072, minimum=4096, maximum=2_000_000,
                      help="Quyết định ngưỡng văn bản dài phải tóm tắt theo từng mục."),
                Field("max_output_tokens", "Số token trả lời tối đa", "int", 4096, minimum=256, maximum=131072,
                      help="Tính cả phần suy nghĩ. Model đang suy nghĩ dễ dùng hết trần trước khi gọi công cụ."),
                Field("temperature", "Temperature", "float", 0.2, minimum=0, maximum=2),
                Field("thinking", "Suy nghĩ trước khi trả lời", "bool", True,
                      help="Bật: trợ lý suy nghĩ rồi mới gọi công cụ (chậm; Qwen có thể lặp trong phần suy nghĩ và hết token). "
                           "Tắt: gọi công cụ và trả lời ngay. Tóm tắt văn bản luôn tắt suy nghĩ. Lượt chat sau khi lưu dùng cấu hình mới."),
            ),
            sends_document_text=True, used_by="Trợ lý AI: hỏi đáp, tóm tắt, soạn thảo",
        ),
        Section(
            "embedding", "Embedding",
            "Model biến đoạn văn bản thành vector để tìm theo ngữ nghĩa. Đổi model hoặc số chiều thì phải lập chỉ mục lại toàn bộ kho.",
            (
                Field("provider", "Loại", "choice", lambda: "openai" if config.EMBEDDING_BASE_URL else "none",
                      choices=("openai", "intramind", "hash", "none"),
                      help="openai = máy chủ /v1/embeddings; intramind = tầng serving /api/v1/embed (tự áp tiền tố câu hỏi); hash = chỉ để thử đường ống, không có ngữ nghĩa; none = chưa cấu hình."),
                Field("base_url", "Địa chỉ máy chủ", "url", lambda: config.EMBEDDING_BASE_URL),
                Field("model", "Tên model", "str", lambda: config.EMBEDDING_MODEL),
                Field("api_key", "API key", "str", "", secret=True),
                Field("dim", "Số chiều vector", "int", lambda: config.EMBEDDING_DIM, minimum=0, maximum=8192),
                Field("query_prefix", "Tiền tố câu hỏi", "str", lambda: config.EMBEDDING_QUERY_PREFIX, verbatim=True,
                      help="Một số model cần chỉ dẫn đứng trước câu hỏi, ví dụ 'Instruct: ...\\nQuery: '."),
                Field("doc_prefix", "Tiền tố đoạn văn bản", "str", "", verbatim=True),
                Field("batch_size", "Cỡ lô", "int", 32, minimum=1, maximum=512),
            ),
            sends_document_text=True, used_by="Kho văn bản (lập chỉ mục), Trợ lý AI (tìm kiếm)",
        ),
        Section(
            "rerank", "Rerank",
            "Model xếp hạng lại các đoạn tìm được để câu trả lời chính xác hơn. Tùy chọn.",
            (
                Field("enabled", "Bật rerank", "bool", False),
                Field("protocol", "Giao thức", "choice", "cohere", choices=("cohere", "tei", "intramind"),
                      help="cohere = /rerank {model, query, documents} (vLLM, Jina); tei = /rerank {query, texts}; "
                           "intramind = /api/v1/rerank {query, documents, top_k}."),
                Field("base_url", "Địa chỉ máy chủ", "url", lambda: config.RERANK_BASE_URL),
                Field("model", "Tên model", "str", lambda: config.RERANK_MODEL),
                Field("api_key", "API key", "str", "", secret=True),
                Field("candidates", "Số đoạn đưa vào rerank", "int", 30, minimum=5, maximum=200),
            ),
            sends_document_text=True, used_by="Trợ lý AI (tìm kiếm)",
        ),
        Section(
            "ocr", "OCR",
            "Nhận dạng chữ cho PDF scan hoặc PDF lỗi phông (ví dụ Peppercorn v3 qua vLLM). Tùy chọn.",
            (
                Field("enabled", "Bật OCR", "bool", False),
                Field("base_url", "Địa chỉ máy chủ", "url", lambda: config.OCR_BASE_URL),
                Field("model", "Tên model", "str", lambda: config.OCR_MODEL),
                Field("api_key", "API key", "str", "", secret=True),
                Field("max_pages", "Số trang tối đa mỗi tệp", "int", 60, minimum=1, maximum=2000),
                Field("grounding", "Đọc theo khối (grounding)", "bool", True,
                      help="Model đọc từng khối (tiêu đề, đoạn, bảng) thay vì cả trang một mạch; giữ các dòng đầu văn bản tách bạch nên trích yếu, số hiệu chính xác hơn."),
            ),
            sends_document_text=True, used_by="Kho văn bản (PDF cần OCR)",
        ),
        Section(
            "moderation", "Kiểm duyệt đầu vào",
            "Rà câu hỏi người dùng gõ vào trợ lý: chửi thề, xúc phạm, kỳ thị, đe dọa. Mọi lần phát hiện đều ghi vào nhật ký (Quản trị → Nhật ký, nhóm moderation) kèm người dùng, địa chỉ, cuộc trò chuyện.",
            (
                Field("enabled", "Bật kiểm duyệt", "bool", True),
                Field("mild_action", "Khi vi phạm nhẹ", "choice", "warn", choices=("log", "warn", "block"),
                      help="log = chỉ ghi nhật ký; warn = cảnh báo người dùng nhưng vẫn gửi; block = không gửi. Ví dụ vi phạm nhẹ: 'vcl', 'thằng ngu'."),
                Field("severe_action", "Khi vi phạm nặng", "choice", "block", choices=("log", "warn", "block"),
                      help="Ví dụ vi phạm nặng: chửi mẹ, kỳ thị dân tộc, đe dọa giết."),
                Field("model_enabled", "Dùng model phân loại", "bool", True,
                      help="ViSoBERT tinh chỉnh trên ViHSD chạy trên CPU (khoảng 10 ms/tin) để bắt câu xúc phạm không có từ khóa. Kết quả chỉ tính là vi phạm nhẹ. "
                           "Không có tệp model thì chỉ chạy luật từ khóa."),
                Field("model_threshold", "Ngưỡng tin cậy của model", "float", 0.95, minimum=0.5, maximum=0.999,
                      help="Xác suất tối thiểu để tính là vi phạm. Cao hơn = ít báo nhầm, bỏ sót nhiều hơn."),
            ),
            used_by="Trợ lý AI (câu hỏi người dùng)",
        ),
        Section(
            "doccheck", "Kiểm tra thể thức",
            "Bộ luật và thời hạn lưu tệp tạm của màn Kiểm tra thể thức.",
            (
                Field("profile", "Bộ luật", "choice", "tt68", choices=("tt68", "nd30")),
                Field("spell", "Kiểm tra chính tả mặc định", "bool", True),
                Field("spell_deep", "Soát chính tả sâu (mô hình GECToR)", "choice", "default", choices=("off", "auto", "default", "fast"),
                      help="Ngoài từ điển và n-gram, một mô hình ngôn ngữ chạy trên CPU đọc từng câu để bắt lỗi dấu thanh, dấu mũ, gõ sót phím, ghép/tách từ. "
                           "off = tắt; auto = bật nếu máy có mô hình và ONNX Runtime; default = mô hình chuẩn (V3, chính xác hơn); fast = mô hình nhanh (S3, nhanh khoảng 3 lần)."),
                Field("spell_deep_gate", "Mô hình đọc câu nào", "choice", "off", choices=("off", "auto"),
                      help="off = đọc mọi câu (chính xác nhất, vẫn chỉ vài giây cho một văn bản dài); auto = chỉ đọc câu n-gram nghi ngờ (nhanh hơn)."),
                Field("spell_deep_low", "Hiện cả mức tin cậy thấp", "bool", False,
                      help="Mức thấp là chỗ mô hình nghi nhưng n-gram không đồng thuận: nhiều khả năng báo nhầm hơn."),
                Field("temp_retention_hours", "Giữ tệp tạm (giờ)", "int", 24, minimum=1, maximum=168),
            ),
            used_by="Kiểm tra thể thức",
        ),
        Section(
            "storage", "Lưu trữ", "Giới hạn tải lên và thời gian giữ cuộc trò chuyện.",
            (
                Field("upload_max_mb", "Dung lượng tối đa mỗi tệp (MB)", "int", lambda: config.UPLOAD_MAX_MB, minimum=1, maximum=500),
                Field("chat_retention_days", "Giữ cuộc trò chuyện (ngày)", "int", 90, minimum=1, maximum=3650,
                      help="Cuộc trò chuyện không hoạt động quá số ngày này bị xóa cùng tệp đính kèm và bản dự thảo."),
            ),
            used_by="Kho văn bản, Trợ lý AI (tệp đính kèm, lịch sử trò chuyện)",
        ),
    )
}
