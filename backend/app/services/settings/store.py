"""Reading and writing administrator settings.

Each section is one `AppSetting` row holding only the values an administrator has saved. Anything not saved falls back to the
field's default (the environment), so a fresh deployment works from its environment alone and a saved value always wins.

Secrets are encrypted in the row and are never handed back out: `public` reports only whether one is set, and `save` treats a
missing secret as "keep the current one".
"""
from __future__ import annotations

import hashlib
import threading
import time
from typing import Any

from sqlalchemy.orm import Session

from app.core import config
from app.core.database import SessionLocal
from app.core.errors import ExternalEndpointNotConfirmed, ValidationFailed
from app.models import AppSetting
from app.models.base import now_utc

from . import secrets
from .endpoints import host_of, is_private_host
from .spec import SECTIONS, Field, Section

CONFIRMED_HOSTS_KEY = "_confirmed_hosts"


def section_of(key: str) -> Section:
    """The section called `key`; raises `ValidationFailed` for an unknown one."""
    try:
        return SECTIONS[key]
    except KeyError:
        raise ValidationFailed(f"Không có mục cấu hình '{key}'.") from None


# --------------------------------------------------------------------------------------------------------------------------
# validation
# --------------------------------------------------------------------------------------------------------------------------
def _coerce(field: Field, raw: Any) -> Any:
    """Validates `raw` against the field's kind and bounds and returns the normalised value."""
    label = field.label
    if field.kind in ("str", "url"):
        if not isinstance(raw, str):
            raise ValidationFailed(f"'{label}' phải là chuỗi.")
        value = raw if field.verbatim else raw.strip()
        if field.kind == "url" and value:
            value = value.rstrip("/")
            if not (value.startswith(("http://", "https://")) and host_of(value)):
                raise ValidationFailed(f"'{label}' phải là địa chỉ http:// hoặc https://.")
        return value
    if field.kind == "bool":
        if not isinstance(raw, bool):
            raise ValidationFailed(f"'{label}' phải là đúng/sai.")
        return raw
    if field.kind == "choice":
        if raw not in field.choices:
            raise ValidationFailed(f"'{label}' phải là một trong: {', '.join(field.choices)}.")
        return raw
    if field.kind in ("int", "float"):
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            raise ValidationFailed(f"'{label}' phải là số.")
        value = int(raw) if field.kind == "int" else float(raw)
        if field.kind == "int" and value != raw:
            raise ValidationFailed(f"'{label}' phải là số nguyên.")
        if (field.minimum is not None and value < field.minimum) or (field.maximum is not None and value > field.maximum):
            raise ValidationFailed(f"'{label}' phải nằm trong khoảng {field.minimum} – {field.maximum}.")
        return value
    raise AssertionError(f"unknown field kind {field.kind!r}")


def _check_consistency(section: Section, values: dict[str, Any]) -> None:
    """Rejects combinations that cannot work (a section switched on without the endpoint it needs)."""
    if section.key == "embedding" and values["provider"] in ("openai", "intramind"):
        needed = ("base_url", "model") if values["provider"] == "openai" else ("base_url",)
        missing = [f for f in needed if not values[f]] + (["dim"] if not values["dim"] else [])
        if missing:
            raise ValidationFailed(f"Embedding loại '{values['provider']}' cần: địa chỉ máy chủ"
                                   f"{', tên model' if values['provider'] == 'openai' else ''} và số chiều vector.")
    if section.key == "rerank" and values["enabled"]:
        if not values["base_url"] or (values["protocol"] != "intramind" and not values["model"]):
            raise ValidationFailed("Bật Rerank cần địa chỉ máy chủ" + ("" if values["protocol"] == "intramind" else " và tên model") + ".")
    if section.key == "ocr" and values["enabled"] and not (values["base_url"] and values["model"]):
        raise ValidationFailed(f"Bật {section.label} cần địa chỉ máy chủ và tên model.")


