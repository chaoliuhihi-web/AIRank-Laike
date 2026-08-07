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

export type ScanRunSummary = {
  run_id: string;
  status: "queued" | "running" | "completed" | "failed" | "canceled";
  metrics: Record<string, unknown>;
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
