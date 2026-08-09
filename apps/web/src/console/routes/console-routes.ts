export type ConsoleAudience = "customer" | "delivery" | "admin";
export type ConsoleRouteGroup = "overview" | "growth" | "result" | "operations" | "platform";

export type ConsoleRoute = {
  id: string;
  path: string;
  label: string;
  icon: string;
  group: ConsoleRouteGroup;
  audience: ConsoleAudience;
  step?: 1 | 2 | 3 | 4 | 5 | 6;
  showInNavigation: boolean;
  requiredPermission?: string;
  featureFlag?: string;
  legacyPaths?: string[];
};

export const customerRoutes: ConsoleRoute[] = [
  { id: "dashboard", path: "/console", label: "工作台", icon: "Home", group: "overview", audience: "customer", showInNavigation: true },
  { id: "questions", path: "/console/questions", label: "买家问题", icon: "Map", group: "growth", audience: "customer", step: 1, showInNavigation: true },
  { id: "scans", path: "/console/scans", label: "多平台扫描", icon: "ScanSearch", group: "growth", audience: "customer", step: 2, showInNavigation: true, legacyPaths: ["/console/checkup", "/console/tasks", "/console/evidence"] },
  { id: "gaps", path: "/console/gaps", label: "证据缺口", icon: "ShieldAlert", group: "growth", audience: "customer", step: 3, showInNavigation: true },
  { id: "facts", path: "/console/facts", label: "可信事实", icon: "NotebookTabs", group: "growth", audience: "customer", step: 4, showInNavigation: true },
  { id: "assets", path: "/console/assets", label: "答案资产", icon: "PackageCheck", group: "growth", audience: "customer", step: 5, showInNavigation: true },
  { id: "publishing", path: "/console/publishing", label: "发布与复测", icon: "Rocket", group: "growth", audience: "customer", step: 6, showInNavigation: true },
  { id: "reports", path: "/console/reports", label: "客户报告", icon: "FileChartColumn", group: "result", audience: "customer", showInNavigation: true },
  { id: "settings", path: "/console/settings", label: "项目设置", icon: "Settings", group: "result", audience: "customer", showInNavigation: false },
  { id: "gap-questions", path: "/console/gaps/questions", label: "缺口问题", icon: "ListChecks", group: "growth", audience: "customer", showInNavigation: false },
  { id: "sample-detail", path: "/console/samples", label: "样本详情", icon: "FileSearch", group: "result", audience: "customer", showInNavigation: false },
  { id: "site-audit", path: "/console/assets/site-audit", label: "官网可提取性", icon: "ScanSearch", group: "growth", audience: "customer", showInNavigation: false, legacyPaths: ["/console/page-audit"] },
  { id: "asset-reviews", path: "/console/assets/reviews", label: "资产审核", icon: "BadgeCheck", group: "growth", audience: "customer", showInNavigation: false },
];

export const deliveryRoutes: ConsoleRoute[] = [
  { id: "delivery-home", path: "/delivery", label: "交付总览", icon: "BriefcaseBusiness", group: "overview", audience: "delivery", showInNavigation: true, requiredPermission: "airank:delivery:admin" },
  { id: "delivery-tasks", path: "/delivery/tasks", label: "异常任务", icon: "ClipboardList", group: "operations", audience: "delivery", showInNavigation: true, requiredPermission: "airank:delivery:admin" },
  { id: "delivery-evidence", path: "/delivery/evidence", label: "证据补录", icon: "FileSearch", group: "operations", audience: "delivery", showInNavigation: true, requiredPermission: "airank:review:admin" },
  { id: "delivery-reviews", path: "/delivery/reviews", label: "审核队列", icon: "BadgeCheck", group: "operations", audience: "delivery", showInNavigation: true, requiredPermission: "airank:review:admin" },
  { id: "delivery-publishing", path: "/delivery/publishing", label: "发布协调", icon: "SquarePen", group: "operations", audience: "delivery", showInNavigation: true, requiredPermission: "airank:delivery:admin" },
];

export const adminRoutes: ConsoleRoute[] = [
  { id: "admin-home", path: "/admin", label: "平台总览", icon: "Activity", group: "overview", audience: "admin", showInNavigation: true, requiredPermission: "airank:provider:admin" },
  { id: "admin-providers", path: "/admin/providers", label: "Provider 管理", icon: "Zap", group: "platform", audience: "admin", showInNavigation: true, requiredPermission: "airank:provider:admin" },
  { id: "admin-skills", path: "/admin/skills", label: "Skill 管理", icon: "Workflow", group: "platform", audience: "admin", showInNavigation: true, requiredPermission: "airank:skill:admin" },
  { id: "admin-operations", path: "/admin/operations", label: "队列与审计", icon: "Settings", group: "platform", audience: "admin", showInNavigation: true, requiredPermission: "airank:provider:platform-admin" },
];

export const consoleRoutes = [...customerRoutes, ...deliveryRoutes, ...adminRoutes];

export const legacyRouteRedirects: Record<string, string> = {
  "/console/checkup": "/console/scans",
  "/console/tasks": "/console/scans",
  "/console/evidence": "/console/scans",
  "/console/page-audit": "/console/assets/site-audit",
  "/console/skills": "/admin/skills",
  "/console/assistant": "/console",
};

function permissionMatches(granted: string, required: string): boolean {
  if (granted === "*" || granted === "*:*:*" || granted === required) return true;
  return granted.endsWith(":*") && required.startsWith(granted.slice(0, -1));
}

export function routeIsAccessible(route: ConsoleRoute, permissions: string[]): boolean {
  if (!route.requiredPermission) return true;
  return permissions.some((permission) => permissionMatches(permission, route.requiredPermission!));
}

export function audienceForPath(path: string): ConsoleAudience {
  if (path === "/delivery" || path.startsWith("/delivery/")) return "delivery";
  if (path === "/admin" || path.startsWith("/admin/")) return "admin";
  return "customer";
}

export function routesForAudience(audience: ConsoleAudience): ConsoleRoute[] {
  if (audience === "delivery") return deliveryRoutes;
  if (audience === "admin") return adminRoutes;
  return customerRoutes;
}

export function activeRouteForPath(path: string): ConsoleRoute | undefined {
  return [...consoleRoutes]
    .sort((left, right) => right.path.length - left.path.length)
    .find((route) => path === route.path || path.startsWith(`${route.path}/`));
}
