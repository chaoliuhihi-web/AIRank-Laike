import { createContext, useContext, useEffect, useState } from "react";
import type { ReactNode } from "react";
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  BadgeCheck,
  BarChart3,
  Bell,
  Bot,
  BriefcaseBusiness,
  Building2,
  CalendarDays,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  CircleUserRound,
  ClipboardList,
  ExternalLink,
  FileChartColumn,
  Globe2,
  HelpCircle,
  Home,
  Info,
  Link2,
  ListChecks,
  LockKeyhole,
  LucideIcon,
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
} from "lucide-react";
import { consoleRoutes } from "./console/routes/console-routes";
import {
  fallbackConsoleOverview,
  fallbackAssetBundle,
  fetchAssetBundle,
  fetchConsoleOverview,
  fallbackReportList,
  fetchReports,
  recordDownloadReceipt,
  type AssetBundle,
  type ConsoleMetricCard,
  type ConsoleOverview,
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
  LockKeyhole,
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

function useConsoleOverview() {
  return useContext(ConsoleOverviewContext);
}

function App() {
  const [path, setPath] = useState(() => normalizePath(window.location.pathname));
  const [overview, setOverview] = useState<ConsoleOverview>(fallbackConsoleOverview);

  useEffect(() => {
    const onPopState = () => setPath(normalizePath(window.location.pathname));
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    fetchConsoleOverview(controller.signal)
      .then(setOverview)
      .catch(() => setOverview(fallbackConsoleOverview));
    return () => controller.abort();
  }, []);

  const navigate = (nextPath: string) => {
    const normalized = normalizePath(nextPath);
    window.history.pushState({}, "", normalized);
    setPath(normalized);
  };

  return (
    <ConsoleOverviewContext.Provider value={overview}>
      <main className="airank-console">
        <div className="airank-console-shell">
          <Sidebar activePath={path} onNavigate={navigate} />
          <section className="airank-console-main">
            <ConsolePage path={path} onNavigate={navigate} />
          </section>
        </div>
      </main>
    </ConsoleOverviewContext.Provider>
  );
}

function normalizePath(path: string) {
  if (path === "/" || path === "/console/") {
    return "/console";
  }
  return path.replace(/\/$/, "");
}

function Sidebar({ activePath, onNavigate }: { activePath: string; onNavigate: (path: string) => void }) {
  const { project } = useConsoleOverview();

  return (
    <aside className="airank-console-sidebar">
      <div className="brand-lockup">
        <div className="brand-mark">
          <Sparkles size={25} />
        </div>
        <div>
          <div className="brand-title">智界问道</div>
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
        <button className="help-link" type="button">
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

function ConsolePage({ path, onNavigate }: { path: string; onNavigate: (path: string) => void }) {
  if (path === "/console/checkup") return <CheckupPage onNavigate={onNavigate} />;
  if (path === "/console/facts") return <FactsPage />;
  if (path === "/console/questions") return <QuestionsPage onNavigate={onNavigate} />;
  if (path === "/console/gaps/questions") return <GapQuestionsPage onNavigate={onNavigate} />;
  if (path === "/console/gaps") return <GapsPage onNavigate={onNavigate} />;
  if (path === "/console/assets") return <AssetsPage onNavigate={onNavigate} />;
  if (path === "/console/publishing") return <PublishingPage onNavigate={onNavigate} />;
  if (path === "/console/assistant") return <AssistantPage />;
  if (path === "/console/reports") return <ReportsPage />;
  if (path === "/console/settings") return <SettingsPage />;
  return <DashboardPage onNavigate={onNavigate} />;
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
    <article className="airank-console-card metric-card">
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

function DashboardPage({ onNavigate }: { onNavigate: (path: string) => void }) {
  const { metricCards } = useConsoleOverview();

  return (
    <>
      <PageHeader
        title="工作台"
        subtitle="老板驾驶舱：AI 当前更容易推荐竞品，而不是你。先补齐推荐证据，再启动发布复测。"
        action={<DatePill />}
      />
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

  return (
    <button className="date-pill" type="button">
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
      <section className="provider-grid">
        {providerResults.map((item) => (
          <article className="airank-console-card provider-card" key={item.name}>
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
  return (
    <>
      <PageHeader
        title="企业事实库"
        subtitle="AI 认识你的前提，是企业事实足够清晰、可信、可公开。"
        action={<button className="airank-console-primary-button" type="button">确认企业事实</button>}
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
        <button className="outline-button" type="button">查看使用指南</button>
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
        action={<button className="airank-console-primary-button" type="button" onClick={() => onNavigate("/console/gaps")}>生成推荐缺口分析</button>}
      />
      <ProjectStrip />
      <QuestionTable showTabs />
    </>
  );
}

function GapQuestionsPage({ onNavigate }: { onNavigate: (path: string) => void }) {
  return (
    <>
      <PageHeader
        title="推荐缺口分析"
        subtitle="按问题维度识别 AI 为什么推荐竞品，以及需要补齐哪些资产。"
        action={<button className="airank-console-primary-button" type="button" onClick={() => onNavigate("/console/assets")}>生成 AI 收录包</button>}
      />
      <ProjectStrip />
      <QuestionTable showTabs={false} />
    </>
  );
}

function QuestionTable({ showTabs }: { showTabs: boolean }) {
  return (
    <section className="content-with-rail">
      <div>
        {showTabs && (
          <div className="tab-row">
            {["全部问题", "品牌认知", "选型决策", "竞品对比", "价格成交", "本地行业"].map((item, index) => (
              <button className="tab-button" data-active={index === 0} type="button" key={item}>{item}</button>
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
              {questionRows.map((row) => (
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
            <span>共 128 条问题</span>
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
          <button className="ghost-button" type="button">查看完整 Top50 问题</button>
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
        subtitle="把可信事实卡转换成 AI 可理解、可引用、可抓取的内容资产。"
        action={<button className="airank-console-primary-button" type="button" onClick={() => onNavigate("/console/publishing")}>发布并复测</button>}
      />
      <ProjectStrip />
      <section className="asset-grid">
        {bundle.assets.map((item, index) => (
          <article className="airank-console-card asset-card" key={item.title}>
            <div className="asset-card-head">
              <IconTile tone={index % 3 === 0 ? "primary" : index % 3 === 1 ? "success" : "warning"}>
                {index > 5 ? <Link2 size={23} /> : <FileChartColumn size={23} />}
              </IconTile>
              <Badge tone={item.status.includes("缺") ? "danger" : item.status.includes("待") ? "warning" : "success"}>{item.status}</Badge>
            </div>
            <h3>{item.title}</h3>
            <p>{item.desc}</p>
            <ProgressBar value={item.progress} />
            <div className="asset-footer">
              <span>完整度 {item.progress}%</span>
              <button type="button">编辑<ChevronRight size={16} /></button>
            </div>
          </article>
        ))}
      </section>
      <div className="package-footer">
        <div>
          <strong>AI 收录包完整度</strong>
          <span>{bundle.recommendation}</span>
        </div>
        <ProgressBar value={bundle.completeness} />
        <button className="airank-console-primary-button" type="button" onClick={() => onNavigate("/console/publishing")}>
          去发布
        </button>
      </div>
    </>
  );
}

function PublishingPage({ onNavigate }: { onNavigate: (path: string) => void }) {
  return (
    <>
      <PageHeader title="发布提交中心" subtitle="把 AI 收录包发布到官网、AI 获客页和搜索入口，并加入复测队列。" action={<button className="airank-console-primary-button" type="button" onClick={() => onNavigate("/console/reports")}>生成复测报告</button>} />
      <ProcessSteps
        steps={[
          ["发布内容", "生成页面与结构化资产"],
          ["提交抓取", "提交 Google / Bing / Baidu"],
          ["索引观察", "追踪收录与抓取状态"],
          ["加入复测", "复测 AI 推荐效果"],
        ]}
      />
      <section className="metric-grid publishing-stats">
        <MiniStat label="已发布页面" value="18" icon={Rocket} />
        <MiniStat label="已抓取页面" value="14" icon={SearchCheck} />
        <MiniStat label="已收录页面" value="9" icon={BadgeCheck} />
        <MiniStat label="待复测任务" value="6" icon={RotateCw} />
      </section>
      <Panel title="页面发布与抓取状态">
        <table className="question-table publish-table">
          <thead>
            <tr><th>页面</th><th>发布渠道</th><th>抓取状态</th><th>索引状态</th><th>最近提交</th><th>操作</th></tr>
          </thead>
          <tbody>
            {publishingRows.map((row) => (
              <tr key={row.page}>
                <td><strong>{row.page}</strong></td>
                <td>{row.channel}</td>
                <td><Badge tone={row.crawl === "失败" ? "danger" : row.crawl === "排队中" ? "warning" : "success"}>{row.crawl}</Badge></td>
                <td><Badge tone={row.index === "已收录" ? "success" : row.index === "待收录" ? "warning" : "muted"}>{row.index}</Badge></td>
                <td>{row.time}</td>
                <td><button className="table-action" type="button">查看</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>
    </>
  );
}

function AssistantPage() {
  return (
    <>
      <PageHeader title="AI 来客助手" subtitle="基于已确认可信事实卡、AI 收录包和买家问题地图承接访客咨询。" action={<Badge tone="primary">P2 能力预览</Badge>} />
      <section className="assistant-grid">
        <Panel title="对话预览">
          <div className="chat-window">
            {assistantMessages.map((msg, index) => (
              <div className={`chat-bubble ${msg.role}`} key={`${msg.role}-${index}`}>{msg.text}</div>
            ))}
          </div>
          <div className="chat-input"><span>输入访客问题进行预览</span><Send size={18} /></div>
        </Panel>
        <div className="rail-stack">
          <ConfigPanel title="知识来源" items={["已确认可信事实卡", "AI 收录包内容", "买家问题地图", "发布后的官网页面"]} />
          <ConfigPanel title="回复风格" items={["专业简洁", "先回答再引导留资", "引用已确认事实", "避免承诺未确认信息"]} />
          <ConfigPanel title="线索规则" items={["询价意向", "案例需求", "集成需求", "人工转接"]} />
        </div>
      </section>
    </>
  );
}

function ReportsPage() {
  const { project } = useConsoleOverview();
  const [reports, setReports] = useState<ReportList>(fallbackReportList);

  useEffect(() => {
    const controller = new AbortController();
    fetchReports(project.id ?? "project_demo", controller.signal)
      .then(setReports)
      .catch(() => setReports({ ...fallbackReportList, reports: reportCards }));
    return () => controller.abort();
  }, [project.id]);

  return (
    <>
      <PageHeader title="报表中心" subtitle="面向老板、市场负责人和交付团队的 AI 来客增长报告。" action={<button className="airank-console-primary-button" type="button">生成报告</button>} />
      <section className="metric-grid">
        <MiniStat label="AI 提及率" value="52%" icon={Activity} />
        <MiniStat label="推荐率" value="35%" icon={Target} />
        <MiniStat label="首推率" value="19%" icon={BadgeCheck} />
        <MiniStat label="线索增长" value="+36%" icon={UsersRound} />
      </section>
      <section className="reports-layout">
        <Panel title="推荐率趋势">
          <TrendChart large />
        </Panel>
        <Panel title="关键结论">
          <ul className="conclusion-list">
            <li>本月 AI 推荐率提升 8%，主要来自 FAQ 页和服务介绍页发布。</li>
            <li>竞品仍在价格成交类问题上有明显优势。</li>
            <li>建议优先生成客户案例页和竞品对比页。</li>
          </ul>
        </Panel>
      </section>
      <section className="report-card-grid">
        {reports.reports.map((item) => (
          <article className="airank-console-card report-card" key={item.title}>
            <FileChartColumn size={28} />
            <div>
              <h3>{item.title}</h3>
              <p>{item.desc}</p>
              <span>{item.date}</span>
            </div>
            <button className="outline-button" type="button" onClick={() => void recordDownloadReceipt(item.report_id ?? item.title)}>
              {item.status}
            </button>
          </article>
        ))}
      </section>
    </>
  );
}

function SettingsPage() {
  const { project } = useConsoleOverview();

  return (
    <>
      <PageHeader title="设置中心" subtitle="管理品牌项目、官网域名、AI 平台接入、通知和成员权限。" action={<button className="airank-console-primary-button" type="button">保存设置</button>} />
      <section className="settings-grid">
        <SettingsSection title="项目资料" icon={Building2} rows={[["企业名称", project.name], ["官网", project.website], ["行业", project.industry], ["目标客户", project.audience]]} />
        <SettingsSection title="AI 平台接入" icon={Bot} rows={[["ChatGPT", "可用"], ["DeepSeek", "可用"], ["Kimi", "部分可用"], ["百度AI搜索", "待配置"]]} />
        <SettingsSection title="通知设置" icon={Bell} rows={[["扫描完成", "站内 + 邮件"], ["发布失败", "立即提醒"], ["复测报告", "每周一 09:00"], ["线索提醒", "实时"]]} />
        <SettingsSection title="成员权限" icon={LockKeyhole} rows={[["管理员", "2 人"], ["运营", "4 人"], ["审核员", "1 人"], ["权限来源", "yudao 绑定"]]} />
      </section>
    </>
  );
}

function SettingsSection({ title, icon: Icon, rows }: { title: string; icon: LucideIcon; rows: [string, string][] }) {
  return (
    <article className="airank-console-card settings-section">
      <div className="settings-head">
        <IconTile><Icon size={22} /></IconTile>
        <h2>{title}</h2>
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

function ProcessSteps({ steps }: { steps: [string, string][] }) {
  return (
    <section className="process-steps">
      {steps.map(([title, desc], index) => (
        <article className="step-card" key={title}>
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
  return (
    <Panel title={title}>
      <div className="config-list">
        {items.map((item) => (
          <label key={item}><input type="checkbox" defaultChecked />{item}</label>
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
