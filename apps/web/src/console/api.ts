import type { Tone } from "./data";

const AUTH_SESSION_STORAGE_KEY = "airank.auth.session.v1";

export type ConsoleProject = {
  id: string;
  name: string;
  website: string;
  industry: string;
  competitors: string;
  audience: string;
  date: string;
};

export type ConsoleMetricCard = {
  label: string;
  value: string;
  suffix: string;
  delta: string;
  tone: Tone;
  icon: string;
};

export type ConsoleOverview = {
  project: ConsoleProject;
  metricCards: ConsoleMetricCard[];
  dataStatus: "empty" | "collecting" | "provider_evidence" | "unverified";
  message: string;
};

export type PageAuditFinding = {
  finding_id: string;
  rule_id: string;
  severity: "info" | "low" | "medium" | "high" | "critical";
  status: "passed" | "failed";
  title: string;
  description: string;
  recommendation: string;
  evidence: Record<string, unknown>;
  score_delta: number;
};

export type PageAuditRun = {
  run_id: string;
  tenant_id: string;
  project_id: string;
  job_id: string;
  requested_url: string;
  final_url: string | null;
  status: "queued" | "running" | "completed" | "blocked" | "failed";
  rules_version: string;
  evidence_grade: string | null;
  technical_extractability_score: number | null;
  response_status: number | null;
  response_content_type: string | null;
  response_bytes: number | null;
  content_sha256: string | null;
  connected_ip: string | null;
  redirect_count: number | null;
  extracted: {
    title?: string;
    meta_description?: string;
    canonical_url?: string;
    robots_directives?: string[];
    h1_count?: number;
    visible_text_chars?: number;
    json_ld_types?: string[];
  };
  error_code: string | null;
  error_message: string | null;
  requested_by: string;
  finding_count: number;
  failed_finding_count: number;
  findings: PageAuditFinding[];
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
  idempotent_replay: boolean;
};

export type AssetBundleItem = {
  asset_id?: string;
  title: string;
  desc: string;
  progress: number;
  status: string;
};

export type AssetBundle = {
  project_id: string;
  tenant_id: string;
  completeness: number;
  recommendation: string;
  assets: AssetBundleItem[];
};

export type EvidenceGap = {
  gap_id: string;
  project_id: string;
  run_id: string;
  gap_type: "brand_unmentioned";
  contract_version: "airank.evidence-gap.v2";
  derivation_policy: "airank.brand-unmentioned-gap.v1";
  severity: "low" | "medium" | "high";
  title: string;
  description: string;
  related_question_ids: string[];
  provider: string;
  collector_surface: "api" | "web" | "app" | "manual_import";
  valid_sample_count: number;
  normal_unmentioned_count: number;
  answer_snapshot_ids: string[];
  evidence_snapshot_ids: string[];
  citation_ids: string[];
  fact_atom_ids: string[];
  suggested_asset_type: string;
  evidence_sha256: string;
  quality_report_sha256: string;
  status: string;
  created_at: string;
};

export type EvidenceGapList = {
  project_id: string;
  contract_version: "airank.evidence-gap.v2";
  gaps: EvidenceGap[];
  governed_gap_count: number;
  unverified_legacy_count: number;
};

export type EvidenceGapDerivation = {
  derivation_run_id: string;
  project_id: string;
  run_id: string;
  contract_version: "airank.evidence-gap.v2";
  derivation_policy: "airank.brand-unmentioned-gap.v1";
  quality_report_sha256: string;
  evidence_basis_sha256: string;
  gap_count: number;
  skipped_group_count: number;
  gaps: EvidenceGap[];
  created_by: string;
  created_at: string;
  idempotent_replay: boolean;
};

export type FactAcquisitionTask = {
  task_id: string;
  project_id: string;
  gap_id: string;
  contract_version: "airank.fact-acquisition-task.v1";
  gap_contract_version: "airank.evidence-gap.v2";
  gap_evidence_sha256: string;
  quality_report_sha256: string;
  status: "open" | "in_review" | "resolved" | "blocked";
  resolution_state: "needs_fact_proposal" | "needs_fact_review" | "ready_for_intervention" | "blocked";
  priority: "low" | "medium" | "high";
  title: string;
  evidence_requirement: string;
  required_authority_policy: "official_or_verified_third_party.v1";
  suggested_fact_type: string;
  related_question_ids: string[];
  provider: string;
  collector_surface: "api" | "web" | "app" | "manual_import";
  knowledge_source_ids: string[];
  fact_revision_ids: string[];
  approved_fact_revision_ids: string[];
  generation_allowed: boolean;
  event_count: number;
  last_event_sha256: string;
  created_by: string;
  updated_by: string;
  version: number;
  resolved_at: string | null;
  created_at: string;
  updated_at: string;
  idempotent_replay: boolean;
};

export type FactAcquisitionTaskList = {
  project_id: string;
  contract_version: "airank.fact-acquisition-task.v1";
  tasks: FactAcquisitionTask[];
  open_count: number;
  in_review_count: number;
  resolved_count: number;
};

export type OpportunitySourceKind = "brand_visibility" | "citation_support" | "fact_governance" | "page_extractability";

export type InterventionOpportunity = {
  snapshot_id: string;
  opportunity_id: string;
  project_id: string;
  derivation_run_id: string;
  contract_version: "airank.intervention-opportunity.v1";
  policy_version: "airank.cross-domain-opportunity-policy.v1";
  source_kind: OpportunitySourceKind;
  source_ref_type: string;
  source_ref_id: string;
  issue_code: string;
  source_evidence_sha256: string;
  evidence_level: "quality_gated_repeated_samples" | "independently_reviewed_source_page" | "immutable_governance_record" | "content_hashed_page_audit" | "immutable_claim_citation_basis";
  state: "blocked_evidence" | "ready_for_action" | "monitor";
  intervention_gate: "evidence_blocked" | "verification_required" | "content_action_ready" | "research_action_ready" | "governance_action_only" | "technical_action_ready";
  severity: "info" | "low" | "medium" | "high" | "critical";
  priority_score: number;
  score_factors: {
    severity_points: number;
    evidence_points: number;
    urgency_points: number;
    total: number;
  };
  source_refs: {
    gap_ids: string[];
    answer_snapshot_ids: string[];
    evidence_snapshot_ids: string[];
    citation_ids: string[];
    citation_review_ids: string[];
    knowledge_source_ids: string[];
    fact_revision_ids: string[];
    fact_conflict_ids: string[];
    page_audit_run_ids: string[];
    page_audit_finding_ids: string[];
  };
  title: string;
  description: string;
  recommended_action: string;
  observed_at: string;
  snapshot_sha256: string;
  created_at: string;
};

export type OpportunityDerivation = {
  derivation_run_id: string;
  project_id: string;
  contract_version: "airank.intervention-opportunity.v1";
  policy_version: "airank.cross-domain-opportunity-policy.v1";
  source_basis_sha256: string;
  evaluated_at: string;
  knowledge_window_days: number;
  previous_run_id: string | null;
  source_counts: Record<OpportunitySourceKind, number>;
  opportunity_count: number;
  new_count: number;
  persisting_count: number;
  cleared_count: number;
  cleared_opportunity_ids: string[];
  opportunities: InterventionOpportunity[];
  created_by: string;
  created_at: string;
  idempotent_replay: boolean;
};

export type OpportunityList = {
  project_id: string;
  contract_version: "airank.intervention-opportunity.v1";
  policy_version: "airank.cross-domain-opportunity-policy.v1";
  latest_derivation_run: OpportunityDerivation | null;
  state_counts: Record<"blocked_evidence" | "ready_for_action" | "monitor", number>;
  source_counts: Record<OpportunitySourceKind, number>;
  opportunities: InterventionOpportunity[];
};

export type OpportunityAction = {
  action_id: string;
  project_id: string;
  opportunity_id: string;
  contract_version: "airank.opportunity-action.v1";
  source_kind: OpportunitySourceKind;
  action_type: string;
  status: "open" | "in_progress" | "evidence_blocked" | "verified_not_observed" | "waived";
  source_snapshot_id: string;
  source_derivation_run_id: string;
  source_snapshot_sha256: string;
  source_evidence_sha256: string;
  latest_snapshot_id: string;
  latest_derivation_run_id: string;
  latest_snapshot_sha256: string;
  latest_evidence_sha256: string;
  routing_state: "unrestricted_legacy" | "team_routed" | "blocked";
  routing_team_id: string | null;
  routing_route_version: number | null;
  routing_member_id: string | null;
  routing_member_version: number | null;
  external_membership_verified: boolean;
  assigned_to: string | null;
  assigned_at: string | null;
  due_at: string;
  sla_state: "on_track" | "due_soon" | "overdue" | "final";
  action_note: string;
  verification_run_id: string | null;
  verification_basis_sha256: string | null;
  closure_reason: string | null;
  effect_claim_allowed: false;
  event_count: number;
  last_event_sha256: string;
  escalation_count: number;
  pending_escalation_count: number;
  external_delivery_verified: boolean;
  latest_escalated_at: string | null;
  created_by: string;
  updated_by: string;
  version: number;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
  idempotent_replay: boolean;
};

export type OpportunityActionList = {
  project_id: string;
  contract_version: "airank.opportunity-action.v1";
  actions: OpportunityAction[];
  open_count: number;
  evidence_blocked_count: number;
  overdue_count: number;
  final_count: number;
};

export type OpportunityActionTeamMember = {
  member_id: string;
  user_id: string;
  display_name: string | null;
  priority: number;
  max_active_actions: number;
  active_action_count: number;
  at_capacity: boolean;
  receives_escalations: boolean;
  status: "active" | "disabled";
  membership_source: "manual" | "yudao";
  external_membership_verified: boolean;
  version: number;
  updated_at: string;
};

export type OpportunityActionTeam = {
  team_id: string;
  name: string;
  status: "active" | "disabled";
  external_source: "manual" | "yudao";
  external_group_id: string | null;
  external_sync_state: "not_configured" | "pending" | "verified" | "stale" | "failed";
  version: number;
  member_count: number;
  members: OpportunityActionTeamMember[];
  created_at: string;
  updated_at: string;
};

export type OpportunityActionRoute = {
  route_id: string;
  source_kind: OpportunitySourceKind;
  team_id: string;
  team_name: string;
  routing_strategy: "manual_claim";
  status: "active" | "disabled";
  version: number;
  eligible_member_count: number;
  escalation_recipient_count: number;
  routing_ready: boolean;
  updated_at: string;
};

export type OpportunityActionRouting = {
  project_id: string;
  contract_version: "airank.opportunity-action-routing.v1";
  routing_mode: "unrestricted_legacy" | "team_routed" | "blocked";
  teams: OpportunityActionTeam[];
  routes: OpportunityActionRoute[];
  missing_source_kinds: OpportunitySourceKind[];
  known_limitations: string[];
  idempotent_replay: boolean;
};

export type OpportunityActionDirectoryBinding = {
  binding_id: string;
  team_id: string;
  team_name: string;
  external_source: "yudao";
  external_group_id: string;
  status: "active" | "disabled";
  sync_enabled: boolean;
  sync_interval_minutes: number;
  default_priority: number;
  default_max_active_actions: number;
  default_receives_escalations: boolean;
  last_sync_state: "not_configured" | "pending" | "verified" | "stale" | "failed";
  last_sync_run_id: string | null;
  last_synced_at: string | null;
  next_sync_at: string | null;
  last_error_code: string | null;
  version: number;
  updated_at: string;
};

export type OpportunityActionDirectoryRun = {
  run_id: string;
  binding_id: string;
  binding_version: number;
  team_id: string;
  external_group_id: string;
  status: "running" | "succeeded" | "failed";
  endpoint_host: string | null;
  response_sha256: string | null;
  discovered_member_count: number;
  active_member_count: number;
  created_member_count: number;
  updated_member_count: number;
  unchanged_member_count: number;
  disabled_member_count: number;
  manual_conflict_count: number;
  error_code: string | null;
  retryable: boolean;
  started_at: string;
  finished_at: string | null;
  idempotent_replay: boolean;
};

export type OpportunityActionDirectory = {
  project_id: string;
  contract_version: "airank.opportunity-action-directory-sync.v1";
  bindings: OpportunityActionDirectoryBinding[];
  recent_sync_runs: OpportunityActionDirectoryRun[];
  configured_team_count: number;
  verified_team_count: number;
  known_limitations: string[];
};

export type OpportunityDependency = {
  dependency_id: string;
  action_id: string;
  prerequisite_action_id: string;
  prerequisite_status: OpportunityAction["status"];
  dependency_type: "finish_to_start" | "evidence_prerequisite";
  status: "active" | "waived";
  satisfied: boolean;
  rationale: string;
  waiver_reason: string | null;
  version: number;
  created_by: string;
  updated_by: string;
  created_at: string;
  updated_at: string;
  idempotent_replay: boolean;
};

export type OpportunityExecutionPlan = {
  plan_id: string;
  action_id: string;
  action_status: OpportunityAction["status"];
  contract_version: "airank.opportunity-execution-plan.v1";
  status: "draft" | "approved";
  estimate_source: "human_estimate";
  estimated_effort_hours: string;
  estimated_budget_amount: string;
  currency: "CNY";
  planned_start_at: string | null;
  planned_due_at: string | null;
  assumptions: string;
  outcome_forecast_allowed: false;
  dependencies: OpportunityDependency[];
  unsatisfied_dependency_count: number;
  version: number;
  event_count: number;
  last_event_sha256: string;
  created_by: string;
  updated_by: string;
  created_at: string;
  updated_at: string;
  idempotent_replay: boolean;
};

export type OpportunityExecutionPortfolio = {
  project_id: string;
  contract_version: "airank.opportunity-execution-plan.v1";
  planning_required_count: number;
  approved_plan_count: number;
  planning_coverage_complete: boolean;
  total_estimated_effort_hours: string | null;
  total_estimated_budget_amount: string | null;
  currency: "CNY";
  topological_order: string[][];
  blocked_action_ids: string[];
  plans: OpportunityExecutionPlan[];
  unplanned_action_ids: string[];
  outcome_forecast_allowed: false;
  known_limitations: string[];
};

export type OpportunityCapacityException = {
  exception_id: string;
  exception_date: string;
  available_hours: string;
  reason: string;
  exception_source: "manual";
  external_calendar_verified: false;
  version: number;
  created_by: string;
  updated_by: string;
  created_at: string;
  updated_at: string;
  idempotent_replay: boolean;
};

export type OpportunityCapacityCalendar = {
  calendar_id: string;
  team_id: string;
  member_id: string;
  user_id: string;
  display_name: string | null;
  member_status: "active" | "disabled";
  member_version: number;
  contract_version: "airank.opportunity-capacity-calendar.v1";
  timezone: string;
  weekly_capacity_hours: string;
  workdays: number[];
  assumptions: string;
  capacity_source: "manual";
  external_calendar_verified: false;
  status: "active" | "disabled";
  exceptions: OpportunityCapacityException[];
  version: number;
  event_count: number;
  last_event_sha256: string;
  created_by: string;
  updated_by: string;
  created_at: string;
  updated_at: string;
  idempotent_replay: boolean;
};

export type OpportunityScheduleWindow = {
  window_code: "day_0_30" | "day_31_60" | "day_61_90";
  start_date: string;
  end_date: string;
  available_capacity_hours: string;
  scheduled_effort_hours: string;
  utilization_rate: string | null;
  action_count: number;
  blocked_action_count: number;
};

export type OpportunityScheduleItem = {
  item_id: string;
  action_id: string;
  action_version: number;
  plan_id: string | null;
  plan_version: number | null;
  member_id: string | null;
  member_version: number | null;
  calendar_id: string | null;
  calendar_version: number | null;
  window_code: "day_0_30" | "day_31_60" | "day_61_90" | "outside_horizon" | "unscheduled";
  schedule_state: "scheduled" | "unplanned" | "dates_missing" | "owner_missing" | "calendar_missing" | "calendar_unavailable" | "dependency_blocked" | "capacity_exceeded" | "outside_horizon";
  reason_codes: string[];
  planned_start_at: string | null;
  planned_due_at: string | null;
  estimated_effort_hours: string | null;
  scheduled_effort_hours: string;
  peak_daily_utilization: string | null;
  item_sha256: string;
};

export type OpportunityScheduleRun = {
  run_id: string;
  project_id: string;
  contract_version: "airank.opportunity-capacity-schedule.v1";
  policy_version: "airank.opportunity-capacity-policy.v1";
  as_of_date: string;
  horizon_days: 90;
  status: "complete";
  source_manifest_sha256: string;
  result_sha256: string;
  action_count: number;
  scheduled_count: number;
  blocked_count: number;
  outside_horizon_count: number;
  capacity_conflict_count: number;
  schedule_feasible: boolean;
  windows: OpportunityScheduleWindow[];
  items: OpportunityScheduleItem[];
  outcome_forecast_allowed: false;
  known_limitations: string[];
  created_by: string;
  created_at: string;
  idempotent_replay: boolean;
};

