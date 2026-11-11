"""Concrete source adapters.

Pull-capable: DemoFixtureAdapter (enabled), OfficialFeedAdapter and MPPublicHomepageAdapter
(both DISABLED until authorised). Push-only: manual CSV and document imports, which are
executed through ``csv_import`` and ``document_import`` by an operator.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime
from functools import cached_property

from app.models import PermissionStatus, SourceProvider
from app.services.ingestion.base import (
    AdapterHealth,
    ChangeRecord,
    DocumentRef,
    NormalizedTender,
    SourceAdapter,
    SourceNotAuthorizedError,
)
from app.services.timeutil import today_ist


class DemoFixtureAdapter(SourceAdapter):
    code = "demo_fixture"
    pull_capable = True

    def __init__(self, anchor: date | None = None) -> None:
        self.anchor = anchor or today_ist()

    @cached_property
    def _records(self) -> dict[str, tuple[NormalizedTender, list[ChangeRecord]]]:
        from app.seed.demo_tenders import build

        return {nt.source_tender_id: (nt, ch) for nt, ch in build(self.anchor)}

    def health(self) -> AdapterHealth:
        return AdapterHealth(True, True, True, "DEMO fixtures – not real tenders.")

    def discover(self, since: datetime | None) -> Iterable[str]:
        return list(self._records)

    def fetch_metadata(self, source_tender_id: str) -> NormalizedTender:
        return self._records[source_tender_id][0]

    def fetch_documents(self, source_tender_id: str) -> list[DocumentRef]:
        return list(self._records[source_tender_id][0].documents)

    def fetch_changes(self, source_tender_id: str) -> list[ChangeRecord]:
        return list(self._records[source_tender_id][1])


class _PushOnlyAdapter(SourceAdapter):
    """Operator-driven imports. The scheduler never pulls from these."""

    pull_capable = False

    def health(self) -> AdapterHealth:
        return AdapterHealth(
            True, True, True, "Operator-attested manual import; coverage = whatever operators import."
        )

    def discover(self, since: datetime | None) -> Iterable[str]:
        return []

    def fetch_metadata(self, source_tender_id: str) -> NormalizedTender:
        raise SourceNotAuthorizedError("Manual sources are push-only")

    def fetch_documents(self, source_tender_id: str) -> list[DocumentRef]:
        return []

    def fetch_changes(self, source_tender_id: str) -> list[ChangeRecord]:
        return []


class ManualCSVImportAdapter(_PushOnlyAdapter):
    code = "manual_csv"


class ManualDocumentImportAdapter(_PushOnlyAdapter):
    code = "manual_document"


class _GatedAdapter(SourceAdapter):
    """Disabled until written authorisation, documentation and credentials are recorded."""

    pull_capable = True
    required_config: tuple[str, ...] = (
        "authorization_reference",
        "integration_documentation",
        "credentials_configured",
        "permitted_usage",
    )

    def __init__(self, source: SourceProvider) -> None:
        self.source = source

    def _missing(self) -> list[str]:
        cfg = self.source.config or {}
        return [k for k in self.required_config if not cfg.get(k)]

    def health(self) -> AdapterHealth:
        missing = self._missing()
        authorized = self.source.permission_status == PermissionStatus.authorized and not missing
        if not self.source.enabled:
            msg = "Disabled: automated collection is not authorised."
        elif not authorized:
            msg = "Disabled: missing " + ", ".join(missing or ["authorisation"]) + "."
        else:
            msg = "Authorised, but no feed client has been implemented for the supplied specification."
        return AdapterHealth(self.source.enabled, not missing, authorized, msg)

    def _refuse(self) -> None:
        raise SourceNotAuthorizedError(self.health().message)

    def discover(self, since: datetime | None) -> Iterable[str]:
        self._refuse()
        return []

    def fetch_metadata(self, source_tender_id: str) -> NormalizedTender:
        self._refuse()
        raise AssertionError

    def fetch_documents(self, source_tender_id: str) -> list[DocumentRef]:
        self._refuse()
        return []

    def fetch_changes(self, source_tender_id: str) -> list[ChangeRecord]:
        self._refuse()
        return []


class OfficialFeedAdapter(_GatedAdapter):
    """Generic seam for a feed provided/authorised by NIC or a government authority.

    No endpoint is assumed. A concrete client must be written against the official
    specification once it is supplied in writing.
    """

    code = "official_feed_mp"


class MPPublicHomepageAdapter(_GatedAdapter):
    """Latest-tender/corrigendum summaries on https://mptenders.gov.in/ (partial coverage).

    Never solves or bypasses CAPTCHA, never claims to retrieve all active tenders.
    """

    code = "mp_public_homepage"


def get_adapter(source: SourceProvider) -> SourceAdapter | None:
    match source.adapter:
        case "demo_fixture":
            anchor = (source.config or {}).get("anchor_date")
            return DemoFixtureAdapter(date.fromisoformat(anchor) if anchor else None)
        case "manual_csv":
            return ManualCSVImportAdapter()
        case "manual_document":
            return ManualDocumentImportAdapter()
        case "official_feed_mp":
            return OfficialFeedAdapter(source)
        case "mp_public_homepage":
            return MPPublicHomepageAdapter(source)
    return None
