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
  fetchAssetBundle,
  fetchConsoleOverview,
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
  type BrandCheckResult,
  type ConsoleActionInput,
  type ConsoleMetricCard,
  type ConsoleOverview,
  type ReportItem,
  type ReportList,
} from "./console/api";
import {
  assistantMessages,
  factGroups,
  gapItems,
  nextActions,
  opportunities,
  providerResults,
  publishingRows,
  questionRows,
  reportCards,
  topIssues,
  Tone,
} from "./console/data";

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
  ["发布到官网", "将 AI 收录包发布到官网"],
  ["生成 AI 获客页", "生成可被引用的获客页"],
  ["提交 sitemap", "提交 sitemap.xml"],
  ["提交 Google", "Google Search Console"],
  ["提交 Bing", "Bing Webmaster Tools"],
  ["提交百度", "百度搜索资源平台"],
  ["加入复测队列", "定期复测与效果追踪"],
];
const reportMetrics = [
  { label: "AI 提及率", value: "56.8%", delta: "↑ 12.6%", previous: "较上月 44.2%", icon: BarChart3, tone: "primary" as Tone },
  { label: "推荐率", value: "38.7%", delta: "↑ 9.8%", previous: "较上月 28.9%", icon: ThumbsUp, tone: "primary" as Tone },
  { label: "首推率", value: "21.4%", delta: "↑ 6.3%", previous: "较上月 15.1%", icon: Crown, tone: "primary" as Tone },
  { label: "线索增长", value: "+68.3%", delta: "↑ 23.6%", previous: "较上月 +44.7%", icon: UsersRound, tone: "success" as Tone },
];
const reportDescriptions: Record<string, string> = {
  周报: "查看本周 AI 表现与来客线索变化",
  月报: "查看本月整体表现与趋势分析",
  老板报告: "一句话结论 + 关键数据摘要",
  竞品压制报告: "对比竞品表现与压制机会点",
};

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
      showToast({
        title: "操作记录失败",
        desc: error instanceof Error ? error.message : "后端未能记录本次操作，请稍后重试。",
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
        desc: `${result.project.brand_name} 已完成 ${result.taskCount} 个 AI 平台检测任务，并生成资料包和报告。`,
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
          <p>系统会创建项目、生成买家问题，在 ChatGPT、DeepSeek、Kimi、通义、豆包、百度 AI 搜索和腾讯元宝中完成检测，并生成可发布资料。</p>
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
          <strong>{lastResult.scanRun.status === "completed" ? "已生成资料和报告" : "检测任务已创建"}</strong>
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
  const { metricCards } = useConsoleOverview();
  const overviewStatus = useConsoleOverviewStatus();

  return (
    <>
      <PageHeader
        title="工作台"
        subtitle="老板驾驶舱：AI 当前更容易推荐竞品，而不是你。先补齐推荐证据，再启动发布复测。"
        action={<DatePill />}
      />
      {overviewStatus === "fallback" && (
        <AlertBanner
          title="当前显示 fallback 数据"
          desc="控制台概览 API 暂不可用，页面已切换到本地兜底数据；恢复 API 后刷新即可读取实时项目数据。"
          action="重新加载"
          onClick={() => window.location.reload()}
        />
      )}
      <BrandCheckCard onNavigate={onNavigate} onComplete={onBrandCheckComplete} />
      <section className="metric-grid">
        {metricCards.map((item) => (
          <MetricCard key={item.label} item={item} />
        ))}
      </section>
      <section className="dashboard-grid">
        <div className="dashboard-main">
          <div className="two-column">
            <Panel title="AI 来客机会总览">
              <div className="donut-layout">
                <DonutChart values={opportunities.map((item) => item.value)} colors={opportunities.map((item) => item.color)} center="568" label="机会总量" />
                <Legend items={opportunities.map((item) => ({ label: `${item.label} ${item.value}%`, color: item.color }))} />
              </div>
              <div className="panel-note">高意向问题中，41% 尚未被你有效覆盖</div>
            </Panel>
            <Panel title="核心问题覆盖率">
              <Gauge value={41} />
              <div className="panel-note">高意向问题 568 个 ｜ 已覆盖 233 个</div>
            </Panel>
          </div>
          <div className="two-column">
            <Panel title="竞品压制问题">
              <BarList items={topIssues} max={28} tone="danger" />
              <button className="ghost-button" type="button" onClick={() => onNavigate("/console/questions")}>
                查看全部 127 个问题
              </button>
            </Panel>
            <Panel title="AI 推荐资产完成度">
              <div className="donut-layout compact">
                <DonutChart values={[58, 42]} colors={["#443efd", "#edf0f7"]} center="58%" label="完成度" />
                <div className="check-list">
                  <CheckLine text="产品信息完整度" value="80%" checked />
                  <CheckLine text="场景解决方案" value="40%" />
                  <CheckLine text="对比优势证据" value="30%" />
                  <CheckLine text="权威信源引用" value="20%" />
                </div>
              </div>
              <div className="panel-note">补齐对比优势证据，可提升推荐可信度</div>
            </Panel>
          </div>
          <div className="two-column short">
            <Panel title="本周新增来客线索">
              <div className="lead-card">
                <strong>46</strong>
                <span>条</span>
                <small>较上周 ↑ 12（+35%）</small>
              </div>
              <SparkLine />
            </Panel>
            <Panel title="复测增长趋势">
              <TrendChart />
            </Panel>
          </div>
        </div>
        <NextActionsRail onNavigate={onNavigate} />
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

function NextActionsRail({ onNavigate }: { onNavigate: (path: string) => void }) {
  return (
    <aside className="airank-console-card right-rail">
      <div className="rail-title">
        <Target size={24} />
        <h2>下一步建议</h2>
      </div>
      <p className="rail-subtitle">优先补齐推荐证据，提升 AI 推荐概率</p>
      <div className="action-timeline">
        {nextActions.map((item, index) => (
          <article className="action-card" key={item.title}>
            <span className="action-index">{index + 1}</span>
            <div>
              <div className="action-head">
                <h3>{item.title}</h3>
                <span>{item.level}</span>
              </div>
              <p>{item.desc}</p>
              <button className="outline-button" type="button" onClick={() => onNavigate(index === 2 ? "/console/publishing" : "/console/assets")}>
                {item.cta}
              </button>
            </div>
          </article>
        ))}
      </div>
      <button className="airank-console-primary-button rail-cta" type="button" onClick={() => onNavigate("/console/assets")}>
        继续下一步
        <ArrowRight size={18} />
      </button>
      <span className="rail-caption">按此顺序执行，可最大化 AI 推荐效果</span>
    </aside>
  );
}

function CheckupPage({ onNavigate }: { onNavigate: (path: string) => void }) {
  return (
    <>
      <PageHeader
        title="AI 收录体检"
        subtitle="检测结论：在 50 个高意向问题中，AI 更常推荐竞品。先看压制原因，再生成 AI 来客诊断报告。"
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
        {providerResults.map((item) => (
          <article className="airank-console-card provider-card" data-testid="provider-card" key={item.name}>
            <div className="provider-avatar">{item.name.slice(0, 1)}</div>
            <h3>{item.name}</h3>
            <div className="provider-metrics">
              <span>提及率<strong>{item.mention}%</strong></span>
              <span>推荐率<strong>{item.recommend}%</strong></span>
              <span>首推率<strong>{item.first}%</strong></span>
            </div>
          </article>
        ))}
      </section>
      <section className="three-column">
        <Panel title="结果总览">
          <div className="donut-layout compact">
            <DonutChart values={[41, 59]} colors={["#443efd", "#edf0f7"]} center="41%" label="综合可见度" />
            <div className="check-list">
              <CheckLine text="提及率" value="52%" checked />
              <CheckLine text="推荐率" value="35%" checked />
              <CheckLine text="首推率" value="19%" />
              <CheckLine text="负面压制率" value="28%" />
            </div>
          </div>
        </Panel>
        <Panel title="竞品对比（推荐率）">
          <CompareBars />
          <div className="warning-note">本品牌推荐率低于竞品 A 27 个百分点</div>
        </Panel>
        <Panel title="引用来源分析">
          <DonutChart values={[22, 18, 27, 15, 11, 7]} colors={["#01c8b1", "#2b93ff", "#7569ff", "#ff6a2a", "#ffcf4d", "#cfd5e4"]} center="引用来源" label="分布" />
          <Legend
            items={[
              { label: "官网 22%", color: "#01c8b1" },
              { label: "行业媒体 18%", color: "#2b93ff" },
              { label: "第三方平台 27%", color: "#7569ff" },
              { label: "问答社区 15%", color: "#ff6a2a" },
              { label: "内容平台 11%", color: "#ffcf4d" },
              { label: "其他 7%", color: "#cfd5e4" },
            ]}
          />
        </Panel>
      </section>
      <AlertBanner
        title="核心问题：AI 更常推荐竞品"
        desc="主要压制原因：权威来源占比低、差异化内容不足、页面信息干扰、结构化信息缺失"
        action="生成 AI 来客诊断报告"
        onClick={() => onNavigate("/console/reports")}
      />
    </>
  );
}

function FactsPage() {
  const { notify, openPanel, recordAction } = useActionFeedback();

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
              void recordAction({
                actionType: "fact.confirm_batch",
                label: "确认企业事实",
                entityType: "fact_group",
                entityId: "pending_facts",
                payload: { pending_count: 36 },
              }).then(() =>
                notify({
                  title: "事实确认已提交",
                  desc: "已将 36 条待确认事实加入审核队列，后续内容生成会优先引用已确认事实。",
                  tone: "success",
                })
              )
            }
          >
            确认企业事实
          </button>
        }
      />
      <section className="summary-band">
        <SummaryMetric label="事实完整度" value="76%" tone="primary" />
        <SummaryMetric label="已确认事实" value="128" tone="success" />
        <SummaryMetric label="待确认事实" value="36" tone="warning" />
        <div className="summary-chart">
          <DonutChart values={[128, 36, 12, 8]} colors={["#01c8b1", "#fea234", "#7569ff", "#8d97b1"]} center="184" label="总数" />
        </div>
      </section>
      <section className="fact-grid">
        {factGroups.map((item) => (
          <article className="airank-console-card fact-card" key={item.title}>
            <div className="fact-card-head">
              <IconTile tone={item.tone}><NotebookTabs size={23} /></IconTile>
              <div>
                <h3>{item.title}</h3>
                <p>{item.desc}</p>
              </div>
              <Badge tone={item.tone}>{item.status}</Badge>
              <ChevronRight size={22} />
            </div>
            <dl className="fact-meta">
              <div><dt>已确认事实</dt><dd>{item.confirmed}</dd></div>
              <div><dt>待确认事实</dt><dd>{item.pending}</dd></div>
              <div><dt>最后更新</dt><dd>2025-05-06</dd></div>
            </dl>
            <div className="fact-tags">
              <Badge tone="success">可公开</Badge>
              <Badge tone="primary">已用于内容</Badge>
              <Badge tone="primary">已被引用 {item.cited}</Badge>
            </div>
          </article>
        ))}
      </section>
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
        <p>基于 AI 大模型与真实客户咨询数据，挖掘客户在认知、选型、对比、成交全过程中的高意向问题，发现您的推荐缺口与内容机会。</p>
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
        subtitle="AI 为什么推荐竞品，不推荐你？系统已反推出关键缺口。"
        action={<HeaderActions primary="生成 AI 收录包" icon={PackageCheck} onPrimary={() => onNavigate("/console/assets")} />}
      />
      <ProjectStrip />
      <QuestionTable showTabs={false} onNavigate={onNavigate} />
    </>
  );
}