export type OpportunityCapacityPortfolio = {
  project_id: string;
  contract_version: "airank.opportunity-capacity-calendar.v1";
  active_member_count: number;
  configured_calendar_count: number;
  capacity_coverage_complete: boolean;
  calendars: OpportunityCapacityCalendar[];
  latest_schedule: OpportunityScheduleRun | null;
  outcome_forecast_allowed: false;
  known_limitations: string[];
};

export type ReportItem = {
  report_id: string;
  title: string;
  desc: string;
  date: string;
  status: string;
};

export type ReportList = {
  project_id: string;
  tenant_id: string;
  reports: ReportItem[];
};

export type ReportEvidencePacket = {
  packet_id: string;
  report_id: string;
  tenant_id: string;
  project_id: string;
  schema_version: "airank.report-evidence-packet.v1" | "airank.report-evidence-packet.v2" | "airank.report-evidence-packet.v3" | "airank.report-evidence-packet.v4" | "airank.report-evidence-packet.v5" | "airank.report-evidence-packet.v6" | "airank.report-evidence-packet.v7";
  status: "ready";
  object_ref_id: string;
  integrity_audit_id: string | null;
  content_url: string;
  content_type: "application/json" | "application/zip";
  byte_size: number;
  content_sha256: string;
  report_sha256: string;
  created_by: string;
  created_at: string;
  summary: {
    sample_count: number;
    citation_count: number;
    fact_claim_count: number;
    fact_accuracy_review_count: number;
    source_host_count: number;
    source_effective_classification_count: number;
    source_authority_resolved_count: number;
    source_authority_coverage_rate: number | null;
    source_authority_summary_eligible: boolean;
    evidence_object_count: number;
    known_limitation_count: number;
  };
  idempotent_replay: boolean;
};

export type KnowledgeSource = {
  source_id: string;
  title: string;
  source_type: string;
  source_uri: string | null;
  content_sha256: string;
  authority_level: string;
  risk_level: string;
  status: "active" | "stale" | "disabled";
  revision_number: number;
  segment_count: number;
  captured_at: string;
  valid_until: string | null;
};

export type KnowledgeSourceInput = {
  idempotency_key: string;
  source_type: string;
  title: string;
  content_text: string;
  source_uri?: string;
  authority_level: "official" | "verified_third_party" | "community" | "unclassified";
  risk_level: "low" | "medium" | "high" | "restricted";
  valid_until?: string;
};

export type KnowledgeSyncPolicy = {
  policy_id: string;
  tenant_id: string;
  project_id: string;
  anchor_source_id: string;
  current_source_id: string;
  source_uri: string;
  interval_hours: number;
  enabled: boolean;
  version: number;
  next_run_at: string;
  last_run_id: string | null;
  last_status: "unchanged" | "changed" | "failed" | "blocked" | null;
  last_checked_at: string | null;
  created_by: string;
  updated_by: string;
  created_at: string;
  updated_at: string;
  idempotent_replay: boolean;
};

export type KnowledgeSyncRun = {
  run_id: string;
  tenant_id: string;
  project_id: string;
  policy_id: string;
  source_before_id: string;
  source_after_id: string | null;
  job_id: string;
  status: "queued" | "running" | "unchanged" | "changed" | "failed" | "blocked";
  requested_url: string;
  final_url: string | null;
  evidence_grade: string | null;
  response_status: number | null;
  content_type: string | null;
  response_bytes: number | null;
  raw_content_sha256: string | null;
  visible_text_sha256: string | null;
  raw_object_ref_id: string | null;
  text_object_ref_id: string | null;
  connected_ip: string | null;
  redirect_count: number | null;
  error_code: string | null;
  error_message: string | null;
  scheduled_at: string;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
  idempotent_replay: boolean;
};

export type KnowledgeSearchResult = {
  rank: number;
  segment_id: string;
  source_id: string;
  source_revision_number: number;
  source_title: string;
  source_uri: string | null;
  segment_index: number;
  text: string;
  source_start: number;
  source_end: number;
  content_sha256: string;
  match_type: "exact" | "terms";
  matched_terms: string[];
};

export type KnowledgeSearch = {
  query: string;
  retrieval_mode: "lexical_only";
  vector_status: "not_configured";
  matched_count: number;
  returned_count: number;
  candidate_limit_reached: boolean;
  results: KnowledgeSearchResult[];
};

export type FactRevision = {
  fact_id: string;
  revision_id: string;
  title: string;
  fact_type: string;
  subject_type: "general" | "brand" | "company" | "product" | "competitor" | "solution_type";
  subject_ref_id: string | null;
  fact_text: string;
  content_sha256: string;
  revision_number: number;
  status: "proposed" | "approved" | "superseded" | "rejected";
  source_ids: string[];
  risk_level: string;
  disclosure: string;
  created_at: string;
  reviewed_by: string | null;
  reviewed_at: string | null;
  valid_until: string | null;
  eligible_for_generation: boolean;
  eligibility_reason: string;
};

export type FactConflict = {
  conflict_id: string;
  fact_id: string;
  left_revision_id: string;
  right_revision_id: string;
  conflict_type: string;
  description: string;
  status: "open" | "resolved_left" | "resolved_right" | "resolved_new_revision" | "dismissed";
  detected_at: string;
  resolved_by: string | null;
  resolved_at: string | null;
  resolution_note: string | null;
};

export type BrandGraphEntity = {
  entity_id: string;
  entity_role: "target" | "competitor" | "related";
  entity_kind: "brand" | "company" | "product" | "service";
  canonical_name: string;
  normalized_name: string;
  website_url: string | null;
  external_ref_type: string | null;
  external_ref_id: string | null;
  usage_scope: "measurement_only" | "public_and_measurement";
  fact_revision_id: string;
  evidence_manifest_sha256: string;
  status: "active" | "disabled";
  version: number;
  created_by: string;
  updated_by: string;
  created_at: string;
  updated_at: string;
};

export type BrandGraphAlias = {
  alias_id: string;
  entity_id: string;
  alias_text: string;
  normalized_alias: string;
  alias_type: "official" | "english" | "abbreviation" | "former_name" | "misspelling" | "product_variant";
  language_code: string | null;
  usage_scope: "measurement_only" | "public_and_measurement";
  fact_revision_id: string;
  evidence_manifest_sha256: string;
  status: "active" | "disabled";
  version: number;
};

export type BrandGraphRelation = {
  relation_id: string;
  subject_entity_id: string;
  predicate: "legal_name_of" | "owns_product" | "offers" | "competitor_of" | "former_name_of" | "part_of";
  object_entity_id: string;
  usage_scope: "measurement_only" | "public_and_measurement";
  fact_revision_id: string;
  evidence_manifest_sha256: string;
  status: "active" | "disabled";
  version: number;
};

export type BrandGraphSnapshot = {
  snapshot_id: string;
  status: "governed" | "partial" | "blocked" | "legacy_unverified";
  graph_sha256: string;
  source_manifest_sha256: string;
  measurement_lexicon: {
    target: { canonical_name: string; brand_aliases: string[]; company_names: string[]; product_names: string[] };
    competitors: Array<{ entity_id: string; canonical_name: string; aliases: string[] }>;
  };
  public_jsonld: Record<string, unknown>;
  ambiguous_aliases: Array<{ normalized_value: string; observed_values: string[]; entity_ids: string[]; excluded_from_measurement: boolean }>;
  known_limitations: string[];
  created_by: string;
  created_at: string;
};

export type BrandGraphPortfolio = {
  contract_version: "airank.brand-graph.v1";
  project_id: string;
  entities: BrandGraphEntity[];
  aliases: BrandGraphAlias[];
  relations: BrandGraphRelation[];
  latest_snapshot: BrandGraphSnapshot | null;
  measurement_ready: boolean;
  public_export_ready: boolean;
  known_limitations: string[];
};

export type KnowledgeGovernanceAlert = {
  alert_id: string;
  kind: "source_stale" | "source_expired" | "source_expiring" | "fact_expired" | "fact_expiring" | "open_conflict";
  severity: "critical" | "warning";
  entity_type: "knowledge_source" | "fact_revision" | "fact_conflict";
  entity_id: string;
  title: string;
  message: string;
  due_at: string | null;
  days_remaining: number | null;
};

export type KnowledgeGovernance = {
  status: "healthy" | "attention_required";
  as_of: string;
  within_days: number;
  source_count: number;
  approved_fact_count: number;
  stale_source_count: number;
  expired_source_count: number;
  expiring_source_count: number;
  expired_fact_count: number;
  expiring_fact_count: number;
  open_conflict_count: number;
  action_required_count: number;
  alerts: KnowledgeGovernanceAlert[];
};

export type AnswerSample = {
  snapshot_id: string;
  run_id: string;
  task_id: string | null;
  question_id: string;
  provider: string;
  cohort_type: string;
  prompt_version_id: string;
  sample_index: number;
  session_id: string;
  collector_surface: string;
  evidence_level: string;
  sample_status: string;
  answer_excerpt: string;
  answer_sha256: string | null;
  brand_mentioned: boolean;
  brand_rank: number | null;
  mention_class: string;
  model_name: string | null;
  search_enabled: boolean | null;
  external_trace_id: string | null;
  citation_count: number;
  created_at: string;
};

export type EvidenceObject = {
  object_ref_id: string | null;
  object_uri: string | null;
  content_type: string | null;
  byte_size: number | null;
  sha256: string | null;
  content_url: string | null;
};

export type EvidenceIntegrityFinding = {
  finding_id: string;
  entity_type: string;
  entity_id: string;
  object_type: string | null;
  status: "verified" | "metadata_invalid" | "unavailable" | "driver_mismatch" | "hash_mismatch" | "size_mismatch" | "scope_too_large";
  blocking: boolean;
  expected_sha256: string | null;
  actual_sha256: string | null;
  expected_byte_size: number | null;
  actual_byte_size: number | null;
  details: Record<string, unknown>;
  created_at: string;
};

export type EvidenceIntegrityAudit = {
  audit_id: string;
  tenant_id: string;
  project_id: string;
  policy_version: "airank.evidence-integrity.v1" | "airank.evidence-integrity.v2";
  scope: "project";
  status: "passed" | "blocked" | "failed";
  entity_count: number;
  verified_count: number;
  blocking_finding_count: number;
  unavailable_count: number;
  hash_mismatch_count: number;
  size_mismatch_count: number;
  metadata_invalid_count: number;
  manifest_sha256: string;
  request_sha256: string;
  requested_by: string;
  trace_id: string;
  started_at: string;
  completed_at: string;
  findings: EvidenceIntegrityFinding[];
  idempotent_replay: boolean;
};

export type AnswerSampleDetail = AnswerSample & {
  project_id: string;
  answer_text: string;
  raw_response_sha256: string;
  raw_response: Record<string, unknown>;
  request_metadata: Record<string, unknown>;
  evidence_snapshot_id: string;
  evidence_captured_at: string;
  screenshot: EvidenceObject;
  source_panel: EvidenceObject;
  attempts: Array<{
    attempt_id: string;
    job_id: string;
    attempt_number: number;
    status: "running" | "succeeded" | "failed" | "blocked" | "unknown" | "suppressed";
    provider: string;
    collector_surface: string;
    answer_snapshot_id: string | null;
    evidence_snapshot_id: string | null;
    provider_request_id: string | null;
    error_code: string | null;
    error_message: string | null;
    metadata: Record<string, unknown>;
    started_at: string;
    completed_at: string | null;
  }>;
  citations: Array<{
    citation_id: string;
    citation_order: number;
    title: string | null;
    url: string;
    host: string | null;
    source_type: string | null;
    cited_text: string | null;
    relevance_score: number | null;
    metadata: Record<string, unknown>;
  }>;
};

export type AnswerSampleCollection = {
  samples: AnswerSample[];
  runId: string | null;
  limit: number;
  total: number;
  validCount: number;
  validUnmentionedCount: number;
  citationSampleCount: number;
};

export type CitationSupportBundle = {
  snapshot_id: string;
  claims: Array<{
    claim_id: string;
    snapshot_id: string;
    claim_text: string;
    answer_start: number;
    answer_end: number;
    answer_sha256: string;
    claim_sha256: string;
    extraction_method: "manual" | "ai_assisted";
    extractor_version: string;
    claim_kind: "unclassified" | "brand_fact" | "competitor_fact" | "general_fact" | "opinion";
    subject_entity_text: string | null;
    created_by: string;
    created_at: string;
  }>;
  reviews: Array<{
    review_id: string;
    claim_id: string;
    citation_id: string;
    support_label: "supports" | "contradicts" | "insufficient";
    evidence_grade: "provider_excerpt_only" | "source_panel_capture" | "source_page_snapshot";
    source_excerpt: string;
    source_content_sha256: string;
    source_object_ref_id: string | null;
    source_capture_id: string | null;
    source_segment_id: string | null;
    source_start: number | null;
    source_end: number | null;
    rationale: string;
    review_method: "human" | "ai_assisted";
    reviewed_by: string;
    reviewed_at: string;
    supersedes_review_id: string | null;
    review_case_id: string | null;
    reviewer_role: "single" | "primary" | "secondary" | "adjudicator";
    review_case_status: "single_review" | "creating" | "awaiting_secondary" | "disputed" | "agreed" | "adjudicated" | "void";
    review_case_purpose: "single_review" | "production" | "benchmark";
    evidence_verified: boolean;
    commercially_verified: boolean;
  }>;
  metrics: {
    selected_citation_count: number;
    claim_count: number;
    review_count: number;
    commercially_verified_review_count: number;
    supports_count: number;
    contradicts_count: number;
    insufficient_count: number;
    citation_support_rate: number | null;
    known_limitations: string[];
  };
};

export type FactAccuracyBundle = {
  snapshot_id: string;
  claims: CitationSupportBundle["claims"];
  reviews: Array<{
    review_id: string;
    claim_id: string;
    verdict: "accurate" | "inaccurate" | "outdated" | "insufficient_evidence";
    evidence_grade: "approved_fact_source_boundary" | "no_approved_fact";
    fact_revision_id: string | null;
    knowledge_source_id: string | null;
    knowledge_segment_id: string | null;
    fact_revision_sha256: string | null;
    source_content_sha256: string | null;
    quoted_text: string | null;
    quoted_text_sha256: string | null;
    source_start: number | null;
    source_end: number | null;
    rationale: string;
    review_method: "human" | "ai_assisted";
    reviewed_by: string;
    reviewed_at: string;
    supersedes_review_id: string | null;
    review_case_id: string | null;
    reviewer_role: "single" | "primary" | "secondary" | "adjudicator";
    review_case_status: "single_review" | "creating" | "awaiting_secondary" | "disputed" | "agreed" | "adjudicated" | "void";
    review_case_purpose: "single_review" | "production" | "benchmark";
    evidence_verified: boolean;
    commercially_verified: boolean;
    idempotent_replay: boolean;
  }>;
  metrics: {
    registered_claim_count: number;
    factual_claim_count: number;
    reviewed_claim_count: number;
    commercially_verified_claim_count: number;
    decisive_claim_count: number;
    accurate_count: number;
    inaccurate_count: number;
    outdated_count: number;
    insufficient_evidence_count: number;
    evaluation_coverage_rate: number | null;
    fact_accuracy: number | null;
    known_limitations: string[];
  };
};

export type EvidenceReviewDecision = {
  reviewer_role: "primary" | "secondary" | "adjudicator";
  label: string;
  rationale: string;
  reviewed_by: string;
  reviewed_at: string;
  review_id: string;
};

export type EvidenceReviewAssignment = {
  assignment_id: string | null;
  case_id: string;
  reviewer_role: "secondary" | "adjudicator";
  state: "unassigned" | "assigned_to_me" | "assigned_to_other" | "expired" | "completed" | "released";
  owned_by_current_actor: boolean;
  sla_state: "on_track" | "due_soon" | "overdue";
  action_available_at: string;
  due_at: string;
  assigned_at: string | null;
  lease_expires_at: string | null;
  last_heartbeat_at: string | null;
  completed_at: string | null;
  released_at: string | null;
  release_reason: string | null;
  version: number | null;
  idempotent_replay: boolean;
};

