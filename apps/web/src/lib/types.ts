export type Role = "owner" | "admin" | "analyst" | "viewer";
export type EligibilityStatus = "ELIGIBLE" | "NOT_ELIGIBLE" | "NEEDS_VERIFICATION";
export type RequirementResult = "PASS" | "FAIL" | "UNKNOWN" | "NOT_APPLICABLE";
export type Action = "review" | "verify" | "not_eligible" | "closed" | "dismissed";

export interface Me {
  user: { id: string; email: string; full_name: string };
  active_company: {
    id: string;
    name: string;
    role: Role;
    onboarding_step: number;
    onboarding_complete: boolean;
    is_demo: boolean;
  } | null;
  companies: { id: string; name: string; role: Role }[];
}

export interface TenderRow {
  id: string;
  title: string;
  reference_number: string | null;
  department: string | null;
  issuing_organization: string | null;
  district: string | null;
  category_code: string | null;
  estimated_value_paise: number | null;
  published_at: string | null;
  deadline: string | null;
  previous_deadline: string | null;
  deadline_changed_at: string | null;
  status: string;
  is_demo: boolean;
  retrieval_method: string;
  documents_available: boolean;
  eligibility_status: EligibilityStatus;
  eligibility_summary: string;
  mandatory_failures: number;
  unknown_count: number;
  relevance_score: number;
  saved_state: "saved" | "dismissed" | null;
  action: Action;
}

export interface TenderList {
  items: TenderRow[];
  total: number;
  page: number;
  page_size: number;
  sort: string;
  order: "asc" | "desc";
  generated_at: string;
}

export interface Citation {
  document: string | null;
  document_id: string | null;
  page: number | null;
  clause: string | null;
  quote: string | null;
}

export interface Evidence {
  kind: "certificate" | "experience" | "profile";
  id?: string;
  title?: string;
  field?: string;
  value?: string;
  verification_status?: string;
  expires_on?: string | null;
  certificate_verified?: boolean;
}

export interface RequirementRow {
  id: string;
  requirement_type: string;
  label: string;
  mandatory: boolean;
  operator: string;
  threshold_value: number | null;
  threshold_text: string | null;
  unit: string | null;
  period_years: number | null;
  citation: Citation;
  extraction_method: string;
  verification_status: "source_verified" | "needs_review" | "rejected";
  result: RequirementResult;
  explanation: string;
  company_evidence: Evidence[];
}

export interface ScoreFactor {
  key: string;
  label: string;
  weight: number;
  fraction: number;
  points: number;
  reason: string;
}

export interface TenderDocument {
  id: string;
  kind: string;
  title: string;
  filename: string | null;
  size_bytes: number | null;
  page_count: number | null;
  is_available: boolean;
  source_url: string | null;
  sha256: string | null;
  retrieval_method: string;
  permission_status: string;
  created_at: string;
  extracted_summary: { warnings?: string[]; requirements_extracted?: number; boq?: { item_count: number; total_paise: number | null } };
}

export interface TenderDetail extends TenderRow {
  source_tender_id: string;
  location: string | null;
  subcategory_codes: string[];
  tender_type: string | null;
  emd_paise: number | null;
  tender_fee_paise: number | null;
  completion_period_days: number | null;
  bid_submission_start_at: string | null;
  bid_opening_at: string | null;
  pre_bid_meeting_at: string | null;
  nit_summary: string | null;
  version: number;
  provenance: {
    source_name: string;
    source_code: string;
    source_url: string | null;
    source_organization: string | null;
    retrieval_method: string;
    permission_status: string;
    imported_at: string;
    imported_by: string | null;
    original_file_sha256: string | null;
    last_seen_at: string;
    is_private_import: boolean;
  };
  also_seen_in: { tender_id: string; source: string; retrieval_method: string; imported_at: string }[];
  documents: TenderDocument[];
  versions: {
    version: number;
    change_kind: string;
    changed_fields: string[];
    previous_values: Record<string, unknown>;
    corrigendum_ref: string | null;
    note: string | null;
    captured_at: string;
  }[];
  timeline: { at: string; kind: string; label: string; note?: string | null }[];
  eligibility: {
    status: EligibilityStatus;
    summary: string;
    mandatory_failures: number;
    unknown_count: number;
    computed_at: string;
    requirements: RequirementRow[];
    disclaimer: string;
  };
  relevance: { score: number; breakdown: ScoreFactor[] };
  notes: { id: string; body: string; author: string; created_at: string }[];
  can_review_requirements: boolean;
}

