"""Administration payloads."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SettingsSave(BaseModel):
    """Values for one settings section. A secret that is omitted or null is kept; an empty string clears it."""

    values: dict[str, Any]
    confirm_hosts: list[str] = Field(default_factory=list, description="External hosts the administrator accepts to send document text to.")


class SettingsTest(BaseModel):
    """Values to try without saving them (omitted secrets use the saved ones)."""

    values: dict[str, Any] = Field(default_factory=dict)


class AuditOut(BaseModel):
    """One audit row."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    action: str
    entity_type: str
    entity_id: str
    detail: str
    ip_address: str
    created_at: datetime