export type EvidenceReviewCase = {
  case_id: string;
  tenant_id: string;
  project_id: string;
  snapshot_id: string;
  review_kind: "citation_support" | "fact_accuracy";
  claim_id: string;
  citation_id: string | null;
  evidence_basis_sha256: string;
  purpose: "production" | "benchmark";
  benchmark_version: string | null;
  status: "creating" | "awaiting_secondary" | "disputed" | "agreed" | "adjudicated" | "void";
  consensus_label: string | null;
  decision_count: number;
  current_actor_role: "primary" | "secondary" | "adjudicator" | null;
  next_action: "submit_secondary" | "adjudicate" | "complete" | "none";
  assignment: EvidenceReviewAssignment | null;
  visible_decisions: EvidenceReviewDecision[];
  created_by: string;
  finalized_by: string | null;
  created_at: string;
  finalized_at: string | null;
  version: number;
  idempotent_replay: boolean;
};

export type ReviewQualityMetrics = {
  case_count: number;
  independently_reviewed_case_count: number;
  finalized_case_count: number;
  awaiting_secondary_count: number;
  disputed_count: number;
  agreement_count: number;
  disagreement_count: number;
  adjudicated_count: number;
  raw_agreement_rate: number | null;
  cohen_kappa: number | null;
  benchmark_minimum_case_count: number;
  benchmark_minimum_kappa: number;
  benchmark_ready: boolean;
  benchmark_quality_passed: boolean;
  known_limitations: string[];
};

export type EvidenceReviewQueue = {
  project_id: string;
  snapshot_id: string | null;
  cases: EvidenceReviewCase[];
  production_quality: ReviewQualityMetrics;
  benchmark_quality: ReviewQualityMetrics;
};

export type EvidenceReviewInbox = {
  project_id: string;
  cases: EvidenceReviewCase[];
  actionable_count: number;
  awaiting_secondary_count: number;
  adjudication_count: number;
  assigned_to_me_count: number;
  unassigned_count: number;
  overdue_count: number;
  limit: number;
  next_cursor: string | null;
};

export type EvidenceReviewEscalationList = {
  project_id: string;
  escalation_count: number;
  pending_count: number;
  published_count: number;
  failed_count: number;
  canceled_count: number;
  escalations: Array<{
    event_id: string;
    case_id: string;
    reviewer_role: "secondary" | "adjudicator";
    due_at: string;
    escalated_at: string;
    overdue_seconds: number;
    assignment_state: "unassigned" | "assigned" | "expired";
    routing_state: "unrestricted_legacy" | "resolved" | "blocked_role_unconfigured" | "blocked_team_inactive" | "blocked_no_recipients";
    routing_team_id: string | null;
    routing_route_version: number | null;
    eligible_recipient_count: number;
    external_sync_state: "not_configured" | "pending" | "verified" | "stale" | "failed";
    outbox_status: "pending" | "published" | "failed" | "canceled";
    external_delivery_verified: boolean;
    delivery_channel: "webhook" | null;
    delivery_attempt_count: number;
    delivery_receipt_id: string | null;
    provider_receipt_id: string | null;
    delivered_at: string | null;
    delivery_endpoint_host: string | null;
    delivery_response_status: number | null;
    delivery_response_sha256: string | null;
  }>;
};

export type EvidenceReviewerRouting = {
  project_id: string;
  routing_mode: "unrestricted_legacy" | "team_routed" | "blocked";
  external_sync_state: "not_configured" | "pending" | "verified" | "stale" | "failed";
  teams: Array<{
    team_id: string;
    name: string;
    status: "active" | "disabled";
    external_source: "manual" | "yudao";
    external_group_id: string | null;
    external_sync_state: "not_configured" | "pending" | "verified" | "stale" | "failed";
    version: number;
    member_count: number;
    members: Array<{
      member_id: string;
      user_id: string;
      display_name: string | null;
      reviewer_role: "secondary" | "adjudicator";
      priority: number;
      max_active_assignments: number;
      receives_escalations: boolean;
      status: "active" | "disabled";
      membership_source: "manual" | "yudao";
      external_membership_verified: boolean;
      version: number;
      updated_at: string;
    }>;
    created_at: string;
    updated_at: string;
    idempotent_replay: boolean;
  }>;
  routes: Array<{
    route_id: string;
    reviewer_role: "secondary" | "adjudicator";
    team_id: string;
    team_name: string;
    routing_strategy: "manual_claim";
    status: "active" | "disabled";
    version: number;
    eligible_member_count: number;
    escalation_recipient_count: number;
    routing_ready: boolean;
    updated_at: string;
  }>;
  sync_bindings: Array<{
    binding_id: string;
    team_id: string;
    team_name: string;
    reviewer_role: "secondary" | "adjudicator";
    external_source: "yudao";
    external_group_id: string;
    status: "active" | "disabled";
    sync_enabled: boolean;
    sync_interval_minutes: number;
    default_priority: number;
    default_max_active_assignments: number;
    default_receives_escalations: boolean;
    last_sync_state: "not_configured" | "pending" | "verified" | "stale" | "failed";
    last_sync_run_id: string | null;
    last_synced_at: string | null;
    next_sync_at: string | null;
    last_error_code: string | null;
    version: number;
    updated_at: string;
  }>;
  recent_sync_runs: Array<{
    run_id: string;
    binding_id: string;
    team_id: string;
    reviewer_role: "secondary" | "adjudicator";
    external_group_id: string;
    status: "running" | "succeeded" | "failed";
    endpoint_host: string | null;
    response_sha256: string | null;
    discovered_member_count: number;
    active_member_count: number;
    upserted_member_count: number;
    disabled_member_count: number;
    error_code: string | null;
    retryable: boolean;
    started_at: string;
    finished_at: string | null;
    idempotent_replay: boolean;
  }>;
  known_limitations: string[];
};

export type CitationSourceCapture = {
  capture_id: string;
  tenant_id: string;
  project_id: string;
  citation_id: string;
  job_id: string;
  requested_url: string;
  final_url: string | null;
  status: "queued" | "running" | "completed" | "blocked" | "failed";
  capture_version: string;
  evidence_grade: string | null;
  response_status: number | null;
  content_type: string | null;
  response_bytes: number | null;
  content_sha256: string | null;
  visible_text_sha256: string | null;
  raw_object_ref_id: string | null;
  text_object_ref_id: string | null;
  connected_ip: string | null;
  redirect_count: number | null;
  error_code: string | null;
  error_message: string | null;
  requested_by: string;
  segments: Array<{
    segment_id: string;
    segment_index: number;
    source_start: number;
    source_end: number;
    segment_text: string;
    segment_sha256: string;
  }>;
  segments_loaded: boolean;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
  idempotent_replay: boolean;
};

export type CitationCaptureBatch = {
  snapshot_id: string;
  requested_count: number;
  queued_count: number;
  idempotent_replay_count: number;
  captures: CitationSourceCapture[];
};

export type SourceClassificationRevision = {
  revision_id: string;
  revision_number: number;
  normalized_host: string;
  source_category_l1:
    | "brand_corporate"
    | "government_public"
    | "news_media"
    | "vertical_professional"
    | "platform_community"
    | "business_services"
    | "research_documentation"
    | "search_page_proxy"
    | "other";
  source_type: string;
  ecosystem: string | null;
  classification_status: "reviewed" | "curated";
  classification_method: "human_review" | "dataset_import";
  classification_confidence: "low" | "medium" | "high";
  authority_level: "unknown" | "low" | "medium" | "high" | "official";
  usage_policy: "primary_evidence" | "context_only" | "lead_only" | "prohibited";
  risk_level: "low" | "medium" | "high" | "critical";
  evidence_note: string;
  evidence_url: string | null;
  source_dataset_name: string | null;
  source_dataset_version: string | null;
  valid_until: string | null;
  reviewed_by: string;
  reviewed_at: string;
  supersedes_revision_id: string | null;
  request_sha256: string;
  effective: boolean;
  idempotent_replay: boolean;
};

export type SourceRegistryEntry = {
  tenant_id: string;
  project_id: string;
  normalized_host: string;
  reviewable: boolean;
  citation_count: number;
  sample_count: number;
  provider_count: number;
  first_seen_at: string;
  last_seen_at: string;
  classification_status: "unclassified" | "reviewed" | "curated";
  current_revision: SourceClassificationRevision | null;
  history: SourceClassificationRevision[];
};

export type MeasurementQualityReport = {
  contract_version: "airank.measurement-quality.v4";
  run_id: string;
  status: "pass" | "blocked";
  publishable: boolean;
  data_sha256: string;
  report_sha256: string;
  metrics: Record<string, unknown>;
  checks: Array<{
    code: string;
    status: "pass" | "blocked" | "warning";
    actual: unknown;
    expected: string;
    detail: string;
  }>;
  surface_evidence: Array<{
    surface: "api" | "web" | "app" | "manual_import";
    evidence_level: "provider_api" | "consumer_web" | "consumer_app" | "manual_import";
    sample_count: number;
    valid_sample_count: number;
    evidence_complete_count: number;
    screenshot_count: number;
    source_panel_captured_count: number;
    source_panel_not_present_count: number;
    blocker_count: number;
  }>;
  known_limitations: string[];
};

export type GovernedContentAsset = {
  asset_id: string;
  tenant_id: string;
  project_id: string;
  asset_type: string;
  title: string;
  body_md: string;
  status: "draft" | "approved" | "rejected" | "changes_requested";
  generation_mode: "approved_fact_template" | "evidence_bound_page_blueprint" | "evidence_bound_comparison" | "evidence_bound_explainer";
  skill_id: string | null;
  skill_version: string | null;
  blueprint_sha256: string | null;
  section_count: number;
  fact_revision_ids: string[];
  claim_assertion_ids: string[];
  claim_support_ids: string[];
  created_at: string;
};

export type GovernedContentCreateInput = {
  assetType: "fact_page" | "product_page" | "faq" | "comparison_page" | "case_page" | "research_page" | "json_ld" | "llms_txt";
  title: string;
  direction: string;
  factRevisionIds: string[];
  createdBy: string;
};

export type ComparisonContentCreateInput = {
  title: string;
  direction: string;
  targetSubjectId: string;
  subjects: Array<{
    subject_id: string;
    display_name: string;
    subject_type: "brand" | "company" | "product" | "competitor" | "solution_type";
  }>;
  dimensions: Array<{ dimension_id: string; label: string }>;
  cells: Array<{ subject_id: string; dimension_id: string; fact_revision_ids: string[] }>;
  createdBy: string;
};

export type ExplainerContentCreateInput = {
  title: string;
  direction: string;
  subjectId: string;
  subjectType: "brand" | "company" | "product" | "competitor" | "solution_type";
  displayName: string;
  brandNames: string[];
  assignments: Array<{
    fact_revision_id: string;
    content_role: "definition" | "mechanism" | "step" | "criterion" | "misconception" | "faq" | "boundary";
  }>;
  createdBy: string;
};

export type ContentReview = {
  review_id: string;
  tenant_id: string;
  project_id: string;
  asset_id: string;
  content_sha256: string;
  action: "approved" | "rejected" | "changes_requested";
  fact_check_status: "passed" | "failed";
  risk_level: "low" | "medium" | "high";
  risk_findings: Array<{ code: string; severity: string; matched_text: string; message: string }>;
  override_reason: string | null;
  reviewed_by: string;
  reviewed_at: string;
};

export type BuyerQuestion = {
  question_id: string;
  question_text: string;
  question_type: string;
  intent_level: "high" | "medium" | "low";
  buyer_stage: "awareness" | "consideration" | "decision";
  recommended_providers: string[];
  coverage_status: "unknown" | "covered" | "gap" | "needs_scan";
  status: "suggested" | "confirmed" | "archived";
  source: string;
  question_version_id: string | null;
  taxonomy_version: string;
  dedupe_sha256: string | null;
  prompt_style: "exploratory" | "comparative" | "factual" | "procedural" | "evaluative";
  temporal_scope: "evergreen" | "current" | "historical";
  scenario: "generic" | "b2b_procurement" | "local_selection" | "replacement" | "risk_validation";
  region: string | null;
  cohort_type: "blind" | "assisted" | "comparison" | "fact_verification" | "unclassified";
  source_kind: "provided_seed" | "template_candidate" | "observed_query" | "imported";
  source_ref: string;
  evidence_level: "provided_seed" | "template_candidate" | "observed_query" | "imported";
  observed_query: boolean;
  reviewed_by: string | null;
  reviewed_at: string | null;
  review_note: string | null;
  created_at: string;
};

export type QuestionMapCompileInput = {
  companyNames?: string[];
  productTerms: string[];
  competitorNames: string[];
  regions: string[];
  seedQuestions: string[];
  observationBatchIds?: string[];
  includeTemplateCandidates: boolean;
  persist?: boolean;
};

export type QuestionMapCandidate = {
  question_id: string | null;
  duplicate_of_question_id: string | null;
  question_text: string;
  question_version_id: string;
  cohort_type: "blind" | "assisted" | "comparison" | "fact_verification";
  source_kind: "provided_seed" | "template_candidate" | "observed_query" | "imported";
  observed_query: boolean;
  provenance_records: Array<{
    source_ref: string;
    source_kind: string;
    evidence_grade: string;
    occurrence_count?: number;
    observed_at?: string | null;
    region?: string | null;
  }>;
  status: "preview" | "suggested" | "confirmed" | "archived" | "duplicate";
};

export type QuestionMapResult = {
  map_id: string;
  map_version_id: string;
  taxonomy_version: string;
  input_sha256: string;
  status: "preview" | "compiled";
  question_count: number;
  duplicate_count: number;
  persisted_count: number;
  idempotent_replay: boolean;
  created_by: string;
  created_at: string;
  questions: QuestionMapCandidate[];
};

export type QuestionReview = {
  review_id: string;
  question_id: string;
  previous_status: "suggested" | "confirmed" | "archived";
  status: "confirmed" | "archived";
  reviewed_by: string;
  reviewed_at: string;
  review_note: string;
  eligible_for_measurement: boolean;
  idempotent_replay: boolean;
};

export type QuestionObservationRecord = {
  observation_id: string;
  batch_id: string;
  row_number: number;
  source_record_id: string;
  question_text: string;
  normalized_question_text: string;
  dedupe_sha256: string;
  occurrence_count: number;
  observed_at: string | null;
  region: string | null;
  audience_role: string | null;
  content_sha256: string;
  pii_status: "none_detected";
  created_at: string;
};

export type QuestionObservationBatch = {
  batch_id: string;
  source_type: "site_search" | "search_console" | "customer_support" | "crm_sales" | "advertising_query" | "community_comment" | "provider_sample" | "other";
  source_name: string;
  access_mode: "user_provided";
  evidence_grade: "user_provided_snapshot";
  source_uri: string | null;
  date_range_start: string | null;
  date_range_end: string | null;
  payload_sha256: string;
  record_count: number;
  occurrence_count: number;
  pii_blocked_count: number;
  status: "ready" | "blocked";
  rights_attested: boolean;
  imported_by: string;
  created_at: string;
  blocked_records: Array<{ row_number: number; content_sha256: string; reasons: string[] }>;
  idempotent_replay: boolean;
};

export type QuestionObservationImportInput = {
  sourceType: QuestionObservationBatch["source_type"];
  sourceName: string;
  records: Array<{
    sourceRecordId: string;
    questionText: string;
    occurrenceCount: number;
    region?: string;
  }>;
  rightsAttested: boolean;
};

export type PublishPackage = {
  package_id: string;
  asset_id: string;
  snapshot_id: string;
  channel: "export" | "wordpress" | "http";
  status: "packaged" | "queued" | "publishing" | "delivered" | "failed" | "published";
  implementation_status: "ready" | "partial";
  idempotency_key: string;
  content_sha256: string;
  published_url: string | null;
  created_at: string;
};

export type PublishPackageCreateInput = {
  assetId: string;
  channel: "export" | "wordpress" | "http";
  targetEndpoint?: string;
};

export type PublicationEvidenceInput = {
  publishedUrl: string;
  baselineRunId: string;
  screenshotRefId?: string;
  screenshotSha256?: string;
};

export type PublishAttempt = {
  attempt_id: string;
  package_id: string;
  attempt_number: number;
  channel: string;
  status: "running" | "succeeded" | "failed";
  request_sha256: string;
  response_status: number | null;
  response_sha256: string | null;
  error_code: string | null;
  error_message: string | null;
  started_at: string;
  finished_at: string | null;
};

export type RetestWindow = {
  window_id: string;
  package_id: string;
  baseline_run_id: string | null;
  window_label: "T0" | "T+7" | "T+14" | "T+30";
  due_at: string;
  status: "scheduled" | "running" | "completed" | "completed_with_limitations" | "failed";
  compare_run_id: string | null;
  completed_at: string | null;
};

