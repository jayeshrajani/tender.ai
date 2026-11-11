from datetime import UTC, datetime, time

import pytest

from app.services.districts import normalize_district
from app.services.ingestion.normalize import content_hash, dedupe_key, normalize_raw
from app.services.money import format_inr, parse_inr
from app.services.taxonomy import classify
from app.services.timeutil import (
    format_ist,
    in_quiet_hours,
    latest_reanalysis_slot,
    next_digest_slot,
    next_reanalysis_slot,
    parse_ist_datetime,
    slot_key,
)


@pytest.mark.parametrize(
    "text,paise",
    [
        ("₹ 2.45 Cr", 2_45_00_000_00),
        ("245 Lakh", 2_45_00_000_00),
        ("Rs. 24,50,000.00/-", 24_50_000_00),
        ("2.45Cr", 2_45_00_000_00),
        ("150.00 लाख", 1_50_00_000_00),
        ("1.5 करोड़", 1_50_00_000_00),
        ("INR 19.10 crore", 19_10_00_000_00),
    ],
)
def test_parse_inr(text: str, paise: int) -> None:
    assert parse_inr(text) == paise


def test_format_inr_uses_crore_lakh() -> None:
    assert format_inr(12_40_00_000_00) == "₹12.40 Cr"
    assert format_inr(96_00_000_00) == "₹96.00 L"
    assert format_inr(9_500_00) == "₹9,500"
    assert format_inr(None) == "Not stated"


def test_ist_parsing_and_display() -> None:
    dt = parse_ist_datetime("15-Nov-2026 05:30 PM")
    assert dt == datetime(2026, 11, 15, 12, 0, tzinfo=UTC)
    assert format_ist(dt) == "15 Nov 2026, 05:30 PM IST"
    # Date-only deadlines are treated as end of day IST.
    assert parse_ist_datetime("15/11/2026", end_of_day=True) == datetime(2026, 11, 15, 18, 29, tzinfo=UTC)


def test_reanalysis_slots_are_00_08_16_ist() -> None:
    # 07:59 IST → latest slot 00:00 IST, next 08:00 IST
    now = datetime(2026, 11, 11, 2, 29, tzinfo=UTC)
    assert slot_key(latest_reanalysis_slot(now)) == "2026-11-11T00:00+05:30"
    assert slot_key(next_reanalysis_slot(now)) == "2026-11-11T08:00+05:30"
    # 23:00 IST → next slot is 00:00 IST tomorrow
    late = datetime(2026, 11, 11, 17, 30, tzinfo=UTC)
    assert slot_key(latest_reanalysis_slot(late)) == "2026-11-11T16:00+05:30"
    assert slot_key(next_reanalysis_slot(late)) == "2026-11-12T00:00+05:30"
    assert slot_key(next_digest_slot(late)) == "2026-11-12T09:00+05:30"


def test_quiet_hours_across_midnight() -> None:
    start, end = time(22, 0), time(7, 0)
    assert in_quiet_hours(datetime(2026, 11, 11, 17, 0, tzinfo=UTC), start, end)  # 22:30 IST
    assert in_quiet_hours(datetime(2026, 11, 11, 0, 0, tzinfo=UTC), start, end)  # 05:30 IST
    assert not in_quiet_hours(datetime(2026, 11, 11, 6, 0, tzinfo=UTC), start, end)  # 11:30 IST


def test_district_aliases() -> None:
    assert normalize_district("Hoshangabad") == "Narmadapuram"
    assert normalize_district("भोपाल") == "Bhopal"
    assert normalize_district("Indore District") == "Indore"
    assert normalize_district("Atlantis") is None


def test_classification_uses_word_boundaries_and_hindi() -> None:
    assert classify("Construction of CC road in Damoh town")[0] == "roads"
    assert classify("सिंचाई नहर का लाइनिंग कार्य")[0] == "irrigation"
    assert classify("Construction of minor bridge and culverts")[0] == "bridges"


def test_normalize_raw_validates_and_normalises() -> None:
    nt = normalize_raw(
        {"tender_id": " 2026_PWD_1_1 ", "title": "BT road Hoshangabad", "estimated_value": "1.2 Cr",
         "deadline": "20-11-2026 17:00", "source_url": "https://mptenders.gov.in/x"}
    )
    assert nt.source_tender_id == "2026_PWD_1_1"
    assert nt.district == "Narmadapuram"
    assert nt.category_code == "roads"
    assert nt.estimated_value_paise == 1_20_00_000_00
    with pytest.raises(ValueError, match="title"):
        normalize_raw({"tender_id": "x"})
    with pytest.raises(ValueError, match="deadline"):
        normalize_raw({"tender_id": "x", "title": "y", "deadline": "soon"})
    with pytest.raises(ValueError, match="http"):
        normalize_raw({"tender_id": "x", "title": "y", "source_url": "javascript:alert(1)"})


def test_content_hash_and_dedupe_key_stability() -> None:
    a = normalize_raw({"tender_id": "1", "title": "Road", "estimated_value": "10 lakh"})
    b = normalize_raw({"tender_id": "1", "title": "Road ", "estimated_value": "10,00,000"})
    assert content_hash(a) == content_hash(b)
    assert dedupe_key("2026_PWDRB_418203_1", "x") == dedupe_key("2026-PWDRB-418203-1", "y")
