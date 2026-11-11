from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from datetime import timedelta
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from fastapi.responses import PlainTextResponse
from sqlalchemy import func, select

from app.config import get_settings
from app.deps import DB, Analyst, Tenant, audit
from app.models import CompanyTenderMatch, NotificationOutbox, NotificationPreference, Tender
from app.schemas import NotificationPrefsIn
from app.services.matching import compute_match, visible_tenders_clause
from app.services.notifications import service as notify
from app.services.notifications import templates as T
from app.services.notifications.transport import get_transport
from app.services.timeutil import utcnow

router = APIRouter(prefix="/api/v1", tags=["notifications"])


def _pref(db: DB, org_id: uuid.UUID, user_id: uuid.UUID) -> NotificationPreference:
    pref = db.scalar(
        select(NotificationPreference).where(
            NotificationPreference.organization_id == org_id, NotificationPreference.user_id == user_id
        )
    )
    if pref is None:
        pref = NotificationPreference(organization_id=org_id, user_id=user_id)
        db.add(pref)
        db.flush()
    return pref


def _pref_json(p: NotificationPreference) -> dict[str, Any]:
    s = get_settings()
    return {
        "phone_e164": p.phone_e164,
        "phone_masked": T.mask_phone(p.phone_e164),
        "phone_verified": p.phone_verified_at is not None,
        "whatsapp_opt_in": p.whatsapp_opt_in,
        "opt_in_at": p.opt_in_at,
        "opted_out_at": p.opted_out_at,
        "daily_digest": p.daily_digest,
        "urgent_alerts": p.urgent_alerts,
        "closing_reminders": p.closing_reminders,
        "min_relevance": p.min_relevance,
        "include_needs_verification": p.include_needs_verification,
        "quiet_hours_start": p.quiet_hours_start.strftime("%H:%M") if p.quiet_hours_start else None,
        "quiet_hours_end": p.quiet_hours_end.strftime("%H:%M") if p.quiet_hours_end else None,
        "transport": "meta" if s.whatsapp_live else "simulated",
        "transport_note": (
            "Live Meta WhatsApp Cloud API credentials are configured."
            if s.whatsapp_live
            else "SIMULATED: no Meta credentials configured. Messages are stored in the outbox and never sent."
        ),
    }


@router.get("/notifications/preferences")
def get_prefs(ctx: Tenant, db: DB) -> dict[str, Any]:
    pref = _pref(db, ctx.org_id, ctx.user.id)
    db.commit()
    return _pref_json(pref)


@router.put("/notifications/preferences")
def put_prefs(body: NotificationPrefsIn, ctx: Tenant, db: DB) -> dict[str, Any]:
    pref = _pref(db, ctx.org_id, ctx.user.id)
    if body.phone_e164 != pref.phone_e164:
        pref.phone_verified_at = None
    was_opted_in = pref.whatsapp_opt_in
    for k, v in body.model_dump().items():
        setattr(pref, k, v)
    if body.whatsapp_opt_in and not was_opted_in:
        pref.opt_in_at = utcnow()
        pref.opt_in_source = "in_app_settings"
        pref.opted_out_at = None
    if not body.whatsapp_opt_in and was_opted_in:
        pref.opted_out_at = utcnow()
    audit(db, ctx, "notifications.preferences_updated", "notification_preference", pref.id,
          {"opt_in": body.whatsapp_opt_in})
    db.commit()
    return _pref_json(pref)


