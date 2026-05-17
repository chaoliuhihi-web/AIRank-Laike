import { assetCards, metricCards, project, reportCards, type Tone } from "./data";

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

export async function fetchConsoleOverview(signal?: AbortSignal): Promise<ConsoleOverview> {
  const response = await fetch("/api/v1/console/overview", {
    headers: {
      "tenant-id": "tenant_demo",
      "X-AIRank-Trace-Id": `trc_web_${Date.now()}`,
    },
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
    headers: {
      "tenant-id": "tenant_demo",
      "X-AIRank-Trace-Id": `trc_web_asset_${Date.now()}`,
    },
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
    headers: {
      "tenant-id": "tenant_demo",
      "X-AIRank-Trace-Id": `trc_web_reports_${Date.now()}`,
    },
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
    headers: {
      "tenant-id": "tenant_demo",
      "X-AIRank-Trace-Id": `trc_web_receipt_${Date.now()}`,
    },
  });
}
