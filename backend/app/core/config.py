"""Process-level configuration, read once from environment variables.

These values bootstrap a deployment: where the data lives, how to reach the database and Qdrant, how to sign tokens. Anything an
administrator is expected to change while the system runs (which LLM, embedding, rerank or OCR model to use, upload limits)
lives in the database instead; see `app.services.settings`. The model-related variables below are only the *defaults* of those
settings, so a fresh deployment can be configured entirely from its environment.
"""
from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]


def _int(name: str, default: int) -> int:
    """Reads an integer environment variable, falling back to `default` when unset or empty."""
    raw = os.getenv(name, "").strip()
    return int(raw) if raw else default


def _url(name: str, default: str = "") -> str:
    """Reads a base URL environment variable without a trailing slash."""
    return os.getenv(name, default).strip().rstrip("/")


# ----- application -----
APP_NAME = os.getenv("APP_NAME", "Hệ thống AI Quân khu 3 (Hỗ trợ xử lý văn bản)")
APP_VERSION = "0.2.0"
APP_ENV = os.getenv("APP_ENV", "development")  # "production" disables development-only facilities (hash embedder)
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]

# ----- storage -----
DATA_DIR = Path(os.getenv("DATA_DIR", str(BASE_DIR / "data"))).resolve()
# Folder of the hate-speech classifier used by the input screening (app/moderation/model.py); without it only the word rules run.
MODERATION_MODEL_DIR = Path(os.getenv("MODERATION_MODEL_DIR", str(BASE_DIR / "models" / "visobert-hsd"))).resolve()
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", str(DATA_DIR / "uploads"))).resolve()  # documents in the store
TEMP_DIR = Path(os.getenv("TEMP_DIR", str(DATA_DIR / "tmp"))).resolve()  # one-off files (format check, uploads in flight)
OBJECT_DIR = Path(os.getenv("OBJECT_DIR", str(DATA_DIR / "objects"))).resolve()  # originals when OBJECT_STORE=local
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{(DATA_DIR / 'qk3.db').as_posix()}")
for _directory in (DATA_DIR, UPLOAD_DIR, TEMP_DIR):
    _directory.mkdir(parents=True, exist_ok=True)

# ----- object storage (original files) -----
OBJECT_STORE = os.getenv("OBJECT_STORE", "local").strip().lower()  # "s3" (MinIO / any S3-compatible server) or "local" (a directory)
S3_ENDPOINT = os.getenv("S3_ENDPOINT", "minio:9000").strip()  # host:port, no scheme
S3_ACCESS_KEY = os.getenv("S3_ACCESS_KEY", "")
S3_SECRET_KEY = os.getenv("S3_SECRET_KEY", "")
S3_BUCKET = os.getenv("S3_BUCKET", "qk3-documents")
S3_SECURE = os.getenv("S3_SECURE", "false").strip().lower() in ("1", "true", "yes")

# ----- authentication -----
JWT_SECRET = os.getenv("JWT_SECRET", "CHANGE_THIS_SECRET_BEFORE_DEPLOYMENT_64_CHARACTERS_MINIMUM")
JWT_EXPIRE_MINUTES = _int("JWT_EXPIRE_MINUTES", 480)
# Key (urlsafe base64, 32 bytes) that encrypts API keys stored in the database. When unset it is derived from JWT_SECRET.
SETTINGS_KEY = os.getenv("SETTINGS_KEY", "").strip()
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "ChangeMe123!")
ADMIN_FULL_NAME = os.getenv("ADMIN_FULL_NAME", "Quản trị hệ thống")
ADMIN_UNIT_ID = os.getenv("ADMIN_UNIT_ID", "btl")  # id in app/org/units.yaml; the bootstrap administrator's unit

# ----- search index -----
QDRANT_URL = _url("QDRANT_URL", "http://127.0.0.1:6333")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", "")
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "qk3_chunks")  # prefix; the embedding fingerprint is appended

# ----- defaults of the admin-editable model settings (see app.services.settings) -----
UPLOAD_MAX_MB = _int("UPLOAD_MAX_MB", 20)
LLM_BASE_URL = _url("QK3_LLM_BASE_URL")
LLM_MODEL = os.getenv("QK3_LLM_MODEL", "")
LLM_API_KEY = os.getenv("QK3_LLM_KEY", "")
EMBEDDING_BASE_URL = _url("EMBEDDING_BASE_URL")  # OpenAI-compatible /v1/embeddings (vLLM, TEI); never a public AI service
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "")
EMBEDDING_DIM = _int("EMBEDDING_DIM", 0)
EMBEDDING_QUERY_PREFIX = os.getenv("EMBEDDING_QUERY_PREFIX", "")
RERANK_BASE_URL = _url("RERANK_BASE_URL")
RERANK_MODEL = os.getenv("RERANK_MODEL", "")
OCR_BASE_URL = _url("OCR_BASE_URL")
OCR_MODEL = os.getenv("OCR_MODEL", "")

# ----- worker -----
WORKER_POLL_SECONDS = float(os.getenv("WORKER_POLL_SECONDS", "2"))
WORKER_MAX_ATTEMPTS = _int("WORKER_MAX_ATTEMPTS", 3)