function QuestionTable({ showTabs, onNavigate }: { showTabs: boolean; onNavigate: (path: string) => void }) {
  const { openPanel, recordAction } = useActionFeedback();
  const tabs = ["全部问题", "品牌认知", "选型决策", "竞品对比", "价格成交", "本地行业"];
  const [selectedTab, setSelectedTab] = useState(0);
  const filteredRows =
    showTabs && selectedTab > 0
      ? questionRows.filter((_row, index) => index % (tabs.length - 1) === selectedTab - 1)
      : questionRows;
  const visibleRows = filteredRows.length > 0 ? filteredRows : questionRows.slice(0, 3);

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
        <div className="airank-console-card table-card">
          <table className="question-table">
            <thead>
              <tr>
                <th>问题</th>
                <th>商业意图</th>
                <th>AI 推荐我</th>
                <th>AI 推荐竞品</th>
                <th>推荐缺口</th>
                <th>建议资产</th>
              </tr>
            </thead>
            <tbody>
              {visibleRows.map((row) => (
                <tr key={row.q}>
                  <td>
                    <strong>{row.q}</strong>
                    <Badge tone={row.tag.includes("价格") ? "warning" : row.intent === "高" ? "primary" : "success"}>{row.tag}</Badge>
                  </td>
                  <td><span className={`intent ${row.intent === "高" ? "high" : "mid"}`}>{row.intent}</span></td>
                  <td><strong>{row.mine}%</strong><small>较低</small></td>
                  <td><strong className="danger-text">{row.competitor}%</strong><small>较高</small></td>
                  <td><strong className={row.gap < -35 ? "danger-text" : "success-text"}>{row.gap}%</strong><small>缺口较大</small></td>
                  <td>
                    {row.assets.map((asset) => (
                      <span className="asset-link" key={asset}><ClipboardList size={14} />{asset}</span>
                    ))}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="table-footer">
            <span>{showTabs ? `${tabs[selectedTab]}：${visibleRows.length} 条样例 / 共 128 条问题` : "共 128 条问题"}</span>
            <div className="pagination">‹ <strong>1</strong> 2 3 4 5 ... 13 ›</div>
          </div>
        </div>
      </div>
      <aside className="rail-stack">
        <Panel title="高价值问题分布">
          <DonutChart values={[38, 24, 16, 14, 8]} colors={["#2b75ff", "#29b7e8", "#7569ff", "#ff982a", "#cfd5e4"]} center="128" label="高价值问题" />
          <Legend
            items={[
              { label: "选型决策 38%", color: "#2b75ff" },
              { label: "价格成交 24%", color: "#29b7e8" },
              { label: "竞品对比 16%", color: "#7569ff" },
              { label: "认知教育 14%", color: "#ff982a" },
              { label: "本地行业 8%", color: "#cfd5e4" },
            ]}
          />
        </Panel>
        <Panel title="Top 问题（按推荐缺口）">
          <ol className="top-list">
            {questionRows.slice(0, 5).map((row, index) => (
              <li key={row.q}><span>{index + 1}</span>{row.q}<strong>{row.gap}%</strong></li>
            ))}
          </ol>
          <button
            className="ghost-button"
            type="button"
            onClick={() =>
              showTabs
                ? onNavigate("/console/gaps/questions")
                : openPanel({
                    title: "Top50 推荐缺口问题",
                    desc: "当前页面已经切换到推荐缺口问题视角，完整 Top50 将按推荐差距、商业意图和建议资产排序展示。",
                    items: ["优先处理高意图问题", "补齐竞品对比与案例证据", "发布后回到报表中心复测推荐变化"],
                  })
            }
          >
            查看完整 Top50 问题
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
          <span>AI 的推荐逻辑 = 证据优先，你的证据越全、越结构化、越容易被引用，推荐的概率就越高。</span>
        </div>
      </div>
      <section className="two-panel-wide">
        <Panel title="证据覆盖雷达图">
          <RadarChart />
          <p className="center-caption">覆盖度越高，AI 越容易理解你、信任你、推荐你</p>
        </Panel>
        <Panel title="AI 推荐缺口清单">
          <div className="gap-table">
            {gapItems.map((item) => (
              <div className="gap-row" key={item.name}>
                <IconTile tone={item.covered ? "success" : "primary"}>{item.covered ? <CheckCircle2 size={21} /> : <ShieldAlert size={21} />}</IconTile>
                <div>
                  <strong>{item.name}</strong>
                  <span>{item.desc}</span>
                </div>
                <Badge tone={item.covered ? "success" : "danger"}>{item.covered ? "是" : "否"}</Badge>
                <strong>{item.impact}</strong>
                <span>{item.action}</span>
                <Badge tone={item.level === "高" ? "danger" : item.level === "中" ? "warning" : "success"}>{item.level}</Badge>
              </div>
            ))}
          </div>
        </Panel>
      </section>
      <div className="bottom-action-band">
        <Target size={42} />
        <div>
          <strong>当前 AI 更倾向推荐竞品，</strong>
          <span>因为竞品提供了更多可验证、可引用的公开证据。</span>
        </div>
        <dl>
          <div><dt>你证据总数</dt><dd>28 条</dd></div>
          <div><dt>竞品平均证据数</dt><dd>86 条</dd></div>
          <div><dt>差距</dt><dd className="danger-text">-58 条</dd></div>
        </dl>
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
    const controller = new AbortController();
    fetchAssetBundle(project.id ?? "project_demo", controller.signal)
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
      <div className="package-footer reference-package-footer">
        <DonutChart values={[bundle.completeness, 100 - bundle.completeness]} colors={["#443efd", "#edf0f7"]} center={`${bundle.completeness}%`} label="" />
        <div>
          <strong>收录包完整度</strong>
          <span>{bundle.recommendation}</span>
          <div className="package-check-grid">
            <CheckLine text="内容完整性" value="" checked />
            <CheckLine text="结构化程度" value="" checked />
            <CheckLine text="证据链强度" value="" checked />
            <CheckLine text="AI 友好度" value="" checked />
          </div>
        </div>
        <div className="package-next">
          <strong>下一步：发布提交</strong>
          <span>将收录包提交至目标平台，提升 AI 引用与收录概率。</span>
          <button className="airank-console-primary-button" type="button" onClick={() => onNavigate("/console/publishing")}>
            <Send size={18} />
            发布提交
          </button>
        </div>
      </div>
    </>
  );
}

function PublishingPage({ onNavigate }: { onNavigate: (path: string) => void }) {
  const { openPanel } = useActionFeedback();

  return (
    <>
      <PageHeader
        title="发布提交中心"
        subtitle="把 AI 收录包发布到官网与可抓取入口，并持续跟踪抓取与索引状态。"
        action={<HeaderActions primary="开始复测" icon={Play} onPrimary={() => onNavigate("/console/reports")} />}
      />
      <ProcessSteps
        className="publishing-flow"
        steps={publishingSteps}
      />
      <section className="metric-grid publishing-stats">
        <MiniStat label="已发布页面" value="128" icon={CloudUpload} />
        <MiniStat label="已抓取页面" value="96" icon={SearchCheck} />
        <MiniStat label="已索引页面" value="82" icon={BadgeCheck} />
        <MiniStat label="待复测页面" value="46" icon={RotateCw} />
      </section>
      <Panel title="页面发布与抓取状态">
        <table className="question-table publish-table">
          <thead>
            <tr><th>页面名称</th><th>发布渠道</th><th>抓取状态</th><th>索引状态</th><th>最近提交时间</th><th>操作</th></tr>
          </thead>
          <tbody>
            {publishingRows.map((row) => (
              <tr key={row.page}>
                <td><strong>{row.page}</strong></td>
                <td>{row.channel}</td>
                <td><Badge tone={row.crawl.includes("失败") || row.crawl.includes("未") ? "danger" : row.crawl.includes("提交") ? "primary" : "success"}>{row.crawl}</Badge></td>
                <td><Badge tone={row.index === "已索引" ? "success" : row.index === "待索引" ? "warning" : "muted"}>{row.index}</Badge></td>
                <td>{row.time}</td>
                <td>
                  <button
                    className="table-action"
                    type="button"
                    onClick={() =>
                      openPanel({
                        title: row.page,
                        desc: "发布记录详情会同步展示抓取、索引和最近提交状态。",
                        items: [`发布渠道：${row.channel}`, `抓取状态：${row.crawl}`, `索引状态：${row.index}`, `最近提交：${row.time}`],
                        primaryLabel: "生成复测报告",
                        onPrimary: () => onNavigate("/console/reports"),
                      })
                    }
                  >
                    查看
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>
    </>
  );
}

function AssistantPage() {
  const { project } = useConsoleOverview();
  const { notify, recordAction } = useActionFeedback();
  const [messages, setMessages] = useState<Array<{ role: string; text: string }>>(() => assistantMessages);
  const [draft, setDraft] = useState("");

  const sendPreviewMessage = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const question = draft.trim();
    if (!question) {
      notify({ title: "请输入问题", desc: "输入访客问题后，助手会基于当前事实库和收录包生成预览回复。", tone: "warning" });
      return;
    }
    void recordAction({
      actionType: "assistant.preview_send",
      label: "发送访客问题",
      entityType: "assistant_preview",
      payload: { question },
    });
    setMessages((currentMessages) => [
      ...currentMessages,
      { role: "visitor", text: question },
      {
        role: "assistant",
        text: `基于 ${project.name} 的已确认事实库和 AI 收录包，我建议先明确客户场景、预算区间和决策周期，再引用官网事实页、FAQ 和案例资料，引导客户留下联系方式。`,
      },
    ]);
    setDraft("");
  };

  return (
    <>
      <PageHeader
        title="AI 销售助手"
        subtitle="客户进来后，AI 先替你接待、答疑、推荐案例并引导留资。"
        action={
          <HeaderActions
            primary="发布到官网"
            icon={Rocket}
            onPrimary={() => {
              void recordAction({
                actionType: "assistant.publish",
                label: "发布到官网",
                entityType: "assistant_config",
                payload: { message_count: messages.length },
              });
              notify({
                title: "发布任务已确认",
                desc: "AI 来客助手配置已加入官网发布队列，发布中心会跟踪后续抓取和复测状态。",
                tone: "success",
              });
            }}
          />
        }
      />
      <section className="assistant-grid">
        <Panel title="实时会话预览" action={<Badge tone="success">在线</Badge>}>
          <div className="chat-window">
            {messages.map((msg, index) => (
              <div className={`chat-bubble ${msg.role}`} key={`${msg.role}-${index}`}>{msg.text}</div>
            ))}
          </div>
          <form className="chat-input" onSubmit={sendPreviewMessage}>
            <input
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              placeholder="输入访客问题进行预览"
              aria-label="访客问题"
            />
	            <button type="submit" aria-label="发送消息">
              <Send size={18} />
            </button>
          </form>
        </Panel>
        <div className="rail-stack">
          <ConfigPanel title="知识来源" items={["企业事实库", "产品与服务资料", "客户案例库", "常见问题库"]} />
          <ConfigPanel title="回复风格" items={["专业简洁", "先回答再引导留资", "引用已确认事实", "避免承诺未确认信息"]} />
          <ConfigPanel title="线索规则" items={["询价意向", "案例需求", "集成需求", "人工转接"]} />
        </div>
      </section>
      <section className="metric-grid assistant-stats">
        <MiniStat label="今日会话数" value="326" icon={Activity} />
        <MiniStat label="留资率" value="18.7%" icon={UsersRound} />
        <MiniStat label="满意度" value="4.8" icon={Sparkles} />
      </section>
    </>
  );
}

function ReportsPage({ onNavigate }: { onNavigate: (path: string) => void }) {
  const { project } = useConsoleOverview();
  const { notify, openPanel, recordAction } = useActionFeedback();
  const [reports, setReports] = useState<ReportList>(fallbackReportList);
  const [downloadingReportId, setDownloadingReportId] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    fetchReports(project.id ?? "project_demo", controller.signal)
      .then(setReports)
      .catch(() => setReports({ ...fallbackReportList, reports: reportCards }));
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
      title: "报告生成任务已确认",
      desc: "当前版本会展示最新可用报告；生产报告生成队列接入后将由后端返回新报告。",
      tone: "success",
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
        subtitle="复测 AI 回答变化，向老板清楚汇报本月 AI 收录与来客增长情况。"
        action={<HeaderActions primary="生成老板报告" icon={FileChartColumn} onPrimary={generateReport} />}
      />
      <section className="report-metric-grid">
        {reportMetrics.map((item) => (
          <ReportMetricCard key={item.label} item={item} />
        ))}
      </section>
      <section className="reports-reference-layout">
        <Panel
          title="核心指标 30 天趋势"
          action={
            <button
              className="date-pill compact-pill"
              type="button"
              onClick={() =>
                openPanel({
                  title: "报表周期",
                  desc: "当前报表按最近 30 天口径展示，后续会接入后端周期筛选并保留下载审计。",
                  items: ["近 30 天：当前视图", "近 90 天：待接入", "自定义时间：待接入"],
                })
              }
            >
              近 30 天
              <ChevronDown size={15} />
            </button>
          }
        >
          <TrendChart large />
        </Panel>
        <div className="rail-stack">
          <Panel title="本月关键结论">
            <ul className="conclusion-list reference-conclusions">
              <li><CheckCircle2 size={22} />AI 提及率提升显著<span>本月 AI 提及率达 56.8%，环比提升 12.6%。</span></li>
              <li><CheckCircle2 size={22} />推荐质量持续优化<span>推荐率提升至 38.7%，多项核心问题进入推荐结果。</span></li>
              <li><CheckCircle2 size={22} />首推占比突破新高<span>首推率达 21.4%，在关键搜索场景中占据更优位置。</span></li>
              <li><CheckCircle2 size={22} />线索增长强劲<span>AI 渠道带来的高质量线索持续放大。</span></li>
            </ul>
          </Panel>
          <Panel title="建议动作">
            <div className="report-action-list">
              {["加强在高转化问题的首推占位", "持续优化产品与解决方案内容", "监控竞品动态，防止被反超"].map((item) => (
                <button
                  className="table-action"
                  type="button"
                  key={item}
                  onClick={() =>
                    openPanel({
                      title: item,
                      desc: "该建议会进入下一轮 AI 收录包优化清单，发布后可在报表中心复测效果。",
                      items: ["关联买家问题", "补齐可信事实", "生成可引用资产", "发布后加入复测队列"],
                      primaryLabel: "去 AI 收录包",
                      onPrimary: () => onNavigate("/console/assets"),
                    })
                  }
                >
                  {item}
                  <ChevronRight size={16} />
                </button>
              ))}
            </div>
          </Panel>
        </div>
      </section>
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
              <span>{reportDescriptions[item.title] ?? item.date}</span>
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
  const { project } = useConsoleOverview();
  const { notify, openPanel, recordAction } = useActionFeedback();
  const [savedAt, setSavedAt] = useState<string | null>(null);

  const saveSettings = () => {
    const nextSavedAt = new Date().toLocaleString("zh-CN", { hour12: false });
    setSavedAt(nextSavedAt);
    void recordAction({
      actionType: "settings.save",
      label: "保存设置",
      entityType: "settings",
      entityId: project.id ?? "project_demo",
      payload: { saved_at: nextSavedAt },
    });
    notify({ title: "设置已保存", desc: `本地控制台设置已保存于 ${nextSavedAt}。`, tone: "success" });
  };

  return (
    <>
      <PageHeader
        title="设置中心"
        subtitle={savedAt ? `统一管理项目基础信息、品牌资料、模型平台、通知与成员权限。最近保存：${savedAt}` : "统一管理项目基础信息、品牌资料、模型平台、通知与成员权限。"}
        action={<HeaderActions primary="保存设置" icon={Settings} onPrimary={saveSettings} />}
      />
      <section className="settings-grid">
        <SettingsSection
          title="项目设置"
          icon={Settings}
          onAction={() =>
            openPanel({
              title: "编辑项目设置",
              desc: "项目基础信息会影响体检、报表和 AI 收录包的默认口径。当前版本先展示配置摘要，后续接入后端保存接口。",
              items: ["项目名称：智界问道 | AIRank 来客", `行业：${project.industry}`, "项目时区：GMT+08:00"],
            })
          }
          rows={[["项目名称", "智界问道 | AIRank 来客"], ["项目 ID", "airank-laike-2024"], ["行业", project.industry], ["项目时区", "(GMT+08:00) 北京、上海、香港"], ["创建时间", "2024-05-20 10:30"]]}
        />
        <SettingsSection
          title="品牌信息"
          icon={BadgeCheck}
          onAction={() =>
            openPanel({
              title: "编辑品牌信息",
              desc: "品牌信息会作为 AI 识别企业和生成公开内容的基础资料。",
              items: ["品牌名称：智界问道", "品牌标语：用 AI 洞察客户，让增长更确定", "联系邮箱：service@zhijiewendao.com"],
            })
          }
          rows={[["品牌名称", "智界问道"], ["品牌标语", "用 AI 洞察客户，让增长更确定"], ["品牌简介", "智界问道是领先的 AI 营销洞察与增长决策平台"], ["联系电话", "400-888-1234"], ["联系邮箱", "service@zhijiewendao.com"]]}
        />
        <SettingsSection
          title="官网与域名"
          icon={Globe2}
          onAction={() =>
            openPanel({
              title: "编辑官网与域名",
              desc: "官网和域名验证状态会影响 AI 收录包发布、sitemap 提交和后续复测。",
              items: ["官网地址：https://www.zhijiewendao.com", "网站状态：已验证", "备案信息：京ICP备2024012345号-1"],
            })
          }
          rows={[["官网地址", "https://www.zhijiewendao.com"], ["网站状态", "已验证"], ["备案信息", "京ICP备2024012345号-1"], ["域名管理", "zhijiewendao.com（主域名）"]]}
        />
        <SettingsSection
          title="AI 平台接入"
          icon={Bot}
          onAction={() =>
            openPanel({
              title: "编辑 AI 平台接入",
              desc: "平台接入状态决定后续多模型体检、复测和推荐结果采样范围。",
              items: ["DeepSeek、豆包、Kimi、通义、ChatGPT", "接入状态：5 / 5 已接入", "更新时间：2024-05-20 10:30"],
            })
          }
          rows={[["已接入平台", "DeepSeek、豆包、Kimi、通义、ChatGPT"], ["接入状态", "5 / 5 已接入"], ["更新时间", "2024-05-20 10:30"], ["接入说明", "已完成企业身份验证与 API 授权"]]}
        />
        <SettingsSection
          title="通知设置"
          icon={Bell}
          onAction={() =>
            openPanel({
              title: "编辑通知设置",
              desc: "通知规则会用于报告生成、推荐缺口提醒和发布复测结果同步。",
              items: ["系统通知：已开启", "分析报告通知：已开启", "邮件接收：service@zhijiewendao.com"],
            })
          }
          rows={[["系统通知", "已开启"], ["分析报告通知", "已开启"], ["推荐缺口提醒", "已开启"], ["邮件接收", "service@zhijiewendao.com"]]}
        />
        <SettingsSection
          title="成员与权限"
          icon={UsersRound}
          actionLabel="管理成员"
          onAction={() =>
            openPanel({
              title: "管理成员与权限",
              desc: "成员权限会控制事实确认、发布提交、报告下载和设置变更等关键操作。",
              items: ["团队成员：12 人", "角色管理：5 个角色", "我的角色：超级管理员", "安全设置：登录保护、操作日志已启用"],
            })
          }
          rows={[["团队成员", "12 人"], ["角色管理", "5 个角色"], ["我的角色", "超级管理员"], ["权限范围", "全部数据与功能"], ["安全设置", "登录保护、操作日志已启用"]]}
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

function ConfigPanel({ title, items }: { title: string; items: string[] }) {
  const { recordAction } = useActionFeedback();

  return (
    <Panel title={title}>
      <div className="config-list">
        {items.map((item) => (
          <label key={item}>
            <input
              type="checkbox"
              defaultChecked
              onChange={(event) =>
                void recordAction({
                  actionType: "assistant.config_toggle",
                  label: item,
                  entityType: "assistant_config",
                  entityId: item,
                  payload: { group: title, checked: event.currentTarget.checked },
                })
              }
            />
            {item}
          </label>
        ))}
      </div>
    </Panel>
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

function ReportMetricCard({
  item,
}: {
  item: {
    label: string;
    value: string;
    delta: string;
    previous: string;
    icon: LucideIcon;
    tone: Tone;
  };
}) {
  const Icon = item.icon;
  return (
    <article className="airank-console-card report-metric-card">
      <div>
        <span>{item.label}<Info size={14} /></span>
        <strong>{item.value}</strong>
        <em>{item.delta}</em>
        <small>{item.previous}</small>
      </div>
      <IconTile tone={item.tone}>
        <Icon size={24} />
      </IconTile>
    </article>
  );
}

function SummaryMetric({ label, value, tone }: { label: string; value: string; tone: Tone }) {
  return (
    <div className="summary-metric">
      <span>{label}</span>
      <strong>{value}</strong>
      <Badge tone={tone}>较上次 +8%</Badge>
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
  const total = values.reduce((sum, value) => sum + value, 0);
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

function Legend({ items }: { items: { label: string; color: string }[] }) {
  return (
    <ul className="legend-list">
      {items.map((item) => (
        <li key={item.label}><span style={{ background: item.color }} />{item.label}</li>
      ))}
    </ul>
  );
}

function Gauge({ value }: { value: number }) {
  return (
    <div className="gauge">
      <svg viewBox="0 0 180 110">
        <path d="M25 90a65 65 0 0 1 130 0" fill="none" stroke="#edf0f7" strokeWidth="16" strokeLinecap="round" />
        <path d="M25 90a65 65 0 0 1 130 0" fill="none" stroke="#443efd" strokeWidth="16" strokeLinecap="round" strokeDasharray={`${value * 2.04} 204`} />
      </svg>
      <strong>{value}%</strong>
      <span>覆盖率</span>
      <small>较上周 ↑ 8%</small>
    </div>
  );
}

function BarList({ items, max, tone }: { items: { label: string; value: number }[]; max: number; tone: Tone }) {
  return (
    <div className="bar-list">
      {items.map((item) => (
        <div className="bar-row" key={item.label}>
          <span>{item.label}</span>
          <div><i style={{ width: `${(item.value / max) * 100}%` }} data-tone={tone} /></div>
          <strong>{item.value}</strong>
        </div>
      ))}
    </div>
  );
}

function CompareBars() {
  const items = [
    ["本品牌", 35, "#443efd"],
    ["竞品A", 62, "#ff6a2a"],
    ["竞品B", 48, "#ff8a45"],
    ["竞品C", 41, "#ffb18c"],
    ["行业均值", 36, "#8d97b1"],
  ] as const;
  return (
    <div className="compare-bars">
      {items.map(([label, value, color]) => (
        <div className="compare-row" key={label}>
          <span>{label}</span>
          <div><i style={{ width: `${value}%`, background: color }} /></div>
          <strong>{value}%</strong>
        </div>
      ))}
    </div>
  );
}

function SparkLine() {
  return (
    <svg className="sparkline" viewBox="0 0 260 110">
      {[20, 45, 70, 95].map((y) => <line key={y} x1="0" x2="260" y1={y} y2={y} stroke="#e8ecf6" />)}
      <polyline points="5,70 38,55 70,78 102,58 132,72 165,38 198,52 228,34 255,22" fill="none" stroke="#443efd" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function TrendChart({ large = false }: { large?: boolean }) {
  return (
    <svg className={`trend-chart ${large ? "large" : ""}`} viewBox="0 0 430 170">
      {[30, 65, 100, 135].map((y) => <line key={y} x1="20" x2="410" y1={y} y2={y} stroke="#e8ecf6" />)}
      <polyline points="20,145 65,130 110,126 155,120 200,98 245,84 290,66 335,54 382,24" fill="none" stroke="#443efd" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" />
      <polyline points="20,150 65,142 110,138 155,126 200,108 245,98 290,90 335,70 382,46" fill="none" stroke="#01c8b1" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function RadarChart() {
  const labels = ["品牌身份", "核心服务", "客户案例", "FAQ问答", "行业方案", "对比选型", "第三方信源", "技术抓取"];
  return (
    <div className="radar-wrap">
      <svg className="radar-chart" viewBox="0 0 360 320">
        <polygon points="180,30 286,74 330,180 286,286 180,330 74,286 30,180 74,74" fill="none" stroke="#d9dfec" />
        <polygon points="180,70 258,102 290,180 258,258 180,290 102,258 70,180 102,102" fill="none" stroke="#d9dfec" strokeDasharray="4 4" />
        <polygon points="180,96 230,124 260,180 230,232 180,248 126,224 102,180 128,120" fill="rgba(68, 62, 253, 0.14)" stroke="#443efd" strokeWidth="4" />
        {labels.map((label, index) => {
          const angle = (Math.PI * 2 * index) / labels.length - Math.PI / 2;
          const x = 180 + Math.cos(angle) * 150;
          const y = 180 + Math.sin(angle) * 138;
          return (
            <text key={label} x={x} y={y} textAnchor="middle" className="radar-label">{label}</text>
          );
        })}
        <text x="180" y="178" textAnchor="middle" className="radar-score">26%</text>
        <text x="180" y="202" textAnchor="middle" className="radar-caption">综合覆盖度</text>
      </svg>
    </div>
  );
}

function ProgressBar({ value }: { value: number }) {
  return (
    <div className="progress-bar">
      <i style={{ width: `${value}%` }} />
    </div>
  );
}

export default App;
