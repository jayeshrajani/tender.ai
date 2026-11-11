from __future__ import annotations

import time
import uuid
from collections import defaultdict, deque
from datetime import timedelta

from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import delete, func, select

from app.config import get_settings
from app.deps import DB, Auth, audit
from app.models import (
    AuthSession,
    Invitation,
    Membership,
    NotificationPreference,
    Organization,
    Role,
    User,
)
from app.schemas import AcceptInviteIn, LoginIn, RegisterIn, SwitchCompanyIn
from app.security import create_session, hash_password, token_hash, verify_password
from app.services.timeutil import utcnow

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

# Simple in-process limiter: 10 attempts per IP+email per 15 minutes.
_attempts: dict[str, deque[float]] = defaultdict(deque)


def _rate_limit(key: str, limit: int = 10, window: int = 900) -> None:
    now = time.monotonic()
    q = _attempts[key]
    while q and now - q[0] > window:
        q.popleft()
    if len(q) >= limit:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many attempts. Try again later.")
    q.append(now)


def _set_cookie(response: Response, token: str) -> None:
    s = get_settings()
    response.set_cookie(
        s.session_cookie_name,
        token,
        max_age=s.session_ttl_hours * 3600,
        httponly=True,
        secure=s.cookie_secure,
        samesite="lax",
        path="/",
    )


def me_payload(db: DB, user: User, active_org_id: uuid.UUID | None) -> dict[str, object]:
    memberships = db.scalars(select(Membership).where(Membership.user_id == user.id)).all()
    active = next((m for m in memberships if m.organization_id == active_org_id), None)
    return {
        "user": {"id": str(user.id), "email": user.email, "full_name": user.full_name},
        "active_company": (
            {
                "id": str(active.organization_id),
                "name": active.organization.legal_name,
                "role": active.role,
                "onboarding_step": active.organization.onboarding_step,
                "onboarding_complete": active.organization.onboarding_completed_at is not None,
                "is_demo": active.organization.is_demo,
            }
            if active
            else None
        ),
        "companies": [
            {"id": str(m.organization_id), "name": m.organization.legal_name, "role": m.role}
            for m in memberships
        ],
    }


@router.post("/register", status_code=201)
def register(body: RegisterIn, request: Request, response: Response, db: DB) -> dict[str, object]:
    _rate_limit(f"register:{request.client.host if request.client else '?'}", limit=5, window=3600)
    email = body.email.lower()
    if db.scalar(select(User.id).where(func.lower(User.email) == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")
    user = User(email=email, full_name=body.full_name.strip(), password_hash=hash_password(body.password))
    org = Organization(legal_name=body.company_name.strip(), contact_email=email, contact_name=user.full_name)
    db.add_all([user, org])
    db.flush()
    db.add(Membership(organization_id=org.id, user_id=user.id, role=Role.owner))
    db.add(NotificationPreference(organization_id=org.id, user_id=user.id))
    token = create_session(db, user, org.id)
    audit(db, None, "company.created", "organization", org.id, {"by": email}, organization_id=org.id)
    db.commit()
    _set_cookie(response, token)
    return me_payload(db, user, org.id)


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response, db: DB) -> dict[str, object]:
    email = body.email.lower()
    _rate_limit(f"login:{request.client.host if request.client else '?'}:{email}")
    user = db.scalar(select(User).where(func.lower(User.email) == email))
    if not verify_password(user, body.password) or user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password")
    first = db.scalar(
        select(Membership).where(Membership.user_id == user.id).order_by(Membership.created_at)
    )
    token = create_session(db, user, first.organization_id if first else None)
    db.commit()
    _set_cookie(response, token)
    return me_payload(db, user, first.organization_id if first else None)


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, db: DB) -> Response:
    token = request.cookies.get(get_settings().session_cookie_name)
    if token:
        db.execute(delete(AuthSession).where(AuthSession.token_hash == token_hash(token)))
        db.commit()
    response.delete_cookie(get_settings().session_cookie_name, path="/")
    response.status_code = 204
    return response


@router.get("/me")
def me(auth: Auth, db: DB) -> dict[str, object]:
    return me_payload(db, auth.user, auth.session.organization_id)


@router.post("/switch-company")
def switch_company(body: SwitchCompanyIn, auth: Auth, db: DB) -> dict[str, object]:
    try:
        org_id = uuid.UUID(body.organization_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid company id") from exc
    membership = db.scalar(
        select(Membership).where(Membership.user_id == auth.user.id, Membership.organization_id == org_id)
    )
    if membership is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You are not a member of that company")
    auth.session.organization_id = org_id
    db.commit()
    return me_payload(db, auth.user, org_id)


def _load_invite(db: DB, token: str) -> Invitation:
    inv = db.scalar(select(Invitation).where(Invitation.token_hash == token_hash(token)))
    if inv is None or inv.accepted_at or inv.revoked_at or inv.expires_at < utcnow():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invitation is invalid or has expired")
    return inv


@router.get("/invitations/{token}")
def invitation_preview(token: str, db: DB) -> dict[str, object]:
    inv = _load_invite(db, token)
    org = db.get(Organization, inv.organization_id)
    exists = db.scalar(select(User.id).where(func.lower(User.email) == inv.email.lower())) is not None
    return {"company": org.legal_name if org else "", "email": inv.email, "role": inv.role, "account_exists": exists}


@router.post("/accept-invite")
def accept_invite(body: AcceptInviteIn, request: Request, response: Response, db: DB) -> dict[str, object]:
    _rate_limit(f"invite:{request.client.host if request.client else '?'}")
    inv = _load_invite(db, body.token)
    user = db.scalar(select(User).where(func.lower(User.email) == inv.email.lower()))
    if user is None:
        if not body.full_name or not body.password:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Name and password are required")
        user = User(email=inv.email.lower(), full_name=body.full_name, password_hash=hash_password(body.password))
        db.add(user)
        db.flush()
    else:
        # Existing accounts must prove ownership with their password.
        if not body.password or not verify_password(user, body.password):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Enter the password for this existing account")
    if not db.scalar(
        select(Membership.id).where(Membership.user_id == user.id, Membership.organization_id == inv.organization_id)
    ):
        db.add(Membership(organization_id=inv.organization_id, user_id=user.id, role=inv.role))
        db.add(NotificationPreference(organization_id=inv.organization_id, user_id=user.id))
    inv.accepted_at = utcnow()
    token = create_session(db, user, inv.organization_id)
    audit(db, None, "member.joined", "user", user.id, {"email": user.email, "role": inv.role},
          organization_id=inv.organization_id)
    db.commit()
    _set_cookie(response, token)
    return me_payload(db, user, inv.organization_id)


INVITE_TTL = timedelta(days=7)
