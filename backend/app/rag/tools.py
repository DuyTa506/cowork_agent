"""Tools the agent calls to work with the document store. Every one runs under the caller's Scope: a document the user may
not read is indistinguishable from one that does not exist.

Results are plain dicts, kept small (snippets, bounded pages) because the model pays for every token it reads.
"""
from __future__ import annotations
import sys
from datetime import datetime, timezone
from typing import Any, Literal

from app.org.access import Scope
from app.search import QdrantIndex, Reranker, SearchFilters
from app.search.store import Hit

SNIPPET_CHARS = 900
RERANK_PASSAGE_CHARS = 2400  # what the cross-encoder reads of a chunk; its own limit is about 512 tokens
READ_PAGE_CHARS = 6000
NOT_FOUND = "Không tìm thấy văn bản này hoặc bạn không có quyền xem."

def _date(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)

def _cut(text: str, n: int) -> str:
    return text if len(text) <= n else text[:n].rsplit(" ", 1)[0] + " …"

def retrieve(index: QdrantIndex, scope: Scope, query: str, top_k: int, *, mode: str, filters: SearchFilters | None = None,
             reranker: Reranker | None = None, candidates: int = 30) -> list[Hit]:
    """The `top_k` best chunks for `query`. With a reranker the first stage returns `candidates` chunks (never fewer than
    `top_k`) and the cross-encoder re-orders them; if it fails, the first-stage order is kept, so search never breaks on it."""
    top_k = max(1, min(top_k, 20))
    if reranker is None:
        return index.search(query, scope, k=top_k, filters=filters, mode=mode)
    hits = index.search(query, scope, k=max(candidates, top_k), filters=filters, mode=mode)
    if len(hits) < 2:
        return hits[:top_k]
    try:
        passages = [_cut("\n".join(filter(None, [h.context, " > ".join(h.path), h.text])), RERANK_PASSAGE_CHARS) for h in hits]
        scores = reranker.rerank(query, passages)
    except Exception as exc:  # noqa: BLE001  (an unreachable or misconfigured rerank server must not break search)
        print(f"rerank unavailable, keeping first-stage order: {type(exc).__name__}", file=sys.stderr)
        return hits[:top_k]
    for h, score in zip(hits, scores):
        h.score = score
    return sorted(hits, key=lambda h: -h.score)[:top_k]

class RagTools:
    def __init__(self, index: QdrantIndex, scope: Scope, reranker: Reranker | None = None, candidates: int = 30):
        self.index, self.scope, self.reranker, self.candidates = index, scope, reranker, candidates

    def search_documents(self, query: str, mode: Literal["hybrid", "keyword", "semantic"] = "hybrid", doc_type: str = "",
                         symbol: str = "", number: str = "", issuing_agency: str = "", title: str = "", date_from: str = "",
                         date_to: str = "", top_k: int = 8) -> list[dict[str, Any]]:
        """Tìm các đoạn văn bản trong kho (chỉ trong phạm vi người hỏi được xem).

        mode: 'keyword' = khớp đúng từ (số hiệu, tên riêng, mã, cụm từ chính xác); 'semantic' = khớp theo ý nghĩa khi câu hỏi
        diễn đạt khác văn bản; 'hybrid' (mặc định) = kết hợp cả hai. Nếu chưa ra kết quả, thử đổi mode hoặc đổi cách diễn đạt.
        Bộ lọc metadata (tuỳ chọn, thu hẹp kết quả): doc_type (vd 'Quyết định', 'Kế hoạch', 'Báo cáo'), symbol (ký hiệu, vd
        'QĐ-QK3'), number (số, vd '15'), issuing_agency (các từ trong tên cơ quan ban hành), title (các từ trong trích yếu),
        date_from/date_to (YYYY-MM-DD, theo ngày ban hành).
        """
        flt = SearchFilters(doc_types=[doc_type] if doc_type else [], symbols=[symbol] if symbol else [],
                            numbers=[number] if number else [], agency=issuing_agency, title=title,
                            date_from=_date(date_from), date_to=_date(date_to))
        hits = retrieve(self.index, self.scope, query, top_k, mode=mode, filters=flt, reranker=self.reranker, candidates=self.candidates)
        return [{"cite": h.chunk_id, "doc_id": h.doc_id, "doc": h.context, "section": " > ".join(h.path),
                 "text": _cut(h.text, SNIPPET_CHARS), "pi": [h.payload.get("pi_first", -1), h.payload.get("pi_last", -1)],
                 "score": round(h.score, 4)} for h in hits]

    def read_document(self, doc_id: str, offset: int = 0) -> dict[str, Any]:
        """Đọc nội dung đầy đủ của một văn bản, theo trang (~6000 ký tự); dùng next_offset để đọc tiếp."""
        chunks = self.index.get_chunks(doc_id, self.scope)
        if not chunks:
            return {"error": NOT_FOUND}
        body = "\n".join(c["text"] for c in chunks)
        offset = max(0, offset)
        page = body[offset:offset + READ_PAGE_CHARS]
        end = offset + len(page)
        return {"doc_id": doc_id, "doc": chunks[0]["context"], "total_chars": len(body), "offset": offset, "text": page,
                "next_offset": end if end < len(body) else None}

    def list_documents(self, doc_type: str = "", symbol: str = "", number: str = "", issuing_agency: str = "", title: str = "",
                       date_from: str = "", date_to: str = "", limit: int = 20) -> list[dict[str, Any]]:
        """Liệt kê văn bản theo metadata (mới nhất trước), không cần từ khoá nội dung: lọc theo loại, ký hiệu, số, cơ quan ban
        hành, trích yếu và khoảng ngày (YYYY-MM-DD). Dùng để tìm văn bản theo số hiệu/cơ quan/thời gian. Văn bản chưa có ngày
        (bản nháp) không có trong danh sách."""
        flt = SearchFilters(doc_types=[doc_type] if doc_type else [], symbols=[symbol] if symbol else [],
                            numbers=[number] if number else [], agency=issuing_agency, title=title,
                            date_from=_date(date_from), date_to=_date(date_to))
        rows = self.index.list_documents(self.scope, flt, limit=max(1, min(limit, 50)))
        return [{"doc_id": r["doc_id"], "loai": r["doc_type"], "so_ky_hieu": f'{r["number"]}/{r["symbol"]}'.strip("/"),
                 "ngay": (r.get("date") or "")[:10], "co_quan": r["issuing_agency"], "trich_yeu": r["title"]} for r in rows]