export type ProviderReadiness = {
  mode: "api" | "browser" | "mock";
  minimum_success_count: number;
  providers: Array<{
    provider: string;
    label: string;
    status: "ready" | "blocked";
    probe_level: "l2_interaction" | "l3_generation";
    generation_verified: boolean;
    blocker_code?: string;
    reason?: string;
  }>;
};

export type ProviderRouteStatus = {
  provider: string;
  label: string;
  route_id: string;
  endpoint_host: string;
  model: string;
  request_kind: "chat_completions" | "chat_completions_search" | "responses_web_search";
  configured: boolean;
  enabled: boolean;
  base_priority: number;
  effective_priority: number;
  priority_override?: number | null;
  control_version: number;
  updated_by?: string | null;
  reason?: string | null;
  updated_at?: string | null;
  configuration_fingerprint: string;
  request_count_24h: number;
  success_count_24h: number;
  failure_count_24h: number;
  success_rate_24h?: number | null;
  average_duration_ms_24h?: number | null;
  total_tokens_24h?: number | null;
  cost_amount_24h?: string | null;
  cost_currency?: string | null;
};

export type ProviderRouteControlInput = {
  enabled: boolean;
  priorityOverride: number | null;
  expectedVersion: number;
  reason: string;
};

export type ProviderCredentialVerification = {
  status: "verified";
  probe_level: "l3_generation";
  model: string;
  endpoint_host: string;
  request_id_present: boolean;
  provider_request_id_sha256: string | null;
  duration_ms: number;
  evidence_grade: string;
  verified_at: string;
};

export type ProviderCredentialStatus = {
  contract_version: "airank.provider-credential-vault.v1";
  provider: "doubao" | "qianwen" | "kimi" | "deepseek";
  label: string;
  route_id: string;
  source: "vault_active" | "vault_revoked" | "vault_key_unavailable" | "environment_legacy" | "unconfigured";
  status: "active" | "revoked" | "unconfigured" | "blocked";
  configured: boolean;
  credential_id: string | null;
  credential_version: number;
  secret_mask: string | null;
  fingerprint_prefix: string | null;
  encryption_key_id: string | null;
  fingerprint_key_id: string | null;
  algorithm: "aes-256-gcm" | null;
  verification: ProviderCredentialVerification | null;
  rotated_from_id: string | null;
  created_by: string | null;
  activated_at: string | null;
  revoked_at: string | null;
  latest_event_sha256: string | null;
  operation_id: string | null;
  idempotent_replay: boolean;
  known_limitations: string[];
};

export type ProviderCredentialPortfolio = {
  contract_version: "airank.provider-credential-vault.v1";
  keyring_contract_version: "airank.provider-credential-keyring.v1";
  keyring_status: "ready" | "blocked";
  credentials: ProviderCredentialStatus[];
  known_limitations: string[];
};

export type ProviderCredentialOperationEvent = {
  event_sequence: number;
  event_type: string;
  from_state: string | null;
  to_state: "claimed" | "external_started" | "succeeded" | "failed";
  request_sha256: string;
  previous_event_sha256: string | null;
  event_sha256: string;
  actor: string;
  trace_id: string;
  created_at: string;
};

export type ProviderCredentialOperation = {
  contract_version: "airank.operation-guard.v1";
  operation_id: string;
  operation_type: "provider_credential.upsert" | "provider_credential.revoke";
  provider: "doubao" | "qianwen" | "kimi" | "deepseek";
  route_id: string;
  state: "claimed" | "external_started" | "succeeded" | "failed";
  external_effect_started: boolean;
  request_sha256: string;
  request_key_id: string | null;
  error_code: string | null;
  created_by: string;
  trace_id: string;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
  reconciliation_required: boolean;
  replay_status: "available" | "in_progress" | "forbidden_unknown" | "forbidden_failed";
  response_credential_id: string | null;
  response_credential_version: number | null;
  response_status: string | null;
  events: ProviderCredentialOperationEvent[];
};

export type ProviderCredentialOperationList = {
  contract_version: "airank.operation-guard.v1";
  operations: ProviderCredentialOperation[];
  reconciliation_required_count: number;
};

export type InternalSkill = {
  skill_id: string;
  version: string;
  category: "measurement" | "research" | "knowledge" | "intervention" | "governance" | "delivery";
  dependencies: string[];
  provider_requirements: string[];
  evidence_level: string[];
  quality_rubric: Array<Record<string, unknown>>;
  promotion_policy: {
    required_suites: Array<"contract" | "holdout" | "adversarial">;
    minimum_pass_rate: number;
    required_evidence: string[];
  };
  evaluation: {
    local_eval_status: "passed" | "failed";
    total_cases: number;
    passed_cases: number;
    failed_cases: number;
    pass_rate: number;
    executed_suites: Array<"contract" | "holdout" | "adversarial">;
    promotion_eligible: boolean;
    promotion_blockers: string[];
    evaluation_sha256: string;
  };
  status: "ready" | "partial" | "blocked" | "disabled" | "dev_only";
  entrypoint: string;
};

export type SkillPromotionLedger = {
  ledger_version: string;
  source_sha256: Record<string, string>;
  skills: Array<{
    skill_id: string;
    version: string;
    decision: "promote_ready" | "retain_partial";
    evaluation_sha256: string;
    promotion_blockers: string[];
  }>;
};

export type ScanRunSummary = {
  run_id: string;
  status: "queued" | "running" | "completed" | "failed" | "canceled";
  metrics: Record<string, unknown>;
};

export type ScanRun = {
  run_id: string;
  tenant_id: string;
  project_id: string;
  name: string | null;
  run_type: "baseline" | "retest" | "manual";
  cohort_type: "blind" | "assisted" | "comparison" | "fact_verification";
  repetitions: number;
  collector_surfaces: Array<"api" | "web" | "app" | "manual_import">;
  status: "queued" | "running" | "completed" | "failed" | "canceled";
  provider_scope: string[];
  question_scope: { mode: "all_active" | "selected"; question_ids: string[] };
  entity_graph_snapshot_id: string | null;
  entity_graph_sha256: string | null;
  entity_graph_status: "governed" | "partial" | "blocked" | "legacy_unverified" | "not_available_dev";
  entity_graph_limitations: string[];
  metrics: Record<string, unknown>;
  error?: { code: string; message: string };
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
  updated_at: string;
};

export type ScanTask = {
  task_id: string;
  run_id: string;
  tenant_id: string;
  project_id: string;
  question_id: string;
  provider: string;
  cohort_type: string;
  prompt_version_id: string;
  sample_index: number;
  session_id: string;
  collector_surface: string;
  evidence_level: string;
  status: "queued" | "running" | "completed" | "failed" | "skipped";
  attempt_count: number;
  scheduled_at: string | null;
  started_at: string | null;
  finished_at: string | null;
  error?: { code: string; message: string };
  created_at: string;
  updated_at: string;
};

export type BrandCheckInput = {
  brandName: string;
  websiteUrl: string;
  industryHint?: string;
  competitorHints?: string[];
  buyerQuestions?: string[];
};

export type BrandCheckResult = {
  project: {
    project_id: string;
    brand_name: string;
    website_url: string;
    industry: string;
  };
  scanRun: ScanRunSummary;
  taskCount: number;
  assetBundle: AssetBundle;
  reports: ReportList;
  overview: ConsoleOverview;
};

export type AuthSession = {
  accessToken: string;
  tokenType: "Bearer";
  expiresIn: number | null;
  tenantId: string;
  yudaoTenantId: string;
  user: {
    userId: string;
    username: string | null;
    nickname: string | null;
  };
  devOnly: boolean;
};

export type ConsoleActionInput = {
  projectId: string;
  actionType: string;
  label: string;
  sourceRoute: string;
  entityType?: string;
  entityId?: string;
  payload?: Record<string, unknown>;
};

export type ConsoleActionReceipt = {
  action_id: string;
  tenant_id: string;
  project_id: string;
  action_type: string;
  entity_type: string | null;
  entity_id: string | null;
  recorded_at: string;
  status: "recorded";
};

export type AuthLoginInput = {
  username: string;
  password: string;
  yudaoTenantId: string;
};

type ConsoleOverviewPayload = {
  data: {
    project: ConsoleProject;
    metric_cards: ConsoleMetricCard[];
    data_status: "empty" | "collecting" | "provider_evidence" | "unverified";
    message: string;
  };
  meta: {
    trace_id: string;
    request_id: string;
  };
};

type AssetBundlePayload = {
  data: AssetBundle;
  meta: {
    trace_id: string;
    request_id: string;
  };
};

type ReportListPayload = {
  data: ReportList;
  meta: {
    trace_id: string;
    request_id: string;
  };
};

type ReportEvidencePacketPayload = {
  data: ReportEvidencePacket;
  meta: {
    trace_id: string;
    request_id: string;
  };
};

type BrandCheckPayload = {
  data: {
    project: {
      project_id: string;
      brand_name: string;
      website_url: string;
      industry: string;
    };
    scan_run: ScanRunSummary;
    tasks: Array<{ task_id: string; status: string }>;
    asset_bundle: AssetBundle;
    reports: ReportList;
    overview: {
      project: ConsoleProject;
      metric_cards: ConsoleMetricCard[];
      data_status: "empty" | "collecting" | "provider_evidence" | "unverified";
      message: string;
    };
  };
  meta: {
    trace_id: string;
    request_id: string;
  };
};

type AuthLoginPayload = {
  data: {
    access_token: string;
    token_type: "Bearer";
    expires_in: number | null;
    tenant_id: string;
    yudao_tenant_id: string;
    user: {
      user_id: string;
      username: string | null;
      nickname: string | null;
    };
    dev_only: boolean;
  };
  meta: {
    trace_id: string;
    request_id: string;
  };
};

type ConsoleActionPayload = {
  data: ConsoleActionReceipt;
  meta: {
    trace_id: string;
    request_id: string;
  };
};

export const fallbackConsoleOverview: ConsoleOverview = {
  project: {
    id: "",
    name: "尚未加载项目",
    website: "",
    industry: "",
    competitors: "",
    audience: "",
    date: "",
  },
  metricCards: [],
  dataStatus: "empty",
  message: "控制台 API 尚未返回真实项目数据。",
};

export const fallbackAssetBundle: AssetBundle = {
  project_id: "",
  tenant_id: "",
  completeness: 0,
  recommendation: "尚未读取真实内容资产。",
  assets: [],
};

export const fallbackReportList: ReportList = {
  project_id: "",
  tenant_id: "",
  reports: [],
};

function canUseStorage() {
  return typeof window !== "undefined" && typeof window.localStorage !== "undefined";
}

export function getStoredAuthSession(): AuthSession | null {
  if (!canUseStorage()) {
    return null;
  }

  const rawSession = window.localStorage.getItem(AUTH_SESSION_STORAGE_KEY);
  if (!rawSession) {
    return null;
  }

  try {
    const parsed = JSON.parse(rawSession) as Partial<AuthSession>;
    if (!parsed.accessToken || !parsed.tenantId || !parsed.yudaoTenantId || !parsed.user?.userId) {
      return null;
    }
    return parsed as AuthSession;
  } catch {
    return null;
  }
}

export function storeAuthSession(session: AuthSession): void {
  if (canUseStorage()) {
    window.localStorage.setItem(AUTH_SESSION_STORAGE_KEY, JSON.stringify(session));
  }
}

export function clearAuthSession(): void {
  if (canUseStorage()) {
    window.localStorage.removeItem(AUTH_SESSION_STORAGE_KEY);
  }
}

function mapAuthSession(payload: AuthLoginPayload): AuthSession {
  return {
    accessToken: payload.data.access_token,
    tokenType: payload.data.token_type,
    expiresIn: payload.data.expires_in,
    tenantId: payload.data.tenant_id,
    yudaoTenantId: payload.data.yudao_tenant_id,
    user: {
      userId: payload.data.user.user_id,
      username: payload.data.user.username,
      nickname: payload.data.user.nickname,
    },
    devOnly: payload.data.dev_only,
  };
}

async function readErrorMessage(response: Response, fallback: string): Promise<string> {
  try {
    const payload = (await response.json()) as { error?: { message?: string; code?: string } };
    return payload.error?.message || payload.error?.code || fallback;
  } catch {
    return fallback;
  }
}

function buildApiHeaders(tracePrefix: string): Record<string, string> {
  const session = getStoredAuthSession();
  const headers: Record<string, string> = {
    "tenant-id": session?.tenantId ?? "tenant_demo",
    "X-AIRank-Trace-Id": `${tracePrefix}_${Date.now()}`,
  };
  if (session?.accessToken) {
    headers.Authorization = `${session.tokenType} ${session.accessToken}`;
  }
  if (session?.user.userId) {
    headers["X-AIRank-User-Id"] = session.user.userId;
  }
  if (session?.yudaoTenantId) {
    headers["X-Yudao-Tenant-Id"] = session.yudaoTenantId;
  }
  return headers;
}

export async function loginToAirank(input: AuthLoginInput): Promise<AuthSession> {
  const response = await fetch("/api/v1/auth/login", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-AIRank-Trace-Id": `trc_web_login_${Date.now()}`,
    },
    body: JSON.stringify({
      username: input.username,
      password: input.password,
      yudao_tenant_id: input.yudaoTenantId,
    }),
  });

  if (!response.ok) {
    throw new Error(await readErrorMessage(response, `Login request failed with ${response.status}`));
  }

  return mapAuthSession((await response.json()) as AuthLoginPayload);
}

export async function fetchConsoleOverview(signal?: AbortSignal): Promise<ConsoleOverview> {
  const response = await fetch("/api/v1/console/overview", {
    headers: buildApiHeaders("trc_web"),
    signal,
  });

  if (!response.ok) {
    throw new Error(`Console overview request failed with ${response.status}`);
  }

  const payload = (await response.json()) as ConsoleOverviewPayload;
  return {
    project: payload.data.project,
    metricCards: payload.data.metric_cards,
    dataStatus: payload.data.data_status,
    message: payload.data.message,
  };
}

export async function fetchAssetBundle(projectId: string, signal?: AbortSignal): Promise<AssetBundle> {
  const response = await fetch(`/api/v1/projects/${projectId}/asset-bundle`, {
    headers: buildApiHeaders("trc_web_asset"),
    signal,
  });

  if (!response.ok) {
    throw new Error(`Asset bundle request failed with ${response.status}`);
  }

  const payload = (await response.json()) as AssetBundlePayload;
  return payload.data;
}

export function fetchEvidenceGaps(projectId: string, signal?: AbortSignal): Promise<EvidenceGapList> {
  return fetchData(
    `/api/v1/projects/${encodeURIComponent(projectId)}/evidence-gaps`,
    "trc_web_evidence_gaps",
    signal,
  );
}

export async function deriveEvidenceGaps(projectId: string, runId: string): Promise<EvidenceGapDerivation> {
  const actor = getStoredAuthSession()?.user.userId;
  if (!actor) {
    throw new Error("当前登录会话缺少可信操作者身份，请重新登录。");
  }
  const response = await fetch(
    `/api/v1/projects/${encodeURIComponent(projectId)}/evidence-gaps/derive`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Idempotency-Key": `gap-${globalThis.crypto.randomUUID()}`,
        ...buildApiHeaders("trc_web_evidence_gap_derive"),
      },
      body: JSON.stringify({ run_id: runId, requested_by: actor }),
    },
  );
  if (!response.ok) {
    throw new Error(await readErrorMessage(response, `Evidence gap derivation failed with ${response.status}`));
  }
  return ((await response.json()) as { data: EvidenceGapDerivation }).data;
}

export function fetchFactAcquisitionTasks(projectId: string, signal?: AbortSignal): Promise<FactAcquisitionTaskList> {
  return fetchData(
    `/api/v1/projects/${encodeURIComponent(projectId)}/fact-acquisition-tasks`,
    "trc_web_fact_acquisition_tasks",
    signal,
  );
}

export async function createFactAcquisitionTask(projectId: string, gapId: string): Promise<FactAcquisitionTask> {
  const actor = getStoredAuthSession()?.user.userId;
  if (!actor) {
    throw new Error("当前登录会话缺少可信操作者身份，请重新登录。");
  }
  const response = await fetch(
    `/api/v1/projects/${encodeURIComponent(projectId)}/evidence-gaps/${encodeURIComponent(gapId)}/fact-acquisition-tasks`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Idempotency-Key": `fact-task-${globalThis.crypto.randomUUID()}`,
        ...buildApiHeaders("trc_web_fact_acquisition_create"),
      },
      body: JSON.stringify({ requested_by: actor }),
    },
  );
  if (!response.ok) {
    throw new Error(await readErrorMessage(response, `Fact acquisition task creation failed with ${response.status}`));
  }
  return ((await response.json()) as { data: FactAcquisitionTask }).data;
}

