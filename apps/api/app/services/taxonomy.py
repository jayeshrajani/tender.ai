"""Construction work taxonomy with English + Hindi synonyms used for classification."""

import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Sub:
    code: str
    name: str
    keywords: tuple[str, ...] = ()


@dataclass(frozen=True)
class Cat:
    code: str
    name: str
    name_hi: str
    keywords: tuple[str, ...]
    subs: tuple[Sub, ...] = field(default_factory=tuple)


CATEGORIES: tuple[Cat, ...] = (
    Cat(
        "roads",
        "Roads",
        "सड़क",
        ("road", "highway", "bitumen", "bituminous", "bt road", "cc road", "pmgsy", "wbm",
         "resurfacing", "carpet", "sadak", "सड़क", "सडक", "मार्ग", "डामरीकरण", "डामर"),
        (
            Sub("roads_bituminous", "Bituminous / BT roads", ("bitumen", "bituminous", "bt ", "dbm", "bc ", "डामर")),
            Sub("roads_cc", "Cement concrete roads", ("cc road", "cement concrete road", "सीसी रोड")),
            Sub("roads_rural", "Rural roads (PMGSY / MMGSY)", ("pmgsy", "mmgsy", "rural road", "ग्रामीण सड़क")),
            Sub("roads_widening", "Widening & strengthening", ("widening", "strengthening", "चौड़ीकरण")),
        ),
    ),
    Cat(
        "bridges",
        "Bridges",
        "पुल",
        ("bridge", "culvert", "rob", "rub", "flyover", "causeway", "पुल", "पुलिया", "सेतु"),
        (
            Sub("bridges_major", "Major bridges", ("major bridge", "high level bridge", "वृहद पुल")),
            Sub("bridges_minor", "Minor bridges & culverts", ("culvert", "minor bridge", "पुलिया")),
            Sub("bridges_rob", "ROB / RUB / flyovers", ("rob", "rub", "flyover", "over bridge")),
        ),
    ),
    Cat(
        "rcc",
        "RCC & structures",
        "आरसीसी",
        ("rcc", "reinforced cement concrete", "retaining wall", "structural", "overhead tank",
         "आरसीसी"),
        (
            Sub("rcc_retaining", "Retaining walls", ("retaining wall", "रिटेनिंग")),
            Sub("rcc_tanks", "Overhead / sump tanks", ("overhead tank", "ohsr", "ohwt", "sump", "टंकी")),
        ),
    ),
    Cat(
        "drains",
        "Drains",
        "नाली",
        ("drain", "nala", "nallah", "storm water", "stormwater", "नाली", "नाला"),
        (
            Sub("drains_storm", "Storm water drains", ("storm water", "stormwater", "swd")),
            Sub("drains_covered", "Covered / RCC drains", ("covered drain", "rcc drain")),
        ),
    ),
    Cat(
        "buildings",
        "Buildings",
        "भवन",
        ("building", "school", "hostel", "hospital", "office", "anganwadi", "auditorium",
         "residential", "quarters", "भवन", "छात्रावास", "विद्यालय"),
        (
            Sub("buildings_institutional", "Institutional buildings", ("school", "hostel", "college", "छात्रावास")),
            Sub("buildings_health", "Health facilities", ("hospital", "phc", "chc", "health centre")),
            Sub("buildings_residential", "Residential quarters", ("quarters", "residential", "आवास")),
        ),
    ),
    Cat(
        "electrical",
        "Electrical",
        "विद्युत",
        ("electrical", "electrification", "street light", "substation", "transformer", "solar",
         "विद्युत", "विद्युतीकरण"),
        (
            Sub("electrical_internal", "Internal electrification", ("internal electrification", "wiring")),
            Sub("electrical_street", "Street lighting", ("street light", "streetlight", "high mast")),
        ),
    ),
    Cat(
        "water_supply",
        "Water supply",
        "जल प्रदाय",
        ("water supply", "pipeline", "jal jeevan", "jjm", "distribution network", "intake well",
         "wtp", "water treatment", "जल प्रदाय", "पेयजल", "नल जल"),
        (
            Sub("water_pipeline", "Pipelines & distribution", ("pipeline", "distribution", "di pipe", "hdpe")),
            Sub("water_treatment", "Water treatment plants", ("wtp", "water treatment", "filter plant")),
            Sub("water_jjm", "Jal Jeevan Mission schemes", ("jal jeevan", "jjm", "नल जल")),
        ),
    ),
    Cat(
        "sewerage",
        "Sewerage",
        "सीवरेज",
        ("sewer", "sewerage", "stp", "sewage", "manhole", "सीवर", "सीवरेज"),
        (
            Sub("sewer_network", "Sewer networks", ("sewer line", "sewer network", "manhole")),
            Sub("sewer_stp", "Sewage treatment plants", ("stp", "sewage treatment")),
        ),
    ),
    Cat(
        "irrigation",
        "Irrigation",
        "सिंचाई",
        ("irrigation", "canal", "dam", "weir", "stop dam", "check dam", "tank", "minor irrigation",
         "सिंचाई", "नहर", "बांध", "तालाब"),
        (
            Sub("irrigation_canal", "Canals & lining", ("canal", "lining", "नहर")),
            Sub("irrigation_dams", "Dams, weirs & stop dams", ("dam", "weir", "stop dam", "बांध")),
        ),
    ),
    Cat(
        "maintenance",
        "Maintenance",
        "रखरखाव",
        ("maintenance", "repair", "renovation", "patch", "annual maintenance", "o&m", "मरम्मत",
         "रखरखाव", "संधारण"),
        (
            Sub("maintenance_roads", "Road maintenance & patchwork", ("patch", "pothole", "ordinary repair")),
            Sub("maintenance_buildings", "Building repair & renovation", ("renovation", "building repair")),
        ),
    ),
)

CATEGORY_CODES = tuple(c.code for c in CATEGORIES)
CATEGORY_BY_CODE = {c.code: c for c in CATEGORIES}

# Related categories earn partial specialisation/experience credit.
RELATED: dict[str, frozenset[str]] = {
    "roads": frozenset({"bridges", "maintenance", "drains"}),
    "bridges": frozenset({"roads", "rcc"}),
    "rcc": frozenset({"bridges", "buildings", "water_supply"}),
    "drains": frozenset({"sewerage", "roads"}),
    "buildings": frozenset({"rcc", "maintenance", "electrical"}),
    "electrical": frozenset({"buildings"}),
    "water_supply": frozenset({"sewerage", "rcc"}),
    "sewerage": frozenset({"water_supply", "drains"}),
    "irrigation": frozenset({"rcc", "water_supply"}),
    "maintenance": frozenset({"roads", "buildings"}),
}


def _has(text: str, keyword: str) -> bool:
    kw = keyword.strip()
    if kw.isascii():
        # Word boundaries so "dam" does not match "Damoh" and "rob" does not match "problem".
        return re.search(rf"(?<![a-z0-9]){re.escape(kw)}(?![a-z0-9])", text) is not None
    return kw in text


def classify(text: str) -> tuple[str | None, list[str]]:
    """Keyword classification; returns (category_code, subcategory_codes)."""
    lowered = text.lower()
    best: tuple[int, str | None] = (0, None)
    for cat in CATEGORIES:
        hits = sum(1 for kw in cat.keywords if _has(lowered, kw))
        if hits > best[0]:
            best = (hits, cat.code)
    code = best[1]
    subs: list[str] = []
    if code:
        for sub in CATEGORY_BY_CODE[code].subs:
            if any(_has(lowered, kw) for kw in sub.keywords):
                subs.append(sub.code)
    return code, subs