# --------------------------------------------------------------------------------------------------------------------------
# reading
# --------------------------------------------------------------------------------------------------------------------------
def _row(db: Session, key: str) -> dict[str, Any]:
    """The saved record of section `key` (raw, secrets still encrypted); empty when nothing was saved."""
    row = db.get(AppSetting, key)
    return dict(row.value) if row else {}


def effective(section: Section, saved: dict[str, Any]) -> dict[str, Any]:
    """Section values as the application sees them: saved value, else default; secrets decrypted."""
    out: dict[str, Any] = {}
    for field in section.fields:
        if field.name in saved:
            out[field.name] = secrets.decrypt(saved[field.name]) if field.secret else saved[field.name]
        else:
            out[field.name] = field.default_value()
    return out


def load(db: Session, key: str) -> dict[str, Any]:
    """Effective values of section `key`, secrets included. For server-side use only: never return this from an API."""
    return effective(section_of(key), _row(db, key))


def confirmed_hosts(db: Session) -> set[str]:
    """External hosts an administrator has explicitly allowed to receive document text."""
    return set(_row(db, CONFIRMED_HOSTS_KEY).get("hosts", []))


def public(db: Session) -> dict[str, Any]:
    """Everything the admin screen needs: each section with field metadata and current values.

    Secret fields carry ``{"set": bool}`` instead of a value, so a response never contains a key, even encrypted.
    """
    sections = []
    for section in SECTIONS.values():
        values = load(db, section.key)
        fields = []
        for field in section.fields:
            item: dict[str, Any] = {
                "name": field.name, "label": field.label, "kind": field.kind, "help": field.help, "secret": field.secret,
                "choices": list(field.choices), "minimum": field.minimum, "maximum": field.maximum,
            }
            if field.secret:
                item["value"] = {"set": bool(values[field.name])}
            else:
                item["value"] = values[field.name]
            fields.append(item)
        sections.append({"key": section.key, "label": section.label, "description": section.description,
                         "used_by": section.used_by, "sends_document_text": section.sends_document_text, "fields": fields})
    return {"sections": sections, "confirmed_hosts": sorted(confirmed_hosts(db)),
            "embedding": {"fingerprint": embedding_fingerprint(load(db, "embedding")),
                          "collection": collection_name(load(db, "embedding"))}}


