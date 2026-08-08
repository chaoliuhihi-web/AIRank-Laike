import { createContext, useCallback, useContext, useEffect, useState } from "react";
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
  FileSearch,
  FileText,
  Globe2,
  HelpCircle,
  Home,
  Info,
  Link2,
  ListChecks,
  LogOut,
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
  ScanSearch,
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
  clearAuthSession,
  compileQuestionMap,
  createCitationClaim,
  createCitationSourceCapture,
  createCitationSupportReview,
  createPageAudit,
  fetchQuestionObservationBatches,
  fetchAnswerSample,
  fetchAnswerSamples,
  fetchBuyerQuestions,
  fetchAssetBundle,
  fetchConsoleOverview,
  fetchContentAssets,
  fetchCitationSupport,
  fetchCitationSourceCapture,
  fetchCitationSourceCaptures,
  fetchEvidenceObject,
  fetchFactConflicts,
  fetchFacts,
  fetchInternalSkills,
  fetchKnowledgeGovernance,
  fetchKnowledgeSources,
  fetchPageAudit,
  fetchPageAudits,
  fetchMeasurementQuality,
  fetchProviderReadiness,
  fetchPublishAttempts,
  fetchPublishPackages,
  fetchRetestWindows,
  fetchSkillPromotionLedger,
  fetchScanRuns,
  fetchScanTasks,
  fallbackReportList,
  fetchReports,
  getStoredAuthSession,
  loginToAirank,
  importQuestionObservations,
  recordConsoleAction,
  recordDownloadReceipt,
  reviewBuyerQuestion,
  reviewContentAsset,
  reviewFactRevision,
  resolveFactConflict,
  saveKnowledgeSource,
  searchKnowledge,
  runBrandCheck,
  storeAuthSession,
  type AuthSession,
  type AnswerSample,
  type AnswerSampleDetail,
  type AssetBundle,
  type BuyerQuestion,
  type BrandCheckResult,
  type ConsoleActionInput,
  type ConsoleMetricCard,
  type ConsoleOverview,
  type CitationSupportBundle,
  type CitationSourceCapture,
  type FactConflict,
  type GovernedContentAsset,
  type FactRevision,
  type InternalSkill,
  type KnowledgeGovernance,
  type KnowledgeSearch,
  type PageAuditFinding,
  type PageAuditRun,
  type KnowledgeSource,
  type MeasurementQualityReport,
  type ProviderReadiness,
  type QuestionMapResult,
  type QuestionObservationBatch,
  type PublishPackage,
  type ReportItem,
  type ReportList,
  type RetestWindow,
  type ScanRun,
  type ScanTask,
  type SkillPromotionLedger,
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
  FileSearch,
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
  ScanSearch,
  Send,
  Settings,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  SquarePen,
  Target,
  UserRound,
  UsersRound,
  Workflow,
  Zap,
};

