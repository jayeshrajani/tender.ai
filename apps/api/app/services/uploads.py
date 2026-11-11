"""Upload validation by extension AND magic bytes. Macro-enabled files are rejected."""

from __future__ import annotations

import hashlib
import io
import zipfile
from dataclasses import dataclass
from pathlib import PurePath

from app.config import get_settings


class UploadError(ValueError):
    pass


@dataclass(frozen=True)
class ValidatedUpload:
    filename: str
    ext: str
    content_type: str
    size: int
    sha256: str
    data: bytes


_TYPES = {
    "pdf": "application/pdf",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "csv": "text/csv",
}


def _sniff(ext: str, data: bytes) -> bool:
    if ext == "pdf":
        return data[:1024].lstrip().startswith(b"%PDF-")
    if ext in ("jpg", "jpeg"):
        return data.startswith(b"\xff\xd8\xff")
    if ext == "png":
        return data.startswith(b"\x89PNG\r\n\x1a\n")
    if ext == "xlsx":
        if not data.startswith(b"PK\x03\x04"):
            return False
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                names = set(zf.namelist())
        except zipfile.BadZipFile:
            return False
        if any(n.lower().endswith("vbaproject.bin") for n in names):
            raise UploadError("Macro-enabled workbooks are not accepted.")
        return "[Content_Types].xml" in names and "xl/workbook.xml" in names
    if ext == "csv":
        head = data[:4096]
        if b"\x00" in head:
            return False
        try:
            head.decode("utf-8-sig")
        except UnicodeDecodeError:
            try:
                head.decode("cp1252")
            except UnicodeDecodeError:
                return False
        return True
    return False


def safe_filename(name: str) -> str:
    base = PurePath(name.replace("\\", "/")).name
    cleaned = "".join(ch for ch in base if ch.isalnum() or ch in "._- ()").strip()
    return cleaned[:200] or "upload"


def validate_upload(filename: str | None, data: bytes, allowed: set[str]) -> ValidatedUpload:
    if not filename:
        raise UploadError("A filename is required.")
    name = safe_filename(filename)
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext not in allowed:
        raise UploadError(f"'.{ext or '?'}' files are not accepted. Allowed: {', '.join(sorted(allowed))}.")
    limit = get_settings().max_upload_mb * 1024 * 1024
    if not data:
        raise UploadError("The file is empty.")
    if len(data) > limit:
        raise UploadError(f"File exceeds the {get_settings().max_upload_mb} MB limit.")
    if not _sniff(ext, data):
        raise UploadError(f"File content does not match a valid .{ext} file.")
    return ValidatedUpload(
        filename=name,
        ext="jpg" if ext == "jpeg" else ext,
        content_type=_TYPES[ext],
        size=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
        data=data,
    )
