"""WhatsApp message templates (must match templates approved in Meta Business Manager).

Template submission to POST /{API_VERSION}/{WABA_ID}/message_templates is an ops step;
``TEMPLATE_DEFINITIONS`` is the body to submit.
"""

from __future__ import annotations

import re
from typing import Any

from app.models import EligibilityStatus
from app.services.money import format_inr
from app.services.timeutil import format_ist

TENDER_ALERT = "tenderos_tender_alert"
DAILY_DIGEST = "tenderos_daily_digest"

TEMPLATE_DEFINITIONS: dict[str, dict[str, Any]] = {
    TENDER_ALERT: {
        "name": TENDER_ALERT,
        "category": "UTILITY",
        "language": "en",
        "components": [
            {
                "type": "BODY",
                "text": (
                    "{{1}}\n\n{{2}}\nDept: {{3}}\nEstimated value: {{4}}\nEligibility: {{5}}\n"
                    "Submission deadline: {{6}}\nOfficial link: {{7}}\nView or save: {{8}}\n{{9}}"
                ),
            },
            {"type": "FOOTER", "text": "Reply STOP to opt out"},
        ],
    },
    DAILY_DIGEST: {
        "name": DAILY_DIGEST,
        "category": "UTILITY",
        "language": "en",
        "components": [
            {"type": "BODY", "text": "{{1}} tenders worth reviewing today.\n\n{{2}}\n\nOpen TenderOS: {{3}}\n{{4}}"},
            {"type": "FOOTER", "text": "Reply STOP to opt out"},
        ],
    },
}

ELIGIBILITY_LABEL = {
    EligibilityStatus.ELIGIBLE: "Eligible",
    EligibilityStatus.NOT_ELIGIBLE: "Not eligible",
    EligibilityStatus.NEEDS_VERIFICATION: "Needs verification",
}

HEADLINES = {
    "closing_48h": "Closing within 48 hours",
    "deadline_change": "Deadline changed (corrigendum)",
    "new_match": "New tender match",
    "test": "Test alert",
}


def _param(text: str, limit: int = 300) -> str:
    # Meta rejects body params with newlines, tabs or >4 consecutive spaces.
    clean = re.sub(r"[\r\n\t]+", " ", text)
    clean = re.sub(r" {4,}", "   ", clean).strip()
    return clean[: limit - 1] + "…" if len(clean) > limit else clean


def freshness_note(is_demo: bool, retrieval_method: str, imported_at_text: str) -> str:
    if is_demo:
        return "DEMO data - not a real tender."
    if retrieval_method.startswith("manual"):
        return f"Source: manual import on {imported_at_text}; confirm on the official portal before bidding."
    return "Confirm details on the official portal before bidding."


def tender_alert_params(
    *,
    alert_type: str,
    title: str,
    department: str | None,
    value_paise: int | None,
    eligibility_status: str,
    eligibility_summary: str,
    deadline: Any,
    official_url: str | None,
    app_url: str,
    freshness: str,
    previous_deadline: Any = None,
) -> list[str]:
    headline = HEADLINES.get(alert_type, "Tender alert")
    if alert_type == "deadline_change" and previous_deadline is not None:
        headline += f" - was {format_ist(previous_deadline)}"
    status = ELIGIBILITY_LABEL.get(EligibilityStatus(eligibility_status), eligibility_status)
    return [
        _param(f"TenderOS: {headline}", 120),
        _param(title, 250),
        _param(department or "Not stated", 120),
        _param(format_inr(value_paise), 40),
        _param(f"{status} - {eligibility_summary}", 250),
        _param(format_ist(deadline), 60),
        _param(official_url or "Not available", 250),
        _param(app_url, 250),
        _param(freshness, 200),
    ]


def render(template: str, params: list[str]) -> str:
    body = next(c["text"] for c in TEMPLATE_DEFINITIONS[template]["components"] if c["type"] == "BODY")
    for i, p in enumerate(params, start=1):
        body = body.replace("{{" + str(i) + "}}", p)
    return body + "\n\nReply STOP to opt out"


def meta_payload(to_e164: str, template: str, params: list[str], language: str) -> dict[str, Any]:
    return {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to_e164.lstrip("+"),
        "type": "template",
        "template": {
            "name": template,
            "language": {"code": language},
            "components": [
                {"type": "body", "parameters": [{"type": "text", "text": p} for p in params]}
            ],
        },
    }


def mask_phone(e164: str | None) -> str | None:
    if not e164:
        return None
    digits = e164.lstrip("+")
    if len(digits) < 6:
        return "•••"
    return f"+{digits[:2]} {digits[2:4]}•••••{digits[-3:]}"


def redact_payload(payload: dict[str, Any]) -> dict[str, Any]:
    out = dict(payload)
    if "to" in out:
        out["to"] = mask_phone("+" + str(out["to"]))
    return out
