from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

os.environ.setdefault("TENDEROS_DATABASE_URL", "postgresql+psycopg://localhost:5432/tenderos_test")
os.environ["TENDEROS_STORAGE_LOCAL_DIR"] = str(Path(__file__).parent / ".storage")
os.environ["TENDEROS_WHATSAPP_MODE"] = "simulated"
os.environ["TENDEROS_WHATSAPP_APP_SECRET"] = "test-app-secret"
os.environ["TENDEROS_WHATSAPP_VERIFY_TOKEN"] = "test-verify-token"

assert "test" in os.environ["TENDEROS_DATABASE_URL"], "Refusing to run tests against a non-test database"

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.db import SessionLocal, engine  # noqa: E402
from app.models import Base  # noqa: E402

API_DIR = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session", autouse=True)
def _migrate() -> None:
    env = {**os.environ}
    for cmd in (["downgrade", "base"], ["upgrade", "head"]):
        subprocess.run([sys.executable, "-m", "alembic", *cmd], cwd=API_DIR, env=env, check=True, capture_output=True)


@pytest.fixture()
def db() -> Iterator[Session]:
    tables = ", ".join(t.name for t in reversed(Base.metadata.sorted_tables))
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    from app.seed.__main__ import seed_sources, seed_taxonomy

    session = SessionLocal()
    seed_taxonomy(session)
    seed_sources(session, reanchor=True)
    session.commit()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def seeded(db: Session) -> Session:
    from app.seed.__main__ import seed_company_malwa, seed_company_narmada
    from app.services import jobs, matching

    jobs.refresh_sources(db, "test-seed", trigger="manual")
    seed_company_narmada(db)
    seed_company_malwa(db)
    db.commit()
    matching.recompute_all(db)
    db.commit()
    return db


class Client(TestClient):
    def login(self, email: str, password: str = "tenderos-demo-2026") -> dict:
        r = self.post("/api/v1/auth/login", json={"email": email, "password": password})
        assert r.status_code == 200, r.text
        return r.json()


@pytest.fixture()
def client_factory(seeded: Session):  # type: ignore[no-untyped-def]
    from app.main import app

    def make() -> Client:
        return Client(app, headers={"X-Requested-With": "tenderos"})

    return make
