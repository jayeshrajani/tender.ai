from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Response, status
from fastapi.responses import Response as RawResponse
from sqlalchemy import func, select

from app.deps import DB, Admin, Owner, Tenant, audit
from app.models import AuditEvent, AuthSession, Invitation, Membership, Role
from app.schemas import InviteIn, RoleChangeIn
from app.security import new_token, token_hash
from app.services.storage import get_storage, verify_download
from app.services.timeutil import utcnow

router = APIRouter(prefix="/api/v1", tags=["team"])

ROLE_PERMISSIONS = {
    "owner": "Everything, including role changes and removing admins",
    "admin": "Edit company profile, documents, imports, invitations, run reanalysis",
    "analyst": "Import tenders, save/dismiss, notes, review extracted criteria",
    "viewer": "Read-only access to tenders, eligibility and sources",
}


@router.get("/team")
def team(ctx: Tenant, db: DB) -> dict[str, Any]:
    members = db.scalars(
        select(Membership).where(Membership.organization_id == ctx.org_id).order_by(Membership.created_at)
    ).all()
    invites = db.scalars(
        select(Invitation).where(
            Invitation.organization_id == ctx.org_id,
            Invitation.accepted_at.is_(None),
            Invitation.revoked_at.is_(None),
            Invitation.expires_at > utcnow(),
        )
    ).all()
    return {
        "members": [
            {"id": str(m.id), "user_id": str(m.user_id), "full_name": m.user.full_name, "email": m.user.email,
             "role": m.role, "joined_at": m.created_at, "last_login_at": m.user.last_login_at,
             "is_you": m.user_id == ctx.user.id}
            for m in members
        ],
        "invitations": [
            {"id": str(i.id), "email": i.email, "role": i.role, "expires_at": i.expires_at} for i in invites
        ],
        "roles": ROLE_PERMISSIONS,
        "your_role": ctx.role,
    }


@router.post("/team/invitations", status_code=201)
def invite(body: InviteIn, ctx: Admin, db: DB) -> dict[str, Any]:
    token = new_token()
    inv = Invitation(
        organization_id=ctx.org_id, email=body.email.lower(), role=body.role, token_hash=token_hash(token),
        invited_by_id=ctx.user.id, expires_at=utcnow() + timedelta(days=7),
    )
    db.add(inv)
    audit(db, ctx, "member.invited", "invitation", None, {"email": body.email, "role": body.role})
    db.commit()
    # No email service in V1: the admin shares this one-time link directly.
    return {"id": str(inv.id), "invite_path": f"/invite/{token}", "expires_at": inv.expires_at}


@router.delete("/team/invitations/{inv_id}", status_code=204)
def revoke_invite(inv_id: uuid.UUID, ctx: Admin, db: DB) -> Response:
    inv = db.scalar(select(Invitation).where(Invitation.id == inv_id, Invitation.organization_id == ctx.org_id))
    if inv is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    inv.revoked_at = utcnow()
    audit(db, ctx, "member.invite_revoked", "invitation", inv.id, {"email": inv.email})
    db.commit()
    return Response(status_code=204)


def _owners(db: DB, org_id: uuid.UUID) -> int:
    return db.scalar(
        select(func.count()).select_from(Membership).where(Membership.organization_id == org_id, Membership.role == Role.owner)
    ) or 0


@router.patch("/team/members/{member_id}")
def change_role(member_id: uuid.UUID, body: RoleChangeIn, ctx: Owner, db: DB) -> dict[str, Any]:
    m = db.scalar(select(Membership).where(Membership.id == member_id, Membership.organization_id == ctx.org_id))
    if m is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    if m.role == Role.owner and body.role != Role.owner and _owners(db, ctx.org_id) <= 1:
        raise HTTPException(status.HTTP_409_CONFLICT, "A company must keep at least one owner")
    before = m.role
    m.role = body.role
    audit(db, ctx, "member.role_changed", "membership", m.id, {"email": m.user.email, "from": before, "to": body.role})
    db.commit()
    return {"id": str(m.id), "role": m.role}


@router.delete("/team/members/{member_id}", status_code=204)
def remove_member(member_id: uuid.UUID, ctx: Admin, db: DB) -> Response:
    m = db.scalar(select(Membership).where(Membership.id == member_id, Membership.organization_id == ctx.org_id))
    if m is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    if m.role in (Role.owner, Role.admin) and ctx.role != Role.owner:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only an owner can remove owners or admins")
    if m.role == Role.owner and _owners(db, ctx.org_id) <= 1:
        raise HTTPException(status.HTTP_409_CONFLICT, "A company must keep at least one owner")
    # End any sessions pointing at this company for the removed user.
    for s in db.scalars(
        select(AuthSession).where(AuthSession.user_id == m.user_id, AuthSession.organization_id == ctx.org_id)
    ):
        s.organization_id = None
    audit(db, ctx, "member.removed", "membership", m.id, {"email": m.user.email, "role": m.role})
    db.delete(m)
    db.commit()
    return Response(status_code=204)


@router.get("/team/audit")
def audit_log(
    ctx: Admin, db: DB, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200)
) -> dict[str, Any]:
    q = select(AuditEvent).where(AuditEvent.organization_id == ctx.org_id)
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    rows = db.scalars(q.order_by(AuditEvent.created_at.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    return {
        "items": [
            {"id": str(e.id), "action": e.action, "actor": e.actor.full_name if e.actor else "System",
             "entity_type": e.entity_type, "entity_id": e.entity_id, "data": e.data, "created_at": e.created_at}
            for e in rows
        ],
        "total": total,
    }


@router.get("/files/{token}")
def download(token: str, ctx: Tenant) -> RawResponse:
    """Signed, short-lived and still bound to the caller's active company."""
    try:
        data = verify_download(token)
    except PermissionError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc
    if data["o"] != str(ctx.org_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Link belongs to a different company")
    body = get_storage().get(data["k"])
    safe_name = data["f"].replace('"', "")
    return RawResponse(
        body,
        media_type=data["c"],
        headers={
            "Content-Disposition": f'inline; filename="{safe_name}"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
            "Content-Security-Policy": "default-src 'none'; sandbox",
        },
    )