@router.get("/notifications/outbox")
def outbox(
    ctx: Tenant, db: DB, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)
) -> dict[str, Any]:
    q = select(NotificationOutbox).where(NotificationOutbox.organization_id == ctx.org_id)
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    rows = db.scalars(
        q.order_by(NotificationOutbox.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return {
        "items": [
            {
                "id": str(o.id), "alert_type": o.alert_type, "template_name": o.template_name,
                "recipient": o.recipient_masked, "rendered_text": o.rendered_text, "status": o.status,
                "transport": o.transport, "created_at": o.created_at, "sent_at": o.sent_at,
                "scheduled_for": o.scheduled_for, "attempts": o.attempts, "error": o.error,
                "tender_id": str(o.tender_id) if o.tender_id else None,
            }
            for o in rows
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/notifications/preview")
def preview(ctx: Tenant, db: DB, tender_id: uuid.UUID | None = None, kind: str = "closing_48h") -> dict[str, Any]:
    """Render exactly what would be sent, without queueing anything."""
    pref = _pref(db, ctx.org_id, ctx.user.id)
    if kind == "daily_digest":
        params, text, count = notify.build_digest(db, ctx.org_id, pref, utcnow())
        return {"template": T.DAILY_DIGEST, "text": text, "items": count,
                "payload": T.redact_payload(T.meta_payload(pref.phone_e164 or "+910000000000", T.DAILY_DIGEST, params, get_settings().whatsapp_template_language))}
    if kind not in ("closing_48h", "deadline_change", "new_match"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown alert kind")
    q = select(Tender).where(visible_tenders_clause(ctx.org_id), Tender.duplicate_of_id.is_(None))
    now = utcnow()
    if tender_id:
        q = q.where(Tender.id == tender_id)
    else:
        q = (
            q.join(CompanyTenderMatch, CompanyTenderMatch.tender_id == Tender.id)
            .where(CompanyTenderMatch.organization_id == ctx.org_id, Tender.bid_submission_end_at > now)
            .order_by(CompanyTenderMatch.relevance_score.desc())
        )
        # Preview only with a tender that would genuinely trigger this alert type.
        if kind == "closing_48h":
            q = q.where(Tender.bid_submission_end_at <= now + timedelta(hours=48))
        elif kind == "deadline_change":
            q = q.where(Tender.deadline_changed_at.is_not(None))
    tender = db.scalars(q.limit(1)).first()
    if tender is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No open tender currently qualifies for this alert type")
    match, _ = compute_match(db, ctx.org_id, tender)
    db.commit()
    params, text = notify.build_tender_alert(tender, match, kind)
    payload = T.meta_payload(pref.phone_e164 or "+910000000000", T.TENDER_ALERT, params, get_settings().whatsapp_template_language)
    return {"template": T.TENDER_ALERT, "text": text, "tender_id": str(tender.id), "payload": T.redact_payload(payload)}


@router.post("/notifications/test", status_code=201)
def send_test(ctx: Analyst, db: DB) -> dict[str, Any]:
    pref = _pref(db, ctx.org_id, ctx.user.id)
    if not pref.whatsapp_opt_in or not pref.phone_e164 or pref.opted_out_at:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Opt in with a mobile number before sending a test")
    tender = db.scalars(
        select(Tender)
        .join(CompanyTenderMatch, CompanyTenderMatch.tender_id == Tender.id)
        .where(CompanyTenderMatch.organization_id == ctx.org_id, visible_tenders_clause(ctx.org_id))
        .order_by(CompanyTenderMatch.relevance_score.desc())
        .limit(1)
    ).first()
    if tender is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No tender available for a test message")
    match, _ = compute_match(db, ctx.org_id, tender)
    params, text = notify.build_tender_alert(tender, match, "test")
    key = f"{ctx.org_id}:test:{uuid.uuid4().hex}"
    notify.enqueue(db, org_id=ctx.org_id, pref=pref, alert_type="test", dedupe_key=key,
                   template=T.TENDER_ALERT, params=params, rendered=text, tender_id=tender.id)
    transport = get_transport()
    notify.dispatch_pending(db, transport)
    msg = db.scalar(select(NotificationOutbox).where(NotificationOutbox.dedupe_key == key))
    audit(db, ctx, "notifications.test_sent", "notification_outbox", msg.id if msg else None,
          {"transport": transport.name})
    db.commit()
    return {"status": msg.status if msg else "unknown", "transport": transport.name,
            "simulated": transport.name == "simulated", "error": msg.error if msg else None}


# --- Meta WhatsApp webhook --------------------------------------------------


@router.get("/whatsapp/webhook", response_class=PlainTextResponse)
def verify_webhook(
    mode: str = Query(alias="hub.mode", default=""),
    token: str = Query(alias="hub.verify_token", default=""),
    challenge: str = Query(alias="hub.challenge", default=""),
) -> str:
    expected = get_settings().whatsapp_verify_token
    if mode == "subscribe" and expected and hmac.compare_digest(token, expected.get_secret_value()):
        return challenge
    raise HTTPException(status.HTTP_403_FORBIDDEN, "Verification failed")


@router.post("/whatsapp/webhook")
async def receive_webhook(request: Request, db: DB) -> Response:
    secret = get_settings().whatsapp_app_secret
    if secret is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Webhook not configured")
    raw = await request.body()
    signature = request.headers.get("x-hub-signature-256", "")
    expected = "sha256=" + hmac.new(secret.get_secret_value().encode(), raw, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid signature")
    try:
        body = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid JSON") from exc
    notify.process_webhook(db, body)
    db.commit()
    return Response(status_code=200)