# --------------------------------------------------------------------------------------------------------------------------
# writing
# --------------------------------------------------------------------------------------------------------------------------
def _merge(section: Section, saved: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    """Applies `payload` over the saved record and returns the new record (secrets encrypted).

    A secret that is absent or ``None`` in the payload keeps its current value; an empty string clears it.
    """
    unknown = sorted(set(payload) - {f.name for f in section.fields})
    if unknown:
        raise ValidationFailed(f"Trường không tồn tại: {', '.join(unknown)}.")
    merged = dict(saved)
    for name, raw in payload.items():
        field = section.field(name)
        if field.secret:
            if raw is None:
                continue
            if not isinstance(raw, str):
                raise ValidationFailed(f"'{field.label}' phải là chuỗi.")
            merged[name] = secrets.encrypt(raw.strip())
        else:
            merged[name] = _coerce(field, raw)
    _check_consistency(section, effective(section, merged))
    return merged


def preview(db: Session, key: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Effective values the section would have after saving `payload`, without saving. Used by "test connection" so an
    administrator can try a form before committing it."""
    section = section_of(key)
    return effective(section, _merge(section, _row(db, key), payload))


def _unconfirmed_hosts(section: Section, before: dict[str, Any], after: dict[str, Any], allowed: set[str]) -> list[str]:
    """External hosts in endpoint fields that this save introduces and nobody has confirmed yet."""
    if not section.sends_document_text:
        return []
    hosts = []
    for field in section.fields:
        if field.kind != "url" or after[field.name] == before[field.name]:
            continue
        host = host_of(after[field.name])
        if host and not is_private_host(host) and host not in allowed:
            hosts.append(host)
    return sorted(set(hosts))


def save(db: Session, key: str, payload: dict[str, Any], *, actor: str, confirm_hosts: list[str] | None = None) -> dict[str, Any]:
    """Validates and stores `payload` for section `key`.

    Endpoints outside the private network receive document text, so they are refused unless the administrator lists the host
    in `confirm_hosts`; a confirmed host is remembered and not asked about again.

    Returns:
        ``{"changed": [field names], "new_hosts": [hosts confirmed by this save]}`` for the caller to audit.

    Raises:
        ValidationFailed: unknown section/field, invalid value, or an inconsistent combination.
        ExternalEndpointNotConfirmed: an external host was submitted without confirmation.
    """
    section = section_of(key)
    saved = _row(db, key)
    merged = _merge(section, saved, payload)
    before, after = effective(section, saved), effective(section, merged)

    known = confirmed_hosts(db)
    pending = _unconfirmed_hosts(section, before, after, known)
    unconfirmed = [h for h in pending if h not in {h.lower() for h in confirm_hosts or []}]
    if unconfirmed:
        raise ExternalEndpointNotConfirmed(
            f"Địa chỉ {', '.join(unconfirmed)} nằm ngoài mạng nội bộ và sẽ nhận nội dung văn bản. Cần xác nhận trước khi lưu.",
            unconfirmed)

    changed = [f.name for f in section.fields if before[f.name] != after[f.name]]
    _write(db, key, merged, actor)
    if pending:
        _write(db, CONFIRMED_HOSTS_KEY, {"hosts": sorted(known | set(pending))}, actor)
    db.commit()
    cache.invalidate()
    return {"changed": changed, "new_hosts": pending}


def _write(db: Session, key: str, value: dict[str, Any], actor: str) -> None:
    """Upserts one settings row (does not commit)."""
    row = db.get(AppSetting, key)
    if row is None:
        db.add(AppSetting(key=key, value=value, updated_by=actor, updated_at=now_utc()))
    else:
        row.value, row.updated_by, row.updated_at = value, actor, now_utc()


# --------------------------------------------------------------------------------------------------------------------------
# embedding identity
# --------------------------------------------------------------------------------------------------------------------------
def embedding_fingerprint(values: dict[str, Any]) -> str:
    """Short id of everything that changes what a stored vector means (model, size, document prefix).

    Two configurations with the same fingerprint can share an index; a different one needs a new index, so the collection
    name carries it and a change triggers a rebuild instead of silently mixing incompatible vectors.
    """
    basis = "|".join(str(values.get(k, "")) for k in ("provider", "model", "dim", "doc_prefix"))
    return hashlib.sha1(basis.encode("utf-8")).hexdigest()[:8]


def collection_name(values: dict[str, Any]) -> str:
    """Qdrant collection that holds vectors for these embedding settings."""
    return f"{config.QDRANT_COLLECTION}_{embedding_fingerprint(values)}"


# --------------------------------------------------------------------------------------------------------------------------
# cache for processes that read settings often (worker, MCP server)
# --------------------------------------------------------------------------------------------------------------------------
class SettingsCache:
    """Short-lived in-process copy of the settings, so hot paths do not query the database on every call yet still notice an
    administrator's change within `ttl` seconds (immediately in the process that saved it)."""

    def __init__(self, ttl: float = 15.0):
        self.ttl = ttl
        self._lock = threading.Lock()
        self._values: dict[str, dict[str, Any]] = {}
        self._loaded_at = 0.0

    def invalidate(self) -> None:
        """Forgets the cached copy; the next `get` reads the database."""
        with self._lock:
            self._loaded_at = 0.0

    def get(self, key: str) -> dict[str, Any]:
        """Effective values of section `key` (secrets included), at most `ttl` seconds old."""
        with self._lock:
            if time.monotonic() - self._loaded_at > self.ttl:
                with SessionLocal() as db:
                    self._values = {k: load(db, k) for k in SECTIONS}
                self._loaded_at = time.monotonic()
            return dict(self._values[key])


cache = SettingsCache()
