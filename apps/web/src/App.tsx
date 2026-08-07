import { createContext, useContext, useEffect, useState } from "react";
import type { FormEvent, ReactNode } from "react";
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  BadgeCheck,
  BarChart3,
  Bell,
  BookOpen,
  Bot,
  Box,
  BriefcaseBusiness,
  Building2,
  CalendarDays,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  CircleUserRound,
  ClipboardList,
  CloudUpload,
  Code2,
  Crown,
  Download,
  Eye,
  ExternalLink,
  FileChartColumn,
  FileText,
  Globe2,
  HelpCircle,
  Home,
  Info,
  Link2,
  ListChecks,
  Lightbulb,
  LucideIcon,
  Map,
  MessageCircle,
  NotebookTabs,
  PackageCheck,
  Phone,
  PieChart,
  Play,
  Rocket,
  RotateCw,
  Scale,
  SearchCheck,
  Send,
  Settings,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  SquarePen,
  Share2,
  Target,
  ThumbsUp,
  UserRound,
  UsersRound,
  Workflow,
  Zap,
} from "lucide-react";
import { consoleRoutes } from "./console/routes/console-routes";
import {
  fallbackConsoleOverview,
  fallbackAssetBundle,
  fetchBuyerQuestions,
  fetchAssetBundle,
  fetchConsoleOverview,
  fetchFacts,
  fetchKnowledgeSources,
  fetchProviderReadiness,
  fetchPublishAttempts,
  fetchPublishPackages,
  fetchRetestWindows,
  fallbackReportList,
  fetchReports,
  getStoredAuthSession,
  loginToAirank,
  recordConsoleAction,
  recordDownloadReceipt,
  runBrandCheck,
  storeAuthSession,
  type AuthSession,
  type AssetBundle,
  type BuyerQuestion,
  type BrandCheckResult,
  type ConsoleActionInput,
  type ConsoleMetricCard,
  type ConsoleOverview,
  type FactRevision,
  type KnowledgeSource,
  type ProviderReadiness,
  type PublishPackage,
  type ReportItem,
  type ReportList,
  type RetestWindow,
} from "./console/api";
import type { Tone } from "./console/data";

const blockedNextActions = [
  { title: "检查 Provider 健康", level: "上线阻断", desc: "确认计划使用的平台已通过对应 API 或消费端采集器的真实探测。", cta: "查看体检状态" },
  { title: "重跑真实采样", level: "关键步骤", desc: "提交品牌检测，生成可追溯快照、引用和排名结果。", cta: "回到检测页" },
  { title: "再生成资产和报告", level: "等待采样", desc: "真实采样完成前不要发布 GEO 结论、AI 收录包或老板报告。", cta: "查看设置" },
];

const evidenceNextActions = [
  { title: "审核企业事实", level: "事实门禁", desc: "只让已审核、未过期且无冲突的事实进入公开内容。", cta: "查看事实库" },
  { title: "生成证据绑定内容", level: "内容门禁", desc: "每条公开主张都必须关联 FactRevision 与原文边界。", cta: "查看内容资产" },
  { title: "发布并进入复测", level: "观察阶段", desc: "发布后按 T0、T+7、T+14、T+30 同口径复测，不承诺因果。", cta: "查看发布复测" },
];

const iconMap: Record<string, LucideIcon> = {
  Activity,
  AlertTriangle,
  BadgeCheck,
  BarChart3,
  Bell,
  Bot,
  BriefcaseBusiness,
  Building2,
  CalendarDays,
  CheckCircle2,
  CircleUserRound,
  ClipboardList,
  FileChartColumn,
  Globe2,
  Home,
  Link2,
  ListChecks,
  Map,
  NotebookTabs,
  PackageCheck,
  Phone,
  PieChart,
  Rocket,
  RotateCw,
  SearchCheck,
  Send,
  Settings,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  SquarePen,
  Target,
  UserRound,
  UsersRound,
  Zap,
};

const navRoutes = consoleRoutes.filter((route) => route.id !== "gap-questions");
const ConsoleOverviewContext = createContext<ConsoleOverview>(fallbackConsoleOverview);
const ConsoleOverviewStatusContext = createContext<"loading" | "api" | "fallback">("loading");
const assetCardIcons: LucideIcon[] = [FileText, Box, UsersRound, MessageCircle, Scale, Lightbulb, Code2, Workflow];
const reportCardIcons: LucideIcon[] = [CalendarDays, NotebookTabs, Crown, FileChartColumn];
const publishingSteps: [string, string][] = [
  ["事实核验", "只使用已审核且未过期的事实"],
  ["内容风险审核", "记录风险结果和人工 override"],
  ["不可变快照", "内容 hash 与审核结果绑定"],
  ["导出发布包", "export 渠道当前为 ready"],
  ["登记发布证据", "保存 URL、截图引用与 T0 基线"],
  ["建立观察窗口", "T0 / T+7 / T+14 / T+30"],
  ["同口径复测", "只输出观察性、非因果结论"],
];

type FeedbackTone = "success" | "warning" | "danger" | "primary";
type ToastState = {
  id: number;
  title: string;
  desc: string;
  tone: FeedbackTone;
};
type ActionPanelState = {
  title: string;
  desc: string;
  items?: string[];
  primaryLabel?: string;
  onPrimary?: () => void;
};
type ActionFeedback = {
  notify: (toast: Omit<ToastState, "id">) => void;
  openPanel: (panel: ActionPanelState) => void;
  closePanel: () => void;
  recordAction: (action: Omit<ConsoleActionInput, "projectId" | "sourceRoute">) => Promise<void>;
};

const ActionFeedbackContext = createContext<ActionFeedback>({
  notify: () => undefined,
  openPanel: () => undefined,
  closePanel: () => undefined,
  recordAction: async () => undefined,
});

function useConsoleOverview() {
  return useContext(ConsoleOverviewContext);
}

function useConsoleOverviewStatus() {
  return useContext(ConsoleOverviewStatusContext);
}

function useActionFeedback() {
  return useContext(ActionFeedbackContext);
}

