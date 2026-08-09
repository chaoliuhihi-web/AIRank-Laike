import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
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
  compileBrandGraph,
  claimEvidenceReviewAssignment,
  claimOpportunityAction,
  createOpportunityDependency,
  createOpportunityActionTeam,
  bindFactAcquisitionEvidence,
  createEvidenceReviewerTeam,
  createKnowledgeSyncPolicy,
  createPublishPackage,
  createPublishMutation,
  createComparisonContent,
  createExplainerContent,
  createGovernedContent,
  createCitationClaim,
  createCitationSourceCapture,
  createCitationSourceCaptureBatch,
  createCitationEvidenceReviewCase,
  createBrandGraphAlias,
  createBrandGraphEntity,
  createBrandGraphRelation,
  createFactEvidenceReviewCase,
  createFactAcquisitionTask,
  createPageAudit,
  createOpportunityAction,
  createOpportunityExecutionSchedule,
  downloadReportEvidencePacket,
  deriveEvidenceGaps,
  deriveOpportunities,
  fetchQuestionObservationBatches,
  fetchAnswerSample,
  fetchAnswerSamples,
  fetchBuyerQuestions,
  fetchBrandGraph,
  fetchAssetBundle,
  fetchConsoleOverview,
  fetchContentAssets,
  fetchCitationSupport,
  fetchCitationSourceCapture,
  fetchCitationSourceCaptures,
  fetchLatestCitationSourceCaptures,
  fetchEvidenceObject,
  fetchEvidenceGaps,
  fetchFactAcquisitionTasks,
  fetchOpportunityActions,
  fetchOpportunityActionRouting,
  fetchOpportunityActionDirectory,
  fetchOpportunityCapacityPortfolio,
  fetchOpportunityExecutionPortfolio,
  fetchOpportunities,
  fetchLatestEvidenceIntegrityAudit,
  fetchEvidenceReviewCases,
  fetchEvidenceReviewEscalations,
  fetchEvidenceReviewInbox,
  fetchEvidenceReviewerRouting,
  fetchFactConflicts,
  fetchFactAccuracy,
  fetchFacts,
  fetchInternalSkills,
  fetchKnowledgeGovernance,
  fetchKnowledgeSyncPolicies,
  fetchKnowledgeSyncRuns,
  fetchKnowledgeSources,
  fetchPageAudit,
  fetchPageAudits,
  fetchMeasurementQuality,
  fetchProviderReadiness,
  fetchProviderCredentials,
  fetchProviderCredentialOperation,
  fetchProviderCredentialOperations,
  fetchProviderModelMigrations,
  fetchProviderPrices,
  fetchProviderRoutes,
  fetchProviderUsageLedger,
  fetchPublishAttempts,
  fetchPublishOperation,
  fetchPublishPackages,
  fetchPublicationReconciliations,
  fetchRetestWindows,
  fetchSkillPromotionLedger,
  fetchSkillTrustReport,
  fetchScanRuns,
  fetchScanTasks,
  fetchSourceRegistry,
  fallbackReportList,
  fetchReports,
  getStoredAuthSession,
  loginToAirank,
  importQuestionObservations,
  heartbeatEvidenceReviewAssignment,
  recordConsoleAction,
  recordPublicationEvidence,
  reviewPublicationReconciliation,
  revokeProviderCredential,
  releaseEvidenceReviewAssignment,
  putEvidenceReviewerDirectoryBinding,
  putEvidenceReviewerRoute,
  reviewBuyerQuestion,
  reviewContentAsset,
  reviewFactRevision,
  resolveFactConflict,
  saveKnowledgeSource,
  searchKnowledge,
  triggerKnowledgeSync,
  submitEvidenceReviewDecision,
  upsertEvidenceReviewerTeamMember,
  reviewSourceRegistryEntry,
  runBrandCheck,
  submitPublicationReconciliation,
  runEvidenceIntegrityAudit,
  runEvidenceReviewerDirectorySync,
  storeAuthSession,
  updateProviderRoute,
  createProviderModelMigration,
  createProviderPriceVersion,
  validateProviderModelMigration,
  approveProviderModelMigration,
  upsertProviderCredential,
  updateKnowledgeSyncPolicy,
  upsertOpportunityActionMember,
  putOpportunityActionRoute,
  putOpportunityActionDirectoryBinding,
  putOpportunityCapacityCalendar,
  putOpportunityCapacityException,
  runOpportunityActionDirectorySync,
  putOpportunityExecutionPlan,
  waiveOpportunityDependency,
  verifyOpportunityActionNotObserved,
  type AuthSession,
  type AnswerSample,
  type AnswerSampleDetail,
  type AssetBundle,
  type BuyerQuestion,
  type BrandCheckResult,
  type BrandGraphPortfolio,
  type ConsoleActionInput,
  type ConsoleMetricCard,
  type ConsoleOverview,
  type CitationSupportBundle,
  type CitationSourceCapture,
  type CitationCaptureBatch,
  type FactConflict,
  type FactAccuracyBundle,
  type EvidenceReviewCase,
  type EvidenceReviewEscalationList,
  type EvidenceReviewInbox,
  type EvidenceReviewQueue,
  type EvidenceReviewerRouting,
  type EvidenceIntegrityAudit,
  type EvidenceGapList,
  type FactAcquisitionTaskList,
  type OpportunityList,
  type OpportunityAction,
  type OpportunityActionList,
  type OpportunityActionRouting,
  type OpportunityActionDirectory,
  type OpportunityCapacityPortfolio,
  type OpportunityDependency,
  type OpportunityExecutionPortfolio,
  type OpportunitySourceKind,
  type GovernedContentAsset,
  type GovernedContentCreateInput,
  type FactRevision,
  type InternalSkill,
  type KnowledgeGovernance,
  type KnowledgeSearch,
  type KnowledgeSyncPolicy,
  type KnowledgeSyncRun,
  type PageAuditFinding,
  type PageAuditRun,
  type KnowledgeSource,
  type MeasurementQualityReport,
  type ProviderReadiness,
  type ProviderCredentialPortfolio,
  type ProviderCredentialOperation,
  type ProviderCredentialOperationList,
  type ProviderCredentialStatus,
  type ProviderModelMigration,
  type ProviderRouteStatus,
  type ProviderPriceVersion,
  type ProviderUsageLedger,
  type ProviderUsagePrecision,
  type QuestionMapResult,
  type QuestionObservationBatch,
  type PublishPackage,
  type PublishPackageCreateInput,
  type PublishMutationCreateInput,
  type PublicationReconciliation,
  type ReportItem,
  type ReportList,
  type RetestWindow,
  type ScanRun,
  type ScanTask,
  type SkillPromotionLedger,
  type SkillTrustReport,
  type SourceRegistryEntry,
} from "./console/api";
import type { Tone } from "./console/data";
import { OpportunityBoard } from "./console/OpportunityBoard";

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
const governedAssetTypes: Array<{ value: GovernedContentCreateInput["assetType"]; label: string }> = [
  { value: "fact_page", label: "企业事实页" },
  { value: "product_page", label: "产品与服务页" },
  { value: "faq", label: "FAQ 页面" },
  { value: "case_page", label: "案例页" },
  { value: "research_page", label: "数据与研究页" },
  { value: "json_ld", label: "JSON-LD" },
  { value: "llms_txt", label: "llms.txt" },
];
const comparisonDimensions = [
  { dimension_id: "deployment", label: "部署方式" },
  { dimension_id: "core_capability", label: "核心能力边界" },
  { dimension_id: "data_security", label: "数据安全" },
  { dimension_id: "evidence_traceability", label: "证据可追溯性" },
  { dimension_id: "provider_coverage", label: "平台覆盖" },
  { dimension_id: "workflow", label: "业务工作流" },
  { dimension_id: "permissions_audit", label: "权限与审计" },
  { dimension_id: "integration", label: "系统集成" },
  { dimension_id: "delivery_operation", label: "交付与运营" },
  { dimension_id: "limitations", label: "限制与适用边界" },
] as const;
const explainerRoles = [
  { value: "definition", label: "定义与范围", minimum: 1 },
  { value: "mechanism", label: "工作机制", minimum: 2 },
  { value: "step", label: "实施步骤", minimum: 3 },
  { value: "criterion", label: "判断标准", minimum: 2 },
  { value: "misconception", label: "常见误区", minimum: 1 },
  { value: "faq", label: "常见问题", minimum: 2 },
  { value: "boundary", label: "适用边界", minimum: 1 },
] as const;
const reportCardIcons: LucideIcon[] = [CalendarDays, NotebookTabs, Crown, FileChartColumn];
const qualityLimitationLabels: Record<string, string> = {
  valid_samples_have_no_provider_citations: "有效样本没有 Provider 原生引用",
  citation_support_not_evaluated: "引用支持度尚未评测",
  fact_accuracy_not_evaluated: "事实准确率尚未评测",
  fact_claims_not_registered: "尚未登记可核验的品牌或竞品事实声明",
  fact_accuracy_incomplete_coverage: "事实声明尚未完成全量、确定性人工核验",
  repeat_stability_unavailable: "重复采样稳定性不可用",
};
const factAccuracyLimitationLabels: Record<string, string> = {
  fact_claims_not_registered: "尚未从回答中登记品牌或竞品事实声明",
  fact_claims_unreviewed: "存在尚未审核的事实声明",
  provisional_or_stale_fact_reviews_excluded: "AI 辅助、过期来源、旧事实版本或冲突审核已排除",
  fact_accuracy_contains_insufficient_evidence: "存在缺少已审核事实来源的声明",
  fact_accuracy_incomplete_coverage: "只有全部事实声明完成确定性人工核验后才输出准确率",
  fact_accuracy_independent_review_required: "单人预审不能进入准确率，必须由不同审核人一致或完成第三人裁决",
  benchmark_reviews_excluded_from_commercial_metrics: "一致性 Benchmark 仅评估审核质量，已从客户指标中排除",
};
const citationSupportLimitationLabels: Record<string, string> = {
  selected_citations_have_no_answer_claims: "原生引用尚未绑定回答中的具体断言",
  citation_support_not_reviewed: "断言与引用尚未复核",
  citation_support_has_no_source_page_snapshot: "尚无不可变来源页面快照",
  provisional_reviews_excluded_from_support_rate: "临时复核不会进入可交付支持率",
  citation_support_independent_review_required: "单人预审不能进入支持率，必须由不同审核人一致或完成第三人裁决",
  benchmark_reviews_excluded_from_commercial_metrics: "一致性 Benchmark 仅评估审核质量，已从客户指标中排除",
};
const reviewCaseStatusLabels: Record<EvidenceReviewCase["status"], string> = {
  creating: "创建中",
  awaiting_secondary: "等待第二审核人",
  disputed: "结论分歧，等待裁决",
  agreed: "双人一致",
  adjudicated: "已完成第三人裁决",
  void: "已作废",
};
const reviewQualityLimitationLabels: Record<string, string> = {
  review_benchmark_has_no_cases: "尚无人工标注 benchmark 样本",
  review_cases_awaiting_independent_second_review: "存在尚未完成第二人独立复核的任务",
  review_cases_awaiting_adjudication: "存在尚未完成第三人裁决的分歧任务",
  review_benchmark_sample_too_small: "已完成样本少于当前 benchmark 最小数量",
  review_benchmark_kappa_not_estimable: "标签分布不足，暂时无法估计 Cohen’s kappa",
  review_benchmark_kappa_below_threshold: "Cohen’s kappa 低于当前审核质量门槛",
};
const sourcePanelStatusLabels: Record<string, string> = {
  captured: "已捕获并存证",
  not_present: "界面未呈现（已检查）",
  not_inspected: "未检查",
  not_applicable: "不适用",
};
const sourceCategoryLabels: Record<string, string> = {
  brand_corporate: "品牌与企业官网",
  government_public: "政府与公共机构",
  news_media: "新闻与媒体",
  vertical_professional: "垂直专业内容",
  platform_community: "平台与社区",
  business_services: "商业信息与服务",
  research_documentation: "研究与文档",
  search_page_proxy: "搜索与页面代理",
  other: "其他",
};
const sourceUsageLabels: Record<string, string> = {
  primary_evidence: "可作主要证据",
  context_only: "仅作背景",
  lead_only: "仅作线索",
  prohibited: "禁止使用",
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

function formatOverdueDuration(seconds: number): string {
  const normalized = Math.max(0, Math.floor(seconds));
  if (normalized < 60) return `${normalized} 秒`;
  if (normalized < 3600) return `${Math.floor(normalized / 60)} 分钟`;
  if (normalized < 86400) return `${Math.floor(normalized / 3600)} 小时`;
  const days = Math.floor(normalized / 86400);
  const hours = Math.floor((normalized % 86400) / 3600);
  return hours ? `${days} 天 ${hours} 小时` : `${days} 天`;
}

function reviewAssignmentStateLabel(state: "unassigned" | "assigned" | "expired"): string {
  if (state === "assigned") return "已领取";
  if (state === "expired") return "租约已过期";
  return "待领取";
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
              <span>探测层级<strong>{item.probe_level === "l3_generation" ? "L3 真实生成" : "L2 页面交互"}</strong></span>
              <span>生成验证<strong>{item.generation_verified ? "已通过" : "未通过"}</strong></span>
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
  const [syncPolicies, setSyncPolicies] = useState<KnowledgeSyncPolicy[]>([]);
  const [syncRuns, setSyncRuns] = useState<KnowledgeSyncRun[]>([]);
  const [syncIntervals, setSyncIntervals] = useState<Record<string, number>>({});
  const [syncAction, setSyncAction] = useState<string | null>(null);
  const [conflicts, setConflicts] = useState<FactConflict[]>([]);
  const [governance, setGovernance] = useState<KnowledgeGovernance | null>(null);
  const [brandGraph, setBrandGraph] = useState<BrandGraphPortfolio | null>(null);
  const [brandGraphAction, setBrandGraphAction] = useState<string | null>(null);
  const [entityDraft, setEntityDraft] = useState({
    entityRole: "target" as "target" | "competitor" | "related",
    entityKind: "brand" as "brand" | "company" | "product" | "service",
    canonicalName: "",
    websiteUrl: "",
    usageScope: "measurement_only" as "measurement_only" | "public_and_measurement",
    factRevisionId: "",
  });
  const [aliasDraft, setAliasDraft] = useState({
    entityId: "",
    aliasText: "",
    aliasType: "official" as "official" | "english" | "abbreviation" | "former_name" | "misspelling" | "product_variant",
    usageScope: "measurement_only" as "measurement_only" | "public_and_measurement",
    factRevisionId: "",
  });
  const [relationDraft, setRelationDraft] = useState({
    subjectEntityId: "",
    predicate: "competitor_of" as "legal_name_of" | "owns_product" | "offers" | "competitor_of" | "former_name_of" | "part_of",
    objectEntityId: "",
    usageScope: "measurement_only" as "measurement_only" | "public_and_measurement",
    factRevisionId: "",
  });
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
    const [nextFacts, nextSources, nextConflicts, nextGovernance, nextSyncPolicies, nextSyncRuns, nextBrandGraph] = await Promise.all([
      fetchFacts(project.id, signal),
      fetchKnowledgeSources(project.id, signal),
      fetchFactConflicts(project.id, signal),
      fetchKnowledgeGovernance(project.id, signal),
      fetchKnowledgeSyncPolicies(project.id, signal),
      fetchKnowledgeSyncRuns(project.id, signal),
      fetchBrandGraph(project.id, signal),
    ]);
    setFacts(nextFacts);
    setSources(nextSources);
    setConflicts(nextConflicts);
    setGovernance(nextGovernance);
    setSyncPolicies(nextSyncPolicies);
    setSyncRuns(nextSyncRuns);
    setBrandGraph(nextBrandGraph);
    setSyncIntervals((current) => {
      const next = { ...current };
      nextSources.forEach((source) => {
        if (!next[source.source_id]) next[source.source_id] = 24;
      });
      nextSyncPolicies.forEach((policy) => {
        next[policy.policy_id] = current[policy.policy_id] ?? policy.interval_hours;
      });
      return next;
    });
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

  useEffect(() => {
    if (!project.id || !syncRuns.some((run) => ["queued", "running"].includes(run.status))) return;
    const controller = new AbortController();
    const timer = window.setInterval(() => {
      refreshKnowledge(controller.signal).catch((error) => {
        if (!controller.signal.aborted) {
          setLoadError(error instanceof Error ? error.message : "来源同步状态刷新失败");
        }
      });
    }, 1800);
    return () => {
      controller.abort();
      window.clearInterval(timer);
    };
  }, [project.id, refreshKnowledge, syncRuns]);

  const approved = facts.filter((item) => item.status === "approved").length;
  const pending = facts.filter((item) => item.status === "proposed").length;
  const eligible = facts.filter((item) => item.eligible_for_generation).length;
  const eligibleFactRevisions = facts.filter((item) => item.status === "approved" && item.eligible_for_generation);

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

  const enableSourceSync = async (source: KnowledgeSource) => {
    if (!project.id || !source.source_uri) return;
    setSyncAction(`create:${source.source_id}`);
    try {
      const policy = await createKnowledgeSyncPolicy(
        project.id,
        source.source_id,
        syncIntervals[source.source_id] ?? 24,
      );
      notify({
        title: "来源自动同步已启用",
        desc: `${source.title} 的首次安全抓取已入队；内容变化只会追加新修订，不会覆盖旧证据。`,
        tone: "success",
      });
      setSyncPolicies((items) => [policy, ...items.filter((item) => item.policy_id !== policy.policy_id)]);
      await refreshKnowledge();
    } catch (error) {
      notify({ title: "自动同步未启用", desc: error instanceof Error ? error.message : "同步策略接口不可用", tone: "danger" });
    } finally {
      setSyncAction(null);
    }
  };

  const triggerSourceSync = async (policy: KnowledgeSyncPolicy) => {
    setSyncAction(`trigger:${policy.policy_id}`);
    try {
      const run = await triggerKnowledgeSync(policy.policy_id);
      setSyncRuns((items) => [run, ...items.filter((item) => item.run_id !== run.run_id)]);
      notify({ title: "来源检查已入队", desc: "Worker 将保存原始响应和可见正文对象，完成后再判断 unchanged 或 changed。", tone: "success" });
    } catch (error) {
      notify({ title: "来源检查未入队", desc: error instanceof Error ? error.message : "同步任务接口不可用", tone: "danger" });
    } finally {
      setSyncAction(null);
    }
  };

  const updateSourceSync = async (policy: KnowledgeSyncPolicy, enabled: boolean) => {
    setSyncAction(`update:${policy.policy_id}`);
    try {
      const intervalHours = syncIntervals[policy.policy_id] ?? policy.interval_hours;
      const updated = await updateKnowledgeSyncPolicy(policy, {
        enabled,
        intervalHours,
        reason: enabled
          ? `运营人员启用自动同步并设置为每 ${intervalHours} 小时检查`
          : "运营人员暂停自动同步，保留全部历史运行与来源修订",
      });
      setSyncPolicies((items) => items.map((item) => item.policy_id === updated.policy_id ? updated : item));
      notify({
        title: enabled ? "自动同步策略已更新" : "自动同步已暂停",
        desc: enabled ? `后续按 ${intervalHours} 小时周期检查。` : "历史来源、对象和运行记录不会被删除。",
        tone: "success",
      });
    } catch (error) {
      notify({ title: "同步策略未更新", desc: error instanceof Error ? error.message : "同步策略接口不可用", tone: "danger" });
      void refreshKnowledge().catch(() => undefined);
    } finally {
      setSyncAction(null);
    }
  };

  const submitBrandEntity = async (event: FormEvent) => {
    event.preventDefault();
    if (!project.id || !entityDraft.factRevisionId || entityDraft.canonicalName.trim().length < 2) return;
    setBrandGraphAction("entity");
    try {
      await createBrandGraphEntity(project.id, {
        entity_role: entityDraft.entityRole,
        entity_kind: entityDraft.entityKind,
        canonical_name: entityDraft.canonicalName.trim(),
        website_url: entityDraft.websiteUrl.trim() || undefined,
        usage_scope: entityDraft.usageScope,
        fact_revision_id: entityDraft.factRevisionId,
      });
      setEntityDraft((current) => ({ ...current, canonicalName: "", websiteUrl: "" }));
      await refreshKnowledge();
      notify({ title: "品牌实体已登记", desc: "实体已绑定当前审核事实和来源 Hash；重新编译后才会进入新的测量快照。", tone: "success" });
    } catch (error) {
      notify({ title: "实体未登记", desc: error instanceof Error ? error.message : "品牌实体接口不可用", tone: "danger" });
    } finally {
      setBrandGraphAction(null);
    }
  };

  const submitBrandAlias = async (event: FormEvent) => {
    event.preventDefault();
    if (!project.id || !aliasDraft.entityId || !aliasDraft.factRevisionId || aliasDraft.aliasText.trim().length < 2) return;
    setBrandGraphAction("alias");
    try {
      await createBrandGraphAlias(project.id, aliasDraft.entityId, {
        alias_text: aliasDraft.aliasText.trim(),
        alias_type: aliasDraft.aliasType,
        usage_scope: aliasDraft.usageScope,
        fact_revision_id: aliasDraft.factRevisionId,
      });
      setAliasDraft((current) => ({ ...current, aliasText: "" }));
      await refreshKnowledge();
      notify({ title: "别名已登记", desc: "编译时会跨全部实体检查规范化歧义；歧义别名不会进入测量词表。", tone: "success" });
    } catch (error) {
      notify({ title: "别名未登记", desc: error instanceof Error ? error.message : "品牌别名接口不可用", tone: "danger" });
    } finally {
      setBrandGraphAction(null);
    }
  };

  const submitBrandRelation = async (event: FormEvent) => {
    event.preventDefault();
    if (!project.id || !relationDraft.subjectEntityId || !relationDraft.objectEntityId || !relationDraft.factRevisionId) return;
    setBrandGraphAction("relation");
    try {
      await createBrandGraphRelation(project.id, {
        subject_entity_id: relationDraft.subjectEntityId,
        predicate: relationDraft.predicate,
        object_entity_id: relationDraft.objectEntityId,
        usage_scope: relationDraft.usageScope,
        fact_revision_id: relationDraft.factRevisionId,
      });
      await refreshKnowledge();
      notify({ title: "实体关系已登记", desc: "方向、事实修订和证据清单已进入追加事件链。", tone: "success" });
    } catch (error) {
      notify({ title: "关系未登记", desc: error instanceof Error ? error.message : "实体关系接口不可用", tone: "danger" });
    } finally {
      setBrandGraphAction(null);
    }
  };

  const compileCurrentBrandGraph = async () => {
    const actor = getStoredAuthSession()?.user.userId;
    if (!project.id || !actor) {
      notify({ title: "无法编译图谱", desc: "当前登录会话缺少可信操作人。", tone: "danger" });
      return;
    }
    setBrandGraphAction("compile");
    try {
      const snapshot = await compileBrandGraph(project.id, actor);
      await refreshKnowledge();
      notify({
        title: snapshot.status === "blocked" ? "图谱已编译但被阻断" : "不可变图谱快照已生成",
        desc: `${snapshot.status} · ${snapshot.graph_sha256.slice(0, 12)}… · ${snapshot.known_limitations.length} 项限制`,
        tone: snapshot.status === "blocked" ? "danger" : snapshot.status === "partial" || snapshot.status === "legacy_unverified" ? "warning" : "success",
      });
    } catch (error) {
      notify({ title: "图谱编译失败", desc: error instanceof Error ? error.message : "图谱编译接口不可用", tone: "danger" });
    } finally {
      setBrandGraphAction(null);
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
      <Panel title="品牌实体图谱 · 测量口径">
        <div className="brand-graph-toolbar">
          <div>
            <strong>把品牌、公司、产品、竞品和别名编译成不可变测量词表</strong>
            <span>每条记录必须绑定当前已批准 FactRevision；歧义词会被排除，公开 JSON-LD 与内部测量词表分开。</span>
          </div>
          <button className="airank-console-primary-button" type="button" disabled={brandGraphAction !== null || eligibleFactRevisions.length === 0} onClick={() => void compileCurrentBrandGraph()}>
            {brandGraphAction === "compile" ? "编译中…" : "编译不可变快照"}
          </button>
        </div>
        {!brandGraph && !loadError && <DataStateCard title="实体图谱尚未加载" desc="等待真实 API 返回；不会用项目字段伪造成已治理图谱。" tone="warning" />}
        {brandGraph && (
          <>
            <div className="brand-graph-summary">
              <Badge tone={brandGraph.latest_snapshot?.status === "governed" ? "success" : brandGraph.latest_snapshot?.status === "blocked" ? "danger" : "warning"}>{brandGraph.latest_snapshot?.status ?? "not_compiled"}</Badge>
              <span>实体 {brandGraph.entities.length}</span>
              <span>别名 {brandGraph.aliases.length}</span>
              <span>关系 {brandGraph.relations.length}</span>
              <span>测量词表 {brandGraph.measurement_ready ? "可用" : "不可用"}</span>
              <span>公开 JSON-LD {brandGraph.public_export_ready ? "可导出" : "已关闭"}</span>
              {brandGraph.latest_snapshot && <code title={brandGraph.latest_snapshot.graph_sha256}>{brandGraph.latest_snapshot.graph_sha256.slice(0, 12)}…</code>}
            </div>
            {brandGraph.known_limitations.length > 0 && (
              <div className="brand-graph-limitations">
                {brandGraph.known_limitations.map((item) => <Badge tone="warning" key={item}>{item}</Badge>)}
              </div>
            )}
            {brandGraph.latest_snapshot?.ambiguous_aliases.map((item) => (
              <DataStateCard key={item.normalized_value} title={`歧义词已排除：${item.observed_values.join(" / ")}`} desc={`同时指向 ${item.entity_ids.length} 个实体；该词不会参与品牌或竞品提及计算。`} tone="danger" />
            ))}
            <div className="brand-graph-records">
              {brandGraph.entities.map((entity) => (
                <article key={entity.entity_id}>
                  <div><strong>{entity.canonical_name}</strong><Badge tone={entity.entity_role === "target" ? "primary" : "muted"}>{entity.entity_role} · {entity.entity_kind}</Badge></div>
                  <span>{brandGraph.aliases.filter((alias) => alias.entity_id === entity.entity_id && alias.status === "active").map((alias) => alias.alias_text).join(" / ") || "无已登记别名"}</span>
                  <code>Fact {entity.fact_revision_id} · v{entity.version} · {entity.evidence_manifest_sha256.slice(0, 10)}…</code>
                </article>
              ))}
            </div>
          </>
        )}
        {eligibleFactRevisions.length === 0 ? (
          <DataStateCard title="没有可绑定的审核事实" desc="先完成来源导入、事实审核、冲突与有效期门禁，再登记实体；项目名称本身不等于已证实身份。" tone="warning" />
        ) : (
          <div className="brand-graph-forms">
            <form onSubmit={submitBrandEntity}>
              <strong>登记实体</strong>
              <input value={entityDraft.canonicalName} onChange={(event) => setEntityDraft({ ...entityDraft, canonicalName: event.target.value })} placeholder="规范名称" required minLength={2} />
              <div className="brand-graph-form-row">
                <select value={entityDraft.entityRole} onChange={(event) => setEntityDraft({ ...entityDraft, entityRole: event.target.value as typeof entityDraft.entityRole })}>
                  <option value="target">目标实体</option><option value="competitor">竞品实体</option><option value="related">关联实体</option>
                </select>
                <select value={entityDraft.entityKind} onChange={(event) => setEntityDraft({ ...entityDraft, entityKind: event.target.value as typeof entityDraft.entityKind })}>
                  <option value="brand">品牌</option><option value="company">公司</option><option value="product">产品</option><option value="service">服务</option>
                </select>
              </div>
              <input type="url" value={entityDraft.websiteUrl} onChange={(event) => setEntityDraft({ ...entityDraft, websiteUrl: event.target.value })} placeholder="官网 URL（可选）" />
              <select value={entityDraft.factRevisionId} onChange={(event) => setEntityDraft({ ...entityDraft, factRevisionId: event.target.value })} required>
                <option value="">选择身份事实证据</option>
                {eligibleFactRevisions.map((fact) => <option value={fact.revision_id} key={fact.revision_id}>{fact.title} · v{fact.revision_number}</option>)}
              </select>
              <select value={entityDraft.usageScope} onChange={(event) => setEntityDraft({ ...entityDraft, usageScope: event.target.value as typeof entityDraft.usageScope })}>
                <option value="measurement_only">仅测量使用</option><option value="public_and_measurement">公开与测量</option>
              </select>
              <button className="outline-button" type="submit" disabled={brandGraphAction !== null}>{brandGraphAction === "entity" ? "登记中…" : "登记实体"}</button>
            </form>
            <form onSubmit={submitBrandAlias}>
              <strong>登记别名</strong>
              <select value={aliasDraft.entityId} onChange={(event) => setAliasDraft({ ...aliasDraft, entityId: event.target.value })} required>
                <option value="">选择所属实体</option>
                {brandGraph?.entities.filter((entity) => entity.status === "active").map((entity) => <option value={entity.entity_id} key={entity.entity_id}>{entity.canonical_name}</option>)}
              </select>
              <input value={aliasDraft.aliasText} onChange={(event) => setAliasDraft({ ...aliasDraft, aliasText: event.target.value })} placeholder="简称、英文名、旧称或常见误写" required minLength={2} />
              <select value={aliasDraft.aliasType} onChange={(event) => setAliasDraft({ ...aliasDraft, aliasType: event.target.value as typeof aliasDraft.aliasType })}>
                <option value="official">官方别名</option><option value="english">英文名</option><option value="abbreviation">简称</option><option value="former_name">旧称</option><option value="misspelling">常见误写</option><option value="product_variant">产品变体</option>
              </select>
              <select value={aliasDraft.factRevisionId} onChange={(event) => setAliasDraft({ ...aliasDraft, factRevisionId: event.target.value })} required>
                <option value="">选择别名事实证据</option>
                {eligibleFactRevisions.map((fact) => <option value={fact.revision_id} key={fact.revision_id}>{fact.title} · v{fact.revision_number}</option>)}
              </select>
              <select value={aliasDraft.usageScope} onChange={(event) => setAliasDraft({ ...aliasDraft, usageScope: event.target.value as typeof aliasDraft.usageScope })}>
                <option value="measurement_only">仅测量使用</option><option value="public_and_measurement">公开与测量</option>
              </select>
              <button className="outline-button" type="submit" disabled={brandGraphAction !== null}>{brandGraphAction === "alias" ? "登记中…" : "登记别名"}</button>
            </form>
            <form onSubmit={submitBrandRelation}>
              <strong>登记方向关系</strong>
              <select value={relationDraft.subjectEntityId} onChange={(event) => setRelationDraft({ ...relationDraft, subjectEntityId: event.target.value })} required>
                <option value="">选择主语实体</option>
                {brandGraph?.entities.filter((entity) => entity.status === "active").map((entity) => <option value={entity.entity_id} key={entity.entity_id}>{entity.canonical_name}</option>)}
              </select>
              <select value={relationDraft.predicate} onChange={(event) => setRelationDraft({ ...relationDraft, predicate: event.target.value as typeof relationDraft.predicate })}>
                <option value="legal_name_of">法定名称对应</option><option value="owns_product">拥有产品</option><option value="offers">提供服务</option><option value="competitor_of">竞争关系</option><option value="former_name_of">曾用名对应</option><option value="part_of">隶属于</option>
              </select>
              <select value={relationDraft.objectEntityId} onChange={(event) => setRelationDraft({ ...relationDraft, objectEntityId: event.target.value })} required>
                <option value="">选择宾语实体</option>
                {brandGraph?.entities.filter((entity) => entity.status === "active").map((entity) => <option value={entity.entity_id} key={entity.entity_id}>{entity.canonical_name}</option>)}
              </select>
              <select value={relationDraft.factRevisionId} onChange={(event) => setRelationDraft({ ...relationDraft, factRevisionId: event.target.value })} required>
                <option value="">选择关系事实证据</option>
                {eligibleFactRevisions.map((fact) => <option value={fact.revision_id} key={fact.revision_id}>{fact.title} · v{fact.revision_number}</option>)}
              </select>
              <select value={relationDraft.usageScope} onChange={(event) => setRelationDraft({ ...relationDraft, usageScope: event.target.value as typeof relationDraft.usageScope })}>
                <option value="measurement_only">仅测量使用</option><option value="public_and_measurement">公开与测量</option>
              </select>
              <button className="outline-button" type="submit" disabled={brandGraphAction !== null || relationDraft.subjectEntityId === relationDraft.objectEntityId}>{brandGraphAction === "relation" ? "登记中…" : "登记关系"}</button>
            </form>
          </div>
        )}
      </Panel>
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
              <Badge tone={item.subject_type === "general" ? "muted" : "primary"}>{item.subject_type === "general" ? "通用事实" : `${item.subject_type} · ${item.subject_ref_id}`}</Badge>
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
            {sources.map((source) => {
              const coveredBySync = syncPolicies.some((policy) => policy.current_source_id === source.source_id || policy.anchor_source_id === source.source_id);
              return (
                <div className="gap-row" key={source.source_id}>
                  <IconTile tone={source.status === "active" ? "success" : "warning"}><Link2 size={21} /></IconTile>
                  <div><strong>{source.title}</strong><span>{source.source_type} · {source.authority_level}</span></div>
                  <Badge tone={source.status === "active" ? "success" : "warning"}>{source.status}</Badge>
                  <strong>{source.segment_count} 段</strong>
                  <span>{source.valid_until ? `有效至 ${formatDateTime(source.valid_until)}` : "长期有效 · 无到期日"}</span>
                  <Badge tone="primary">v{source.revision_number}</Badge>
                  <div className="gap-row-actions">
                    {source.status === "active" && <button className="table-action" type="button" onClick={() => openSourceEditor(source)}>人工更新</button>}
                    {source.status === "active" && source.source_uri && !coveredBySync && (
                      <>
                        <select
                          aria-label={`${source.title} 自动同步周期`}
                          value={syncIntervals[source.source_id] ?? 24}
                          onChange={(event) => setSyncIntervals((items) => ({ ...items, [source.source_id]: Number(event.target.value) }))}
                        >
                          <option value={6}>每 6 小时</option>
                          <option value={24}>每天</option>
                          <option value={72}>每 3 天</option>
                          <option value={168}>每周</option>
                        </select>
                        <button className="table-action" type="button" disabled={syncAction === `create:${source.source_id}`} onClick={() => void enableSourceSync(source)}>
                          {syncAction === `create:${source.source_id}` ? "启用中…" : "自动同步"}
                        </button>
                      </>
                    )}
                    {coveredBySync && <Badge tone="success">已纳入同步</Badge>}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </Panel>
      <Panel title="公开来源自动同步">
        <div className="knowledge-sync-intro">
          <ShieldCheck size={20} />
          <span>只抓取客户授权的公开 HTTP(S) 来源。DNS 固定、原始响应、可见正文、Hash 和运行元数据会被不可变保存；正文变化只追加新版本，并立即让依赖旧来源的事实失去生成资格。</span>
        </div>
        {syncPolicies.length === 0 ? (
          <DataStateCard title="尚未启用来源自动同步" desc="在上方具有公开 URL 的 active 来源中选择周期。系统不会擅自发现或抓取未授权站点。" tone="warning" />
        ) : (
          <div className="knowledge-sync-list">
            {syncPolicies.map((policy) => {
              const currentSource = sources.find((source) => source.source_id === policy.current_source_id);
              const latestRun = syncRuns.find((run) => run.policy_id === policy.policy_id);
              const activeRun = syncRuns.find((run) => run.policy_id === policy.policy_id && ["queued", "running"].includes(run.status));
              const statusTone: Tone = latestRun?.status === "changed" || latestRun?.status === "unchanged"
                ? "success"
                : latestRun?.status === "failed" || latestRun?.status === "blocked"
                  ? "danger"
                  : "warning";
              return (
                <article className="knowledge-sync-card" key={policy.policy_id}>
                  <div className="knowledge-sync-card-head">
                    <div>
                      <strong>{currentSource?.title ?? policy.source_uri}</strong>
                      <span>{policy.source_uri}</span>
                    </div>
                    <Badge tone={policy.enabled ? "success" : "muted"}>{policy.enabled ? "enabled" : "paused"}</Badge>
                  </div>
                  <dl>
                    <div><dt>当前版本</dt><dd>{currentSource ? `v${currentSource.revision_number}` : policy.current_source_id}</dd></div>
                    <div><dt>最近结果</dt><dd><Badge tone={statusTone}>{latestRun?.status ?? "等待首次运行"}</Badge></dd></div>
                    <div><dt>最近检查</dt><dd>{policy.last_checked_at ? formatDateTime(policy.last_checked_at) : "尚未完成"}</dd></div>
                    <div><dt>下次计划</dt><dd>{policy.enabled ? formatDateTime(policy.next_run_at) : "已暂停"}</dd></div>
                    <div><dt>证据 Hash</dt><dd title={latestRun?.visible_text_sha256 ?? undefined}>{latestRun?.visible_text_sha256 ? `${latestRun.visible_text_sha256.slice(0, 12)}…` : "—"}</dd></div>
                    <div><dt>对象存证</dt><dd>{latestRun?.raw_object_ref_id && latestRun?.text_object_ref_id ? "原始页 + 正文" : "等待完成"}</dd></div>
                  </dl>
                  {latestRun?.error_code && <p className="knowledge-sync-error">{latestRun.error_code} · {latestRun.error_message}</p>}
                  <div className="knowledge-sync-actions">
                    <label>
                      <span>检查周期</span>
                      <select
                        value={syncIntervals[policy.policy_id] ?? policy.interval_hours}
                        disabled={!policy.enabled || syncAction === `update:${policy.policy_id}`}
                        onChange={(event) => setSyncIntervals((items) => ({ ...items, [policy.policy_id]: Number(event.target.value) }))}
                      >
                        <option value={6}>每 6 小时</option>
                        <option value={24}>每天</option>
                        <option value={72}>每 3 天</option>
                        <option value={168}>每周</option>
                      </select>
                    </label>
                    {policy.enabled && (
                      <button className="outline-button" type="button" disabled={Boolean(activeRun) || syncAction === `trigger:${policy.policy_id}`} onClick={() => void triggerSourceSync(policy)}>
                        {activeRun ? `${activeRun.status}…` : syncAction === `trigger:${policy.policy_id}` ? "入队中…" : "立即检查"}
                      </button>
                    )}
                    <button className="airank-console-primary-button" type="button" disabled={syncAction === `update:${policy.policy_id}`} onClick={() => void updateSourceSync(policy, !policy.enabled || (syncIntervals[policy.policy_id] ?? policy.interval_hours) !== policy.interval_hours)}>
                      {syncAction === `update:${policy.policy_id}` ? "保存中…" : !policy.enabled ? "重新启用" : (syncIntervals[policy.policy_id] ?? policy.interval_hours) !== policy.interval_hours ? "保存周期" : "暂停同步"}
                    </button>
                  </div>
                </article>
              );
            })}
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

const EVIDENCE_CITATION_INITIAL_LIMIT = 20;

function EvidencePage() {
  const { project } = useConsoleOverview();
  const answerTextRef = useRef<HTMLDivElement>(null);
  const sampleDetailScrollTargetRef = useRef<string | null>(null);
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
  const [showAllCitations, setShowAllCitations] = useState(false);
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
  const [citationClaimText, setCitationClaimText] = useState("");
  const [citationClaimId, setCitationClaimId] = useState("");
  const [citationClaimBoundary, setCitationClaimBoundary] = useState<{ start: number; end: number } | null>(null);
  const [citationCaptures, setCitationCaptures] = useState<Record<string, CitationSourceCapture[]>>({});
  const [citationBatch, setCitationBatch] = useState<CitationCaptureBatch | null>(null);
  const [citationAction, setCitationAction] = useState<string | null>(null);
  const [citationActionError, setCitationActionError] = useState<string | null>(null);
  const [factAccuracy, setFactAccuracy] = useState<FactAccuracyBundle | null>(null);
  const [factAccuracyError, setFactAccuracyError] = useState<string | null>(null);
  const [factAction, setFactAction] = useState<string | null>(null);
  const [facts, setFacts] = useState<FactRevision[]>([]);
  const [factClaimText, setFactClaimText] = useState("");
  const [factClaimKind, setFactClaimKind] = useState<"brand_fact" | "competitor_fact">("brand_fact");
  const [factSubject, setFactSubject] = useState("");
  const [factClaimId, setFactClaimId] = useState("");
  const [factRevisionId, setFactRevisionId] = useState("");
  const [factRationale, setFactRationale] = useState("人工核对回答声明、当前审核事实与原始来源边界。");
  const [reviewQueue, setReviewQueue] = useState<EvidenceReviewQueue | null>(null);
  const [reviewQueueError, setReviewQueueError] = useState<string | null>(null);
  const [reviewInbox, setReviewInbox] = useState<EvidenceReviewInbox | null>(null);
  const [reviewInboxError, setReviewInboxError] = useState<string | null>(null);
  const [reviewEscalations, setReviewEscalations] = useState<EvidenceReviewEscalationList | null>(null);
  const [reviewEscalationError, setReviewEscalationError] = useState<string | null>(null);
  const [reviewRouting, setReviewRouting] = useState<EvidenceReviewerRouting | null>(null);
  const [reviewRoutingError, setReviewRoutingError] = useState<string | null>(null);
  const [reviewRoutingBusy, setReviewRoutingBusy] = useState<string | null>(null);
  const [reviewTeamName, setReviewTeamName] = useState("");
  const [reviewTeamId, setReviewTeamId] = useState("");
  const [reviewMemberUserId, setReviewMemberUserId] = useState("");
  const [reviewMemberDisplayName, setReviewMemberDisplayName] = useState("");
  const [reviewMemberRole, setReviewMemberRole] = useState<"secondary" | "adjudicator">("secondary");
  const [reviewMemberCapacity, setReviewMemberCapacity] = useState(5);
  const [reviewRouteRole, setReviewRouteRole] = useState<"secondary" | "adjudicator">("secondary");
  const [reviewDirectoryRole, setReviewDirectoryRole] = useState<"secondary" | "adjudicator">("secondary");
  const [reviewDirectoryGroupId, setReviewDirectoryGroupId] = useState("");
  const [reviewDirectoryInterval, setReviewDirectoryInterval] = useState(60);
  const [reviewInboxLoadingMore, setReviewInboxLoadingMore] = useState(false);
  const [reviewAssignmentAction, setReviewAssignmentAction] = useState<string | null>(null);
  const [reviewAction, setReviewAction] = useState<string | null>(null);
  const [reviewPurpose, setReviewPurpose] = useState<"production" | "benchmark">("production");
  const [reviewDrafts, setReviewDrafts] = useState<Record<string, { label: string; rationale: string }>>({});
  const [sourceRegistry, setSourceRegistry] = useState<SourceRegistryEntry[]>([]);
  const [sourceRegistryError, setSourceRegistryError] = useState<string | null>(null);
  const [integrityAudit, setIntegrityAudit] = useState<EvidenceIntegrityAudit | null>(null);
  const [integrityAuditError, setIntegrityAuditError] = useState<string | null>(null);
  const [integrityAuditRunning, setIntegrityAuditRunning] = useState(false);
  const [sourceReviewHost, setSourceReviewHost] = useState("");
  const [sourceReviewBusy, setSourceReviewBusy] = useState(false);
  const [sourceReviewForm, setSourceReviewForm] = useState({
    sourceCategoryL1: "other" as NonNullable<SourceRegistryEntry["current_revision"]>["source_category_l1"],
    sourceType: "unknown",
    ecosystem: "",
    classificationConfidence: "low" as NonNullable<SourceRegistryEntry["current_revision"]>["classification_confidence"],
    authorityLevel: "unknown" as NonNullable<SourceRegistryEntry["current_revision"]>["authority_level"],
    usagePolicy: "context_only" as NonNullable<SourceRegistryEntry["current_revision"]>["usage_policy"],
    riskLevel: "medium" as NonNullable<SourceRegistryEntry["current_revision"]>["risk_level"],
    evidenceNote: "",
    evidenceUrl: "",
    validUntil: "",
    supersedesRevisionId: "",
  });

  useEffect(() => {
    if (!selected?.snapshot_id || sampleDetailScrollTargetRef.current !== selected.snapshot_id) return;
    sampleDetailScrollTargetRef.current = null;
    const animationFrame = window.requestAnimationFrame(() => {
      document.getElementById("evidence-sample-detail")?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
    return () => window.cancelAnimationFrame(animationFrame);
  }, [selected?.snapshot_id]);

  useEffect(() => {
    if (!project.id) {
      setSourceRegistry([]);
      setSourceRegistryError(null);
      return;
    }
    const controller = new AbortController();
    fetchSourceRegistry(project.id, controller.signal)
      .then((rows) => {
        setSourceRegistry(rows);
        setSourceRegistryError(null);
      })
      .catch((error) => {
        if (controller.signal.aborted) return;
        setSourceRegistry([]);
        setSourceRegistryError(error instanceof Error ? error.message : "来源注册表接口不可用");
      });
    return () => controller.abort();
  }, [project.id]);

  useEffect(() => {
    if (!project.id) {
      setReviewInbox(null);
      setReviewInboxError(null);
      return;
    }
    const controller = new AbortController();
    fetchEvidenceReviewInbox(project.id, undefined, controller.signal)
      .then((queue) => {
        setReviewInbox(queue);
        setReviewInboxError(null);
      })
      .catch((error) => {
        if (controller.signal.aborted) return;
        setReviewInbox(null);
        setReviewInboxError(error instanceof Error ? error.message : "项目独立复核待办不可用");
      });
    return () => controller.abort();
  }, [project.id]);

  useEffect(() => {
    if (!project.id) {
      setReviewEscalations(null);
      setReviewEscalationError(null);
      return;
    }
    const controller = new AbortController();
    fetchEvidenceReviewEscalations(project.id, controller.signal)
      .then((result) => {
        setReviewEscalations(result);
        setReviewEscalationError(null);
      })
      .catch((error) => {
        if (controller.signal.aborted) return;
        setReviewEscalations(null);
        setReviewEscalationError(error instanceof Error ? error.message : "SLA 升级事件不可用");
      });
    return () => controller.abort();
  }, [project.id]);

  useEffect(() => {
    if (!project.id) {
      setReviewRouting(null);
      setReviewRoutingError(null);
      setReviewTeamId("");
      return;
    }
    const controller = new AbortController();
    fetchEvidenceReviewerRouting(project.id, controller.signal)
      .then((routing) => {
        setReviewRouting(routing);
        setReviewRoutingError(null);
        setReviewTeamId((current) =>
          routing.teams.some((team) => team.team_id === current)
            ? current
            : routing.teams.find((team) => team.status === "active")?.team_id ?? "",
        );
      })
      .catch((error) => {
        if (controller.signal.aborted) return;
        setReviewRouting(null);
        setReviewRoutingError(error instanceof Error ? error.message : "审核团队路由不可用");
      });
    return () => controller.abort();
  }, [project.id]);

  useEffect(() => {
    if (!project.id) {
      setIntegrityAudit(null);
      setIntegrityAuditError(null);
      return;
    }
    const controller = new AbortController();
    fetchLatestEvidenceIntegrityAudit(project.id, controller.signal)
      .then((audit) => {
        setIntegrityAudit(audit);
        setIntegrityAuditError(null);
      })
      .catch((error) => {
        if (controller.signal.aborted) return;
        setIntegrityAudit(null);
        setIntegrityAuditError(error instanceof Error ? error.message : "证据完整性巡检接口不可用");
      });
    return () => controller.abort();
  }, [project.id]);

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
    setShowAllCitations(false);
    setCitationBatch(null);
    setCitationClaimText("");
    setCitationClaimId("");
    setCitationClaimBoundary(null);
  }, [selected?.snapshot_id]);

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
        setCitationClaimId((current) => data.claims.some((claim) => claim.claim_id === current) ? current : data.claims[0]?.claim_id || "");
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
    if (!selected?.snapshot_id || !project.id) {
      setFactAccuracy(null);
      setFactAccuracyError(null);
      setFacts([]);
      return;
    }
    const controller = new AbortController();
    Promise.all([
      fetchFactAccuracy(selected.snapshot_id, controller.signal),
      fetchFacts(project.id, controller.signal),
    ])
      .then(([bundle, factRows]) => {
        setFactAccuracy(bundle);
        setFacts(factRows.filter((fact) => fact.eligible_for_generation));
        setFactClaimId((current) => bundle.claims.some((claim) => claim.claim_id === current) ? current : bundle.claims.find((claim) => claim.claim_kind === "brand_fact" || claim.claim_kind === "competitor_fact")?.claim_id || "");
        setFactRevisionId((current) => factRows.some((fact) => fact.revision_id === current && fact.eligible_for_generation) ? current : factRows.find((fact) => fact.eligible_for_generation)?.revision_id || "");
        setFactAccuracyError(null);
      })
      .catch((error) => {
        if (controller.signal.aborted) return;
        setFactAccuracy(null);
        setFacts([]);
        setFactAccuracyError(error instanceof Error ? error.message : "事实准确性接口不可用");
      });
    return () => controller.abort();
  }, [project.id, selected?.snapshot_id]);

  useEffect(() => {
    if (!project.id || !selected?.snapshot_id) {
      setReviewQueue(null);
      setReviewQueueError(null);
      return;
    }
    const controller = new AbortController();
    fetchEvidenceReviewCases(project.id, selected.snapshot_id, controller.signal)
      .then((queue) => {
        setReviewQueue(queue);
        setReviewQueueError(null);
      })
      .catch((error) => {
        if (controller.signal.aborted) return;
        setReviewQueue(null);
        setReviewQueueError(error instanceof Error ? error.message : "双人复核队列不可用");
      });
    return () => controller.abort();
  }, [project.id, selected?.snapshot_id]);

  useEffect(() => {
    if (!selected?.snapshot_id || selected.citations.length === 0) {
      setCitationCaptures({});
      setCitationActionError(null);
      return;
    }
    const controller = new AbortController();
    fetchLatestCitationSourceCaptures(selected.snapshot_id, controller.signal)
      .then((rows) => {
        setCitationCaptures(Object.fromEntries(
          rows.map((capture) => [capture.citation_id, [capture]]),
        ));
        setCitationActionError(null);
      })
      .catch((error) => {
        if (controller.signal.aborted) return;
        setCitationCaptures({});
        setCitationActionError(error instanceof Error ? error.message : "引用来源抓取接口不可用");
      });
    return () => controller.abort();
  }, [selected?.snapshot_id]);

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
    const bundle = await fetchCitationSupport(selected.snapshot_id);
    setCitationSupport(bundle);
    setCitationClaimId((current) => bundle.claims.some((claim) => claim.claim_id === current) ? current : bundle.claims[0]?.claim_id || "");
  };
  const refreshFactAccuracy = async () => {
    if (!selected?.snapshot_id) return;
    const bundle = await fetchFactAccuracy(selected.snapshot_id);
    setFactAccuracy(bundle);
    setFactClaimId((current) => bundle.claims.some((claim) => claim.claim_id === current) ? current : bundle.claims.find((claim) => claim.claim_kind === "brand_fact" || claim.claim_kind === "competitor_fact")?.claim_id || "");
  };
  const refreshReviewQueue = async () => {
    if (!project.id || !selected?.snapshot_id) return;
    setReviewQueue(await fetchEvidenceReviewCases(project.id, selected.snapshot_id));
  };
  const refreshReviewInbox = async () => {
    if (!project.id) return;
    try {
      setReviewInbox(await fetchEvidenceReviewInbox(project.id));
      setReviewInboxError(null);
    } catch (error) {
      setReviewInboxError(error instanceof Error ? error.message : "项目独立复核待办刷新失败");
    }
  };
  const refreshReviewRouting = async () => {
    if (!project.id) return;
    const routing = await fetchEvidenceReviewerRouting(project.id);
    setReviewRouting(routing);
    setReviewTeamId((current) =>
      routing.teams.some((team) => team.team_id === current)
        ? current
        : routing.teams.find((team) => team.status === "active")?.team_id ?? "",
    );
    setReviewRoutingError(null);
  };
  const submitReviewTeam = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!project.id || !reviewTeamName.trim()) return;
    setReviewRoutingBusy("team");
    setReviewRoutingError(null);
    try {
      const routing = await createEvidenceReviewerTeam(project.id, reviewTeamName);
      setReviewRouting(routing);
      const created = routing.teams.find((team) => team.name === reviewTeamName.trim());
      if (created) setReviewTeamId(created.team_id);
      setReviewTeamName("");
    } catch (error) {
      setReviewRoutingError(error instanceof Error ? error.message : "审核团队创建失败");
    } finally {
      setReviewRoutingBusy(null);
    }
  };
  const submitReviewTeamMember = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!project.id || !reviewTeamId || !reviewMemberUserId.trim()) return;
    setReviewRoutingBusy("member");
    setReviewRoutingError(null);
    try {
      setReviewRouting(await upsertEvidenceReviewerTeamMember(
        project.id,
        reviewTeamId,
        reviewMemberUserId.trim(),
        reviewMemberRole,
        {
          displayName: reviewMemberDisplayName,
          maxActiveAssignments: reviewMemberCapacity,
          expectedVersion: reviewRouting?.teams
            .find((team) => team.team_id === reviewTeamId)
            ?.members.find(
              (member) => member.user_id === reviewMemberUserId.trim()
                && member.reviewer_role === reviewMemberRole,
            )?.version,
        },
      ));
      setReviewMemberUserId("");
      setReviewMemberDisplayName("");
      await refreshReviewInbox();
    } catch (error) {
      setReviewRoutingError(error instanceof Error ? error.message : "审核成员保存失败");
    } finally {
      setReviewRoutingBusy(null);
    }
  };
  const submitReviewRoute = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!project.id || !reviewTeamId) return;
    setReviewRoutingBusy("route");
    setReviewRoutingError(null);
    try {
      const currentRoute = reviewRouting?.routes.find(
        (route) => route.reviewer_role === reviewRouteRole,
      );
      setReviewRouting(await putEvidenceReviewerRoute(
        project.id,
        reviewRouteRole,
        reviewTeamId,
        currentRoute?.version,
      ));
      await refreshReviewInbox();
    } catch (error) {
      setReviewRoutingError(error instanceof Error ? error.message : "审核角色路由保存失败");
      await refreshReviewRouting().catch(() => undefined);
    } finally {
      setReviewRoutingBusy(null);
    }
  };
  const submitReviewDirectoryBinding = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!project.id || !reviewTeamId || !reviewDirectoryGroupId.trim()) return;
    setReviewRoutingBusy("directory-binding");
    setReviewRoutingError(null);
    try {
      const existingBinding = reviewRouting?.sync_bindings.find(
        (binding) => binding.team_id === reviewTeamId
          && binding.reviewer_role === reviewDirectoryRole,
      );
      setReviewRouting(await putEvidenceReviewerDirectoryBinding(
        project.id,
        reviewTeamId,
        reviewDirectoryRole,
        {
          externalGroupId: reviewDirectoryGroupId,
          syncIntervalMinutes: reviewDirectoryInterval,
          defaultMaxActiveAssignments: reviewMemberCapacity,
          expectedVersion: existingBinding?.version,
        },
      ));
      setReviewDirectoryGroupId("");
    } catch (error) {
      setReviewRoutingError(error instanceof Error ? error.message : "Yudao 审核组绑定失败");
      await refreshReviewRouting().catch(() => undefined);
    } finally {
      setReviewRoutingBusy(null);
    }
  };
  const runReviewDirectorySync = async (
    teamId: string,
    reviewerRole: "secondary" | "adjudicator",
  ) => {
    if (!project.id) return;
    const busyKey = `directory-sync:${teamId}:${reviewerRole}`;
    setReviewRoutingBusy(busyKey);
    setReviewRoutingError(null);
    try {
      setReviewRouting(await runEvidenceReviewerDirectorySync(
        project.id,
        teamId,
        reviewerRole,
      ));
      await refreshReviewInbox();
    } catch (error) {
      setReviewRoutingError(error instanceof Error ? error.message : "Yudao 审核组同步失败");
      await refreshReviewRouting().catch(() => undefined);
    } finally {
      setReviewRoutingBusy(null);
    }
  };
  const loadMoreReviewInbox = async () => {
    if (!project.id || !reviewInbox?.next_cursor || reviewInboxLoadingMore) return;
    setReviewInboxLoadingMore(true);
    setReviewInboxError(null);
    try {
      const next = await fetchEvidenceReviewInbox(project.id, reviewInbox.next_cursor);
      setReviewInbox((current) => {
        if (!current) return next;
        const existing = new Set(current.cases.map((reviewCase) => reviewCase.case_id));
        return {
          ...next,
          cases: [...current.cases, ...next.cases.filter((reviewCase) => !existing.has(reviewCase.case_id))],
        };
      });
    } catch (error) {
      setReviewInboxError(error instanceof Error ? error.message : "项目独立复核待办翻页失败");
    } finally {
      setReviewInboxLoadingMore(false);
    }
  };
  const claimReviewAssignment = async (reviewCase: EvidenceReviewCase) => {
    const actionKey = `${reviewCase.case_id}:claim`;
    setReviewAssignmentAction(actionKey);
    setReviewInboxError(null);
    try {
      await claimEvidenceReviewAssignment(reviewCase.case_id, reviewCase.version);
      await refreshReviewInbox();
    } catch (error) {
      setReviewInboxError(error instanceof Error ? error.message : "复核任务领取失败");
    } finally {
      setReviewAssignmentAction(null);
    }
  };
  const heartbeatReviewAssignment = async (reviewCase: EvidenceReviewCase) => {
    const assignment = reviewCase.assignment;
    if (!assignment?.assignment_id || !assignment.version) return;
    const actionKey = `${reviewCase.case_id}:heartbeat`;
    setReviewAssignmentAction(actionKey);
    setReviewInboxError(null);
    try {
      await heartbeatEvidenceReviewAssignment(assignment.assignment_id, assignment.version);
      await refreshReviewInbox();
    } catch (error) {
      setReviewInboxError(error instanceof Error ? error.message : "复核任务续租失败");
    } finally {
      setReviewAssignmentAction(null);
    }
  };
  const releaseReviewAssignment = async (reviewCase: EvidenceReviewCase) => {
    const assignment = reviewCase.assignment;
    if (!assignment?.assignment_id || !assignment.version) return;
    const actionKey = `${reviewCase.case_id}:release`;
    setReviewAssignmentAction(actionKey);
    setReviewInboxError(null);
    try {
      await releaseEvidenceReviewAssignment(
        assignment.assignment_id,
        assignment.version,
        "当前审核人主动释放，返回未分配队列。",
      );
      await refreshReviewInbox();
    } catch (error) {
      setReviewInboxError(error instanceof Error ? error.message : "复核任务释放失败");
    } finally {
      setReviewAssignmentAction(null);
    }
  };
  const refreshQuality = async () => {
    if (!project.id || !selectedRunId) return;
    setQuality(await fetchMeasurementQuality(project.id, selectedRunId));
  };
  const useSelectedAnswerText = () => {
    if (!selected || !answerTextRef.current) return;
    const selection = window.getSelection();
    if (!selection || selection.rangeCount === 0 || selection.isCollapsed) {
      setCitationActionError("请先在上方不可变回答中选中一段完整、可独立核验的原句。");
      return;
    }
    const range = selection.getRangeAt(0);
    const answerElement = answerTextRef.current;
    if (
      !answerElement.contains(range.startContainer)
      || !answerElement.contains(range.endContainer)
    ) {
      setCitationActionError("所选文本必须完整位于上方不可变回答内。");
      return;
    }
    const prefix = document.createRange();
    prefix.selectNodeContents(answerElement);
    prefix.setEnd(range.startContainer, range.startOffset);
    const start = prefix.toString().length;
    const claimText = range.toString();
    const end = start + claimText.length;
    if (!claimText.trim() || selected.answer_text.slice(start, end) !== claimText) {
      setCitationActionError("无法把当前选择映射到不可变回答边界，请重新选择完整原句。");
      return;
    }
    setCitationClaimText(claimText);
    setCitationClaimBoundary({ start, end });
    setCitationActionError(null);
  };
  const registerCitationClaim = async () => {
    if (!selected || selected.sample_status !== "valid") return;
    const claimText = citationClaimText.trim();
    let answerStart = -1;
    let answerEnd = -1;
    if (
      citationClaimBoundary
      && selected.answer_text.slice(citationClaimBoundary.start, citationClaimBoundary.end) === citationClaimText
    ) {
      answerStart = citationClaimBoundary.start;
      answerEnd = citationClaimBoundary.end;
    } else {
      answerStart = selected.answer_text.indexOf(claimText);
      answerEnd = answerStart + claimText.length;
      if (claimText && selected.answer_text.indexOf(claimText, answerEnd) >= 0) {
        setCitationActionError("该原句在回答中出现多次，请直接在上方回答中选取精确文本。");
        return;
      }
    }
    if (!claimText || answerStart < 0 || answerEnd <= answerStart) {
      setCitationActionError("请从上方回答选取，或粘贴回答中原样存在的一条完整断言。");
      return;
    }
    setCitationAction("claim");
    setCitationActionError(null);
    try {
      const claim = await createCitationClaim(selected.snapshot_id, answerStart, answerEnd);
      setCitationClaimId(claim.claim_id);
      setCitationClaimText("");
      setCitationClaimBoundary(null);
      await refreshCitationSupport();
    } catch (error) {
      setCitationActionError(error instanceof Error ? error.message : "回答断言登记失败");
    } finally {
      setCitationAction(null);
    }
  };
  const registerFactClaim = async () => {
    if (!selected || selected.sample_status !== "valid") return;
    const claimText = factClaimText.trim();
    const subject = factSubject.trim();
    const answerStart = selected.answer_text.indexOf(claimText);
    if (!claimText || answerStart < 0) {
      setFactAccuracyError("请粘贴回答中原样存在的完整事实句，系统必须保存精确回答边界。");
      return;
    }
    if (selected.answer_text.indexOf(claimText, answerStart + claimText.length) >= 0) {
      setFactAccuracyError("该文本在回答中出现多次，请扩大选择范围，使事实声明边界唯一。");
      return;
    }
    if (!subject) {
      setFactAccuracyError("请填写该事实声明对应的品牌、产品或竞品实体。");
      return;
    }
    setFactAction("register");
    setFactAccuracyError(null);
    try {
      const claim = await createCitationClaim(
        selected.snapshot_id,
        answerStart,
        answerStart + claimText.length,
        { claimKind: factClaimKind, subjectEntityText: subject },
      );
      setFactClaimId(claim.claim_id);
      setFactClaimText("");
      await Promise.all([refreshFactAccuracy(), refreshCitationSupport(), refreshQuality()]);
    } catch (error) {
      setFactAccuracyError(error instanceof Error ? error.message : "事实声明登记失败");
    } finally {
      setFactAction(null);
    }
  };
  const reviewFactClaim = async (
    verdict: "accurate" | "inaccurate" | "outdated" | "insufficient_evidence",
  ) => {
    if (!factClaimId) {
      setFactAccuracyError("请先选择一条事实声明。");
      return;
    }
    if (verdict !== "insufficient_evidence" && !factRevisionId) {
      setFactAccuracyError("确定性裁决必须绑定当前已审核、可公开且有原文边界的事实版本。");
      return;
    }
    if (!factRationale.trim()) {
      setFactAccuracyError("请填写人工核验依据。");
      return;
    }
    setFactAction(`review:${verdict}`);
    setFactAccuracyError(null);
    try {
      await createFactEvidenceReviewCase(project.id, factClaimId, {
        verdict,
        factRevisionId: verdict === "insufficient_evidence" ? undefined : factRevisionId,
        rationale: factRationale.trim(),
        purpose: reviewPurpose,
      });
      await Promise.all([refreshFactAccuracy(), refreshReviewQueue(), refreshReviewInbox(), refreshQuality()]);
    } catch (error) {
      setFactAccuracyError(error instanceof Error ? error.message : "事实准确性审核失败");
    } finally {
      setFactAction(null);
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
  const startCitationCaptureBatch = async () => {
    if (!selected) return;
    const citationIds = selected.citations
      .filter((citation) => {
        const status = citationCaptures[citation.citation_id]?.[0]?.status;
        return !status || status === "blocked" || status === "failed";
      })
      .slice(0, EVIDENCE_CITATION_INITIAL_LIMIT)
      .map((citation) => citation.citation_id);
    if (citationIds.length === 0) return;
    setCitationAction("capture:batch");
    setCitationActionError(null);
    try {
      const result = await createCitationSourceCaptureBatch(selected.snapshot_id, citationIds);
      setCitationBatch(result);
      const latest = await fetchLatestCitationSourceCaptures(selected.snapshot_id);
      setCitationCaptures(Object.fromEntries(
        latest.map((capture) => [capture.citation_id, [capture]]),
      ));
    } catch (error) {
      setCitationActionError(error instanceof Error ? error.message : "批量引用来源抓取创建失败");
    } finally {
      setCitationAction(null);
    }
  };
  const loadCitationCaptureDetail = async (citationId: string, captureId: string) => {
    setCitationActionError(null);
    try {
      const detail = await fetchCitationSourceCapture(captureId);
      setCitationCaptures((current) => {
        const rows = current[citationId] ?? [];
        const matchingIndex = rows.findIndex((row) => row.capture_id === captureId);
        return {
          ...current,
          [citationId]: matchingIndex >= 0
            ? rows.map((row, index) => index === matchingIndex ? detail : row)
            : [detail, ...rows],
        };
      });
    } catch (error) {
      setCitationActionError(error instanceof Error ? error.message : "引用来源正文读取失败");
    }
  };
  const refreshLatestCitationCaptureStatus = async () => {
    if (!selected) return;
    setCitationAction("capture:refresh");
    setCitationActionError(null);
    try {
      const latest = await fetchLatestCitationSourceCaptures(selected.snapshot_id);
      setCitationCaptures(Object.fromEntries(
        latest.map((capture) => [capture.citation_id, [capture]]),
      ));
    } catch (error) {
      setCitationActionError(error instanceof Error ? error.message : "引用来源状态刷新失败");
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
    const claim = citationSupport?.claims.find((item) => item.claim_id === citationClaimId);
    if (!claim || !capture.content_sha256 || !capture.raw_object_ref_id) {
      setCitationActionError("请先登记并选择具体回答断言，再等待来源抓取完成后复核。");
      return;
    }
    setCitationAction(`review:${citationId}:${supportLabel}`);
    setCitationActionError(null);
    try {
      await createCitationEvidenceReviewCase(project.id, claim.claim_id, {
        citationId,
        supportLabel,
        sourceExcerpt: segment.segment_text,
        sourceContentSha256: capture.content_sha256,
        sourceObjectRefId: capture.raw_object_ref_id,
        sourceCaptureId: capture.capture_id,
        sourceSegmentId: segment.segment_id,
        sourceStart: segment.source_start,
        sourceEnd: segment.source_end,
        purpose: reviewPurpose,
      });
      await Promise.all([refreshCitationSupport(), refreshReviewQueue(), refreshReviewInbox(), refreshQuality()]);
    } catch (error) {
      setCitationActionError(error instanceof Error ? error.message : "引用支持度复核失败");
    } finally {
      setCitationAction(null);
    }
  };
  const submitReviewCaseDecision = async (reviewCase: EvidenceReviewCase) => {
    const draft = reviewDrafts[reviewCase.case_id] ?? {
      label: reviewCase.review_kind === "citation_support" ? "supports" : "accurate",
      rationale: "独立核对不可变证据后提交复核结论。",
    };
    if (!draft.rationale.trim()) {
      setReviewQueueError("请填写独立复核或裁决依据。");
      return;
    }
    setReviewAction(reviewCase.case_id);
    setReviewQueueError(null);
    try {
      await submitEvidenceReviewDecision(reviewCase.case_id, {
        label: draft.label,
        rationale: draft.rationale.trim(),
      });
      await Promise.all([
        refreshReviewQueue(),
        refreshReviewInbox(),
        refreshCitationSupport(),
        refreshFactAccuracy(),
        refreshQuality(),
      ]);
    } catch (error) {
      setReviewQueueError(error instanceof Error ? error.message : "独立复核提交失败");
    } finally {
      setReviewAction(null);
    }
  };
  const openReviewCaseSample = async (reviewCase: EvidenceReviewCase) => {
    if (selected?.snapshot_id === reviewCase.snapshot_id) {
      document.getElementById("evidence-sample-detail")?.scrollIntoView({ behavior: "smooth", block: "start" });
      return;
    }
    sampleDetailScrollTargetRef.current = reviewCase.snapshot_id;
    await openSample(reviewCase.snapshot_id);
  };
  const openSourceReview = (entry: SourceRegistryEntry) => {
    const current = entry.current_revision;
    setSourceReviewHost(entry.normalized_host);
    setSourceReviewForm({
      sourceCategoryL1: current?.source_category_l1 ?? "other",
      sourceType: current?.source_type ?? "unknown",
      ecosystem: current?.ecosystem ?? "",
      classificationConfidence: current?.classification_confidence ?? "low",
      authorityLevel: current?.authority_level ?? "unknown",
      usagePolicy: current?.usage_policy ?? "context_only",
      riskLevel: current?.risk_level ?? "medium",
      evidenceNote: "",
      evidenceUrl: current?.evidence_url ?? "",
      validUntil: current?.valid_until?.slice(0, 10) ?? "",
      supersedesRevisionId: current?.revision_id ?? "",
    });
    setSourceRegistryError(null);
  };
  const submitSourceReview = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!project.id || !sourceReviewHost) return;
    if (!/^[a-z0-9_-]+$/.test(sourceReviewForm.sourceType)) {
      setSourceRegistryError("来源细分类只能使用小写字母、数字、下划线或连字符。");
      return;
    }
    if (sourceReviewForm.evidenceNote.trim().length < 8) {
      setSourceRegistryError("请填写至少 8 个字符的人工分类依据；系统不会自动猜测权威度。");
      return;
    }
    setSourceReviewBusy(true);
    setSourceRegistryError(null);
    try {
      const reviewed = await reviewSourceRegistryEntry(project.id, sourceReviewHost, {
        ...sourceReviewForm,
        validUntil: sourceReviewForm.validUntil ? `${sourceReviewForm.validUntil}T23:59:59Z` : undefined,
        supersedesRevisionId: sourceReviewForm.supersedesRevisionId || undefined,
      });
      setSourceRegistry((current) => current.map((entry) => entry.normalized_host === reviewed.normalized_host ? reviewed : entry));
      setSourceReviewHost("");
    } catch (error) {
      setSourceRegistryError(error instanceof Error ? error.message : "来源人工复核失败");
    } finally {
      setSourceReviewBusy(false);
    }
  };
  const executeIntegrityAudit = async () => {
    if (!project.id || integrityAuditRunning) return;
    setIntegrityAuditRunning(true);
    setIntegrityAuditError(null);
    try {
      const audit = await runEvidenceIntegrityAudit(project.id);
      setIntegrityAudit(audit);
    } catch (error) {
      setIntegrityAuditError(error instanceof Error ? error.message : "证据完整性巡检执行失败");
    } finally {
      setIntegrityAuditRunning(false);
    }
  };
  const selectedProviderRequest = selected?.request_metadata.provider_request;
  const selectedSourcePanelStatus = selectedProviderRequest
    && typeof selectedProviderRequest === "object"
    && "source_panel_status" in selectedProviderRequest
    && typeof selectedProviderRequest.source_panel_status === "string"
      ? selectedProviderRequest.source_panel_status
      : null;
  const selectedRouteId = selectedProviderRequest
    && typeof selectedProviderRequest === "object"
    && "route_id" in selectedProviderRequest
    && typeof selectedProviderRequest.route_id === "string"
      ? selectedProviderRequest.route_id
      : null;
  const selectedSearchEvidence = selectedProviderRequest
    && typeof selectedProviderRequest === "object"
    && "search_evidence" in selectedProviderRequest
    && typeof selectedProviderRequest.search_evidence === "string"
      ? selectedProviderRequest.search_evidence
      : null;
  const selectedCitationParserVersion = selectedProviderRequest
    && typeof selectedProviderRequest === "object"
    && "citation_parser_version" in selectedProviderRequest
    && typeof selectedProviderRequest.citation_parser_version === "string"
      ? selectedProviderRequest.citation_parser_version
      : null;
  const selectedRequestContract = selectedProviderRequest
    && typeof selectedProviderRequest === "object"
    && "request_contract" in selectedProviderRequest
    && selectedProviderRequest.request_contract
    && typeof selectedProviderRequest.request_contract === "object"
      ? selectedProviderRequest.request_contract
      : null;
  const selectedRequestKind = selectedRequestContract
    && "request_kind" in selectedRequestContract
    && typeof selectedRequestContract.request_kind === "string"
      ? selectedRequestContract.request_kind
      : null;
  const pendingCitationCaptureCount = selected?.citations.filter((citation) => {
    const status = citationCaptures[citation.citation_id]?.[0]?.status;
    return !status || status === "blocked" || status === "failed";
  }).length ?? 0;
  const activeCitationCaptureCount = selected?.citations.filter((citation) => {
    const status = citationCaptures[citation.citation_id]?.[0]?.status;
    return status === "queued" || status === "running";
  }).length ?? 0;
  const completedCitationCaptureCount = selected?.citations.filter(
    (citation) => citationCaptures[citation.citation_id]?.[0]?.status === "completed",
  ).length ?? 0;
  const actionableReviewCases = reviewInbox?.cases ?? [];

  return (
    <>
      <PageHeader title="证据中心" subtitle="从指标下钻到不可变回答、真实引用、请求元数据与证据对象；未提及样本同样保留并计入分母。" />
      <div className="evidence-toolbar">
        <label>测量批次<select value={selectedRunId} onChange={(event) => { setSelectedRunId(event.target.value); setSelected(null); }}>{runs.map((run) => <option value={run.run_id} key={run.run_id}>{run.run_id} · {run.status}</option>)}</select></label>
        <span>顶部统计由服务端按完整批次聚合，不跨 run 混算；表格显示最近 {samples.length}/{sampleSummary.total} 条。</span>
      </div>
      <Panel title="审核团队与角色路由">
        <p className="rail-caption">
          未配置路由时系统明确处于兼容模式；一旦配置，第二审核与第三人裁决只向对应团队成员开放，并按成员的活跃领取上限控制容量。可按角色绑定 Yudao 部门并保留每次目录响应哈希；手工成员仍不代表外部资格，Yudao 服务凭证只允许由服务端安全注入。外部通知送达仍未验证。
        </p>
        {reviewRoutingError && <DataStateCard title="审核团队路由操作失败" desc={reviewRoutingError} tone="danger" />}
        {reviewRouting && (
          <>
            <dl className="evidence-metadata review-routing-metrics">
              <div><dt>路由模式</dt><dd><Badge tone={reviewRouting.routing_mode === "team_routed" ? "success" : reviewRouting.routing_mode === "blocked" ? "danger" : "warning"}>{reviewRouting.routing_mode}</Badge></dd></div>
              <div><dt>审核团队</dt><dd>{reviewRouting.teams.length}</dd></div>
              <div><dt>角色路由</dt><dd>{reviewRouting.routes.length} / 2</dd></div>
              <div><dt>Yudao 绑定</dt><dd>{reviewRouting.sync_bindings.length} / 2</dd></div>
              <div><dt>外部同步</dt><dd>{reviewRouting.external_sync_state}</dd></div>
            </dl>
            <div className="review-routing-layout">
              <div className="review-routing-forms">
                <form className="review-routing-form" onSubmit={(event) => void submitReviewTeam(event)}>
                  <strong>1. 建立本地审核团队</strong>
                  <label>团队名称<input required maxLength={160} value={reviewTeamName} onChange={(event) => setReviewTeamName(event.target.value)} placeholder="如：核心证据复核组" /></label>
                  <button className="airank-console-primary-button" type="submit" disabled={reviewRoutingBusy !== null || !reviewTeamName.trim()}>{reviewRoutingBusy === "team" ? "创建中…" : "创建团队"}</button>
                </form>
                <form className="review-routing-form" onSubmit={(event) => void submitReviewTeamMember(event)}>
                  <strong>2. 添加角色成员</strong>
                  <label>审核团队<select required value={reviewTeamId} onChange={(event) => setReviewTeamId(event.target.value)}><option value="">请选择</option>{reviewRouting.teams.filter((team) => team.status === "active").map((team) => <option value={team.team_id} key={team.team_id}>{team.name}</option>)}</select></label>
                  <label>用户 ID<input required maxLength={128} value={reviewMemberUserId} onChange={(event) => setReviewMemberUserId(event.target.value)} placeholder="必须与登录身份一致" /></label>
                  <label>显示名称<input maxLength={160} value={reviewMemberDisplayName} onChange={(event) => setReviewMemberDisplayName(event.target.value)} placeholder="可选" /></label>
                  <label>审核角色<select value={reviewMemberRole} onChange={(event) => setReviewMemberRole(event.target.value as typeof reviewMemberRole)}><option value="secondary">第二审核</option><option value="adjudicator">第三人裁决</option></select></label>
                  <label>同时领取上限<input type="number" min={1} max={100} value={reviewMemberCapacity} onChange={(event) => setReviewMemberCapacity(Math.max(1, Math.min(100, Number(event.target.value) || 1)))} /></label>
                  <button className="airank-console-primary-button" type="submit" disabled={reviewRoutingBusy !== null || !reviewTeamId || !reviewMemberUserId.trim()}>{reviewRoutingBusy === "member" ? "保存中…" : "保存成员"}</button>
                </form>
                <form className="review-routing-form" onSubmit={(event) => void submitReviewRoute(event)}>
                  <strong>3. 绑定角色路由</strong>
                  <label>审核角色<select value={reviewRouteRole} onChange={(event) => setReviewRouteRole(event.target.value as typeof reviewRouteRole)}><option value="secondary">第二审核</option><option value="adjudicator">第三人裁决</option></select></label>
                  <label>目标团队<select required value={reviewTeamId} onChange={(event) => setReviewTeamId(event.target.value)}><option value="">请选择</option>{reviewRouting.teams.filter((team) => team.status === "active").map((team) => <option value={team.team_id} key={team.team_id}>{team.name}</option>)}</select></label>
                  <button className="airank-console-primary-button" type="submit" disabled={reviewRoutingBusy !== null || !reviewTeamId}>{reviewRoutingBusy === "route" ? "保存中…" : "保存角色路由"}</button>
                </form>
                <form className="review-routing-form" onSubmit={(event) => void submitReviewDirectoryBinding(event)}>
                  <strong>4. 绑定 Yudao 审核组</strong>
                  <label>审核团队<select required value={reviewTeamId} onChange={(event) => setReviewTeamId(event.target.value)}><option value="">请选择</option>{reviewRouting.teams.filter((team) => team.status === "active").map((team) => <option value={team.team_id} key={team.team_id}>{team.name}</option>)}</select></label>
                  <label>同步角色<select value={reviewDirectoryRole} onChange={(event) => setReviewDirectoryRole(event.target.value as typeof reviewDirectoryRole)}><option value="secondary">第二审核</option><option value="adjudicator">第三人裁决</option></select></label>
                  <label>Yudao 部门 ID<input required maxLength={128} value={reviewDirectoryGroupId} onChange={(event) => setReviewDirectoryGroupId(event.target.value)} placeholder="只填写部门 ID，不填写 Token" /></label>
                  <label>同步周期（分钟）<input type="number" min={15} max={10080} value={reviewDirectoryInterval} onChange={(event) => setReviewDirectoryInterval(Math.max(15, Math.min(10080, Number(event.target.value) || 60)))} /></label>
                  <small>同步后的成员按当前“同时领取上限”初始化；目录内容未变化时不会制造成员新版本。</small>
                  <button className="airank-console-primary-button" type="submit" disabled={reviewRoutingBusy !== null || !reviewTeamId || !reviewDirectoryGroupId.trim()}>{reviewRoutingBusy === "directory-binding" ? "保存中…" : "保存 Yudao 绑定"}</button>
                </form>
              </div>
              <div className="review-routing-summary">
                {reviewRouting.routes.length === 0 ? (
                  <DataStateCard title="尚未启用团队路由" desc="当前为 unrestricted_legacy 兼容模式。要进入可审计运营，请先添加成员，再分别绑定第二审核和第三人裁决路由。" tone="warning" />
                ) : reviewRouting.routes.map((route) => (
                  <article className="review-routing-card" key={route.route_id}>
                    <div><strong>{route.reviewer_role === "secondary" ? "第二审核" : "第三人裁决"} → {route.team_name}</strong><small>route v{route.version} · {route.routing_strategy}</small></div>
                    <Badge tone={route.routing_ready ? "success" : "danger"}>{route.routing_ready ? "可路由" : "已阻断"}</Badge>
                    <small>有效成员 {route.eligible_member_count} · 接收升级 {route.escalation_recipient_count}</small>
                  </article>
                ))}
                {reviewRouting.teams.map((team) => (
                  <article className="review-routing-card" key={team.team_id}>
                    <div><strong>{team.name}</strong><small>{team.external_source} · 外部同步 {team.external_sync_state}</small></div>
                    <Badge tone={team.member_count > 0 ? "primary" : "warning"}>{team.member_count} 人</Badge>
                    {team.members.map((member) => <small key={member.member_id}>{member.display_name || member.user_id} · {member.reviewer_role === "secondary" ? "第二审核" : "第三人裁决"} · 上限 {member.max_active_assignments} · 外部资格{member.external_membership_verified ? "已验证" : "未验证"}</small>)}
                  </article>
                ))}
                {reviewRouting.sync_bindings.length === 0 ? (
                  <DataStateCard title="尚未绑定 Yudao 审核组" desc="团队成员可先手工维护，但外部资格固定显示未验证。配置服务端凭证和部门绑定后，才能执行真实目录同步。" tone="warning" />
                ) : reviewRouting.sync_bindings.map((binding) => {
                  const busyKey = `directory-sync:${binding.team_id}:${binding.reviewer_role}`;
                  const latestRun = reviewRouting.recent_sync_runs.find(
                    (run) => run.binding_id === binding.binding_id,
                  );
                  return (
                    <article className="review-routing-card" key={binding.binding_id}>
                      <div>
                        <strong>Yudao · {binding.reviewer_role === "secondary" ? "第二审核" : "第三人裁决"}</strong>
                        <small>{binding.team_name} · 部门 {binding.external_group_id} · binding v{binding.version}</small>
                      </div>
                      <Badge tone={binding.last_sync_state === "verified" ? "success" : binding.last_sync_state === "failed" ? "danger" : "warning"}>{binding.last_sync_state}</Badge>
                      <small>周期 {binding.sync_interval_minutes} 分钟 · 下次 {binding.next_sync_at ? formatDateTime(binding.next_sync_at) : "未安排"}</small>
                      {latestRun && (
                        <small>
                          最近 {latestRun.status} · 发现 {latestRun.discovered_member_count} · 变更 {latestRun.upserted_member_count} · 停用 {latestRun.disabled_member_count}
                          {latestRun.response_sha256 ? ` · 响应 ${latestRun.response_sha256.slice(0, 12)}…` : ""}
                          {latestRun.error_code ? ` · ${latestRun.error_code}${latestRun.retryable ? "（可重试）" : ""}` : ""}
                        </small>
                      )}
                      <button className="outline-button" type="button" disabled={reviewRoutingBusy !== null || !binding.sync_enabled} onClick={() => void runReviewDirectorySync(binding.team_id, binding.reviewer_role)}>{reviewRoutingBusy === busyKey ? "同步中…" : "立即同步目录"}</button>
                    </article>
                  );
                })}
              </div>
            </div>
          </>
        )}
      </Panel>
      <Panel title={`我的独立复核待办 · ${reviewInbox?.actionable_count ?? 0}`}>
        <p className="rail-caption">
          这里按当前登录账号从整个项目汇总可执行的第二审核与第三人裁决。领取会建立持久租约和 SLA，其他审核人不会重复看到已领取任务；队列仍不显示同伴未终结标签，必须先打开原始样本、精确 Claim 和不可变来源，再提交决定。
        </p>
        {reviewInboxError && <DataStateCard title="项目复核待办读取失败" desc={reviewInboxError} tone="danger" />}
        {reviewInbox && (
          <>
            <dl className="evidence-metadata review-inbox-metrics">
              <div><dt>当前账号可执行</dt><dd>{reviewInbox.actionable_count}</dd></div>
              <div><dt>等待第二审核</dt><dd>{reviewInbox.awaiting_secondary_count}</dd></div>
              <div><dt>等待第三人裁决</dt><dd>{reviewInbox.adjudication_count}</dd></div>
              <div><dt>我已领取</dt><dd>{reviewInbox.assigned_to_me_count}</dd></div>
              <div><dt>待领取</dt><dd>{reviewInbox.unassigned_count}</dd></div>
              <div><dt>SLA 已逾期</dt><dd>{reviewInbox.overdue_count}</dd></div>
              <div><dt>当前已加载</dt><dd>{reviewInbox.cases.length} / {reviewInbox.actionable_count}</dd></div>
            </dl>
            {actionableReviewCases.length === 0 ? (
              <DataStateCard title="当前账号没有可执行复核" desc="可能尚未建立复核 case、当前账号已参与任务，或账号不在已配置角色团队内；请先核对上方路由状态和登录用户 ID。" tone="warning" />
            ) : (
              <div className="review-inbox-list">
                {actionableReviewCases.map((reviewCase) => (
                  <article className="review-inbox-card" key={reviewCase.case_id}>
                    <div>
                      <strong>{reviewCase.review_kind === "citation_support" ? "引用支持" : "事实准确性"} · {reviewCase.next_action === "adjudicate" ? "第三人裁决" : "第二人复核"}</strong>
                      <small>{reviewCase.purpose === "benchmark" ? `${reviewCase.benchmark_version} · 仅质量评测` : "生产指标复核"}</small>
                      <small>样本 {reviewCase.snapshot_id} · Claim {reviewCase.claim_id}</small>
                      <small>创建于 {formatDateTime(reviewCase.created_at)} · 证据 {reviewCase.evidence_basis_sha256.slice(0, 12)}…</small>
                      {reviewCase.assignment && (
                        <>
                          <small>
                            {reviewCase.assignment.state === "assigned_to_me"
                              ? `我已领取 · 租约至 ${formatDateTime(reviewCase.assignment.lease_expires_at)}`
                              : reviewCase.assignment.state === "expired"
                                ? "上一租约已过期 · 可重新领取"
                                : "尚未领取 · 当前账号可领取"}
                          </small>
                          <small>
                            SLA {reviewCase.assignment.sla_state === "overdue" ? "已逾期" : reviewCase.assignment.sla_state === "due_soon" ? "即将到期" : "进行中"}
                            {` · 截止 ${formatDateTime(reviewCase.assignment.due_at)}`}
                          </small>
                        </>
                      )}
                    </div>
                    <div className="review-inbox-actions">
                      {reviewCase.assignment?.state === "assigned_to_me" ? (
                        <>
                          <button className="table-action" type="button" disabled={reviewAssignmentAction !== null} onClick={() => void heartbeatReviewAssignment(reviewCase)}>
                            {reviewAssignmentAction === `${reviewCase.case_id}:heartbeat` ? "续租中" : "续租"}
                          </button>
                          <button className="table-action" type="button" disabled={reviewAssignmentAction !== null} onClick={() => void releaseReviewAssignment(reviewCase)}>
                            {reviewAssignmentAction === `${reviewCase.case_id}:release` ? "释放中" : "释放"}
                          </button>
                        </>
                      ) : (
                        <button className="table-action" type="button" disabled={reviewAssignmentAction !== null} onClick={() => void claimReviewAssignment(reviewCase)}>
                          {reviewAssignmentAction === `${reviewCase.case_id}:claim` ? "领取中" : "领取任务"}
                        </button>
                      )}
                      <button className="table-action" type="button" disabled={loadingDetail === reviewCase.snapshot_id} onClick={() => void openReviewCaseSample(reviewCase)}>
                        {loadingDetail === reviewCase.snapshot_id ? "读取中" : "打开证据样本"}
                      </button>
                    </div>
                  </article>
                ))}
              </div>
            )}
            {reviewInbox.next_cursor && (
              <div className="review-inbox-pagination">
                <small>服务端每页最多返回 {reviewInbox.limit} 条；争议裁决优先、同优先级按最早创建顺序。</small>
                <button className="table-action" type="button" disabled={reviewInboxLoadingMore} onClick={() => void loadMoreReviewInbox()}>
                  {reviewInboxLoadingMore ? "加载中" : `继续加载（${reviewInbox.cases.length}/${reviewInbox.actionable_count}）`}
                </button>
              </div>
            )}
          </>
        )}
      </Panel>
      <Panel title={`SLA 升级运营 · ${reviewEscalations?.escalation_count ?? 0}`}>
        <p className="rail-caption">
          这里只展示 Scheduler 已持久写入 Outbox 的真实逾期事件。pending 只表示等待 Consumer；只有安全 HTTPS Webhook 返回成功并写入不可变渠道回执，才显示“外部送达已验证”。未配置客户 Webhook、网络失败或仅有 Outbox 事件都不能冒充送达。
        </p>
        {reviewEscalationError && <DataStateCard title="SLA 升级事件读取失败" desc={reviewEscalationError} tone="danger" />}
        {reviewEscalations && (
          <>
            <dl className="evidence-metadata review-inbox-metrics">
              <div><dt>持久升级事件</dt><dd>{reviewEscalations.escalation_count}</dd></div>
              <div><dt>Outbox 待处理</dt><dd>{reviewEscalations.pending_count}</dd></div>
              <div><dt>已取得渠道回执</dt><dd>{reviewEscalations.published_count}</dd></div>
              <div><dt>处理失败</dt><dd>{reviewEscalations.failed_count}</dd></div>
              <div><dt>已取消</dt><dd>{reviewEscalations.canceled_count}</dd></div>
              <div><dt>外部送达已验证</dt><dd>{reviewEscalations.escalations.filter((event) => event.external_delivery_verified).length}</dd></div>
            </dl>
            {reviewEscalations.escalations.length === 0 ? (
              <DataStateCard
                title="尚无持久升级事件"
                desc={reviewInbox?.overdue_count
                  ? `当前有 ${reviewInbox.overdue_count} 条逾期待办，但 Scheduler 尚未写入升级 Outbox；系统不会把动态逾期状态冒充已通知。`
                  : "当前没有已持久化的审核 SLA 升级事件。"}
                tone={reviewInbox?.overdue_count ? "warning" : "success"}
              />
            ) : (
              <div className="review-inbox-list">
                {reviewEscalations.escalations.map((event) => (
                  <article className="review-inbox-card" key={event.event_id}>
                    <div>
                      <strong>{event.reviewer_role === "secondary" ? "第二人复核" : "第三人裁决"} · SLA 已升级</strong>
                      <small>Case {event.case_id}</small>
                      <small>截止 {formatDateTime(event.due_at)} · 已逾期 {formatOverdueDuration(event.overdue_seconds)}</small>
                      <small>升级于 {formatDateTime(event.escalated_at)} · 任务状态 {reviewAssignmentStateLabel(event.assignment_state)}</small>
                      <small>
                        路由 {event.routing_state}
                        {event.routing_team_id ? ` · 团队 ${event.routing_team_id} · route v${event.routing_route_version}` : " · 未配置团队"}
                      </small>
                      <small>可接收升级 {event.eligible_recipient_count} 人 · 外部成员同步 {event.external_sync_state}</small>
                      {event.delivery_channel && <small>渠道 {event.delivery_channel} · 尝试 {event.delivery_attempt_count} 次 · 端点 {event.delivery_endpoint_host || "未记录"}</small>}
                      {event.delivery_response_sha256 && <small>回执响应 {event.delivery_response_status ?? "-"} · hash {event.delivery_response_sha256.slice(0, 12)}…{event.provider_receipt_id ? ` · provider ${event.provider_receipt_id}` : ""}</small>}
                    </div>
                    <div className="review-inbox-actions">
                      <Badge tone={event.outbox_status === "failed" ? "danger" : event.outbox_status === "published" ? "success" : "warning"}>
                        Outbox {event.outbox_status}
                      </Badge>
                      <small>{event.external_delivery_verified ? `外部送达已验证 · ${event.delivered_at ? formatDateTime(event.delivered_at) : "已记录"}` : "外部送达未验证"}</small>
                    </div>
                  </article>
                ))}
              </div>
            )}
          </>
        )}
      </Panel>
      <Panel title="证据与派生指标完整性">
        <div className="integrity-audit-head">
          <p className="rail-caption">
            按项目逐条复验原始回答、Provider 原始响应、引用边界、知识与对象存储，并从不可变任务重算 ScanRun 任务数和复测报告。原始证据缺失或派生指标漂移都会阻断新客户证据包。
          </p>
          <button
            className="airank-console-primary-button"
            type="button"
            disabled={!project.id || integrityAuditRunning}
            onClick={() => void executeIntegrityAudit()}
          >
            {integrityAuditRunning ? "正在逐条校验…" : "执行全库巡检"}
          </button>
        </div>
        {integrityAuditError && <DataStateCard title="证据与指标巡检失败" desc={integrityAuditError} tone="danger" />}
        {!integrityAudit && !integrityAuditError ? (
          <DataStateCard title="尚未执行项目级完整性巡检" desc="生成客户证据包前必须执行；系统不会用对象存在、旧报告 hash 或单条读取成功冒充证据与指标一致。" tone="warning" />
        ) : integrityAudit ? (
          <>
            <dl className="evidence-metadata integrity-audit-metrics">
              <div><dt>巡检结论</dt><dd><Badge tone={integrityAudit.status === "passed" ? "success" : "danger"}>{integrityAudit.status === "passed" ? "通过" : "阻断"}</Badge></dd></div>
              <div><dt>逐条通过</dt><dd>{integrityAudit.verified_count} / {integrityAudit.entity_count}</dd></div>
              <div><dt>阻断项</dt><dd>{integrityAudit.blocking_finding_count}</dd></div>
              <div><dt>完成时间</dt><dd>{formatDateTime(integrityAudit.completed_at)}</dd></div>
            </dl>
            <p className="integrity-audit-hash">
              策略 {integrityAudit.policy_version} · Manifest SHA-256 <code>{integrityAudit.manifest_sha256}</code>
            </p>
            {integrityAudit.blocking_finding_count > 0 && (
              <div className="airank-console-card table-card evidence-table-wrap">
                <table className="question-table integrity-finding-table">
                  <thead><tr><th>证据类型</th><th>对象</th><th>异常</th><th>预期 / 实际</th></tr></thead>
                  <tbody>
                    {integrityAudit.findings.filter((finding) => finding.blocking).map((finding) => (
                      <tr key={finding.finding_id}>
                        <td><strong>{finding.entity_type}</strong><small>{finding.object_type ?? "数据库证据"}</small></td>
                        <td><strong>{finding.entity_id}</strong><small>finding {finding.finding_id}</small></td>
                        <td><Badge tone="danger">{finding.status}</Badge><small>{typeof finding.details.reason === "string" ? finding.details.reason : "完整性校验未通过"}</small></td>
                        <td><code>{finding.expected_sha256?.slice(0, 16) ?? "—"}</code><small><code>{finding.actual_sha256?.slice(0, 16) ?? "—"}</code></small></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
        ) : null}
      </Panel>
      <Panel title={`引用来源注册表 · ${sourceRegistry.length} 个已观测域名`}>
        <p className="rail-caption">
          这里只汇总当前项目 Citation 记录中实际出现的精确域名。未知来源保留为 unclassified；分类、权威度与用途必须由人工给出依据并形成追加版本，不能由域名或模型自动推断。
        </p>
        {sourceRegistryError && <DataStateCard title="来源注册表操作失败" desc={sourceRegistryError} tone="danger" />}
        {sourceRegistry.length === 0 ? (
          <DataStateCard title="尚无可分类的引用域名" desc="完成带来源引用的可验证采样后，这里才会出现来源；系统不会预置媒体数量或伪造权威来源。" tone="warning" />
        ) : (
          <div className="airank-console-card table-card evidence-table-wrap">
            <table className="question-table source-registry-table">
              <thead><tr><th>精确域名</th><th>Citation 出现</th><th>人工分类</th><th>权威 / 用途</th><th>复核证据</th><th>操作</th></tr></thead>
              <tbody>
                {sourceRegistry.map((entry) => {
                  const current = entry.current_revision;
                  return (
                    <tr key={entry.normalized_host}>
                      <td><strong>{entry.normalized_host}</strong><small>{entry.reviewable ? "可人工复核" : "历史主机格式异常，仅保留"}</small></td>
                      <td><strong>{entry.citation_count} 次引用</strong><small>{entry.sample_count} 个样本 · {entry.provider_count} 个平台</small></td>
                      <td>
                        <Badge tone={current?.effective ? "success" : current ? "warning" : "muted"}>{entry.classification_status}</Badge>
                        <small>{current ? `${sourceCategoryLabels[current.source_category_l1] ?? current.source_category_l1} · ${current.source_type}` : "未知来源，不猜测类型"}</small>
                      </td>
                      <td><strong>{current?.authority_level ?? "unknown"}</strong><small>{current ? sourceUsageLabels[current.usage_policy] ?? current.usage_policy : "尚无用途结论"}</small></td>
                      <td>{current ? <><strong>{current.classification_method} · v{current.revision_number}</strong><small>{current.reviewed_by} · {formatDateTime(current.reviewed_at)}</small></> : <><strong>待人工复核</strong><small>不进入权威来源结论</small></>}</td>
                      <td><button className="table-action" type="button" disabled={!entry.reviewable} onClick={() => openSourceReview(entry)}>{current ? "新增版本" : "人工分类"}</button></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
        {sourceReviewHost && (
          <form className="source-registry-form" onSubmit={(event) => void submitSourceReview(event)}>
            <div className="source-registry-form-head">
              <div><strong>人工复核 · {sourceReviewHost}</strong><span>提交后生成不可变新版本；旧版本不会被覆盖。</span></div>
              <button className="table-action" type="button" onClick={() => setSourceReviewHost("")}>取消</button>
            </div>
            <label>一级分类<select value={sourceReviewForm.sourceCategoryL1} onChange={(event) => setSourceReviewForm((current) => ({ ...current, sourceCategoryL1: event.target.value as typeof current.sourceCategoryL1 }))}>{Object.entries(sourceCategoryLabels).map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label>
            <label>来源细分类<input value={sourceReviewForm.sourceType} onChange={(event) => setSourceReviewForm((current) => ({ ...current, sourceType: event.target.value }))} placeholder="如 news_media / brand_corporate" /></label>
            <label>生态 / 主体<input value={sourceReviewForm.ecosystem} onChange={(event) => setSourceReviewForm((current) => ({ ...current, ecosystem: event.target.value }))} placeholder="可选，填写已核对的主体" /></label>
            <label>分类置信度<select value={sourceReviewForm.classificationConfidence} onChange={(event) => setSourceReviewForm((current) => ({ ...current, classificationConfidence: event.target.value as typeof current.classificationConfidence }))}><option value="low">低</option><option value="medium">中</option><option value="high">高</option></select></label>
            <label>权威等级<select value={sourceReviewForm.authorityLevel} onChange={(event) => setSourceReviewForm((current) => ({ ...current, authorityLevel: event.target.value as typeof current.authorityLevel }))}><option value="unknown">未知</option><option value="low">低</option><option value="medium">中</option><option value="high">高</option><option value="official">官方</option></select></label>
            <label>使用政策<select value={sourceReviewForm.usagePolicy} onChange={(event) => setSourceReviewForm((current) => ({ ...current, usagePolicy: event.target.value as typeof current.usagePolicy }))}><option value="primary_evidence">可作主要证据</option><option value="context_only">仅作背景</option><option value="lead_only">仅作线索</option><option value="prohibited">禁止使用</option></select></label>
            <label>风险等级<select value={sourceReviewForm.riskLevel} onChange={(event) => setSourceReviewForm((current) => ({ ...current, riskLevel: event.target.value as typeof current.riskLevel }))}><option value="low">低</option><option value="medium">中</option><option value="high">高</option><option value="critical">严重</option></select></label>
            <label>有效至<input type="date" value={sourceReviewForm.validUntil} onChange={(event) => setSourceReviewForm((current) => ({ ...current, validUntil: event.target.value }))} /></label>
            <label className="source-registry-form-wide">证据 URL<input value={sourceReviewForm.evidenceUrl} onChange={(event) => setSourceReviewForm((current) => ({ ...current, evidenceUrl: event.target.value }))} placeholder="可选；必须是无凭证、无 fragment 的 HTTPS 地址" /></label>
            <label className="source-registry-form-wide">人工分类依据<textarea rows={3} value={sourceReviewForm.evidenceNote} onChange={(event) => setSourceReviewForm((current) => ({ ...current, evidenceNote: event.target.value }))} placeholder="说明核对了什么页面、主体或样本，以及为什么采用该分类与用途。" /></label>
            <div className="source-registry-form-actions"><button className="airank-console-primary-button" type="submit" disabled={sourceReviewBusy}>{sourceReviewBusy ? "提交中…" : "保存人工复核版本"}</button></div>
          </form>
        )}
      </Panel>
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
        <section className="evidence-detail-grid" id="evidence-sample-detail">
          <Panel title={selected.sample_status === "valid" ? "不可变原始回答" : "不可变失败证据"}>
            {selected.sample_status === "valid"
              ? <div className="evidence-answer evidence-answer--selectable" ref={answerTextRef}>{selected.answer_text}</div>
              : <DataStateCard title="该任务没有有效回答" desc="系统保留了不可变失败快照、请求元数据和可用的阻塞截图；该样本不会被误算为品牌未提及。" tone={selected.sample_status === "blocked" ? "warning" : "danger"} />}
            <dl className="evidence-metadata">
              <div><dt>回答 SHA-256</dt><dd>{selected.answer_sha256 || "不适用（失败/阻塞样本）"}</dd></div>
              <div><dt>原始响应 SHA-256</dt><dd>{selected.raw_response_sha256}</dd></div>
              <div><dt>Evidence Snapshot</dt><dd>{selected.evidence_snapshot_id}</dd></div>
              <div><dt>采集时间</dt><dd>{formatDateTime(selected.evidence_captured_at)}</dd></div>
              <div><dt>会话</dt><dd>{selected.session_id}</dd></div>
              <div><dt>证据等级</dt><dd>{selected.evidence_level}</dd></div>
              <div><dt>Provider 路由</dt><dd>{selectedRouteId || "历史样本未记录"}</dd></div>
            </dl>
          </Panel>
          <Panel title="事实准确性 · 人工证据审核">
            {factAccuracyError && <DataStateCard title="事实准确性操作失败" desc={factAccuracyError} tone="danger" />}
            {factAccuracy && (
              <>
                <p className="rail-caption">
                  准确率只统计品牌/竞品事实声明；第一审核人必须绑定当前审核事实与精确来源边界，第二审核人独立判断。一致或第三人裁决后才进入商业指标。
                </p>
                <dl className="evidence-metadata fact-accuracy-metrics">
                  <div><dt>可交付准确率</dt><dd>{factAccuracy.metrics.fact_accuracy === null ? "待完成全量核验" : `${Math.round(factAccuracy.metrics.fact_accuracy * 100)}%`}</dd></div>
                  <div><dt>确定性覆盖</dt><dd>{factAccuracy.metrics.evaluation_coverage_rate === null ? "无事实声明" : `${Math.round(factAccuracy.metrics.evaluation_coverage_rate * 100)}%`}</dd></div>
                  <div><dt>事实声明 / 确定性审核</dt><dd>{factAccuracy.metrics.factual_claim_count} / {factAccuracy.metrics.decisive_claim_count}</dd></div>
                  <div><dt>准确 / 不准确 / 过期</dt><dd>{factAccuracy.metrics.accurate_count} / {factAccuracy.metrics.inaccurate_count} / {factAccuracy.metrics.outdated_count}</dd></div>
                </dl>
                {factAccuracy.metrics.known_limitations.length > 0 && (
                  <DataStateCard
                    title="事实准确率仍有限制"
                    desc={factAccuracy.metrics.known_limitations.map((item) => factAccuracyLimitationLabels[item] ?? item).join(" · ")}
                    tone="warning"
                  />
                )}
                {selected.sample_status === "valid" && (
                  <div className="fact-accuracy-form">
                    <label className="fact-accuracy-wide">回答中的事实原句<textarea rows={3} value={factClaimText} onChange={(event) => setFactClaimText(event.target.value)} placeholder="从上方不可变回答复制一条完整、唯一的事实句" /></label>
                    <label>声明类型<select value={factClaimKind} onChange={(event) => setFactClaimKind(event.target.value as "brand_fact" | "competitor_fact")}><option value="brand_fact">品牌事实</option><option value="competitor_fact">竞品事实</option></select></label>
                    <label>主体实体<input value={factSubject} onChange={(event) => setFactSubject(event.target.value)} placeholder="品牌、产品或竞品名" /></label>
                    <button className="outline-button fact-accuracy-wide" type="button" disabled={factAction === "register"} onClick={() => void registerFactClaim()}>{factAction === "register" ? "登记中" : "按精确回答边界登记"}</button>
                  </div>
                )}
                {factAccuracy.metrics.factual_claim_count > 0 && (
                  <div className="fact-review-workbench">
                    <label>事实声明<select value={factClaimId} onChange={(event) => setFactClaimId(event.target.value)}>{factAccuracy.claims.filter((claim) => claim.claim_kind === "brand_fact" || claim.claim_kind === "competitor_fact").map((claim) => <option value={claim.claim_id} key={claim.claim_id}>{claim.subject_entity_text || "未命名实体"} · {claim.claim_text.slice(0, 48)}</option>)}</select></label>
                    <label>审核事实版本<select value={factRevisionId} onChange={(event) => setFactRevisionId(event.target.value)}><option value="">请选择当前已审核事实</option>{facts.map((fact) => <option value={fact.revision_id} key={fact.revision_id}>#{fact.revision_number} {fact.title} · {fact.fact_text.slice(0, 42)}</option>)}</select></label>
                    <label>人工核验依据<textarea rows={2} value={factRationale} onChange={(event) => setFactRationale(event.target.value)} /></label>
                    {facts.length === 0 && <DataStateCard title="没有可绑定的审核事实" desc="请先在事实知识库添加来源并审核事实。缺少证据时只能记录“证据不足”，不能推断准确或错误。" tone="warning" />}
                    <div className="citation-review-actions">
                      <button type="button" className="table-action" disabled={!factRevisionId || factAction !== null} onClick={() => void reviewFactClaim("accurate")}>第一复核：准确</button>
                      <button type="button" className="table-action" disabled={!factRevisionId || factAction !== null} onClick={() => void reviewFactClaim("inaccurate")}>第一复核：不准确</button>
                      <button type="button" className="table-action" disabled={!factRevisionId || factAction !== null} onClick={() => void reviewFactClaim("outdated")}>第一复核：已过期</button>
                      <button type="button" className="table-action" disabled={factAction !== null} onClick={() => void reviewFactClaim("insufficient_evidence")}>第一复核：证据不足</button>
                    </div>
                  </div>
                )}
                {factAccuracy.metrics.factual_claim_count > 0 && (
                  <ol className="evidence-citations fact-accuracy-claims">
                    {factAccuracy.claims.filter((claim) => claim.claim_kind === "brand_fact" || claim.claim_kind === "competitor_fact").map((claim) => {
                      const reviews = factAccuracy.reviews.filter((review) => review.claim_id === claim.claim_id);
                      const latest = reviews[reviews.length - 1];
                      return <li key={claim.claim_id}><strong>{claim.claim_text}</strong><span>{claim.claim_kind === "brand_fact" ? "品牌事实" : "竞品事实"} · {claim.subject_entity_text || "主体未记录"} · 回答边界 {claim.answer_start}–{claim.answer_end}</span>{latest ? <span><Badge tone={latest.commercially_verified ? latest.verdict === "accurate" ? "success" : "danger" : "warning"}>{latest.verdict}</Badge> {latest.commercially_verified ? `双人复核证据 ${latest.fact_revision_sha256?.slice(0, 12)}…` : latest.evidence_verified ? "证据边界通过，等待独立复核/裁决" : "当前审核不进入商业指标"}</span> : <span>尚未审核</span>}</li>;
                    })}
                  </ol>
                )}
              </>
            )}
          </Panel>
          <Panel title="双人复核与一致性门禁">
            <p className="rail-caption">
              第一审核人的标签和依据在任务终结前不会向其他审核人展示；第二审核人必须使用不同账号独立提交。结论不一致时，必须再由第三个不同账号裁决。单人预审永远不会直接进入客户指标。
            </p>
            <label className="review-purpose-control">
              新建复核用途
              <select value={reviewPurpose} onChange={(event) => setReviewPurpose(event.target.value as "production" | "benchmark")}>
                <option value="production">生产指标复核</option>
                <option value="benchmark">一致性 Benchmark</option>
              </select>
              <small>Benchmark 任务只用于检验审核质量，不会进入客户生产指标。</small>
            </label>
            {reviewQueueError && <DataStateCard title="双人复核操作失败" desc={reviewQueueError} tone="danger" />}
            {reviewQueue && (
              <>
                <dl className="evidence-metadata review-quality-metrics">
                  <div><dt>生产任务完成</dt><dd>{reviewQueue.production_quality.finalized_case_count} / {reviewQueue.production_quality.case_count}</dd></div>
                  <div><dt>等待第二审核 / 裁决</dt><dd>{reviewQueue.production_quality.awaiting_secondary_count} / {reviewQueue.production_quality.disputed_count}</dd></div>
                  <div><dt>Benchmark 双人样本</dt><dd>{reviewQueue.benchmark_quality.independently_reviewed_case_count} / {reviewQueue.benchmark_quality.benchmark_minimum_case_count}</dd></div>
                  <div><dt>一致率 / Cohen’s kappa</dt><dd>{reviewQueue.benchmark_quality.raw_agreement_rate === null ? "样本不足" : `${Math.round(reviewQueue.benchmark_quality.raw_agreement_rate * 100)}%`} / {reviewQueue.benchmark_quality.cohen_kappa === null ? "不可估计" : reviewQueue.benchmark_quality.cohen_kappa.toFixed(3)}（门槛 ≥ {reviewQueue.benchmark_quality.benchmark_minimum_kappa.toFixed(2)}）</dd></div>
                </dl>
                {!reviewQueue.benchmark_quality.benchmark_quality_passed && (
                  <DataStateCard
                    title="人工标注 benchmark 尚未达门禁"
                    desc={reviewQueue.benchmark_quality.known_limitations.map((item) => reviewQualityLimitationLabels[item] ?? item).join(" · ")}
                    tone="warning"
                  />
                )}
                {reviewQueue.cases.length === 0 ? (
                  <DataStateCard title="当前样本尚无双人复核任务" desc="请先在事实准确性或引用来源片段中提交第一复核；系统不会把旧的单人审核自动升级成双人结论。" tone="warning" />
                ) : (
                  <div className="review-case-list">
                    {reviewQueue.cases.map((reviewCase) => {
                      const options = reviewCase.review_kind === "citation_support"
                        ? [["supports", "支持"], ["contradicts", "矛盾"], ["insufficient", "证据不足"]]
                        : [["accurate", "准确"], ["inaccurate", "不准确"], ["outdated", "已过期"], ["insufficient_evidence", "证据不足"]];
                      const draft = reviewDrafts[reviewCase.case_id] ?? {
                        label: options[0][0],
                        rationale: "独立核对不可变证据后提交复核结论。",
                      };
                      return (
                        <article className="review-case-card" key={reviewCase.case_id}>
                          <div className="review-case-heading">
                            <div><strong>{reviewCase.review_kind === "citation_support" ? "引用支持" : "事实准确性"}</strong><small>{reviewCase.purpose === "benchmark" ? reviewCase.benchmark_version : "生产复核"} · v{reviewCase.version}</small></div>
                            <Badge tone={reviewCase.status === "agreed" || reviewCase.status === "adjudicated" ? "success" : reviewCase.status === "disputed" ? "danger" : "warning"}>{reviewCaseStatusLabels[reviewCase.status]}</Badge>
                          </div>
                          <dl className="evidence-metadata">
                            <div><dt>证据基础</dt><dd>{reviewCase.evidence_basis_sha256.slice(0, 16)}…</dd></div>
                            <div><dt>已提交决定</dt><dd>{reviewCase.decision_count}</dd></div>
                            <div><dt>当前账号角色</dt><dd>{reviewCase.current_actor_role || "尚未参与"}</dd></div>
                            <div><dt>最终标签</dt><dd>{reviewCase.consensus_label || "未形成"}</dd></div>
                          </dl>
                          {reviewCase.visible_decisions.length > 0 && (
                            <ol className="review-decision-list">
                              {reviewCase.visible_decisions.map((decision) => <li key={decision.review_id}><strong>{decision.reviewer_role} · {decision.label}</strong><span>{decision.reviewed_by} · {decision.rationale}</span></li>)}
                            </ol>
                          )}
                          {(reviewCase.next_action === "submit_secondary" || reviewCase.next_action === "adjudicate") && (
                            <div className="review-decision-form">
                              <label>独立结论<select value={draft.label} onChange={(event) => setReviewDrafts((current) => ({ ...current, [reviewCase.case_id]: { ...draft, label: event.target.value } }))}>{options.map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label>
                              <label>审核依据<textarea rows={2} value={draft.rationale} onChange={(event) => setReviewDrafts((current) => ({ ...current, [reviewCase.case_id]: { ...draft, rationale: event.target.value } }))} /></label>
                              <button className="primary-button" type="button" disabled={reviewAction === reviewCase.case_id} onClick={() => void submitReviewCaseDecision(reviewCase)}>{reviewAction === reviewCase.case_id ? "提交中" : reviewCase.next_action === "adjudicate" ? "提交第三人裁决" : "提交第二人独立复核"}</button>
                            </div>
                          )}
                          {reviewCase.next_action === "none" && reviewCase.status === "awaiting_secondary" && <small>当前账号已完成第一复核，请由另一审核账号独立提交。</small>}
                          {reviewCase.next_action === "none" && reviewCase.status === "disputed" && <small>当前账号已参与该任务，请由第三个不同审核账号裁决。</small>}
                        </article>
                      );
                    })}
                  </div>
                )}
              </>
            )}
          </Panel>
          <Panel title={`${selected.sample_status === "valid" ? "真实引用" : "失败任务引用"}（${selected.citations.length}）`}>
            {selected.citations.length > 0 && (
              <div className="citation-batch-toolbar">
                <div>
                  <strong>批量准备来源正文</strong>
                  <small>每次最多安全入队 {EVIDENCE_CITATION_INITIAL_LIMIT} 条；抓取成功只代表页面已存证，不代表来源支持回答。</small>
                  <small>已完成 {completedCitationCaptureCount} · 队列中 {activeCitationCaptureCount} · 待处理/可重试 {pendingCitationCaptureCount}</small>
                </div>
                <div className="citation-batch-actions">
                  <button
                    className="outline-button"
                    type="button"
                    disabled={pendingCitationCaptureCount === 0 || citationAction !== null}
                    onClick={() => void startCitationCaptureBatch()}
                  >
                    {citationAction === "capture:batch"
                      ? "批量入队中…"
                      : pendingCitationCaptureCount === 0
                        ? "当前来源均已处理"
                        : `批量入队前 ${Math.min(EVIDENCE_CITATION_INITIAL_LIMIT, pendingCitationCaptureCount)} 条`}
                  </button>
                  <button className="table-action" type="button" disabled={citationAction !== null} onClick={() => void refreshLatestCitationCaptureStatus()}>
                    <RotateCw size={13} />{citationAction === "capture:refresh" ? "刷新中" : "刷新状态"}
                  </button>
                </div>
                {citationBatch && (
                  <small>本次请求 {citationBatch.requested_count} 条，新增入队 {citationBatch.queued_count} 条，幂等复用 {citationBatch.idempotent_replay_count} 条。</small>
                )}
              </div>
            )}
            {selected.citations.length === 0 ? <DataStateCard title="该样本没有原生引用" desc={selected.sample_status === "valid" ? "无引用是有效证据状态，不补造来源。" : "任务未产生有效回答，不把空引用误写成有效证据结论。"} tone="warning" /> : (
              <ol className="evidence-citations">
                {(showAllCitations
                  ? selected.citations
                  : selected.citations.slice(0, EVIDENCE_CITATION_INITIAL_LIMIT)
                ).map((citation) => {
                  const capture = citationCaptures[citation.citation_id]?.[0];
                  return (
                    <li key={citation.citation_id} className="citation-evidence-item">
                      <a href={citation.url} target="_blank" rel="noreferrer">{citation.title || citation.host || citation.url}<ExternalLink size={14} /></a>
                      <span>{citation.cited_text || "Provider 未返回引用原文"}</span>
                      <small>
                        原生结构 {typeof citation.metadata.native_type === "string" ? citation.metadata.native_type : "未记录"}
                        {typeof citation.metadata.source_path === "string" && citation.metadata.source_path ? ` · ${citation.metadata.source_path}` : ""}
                      </small>
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
                        <details
                          className="citation-source-capture"
                          onToggle={(event) => {
                            if (event.currentTarget.open && !capture.segments_loaded) {
                              void loadCitationCaptureDetail(citation.citation_id, capture.capture_id);
                            }
                          }}
                        >
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
                                <button type="button" className="table-action" disabled={!citationSupport?.claims.length || citationAction?.startsWith(`review:${citation.citation_id}`)} onClick={() => void reviewCitationSegment(citation.citation_id, capture, segment, "supports")}>第一复核：支持</button>
                                <button type="button" className="table-action" disabled={!citationSupport?.claims.length || citationAction?.startsWith(`review:${citation.citation_id}`)} onClick={() => void reviewCitationSegment(citation.citation_id, capture, segment, "contradicts")}>第一复核：矛盾</button>
                                <button type="button" className="table-action" disabled={!citationSupport?.claims.length || citationAction?.startsWith(`review:${citation.citation_id}`)} onClick={() => void reviewCitationSegment(citation.citation_id, capture, segment, "insufficient")}>第一复核：证据不足</button>
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
            {selected.citations.length > EVIDENCE_CITATION_INITIAL_LIMIT && (
              <button className="outline-button citation-list-toggle" type="button" onClick={() => setShowAllCitations((current) => !current)}>
                {showAllCitations
                  ? `收起到前 ${EVIDENCE_CITATION_INITIAL_LIMIT} 条`
                  : `展开全部 ${selected.citations.length} 条引用`}
              </button>
            )}
            <div className="citation-support-separator" />
            <strong>引用选择 ≠ 引用支持</strong>
            {citationActionError && <DataStateCard title="引用证据操作失败" desc={citationActionError} tone="danger" />}
            {citationSupportError && <DataStateCard title="引用支持度读取失败" desc={citationSupportError} tone="danger" />}
            {citationSupport && (
              <>
                <p className="rail-caption">
                  Provider 列出 {citationSupport.metrics.selected_citation_count} 个来源；已登记 {citationSupport.metrics.claim_count} 条回答断言，
                  当前有 {citationSupport.metrics.commercially_verified_review_count} 个“不可变来源页面 + 不同审核人一致/裁决”结论可进入支持率。
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
                {selected.sample_status === "valid" && (
                  <div className="citation-claim-form">
                    <label>回答中的待核验断言原句<textarea rows={3} value={citationClaimText} onChange={(event) => { setCitationClaimText(event.target.value); setCitationClaimBoundary(null); }} placeholder="在上方回答中选中一条完整断言，或粘贴唯一原句" /></label>
                    <div className="citation-claim-actions">
                      <button className="table-action" type="button" onClick={useSelectedAnswerText}>使用上方选中文本</button>
                      <button className="primary-button citation-claim-button" type="button" disabled={citationAction === "claim" || !citationClaimText.trim()} onClick={() => void registerCitationClaim()}>
                        {citationAction === "claim" ? "登记中" : "按精确回答边界登记"}
                      </button>
                    </div>
                    <small>{citationClaimBoundary ? `已映射回答边界 ${citationClaimBoundary.start}–${citationClaimBoundary.end}` : "粘贴文本必须在回答中唯一；直接选择可保留精确位置。"}</small>
                  </div>
                )}
                {citationSupport.claims.length > 0 && (
                  <>
                    <label className="citation-claim-selector">当前来源片段要核验的断言<select value={citationClaimId} onChange={(event) => setCitationClaimId(event.target.value)}>{citationSupport.claims.map((claim) => <option value={claim.claim_id} key={claim.claim_id}>{claim.claim_text.slice(0, 80)} · {claim.answer_start}–{claim.answer_end}</option>)}</select><small>下方每个“支持/矛盾/不足”决定只绑定这里明确选择的一条断言。</small></label>
                    <ol className="evidence-citations citation-claims">
                      {citationSupport.claims.map((claim) => (
                        <li key={claim.claim_id} className={claim.claim_id === citationClaimId ? "is-selected" : undefined}><strong>{claim.claim_text}</strong><span>回答边界 {claim.answer_start}–{claim.answer_end} · {claim.extraction_method}</span></li>
                      ))}
                    </ol>
                  </>
                )}
              </>
            )}
          </Panel>
          <Panel title="采集与对象证据">
            <dl className="evidence-metadata">
              <div><dt>联网状态</dt><dd>{selected.search_enabled === null ? "未记录" : selected.search_enabled ? "已联网" : "未联网"}</dd></div>
              <div><dt>请求类型</dt><dd>{selectedRequestKind || "历史样本未记录"}</dd></div>
              <div><dt>联网判据</dt><dd>{selectedSearchEvidence || "未记录"}</dd></div>
              <div><dt>引用解析器</dt><dd>{selectedCitationParserVersion || "未记录"}</dd></div>
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
      {selectedRun && (
        <div className="brand-graph-summary">
          <Badge tone={selectedRun.entity_graph_status === "governed" ? "success" : selectedRun.entity_graph_status === "blocked" ? "danger" : "warning"}>{selectedRun.entity_graph_status}</Badge>
          <span>实体口径快照 {selectedRun.entity_graph_snapshot_id ?? "dev-only 未冻结"}</span>
          <code title={selectedRun.entity_graph_sha256 ?? undefined}>{selectedRun.entity_graph_sha256 ? `${selectedRun.entity_graph_sha256.slice(0, 12)}…` : "无图谱 hash"}</code>
          {selectedRun.entity_graph_limitations.map((item) => <Badge tone="warning" key={item}>{item}</Badge>)}
        </div>
      )}
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
  const [facts, setFacts] = useState<FactRevision[]>([]);
  const [scanRuns, setScanRuns] = useState<ScanRun[]>([]);
  const [evidenceGaps, setEvidenceGaps] = useState<EvidenceGapList>({
    project_id: "",
    contract_version: "airank.evidence-gap.v2",
    gaps: [],
    governed_gap_count: 0,
    unverified_legacy_count: 0,
  });
  const [factAcquisitionTasks, setFactAcquisitionTasks] = useState<FactAcquisitionTaskList>({
    project_id: "",
    contract_version: "airank.fact-acquisition-task.v1",
    tasks: [],
    open_count: 0,
    in_review_count: 0,
    resolved_count: 0,
  });
  const [opportunities, setOpportunities] = useState<OpportunityList>({
    project_id: "",
    contract_version: "airank.intervention-opportunity.v1",
    policy_version: "airank.cross-domain-opportunity-policy.v1",
    latest_derivation_run: null,
    state_counts: { blocked_evidence: 0, ready_for_action: 0, monitor: 0 },
    source_counts: { brand_visibility: 0, citation_support: 0, fact_governance: 0, page_extractability: 0 },
    opportunities: [],
  });
  const [opportunityActions, setOpportunityActions] = useState<OpportunityActionList>({
    project_id: "",
    contract_version: "airank.opportunity-action.v1",
    actions: [],
    open_count: 0,
    evidence_blocked_count: 0,
    overdue_count: 0,
    final_count: 0,
  });
  const [opportunityRouting, setOpportunityRouting] = useState<OpportunityActionRouting>({
    project_id: "",
    contract_version: "airank.opportunity-action-routing.v1",
    routing_mode: "unrestricted_legacy",
    teams: [],
    routes: [],
    missing_source_kinds: ["brand_visibility", "citation_support", "fact_governance", "page_extractability"],
    known_limitations: ["yudao_action_team_sync_not_configured"],
    idempotent_replay: false,
  });
  const [opportunityDirectory, setOpportunityDirectory] = useState<OpportunityActionDirectory>({
    project_id: "",
    contract_version: "airank.opportunity-action-directory-sync.v1",
    bindings: [],
    recent_sync_runs: [],
    configured_team_count: 0,
    verified_team_count: 0,
    known_limitations: ["yudao_action_team_sync_not_configured"],
  });
  const [opportunityPlanning, setOpportunityPlanning] = useState<OpportunityExecutionPortfolio>({
    project_id: "",
    contract_version: "airank.opportunity-execution-plan.v1",
    planning_required_count: 0,
    approved_plan_count: 0,
    planning_coverage_complete: false,
    total_estimated_effort_hours: null,
    total_estimated_budget_amount: null,
    currency: "CNY",
    topological_order: [],
    blocked_action_ids: [],
    plans: [],
    unplanned_action_ids: [],
    outcome_forecast_allowed: false,
    known_limitations: ["human_estimate_not_invoice_or_spend"],
  });
  const [opportunityCapacity, setOpportunityCapacity] = useState<OpportunityCapacityPortfolio>({
    project_id: "",
    contract_version: "airank.opportunity-capacity-calendar.v1",
    active_member_count: 0,
    configured_calendar_count: 0,
    capacity_coverage_complete: false,
    calendars: [],
    latest_schedule: null,
    outcome_forecast_allowed: false,
    known_limitations: ["manual_capacity_not_external_calendar"],
  });
  const [derivingOpportunities, setDerivingOpportunities] = useState(false);
  const [actingOpportunityId, setActingOpportunityId] = useState<string | null>(null);
  const [routingMutationKey, setRoutingMutationKey] = useState<string | null>(null);
  const [planningMutationKey, setPlanningMutationKey] = useState<string | null>(null);
  const [creatingFactTaskGapId, setCreatingFactTaskGapId] = useState<string | null>(null);
  const [bindingFactTaskId, setBindingFactTaskId] = useState<string | null>(null);
  const [taskFactSelections, setTaskFactSelections] = useState<Record<string, string>>({});
  const [selectedGapRunId, setSelectedGapRunId] = useState("");
  const [derivingGaps, setDerivingGaps] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [reviewingAssetId, setReviewingAssetId] = useState<string | null>(null);
  const [creatingBlueprint, setCreatingBlueprint] = useState(false);
  const [assetType, setAssetType] = useState<GovernedContentCreateInput["assetType"]>("fact_page");
  const [assetTitle, setAssetTitle] = useState("企业事实证据页");
  const [editorialDirection, setEditorialDirection] = useState("面向企业采购与技术评审，只陈述已审核事实。");
  const [selectedFactRevisionIds, setSelectedFactRevisionIds] = useState<string[]>([]);
  const [creatingComparison, setCreatingComparison] = useState(false);
  const [comparisonTitle, setComparisonTitle] = useState("同维度证据对比");
  const [comparisonDirection, setComparisonDirection] = useState("面向企业采购评审，公平呈现相同维度下的已审核事实，不输出排名。");
  const [targetSubjectId, setTargetSubjectId] = useState("");
  const [targetDisplayName, setTargetDisplayName] = useState("");
  const [peerSubjectId, setPeerSubjectId] = useState("");
  const [peerDisplayName, setPeerDisplayName] = useState("");
  const [comparisonAssignments, setComparisonAssignments] = useState<Record<string, string>>({});
  const [creatingExplainer, setCreatingExplainer] = useState(false);
  const [explainerTitle, setExplainerTitle] = useState("证据解释指南");
  const [explainerDirection, setExplainerDirection] = useState("面向采购者解释定义、机制、步骤、标准、误区、FAQ 与适用边界。");
  const [explainerSubjectId, setExplainerSubjectId] = useState("");
  const [explainerDisplayName, setExplainerDisplayName] = useState("");
  const [explainerBrandAliases, setExplainerBrandAliases] = useState("");
  const [explainerAssignments, setExplainerAssignments] = useState<Record<string, string>>({});

  useEffect(() => {
    if (!project.id) {
      setBundle(fallbackAssetBundle);
      setScanRuns([]);
      setEvidenceGaps({ project_id: "", contract_version: "airank.evidence-gap.v2", gaps: [], governed_gap_count: 0, unverified_legacy_count: 0 });
      setFactAcquisitionTasks({ project_id: "", contract_version: "airank.fact-acquisition-task.v1", tasks: [], open_count: 0, in_review_count: 0, resolved_count: 0 });
      setOpportunities({ project_id: "", contract_version: "airank.intervention-opportunity.v1", policy_version: "airank.cross-domain-opportunity-policy.v1", latest_derivation_run: null, state_counts: { blocked_evidence: 0, ready_for_action: 0, monitor: 0 }, source_counts: { brand_visibility: 0, citation_support: 0, fact_governance: 0, page_extractability: 0 }, opportunities: [] });
      setOpportunityActions({ project_id: "", contract_version: "airank.opportunity-action.v1", actions: [], open_count: 0, evidence_blocked_count: 0, overdue_count: 0, final_count: 0 });
      setOpportunityRouting({ project_id: "", contract_version: "airank.opportunity-action-routing.v1", routing_mode: "unrestricted_legacy", teams: [], routes: [], missing_source_kinds: ["brand_visibility", "citation_support", "fact_governance", "page_extractability"], known_limitations: ["yudao_action_team_sync_not_configured"], idempotent_replay: false });
      setOpportunityDirectory({ project_id: "", contract_version: "airank.opportunity-action-directory-sync.v1", bindings: [], recent_sync_runs: [], configured_team_count: 0, verified_team_count: 0, known_limitations: ["yudao_action_team_sync_not_configured"] });
      setOpportunityPlanning({ project_id: "", contract_version: "airank.opportunity-execution-plan.v1", planning_required_count: 0, approved_plan_count: 0, planning_coverage_complete: false, total_estimated_effort_hours: null, total_estimated_budget_amount: null, currency: "CNY", topological_order: [], blocked_action_ids: [], plans: [], unplanned_action_ids: [], outcome_forecast_allowed: false, known_limitations: ["human_estimate_not_invoice_or_spend"] });
      setOpportunityCapacity({ project_id: "", contract_version: "airank.opportunity-capacity-calendar.v1", active_member_count: 0, configured_calendar_count: 0, capacity_coverage_complete: false, calendars: [], latest_schedule: null, outcome_forecast_allowed: false, known_limitations: ["manual_capacity_not_external_calendar"] });
      return;
    }
    const controller = new AbortController();
    Promise.all([
      fetchAssetBundle(project.id, controller.signal),
      fetchContentAssets(project.id, controller.signal),
      fetchFacts(project.id, controller.signal),
      fetchScanRuns(project.id, controller.signal),
      fetchEvidenceGaps(project.id, controller.signal),
      fetchFactAcquisitionTasks(project.id, controller.signal),
      fetchOpportunities(project.id, controller.signal),
      fetchOpportunityActions(project.id, controller.signal),
      fetchOpportunityActionRouting(project.id, controller.signal),
      fetchOpportunityActionDirectory(project.id, controller.signal),
      fetchOpportunityExecutionPortfolio(project.id, controller.signal),
      fetchOpportunityCapacityPortfolio(project.id, controller.signal),
    ])
      .then(([nextBundle, nextAssets, nextFacts, nextRuns, nextGaps, nextFactTasks, nextOpportunities, nextOpportunityActions, nextOpportunityRouting, nextOpportunityDirectory, nextOpportunityPlanning, nextOpportunityCapacity]) => {
        setBundle(nextBundle);
        setContentAssets(nextAssets);
        setFacts(nextFacts);
        setScanRuns(nextRuns);
        setEvidenceGaps(nextGaps);
        setFactAcquisitionTasks(nextFactTasks);
        setOpportunities(nextOpportunities);
        setOpportunityActions(nextOpportunityActions);
        setOpportunityRouting(nextOpportunityRouting);
        setOpportunityDirectory(nextOpportunityDirectory);
        setOpportunityPlanning(nextOpportunityPlanning);
        setOpportunityCapacity(nextOpportunityCapacity);
        const latestCompletedRun = nextRuns.find((run) => run.status === "completed");
        setSelectedGapRunId((current) => current || latestCompletedRun?.run_id || "");
        const eligibleIds = new Set(nextFacts.filter((fact) => fact.status === "approved" && fact.eligible_for_generation).map((fact) => fact.revision_id));
        setSelectedFactRevisionIds((current) => current.filter((revisionId) => eligibleIds.has(revisionId)));
        const entityFacts = nextFacts.filter((fact) => fact.status === "approved" && fact.eligible_for_generation && fact.subject_ref_id);
        const defaultTarget = entityFacts.find((fact) => fact.subject_type !== "competitor")?.subject_ref_id ?? "";
        const defaultPeer = entityFacts.find((fact) => fact.subject_type === "competitor" && fact.subject_ref_id !== defaultTarget)?.subject_ref_id ?? "";
        setTargetSubjectId((current) => current || defaultTarget);
        setPeerSubjectId((current) => current || defaultPeer);
        setTargetDisplayName((current) => current || defaultTarget);
        setPeerDisplayName((current) => current || defaultPeer);
        setExplainerSubjectId((current) => current || defaultTarget);
        setExplainerDisplayName((current) => current || defaultTarget);
        setComparisonAssignments((current) => Object.fromEntries(Object.entries(current).filter(([revisionId]) => eligibleIds.has(revisionId))));
        setExplainerAssignments((current) => Object.fromEntries(Object.entries(current).filter(([revisionId]) => eligibleIds.has(revisionId))));
        setLoadError(null);
      })
      .catch((error) => {
        if (controller.signal.aborted) return;
        setBundle(fallbackAssetBundle);
        setContentAssets([]);
        setFacts([]);
        setScanRuns([]);
        setEvidenceGaps({ project_id: project.id, contract_version: "airank.evidence-gap.v2", gaps: [], governed_gap_count: 0, unverified_legacy_count: 0 });
        setFactAcquisitionTasks({ project_id: project.id, contract_version: "airank.fact-acquisition-task.v1", tasks: [], open_count: 0, in_review_count: 0, resolved_count: 0 });
        setOpportunities({ project_id: project.id, contract_version: "airank.intervention-opportunity.v1", policy_version: "airank.cross-domain-opportunity-policy.v1", latest_derivation_run: null, state_counts: { blocked_evidence: 0, ready_for_action: 0, monitor: 0 }, source_counts: { brand_visibility: 0, citation_support: 0, fact_governance: 0, page_extractability: 0 }, opportunities: [] });
        setOpportunityActions({ project_id: project.id, contract_version: "airank.opportunity-action.v1", actions: [], open_count: 0, evidence_blocked_count: 0, overdue_count: 0, final_count: 0 });
        setOpportunityRouting({ project_id: project.id, contract_version: "airank.opportunity-action-routing.v1", routing_mode: "unrestricted_legacy", teams: [], routes: [], missing_source_kinds: ["brand_visibility", "citation_support", "fact_governance", "page_extractability"], known_limitations: ["yudao_action_team_sync_not_configured"], idempotent_replay: false });
        setOpportunityDirectory({ project_id: project.id, contract_version: "airank.opportunity-action-directory-sync.v1", bindings: [], recent_sync_runs: [], configured_team_count: 0, verified_team_count: 0, known_limitations: ["directory_state_unavailable"] });
        setOpportunityPlanning({ project_id: project.id, contract_version: "airank.opportunity-execution-plan.v1", planning_required_count: 0, approved_plan_count: 0, planning_coverage_complete: false, total_estimated_effort_hours: null, total_estimated_budget_amount: null, currency: "CNY", topological_order: [], blocked_action_ids: [], plans: [], unplanned_action_ids: [], outcome_forecast_allowed: false, known_limitations: ["human_estimate_not_invoice_or_spend"] });
        setOpportunityCapacity({ project_id: project.id, contract_version: "airank.opportunity-capacity-calendar.v1", active_member_count: 0, configured_calendar_count: 0, capacity_coverage_complete: false, calendars: [], latest_schedule: null, outcome_forecast_allowed: false, known_limitations: ["capacity_state_unavailable"] });
        setLoadError(error instanceof Error ? error.message : "内容资产接口不可用");
      });
    return () => controller.abort();
  }, [project.id]);

  const eligibleFacts = facts.filter((fact) => fact.status === "approved" && fact.eligible_for_generation);
  const completedScanRuns = scanRuns.filter((run) => run.status === "completed");
  const subjectOptions = Array.from(new globalThis.Map<string, { subjectId: string; subjectType: FactRevision["subject_type"] }>(
    eligibleFacts
      .filter((fact) => fact.subject_ref_id && fact.subject_type !== "general")
      .map((fact) => [fact.subject_ref_id as string, { subjectId: fact.subject_ref_id as string, subjectType: fact.subject_type }]),
  ).values());
  const comparisonFacts = eligibleFacts.filter((fact) => fact.subject_ref_id === targetSubjectId || fact.subject_ref_id === peerSubjectId);
  const comparisonCoveredCellCount = new Set(
    comparisonFacts
      .filter((fact) => comparisonAssignments[fact.revision_id])
      .map((fact) => `${fact.subject_ref_id}:${comparisonAssignments[fact.revision_id]}`),
  ).size;
  const explainerFacts = eligibleFacts.filter((fact) => fact.subject_ref_id === explainerSubjectId);
  const explainerRoleCounts = Object.fromEntries(explainerRoles.map((role) => [
    role.value,
    explainerFacts.filter((fact) => explainerAssignments[fact.revision_id] === role.value).length,
  ])) as Record<(typeof explainerRoles)[number]["value"], number>;
  const explainerSupportedCharacterCount = explainerFacts
    .filter((fact) => explainerAssignments[fact.revision_id])
    .reduce((total, fact) => total + fact.fact_text.replace(/\s+/g, "").length, 0);
  const explainerRoleCoverageComplete = explainerRoles.every((role) => explainerRoleCounts[role.value] >= role.minimum);

  const submitEvidenceGapDerivation = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!project.id || !selectedGapRunId) {
      notify({ title: "没有可推导的扫描", desc: "请选择一条已完成扫描；排队、运行中或失败扫描不能形成干预依据。", tone: "warning" });
      return;
    }
    setDerivingGaps(true);
    try {
      const result = await deriveEvidenceGaps(project.id, selectedGapRunId);
      const [nextGaps, nextBundle] = await Promise.all([
        fetchEvidenceGaps(project.id),
        fetchAssetBundle(project.id),
      ]);
      setEvidenceGaps(nextGaps);
      setBundle(nextBundle);
      notify({
        title: result.idempotent_replay ? "证据缺口已复用" : "证据缺口已推导",
        desc: `形成 ${result.gap_count} 个稳定未提及缺口，跳过 ${result.skipped_group_count} 个不满足规则的分组；所有正常样本仍保留。`,
        tone: "success",
      });
    } catch (error) {
      notify({
        title: "证据缺口未生成",
        desc: error instanceof Error ? error.message : "扫描质量或不可变证据未通过门禁。",
        tone: "danger",
      });
    } finally {
      setDerivingGaps(false);
    }
  };

  const submitOpportunityDerivation = async () => {
    if (!project.id) return;
    setDerivingOpportunities(true);
    try {
      const result = await deriveOpportunities(project.id);
      const [next, nextActions] = await Promise.all([
        fetchOpportunities(project.id),
        fetchOpportunityActions(project.id),
      ]);
      setOpportunities(next);
      setOpportunityActions(nextActions);
      notify({
        title: result.idempotent_replay ? "机会快照已复用" : "跨域机会快照已冻结",
        desc: `当前观察到 ${result.opportunity_count} 项：新增 ${result.new_count}、持续 ${result.persisting_count}、本轮未再观察到 ${result.cleared_count}。后者不会自动标成已解决。`,
        tone: "success",
      });
    } catch (error) {
      notify({
        title: "机会快照未生成",
        desc: error instanceof Error ? error.message : "当前项目没有可验证的缺口、引用、事实或页面审计证据。",
        tone: "danger",
      });
    } finally {
      setDerivingOpportunities(false);
    }
  };

  const submitOpportunityActionCreate = async (item: OpportunityList["opportunities"][number]) => {
    if (!project.id) return;
    setActingOpportunityId(item.snapshot_id);
    try {
      const action = await createOpportunityAction(project.id, item.snapshot_id);
      const [nextActions, nextPlanning] = await Promise.all([
        fetchOpportunityActions(project.id),
        fetchOpportunityExecutionPortfolio(project.id),
      ]);
      setOpportunityActions(nextActions);
      setOpportunityPlanning(nextPlanning);
      notify({
        title: action.idempotent_replay ? "执行行动已存在" : "已纳入执行台账",
        desc: action.status === "evidence_blocked"
          ? "当前行动仍被事实或复核证据阻断；可领取跟进，但不能进入效果结论。"
          : `行动截止 ${new Date(action.due_at).toLocaleString("zh-CN")}，完成必须由后续完整复测确认。`,
        tone: action.status === "evidence_blocked" ? "warning" : "success",
      });
    } catch (error) {
      notify({ title: "行动未创建", desc: error instanceof Error ? error.message : "机会快照已过期或不满足执行门禁。", tone: "danger" });
    } finally {
      setActingOpportunityId(null);
    }
  };

  const submitOpportunityActionClaim = async (action: OpportunityAction) => {
    if (!project.id) return;
    setActingOpportunityId(action.action_id);
    try {
      const claimed = await claimOpportunityAction(project.id, action.action_id, action.version);
      const [nextActions, nextPlanning] = await Promise.all([
        fetchOpportunityActions(project.id),
        fetchOpportunityExecutionPortfolio(project.id),
      ]);
      setOpportunityActions(nextActions);
      setOpportunityPlanning(nextPlanning);
      notify({
        title: "行动已领取",
        desc: claimed.status === "evidence_blocked"
          ? "责任人已记录，但证据阻断仍保留；先补证再执行干预。"
          : `当前状态 ${claimed.status}，SLA ${claimed.sla_state}。`,
        tone: "success",
      });
    } catch (error) {
      notify({ title: "行动领取失败", desc: error instanceof Error ? error.message : "任务已被他人领取或版本已变化。", tone: "danger" });
    } finally {
      setActingOpportunityId(null);
    }
  };

  const submitOpportunityActionVerification = async (action: OpportunityAction, verificationRunId: string) => {
    if (!project.id) return;
    setActingOpportunityId(action.action_id);
    try {
      await verifyOpportunityActionNotObserved(project.id, action.action_id, action.version, verificationRunId);
      const [nextActions, nextPlanning] = await Promise.all([
        fetchOpportunityActions(project.id),
        fetchOpportunityExecutionPortfolio(project.id),
      ]);
      setOpportunityActions(nextActions);
      setOpportunityPlanning(nextPlanning);
      notify({
        title: "已记录本轮未再观察到",
        desc: "行动由最新完整快照终结，但这不是品牌推荐、增长或长期解决的证明。",
        tone: "success",
      });
    } catch (error) {
      notify({ title: "复测确认未通过", desc: error instanceof Error ? error.message : "需要更新且完整的机会推导证据。", tone: "danger" });
    } finally {
      setActingOpportunityId(null);
    }
  };

  const submitOpportunityTeamCreate = async (name: string) => {
    if (!project.id) return;
    setRoutingMutationKey("create-team");
    try {
      const routing = await createOpportunityActionTeam(project.id, name);
      setOpportunityRouting(routing);
      notify({
        title: routing.idempotent_replay ? "交付团队已存在" : "交付团队已创建",
        desc: "手工成员不会被标记为 Yudao 已核验；请继续添加成员并配置四类来源路由。",
        tone: "success",
      });
    } catch (error) {
      notify({ title: "交付团队未创建", desc: error instanceof Error ? error.message : "请确认管理员权限与团队名称。", tone: "danger" });
    } finally {
      setRoutingMutationKey(null);
    }
  };

  const submitOpportunityTeamJoin = async (teamId: string) => {
    if (!project.id) return;
    const userId = getStoredAuthSession()?.user.userId;
    if (!userId) {
      notify({ title: "缺少登录身份", desc: "请重新登录后再加入交付团队。", tone: "danger" });
      return;
    }
    setRoutingMutationKey(`member:${teamId}`);
    try {
      const routing = await upsertOpportunityActionMember(project.id, teamId, userId);
      setOpportunityRouting(routing);
      setOpportunityCapacity(await fetchOpportunityCapacityPortfolio(project.id));
      notify({ title: "当前账号已加入团队", desc: "默认容量为 5 个活动行动；手工成员身份未经过 Yudao 外部目录核验。", tone: "success" });
    } catch (error) {
      notify({ title: "团队成员未更新", desc: error instanceof Error ? error.message : "成员版本或管理员权限不满足。", tone: "danger" });
    } finally {
      setRoutingMutationKey(null);
    }
  };

  const submitOpportunityRoute = async (sourceKind: OpportunitySourceKind, teamId: string) => {
    if (!project.id) return;
    const existing = opportunityRouting.routes.find((route) => route.source_kind === sourceKind);
    setRoutingMutationKey(`route:${sourceKind}`);
    try {
      setOpportunityRouting(await putOpportunityActionRoute(project.id, sourceKind, teamId, existing?.version));
      notify({ title: "机会来源路由已保存", desc: "领取时将重新核验团队成员资格与容量；配置任一路由后不再回退到无限制领取。", tone: "success" });
    } catch (error) {
      notify({ title: "机会来源路由未保存", desc: error instanceof Error ? error.message : "团队为空、停用或路由版本已变化。", tone: "danger" });
    } finally {
      setRoutingMutationKey(null);
    }
  };

  const submitOpportunityDirectoryBinding = async (
    teamId: string,
    externalGroupId: string,
    expectedVersion?: number,
  ) => {
    if (!project.id) return;
    setRoutingMutationKey(`directory-binding:${teamId}`);
    try {
      const directory = await putOpportunityActionDirectoryBinding(
        project.id,
        teamId,
        externalGroupId,
        expectedVersion,
      );
      const [routing, capacity] = await Promise.all([
        fetchOpportunityActionRouting(project.id),
        fetchOpportunityCapacityPortfolio(project.id),
      ]);
      setOpportunityDirectory(directory);
      setOpportunityRouting(routing);
      setOpportunityCapacity(capacity);
      notify({
        title: "Yudao 成员目录已绑定",
        desc: "绑定处于 pending；只有真实同步成功后，外部成员才会标记为已核验。凭证未进入请求或数据库。",
        tone: "success",
      });
    } catch (error) {
      notify({ title: "成员目录未绑定", desc: error instanceof Error ? error.message : "请确认管理员权限、部门 ID 与绑定版本。", tone: "danger" });
    } finally {
      setRoutingMutationKey(null);
    }
  };

  const submitOpportunityDirectoryRun = async (teamId: string) => {
    if (!project.id) return;
    setRoutingMutationKey(`directory-run:${teamId}`);
    try {
      const directory = await runOpportunityActionDirectorySync(project.id, teamId);
      const [routing, capacity] = await Promise.all([
        fetchOpportunityActionRouting(project.id),
        fetchOpportunityCapacityPortfolio(project.id),
      ]);
      setOpportunityDirectory(directory);
      setOpportunityRouting(routing);
      setOpportunityCapacity(capacity);
      const run = directory.recent_sync_runs.find((item) => item.team_id === teamId);
      notify({
        title: "交付成员目录真实同步完成",
        desc: run
          ? `有效外部成员 ${run.active_member_count}，新增 ${run.created_member_count}，更新 ${run.updated_member_count}，手工身份冲突 ${run.manual_conflict_count}。`
          : "同步已完成，请查看同步运行证据。",
        tone: "success",
      });
    } catch (error) {
      try {
        const [directory, routing, capacity] = await Promise.all([
          fetchOpportunityActionDirectory(project.id),
          fetchOpportunityActionRouting(project.id),
          fetchOpportunityCapacityPortfolio(project.id),
        ]);
        setOpportunityDirectory(directory);
        setOpportunityRouting(routing);
        setOpportunityCapacity(capacity);
      } catch {
        // Preserve the original, more actionable synchronization error.
      }
      notify({ title: "交付成员目录同步失败", desc: error instanceof Error ? error.message : "运行失败已留痕，团队保持失败关闭状态。", tone: "danger" });
    } finally {
      setRoutingMutationKey(null);
    }
  };

  const submitOpportunityPlan = async (
    action: OpportunityAction,
    effortHours: string,
    budgetAmount: string,
    plannedStartAt: string,
    plannedDueAt: string,
    assumptions: string,
    expectedVersion?: number,
  ) => {
    if (!project.id) return;
    setPlanningMutationKey(`plan:${action.action_id}`);
    try {
      const plan = await putOpportunityExecutionPlan(project.id, action.action_id, {
        estimatedEffortHours: effortHours,
        estimatedBudgetAmount: budgetAmount,
        plannedStartAt,
        plannedDueAt,
        assumptions,
        expectedVersion,
      });
      const [nextPlanning, nextCapacity] = await Promise.all([
        fetchOpportunityExecutionPortfolio(project.id),
        fetchOpportunityCapacityPortfolio(project.id),
      ]);
      setOpportunityPlanning(nextPlanning);
      setOpportunityCapacity(nextCapacity);
      notify({
        title: plan.idempotent_replay ? "人工计划未变化" : "人工计划已批准",
        desc: `记录 ${plan.estimated_effort_hours} 小时、¥${plan.estimated_budget_amount} 人工估算；不作为实际支出或效果预测。`,
        tone: "success",
      });
    } catch (error) {
      notify({ title: "人工计划未保存", desc: error instanceof Error ? error.message : "估算字段或版本不满足门禁。", tone: "danger" });
    } finally {
      setPlanningMutationKey(null);
    }
  };

  const submitOpportunityDependency = async (
    action: OpportunityAction,
    prerequisiteActionId: string,
    rationale: string,
  ) => {
    if (!project.id) return;
    setPlanningMutationKey(`dependency:${action.action_id}`);
    try {
      const dependency = await createOpportunityDependency(
        project.id,
        action.action_id,
        prerequisiteActionId,
        rationale,
      );
      setOpportunityPlanning(await fetchOpportunityExecutionPortfolio(project.id));
      notify({
        title: dependency.idempotent_replay ? "前置依赖已存在" : "前置依赖已记录",
        desc: dependency.satisfied ? "前置行动已满足。" : "当前行动已进入依赖阻断，完成前置行动或记录人工豁免后解除。",
        tone: dependency.satisfied ? "success" : "warning",
      });
    } catch (error) {
      notify({ title: "前置依赖未添加", desc: error instanceof Error ? error.message : "依赖无效或会形成循环。", tone: "danger" });
    } finally {
      setPlanningMutationKey(null);
    }
  };

  const submitOpportunityDependencyWaiver = async (
    dependency: OpportunityDependency,
    waiverReason: string,
  ) => {
    if (!project.id) return;
    setPlanningMutationKey(`waive:${dependency.dependency_id}`);
    try {
      await waiveOpportunityDependency(
        project.id,
        dependency.dependency_id,
        dependency.version,
        waiverReason,
      );
      setOpportunityPlanning(await fetchOpportunityExecutionPortfolio(project.id));
      notify({
        title: "人工依赖豁免已审计",
        desc: "该依赖视为满足，但豁免不证明行动效果、品牌推荐或增长。",
        tone: "warning",
      });
    } catch (error) {
      notify({ title: "依赖豁免未记录", desc: error instanceof Error ? error.message : "豁免原因或版本不满足门禁。", tone: "danger" });
    } finally {
      setPlanningMutationKey(null);
    }
  };

  const submitOpportunityCapacityCalendar = async (
    memberId: string,
    timezone: string,
    weeklyCapacityHours: string,
    workdays: number[],
    assumptions: string,
    expectedVersion?: number,
  ) => {
    if (!project.id) return;
    setPlanningMutationKey(`calendar:${memberId}`);
    try {
      const calendar = await putOpportunityCapacityCalendar(project.id, memberId, {
        timezone,
        weeklyCapacityHours,
        workdays,
        assumptions,
        expectedVersion,
      });
      setOpportunityCapacity(await fetchOpportunityCapacityPortfolio(project.id));
      notify({
        title: calendar.idempotent_replay ? "成员容量未变化" : "成员工作日历已保存",
        desc: `每周 ${calendar.weekly_capacity_hours} 小时，工作日 ${calendar.workdays.join("/")}；这是人工计划容量，不是外部日历或真实工时。`,
        tone: "success",
      });
    } catch (error) {
      notify({ title: "成员工作日历未保存", desc: error instanceof Error ? error.message : "时区、工作日、容量或版本不满足门禁。", tone: "danger" });
    } finally {
      setPlanningMutationKey(null);
    }
  };

  const submitOpportunityCapacityException = async (
    memberId: string,
    exceptionDate: string,
    availableHours: string,
    reason: string,
    expectedVersion?: number,
  ) => {
    if (!project.id) return;
    setPlanningMutationKey(`calendar-exception:${memberId}`);
    try {
      await putOpportunityCapacityException(
        project.id,
        memberId,
        exceptionDate,
        availableHours,
        reason,
        expectedVersion,
      );
      setOpportunityCapacity(await fetchOpportunityCapacityPortfolio(project.id));
      notify({
        title: "容量日期例外已审计",
        desc: `${exceptionDate} 可用 ${availableHours} 小时；人工例外不会冒充飞书、Yudao 或其他外部日历回执。`,
        tone: "success",
      });
    } catch (error) {
      notify({ title: "容量日期例外未保存", desc: error instanceof Error ? error.message : "日期、容量、原因或版本不满足门禁。", tone: "danger" });
    } finally {
      setPlanningMutationKey(null);
    }
  };

  const submitOpportunitySchedule = async (asOfDate: string) => {
    if (!project.id) return;
    setPlanningMutationKey("capacity-schedule");
    try {
      const schedule = await createOpportunityExecutionSchedule(project.id, asOfDate);
      setOpportunityCapacity(await fetchOpportunityCapacityPortfolio(project.id));
      notify({
        title: schedule.idempotent_replay ? "排程快照已复用" : "30/60/90 排程快照已冻结",
        desc: schedule.schedule_feasible
          ? `${schedule.scheduled_count} 个行动在当前人工容量内；该结论不包含增长或推荐预测。`
          : `${schedule.blocked_count} 个行动阻断、${schedule.capacity_conflict_count} 个容量冲突、${schedule.outside_horizon_count} 个超出窗口。`,
        tone: schedule.schedule_feasible ? "success" : "warning",
      });
    } catch (error) {
      notify({ title: "排程快照未生成", desc: error instanceof Error ? error.message : "行动、计划、成员或日历证据不完整。", tone: "danger" });
    } finally {
      setPlanningMutationKey(null);
    }
  };

  const createGapFactTask = async (gapId: string) => {
    if (!project.id) return;
    setCreatingFactTaskGapId(gapId);
    try {
      const task = await createFactAcquisitionTask(project.id, gapId);
      const nextTasks = await fetchFactAcquisitionTasks(project.id);
      setFactAcquisitionTasks(nextTasks);
      notify({
        title: task.idempotent_replay ? "补证任务已复用" : "补证任务已创建",
        desc: "任务冻结了缺口证据与质量报告；请先补充并审核企业事实，系统不会直接生成内容。",
        tone: "success",
      });
    } catch (error) {
      notify({
        title: "补证任务未创建",
        desc: error instanceof Error ? error.message : "缺口不满足真实证据门禁。",
        tone: "danger",
      });
    } finally {
      setCreatingFactTaskGapId(null);
    }
  };

  const bindTaskFact = async (taskId: string, version: number) => {
    if (!project.id) return;
    const revisionId = taskFactSelections[taskId];
    if (!revisionId) {
      notify({ title: "尚未选择审核事实", desc: "请选择一条当前有效且可用于生成的审核事实。", tone: "warning" });
      return;
    }
    setBindingFactTaskId(taskId);
    try {
      const task = await bindFactAcquisitionEvidence(project.id, taskId, version, [revisionId]);
      const [nextTasks, nextGaps, nextBundle] = await Promise.all([
        fetchFactAcquisitionTasks(project.id),
        fetchEvidenceGaps(project.id),
        fetchAssetBundle(project.id),
      ]);
      setFactAcquisitionTasks(nextTasks);
      setEvidenceGaps(nextGaps);
      setBundle(nextBundle);
      notify({
        title: task.generation_allowed ? "补证任务已通过" : "事实已进入审核",
        desc: task.generation_allowed
          ? "缺口已绑定审核事实，可进入受治理干预；这不等于内容已生成、已发布或一定被模型推荐。"
          : "事实尚未满足审核、来源、有效期或冲突门禁，任务不会放行内容生成。",
        tone: task.generation_allowed ? "success" : "warning",
      });
    } catch (error) {
      notify({
        title: "事实补证未通过",
        desc: error instanceof Error ? error.message : "事实证据不满足治理门禁。",
        tone: "danger",
      });
    } finally {
      setBindingFactTaskId(null);
    }
  };

  const toggleBlueprintFact = (revisionId: string) => {
    setSelectedFactRevisionIds((current) => current.includes(revisionId)
      ? current.filter((item) => item !== revisionId)
      : [...current, revisionId]);
  };

  const submitBlueprint = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const actor = getStoredAuthSession()?.user.userId;
    if (!project.id || !actor) {
      notify({ title: "无法生成页面蓝图", desc: "缺少项目或可信操作者身份，请重新登录。", tone: "danger" });
      return;
    }
    if (!assetTitle.trim() || !editorialDirection.trim() || selectedFactRevisionIds.length === 0) {
      notify({ title: "证据输入不完整", desc: "请填写标题与编辑方向，并至少选择一条当前可用于生成的审核事实。", tone: "warning" });
      return;
    }
    setCreatingBlueprint(true);
    try {
      const created = await createGovernedContent(project.id, {
        assetType,
        title: assetTitle.trim(),
        direction: editorialDirection.trim(),
        factRevisionIds: selectedFactRevisionIds,
        createdBy: actor,
      });
      setContentAssets((current) => [created, ...current]);
      setSelectedFactRevisionIds([]);
      notify({
        title: "证据绑定页面蓝图已生成",
        desc: `${created.section_count} 个结构段、${created.claim_support_ids.length} 条精确证据支持；编辑方向未直接复制进公开正文。`,
        tone: "success",
      });
    } catch (error) {
      notify({ title: "页面蓝图未生成", desc: error instanceof Error ? error.message : "内容生成接口不可用", tone: "danger" });
    } finally {
      setCreatingBlueprint(false);
    }
  };

  const submitComparison = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const actor = getStoredAuthSession()?.user.userId;
    if (!project.id || !actor) {
      notify({ title: "无法生成证据对比", desc: "缺少项目或可信操作者身份，请重新登录。", tone: "danger" });
      return;
    }
    if (!targetSubjectId || !peerSubjectId || targetSubjectId === peerSubjectId || !targetDisplayName.trim() || !peerDisplayName.trim()) {
      notify({ title: "对比主体不完整", desc: "请选择两个不同的事实主体，并填写用于公开展示的主体名称。", tone: "warning" });
      return;
    }
    const targetType = subjectOptions.find((item) => item.subjectId === targetSubjectId)?.subjectType;
    const peerType = subjectOptions.find((item) => item.subjectId === peerSubjectId)?.subjectType;
    if (!targetType || !peerType || targetType === "general" || peerType === "general") {
      notify({ title: "主体绑定无效", desc: "对比只能使用已绑定品牌、公司、产品、竞品或方案类型的事实。", tone: "warning" });
      return;
    }
    const cells = [targetSubjectId, peerSubjectId].flatMap((subjectId) => comparisonDimensions.map((dimension) => ({
      subject_id: subjectId,
      dimension_id: dimension.dimension_id,
      fact_revision_ids: comparisonFacts
        .filter((fact) => fact.subject_ref_id === subjectId && comparisonAssignments[fact.revision_id] === dimension.dimension_id)
        .map((fact) => fact.revision_id),
    })));
    const missingCells = cells.filter((cell) => cell.fact_revision_ids.length === 0);
    if (missingCells.length > 0) {
      notify({ title: "对称证据矩阵未补齐", desc: `仍有 ${missingCells.length} 个“主体 × 维度”单元缺少审核事实；系统不会用空白或推断补齐。`, tone: "warning" });
      return;
    }
    setCreatingComparison(true);
    try {
      const created = await createComparisonContent(project.id, {
        title: comparisonTitle.trim(),
        direction: comparisonDirection.trim(),
        targetSubjectId,
        subjects: [
          { subject_id: targetSubjectId, display_name: targetDisplayName.trim(), subject_type: targetType },
          { subject_id: peerSubjectId, display_name: peerDisplayName.trim(), subject_type: peerType },
        ],
        dimensions: [...comparisonDimensions],
        cells,
        createdBy: actor,
      });
      setContentAssets((current) => [created, ...current]);
      setComparisonAssignments({});
      notify({ title: "公平证据对比已生成", desc: `${created.section_count} 个相同维度、${created.claim_support_ids.length} 条精确证据；未生成排名或无证据优劣结论。`, tone: "success" });
    } catch (error) {
      notify({ title: "证据对比未生成", desc: error instanceof Error ? error.message : "对比内容接口不可用", tone: "danger" });
    } finally {
      setCreatingComparison(false);
    }
  };

  const submitExplainer = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const actor = getStoredAuthSession()?.user.userId;
    if (!project.id || !actor) {
      notify({ title: "无法生成解释指南", desc: "缺少项目或可信操作者身份，请重新登录。", tone: "danger" });
      return;
    }
    const subjectType = subjectOptions.find((item) => item.subjectId === explainerSubjectId)?.subjectType;
    if (!subjectType || subjectType === "general" || !explainerDisplayName.trim()) {
      notify({ title: "解释主体不完整", desc: "请选择已绑定事实主体，并填写公开名称。", tone: "warning" });
      return;
    }
    if (!explainerRoleCoverageComplete || explainerSupportedCharacterCount < 1400) {
      notify({ title: "解释证据尚未达到门禁", desc: `七类角色必须全部达标，且已选事实需达到 1400 个非空白字符；当前 ${explainerSupportedCharacterCount}。`, tone: "warning" });
      return;
    }
    const assignments = explainerFacts
      .filter((fact) => explainerAssignments[fact.revision_id])
      .map((fact) => ({
        fact_revision_id: fact.revision_id,
        content_role: explainerAssignments[fact.revision_id] as (typeof explainerRoles)[number]["value"],
      }));
    setCreatingExplainer(true);
    try {
      const created = await createExplainerContent(project.id, {
        title: explainerTitle.trim(),
        direction: explainerDirection.trim(),
        subjectId: explainerSubjectId,
        subjectType,
        displayName: explainerDisplayName.trim(),
        brandNames: explainerBrandAliases.split(/[，,\n]/).map((item) => item.trim()).filter(Boolean),
        assignments,
        createdBy: actor,
      });
      setContentAssets((current) => [created, ...current]);
      setExplainerAssignments({});
      notify({ title: "证据解释指南已生成", desc: `${created.section_count} 类结构、${created.claim_support_ids.length} 条精确证据；品牌露出、篇幅和角色覆盖均已通过门禁。`, tone: "success" });
    } catch (error) {
      notify({ title: "解释指南未生成", desc: error instanceof Error ? error.message : "解释内容接口不可用", tone: "danger" });
    } finally {
      setCreatingExplainer(false);
    }
  };

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
      <OpportunityBoard
        data={opportunities}
        actionData={opportunityActions}
        routingData={opportunityRouting}
        directoryData={opportunityDirectory}
        planningData={opportunityPlanning}
        capacityData={opportunityCapacity}
        currentUserId={getStoredAuthSession()?.user.userId ?? ""}
        deriving={derivingOpportunities}
        actingActionId={actingOpportunityId}
        routingMutationKey={routingMutationKey}
        planningMutationKey={planningMutationKey}
        onDerive={() => void submitOpportunityDerivation()}
        onCreateAction={(item) => void submitOpportunityActionCreate(item)}
        onClaimAction={(item) => void submitOpportunityActionClaim(item)}
        onVerifyAction={(item, runId) => void submitOpportunityActionVerification(item, runId)}
        onCreateTeam={(name) => void submitOpportunityTeamCreate(name)}
        onJoinTeam={(teamId) => void submitOpportunityTeamJoin(teamId)}
        onPutRoute={(sourceKind, teamId) => void submitOpportunityRoute(sourceKind, teamId)}
        onSaveDirectoryBinding={(teamId, externalGroupId, expectedVersion) => void submitOpportunityDirectoryBinding(teamId, externalGroupId, expectedVersion)}
        onRunDirectorySync={(teamId) => void submitOpportunityDirectoryRun(teamId)}
        onSavePlan={(action, effortHours, budgetAmount, plannedStartAt, plannedDueAt, assumptions, expectedVersion) => void submitOpportunityPlan(action, effortHours, budgetAmount, plannedStartAt, plannedDueAt, assumptions, expectedVersion)}
        onAddDependency={(action, prerequisiteActionId, rationale) => void submitOpportunityDependency(action, prerequisiteActionId, rationale)}
        onWaiveDependency={(dependency, waiverReason) => void submitOpportunityDependencyWaiver(dependency, waiverReason)}
        onSaveCapacityCalendar={(memberId, timezone, weeklyCapacityHours, workdays, assumptions, expectedVersion) => void submitOpportunityCapacityCalendar(memberId, timezone, weeklyCapacityHours, workdays, assumptions, expectedVersion)}
        onSaveCapacityException={(memberId, exceptionDate, availableHours, reason, expectedVersion) => void submitOpportunityCapacityException(memberId, exceptionDate, availableHours, reason, expectedVersion)}
        onGenerateSchedule={(asOfDate) => void submitOpportunitySchedule(asOfDate)}
        onNavigate={onNavigate}
      />
      <Panel title="真实扫描 → 证据缺口">
        <form className="content-blueprint-form" data-testid="evidence-gap-derive-form" onSubmit={(event) => void submitEvidenceGapDerivation(event)}>
          <div className="content-blueprint-wide knowledge-search-policy">
            <Badge tone="primary">airank.evidence-gap.v2</Badge>
            <span>只读取质量门禁通过的不可变样本。同一问题、平台和采集面至少 3 次独立有效回答都未提及品牌，才形成稳定缺口；未提及仍计入有效分母。</span>
          </div>
          <label>
            已完成扫描
            <select data-testid="evidence-gap-run-select" value={selectedGapRunId} onChange={(event) => setSelectedGapRunId(event.target.value)}>
              <option value="">请选择真实扫描</option>
              {completedScanRuns.map((run) => <option value={run.run_id} key={run.run_id}>{run.name || run.run_id} · {run.cohort_type} · {run.repetitions} 次 · {run.collector_surfaces.join("/")}</option>)}
            </select>
            <small>服务端会重新计算 measurement-quality.v4；质量阻断时不会落库缺口。</small>
          </label>
          <div className="content-blueprint-actions">
            <span>{completedScanRuns.length} 条已完成扫描 · {evidenceGaps.governed_gap_count} 个证据缺口</span>
            <button className="airank-console-primary-button" data-testid="derive-evidence-gaps" type="submit" disabled={derivingGaps || !selectedGapRunId}>{derivingGaps ? "校验证据中…" : "从真实样本推导"}</button>
          </div>
        </form>
        {evidenceGaps.unverified_legacy_count > 0 ? (
          <DataStateCard title="历史缺口未进入干预" desc={`检测到 ${evidenceGaps.unverified_legacy_count} 个未绑定真实样本证据的历史缺口。它们只保留审计，不会生成内容建议；请从质量通过的扫描重新推导。`} tone="warning" />
        ) : null}
        {evidenceGaps.gaps.length === 0 ? (
          <DataStateCard title="尚无稳定证据缺口" desc="这可能表示尚未执行推导、扫描质量被阻断，或没有任何分组满足连续独立有效样本均未提及的规则；系统不会补造缺口数量。" tone="warning" />
        ) : (
          <div className="content-review-list" data-testid="evidence-gap-list">
            {evidenceGaps.gaps.map((gap) => {
              const existingTask = factAcquisitionTasks.tasks.find((task) => task.gap_id === gap.gap_id);
              return <article className="content-review-item" data-testid="evidence-gap-card" key={gap.gap_id}>
                <div className="content-review-head">
                  <div><strong>{gap.title}</strong><span>{gap.provider} · {gap.collector_surface} · {formatDateTime(gap.created_at)}</span></div>
                  <Badge tone={gap.severity === "high" ? "danger" : gap.severity === "medium" ? "warning" : "muted"}>{gap.severity}</Badge>
                </div>
                <div className="content-review-body">{gap.description}</div>
                <div className="content-review-proof">
                  <span>{gap.valid_sample_count} 条有效样本</span>
                  <span>{gap.normal_unmentioned_count} 条正常未提及</span>
                  <span>{gap.citation_ids.length} 条原生引用</span>
                  <span>{gap.fact_atom_ids.length} 条审核事实</span>
                  <span>建议 {gap.suggested_asset_type}</span>
                  <code>{gap.evidence_sha256.slice(0, 16)}…</code>
                </div>
                <div className="fact-review-actions">
                  <button className="outline-button" type="button" onClick={() => openPanel({
                    title: `${gap.title} · 样本证据`,
                    desc: `质量报告 ${gap.quality_report_sha256}；证据基础 ${gap.evidence_sha256}。`,
                    items: [
                      `AnswerSnapshot：${gap.answer_snapshot_ids.join("、")}`,
                      `EvidenceSnapshot：${gap.evidence_snapshot_ids.join("、")}`,
                      `Citation：${gap.citation_ids.length ? gap.citation_ids.join("、") : "当前样本无 Provider 原生引用"}`,
                      `FactAtom：${gap.fact_atom_ids.length ? gap.fact_atom_ids.join("、") : "待补审核事实，不允许直接生成内容"}`,
                    ],
                  })}><Eye size={16} />下钻证据</button>
                  {existingTask ? (
                    <Badge tone={existingTask.status === "resolved" ? "success" : "warning"}>
                      补证任务 · {existingTask.resolution_state}
                    </Badge>
                  ) : (
                    <button
                      className="outline-button"
                      data-testid="create-fact-acquisition-task"
                      type="button"
                      disabled={creatingFactTaskGapId === gap.gap_id || gap.fact_atom_ids.length > 0}
                      onClick={() => void createGapFactTask(gap.gap_id)}
                    ><BookOpen size={16} />{creatingFactTaskGapId === gap.gap_id ? "创建中…" : "创建事实补证任务"}</button>
                  )}
                </div>
              </article>
            })}
          </div>
        )}
      </Panel>
      <Panel title={`事实补证任务 · ${factAcquisitionTasks.tasks.length}`}>
        <div className="content-blueprint-wide knowledge-search-policy">
          <Badge tone="primary">airank.fact-acquisition-task.v1</Badge>
          <span>补证任务冻结缺口与质量证据；只有官方或已核验第三方来源、人工审核通过、当前有效且无冲突的事实才能放行。补证任务完成不等于内容已生成或已发布。</span>
        </div>
        {factAcquisitionTasks.tasks.length === 0 ? (
          <DataStateCard title="尚无事实补证任务" desc="请先从上方真实证据缺口创建任务；系统不会从历史缺口或营销猜测自动造任务。" tone="warning" />
        ) : (
          <div className="content-review-list" data-testid="fact-acquisition-task-list">
            {factAcquisitionTasks.tasks.map((task) => (
              <article className="content-review-item" data-testid="fact-acquisition-task-card" key={task.task_id}>
                <div className="content-review-head">
                  <div><strong>{task.title}</strong><span>{task.provider} · {task.collector_surface} · v{task.version} · {task.event_count} 条追加事件</span></div>
                  <Badge tone={task.status === "resolved" ? "success" : task.status === "blocked" ? "danger" : "warning"}>{task.resolution_state === "needs_fact_proposal" ? "待提议事实" : task.resolution_state === "needs_fact_review" ? "待审核事实" : task.resolution_state === "ready_for_intervention" ? "可进入干预" : "已阻断"}</Badge>
                </div>
                <div className="content-review-body">{task.evidence_requirement}</div>
                <div className="content-review-proof">
                  <span>{task.knowledge_source_ids.length} 个来源</span>
                  <span>{task.fact_revision_ids.length} 个事实修订</span>
                  <span>{task.approved_fact_revision_ids.length} 个已放行事实</span>
                  <span>来源门槛：官方 / 已核验第三方</span>
                  <code>{task.last_event_sha256.slice(0, 16)}…</code>
                </div>
                {task.status !== "resolved" ? (
                  <div className="fact-review-actions">
                    <select
                      aria-label={`为 ${task.title} 选择审核事实`}
                      value={taskFactSelections[task.task_id] ?? ""}
                      onChange={(event) => setTaskFactSelections((current) => ({ ...current, [task.task_id]: event.target.value }))}
                    >
                      <option value="">请选择当前可用审核事实</option>
                      {eligibleFacts.map((fact) => <option value={fact.revision_id} key={`${task.task_id}-${fact.revision_id}`}>{fact.title} · {fact.revision_id}</option>)}
                    </select>
                    <button
                      className="outline-button"
                      data-testid="bind-fact-acquisition-evidence"
                      type="button"
                      disabled={bindingFactTaskId === task.task_id || !taskFactSelections[task.task_id]}
                      onClick={() => void bindTaskFact(task.task_id, task.version)}
                    ><ShieldCheck size={16} />{bindingFactTaskId === task.task_id ? "核验中…" : "绑定并核验事实"}</button>
                    {eligibleFacts.length === 0 ? <button className="ghost-button" type="button" onClick={() => onNavigate("/console/knowledge")}>先去事实库补证</button> : null}
                  </div>
                ) : (
                  <div className="fact-review-actions"><Badge tone="success">可进入受治理内容干预</Badge><small>仍需内容审校、发布存证和同口径复测。</small></div>
                )}
              </article>
            ))}
          </div>
        )}
      </Panel>
      <Panel title="证据绑定页面蓝图">
        <form className="content-blueprint-form" onSubmit={(event) => void submitBlueprint(event)}>
          <label>产物类型<select value={assetType} onChange={(event) => setAssetType(event.target.value as GovernedContentCreateInput["assetType"])}>{governedAssetTypes.map((option) => <option value={option.value} key={option.value}>{option.label}</option>)}</select></label>
          <label>蓝图主题<input value={assetTitle} onChange={(event) => setAssetTitle(event.target.value)} maxLength={255} placeholder="例如：企业部署与审计能力" /><small>只进入 brief hash；公开标题由已审核事实和产物类型确定性生成。</small></label>
          <label className="content-blueprint-wide">编辑方向<textarea rows={3} value={editorialDirection} onChange={(event) => setEditorialDirection(event.target.value)} maxLength={1000} /><small>只作为结构编排输入并保存 hash，不会直接复制为公开事实。</small></label>
          <fieldset className="content-blueprint-facts">
            <legend>选择当前可用于生成的审核事实</legend>
            {eligibleFacts.length === 0 ? (
              <DataStateCard title="没有可用事实" desc="事实必须已批准、当前有效、无开放冲突，并能定位到有效来源的精确原文边界。" tone="warning" />
            ) : eligibleFacts.map((fact) => (
              <label className="content-blueprint-fact" key={fact.revision_id}>
                <input type="checkbox" checked={selectedFactRevisionIds.includes(fact.revision_id)} onChange={() => toggleBlueprintFact(fact.revision_id)} />
                <span><strong>{fact.title}</strong><small>{fact.fact_text}</small><code>{fact.revision_id}</code></span>
              </label>
            ))}
          </fieldset>
          <div className="content-blueprint-actions">
            <span>{eligibleFacts.length} 条可用 / {facts.length} 条事实；已选 {selectedFactRevisionIds.length} 条</span>
            <button className="airank-console-primary-button" type="submit" disabled={creatingBlueprint || eligibleFacts.length === 0}>{creatingBlueprint ? "生成中…" : "生成证据绑定蓝图"}</button>
          </div>
        </form>
      </Panel>
      <Panel title="公平证据对比 · 专用门禁">
        <form className="content-blueprint-form" onSubmit={(event) => void submitComparison(event)}>
          <div className="content-blueprint-wide knowledge-search-policy">
            <Badge tone="primary">same-scope</Badge>
            <span>两个主体必须使用相同 10 个维度，每个单元都绑定审核事实和精确原文；缺一项则整页不生成，不输出排名或市场份额推断。</span>
          </div>
          <label>目标主体<select value={targetSubjectId} onChange={(event) => { setTargetSubjectId(event.target.value); setTargetDisplayName(event.target.value); setComparisonAssignments({}); }}><option value="">请选择已绑定主体</option>{subjectOptions.map((option) => <option value={option.subjectId} key={`target-${option.subjectId}`}>{option.subjectId} · {option.subjectType}</option>)}</select></label>
          <label>目标公开名称<input value={targetDisplayName} onChange={(event) => setTargetDisplayName(event.target.value)} maxLength={128} placeholder="例如：AIRank" /></label>
          <label>对比主体<select value={peerSubjectId} onChange={(event) => { setPeerSubjectId(event.target.value); setPeerDisplayName(event.target.value); setComparisonAssignments({}); }}><option value="">请选择另一个主体</option>{subjectOptions.map((option) => <option value={option.subjectId} key={`peer-${option.subjectId}`}>{option.subjectId} · {option.subjectType}</option>)}</select></label>
          <label>对比公开名称<input value={peerDisplayName} onChange={(event) => setPeerDisplayName(event.target.value)} maxLength={128} placeholder="例如：竞品甲" /></label>
          <label>对比 brief<input value={comparisonTitle} onChange={(event) => setComparisonTitle(event.target.value)} maxLength={255} /><small>只进入 brief hash；公开标题由主体名称确定性生成。</small></label>
          <label>公平说明<input value={comparisonDirection} onChange={(event) => setComparisonDirection(event.target.value)} maxLength={1000} /><small>不直接复制进正文，不允许作为事实。</small></label>
          <div className="content-blueprint-wide fact-tags">
            {comparisonDimensions.map((dimension) => <Badge tone="muted" key={dimension.dimension_id}>{dimension.label}</Badge>)}
          </div>
          <fieldset className="content-blueprint-facts">
            <legend>把主体事实分配到相同维度</legend>
            {comparisonFacts.length === 0 ? (
              <DataStateCard title="没有可用于对比的主体事实" desc="事实必须先绑定 subject_type 与 subject_ref_id，并完成来源、审核、有效期和冲突门禁。" tone="warning" />
            ) : comparisonFacts.map((fact) => (
              <label className="content-blueprint-fact comparison-evidence-row" key={`comparison-${fact.revision_id}`}>
                <span><strong>{fact.subject_ref_id} · {fact.title}</strong><small>{fact.fact_text}</small><code>{fact.revision_id}</code></span>
                <select aria-label={`为 ${fact.title} 选择对比维度`} value={comparisonAssignments[fact.revision_id] ?? ""} onChange={(event) => setComparisonAssignments((current) => ({ ...current, [fact.revision_id]: event.target.value }))}>
                  <option value="">不用于本次对比</option>
                  {comparisonDimensions.map((dimension) => <option value={dimension.dimension_id} key={dimension.dimension_id}>{dimension.label}</option>)}
                </select>
              </label>
            ))}
          </fieldset>
          <div className="content-blueprint-actions">
            <span>证据矩阵 {comparisonCoveredCellCount} / 20 个单元已覆盖</span>
            <button className="airank-console-primary-button" type="submit" disabled={creatingComparison || comparisonCoveredCellCount < 20}>{creatingComparison ? "生成中…" : "生成公平证据对比"}</button>
          </div>
        </form>
      </Panel>
      <Panel title="长篇证据解释 · 专用门禁">
        <form className="content-blueprint-form" onSubmit={(event) => void submitExplainer(event)}>
          <div className="content-blueprint-wide knowledge-search-policy">
            <Badge tone="primary">evidence-heavy</Badge>
            <span>必须覆盖 7 类内容角色、至少 12 条审核事实和 1400 个有证据字符；正文中的品牌及别名总露出超过 3 次会被服务端拒绝。</span>
          </div>
          <label>解释主体<select value={explainerSubjectId} onChange={(event) => { setExplainerSubjectId(event.target.value); setExplainerDisplayName(event.target.value); setExplainerAssignments({}); }}><option value="">请选择已绑定主体</option>{subjectOptions.map((option) => <option value={option.subjectId} key={`explainer-${option.subjectId}`}>{option.subjectId} · {option.subjectType}</option>)}</select></label>
          <label>主体公开名称<input value={explainerDisplayName} onChange={(event) => setExplainerDisplayName(event.target.value)} maxLength={128} placeholder="例如：AIRank" /></label>
          <label>解释 brief<input value={explainerTitle} onChange={(event) => setExplainerTitle(event.target.value)} maxLength={255} /><small>只进入 brief hash；不会复制成公开主张。</small></label>
          <label>品牌别名<input value={explainerBrandAliases} onChange={(event) => setExplainerBrandAliases(event.target.value)} maxLength={512} placeholder="多个别名用逗号分隔" /><small>用于品牌露出计数，不用于自动插入品牌。</small></label>
          <label className="content-blueprint-wide">编辑方向<textarea rows={2} value={explainerDirection} onChange={(event) => setExplainerDirection(event.target.value)} maxLength={1000} /></label>
          <div className="content-blueprint-wide fact-tags">
            {explainerRoles.map((role) => <Badge tone={explainerRoleCounts[role.value] >= role.minimum ? "success" : "warning"} key={role.value}>{role.label} {explainerRoleCounts[role.value]}/{role.minimum}</Badge>)}
            <Badge tone={explainerSupportedCharacterCount >= 1400 ? "success" : "warning"}>证据字符 {explainerSupportedCharacterCount}/1400</Badge>
          </div>
          <fieldset className="content-blueprint-facts">
            <legend>把主体事实分配到解释角色</legend>
            {explainerFacts.length === 0 ? (
              <DataStateCard title="没有可用于解释的主体事实" desc="先补齐同一主体的审核事实与精确来源边界；系统不会为凑篇幅重复事实或扩写无证据段落。" tone="warning" />
            ) : explainerFacts.map((fact) => (
              <label className="content-blueprint-fact comparison-evidence-row" key={`explainer-fact-${fact.revision_id}`}>
                <span><strong>{fact.title}</strong><small>{fact.fact_text}</small><code>{fact.revision_id}</code></span>
                <select aria-label={`为 ${fact.title} 选择解释角色`} value={explainerAssignments[fact.revision_id] ?? ""} onChange={(event) => setExplainerAssignments((current) => ({ ...current, [fact.revision_id]: event.target.value }))}>
                  <option value="">不用于本次解释</option>
                  {explainerRoles.map((role) => <option value={role.value} key={role.value}>{role.label} · 至少 {role.minimum}</option>)}
                </select>
              </label>
            ))}
          </fieldset>
          <div className="content-blueprint-actions">
            <span>{explainerRoleCoverageComplete ? "角色覆盖已完成" : "角色覆盖未完成"} · {explainerSupportedCharacterCount} 个证据字符</span>
            <button className="airank-console-primary-button" type="submit" disabled={creatingExplainer || !explainerRoleCoverageComplete || explainerSupportedCharacterCount < 1400}>{creatingExplainer ? "生成中…" : "生成证据解释指南"}</button>
          </div>
        </form>
      </Panel>
      <Panel title="证据绑定内容审校">
        {contentAssets.length === 0 ? (
          <DataStateCard title="尚无可审校内容" desc="只有审核通过且存在精确原文支持的事实，才能生成这里的内容资产。" tone="warning" />
        ) : (
          <div className="content-review-list">
            {contentAssets.map((asset) => (
              <article className="content-review-item" key={asset.asset_id}>
                <div className="content-review-head"><div><strong>{asset.title}</strong><span>{asset.asset_type} · {asset.skill_id ? `${asset.skill_id}@${asset.skill_version}` : asset.generation_mode} · {formatDateTime(asset.created_at)}</span></div><Badge tone={asset.status === "approved" ? "success" : asset.status === "rejected" ? "danger" : "warning"}>{asset.status}</Badge></div>
                <div className="content-review-body">{asset.body_md}</div>
                <div className="content-review-proof"><span>{asset.section_count} 个结构段</span><span>{asset.fact_revision_ids.length} 个事实修订</span><span>{asset.claim_assertion_ids.length} 条主张</span><span>{asset.claim_support_ids.length} 条证据支持</span>{asset.blueprint_sha256 ? <span>蓝图 {asset.blueprint_sha256.slice(0, 12)}…</span> : null}</div>
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
  const [contentAssets, setContentAssets] = useState<GovernedContentAsset[]>([]);
  const [scanRuns, setScanRuns] = useState<ScanRun[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [selectedAssetId, setSelectedAssetId] = useState("");
  const [publishChannel, setPublishChannel] = useState<PublishPackageCreateInput["channel"]>("export");
  const [targetEndpoint, setTargetEndpoint] = useState("");
  const [creatingPackage, setCreatingPackage] = useState(false);
  const [selectedPackageId, setSelectedPackageId] = useState("");
  const [publishedUrl, setPublishedUrl] = useState("");
  const [baselineRunId, setBaselineRunId] = useState("");
  const [screenshotRefId, setScreenshotRefId] = useState("");
  const [screenshotSha256, setScreenshotSha256] = useState("");
  const [recordingEvidence, setRecordingEvidence] = useState(false);
  const [mutationTargetId, setMutationTargetId] = useState("");
  const [mutationAction, setMutationAction] = useState<PublishMutationCreateInput["action"]>("update");
  const [replacementAssetId, setReplacementAssetId] = useState("");
  const [mutationReason, setMutationReason] = useState("");
  const [creatingMutation, setCreatingMutation] = useState(false);
  const [reconciliations, setReconciliations] = useState<PublicationReconciliation[]>([]);
  const [reconciliationPackageId, setReconciliationPackageId] = useState("");
  const [reconciliationPublishedUrl, setReconciliationPublishedUrl] = useState("");
  const [reconciliationReceiptId, setReconciliationReceiptId] = useState("");
  const [reconciliationResponseStatus, setReconciliationResponseStatus] = useState("200");
  const [reconciliationEvidenceRef, setReconciliationEvidenceRef] = useState("");
  const [reconciliationEvidenceSha, setReconciliationEvidenceSha] = useState("");
  const [reconciliationEvidenceNote, setReconciliationEvidenceNote] = useState("");
  const [reconciliationObservedAt, setReconciliationObservedAt] = useState(() => {
    const now = new Date();
    return new Date(now.getTime() - now.getTimezoneOffset() * 60_000).toISOString().slice(0, 16);
  });
  const [submittingReconciliation, setSubmittingReconciliation] = useState(false);
  const [reviewCaseId, setReviewCaseId] = useState("");
  const [reviewAction, setReviewAction] = useState<"approved" | "rejected">("approved");
  const [reconciliationReviewNote, setReconciliationReviewNote] = useState("");
  const [reviewingReconciliation, setReviewingReconciliation] = useState(false);

  useEffect(() => {
    if (!project.id) return;
    const controller = new AbortController();
    Promise.all([
      fetchPublishPackages(project.id, controller.signal),
      fetchRetestWindows(project.id, controller.signal),
      fetchContentAssets(project.id, controller.signal),
      fetchScanRuns(project.id, controller.signal),
      fetchPublicationReconciliations(project.id, controller.signal),
    ])
      .then(([nextPackages, nextWindows, nextAssets, nextRuns, nextReconciliations]) => {
        setPackages(nextPackages);
        setWindows(nextWindows);
        setContentAssets(nextAssets);
        setScanRuns(nextRuns);
        setReconciliations(nextReconciliations);
        const firstApprovedAsset = nextAssets.find((item) => item.status === "approved");
        const firstUnpublishedPackage = nextPackages.find((item) => ["packaged", "delivered"].includes(item.status));
        const firstPublishedExternal = nextPackages.find((item) => item.status === "published" && item.channel !== "export");
        const firstCompletedBaseline = nextRuns.find((item) => item.status === "completed" && item.run_type === "baseline");
        const firstUnknownPackage = nextPackages.find((item) => item.status === "outcome_unknown");
        const currentUserId = getStoredAuthSession()?.user.userId ?? "";
        const firstReviewableCase = nextReconciliations.find((item) => item.status === "awaiting_review" && item.submitted_by !== currentUserId);
        setSelectedAssetId((current) => current || firstApprovedAsset?.asset_id || "");
        setReplacementAssetId((current) => current || firstApprovedAsset?.asset_id || "");
        setSelectedPackageId((current) => current || firstUnpublishedPackage?.package_id || "");
        setMutationTargetId((current) => current || firstPublishedExternal?.package_id || "");
        setPublishedUrl((current) => current || firstUnpublishedPackage?.published_url || "");
        setBaselineRunId((current) => current || firstCompletedBaseline?.run_id || "");
        setReconciliationPackageId((current) => current || firstUnknownPackage?.package_id || "");
        setReconciliationPublishedUrl((current) => current || firstUnknownPackage?.published_url || "");
        setReviewCaseId((current) => current || firstReviewableCase?.case_id || "");
        setLoadError(null);
      })
      .catch((error) => {
        if (controller.signal.aborted) return;
        setLoadError(error instanceof Error ? error.message : "发布中心接口不可用");
      });
    return () => controller.abort();
  }, [project.id]);

  const approvedAssets = contentAssets.filter((item) => item.status === "approved");
  const evidenceCandidates = packages.filter((item) => ["packaged", "delivered"].includes(item.status) && item.publication_action !== "withdraw");
  const mutationCandidates = packages.filter((item) => item.status === "published" && item.channel !== "export");
  const completedBaselines = scanRuns.filter((item) => item.status === "completed" && item.run_type === "baseline");
  const reconciliationCandidates = packages.filter((item) => item.status === "outcome_unknown" && item.channel !== "export");
  const currentUserId = getStoredAuthSession()?.user.userId ?? "";
  const reviewableReconciliations = reconciliations.filter((item) => item.status === "awaiting_review" && item.submitted_by !== currentUserId);
  const selectedReviewReconciliation = reviewableReconciliations.find((item) => item.case_id === reviewCaseId) || null;

  const submitPublishPackage = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!selectedAssetId) {
      notify({ title: "没有可发布内容", desc: "请先让内容资产通过事实核验和风险审核。", tone: "warning" });
      return;
    }
    const endpoint = targetEndpoint.trim();
    if (publishChannel !== "export" && !endpoint) {
      notify({ title: "缺少目标端点", desc: "WordPress / HTTP 发布必须填写客户授权的 HTTPS 端点。", tone: "warning" });
      return;
    }
    setCreatingPackage(true);
    try {
      const created = await createPublishPackage({
        assetId: selectedAssetId,
        channel: publishChannel,
        targetEndpoint: publishChannel === "export" ? undefined : endpoint,
      });
      setPackages((current) => [created, ...current.filter((item) => item.package_id !== created.package_id)]);
      setSelectedPackageId(created.package_id);
      setPublishedUrl(created.published_url || "");
      notify({
        title: publishChannel === "export" ? "不可变导出包已创建" : "外部发布任务已入队",
        desc: publishChannel === "export"
          ? `快照 ${created.snapshot_id} 已绑定审核结果与内容 hash。`
          : "Worker 将使用服务端安全注入的客户凭证执行；前端不会接收或保存站点密钥。",
        tone: "success",
      });
    } catch (error) {
      notify({ title: "发布包未创建", desc: error instanceof Error ? error.message : "发布接口不可用", tone: "danger" });
    } finally {
      setCreatingPackage(false);
    }
  };

  const submitPublicationEvidence = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const screenshotRef = screenshotRefId.trim();
    const screenshotHash = screenshotSha256.trim().toLowerCase();
    if (!selectedPackageId || !publishedUrl.trim() || !baselineRunId) {
      notify({ title: "发布证据不完整", desc: "必须选择发布包、填写真实发布 URL，并绑定已完成的 T0 基线。", tone: "warning" });
      return;
    }
    if ((screenshotRef && !screenshotHash) || (!screenshotRef && screenshotHash)) {
      notify({ title: "截图证据不完整", desc: "截图对象引用与 SHA-256 必须同时填写，或者同时留空。", tone: "warning" });
      return;
    }
    if (screenshotHash && !/^[0-9a-f]{64}$/.test(screenshotHash)) {
      notify({ title: "截图哈希格式错误", desc: "SHA-256 必须是 64 位十六进制字符串。", tone: "warning" });
      return;
    }
    setRecordingEvidence(true);
    try {
      const updated = await recordPublicationEvidence(selectedPackageId, {
        publishedUrl: publishedUrl.trim(),
        baselineRunId,
        screenshotRefId: screenshotRef || undefined,
        screenshotSha256: screenshotHash || undefined,
      });
      setPackages((current) => current.map((item) => item.package_id === updated.package_id ? updated : item));
      setWindows(await fetchRetestWindows(project.id));
      setSelectedPackageId("");
      setPublishedUrl("");
      setScreenshotRefId("");
      setScreenshotSha256("");
      notify({ title: "真实发布证据已登记", desc: "系统已创建 T0、T+7、T+14、T+30 观察窗口；后续只做审慎归因。", tone: "success" });
    } catch (error) {
      notify({ title: "发布证据未登记", desc: error instanceof Error ? error.message : "发布证据接口不可用", tone: "danger" });
    } finally {
      setRecordingEvidence(false);
    }
  };

  const submitPublishMutation = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const reason = mutationReason.trim();
    if (!mutationTargetId || reason.length < 10 || (mutationAction === "update" && !replacementAssetId)) {
      notify({ title: "变更申请不完整", desc: "必须选择已发布外部包、填写至少 10 个字符的原因；更新还必须选择已审核替换内容。", tone: "warning" });
      return;
    }
    setCreatingMutation(true);
    try {
      const created = await createPublishMutation({
        packageId: mutationTargetId,
        action: mutationAction,
        replacementAssetId: mutationAction === "update" ? replacementAssetId : undefined,
        reason,
      });
      setPackages((current) => [created, ...current.filter((item) => item.package_id !== created.package_id)]);
      setMutationReason("");
      notify({
        title: mutationAction === "update" ? "更新动作已入队" : "撤回动作已入队",
        desc: "原发布状态只有在 Worker 收到可信远端回执后才会改变；未知结果会停止自动重发并进入人工对账。",
        tone: "success",
      });
    } catch (error) {
      notify({ title: "发布变更未创建", desc: error instanceof Error ? error.message : "发布变更接口不可用", tone: "danger" });
    } finally {
      setCreatingMutation(false);
    }
  };

  const submitReconciliationCase = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const evidenceSha = reconciliationEvidenceSha.trim().toLowerCase();
    const evidenceNote = reconciliationEvidenceNote.trim();
    const responseStatus = Number(reconciliationResponseStatus);
    if (!reconciliationPackageId || !reconciliationPublishedUrl.trim() || !reconciliationReceiptId.trim() || !Number.isInteger(responseStatus) || responseStatus < 200 || responseStatus > 299 || !reconciliationEvidenceRef.trim() || !/^[0-9a-f]{64}$/.test(evidenceSha) || evidenceNote.length < 20 || !reconciliationObservedAt) {
      notify({ title: "人工对账证据不完整", desc: "必须填写真实 URL、外部回执标识、实际 2xx 状态码、不可变对象引用及 SHA-256、至少 20 个字符的核对说明和观察时间。", tone: "warning" });
      return;
    }
    setSubmittingReconciliation(true);
    try {
      const created = await submitPublicationReconciliation({
        packageId: reconciliationPackageId,
        publishedUrl: reconciliationPublishedUrl.trim(),
        externalReceiptId: reconciliationReceiptId.trim(),
        responseStatus,
        evidenceObjectRefId: reconciliationEvidenceRef.trim(),
        evidenceSha256: evidenceSha,
        evidenceNote,
        observedAt: new Date(reconciliationObservedAt).toISOString(),
      });
      setReconciliations((current) => [created, ...current.filter((item) => item.case_id !== created.case_id)]);
      setReconciliationPackageId("");
      setReconciliationPublishedUrl("");
      setReconciliationReceiptId("");
      setReconciliationResponseStatus("200");
      setReconciliationEvidenceRef("");
      setReconciliationEvidenceSha("");
      setReconciliationEvidenceNote("");
      notify({ title: "对账证据已提交", desc: "当前仍保持 outcome_unknown 和禁止重放；只有另一位交付管理员复核通过后才会恢复为 delivered。", tone: "success" });
    } catch (error) {
      notify({ title: "对账证据未提交", desc: error instanceof Error ? error.message : "人工对账接口不可用", tone: "danger" });
    } finally {
      setSubmittingReconciliation(false);
    }
  };

  const submitReconciliationReview = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const note = reconciliationReviewNote.trim();
    if (!reviewCaseId || note.length < 10) {
      notify({ title: "复核意见不完整", desc: "请选择非本人提交的待复核案例，并填写至少 10 个字符的意见。", tone: "warning" });
      return;
    }
    setReviewingReconciliation(true);
    try {
      if (!selectedReviewReconciliation) {
        throw new Error("待复核案例已变化，请刷新后重新选择。");
      }
      const updated = await reviewPublicationReconciliation(
        reviewCaseId,
        reviewAction,
        note,
        selectedReviewReconciliation.evidence_object_ref_id,
        selectedReviewReconciliation.evidence_sha256,
      );
      setReconciliations((current) => current.map((item) => item.case_id === updated.case_id ? updated : item));
      setPackages(await fetchPublishPackages(project.id));
      setReviewCaseId("");
      setReconciliationReviewNote("");
      notify({
        title: reviewAction === "approved" ? "双人复核已应用" : "对账申请已驳回",
        desc: reviewAction === "approved"
          ? "发布包只恢复为 delivered/withdrawn，回执明确标记为人工证据且 external_delivery_verified=false；仍需登记真实页面证据。"
          : "外部结果仍为未知，系统继续禁止自动重放。",
        tone: reviewAction === "approved" ? "success" : "warning",
      });
    } catch (error) {
      notify({ title: "对账复核未完成", desc: error instanceof Error ? error.message : "对账复核接口不可用", tone: "danger" });
    } finally {
      setReviewingReconciliation(false);
    }
  };

  const downloadReconciliationEvidence = async () => {
    if (!selectedReviewReconciliation) return;
    try {
      const blob = await fetchEvidenceObject(selectedReviewReconciliation.evidence_object_ref_id);
      const objectUrl = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = objectUrl;
      anchor.download = `${selectedReviewReconciliation.case_id}-${selectedReviewReconciliation.evidence_sha256.slice(0, 12)}`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
      notify({ title: "不可变证据已下载", desc: `请核对对象 ${selectedReviewReconciliation.evidence_object_ref_id} 与页面、回执是否一致后再提交决定。`, tone: "success" });
    } catch (error) {
      notify({ title: "证据对象无法读取", desc: error instanceof Error ? error.message : "对象存储不可用", tone: "danger" });
    }
  };

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
        <MiniStat label="待处理/失败/待对账" value={String(packages.filter((item) => ["queued", "publishing", "failed", "outcome_unknown"].includes(item.status)).length)} icon={SearchCheck} />
        <MiniStat label="复测窗口" value={String(windows.length)} icon={RotateCw} />
      </section>
      <Panel title="创建不可变发布包">
        <form className="content-blueprint-form publishing-action-form" onSubmit={(event) => void submitPublishPackage(event)}>
          <label>
            已审核内容
            <select value={selectedAssetId} onChange={(event) => setSelectedAssetId(event.target.value)}>
              <option value="">请选择已通过审校的内容</option>
              {approvedAssets.map((asset) => <option value={asset.asset_id} key={asset.asset_id}>{asset.title} · {asset.asset_type}</option>)}
            </select>
            <small>只有当前正文 hash 对应的事实核验和人工审核均通过，服务端才会创建快照。</small>
          </label>
          <label>
            发布渠道
            <select value={publishChannel} onChange={(event) => setPublishChannel(event.target.value as PublishPackageCreateInput["channel"])}>
              <option value="export">导出发布包</option>
              <option value="wordpress">WordPress</option>
              <option value="http">通用 HTTP</option>
            </select>
            <small>export 可立即交付；外部渠道只有拿到真实回执后才会从 partial 晋级。</small>
          </label>
          {publishChannel !== "export" ? (
            <label className="content-blueprint-wide">
              客户授权 HTTPS 端点
              <input type="url" required value={targetEndpoint} onChange={(event) => setTargetEndpoint(event.target.value)} maxLength={2048} placeholder={publishChannel === "wordpress" ? "https://customer.example/wp-json/wp/v2/posts" : "https://customer.example/api/publish"} />
              <small>客户站点凭证只允许由 Worker 安全注入；不得写入浏览器、发布快照、日志或 Git。</small>
            </label>
          ) : null}
          <div className="content-blueprint-actions">
            <span>{approvedAssets.length} 个已审核内容可发布；系统会冻结正文、审核记录、Skill 版本与证据绑定。</span>
            <button className="airank-console-primary-button" type="submit" disabled={creatingPackage || !selectedAssetId}>{creatingPackage ? "创建中…" : publishChannel === "export" ? "创建导出包" : "创建并入队"}</button>
          </div>
        </form>
      </Panel>
      <Panel title="更新 / 撤回已发布内容">
        <form className="content-blueprint-form publishing-action-form" onSubmit={(event) => void submitPublishMutation(event)}>
          <label>
            已发布外部包
            <select value={mutationTargetId} onChange={(event) => setMutationTargetId(event.target.value)}>
              <option value="">请选择已登记真实发布证据的外部包</option>
              {mutationCandidates.map((item) => <option value={item.package_id} key={item.package_id}>{item.package_id} · {item.channel} · {item.published_url}</option>)}
            </select>
            <small>只允许操作 `published` 的 WordPress / HTTP 包；导出包、未确认回执和历史版本均被服务端拒绝。</small>
          </label>
          <label>
            变更动作
            <select value={mutationAction} onChange={(event) => setMutationAction(event.target.value as PublishMutationCreateInput["action"])}>
              <option value="update">版本化更新</option>
              <option value="withdraw">撤回为不可公开</option>
            </select>
            <small>WordPress 撤回使用可恢复的 draft，不执行 DELETE；通用 HTTP 按 v2 契约交由客户端实现。</small>
          </label>
          {mutationAction === "update" ? (
            <label className="content-blueprint-wide">
              已审核替换内容
              <select value={replacementAssetId} onChange={(event) => setReplacementAssetId(event.target.value)}>
                <option value="">请选择当前 hash 已通过审核的内容</option>
                {approvedAssets.map((asset) => <option value={asset.asset_id} key={asset.asset_id}>{asset.title} · {asset.asset_type}</option>)}
              </select>
              <small>系统创建新的不可变快照；真实更新回执后原包变为 superseded，新包仍需重新登记页面证据。</small>
            </label>
          ) : null}
          <label className="content-blueprint-wide">
            变更原因
            <textarea required minLength={10} maxLength={1000} value={mutationReason} onChange={(event) => setMutationReason(event.target.value)} placeholder="记录客户授权、事实过期、合规整改或版本替换依据。" />
            <small>原因、操作者、目标包和内容 hash 会随动作快照保留；浏览器不接触客户站点凭证。</small>
          </label>
          <div className="content-blueprint-actions">
            <span>{mutationCandidates.length} 个已发布外部包可操作；远端响应丢失时禁止自动重发。</span>
            <button className="airank-console-primary-button" type="submit" disabled={creatingMutation || !mutationTargetId}>{creatingMutation ? "提交中…" : mutationAction === "update" ? "提交更新" : "提交撤回"}</button>
          </div>
        </form>
      </Panel>
      <Panel title="未知发布结果 · 双人证据对账">
        <form className="content-blueprint-form publishing-action-form" onSubmit={(event) => void submitReconciliationCase(event)}>
          <label>
            待对账发布包
            <select
              value={reconciliationPackageId}
              onChange={(event) => {
                const packageId = event.target.value;
                setReconciliationPackageId(packageId);
                setReconciliationPublishedUrl(packages.find((item) => item.package_id === packageId)?.published_url || "");
              }}
            >
              <option value="">请选择 outcome_unknown 发布包</option>
              {reconciliationCandidates.map((item) => <option value={item.package_id} key={item.package_id}>{item.package_id} · {item.publication_action} · {item.channel}</option>)}
            </select>
            <small>只接受 Operation Guard 已记录外部副作用开始的未知结果；本流程不会重新调用客户站点。</small>
          </label>
          <label>
            外部回执 / 远端 ID
            <input required maxLength={255} value={reconciliationReceiptId} onChange={(event) => setReconciliationReceiptId(event.target.value)} placeholder="WordPress 填数字 post ID；HTTP 填渠道回执 ID" />
            <small>WordPress 必须是数字远端 ID，供后续更新和可恢复撤回使用。</small>
          </label>
          <label>
            实际 HTTP 状态码
            <input type="number" required min={200} max={299} step={1} value={reconciliationResponseStatus} onChange={(event) => setReconciliationResponseStatus(event.target.value)} />
            <small>必须按客户后台或渠道回执原样录入 2xx，不使用固定演示状态。</small>
          </label>
          <label className="content-blueprint-wide">
            已观察到的真实 URL
            <input type="url" required maxLength={2048} value={reconciliationPublishedUrl} onChange={(event) => setReconciliationPublishedUrl(event.target.value)} placeholder="https://customer.example/published-page" />
          </label>
          <label>
            不可变证据对象引用
            <input required maxLength={64} value={reconciliationEvidenceRef} onChange={(event) => setReconciliationEvidenceRef(event.target.value)} placeholder="object_…" />
          </label>
          <label>
            证据 SHA-256
            <input required maxLength={64} value={reconciliationEvidenceSha} onChange={(event) => setReconciliationEvidenceSha(event.target.value)} placeholder="64 位十六进制哈希" />
          </label>
          <label>
            实际观察时间
            <input type="datetime-local" required value={reconciliationObservedAt} onChange={(event) => setReconciliationObservedAt(event.target.value)} />
          </label>
          <label className="content-blueprint-wide">
            核对说明
            <textarea required minLength={20} maxLength={2000} value={reconciliationEvidenceNote} onChange={(event) => setReconciliationEvidenceNote(event.target.value)} placeholder="说明通过哪个客户后台、页面或渠道回执确认了远端副作用，以及证据对象包含什么。" />
            <small>服务端会重新读取对象存储并校验字节哈希、项目归属和 immutable 标记。</small>
          </label>
          <div className="content-blueprint-actions">
            <span>{reconciliationCandidates.length} 个未知结果待核对；提交人不能复核自己的申请。</span>
            <button className="airank-console-primary-button" type="submit" disabled={submittingReconciliation || !reconciliationPackageId}>{submittingReconciliation ? "提交中…" : "提交证据等待复核"}</button>
          </div>
        </form>
      </Panel>
      <Panel title="独立复核 · 不执行外部重放">
        <form className="content-blueprint-form publishing-action-form" onSubmit={(event) => void submitReconciliationReview(event)}>
          <label>
            非本人待复核案例
            <select value={reviewCaseId} onChange={(event) => setReviewCaseId(event.target.value)}>
              <option value="">请选择另一位管理员提交的案例</option>
              {reviewableReconciliations.map((item) => <option value={item.case_id} key={item.case_id}>{item.case_id} · {item.package_id} · {item.submitted_by}</option>)}
            </select>
            <small>当前登录用户与提交人必须不同；服务端再次校验，不依赖前端隐藏。</small>
          </label>
          <label>
            复核结论
            <select value={reviewAction} onChange={(event) => setReviewAction(event.target.value as "approved" | "rejected")}>
              <option value="approved">证据支持已发生</option>
              <option value="rejected">证据不足，继续阻塞</option>
            </select>
            <small>系统不提供“确认未发生并重发”选项；通用渠道的缺席证据不足以安全重试。</small>
          </label>
          {selectedReviewReconciliation ? (
            <div className="content-blueprint-wide publication-reconciliation-evidence-summary">
              <strong>复核对象：{selectedReviewReconciliation.evidence_object_ref_id}</strong>
              <span>SHA-256：{selectedReviewReconciliation.evidence_sha256}</span>
              <span>观察时间：{formatDateTime(selectedReviewReconciliation.observed_at)} · 外部回执：{selectedReviewReconciliation.external_receipt_id}</span>
              <span>真实 URL：{selectedReviewReconciliation.published_url}</span>
              <span>提交说明：{selectedReviewReconciliation.evidence_note}</span>
              <button className="table-action" type="button" onClick={() => void downloadReconciliationEvidence()}>下载并核对不可变证据</button>
            </div>
          ) : null}
          <label className="content-blueprint-wide">
            独立复核意见
            <textarea required minLength={10} maxLength={2000} value={reconciliationReviewNote} onChange={(event) => setReconciliationReviewNote(event.target.value)} placeholder="记录独立核验路径、回执与截图的一致性，或驳回原因。" />
          </label>
          <div className="content-blueprint-actions">
            <span>通过后只形成 two_person_manual_evidence 回执，并保持 external_delivery_verified=false。</span>
            <button className="airank-console-primary-button" type="submit" disabled={reviewingReconciliation || !reviewCaseId}>{reviewingReconciliation ? "复核中…" : reviewAction === "approved" ? "复核通过并本地收口" : "驳回并继续阻塞"}</button>
          </div>
        </form>
        {reconciliations.length > 0 ? (
          <div className="gap-table">
            {reconciliations.map((item) => (
              <div className="gap-row" key={item.case_id}>
                <IconTile tone={item.status === "applied" ? "success" : item.status === "rejected" ? "danger" : "warning"}><ShieldCheck size={21} /></IconTile>
                <div><strong>{item.case_id}</strong><span>{item.package_id} · 提交 {item.submitted_by} · 复核 {item.reviewed_by || "待定"}</span></div>
                <Badge tone={item.status === "applied" ? "success" : item.status === "rejected" ? "danger" : "warning"}>{item.status}</Badge>
                <strong>{item.reconciliation_method}</strong>
                <span>事件 {item.event_sequence} · 回执 {item.receipt_sha256 ? `${item.receipt_sha256.slice(0, 10)}…` : "待生成"}</span>
                <Badge tone="warning">非原生回执</Badge>
              </div>
            ))}
          </div>
        ) : <DataStateCard title="尚无人工对账案例" desc="只有真实发布调用在外部副作用开始后丢失响应时，才允许提交证据。" tone="warning" />}
      </Panel>
      <Panel title="登记真实发布证据">
        <form className="content-blueprint-form publishing-action-form" onSubmit={(event) => void submitPublicationEvidence(event)}>
          <label>
            待登记发布包
            <select
              value={selectedPackageId}
              onChange={(event) => {
                const packageId = event.target.value;
                setSelectedPackageId(packageId);
                setPublishedUrl(packages.find((item) => item.package_id === packageId)?.published_url || "");
              }}
            >
              <option value="">请选择尚未完成证据登记的发布包</option>
              {evidenceCandidates.map((item) => <option value={item.package_id} key={item.package_id}>{item.package_id} · {item.channel} · {item.status}</option>)}
            </select>
            <small>外部 Worker 的 delivered 回执仍需人工确认页面可访问，不能自动当作已发布。</small>
          </label>
          <label>
            T0 基线
            <select value={baselineRunId} onChange={(event) => setBaselineRunId(event.target.value)}>
              <option value="">请选择已完成基线</option>
              {completedBaselines.map((run) => <option value={run.run_id} key={run.run_id}>{run.name || run.run_id} · {run.run_type} · {formatDateTime(run.finished_at || run.updated_at)}</option>)}
            </select>
            <small>登记后复测会冻结该基线的 Prompt、Provider、Cohort、采集面和模型口径。</small>
          </label>
          <label className="content-blueprint-wide">
            真实发布 URL
            <input type="url" required value={publishedUrl} onChange={(event) => setPublishedUrl(event.target.value)} maxLength={2048} placeholder="https://customer.example/evidence/page" />
            <small>这里只登记实际可访问地址，不接受计划 URL、媒体名单或未落地渠道。</small>
          </label>
          <label>
            截图对象引用（可选）
            <input value={screenshotRefId} onChange={(event) => setScreenshotRefId(event.target.value)} maxLength={64} placeholder="evidence_object_…" />
          </label>
          <label>
            截图 SHA-256（可选）
            <input value={screenshotSha256} onChange={(event) => setScreenshotSha256(event.target.value)} maxLength={64} placeholder="64 位十六进制哈希" />
          </label>
          <div className="content-blueprint-actions">
            <span>{completedBaselines.length} 个已完成运行可作为基线；缺少真实 URL 或有效基线时服务端拒绝建立观察窗口。</span>
            <button className="airank-console-primary-button" type="submit" disabled={recordingEvidence || !selectedPackageId || !baselineRunId}>{recordingEvidence ? "登记中…" : "登记证据并建立复测"}</button>
          </div>
        </form>
      </Panel>
      {loadError && <DataStateCard title="发布中心读取失败" desc={loadError} tone="danger" />}
      {!loadError && packages.length === 0 && <DataStateCard title="尚无发布包" desc="内容必须通过事实核验和风险审核后，才能生成不可变发布快照。" tone="warning" />}
      <Panel title="不可变发布包">
        <table className="question-table publish-table">
          <thead>
            <tr><th>发布包</th><th>动作 / 目标</th><th>渠道</th><th>状态</th><th>实现等级</th><th>内容哈希</th><th>创建时间</th><th>操作</th></tr>
          </thead>
          <tbody>
            {packages.map((item) => (
              <tr key={item.package_id}>
                <td><strong>{item.package_id}</strong></td>
                <td><strong>{item.publication_action}</strong><br /><span>{item.target_package_id || "首次发布"}</span></td>
                <td>{item.channel}</td>
                <td><Badge tone={["published", "delivered"].includes(item.status) ? "success" : ["failed", "withdrawn"].includes(item.status) ? "danger" : ["queued", "outcome_unknown", "superseded"].includes(item.status) ? "warning" : "primary"}>{item.status}</Badge></td>
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
                        const operation = latest?.operation_id
                          ? await fetchPublishOperation(latest.operation_id)
                          : null;
                        openPanel({
                          title: item.package_id,
                          desc: "发布包与内容审核、不可变快照、Worker attempt 和复测窗口关联。",
                          items: [
                            `发布渠道：${item.channel}`,
                            `发布动作：${item.publication_action}`,
                            `目标发布包：${item.target_package_id || "首次发布"}`,
                            `变更原因：${item.action_reason || "无"}`,
                            `状态：${item.status}`,
                            `快照：${item.snapshot_id}`,
                            `发布 URL：${item.published_url || "尚未登记"}`,
                            `执行次数：${attempts.length}`,
                            `最近执行：${latest ? `${latest.status}${latest.error_code ? ` / ${latest.error_code}` : ""}` : "尚未执行"}`,
                            `操作保护：${operation ? `${operation.state} / ${operation.operation_id}` : "尚无 Operation Guard 记录"}`,
                            `外部副作用：${operation?.external_effect_started ? "可能已开始" : "未记录开始"}`,
                            `待对账：${latest?.reconciliation_required || operation?.reconciliation_required ? "是，禁止自动重发" : "否"}`,
                            `事件链：${operation ? `${operation.events.length} 个不可变事件` : "0"}`,
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
    const reportId = report.report_id;
    setDownloadingReportId(reportId);
    try {
      const packet = await downloadReportEvidencePacket(report);
      const sourceGovernance = packet.summary.source_host_count > 0
        ? `${packet.summary.source_authority_resolved_count}/${packet.summary.source_host_count} 个来源已具备有效权威结论${packet.summary.source_authority_summary_eligible ? "" : "（覆盖不完整，不生成整体权威性结论）"}`
        : "当前证据包没有可分类的 Citation 域名";
      notify({
        title: "可核验证据 ZIP 已下载",
        desc: `${packet.summary.sample_count} 个样本、${packet.summary.citation_count} 条引用；${sourceGovernance}；内含 canonical manifest、可打印 HTML、空白评分表和 SHA256SUMS。整包 SHA-256 ${packet.content_sha256.slice(0, 12)}…，下载回执已记录。`,
        tone: "success",
      });
    } catch (error) {
      notify({
        title: "证据包导出失败",
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
        subtitle="复测 AI 回答变化；导出确定性 ZIP，包含证据 manifest、可打印 HTML、空白人工评分表与逐文件哈希，并用下载回执锚定整包 SHA-256。"
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
              <div className="report-card-heading">
                <h3>{item.title}</h3>
                <Badge tone={qualityBlocked ? "danger" : "success"}>{qualityBlocked ? "quality blocked" : "evidence ready"}</Badge>
              </div>
              <p>{item.desc}</p>
              <span>{item.date}</span>
            </div>
            <button
              className="outline-button"
              type="button"
              disabled={qualityBlocked || downloadingReportId === item.report_id}
              onClick={() => void downloadReport(item)}
            >
              {qualityBlocked ? (
                "质量阻断"
              ) : downloadingReportId === item.report_id ? (
                "生成并校验中"
              ) : (
                <>
                  <Download size={15} />
                  导出可核验 ZIP
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

type ProviderCredentialDraft = {
  secret: string;
  reason: string;
  confirmBillable: boolean;
  confirmRevoke: boolean;
};

type ProviderPriceDraft = {
  routeKey: string;
  currency: string;
  inputPrice: string;
  outputPrice: string;
  effectiveFrom: string;
  sourceKind: ProviderPriceVersion["source_kind"];
  sourceReference: string;
  reason: string;
};

const emptyProviderCredentialDraft = (): ProviderCredentialDraft => ({
  secret: "",
  reason: "",
  confirmBillable: false,
  confirmRevoke: false,
});

function SettingsPage() {
  const overview = useConsoleOverview();
  const { project } = overview;
  const { notify, openPanel } = useActionFeedback();
  const [readiness, setReadiness] = useState<ProviderReadiness | null>(null);
  const [providerRoutes, setProviderRoutes] = useState<ProviderRouteStatus[]>([]);
  const [credentialPortfolio, setCredentialPortfolio] = useState<ProviderCredentialPortfolio | null>(null);
  const [credentialOperations, setCredentialOperations] = useState<ProviderCredentialOperationList | null>(null);
  const [credentialLoadError, setCredentialLoadError] = useState<string | null>(null);
  const [credentialOperationLoadError, setCredentialOperationLoadError] = useState<string | null>(null);
  const [credentialDrafts, setCredentialDrafts] = useState<Record<string, ProviderCredentialDraft>>({});
  const [updatingCredential, setUpdatingCredential] = useState<string | null>(null);
  const [routeLoadError, setRouteLoadError] = useState<string | null>(null);
  const [updatingRoute, setUpdatingRoute] = useState<string | null>(null);
  const [routeDrafts, setRouteDrafts] = useState<Record<string, { enabled: boolean; priority: string; reason: string }>>({});
  const [providerMigrations, setProviderMigrations] = useState<ProviderModelMigration[]>([]);
  const [migrationLoadError, setMigrationLoadError] = useState<string | null>(null);
  const [updatingMigration, setUpdatingMigration] = useState<string | null>(null);
  const [migrationAuditDrafts, setMigrationAuditDrafts] = useState<Record<string, string>>({});
  const [usageLedger, setUsageLedger] = useState<ProviderUsageLedger | null>(null);
  const [usageCostFilter, setUsageCostFilter] = useState<ProviderUsagePrecision | "all">("all");
  const [usageLedgerError, setUsageLedgerError] = useState<string | null>(null);
  const [providerPrices, setProviderPrices] = useState<ProviderPriceVersion[]>([]);
  const [providerPriceError, setProviderPriceError] = useState<string | null>(null);
  const [creatingPrice, setCreatingPrice] = useState(false);
  const [priceDraft, setPriceDraft] = useState<ProviderPriceDraft>({
    routeKey: "",
    currency: "CNY",
    inputPrice: "",
    outputPrice: "",
    effectiveFrom: new Date().toISOString().slice(0, 16),
    sourceKind: "official_price_page",
    sourceReference: "",
    reason: "",
  });

  const loadProviderRoutes = useCallback(async (signal?: AbortSignal) => {
    try {
      const routes = await fetchProviderRoutes(signal);
      setProviderRoutes(routes);
      setRouteLoadError(null);
      setRouteDrafts((current) => {
        const next = { ...current };
        routes.forEach((route) => {
          const key = `${route.provider}/${route.route_id}`;
          next[key] = {
            enabled: route.enabled,
            priority: route.priority_override == null ? "" : String(route.priority_override),
            reason: "",
          };
        });
        return next;
      });
    } catch (error) {
      if (signal?.aborted) return;
      setProviderRoutes([]);
      setRouteLoadError(error instanceof Error ? error.message : "Provider 路由控制接口不可用");
    }
  }, []);

  const loadProviderCredentials = useCallback(async (signal?: AbortSignal) => {
    try {
      const portfolio = await fetchProviderCredentials(signal);
      setCredentialPortfolio(portfolio);
      setCredentialLoadError(null);
      setCredentialDrafts((current) => {
        const next = { ...current };
        portfolio.credentials.forEach((credential) => {
          const key = `${credential.provider}/${credential.route_id}`;
          if (!next[key]) next[key] = emptyProviderCredentialDraft();
        });
        return next;
      });
    } catch (error) {
      if (signal?.aborted) return;
      setCredentialPortfolio(null);
      setCredentialLoadError(error instanceof Error ? error.message : "Provider 凭证接口不可用");
    }
  }, []);

  const loadProviderMigrations = useCallback(async (signal?: AbortSignal) => {
    try {
      setProviderMigrations(await fetchProviderModelMigrations(signal));
      setMigrationLoadError(null);
    } catch (error) {
      if (signal?.aborted) return;
      setProviderMigrations([]);
      setMigrationLoadError(error instanceof Error ? error.message : "Provider 模型迁移接口不可用");
    }
  }, []);

  const loadProviderCredentialOperations = useCallback(async (signal?: AbortSignal) => {
    try {
      const operations = await fetchProviderCredentialOperations(signal);
      setCredentialOperations(operations);
      setCredentialOperationLoadError(null);
    } catch (error) {
      if (signal?.aborted) return;
      setCredentialOperations(null);
      setCredentialOperationLoadError(error instanceof Error ? error.message : "Provider 凭证操作对账接口不可用");
    }
  }, []);

  const loadProviderUsage = useCallback(async (costPrecision?: ProviderUsagePrecision, signal?: AbortSignal) => {
    try {
      setUsageLedger(await fetchProviderUsageLedger(costPrecision, signal));
      setUsageLedgerError(null);
    } catch (error) {
      if (signal?.aborted) return;
      setUsageLedger(null);
      setUsageLedgerError(error instanceof Error ? error.message : "Provider 用量账本不可用");
    }
  }, []);

  const loadProviderPrices = useCallback(async (signal?: AbortSignal) => {
    try {
      setProviderPrices(await fetchProviderPrices(signal));
      setProviderPriceError(null);
    } catch (error) {
      if (signal?.aborted) return;
      setProviderPrices([]);
      setProviderPriceError(error instanceof Error ? error.message : "Provider 价格目录不可用");
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    fetchProviderReadiness(controller.signal).then(setReadiness).catch(() => setReadiness(null));
    void loadProviderRoutes(controller.signal);
    void loadProviderMigrations(controller.signal);
    void loadProviderCredentials(controller.signal);
    void loadProviderCredentialOperations(controller.signal);
    void loadProviderUsage(undefined, controller.signal);
    void loadProviderPrices(controller.signal);
    return () => controller.abort();
  }, [loadProviderCredentialOperations, loadProviderCredentials, loadProviderMigrations, loadProviderPrices, loadProviderRoutes, loadProviderUsage]);

  useEffect(() => {
    if (priceDraft.routeKey || providerRoutes.length === 0) return;
    const route = providerRoutes[0];
    setPriceDraft((current) => ({
      ...current,
      routeKey: `${route.provider}/${route.route_id}`,
    }));
  }, [priceDraft.routeKey, providerRoutes]);

  const applyUsageCostFilter = async (value: ProviderUsagePrecision | "all") => {
    setUsageCostFilter(value);
    await loadProviderUsage(value === "all" ? undefined : value);
  };

  const createProviderPrice = async () => {
    const route = providerRoutes.find((item) => `${item.provider}/${item.route_id}` === priceDraft.routeKey);
    if (!route) {
      notify({ title: "请选择 Provider 路由", desc: "价格版本必须绑定当前运行时路由和模型。", tone: "warning" });
      return;
    }
    if (!/^\d+(\.\d+)?$/.test(priceDraft.inputPrice) || !/^\d+(\.\d+)?$/.test(priceDraft.outputPrice)) {
      notify({ title: "价格格式无效", desc: "输入、输出价格必须是每百万 Token 的非负十进制金额。", tone: "warning" });
      return;
    }
    if (priceDraft.sourceReference.trim().length < 3 || priceDraft.reason.trim().length < 3) {
      notify({ title: "缺少价格证据", desc: "请填写来源引用和变更理由；系统不会内置演示价格。", tone: "warning" });
      return;
    }
    const previousVersion = providerPrices
      .filter((price) => price.provider === route.provider && price.route_id === route.route_id && price.model === route.model)
      .reduce((max, price) => Math.max(max, price.catalog_version), 0);
    setCreatingPrice(true);
    try {
      const result = await createProviderPriceVersion({
        provider: route.provider as "doubao" | "qianwen" | "kimi" | "deepseek",
        routeId: route.route_id,
        model: route.model,
        currency: priceDraft.currency.toUpperCase(),
        inputPricePerMillion: priceDraft.inputPrice,
        outputPricePerMillion: priceDraft.outputPrice,
        effectiveFrom: new Date(priceDraft.effectiveFrom).toISOString(),
        sourceKind: priceDraft.sourceKind,
        sourceReference: priceDraft.sourceReference.trim(),
        expectedPreviousVersion: previousVersion,
        reason: priceDraft.reason.trim(),
      });
      await Promise.all([loadProviderPrices(), loadProviderUsage(usageCostFilter === "all" ? undefined : usageCostFilter), loadProviderRoutes()]);
      setPriceDraft((current) => ({ ...current, inputPrice: "", outputPrice: "", sourceReference: "", reason: "" }));
      notify({ title: "价格版本已追加", desc: `v${result.catalog_version} 已记录，并回算 ${result.backfilled_usage_count ?? 0} 条历史用量；目录计算固定标记 estimated。`, tone: "success" });
    } catch (error) {
      notify({ title: "价格版本创建失败", desc: error instanceof Error ? error.message : "请刷新版本后重试。", tone: "danger" });
    } finally {
      setCreatingPrice(false);
    }
  };

  const applyProviderRoute = async (route: ProviderRouteStatus) => {
    const key = `${route.provider}/${route.route_id}`;
    const draft = routeDrafts[key] ?? { enabled: route.enabled, priority: "", reason: "" };
    const reason = draft.reason.trim();
    if (reason.length < 3) {
      notify({ title: "需要变更理由", desc: "请填写至少 3 个字符，理由会进入不可变审计事件。", tone: "warning" });
      return;
    }
    const priorityOverride = draft.priority.trim() === "" ? null : Number(draft.priority);
    if (priorityOverride !== null && (!Number.isInteger(priorityOverride) || priorityOverride < -10000 || priorityOverride > 10000)) {
      notify({ title: "优先级无效", desc: "请输入 -10000 到 10000 之间的整数，留空则使用环境配置优先级。", tone: "warning" });
      return;
    }
    setUpdatingRoute(key);
    try {
      await updateProviderRoute(route, {
        enabled: draft.enabled,
        priorityOverride,
        expectedVersion: route.control_version,
        reason,
      });
      await loadProviderRoutes();
      notify({ title: "路由控制已生效", desc: `${route.label} · ${route.route_id} 已热更新并记录审计事件。`, tone: "success" });
    } catch (error) {
      notify({ title: "路由控制更新失败", desc: error instanceof Error ? error.message : "请刷新状态后重试。", tone: "danger" });
    } finally {
      setUpdatingRoute(null);
    }
  };

  const migrationForRoute = (route: ProviderRouteStatus) => providerMigrations.find((item) => (
    item.provider === route.provider
    && item.route_id === route.route_id
    && item.from_model === route.model
    && item.from_configuration_fingerprint === route.configuration_fingerprint
  ));

  const runProviderMigrationAction = async (
    route: ProviderRouteStatus,
    action: "create" | "validate" | "approve",
  ) => {
    const key = `${route.provider}/${route.route_id}`;
    const reason = (routeDrafts[key]?.reason ?? "").trim();
    if (reason.length < 3) {
      notify({ title: "需要迁移理由", desc: "理由至少 3 个字符，并会进入不可变迁移事件。", tone: "warning" });
      return;
    }
    const migration = migrationForRoute(route);
    if (action !== "create" && !migration) {
      notify({ title: "迁移计划不存在", desc: "请先刷新或创建迁移计划。", tone: "warning" });
      return;
    }
    const requestAuditId = (migrationAuditDrafts[key] ?? "").trim();
    if (action === "validate" && !requestAuditId) {
      notify({ title: "缺少真实 L3 审计", desc: "请粘贴目标模型成功请求的 request_audit_id；失败调用不能审批。", tone: "warning" });
      return;
    }
    setUpdatingMigration(key);
    try {
      if (action === "create") await createProviderModelMigration(route, reason);
      if (action === "validate" && migration) await validateProviderModelMigration(migration, requestAuditId, reason);
      if (action === "approve" && migration) await approveProviderModelMigration(migration, reason);
      await Promise.all([loadProviderMigrations(), loadProviderRoutes()]);
      notify({
        title: action === "create" ? "迁移计划已建立" : action === "validate" ? "目标模型证据已验证" : "迁移计划已批准",
        desc: action === "approve" ? "发布门禁将重新按生命周期窗口计算；执行窗口内仍必须切换模型。" : "状态和哈希事件已更新。",
        tone: "success",
      });
    } catch (error) {
      notify({ title: "模型迁移操作失败", desc: error instanceof Error ? error.message : "请刷新状态后重试。", tone: "danger" });
    } finally {
      setUpdatingMigration(null);
    }
  };

  const saveProviderCredential = async (credential: ProviderCredentialStatus) => {
    const key = `${credential.provider}/${credential.route_id}`;
    const draft = credentialDrafts[key] ?? emptyProviderCredentialDraft();
    const secret = draft.secret.trim();
    const reason = draft.reason.trim();
    if (secret.length < 8 || /\s/.test(secret)) {
      notify({ title: "凭证格式无效", desc: "请输入至少 8 个字符且不含空白的 Provider 凭证。", tone: "warning" });
      return;
    }
    if (reason.length < 3) {
      notify({ title: "需要变更理由", desc: "理由会写入不可变凭证事件，至少填写 3 个字符。", tone: "warning" });
      return;
    }
    if (!draft.confirmBillable) {
      notify({ title: "需要确认真实验证", desc: "保存前会发起一次可能计费的 L3 真实生成请求。", tone: "warning" });
      return;
    }
    setUpdatingCredential(key);
    try {
      const updated = await upsertProviderCredential(credential, {
        secret,
        reason,
        confirmBillable: true,
      });
      setCredentialDrafts((current) => ({ ...current, [key]: emptyProviderCredentialDraft() }));
      await Promise.all([loadProviderCredentials(), loadProviderCredentialOperations()]);
      notify({
        title: "凭证已验证并激活",
        desc: `${updated.label} · ${updated.route_id} 已通过 L3 验证并以 v${updated.credential_version} 加密保存。操作回执：${updated.operation_id ?? "未返回"}。`,
        tone: "success",
      });
    } catch (error) {
      notify({ title: "凭证更新失败", desc: error instanceof Error ? error.message : "请刷新版本后重试。", tone: "danger" });
    } finally {
      setUpdatingCredential(null);
    }
  };

  const revokeCredential = async (credential: ProviderCredentialStatus) => {
    const key = `${credential.provider}/${credential.route_id}`;
    const draft = credentialDrafts[key] ?? emptyProviderCredentialDraft();
    const reason = draft.reason.trim();
    if (reason.length < 3) {
      notify({ title: "需要撤销理由", desc: "请填写至少 3 个字符，撤销会写入不可变审计事件。", tone: "warning" });
      return;
    }
    if (!draft.confirmRevoke) {
      notify({ title: "需要确认撤销", desc: "撤销会擦除密文并立即阻断该租户路由，且不会回退环境凭证。", tone: "warning" });
      return;
    }
    setUpdatingCredential(key);
    try {
      const updated = await revokeProviderCredential(credential, reason);
      setCredentialDrafts((current) => ({ ...current, [key]: emptyProviderCredentialDraft() }));
      await Promise.all([loadProviderCredentials(), loadProviderCredentialOperations()]);
      notify({ title: "凭证已撤销", desc: `${credential.label} · ${credential.route_id} 的密文已擦除并停止使用。操作回执：${updated.operation_id ?? "未返回"}。`, tone: "success" });
    } catch (error) {
      notify({ title: "凭证撤销失败", desc: error instanceof Error ? error.message : "请刷新版本后重试。", tone: "danger" });
    } finally {
      setUpdatingCredential(null);
    }
  };

  const showCredentialOperation = async (operation: ProviderCredentialOperation) => {
    try {
      const detail = await fetchProviderCredentialOperation(operation.operation_id);
      openPanel({
        title: `凭证操作对账 · ${detail.state}`,
        desc: detail.reconciliation_required
          ? "外部副作用可能已开始但没有可信终态。请刷新当前凭证状态、核对请求审计后再使用新幂等键，系统不会自动重试。"
          : "该回执只展示服务端持久操作状态和哈希链，不包含凭证明文或原始幂等键。",
        items: [
          `操作回执：${detail.operation_id}`,
          `动作：${detail.operation_type}`,
          `路由：${detail.provider} / ${detail.route_id}`,
          `请求 SHA-256：${detail.request_sha256}`,
          `重放状态：${detail.replay_status}`,
          `结果凭证：${detail.response_credential_id ?? "无"}${detail.response_credential_version == null ? "" : ` / v${detail.response_credential_version}`}`,
          ...detail.events.map((event) => `#${event.event_sequence} ${event.event_type} · ${event.to_state} · ${event.event_sha256}`),
        ],
      });
    } catch (error) {
      notify({ title: "操作回执读取失败", desc: error instanceof Error ? error.message : "请稍后重试。", tone: "danger" });
    }
  };

  return (
    <>
      <PageHeader
        title="设置中心"
        subtitle="展示真实项目与 Provider 状态；租户凭证先通过 L3 真实生成验证，再加密入库、版本化轮换并记录哈希链事件。"
        action={<Badge tone="primary">audited control</Badge>}
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
      <section className="airank-console-card provider-credential-vault" data-testid="provider-credential-vault">
        <div className="provider-route-control-head">
          <div>
            <h2>Provider 凭证保险库</h2>
            <p>页面永不回显明文。租户凭证覆盖对应运行时路由；撤销后立即擦除密文并对该路由失败关闭。</p>
          </div>
          <Badge tone={credentialPortfolio?.keyring_status === "ready" ? "success" : "danger"}>
            keyring {credentialPortfolio?.keyring_status ?? "unavailable"}
          </Badge>
        </div>
        {credentialLoadError && <DataStateCard title="凭证保险库不可用" desc={credentialLoadError} tone="danger" />}
        {!credentialLoadError && credentialPortfolio?.keyring_status === "blocked" && (
          <DataStateCard
            title="主密钥环未配置"
            desc="当前只能识别环境变量中的 legacy 凭证，不能在页面保存。请由部署密钥管理器注入独立的 AES-GCM 与 HMAC 32 字节密钥。"
            tone="danger"
          />
        )}
        {!credentialLoadError && credentialPortfolio && credentialPortfolio.credentials.length === 0 && (
          <DataStateCard title="没有 Provider 路由" desc="系统不会生成演示凭证或伪造验证状态。" tone="warning" />
        )}
        {credentialPortfolio && credentialPortfolio.credentials.length > 0 && (
          <div className="provider-credential-grid">
            {credentialPortfolio.credentials.map((credential) => {
              const key = `${credential.provider}/${credential.route_id}`;
              const draft = credentialDrafts[key] ?? emptyProviderCredentialDraft();
              const isVaultActive = credential.source === "vault_active" && credential.status === "active";
              const keyringReady = credentialPortfolio.keyring_status === "ready";
              const busy = updatingCredential === key;
              const statusTone: Tone = credential.status === "active" ? "success" : credential.status === "revoked" || credential.status === "blocked" ? "danger" : "warning";
              return (
                <article className="provider-credential-card" key={key}>
                  <header>
                    <div>
                      <strong>{credential.label}</strong>
                      <small>{credential.route_id}</small>
                    </div>
                    <Badge tone={statusTone}>{credential.source}</Badge>
                  </header>
                  <dl className="provider-credential-meta">
                    <div><dt>版本 / 掩码</dt><dd>v{credential.credential_version} · {credential.secret_mask ?? "无"}</dd></div>
                    <div><dt>加密</dt><dd>{credential.algorithm ?? "未入库"} · {credential.encryption_key_id ?? "无 key id"}</dd></div>
                    <div><dt>指纹</dt><dd>{credential.fingerprint_prefix ? `${credential.fingerprint_prefix}…` : "无"}</dd></div>
                    <div><dt>激活时间</dt><dd>{formatDateTime(credential.activated_at)}</dd></div>
                  </dl>
                  {credential.verification ? (
                    <div className="provider-credential-verification">
                      <Badge tone="success">L3 verified</Badge>
                      <span>{credential.verification.model} · {credential.verification.endpoint_host}</span>
                      <small>{credential.verification.duration_ms} ms · {credential.verification.evidence_grade} · request-id {credential.verification.request_id_present ? "present" : "missing"}</small>
                    </div>
                  ) : (
                    <div className="provider-credential-verification is-unverified">
                      <Badge tone="warning">未做租户 L3 验证</Badge>
                      <small>环境变量可用不等于已进入租户保险库。</small>
                    </div>
                  )}
                  {credential.known_limitations.length > 0 && (
                    <small className="provider-credential-limitations">限制：{credential.known_limitations.join("；")}</small>
                  )}
                  <div className="provider-credential-form">
                    <label>
                      <span>{isVaultActive ? "新凭证（轮换）" : "新凭证"}</span>
                      <input
                        type="password"
                        autoComplete="new-password"
                        value={draft.secret}
                        disabled={!keyringReady || busy}
                        placeholder="仅在本次提交的内存中暂存"
                        onChange={(event) => setCredentialDrafts((current) => ({ ...current, [key]: { ...(current[key] ?? draft), secret: event.target.value } }))}
                      />
                    </label>
                    <label>
                      <span>变更 / 撤销理由</span>
                      <input
                        value={draft.reason}
                        maxLength={500}
                        disabled={!keyringReady || busy}
                        placeholder="必填，进入审计事件"
                        onChange={(event) => setCredentialDrafts((current) => ({ ...current, [key]: { ...(current[key] ?? draft), reason: event.target.value } }))}
                      />
                    </label>
                    <label className="provider-credential-check">
                      <input
                        type="checkbox"
                        checked={draft.confirmBillable}
                        disabled={!keyringReady || busy}
                        onChange={(event) => setCredentialDrafts((current) => ({ ...current, [key]: { ...(current[key] ?? draft), confirmBillable: event.target.checked } }))}
                      />
                      <span>确认保存前执行一次可能计费的 L3 真实生成</span>
                    </label>
                    {isVaultActive && (
                      <label className="provider-credential-check is-danger">
                        <input
                          type="checkbox"
                          checked={draft.confirmRevoke}
                          disabled={busy}
                          onChange={(event) => setCredentialDrafts((current) => ({ ...current, [key]: { ...(current[key] ?? draft), confirmRevoke: event.target.checked } }))}
                        />
                        <span>确认撤销后立即中断该租户路由</span>
                      </label>
                    )}
                    <div className="provider-credential-actions">
                      <button className="primary-button" type="button" disabled={!keyringReady || busy} onClick={() => void saveProviderCredential(credential)}>
                        {busy ? "处理中…" : isVaultActive ? "验证并轮换" : "验证并激活"}
                      </button>
                      {isVaultActive && (
                        <button className="outline-button danger-outline" type="button" disabled={busy} onClick={() => void revokeCredential(credential)}>
                          撤销并擦除
                        </button>
                      )}
                    </div>
                  </div>
                </article>
              );
            })}
          </div>
        )}
        <div className="provider-credential-operations" data-testid="provider-credential-operations">
          <div className="provider-route-control-head">
            <div>
              <h3>凭证操作对账</h3>
              <p>只读展示持久操作回执与状态链。未知结果必须人工核对，系统不会自动重复 L3 或密钥写入。</p>
            </div>
            <Badge tone={(credentialOperations?.reconciliation_required_count ?? 0) > 0 ? "danger" : "success"}>
              待对账 {credentialOperations?.reconciliation_required_count ?? 0}
            </Badge>
          </div>
          {credentialOperationLoadError && <DataStateCard title="操作对账不可用" desc={credentialOperationLoadError} tone="danger" />}
          {!credentialOperationLoadError && credentialOperations?.operations.length === 0 && (
            <DataStateCard title="暂无凭证操作回执" desc="系统不会生成演示操作记录。完成真实激活、轮换或撤销后才会出现。" tone="warning" />
          )}
          {(credentialOperations?.reconciliation_required_count ?? 0) > 0 && (
            <DataStateCard title="存在结果未知操作" desc="先刷新凭证当前状态并下钻事件链；核对 Provider 请求审计后，才可使用新的幂等键发起明确操作。" tone="danger" />
          )}
          {credentialOperations && credentialOperations.operations.length > 0 && (
            <div className="table-shell">
              <table>
                <thead>
                  <tr><th>操作 / 路由</th><th>状态</th><th>安全结果</th><th>时间</th><th>证据</th></tr>
                </thead>
                <tbody>
                  {credentialOperations.operations.map((operation) => {
                    const tone: Tone = operation.reconciliation_required || operation.state === "failed" ? "danger" : operation.state === "succeeded" ? "success" : "warning";
                    return (
                      <tr key={operation.operation_id}>
                        <td><strong>{operation.operation_type.endsWith("upsert") ? "激活 / 轮换" : "撤销"}</strong><small>{operation.provider} · {operation.route_id}</small></td>
                        <td><Badge tone={tone}>{operation.state}</Badge><small>{operation.replay_status}</small></td>
                        <td><span>{operation.response_credential_id ?? "无终态凭证"}</span><small>{operation.response_credential_version == null ? operation.error_code ?? "等待终态" : `v${operation.response_credential_version} · ${operation.response_status}`}</small></td>
                        <td><span>{formatDateTime(operation.created_at)}</span><small>{operation.created_by}</small></td>
                        <td><button className="outline-button" type="button" onClick={() => void showCredentialOperation(operation)}>下钻事件链</button></td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </section>
      <section className="airank-console-card provider-route-control" data-testid="provider-usage-ledger">
        <div className="provider-route-control-head">
          <div>
            <h2>Provider 用量与成本账本</h2>
            <p>Token 是不可变原始事件；价格回算是独立派生证据。已知成本不等于总成本，覆盖不足时汇总精度保持 unknown。</p>
          </div>
          <label>
            成本精度
            <select
              value={usageCostFilter}
              onChange={(event) => void applyUsageCostFilter(event.target.value as ProviderUsagePrecision | "all")}
            >
              <option value="all">全部</option>
              <option value="exact">exact · Provider 账单</option>
              <option value="estimated">estimated · 目录计算</option>
              <option value="unknown">unknown · 未定价</option>
            </select>
          </label>
        </div>
        {usageLedgerError && <DataStateCard title="用量账本不可用" desc={usageLedgerError} tone="danger" />}
        {usageLedger && (
          <>
            <div className="settings-grid">
              <SettingsSection
                title="Token 证据"
                icon={Activity}
                onAction={() => openPanel({ title: "Token 精度口径", desc: "exact 仅来自 Provider 原生 usage；estimated 必须有估算来源；unknown 不得参与精确成本结论。", items: ["原始事件不可变", "失败调用有 usage 仍入账", "request id 仅展示是否存在"] })}
                rows={[
                  ["事件总数", String(usageLedger.summary.event_count)],
                  ["exact / estimated", `${usageLedger.summary.exact_usage_count} / ${usageLedger.summary.estimated_usage_count}`],
                  ["unknown", String(usageLedger.summary.unknown_usage_count)],
                ]}
              />
              <SettingsSection
                title="成本覆盖"
                icon={ShieldCheck}
                onAction={() => openPanel({ title: "成本精度口径", desc: "Provider 明示账单金额才可标 exact；价格目录乘 Token 的结果固定为 estimated。", items: ["已知金额不等于总金额", "未知事件使聚合精度保持 unknown", "不同币种不强行合并"] })}
                rows={[
                  ["覆盖率", `${(usageLedger.summary.cost_coverage_rate * 100).toFixed(1)}%`],
                  ["已知 / 未知事件", `${usageLedger.summary.known_cost_event_count} / ${usageLedger.summary.unknown_cost_count}`],
                  ["已知金额", usageLedger.summary.known_cost_amount == null ? "无可合并金额" : `${usageLedger.summary.known_cost_currency} ${usageLedger.summary.known_cost_amount}`],
                  ["聚合精度", usageLedger.summary.aggregate_cost_precision],
                ]}
              />
            </div>
            {usageLedger.events.length === 0 ? (
              <DataStateCard title="当前筛选没有用量事件" desc="系统不会补造 Token 或成本；完成真实 Provider 调用后才会入账。" tone="warning" />
            ) : (
              <div className="table-shell">
                <table>
                  <thead><tr><th>Provider / 请求</th><th>Token</th><th>成本</th><th>来源与版本</th><th>时间 / hash</th></tr></thead>
                  <tbody>
                    {usageLedger.events.map((event) => (
                      <tr key={event.usage_event_id}>
                        <td><strong>{event.provider} · {event.route_id || "未记录路由"}</strong><small>{event.model} · {event.outcome} · request id {event.provider_request_id_present ? "present" : "missing"}</small></td>
                        <td><Badge tone={event.usage_precision === "exact" ? "success" : event.usage_precision === "estimated" ? "warning" : "danger"}>{event.usage_precision}</Badge><small>in {event.input_tokens ?? "?"} / out {event.output_tokens ?? "?"} / total {event.total_tokens ?? "?"}</small></td>
                        <td><Badge tone={event.cost_precision === "exact" ? "success" : event.cost_precision === "estimated" ? "warning" : "danger"}>{event.cost_precision}</Badge><small>{event.cost_amount == null ? "未定价" : `${event.cost_currency} ${event.cost_amount}`}</small></td>
                        <td><span>{event.usage_source}</span><small>{event.cost_source} · {event.price_version_id ?? "无价格版本"}</small></td>
                        <td><span>{formatDateTime(event.occurred_at)}</span><small>raw {event.raw_usage_sha256.slice(0, 12)}…{event.calculation_sha256 ? ` · calc ${event.calculation_sha256.slice(0, 12)}…` : ""}</small></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}
      </section>
      <section className="airank-console-card provider-route-control" data-testid="provider-price-catalog">
        <div className="provider-route-control-head">
          <div>
            <h2>Provider 价格版本</h2>
            <p>只接受带来源和生效时间的追加版本，不内置可能过期的演示价格。按目录计算的成本永远是 estimated。</p>
          </div>
          <Badge tone={providerPriceError ? "danger" : "primary"}>{providerPriceError ? "blocked" : `${providerPrices.length} versions`}</Badge>
        </div>
        {providerPriceError && <DataStateCard title="价格目录不可用" desc={providerPriceError} tone="danger" />}
        <div className="provider-credential-form">
          <label>路由 / 模型<select value={priceDraft.routeKey} onChange={(event) => setPriceDraft((current) => ({ ...current, routeKey: event.target.value }))}>{providerRoutes.map((route) => <option key={`${route.provider}/${route.route_id}`} value={`${route.provider}/${route.route_id}`}>{route.label} · {route.route_id} · {route.model}</option>)}</select></label>
          <label>币种<input value={priceDraft.currency} maxLength={3} onChange={(event) => setPriceDraft((current) => ({ ...current, currency: event.target.value.toUpperCase() }))} /></label>
          <label>输入 / 百万 Token<input inputMode="decimal" value={priceDraft.inputPrice} placeholder="真实价格" onChange={(event) => setPriceDraft((current) => ({ ...current, inputPrice: event.target.value }))} /></label>
          <label>输出 / 百万 Token<input inputMode="decimal" value={priceDraft.outputPrice} placeholder="真实价格" onChange={(event) => setPriceDraft((current) => ({ ...current, outputPrice: event.target.value }))} /></label>
          <label>生效时间<input type="datetime-local" value={priceDraft.effectiveFrom} onChange={(event) => setPriceDraft((current) => ({ ...current, effectiveFrom: event.target.value }))} /></label>
          <label>来源类型<select value={priceDraft.sourceKind} onChange={(event) => setPriceDraft((current) => ({ ...current, sourceKind: event.target.value as ProviderPriceVersion["source_kind"] }))}><option value="official_price_page">官方价格页</option><option value="provider_invoice">Provider 账单</option><option value="customer_contract">客户合同</option><option value="manual_verified">人工核验</option></select></label>
          <label>来源引用<input value={priceDraft.sourceReference} maxLength={2048} placeholder="URL / 合同或账单证据编号" onChange={(event) => setPriceDraft((current) => ({ ...current, sourceReference: event.target.value }))} /></label>
          <label>变更理由<input value={priceDraft.reason} maxLength={500} placeholder="必填：为什么新增此版本" onChange={(event) => setPriceDraft((current) => ({ ...current, reason: event.target.value }))} /></label>
          <button className="primary-button" type="button" disabled={creatingPrice || providerRoutes.length === 0} onClick={() => void createProviderPrice()}>{creatingPrice ? "追加中…" : "追加价格版本并回算"}</button>
        </div>
        {providerPrices.length === 0 ? (
          <DataStateCard title="暂无价格版本" desc="真实 Token 仍会入账，但成本保持 unknown；补充有来源的价格后才能回算。" tone="warning" />
        ) : (
          <div className="table-shell">
            <table>
              <thead><tr><th>Provider / 版本</th><th>价格</th><th>生效时间</th><th>来源</th><th>审计</th></tr></thead>
              <tbody>{providerPrices.map((price) => <tr key={price.price_version_id}><td><strong>{price.provider} · {price.route_id}</strong><small>{price.model} · v{price.catalog_version}</small></td><td><span>{price.currency} / 1M</span><small>in {price.input_price_per_million} · out {price.output_price_per_million}</small></td><td><span>{formatDateTime(price.effective_from)}</span><small>{price.effective_until ? `至 ${formatDateTime(price.effective_until)}` : "持续生效，后续版本优先"}</small></td><td><span>{price.source_kind}</span><small>{price.source_reference}</small></td><td><span>{price.created_by}</span><small>{price.source_sha256.slice(0, 12)}…</small></td></tr>)}</tbody>
            </table>
          </div>
        )}
      </section>
      <section className="airank-console-card provider-route-control" data-testid="provider-route-control">
        <div className="provider-route-control-head">
          <div>
            <h2>Provider 路由控制</h2>
            <p>显示运行时已配置路由和 24 小时真实调用指标。所有变更需理由和版本校验；服务端禁止停用最后一路。</p>
          </div>
          <Badge tone={routeLoadError ? "danger" : "success"}>{routeLoadError ? "blocked" : `${providerRoutes.length} routes`}</Badge>
        </div>
        {routeLoadError && <DataStateCard title="路由控制不可用" desc={routeLoadError} tone="danger" />}
        {migrationLoadError && <DataStateCard title="模型迁移治理不可用" desc={migrationLoadError} tone="danger" />}
        {!routeLoadError && providerRoutes.length === 0 && <DataStateCard title="没有运行时路由" desc="没有已配置凭证时不生成演示路由，也不允许在页面录入密钥。" tone="warning" />}
        {providerRoutes.length > 0 && (
          <div className="provider-route-table-wrap">
            <table className="question-table provider-route-table">
              <thead><tr><th>Provider / 路由</th><th>状态</th><th>模型生命周期</th><th>24h 实际调用</th><th>优先级</th><th>变更理由</th><th>操作</th></tr></thead>
              <tbody>
                {providerRoutes.map((route) => {
                  const key = `${route.provider}/${route.route_id}`;
                  const draft = routeDrafts[key] ?? { enabled: route.enabled, priority: route.priority_override == null ? "" : String(route.priority_override), reason: "" };
                  const successRate = route.success_rate_24h == null ? "无样本" : `${(route.success_rate_24h * 100).toFixed(1)}%`;
                  const migration = migrationForRoute(route);
                  return (
                    <tr key={key}>
                      <td>
                        <strong>{route.label} · {route.route_id}</strong>
                        <small>{route.model} · {route.endpoint_host} · {route.request_kind}</small>
                        <small>fp {route.configuration_fingerprint.slice(0, 12)}… · v{route.control_version}</small>
                      </td>
                      <td>
                        <label className="provider-route-toggle">
                          <input
                            type="checkbox"
                            checked={draft.enabled}
                            disabled={!route.configured}
                            onChange={(event) => setRouteDrafts((current) => ({ ...current, [key]: { ...(current[key] ?? draft), enabled: event.target.checked } }))}
                          />
                          <Badge tone={!route.configured ? "warning" : draft.enabled ? "success" : "danger"}>{!route.configured ? "not configured" : draft.enabled ? "enabled" : "disabled"}</Badge>
                        </label>
                      </td>
                      <td>
                        <Badge tone={route.release_gate_status === "blocked" ? "danger" : route.lifecycle_status === "unmanaged" ? "warning" : "success"}>{route.lifecycle_status}</Badge>
                        <small>{route.sunset_at ? `${formatDateTime(route.sunset_at)} · 剩余 ${route.days_to_sunset} 天` : "manifest 未登记下架日期"}</small>
                        <small>{route.replacement_model ? `替代：${route.replacement_model}` : route.lifecycle_reason}</small>
                        <small>执行门禁 {route.execution_gate_status} · 发布门禁 {route.release_gate_status}</small>
                        <small>{migration ? `迁移 ${migration.status} · v${migration.plan_version}` : route.replacement_model ? "尚未建立迁移计划" : "无需创建迁移计划"}</small>
                        {migration && <small>事件链 {migration.event_chain_status} · L3 证据 {migration.validation_evidence_status} · 发布资格 {migration.release_eligible ? "valid" : "blocked"}</small>}
                      </td>
                      <td><strong>{route.request_count_24h} 次 · {successRate}</strong><small>{route.average_duration_ms_24h == null ? "无延迟样本" : `均值 ${route.average_duration_ms_24h} ms`} · {route.total_tokens_24h ?? "无 token"}</small><small>用量 exact/estimated/unknown：{route.exact_usage_count_24h}/{route.estimated_usage_count_24h}/{route.unknown_usage_count_24h}</small><small>成本覆盖 {(route.cost_coverage_rate_24h * 100).toFixed(1)}% · {route.known_cost_amount_24h == null ? "无已知金额" : `${route.known_cost_currency} ${route.known_cost_amount_24h}`} · {route.aggregate_cost_precision_24h}</small></td>
                      <td>
                        <input
                          className="provider-route-priority"
                          type="number"
                          min={-10000}
                          max={10000}
                          step={1}
                          value={draft.priority}
                          disabled={!route.configured}
                          placeholder={`默认 ${route.base_priority}`}
                          onChange={(event) => setRouteDrafts((current) => ({ ...current, [key]: { ...(current[key] ?? draft), priority: event.target.value } }))}
                          aria-label={`${route.route_id} 优先级`}
                        />
                        <small>生效 {route.effective_priority}</small>
                      </td>
                      <td>
                        <input
                          className="provider-route-reason"
                          value={draft.reason}
                          maxLength={500}
                          disabled={!route.configured}
                          placeholder="必填：本次变更原因"
                          onChange={(event) => setRouteDrafts((current) => ({ ...current, [key]: { ...(current[key] ?? draft), reason: event.target.value } }))}
                          aria-label={`${route.route_id} 变更理由`}
                        />
                        <small>{route.reason ? `上次：${route.reason}` : "尚无人工控制记录"}</small>
                      </td>
                      <td>
                        <button className="outline-button" type="button" disabled={!route.configured || updatingRoute === key} onClick={() => void applyProviderRoute(route)}>{updatingRoute === key ? "保存中…" : "应用路由"}</button>
                        {route.replacement_model && !migration && <button className="outline-button" type="button" disabled={updatingMigration === key} onClick={() => void runProviderMigrationAction(route, "create")}>{updatingMigration === key ? "处理中…" : "建立迁移计划"}</button>}
                        {migration && ["planned", "validation_failed"].includes(migration.status) && (
                          <>
                            <input
                              className="provider-route-reason"
                              value={migrationAuditDrafts[key] ?? ""}
                              placeholder="目标模型成功 request_audit_id"
                              onChange={(event) => setMigrationAuditDrafts((current) => ({ ...current, [key]: event.target.value }))}
                              aria-label={`${route.route_id} 目标模型验证审计 ID`}
                            />
                            <button className="outline-button" type="button" disabled={updatingMigration === key} onClick={() => void runProviderMigrationAction(route, "validate")}>{updatingMigration === key ? "验证中…" : "绑定真实 L3"}</button>
                          </>
                        )}
                        {migration?.status === "validated" && <button className="outline-button" type="button" disabled={updatingMigration === key} onClick={() => void runProviderMigrationAction(route, "approve")}>{updatingMigration === key ? "审批中…" : "批准迁移"}</button>}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  );
}

function SkillConsolePage() {
  const [skills, setSkills] = useState<InternalSkill[]>([]);
  const [ledger, setLedger] = useState<SkillPromotionLedger | null>(null);
  const [trustReport, setTrustReport] = useState<SkillTrustReport | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    Promise.all([fetchInternalSkills(controller.signal), fetchSkillPromotionLedger(controller.signal), fetchSkillTrustReport(controller.signal)])
      .then(([nextSkills, nextLedger, nextTrustReport]) => {
        setSkills(nextSkills);
        setLedger(nextLedger);
        setTrustReport(nextTrustReport);
        setLoadError(null);
      })
      .catch((error) => {
        if (controller.signal.aborted) return;
        setSkills([]);
        setLedger(null);
        setTrustReport(null);
        setLoadError(error instanceof Error ? error.message : "Skill 控制台接口不可用");
      });
    return () => controller.abort();
  }, []);

  const locallyPassed = skills.filter((skill) => skill.evaluation.local_eval_status === "passed").length;
  const promotionEligible = skills.filter((skill) => skill.evaluation.promotion_eligible).length;
  const trustAllowed = skills.filter((skill) => skill.trust.execution_allowed).length;
  const retainedPartial = ledger?.skills.filter((item) => item.decision === "retain_partial").length ?? 0;

  return (
    <>
      <PageHeader
        title="内部 Skill 控制台"
        subtitle="展示版本化契约、独立评测、依赖/能力信任门禁和内容寻址晋级账本；仓库门禁通过不等于生产沙箱或外部证据齐备。"
        action={<Badge tone="warning">internal · read-only</Badge>}
      />
      <section className="summary-band evidence-summary">
        <SummaryMetric label="核心 Skill" value={String(skills.length)} tone="primary" />
        <SummaryMetric label="本地评测通过" value={String(locallyPassed)} tone={locallyPassed === skills.length && skills.length > 0 ? "success" : "warning"} />
        <SummaryMetric label="本地信任放行" value={String(trustAllowed)} tone={trustAllowed === skills.length && skills.length > 0 ? "success" : "danger"} />
        <SummaryMetric label="可晋级 ready" value={String(promotionEligible)} tone={promotionEligible > 0 ? "success" : "warning"} />
        <SummaryMetric label="保留 partial" value={String(retainedPartial)} tone="warning" />
      </section>
      {loadError && <DataStateCard title="Skill 状态读取失败" desc={loadError} tone="danger" />}
      {!loadError && skills.length === 0 && <DataStateCard title="尚无已注册 Skill" desc="系统不会用演示 Skill 或固定评测结果补位。" tone="warning" />}
      {skills.length > 0 && (
        <div className="airank-console-card table-card skill-table-wrap">
          <table className="question-table skill-table">
            <thead><tr><th>Skill / 版本</th><th>类别</th><th>Manifest</th><th>信任门禁</th><th>评测</th><th>套件</th><th>晋级</th><th>证据阻断</th></tr></thead>
            <tbody>
              {skills.map((skill) => (
                <tr key={skill.skill_id}>
                  <td><strong>{skill.skill_id}</strong><small>v{skill.version} · {skill.evaluation.evaluation_sha256.slice(0, 12)}…</small></td>
                  <td>{skill.category}</td>
                  <td><Badge tone={skill.status === "ready" ? "success" : "warning"}>{skill.status}</Badge></td>
                  <td><Badge tone={skill.trust.execution_allowed ? "success" : "danger"}>{skill.trust.execution_allowed ? "local allow" : "blocked"}</Badge><small>{skill.trust.policy_sha256.slice(0, 12)}…</small></td>
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
      {trustReport && (
        <Panel title="Skill Trust Gate">
          <dl className="evidence-metadata">
            <div><dt>门禁状态</dt><dd>{trustReport.status}</dd></div>
            <div><dt>隔离安装模拟</dt><dd>{trustReport.installation.status} · {trustReport.installation.skill_count}/{trustReport.summary.skill_count}</dd></div>
            <div><dt>声明边界</dt><dd>{trustReport.claim_level}</dd></div>
            <div><dt>原生运行时强制</dt><dd>{trustReport.native_runtime_enforcement ? "verified" : "未验证"}</dd></div>
            <div><dt>Package SHA-256</dt><dd>{trustReport.installation.package_manifest_sha256 ?? "未生成"}</dd></div>
            <div><dt>Report SHA-256</dt><dd>{trustReport.report_sha256}</dd></div>
          </dl>
          <p className="settings-note">当前只证明 AIRank 仓库内依赖、网络、secret、文件写入、子进程、权限声明和隔离导入门禁；不把它表述为 OS 级沙箱或生产 Worker 原生权限强制。</p>
        </Panel>
      )}
      {ledger && (
        <Panel title="Promotion Evidence Ledger">
          <dl className="evidence-metadata">
            <div><dt>Ledger 版本</dt><dd>{ledger.ledger_version}</dd></div>
            <div><dt>Registry SHA-256</dt><dd>{ledger.source_sha256.registry}</dd></div>
            <div><dt>Eval Corpus SHA-256</dt><dd>{ledger.source_sha256.eval_corpus}</dd></div>
            <div><dt>Implementation SHA-256</dt><dd>{ledger.source_sha256.implementation}</dd></div>
            <div><dt>Trust Report SHA-256</dt><dd>{ledger.trust_report_sha256}</dd></div>
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