const navRoutes = consoleRoutes.filter((route) => route.id !== "gap-questions");
const ConsoleOverviewContext = createContext<ConsoleOverview>(fallbackConsoleOverview);
const ConsoleOverviewStatusContext = createContext<"loading" | "api" | "fallback">("loading");
const assetCardIcons: LucideIcon[] = [FileText, Box, UsersRound, MessageCircle, Scale, Lightbulb, Code2, Workflow];
const reportCardIcons: LucideIcon[] = [CalendarDays, NotebookTabs, Crown, FileChartColumn];
const qualityLimitationLabels: Record<string, string> = {
  valid_samples_have_no_provider_citations: "有效样本没有 Provider 原生引用",
  citation_support_not_evaluated: "引用支持度尚未评测",
  fact_accuracy_not_evaluated: "事实准确率尚未评测",
  repeat_stability_unavailable: "重复采样稳定性不可用",
};
const citationSupportLimitationLabels: Record<string, string> = {
  selected_citations_have_no_answer_claims: "原生引用尚未绑定回答中的具体断言",
  citation_support_not_reviewed: "断言与引用尚未复核",
  citation_support_has_no_source_page_snapshot: "尚无不可变来源页面快照",
  provisional_reviews_excluded_from_support_rate: "临时复核不会进入可交付支持率",
};
const sourcePanelStatusLabels: Record<string, string> = {
  captured: "已捕获并存证",
  not_present: "界面未呈现（已检查）",
  not_inspected: "未检查",
  not_applicable: "不适用",
};
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
      .catch((error) => {
        if (controller.signal.aborted) return;
        if (error instanceof Error && error.message.includes("401")) {
          clearAuthSession();
          setAuthSession(null);
        }
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

  const handleLogout = () => {
    clearAuthSession();
    setAuthSession(null);
    setOverview(fallbackConsoleOverview);
    setOverviewStatus("fallback");
    navigate("/login");
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
              <Sidebar activePath={path} onNavigate={navigateWithAudit} onLogout={handleLogout} />
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
  onLogout,
}: {
  activePath: string;
  onNavigate: (path: string) => void;
  onLogout: () => void;
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
        <button className="help-link" type="button" onClick={onLogout}>
          <LogOut size={22} />
          <span>退出登录</span>
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
  if (path === "/console/page-audit") return <PageAuditPage />;
  if (path === "/console/evidence") return <EvidencePage />;
  if (path === "/console/tasks") return <TaskCenterPage />;
  if (path === "/console/questions") return <QuestionsPage onNavigate={onNavigate} />;
  if (path === "/console/gaps/questions") return <GapQuestionsPage onNavigate={onNavigate} />;
  if (path === "/console/gaps") return <GapsPage onNavigate={onNavigate} />;
  if (path === "/console/assets") return <AssetsPage onNavigate={onNavigate} />;
  if (path === "/console/publishing") return <PublishingPage onNavigate={onNavigate} />;
  if (path === "/console/assistant") return <AssistantPage />;
  if (path === "/console/reports") return <ReportsPage onNavigate={onNavigate} />;
  if (path === "/console/settings") return <SettingsPage />;
  if (path === "/console/skills") return <SkillConsolePage />;
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
      const completed = result.scanRun.status === "completed";
      notify({
        title: completed ? "品牌检测已完成" : "品牌检测已进入队列",
        desc: completed
          ? `${result.project.brand_name} 已处理 ${result.taskCount} 个检测任务；请在体检页核对有效、失败、阻塞和未提及样本。`
          : `${result.project.brand_name} 已创建 ${result.taskCount} 个真实采样任务；Worker 将异步执行，请在任务中心查看进度。`,
        tone: completed ? "success" : "warning",
      });
      onNavigate(completed ? "/console/checkup" : "/console/tasks");
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
          {submitting ? "提交中" : "开始 AI 排名检测"}
          <ArrowRight size={18} />
        </button>
      </form>
      {lastResult && (
        <div className="brand-check-result" role="status">
          <Badge tone={lastResult.scanRun.status === "completed" ? "success" : "warning"}>{lastResult.scanRun.status === "completed" ? "检测完成" : "已进入队列"}</Badge>
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
      .catch((error) => {
        if (controller.signal.aborted) return;
        setLoadError(error instanceof Error ? error.message : "Provider 健康接口不可用");
      });
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

function pageAuditTone(status: PageAuditRun["status"]): Tone {
  if (status === "completed") return "success";
  if (status === "blocked" || status === "failed") return "danger";
  return "warning";
}

function findingTone(finding: PageAuditFinding): Tone {
  if (finding.status === "passed") return "success";
  if (finding.severity === "critical" || finding.severity === "high") return "danger";
  return finding.severity === "medium" ? "warning" : "muted";
}

function PageAuditPage() {
  const { project } = useConsoleOverview();
  const { notify } = useActionFeedback();
  const [url, setUrl] = useState(project.website || "");
  const [runs, setRuns] = useState<PageAuditRun[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const selected = runs.find((run) => run.run_id === selectedRunId) ?? runs[0] ?? null;

  useEffect(() => {
    setUrl(project.website || "");
    if (!project.id) {
      setRuns([]);
      setSelectedRunId(null);
      return;
    }
    const controller = new AbortController();
    setLoading(true);
    fetchPageAudits(project.id, controller.signal)
      .then((data) => {
        setRuns(data);
        setSelectedRunId((current) => current ?? data[0]?.run_id ?? null);
        setLoadError(null);
      })
      .catch((error) => {
        if (controller.signal.aborted) return;
        setLoadError(error instanceof Error ? error.message : "页面诊断接口不可用");
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [project.id, project.website]);

  useEffect(() => {
    if (!project.id || !selected || !["queued", "running"].includes(selected.status)) return;
    const controller = new AbortController();
    const timer = window.setInterval(() => {
      fetchPageAudit(project.id, selected.run_id, controller.signal)
        .then((updated) => {
          setRuns((current) => [updated, ...current.filter((item) => item.run_id !== updated.run_id)]);
          setLoadError(null);
        })
        .catch((error) => {
          if (!controller.signal.aborted) {
            setLoadError(error instanceof Error ? error.message : "页面诊断状态刷新失败");
          }
        });
    }, 1800);
    return () => {
      controller.abort();
      window.clearInterval(timer);
    };
  }, [project.id, selected?.run_id, selected?.status]);

  const submitAudit = async (event: FormEvent) => {
    event.preventDefault();
    const actor = getStoredAuthSession()?.user.userId;
    if (!project.id || !actor || !url.trim()) {
      notify({
        title: "无法发起诊断",
        desc: !project.id ? "请先创建品牌项目。" : !actor ? "当前会话缺少可信操作人。" : "请输入公开页面 URL。",
        tone: "danger",
      });
      return;
    }
    setSubmitting(true);
    try {
      const created = await createPageAudit(project.id, url.trim(), actor);
      setRuns((current) => [created, ...current.filter((item) => item.run_id !== created.run_id)]);
      setSelectedRunId(created.run_id);
      setLoadError(null);
      notify({ title: "诊断任务已入队", desc: "Worker 将使用固定 DNS 目标抓取，并保存逐规则证据。", tone: "success" });
    } catch (error) {
      const message = error instanceof Error ? error.message : "页面诊断任务创建失败";
      setLoadError(message);
      notify({ title: "诊断任务创建失败", desc: message, tone: "danger" });
    } finally {
      setSubmitting(false);
    }
  };

  const failedFindings = selected?.findings.filter((finding) => finding.status === "failed") ?? [];

  return (
    <>
      <PageHeader
        title="官网可提取性"
        subtitle="检查服务器返回的 HTML、索引指令、正文与结构化数据；技术可提取性分不等于品牌推荐率。"
        action={<Badge tone="primary">独立技术指标</Badge>}
      />
      <form className="airank-console-card page-audit-launcher" onSubmit={submitAudit}>
        <div>
          <label htmlFor="page-audit-url">公开页面 URL</label>
          <span>支持公开 HTTP(S) 页面；私网、云元数据地址、危险重定向和超大响应会被阻断。</span>
        </div>
        <input
          id="page-audit-url"
          value={url}
          onChange={(event) => setUrl(event.target.value)}
          placeholder="https://example.com/product"
          inputMode="url"
        />
        <button className="airank-console-primary-button" type="submit" disabled={submitting || !project.id}>
          <ScanSearch size={18} />{submitting ? "提交中…" : "开始真实抓取"}
        </button>
      </form>

      {loadError && <DataStateCard title="页面诊断链路异常" desc={loadError} tone="danger" />}
      {!project.id && <DataStateCard title="尚未创建品牌项目" desc="先完成品牌建档，再对官网或事实页发起技术诊断。" tone="warning" />}
      {project.id && loading && <DataStateCard title="正在读取诊断历史" desc="只加载当前租户和项目的真实任务。" tone="primary" />}
      {project.id && !loading && runs.length === 0 && !loadError && (
        <DataStateCard title="尚无官网诊断证据" desc="输入公开页面 URL 后发起第一次真实抓取；本页不会生成示例分数。" tone="warning" />
      )}

      {selected && (
        <section className="page-audit-layout">
          <div className="page-audit-main">
            <article className="airank-console-card page-audit-summary">
              <div className="page-audit-score" data-status={selected.status}>
                <strong>{selected.technical_extractability_score ?? "—"}</strong>
                <span>技术可提取性</span>
              </div>
              <div className="page-audit-summary-copy">
                <div className="page-audit-summary-head">
                  <div>
                    <Badge tone={pageAuditTone(selected.status)}>{selected.status}</Badge>
                    <h2>{selected.extracted.title || selected.requested_url}</h2>
                  </div>
                  <span>{formatDateTime(selected.completed_at || selected.created_at)}</span>
                </div>
                <p>{selected.error_message || (selected.status === "completed" ? `${selected.finding_count - selected.failed_finding_count} 项通过，${selected.failed_finding_count} 项需要修复。` : "任务已入队，等待 Worker 抓取和逐规则分析。")}</p>
                <dl className="page-audit-proof-grid">
                  <div><dt>HTTP</dt><dd>{selected.response_status ?? "—"}</dd></div>
                  <div><dt>正文字符</dt><dd>{selected.extracted.visible_text_chars ?? "—"}</dd></div>
                  <div><dt>H1</dt><dd>{selected.extracted.h1_count ?? "—"}</dd></div>
                  <div><dt>重定向</dt><dd>{selected.redirect_count ?? "—"}</dd></div>
                  <div><dt>证据等级</dt><dd>{selected.evidence_grade || "等待抓取"}</dd></div>
                  <div><dt>内容 Hash</dt><dd title={selected.content_sha256 ?? undefined}>{selected.content_sha256 ? selected.content_sha256.slice(0, 12) : "—"}</dd></div>
                </dl>
              </div>
            </article>

            {selected.status === "completed" && (
              <div className="page-audit-findings">
                <div className="section-heading">
                  <div><span>逐规则证据</span><h2>{failedFindings.length ? "优先修复可定位的问题" : "当前规则全部通过"}</h2></div>
                  <Badge tone={failedFindings.length ? "warning" : "success"}>{failedFindings.length} 项失败</Badge>
                </div>
                {selected.findings.map((finding) => (
                  <article className="airank-console-card page-audit-finding" data-status={finding.status} key={finding.finding_id || finding.rule_id}>
                    <div className="page-audit-finding-icon">
                      {finding.status === "passed" ? <CheckCircle2 size={20} /> : <AlertTriangle size={20} />}
                    </div>
                    <div>
                      <div className="page-audit-finding-head">
                        <h3>{finding.title}</h3>
                        <Badge tone={findingTone(finding)}>{finding.status === "passed" ? "通过" : finding.severity}</Badge>
                      </div>
                      <p>{finding.description}</p>
                      {finding.recommendation && <strong>{finding.recommendation}</strong>}
                      <code>{finding.rule_id} · {JSON.stringify(finding.evidence)}</code>
                    </div>
                  </article>
                ))}
              </div>
            )}
          </div>

          <aside className="airank-console-card page-audit-history">
            <div className="rail-title"><FileSearch size={22} /><h2>诊断历史</h2></div>
            <p>每次抓取独立保存，不覆盖旧结果。</p>
            <div className="page-audit-history-list">
              {runs.map((run) => (
                <button
                  type="button"
                  data-active={run.run_id === selected.run_id}
                  key={run.run_id}
                  onClick={() => setSelectedRunId(run.run_id)}
                >
                  <span><Badge tone={pageAuditTone(run.status)}>{run.status}</Badge><small>{formatDateTime(run.created_at)}</small></span>
                  <strong>{run.technical_extractability_score ?? "—"}</strong>
                  <em>{run.requested_url}</em>
                </button>
              ))}
            </div>
            <div className="page-audit-disclaimer">
              <Info size={18} />
              <span>该结果只说明页面是否便于抓取和提取；品牌提及、推荐与引用必须回到多平台真实样本验证。</span>
            </div>
          </aside>
        </section>
      )}
    </>
  );
}

function FactsPage() {
  const { project } = useConsoleOverview();
  const { openPanel, notify } = useActionFeedback();
  const [facts, setFacts] = useState<FactRevision[]>([]);
  const [sources, setSources] = useState<KnowledgeSource[]>([]);
  const [conflicts, setConflicts] = useState<FactConflict[]>([]);
  const [governance, setGovernance] = useState<KnowledgeGovernance | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [reviewingRevisionId, setReviewingRevisionId] = useState<string | null>(null);
  const [resolvingConflictId, setResolvingConflictId] = useState<string | null>(null);
  const [conflictNotes, setConflictNotes] = useState<Record<string, string>>({});
  const [conflictResolutions, setConflictResolutions] = useState<Record<string, "resolved_left" | "resolved_right" | "resolved_new_revision" | "dismissed">>({});
  const [sourceEditor, setSourceEditor] = useState<{
    parent: KnowledgeSource | null;
    idempotencyKey: string;
    title: string;
    sourceType: string;
    sourceUri: string;
    contentText: string;
    authorityLevel: "official" | "verified_third_party" | "community" | "unclassified";
    riskLevel: "low" | "medium" | "high" | "restricted";
    validUntil: string;
  } | null>(null);
  const [savingSource, setSavingSource] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [knowledgeSearch, setKnowledgeSearch] = useState<KnowledgeSearch | null>(null);
  const [searchingKnowledge, setSearchingKnowledge] = useState(false);
  const [knowledgeSearchError, setKnowledgeSearchError] = useState<string | null>(null);

  const refreshKnowledge = useCallback(async (signal?: AbortSignal) => {
    if (!project.id) return;
    const [nextFacts, nextSources, nextConflicts, nextGovernance] = await Promise.all([
      fetchFacts(project.id, signal),
      fetchKnowledgeSources(project.id, signal),
      fetchFactConflicts(project.id, signal),
      fetchKnowledgeGovernance(project.id, signal),
    ]);
    setFacts(nextFacts);
    setSources(nextSources);
    setConflicts(nextConflicts);
    setGovernance(nextGovernance);
    setLoadError(null);
  }, [project.id]);

  useEffect(() => {
    if (!project.id) return;
    const controller = new AbortController();
    refreshKnowledge(controller.signal)
      .catch((error) => {
        if (controller.signal.aborted) return;
        setLoadError(error instanceof Error ? error.message : "事实库接口不可用");
      });
    return () => controller.abort();
  }, [project.id, refreshKnowledge]);

  const approved = facts.filter((item) => item.status === "approved").length;
  const pending = facts.filter((item) => item.status === "proposed").length;
  const eligible = facts.filter((item) => item.eligible_for_generation).length;

  const reviewRevision = async (revision: FactRevision, action: "approved" | "rejected") => {
    const actor = getStoredAuthSession()?.user.userId;
    if (!project.id || !actor) {
      notify({ title: "无法提交审核", desc: "当前登录会话缺少可信审核人身份，请重新登录。", tone: "danger" });
      return;
    }
    setReviewingRevisionId(revision.revision_id);
    try {
      const updated = await reviewFactRevision(project.id, revision.revision_id, action, actor);
      setFacts((items) => items.map((item) => item.revision_id === updated.revision_id ? updated : item));
      notify({ title: action === "approved" ? "事实已批准" : "事实已驳回", desc: `${updated.title} 的审核结果已由服务端持久化。`, tone: "success" });
      void refreshKnowledge().catch((error) => {
        setLoadError(error instanceof Error ? error.message : "事实库刷新失败");
      });
    } catch (error) {
      notify({ title: "审核未通过", desc: error instanceof Error ? error.message : "事实审核接口不可用", tone: "danger" });
    } finally {
      setReviewingRevisionId(null);
    }
  };

  const resolveConflict = async (conflict: FactConflict) => {
    const actor = getStoredAuthSession()?.user.userId;
    const note = (conflictNotes[conflict.conflict_id] ?? "").trim();
    const resolution = conflictResolutions[conflict.conflict_id] ?? "resolved_right";
    if (!project.id || !actor) {
      notify({ title: "无法提交裁决", desc: "当前登录会话缺少可信审核人身份，请重新登录。", tone: "danger" });
      return;
    }
    if (!note) {
      notify({ title: "需要裁决说明", desc: "请记录判断依据；系统不会自动消除事实冲突。", tone: "warning" });
      return;
    }
    setResolvingConflictId(conflict.conflict_id);
    try {
      await resolveFactConflict(project.id, conflict.conflict_id, resolution, actor, note);
      setConflicts((items) => items.filter((item) => item.conflict_id !== conflict.conflict_id));
      setConflictNotes((items) => ({ ...items, [conflict.conflict_id]: "" }));
      notify({ title: "冲突已人工裁决", desc: "裁决人、时间、选择和说明已由服务端保存。", tone: "success" });
      void refreshKnowledge().catch((error) => {
        setLoadError(error instanceof Error ? error.message : "事实库刷新失败");
      });
    } catch (error) {
      notify({ title: "冲突裁决失败", desc: error instanceof Error ? error.message : "事实冲突接口不可用", tone: "danger" });
    } finally {
      setResolvingConflictId(null);
    }
  };

  const openSourceEditor = (parent: KnowledgeSource | null) => {
    setSourceEditor({
      parent,
      idempotencyKey: `web-source-${crypto.randomUUID()}`,
      title: parent?.title ?? "",
      sourceType: parent?.source_type ?? "official_document",
      sourceUri: parent?.source_uri ?? "",
      contentText: "",
      authorityLevel: (parent?.authority_level as "official" | "verified_third_party" | "community" | "unclassified" | undefined) ?? "official",
      riskLevel: (parent?.risk_level as "low" | "medium" | "high" | "restricted" | undefined) ?? "medium",
      validUntil: parent?.valid_until ? parent.valid_until.slice(0, 16) : "",
    });
  };

  const submitSource = async (event: FormEvent) => {
    event.preventDefault();
    if (!project.id || !sourceEditor) return;
    if (!sourceEditor.title.trim() || !sourceEditor.contentText.trim()) {
      notify({ title: "来源资料不完整", desc: "标题和完整原文不能为空。更新来源时必须提交完整新快照。", tone: "warning" });
      return;
    }
    setSavingSource(true);
    try {
      const saved = await saveKnowledgeSource(project.id, {
        idempotency_key: sourceEditor.idempotencyKey,
        source_type: sourceEditor.sourceType.trim(),
        title: sourceEditor.title.trim(),
        source_uri: sourceEditor.sourceUri.trim() || undefined,
        content_text: sourceEditor.contentText,
        authority_level: sourceEditor.authorityLevel,
        risk_level: sourceEditor.riskLevel,
        valid_until: sourceEditor.validUntil ? new Date(sourceEditor.validUntil).toISOString() : undefined,
      }, sourceEditor.parent?.source_id);
      setSourceEditor(null);
      notify({
        title: sourceEditor.parent ? "来源新版本已保存" : "知识来源已导入",
        desc: `${saved.title} 已保存为 v${saved.revision_number}；原文、边界和 hash 均由服务端生成。`,
        tone: "success",
      });
      void refreshKnowledge().catch((error) => {
        setLoadError(error instanceof Error ? error.message : "事实库刷新失败");
      });
    } catch (error) {
      notify({ title: "来源保存失败", desc: error instanceof Error ? error.message : "知识来源接口不可用", tone: "danger" });
    } finally {
      setSavingSource(false);
    }
  };

  const submitKnowledgeSearch = async (event: FormEvent) => {
    event.preventDefault();
    const query = searchQuery.trim();
    if (!project.id || query.length < 2) {
      setKnowledgeSearchError("请输入至少 2 个字符，检索只覆盖当前有效来源。");
      return;
    }
    setSearchingKnowledge(true);
    setKnowledgeSearchError(null);
    try {
      setKnowledgeSearch(await searchKnowledge(project.id, query));
    } catch (error) {
      setKnowledgeSearchError(error instanceof Error ? error.message : "知识检索接口不可用");
    } finally {
      setSearchingKnowledge(false);
    }
  };

  return (
    <>
      <PageHeader
        title="企业事实库"
        subtitle="AI 认识你的前提，是企业事实足够清晰、可信、可公开。"
        action={
          <div className="header-actions">
            <button className="outline-button" type="button" onClick={() => openSourceEditor(null)}>导入知识来源</button>
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
          </div>
        }
      />
      {sourceEditor && (
        <Panel title={sourceEditor.parent ? `更新来源 · ${sourceEditor.parent.title}` : "导入知识来源"}>
          <form className="knowledge-source-form" onSubmit={submitSource}>
            <label>
              <span>来源标题</span>
              <input value={sourceEditor.title} onChange={(event) => setSourceEditor({ ...sourceEditor, title: event.target.value })} placeholder="例如：企业官方产品说明" />
            </label>
            <label>
              <span>来源类型</span>
              <input value={sourceEditor.sourceType} onChange={(event) => setSourceEditor({ ...sourceEditor, sourceType: event.target.value })} placeholder="official_document" />
            </label>
            <label className="knowledge-source-form-wide">
              <span>公开原文 URL（可选）</span>
              <input type="url" value={sourceEditor.sourceUri} onChange={(event) => setSourceEditor({ ...sourceEditor, sourceUri: event.target.value })} placeholder="https://example.com/facts" />
            </label>
            <label>
              <span>权威等级</span>
              <select value={sourceEditor.authorityLevel} onChange={(event) => setSourceEditor({ ...sourceEditor, authorityLevel: event.target.value as "official" | "verified_third_party" | "community" | "unclassified" })}>
                <option value="official">官方</option>
                <option value="verified_third_party">已核验第三方</option>
                <option value="community">社区来源</option>
                <option value="unclassified">未分类</option>
              </select>
            </label>
            <label>
              <span>风险等级</span>
              <select value={sourceEditor.riskLevel} onChange={(event) => setSourceEditor({ ...sourceEditor, riskLevel: event.target.value as "low" | "medium" | "high" | "restricted" })}>
                <option value="low">低</option>
                <option value="medium">中</option>
                <option value="high">高</option>
                <option value="restricted">受限</option>
              </select>
            </label>
            <label>
              <span>有效期（可选）</span>
              <input type="datetime-local" value={sourceEditor.validUntil} onChange={(event) => setSourceEditor({ ...sourceEditor, validUntil: event.target.value })} />
            </label>
            <label className="knowledge-source-form-wide">
              <span>{sourceEditor.parent ? "完整新版本原文" : "完整原文"}</span>
              <textarea value={sourceEditor.contentText} onChange={(event) => setSourceEditor({ ...sourceEditor, contentText: event.target.value })} placeholder="粘贴完整、未经改写的企业资料；系统会保存不可变快照和精确字符边界。" rows={7} />
            </label>
            <div className="knowledge-source-form-actions">
              <button className="outline-button" type="button" disabled={savingSource} onClick={() => setSourceEditor(null)}>取消</button>
              <button className="airank-console-primary-button" type="submit" disabled={savingSource}>{savingSource ? "保存中…" : sourceEditor.parent ? "保存新版本" : "导入并切片"}</button>
            </div>
          </form>
        </Panel>
      )}
      <Panel title="当前有效原文检索">
        <form className="knowledge-search-form" onSubmit={submitKnowledgeSearch}>
          <input value={searchQuery} onChange={(event) => setSearchQuery(event.target.value)} placeholder="检索产品参数、资质、案例或公开主张" />
          <button className="airank-console-primary-button" type="submit" disabled={searchingKnowledge}>{searchingKnowledge ? "检索中…" : "检索原文"}</button>
        </form>
        <div className="knowledge-search-policy">
          <Badge tone="primary">lexical_only</Badge>
          <span>只检索 active 且在有效期内的不可变切片；向量检索未配置，不冒充混合检索。</span>
        </div>
        {knowledgeSearchError && <DataStateCard title="知识检索失败" desc={knowledgeSearchError} tone="danger" />}
        {knowledgeSearch && knowledgeSearch.results.length === 0 && <DataStateCard title="当前有效来源无匹配" desc="旧版本、过期来源和未命中切片不会补造搜索结果。" tone="warning" />}
        {knowledgeSearch && knowledgeSearch.results.length > 0 && (
          <ol className="knowledge-search-results">
            {knowledgeSearch.results.map((result) => (
              <li key={result.segment_id}>
                <div>
                  <strong>#{result.rank} · {result.source_title} · v{result.source_revision_number}</strong>
                  <Badge tone={result.match_type === "exact" ? "success" : "primary"}>{result.match_type}</Badge>
                </div>
                <p>{result.text}</p>
                <span>边界 {result.source_start}—{result.source_end} · hash {result.content_sha256.slice(0, 12)}… · 命中 {result.matched_terms.join(" / ")}</span>
              </li>
            ))}
          </ol>
        )}
      </Panel>
      <section className="summary-band">
        <SummaryMetric label="知识来源" value={String(sources.length)} tone="primary" />
        <SummaryMetric label="已审核事实" value={String(approved)} tone="success" />
        <SummaryMetric label="待审核事实" value={String(pending)} tone="warning" />
        <div className="summary-chart">
          <DonutChart values={[eligible, Math.max(facts.length - eligible, 0)]} colors={["#01c8b1", "#edf0f7"]} center={String(facts.length)} label="事实修订" />
        </div>
      </section>
      {loadError && <DataStateCard title="事实库读取失败" desc={loadError} tone="danger" />}
      {!loadError && governance && (
        <DataStateCard
          title={governance.status === "healthy" ? "事实与来源当前无到期或冲突提醒" : `${governance.action_required_count} 项事实治理工作待处理`}
          desc={governance.status === "healthy"
            ? `系统按 ${governance.within_days} 天观察窗检查来源、已批准事实与开放冲突。`
            : `旧版本来源 ${governance.stale_source_count}、已过期来源 ${governance.expired_source_count}、即将到期来源 ${governance.expiring_source_count}、已过期事实 ${governance.expired_fact_count}、即将到期事实 ${governance.expiring_fact_count}、开放冲突 ${governance.open_conflict_count}。`}
          tone={governance.status === "healthy" ? "primary" : "danger"}
        />
      )}
      {!loadError && governance && governance.alerts.length > 0 && (
        <Panel title={`治理提醒 · 未来 ${governance.within_days} 天`}>
          <div className="knowledge-governance-list">
            {governance.alerts.map((alert) => (
              <article className="knowledge-governance-row" data-severity={alert.severity} key={alert.alert_id}>
                <AlertTriangle size={20} />
                <div>
                  <strong>{alert.title}</strong>
                  <span>{alert.message}</span>
                </div>
                <Badge tone={alert.severity === "critical" ? "danger" : "warning"}>{alert.kind}</Badge>
                <time>{alert.due_at ? formatDateTime(alert.due_at) : "等待人工裁决"}</time>
              </article>
            ))}
          </div>
        </Panel>
      )}
      {!loadError && conflicts.length > 0 && (
        <Panel title="开放事实冲突 · 必须人工裁决">
          <div className="fact-conflict-list">
            {conflicts.map((conflict) => (
              <article className="fact-conflict-card" key={conflict.conflict_id}>
                <div className="fact-conflict-head">
                  <div>
                    <strong>{conflict.description}</strong>
                    <span>{conflict.conflict_type} · {formatDateTime(conflict.detected_at)}</span>
                  </div>
                  <Badge tone="danger">{conflict.status}</Badge>
                </div>
                <div className="fact-conflict-revisions">
                  <code>左：{conflict.left_revision_id}</code>
                  <code>右：{conflict.right_revision_id}</code>
                </div>
                <div className="fact-conflict-resolution">
                  <select
                    aria-label={`选择 ${conflict.conflict_id} 的裁决结果`}
                    value={conflictResolutions[conflict.conflict_id] ?? "resolved_right"}
                    onChange={(event) => setConflictResolutions((items) => ({ ...items, [conflict.conflict_id]: event.target.value as "resolved_left" | "resolved_right" | "resolved_new_revision" | "dismissed" }))}
                  >
                    <option value="resolved_left">采用左版本</option>
                    <option value="resolved_right">采用右版本</option>
                    <option value="resolved_new_revision">已创建新修订</option>
                    <option value="dismissed">判定无需处理</option>
                  </select>
                  <input
                    aria-label={`填写 ${conflict.conflict_id} 的裁决说明`}
                    placeholder="填写事实依据与裁决说明"
                    value={conflictNotes[conflict.conflict_id] ?? ""}
                    onChange={(event) => setConflictNotes((items) => ({ ...items, [conflict.conflict_id]: event.target.value }))}
                  />
                  <button
                    className="airank-console-primary-button"
                    type="button"
                    disabled={resolvingConflictId === conflict.conflict_id}
                    onClick={() => void resolveConflict(conflict)}
                  >
                    {resolvingConflictId === conflict.conflict_id ? "保存中…" : "提交人工裁决"}
                  </button>
                </div>
              </article>
            ))}
          </div>
        </Panel>
      )}
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
            {item.status === "proposed" && (
              <div className="fact-review-actions">
                <button className="outline-button" type="button" disabled={reviewingRevisionId === item.revision_id} onClick={() => void reviewRevision(item, "rejected")}>驳回</button>
                <button className="airank-console-primary-button" type="button" disabled={reviewingRevisionId === item.revision_id} onClick={() => void reviewRevision(item, "approved")}>{reviewingRevisionId === item.revision_id ? "提交中…" : "批准事实"}</button>
              </div>
            )}
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
                <span>{source.valid_until ? `有效至 ${formatDateTime(source.valid_until)}` : "长期有效 · 无到期日"}</span>
                <Badge tone="primary">v{source.revision_number}</Badge>
                {source.status === "active" && <button className="table-action gap-row-action" type="button" onClick={() => openSourceEditor(source)}>更新来源</button>}
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

function EvidencePage() {
  const { project } = useConsoleOverview();
  const [runs, setRuns] = useState<ScanRun[]>([]);
  const [samples, setSamples] = useState<AnswerSample[]>([]);
  const [sampleSummary, setSampleSummary] = useState({
    total: 0,
    validCount: 0,
    validUnmentionedCount: 0,
    citationSampleCount: 0,
    limit: 200,
  });
  const [selected, setSelected] = useState<AnswerSampleDetail | null>(null);
  const [quality, setQuality] = useState<MeasurementQualityReport | null>(null);
  const [qualityError, setQualityError] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [loadingDetail, setLoadingDetail] = useState<string | null>(null);
  const [selectedRunId, setSelectedRunId] = useState("");
  const [objectPreviews, setObjectPreviews] = useState<{ screenshot: string | null; sourcePanel: string | null }>({ screenshot: null, sourcePanel: null });
  const [objectPreviewError, setObjectPreviewError] = useState<string | null>(null);
  const [citationSupport, setCitationSupport] = useState<CitationSupportBundle | null>(null);
  const [citationSupportError, setCitationSupportError] = useState<string | null>(null);
  const [citationCaptures, setCitationCaptures] = useState<Record<string, CitationSourceCapture[]>>({});
  const [citationAction, setCitationAction] = useState<string | null>(null);
  const [citationActionError, setCitationActionError] = useState<string | null>(null);

  useEffect(() => {
    if (!project.id) return;
    const controller = new AbortController();
    fetchScanRuns(project.id, controller.signal)
      .then((data) => {
        setRuns(data);
        setSelectedRunId((current) => data.some((run) => run.run_id === current) ? current : data[0]?.run_id || "");
        setLoadError(null);
      })
      .catch((error) => {
        if (controller.signal.aborted) return;
        setRuns([]);
        setSelectedRunId("");
        setLoadError(error instanceof Error ? error.message : "测量批次接口不可用");
      });
    return () => controller.abort();
  }, [project.id]);

  useEffect(() => {
    if (!project.id || !selectedRunId) {
      setSamples([]);
      setSampleSummary({ total: 0, validCount: 0, validUnmentionedCount: 0, citationSampleCount: 0, limit: 200 });
      return;
    }
    const controller = new AbortController();
    fetchAnswerSamples(project.id, selectedRunId, controller.signal)
      .then((collection) => {
        setSamples(collection.samples);
        setSampleSummary({
          total: collection.total,
          validCount: collection.validCount,
          validUnmentionedCount: collection.validUnmentionedCount,
          citationSampleCount: collection.citationSampleCount,
          limit: collection.limit,
        });
        setLoadError(null);
      })
      .catch((error) => {
        if (controller.signal.aborted) return;
        setSamples([]);
        setSampleSummary({ total: 0, validCount: 0, validUnmentionedCount: 0, citationSampleCount: 0, limit: 200 });
        setLoadError(error instanceof Error ? error.message : "证据样本接口不可用");
      });
    return () => controller.abort();
  }, [project.id, selectedRunId]);

  useEffect(() => {
    if (!project.id || !selectedRunId) {
      setQuality(null);
      setQualityError(null);
      return;
    }
    const controller = new AbortController();
    fetchMeasurementQuality(project.id, selectedRunId, controller.signal)
      .then((report) => {
        setQuality(report);
        setQualityError(null);
      })
      .catch((error) => {
        if (controller.signal.aborted) return;
        setQuality(null);
        setQualityError(error instanceof Error ? error.message : "质量报告接口不可用");
      });
    return () => controller.abort();
  }, [project.id, selectedRunId]);

  useEffect(() => {
    const controller = new AbortController();
    const createdUrls: string[] = [];
    let disposed = false;
    setObjectPreviews({ screenshot: null, sourcePanel: null });
    setObjectPreviewError(null);

    const loadPreview = async (kind: "screenshot" | "sourcePanel", objectRefId: string | null) => {
      if (!objectRefId) return;
      try {
        const blob = await fetchEvidenceObject(objectRefId, controller.signal);
        if (disposed) return;
        const objectUrl = URL.createObjectURL(blob);
        createdUrls.push(objectUrl);
        setObjectPreviews((current) => ({ ...current, [kind]: objectUrl }));
      } catch (error) {
        if (controller.signal.aborted) return;
        setObjectPreviewError(error instanceof Error ? error.message : "证据对象读取失败");
      }
    };

    void loadPreview("screenshot", selected?.screenshot.object_ref_id || null);
    void loadPreview("sourcePanel", selected?.source_panel.object_ref_id || null);
    return () => {
      disposed = true;
      controller.abort();
      createdUrls.forEach((url) => URL.revokeObjectURL(url));
    };
  }, [selected?.screenshot.object_ref_id, selected?.source_panel.object_ref_id]);

  useEffect(() => {
    if (!selected?.snapshot_id) {
      setCitationSupport(null);
      setCitationSupportError(null);
      return;
    }
    const controller = new AbortController();
    fetchCitationSupport(selected.snapshot_id, controller.signal)
      .then((data) => {
        setCitationSupport(data);
        setCitationSupportError(null);
      })
      .catch((error) => {
        if (controller.signal.aborted) return;
        setCitationSupport(null);
        setCitationSupportError(error instanceof Error ? error.message : "引用支持度接口不可用");
      });
    return () => controller.abort();
  }, [selected?.snapshot_id]);

  useEffect(() => {
    const citations = selected?.citations ?? [];
    if (citations.length === 0) {
      setCitationCaptures({});
      setCitationActionError(null);
      return;
    }
    const controller = new AbortController();
    Promise.all(
      citations.map(async (citation) => {
        const rows = await fetchCitationSourceCaptures(citation.citation_id, controller.signal);
        if (rows[0]) {
          const detail = await fetchCitationSourceCapture(rows[0].capture_id, controller.signal);
          return [citation.citation_id, [detail, ...rows.slice(1)]] as const;
        }
        return [citation.citation_id, []] as const;
      }),
    )
      .then((entries) => {
        setCitationCaptures(Object.fromEntries(entries));
        setCitationActionError(null);
      })
      .catch((error) => {
        if (controller.signal.aborted) return;
        setCitationCaptures({});
        setCitationActionError(error instanceof Error ? error.message : "引用来源抓取接口不可用");
      });
    return () => controller.abort();
  }, [selected?.citations]);

  const openSample = async (snapshotId: string) => {
    setLoadingDetail(snapshotId);
    setDetailError(null);
    try {
      setSelected(await fetchAnswerSample(snapshotId));
    } catch (error) {
      setDetailError(error instanceof Error ? error.message : "样本详情接口不可用");
    } finally {
      setLoadingDetail(null);
    }
  };
  const reloadCitationCapture = async (citationId: string, captureId?: string) => {
    const rows = await fetchCitationSourceCaptures(citationId);
    const detailId = captureId || rows[0]?.capture_id;
    const detail = detailId ? await fetchCitationSourceCapture(detailId) : null;
    const withoutDetail = detail ? rows.filter((row) => row.capture_id !== detail.capture_id) : rows;
    setCitationCaptures((current) => ({
      ...current,
      [citationId]: detail ? [detail, ...withoutDetail] : rows,
    }));
  };
  const refreshCitationSupport = async () => {
    if (!selected?.snapshot_id) return;
    setCitationSupport(await fetchCitationSupport(selected.snapshot_id));
  };
  const registerFullAnswerClaim = async () => {
    if (!selected || selected.sample_status !== "valid" || !selected.answer_text.trim()) return;
    setCitationAction("claim");
    setCitationActionError(null);
    try {
      await createCitationClaim(selected.snapshot_id, 0, selected.answer_text.length);
      await refreshCitationSupport();
    } catch (error) {
      setCitationActionError(error instanceof Error ? error.message : "回答断言登记失败");
    } finally {
      setCitationAction(null);
    }
  };
  const startCitationCapture = async (citationId: string) => {
    setCitationAction(`capture:${citationId}`);
    setCitationActionError(null);
    try {
      const created = await createCitationSourceCapture(citationId);
      await reloadCitationCapture(citationId, created.capture_id);
    } catch (error) {
      setCitationActionError(error instanceof Error ? error.message : "引用来源抓取创建失败");
    } finally {
      setCitationAction(null);
    }
  };
  const reviewCitationSegment = async (
    citationId: string,
    capture: CitationSourceCapture,
    segment: CitationSourceCapture["segments"][number],
    supportLabel: "supports" | "contradicts" | "insufficient",
  ) => {
    const claim = citationSupport?.claims[0];
    if (!claim || !capture.content_sha256 || !capture.raw_object_ref_id) {
      setCitationActionError("请先登记回答断言，并等待来源抓取完成后再复核。");
      return;
    }
    setCitationAction(`review:${citationId}:${supportLabel}`);
    setCitationActionError(null);
    try {
      await createCitationSupportReview(claim.claim_id, {
        citationId,
        supportLabel,
        sourceExcerpt: segment.segment_text,
        sourceContentSha256: capture.content_sha256,
        sourceObjectRefId: capture.raw_object_ref_id,
        sourceCaptureId: capture.capture_id,
        sourceSegmentId: segment.segment_id,
        sourceStart: segment.source_start,
        sourceEnd: segment.source_end,
      });
      await refreshCitationSupport();
    } catch (error) {
      setCitationActionError(error instanceof Error ? error.message : "引用支持度复核失败");
    } finally {
      setCitationAction(null);
    }
  };
  const selectedProviderRequest = selected?.request_metadata.provider_request;
  const selectedSourcePanelStatus = selectedProviderRequest
    && typeof selectedProviderRequest === "object"
    && "source_panel_status" in selectedProviderRequest
    && typeof selectedProviderRequest.source_panel_status === "string"
      ? selectedProviderRequest.source_panel_status
      : null;

  return (
    <>
      <PageHeader title="证据中心" subtitle="从指标下钻到不可变回答、真实引用、请求元数据与证据对象；未提及样本同样保留并计入分母。" />
      <div className="evidence-toolbar">
        <label>测量批次<select value={selectedRunId} onChange={(event) => { setSelectedRunId(event.target.value); setSelected(null); }}>{runs.map((run) => <option value={run.run_id} key={run.run_id}>{run.run_id} · {run.status}</option>)}</select></label>
        <span>顶部统计由服务端按完整批次聚合，不跨 run 混算；表格显示最近 {samples.length}/{sampleSummary.total} 条。</span>
      </div>
      {quality && (
        <Panel title={`测量质量门禁 · ${quality.publishable ? "可交付" : "已阻断"}`}>
          <DataStateCard
            title={quality.publishable ? "样本证据通过质量门禁" : "样本证据不可作为客户报告交付"}
            desc={quality.publishable
              ? `报告 ${quality.report_sha256.slice(0, 12)}… 可按当前契约重算；API、Web、App 与人工导入仍按各自证据等级统计。`
              : quality.checks.filter((check) => check.status === "blocked").map((check) => check.detail).join("；")}
            tone={quality.publishable ? "success" : "danger"}
          />
          <div className="airank-console-card table-card evidence-table-wrap">
            <table className="question-table evidence-table">
              <thead><tr><th>采集面 / 等级</th><th>样本</th><th>有效</th><th>有效证据完整</th><th>有效截图</th><th>有效来源面板</th><th>有效证据缺口</th></tr></thead>
              <tbody>
                {quality.surface_evidence.map((surface) => (
                  <tr key={surface.surface}>
                    <td><strong>{surface.surface}</strong><small>{surface.evidence_level}</small></td>
                    <td>{surface.sample_count}</td>
                    <td>{surface.valid_sample_count}</td>
                    <td>{surface.evidence_complete_count}</td>
                    <td>{surface.screenshot_count}</td>
                    <td>{surface.source_panel_captured_count} 已捕获<small>{surface.source_panel_not_present_count} 明确无面板</small></td>
                    <td><Badge tone={surface.blocker_count === 0 ? "success" : "danger"}>{surface.blocker_count}</Badge></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {quality.known_limitations.length > 0 && <p className="rail-caption">已知限制：{quality.known_limitations.map((item) => qualityLimitationLabels[item] ?? item).join(" · ")}</p>}
        </Panel>
      )}
      {qualityError && <DataStateCard title="当前批次尚无可重算质量报告" desc={qualityError} tone="warning" />}
      <section className="summary-band evidence-summary">
        <SummaryMetric label="样本总数" value={String(sampleSummary.total)} tone="primary" />
        <SummaryMetric label="有效样本" value={String(sampleSummary.validCount)} tone="success" />
        <SummaryMetric label="有效未提及" value={String(sampleSummary.validUnmentionedCount)} tone="warning" />
        <SummaryMetric label="含原生引用" value={String(sampleSummary.citationSampleCount)} tone="primary" />
      </section>
      {loadError && <DataStateCard title="证据中心读取失败" desc={loadError} tone="danger" />}
      {!loadError && sampleSummary.total === 0 && <DataStateCard title="尚无回答证据" desc="完成真实 Provider 采样后，这里会保存原始回答、引用、截图对象、采集面和哈希；系统不会用演示样本补位。" tone="warning" />}
      {samples.length > 0 && (
        <div className="airank-console-card table-card evidence-table-wrap">
          <table className="question-table evidence-table">
            <thead><tr><th>平台 / 采集面</th><th>测试类型</th><th>样本状态</th><th>品牌结果</th><th>引用</th><th>采集时间</th><th>证据</th></tr></thead>
            <tbody>
              {samples.map((sample) => (
                <tr key={sample.snapshot_id}>
                  <td><strong>{sample.provider}</strong><small>{sample.collector_surface} · {sample.model_name || "模型未记录"}</small></td>
                  <td><Badge tone="primary">{sample.cohort_type}</Badge><small>#{sample.sample_index} · {sample.prompt_version_id}</small></td>
                  <td><Badge tone={sample.sample_status === "valid" ? "success" : sample.sample_status === "failed" ? "danger" : "warning"}>{sample.sample_status}</Badge></td>
                  <td>{sample.sample_status === "valid" ? <><strong>{sample.brand_mentioned ? sample.mention_class : "未提及"}</strong><small>{sample.brand_rank ? `排名 ${sample.brand_rank}` : "无条件排名"}</small></> : <><strong>{sample.sample_status === "blocked" ? "阻塞，不计品牌分类" : "失败，不计品牌分类"}</strong><small>保留失败证据，不进入可见度分母</small></>}</td>
                  <td>{sample.citation_count}</td>
                  <td>{formatDateTime(sample.created_at)}</td>
                  <td><button className="table-action" type="button" disabled={loadingDetail === sample.snapshot_id} onClick={() => void openSample(sample.snapshot_id)}>{loadingDetail === sample.snapshot_id ? "读取中" : "下钻"}</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {detailError && <DataStateCard title="样本详情读取失败" desc={detailError} tone="danger" />}
      {selected && (
        <section className="evidence-detail-grid">
          <Panel title={selected.sample_status === "valid" ? "不可变原始回答" : "不可变失败证据"}>
            {selected.sample_status === "valid"
              ? <div className="evidence-answer">{selected.answer_text}</div>
              : <DataStateCard title="该任务没有有效回答" desc="系统保留了不可变失败快照、请求元数据和可用的阻塞截图；该样本不会被误算为品牌未提及。" tone={selected.sample_status === "blocked" ? "warning" : "danger"} />}
            <dl className="evidence-metadata">
              <div><dt>回答 SHA-256</dt><dd>{selected.answer_sha256 || "不适用（失败/阻塞样本）"}</dd></div>
              <div><dt>原始响应 SHA-256</dt><dd>{selected.raw_response_sha256}</dd></div>
              <div><dt>Evidence Snapshot</dt><dd>{selected.evidence_snapshot_id}</dd></div>
              <div><dt>采集时间</dt><dd>{formatDateTime(selected.evidence_captured_at)}</dd></div>
              <div><dt>会话</dt><dd>{selected.session_id}</dd></div>
              <div><dt>证据等级</dt><dd>{selected.evidence_level}</dd></div>
            </dl>
          </Panel>
          <Panel title={`${selected.sample_status === "valid" ? "真实引用" : "失败任务引用"}（${selected.citations.length}）`}>
            {selected.citations.length === 0 ? <DataStateCard title="该样本没有原生引用" desc={selected.sample_status === "valid" ? "无引用是有效证据状态，不补造来源。" : "任务未产生有效回答，不把空引用误写成有效证据结论。"} tone="warning" /> : (
              <ol className="evidence-citations">
                {selected.citations.map((citation) => {
                  const capture = citationCaptures[citation.citation_id]?.[0];
                  return (
                    <li key={citation.citation_id} className="citation-evidence-item">
                      <a href={citation.url} target="_blank" rel="noreferrer">{citation.title || citation.host || citation.url}<ExternalLink size={14} /></a>
                      <span>{citation.cited_text || "Provider 未返回引用原文"}</span>
                      <div className="citation-capture-toolbar">
                        <Badge tone={capture?.status === "completed" ? "success" : capture?.status === "blocked" || capture?.status === "failed" ? "danger" : "warning"}>
                          {capture ? `来源抓取 ${capture.status}` : "来源页未抓取"}
                        </Badge>
                        <button
                          className="table-action"
                          type="button"
                          disabled={citationAction === `capture:${citation.citation_id}`}
                          onClick={() => void startCitationCapture(citation.citation_id)}
                        >
                          {citationAction === `capture:${citation.citation_id}` ? "入队中" : capture ? "重新抓取" : "抓取来源页"}
                        </button>
                        {capture && capture.status !== "completed" && (
                          <button className="table-action" type="button" onClick={() => void reloadCitationCapture(citation.citation_id, capture.capture_id)}>
                            <RotateCw size={13} />刷新状态
                          </button>
                        )}
                      </div>
                      {capture?.status === "completed" && (
                        <details className="citation-source-capture">
                          <summary>查看不可变来源正文与审核入口</summary>
                          <dl className="evidence-metadata citation-capture-metadata">
                            <div><dt>内容 SHA-256</dt><dd>{capture.content_sha256}</dd></div>
                            <div><dt>抓取网络证据</dt><dd>{capture.connected_ip} · {capture.evidence_grade}</dd></div>
                            <div><dt>最终 URL</dt><dd>{capture.final_url}</dd></div>
                            <div><dt>片段数量</dt><dd>{capture.segments.length}</dd></div>
                          </dl>
                          {capture.segments.map((segment) => (
                            <article className="citation-source-segment" key={segment.segment_id}>
                              <small>原文边界 {segment.source_start}–{segment.source_end} · {segment.segment_sha256.slice(0, 12)}…</small>
                              <p>{segment.segment_text}</p>
                              <div className="citation-review-actions">
                                <button type="button" className="table-action" disabled={!citationSupport?.claims.length || citationAction?.startsWith(`review:${citation.citation_id}`)} onClick={() => void reviewCitationSegment(citation.citation_id, capture, segment, "supports")}>人工确认支持</button>
                                <button type="button" className="table-action" disabled={!citationSupport?.claims.length || citationAction?.startsWith(`review:${citation.citation_id}`)} onClick={() => void reviewCitationSegment(citation.citation_id, capture, segment, "contradicts")}>人工确认矛盾</button>
                                <button type="button" className="table-action" disabled={!citationSupport?.claims.length || citationAction?.startsWith(`review:${citation.citation_id}`)} onClick={() => void reviewCitationSegment(citation.citation_id, capture, segment, "insufficient")}>证据不足</button>
                              </div>
                            </article>
                          ))}
                        </details>
                      )}
                      {capture && capture.status !== "completed" && capture.error_code && <span className="citation-capture-error">{capture.error_code} · {capture.error_message || "抓取未完成"}</span>}
                    </li>
                  );
                })}
              </ol>
            )}
            <div className="citation-support-separator" />
            <strong>引用选择 ≠ 引用支持</strong>
            {citationActionError && <DataStateCard title="引用证据操作失败" desc={citationActionError} tone="danger" />}
            {citationSupportError && <DataStateCard title="引用支持度读取失败" desc={citationSupportError} tone="danger" />}
            {citationSupport && (
              <>
                <p className="rail-caption">
                  Provider 列出 {citationSupport.metrics.selected_citation_count} 个来源；已登记 {citationSupport.metrics.claim_count} 条回答断言，
                  当前有 {citationSupport.metrics.commercially_verified_review_count} 个“人工核对 + 不可变来源页面”复核可进入支持率。
                </p>
                <dl className="evidence-metadata citation-support-metrics">
                  <div><dt>可交付支持率</dt><dd>{citationSupport.metrics.citation_support_rate === null ? "待核验" : `${Math.round(citationSupport.metrics.citation_support_rate * 100)}%`}</dd></div>
                  <div><dt>支持 / 矛盾 / 不足</dt><dd>{citationSupport.metrics.supports_count} / {citationSupport.metrics.contradicts_count} / {citationSupport.metrics.insufficient_count}</dd></div>
                  <div><dt>当前复核对</dt><dd>{citationSupport.metrics.review_count}</dd></div>
                </dl>
                {citationSupport.metrics.known_limitations.length > 0 && (
                  <DataStateCard
                    title="引用支持度尚不可用于客户报告"
                    desc={citationSupport.metrics.known_limitations.map((item) => citationSupportLimitationLabels[item] ?? item).join(" · ")}
                    tone="warning"
                  />
                )}
                {selected.sample_status === "valid" && citationSupport.claims.length === 0 && (
                  <button className="primary-button citation-claim-button" type="button" disabled={citationAction === "claim"} onClick={() => void registerFullAnswerClaim()}>
                    {citationAction === "claim" ? "登记中" : "登记整段回答为待核验断言"}
                  </button>
                )}
                {citationSupport.claims.length > 0 && (
                  <ol className="evidence-citations citation-claims">
                    {citationSupport.claims.map((claim) => (
                      <li key={claim.claim_id}><strong>{claim.claim_text}</strong><span>回答边界 {claim.answer_start}–{claim.answer_end} · {claim.extraction_method}</span></li>
                    ))}
                  </ol>
                )}
              </>
            )}
          </Panel>
          <Panel title="采集与对象证据">
            <dl className="evidence-metadata">
              <div><dt>联网状态</dt><dd>{selected.search_enabled === null ? "未记录" : selected.search_enabled ? "已联网" : "未联网"}</dd></div>
              <div><dt>外部请求 ID</dt><dd>{selected.external_trace_id || "未返回"}</dd></div>
              <div><dt>截图对象</dt><dd>{selected.screenshot.object_ref_id || "未采集"}</dd></div>
              <div><dt>来源面板状态</dt><dd>{selectedSourcePanelStatus ? sourcePanelStatusLabels[selectedSourcePanelStatus] ?? selectedSourcePanelStatus : "未记录"}</dd></div>
              <div><dt>来源面板对象</dt><dd>{selected.source_panel.object_ref_id || "未采集"}</dd></div>
            </dl>
            {objectPreviewError && <DataStateCard title="证据对象读取失败" desc={objectPreviewError} tone="danger" />}
            {objectPreviews.screenshot && <figure className="evidence-object-preview"><img src={objectPreviews.screenshot} alt={selected.sample_status === "valid" ? "Provider 回答截图证据" : "Provider 失败现场截图证据"} /><figcaption>{selected.sample_status === "valid" ? "回答截图" : "失败现场截图"} · 服务端读取时已复验 SHA-256</figcaption></figure>}
            {objectPreviews.sourcePanel && <figure className="evidence-object-preview"><img src={objectPreviews.sourcePanel} alt="Provider 来源面板截图证据" /><figcaption>来源面板截图 · 服务端读取时已复验 SHA-256</figcaption></figure>}
            <details className="evidence-json"><summary>查看请求元数据</summary><pre>{JSON.stringify(selected.request_metadata, null, 2)}</pre></details>
            <details className="evidence-json"><summary>查看原始响应</summary><pre>{JSON.stringify(selected.raw_response, null, 2)}</pre></details>
          </Panel>
          <Panel title={`Worker 尝试链（${selected.attempts.length}）`}>
            {selected.attempts.length === 0 ? (
              <DataStateCard title="无 Worker attempt 记录" desc="这是迁移前或人工导入样本；系统不会为历史数据补造执行记录。" tone="warning" />
            ) : (
              <div className="airank-console-card table-card evidence-table-wrap">
                <table className="question-table evidence-table">
                  <thead><tr><th>Attempt</th><th>状态</th><th>Job / 请求</th><th>时间</th><th>结果</th></tr></thead>
                  <tbody>
                    {selected.attempts.map((attempt) => (
                      <tr key={attempt.attempt_id}>
                        <td><strong>#{attempt.attempt_number}</strong><small>{attempt.provider} · {attempt.collector_surface}</small></td>
                        <td><Badge tone={attempt.status === "succeeded" ? "success" : attempt.status === "running" ? "primary" : attempt.status === "blocked" ? "warning" : "danger"}>{attempt.status}</Badge></td>
                        <td><strong>{attempt.job_id}</strong><small>{attempt.provider_request_id || "无外部请求 ID"}</small></td>
                        <td>{formatDateTime(attempt.started_at)}<small>{attempt.completed_at ? `结束 ${formatDateTime(attempt.completed_at)}` : "尚未结束"}</small></td>
                        <td>{attempt.error_code ? <><strong>{attempt.error_code}</strong><small>{attempt.error_message || "无错误详情"}</small></> : <><strong>{attempt.evidence_snapshot_id || "待落证据"}</strong><small>{attempt.answer_snapshot_id || "无回答快照"}</small></>}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Panel>
        </section>
      )}
    </>
  );
}

function TaskCenterPage() {
  const { project } = useConsoleOverview();
  const [runs, setRuns] = useState<ScanRun[]>([]);
  const [selectedRunId, setSelectedRunId] = useState("");
  const [tasks, setTasks] = useState<ScanTask[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    if (!project.id) return;
    const controller = new AbortController();
    const loadRuns = () => {
      void fetchScanRuns(project.id, controller.signal)
        .then((data) => {
          setRuns(data);
          setSelectedRunId((current) => current || data[0]?.run_id || "");
          setLoadError(null);
        })
        .catch((error) => {
          if (controller.signal.aborted) return;
          setLoadError(error instanceof Error ? error.message : "测量任务接口不可用");
        });
    };
    loadRuns();
    const poll = window.setInterval(loadRuns, 5000);
    return () => {
      window.clearInterval(poll);
      controller.abort();
    };
  }, [project.id]);

  useEffect(() => {
    if (!selectedRunId) {
      setTasks([]);
      return;
    }
    const controller = new AbortController();
    const loadTasks = () => {
      void fetchScanTasks(selectedRunId, controller.signal)
        .then((data) => {
          setTasks(data);
          setLoadError(null);
        })
        .catch((error) => {
          if (controller.signal.aborted) return;
          setLoadError(error instanceof Error ? error.message : "任务明细接口不可用");
        });
    };
    loadTasks();
    const poll = window.setInterval(loadTasks, 3000);
    return () => {
      window.clearInterval(poll);
      controller.abort();
    };
  }, [selectedRunId]);

  const selectedRun = runs.find((run) => run.run_id === selectedRunId);
  const completed = tasks.filter((task) => task.status === "completed").length;
  const failed = tasks.filter((task) => task.status === "failed").length;
  const active = tasks.filter((task) => task.status === "queued" || task.status === "running").length;

  return (
    <>
      <PageHeader title="任务中心" subtitle="按测量批次查看每个平台、采集面、会话和重复样本的真实执行状态；失败、阻塞和未提及不会相互替代。" />
      <div className="evidence-toolbar">
        <label>测量批次<select value={selectedRunId} onChange={(event) => setSelectedRunId(event.target.value)}>{runs.map((run) => <option value={run.run_id} key={run.run_id}>{run.name || run.run_id} · {run.status}</option>)}</select></label>
        <span>{selectedRun ? `${selectedRun.cohort_type} · ${selectedRun.collector_surfaces.join("/")} · 重复 ${selectedRun.repetitions} 次` : "暂无批次"}</span>
      </div>
      <section className="summary-band evidence-summary">
        <SummaryMetric label="任务总数" value={String(tasks.length)} tone="primary" />
        <SummaryMetric label="已完成" value={String(completed)} tone="success" />
        <SummaryMetric label="失败/阻塞" value={String(failed)} tone="warning" />
        <SummaryMetric label="排队/运行" value={String(active)} tone="primary" />
      </section>
      {loadError && <DataStateCard title="任务中心读取失败" desc={loadError} tone="danger" />}
      {!loadError && runs.length === 0 && <DataStateCard title="尚无测量任务" desc="提交品牌检测后，系统会在这里保留每个独立会话任务及其结构化失败原因。" tone="warning" />}
      {tasks.length > 0 && (
        <div className="airank-console-card table-card">
          <table className="question-table task-table"><thead><tr><th>Provider</th><th>采集契约</th><th>样本</th><th>状态</th><th>错误/阻塞原因</th><th>完成时间</th></tr></thead><tbody>
            {tasks.map((task) => <tr key={task.task_id}><td><strong>{task.provider}</strong><small>{task.task_id}</small></td><td><strong>{task.collector_surface}</strong><small>{task.evidence_level} · {task.cohort_type}</small></td><td>#{task.sample_index}<small>{task.session_id}</small></td><td><Badge tone={task.status === "completed" ? "success" : task.status === "failed" ? "danger" : "warning"}>{task.status}</Badge></td><td>{task.error ? <><strong>{task.error.code}</strong><small>{task.error.message}</small></> : "—"}</td><td>{task.finished_at ? formatDateTime(task.finished_at) : "未完成"}</td></tr>)}
          </tbody></table>
        </div>
      )}
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
  const [observationBatches, setObservationBatches] = useState<QuestionObservationBatch[]>([]);
  const [selectedObservationBatchIds, setSelectedObservationBatchIds] = useState<string[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [observationSourceType, setObservationSourceType] = useState<QuestionObservationBatch["source_type"]>("site_search");
  const [observationSourceName, setObservationSourceName] = useState("");
  const [observationRows, setObservationRows] = useState("");
  const [observationRightsAttested, setObservationRightsAttested] = useState(false);
  const [importingObservations, setImportingObservations] = useState(false);
  const [observationError, setObservationError] = useState<string | null>(null);
  const [observationNotice, setObservationNotice] = useState<string | null>(null);
  const [seedQuestions, setSeedQuestions] = useState("");
  const [productTerms, setProductTerms] = useState("");
  const [competitorNames, setCompetitorNames] = useState("");
  const [regions, setRegions] = useState("");
  const [includeTemplates, setIncludeTemplates] = useState(true);
  const [compiling, setCompiling] = useState(false);
  const [compileError, setCompileError] = useState<string | null>(null);
  const [compileResult, setCompileResult] = useState<QuestionMapResult | null>(null);
  const [reviewingQuestionId, setReviewingQuestionId] = useState<string | null>(null);
  const [reviewError, setReviewError] = useState<string | null>(null);
  const tabs = ["全部问题", "购买", "对比", "选型", "信任", "价格", "风险", "场景", "本地", "替代"];
  const tabTypes = ["", "purchase", "compare", "select", "trust", "price", "risk", "scenario", "local", "alternative"];
  const [selectedTab, setSelectedTab] = useState(0);

  const loadQuestions = useCallback(async (signal?: AbortSignal) => {
    if (!project.id) return;
    try {
      const data = await fetchBuyerQuestions(project.id, signal);
      setQuestions(data);
      setLoadError(null);
    } catch (error) {
      if (signal?.aborted) return;
      setLoadError(error instanceof Error ? error.message : "买家问题接口不可用");
    }
  }, [project.id]);

  const loadObservationBatches = useCallback(async (signal?: AbortSignal) => {
    if (!project.id) return;
    try {
      const data = await fetchQuestionObservationBatches(project.id, signal);
      setObservationBatches(data);
      setSelectedObservationBatchIds((current) => current.filter((batchId) => data.some((item) => item.batch_id === batchId)));
    } catch (error) {
      if (signal?.aborted) return;
      setObservationError(error instanceof Error ? error.message : "观察数据批次读取失败");
    }
  }, [project.id]);

  useEffect(() => {
    if (!project.id) return;
    const controller = new AbortController();
    void loadQuestions(controller.signal);
    void loadObservationBatches(controller.signal);
    return () => controller.abort();
  }, [loadObservationBatches, loadQuestions, project.id]);

  const splitQuestionInput = (value: string) => value
    .split(/[\n,，]/)
    .map((item) => item.trim())
    .filter(Boolean);

  const handleObservationImport = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!project.id) return;
    const records = splitLines(observationRows).map((line, index) => {
      const [questionText = "", rawCount = "1", region = ""] = line.split("|").map((item) => item.trim());
      const parsedCount = rawCount ? Number(rawCount) : 1;
      return {
        lineNumber: index + 1,
        sourceRecordId: `console-row-${index + 1}`,
        questionText,
        occurrenceCount: parsedCount,
        region: region || undefined,
      };
    }).filter((item) => item.questionText.length >= 4);
    if (!observationSourceName.trim() || records.length === 0) {
      setObservationError("请填写来源名称，并至少录入一条不少于 4 个字符的观察问题。");
      return;
    }
    const invalidCount = records.find((item) => !Number.isInteger(item.occurrenceCount) || item.occurrenceCount < 1 || item.occurrenceCount > 1_000_000);
    if (invalidCount) {
      setObservationError(`第 ${invalidCount.lineNumber} 行的来源内出现次数必须是 1—1000000 的整数。`);
      return;
    }
    if (!observationRightsAttested) {
      setObservationError("必须确认数据来源已获授权，AIRank 才会保存不可变观察快照。");
      return;
    }
    setImportingObservations(true);
    setObservationError(null);
    setObservationNotice(null);
    try {
      const result = await importQuestionObservations(project.id, {
        sourceType: observationSourceType,
        sourceName: observationSourceName.trim(),
        records: records.map((item) => ({
          sourceRecordId: item.sourceRecordId,
          questionText: item.questionText,
          occurrenceCount: item.occurrenceCount,
          region: item.region,
        })),
        rightsAttested: observationRightsAttested,
      });
      setSelectedObservationBatchIds((current) => Array.from(new Set([...current, result.batch.batch_id])));
      setObservationNotice(
        `已保存 ${result.batch.record_count} 条客户提供记录；${result.batch.pii_blocked_count} 条因疑似个人信息未落原文。频次仅代表该来源记录，不等于搜索量。`,
      );
      setObservationRows("");
      await loadObservationBatches();
      void recordAction({
        actionType: "question.observation_import",
        label: "导入买家问题观察批次",
        entityType: "question_observation_batch",
        entityId: result.batch.batch_id,
        payload: {
          record_count: result.batch.record_count,
          pii_blocked_count: result.batch.pii_blocked_count,
          evidence_grade: result.batch.evidence_grade,
        },
      });
    } catch (error) {
      setObservationError(error instanceof Error ? error.message : "观察数据导入失败");
    } finally {
      setImportingObservations(false);
    }
  };

  const toggleObservationBatch = (batchId: string) => {
    setSelectedObservationBatchIds((current) => current.includes(batchId)
      ? current.filter((item) => item !== batchId)
      : [...current, batchId]);
  };

  const handleCompile = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!project.id) return;
    const seeds = splitLines(seedQuestions);
    const products = splitQuestionInput(productTerms);
    if (seeds.length === 0 && products.length === 0 && selectedObservationBatchIds.length === 0) {
      setCompileError("至少填写一个种子问题、产品/服务词或选择一个观察批次。系统不会凭空生成问题。");
      return;
    }
    setCompiling(true);
    setCompileError(null);
    try {
      const result = await compileQuestionMap(project.id, {
        productTerms: products,
        competitorNames: splitQuestionInput(competitorNames),
        regions: splitQuestionInput(regions),
        seedQuestions: seeds,
        observationBatchIds: selectedObservationBatchIds,
        includeTemplateCandidates: includeTemplates,
      });
      setCompileResult(result);
      await loadQuestions();
      void recordAction({
        actionType: "question.map_compile",
        label: "编译买家问题地图",
        entityType: "question_map",
        entityId: result.map_id,
        payload: {
          map_version_id: result.map_version_id,
          persisted_count: result.persisted_count,
          duplicate_count: result.duplicate_count,
        },
      });
    } catch (error) {
      setCompileError(error instanceof Error ? error.message : "问题地图编译失败");
    } finally {
      setCompiling(false);
    }
  };

  const confirmQuestion = async (row: BuyerQuestion) => {
    if (!project.id) return;
    setReviewingQuestionId(row.question_id);
    setReviewError(null);
    try {
      await reviewBuyerQuestion(
        project.id,
        row.question_id,
        "confirmed",
        "控制台人工确认：问题意图、Cohort 与目标客户匹配。",
      );
      await loadQuestions();
    } catch (error) {
      setReviewError(error instanceof Error ? error.message : "问题确认失败");
    } finally {
      setReviewingQuestionId(null);
    }
  };

  const visibleRows = showTabs && selectedTab > 0
    ? questions.filter((row) => row.question_type === tabTypes[selectedTab])
    : questions;
  const gapRows = questions.filter((row) => row.coverage_status === "gap" || row.coverage_status === "needs_scan");
  const confirmedCount = questions.filter((row) => row.status === "confirmed").length;
  const suggestedCount = questions.filter((row) => row.status === "suggested").length;
  const observedCount = questions.filter((row) => row.observed_query).length;

  return (
    <>
      {showTabs && (
        <section className="airank-console-card question-compiler-card">
          <div className="question-compiler-heading">
            <div>
              <span className="section-kicker">Research Intent Skill · v1.2</span>
              <h2>编译买家问题地图</h2>
              <p>种子问题保留为 provided_seed；规则扩展只标记为 template_candidate，不冒充真实用户搜索或搜索量。</p>
            </div>
            <Badge tone="primary">{compileResult?.taxonomy_version ?? "等待输入"}</Badge>
          </div>
          <div className="question-observation-panel">
            <div className="question-observation-heading">
              <div>
                <span className="section-kicker">M1 · 用户提供观察数据</span>
                <h3>导入真实问题来源</h3>
                <p>每行格式：问题 | 来源内出现次数 | 地区。系统保存内容 hash 和来源批次；次数不是搜索量，当前证据未经过独立连接器核验。</p>
              </div>
              <Badge tone="warning">user_provided_snapshot</Badge>
            </div>
            <form className="question-observation-form" onSubmit={handleObservationImport}>
              <label>
                来源类型
                <select value={observationSourceType} onChange={(event) => setObservationSourceType(event.target.value as QuestionObservationBatch["source_type"])}>
                  <option value="site_search">站内搜索</option>
                  <option value="search_console">Search Console</option>
                  <option value="customer_support">客服问题</option>
                  <option value="crm_sales">CRM / 销售访谈</option>
                  <option value="advertising_query">投放搜索词</option>
                  <option value="community_comment">社群 / 评论</option>
                  <option value="provider_sample">AI 平台采样问题</option>
                  <option value="other">其他授权来源</option>
                </select>
              </label>
              <label>
                来源名称
                <input value={observationSourceName} onChange={(event) => setObservationSourceName(event.target.value)} placeholder="例如：官网站内搜索导出 2026-08" />
              </label>
              <label className="question-observation-wide">
                观察问题
                <textarea value={observationRows} onChange={(event) => setObservationRows(event.target.value)} placeholder="制造企业如何选择 GEO 平台？ | 7 | 上海&#10;GEO 监测是否支持原始回答追溯？ | 3 | 北京" />
              </label>
              <div className="question-observation-actions">
                <label className="question-template-toggle">
                  <input type="checkbox" checked={observationRightsAttested} onChange={(event) => setObservationRightsAttested(event.target.checked)} />
                  我确认数据来源已获授权且可用于问题研究
                </label>
                <button className="ghost-button" type="submit" disabled={importingObservations}>{importingObservations ? "保存并检查中…" : "保存观察批次"}</button>
              </div>
            </form>
            {observationError && <p className="question-governance-error">{observationError}</p>}
            {observationNotice && <p className="question-observation-notice">{observationNotice}</p>}
            {observationBatches.length > 0 && (
              <div className="question-observation-batches">
                {observationBatches.map((batch) => (
                  <label className="question-observation-batch" data-status={batch.status} key={batch.batch_id}>
                    <input
                      type="checkbox"
                      checked={selectedObservationBatchIds.includes(batch.batch_id)}
                      disabled={batch.status !== "ready"}
                      onChange={() => toggleObservationBatch(batch.batch_id)}
                    />
                    <span>
                      <strong>{batch.source_name}</strong>
                      <small>{batch.record_count} 条可用 · 来源内频次 {batch.occurrence_count} · PII 拦截 {batch.pii_blocked_count}</small>
                    </span>
                    <span className="question-observation-proof" title={batch.payload_sha256}>{batch.evidence_grade}<small>{batch.payload_sha256.slice(0, 10)}</small></span>
                  </label>
                ))}
              </div>
            )}
          </div>
          <form className="question-compiler-form" onSubmit={handleCompile}>
            <label className="question-compiler-wide">
              种子问题（每行一个）
              <textarea value={seedQuestions} onChange={(event) => setSeedQuestions(event.target.value)} placeholder="企业应该如何选择 GEO 监测服务商？&#10;AIRank 是否支持样本级证据追溯？" />
            </label>
            <label>产品 / 服务词<input value={productTerms} onChange={(event) => setProductTerms(event.target.value)} placeholder="GEO 监测平台，AI 可见度诊断" /></label>
            <label>竞品实体<input value={competitorNames} onChange={(event) => setCompetitorNames(event.target.value)} placeholder="竞品甲，竞品乙" /></label>
            <label>服务区域<input value={regions} onChange={(event) => setRegions(event.target.value)} placeholder="北京，上海" /></label>
            <div className="question-compiler-actions">
              <label className="question-template-toggle">
                <input type="checkbox" checked={includeTemplates} onChange={(event) => setIncludeTemplates(event.target.checked)} />
                生成可审核的模板候选
              </label>
              {selectedObservationBatchIds.length > 0 && <Badge tone="success">已选 {selectedObservationBatchIds.length} 个观察批次</Badge>}
              <button className="airank-console-primary-button" type="submit" disabled={compiling}>{compiling ? "编译并去重中…" : "编译并保存候选"}</button>
            </div>
          </form>
          {compileError && <p className="question-governance-error">{compileError}</p>}
          {compileResult && (
            <div className="question-compile-result">
              <span><strong>{compileResult.question_count}</strong> 个唯一问题</span>
              <span><strong>{compileResult.persisted_count}</strong> 个已保存候选</span>
              <span><strong>{compileResult.duplicate_count}</strong> 个重复被拦截</span>
              <span title={compileResult.map_version_id}>版本 {compileResult.map_version_id.slice(-8)}</span>
              {compileResult.idempotent_replay && <Badge tone="muted">幂等回放</Badge>}
            </div>
          )}
        </section>
      )}
      <section className="content-with-rail">
        <div>
          {showTabs && (
            <div className="tab-row">
              {tabs.map((item, index) => (
                <button className="tab-button" data-active={index === selectedTab} type="button" key={item} onClick={() => {
                  void recordAction({
                    actionType: "question.tab_select",
                    label: item,
                    entityType: "buyer_question_tab",
                    entityId: String(index),
                    payload: { previous_tab: tabs[selectedTab], next_tab: item },
                  });
                  setSelectedTab(index);
                }}>{item}</button>
              ))}
            </div>
          )}
          {loadError && <DataStateCard title="问题地图读取失败" desc={loadError} tone="danger" />}
          {!loadError && questions.length === 0 && <DataStateCard title="尚无买家问题" desc="录入种子问题或产品词；模板候选必须人工确认后才能进入监测。" tone="warning" />}
          {reviewError && <DataStateCard title="问题审核失败" desc={reviewError} tone="danger" />}
          <div className="airank-console-card table-card question-governance-card">
            <table className="question-table question-governance-table">
              <thead><tr><th>问题</th><th>Cohort / 版本</th><th>意图 / 阶段</th><th>来源证据</th><th>测量状态</th><th>人工门禁</th></tr></thead>
              <tbody>
                {visibleRows.map((row) => (
                  <tr key={row.question_id}>
                    <td><strong>{row.question_text}</strong><Badge tone={row.intent_level === "high" ? "primary" : row.intent_level === "medium" ? "warning" : "muted"}>{row.question_type}</Badge></td>
                    <td><Badge tone={row.cohort_type === "blind" ? "success" : row.cohort_type === "comparison" ? "warning" : "primary"}>{row.cohort_type}</Badge><small title={row.question_version_id ?? undefined}>{row.question_version_id ? `v · ${row.question_version_id.slice(-8)}` : row.taxonomy_version}</small></td>
                    <td><span className={`intent ${row.intent_level === "high" ? "high" : "mid"}`}>{row.intent_level}</span><small>{row.buyer_stage} · {row.prompt_style}</small></td>
                    <td><strong>{row.source_kind}</strong><small title={row.source_ref}>{row.observed_query ? "客户提供观察记录（未独立核验）" : "非真实搜索量"} · {row.source_ref}</small></td>
                    <td><Badge tone={row.coverage_status === "covered" ? "success" : row.coverage_status === "gap" ? "danger" : "warning"}>{row.coverage_status}</Badge><small>{row.recommended_providers.join("、") || "扫描时选择 Provider"}</small></td>
                    <td>
                      <Badge tone={row.status === "confirmed" ? "success" : row.status === "archived" ? "muted" : "warning"}>{row.status}</Badge>
                      {row.status === "suggested" ? (
                        <button className="question-review-button" type="button" disabled={reviewingQuestionId === row.question_id} onClick={() => void confirmQuestion(row)}>{reviewingQuestionId === row.question_id ? "提交中…" : "确认纳入监测"}</button>
                      ) : <small>{row.reviewed_by ? `由 ${row.reviewed_by} 确认` : "已可进入同 Cohort 测量"}</small>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="table-footer"><span>{showTabs ? `${tabs[selectedTab]}：${visibleRows.length} 条 / 共 ${questions.length} 条问题` : `共 ${questions.length} 条问题`}</span></div>
          </div>
        </div>
        <aside className="rail-stack">
          <Panel title="问题证据状态">
            <div className="check-list">
              <CheckLine text="问题总数" value={String(questions.length)} checked={questions.length > 0} />
              <CheckLine text="已确认可测量" value={String(confirmedCount)} checked={confirmedCount > 0} />
              <CheckLine text="待人工确认" value={String(suggestedCount)} checked={suggestedCount === 0 && questions.length > 0} />
              <CheckLine text="客户观察记录" value={String(observedCount)} checked={observedCount > 0} />
            </div>
          </Panel>
          <Panel title="待处理问题">
            <ol className="top-list">
              {gapRows.slice(0, 5).map((row, index) => <li key={row.question_id}><span>{index + 1}</span>{row.question_text}<strong>{row.status === "suggested" ? "待确认" : row.coverage_status}</strong></li>)}
            </ol>
            <button className="ghost-button" type="button" onClick={() => showTabs ? onNavigate("/console/gaps/questions") : openPanel({
              title: "推荐缺口处理说明",
              desc: "当前只展示数据库中真实存在且标记为 gap/needs_scan 的问题，不补造 Top50 或推荐差距。",
              items: ["先确认问题 Cohort", "补齐可审核事实与内容证据", "发布后按同口径复测"],
            })}>{showTabs ? "查看缺口问题" : "查看处理说明"}</button>
          </Panel>
        </aside>
      </section>
    </>
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
  const { openPanel, notify } = useActionFeedback();
  const [bundle, setBundle] = useState<AssetBundle>(fallbackAssetBundle);
  const [contentAssets, setContentAssets] = useState<GovernedContentAsset[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [reviewingAssetId, setReviewingAssetId] = useState<string | null>(null);

  useEffect(() => {
    if (!project.id) {
      setBundle(fallbackAssetBundle);
      return;
    }
    const controller = new AbortController();
    Promise.all([
      fetchAssetBundle(project.id, controller.signal),
      fetchContentAssets(project.id, controller.signal),
    ])
      .then(([nextBundle, nextAssets]) => {
        setBundle(nextBundle);
        setContentAssets(nextAssets);
        setLoadError(null);
      })
      .catch((error) => {
        if (controller.signal.aborted) return;
        setBundle(fallbackAssetBundle);
        setContentAssets([]);
        setLoadError(error instanceof Error ? error.message : "内容资产接口不可用");
      });
    return () => controller.abort();
  }, [project.id]);

  const reviewAsset = async (asset: GovernedContentAsset, action: "approved" | "rejected" | "changes_requested") => {
    const actor = getStoredAuthSession()?.user.userId;
    if (!actor) {
      notify({ title: "无法提交审校", desc: "当前登录会话缺少可信审核人身份，请重新登录。", tone: "danger" });
      return;
    }
    setReviewingAssetId(asset.asset_id);
    try {
      const review = await reviewContentAsset(asset.asset_id, action, actor);
      setContentAssets((items) => items.map((item) => item.asset_id === asset.asset_id ? { ...item, status: action === "approved" ? "approved" : action } : item));
      notify({ title: action === "approved" ? "内容审校通过" : "内容审校已记录", desc: `事实核验 ${review.fact_check_status}，风险等级 ${review.risk_level}。`, tone: review.fact_check_status === "passed" ? "success" : "warning" });
    } catch (error) {
      notify({ title: "内容审校未通过", desc: error instanceof Error ? error.message : "内容审核接口不可用", tone: "danger" });
    } finally {
      setReviewingAssetId(null);
    }
  };

  return (
    <>
      <PageHeader
        title="AI 收录包"
        subtitle="这些不是普通文章，而是 AI 能抓取、理解、引用的企业证据链。"
        action={<HeaderActions primary="发布 AI 收录包" icon={Rocket} onPrimary={() => onNavigate("/console/publishing")} />}
      />
      {loadError && <DataStateCard title="内容资产读取失败" desc={loadError} tone="danger" />}
      <Panel title="证据绑定内容审校">
        {contentAssets.length === 0 ? (
          <DataStateCard title="尚无可审校内容" desc="只有审核通过且存在精确原文支持的事实，才能生成这里的内容资产。" tone="warning" />
        ) : (
          <div className="content-review-list">
            {contentAssets.map((asset) => (
              <article className="content-review-item" key={asset.asset_id}>
                <div className="content-review-head"><div><strong>{asset.title}</strong><span>{asset.asset_type} · {formatDateTime(asset.created_at)}</span></div><Badge tone={asset.status === "approved" ? "success" : asset.status === "rejected" ? "danger" : "warning"}>{asset.status}</Badge></div>
                <div className="content-review-body">{asset.body_md}</div>
                <div className="content-review-proof"><span>{asset.fact_revision_ids.length} 个事实修订</span><span>{asset.claim_assertion_ids.length} 条主张</span><span>{asset.claim_support_ids.length} 条证据支持</span></div>
                {asset.status === "draft" || asset.status === "changes_requested" ? (
                  <div className="fact-review-actions">
                    <button className="outline-button" type="button" disabled={reviewingAssetId === asset.asset_id} onClick={() => void reviewAsset(asset, "changes_requested")}>要求修改</button>
                    <button className="outline-button" type="button" disabled={reviewingAssetId === asset.asset_id} onClick={() => void reviewAsset(asset, "rejected")}>驳回</button>
                    <button className="airank-console-primary-button" type="button" disabled={reviewingAssetId === asset.asset_id} onClick={() => void reviewAsset(asset, "approved")}>{reviewingAssetId === asset.asset_id ? "审校中…" : "通过审校"}</button>
                  </div>
                ) : null}
              </article>
            ))}
          </div>
        )}
      </Panel>
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
      .catch((error) => {
        if (controller.signal.aborted) return;
        setLoadError(error instanceof Error ? error.message : "发布中心接口不可用");
      });
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
        title="AI 来客助手"
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
          const qualityBlocked = item.status === "quality_blocked";
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
              disabled={qualityBlocked || downloadingReportId === (item.report_id ?? item.title)}
              onClick={() => void downloadReport(item)}
            >
              {qualityBlocked ? (
                "质量阻断"
              ) : downloadingReportId === (item.report_id ?? item.title) ? (
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
              items: ["外部 Publisher 仍为 partial", "AI 来客助手为 disabled", "商业上线仍为 no-go"],
            })
          }
          rows={[["事实与证据", "partial"], ["导出发布包", "ready"], ["WordPress / HTTP", "partial"], ["AI 来客助手", "disabled"], ["商业上线", "blocked"]]}
        />
      </section>
    </>
  );
}

function SkillConsolePage() {
  const [skills, setSkills] = useState<InternalSkill[]>([]);
  const [ledger, setLedger] = useState<SkillPromotionLedger | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    Promise.all([fetchInternalSkills(controller.signal), fetchSkillPromotionLedger(controller.signal)])
      .then(([nextSkills, nextLedger]) => {
        setSkills(nextSkills);
        setLedger(nextLedger);
        setLoadError(null);
      })
      .catch((error) => {
        if (controller.signal.aborted) return;
        setSkills([]);
        setLedger(null);
        setLoadError(error instanceof Error ? error.message : "Skill 控制台接口不可用");
      });
    return () => controller.abort();
  }, []);

  const locallyPassed = skills.filter((skill) => skill.evaluation.local_eval_status === "passed").length;
  const promotionEligible = skills.filter((skill) => skill.evaluation.promotion_eligible).length;
  const retainedPartial = ledger?.skills.filter((item) => item.decision === "retain_partial").length ?? 0;

  return (
    <>
      <PageHeader
        title="内部 Skill 控制台"
        subtitle="展示版本化契约、独立评测和内容寻址晋级账本；本地用例通过不等于生产证据齐备。"
        action={<Badge tone="warning">internal · read-only</Badge>}
      />
      <section className="summary-band evidence-summary">
        <SummaryMetric label="核心 Skill" value={String(skills.length)} tone="primary" />
        <SummaryMetric label="本地评测通过" value={String(locallyPassed)} tone={locallyPassed === skills.length && skills.length > 0 ? "success" : "warning"} />
        <SummaryMetric label="可晋级 ready" value={String(promotionEligible)} tone={promotionEligible > 0 ? "success" : "warning"} />
        <SummaryMetric label="保留 partial" value={String(retainedPartial)} tone="warning" />
      </section>
      {loadError && <DataStateCard title="Skill 状态读取失败" desc={loadError} tone="danger" />}
      {!loadError && skills.length === 0 && <DataStateCard title="尚无已注册 Skill" desc="系统不会用演示 Skill 或固定评测结果补位。" tone="warning" />}
      {skills.length > 0 && (
        <div className="airank-console-card table-card skill-table-wrap">
          <table className="question-table skill-table">
            <thead><tr><th>Skill / 版本</th><th>类别</th><th>Manifest</th><th>评测</th><th>套件</th><th>晋级</th><th>证据阻断</th></tr></thead>
            <tbody>
              {skills.map((skill) => (
                <tr key={skill.skill_id}>
                  <td><strong>{skill.skill_id}</strong><small>v{skill.version} · {skill.evaluation.evaluation_sha256.slice(0, 12)}…</small></td>
                  <td>{skill.category}</td>
                  <td><Badge tone={skill.status === "ready" ? "success" : "warning"}>{skill.status}</Badge></td>
                  <td><Badge tone={skill.evaluation.local_eval_status === "passed" ? "success" : "danger"}>{skill.evaluation.passed_cases}/{skill.evaluation.total_cases} {skill.evaluation.local_eval_status}</Badge></td>
                  <td><small>{skill.evaluation.executed_suites.join(" · ")}</small></td>
                  <td><Badge tone={skill.evaluation.promotion_eligible ? "success" : "warning"}>{skill.evaluation.promotion_eligible ? "eligible" : "blocked"}</Badge></td>
                  <td><small>{skill.evaluation.promotion_blockers.map((item) => item.replace("missing_promotion_evidence:", "缺证：")).join("；") || "无"}</small></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {ledger && (
        <Panel title="Promotion Evidence Ledger">
          <dl className="evidence-metadata">
            <div><dt>Ledger 版本</dt><dd>{ledger.ledger_version}</dd></div>
            <div><dt>Registry SHA-256</dt><dd>{ledger.source_sha256.registry}</dd></div>
            <div><dt>Eval Corpus SHA-256</dt><dd>{ledger.source_sha256.eval_corpus}</dd></div>
            <div><dt>Implementation SHA-256</dt><dd>{ledger.source_sha256.implementation}</dd></div>
          </dl>
        </Panel>
      )}
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