function App() {
  const [path, setPath] = useState(() => normalizePath(window.location.pathname));
  const [authSession, setAuthSession] = useState<AuthSession | null>(() => getStoredAuthSession());
  const [overview, setOverview] = useState<ConsoleOverview>(fallbackConsoleOverview);
  const [overviewStatus, setOverviewStatus] = useState<"loading" | "api" | "fallback">("loading");
  const [toast, setToast] = useState<ToastState | null>(null);
  const [actionPanel, setActionPanel] = useState<ActionPanelState | null>(null);

  const navigate = (nextPath: string) => {
    const normalized = normalizePath(nextPath);
    window.history.pushState({}, "", normalized);
    setPath(normalized);
  };

  useEffect(() => {
    const onPopState = () => setPath(normalizePath(window.location.pathname));
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  useEffect(() => {
    if (!authSession) {
      setOverview(fallbackConsoleOverview);
      setOverviewStatus("fallback");
      return;
    }

    setOverviewStatus("loading");
    const controller = new AbortController();
    fetchConsoleOverview(controller.signal)
      .then((nextOverview) => {
        setOverview(nextOverview);
        setOverviewStatus("api");
      })
      .catch(() => {
        setOverview(fallbackConsoleOverview);
        setOverviewStatus("fallback");
      });
    return () => controller.abort();
  }, [authSession]);

  useEffect(() => {
    if (!authSession && path !== "/login") {
      navigate("/login");
      return;
    }
    if (authSession && path === "/login") {
      navigate("/console");
    }
  }, [authSession, path]);

  const handleLogin = (nextSession: AuthSession) => {
    storeAuthSession(nextSession);
    setOverviewStatus("loading");
    setAuthSession(nextSession);
    navigate("/console");
  };

  const applyBrandCheckResult = (result: BrandCheckResult) => {
    setOverview(result.overview);
    setOverviewStatus("api");
  };

  const showToast = (nextToast: Omit<ToastState, "id">) => {
    const id = Date.now();
    setToast({ ...nextToast, id });
    window.setTimeout(() => {
      setToast((currentToast) => (currentToast?.id === id ? null : currentToast));
    }, 3200);
  };

  const recordAction = async (action: Omit<ConsoleActionInput, "projectId" | "sourceRoute">) => {
    if (!overview.project.id) {
      return;
    }
    try {
      await recordConsoleAction({
        ...action,
        projectId: overview.project.id,
        sourceRoute: path,
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : "后端未能记录本次操作，请稍后重试。";
      if (message === "Project not found" || message === "PROJECT_NOT_FOUND") {
        return;
      }
      showToast({
        title: "操作记录失败",
        desc: message,
        tone: "danger",
      });
    }
  };

  const notify = (nextToast: Omit<ToastState, "id">) => {
    void recordAction({
      actionType: "ui.notify",
      label: nextToast.title,
      entityType: "toast",
      entityId: nextToast.tone,
      payload: { desc: nextToast.desc, tone: nextToast.tone },
    });
    showToast(nextToast);
  };

  const openActionPanel = (nextPanel: ActionPanelState) => {
    void recordAction({
      actionType: "panel.open",
      label: nextPanel.title,
      entityType: "console_panel",
      payload: { desc: nextPanel.desc, items: nextPanel.items ?? [], primary_label: nextPanel.primaryLabel ?? null },
    });
    setActionPanel(nextPanel);
  };

  const navigateWithAudit = (nextPath: string) => {
    void recordAction({
      actionType: "navigation.route",
      label: "页面导航",
      entityType: "route",
      entityId: nextPath,
      payload: { from: path, to: nextPath },
    });
    navigate(nextPath);
  };

  if (!authSession || path === "/login") {
    return <LoginPage onLogin={handleLogin} />;
  }

  return (
    <ConsoleOverviewContext.Provider value={overview}>
      <ConsoleOverviewStatusContext.Provider value={overviewStatus}>
        <ActionFeedbackContext.Provider
          value={{
            notify,
            openPanel: openActionPanel,
            closePanel: () => setActionPanel(null),
            recordAction,
          }}
        >
          <main className="airank-console">
            <div className="airank-console-shell">
              <Sidebar activePath={path} onNavigate={navigateWithAudit} />
              <section className="airank-console-main">
                <ConsolePage path={path} onNavigate={navigateWithAudit} onBrandCheckComplete={applyBrandCheckResult} />
              </section>
            </div>
            {toast && <ActionToast toast={toast} onDismiss={() => setToast(null)} />}
            {actionPanel && <ActionPanel panel={actionPanel} onClose={() => setActionPanel(null)} />}
          </main>
        </ActionFeedbackContext.Provider>
      </ConsoleOverviewStatusContext.Provider>
    </ConsoleOverviewContext.Provider>
  );
}

function LoginPage({ onLogin }: { onLogin: (session: AuthSession) => void }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [yudaoTenantId, setYudaoTenantId] = useState("1");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const submitLogin = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const session = await loginToAirank({ username, password, yudaoTenantId });
      onLogin(session);
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "Login failed");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <main className="airank-login">
      <section className="airank-login-panel">
        <div className="brand-lockup login-brand">
          <div className="brand-mark">
            <Sparkles size={25} />
          </div>
          <div>
            <div className="brand-title">AIRank Laike</div>
            <div className="brand-subtitle">Product console</div>
          </div>
        </div>
        <div className="login-copy">
          <h1>Sign in</h1>
          <p>Use yudao credentials to open the AIRank console. Local demos can set AIRANK_AUTH_MODE=dev_only.</p>
        </div>
        <form className="login-form" onSubmit={submitLogin}>
          <label>
            <span>Yudao tenant</span>
            <input value={yudaoTenantId} onChange={(event) => setYudaoTenantId(event.target.value)} autoComplete="organization" />
          </label>
          <label>
            <span>Username</span>
            <input value={username} onChange={(event) => setUsername(event.target.value)} autoComplete="username" required />
          </label>
          <label>
            <span>Password</span>
            <input
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete="current-password"
              type="password"
              required
            />
          </label>
          {error && (
            <div className="login-error" role="alert">
              <ShieldAlert size={18} />
              <span>{error}</span>
            </div>
          )}
          <button className="airank-console-primary-button login-submit" type="submit" disabled={submitting}>
            {submitting ? "Signing in" : "Sign in"}
            <ArrowRight size={18} />
          </button>
        </form>
      </section>
    </main>
  );
}

function ActionToast({ toast, onDismiss }: { toast: ToastState; onDismiss: () => void }) {
  const Icon = toast.tone === "success" ? CheckCircle2 : toast.tone === "danger" ? ShieldAlert : Info;

  return (
    <div className="action-toast" data-tone={toast.tone} role="status">
      <Icon size={22} />
      <div>
        <strong>{toast.title}</strong>
        <span>{toast.desc}</span>
      </div>
      <button type="button" onClick={onDismiss} aria-label="关闭提示">
        关闭
      </button>
    </div>
  );
}

function ActionPanel({ panel, onClose }: { panel: ActionPanelState; onClose: () => void }) {
  const { recordAction } = useActionFeedback();

  const runPrimaryAction = () => {
    void recordAction({
      actionType: "panel.primary",
      label: panel.primaryLabel ?? panel.title,
      entityType: "console_panel",
      payload: { panel_title: panel.title, primary_label: panel.primaryLabel ?? null },
    });
    panel.onPrimary?.();
    onClose();
  };

  return (
    <div className="action-panel-backdrop" role="presentation" onClick={onClose}>
      <section className="action-panel" role="dialog" aria-modal="true" aria-label={panel.title} onClick={(event) => event.stopPropagation()}>
        <div className="action-panel-head">
          <h2>{panel.title}</h2>
          <button type="button" onClick={onClose} aria-label="关闭面板">
            关闭
          </button>
        </div>
        <p>{panel.desc}</p>
        {panel.items && (
          <ul>
            {panel.items.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        )}
        <div className="action-panel-actions">
          <button className="outline-button" type="button" onClick={onClose}>
            知道了
          </button>
          {panel.primaryLabel && (
            <button className="airank-console-primary-button" type="button" onClick={runPrimaryAction}>
              {panel.primaryLabel}
            </button>
          )}
        </div>
      </section>
    </div>
  );
}

function normalizePath(path: string) {
  if (path === "/" || path === "/console/") {
    return "/console";
  }
  return path.replace(/\/$/, "");
}

function Sidebar({
  activePath,
  onNavigate,
}: {
  activePath: string;
  onNavigate: (path: string) => void;
}) {
  const { project } = useConsoleOverview();
  const { openPanel } = useActionFeedback();

  return (
    <aside className="airank-console-sidebar">
      <div className="brand-lockup">
        <div className="brand-mark">
          <Sparkles size={25} />
        </div>
        <div>
          <div className="brand-title">{project.name}</div>
          <div className="brand-subtitle">AIRank 来客</div>
        </div>
      </div>

      <nav className="console-nav" aria-label="AIRank 控制台">
        {navRoutes.map((route) => {
          const Icon = iconMap[route.icon] ?? Home;
          const active = route.path === "/console" ? activePath === "/console" : activePath.startsWith(route.path);
          return (
            <button
              key={route.id}
              className="airank-console-nav-item"
              data-active={active}
              type="button"
              onClick={() => onNavigate(route.path)}
            >
              <Icon size={22} strokeWidth={2.2} />
              <span>{route.label}</span>
            </button>
          );
        })}
      </nav>

      <div className="sidebar-footer">
        <button
          className="help-link"
          type="button"
          onClick={() =>
            openPanel({
              title: "帮助中心",
              desc: "当前控制台按 AI 来客闭环组织：先体检，再确认事实和问题，补齐资产，最后发布复测并下载报告。",
              items: ["遇到数据异常时先刷新工作台", "发布前确认事实库和 AI 收录包", "报告页会记录每一次下载回执"],
            })
          }
        >
          <HelpCircle size={22} />
          <span>帮助中心</span>
        </button>
        <div className="tenant-switcher">
          <div className="tenant-avatar">
            <CircleUserRound size={23} />
          </div>
          <div>
            <div className="tenant-name">{project.name}</div>
            <div className="tenant-plan">企业版</div>
          </div>
          <ChevronDown size={18} />
        </div>
      </div>
    </aside>
  );
}

function ConsolePage({
  path,
  onNavigate,
  onBrandCheckComplete,
}: {
  path: string;
  onNavigate: (path: string) => void;
  onBrandCheckComplete: (result: BrandCheckResult) => void;
}) {
  if (path === "/console/checkup") return <CheckupPage onNavigate={onNavigate} />;
  if (path === "/console/facts") return <FactsPage />;
  if (path === "/console/questions") return <QuestionsPage onNavigate={onNavigate} />;
  if (path === "/console/gaps/questions") return <GapQuestionsPage onNavigate={onNavigate} />;
  if (path === "/console/gaps") return <GapsPage onNavigate={onNavigate} />;
  if (path === "/console/assets") return <AssetsPage onNavigate={onNavigate} />;
  if (path === "/console/publishing") return <PublishingPage onNavigate={onNavigate} />;
  if (path === "/console/assistant") return <AssistantPage />;
  if (path === "/console/reports") return <ReportsPage onNavigate={onNavigate} />;
  if (path === "/console/settings") return <SettingsPage />;
  return <DashboardPage onNavigate={onNavigate} onBrandCheckComplete={onBrandCheckComplete} />;
}

function PageHeader({
  title,
  subtitle,
  action,
}: {
  title: string;
  subtitle: string;
  action?: ReactNode;
}) {
  return (
    <header className="page-header">
      <div>
        <h1 className="airank-console-page-title">{title}</h1>
        <p className="page-subtitle">{subtitle}</p>
      </div>
      {action}
    </header>
  );
}

function HeaderActions({
  primary,
  icon: Icon,
  onPrimary,
}: {
  primary: string;
  icon: LucideIcon;
  onPrimary?: () => void;
}) {
  const { notify, openPanel, recordAction } = useActionFeedback();

  const shareCurrentPage = () => {
    const currentUrl = window.location.href;
    void recordAction({
      actionType: "share.link",
      label: "分享",
      entityType: "console_page",
      entityId: window.location.pathname,
      payload: { url: currentUrl },
    });
    void navigator.clipboard?.writeText(currentUrl).catch(() => undefined);
    notify({
      title: "分享链接已生成",
      desc: `当前页面链接已准备：${window.location.pathname}`,
      tone: "success",
    });
  };

  return (
    <div className="header-actions">
      <button
        className="date-pill"
        type="button"
        onClick={() =>
          openPanel({
            title: "使用指南",
            desc: "按当前页面的主任务继续推进，系统会保留体检、事实、问题、资产、发布和报告之间的上下文。",
            items: ["先确认事实与买家问题", "再补齐 AI 收录包", "发布后回到报表中心复测效果"],
          })
        }
      >
        <BookOpen size={17} />
        使用指南
      </button>
      <button className="date-pill" type="button" onClick={shareCurrentPage}>
        <Share2 size={17} />
        分享
      </button>
      <button className="airank-console-primary-button" type="button" onClick={onPrimary}>
        <Icon size={18} />
        {primary}
      </button>
    </div>
  );
}

function ProjectStrip() {
  const { project } = useConsoleOverview();

  return (
    <section className="project-strip">
      <StripItem icon={Globe2} label="官网" value={project.website} />
      <StripItem icon={Building2} label="行业" value={project.industry} />
      <StripItem icon={BriefcaseBusiness} label="竞品" value={project.competitors} />
      <StripItem icon={UsersRound} label="目标客户类型" value={project.audience} />
    </section>
  );
}

function StripItem({ icon: Icon, label, value }: { icon: LucideIcon; label: string; value: string }) {
  return (
    <div className="strip-item">
      <span className="strip-icon">
        <Icon size={22} />
      </span>
      <div>
        <span>{label}</span>
        <strong>{value}</strong>
      </div>
    </div>
  );
}

function MetricCard({ item }: { item: ConsoleMetricCard }) {
  const Icon = iconMap[item.icon] ?? Activity;
  return (
    <article className="airank-console-card metric-card" data-testid="stat-card">
      <IconTile tone={item.tone}>
        <Icon size={30} />
      </IconTile>
      <div className="metric-copy">
        <div className="metric-label">
          {item.label}
          <Info size={15} />
        </div>
        <div>
          <span className="airank-console-metric">{item.value}</span>
          {item.suffix && <span className="metric-suffix">{item.suffix}</span>}
        </div>
        <span className={`metric-delta ${item.tone === "warning" ? "danger-text" : "success-text"}`}>{item.delta}</span>
      </div>
    </article>
  );
}

function IconTile({ tone = "primary", children }: { tone?: Tone; children: ReactNode }) {
  return (
    <span className="airank-console-icon-tile" data-tone={tone}>
      {children}
    </span>
  );
}

function splitLines(value: string): string[] {
  return value
    .split(/[\n,，、]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function BrandCheckCard({
  onNavigate,
  onComplete,
}: {
  onNavigate: (path: string) => void;
  onComplete: (result: BrandCheckResult) => void;
}) {
  const { notify } = useActionFeedback();
  const [brandName, setBrandName] = useState("");
  const [websiteUrl, setWebsiteUrl] = useState("");
  const [industryHint, setIndustryHint] = useState("");
  const [competitorHints, setCompetitorHints] = useState("");
  const [buyerQuestions, setBuyerQuestions] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [lastResult, setLastResult] = useState<BrandCheckResult | null>(null);
  const [lastError, setLastError] = useState<string | null>(null);

  const submitBrandCheck = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSubmitting(true);
    setLastError(null);
    setLastResult(null);
    try {
      const result = await runBrandCheck({
        brandName: brandName.trim(),
        websiteUrl: websiteUrl.trim(),
        industryHint: industryHint.trim() || undefined,
        competitorHints: splitLines(competitorHints),
        buyerQuestions: splitLines(buyerQuestions),
      });
      setLastResult(result);
      onComplete(result);
      notify({
        title: "品牌检测已完成",
        desc: `${result.project.brand_name} 已处理 ${result.taskCount} 个检测任务；请在体检页核对有效、失败、阻塞和未提及样本。`,
        tone: "success",
      });
      onNavigate("/console/checkup");
    } catch (error) {
      const message = error instanceof Error ? error.message : "后端未能完成检测，请检查品牌和网址。";
      setLastError(message);
      notify({
        title: "品牌检测失败",
        desc: message,
        tone: "danger",
      });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <section className="airank-console-card brand-check-card" aria-label="品牌 AI 排名检测">
      <div className="brand-check-copy">
        <IconTile tone="primary">
          <SearchCheck size={27} />
        </IconTile>
        <div>
          <h2>输入品牌，立即检测 AI 平台排名</h2>
          <p>系统会创建项目、生成买家问题，并在当前已启用且通过健康门禁的 Provider 上采样；未通过的任务会明确记录为失败或阻塞。</p>
        </div>
      </div>
      <form className="brand-check-form" onSubmit={submitBrandCheck}>
        <label>
          <span>品牌名称</span>
          <input value={brandName} onChange={(event) => setBrandName(event.target.value)} placeholder="例如：中关村软件园孵化器" required />
        </label>
        <label>
          <span>官网或资料页</span>
          <input value={websiteUrl} onChange={(event) => setWebsiteUrl(event.target.value)} placeholder="https://example.com" required />
        </label>
        <label>
          <span>行业</span>
          <input value={industryHint} onChange={(event) => setIndustryHint(event.target.value)} placeholder="科技企业孵化 / 产业服务" />
        </label>
        <label>
          <span>竞品/对标方</span>
          <input value={competitorHints} onChange={(event) => setCompetitorHints(event.target.value)} placeholder="用顿号或逗号分隔，可留空" />
        </label>
        <label className="brand-check-wide">
          <span>核心买家问题</span>
          <input value={buyerQuestions} onChange={(event) => setBuyerQuestions(event.target.value)} placeholder="可留空，系统会自动生成 3 个高意向问题" />
        </label>
        <button className="airank-console-primary-button brand-check-submit" type="submit" disabled={submitting}>
          {submitting ? "检测中" : "开始 AI 排名检测"}
          <ArrowRight size={18} />
        </button>
      </form>
      {lastResult && (
        <div className="brand-check-result" role="status">
          <Badge tone="success">检测完成</Badge>
          <span>{lastResult.project.brand_name}</span>
          <strong>{lastResult.scanRun.status === "completed" ? "真实采样已完成" : "检测任务已创建"}</strong>
          <span>{lastResult.taskCount} 个任务</span>
        </div>
      )}
      {lastError && (
        <div className="brand-check-result" data-tone="danger" role="alert">
          <Badge tone="danger">检测失败</Badge>
          <strong>{lastError}</strong>
        </div>
      )}
    </section>
  );
}

function DashboardPage({
  onNavigate,
  onBrandCheckComplete,
}: {
  onNavigate: (path: string) => void;
  onBrandCheckComplete: (result: BrandCheckResult) => void;
}) {
  const overview = useConsoleOverview();
  const overviewStatus = useConsoleOverviewStatus();
  const hasEvidence = overview.dataStatus === "provider_evidence" && overview.metricCards.length > 0;

  return (
    <>
      <PageHeader
        title="工作台"
        subtitle="老板驾驶舱：只展示可下钻到真实样本、引用和事实来源的 GEO 指标。"
        action={<DatePill />}
      />
      {overviewStatus === "fallback" && (
        <AlertBanner
          title="控制台 API 暂不可用"
          desc="为避免把演示数字冒充真实结果，当前不展示本地业务指标；恢复 API 后刷新读取项目数据。"
          action="重新加载"
          onClick={() => window.location.reload()}
        />
      )}
      <BrandCheckCard onNavigate={onNavigate} onComplete={onBrandCheckComplete} />
      <section className="metric-grid">
        {overview.metricCards.map((item) => (
          <MetricCard key={item.label} item={item} />
        ))}
      </section>
      {!hasEvidence && (
        <AlertBanner
          title={overview.dataStatus === "collecting" ? "真实采样正在执行" : "尚无可验证的品牌指标"}
          desc={overview.message || "完成真实 Provider 采样后才会展示提及率、推荐率和排名；正常未提及回答仍计入有效分母。"}
          action="查看体检状态"
          onClick={() => onNavigate("/console/checkup")}
        />
      )}
      <section className="dashboard-grid">
        <div className="dashboard-main">
          <Panel title="证据状态">
            <DataStateCard
              title={hasEvidence ? "真实 Provider 证据已入库" : "等待真实样本"}
              desc={overview.message || "当前没有可展示的证据结论。"}
              tone={hasEvidence ? "success" : "warning"}
            />
          </Panel>
          <Panel title="指标口径">
            <div className="check-list">
              <CheckLine text="正常未提及样本" value="计入有效分母" checked />
              <CheckLine text="失败与阻塞样本" value="单独统计" checked />
              <CheckLine text="API / Web / App" value="分开标记" checked />
              <CheckLine text="原始回答与引用" value="可下钻追溯" checked />
            </div>
          </Panel>
        </div>
        <NextActionsRail onNavigate={onNavigate} blocked={!hasEvidence} />
      </section>
    </>
  );
}

function DatePill() {
  const { project } = useConsoleOverview();
  const { openPanel } = useActionFeedback();

  return (
    <button
      className="date-pill"
      type="button"
      onClick={() =>
        openPanel({
          title: "数据周期",
          desc: "当前工作台展示最近一次 AI 来客体检和复测后的汇总数据。",
          items: [`数据日期：${project.date}`, "下一版会接入后端周期筛选；当前版本点击可确认所见指标口径。"],
        })
      }
    >
      <CalendarDays size={18} />
      {project.date}
      <ChevronDown size={16} />
    </button>
  );
}

function Panel({ title, children, action }: { title: string; children: ReactNode; action?: ReactNode }) {
  return (
    <article className="airank-console-card panel">
      <div className="panel-head">
        <h2 className="airank-console-section-title">{title}</h2>
        {action}
      </div>
      {children}
    </article>
  );
}

function DataStateCard({ title, desc, tone }: { title: string; desc: string; tone: Tone }) {
  return (
    <div className="airank-console-card data-state-card" data-tone={tone} role={tone === "danger" ? "alert" : "status"}>
      <IconTile tone={tone}>
        {tone === "success" ? <CheckCircle2 size={22} /> : tone === "danger" ? <AlertTriangle size={22} /> : <Info size={22} />}
      </IconTile>
      <div>
        <strong>{title}</strong>
        <span>{desc}</span>
      </div>
    </div>
  );
}

function formatDateTime(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString("zh-CN", { hour12: false });
}

function NextActionsRail({ onNavigate, blocked = false }: { onNavigate: (path: string) => void; blocked?: boolean }) {
  return (
    <aside className="airank-console-card right-rail">
      <div className="rail-title">
        <Target size={24} />
        <h2>下一步建议</h2>
      </div>
      <p className="rail-subtitle">{blocked ? "先完成真实 Provider 门禁，再生成 GEO 结论" : "先补齐可审核证据，再通过复测观察变化"}</p>
      <div className="action-timeline">
        {(blocked ? blockedNextActions : evidenceNextActions).map((item, index) => (
          <article className="action-card" key={item.title}>
            <span className="action-index">{index + 1}</span>
            <div>
              <div className="action-head">
                <h3>{item.title}</h3>
                <span>{item.level}</span>
              </div>
              <p>{item.desc}</p>
              <button
                className="outline-button"
                type="button"
                onClick={() => onNavigate(blocked ? (index === 2 ? "/console/settings" : "/console/checkup") : index === 0 ? "/console/facts" : index === 1 ? "/console/assets" : "/console/publishing")}
              >
                {item.cta}
              </button>
            </div>
          </article>
        ))}
      </div>
      <button className="airank-console-primary-button rail-cta" type="button" onClick={() => onNavigate(blocked ? "/console/checkup" : "/console/assets")}>
        {blocked ? "查看阻断状态" : "继续下一步"}
        <ArrowRight size={18} />
      </button>
      <span className="rail-caption">{blocked ? "上线前必须让计划使用的采集器通过真实门禁" : "按证据、审核、发布、复测顺序推进"}</span>
    </aside>
  );
}

function CheckupPage({ onNavigate }: { onNavigate: (path: string) => void }) {
  const overview = useConsoleOverview();
  const [readiness, setReadiness] = useState<ProviderReadiness | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    fetchProviderReadiness(controller.signal)
      .then((data) => {
        setReadiness(data);
        setLoadError(null);
      })
      .catch((error) => setLoadError(error instanceof Error ? error.message : "Provider 健康接口不可用"));
    return () => controller.abort();
  }, []);

  return (
    <>
      <PageHeader
        title="AI 收录体检"
        subtitle="分别查看真实 Provider 健康状态和已入库采样指标；无证据时不生成品牌结论。"
        action={<span className="step-counter">02 / 09</span>}
      />
      <ProcessSteps
        steps={[
          ["客户问题采样", "基于目标客户使用场景采样高价值问题"],
          ["多 AI 平台检测", "在主流 AI 平台检测品牌可见度"],
          ["引用来源分析", "分析 AI 引用来源与内容权威性"],
          ["竞品压制分析", "对比竞品表现并识别压制点"],
        ]}
      />
      <ProjectStrip />
      <section className="provider-grid">
        {(readiness?.providers ?? []).map((item) => (
          <article className="airank-console-card provider-card" data-testid="provider-card" key={item.provider}>
            <div className="provider-avatar">{item.label.slice(0, 1)}</div>
            <h3>{item.label}</h3>
            <div className="provider-metrics">
              <Badge tone={item.status === "ready" ? "success" : "danger"}>{item.status}</Badge>
              <span>采集模式<strong>{readiness?.mode ?? "unknown"}</strong></span>
              <span>状态说明<strong>{item.reason || item.blocker_code || "探测通过"}</strong></span>
            </div>
          </article>
        ))}
      </section>
      {loadError && <DataStateCard title="Provider 健康接口不可用" desc={loadError} tone="danger" />}
      {!readiness && !loadError && <DataStateCard title="正在读取 Provider 状态" desc="等待真实探测结果。" tone="primary" />}
      <section className="metric-grid">
        {overview.metricCards.map((item) => <MetricCard key={item.label} item={item} />)}
      </section>
      <AlertBanner
        title={overview.dataStatus === "provider_evidence" ? "指标来自真实样本" : "当前没有可验证的诊断结论"}
        desc={overview.message || "完成真实采样后才能生成诊断和客户报告。"}
        action={overview.dataStatus === "provider_evidence" ? "查看客户报告" : "返回重新检测"}
        onClick={() => onNavigate(overview.dataStatus === "provider_evidence" ? "/console/reports" : "/console")}
      />
    </>
  );
}

function FactsPage() {
  const { project } = useConsoleOverview();
  const { openPanel } = useActionFeedback();
  const [facts, setFacts] = useState<FactRevision[]>([]);
  const [sources, setSources] = useState<KnowledgeSource[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    if (!project.id) return;
    const controller = new AbortController();
    Promise.all([
      fetchFacts(project.id, controller.signal),
      fetchKnowledgeSources(project.id, controller.signal),
    ])
      .then(([nextFacts, nextSources]) => {
        setFacts(nextFacts);
        setSources(nextSources);
        setLoadError(null);
      })
      .catch((error) => setLoadError(error instanceof Error ? error.message : "事实库接口不可用"));
    return () => controller.abort();
  }, [project.id]);

  const approved = facts.filter((item) => item.status === "approved").length;
  const pending = facts.filter((item) => item.status === "proposed").length;
  const eligible = facts.filter((item) => item.eligible_for_generation).length;

  return (
    <>
      <PageHeader
        title="企业事实库"
        subtitle="AI 认识你的前提，是企业事实足够清晰、可信、可公开。"
        action={
          <button
            className="airank-console-primary-button"
            type="button"
            onClick={() =>
              openPanel({
                title: "事实审核门禁",
                desc: "当前页面只展示真实 FactRevision。审核必须逐条绑定来源、风险、公开范围和有效期，尚未提供虚假的批量确认。",
                items: ["缺少来源不能批准", "开放冲突会阻断", "过期事实不能生成公开内容"],
              })
            }
          >
            查看审核规则
          </button>
        }
      />
      <section className="summary-band">
        <SummaryMetric label="知识来源" value={String(sources.length)} tone="primary" />
        <SummaryMetric label="已审核事实" value={String(approved)} tone="success" />
        <SummaryMetric label="待审核事实" value={String(pending)} tone="warning" />
        <div className="summary-chart">
          <DonutChart values={[eligible, Math.max(facts.length - eligible, 0)]} colors={["#01c8b1", "#edf0f7"]} center={String(facts.length)} label="事实修订" />
        </div>
      </section>
      {loadError && <DataStateCard title="事实库读取失败" desc={loadError} tone="danger" />}
      {!loadError && facts.length === 0 && <DataStateCard title="尚无事实修订" desc="先导入企业官方资料，再逐条审核事实；没有事实时不会生成公开内容。" tone="warning" />}
      <section className="fact-grid">
        {facts.map((item) => (
          <article className="airank-console-card fact-card" key={item.revision_id}>
            <div className="fact-card-head">
              <IconTile tone={item.status === "approved" ? "success" : item.status === "rejected" ? "danger" : "warning"}><NotebookTabs size={23} /></IconTile>
              <div>
                <h3>{item.title}</h3>
                <p>{item.fact_text}</p>
              </div>
              <Badge tone={item.status === "approved" ? "success" : item.status === "rejected" ? "danger" : "warning"}>{item.status}</Badge>
              <ChevronRight size={22} />
            </div>
            <dl className="fact-meta">
              <div><dt>版本</dt><dd>v{item.revision_number}</dd></div>
              <div><dt>来源</dt><dd>{item.source_ids.length}</dd></div>
              <div><dt>创建时间</dt><dd>{formatDateTime(item.created_at)}</dd></div>
            </dl>
            <div className="fact-tags">
              <Badge tone={item.disclosure === "public" ? "success" : "warning"}>{item.disclosure}</Badge>
              <Badge tone={item.eligible_for_generation ? "success" : "muted"}>{item.eligible_for_generation ? "可用于内容" : item.eligibility_reason}</Badge>
              <Badge tone={item.risk_level === "high" || item.risk_level === "restricted" ? "danger" : "primary"}>风险 {item.risk_level}</Badge>
            </div>
          </article>
        ))}
      </section>
      <Panel title="知识来源">
        {sources.length === 0 ? (
          <DataStateCard title="尚无来源" desc="事实必须能回到不可变原文和精确边界。" tone="warning" />
        ) : (
          <div className="gap-table">
            {sources.map((source) => (
              <div className="gap-row" key={source.source_id}>
                <IconTile tone={source.status === "active" ? "success" : "warning"}><Link2 size={21} /></IconTile>
                <div><strong>{source.title}</strong><span>{source.source_type} · {source.authority_level}</span></div>
                <Badge tone={source.status === "active" ? "success" : "warning"}>{source.status}</Badge>
                <strong>{source.segment_count} 段</strong>
                <span>hash {source.content_sha256.slice(0, 12)}…</span>
                <Badge tone="primary">v{source.revision_number}</Badge>
              </div>
            ))}
          </div>
        )}
      </Panel>
      <div className="bottom-guide">
        <ShieldCheck size={24} />
        <div>
          <strong>为什么需要确认企业事实？</strong>
          <span>AI 基于可信事实生成内容与回答，事实不清晰或未公开可能导致推荐偏差、信息缺失、信任下降。</span>
        </div>
        <button
          className="outline-button"
          type="button"
          onClick={() =>
            openPanel({
              title: "事实库使用指南",
              desc: "事实库只保存可被 AI 引用的公开可信信息。进入发布前，请优先确认企业简介、核心服务、案例和联系方式。",
              items: ["确认后的事实可用于 AI 收录包", "敏感事实保持内部或脱敏状态", "缺少来源的事实不会进入公开内容"],
            })
          }
        >
          查看使用指南
        </button>
      </div>
    </>
  );
}

function QuestionsPage({ onNavigate }: { onNavigate: (path: string) => void }) {
  return (
    <>
      <PageHeader
        title="买家问题地图"
        subtitle="真正带来客户的，不是泛流量关键词，而是高意向买家问题。"
        action={<HeaderActions primary="生成推荐缺口分析" icon={Target} onPrimary={() => onNavigate("/console/gaps")} />}
      />
      <section className="opportunity-intro-card">
        <h2>AI 来客机会地图 <Badge tone="primary">问题库升级为来客机会地图</Badge></h2>
        <p>这里只展示项目中真实保存的买家问题及其来源、意图、阶段、目标平台和覆盖状态，不用样例问题补位。</p>
        <ProjectStrip />
      </section>
      <QuestionTable showTabs onNavigate={onNavigate} />
    </>
  );
}

function GapQuestionsPage({ onNavigate }: { onNavigate: (path: string) => void }) {
  return (
    <>
      <PageHeader
        title="推荐缺口分析"
        subtitle="只展示由真实问题、回答样本和覆盖状态支持的缺口；未采样问题明确标记 needs_scan。"
        action={<HeaderActions primary="生成 AI 收录包" icon={PackageCheck} onPrimary={() => onNavigate("/console/assets")} />}
      />
      <ProjectStrip />
      <QuestionTable showTabs={false} onNavigate={onNavigate} />
    </>
  );
}

function QuestionTable({ showTabs, onNavigate }: { showTabs: boolean; onNavigate: (path: string) => void }) {
  const { project } = useConsoleOverview();
  const { openPanel, recordAction } = useActionFeedback();
  const [questions, setQuestions] = useState<BuyerQuestion[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const tabs = ["全部问题", "购买", "对比", "选型", "信任", "价格", "风险", "场景", "本地", "替代"];
  const tabTypes = ["", "purchase", "compare", "select", "trust", "price", "risk", "scenario", "local", "alternative"];
  const [selectedTab, setSelectedTab] = useState(0);

  useEffect(() => {
    if (!project.id) return;
    const controller = new AbortController();
    fetchBuyerQuestions(project.id, controller.signal)
      .then((data) => {
        setQuestions(data);
        setLoadError(null);
      })
      .catch((error) => setLoadError(error instanceof Error ? error.message : "买家问题接口不可用"));
    return () => controller.abort();
  }, [project.id]);

  const visibleRows = showTabs && selectedTab > 0
    ? questions.filter((row) => row.question_type === tabTypes[selectedTab])
    : questions;
  const gapRows = questions.filter((row) => row.coverage_status === "gap" || row.coverage_status === "needs_scan");

  return (
    <section className="content-with-rail">
      <div>
        {showTabs && (
          <div className="tab-row">
            {tabs.map((item, index) => (
              <button
                className="tab-button"
                data-active={index === selectedTab}
                type="button"
                key={item}
                onClick={() => {
                  void recordAction({
                    actionType: "question.tab_select",
                    label: item,
                    entityType: "buyer_question_tab",
                    entityId: String(index),
                    payload: { previous_tab: tabs[selectedTab], next_tab: item },
                  });
                  setSelectedTab(index);
                }}
              >
                {item}
              </button>
            ))}
          </div>
        )}
        {loadError && <DataStateCard title="问题地图读取失败" desc={loadError} tone="danger" />}
        {!loadError && questions.length === 0 && <DataStateCard title="尚无买家问题" desc="创建品牌项目后生成或录入真实买家问题；系统不会用样例问题补位。" tone="warning" />}
        <div className="airank-console-card table-card">
          <table className="question-table">
            <thead>
              <tr>
                <th>问题</th>
                <th>商业意图</th>
                <th>买家阶段</th>
                <th>覆盖状态</th>
                <th>目标平台</th>
                <th>来源</th>
              </tr>
            </thead>
            <tbody>
              {visibleRows.map((row) => (
                <tr key={row.question_id}>
                  <td>
                    <strong>{row.question_text}</strong>
                    <Badge tone={row.intent_level === "high" ? "primary" : row.intent_level === "medium" ? "warning" : "muted"}>{row.question_type}</Badge>
                  </td>
                  <td><span className={`intent ${row.intent_level === "high" ? "high" : "mid"}`}>{row.intent_level}</span></td>
                  <td><strong>{row.buyer_stage}</strong></td>
                  <td><Badge tone={row.coverage_status === "covered" ? "success" : row.coverage_status === "gap" ? "danger" : "warning"}>{row.coverage_status}</Badge></td>
                  <td>{row.recommended_providers.join("、") || "待配置"}</td>
                  <td>{row.source}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="table-footer">
            <span>{showTabs ? `${tabs[selectedTab]}：${visibleRows.length} 条 / 共 ${questions.length} 条问题` : `共 ${questions.length} 条问题`}</span>
          </div>
        </div>
      </div>
      <aside className="rail-stack">
        <Panel title="问题证据状态">
          <div className="check-list">
            <CheckLine text="问题总数" value={String(questions.length)} checked={questions.length > 0} />
            <CheckLine text="待采样/缺口" value={String(gapRows.length)} checked={gapRows.length === 0 && questions.length > 0} />
            <CheckLine text="已覆盖" value={String(questions.filter((row) => row.coverage_status === "covered").length)} checked />
          </div>
        </Panel>
        <Panel title="待处理问题">
          <ol className="top-list">
            {gapRows.slice(0, 5).map((row, index) => (
              <li key={row.question_id}><span>{index + 1}</span>{row.question_text}<strong>{row.coverage_status}</strong></li>
            ))}
          </ol>
          <button
            className="ghost-button"
            type="button"
            onClick={() =>
              showTabs
                ? onNavigate("/console/gaps/questions")
                : openPanel({
                    title: "推荐缺口处理说明",
                    desc: "当前只展示数据库中真实存在且标记为 gap/needs_scan 的问题，不补造 Top50 或推荐差距。",
                    items: ["优先处理高意图问题", "补齐可审核事实与内容证据", "发布后按同口径复测"],
                  })
            }
          >
            {showTabs ? "查看缺口问题" : "查看处理说明"}
          </button>
        </Panel>
      </aside>
    </section>
  );
}

function GapsPage({ onNavigate }: { onNavigate: (path: string) => void }) {
  return (
    <>
      <PageHeader title="推荐缺口分析" subtitle="AI 不推荐你，不一定是你不强，而是 AI 找不到足够可信、结构化、可引用的证据。" action={<span className="step-counter">05 / 09</span>} />
      <div className="danger-hero">
        <AlertTriangle size={54} />
        <div>
          <strong>AI 不推荐你，不一定是你不强，而是 AI 找不到足够可信、结构化、可引用的证据。</strong>
          <span>可信、结构化、可引用的证据是可干预要素，但发布后是否变化必须通过同口径复测观察。</span>
        </div>
      </div>
      <Panel title="缺口判定规则">
        <div className="check-list">
          <CheckLine text="问题缺口" value="来自真实 BuyerQuestion.coverage_status" checked />
          <CheckLine text="内容缺口" value="必须关联事实与 ClaimSupport" checked />
          <CheckLine text="技术页面分" value="不等同品牌推荐率" checked />
          <CheckLine text="干预效果" value="发布后同口径复测" checked />
        </div>
      </Panel>
      <QuestionTable showTabs={false} onNavigate={onNavigate} />
      <div className="bottom-action-band">
        <Target size={42} />
        <div>
          <strong>只根据已验证缺口采取行动</strong>
          <span>没有真实样本、引用或事实支持时，系统不会生成竞品压制数字。</span>
        </div>
        <button className="airank-console-primary-button" type="button" onClick={() => onNavigate("/console/assets")}>
          <PackageCheck size={20} />生成 AI 收录包
        </button>
      </div>
    </>
  );
}

function AssetsPage({ onNavigate }: { onNavigate: (path: string) => void }) {
  const { project } = useConsoleOverview();
  const { openPanel } = useActionFeedback();
  const [bundle, setBundle] = useState<AssetBundle>(fallbackAssetBundle);

  useEffect(() => {
    if (!project.id) {
      setBundle(fallbackAssetBundle);
      return;
    }
    const controller = new AbortController();
    fetchAssetBundle(project.id, controller.signal)
      .then(setBundle)
      .catch(() => setBundle(fallbackAssetBundle));
    return () => controller.abort();
  }, [project.id]);

  return (
    <>
      <PageHeader
        title="AI 收录包"
        subtitle="这些不是普通文章，而是 AI 能抓取、理解、引用的企业证据链。"
        action={<HeaderActions primary="发布 AI 收录包" icon={Rocket} onPrimary={() => onNavigate("/console/publishing")} />}
      />
      <section className="asset-grid reference-asset-grid">
        {bundle.assets.map((item, index) => (
          <article className="airank-console-card asset-card reference-asset-card" data-testid="asset-card" key={item.title}>
            <div className="asset-card-head">
              <IconTile tone={index % 3 === 0 ? "primary" : index % 3 === 1 ? "success" : "warning"}>
                {(() => {
                  const AssetIcon = assetCardIcons[index] ?? FileText;
                  return <AssetIcon size={25} />;
                })()}
              </IconTile>
              <Badge tone={item.status.includes("缺") ? "danger" : item.status.includes("待") ? "warning" : "success"}>{item.status}</Badge>
            </div>
            <h3>{item.title}</h3>
            <p>{item.desc}</p>
            <div className="asset-footer">
              <button
                className="outline-button"
                type="button"
                onClick={() =>
                  openPanel({
                    title: item.title,
                    desc: item.desc,
                    items: [`完整度 ${item.progress}%`, `当前状态：${item.status}`, "可继续补齐证据、来源和结构化字段后再发布复测。"],
                    primaryLabel: "去发布中心",
                    onPrimary: () => onNavigate("/console/publishing"),
                  })
                }
              >
                <Eye size={16} />
                预览
              </button>
            </div>
          </article>
        ))}
      </section>
      {bundle.assets.length === 0 ? (
        <DataStateCard title="尚无证据绑定内容资产" desc={bundle.recommendation || "只有通过事实审核并建立 ClaimSupport 后，才能生成内容资产。"} tone="warning" />
      ) : (
        <div className="package-footer reference-package-footer">
          <DonutChart values={[bundle.completeness, Math.max(100 - bundle.completeness, 0)]} colors={["#443efd", "#edf0f7"]} center={`${bundle.completeness}%`} label="后端计算" />
          <div>
            <strong>收录包状态</strong>
            <span>{bundle.recommendation}</span>
          </div>
          <div className="package-next">
            <strong>下一步：审核与发布</strong>
            <span>发布前必须通过事实覆盖、风险扫描和内容 hash 审核。</span>
            <button className="airank-console-primary-button" type="button" onClick={() => onNavigate("/console/publishing")}>
              <Send size={18} />
              发布提交
            </button>
          </div>
        </div>
      )}
    </>
  );
}

function PublishingPage({ onNavigate }: { onNavigate: (path: string) => void }) {
  const { project } = useConsoleOverview();
  const { notify, openPanel } = useActionFeedback();
  const [packages, setPackages] = useState<PublishPackage[]>([]);
  const [windows, setWindows] = useState<RetestWindow[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    if (!project.id) return;
    const controller = new AbortController();
    Promise.all([
      fetchPublishPackages(project.id, controller.signal),
      fetchRetestWindows(project.id, controller.signal),
    ])
      .then(([nextPackages, nextWindows]) => {
        setPackages(nextPackages);
        setWindows(nextWindows);
        setLoadError(null);
      })
      .catch((error) => setLoadError(error instanceof Error ? error.message : "发布中心接口不可用"));
    return () => controller.abort();
  }, [project.id]);

  return (
    <>
      <PageHeader
        title="发布提交中心"
        subtitle="保存审核后的不可变发布快照、Worker 执行回执、真实发布证据与复测窗口；未拿到外部回执的渠道保持 partial。"
        action={<HeaderActions primary="开始复测" icon={Play} onPrimary={() => onNavigate("/console/reports")} />}
      />
      <ProcessSteps
        className="publishing-flow"
        steps={publishingSteps}
      />
      <section className="metric-grid publishing-stats">
        <MiniStat label="发布包" value={String(packages.length)} icon={CloudUpload} />
        <MiniStat label="已发布" value={String(packages.filter((item) => item.status === "published").length)} icon={BadgeCheck} />
        <MiniStat label="待处理/失败" value={String(packages.filter((item) => ["queued", "publishing", "failed"].includes(item.status)).length)} icon={SearchCheck} />
        <MiniStat label="复测窗口" value={String(windows.length)} icon={RotateCw} />
      </section>
      {loadError && <DataStateCard title="发布中心读取失败" desc={loadError} tone="danger" />}
      {!loadError && packages.length === 0 && <DataStateCard title="尚无发布包" desc="内容必须通过事实核验和风险审核后，才能生成不可变发布快照。" tone="warning" />}
      <Panel title="不可变发布包">
        <table className="question-table publish-table">
          <thead>
            <tr><th>发布包</th><th>渠道</th><th>状态</th><th>实现等级</th><th>内容哈希</th><th>创建时间</th><th>操作</th></tr>
          </thead>
          <tbody>
            {packages.map((item) => (
              <tr key={item.package_id}>
                <td><strong>{item.package_id}</strong></td>
                <td>{item.channel}</td>
                <td><Badge tone={["published", "delivered"].includes(item.status) ? "success" : item.status === "failed" ? "danger" : item.status === "queued" ? "warning" : "primary"}>{item.status}</Badge></td>
                <td><Badge tone={item.implementation_status === "ready" ? "success" : "warning"}>{item.implementation_status}</Badge></td>
                <td>{item.content_sha256.slice(0, 12)}…</td>
                <td>{formatDateTime(item.created_at)}</td>
                <td>
                  <button
                    className="table-action"
                    type="button"
                    onClick={async () => {
                      try {
                        const attempts = await fetchPublishAttempts(item.package_id);
                        const latest = attempts[attempts.length - 1];
                        openPanel({
                          title: item.package_id,
                          desc: "发布包与内容审核、不可变快照、Worker attempt 和复测窗口关联。",
                          items: [
                            `发布渠道：${item.channel}`,
                            `状态：${item.status}`,
                            `快照：${item.snapshot_id}`,
                            `发布 URL：${item.published_url || "尚未登记"}`,
                            `执行次数：${attempts.length}`,
                            `最近执行：${latest ? `${latest.status}${latest.error_code ? ` / ${latest.error_code}` : ""}` : "尚未执行"}`,
                          ],
                          primaryLabel: "查看复测报告",
                          onPrimary: () => onNavigate("/console/reports"),
                        });
                      } catch (error) {
                        notify({
                          title: "发布执行记录读取失败",
                          desc: error instanceof Error ? error.message : "请稍后重试。",
                          tone: "danger",
                        });
                      }
                    }}
                  >
                    查看
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>
      <Panel title="T0 / T+7 / T+14 / T+30 复测窗口">
        {windows.length === 0 ? (
          <DataStateCard title="尚未进入复测" desc="登记真实发布 URL 并绑定已完成的 T0 基线后，系统才会创建观察窗口。" tone="warning" />
        ) : (
          <div className="gap-table">
            {windows.map((window) => (
              <div className="gap-row" key={window.window_id}>
                <IconTile tone={window.status === "completed" ? "success" : window.status === "failed" ? "danger" : "primary"}><RotateCw size={21} /></IconTile>
                <div><strong>{window.window_label}</strong><span>{window.window_id}</span></div>
                <Badge tone={window.status === "completed" ? "success" : window.status === "failed" ? "danger" : "warning"}>{window.status}</Badge>
                <strong>{formatDateTime(window.due_at)}</strong>
                <span>基线 {window.baseline_run_id || "未绑定"}</span>
                <Badge tone={window.compare_run_id ? "success" : "muted"}>{window.compare_run_id || "待复测"}</Badge>
              </div>
            ))}
          </div>
        )}
      </Panel>
    </>
  );
}

function AssistantPage() {
  return (
    <>
      <PageHeader
        title="AI 销售助手"
        subtitle="该能力尚未接入事实检索、对话审计和真实线索系统，当前明确标记为 disabled。"
        action={<Badge tone="muted">disabled</Badge>}
      />
      <DataStateCard
        title="未提供真实对话与线索数据"
        desc="完成事实检索、敏感信息策略、人工转接、会话证据和 CRM 写回门禁前，本页面不会生成示例回复、会话量、留资率或满意度。"
        tone="warning"
      />
      <Panel title="启用前置条件">
        <div className="check-list">
          <CheckLine text="只检索已审核事实" value="待接入" />
          <CheckLine text="敏感与缺证回答阻断" value="待接入" />
          <CheckLine text="会话与线索证据审计" value="待接入" />
          <CheckLine text="真实 CRM 写回" value="待接入" />
        </div>
      </Panel>
    </>
  );
}

function ReportsPage({ onNavigate }: { onNavigate: (path: string) => void }) {
  const { project } = useConsoleOverview();
  const { notify, recordAction } = useActionFeedback();
  const [reports, setReports] = useState<ReportList>(fallbackReportList);
  const [downloadingReportId, setDownloadingReportId] = useState<string | null>(null);

  useEffect(() => {
    if (!project.id) {
      setReports(fallbackReportList);
      return;
    }
    const controller = new AbortController();
    fetchReports(project.id, controller.signal)
      .then(setReports)
      .catch(() => setReports(fallbackReportList));
    return () => controller.abort();
  }, [project.id]);

  const generateReport = () => {
    void recordAction({
      actionType: "report.generate",
      label: "生成老板报告",
      entityType: "report",
      entityId: "executive_report",
      payload: { report_count: reports.reports.length },
    });
    notify({
      title: "报告生成尚未开放",
      desc: "只有完成同口径复测后，后端才会生成带证据索引与内容哈希的报告；本页面不会伪造任务成功。",
      tone: "warning",
    });
  };

  const downloadReport = async (report: ReportItem) => {
    const reportId = report.report_id ?? report.title;
    setDownloadingReportId(reportId);
    try {
      await recordDownloadReceipt(reportId);
      notify({ title: "下载回执已记录", desc: `${report.title} 的下载审计已写入 API。`, tone: "success" });
    } catch (error) {
      notify({
        title: "下载回执记录失败",
        desc: error instanceof Error ? error.message : "请稍后重试。",
        tone: "danger",
      });
    } finally {
      setDownloadingReportId(null);
    }
  };

  return (
    <>
      <PageHeader
        title="报表中心"
        subtitle="复测 AI 回答变化，只汇报可追溯的观察结果、证据索引和归因置信度。"
        action={<HeaderActions primary="生成老板报告" icon={FileChartColumn} onPrimary={generateReport} />}
      />
      {reports.reports.length === 0 && (
        <DataStateCard title="尚无客户报告" desc="报告必须来自真实扫描或同口径复测；没有证据时不会显示趋势、增长或关键结论。" tone="warning" />
      )}
      <section className="report-card-grid">
        {reports.reports.map((item, index) => {
          const ReportIcon = reportCardIcons[index] ?? FileChartColumn;
          return (
          <article className="airank-console-card report-card" data-testid="report-card" key={item.title}>
            <IconTile tone={index === 1 ? "success" : index === 2 ? "warning" : "primary"}>
              <ReportIcon size={23} />
            </IconTile>
            <div>
              <h3>{item.title}</h3>
              <p>{item.desc}</p>
              <span>{item.date}</span>
            </div>
            <button
              className="outline-button"
              type="button"
              disabled={downloadingReportId === (item.report_id ?? item.title)}
              onClick={() => void downloadReport(item)}
            >
              {downloadingReportId === (item.report_id ?? item.title) ? (
                "记录中"
              ) : (
                <>
                  {item.status.includes("下载") ? <Download size={15} /> : <FileChartColumn size={15} />}
                  {item.status}
                </>
              )}
            </button>
          </article>
          );
        })}
      </section>
    </>
  );
}

function SettingsPage() {
  const overview = useConsoleOverview();
  const { project } = overview;
  const { openPanel } = useActionFeedback();
  const [readiness, setReadiness] = useState<ProviderReadiness | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    fetchProviderReadiness(controller.signal).then(setReadiness).catch(() => setReadiness(null));
    return () => controller.abort();
  }, []);

  return (
    <>
      <PageHeader
        title="设置中心"
        subtitle="展示后端返回的项目、Provider 与能力状态；未接入保存 API 的配置不伪装成已保存。"
        action={<Badge tone="primary">read-only</Badge>}
      />
      <section className="settings-grid">
        <SettingsSection
          title="项目设置"
          icon={Settings}
          onAction={() =>
            openPanel({
              title: "编辑项目设置",
              desc: "当前仓库没有项目设置更新 API，因此本页面保持只读，不记录虚假的保存成功。",
              items: [`项目：${project.name || "尚未创建"}`, `行业：${project.industry || "尚未填写"}`, `官网：${project.website || "尚未填写"}`],
            })
          }
          rows={[["项目名称", project.name || "尚未创建"], ["项目 ID", project.id || "无"], ["行业", project.industry || "尚未填写"], ["官网", project.website || "尚未填写"], ["数据状态", overview.dataStatus]]}
        />
        <SettingsSection
          title="品牌信息"
          icon={BadgeCheck}
          onAction={() =>
            openPanel({
              title: "编辑品牌信息",
              desc: "品牌档案更新 API 尚未开放；当前只展示项目真实字段。",
              items: ["品牌、公司和产品别名应分别保存", "公开内容只能使用已审核事实", "联系方式必须来自官方来源"],
            })
          }
          rows={[["品牌名称", project.name || "尚未创建"], ["行业", project.industry || "尚未填写"], ["竞品", project.competitors || "尚未填写"], ["目标客户", project.audience || "尚未填写"]]}
        />
        <SettingsSection
          title="Provider 健康"
          icon={Bot}
          onAction={() =>
            openPanel({
              title: "Provider 健康说明",
              desc: "ready 只表示当前探测层通过，不等同四平台重复采样、报告和商业上线门禁全部完成。",
              items: ["L1 网络", "L2 鉴权与模型", "L3 真实生成", "API/Web/App 分开标记"],
            })
          }
          rows={(readiness?.providers ?? []).map((item) => [item.label, `${item.status}${item.reason ? ` · ${item.reason}` : ""}`] as [string, string])}
        />
        <SettingsSection
          title="能力状态"
          icon={ShieldCheck}
          onAction={() =>
            openPanel({
              title: "能力状态枚举",
              desc: "所有未覆盖能力必须显示 ready、partial、blocked、disabled 或 dev_only，不能包装成完成。",
              items: ["外部 Publisher 仍为 partial", "AI 销售助手为 disabled", "商业上线仍为 no-go"],
            })
          }
          rows={[["事实与证据", "partial"], ["导出发布包", "ready"], ["WordPress / HTTP", "partial"], ["AI 销售助手", "disabled"], ["商业上线", "blocked"]]}
        />
      </section>
    </>
  );
}

function SettingsSection({
  title,
  icon: Icon,
  rows,
  actionLabel = "编辑",
  onAction,
}: {
  title: string;
  icon: LucideIcon;
  rows: [string, string][];
  actionLabel?: string;
  onAction: () => void;
}) {
  return (
    <article className="airank-console-card settings-section">
      <div className="settings-head">
        <IconTile><Icon size={22} /></IconTile>
        <div>
          <h2>{title}</h2>
          <span>{title === "项目设置" ? "管理项目的基本信息与业务属性" : title === "成员与权限" ? "管理团队成员与角色权限" : "管理" + title + "配置"}</span>
        </div>
        <button className="settings-edit" type="button" onClick={onAction}>{actionLabel}</button>
      </div>
      {rows.map(([label, value]) => (
        <div className="settings-row" key={label}>
          <span>{label}</span>
          <strong>{value}</strong>
        </div>
      ))}
    </article>
  );
}

function ProcessSteps({ steps, className = "" }: { steps: [string, string][]; className?: string }) {
  return (
    <section className={`process-steps ${className}`}>
      {steps.map(([title, desc], index) => (
        <article className="step-card" data-testid="checkup-stage" key={title}>
          <IconTile tone={index === 2 ? "success" : index === 3 ? "warning" : "primary"}>
            <span>{index + 1}</span>
          </IconTile>
          <div>
            <h3>{title}</h3>
            <p>{desc}</p>
          </div>
        </article>
      ))}
    </section>
  );
}

function AlertBanner({ title, desc, action, onClick }: { title: string; desc: string; action: string; onClick: () => void }) {
  return (
    <div className="alert-banner">
      <AlertTriangle size={48} />
      <div>
        <strong>{title}</strong>
        <span>{desc}</span>
      </div>
      <button className="airank-console-primary-button" type="button" onClick={onClick}>{action}</button>
    </div>
  );
}

function MiniStat({ label, value, icon: Icon }: { label: string; value: string; icon: LucideIcon }) {
  return (
    <article className="airank-console-card mini-stat">
      <IconTile><Icon size={24} /></IconTile>
      <div>
        <span>{label}</span>
        <strong>{value}</strong>
      </div>
    </article>
  );
}

function SummaryMetric({ label, value, tone }: { label: string; value: string; tone: Tone }) {
  return (
    <div className="summary-metric">
      <span>{label}</span>
      <strong>{value}</strong>
      <Badge tone={tone}>实时数据</Badge>
    </div>
  );
}

function Badge({ tone, children }: { tone: Tone; children: ReactNode }) {
  return <span className="airank-console-badge" data-tone={tone}>{children}</span>;
}

function CheckLine({ text, value, checked = false }: { text: string; value: string; checked?: boolean }) {
  return (
    <div className="check-line">
      {checked ? <CheckCircle2 size={18} /> : <span className="empty-dot" />}
      <span>{text}</span>
      <strong>{value}</strong>
    </div>
  );
}

function DonutChart({ values, colors, center, label }: { values: number[]; colors: string[]; center: string; label: string }) {
  const radius = 42;
  const circumference = 2 * Math.PI * radius;
  let offset = 0;
  const total = Math.max(values.reduce((sum, value) => sum + value, 0), 1);
  return (
    <svg className="donut-chart" viewBox="0 0 120 120" role="img" aria-label={label}>
      <circle cx="60" cy="60" r={radius} fill="none" stroke="#edf0f7" strokeWidth="14" />
      {values.map((value, index) => {
        const dash = (value / total) * circumference;
        const segment = (
          <circle
            key={`${value}-${index}`}
            cx="60"
            cy="60"
            r={radius}
            fill="none"
            stroke={colors[index]}
            strokeWidth="14"
            strokeLinecap="round"
            strokeDasharray={`${dash} ${circumference - dash}`}
            strokeDashoffset={-offset}
            transform="rotate(-90 60 60)"
          />
        );
        offset += dash;
        return segment;
      })}
      <text x="60" y="57" textAnchor="middle" className="donut-center">{center}</text>
      <text x="60" y="75" textAnchor="middle" className="donut-label">{label}</text>
    </svg>
  );
}

export default App;