class AttachmentTools:
    """Tools over the files the user attached to this conversation (and nothing else). Same shapes as the store tools; ids are
    ``att<N>``."""

    def __init__(self, index: QdrantIndex, scope: Scope, reranker: Reranker | None = None, candidates: int = 30):
        self.index, self.scope, self.reranker, self.candidates = index, scope, reranker, candidates

    def search_attachments(self, query: str, mode: Literal["hybrid", "keyword", "semantic"] = "hybrid", top_k: int = 8) -> list[dict[str, Any]]:
        """Tìm các đoạn trong tệp người dùng đã đính kèm vào cuộc trò chuyện này (không phải kho văn bản). Cách dùng giống
        search_documents; mã 'cite' dùng để trích dẫn."""
        hits = retrieve(self.index, self.scope, query, top_k, mode=mode, reranker=self.reranker, candidates=self.candidates)
        return [{"cite": h.chunk_id, "doc_id": h.doc_id, "doc": h.context, "section": " > ".join(h.path), "text": _cut(h.text, SNIPPET_CHARS),
                 "pi": [h.payload.get("pi_first", -1), h.payload.get("pi_last", -1)], "score": round(h.score, 4)} for h in hits]

    def list_attachments(self) -> list[dict[str, Any]]:
        """Liệt kê các tệp đã đính kèm vào cuộc trò chuyện này (mã att<N>, loại, trích yếu)."""
        rows = self.index.list_documents(self.scope, None, limit=50)
        return [{"doc_id": r["doc_id"], "loai": r["doc_type"], "so_ky_hieu": f'{r["number"]}/{r["symbol"]}'.strip("/"),
                 "trich_yeu": r["title"]} for r in rows]

    def read_attachment(self, doc_id: str, offset: int = 0) -> dict[str, Any]:
        """Đọc nội dung một tệp đính kèm theo trang (~6000 ký tự); dùng next_offset để đọc tiếp. Muốn tóm tắt cả tệp thì gọi
        summarize_document, đừng đọc từng trang."""
        chunks = self.index.get_chunks(doc_id, self.scope)
        if not chunks:
            return {"error": "Không tìm thấy tệp đính kèm này."}
        body = "\n".join(c["text"] for c in chunks)
        offset = max(0, offset)
        page = body[offset:offset + READ_PAGE_CHARS]
        end = offset + len(page)
        return {"doc_id": doc_id, "doc": chunks[0]["context"], "total_chars": len(body), "offset": offset, "text": page,
                "next_offset": end if end < len(body) else None}


class SummaryTools:
    """Whole-document summaries, for documents of the store and files attached to this conversation alike."""

    def __init__(self, store: tuple[QdrantIndex, Scope] | None, attached: tuple[QdrantIndex, Scope] | None, summarizer: Any):
        self.store, self.attached, self.summarizer = store, attached, summarizer

    def summarize_document(self, doc_id: str, focus: str = "") -> dict[str, Any]:
        """Tóm tắt toàn bộ một văn bản (mã trong kho, vd '12') hoặc tệp đính kèm (vd 'att3') theo cấu trúc: mục đích, nội dung chính,
        thời gian-địa điểm-lực lượng, trách nhiệm-thời hạn. Văn bản dài được tóm tắt theo từng phần rồi hợp nhất. focus (tuỳ chọn):
        điều người dùng đặc biệt quan tâm. Dùng công cụ này thay vì đọc từng trang."""
        target = self.attached if doc_id.startswith("att") else self.store
        if target is None:
            return {"error": NOT_FOUND}
        index, scope = target
        chunks = index.get_chunks(doc_id, scope)
        if not chunks:
            return {"error": NOT_FOUND}
        out = self.summarizer.summarize(chunks, focus)
        return {"doc_id": doc_id, "doc": chunks[0]["context"], "summary": out["summary"], "parts": out["parts"], "method": out["method"]}
