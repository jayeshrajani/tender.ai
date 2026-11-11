"""Alert generation, outbox, dispatch and WhatsApp webhook handling."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import (
    CompanyTenderMatch,
    EligibilityStatus,
    NotificationDelivery,
    NotificationOutbox,
    NotificationPreference,
    SavedTender,
    Tender,
)
from app.services.matching import visible_tenders_clause
from app.services.money import format_inr
from app.services.notifications import templates as T
from app.services.notifications.transport import Transport, get_transport
from app.services.timeutil import format_ist, in_quiet_hours, quiet_hours_end, to_ist, utcnow


def _recipients(db: Session, org_id: uuid.UUID) -> list[NotificationPreference]:
    return list(
        db.scalars(
            select(NotificationPreference).where(
                NotificationPreference.organization_id == org_id,
                NotificationPreference.whatsapp_opt_in.is_(True),
                NotificationPreference.opted_out_at.is_(None),
                NotificationPreference.phone_e164.is_not(None),
            )
        )
    )


def _app_link(tender_id: uuid.UUID) -> str:
    return f"{get_settings().app_url.rstrip('/')}/tenders/{tender_id}"


def build_tender_alert(
    tender: Tender, match: CompanyTenderMatch, alert_type: str
) -> tuple[list[str], str]:
    params = T.tender_alert_params(
        alert_type=alert_type,
        title=tender.title,
        department=tender.department,
        value_paise=tender.estimated_value_paise,
        eligibility_status=match.eligibility_status,
        eligibility_summary=match.eligibility_summary,
        deadline=tender.bid_submission_end_at,
        official_url=tender.source_url,
        app_url=_app_link(tender.id),
        freshness=T.freshness_note(tender.is_demo, tender.retrieval_method, format_ist(tender.imported_at)),
        previous_deadline=tender.previous_deadline_at if alert_type == "deadline_change" else None,
    )
    return params, T.render(T.TENDER_ALERT, params)


def enqueue(
    db: Session,
    *,
    org_id: uuid.UUID,
    pref: NotificationPreference | None,
    alert_type: str,
    dedupe_key: str,
    template: str,
    params: list[str],
    rendered: str,
    tender_id: uuid.UUID | None = None,
) -> bool:
    """Insert into the outbox; returns False if this alert was already queued (dedupe)."""
    settings = get_settings()
    phone = pref.phone_e164 if pref else None
    payload = T.meta_payload(phone or "+910000000000", template, params, settings.whatsapp_template_language)
    stmt = (
        pg_insert(NotificationOutbox)
        .values(
            id=uuid.uuid4(),
            organization_id=org_id,
            user_id=pref.user_id if pref else None,
            tender_id=tender_id,
            alert_type=alert_type,
            dedupe_key=dedupe_key,
            channel="whatsapp",
            template_name=template,
            recipient_masked=T.mask_phone(phone),
            payload=payload,
            rendered_text=rendered,
            status="pending",
            transport="meta" if settings.whatsapp_live else "simulated",
            scheduled_for=utcnow(),
        )
        .on_conflict_do_nothing(index_elements=["dedupe_key"])
        .returning(NotificationOutbox.id)
    )
    return db.execute(stmt).scalar() is not None


def _alertable_matches(db: Session, org_id: uuid.UUID, pref: NotificationPreference) -> Any:
    q = (
        select(Tender, CompanyTenderMatch)
        .join(CompanyTenderMatch, CompanyTenderMatch.tender_id == Tender.id)
        .outerjoin(
            SavedTender,
            and_(SavedTender.tender_id == Tender.id, SavedTender.organization_id == org_id),
        )
        .where(
            CompanyTenderMatch.organization_id == org_id,
            visible_tenders_clause(org_id),
            Tender.duplicate_of_id.is_(None),
            Tender.status == "active",
            (SavedTender.state.is_(None)) | (SavedTender.state != "dismissed"),
        )
    )
    relevant = CompanyTenderMatch.relevance_score >= pref.min_relevance
    statuses = [EligibilityStatus.ELIGIBLE]
    if pref.include_needs_verification:
        statuses.append(EligibilityStatus.NEEDS_VERIFICATION)
    # Saved tenders always alert; otherwise require relevance + an acceptable eligibility state.
    return q.where((SavedTender.state == "saved") | (relevant & CompanyTenderMatch.eligibility_status.in_(statuses)))


def generate_event_alerts(db: Session, org_id: uuid.UUID, now: datetime | None = None) -> dict[str, int]:
    now = now or utcnow()
    stats = {"closing_48h": 0, "deadline_change": 0}
    for pref in _recipients(db, org_id):
        if pref.closing_reminders:
            rows = db.execute(
                _alertable_matches(db, org_id, pref).where(
                    Tender.bid_submission_end_at > now,
                    Tender.bid_submission_end_at <= now + timedelta(hours=48),
                )
            ).all()
            for tender, match in rows:
                params, text = build_tender_alert(tender, match, "closing_48h")
                stats["closing_48h"] += enqueue(
                    db, org_id=org_id, pref=pref, alert_type="closing_48h", tender_id=tender.id,
                    dedupe_key=f"{org_id}:{tender.id}:closing_48h:{pref.user_id}",
                    template=T.TENDER_ALERT, params=params, rendered=text,
                )
        if pref.urgent_alerts:
            rows = db.execute(
                _alertable_matches(db, org_id, pref).where(
                    Tender.deadline_changed_at.is_not(None),
                    Tender.deadline_changed_at >= now - timedelta(days=3),
                    Tender.bid_submission_end_at > now,
                )
            ).all()
            for tender, match in rows:
                params, text = build_tender_alert(tender, match, "deadline_change")
                end = tender.bid_submission_end_at
                stamp = end.astimezone(UTC).strftime("%Y%m%dT%H%M") if end else "none"
                stats["deadline_change"] += enqueue(
                    db, org_id=org_id, pref=pref, alert_type="deadline_change", tender_id=tender.id,
                    dedupe_key=f"{org_id}:{tender.id}:deadline_change:{stamp}:{pref.user_id}",
                    template=T.TENDER_ALERT, params=params, rendered=text,
                )
    return stats


def build_digest(db: Session, org_id: uuid.UUID, pref: NotificationPreference, now: datetime) -> tuple[list[str], str, int]:
    rows = db.execute(
        _alertable_matches(db, org_id, pref)
        .where(Tender.bid_submission_end_at > now)
        .order_by(CompanyTenderMatch.relevance_score.desc())
        .limit(5)
    ).all()
    lines = [
        f"{i}. {t.title[:70]} | {format_inr(t.estimated_value_paise)} | "
        f"{T.ELIGIBILITY_LABEL[EligibilityStatus(m.eligibility_status)]} | due {to_ist(t.bid_submission_end_at):%d %b}"
        for i, (t, m) in enumerate(rows, start=1)
    ]
    any_demo = any(t.is_demo for t, _ in rows)
    params = [
        str(len(rows)),
        T._param(" / ".join(lines) or "No new matches today.", 900),
        f"{get_settings().app_url.rstrip('/')}/dashboard",
        "Includes DEMO data - not real tenders." if any_demo else
        "Coverage is limited to imported sources; confirm on official portals.",
    ]
    return params, T.render(T.DAILY_DIGEST, params), len(rows)


def generate_digests(db: Session, org_id: uuid.UUID, now: datetime | None = None) -> int:
    now = now or utcnow()
    day = to_ist(now).date().isoformat()
    created = 0
    for pref in _recipients(db, org_id):
        if not pref.daily_digest:
            continue
        params, text, count = build_digest(db, org_id, pref, now)
        if count == 0:
            continue
        created += enqueue(
            db, org_id=org_id, pref=pref, alert_type="daily_digest",
            dedupe_key=f"{org_id}:digest:{day}:{pref.user_id}",
            template=T.DAILY_DIGEST, params=params, rendered=text,
        )
    return created


def dispatch_pending(db: Session, transport: Transport | None = None, now: datetime | None = None) -> dict[str, int]:
    now = now or utcnow()
    transport = transport or get_transport()
    stats = {"sent": 0, "simulated": 0, "held": 0, "skipped_opt_out": 0, "failed": 0}
    rows = db.scalars(
        select(NotificationOutbox)
        .where(
            NotificationOutbox.status.in_(("pending", "held_quiet_hours", "retry")),
            NotificationOutbox.scheduled_for <= now,
        )
        .order_by(NotificationOutbox.created_at)
        .limit(500)
        .with_for_update(skip_locked=True)
    ).all()
    for msg in rows:
        pref = (
            db.scalar(
                select(NotificationPreference).where(
                    NotificationPreference.organization_id == msg.organization_id,
                    NotificationPreference.user_id == msg.user_id,
                )
            )
            if msg.user_id
            else None
        )
        if pref is None or not pref.whatsapp_opt_in or pref.opted_out_at is not None or not pref.phone_e164:
            msg.status = "skipped_opt_out"
            stats["skipped_opt_out"] += 1
            continue
        if msg.alert_type != "test" and in_quiet_hours(now, pref.quiet_hours_start, pref.quiet_hours_end):
            msg.status = "held_quiet_hours"
            msg.scheduled_for = quiet_hours_end(now, pref.quiet_hours_end)  # type: ignore[arg-type]
            stats["held"] += 1
            continue
        payload = dict(msg.payload)
        payload["to"] = pref.phone_e164.lstrip("+")
        msg.attempts += 1
        result = transport.send(payload)
        msg.transport = transport.name
        if result.ok:
            msg.status = result.status
            msg.sent_at = now
            msg.provider_message_id = result.provider_message_id
            msg.error = None
            stats[result.status] += 1
        else:
            msg.error = result.error
            msg.status = "retry" if msg.attempts < 3 else "failed"
            msg.scheduled_for = now + timedelta(minutes=5 * msg.attempts)
            stats["failed"] += 1
        # Never persist the full phone number in the stored payload.
        msg.payload = T.redact_payload(payload)
    db.flush()
    return stats


STOP_WORDS = {"stop", "unsubscribe", "cancel", "बंद", "रोकें"}


def process_webhook(db: Session, body: dict[str, Any]) -> dict[str, int]:
    """Idempotent: (provider_message_id, status) is unique in notification_deliveries."""
    stats = {"statuses": 0, "duplicates": 0, "opt_outs": 0}
    for entry in body.get("entry", []) or []:
        for change in entry.get("changes", []) or []:
            value = change.get("value", {}) or {}
            for st in value.get("statuses", []) or []:
                mid, status = st.get("id"), st.get("status")
                if not mid or not status:
                    continue
                outbox = db.scalar(select(NotificationOutbox).where(NotificationOutbox.provider_message_id == mid))
                ts = st.get("timestamp")
                occurred = datetime.fromtimestamp(int(ts), tz=UTC) if ts else utcnow()
                errors = st.get("errors") or [{}]
                res = db.execute(
                    pg_insert(NotificationDelivery)
                    .values(
                        id=uuid.uuid4(),
                        outbox_id=outbox.id if outbox else None,
                        organization_id=outbox.organization_id if outbox else None,
                        provider_message_id=mid,
                        status=status,
                        occurred_at=occurred,
                        error_code=str(errors[0].get("code")) if errors[0].get("code") else None,
                    )
                    .on_conflict_do_nothing(index_elements=["provider_message_id", "status"])
                    .returning(NotificationDelivery.id)
                ).scalar()
                if res is not None:
                    stats["statuses"] += 1
                    if outbox and status in ("delivered", "read", "failed"):
                        outbox.status = status
                else:
                    stats["duplicates"] += 1
            for message in value.get("messages", []) or []:
                text = ((message.get("text") or {}).get("body") or "").strip().lower()
                if text in STOP_WORDS and message.get("from"):
                    phone = "+" + str(message["from"]).lstrip("+")
                    for pref in db.scalars(
                        select(NotificationPreference).where(NotificationPreference.phone_e164 == phone)
                    ):
                        pref.whatsapp_opt_in = False
                        pref.opted_out_at = utcnow()
                        stats["opt_outs"] += 1
    db.flush()
    return stats