export async function bindFactAcquisitionEvidence(
  projectId: string,
  taskId: string,
  expectedVersion: number,
  factRevisionIds: string[],
): Promise<FactAcquisitionTask> {
  const actor = getStoredAuthSession()?.user.userId;
  if (!actor) {
    throw new Error("当前登录会话缺少可信操作者身份，请重新登录。");
  }
  const response = await fetch(
    `/api/v1/projects/${encodeURIComponent(projectId)}/fact-acquisition-tasks/${encodeURIComponent(taskId)}/evidence-bindings`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Idempotency-Key": `fact-task-bind-${globalThis.crypto.randomUUID()}`,
        ...buildApiHeaders("trc_web_fact_acquisition_bind"),
      },
      body: JSON.stringify({
        fact_revision_ids: factRevisionIds,
        expected_version: expectedVersion,
        requested_by: actor,
      }),
    },
  );
  if (!response.ok) {
    throw new Error(await readErrorMessage(response, `Fact acquisition evidence binding failed with ${response.status}`));
  }
  return ((await response.json()) as { data: FactAcquisitionTask }).data;
}

export function fetchOpportunities(projectId: string, signal?: AbortSignal): Promise<OpportunityList> {
  return fetchData(
    `/api/v1/projects/${encodeURIComponent(projectId)}/opportunities`,
    "trc_web_opportunities",
    signal,
  );
}

export async function deriveOpportunities(projectId: string): Promise<OpportunityDerivation> {
  const actor = getStoredAuthSession()?.user.userId;
  if (!actor) {
    throw new Error("当前登录会话缺少可信操作者身份，请重新登录。");
  }
  const response = await fetch(
    `/api/v1/projects/${encodeURIComponent(projectId)}/opportunities/derive`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Idempotency-Key": `opportunity-${globalThis.crypto.randomUUID()}`,
        ...buildApiHeaders("trc_web_opportunity_derive"),
      },
      body: JSON.stringify({ requested_by: actor, knowledge_window_days: 30 }),
    },
  );
  if (!response.ok) {
    throw new Error(await readErrorMessage(response, `Opportunity derivation failed with ${response.status}`));
  }
  return ((await response.json()) as { data: OpportunityDerivation }).data;
}

export function fetchOpportunityActions(projectId: string, signal?: AbortSignal): Promise<OpportunityActionList> {
  return fetchData(
    `/api/v1/projects/${encodeURIComponent(projectId)}/opportunity-actions`,
    "trc_web_opportunity_actions",
    signal,
  );
}

export function fetchOpportunityActionRouting(projectId: string, signal?: AbortSignal): Promise<OpportunityActionRouting> {
  return fetchData(
    `/api/v1/projects/${encodeURIComponent(projectId)}/opportunity-action-routing`,
    "trc_web_opportunity_action_routing",
    signal,
  );
}

export function fetchOpportunityExecutionPortfolio(projectId: string, signal?: AbortSignal): Promise<OpportunityExecutionPortfolio> {
  return fetchData(
    `/api/v1/projects/${encodeURIComponent(projectId)}/opportunity-execution-portfolio`,
    "trc_web_opportunity_execution_portfolio",
    signal,
  );
}

export function fetchOpportunityCapacityPortfolio(projectId: string, signal?: AbortSignal): Promise<OpportunityCapacityPortfolio> {
  return fetchData(
    `/api/v1/projects/${encodeURIComponent(projectId)}/opportunity-capacity-portfolio`,
    "trc_web_opportunity_capacity_portfolio",
    signal,
  );
}

export async function putOpportunityExecutionPlan(
  projectId: string,
  actionId: string,
  input: {
    estimatedEffortHours: string;
    estimatedBudgetAmount: string;
    plannedStartAt: string;
    plannedDueAt: string;
    assumptions: string;
    expectedVersion?: number;
  },
): Promise<OpportunityExecutionPlan> {
  const response = await fetch(
    `/api/v1/projects/${encodeURIComponent(projectId)}/opportunity-actions/${encodeURIComponent(actionId)}/plan`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json", ...buildApiHeaders("trc_web_opportunity_execution_plan") },
      body: JSON.stringify({
        status: "approved",
        estimated_effort_hours: input.estimatedEffortHours,
        estimated_budget_amount: input.estimatedBudgetAmount,
        currency: "CNY",
        planned_start_at: new Date(input.plannedStartAt).toISOString(),
        planned_due_at: new Date(input.plannedDueAt).toISOString(),
        assumptions: input.assumptions,
        ...(input.expectedVersion ? { expected_version: input.expectedVersion } : {}),
      }),
    },
  );
  if (!response.ok) throw new Error(await readErrorMessage(response, `Opportunity execution plan update failed with ${response.status}`));
  return ((await response.json()) as { data: OpportunityExecutionPlan }).data;
}

export async function putOpportunityCapacityCalendar(
  projectId: string,
  memberId: string,
  input: {
    timezone: string;
    weeklyCapacityHours: string;
    workdays: number[];
    assumptions: string;
    expectedVersion?: number;
  },
): Promise<OpportunityCapacityCalendar> {
  const response = await fetch(
    `/api/v1/projects/${encodeURIComponent(projectId)}/opportunity-action-team-members/${encodeURIComponent(memberId)}/capacity-calendar`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json", ...buildApiHeaders("trc_web_opportunity_capacity_calendar") },
      body: JSON.stringify({
        timezone: input.timezone,
        weekly_capacity_hours: input.weeklyCapacityHours,
        workdays: input.workdays,
        assumptions: input.assumptions,
        ...(input.expectedVersion ? { expected_version: input.expectedVersion } : {}),
      }),
    },
  );
  if (!response.ok) throw new Error(await readErrorMessage(response, `Opportunity capacity calendar update failed with ${response.status}`));
  return ((await response.json()) as { data: OpportunityCapacityCalendar }).data;
}

export async function putOpportunityCapacityException(
  projectId: string,
  memberId: string,
  exceptionDate: string,
  availableHours: string,
  reason: string,
  expectedVersion?: number,
): Promise<OpportunityCapacityException> {
  const response = await fetch(
    `/api/v1/projects/${encodeURIComponent(projectId)}/opportunity-action-team-members/${encodeURIComponent(memberId)}/capacity-calendar/exceptions/${encodeURIComponent(exceptionDate)}`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json", ...buildApiHeaders("trc_web_opportunity_capacity_exception") },
      body: JSON.stringify({
        available_hours: availableHours,
        reason,
        ...(expectedVersion ? { expected_version: expectedVersion } : {}),
      }),
    },
  );
  if (!response.ok) throw new Error(await readErrorMessage(response, `Opportunity capacity exception update failed with ${response.status}`));
  return ((await response.json()) as { data: OpportunityCapacityException }).data;
}

export async function createOpportunityExecutionSchedule(projectId: string, asOfDate: string): Promise<OpportunityScheduleRun> {
  const response = await fetch(
    `/api/v1/projects/${encodeURIComponent(projectId)}/opportunity-execution-schedules`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Idempotency-Key": `opportunity-schedule-${globalThis.crypto.randomUUID()}`,
        ...buildApiHeaders("trc_web_opportunity_capacity_schedule"),
      },
      body: JSON.stringify({ as_of_date: asOfDate, horizon_days: 90 }),
    },
  );
  if (!response.ok) throw new Error(await readErrorMessage(response, `Opportunity schedule generation failed with ${response.status}`));
  return ((await response.json()) as { data: OpportunityScheduleRun }).data;
}

export async function createOpportunityDependency(
  projectId: string,
  actionId: string,
  prerequisiteActionId: string,
  rationale: string,
): Promise<OpportunityDependency> {
  const response = await fetch(
    `/api/v1/projects/${encodeURIComponent(projectId)}/opportunity-actions/${encodeURIComponent(actionId)}/dependencies`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Idempotency-Key": `opportunity-dependency-${globalThis.crypto.randomUUID()}`,
        ...buildApiHeaders("trc_web_opportunity_dependency"),
      },
      body: JSON.stringify({
        prerequisite_action_id: prerequisiteActionId,
        dependency_type: "finish_to_start",
        rationale,
      }),
    },
  );
  if (!response.ok) throw new Error(await readErrorMessage(response, `Opportunity dependency creation failed with ${response.status}`));
  return ((await response.json()) as { data: OpportunityDependency }).data;
}

export async function waiveOpportunityDependency(
  projectId: string,
  dependencyId: string,
  expectedVersion: number,
  waiverReason: string,
): Promise<OpportunityDependency> {
  const response = await fetch(
    `/api/v1/projects/${encodeURIComponent(projectId)}/opportunity-dependencies/${encodeURIComponent(dependencyId)}/waivers`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json", ...buildApiHeaders("trc_web_opportunity_dependency_waiver") },
      body: JSON.stringify({
        expected_version: expectedVersion,
        waiver_reason: waiverReason,
        acknowledge_no_outcome_claim: true,
      }),
    },
  );
  if (!response.ok) throw new Error(await readErrorMessage(response, `Opportunity dependency waiver failed with ${response.status}`));
  return ((await response.json()) as { data: OpportunityDependency }).data;
}

export async function createOpportunityActionTeam(projectId: string, name: string): Promise<OpportunityActionRouting> {
  const response = await fetch(
    `/api/v1/projects/${encodeURIComponent(projectId)}/opportunity-action-teams`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Idempotency-Key": `opportunity-team-${globalThis.crypto.randomUUID()}`,
        ...buildApiHeaders("trc_web_opportunity_action_team_create"),
      },
      body: JSON.stringify({ name }),
    },
  );
  if (!response.ok) throw new Error(await readErrorMessage(response, `Opportunity action team creation failed with ${response.status}`));
  return ((await response.json()) as { data: OpportunityActionRouting }).data;
}

export async function fetchOpportunityActionDirectory(
  projectId: string,
  signal?: AbortSignal,
): Promise<OpportunityActionDirectory> {
  const response = await fetch(
    `/api/v1/projects/${encodeURIComponent(projectId)}/opportunity-action-directory-sync`,
    { signal, headers: buildApiHeaders("trc_web_opportunity_action_directory") },
  );
  if (!response.ok) throw new Error(await readErrorMessage(response, `Opportunity directory fetch failed with ${response.status}`));
  return ((await response.json()) as { data: OpportunityActionDirectory }).data;
}

export async function putOpportunityActionDirectoryBinding(
  projectId: string,
  teamId: string,
  externalGroupId: string,
  expectedVersion?: number,
): Promise<OpportunityActionDirectory> {
  const response = await fetch(
    `/api/v1/projects/${encodeURIComponent(projectId)}/opportunity-action-teams/${encodeURIComponent(teamId)}/sync-binding`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json", ...buildApiHeaders("trc_web_opportunity_action_directory_binding") },
      body: JSON.stringify({
        external_group_id: externalGroupId,
        sync_enabled: true,
        sync_interval_minutes: 60,
        default_priority: 100,
        default_max_active_actions: 5,
        default_receives_escalations: true,
        ...(expectedVersion ? { expected_version: expectedVersion } : {}),
      }),
    },
  );
  if (!response.ok) throw new Error(await readErrorMessage(response, `Opportunity directory binding failed with ${response.status}`));
  return ((await response.json()) as { data: OpportunityActionDirectory }).data;
}

export async function runOpportunityActionDirectorySync(
  projectId: string,
  teamId: string,
): Promise<OpportunityActionDirectory> {
  const response = await fetch(
    `/api/v1/projects/${encodeURIComponent(projectId)}/opportunity-action-teams/${encodeURIComponent(teamId)}/sync-runs`,
    {
      method: "POST",
      headers: {
        "Idempotency-Key": `opportunity-directory-${globalThis.crypto.randomUUID()}`,
        ...buildApiHeaders("trc_web_opportunity_action_directory_run"),
      },
    },
  );
  if (!response.ok) throw new Error(await readErrorMessage(response, `Opportunity directory synchronization failed with ${response.status}`));
  return ((await response.json()) as { data: OpportunityActionDirectory }).data;
}

export async function upsertOpportunityActionMember(
  projectId: string,
  teamId: string,
  userId: string,
  expectedVersion?: number,
): Promise<OpportunityActionRouting> {
  const response = await fetch(
    `/api/v1/projects/${encodeURIComponent(projectId)}/opportunity-action-teams/${encodeURIComponent(teamId)}/members/${encodeURIComponent(userId)}`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json", ...buildApiHeaders("trc_web_opportunity_action_member") },
      body: JSON.stringify({
        display_name: userId,
        max_active_actions: 5,
        receives_escalations: true,
        ...(expectedVersion ? { expected_version: expectedVersion } : {}),
      }),
    },
  );
  if (!response.ok) throw new Error(await readErrorMessage(response, `Opportunity action member update failed with ${response.status}`));
  return ((await response.json()) as { data: OpportunityActionRouting }).data;
}

export async function putOpportunityActionRoute(
  projectId: string,
  sourceKind: OpportunitySourceKind,
  teamId: string,
  expectedVersion?: number,
): Promise<OpportunityActionRouting> {
  const response = await fetch(
    `/api/v1/projects/${encodeURIComponent(projectId)}/opportunity-action-routes/${encodeURIComponent(sourceKind)}`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json", ...buildApiHeaders("trc_web_opportunity_action_route") },
      body: JSON.stringify({ team_id: teamId, ...(expectedVersion ? { expected_version: expectedVersion } : {}) }),
    },
  );
  if (!response.ok) throw new Error(await readErrorMessage(response, `Opportunity action route update failed with ${response.status}`));
  return ((await response.json()) as { data: OpportunityActionRouting }).data;
}

export async function createOpportunityAction(projectId: string, snapshotId: string): Promise<OpportunityAction> {
  const actor = getStoredAuthSession()?.user.userId;
  if (!actor) throw new Error("当前登录会话缺少可信操作者身份，请重新登录。");
  const response = await fetch(
    `/api/v1/projects/${encodeURIComponent(projectId)}/opportunities/${encodeURIComponent(snapshotId)}/actions`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Idempotency-Key": `opportunity-action-${globalThis.crypto.randomUUID()}`,
        ...buildApiHeaders("trc_web_opportunity_action_create"),
      },
      body: JSON.stringify({ requested_by: actor }),
    },
  );
  if (!response.ok) throw new Error(await readErrorMessage(response, `Opportunity action creation failed with ${response.status}`));
  return ((await response.json()) as { data: OpportunityAction }).data;
}

export async function claimOpportunityAction(projectId: string, actionId: string, expectedVersion: number): Promise<OpportunityAction> {
  const actor = getStoredAuthSession()?.user.userId;
  if (!actor) throw new Error("当前登录会话缺少可信操作者身份，请重新登录。");
  const response = await fetch(
    `/api/v1/projects/${encodeURIComponent(projectId)}/opportunity-actions/${encodeURIComponent(actionId)}/claims`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Idempotency-Key": `opportunity-action-claim-${globalThis.crypto.randomUUID()}`,
        ...buildApiHeaders("trc_web_opportunity_action_claim"),
      },
      body: JSON.stringify({ requested_by: actor, expected_version: expectedVersion }),
    },
  );
  if (!response.ok) throw new Error(await readErrorMessage(response, `Opportunity action claim failed with ${response.status}`));
  return ((await response.json()) as { data: OpportunityAction }).data;
}

export async function verifyOpportunityActionNotObserved(
  projectId: string,
  actionId: string,
  expectedVersion: number,
  verificationRunId: string,
): Promise<OpportunityAction> {
  const actor = getStoredAuthSession()?.user.userId;
  if (!actor) throw new Error("当前登录会话缺少可信操作者身份，请重新登录。");
  const response = await fetch(
    `/api/v1/projects/${encodeURIComponent(projectId)}/opportunity-actions/${encodeURIComponent(actionId)}/transitions`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Idempotency-Key": `opportunity-action-verify-${globalThis.crypto.randomUUID()}`,
        ...buildApiHeaders("trc_web_opportunity_action_verify"),
      },
      body: JSON.stringify({
        transition: "verify_not_observed",
        requested_by: actor,
        expected_version: expectedVersion,
        reason: "由当前最新完整机会快照确认本轮未再观察到；不据此声明推荐或增长效果。",
        verification_run_id: verificationRunId,
        acknowledge_no_outcome_claim: true,
      }),
    },
  );
  if (!response.ok) throw new Error(await readErrorMessage(response, `Opportunity action verification failed with ${response.status}`));
  return ((await response.json()) as { data: OpportunityAction }).data;
}

