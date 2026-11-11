"""Message transports. Live sends only with explicit live mode + configured credentials."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from app.config import get_settings


@dataclass
class SendResult:
    ok: bool
    status: str  # simulated | sent | failed
    provider_message_id: str | None = None
    error: str | None = None


class Transport(Protocol):
    name: str

    def send(self, payload: dict[str, Any]) -> SendResult: ...


class SimulatedTransport:
    """Stores the message in the outbox only. Nothing leaves the system."""

    name = "simulated"

    def send(self, payload: dict[str, Any]) -> SendResult:
        return SendResult(True, "simulated", f"sim-{uuid.uuid4().hex[:16]}")


class MetaCloudTransport:
    """POST https://graph.facebook.com/{API_VERSION}/{PHONE_NUMBER_ID}/messages"""

    name = "meta"

    def __init__(self, client: httpx.Client | None = None) -> None:
        s = get_settings()
        assert s.whatsapp_phone_number_id and s.whatsapp_access_token
        self.url = f"https://graph.facebook.com/{s.whatsapp_api_version}/{s.whatsapp_phone_number_id}/messages"
        self._token = s.whatsapp_access_token.get_secret_value()
        self.client = client or httpx.Client(timeout=15)

    def send(self, payload: dict[str, Any]) -> SendResult:
        try:
            resp = self.client.post(
                self.url, json=payload, headers={"Authorization": f"Bearer {self._token}"}
            )
        except httpx.HTTPError as exc:
            return SendResult(False, "failed", error=f"network error: {type(exc).__name__}")
        if resp.status_code >= 400:
            try:
                err = resp.json().get("error", {})
                detail = f"{err.get('code')}: {err.get('message')}"
            except ValueError:
                detail = f"HTTP {resp.status_code}"
            return SendResult(False, "failed", error=detail[:300])
        messages = resp.json().get("messages") or [{}]
        return SendResult(True, "sent", messages[0].get("id"))


def get_transport() -> Transport:
    return MetaCloudTransport() if get_settings().whatsapp_live else SimulatedTransport()
