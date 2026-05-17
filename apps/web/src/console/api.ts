import { assetCards, metricCards, project, reportCards, type Tone } from "./data";

const AUTH_SESSION_STORAGE_KEY = "airank.auth.session.v1";

export type ConsoleProject = typeof project & {
  id?: string;
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

export type AuthLoginInput = {
  username: string;
  password: string;
  yudaoTenantId: string;
};

type ConsoleOverviewPayload = {
  data: {
    project: ConsoleProject;
    metric_cards: ConsoleMetricCard[];
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

export const fallbackConsoleOverview: ConsoleOverview = {
  project,
  metricCards,
};

export const fallbackAssetBundle: AssetBundle = {
  project_id: "project_demo",
  tenant_id: "tenant_demo",
  completeness: 68,
  recommendation: "建议先补齐竞品对比页和客户案例页，再发布复测。",
  assets: assetCards,
};

export const fallbackReportList: ReportList = {
  project_id: "project_demo",
  tenant_id: "tenant_demo",
  reports: reportCards,
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

export async function recordDownloadReceipt(reportId: string): Promise<void> {
  await fetch(`/api/v1/reports/${reportId}/download-receipts`, {
    method: "POST",
    headers: buildApiHeaders("trc_web_receipt"),
  });
}