export async function fetchReports(projectId: string, signal?: AbortSignal): Promise<ReportList> {
  const response = await fetch(`/api/v1/projects/${projectId}/reports`, {
    headers: buildApiHeaders("trc_web_reports"),
    signal,
  });

  if (!response.ok) {
    throw new Error(`Reports request failed with ${response.status}`);
  }

  const payload = (await response.json()) as ReportListPayload;
  return payload.data;
}

async function fetchData<T>(url: string, tracePrefix: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(url, { headers: buildApiHeaders(tracePrefix), signal });
  if (!response.ok) {
    throw new Error(await readErrorMessage(response, `${url} request failed with ${response.status}`));
  }
  const payload = (await response.json()) as { data: T };
  return payload.data;
}

export function fetchKnowledgeSources(projectId: string, signal?: AbortSignal): Promise<KnowledgeSource[]> {
  return fetchData(`/api/v1/projects/${projectId}/knowledge-sources`, "trc_web_sources", signal);
}

export function fetchKnowledgeSyncPolicies(projectId: string, signal?: AbortSignal): Promise<KnowledgeSyncPolicy[]> {
  return fetchData(`/api/v1/projects/${projectId}/knowledge-source-sync-policies`, "trc_web_knowledge_sync_policies", signal);
}

export function fetchKnowledgeSyncRuns(projectId: string, signal?: AbortSignal): Promise<KnowledgeSyncRun[]> {
  return fetchData(`/api/v1/projects/${projectId}/knowledge-source-sync-runs?limit=100`, "trc_web_knowledge_sync_runs", signal);
}

export function fetchPageAudits(projectId: string, signal?: AbortSignal): Promise<PageAuditRun[]> {
  return fetchData(`/api/v1/projects/${projectId}/page-audits`, "trc_web_page_audits", signal);
}

export function fetchPageAudit(projectId: string, runId: string, signal?: AbortSignal): Promise<PageAuditRun> {
  return fetchData(`/api/v1/projects/${projectId}/page-audits/${runId}`, "trc_web_page_audit", signal);
}

export async function createPageAudit(projectId: string, url: string, requestedBy: string): Promise<PageAuditRun> {
  const randomPart = typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  const response = await fetch(`/api/v1/projects/${projectId}/page-audits`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...buildApiHeaders("trc_web_page_audit_create") },
    body: JSON.stringify({
      url,
      idempotency_key: `page-audit-${randomPart}`,
      requested_by: requestedBy,
    }),
  });
  if (!response.ok) {
    throw new Error(await readErrorMessage(response, `Page audit request failed with ${response.status}`));
  }
  const payload = (await response.json()) as { data: PageAuditRun };
  return payload.data;
}

export async function saveKnowledgeSource(
  projectId: string,
  input: KnowledgeSourceInput,
  parentSourceId?: string,
): Promise<KnowledgeSource> {
  const suffix = parentSourceId ? `/knowledge-sources/${parentSourceId}/revisions` : "/knowledge-sources";
  const response = await fetch(`/api/v1/projects/${projectId}${suffix}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...buildApiHeaders("trc_web_source_save"),
    },
    body: JSON.stringify(input),
  });
  if (!response.ok) {
    throw new Error(await readErrorMessage(response, `Knowledge source request failed with ${response.status}`));
  }
  const payload = (await response.json()) as { data: KnowledgeSource };
  return payload.data;
}

export async function createKnowledgeSyncPolicy(
  projectId: string,
  sourceId: string,
  intervalHours: number,
): Promise<KnowledgeSyncPolicy> {
  const session = getStoredAuthSession();
  const randomPart = globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random()}`;
  const response = await fetch(
    `/api/v1/projects/${encodeURIComponent(projectId)}/knowledge-sources/${encodeURIComponent(sourceId)}/sync-policies`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json", ...buildApiHeaders("trc_web_knowledge_sync_create") },
      body: JSON.stringify({
        idempotency_key: `knowledge-sync-policy-${sourceId}-${randomPart}`,
        interval_hours: intervalHours,
        created_by: session?.user.userId ?? "console-operator",
      }),
    },
  );
  if (!response.ok) {
    throw new Error(await readErrorMessage(response, `Knowledge sync policy request failed with ${response.status}`));
  }
  return ((await response.json()) as { data: KnowledgeSyncPolicy }).data;
}

export async function updateKnowledgeSyncPolicy(
  policy: KnowledgeSyncPolicy,
  input: { enabled: boolean; intervalHours: number; reason: string },
): Promise<KnowledgeSyncPolicy> {
  const session = getStoredAuthSession();
  const response = await fetch(
    `/api/v1/knowledge-source-sync-policies/${encodeURIComponent(policy.policy_id)}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json", ...buildApiHeaders("trc_web_knowledge_sync_update") },
      body: JSON.stringify({
        expected_version: policy.version,
        enabled: input.enabled,
        interval_hours: input.intervalHours,
        reason: input.reason,
        updated_by: session?.user.userId ?? "console-operator",
      }),
    },
  );
  if (!response.ok) {
    throw new Error(await readErrorMessage(response, `Knowledge sync policy update failed with ${response.status}`));
  }
  return ((await response.json()) as { data: KnowledgeSyncPolicy }).data;
}

export async function triggerKnowledgeSync(policyId: string): Promise<KnowledgeSyncRun> {
  const session = getStoredAuthSession();
  const randomPart = globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random()}`;
  const response = await fetch(
    `/api/v1/knowledge-source-sync-policies/${encodeURIComponent(policyId)}/runs`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json", ...buildApiHeaders("trc_web_knowledge_sync_trigger") },
      body: JSON.stringify({
        idempotency_key: `knowledge-sync-manual-${policyId}-${randomPart}`,
        requested_by: session?.user.userId ?? "console-operator",
      }),
    },
  );
  if (!response.ok) {
    throw new Error(await readErrorMessage(response, `Knowledge sync trigger failed with ${response.status}`));
  }
  return ((await response.json()) as { data: KnowledgeSyncRun }).data;
}

export function searchKnowledge(projectId: string, query: string, signal?: AbortSignal): Promise<KnowledgeSearch> {
  const params = new URLSearchParams({ q: query, limit: "20" });
  return fetchData(`/api/v1/projects/${projectId}/knowledge-search?${params.toString()}`, "trc_web_knowledge_search", signal);
}

export function fetchFacts(projectId: string, signal?: AbortSignal): Promise<FactRevision[]> {
  return fetchData(`/api/v1/projects/${projectId}/facts`, "trc_web_facts", signal);
}

export function fetchBrandGraph(projectId: string, signal?: AbortSignal): Promise<BrandGraphPortfolio> {
  return fetchData(`/api/v1/projects/${encodeURIComponent(projectId)}/brand-graph`, "trc_web_brand_graph", signal);
}

async function brandGraphWrite<T>(url: string, method: "POST" | "PUT", body: Record<string, unknown>, tracePrefix: string): Promise<T> {
  const response = await fetch(url, {
    method,
    headers: { "Content-Type": "application/json", ...buildApiHeaders(tracePrefix) },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw new Error(await readErrorMessage(response, `Brand graph request failed with ${response.status}`));
  }
  return ((await response.json()) as { data: T }).data;
}

export function createBrandGraphEntity(
  projectId: string,
  input: Pick<BrandGraphEntity, "entity_role" | "entity_kind" | "canonical_name" | "usage_scope" | "fact_revision_id"> & { website_url?: string },
): Promise<BrandGraphEntity> {
  return brandGraphWrite(`/api/v1/projects/${encodeURIComponent(projectId)}/brand-entities`, "POST", input, "trc_web_brand_entity");
}

export function createBrandGraphAlias(
  projectId: string,
  entityId: string,
  input: Pick<BrandGraphAlias, "alias_text" | "alias_type" | "usage_scope" | "fact_revision_id">,
): Promise<BrandGraphAlias> {
  return brandGraphWrite(`/api/v1/projects/${encodeURIComponent(projectId)}/brand-entities/${encodeURIComponent(entityId)}/aliases`, "POST", input, "trc_web_brand_alias");
}

export function createBrandGraphRelation(
  projectId: string,
  input: Pick<BrandGraphRelation, "subject_entity_id" | "predicate" | "object_entity_id" | "usage_scope" | "fact_revision_id">,
): Promise<BrandGraphRelation> {
  return brandGraphWrite(`/api/v1/projects/${encodeURIComponent(projectId)}/brand-relations`, "POST", input, "trc_web_brand_relation");
}

export function compileBrandGraph(projectId: string, requestedBy: string): Promise<BrandGraphSnapshot> {
  return brandGraphWrite(`/api/v1/projects/${encodeURIComponent(projectId)}/brand-graph/snapshots`, "POST", { requested_by: requestedBy }, "trc_web_brand_graph_compile");
}

export function fetchFactConflicts(projectId: string, signal?: AbortSignal): Promise<FactConflict[]> {
  return fetchData(`/api/v1/projects/${projectId}/fact-conflicts?status=open`, "trc_web_fact_conflicts", signal);
}

export function fetchKnowledgeGovernance(projectId: string, signal?: AbortSignal): Promise<KnowledgeGovernance> {
  return fetchData(`/api/v1/projects/${projectId}/knowledge-governance?within_days=30`, "trc_web_knowledge_governance", signal);
}

export async function reviewFactRevision(
  projectId: string,
  revisionId: string,
  action: "approved" | "rejected",
  reviewedBy: string,
): Promise<FactRevision> {
  const response = await fetch(`/api/v1/projects/${projectId}/fact-revisions/${revisionId}/review`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
      ...buildApiHeaders("trc_web_fact_review"),
    },
    body: JSON.stringify({ action, reviewed_by: reviewedBy }),
  });
  if (!response.ok) {
    throw new Error(await readErrorMessage(response, `Fact review request failed with ${response.status}`));
  }
  const payload = (await response.json()) as { data: FactRevision };
  return payload.data;
}

export async function resolveFactConflict(
  projectId: string,
  conflictId: string,
  resolution: "resolved_left" | "resolved_right" | "resolved_new_revision" | "dismissed",
  resolvedBy: string,
  resolutionNote: string,
): Promise<FactConflict> {
  const response = await fetch(`/api/v1/projects/${projectId}/fact-conflicts/${conflictId}/resolve`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
      ...buildApiHeaders("trc_web_fact_conflict_resolve"),
    },
    body: JSON.stringify({ resolution, resolved_by: resolvedBy, resolution_note: resolutionNote }),
  });
  if (!response.ok) {
    throw new Error(await readErrorMessage(response, `Fact conflict resolution failed with ${response.status}`));
  }
  const payload = (await response.json()) as { data: FactConflict };
  return payload.data;
}

export async function fetchAnswerSamples(
  projectId: string,
  runId: string,
  signal?: AbortSignal,
): Promise<AnswerSampleCollection> {
  const url = `/api/v1/projects/${projectId}/samples?run_id=${encodeURIComponent(runId)}&limit=200`;
  const response = await fetch(url, { headers: buildApiHeaders("trc_web_samples"), signal });
  if (!response.ok) {
    throw new Error(await readErrorMessage(response, `Answer samples request failed with ${response.status}`));
  }
  const payload = (await response.json()) as {
    data: AnswerSample[];
    meta: {
      run_id: string | null;
      limit: number;
      total: number;
      valid_count: number;
      valid_unmentioned_count: number;
      citation_sample_count: number;
    };
  };
  return {
    samples: payload.data,
    runId: payload.meta.run_id,
    limit: payload.meta.limit,
    total: payload.meta.total,
    validCount: payload.meta.valid_count,
    validUnmentionedCount: payload.meta.valid_unmentioned_count,
    citationSampleCount: payload.meta.citation_sample_count,
  };
}

export function fetchAnswerSample(snapshotId: string, signal?: AbortSignal): Promise<AnswerSampleDetail> {
  return fetchData(`/api/v1/samples/${snapshotId}`, "trc_web_sample", signal);
}

export function fetchCitationSupport(snapshotId: string, signal?: AbortSignal): Promise<CitationSupportBundle> {
  return fetchData(`/api/v1/samples/${snapshotId}/citation-support`, "trc_web_citation_support", signal);
}

export async function createCitationClaim(
  snapshotId: string,
  answerStart: number,
  answerEnd: number,
  input?: {
    claimKind?: CitationSupportBundle["claims"][number]["claim_kind"];
    subjectEntityText?: string;
  },
): Promise<CitationSupportBundle["claims"][number]> {
  const session = getStoredAuthSession();
  const response = await fetch(`/api/v1/samples/${encodeURIComponent(snapshotId)}/citation-claims`, {
    method: "POST",
    headers: { ...buildApiHeaders("trc_web_citation_claim"), "Content-Type": "application/json" },
    body: JSON.stringify({
      answer_start: answerStart,
      answer_end: answerEnd,
      extraction_method: "manual",
      claim_kind: input?.claimKind ?? "unclassified",
      subject_entity_text: input?.subjectEntityText?.trim() || undefined,
      created_by: session?.user.userId ?? "console-operator",
    }),
  });
  if (!response.ok) {
    throw new Error(await readErrorMessage(response, `Citation claim request failed with ${response.status}`));
  }
  return ((await response.json()) as { data: CitationSupportBundle["claims"][number] }).data;
}

export function fetchFactAccuracy(snapshotId: string, signal?: AbortSignal): Promise<FactAccuracyBundle> {
  return fetchData(`/api/v1/samples/${snapshotId}/fact-accuracy`, "trc_web_fact_accuracy", signal);
}

export function fetchEvidenceReviewCases(
  projectId: string,
  snapshotId?: string,
  signal?: AbortSignal,
): Promise<EvidenceReviewQueue> {
  const query = snapshotId ? `?snapshot_id=${encodeURIComponent(snapshotId)}` : "";
  return fetchData(
    `/api/v1/projects/${encodeURIComponent(projectId)}/evidence-review-cases${query}`,
    "trc_web_evidence_review_queue",
    signal,
  );
}

export function fetchEvidenceReviewInbox(
  projectId: string,
  cursor?: string,
  signal?: AbortSignal,
): Promise<EvidenceReviewInbox> {
  const params = new URLSearchParams({ limit: "12" });
  if (cursor) params.set("cursor", cursor);
  return fetchData(
    `/api/v1/projects/${encodeURIComponent(projectId)}/evidence-review-inbox?${params.toString()}`,
    "trc_web_evidence_review_inbox",
    signal,
  );
}

export function fetchEvidenceReviewEscalations(
  projectId: string,
  signal?: AbortSignal,
): Promise<EvidenceReviewEscalationList> {
  return fetchData(
    `/api/v1/projects/${encodeURIComponent(projectId)}/evidence-review-escalations?limit=50`,
    "trc_web_evidence_review_escalations",
    signal,
  );
}

export function fetchEvidenceReviewerRouting(
  projectId: string,
  signal?: AbortSignal,
): Promise<EvidenceReviewerRouting> {
  return fetchData(
    `/api/v1/projects/${encodeURIComponent(projectId)}/evidence-review-routing`,
    "trc_web_evidence_review_routing",
    signal,
  );
}

