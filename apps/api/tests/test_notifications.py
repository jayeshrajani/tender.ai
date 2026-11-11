import hashlib
import hmac
import json
from datetime import UTC, datetime, time

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import NotificationDelivery, NotificationOutbox, NotificationPreference, Organization, User
from app.services.notifications import service as notify
from app.services.notifications import templates as T
from app.services.notifications.transport import SendResult


class Recorder:
    name = "meta"

    def __init__(self) -> None:
        self.sent: list[dict] = []

    def send(self, payload: dict) -> SendResult:
        self.sent.append(payload)
        return SendResult(True, "sent", f"wamid.{len(self.sent)}")


def _narmada(db: Session) -> tuple[Organization, NotificationPreference]:
    org = db.scalar(select(Organization).where(Organization.legal_name.like("Narmada%")))
    owner = db.scalar(select(User).where(User.email == "owner@narmada.demo"))
    pref = db.scalar(select(NotificationPreference).where(NotificationPreference.user_id == owner.id))
    assert org and pref
    return org, pref


def test_whatsapp_payload_shape_and_content() -> None:
    params = T.tender_alert_params(
        alert_type="closing_48h", title="BT road\nwith drains", department="PWD", value_paise=2_95_00_000_00,
        eligibility_status="NEEDS_VERIFICATION", eligibility_summary="Solvency unverified",
        deadline=datetime(2026, 11, 20, 12, 0, tzinfo=UTC), official_url="https://mptenders.gov.in/",
        app_url="http://localhost:3000/tenders/1", freshness="DEMO data - not a real tender.",
    )
    payload = T.meta_payload("+919800000001", T.TENDER_ALERT, params, "en")
    assert payload["messaging_product"] == "whatsapp" and payload["type"] == "template"
    assert payload["to"] == "919800000001"
    body = payload["template"]["components"][0]["parameters"]
    assert len(body) == 9 and all("\n" not in p["text"] for p in body)
    text = T.render(T.TENDER_ALERT, params)
    for expected in ("BT road with drains", "PWD", "₹2.95 Cr", "Needs verification", "20 Nov 2026, 05:30 PM IST",
                     "https://mptenders.gov.in/", "/tenders/1", "DEMO data"):
        assert expected in text
    assert T.redact_payload(payload)["to"] == "+91 98•••••001"


def test_alerts_dedupe_and_opt_out_enforcement(seeded: Session) -> None:
    db = seeded
    org, pref = _narmada(db)
    first = notify.generate_event_alerts(db, org.id)
    second = notify.generate_event_alerts(db, org.id)
    db.commit()
    assert first["closing_48h"] >= 1 and first["deadline_change"] == 1
    assert second == {"closing_48h": 0, "deadline_change": 0}

    pref.opted_out_at = datetime.now(UTC)
    db.commit()
    rec = Recorder()
    stats = notify.dispatch_pending(db, rec)
    db.commit()
    assert rec.sent == []
    assert stats["skipped_opt_out"] >= 2
    statuses = set(db.scalars(select(NotificationOutbox.status).where(NotificationOutbox.organization_id == org.id)))
    assert statuses == {"skipped_opt_out"}


def test_dispatch_redacts_and_respects_quiet_hours(seeded: Session) -> None:
    db = seeded
    org, pref = _narmada(db)
    pref.quiet_hours_start, pref.quiet_hours_end = time(22, 0), time(7, 0)
    notify.generate_event_alerts(db, org.id)
    db.commit()
    rec = Recorder()
    night = datetime(2026, 11, 11, 17, 0, tzinfo=UTC)  # 22:30 IST
    held = notify.dispatch_pending(db, rec, now=night)
    assert held["held"] >= 1 and rec.sent == []
    morning = datetime(2026, 11, 12, 2, 0, tzinfo=UTC)  # 07:30 IST
    sent = notify.dispatch_pending(db, rec, now=morning)
    db.commit()
    assert sent["sent"] == held["held"] and rec.sent[0]["to"] == "919800000001"
    stored = db.scalars(select(NotificationOutbox).where(NotificationOutbox.status == "sent")).first()
    assert stored is not None and stored.payload["to"].startswith("+91 98•")


def _sign(body: bytes) -> str:
    return "sha256=" + hmac.new(b"test-app-secret", body, hashlib.sha256).hexdigest()


def test_webhook_verification_signature_idempotency_and_stop(client_factory, seeded: Session) -> None:  # type: ignore[no-untyped-def]
    db = seeded
    c = client_factory()
    ok = c.get("/api/v1/whatsapp/webhook", params={"hub.mode": "subscribe", "hub.verify_token": "test-verify-token", "hub.challenge": "42"})
    assert ok.status_code == 200 and ok.text == "42"
    assert c.get("/api/v1/whatsapp/webhook", params={"hub.mode": "subscribe", "hub.verify_token": "nope", "hub.challenge": "1"}).status_code == 403

    org, pref = _narmada(db)
    notify.generate_event_alerts(db, org.id)
    notify.dispatch_pending(db, Recorder())
    db.commit()
    msg = db.scalars(select(NotificationOutbox).where(NotificationOutbox.status == "sent")).first()
    assert msg is not None
    event = {"entry": [{"changes": [{"value": {
        "statuses": [{"id": msg.provider_message_id, "status": "delivered", "timestamp": "1794300000"}],
        "messages": [{"from": "919800000001", "text": {"body": "STOP"}}],
    }}]}]}
    raw = json.dumps(event).encode()
    assert c.post("/api/v1/whatsapp/webhook", content=raw, headers={"X-Hub-Signature-256": "sha256=bad"}).status_code == 401
    for _ in range(2):
        r = c.post("/api/v1/whatsapp/webhook", content=raw, headers={"X-Hub-Signature-256": _sign(raw), "Content-Type": "application/json"})
        assert r.status_code == 200
    db.expire_all()
    deliveries = db.scalars(select(NotificationDelivery).where(NotificationDelivery.provider_message_id == msg.provider_message_id)).all()
    assert len(deliveries) == 1
    assert db.get(NotificationOutbox, msg.id).status == "delivered"
    refreshed = db.get(NotificationPreference, pref.id)
    assert refreshed.whatsapp_opt_in is False and refreshed.opted_out_at is not None


def test_simulated_test_message_is_labelled(client_factory) -> None:  # type: ignore[no-untyped-def]
    c = client_factory()
    c.login("owner@narmada.demo")
    r = c.post("/api/v1/notifications/test")
    assert r.status_code == 201 and r.json()["simulated"] is True and r.json()["status"] == "simulated"
    prefs = c.get("/api/v1/notifications/preferences").json()
    assert prefs["transport"] == "simulated" and "SIMULATED" in prefs["transport_note"]
    out = c.get("/api/v1/notifications/outbox").json()["items"]
    assert out[0]["transport"] == "simulated" and out[0]["recipient"] == "+91 98•••••001"
