"""Request dependencies: authentication, tenant context and role checks."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Annotated, Any

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import AuditEvent, AuthSession, Membership, Organization, Role, User
from app.security import token_hash
from app.services.timeutil import utcnow

ROLE_RANK = {Role.viewer: 1, Role.analyst: 2, Role.admin: 3, Role.owner: 4}

DB = Annotated[Session, Depends(get_db)]


@dataclass
class AuthContext:
    user: User
    session: AuthSession


@dataclass
class TenantContext:
    user: User
    session: AuthSession
    membership: Membership

    @property
    def org_id(self) -> uuid.UUID:
        return self.membership.organization_id

    @property
    def org(self) -> Organization:
        return self.membership.organization

    @property
    def role(self) -> str:
        return self.membership.role


def get_auth(request: Request, db: DB) -> AuthContext:
    token = request.cookies.get(get_settings().session_cookie_name)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed in")
    sess = db.scalar(select(AuthSession).where(AuthSession.token_hash == token_hash(token)))
    now = utcnow()
    if sess is None or sess.expires_at < now:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired")
    user = db.get(User, sess.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Account disabled")
    if now - sess.last_seen_at > timedelta(minutes=5):
        sess.last_seen_at = now
        db.commit()
    return AuthContext(user, sess)


Auth = Annotated[AuthContext, Depends(get_auth)]


def get_tenant(auth: Auth, db: DB) -> TenantContext:
    """Resolve the active company from the server-side session and re-check membership."""
    if auth.session.organization_id is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "No active company. Create or join a company first.")
    membership = db.scalar(
        select(Membership).where(
            Membership.user_id == auth.user.id,
            Membership.organization_id == auth.session.organization_id,
        )
    )
    if membership is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You are no longer a member of this company")
    return TenantContext(auth.user, auth.session, membership)


Tenant = Annotated[TenantContext, Depends(get_tenant)]


def require_role(minimum: Role) -> Callable[[TenantContext], TenantContext]:
    def checker(ctx: Tenant) -> TenantContext:
        if ROLE_RANK[Role(ctx.role)] < ROLE_RANK[minimum]:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Requires {minimum.value} role or higher")
        return ctx

    return checker


Analyst = Annotated[TenantContext, Depends(require_role(Role.analyst))]
Admin = Annotated[TenantContext, Depends(require_role(Role.admin))]
Owner = Annotated[TenantContext, Depends(require_role(Role.owner))]


def audit(
    db: Session,
    ctx: TenantContext | AuthContext | None,
    action: str,
    entity_type: str | None = None,
    entity_id: Any = None,
    data: dict[str, Any] | None = None,
    *,
    organization_id: uuid.UUID | None = None,
) -> None:
    org_id = organization_id or (ctx.org_id if isinstance(ctx, TenantContext) else None)
    db.add(
        AuditEvent(
            organization_id=org_id,
            actor_user_id=ctx.user.id if ctx else None,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id is not None else None,
            data=data or {},
        )
    )