export async function createEvidenceReviewerTeam(
  projectId: string,
  name: string,
): Promise<EvidenceReviewerRouting> {
  const randomPart = globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random()}`;
  const response = await fetch(
    `/api/v1/projects/${encodeURIComponent(projectId)}/evidence-review-teams`,
    {
      method: "POST",
      headers: {
        ...buildApiHeaders("trc_web_evidence_review_team_create"),
        "Content-Type": "application/json",
        "Idempotency-Key": `review-team-${randomPart}`,
      },
      body: JSON.stringify({ name: name.trim() }),
    },
  );
  if (!response.ok) {
    throw new Error(await readErrorMessage(response, `Reviewer team request failed with ${response.status}`));
  }
  return ((await response.json()) as { data: EvidenceReviewerRouting }).data;
}

export async function upsertEvidenceReviewerTeamMember(
  projectId: string,
  teamId: string,
  userId: string,
  reviewerRole: "secondary" | "adjudicator",
  input: { displayName?: string; maxActiveAssignments: number; expectedVersion?: number },
): Promise<EvidenceReviewerRouting> {
  const response = await fetch(
    `/api/v1/projects/${encodeURIComponent(projectId)}/evidence-review-teams/${encodeURIComponent(teamId)}/members/${encodeURIComponent(userId)}/${reviewerRole}`,
    {
      method: "PUT",
      headers: {
        ...buildApiHeaders("trc_web_evidence_review_team_member"),
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        display_name: input.displayName?.trim() || undefined,
        priority: 100,
        max_active_assignments: input.maxActiveAssignments,
        receives_escalations: true,
        expected_version: input.expectedVersion,
      }),
    },
  );
  if (!response.ok) {
    throw new Error(await readErrorMessage(response, `Reviewer member request failed with ${response.status}`));
  }
  return ((await response.json()) as { data: EvidenceReviewerRouting }).data;
}

export async function putEvidenceReviewerRoute(
  projectId: string,
  reviewerRole: "secondary" | "adjudicator",
  teamId: string,
  expectedVersion?: number,
): Promise<EvidenceReviewerRouting> {
  const response = await fetch(
    `/api/v1/projects/${encodeURIComponent(projectId)}/evidence-review-routes/${reviewerRole}`,
    {
      method: "PUT",
      headers: {
        ...buildApiHeaders("trc_web_evidence_review_route"),
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ team_id: teamId, expected_version: expectedVersion }),
    },
  );
  if (!response.ok) {
    throw new Error(await readErrorMessage(response, `Reviewer route request failed with ${response.status}`));
  }
  return ((await response.json()) as { data: EvidenceReviewerRouting }).data;
}

export async function putEvidenceReviewerDirectoryBinding(
  projectId: string,
  teamId: string,
  reviewerRole: "secondary" | "adjudicator",
  input: {
    externalGroupId: string;
    syncIntervalMinutes: number;
    defaultMaxActiveAssignments: number;
    expectedVersion?: number;
  },
): Promise<EvidenceReviewerRouting> {
  const response = await fetch(
    `/api/v1/projects/${encodeURIComponent(projectId)}/evidence-review-teams/${encodeURIComponent(teamId)}/sync-bindings/${reviewerRole}`,
    {
      method: "PUT",
      headers: {
        ...buildApiHeaders("trc_web_evidence_review_directory_binding"),
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        external_group_id: input.externalGroupId.trim(),
        sync_enabled: true,
        sync_interval_minutes: input.syncIntervalMinutes,
        default_priority: 100,
        default_max_active_assignments: input.defaultMaxActiveAssignments,
        default_receives_escalations: true,
        expected_version: input.expectedVersion,
      }),
    },
  );
  if (!response.ok) {
    throw new Error(await readErrorMessage(response, `Reviewer directory binding request failed with ${response.status}`));
  }
  return ((await response.json()) as { data: EvidenceReviewerRouting }).data;
}

export async function runEvidenceReviewerDirectorySync(
  projectId: string,
  teamId: string,
  reviewerRole: "secondary" | "adjudicator",
): Promise<EvidenceReviewerRouting> {
  const randomPart = globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random()}`;
  const response = await fetch(
    `/api/v1/projects/${encodeURIComponent(projectId)}/evidence-review-teams/${encodeURIComponent(teamId)}/sync-bindings/${reviewerRole}/runs`,
    {
      method: "POST",
      headers: {
        ...buildApiHeaders("trc_web_evidence_review_directory_sync"),
        "Idempotency-Key": `review-directory-sync-${randomPart}`,
      },
    },
  );
  if (!response.ok) {
    throw new Error(await readErrorMessage(response, `Reviewer directory sync request failed with ${response.status}`));
  }
  return ((await response.json()) as { data: EvidenceReviewerRouting }).data;
}

export async function createFactEvidenceReviewCase(
  projectId: string,
  claimId: string,
  input: {
    verdict: FactAccuracyBundle["reviews"][number]["verdict"];
    factRevisionId?: string;
    rationale: string;
    purpose?: "production" | "benchmark";
  },
): Promise<EvidenceReviewCase> {
  const session = getStoredAuthSession();
  const randomPart = globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random()}`;
  const response = await fetch(
    `/api/v1/projects/${encodeURIComponent(projectId)}/evidence-review-cases/fact-accuracy`,
    {
      method: "POST",
      headers: {
        ...buildApiHeaders("trc_web_fact_review_case"),
        "Content-Type": "application/json",
        "Idempotency-Key": `fact-review-case-${claimId}-${randomPart}`,
      },
      body: JSON.stringify({
        claim_id: claimId,
        purpose: input.purpose ?? "production",
        review: {
          verdict: input.verdict,
          fact_revision_id: input.factRevisionId,
          rationale: input.rationale,
          review_method: "human",
          reviewed_by: session?.user.userId ?? "console-reviewer",
        },
      }),
    },
  );
  if (!response.ok) {
    throw new Error(await readErrorMessage(response, `Fact review case failed with ${response.status}`));
  }
  return ((await response.json()) as { data: EvidenceReviewCase }).data;
}

export async function createCitationSourceCapture(citationId: string): Promise<CitationSourceCapture> {
  const session = getStoredAuthSession();
  const randomPart = globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random()}`;
  const response = await fetch(`/api/v1/citations/${encodeURIComponent(citationId)}/source-captures`, {
    method: "POST",
    headers: { ...buildApiHeaders("trc_web_citation_capture"), "Content-Type": "application/json" },
    body: JSON.stringify({
      idempotency_key: `citation-capture-${randomPart}`,
      requested_by: session?.user.userId ?? "console-operator",
    }),
  });
  if (!response.ok) {
    throw new Error(await readErrorMessage(response, `Citation capture request failed with ${response.status}`));
  }
  return ((await response.json()) as { data: CitationSourceCapture }).data;
}

export async function createCitationSourceCaptureBatch(
  snapshotId: string,
  citationIds: string[],
): Promise<CitationCaptureBatch> {
  const session = getStoredAuthSession();
  const randomPart = globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random()}`;
  const response = await fetch(
    `/api/v1/answer-snapshots/${encodeURIComponent(snapshotId)}/citation-source-captures:batch`,
    {
      method: "POST",
      headers: { ...buildApiHeaders("trc_web_citation_capture_batch"), "Content-Type": "application/json" },
      body: JSON.stringify({
        idempotency_key: `citation-batch-${randomPart}`,
        requested_by: session?.user.userId ?? "console-operator",
        citation_ids: citationIds,
      }),
    },
  );
  if (!response.ok) {
    throw new Error(await readErrorMessage(response, `Citation batch request failed with ${response.status}`));
  }
  return ((await response.json()) as { data: CitationCaptureBatch }).data;
}

export function fetchLatestCitationSourceCaptures(
  snapshotId: string,
  signal?: AbortSignal,
): Promise<CitationSourceCapture[]> {
  return fetchData(
    `/api/v1/answer-snapshots/${encodeURIComponent(snapshotId)}/citation-source-captures/latest`,
    "trc_web_citation_capture_latest",
    signal,
  );
}

export function fetchCitationSourceCaptures(
  citationId: string,
  signal?: AbortSignal,
): Promise<CitationSourceCapture[]> {
  return fetchData(
    `/api/v1/citations/${encodeURIComponent(citationId)}/source-captures`,
    "trc_web_citation_captures",
    signal,
  );
}

export function fetchCitationSourceCapture(
  captureId: string,
  signal?: AbortSignal,
): Promise<CitationSourceCapture> {
  return fetchData(
    `/api/v1/citation-source-captures/${encodeURIComponent(captureId)}`,
    "trc_web_citation_capture",
    signal,
  );
}

export function fetchSourceRegistry(
  projectId: string,
  signal?: AbortSignal,
): Promise<SourceRegistryEntry[]> {
  return fetchData(
    `/api/v1/projects/${encodeURIComponent(projectId)}/source-registry`,
    "trc_web_source_registry",
    signal,
  );
}

export async function reviewSourceRegistryEntry(
  projectId: string,
  host: string,
  input: {
    sourceCategoryL1: SourceClassificationRevision["source_category_l1"];
    sourceType: string;
    ecosystem?: string;
    classificationConfidence: SourceClassificationRevision["classification_confidence"];
    authorityLevel: SourceClassificationRevision["authority_level"];
    usagePolicy: SourceClassificationRevision["usage_policy"];
    riskLevel: SourceClassificationRevision["risk_level"];
    evidenceNote: string;
    evidenceUrl?: string;
    validUntil?: string;
    supersedesRevisionId?: string;
  },
): Promise<SourceRegistryEntry> {
  const session = getStoredAuthSession();
  const randomPart = globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random()}`;
  const response = await fetch(
    `/api/v1/projects/${encodeURIComponent(projectId)}/source-registry/${encodeURIComponent(host)}/reviews`,
    {
      method: "POST",
      headers: {
        ...buildApiHeaders("trc_web_source_registry_review"),
        "Content-Type": "application/json",
        "Idempotency-Key": `source-review-${randomPart}`,
      },
      body: JSON.stringify({
        source_category_l1: input.sourceCategoryL1,
        source_type: input.sourceType,
        ecosystem: input.ecosystem?.trim() || undefined,
        classification_confidence: input.classificationConfidence,
        authority_level: input.authorityLevel,
        usage_policy: input.usagePolicy,
        risk_level: input.riskLevel,
        evidence_note: input.evidenceNote.trim(),
        evidence_url: input.evidenceUrl?.trim() || undefined,
        valid_until: input.validUntil || undefined,
        reviewed_by: session?.user.userId ?? "console-reviewer",
        supersedes_revision_id: input.supersedesRevisionId || undefined,
      }),
    },
  );
  if (!response.ok) {
    throw new Error(await readErrorMessage(response, `Source registry review failed with ${response.status}`));
  }
  return ((await response.json()) as { data: SourceRegistryEntry }).data;
}

export async function createCitationEvidenceReviewCase(
  projectId: string,
  claimId: string,
  input: {
    citationId: string;
    supportLabel: "supports" | "contradicts" | "insufficient";
    sourceExcerpt: string;
    sourceContentSha256: string;
    sourceObjectRefId: string;
    sourceCaptureId: string;
    sourceSegmentId: string;
    sourceStart: number;
    sourceEnd: number;
    purpose?: "production" | "benchmark";
  },
): Promise<EvidenceReviewCase> {
  const session = getStoredAuthSession();
  const randomPart = globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random()}`;
  const response = await fetch(
    `/api/v1/projects/${encodeURIComponent(projectId)}/evidence-review-cases/citation-support`,
    {
      method: "POST",
      headers: {
        ...buildApiHeaders("trc_web_citation_review_case"),
        "Content-Type": "application/json",
        "Idempotency-Key": `citation-review-case-${claimId}-${randomPart}`,
      },
      body: JSON.stringify({
        claim_id: claimId,
        purpose: input.purpose ?? "production",
        review: {
          citation_id: input.citationId,
          support_label: input.supportLabel,
          evidence_grade: "source_page_snapshot",
          source_excerpt: input.sourceExcerpt,
          source_content_sha256: input.sourceContentSha256,
          source_object_ref_id: input.sourceObjectRefId,
          source_capture_id: input.sourceCaptureId,
          source_segment_id: input.sourceSegmentId,
          source_start: input.sourceStart,
          source_end: input.sourceEnd,
          rationale: "第一审核人独立核对不可变来源页面片段与回答断言。",
          review_method: "human",
          reviewed_by: session?.user.userId ?? "console-reviewer",
        },
      }),
    },
  );
  if (!response.ok) {
    throw new Error(await readErrorMessage(response, `Citation review case failed with ${response.status}`));
  }
  return ((await response.json()) as { data: EvidenceReviewCase }).data;
}

export async function submitEvidenceReviewDecision(
  caseId: string,
  input: { label: string; rationale: string },
): Promise<EvidenceReviewCase> {
  const session = getStoredAuthSession();
  const response = await fetch(
    `/api/v1/evidence-review-cases/${encodeURIComponent(caseId)}/decisions`,
    {
      method: "POST",
      headers: {
        ...buildApiHeaders("trc_web_evidence_review_decision"),
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        label: input.label,
        rationale: input.rationale,
        reviewed_by: session?.user.userId ?? "console-reviewer",
      }),
    },
  );
  if (!response.ok) {
    throw new Error(await readErrorMessage(response, `Evidence review decision failed with ${response.status}`));
  }
  return ((await response.json()) as { data: EvidenceReviewCase }).data;
}

export async function claimEvidenceReviewAssignment(
  caseId: string,
  expectedCaseVersion?: number,
): Promise<EvidenceReviewAssignment> {
  const response = await fetch(
    `/api/v1/evidence-review-cases/${encodeURIComponent(caseId)}/assignment-claims`,
    {
      method: "POST",
      headers: {
        ...buildApiHeaders("trc_web_evidence_review_assignment_claim"),
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ expected_case_version: expectedCaseVersion }),
    },
  );
  if (!response.ok) {
    throw new Error(await readErrorMessage(response, `Evidence review assignment claim failed with ${response.status}`));
  }
  return ((await response.json()) as { data: EvidenceReviewAssignment }).data;
}

export async function heartbeatEvidenceReviewAssignment(
  assignmentId: string,
  expectedVersion: number,
): Promise<EvidenceReviewAssignment> {
  const response = await fetch(
    `/api/v1/evidence-review-assignments/${encodeURIComponent(assignmentId)}/heartbeats`,
    {
      method: "POST",
      headers: {
        ...buildApiHeaders("trc_web_evidence_review_assignment_heartbeat"),
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ expected_version: expectedVersion }),
    },
  );
  if (!response.ok) {
    throw new Error(await readErrorMessage(response, `Evidence review assignment heartbeat failed with ${response.status}`));
  }
  return ((await response.json()) as { data: EvidenceReviewAssignment }).data;
}

export async function releaseEvidenceReviewAssignment(
  assignmentId: string,
  expectedVersion: number,
  reason: string,
): Promise<EvidenceReviewAssignment> {
  const response = await fetch(
    `/api/v1/evidence-review-assignments/${encodeURIComponent(assignmentId)}/release`,
    {
      method: "POST",
      headers: {
        ...buildApiHeaders("trc_web_evidence_review_assignment_release"),
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ expected_version: expectedVersion, reason }),
    },
  );
  if (!response.ok) {
    throw new Error(await readErrorMessage(response, `Evidence review assignment release failed with ${response.status}`));
  }
  return ((await response.json()) as { data: EvidenceReviewAssignment }).data;
}

export function fetchMeasurementQuality(
  projectId: string,
  runId: string,
  signal?: AbortSignal,
): Promise<MeasurementQualityReport> {
  return fetchData(
    `/api/v1/projects/${projectId}/scan-runs/${runId}/quality-report`,
    "trc_web_measurement_quality",
    signal,
  );
}

export function fetchLatestEvidenceIntegrityAudit(
  projectId: string,
  signal?: AbortSignal,
): Promise<EvidenceIntegrityAudit | null> {
  return fetchData(
    `/api/v1/projects/${encodeURIComponent(projectId)}/evidence-integrity-audits/latest`,
    "trc_web_evidence_integrity_latest",
    signal,
  );
}

export async function runEvidenceIntegrityAudit(projectId: string): Promise<EvidenceIntegrityAudit> {
  const randomPart = typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  const response = await fetch(
    `/api/v1/projects/${encodeURIComponent(projectId)}/evidence-integrity-audits`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Idempotency-Key": `evidence-integrity-${randomPart}`,
        ...buildApiHeaders("trc_web_evidence_integrity_run"),
      },
      body: JSON.stringify({ scope: "project" }),
    },
  );
  if (!response.ok) {
    throw new Error(await readErrorMessage(response, `Evidence integrity audit failed with ${response.status}`));
  }
  return ((await response.json()) as { data: EvidenceIntegrityAudit }).data;
}

export async function fetchEvidenceObject(objectRefId: string, signal?: AbortSignal): Promise<Blob> {
  const response = await fetch(`/api/v1/evidence-objects/${encodeURIComponent(objectRefId)}/content`, {
    headers: buildApiHeaders("trc_web_evidence_object"),
    signal,
  });
  if (!response.ok) {
    throw new Error(await readErrorMessage(response, `Evidence object request failed with ${response.status}`));
  }
  return response.blob();
}

export function fetchContentAssets(projectId: string, signal?: AbortSignal): Promise<GovernedContentAsset[]> {
  return fetchData(`/api/v1/projects/${projectId}/content-assets`, "trc_web_content_assets", signal);
}

export async function createGovernedContent(
  projectId: string,
  input: GovernedContentCreateInput,
): Promise<GovernedContentAsset> {
  const response = await fetch(`/api/v1/projects/${encodeURIComponent(projectId)}/content-assets`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...buildApiHeaders("trc_web_content_blueprint_create"),
    },
    body: JSON.stringify({
      asset_type: input.assetType,
      title: input.title,
      direction: input.direction,
      fact_revision_ids: input.factRevisionIds,
      created_by: input.createdBy,
    }),
  });
  if (!response.ok) {
    throw new Error(await readErrorMessage(response, `Content blueprint request failed with ${response.status}`));
  }
  return ((await response.json()) as { data: GovernedContentAsset }).data;
}

export async function createComparisonContent(
  projectId: string,
  input: ComparisonContentCreateInput,
): Promise<GovernedContentAsset> {
  const response = await fetch(`/api/v1/projects/${encodeURIComponent(projectId)}/comparison-content-assets`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...buildApiHeaders("trc_web_comparison_content_create"),
    },
    body: JSON.stringify({
      title: input.title,
      direction: input.direction,
      target_subject_id: input.targetSubjectId,
      subjects: input.subjects,
      dimensions: input.dimensions,
      cells: input.cells,
      created_by: input.createdBy,
    }),
  });
  if (!response.ok) {
    throw new Error(await readErrorMessage(response, `Comparison content request failed with ${response.status}`));
  }
  return ((await response.json()) as { data: GovernedContentAsset }).data;
}

export async function createExplainerContent(
  projectId: string,
  input: ExplainerContentCreateInput,
): Promise<GovernedContentAsset> {
  const response = await fetch(`/api/v1/projects/${encodeURIComponent(projectId)}/explainer-content-assets`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...buildApiHeaders("trc_web_explainer_content_create"),
    },
    body: JSON.stringify({
      title: input.title,
      direction: input.direction,
      subject_id: input.subjectId,
      subject_type: input.subjectType,
      display_name: input.displayName,
      brand_names: input.brandNames,
      assignments: input.assignments,
      created_by: input.createdBy,
    }),
  });
  if (!response.ok) {
    throw new Error(await readErrorMessage(response, `Explainer content request failed with ${response.status}`));
  }
  return ((await response.json()) as { data: GovernedContentAsset }).data;
}

export function fetchScanRuns(projectId: string, signal?: AbortSignal): Promise<ScanRun[]> {
  return fetchData(`/api/v1/projects/${projectId}/scan-runs`, "trc_web_scan_runs", signal);
}

export function fetchScanTasks(runId: string, signal?: AbortSignal): Promise<ScanTask[]> {
  return fetchData(`/api/v1/scan-runs/${runId}/tasks`, "trc_web_scan_tasks", signal);
}

export async function reviewContentAsset(
  assetId: string,
  action: "approved" | "rejected" | "changes_requested",
  reviewedBy: string,
): Promise<ContentReview> {
  const response = await fetch(`/api/v1/content-assets/${assetId}/reviews`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...buildApiHeaders("trc_web_content_review"),
    },
    body: JSON.stringify({ action, reviewed_by: reviewedBy }),
  });
  if (!response.ok) {
    throw new Error(await readErrorMessage(response, `Content review request failed with ${response.status}`));
  }
  const payload = (await response.json()) as { data: ContentReview };
  return payload.data;
}

export function fetchBuyerQuestions(projectId: string, signal?: AbortSignal): Promise<BuyerQuestion[]> {
  return fetchData(`/api/v1/projects/${projectId}/buyer-questions`, "trc_web_questions", signal);
}

export async function compileQuestionMap(projectId: string, input: QuestionMapCompileInput): Promise<QuestionMapResult> {
  const session = getStoredAuthSession();
  const response = await fetch(`/api/v1/projects/${projectId}/question-maps/compile`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...buildApiHeaders("trc_web_question_compile") },
    body: JSON.stringify({
      company_names: input.companyNames ?? [],
      product_terms: input.productTerms,
      competitor_names: input.competitorNames,
      regions: input.regions,
      seed_questions: input.seedQuestions,
      observation_batch_ids: input.observationBatchIds ?? [],
      include_template_candidates: input.includeTemplateCandidates,
      persist: input.persist ?? true,
      created_by: session?.user.userId ?? "console_operator",
    }),
  });
  if (!response.ok) {
    throw new Error(await readErrorMessage(response, `Question map compile request failed with ${response.status}`));
  }
  const payload = (await response.json()) as { data: QuestionMapResult };
  return payload.data;
}

export function fetchQuestionObservationBatches(
  projectId: string,
  signal?: AbortSignal,
): Promise<QuestionObservationBatch[]> {
  return fetchData(
    `/api/v1/projects/${projectId}/question-observation-batches`,
    "trc_web_question_observation_batches",
    signal,
  );
}

export async function importQuestionObservations(
  projectId: string,
  input: QuestionObservationImportInput,
): Promise<{ batch: QuestionObservationBatch; records: QuestionObservationRecord[] }> {
  const session = getStoredAuthSession();
  const response = await fetch(`/api/v1/projects/${projectId}/question-observation-batches`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...buildApiHeaders("trc_web_question_observation_import") },
    body: JSON.stringify({
      source_type: input.sourceType,
      source_name: input.sourceName,
      records: input.records.map((item) => ({
        source_record_id: item.sourceRecordId,
        question_text: item.questionText,
        occurrence_count: item.occurrenceCount,
        region: item.region || undefined,
      })),
      rights_attested: input.rightsAttested,
      imported_by: session?.user.userId ?? "console_operator",
    }),
  });
  if (!response.ok) {
    throw new Error(await readErrorMessage(response, `Question observation import failed with ${response.status}`));
  }
  const payload = (await response.json()) as {
    data: { batch: QuestionObservationBatch; records: QuestionObservationRecord[] };
  };
  return payload.data;
}

export async function reviewBuyerQuestion(
  projectId: string,
  questionId: string,
  action: "confirmed" | "archived",
  reviewNote: string,
): Promise<QuestionReview> {
  const session = getStoredAuthSession();
  const response = await fetch(`/api/v1/projects/${projectId}/buyer-questions/${questionId}/review`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", ...buildApiHeaders("trc_web_question_review") },
    body: JSON.stringify({
      action,
      reviewed_by: session?.user.userId ?? "console_operator",
      review_note: reviewNote,
    }),
  });
  if (!response.ok) {
    throw new Error(await readErrorMessage(response, `Question review request failed with ${response.status}`));
  }
  const payload = (await response.json()) as { data: QuestionReview };
  return payload.data;
}

export function fetchPublishPackages(projectId: string, signal?: AbortSignal): Promise<PublishPackage[]> {
  return fetchData(`/api/v1/projects/${projectId}/publish-packages`, "trc_web_publish", signal);
}

export async function createPublishPackage(input: PublishPackageCreateInput): Promise<PublishPackage> {
  const session = getStoredAuthSession();
  const randomPart = globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random()}`;
  const response = await fetch(
    `/api/v1/content-assets/${encodeURIComponent(input.assetId)}/publish-packages`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json", ...buildApiHeaders("trc_web_publish_create") },
      body: JSON.stringify({
        channel: input.channel,
        idempotency_key: `publish-${input.assetId}-${input.channel}-${randomPart}`,
        requested_by: session?.user.userId ?? "console_operator",
        target_endpoint: input.targetEndpoint || null,
      }),
    },
  );
  if (!response.ok) {
    throw new Error(await readErrorMessage(response, `Publish package request failed with ${response.status}`));
  }
  return ((await response.json()) as { data: PublishPackage }).data;
}

