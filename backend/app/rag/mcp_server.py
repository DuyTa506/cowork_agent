"""MCP server (stdio) exposing the document and drafting tools to the agent harness.

One process per chat session: it reads the caller's identity (who is asking, and in which conversation) from QK3_SCOPE_TOKEN once
at start-up and refuses to start without a valid one. Run:  QK3_SCOPE_TOKEN=... python -m app.rag.mcp_server
"""
from __future__ import annotations

import os
import sys

from mcp.server.mcpserver import MCPServer
from qdrant_client import QdrantClient

from app.core import config
from app.org import UnitTree, scope_for
from app.rag.canvas_tools import CanvasTools
from app.rag.identity import Caller, IdentityError, caller_from_environment
from app.rag.llm import LlmClient
from app.rag.summarize import Summarizer
from app.rag.tools import AttachmentTools, RagTools, SummaryTools
from app.search import EmbeddingNotConfigured, HashEmbedder, QdrantIndex, Reranker, make_embedder, make_reranker
from app.services import attachments, indexing, settings

INSTRUCTIONS = (
    "Bạn truy cập kho văn bản của Quân khu 3 qua các công cụ này, trong phạm vi quyền của người đang hỏi. "
    "Luôn tìm bằng search_documents trước khi trả lời về nội dung văn bản; trích dẫn bằng mã 'cite' của từng đoạn dùng. "
    "Tự chọn cách tìm: mode 'keyword' cho số hiệu, tên riêng, mã, cụm từ chính xác; 'semantic' cho câu hỏi diễn đạt khác văn bản; "
    "'hybrid' khi chưa rõ. Dùng bộ lọc metadata (loại, ký hiệu, số, cơ quan, trích yếu, ngày) để thu hẹp, và list_documents khi chỉ "
    "cần tìm văn bản theo metadata. Kết quả trống thì thử mode hoặc cách diễn đạt khác trước khi kết luận. "
    "Không có kết quả nghĩa là không tìm thấy hoặc không có quyền xem: không suy đoán nội dung."
)

CANVAS_INSTRUCTIONS = (
    " Khi soạn văn bản trong canvas: mở mẫu phù hợp, điền các trường, viết nội dung rồi gọi canvas_check tối đa hai lần. "
    "Viết theo văn phong của đơn vị người dùng ('style' trong kết quả canvas_create, gồm phong cách trong 'style.chosen'; "
    "canvas_style có thêm văn bản mẫu cùng loại gần chủ đề): theo bố cục, câu mở đầu, câu kết và cách dùng từ của đơn vị, nhưng "
    "nội dung lấy từ yêu cầu và tài liệu được cung cấp, không chép số liệu của văn bản mẫu. Khi viết hoặc sửa đoạn thuộc một mục, "
    "gọi canvas_style(section=tên mục) để lấy đoạn mẫu của mục đó; đoạn mẫu chỉ để học cách viết, không lấy làm nội dung. "
    "Chỉ sửa những lỗi về nội dung mà kiểm tra báo; số/ký hiệu, chữ ký, chức vụ và họ tên người ký do con người hoàn tất, "
    "không tự bịa. Không đề xuất sửa hàng loạt về định dạng (in đậm, đánh số) và không đề xuất sửa đoạn người dùng đã viết trừ khi "
    "được yêu cầu. Bảng biểu chỉ tạo bằng khối 'table' (không vẽ bằng Markdown); số liệu người dùng chưa cung cấp để '…'; tổng cộng "
    "và số suy ra (thành tiền, tỷ lệ) dùng dòng 'total' và 'formula' để hệ thống tính, không tự tính; sửa vài ô, dòng, cột thì dùng "
    "canvas_edit_table. Gọi công cụ thật trong lượt đó; không viết '*Tool Call*' hay mô tả lệnh bằng chữ thay cho lệnh gọi. "
    "Kết thúc bằng một thông báo ngắn: đã soạn gì và người dùng còn phải nhập gì."
)


def _client() -> QdrantClient:
    return QdrantClient(url=config.QDRANT_URL, api_key=config.QDRANT_API_KEY or None)


