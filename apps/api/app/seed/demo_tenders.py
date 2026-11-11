"""24 DEMO construction tenders for Madhya Pradesh.

These are fictional records for demonstration only. They do NOT exist on any government
portal. Dates are expressed as day offsets from an anchor date (stored on the demo
source) so repeated scheduler runs are idempotent and the demo stays current after a
re-anchor (`python -m app.seed --reanchor-demo`).
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal

from app.services.ingestion.base import ChangeRecord, DocumentRef, NormalizedTender, RequirementSpec
from app.services.money import CRORE, LAKH, rupees_to_paise
from app.services.taxonomy import classify
from app.services.timeutil import IST, ist_to_utc

MP_ACTIVE_TENDERS_URL = "https://mptenders.gov.in/nicgep/app?page=FrontEndLatestActiveTenders&service=page"


def cr(x: str) -> int:
    return rupees_to_paise(Decimal(x) * CRORE)


def lakh(x: str) -> int:
    return rupees_to_paise(Decimal(x) * LAKH)


def _nit(page: int, clause: str, quote: str) -> dict[str, object]:
    return {"document_ref": "NIT (DEMO)", "page_number": page, "clause_ref": clause, "evidence_quote": quote}


def turnover(amount: str, page: int, clause: str, quote: str, years: int = 3) -> RequirementSpec:
    return RequirementSpec(
        "annual_turnover",
        f"Average annual turnover ≥ ₹{amount} Cr (last {years} FY)",
        "gte",
        threshold_value=cr(amount),
        unit="paise",
        period_years=years,
        **_nit(page, clause, quote),  # type: ignore[arg-type]
    )


def similar(amount: str, count: int, cat: str, page: int, clause: str, quote: str) -> RequirementSpec:
    noun = "work" if count == 1 else "works"
    return RequirementSpec(
        "similar_work",
        f"{count} similar completed {noun} ≥ ₹{amount} Cr each",
        "gte",
        threshold_value=cr(amount),
        threshold_text=str(count),
        unit="paise",
        category_code=cat,
        **_nit(page, clause, quote),  # type: ignore[arg-type]
    )


def reg(cls: str, page: int, clause: str, quote: str) -> RequirementSpec:
    return RequirementSpec(
        "contractor_registration",
        f"Contractor registration Class {cls} or above",
        "gte",
        threshold_text=cls,
        unit="class",
        **_nit(page, clause, quote),  # type: ignore[arg-type]
    )


def cert(kind: str, label: str, page: int, clause: str, quote: str, mandatory: bool = True) -> RequirementSpec:
    return RequirementSpec(
        "certificate", label, "exists", mandatory=mandatory, threshold_text=kind, unit="none",
        **_nit(page, clause, quote),  # type: ignore[arg-type]
    )


def solvency(amount: str, page: int, clause: str, quote: str) -> RequirementSpec:
    return RequirementSpec(
        "solvency", f"Bank solvency certificate ≥ ₹{amount} Cr", "gte", threshold_value=cr(amount),
        unit="paise", **_nit(page, clause, quote),  # type: ignore[arg-type]
    )


def equipment(item: str, page: int, clause: str, quote: str) -> RequirementSpec:
    return RequirementSpec(
        "equipment", f"Own/leased {item}", "exists", threshold_text=item, unit="none",
        **_nit(page, clause, quote),  # type: ignore[arg-type]
    )


def bid_capacity(page: int, clause: str, quote: str) -> RequirementSpec:
    return RequirementSpec(
        "bid_capacity", "Available bid capacity ≥ estimated cost", "gte", unit="paise",
        **_nit(page, clause, quote),  # type: ignore[arg-type]
    )


def info(label: str, page: int, clause: str, quote: str) -> RequirementSpec:
    return RequirementSpec(
        "information", label, "info", mandatory=False, **_nit(page, clause, quote)  # type: ignore[arg-type]
    )


GST = ("gst", "Valid GST registration")
PAN = ("pan", "PAN of the bidder")
EPF = ("epf", "EPF registration")
LABOUR = ("labour_licence", "Labour licence under CLRA Act")

# (id, ref, title, dept, org, district, location, category, value, emd, months,
#  published_offset, deadline_offset, requirements, extra)
FIXTURES: list[dict[str, object]] = [
    dict(
        n=1, ref="2026_PWDRB_418203_1", category="roads", district="Bhopal",
        title="Strengthening and widening of Bhopal–Berasia road (km 12/0 to 26/4) with bituminous surfacing",
        dept="Public Works Department (Roads & Bridges)", org="PWD Division No. 1, Bhopal",
        location="Berasia Road, Bhopal", value=cr("12.40"), emd=lakh("12.40"), months=12, pub=-9, due=12,
        summary="Two-lane widening to 10 m with DBM 50 mm + BC 30 mm, shoulders and cross-drainage works. Item-rate.",
        reqs=[
            turnover("6.20", 4, "3.1(a)", "Average annual financial turnover during the last 3 financial years shall not be less than Rs. 620.00 lakh."),
            similar("9.92", 1, "roads", 4, "3.1(b)", "The bidder should have satisfactorily completed at least one similar work of value not less than Rs. 992.00 lakh in the last 5 years."),
            reg("A", 3, "2.4", "Bidder must be registered in Class A or above in the MP PWD centralised contractor registration system."),
            cert(*GST, 5, "3.4", "Bidder shall upload a valid GST registration certificate."),
            cert(*EPF, 5, "3.5", "Proof of EPF registration shall be uploaded with the technical bid."),
        ],
    ),
    dict(
        n=2, ref="2026_MPRRDA_421877_1", category="roads", district="Sehore",
        title="Upgradation of 6 rural roads under PMGSY-III, package MP-38-112, Sehore block",
        dept="MP Rural Road Development Authority", org="PIU Sehore, MPRRDA",
        location="Sehore block", value=cr("4.85"), emd=lakh("9.70"), months=9, pub=-6, due=18,
        summary="Upgradation of 21.6 km rural roads with 5-year routine maintenance. Standard Bidding Document (PMGSY).",
        reqs=[
            turnover("2.40", 6, "2.2.2.3", "Minimum average annual construction turnover of Rs. 240 lakh over the last three financial years."),
            similar("3.88", 1, "roads", 6, "2.2.2.4", "Completed at least one work of similar nature of value not less than 80% of the estimated cost."),
            reg("C", 5, "2.2.1", "Bidder shall be a registered contractor of Class C or above with MP PWD."),
            cert(*GST, 7, "2.2.5", "Copy of valid GST registration."),
            cert(*PAN, 7, "2.2.5", "Copy of PAN card of the bidder."),
            cert(*EPF, 7, "2.2.6", "EPF registration certificate."),
            info("Joint ventures not permitted", 5, "2.1.3", "Joint venture / consortium is not allowed for this package."),
        ],
    ),
    dict(
        n=3, ref="2026_PWDBR_419540_1", category="bridges", district="Narmadapuram",
        title="Construction of high level bridge across Tawa river on Itarsi–Kesla road including approaches",
        dept="Public Works Department (Bridges)", org="PWD Bridge Division, Narmadapuram",
        location="Tawa river crossing, Kesla", value=cr("18.75"), emd=lakh("18.75"), months=24, pub=-10, due=21,
        summary="6 × 30 m spans, well foundation, PSC girders, 1.2 km approaches.",
        reqs=[
            turnover("9.40", 8, "4.2(i)", "Average annual turnover of the bidder in the last 3 years shall not be less than Rs. 9.40 crore."),
            similar("7.50", 1, "bridges", 8, "4.2(ii)", "One completed bridge work with well foundation of value not less than Rs. 7.50 crore."),
            reg("A", 7, "4.1", "Class A registration in PWD MP is mandatory."),
            solvency("1.90", 9, "4.4", "Solvency certificate from a scheduled bank of not less than Rs. 190.00 lakh."),
        ],
    ),
    dict(
        n=4, ref="2026_BMC_422109_1", category="drains", district="Bhopal",
        title="Construction of RCC covered storm water drain, Kolar Road wards 82–84",
        dept="Urban Administration & Development", org="Bhopal Municipal Corporation",
        location="Kolar Road, Bhopal", value=cr("1.86"), emd=lakh("1.86"), months=6, pub=-11, due=5,
        summary="1.9 km RCC box drain 1.2 × 1.0 m with precast covers, outfall and road restoration.",
        reqs=[
            turnover("0.93", 3, "5(a)", "Average annual turnover in the last three years shall be at least Rs. 93.00 lakh."),
            similar("1.49", 1, "drains", 3, "5(b)", "One similar work (drain/nala construction) of value not less than Rs. 149 lakh."),
            reg("C", 2, "4", "Registered contractor of Class C and above."),
            cert(*LABOUR, 3, "5(e)", "Valid labour licence under Contract Labour (R&A) Act, 1970."),
        ],
    ),
    dict(
        n=5, ref="2026_MPUDC_420331_1", category="sewerage", district="Indore",
        title="Sewer network and house service connections, Zone 4, Indore (AMRUT 2.0)",
        dept="Urban Development & Housing", org="MP Urban Development Company Ltd.",
        location="Zone 4, Indore", value=cr("38.20"), emd=lakh("38.20"), months=24, pub=-5, due=25,
        summary="62 km HDPE/RCC sewer lines, 4,800 house connections, 3 pumping stations; 5-year O&M.",
        reqs=[
            turnover("19.10", 12, "ITB 4.2(a)", "Average annual turnover for the last 3 years shall be minimum INR 19.10 crore."),
            similar("15.28", 1, "sewerage", 12, "ITB 4.2(b)", "One similar work of sewerage network of value at least INR 15.28 crore."),
            bid_capacity(13, "ITB 4.3", "Available bid capacity calculated as (A × N × 2 − B) shall exceed the estimated cost."),
            cert(*GST, 14, "ITB 4.5", "GST registration certificate."),
        ],
    ),
    dict(
        n=6, ref="2026_PHED_423018_1", category="water_supply", district="Raisen",
        title="Multi-village rural water supply scheme, Begumganj cluster (Jal Jeevan Mission)",
        dept="Public Health Engineering Department", org="PHED Project Division, Raisen",
        location="Begumganj, Raisen", value=cr("26.40"), emd=lakh("26.40"), months=18, pub=-4, due=30,
        summary="Intake, 8 MLD WTP, 140 km DI/HDPE pipelines and 46 village OHTs; 10-year O&M.",
        reqs=[
            turnover("13.20", 10, "3.2", "Average annual turnover not less than Rs. 13.20 crore during last three financial years."),
            similar("10.56", 1, "water_supply", 10, "3.3", "One completed water supply scheme of value not less than Rs. 10.56 crore."),
            reg("A", 9, "3.1", "Contractor must hold Class A registration with PWD / PHED MP."),
            bid_capacity(11, "3.4", "Bid capacity shall be calculated as per Annexure-B."),
        ],
    ),
    dict(
        n=7, ref="2026_WRD_420786_1", category="irrigation", district="Vidisha",
        title="Construction of stop dams and canal lining, Sironj minor irrigation project",
        dept="Water Resources Department", org="WRD Division, Vidisha",
        location="Sironj, Vidisha", value=cr("3.15"), emd=lakh("3.15"), months=10, pub=-8, due=9,
        summary="4 stop dams and 6.2 km CC lining of distributaries. सिंचाई परियोजना.",
        reqs=[
            turnover("1.50", 4, "2(क)", "निविदाकार का पिछले तीन वर्षों का औसत वार्षिक टर्नओवर ₹ 150.00 लाख से कम नहीं होना चाहिए।"),
            similar("1.26", 1, "irrigation", 4, "2(ख)", "पिछले पाँच वर्षों में कम से कम एक समान प्रकृति का कार्य जिसकी लागत ₹ 126.00 लाख से कम न हो।"),
            reg("C", 3, "1", "जल संसाधन विभाग / लोक निर्माण विभाग में श्रेणी 'C' या उससे ऊपर का पंजीयन अनिवार्य।"),
        ],
    ),
    dict(
        n=8, ref="2026_PWDPIU_421455_1", category="buildings", district="Bhopal",
        title="Construction of 100-seater girls hostel at Government Polytechnic College, Bhopal (G+3)",
        dept="Public Works Department (Project Implementation Unit)", org="PWD PIU Division, Bhopal",
        location="Govt. Polytechnic, Bhopal", value=cr("5.60"), emd=lakh("5.60"), months=15, pub=-12, due=14,
        summary="RCC framed G+3 building, 3,400 sqm, with internal electrification and plumbing.",
        reqs=[
            turnover("2.80", 5, "6.1", "Average annual turnover of last 3 years ≥ Rs. 280 lakh."),
            similar("2.24", 1, "buildings", 5, "6.2", "At least one similar building work costing not less than 40% of the estimated cost."),
            reg("B", 4, "5", "Bidder should be registered in Class B or above."),
            cert(*GST, 6, "6.4", "GST registration."),
            cert(*EPF, 6, "6.5", "EPF code number."),
        ],
    ),
    dict(
        n=9, ref="2026_JMC_419902_1", category="maintenance", district="Jabalpur",
        title="Annual maintenance and patch repair of city roads, Zones 3 & 7 (2 years)",
        dept="Urban Administration & Development", org="Jabalpur Municipal Corporation",
        location="Zones 3 and 7, Jabalpur", value=cr("2.20"), emd=lakh("2.20"), months=24, pub=-10, due=3,
        summary="Pothole repair, BT patching and kerb painting on 84 km of city roads, rate contract.",
        reqs=[
            turnover("1.10", 2, "3(i)", "Average annual turnover ≥ Rs. 110 lakh in last 3 years."),
            reg("C", 2, "2", "Class C or above registration."),
            cert(*GST, 3, "3(iii)", "GST registration certificate."),
            cert(*EPF, 3, "3(iv)", "EPF registration."),
        ],
    ),
    dict(
        n=10, ref="2026_MPRDC_417660_1", category="roads", district="Ujjain",
        title="Four-laning of Dewas–Ujjain section (km 0 to 38) on EPC mode",
        dept="MP Road Development Corporation", org="MPRDC Ltd., Bhopal",
        location="Dewas–Ujjain", value=cr("142.00"), emd=cr("1.42"), months=30, pub=-14, due=28,
        summary="EPC four-laning with service roads, 2 flyovers and 9 minor bridges.",
        reqs=[
            turnover("71.00", 18, "2.2.2.2(i)", "Average annual turnover of the bidder in the last 5 financial years shall be at least INR 71 crore.", years=5),
            similar("56.80", 1, "roads", 18, "2.2.2.2(ii)", "Completed one similar work of 40% of estimated project cost."),
            reg("AA", 17, "2.1", "Bidder shall be registered in the highest class (AA) of MP PWD."),
        ],
    ),
    dict(
        n=11, ref="2026_PWDRB_423551_1", category="roads", district="Raisen",
        title="CC road and side drain construction in Obaidullaganj town",
        dept="Public Works Department (Roads & Bridges)", org="PWD Division, Raisen",
        location="Obaidullaganj, Raisen", value=lakh("96.00"), emd=lakh("0.96"), months=4, pub=-7, due=1,
        summary="M-30 cement concrete road 1.1 km with RCC side drains both sides.",
        reqs=[
            turnover("0.48", 2, "2.1", "Average annual turnover not less than Rs. 48 lakh."),
            reg("D", 2, "1.3", "Registered contractor of Class D and above."),
            cert(*GST, 2, "2.3", "GST registration certificate."),
        ],
    ),
    dict(
        n=12, ref="2026_MPJN_424002_1", category="water_supply", district="Shajapur",
        title="Intake well, 12 MLD WTP and clear water rising main, Shajapur group water supply scheme",
        dept="MP Jal Nigam", org="MP Jal Nigam Maryadit, Bhopal",
        location="Shajapur", value=cr("44.70"), emd=cr("0.45"), months=24, pub=-2, due=35,
        summary=None, docs_available=False, reqs=[],
    ),
    dict(
        n=13, ref="2026_PWDEL_420915_1", category="electrical", district="Sehore",
        title="Internal electrification and 250 kVA substation, new district court building, Sehore",
        dept="Public Works Department (Electrical & Mechanical)", org="PWD E&M Division, Bhopal",
        location="District Court, Sehore", value=cr("1.42"), emd=lakh("1.42"), months=6, pub=-8, due=10,
        summary="Wiring, LT panels, 250 kVA transformer, DG set and lightning protection.",
        reqs=[
            turnover("0.71", 3, "4.1", "Average annual turnover of Rs. 71 lakh."),
            cert("electrical_licence", "Electrical contractor licence (MP)", 3, "4.2", "Valid electrical contractor licence issued by the Chief Electrical Inspector, MP."),
            cert(*GST, 3, "4.3", "GST registration."),
        ],
    ),
    dict(
        n=14, ref="2026_BSCDCL_421320_1", category="rcc", district="Bhopal",
        title="RCC retaining wall and slope protection along Upper Lake promenade",
        dept="Urban Administration & Development", org="Bhopal Smart City Development Corporation Ltd.",
        location="Upper Lake, Bhopal", value=cr("3.80"), emd=lakh("3.80"), months=8, pub=-5, due=16,
        summary="Cantilever RCC retaining wall 640 m, gabions and stone pitching.",
        reqs=[
            turnover("1.90", 7, "3.1", "Average annual turnover in last 3 years ≥ INR 190 lakh."),
            similar("1.52", 1, "rcc", 7, "3.2", "One completed RCC structural work of value ≥ 40% of estimate."),
            solvency("0.38", 7, "3.3", "Solvency certificate of 10% of estimated cost from a nationalised bank."),
            cert(*GST, 8, "3.5", "GST certificate."),
        ],
    ),
    dict(
        n=15, ref="2026_NVDA_418745_1", category="irrigation", district="Khargone",
        title="Lining of Indira Sagar main canal, RD 120 to 142 km",
        dept="Narmada Valley Development Authority", org="NVDA Canal Division, Khargone",
        location="Khargone", value=cr("21.30"), emd=lakh("21.30"), months=18, pub=-6, due=40,
        summary="CC lining with paver, structures and service road.",
        reqs=[
            turnover("10.65", 9, "B-2", "Average annual turnover ≥ Rs. 10.65 crore."),
            similar("8.52", 1, "irrigation", 9, "B-3", "Completed canal lining work ≥ Rs. 8.52 crore."),
            reg("A", 8, "B-1", "Class A registration with WRD/NVDA."),
        ],
    ),
    dict(
        n=16, ref="2026_PWDRB_422874_1", category="bridges", district="Vidisha",
        title="Construction of 3 minor bridges and culverts on Vidisha–Kurwai road",
        dept="Public Works Department (Roads & Bridges)", org="PWD Division, Vidisha",
        location="Vidisha–Kurwai road", value=cr("2.65"), emd=lakh("2.65"), months=9, pub=-6, due=8,
        summary="Three minor bridges (RCC slab, 3 × 8 m) and 11 pipe culverts.",
        reqs=[
            turnover("1.30", 3, "2.1", "Average annual turnover ≥ Rs. 130 lakh."),
            similar("1.59", 1, "bridges", 3, "2.2", "One completed bridge work of value not less than 60% of the estimate."),
            reg("C", 3, "1.2", "Class C or above."),
            cert(*GST, 4, "2.4", "GST registration."),
        ],
    ),
    dict(
        n=17, ref="2026_MPRRDA_421006_1", category="maintenance", district="Vidisha",
        title="Periodic maintenance of PMGSY roads, Ganjbasoda cluster (5-year performance-based)",
        dept="MP Rural Road Development Authority", org="PIU Vidisha, MPRRDA",
        location="Ganjbasoda, Vidisha", value=cr("1.12"), emd=lakh("2.24"), months=60, pub=-12, due=2,
        summary="Renewal coat and routine maintenance of 38 km rural roads.",
        reqs=[
            turnover("0.56", 4, "2.2.2.3", "Average annual turnover ≥ Rs. 56 lakh."),
            reg("D", 4, "2.2.1", "Class D or above registration."),
            cert(*GST, 5, "2.2.5", "GST registration."),
        ],
        corrigenda=[
            dict(ref="CORR-1/2026", due=6, note="Bid submission date extended by 4 days due to revised quantities."),
        ],
    ),
    dict(
        n=18, ref="2026_GMC_420114_1", category="electrical", district="Gwalior",
        title="LED street light retrofit and high-mast installation, Gwalior",
        dept="Urban Administration & Development", org="Gwalior Municipal Corporation",
        location="Gwalior city", value=cr("4.10"), emd=lakh("4.10"), months=8, pub=-4, due=19,
        summary="Retrofit of 9,200 fittings and 24 high-masts with CCMS.",
        reqs=[
            turnover("2.05", 6, "5.1", "Average annual turnover ≥ Rs. 205 lakh."),
            cert("electrical_licence", "Electrical contractor licence (MP)", 6, "5.3", "Valid electrical licence (Class A) from CEI, MP."),
        ],
    ),
    dict(
        n=19, ref="2026_PWDBLD_422640_1", category="buildings", district="Sagar",
        title="Construction of 50-bed Community Health Centre building, Rahatgarh",
        dept="Public Works Department (Buildings)", org="PWD Building Division, Sagar",
        location="Rahatgarh, Sagar", value=cr("7.90"), emd=lakh("7.90"), months=18, pub=-7, due=22,
        summary="G+2 hospital building with OT block, staff quarters and external services.",
        reqs=[
            turnover("3.95", 5, "3.1", "Average annual turnover ≥ Rs. 395 lakh."),
            similar("3.16", 1, "buildings", 5, "3.2", "One building work of not less than 40% of the estimated cost."),
            reg("B", 4, "2", "Class B or above."),
            cert(*EPF, 6, "3.6", "EPF registration."),
        ],
    ),
    dict(
        n=20, ref="2026_MPUDC_423377_1", category="water_supply", district="Raisen",
        title="Water supply distribution network and overhead tanks, Mandideep (AMRUT 2.0)",
        dept="Urban Development & Housing", org="MP Urban Development Company Ltd.",
        location="Mandideep, Raisen", value=cr("16.80"), emd=lakh("16.80"), months=18, pub=-3, due=26,
        summary="96 km DI/HDPE network, 3 OHTs and 7,500 metered connections.",
        reqs=[
            turnover("8.40", 11, "ITB 4.2(a)", "Average annual turnover ≥ INR 8.40 crore."),
            similar("6.72", 1, "water_supply", 11, "ITB 4.2(b)", "One similar water supply work ≥ INR 6.72 crore."),
            bid_capacity(12, "ITB 4.3", "Available bid capacity ≥ estimated cost."),
        ],
    ),
    dict(
        n=21, ref="2026_PWDRB_416992_1", category="roads", district="Sehore",
        title="Resurfacing (BC 30 mm) of Sehore–Ichhawar road, km 0 to 22",
        dept="Public Works Department (Roads & Bridges)", org="PWD Division, Sehore",
        location="Sehore–Ichhawar road", value=cr("3.35"), emd=lakh("3.35"), months=5, pub=-24, due=-3,
        status="closed", summary="Profile correction and BC 30 mm resurfacing.",
        reqs=[
            turnover("1.68", 3, "2.1", "Average annual turnover ≥ Rs. 168 lakh."),
            reg("C", 3, "1.2", "Class C or above."),
        ],
    ),
    dict(
        n=22, ref="2026_RMC_423760_1", category="sewerage", district="Rewa",
        title="18 MLD sewage treatment plant (SBR) with 10-year O&M, Rewa",
        dept="Urban Administration & Development", org="Rewa Municipal Corporation",
        location="Rewa", value=cr("58.00"), emd=cr("0.58"), months=24, pub=-3, due=45,
        summary="SBR-technology STP with SCADA, sludge handling and 10-year O&M.",
        reqs=[
            turnover("29.00", 14, "4.1", "Average annual turnover ≥ INR 29 crore."),
            similar("23.20", 1, "sewerage", 14, "4.2", "One completed STP of ≥ 10 MLD capacity and value ≥ INR 23.20 crore."),
        ],
    ),
    dict(
        n=23, ref="2026_MPRDC_422233_1", category="bridges", district="Sehore",
        title="Construction of ROB at LC 241 on Bhopal–Itarsi rail section, Budhni",
        dept="MP Road Development Corporation", org="MPRDC Ltd., Bhopal",
        location="Budhni, Sehore", value=cr("34.50"), emd=lakh("34.50"), months=24, pub=-8, due=31,
        summary="Two-lane ROB with steel composite girder over railway span and RE-wall approaches.",
        reqs=[
            turnover("17.25", 9, "2.2(a)", "Average annual turnover ≥ INR 17.25 crore."),
            similar("13.80", 1, "bridges", 9, "2.2(b)", "One completed ROB/flyover of value ≥ INR 13.80 crore."),
            reg("AA", 8, "2.1", "Registration in Class AA with MP PWD."),
        ],
    ),
    dict(
        n=24, ref="2026_PWDRB_423905_1", category="roads", district="Bhopal",
        title="BT road with side drains, Bairagarh–Lambakheda link road",
        dept="Public Works Department (Roads & Bridges)", org="PWD Division No. 2, Bhopal",
        location="Bairagarh, Bhopal", value=cr("2.95"), emd=lakh("2.95"), months=8, pub=-5, due=11,
        summary="3.4 km BT road (WMM + DBM + BC) with lined side drains. द्विभाषी NIT.",
        reqs=[
            turnover("1.47", 3, "3(क)", "पिछले तीन वित्तीय वर्षों का औसत वार्षिक टर्नओवर ₹ 147.00 लाख से कम न हो।"),
            similar("1.18", 1, "roads", 3, "3(ख)", "एक समान प्रकृति का पूर्ण कार्य जिसकी लागत अनुमानित लागत के 40% से कम न हो।"),
            reg("C", 3, "2", "म.प्र. लो.नि.वि. में श्रेणी 'C' या उससे ऊपर का पंजीयन।"),
            equipment("Paver finisher", 4, "4", "निविदाकार के पास स्वयं का अथवा किराये पर पेवर फिनिशर उपलब्ध होना चाहिए।"),
            cert(*GST, 4, "5", "GST पंजीयन प्रमाण पत्र।"),
            cert(*PAN, 4, "5", "PAN कार्ड की प्रति।"),
        ],
    ),
]


def _at(anchor: date, offset_days: int, hh: int = 17, mm: int = 0) -> datetime:
    local = datetime.combine(anchor + timedelta(days=offset_days), time(hh, mm), tzinfo=IST)
    return ist_to_utc(local)


def build(anchor: date) -> list[tuple[NormalizedTender, list[ChangeRecord]]]:
    out: list[tuple[NormalizedTender, list[ChangeRecord]]] = []
    for f in FIXTURES:
        n = int(f["n"])  # type: ignore[call-overload]
        sid = f"DEMO-2026-{n:03d}"
        due = int(f["due"])  # type: ignore[call-overload]
        pub = int(f["pub"])  # type: ignore[call-overload]
        docs_available = bool(f.get("docs_available", True))
        reqs = list(f["reqs"])  # type: ignore[call-overload]
        documents = [
            DocumentRef(
                kind="nit",
                title="Notice Inviting Tender (DEMO – no file attached)" if docs_available
                else "NIT not yet published on portal (DEMO)",
                source_url=None,
                is_available=False,
            )
        ]
        if n in (1, 2, 24):
            documents.append(DocumentRef(kind="boq", title="Bill of Quantities (DEMO – no file attached)"))
        nt = NormalizedTender(
            source_tender_id=sid,
            reference_number=f"DEMO/{f['ref']}",
            title=str(f["title"]),
            department=str(f["dept"]),
            issuing_organization=str(f["org"]),
            district=str(f["district"]),
            location=str(f["location"]),
            category_code=str(f["category"]),
            subcategory_codes=[],
            tender_type="Open / Item rate",
            estimated_value_paise=int(f["value"]),  # type: ignore[call-overload]
            emd_paise=int(f["emd"]),  # type: ignore[call-overload]
            tender_fee_paise=rupees_to_paise(5000 if int(f["value"]) < cr("5") else 10000),  # type: ignore[call-overload]
            completion_period_days=int(f["months"]) * 30,  # type: ignore[call-overload]
            published_at=_at(anchor, pub, 10, 30),
            bid_submission_start_at=_at(anchor, pub, 18, 0),
            bid_submission_end_at=_at(anchor, due, 17, 30),
            bid_opening_at=_at(anchor, due + 1, 11, 0),
            pre_bid_meeting_at=_at(anchor, pub + 5, 12, 0) if due - pub > 12 else None,
            status=str(f.get("status", "active")),
            nit_summary=f.get("summary"),  # type: ignore[arg-type]
            source_url=MP_ACTIVE_TENDERS_URL,
            source_organization="DEMO fixture (modelled on MP eProcurement listings)",
            documents=documents,
            requirements=reqs,
        )
        _, nt.subcategory_codes = classify(nt.title + " " + (nt.nit_summary or ""))
        changes = [
            ChangeRecord(
                reference=str(c["ref"]),
                changes={"bid_submission_end_at": _at(anchor, int(c["due"]), 17, 30),
                         "bid_opening_at": _at(anchor, int(c["due"]) + 1, 11, 0)},
                note=str(c["note"]),
            )
            for c in f.get("corrigenda", [])  # type: ignore[attr-defined]
        ]
        out.append((nt, changes))
    return out
