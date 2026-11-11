"""Provider-neutral AI extraction seam.

Disabled by default (TENDEROS_AI_PROVIDER=none). Any implementation must:
- run only after deterministic parsing and only over text that exists in the source;
- return JSON validated against ``AIRequirement``;
- cite document, page and verbatim quote (quotes not found on that page are dropped);
- emit requirements as ``needs_review`` so they can never create or override a
  confirmed mandatory failure.
"""

from __future__ import annotations

from typing import Literal, Protocol

from pydantic import BaseModel, Field

from app.config import get_settings
from app.services.extraction.nit import PageText
from app.services.ingestion.base import RequirementSpec


class AIRequirement(BaseModel):
    requirement_type: Literal[
        "annual_turnover", "similar_work", "contractor_registration", "certificate", "solvency",
        "equipment", "bid_capacity", "information",
    ]
    label: str = Field(max_length=240)
    operator: Literal["gte", "lte", "eq", "exists", "info"]
    threshold_value_paise: int | None = None
    threshold_text: str | None = Field(default=None, max_length=120)
    unit: Literal["paise", "count", "years", "class", "none"] | None = None
    page_number: int = Field(ge=1)
    clause_ref: str | None = Field(default=None, max_length=60)
    evidence_quote: str = Field(min_length=8, max_length=400)


class AIExtractionResult(BaseModel):
    requirements: list[AIRequirement]


class AIExtractor(Protocol):
    def extract(self, pages: list[PageText], doc_ref: str) -> AIExtractionResult: ...


def get_ai_extractor() -> AIExtractor | None:
    if get_settings().ai_provider == "none":
        return None
    raise NotImplementedError(
        f"AI provider '{get_settings().ai_provider}' is not implemented; set TENDEROS_AI_PROVIDER=none"
    )


def grounded(result: AIExtractionResult, pages: list[PageText], doc_ref: str) -> list[RequirementSpec]:
    """Keep only requirements whose quote literally appears on the cited page."""
    by_page = {p.number: " ".join(p.text.split()) for p in pages}
    out: list[RequirementSpec] = []
    for r in result.requirements:
        page_text = by_page.get(r.page_number, "")
        if " ".join(r.evidence_quote.split()) not in page_text:
            continue
        out.append(
            RequirementSpec(
                requirement_type=r.requirement_type,
                label=r.label,
                operator=r.operator,
                mandatory=r.operator != "info",
                threshold_value=r.threshold_value_paise,
                threshold_text=r.threshold_text,
                unit=r.unit,
                document_ref=doc_ref,
                page_number=r.page_number,
                clause_ref=r.clause_ref,
                evidence_quote=r.evidence_quote,
                extraction_method="ai",
                verification_status="needs_review",
            )
        )
    return out
