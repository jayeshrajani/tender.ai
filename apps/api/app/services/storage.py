"""Object storage (local filesystem or S3/MinIO) with short-lived signed download tokens."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import uuid
from pathlib import Path
from typing import Protocol

from app.config import get_settings


class Storage(Protocol):
    def put(self, key: str, data: bytes, content_type: str) -> None: ...
    def get(self, key: str) -> bytes: ...


class LocalStorage:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        p = (self.root / key).resolve()
        if self.root not in p.parents:
            raise ValueError("invalid storage key")
        return p

    def put(self, key: str, data: bytes, content_type: str) -> None:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()


class S3Storage:
    def __init__(self) -> None:
        import boto3

        s = get_settings()
        self.bucket = s.s3_bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=s.s3_endpoint_url,
            aws_access_key_id=s.s3_access_key.get_secret_value() if s.s3_access_key else None,
            aws_secret_access_key=s.s3_secret_key.get_secret_value() if s.s3_secret_key else None,
            region_name=s.s3_region,
        )

    def put(self, key: str, data: bytes, content_type: str) -> None:
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type)

    def get(self, key: str) -> bytes:
        return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()


_storage: Storage | None = None


def get_storage() -> Storage:
    global _storage
    if _storage is None:
        s = get_settings()
        _storage = S3Storage() if s.storage_backend == "s3" else LocalStorage(s.storage_local_dir)
    return _storage


def new_key(prefix: str, org_id: uuid.UUID | None, ext: str) -> str:
    scope = str(org_id) if org_id else "global"
    return f"{prefix}/{scope}/{uuid.uuid4().hex}.{ext}"


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def sign_download(key: str, org_id: uuid.UUID, filename: str, content_type: str, ttl: int = 300) -> str:
    """Issue a token only after the caller's tenant authorisation has been checked."""
    payload = _b64(
        json.dumps(
            {"k": key, "o": str(org_id), "f": filename, "c": content_type, "e": int(time.time()) + ttl},
            separators=(",", ":"),
        ).encode()
    )
    secret = get_settings().signing_secret.get_secret_value().encode()
    sig = _b64(hmac.new(secret, payload.encode(), hashlib.sha256).digest())
    return f"{payload}.{sig}"


def verify_download(token: str) -> dict[str, str]:
    try:
        payload, sig = token.split(".", 1)
    except ValueError as exc:
        raise PermissionError("malformed token") from exc
    secret = get_settings().signing_secret.get_secret_value().encode()
    expected = _b64(hmac.new(secret, payload.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(expected, sig):
        raise PermissionError("bad signature")
    data = json.loads(_unb64(payload))
    if int(data["e"]) < time.time():
        raise PermissionError("link expired")
    return data
