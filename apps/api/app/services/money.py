"""Indian money handling. All amounts are integer paise; never floats."""

import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

PAISE_PER_RUPEE = 100
LAKH = 100_000
CRORE = 10_000_000

_UNIT_PATTERNS: tuple[tuple[re.Pattern[str], int], ...] = (
    (re.compile(r"(?<=[\d\s.])(crores?|cr\.?|करोड़)\s*$", re.I), CRORE),
    (re.compile(r"(?<=[\d\s.])(lakhs?|lacs?|lac|lk|लाख)\s*$", re.I), LAKH),
    (re.compile(r"(?<=[\d\s.])(thousand|k|हजार)\s*$", re.I), 1_000),
)


def rupees_to_paise(rupees: Decimal | int | str) -> int:
    value = Decimal(str(rupees)) * PAISE_PER_RUPEE
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def parse_inr(text: str | int | None) -> int | None:
    """Parse '₹ 2.45 Cr', '245 Lakh', 'Rs. 24,50,000.00', '24500000' → paise."""
    if text is None:
        return None
    if isinstance(text, int):
        return text * PAISE_PER_RUPEE
    s = str(text).strip()
    if not s:
        return None
    s = re.sub(r"(₹|rs\.?|inr|रु\.?|रुपये)", "", s, flags=re.I).strip()
    s = s.replace("/-", "").strip()
    multiplier = 1
    for pattern, mult in _UNIT_PATTERNS:
        if pattern.search(s):
            multiplier = mult
            s = pattern.sub("", s).strip()
            break
    s = s.replace(",", "").replace(" ", "")
    try:
        amount = Decimal(s)
    except InvalidOperation:
        return None
    if amount < 0:
        return None
    return rupees_to_paise(amount * multiplier)


def format_inr(paise: int | None) -> str:
    """Compact Indian representation: ₹2.45 Cr, ₹48.6 L, ₹9,500."""
    if paise is None:
        return "Not stated"
    rupees = Decimal(paise) / PAISE_PER_RUPEE
    if rupees >= CRORE:
        return f"₹{(rupees / CRORE).quantize(Decimal('0.01'))} Cr"
    if rupees >= LAKH:
        return f"₹{(rupees / LAKH).quantize(Decimal('0.01'))} L"
    return f"₹{group_indian(int(rupees))}"


def group_indian(n: int) -> str:
    s = str(abs(n))
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        s = ",".join(parts) + "," + tail
    return ("-" if n < 0 else "") + s
