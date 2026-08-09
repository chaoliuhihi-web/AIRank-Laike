import { useEffect, useRef, useState } from "react";
import {
  Activity,
  BadgeCheck,
  BriefcaseBusiness,
  ChevronDown,
  CircleUserRound,
  ClipboardList,
  FileChartColumn,
  FileSearch,
  HelpCircle,
  Home,
  ListChecks,
  LogOut,
  Map,
  Menu,
  NotebookTabs,
  PackageCheck,
  Rocket,
  ScanSearch,
  Settings,
  ShieldAlert,
  Sparkles,
  SquarePen,
  Workflow,
  X,
  Zap,
  type LucideIcon,
} from "lucide-react";
import {
  audienceForPath,
  routeIsAccessible,
  routesForAudience,
  type ConsoleAudience,
} from "../routes/console-routes";

const iconMap: Record<string, LucideIcon> = {
  Activity,
  BadgeCheck,
  BriefcaseBusiness,
  ClipboardList,
  FileChartColumn,
  FileSearch,
  Home,
  ListChecks,
  Map,
  NotebookTabs,
  PackageCheck,
  Rocket,
  ScanSearch,
  Settings,
  ShieldAlert,
  SquarePen,
  Workflow,
  Zap,
};

const audienceMeta: Record<ConsoleAudience, { label: string; home: string }> = {
  customer: { label: "客户控制台", home: "/console" },
  delivery: { label: "交付工作台", home: "/delivery" },
  admin: { label: "平台管理后台", home: "/admin" },
};

type ConsoleSidebarProps = {
  activePath: string;
  projectName: string;
  userName: string;
  permissions: string[];
  dataStatus: "empty" | "collecting" | "provider_evidence" | "unverified";
  growthLoopSteps?: Array<{
    step_id: string;
    status: "completed" | "current" | "blocked" | "pending";
  }>;
  onNavigate: (path: string) => void;
  onHelp: () => void;
  onLogout: () => void;
};

function routeActive(activePath: string, routePath: string): boolean {
  if (["/console", "/delivery", "/admin"].includes(routePath)) return activePath === routePath;
  return activePath === routePath || activePath.startsWith(`${routePath}/`);
}

function stepState(
  step: number | undefined,
  active: boolean,
  dataStatus: ConsoleSidebarProps["dataStatus"],
): "current" | "completed" | "blocked" | "pending" | undefined {
  if (!step) return undefined;
  if (active) return "current";
  if (step === 1 && dataStatus !== "empty") return "completed";
  if (step === 2 && dataStatus === "provider_evidence") return "completed";
  if (step >= 3 && dataStatus !== "provider_evidence") return "blocked";
  return "pending";
}

