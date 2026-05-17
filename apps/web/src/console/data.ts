export type Tone = "primary" | "success" | "warning" | "danger" | "muted";

export const project = {
  name: "示例科技有限公司",
  website: "www.example.com",
  industry: "营销科技",
  competitors: "数智易、神策、Convertlab",
  audience: "中大型企业市场/增长负责人",
  date: "2024-05-20",
};

export const metricCards = [
  { label: "AI 来客指数", value: "62", suffix: "/100", delta: "较上周 ↑ 12", tone: "primary" as Tone, icon: "Activity" },
  { label: "高意向问题覆盖率", value: "41", suffix: "%", delta: "较上周 ↑ 8%", tone: "primary" as Tone, icon: "Target" },
  { label: "竞品压制问题数", value: "127", suffix: "", delta: "较上周 ↑ 23", tone: "warning" as Tone, icon: "ShieldAlert" },
  { label: "本月 AI 来客线索", value: "186", suffix: "", delta: "较上月 ↑ 36%", tone: "success" as Tone, icon: "UserRound" },
];

export const opportunities = [
  { label: "高意向可覆盖", value: 41, color: "#443efd" },
  { label: "需补齐证据", value: 33, color: "#ff8a1f" },
  { label: "被竞品压制", value: 22, color: "#ff5a3d" },
  { label: "低价值问题", value: 4, color: "#d7dce9" },
];

export const topIssues = [
  { label: "价格方案对比", value: 28 },
  { label: "与竞品功能对比", value: 24 },
  { label: "售后服务怎么样", value: 21 },
  { label: "实施周期多久", value: 18 },
  { label: "数据安全能力", value: 12 },
];

export const nextActions = [
  { title: "补齐对比优势证据", level: "高优先级", desc: "当前有 127 个问题被竞品压制，补齐对比证据可显著提升推荐概率。", cta: "去补齐证据" },
  { title: "完善场景解决方案", level: "中优先级", desc: "完善高频场景方案，覆盖更多高意向问题。", cta: "去完善方案" },
  { title: "发布并启动复测", level: "关键步骤", desc: "完成上述优化后，发布内容并启动复测，验证效果提升。", cta: "去发布复测" },
];

export const providerResults = [
  { name: "豆包", mention: 52, recommend: 34, first: 18 },
  { name: "DeepSeek", mention: 58, recommend: 38, first: 22 },
  { name: "Kimi", mention: 55, recommend: 32, first: 16 },
  { name: "通义", mention: 50, recommend: 30, first: 15 },
  { name: "百度AI搜索", mention: 45, recommend: 28, first: 14 },
  { name: "腾讯元宝", mention: 48, recommend: 30, first: 14 },
  { name: "ChatGPT", mention: 60, recommend: 40, first: 25 },
];

export const factGroups = [
  { title: "企业简介", desc: "公司定位、发展历程、业务覆盖、团队规模等", confirmed: 18, pending: 2, cited: 12, status: "已确认", tone: "success" as Tone },
  { title: "核心服务", desc: "主要产品与服务、服务能力、解决方案等", confirmed: 24, pending: 5, cited: 18, status: "已确认", tone: "success" as Tone },
  { title: "典型案例", desc: "客户案例、应用场景、项目成果与价值等", confirmed: 15, pending: 9, cited: 7, status: "待确认", tone: "warning" as Tone },
  { title: "资质与荣誉", desc: "资质认证、荣誉奖项、行业认可等", confirmed: 16, pending: 1, cited: 9, status: "已确认", tone: "success" as Tone },
  { title: "联系方式", desc: "官网、电话、邮箱、地址等官方联系方式", confirmed: 8, pending: 0, cited: 15, status: "已确认", tone: "success" as Tone },
  { title: "品牌方法论", desc: "核心理念、方法论、技术路线与知识体系", confirmed: 14, pending: 6, cited: 4, status: "需脱敏", tone: "primary" as Tone },
];

export const questionRows = [
  { q: "企业如何选择营销自动化平台？", tag: "选型决策", intent: "高", mine: 28, competitor: 72, gap: -44, assets: ["《营销自动化选型指南》", "《平台核心能力对比表》"] },
  { q: "营销自动化和 CRM 有什么区别？", tag: "认知教育", intent: "中", mine: 35, competitor: 65, gap: -30, assets: ["《MA 与 CRM 区别详解》", "《一图看懂获客关系》"] },
  { q: "营销自动化平台有哪些核心功能？", tag: "选型决策", intent: "高", mine: 32, competitor: 68, gap: -36, assets: ["《核心功能清单》", "《功能场景化案例》"] },
  { q: "平台价格一般是多少？", tag: "价格成交", intent: "高", mine: 22, competitor: 78, gap: -56, assets: ["《产品定价说明》", "《不同版本价格对比》"] },
  { q: "实施周期需要多久？", tag: "选型决策", intent: "中", mine: 30, competitor: 70, gap: -40, assets: ["《实施方法论》", "《典型项目时间表》"] },
  { q: "是否支持与企业微信/钉钉集成？", tag: "选型决策", intent: "中", mine: 40, competitor: 60, gap: -20, assets: ["《集成能力说明》", "《集成配置指南》"] },
  { q: "有哪些成功案例可以参考？", tag: "决策验证", intent: "高", mine: 26, competitor: 74, gap: -48, assets: ["《行业客户案例集》", "《ROI 效果报告》"] },
];

