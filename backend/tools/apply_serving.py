"""Fills Quản trị → Hệ thống (LLM, embedding, rerank, OCR) with the endpoints of the qk3-serving stack, the same as typing them in.

    python tools/apply_serving.py --host 127.0.0.1

Ports and model names are those of qk3-serving/README.md; pass --llm-port etc. when its .env differs. Uses whatever DATABASE_URL names.
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.core.database import SessionLocal, engine  # noqa: E402
from app.core.migrate import ensure_schema  # noqa: E402
from app.services import users  # noqa: E402
from app.services.settings import store  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--llm-port", type=int, default=8201)
    ap.add_argument("--llm-model", default="qwen3.6-35b-a3b")
    ap.add_argument("--adapter-port", type=int, default=8204)
    ap.add_argument("--ocr-port", type=int, default=8205)
    ap.add_argument("--ocr-model", default="peppercorn-v3")
    ap.add_argument("--ocr-max-pages", type=int, default=200)
    a = ap.parse_args()
    adapter = f"http://{a.host}:{a.adapter_port}"
    sections = {
        "llm": {"base_url": f"http://{a.host}:{a.llm_port}/v1", "model": a.llm_model, "context_window": 131072, "max_output_tokens": 8192},
        "embedding": {"provider": "intramind", "base_url": adapter, "model": "microsoft/harrier-oss-v1-270m", "dim": 640},
        "rerank": {"enabled": True, "protocol": "intramind", "base_url": adapter, "model": "BAAI/bge-reranker-v2-m3", "candidates": 30},
        "ocr": {"enabled": True, "base_url": f"http://{a.host}:{a.ocr_port}/v1", "model": a.ocr_model, "max_pages": a.ocr_max_pages},
    }
    ensure_schema(engine)
    with SessionLocal() as db:
        users.ensure_admin(db)
        for key, payload in sections.items():
            result = store.save(db, key, payload, actor="apply_serving")
            print(f"{key}: {', '.join(result['changed']) or 'không đổi'}")


if __name__ == "__main__":
    main()
