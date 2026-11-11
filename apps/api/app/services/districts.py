"""Madhya Pradesh districts (55, including Maihar, Mauganj and Pandhurna created in 2023).

Coordinates are APPROXIMATE district-headquarter locations, used only for the
operating-radius preference in relevance scoring. They are not survey data.
"""

import math
import re

MP_DISTRICTS: dict[str, tuple[float, float]] = {
    "Agar Malwa": (23.71, 76.01),
    "Alirajpur": (22.31, 74.36),
    "Anuppur": (23.10, 81.69),
    "Ashoknagar": (24.58, 77.73),
    "Balaghat": (21.81, 80.18),
    "Barwani": (22.03, 74.90),
    "Betul": (21.90, 77.90),
    "Bhind": (26.56, 78.79),
    "Bhopal": (23.26, 77.41),
    "Burhanpur": (21.31, 76.23),
    "Chhatarpur": (24.92, 79.58),
    "Chhindwara": (22.06, 78.94),
    "Damoh": (23.83, 79.44),
    "Datia": (25.67, 78.46),
    "Dewas": (22.97, 76.05),
    "Dhar": (22.60, 75.30),
    "Dindori": (22.94, 81.08),
    "Guna": (24.65, 77.31),
    "Gwalior": (26.22, 78.18),
    "Harda": (22.34, 77.09),
    "Indore": (22.72, 75.86),
    "Jabalpur": (23.18, 79.99),
    "Jhabua": (22.77, 74.59),
    "Katni": (23.83, 80.39),
    "Khandwa": (21.82, 76.35),
    "Khargone": (21.82, 75.61),
    "Maihar": (24.27, 80.76),
    "Mandla": (22.60, 80.37),
    "Mandsaur": (24.07, 75.07),
    "Mauganj": (24.67, 81.88),
    "Morena": (26.50, 78.00),
    "Narmadapuram": (22.75, 77.72),
    "Narsinghpur": (22.95, 79.19),
    "Neemuch": (24.47, 74.87),
    "Niwari": (25.37, 78.80),
    "Pandhurna": (21.60, 78.52),
    "Panna": (24.72, 80.19),
    "Raisen": (23.33, 77.78),
    "Rajgarh": (24.01, 76.73),
    "Ratlam": (23.33, 75.04),
    "Rewa": (24.53, 81.30),
    "Sagar": (23.84, 78.74),
    "Satna": (24.60, 80.83),
    "Sehore": (23.20, 77.08),
    "Seoni": (22.09, 79.54),
    "Shahdol": (23.30, 81.36),
    "Shajapur": (23.43, 76.27),
    "Sheopur": (25.67, 76.70),
    "Shivpuri": (25.42, 77.66),
    "Sidhi": (24.40, 81.88),
    "Singrauli": (24.20, 82.67),
    "Tikamgarh": (24.74, 78.83),
    "Ujjain": (23.18, 75.78),
    "Umaria": (23.52, 80.84),
    "Vidisha": (23.52, 77.81),
}

_ALIASES = {
    "hoshangabad": "Narmadapuram",
    "east nimar": "Khandwa",
    "west nimar": "Khargone",
    "badwani": "Barwani",
    "narsimhapur": "Narsinghpur",
    "jabalpore": "Jabalpur",
    "agar": "Agar Malwa",
    "agar-malwa": "Agar Malwa",
    "alirajpur (jobat)": "Alirajpur",
    "भोपाल": "Bhopal",
    "इंदौर": "Indore",
    "इन्दौर": "Indore",
    "जबलपुर": "Jabalpur",
    "ग्वालियर": "Gwalior",
    "उज्जैन": "Ujjain",
    "सागर": "Sagar",
    "रीवा": "Rewa",
    "सतना": "Satna",
    "छिंदवाड़ा": "Chhindwara",
    "नर्मदापुरम": "Narmadapuram",
    "होशंगाबाद": "Narmadapuram",
    "विदिशा": "Vidisha",
    "रतलाम": "Ratlam",
    "देवास": "Dewas",
    "धार": "Dhar",
    "कटनी": "Katni",
}

_CANONICAL = {name.lower(): name for name in MP_DISTRICTS}


def normalize_district(value: str | None) -> str | None:
    if not value:
        return None
    key = re.sub(r"\s+", " ", value).strip().lower()
    key = re.sub(r"\s+(district|zila|जिला)$", "", key)
    if key in _CANONICAL:
        return _CANONICAL[key]
    if key in _ALIASES:
        return _ALIASES[key]
    return None


def find_district_in_text(text: str) -> str | None:
    lowered = text.lower()
    for name in sorted(MP_DISTRICTS, key=len, reverse=True):
        if re.search(rf"\b{re.escape(name.lower())}\b", lowered):
            return name
    for alias, name in _ALIASES.items():
        if alias in lowered:
            return name
    return None


def distance_km(a: str, b: str) -> float | None:
    pa, pb = MP_DISTRICTS.get(a), MP_DISTRICTS.get(b)
    if pa is None or pb is None:
        return None
    lat1, lon1, lat2, lon2 = map(math.radians, (*pa, *pb))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(
        (lon2 - lon1) / 2
    ) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))