export const gapItems = [
  { name: "品牌身份", desc: "品牌介绍 / 资质荣誉 / 官方背书", covered: false, impact: 128, action: "补充品牌介绍、资质证书、媒体报道", level: "高" },
  { name: "核心服务", desc: "服务内容 / 服务流程 / 服务优势", covered: true, impact: 96, action: "完善服务流程与差异化优势", level: "高" },
  { name: "客户案例", desc: "案例详情 / 客户评价 / 实施效果", covered: false, impact: 112, action: "补充典型案例与客户评价", level: "高" },
  { name: "FAQ问答", desc: "常见问题 / 官方解答 / 使用疑问", covered: false, impact: 86, action: "整理高频问题并提供结构化答案", level: "中" },
  { name: "行业方案", desc: "行业解决方案 / 场景应用", covered: false, impact: 104, action: "沉淀行业解决方案与落地场景", level: "高" },
  { name: "对比选型", desc: "产品对比 / 选型建议 / 优势分析", covered: false, impact: 78, action: "提供对比资料与选型建议", level: "中" },
  { name: "第三方信源", desc: "媒体报道 / 评测报告 / 行业榜单", covered: false, impact: 92, action: "获取第三方报道与评测背书", level: "中" },
  { name: "技术抓取", desc: "技术文档 / API 文档 / 开发者资源", covered: true, impact: 54, action: "完善技术文档与开发者资源", level: "低" },
];

export const assetCards = [
  { title: "企业事实页", desc: "把已确认事实卡发布为 AI 易读页面", progress: 86, status: "可发布" },
  { title: "服务介绍页", desc: "结构化呈现核心服务、流程与优势", progress: 72, status: "待补证据" },
  { title: "客户案例页", desc: "承接案例、成效、行业场景与客户评价", progress: 58, status: "待确认" },
  { title: "FAQ 页", desc: "覆盖高频买家问题和官方回答", progress: 64, status: "可生成" },
  { title: "竞品对比页", desc: "形成差异化选型依据和对比证据", progress: 45, status: "缺证据" },
  { title: "行业解决方案页", desc: "沉淀本地行业和高价值场景方案", progress: 52, status: "可生成" },
  { title: "JSON-LD", desc: "让 AI 和搜索引擎识别品牌事实", progress: 80, status: "可发布" },
  { title: "sitemap.xml", desc: "发布后提交抓取和复测", progress: 92, status: "可发布" },
];

export const publishingRows = [
  { page: "企业事实页", channel: "官网", crawl: "已抓取", index: "已收录", time: "2024-05-20 10:30" },
  { page: "服务介绍页", channel: "官网", crawl: "已抓取", index: "待收录", time: "2024-05-20 10:28" },
  { page: "客户案例页", channel: "AI 获客页", crawl: "排队中", index: "未提交", time: "2024-05-20 10:25" },
  { page: "FAQ 页", channel: "官网", crawl: "已抓取", index: "已收录", time: "2024-05-20 10:18" },
  { page: "竞品对比页", channel: "AI 获客页", crawl: "失败", index: "未提交", time: "2024-05-20 10:11" },
];

export const reportCards = [
  { title: "AI 来客诊断报告", desc: "覆盖平台表现、竞品压制、引用来源和优化建议", date: "2024-05-20", status: "已生成" },
  { title: "推荐缺口复测报告", desc: "对比发布前后推荐率、首推率和引用变化", date: "2024-05-18", status: "可下载" },
  { title: "高管月报", desc: "面向管理层的 AI 可见性和线索增长摘要", date: "2024-05-01", status: "已归档" },
];

export const assistantMessages = [
  { role: "visitor", text: "你们和传统 CRM 有什么区别？" },
  { role: "assistant", text: "我们更侧重从匿名访客到可运营线索的全链路识别，并可和 CRM 对接沉淀客户资产。" },
  { role: "visitor", text: "有制造业案例吗？" },
  { role: "assistant", text: "有。已确认案例中包含装备制造和工业服务场景，我可以给你发送案例摘要。" },
];