export interface Reference {
  categories: { code: string; name: string; name_hi: string; subcategories: { code: string; name: string }[] }[];
  districts: string[];
  registration_classes: string[];
  business_types: string[];
  certificate_types: { code: string; label: string }[];
}

export interface Certificate {
  id: string;
  cert_type: string;
  type_label: string;
  title: string;
  number: string | null;
  issuer: string | null;
  issued_on: string | null;
  expires_on: string | null;
  expiry_state: "none" | "valid" | "expiring" | "expired";
  registration_class: string | null;
  value_paise: number | null;
  verification_status: "verified" | "unverified" | "rejected";
  verified_at: string | null;
  notes: string | null;
  document: { id: string; filename: string; size_bytes: number; content_type: string } | null;
}

export interface Experience {
  id: string;
  project_name: string;
  client_name: string | null;
  category_code: string;
  district: string | null;
  contract_value_paise: number;
  completed_on: string | null;
  certificate_id: string | null;
  certificate_status: string | null;
}

export interface Profile {
  id: string;
  legal_name: string;
  business_type: string | null;
  gstin: string | null;
  pan: string | null;
  contact_name: string | null;
  contact_email: string | null;
  contact_phone: string | null;
  address: string | null;
  base_district: string | null;
  annual_turnover_paise: number | null;
  turnover_financial_year: string | null;
  contractor_registration_class: string | null;
  registration_authority: string | null;
  workforce_count: number | null;
  equipment: string[];
  available_resources: string | null;
  max_concurrent_projects: number | null;
  current_active_projects: number | null;
  category_codes: string[];
  subcategory_codes: string[];
  specialties: string[];
  districts: string[];
  operating_radius_km: number | null;
  statewide: boolean;
  min_tender_value_paise: number | null;
  max_tender_value_paise: number | null;
  onboarding_step: number;
  onboarding_completed_at: string | null;
  is_demo: boolean;
  experience: Experience[];
  certificates: Certificate[];
  role: Role;
}

export interface SourceItem {
  id: string;
  code: string;
  name: string;
  owner_organization: string;
  kind: string;
  url: string | null;
  api_status: string;
  collection_mode: string;
  collection_state: string;
  permission_status: string;
  enabled: boolean;
  configured: boolean;
  captcha_dependency: boolean;
  coverage_note: string;
  phase: string;
  priority: string;
  health_message: string;
  last_success_at: string | null;
  last_failure_at: string | null;
  last_error: string | null;
  tender_count: number;
  last_run: { status: string; started_at: string; message: string | null } | null;
  supports_import: boolean;
}

export interface JobInfo {
  job: string;
  slot_key: string;
  trigger: string;
  status: string;
  started_at: string;
  finished_at: string | null;
  stats: Record<string, unknown>;
  error: string | null;
}

export interface SourcesResponse {
  schedule: {
    timezone: string;
    reanalysis_times_ist: string[];
    digest_time_ist: string;
    current_slot: string;
    current_slot_ran: boolean;
    next_reanalysis_at: string;
    next_digest_at: string;
    note: string;
    recent_jobs: JobInfo[];
  };
  items: SourceItem[];
  attestation_text: string;
}

export interface SourceRun {
  id: string;
  source_code: string;
  source_name: string;
  trigger: string;
  slot_key: string | null;
  status: string;
  attempt: number;
  started_at: string;
  finished_at: string | null;
  records_seen: number;
  records_created: number;
  records_updated: number;
  records_unchanged: number;
  duplicates: number;
  failed_records: number;
  errors: { row?: number; record?: string | null; error: string }[];
  message: string | null;
  filename: string | null;
  file_sha256: string | null;
  operator: string | null;
}

export interface NotificationPrefs {
  phone_e164: string | null;
  phone_masked: string | null;
  phone_verified: boolean;
  whatsapp_opt_in: boolean;
  opt_in_at: string | null;
  opted_out_at: string | null;
  daily_digest: boolean;
  urgent_alerts: boolean;
  closing_reminders: boolean;
  min_relevance: number;
  include_needs_verification: boolean;
  quiet_hours_start: string | null;
  quiet_hours_end: string | null;
  transport: "meta" | "simulated";
  transport_note: string;
}

export interface OutboxItem {
  id: string;
  alert_type: string;
  template_name: string;
  recipient: string | null;
  rendered_text: string;
  status: string;
  transport: string;
  created_at: string;
  sent_at: string | null;
  scheduled_for: string;
  attempts: number;
  error: string | null;
  tender_id: string | null;
}