export async function recordPublicationEvidence(
  packageId: string,
  input: PublicationEvidenceInput,
): Promise<PublishPackage> {
  const session = getStoredAuthSession();
  const response = await fetch(
    `/api/v1/publish-packages/${encodeURIComponent(packageId)}/publication-evidence`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json", ...buildApiHeaders("trc_web_publication_evidence") },
      body: JSON.stringify({
        published_url: input.publishedUrl,
        baseline_run_id: input.baselineRunId,
        recorded_by: session?.user.userId ?? "console_operator",
        screenshot_ref_id: input.screenshotRefId || null,
        screenshot_sha256: input.screenshotSha256 || null,
      }),
    },
  );
  if (!response.ok) {
    throw new Error(await readErrorMessage(response, `Publication evidence request failed with ${response.status}`));
  }
  return ((await response.json()) as { data: PublishPackage }).data;
}

export function fetchPublishAttempts(packageId: string, signal?: AbortSignal): Promise<PublishAttempt[]> {
  return fetchData(`/api/v1/publish-packages/${packageId}/attempts`, "trc_web_publish_attempts", signal);
}

export function fetchRetestWindows(projectId: string, signal?: AbortSignal): Promise<RetestWindow[]> {
  return fetchData(`/api/v1/projects/${projectId}/retest-windows`, "trc_web_retest", signal);
}

export function fetchProviderReadiness(signal?: AbortSignal): Promise<ProviderReadiness> {
  return fetchData("/api/v1/provider-readiness", "trc_web_provider_health", signal);
}

export async function fetchProviderRoutes(signal?: AbortSignal): Promise<ProviderRouteStatus[]> {
  const data = await fetchData<{ routes: ProviderRouteStatus[]; window_hours: 24 }>(
    "/api/v1/admin/provider-routes",
    "trc_web_provider_routes",
    signal,
  );
  return data.routes;
}

export async function updateProviderRoute(
  route: Pick<ProviderRouteStatus, "provider" | "route_id">,
  input: ProviderRouteControlInput,
): Promise<void> {
  const response = await fetch(
    `/api/v1/admin/provider-routes/${encodeURIComponent(route.provider)}/${encodeURIComponent(route.route_id)}`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json", ...buildApiHeaders("trc_web_provider_route_update") },
      body: JSON.stringify({
        enabled: input.enabled,
        priority_override: input.priorityOverride,
        expected_version: input.expectedVersion,
        reason: input.reason,
      }),
    },
  );
  if (!response.ok) {
    throw new Error(await readErrorMessage(response, `Provider route update failed with ${response.status}`));
  }
}

export function fetchProviderCredentials(signal?: AbortSignal): Promise<ProviderCredentialPortfolio> {
  return fetchData(
    "/api/v1/admin/provider-credentials",
    "trc_web_provider_credentials",
    signal,
  );
}

export function fetchProviderCredentialOperations(signal?: AbortSignal): Promise<ProviderCredentialOperationList> {
  return fetchData(
    "/api/v1/admin/provider-credential-operations?limit=25",
    "trc_web_provider_credential_operations",
    signal,
  );
}

export function fetchProviderCredentialOperation(
  operationId: string,
  signal?: AbortSignal,
): Promise<ProviderCredentialOperation> {
  return fetchData(
    `/api/v1/admin/provider-credential-operations/${encodeURIComponent(operationId)}`,
    "trc_web_provider_credential_operation_detail",
    signal,
  );
}

function providerCredentialIdempotencyKey(operation: "upsert" | "revoke"): string {
  return `provider-credential-${operation}:${crypto.randomUUID()}`;
}

export async function upsertProviderCredential(
  credential: Pick<ProviderCredentialStatus, "provider" | "route_id" | "credential_version">,
  input: { secret: string; reason: string; confirmBillable: true },
): Promise<ProviderCredentialStatus> {
  const response = await fetch(
    `/api/v1/admin/provider-credentials/${encodeURIComponent(credential.provider)}/${encodeURIComponent(credential.route_id)}`,
    {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
        "Idempotency-Key": providerCredentialIdempotencyKey("upsert"),
        ...buildApiHeaders("trc_web_provider_credential_upsert"),
      },
      body: JSON.stringify({
        secret: input.secret,
        expected_version: credential.credential_version,
        reason: input.reason,
        confirm_billable: input.confirmBillable,
      }),
    },
  );
  if (!response.ok) {
    throw new Error(
      await readErrorMessage(response, `Provider credential update failed with ${response.status}`),
    );
  }
  return ((await response.json()) as { data: ProviderCredentialStatus }).data;
}

export async function revokeProviderCredential(
  credential: Pick<ProviderCredentialStatus, "provider" | "route_id" | "credential_version">,
  reason: string,
): Promise<ProviderCredentialStatus> {
  const response = await fetch(
    `/api/v1/admin/provider-credentials/${encodeURIComponent(credential.provider)}/${encodeURIComponent(credential.route_id)}/revoke`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Idempotency-Key": providerCredentialIdempotencyKey("revoke"),
        ...buildApiHeaders("trc_web_provider_credential_revoke"),
      },
      body: JSON.stringify({
        expected_version: credential.credential_version,
        reason,
      }),
    },
  );
  if (!response.ok) {
    throw new Error(
      await readErrorMessage(response, `Provider credential revoke failed with ${response.status}`),
    );
  }
  return ((await response.json()) as { data: ProviderCredentialStatus }).data;
}

export async function fetchInternalSkills(signal?: AbortSignal): Promise<InternalSkill[]> {
  const data = await fetchData<{ skills: InternalSkill[] }>("/api/v1/admin/skills", "trc_web_skills", signal);
  return data.skills;
}

export function fetchSkillPromotionLedger(signal?: AbortSignal): Promise<SkillPromotionLedger> {
  return fetchData("/api/v1/admin/skills/promotion-ledger", "trc_web_skill_ledger", signal);
}

export async function runBrandCheck(input: BrandCheckInput): Promise<BrandCheckResult> {
  const response = await fetch("/api/v1/brand-checks", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...buildApiHeaders("trc_web_brand_check"),
    },
    body: JSON.stringify({
      brand_name: input.brandName,
      website_url: input.websiteUrl,
      industry_hint: input.industryHint || undefined,
      competitor_hints: input.competitorHints ?? [],
      buyer_questions: input.buyerQuestions ?? [],
    }),
  });

  if (!response.ok) {
    throw new Error(await readErrorMessage(response, `Brand check request failed with ${response.status}`));
  }

  const payload = (await response.json()) as BrandCheckPayload;
  return {
    project: payload.data.project,
    scanRun: payload.data.scan_run,
    taskCount: payload.data.tasks.length,
    assetBundle: payload.data.asset_bundle,
    reports: payload.data.reports,
    overview: {
      project: payload.data.overview.project,
      metricCards: payload.data.overview.metric_cards,
      dataStatus: payload.data.overview.data_status,
      message: payload.data.overview.message,
    },
  };
}

export async function recordDownloadReceipt(packet: ReportEvidencePacket): Promise<void> {
  const response = await fetch(`/api/v1/reports/${packet.report_id}/download-receipts`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...buildApiHeaders("trc_web_receipt"),
    },
    body: JSON.stringify({
      packet_id: packet.packet_id,
      content_sha256: packet.content_sha256,
    }),
  });

  if (!response.ok) {
    throw new Error(await readErrorMessage(response, `Download receipt request failed with ${response.status}`));
  }
}

export async function createReportEvidencePacket(reportId: string): Promise<ReportEvidencePacket> {
  const headers = buildApiHeaders("trc_web_report_packet");
  headers["Idempotency-Key"] = `report-packet-${reportId}-v7-${crypto.randomUUID()}`;
  const response = await fetch(`/api/v1/reports/${reportId}/evidence-packets`, {
    method: "POST",
    headers,
  });

  if (!response.ok) {
    throw new Error(
      await readErrorMessage(response, `Evidence packet request failed with ${response.status}`),
    );
  }
  return ((await response.json()) as ReportEvidencePacketPayload).data;
}

function bytesToHex(bytes: Uint8Array): string {
  return Array.from(bytes, (value) => value.toString(16).padStart(2, "0")).join("");
}

export async function downloadReportEvidencePacket(
  report: ReportItem,
): Promise<ReportEvidencePacket> {
  const packet = await createReportEvidencePacket(report.report_id);
  const response = await fetch(packet.content_url, {
    headers: buildApiHeaders("trc_web_report_packet_content"),
  });
  if (!response.ok) {
    throw new Error(
      await readErrorMessage(response, `Evidence packet download failed with ${response.status}`),
    );
  }
  const payload = await response.arrayBuffer();
  const digest = bytesToHex(new Uint8Array(await crypto.subtle.digest("SHA-256", payload)));
  if (digest !== packet.content_sha256) {
    throw new Error("EVIDENCE_INTEGRITY_FAILED");
  }

  const extension = packet.content_type === "application/zip" ? "zip" : "json";
  const filename = `${report.title.replace(/[\\/:*?"<>|]+/g, "-")}-可核验证据包.${extension}`;
  const objectUrl = URL.createObjectURL(new Blob([payload], { type: packet.content_type }));
  try {
    const anchor = document.createElement("a");
    anchor.href = objectUrl;
    anchor.download = filename;
    anchor.click();
  } finally {
    URL.revokeObjectURL(objectUrl);
  }
  await recordDownloadReceipt(packet);
  return packet;
}

export async function recordConsoleAction(input: ConsoleActionInput): Promise<ConsoleActionReceipt> {
  const response = await fetch("/api/v1/console/actions", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...buildApiHeaders("trc_web_action"),
    },
    body: JSON.stringify({
      project_id: input.projectId,
      action_type: input.actionType,
      label: input.label,
      source_route: input.sourceRoute,
      entity_type: input.entityType,
      entity_id: input.entityId,
      payload: input.payload ?? {},
    }),
  });

  if (!response.ok) {
    throw new Error(await readErrorMessage(response, `Console action request failed with ${response.status}`));
  }

  const payload = (await response.json()) as ConsoleActionPayload;
  return payload.data;
}