export function ConsoleSidebar({
  activePath,
  projectName,
  userName,
  permissions,
  dataStatus,
  growthLoopSteps,
  onNavigate,
  onHelp,
  onLogout,
}: ConsoleSidebarProps) {
  const [mobileOpen, setMobileOpen] = useState(false);
  const sidebarRef = useRef<HTMLElement>(null);
  const audience = audienceForPath(activePath);
  const routes = routesForAudience(audience).filter(
    (route) => route.showInNavigation && routeIsAccessible(route, permissions),
  );
  const currentRoute = routes.find((route) => routeActive(activePath, route.path));
  const canAccessDelivery = routesForAudience("delivery").some((route) => routeIsAccessible(route, permissions));
  const canAccessAdmin = routesForAudience("admin").some((route) => routeIsAccessible(route, permissions));

  const navigate = (path: string) => {
    setMobileOpen(false);
    onNavigate(path);
  };

  useEffect(() => {
    if (!mobileOpen) return undefined;
    sidebarRef.current?.scrollTo({ top: 0 });
    const frame = window.requestAnimationFrame(() => sidebarRef.current?.scrollTo({ top: 0 }));
    const timer = window.setTimeout(() => sidebarRef.current?.scrollTo({ top: 0 }), 200);
    return () => {
      window.cancelAnimationFrame(frame);
      window.clearTimeout(timer);
    };
  }, [mobileOpen]);

  const toggleMobileNavigation = () => {
    if (!mobileOpen && sidebarRef.current) {
      sidebarRef.current.scrollTop = 0;
    }
    setMobileOpen((open) => !open);
  };

  return (
    <>
      <header className="console-mobile-header">
        <button
          className="console-mobile-menu"
          type="button"
          aria-label={mobileOpen ? "关闭导航" : "打开导航"}
          aria-expanded={mobileOpen}
          onClick={toggleMobileNavigation}
        >
          {mobileOpen ? <X size={22} /> : <Menu size={22} />}
        </button>
        <div>
          <strong>{currentRoute?.step ? `${String(currentRoute.step).padStart(2, "0")} ${currentRoute.label}` : currentRoute?.label ?? audienceMeta[audience].label}</strong>
          <span>{projectName || "AIRank 项目"}</span>
        </div>
      </header>
      {mobileOpen && <button className="console-nav-backdrop" type="button" aria-label="关闭导航" onClick={() => setMobileOpen(false)} />}
      <aside ref={sidebarRef} className="airank-console-sidebar" data-open={mobileOpen} data-audience={audience}>
        <button className="brand-lockup sidebar-brand-button" type="button" onClick={() => navigate(audienceMeta[audience].home)}>
          <img className="sidebar-brand-logo" src="/favicon.svg" alt="AIRank Logo" />
          <div>
            <div className="brand-title">AIRank</div>
            <div className="brand-subtitle">{audienceMeta[audience].label}</div>
          </div>
        </button>

        <div className="workspace-switcher" aria-label="产品区域">
          <button type="button" data-active={audience === "customer"} onClick={() => navigate("/console")}>客户</button>
          {canAccessDelivery && <button type="button" data-active={audience === "delivery"} onClick={() => navigate("/delivery")}>交付</button>}
          {canAccessAdmin && <button type="button" data-active={audience === "admin"} onClick={() => navigate("/admin")}>管理</button>}
        </div>

        <nav className="console-nav" aria-label={audienceMeta[audience].label}>
          {routes.map((route) => {
            const Icon = iconMap[route.icon] ?? Home;
            const active = routeActive(activePath, route.path);
            const governedState = growthLoopSteps?.find((step) => step.step_id === route.id)?.status;
            const state = governedState ?? stepState(route.step, active, dataStatus);
            return (
              <button
                key={route.id}
                className="airank-console-nav-item"
                data-active={active}
                data-step-state={state}
                type="button"
                onClick={() => navigate(route.path)}
              >
                {route.step ? <span className="growth-step-index">{String(route.step).padStart(2, "0")}</span> : <Icon size={20} strokeWidth={2.2} />}
                <span>{route.label}</span>
                {state === "completed" && <span className="growth-step-dot" aria-label="已完成">✓</span>}
                {state === "blocked" && <span className="growth-step-dot" aria-label="前置条件未满足">•</span>}
              </button>
            );
          })}
        </nav>

        <div className="sidebar-footer">
          {audience === "customer" && (
            <button className="help-link" type="button" onClick={() => navigate("/console/settings")}>
              <Settings size={20} />
              <span>项目设置</span>
            </button>
          )}
          <button className="help-link" type="button" onClick={onHelp}>
            <HelpCircle size={20} />
            <span>帮助与支持</span>
          </button>
          <button className="help-link" type="button" onClick={onLogout}>
            <LogOut size={20} />
            <span>退出登录</span>
          </button>
          <div className="tenant-switcher">
            <div className="tenant-avatar"><CircleUserRound size={22} /></div>
            <div>
              <div className="tenant-name">{userName || projectName || "AIRank 用户"}</div>
              <div className="tenant-plan">{audienceMeta[audience].label}</div>
            </div>
            <ChevronDown size={17} />
          </div>
        </div>
      </aside>
    </>
  );
}

export function ConsoleWorkspaceHeader({
  activePath,
  projectName,
  projectDate,
  dataStatus,
}: Pick<ConsoleSidebarProps, "activePath" | "projectName" | "dataStatus"> & { projectDate: string }) {
  const route = [...routesForAudience(audienceForPath(activePath))]
    .sort((left, right) => right.path.length - left.path.length)
    .find((item) => activePath === item.path || activePath.startsWith(`${item.path}/`));
  const status = dataStatus === "provider_evidence"
    ? "真实数据"
    : dataStatus === "collecting"
      ? "运行中"
      : dataStatus === "unverified"
        ? "待验证"
        : "暂无数据";
  return (
    <div className="console-workspace-header" aria-label="当前项目与数据状态">
      <div>
        <span>当前项目</span>
        <strong>{projectName || "尚未建立项目"}</strong>
      </div>
      <div>
        <span>当前步骤</span>
        <strong>{route?.step ? `${String(route.step).padStart(2, "0")} · ${route.label}` : route?.label ?? "工作台"}</strong>
      </div>
      <div>
        <span>数据状态</span>
        <strong data-status={dataStatus}><Sparkles size={14} />{status}</strong>
      </div>
      <div>
        <span>数据时间</span>
        <strong>{projectDate || "尚无成功批次"}</strong>
      </div>
    </div>
  );
}