def open_index() -> QdrantIndex:
    """The search index described by the administrator's embedding settings (read from the database).

    QK3_EMBEDDER=hash (with QDRANT_COLLECTION naming the collection) is a development/test override that needs no model server;
    it is refused in production.
    """
    if os.environ.get("QK3_EMBEDDER") == "hash":
        if config.APP_ENV == "production":
            raise SystemExit("QK3_EMBEDDER=hash không được dùng ở môi trường vận hành.")
        return QdrantIndex(_client(), HashEmbedder(int(os.environ.get("QK3_EMBEDDER_DIM", "256"))), config.QDRANT_COLLECTION)
    values = settings.cache.get("embedding")
    try:
        return QdrantIndex(_client(), make_embedder(values), settings.collection_name(values))
    except EmbeddingNotConfigured as exc:
        raise SystemExit(str(exc)) from exc


def open_attachment_index() -> QdrantIndex:
    """The index of files attached to chats (same embedding model, collection of its own)."""
    if os.environ.get("QK3_EMBEDDER") == "hash":
        return QdrantIndex(_client(), HashEmbedder(int(os.environ.get("QK3_EMBEDDER_DIM", "256"))), f"{config.QDRANT_COLLECTION}_att")
    try:
        return indexing.attachments()
    except EmbeddingNotConfigured as exc:
        raise SystemExit(str(exc)) from exc


def open_reranker() -> tuple[Reranker | None, int]:
    """The configured reranker and how many first-stage chunks it re-orders; (None, 0) when rerank is off or unreadable."""
    try:
        values = settings.cache.get("rerank")
        return make_reranker(values), int(values.get("candidates") or 30)
    except Exception as exc:  # noqa: BLE001  (no database reachable from this process)
        print(f"rerank unavailable: {type(exc).__name__}", file=sys.stderr)
        return None, 0


def open_summarizer() -> Summarizer | None:
    """The summariser for the configured chat model, or None when none is configured (or the settings cannot be read): the
    assistant then simply has no `summarize_document` tool."""
    try:
        llm = settings.cache.get("llm")
    except Exception as exc:  # noqa: BLE001  (no database reachable from this process)
        print(f"summarize_document unavailable: {type(exc).__name__}", file=sys.stderr)
        return None
    if not (llm.get("base_url") and llm.get("model")):
        return None
    return Summarizer(LlmClient(llm), int(llm.get("context_window") or 131072))


def build_server(tools: RagTools, *, attached: AttachmentTools | None = None, summary: SummaryTools | None = None,
                 canvas: CanvasTools | None = None) -> MCPServer:
    """Registers the tools that apply to this conversation."""
    server = MCPServer("qk3-documents", instructions=INSTRUCTIONS + (CANVAS_INSTRUCTIONS if canvas is not None else ""))
    server.add_tool(tools.search_documents, name="search_documents")
    server.add_tool(tools.read_document, name="read_document")
    server.add_tool(tools.list_documents, name="list_documents")
    if attached is not None:
        server.add_tool(attached.search_attachments, name="search_attachments")
        server.add_tool(attached.list_attachments, name="list_attachments")
        server.add_tool(attached.read_attachment, name="read_attachment")
    if summary is not None:
        server.add_tool(summary.summarize_document, name="summarize_document")
    if canvas is not None:
        for name in ("canvas_create", "canvas_style", "canvas_read", "canvas_set_fields", "canvas_set_content", "canvas_edit_block",
                     "canvas_edit_table", "canvas_check"):
            server.add_tool(getattr(canvas, name), name=name)
    return server


def assemble(caller: Caller) -> MCPServer:
    """The server for one caller: store tools always; attachment, summary and canvas tools inside a conversation."""
    scope = scope_for(UnitTree.load(), caller.principal)
    store = open_index()
    in_chat = bool(caller.session_id)
    attached_index = open_attachment_index() if in_chat else None
    attached_scope = attachments.scope_for(caller.session_id) if in_chat else None
    summarizer = open_summarizer()
    reranker, candidates = open_reranker()
    summary = SummaryTools((store, scope), (attached_index, attached_scope) if in_chat else None, summarizer) if summarizer else None
    return build_server(RagTools(store, scope, reranker, candidates),
                        attached=AttachmentTools(attached_index, attached_scope, reranker, candidates) if in_chat else None, summary=summary,
                        canvas=CanvasTools(caller.session_id, caller.user_id, (store, scope)) if in_chat and caller.user_id else None)


def main() -> None:
    try:
        caller = caller_from_environment(config.JWT_SECRET)
    except IdentityError as exc:
        sys.exit(str(exc))
    assemble(caller).run("stdio")


if __name__ == "__main__":
    main()
