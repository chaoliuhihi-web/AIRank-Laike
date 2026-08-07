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

export type ReportItem = {
  report_id?: string;
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

export type MeasurementQualityReport = {
  contract_version: "airank.measurement-quality.v3";
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
  generation_mode: "approved_fact_template";
  fact_revision_ids: string[];
  claim_assertion_ids: string[];
  claim_support_ids: string[];
  created_at: string;
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
    blocker_code?: string;
    reason?: string;
  }>;
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

export function searchKnowledge(projectId: string, query: string, signal?: AbortSignal): Promise<KnowledgeSearch> {
  const params = new URLSearchParams({ q: query, limit: "20" });
  return fetchData(`/api/v1/projects/${projectId}/knowledge-search?${params.toString()}`, "trc_web_knowledge_search", signal);
}

export function fetchFacts(projectId: string, signal?: AbortSignal): Promise<FactRevision[]> {
  return fetchData(`/api/v1/projects/${projectId}/facts`, "trc_web_facts", signal);
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

export function fetchPublishAttempts(packageId: string, signal?: AbortSignal): Promise<PublishAttempt[]> {
  return fetchData(`/api/v1/publish-packages/${packageId}/attempts`, "trc_web_publish_attempts", signal);
}

export function fetchRetestWindows(projectId: string, signal?: AbortSignal): Promise<RetestWindow[]> {
  return fetchData(`/api/v1/projects/${projectId}/retest-windows`, "trc_web_retest", signal);
}

export function fetchProviderReadiness(signal?: AbortSignal): Promise<ProviderReadiness> {
  return fetchData("/api/v1/provider-readiness", "trc_web_provider_health", signal);
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

export async function recordDownloadReceipt(reportId: string): Promise<void> {
  const response = await fetch(`/api/v1/reports/${reportId}/download-receipts`, {
    method: "POST",
    headers: buildApiHeaders("trc_web_receipt"),
  });

  if (!response.ok) {
    throw new Error(await readErrorMessage(response, `Download receipt request failed with ${response.status}`));
  }
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
