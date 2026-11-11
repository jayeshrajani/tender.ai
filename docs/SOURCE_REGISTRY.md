# Source registry

All entries below are **official public websites or reference documents**. None of the
government entries is a verified public JSON/REST tender API. TenderOS does not integrate
commercial tender resellers (TenderTiger, TenderProcure, TenderInfo, API.SH, etc.) and does
not call undocumented GeM/CPPP/MP endpoints.

The same registry is seeded into the `source_providers` table and shown on `/sources`.

Legend

- **Kind** – web page, PDF, contact, or genuine API.
- **Acquisition** – how data may enter TenderOS.
- **Permission** – `not_required (demo)`, `operator_attested` (a person imports what they are
  allowed to), `pending_authorization`, `authorized`, `link_only`.
- **Adapter** – implementation status in this repository.
- **Freshness** – what the source itself claims; TenderOS never labels partial coverage as
  "Live", "All tenders" or "Synced".

## Tender sources

| Name | Phase | Kind | URL | API status | Acquisition | Permission | Freshness | Adapter | Priority |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| MP eProcurement home | V1 | Web page (government portal) | https://mptenders.gov.in/ | Public HTML summary; **not** a REST API | Official homepage summary; automated ingestion only with authorisation | pending_authorization | Site states latest tenders/corrigenda refresh ≈ every 15 min; **partial coverage only** | `MPPublicHomepageAdapter` – defined, **disabled** | P0 |
| MP Active Tenders | V1 | Web page | https://mptenders.gov.in/nicgep/app?page=FrontEndLatestActiveTenders&service=page | No open REST API verified | Manual CAPTCHA completion by operator, then permitted import; official feed if authorised | operator_attested | As of operator's visit | `ManualCSVImportAdapter`, `ManualDocumentImportAdapter` | P0 |
| MP Advanced Search | V1 | Web page | https://mptenders.gov.in/nicgep/app?page=FrontEndAdvancedSearch&service=page | No open REST API verified | Manual CAPTCHA completion then permitted import; official feed if authorised | operator_attested | As of operator's visit | Manual import | P0 |
| MP Classification | V1 | Web page | https://mptenders.gov.in/nicgep/app?page=FrontEndTendersByClassification&service=page | No open REST API verified | Human review or authorised feed | operator_attested | As of operator's visit | Manual import | P1 |
| MP Tender Archive | V2 | Web page | https://mptenders.gov.in/nicgep/app?page=FrontEndTendersInArchive&service=page | No open REST API verified | Manual import or official feed if authorised | operator_attested | Historical | Manual import (V2 analysis not built) | P1 |
| MP Corrigenda | V1 | Web page | https://mptenders.gov.in/nicgep/app?page=FrontEndLatestActiveCorrigendums&service=page | No open REST API verified | Manual import or official feed if authorised | operator_attested | As of operator's visit | Manual document import (`kind=corrigendum`) | P0 |
| MP Tender Status | V2 | Web page | https://mptenders.gov.in/nicgep/app?component=loadNext&page=WebTenderStatusLists&service=direct | No open REST API verified | Manual import or official feed if authorised | operator_attested | As of operator's visit | Not built (V2) | P1 |
| MP Portal Policy | V1 | Legal terms | https://www.mptenders.gov.in/nicgep/app?page=Disclaimer&service=page | Not applicable | Legal review | — | — | — | P0 |
| MP eProcurement contact | V1 | Support contact (not an API) | https://mptenders.gov.in/nicgep/app?page=FrontEndContactUs&service=page | Not an API | Request an authorised data feed from NIC technical support (support-eproc@nic.in) | — | — | `OfficialFeedAdapter` – defined, **disabled** | P0 |
| CPPP (Central Public Procurement Portal) | V1 | Web page | https://eprocure.gov.in/eprocure/app | No open REST API verified | Permission-gated feed or link-only | link_only | — | Link + manual import | P1 |
| GeM BidPlus | V1 | Web page | https://bidplus.gem.gov.in/all-bids | No open public REST API verified | Official portal link or manual import | link_only | — | Link + manual import | P1 |
| MP Urban Development (MPUDC) | V1 | Department web page | https://mpudc.co.in/mptenders.aspx | Not verified as API | Link and reference | link_only | — | Link + manual import | P1 |

## Qualification and reference sources

| Name | Phase | Kind | URL | API status | Acquisition | Notes | Priority |
| --- | --- | --- | --- | --- | --- | --- | --- |
| MP PWD Contractor Registry | V1 | Web portal | https://pwd.mponline.gov.in/portal/services/Pwd/Home.aspx | No open REST API verified | Manual verification by a person | Contractor registration class/validity | P1 |
| MP UADD Road & Bridge SoR 2025-26 | V2 | PDF | https://www.mpurban.gov.in/Uploaded%20Document/SOR/SOR%20Road%20and%20Bridge%20Works2025_ISSR%20_Volume%20I.pdf | PDF document | Manual review; permission needed for reproduction | Rate reference for V2 | P2 |
| GST Taxpayer Search | V1 | Web page | https://services.gst.gov.in/services/searchtp | No open REST API verified | Human verification | Certificate verification is manual in V1 | P1 |
| Udyam Verification | V1 | Web page (CAPTCHA) | https://www.udyamregistration.gov.in/Udyam_Verify.aspx | No open REST API verified | Human verification | CAPTCHA – never automated | P1 |
| MCA Company Master Data | V2 | Web portal | https://www.mca.gov.in/ | No open REST API verified | Human verification | Company/LLP information | P2 |

## Messaging (genuine APIs)

| Name | Phase | Kind | Endpoint | Status | Requirements | Adapter | Priority |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Meta WhatsApp Cloud API – messages | V1 | Official REST API | `POST https://graph.facebook.com/{API_VERSION}/{PHONE_NUMBER_ID}/messages` | Official POST API | Meta access token, phone number ID, recipient opt-in, approved template | `MetaCloudTransport` – used only when credentials are configured and `WHATSAPP_MODE=live`; otherwise `SimulatedTransport` | P0 |
| Meta WhatsApp Cloud API – templates | V1 | Official REST API | `POST https://graph.facebook.com/{API_VERSION}/{WABA_ID}/message_templates` | Official POST API | Template approval by Meta | Template definitions in `services/notifications/templates.py`; submission is a manual/ops step | P1 |

Documentation: https://www.postman.com/meta/whatsapp-business-platform/overview

## In-app sources

| Code | Purpose | Status |
| --- | --- | --- |
| `demo_fixture` | 24 realistic, clearly **DEMO**-labelled MP construction tenders | Enabled; refreshed by the scheduler |
| `manual_csv` | Operator-attested CSV metadata import with column mapping, validation, duplicate detection and history | Enabled |
| `manual_document` | Operator-attested NIT/BOQ/corrigendum upload with deterministic extraction and human review | Enabled |
| `official_feed_mp` | Generic interface for a future NIC/government-authorised feed | **Disabled** until written authorisation, documentation, credentials and usage terms exist |
| `mp_public_homepage` | Latest-tender/corrigendum summaries on the MP homepage | **Disabled** until automated collection is authorised; never claims full coverage |

## Hard rules

- No CAPTCHA solving, outsourcing, suppression or automated browser bypass.
- No anti-bot evasion or session-token harvesting.
- Protected searches → official portal link + manual **Import tender** action.
- Every imported tender stores: source URL, source organisation, tender ID, retrieval method,
  import operator, import timestamp, permission status, original file hash, document provenance.
- Mailbox/email forwarding import is a future feature and requires explicit user consent.
