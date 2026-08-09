import fs from 'node:fs';
import path from 'node:path';

const root = process.cwd();
const date = '2026-08-09';

const series = {
  observability: { label: '多平台观测', no: '01', source: ['https://github.com/yaojingang/yao-geo-skills', 'https://github.com/yaojingang/geo-citation-lab'] },
  citation: { label: '引用证据', no: '02', source: ['https://github.com/yaojingang/geo-citation-lab', 'https://github.com/yaojingang/yao-geo-skills'] },
  assets: { label: '事实资产', no: '03', source: ['https://github.com/yaojingang/GEOFlow', 'https://github.com/yaojingang/yao-geo-skills'] },
  technical: { label: '页面工程', no: '04', source: ['https://github.com/yaojingang/GEORank', 'https://github.com/yaojingang/yao-geo-skills'] },
  operations: { label: '模型治理', no: '05', source: ['https://github.com/yaojingang/TokHub', 'https://github.com/yaojingang/yao-geo-skills'] },
  business: { label: '企业落地', no: '06', source: ['https://github.com/yaojingang/yao-geo-skills', 'https://github.com/yaojingang/GEOFlow'] },
};

const featured = [
  ['ai-observability-baseline', 'observability', 'AI 可见性不是一次搜索：企业如何建立多平台可比基线', '统一问题、平台、终端、时间与证据快照，建立可复查的观测基线。', '10 分钟'],
  ['citation-evidence-engineering', 'citation', '从被引用到被相信：AI 引用来源与主张核验方法', '区分来源出现、内容吸收与主张支持，建立可追溯证据链。', '11 分钟'],
  ['enterprise-fact-assets', 'assets', '企业知识库为何不能直接变成 AI 可信答案', '从文档集合走向有来源、有版本、有审核边界的事实资产。', '12 分钟'],
  ['ai-extractability-engineering', 'technical', '官网可提取性工程：让 AI 准确理解页面，不是堆关键词', '从抓取、正文、实体、证据与 Schema 检查机器可读性。', '10 分钟'],
  ['model-sampling-governance', 'operations', '多模型采样治理：稳定性、质量、成本与审计如何统一', '治理提供方健康、任务路由、失败质量、配额成本与审计证据。', '10 分钟'],
].map(([slug, category, title, lead, read]) => ({ slug, category, title, lead, read, featured: true }));

const articles = [
  {
    slug: 'buyer-question-map', category: 'observability', read: '8 分钟',
    title: '买家问题地图：为什么品牌词不是 AI 可见性研究的起点',
    lead: '企业真正要回答的不是“AI 知不知道我”，而是买家在认知、比较、选型和采购阶段提问时，品牌能否进入候选答案。',
    core: '问题地图应从客户任务和决策阶段出发，并保留真实问法、意图、场景和证据要求。只有品牌词的测试会高估可见性，也无法指导内容与产品行动。',
    context: ['品牌词通常已经包含明确指向，容易得到看似积极的答案，但它无法代表陌生买家如何发现解决方案。真正影响业务的是非品牌问题、场景问题、比较问题与风险问题。', '同一个业务主题需要区分信息获取、方案比较、预算评估、实施验证和供应商选择。不同阶段的回答结构、引用来源和品牌进入条件并不相同。'],
    pillars: [['角色', '识别决策人、使用者、技术评估者和采购者的不同关注点。'], ['阶段', '把认知、研究、比较、验证和采购拆成独立问题簇。'], ['场景', '围绕行业、规模、系统环境和约束条件保留上下文。'], ['证据', '为每类问题定义回答必须引用或核验的事实。']],
    method: ['AIRank 将销售访谈、官网搜索词、客服问题、投标材料和行业报告中的问法统一去重，再按业务价值和证据成熟度分层。问题不是一次性关键词清单，而是持续治理的研究资产。', '每个问题都绑定平台采样、引用来源、事实缺口、内容任务和复测批次。这样团队能看清某个问题为何没有出现品牌，以及应该补产品事实、案例证据还是页面结构。'],
    steps: ['收集真实客户问法并去除内部产品术语', '按角色、阶段、场景和风险建立问题簇', '标记高价值问题与必须核验的主张', '建立平台采样基线并保存原始回答', '把缺口转为事实、页面和复测任务'],
    product: 'AIRank 的买家问题地图连接监测、事实库、内容任务和报告，不把“关键词数量”当作完成度，而关注高价值问题是否有稳定、可信、可验证的回答。',
    boundary: '问题地图不能替代真实客户研究。若企业没有销售访谈、赢单复盘或采购反馈，首版只能视为待验证假设，必须在项目中持续校正。',
  },
  {
    slug: 'repeated-sampling-confidence', category: 'observability', read: '9 分钟',
    title: '重复采样与置信边界：如何避免把 AI 随机波动当成增长',
    lead: '生成式回答存在波动，企业需要用重复采样、失败记录和完整性说明，区分真实变化、平台变化与随机噪声。',
    core: '趋势判断必须建立在同口径重复样本上。样本轮次、有效回答率、时间窗口和失败分布应与结果一起披露，不能只展示最好的一次。',
    context: ['相同提示在不同会话中可能产生不同答案，搜索触发、来源选择和品牌排序也会变化。单次观测适合发现问题，不适合证明趋势。', '盲目增加轮次也不能自动提高质量。若平台协议、终端或模型版本改变，更多样本只会混合不同研究对象。'],
    pillars: [['重复', '同一协议下进行独立采样，避免共享上下文污染。'], ['完整', '成功、拒答、超时、无搜索和异常结果全部计入。'], ['分层', '平台、终端、问题簇和时间窗口分别统计。'], ['边界', '报告样本量、有效率和结论适用期。']],
    method: ['AIRank 为每个项目冻结采样协议，并把协议版本与样本绑定。系统计算提及、引用、事实一致性和质量指标时，同时展示有效样本数与失败分布。', '当平台发生明显协议变化时，系统不强行延续旧趋势，而是建立新基线，并保留两个阶段的差异说明。'],
    steps: ['定义最小独立样本和允许的重试策略', '按平台与终端分开运行并记录环境', '对质量失败与运行失败分别分类', '汇总指标时同步展示样本完整性', '变更协议时重建基线而不是拼接趋势'],
    product: 'AIRank 报告中的每条趋势都可以下钻到原始回答和失败样本，让管理层知道结论强度，而不是只看到一条看似精确的曲线。',
    boundary: '在平台不可稳定访问或样本量过低时，应输出“证据不足”而不是排名结论。重复采样提供更可靠的描述，但仍不能单独证明内容变化与结果之间的因果。',
  },
  {
    slug: 'web-app-platform-differences', category: 'observability', read: '8 分钟',
    title: '同一 AI 的 Web 与 App 为什么要分开监测',
    lead: '终端界面、账号状态、检索链路和引用展示可能不同，把 Web 与 App 混成一个指标会掩盖真实差异。',
    core: '平台名称不是完整的观测身份。有效样本至少需要记录终端、会话状态、功能入口、模型标识、搜索状态和引用展示方式。',
    context: ['同一品牌问题在网页端可能展示完整来源，在 App 端只显示资料卡片；也可能因为入口不同触发不同搜索链路。此时“引用数量”并不可直接比较。', '企业如果只监测容易自动化的网页端，可能错过真实用户更常使用的移动端体验；反过来，只看 App 截图又难以形成稳定、可查询的数据。'],
    pillars: [['身份', '平台、终端、入口、模型与账号状态共同定义样本。'], ['展示', '区分正文引用、来源列表、资料卡片和无显式来源。'], ['协议', 'Web 与 App 使用独立采样与证据格式。'], ['汇总', '先分端分析，再在明确权重下形成组合视图。']],
    method: ['AIRank 为终端建立独立数据契约：网页保留 DOM、链接和截图，移动端保留截图、可访问性结构和资料卡片状态。两端最终映射到统一的回答、引用和质量模型。', '报告不会把无法同口径的界面字段强行平均，而是显示平台内差异，并提示哪些变化可能来自产品界面而非品牌优化。'],
    steps: ['列出客户真实使用的 AI 终端与入口', '为每个终端定义可采集的回答和引用证据', '分开运行并记录账号与功能状态', '建立可比字段和不可比字段清单', '按业务使用权重呈现终端差异'],
    product: 'AIRank 的多终端监测让品牌看到真实用户入口中的回答差异，并为移动端引用卡片、网页来源和模型回答保留各自证据。',
    boundary: '移动端自动化受版本、登录和系统环境影响较大。无法稳定复现时，应标记为实验或人工抽检，不应伪装成持续生产能力。',
  },
  {
    slug: 'source-ecosystem-strategy', category: 'citation', read: '9 分钟',
    title: 'AI 信源生态：为什么只优化企业官网远远不够',
    lead: 'AI 回答可能同时吸收官网、媒体、文档、社区、行业机构和聚合页面。品牌需要治理的是完整证据生态，而不是单一域名。',
    core: '官网负责第一方事实，外部信源负责独立验证与场景补充。两者角色不同，不能用批量转载代替真实第三方证据。',
    context: ['企业官网通常最适合承载产品定义、参数、实施边界和官方案例，但 AI 在比较、推荐和风险判断中也会寻找外部来源。', '外部曝光越多不等于证据越强。重复新闻稿、低质量目录和来源不明的聚合页可能增加噪声，甚至传播过期事实。'],
    pillars: [['第一方', '官网、文档、帮助中心和官方报告提供权威事实。'], ['第二方', '客户、合作伙伴和渠道提供交付与使用证据。'], ['第三方', '行业机构、媒体与研究提供独立验证。'], ['社区', '真实问题和经验补充场景，但需要风险核验。']],
    method: ['AIRank 按问题簇统计来源类型、域名、页面和主张覆盖，不只做域名排行榜。系统识别哪些关键问题过度依赖单一来源，哪些外部页面传播了错误或过期事实。', '行动建议优先补齐证据角色：官网缺定义就完善第一方页面，方案缺交付证明就建设案例，行业判断缺独立支持就寻找可核验研究，而不是机械增加链接。'],
    steps: ['按买家问题建立当前引用来源台账', '区分来源角色、质量、时效和可控程度', '识别关键主张的单点依赖与证据空白', '建设第一方事实并争取真实外部验证', '持续监测错误、过期和冲突来源'],
    product: 'AIRank 的引用来源图谱把“域名出现”升级为“来源角色—支持主张—覆盖问题”的证据地图，帮助品牌有序建设信源生态。',
    boundary: 'AIRank 不承诺操控第三方平台或购买引用。外部信源建设应基于真实合作、研究和交付证据，并遵守平台、广告和合规要求。',
  },
  {
    slug: 'claim-evidence-matrix', category: 'citation', read: '9 分钟',
    title: '主张—证据矩阵：把品牌宣传语变成可核验事实',
    lead: '“领先、专业、智能”无法被精确核验。企业需要将宣传语拆成原子主张，并为每条主张绑定来源、边界和审核状态。',
    core: '可用主张必须回答：具体说了什么、适用于什么范围、由什么证据支持、证据何时有效、谁批准对外表达。',
    context: ['企业材料中常见复合表达：一句话同时包含产品能力、客户规模、效果和行业地位。任何一个部分缺乏证据，都可能让整句表达失真。', '模型会自然改写和概括。如果事实没有边界，原本限定于单一客户或版本的结论可能被扩展为普遍承诺。'],
    pillars: [['拆解', '将复合宣传语拆成最小可核验主张。'], ['绑定', '主张关联来源页面、证据片段和事实版本。'], ['评级', '按直接、间接、相关和不足评估支持强度。'], ['治理', '记录有效期、公开范围、审核人与禁用表达。']],
    method: ['AIRank 先从官网、销售材料和 AI 回答中抽取高价值主张，再与企业事实库对齐。没有直接证据的主张不会自动进入可信答案资产。', '矩阵同时反向指导内容建设：关键能力如果只有内部文档支持，应建设可公开页面；高频买家问题如果缺案例证据，应进入客户证明计划。'],
    steps: ['盘点官网与销售材料中的核心宣传语', '拆分能力、数字、效果、资质和地位主张', '绑定证据并标记支持强度', '由业务、品牌或法务确认表达边界', '将证据缺口转化为内容与案例任务'],
    product: 'AIRank 通过主张核验队列、事实版本和报告证据索引，让品牌表达从“看起来可信”变成“能够说明依据”。',
    boundary: '证据矩阵不能替代法律意见或行业认证。涉及医疗、金融、安全、效果承诺等高风险内容，仍需专业审查和明确免责声明。',
  },
  {
    slug: 'citation-absorption-depth', category: 'citation', read: '8 分钟',
    title: '引用广度与内容吸收深度：企业应该优化哪个指标',
    lead: '被列为来源和真正影响答案是两件事。企业需要同时观察来源覆盖与内容吸收，避免用引用数量掩盖低质量影响。',
    core: '引用广度说明进入了多少来源集合，吸收深度说明页面中的具体定义、数字、比较和步骤是否进入答案。两者应分别测量。',
    context: ['一个页面可能频繁出现在来源列表，却很少影响答案主张；另一个页面引用次数较少，但其定义或数据被核心答案采用。只看 URL 数量会错过这种差异。', '吸收深度也不能仅凭语义相似度判断。常识性表述可能在多个来源重复，必须结合独特主张、证据片段和时间关系谨慎分析。'],
    pillars: [['广度', '来源、域名和页面进入引用集合的覆盖程度。'], ['深度', '具体内容单元进入答案核心主张的程度。'], ['位置', '内容位于定义、比较、建议还是附加说明。'], ['稳定', '同一内容是否在重复采样中持续被采用。']],
    method: ['AIRank 先保存回答与来源快照，再将回答拆成主张，与来源页面中的证据片段对齐。系统区分直接支持、间接相关与无法确认，不把相似表达自动当成因果。', '优化优先级取决于业务目标：新品牌可能先扩大高质量来源覆盖，成熟品牌则更应提升关键主张的吸收深度和事实一致性。'],
    steps: ['统计来源覆盖但不直接作为成效结论', '识别答案中的关键主张和决策位置', '对齐来源证据片段并评估支持强度', '比较重复样本中的稳定性', '按业务问题决定扩广度还是提深度'],
    product: 'AIRank 将引用页面、答案主张和企业事实放在同一证据视图中，让团队知道哪些内容只是出现，哪些内容真正参与了答案形成。',
    boundary: '内容吸收通常是基于可观察结果的推断。除非平台公开内部链路，否则报告应使用“相关、支持、可能吸收”等谨慎表述。',
  },
  {
    slug: 'brand-entity-graph', category: 'assets', read: '9 分钟',
    title: '品牌实体图谱：解决 AI 对公司、产品与能力关系的误解',
    lead: '品牌简称、公司主体、产品线、旧名称和行业术语混在一起时，AI 很容易错指。实体图谱先把“谁和谁是什么关系”说清楚。',
    core: '实体图谱的目标不是画一张漂亮网络图，而是为每个实体建立稳定身份、别名、关系、来源和可信等级，减少品牌错指和产品归属错误。',
    context: ['企业常同时存在工商主体、品牌名、产品名、平台名和历史名称。官网如果缺少明确关系，外部来源又使用不同叫法，AI 可能把产品归到错误公司。', '关系也需要证据。公司拥有产品、产品适用场景、人物担任职务、案例使用方案，都应由具体来源支持。'],
    pillars: [['实体', '公司、品牌、产品、人物、地点、案例与行业。'], ['别名', '简称、英文名、旧名称和常见误写。'], ['关系', '拥有、提供、适用、合作、使用和证明。'], ['证据', '每条关系绑定来源、版本与可信等级。']],
    method: ['AIRank 从官网、文档、案例和外部来源抽取实体与关系，优先处理高频买家问题涉及的对象。系统识别同名冲突、缺失关系和来源不一致。', '图谱结果用于事实检索、页面 Schema、内容生成和 AI 回答核验。更新企业事实时，系统可追踪受影响关系和内容资产。'],
    steps: ['建立公司、品牌和核心产品的稳定 ID', '整理别名、旧名与禁止混用表达', '提取高价值关系并绑定来源', '处理冲突、缺失和低可信关系', '将实体关系用于页面、内容与回答核验'],
    product: 'AIRank 的品牌实体图谱是可信事实库的关系层，帮助系统在生成内容或核验回答时先确认主体和关系，再处理具体主张。',
    boundary: '图谱不能凭模型推断补齐事实。缺少可靠来源的关系应标记待核验，而不是自动写入正式知识资产。',
  },
  {
    slug: 'answer-asset-production', category: 'assets', read: '9 分钟',
    title: '答案资产工厂：如何规模化生产内容又不牺牲可信度',
    lead: '企业需要的不是批量生成文章，而是把买家问题、可信事实、证据和发布复测组合成可持续生产的答案资产。',
    core: '答案资产必须同时满足用户价值、事实支持、页面可提取性和复测目标。模型负责组织表达，事实库与审核机制负责边界。',
    context: ['纯提示词生产容易得到结构相似、证据稀薄的内容。文章数量增长不等于品牌在 AI 回答中更可信，反而可能制造内部重复和事实冲突。', '高价值内容通常对应明确问题和决策任务，并能说明方法、条件、证据和下一步，而不是只重复产品卖点。'],
    pillars: [['Brief', '明确问题、读者、阶段、目标主张和复测方式。'], ['Facts', '只调用审核通过且在有效期内的企业事实。'], ['Evidence', '为关键判断附来源、案例、数据和边界。'], ['Review', '事实、品牌、法务和发布角色按风险分层审核。']],
    method: ['AIRank 将问题地图中的缺口转成内容 Brief，自动带入可用事实、来源和禁用表达。生成稿同时输出事实引用清单，审核者可以定位每个关键句的依据。', '内容发布后进入页面抓取和多平台复测。没有复测目标的内容仍可用于教育，但不能被包装成 GEO 优化结果。'],
    steps: ['从高价值问题和证据缺口创建内容任务', '选择有效事实、来源和表达边界', '生成正文与事实引用清单', '按风险分配审核和发布', '抓取上线页面并绑定复测批次'],
    product: 'AIRank 把内容生产从单次写作升级为问题驱动、证据约束、审核可追踪、发布可复测的答案资产流水线。',
    boundary: '自动生成不能替代专家判断。涉及原创研究、客户承诺或高风险行业结论时，必须由具备责任权限的人审核。',
  },
  {
    slug: 'fact-freshness-governance', category: 'assets', read: '8 分钟',
    title: '事实新鲜度治理：如何防止 AI 持续传播过期企业信息',
    lead: '价格、产品能力、认证、客户和服务区域会变化。没有有效期与变更影响分析的知识库，迟早会把旧事实继续发布出去。',
    core: '事实新鲜度不是统一设置一个更新时间，而是按事实类型定义复核周期、触发事件、责任人和下游影响范围。',
    context: ['官网更新后，旧 PDF、媒体稿、渠道页和内部销售材料仍可能继续传播历史信息。AI 可能引用这些外部来源，形成“官网已改但答案未改”的滞后。', '简单删除旧内容也可能破坏历史可追溯性。更合理的做法是保留版本、停止公开使用，并为替代事实建立明确关系。'],
    pillars: [['周期', '价格、参数、资质和案例采用不同复核频率。'], ['触发', '产品发布、合同变化和认证到期触发即时复核。'], ['影响', '追踪事实被哪些页面、文章和报告使用。'], ['替代', '旧事实保留历史状态并指向当前有效版本。']],
    method: ['AIRank 为事实设置所有者、有效期和复核规则。临近到期的事实进入审核队列；变更后自动列出受影响内容与待复测问题。', '外部过期来源无法直接删除时，系统持续监测其在 AI 回答中的出现，并通过新的官方页面、说明或合作沟通建立更清晰的当前证据。'],
    steps: ['按事实类型定义有效期与责任人', '建立产品和政策变更触发器', '扫描事实的页面与内容引用关系', '更新版本并停止旧事实继续生产', '复测 AI 是否仍采用过期来源'],
    product: 'AIRank 通过事实版本、到期提醒、影响分析和复测任务，让品牌知识从一次建库变成持续维护的企业资产。',
    boundary: '外部平台的更新速度不可控。AIRank 可以记录和推动纠偏，但不能保证所有 AI 平台在固定时间内接受新事实。',
  },
  {
    slug: 'schema-semantic-structure', category: 'technical', read: '9 分钟',
    title: 'Schema 与语义结构：哪些标记真正帮助 AI 理解企业官网',
    lead: '结构化数据的价值是消除实体与页面类型歧义，不是堆叠越多越好，更不能声明页面正文没有展示的内容。',
    core: 'Schema 必须与可见正文一致，并使用稳定 canonical 和实体 ID 连接组织、产品、文章、作者、案例与面包屑。',
    context: ['很多网站安装插件后生成大量结构化数据，但字段来自模板默认值，与页面实际内容不一致。错误标记会扩大歧义，而不是增加可信度。', 'AI 理解页面首先依赖清晰正文。Schema 是补充机器关系的结构层，不能替代产品定义、证据、条件和更新时间。'],
    pillars: [['一致', '标记内容必须在页面正文中真实可见。'], ['稳定', 'canonical、实体 ID 和 URL 不因模板变化频繁漂移。'], ['关系', 'Organization、Product、Article 等对象形成清晰连接。'], ['克制', '只使用有真实内容和维护能力的类型与字段。']],
    method: ['AIRank 从页面可见内容反向生成 Schema 检查表，核对主体、名称、描述、作者、日期和关系。系统识别重复实体、冲突 canonical 和不可见声明。', '修复优先级由业务页面和买家问题决定。产品页、案例页、文章页和 FAQ 的结构化要求不同，不使用一套模板覆盖全部页面。'],
    steps: ['确定页面主题、主体与 canonical', '核对可见正文中的实体与关键属性', '选择必要 Schema 类型和稳定实体 ID', '验证标记与正文、站内链接的一致性', '上线后持续检查错误和内容变更'],
    product: 'AIRank 的 Schema 诊断与实体图谱、事实库和页面检查联动，输出代码建议时同时说明对应事实和业务目的。',
    boundary: '结构化数据不能保证 AI 引用或排名。它降低机器理解歧义，但仍需要高质量正文、真实证据和可访问页面。',
  },
  {
    slug: 'dom-over-image-content', category: 'technical', read: '8 分钟',
    title: '关键文字为什么必须留在 DOM：官网图片与网页控件的正确分工',
    lead: '视觉效果可以用高质量图片承载，但标题、参数、步骤、结论和按钮如果只存在于截图中，会同时损害清晰度、移动端、无障碍和机器提取。',
    core: '复杂场景与质感适合图片，关键事实与交互适合真实 DOM。最优方案通常是“底图或透明视觉 + 真文字 + 真按钮”的混合结构。',
    context: ['整屏截图在固定尺寸下看似接近设计稿，但缩放到手机或高分辨率屏幕后容易模糊；文字不可选择、不可搜索、不可适配，也难以维护。', '完全不用图片同样会失去品牌质感。企业官网应把产品场景、空间关系和氛围交给视觉素材，把信息与交互交给网页控件。'],
    pillars: [['图片', '承载产品场景、质感、真实界面和复杂空间。'], ['DOM', '承载标题、说明、数据、步骤、标签和行动按钮。'], ['适配', '图片裁切与文字布局分别响应不同视口。'], ['等价', '重要图片提供准确 alt 或正文等价描述。']],
    method: ['AIRank 页面审计会识别含大量文字的图片、模糊截图、不可点击按钮和移动端裁切问题，并按业务重要性给出重构建议。', '对复杂产品示意图，可保留无文字的底图与少量视觉标签，再使用绝对定位或网格布局叠加真实文字；对数据面板，优先使用 DOM 图表和可访问表格。'],
    steps: ['盘点图片中的标题、参数、步骤和按钮', '区分装饰视觉与必须可提取的信息', '重制无文字底图或透明视觉资产', '用真实 DOM 还原文字、标签与交互', '验证桌面、手机、缩放和机器读取'],
    product: 'AIRank 的官网诊断把图片文字问题映射到可提取性、移动端和引用证据三个维度，帮助企业同时提升视觉与机器可读性。',
    boundary: '并非所有图片文字都必须拆出，例如品牌 Logo、产品截图中的原生界面和受控海报可以保留，但关键结论应在正文提供等价信息。',
  },
  {
    slug: 'crawler-rendering-boundaries', category: 'technical', read: '9 分钟',
    title: '抓取与渲染边界：为什么用户看得到，AI 不一定读得到',
    lead: '浏览器可以运行复杂脚本，但不同搜索与 AI 抓取系统的渲染能力、等待时间和资源策略不同。关键内容不应依赖脆弱的客户端链路。',
    core: '代表性页面必须同时检查原始 HTML、渲染 DOM、网络依赖和失败降级。重要事实应在稳定路径中可达，并有清晰 canonical。',
    context: ['SPA 页面可能只返回空壳 HTML，正文依赖接口、登录、地区或异步脚本。用户网络正常时能看到，不代表抓取系统能完整执行。', '反过来，所有页面都做静态复制会增加维护成本。企业需要识别真正影响发现与引用的公开页面，而不是对整个系统一刀切。'],
    pillars: [['原始', '检查首个 HTML 是否包含标题、摘要和核心内容。'], ['渲染', '比较执行脚本后的正文、链接和结构变化。'], ['依赖', '识别接口、Cookie、地区、登录和第三方资源。'], ['降级', '脚本或资源失败时仍保留必要信息与导航。']],
    method: ['AIRank 抽取首页、产品、方案、案例和文章样本，记录状态码、canonical、原始正文、渲染正文与资源错误。系统重点报告导致实体、主张和证据缺失的问题。', '修复策略包括服务端渲染、预渲染、静态生成、渐进增强或关键内容直出，具体选择取决于技术栈和维护成本。'],
    steps: ['选择高价值公开页面作为诊断样本', '对比原始 HTML 与渲染后正文', '记录关键接口和资源失败影响', '选择适合现有栈的稳定输出方式', '上线后以真实抓取结果复验'],
    product: 'AIRank 把抓取技术问题与受影响的品牌事实和买家问题绑定，避免技术团队面对一份没有业务优先级的通用 SEO 清单。',
    boundary: '不同平台的抓取实现并不完全公开。技术诊断只能验证可观察行为和通用可达性，不能声称掌握所有平台内部索引规则。',
  },
  {
    slug: 'provider-health-routing', category: 'operations', read: '9 分钟',
    title: 'Provider 健康与路由：如何保证多平台监测不被静默降级',
    lead: '端点返回成功不代表目标平台采样成功。健康检查必须覆盖鉴权、模型、搜索、引用和响应质量，并禁止正式研究跨平台伪装。',
    core: '路由应服务任务完整性。辅助分析可以使用等价模型，正式平台观测必须锁定研究对象，并完整记录失败。',
    context: ['多上游系统常在失败时自动切换，以保证应用继续响应。但在可见性研究中，切换模型会改变研究对象，若不披露就会污染数据。', '仅用 ping 或模型列表检查健康也不够。端点可能可达，却无法搜索、缺少引用字段或持续返回截断内容。'],
    pillars: [['连通', '网络、TLS、DNS 与基础接口可达。'], ['鉴权', '凭据有效、权限范围和租户归属正确。'], ['能力', '目标模型、搜索、引用与协议字段可用。'], ['质量', '真实任务响应完整且符合采样协议。']],
    method: ['AIRank 对连接进行分层探测，并为能力标记 ready、partial、blocked、disabled 或 dev_only。正式批次执行前冻结允许端点，运行中发生切换必须进入审计记录。', '熔断保护上游与预算，但不会隐藏失败。报告同时展示有效样本、运行失败和质量失败，让用户知道完整性。'],
    steps: ['登记提供方、协议、能力和生产状态', '建立分层探测与真实任务探针', '为正式采样锁定允许路由', '记录熔断、重试、切换和失败原因', '将连接健康纳入报告完整性'],
    product: 'AIRank 的模型基础设施对用户呈现采样完整性与能力状态，而不是复杂网关配置；运维细节服务于可信报告。',
    boundary: '实验性网页登录、个人账号或非官方连接不应默认承诺生产稳定性。必须明确范围、风控和数据责任。',
  },
  {
    slug: 'valid-sample-cost', category: 'operations', read: '8 分钟',
    title: '每个有效样本的真实成本：别只比较模型调用单价',
    lead: '低价端点如果失败率高、缺少引用或需要大量人工核验，最终成本可能更高。企业应按有效样本和可交付证据计算成本。',
    core: '有效样本成本应包括调用、重试、失败、证据存储、质量检查和人工复核，并与项目、平台和批次绑定。',
    context: ['模型价格只是直接成本。引用字段不稳定、协议频繁变化或内容质量差，会增加返工和人工审查，甚至使整个批次失去可比性。', '过度压缩样本也会降低结论价值。成本控制应在研究目标、样本完整性和预算之间做显式取舍。'],
    pillars: [['调用', '输入输出、搜索和工具使用的直接费用。'], ['失败', '限流、超时、重试和无效响应消耗。'], ['证据', '快照、页面、截图和审计日志的存储处理。'], ['人工', '质量抽检、事实核验和报告解释时间。']],
    method: ['AIRank 按租户、项目、问题簇、平台和复测批次归集用量，并计算有效样本率。预算告警会说明暂停或降频对样本完整性的影响。', '系统优化优先减少质量失败、无意义重试和重复任务，而不是在不披露的情况下替换研究平台。'],
    steps: ['定义有效样本和必要证据标准', '按项目记录调用、失败与重试', '估算证据处理和人工审核成本', '比较单位有效样本而非单位请求', '在报告中披露预算导致的样本变化'],
    product: 'AIRank 把成本与证据完整性放在同一运营视图，帮助企业知道预算花在了哪些可验证结果上。',
    boundary: '不同平台价格和连接方式会变化。成本模型必须按实际合同和运行数据更新，不能把示例单价当成长期承诺。',
  },
  {
    slug: 'model-protocol-audit', category: 'operations', read: '9 分钟',
    title: '模型协议与版本审计：平台变化后趋势还能不能继续比较',
    lead: '模型名称、搜索入口、引用字段和默认行为会变化。没有协议版本审计，历史趋势可能把系统变化误判为品牌变化。',
    core: '每个样本应绑定模型标识、接口版本、关键参数、功能状态与采样协议。发生破坏性变化时建立新基线，而不是强行延续。',
    context: ['提供方可能在不改变营销名称的情况下更新模型，也可能调整搜索触发、引用展示和安全策略。结果变化未必来自企业内容。', '只记录一个模型字符串无法复查。还需要保存请求结构、响应字段、端点、功能开关和任务版本的摘要。'],
    pillars: [['身份', '提供方、端点、模型、接口和终端共同标识。'], ['参数', '温度、工具、搜索和上下文设置有版本记录。'], ['契约', '回答、引用、错误和用量字段保持可解析。'], ['变更', '检测破坏性变化并暂停跨阶段直接比较。']],
    method: ['AIRank 在每批采样前运行协议探针，并把结果与上一个可用版本比较。字段缺失、搜索状态改变或质量分布突变会触发人工复核。', '报告将品牌变化与采样环境变化分开呈现；必要时使用重叠窗口同时运行新旧协议，评估可比性。'],
    steps: ['建立模型与协议身份记录', '对关键字段和功能运行自动探针', '检测版本、字段与质量分布变化', '决定延续、校准或重建基线', '在报告中披露协议变化影响'],
    product: 'AIRank 的协议审计保护长期趋势可信度，让企业不会因为平台升级而错误归因自己的优化成败。',
    boundary: '平台内部模型更新可能无法完全获知。系统只能根据公开版本与可观察行为识别变化，因此结论需要保留不确定性。',
  },
  {
    slug: 'ai-visibility-vs-seo', category: 'business', read: '10 分钟',
    title: 'AI 可见性与 SEO 有什么不同，又为什么必须协同',
    lead: 'SEO 关注页面在搜索结果中的发现与点击，AI 可见性还关注答案如何理解实体、选择来源、组合主张和呈现品牌。',
    core: '两者共享可抓取页面、内容质量和权威信号，但观测对象与交付物不同。企业不应把 GEO 变成换名 SEO，也不应抛弃成熟搜索基础。',
    context: ['传统搜索通常给出结果列表，用户自行进入页面；生成式搜索先组织答案，品牌可能在用户点击前就被提及、比较或排除。', 'AI 回答仍大量依赖公开网络内容，因此技术 SEO、信息架构和高质量页面依然重要。区别在于还要追踪回答原文、引用来源和事实一致性。'],
    pillars: [['发现', '页面能否被抓取、索引和理解。'], ['答案', '品牌是否进入目标问题的候选与解释。'], ['引用', '哪些来源和证据支持答案主张。'], ['行动', '如何把缺口转成事实、页面、内容与复测。']],
    method: ['AIRank 将现有 SEO 资产作为公开证据基础，再增加买家问题地图、多平台回答监测、引用核验和事实治理。团队不需要重建所有内容，而是识别哪些页面最值得升级。', '指标也应协同：搜索流量、品牌查询和转化与 AI 提及、引用、事实一致性并列观察，避免用单一指标解释全部业务变化。'],
    steps: ['保留现有技术 SEO 与高价值页面治理', '新增买家问题和 AI 回答基线', '分析引用来源与现有页面资产关系', '优先改造高价值且证据不足的页面', '联合观察搜索、AI 可见性和业务结果'],
    product: 'AIRank 补足传统 SEO 工具看不到的回答、引用和事实层，不替代搜索分析平台，而是建立面向 AI 答案的新证据体系。',
    boundary: '目前行业仍在快速变化，AI 可见性与流量、线索之间的归因需要谨慎。企业应从可验证试点开始，而不是立刻重分配全部搜索预算。',
  },
  {
    slug: 'geo-30-60-90-roadmap', category: 'business', read: '10 分钟',
    title: '企业 AI 搜索增长 30/60/90 天路线图',
    lead: 'AI 搜索增长不是先批量发文。一个可验收的项目应先建立基线，再建设事实和页面，最后复测与制度化。',
    core: '30 天看清问题，60 天补齐高价值证据，90 天完成发布复测并建立治理节奏。每个阶段都必须有交付物和退出条件。',
    context: ['没有基线就开始内容生产，团队无法判断问题来自品牌认知、信源、事实、页面还是模型波动。没有责任人和复测，优化会退化成一次性营销活动。', '路线图应围绕少量高价值产品和问题簇，而不是第一天覆盖全部业务。范围越清晰，越容易形成可验证结果。'],
    pillars: [['0-30 天', '问题地图、平台基线、引用台账和事实缺口。'], ['31-60 天', '可信事实、重点页面、案例证据和内容任务。'], ['61-90 天', '发布抓取、同口径复测、报告与治理机制。'], ['持续期', '月度监测、事实更新、异常和季度复盘。']],
    method: ['AIRank 项目先选择一个产品、一个目标行业和一组买家问题，完成基线报告。第二阶段把缺口分配给业务、内容和技术团队。第三阶段用同一协议复测并形成证据索引。', '每个阶段都设置停止条件：样本不足则先解决采集，事实不可公开则不生产内容，页面无法稳定抓取则先修技术基础。'],
    steps: ['选择可验证的产品、行业与问题范围', '完成回答、引用、事实与页面四类基线', '按价值和证据成熟度排定行动优先级', '交付事实、页面、内容和案例资产', '复测并建立月度与季度治理节奏'],
    product: 'AIRank 将路线图中的问题、任务、证据和复测放在一个项目视图，管理层可以看到每个行动为何产生、由谁负责、如何验收。',
    boundary: '90 天适合验证方法和形成首个闭环，不代表所有行业都能在此周期获得显著市场结果。采购、内容发布和外部信源建设速度会影响进度。',
  },
  {
    slug: 'cross-team-governance', category: 'business', read: '9 分钟',
    title: '市场、产品、销售、技术如何共同治理 AI 品牌答案',
    lead: 'AI 回答涉及产品事实、品牌表达、客户证据、网页技术和模型运行，任何单一部门都无法独立完成。',
    core: '有效治理需要明确事实所有者、内容责任人、技术维护者、风险审核者和项目负责人，并用同一证据链协作。',
    context: ['市场团队最了解传播，但未必拥有产品参数和合规批准；产品团队掌握事实，却可能不了解买家问法；技术团队能修页面，但需要业务优先级。', '如果所有问题都交给内容团队，最终容易产生无法核验的文章；如果全部交给技术团队，又会变成缺少业务目标的抓取清单。'],
    pillars: [['业务', '定义产品事实、适用范围和优先场景。'], ['市场', '管理问题、内容、品牌表达和外部信源。'], ['技术', '保障页面、数据、连接与证据系统稳定。'], ['治理', '审核高风险主张、版本、权限与复测结论。']],
    method: ['AIRank 以任务和证据为协作对象。每个缺口同时显示关联问题、回答样本、来源、事实和建议动作，并分配给具备责任权限的人。', '会议不再围绕抽象分数，而是处理异常：高价值问题未出现、AI 使用过期事实、关键引用不可达、页面变更未复测等。'],
    steps: ['指定项目负责人和各类事实所有者', '定义内容、技术和风险任务的责任边界', '使用同一问题与证据视图评审', '建立周度异常处理和月度报告', '将事实更新与产品发布流程连接'],
    product: 'AIRank 的任务闭环让监测结果能够进入真实组织流程，而不是停留在市场部门的一份 PDF 报告。',
    boundary: '工具不能替代组织授权。若没有事实负责人、发布权限和审核节奏，再完整的诊断也难以转化为持续结果。',
  },
  {
    slug: 'executive-evidence-dashboard', category: 'business', read: '8 分钟',
    title: '管理层真正需要的 AI 可见性看板，不是更多图表',
    lead: '管理层需要知道风险、机会、行动和证据，而不是被几十个缺少口径的指标淹没。',
    core: '高质量看板应从结论进入证据，从证据进入行动，并同步展示样本完整性、事实风险和复测状态。',
    context: ['单一可见性总分便于传播，却容易掩盖平台、问题和样本差异。一个品牌可能在认知问题表现良好，却在高价值选型问题完全缺席。', '管理层也需要区分可控与不可控：企业可以建设事实和页面，但不能直接控制平台答案。'],
    pillars: [['机会', '高价值问题中的品牌缺席与证据空白。'], ['风险', '错误事实、过期来源、冲突主张和质量异常。'], ['行动', '正在建设的事实、页面、内容和外部证据。'], ['验证', '复测结果、样本完整性和下一阶段决策。']],
    method: ['AIRank 的管理视图按产品、问题簇和项目阶段组织，不以平台数量为唯一主线。每个指标都能下钻到回答快照和引用证据。', '看板同时显示“证据不足”和“协议变化”，避免团队因为数据缺失得到过度确定的结论。'],
    steps: ['确定管理层需要决策的产品与市场问题', '选择少量可解释的结果和风险指标', '为指标建立证据下钻和口径说明', '连接任务负责人、截止时间和复测计划', '按月复盘趋势，按季度调整范围'],
    product: 'AIRank 将研究数据、事实治理和任务交付汇总为管理层可审计的增长看板，让每个决策都有来源和下一步。',
    boundary: '看板不是财务归因系统。AI 可见性与线索、收入的关系需要结合 CRM、分析平台和具体实验验证。',
  },
  {
    slug: 'visibility-to-lead-conversion', category: 'business', read: '9 分钟',
    title: '从 AI 可见到销售线索：中间还缺哪几层能力',
    lead: '品牌被 AI 提及并不会自动产生线索。企业还需要可信落地页、明确行动、线索承接和跨系统证据，才能连接业务结果。',
    core: 'AI 可见性位于购买旅程上游。要验证商业价值，需要将问题、回答、引用、访问、表单、顾问跟进和 CRM 结果按合规方式连接。',
    context: ['用户可能在 AI 中完成大量研究，只在最后访问官网；也可能看到品牌却不点击。单纯比较网站流量无法完整反映 AI 影响。', '反过来，把所有品牌搜索或直接访问归因给 AI 同样不可靠。企业需要设计可观察的中间信号和试点。'],
    pillars: [['承接页', '针对买家问题提供可信答案、证据和清晰下一步。'], ['行动', '诊断、报告、咨询或试用与问题阶段匹配。'], ['记录', '保存来源参数、表单意图和顾问跟进状态。'], ['验证', '结合 CRM 结果与访谈谨慎评估影响。']],
    method: ['AIRank 将高价值问题连接到对应落地页和诊断入口，并在报告中保留建议行动。线索提交后记录意图来源，但不将不可确认的访问强行归因给某个平台。', '更可靠的试点是选择明确行业与问题簇，在一段时间内建设事实和页面，同时观察 AI 回答、品牌查询、直接访问、表单质量和销售反馈。'],
    steps: ['为高价值问题设计对应证据页面', '提供与购买阶段匹配的明确行动', '在隐私合规下记录来源和意图', '将有效线索与销售结果回传分析', '用对照、访谈和多信号评估影响'],
    product: 'AIRank 通过诊断入口、问题地图、证据页面和线索意图连接品牌可见与销售承接，但不会把无法证明的业务结果包装成直接归因。',
    boundary: 'AI 平台通常不会提供完整转介数据，跨设备与无点击影响难以精确归因。商业价值判断应使用多证据，而不是单一追踪参数。',
  },
];

function esc(value) {
  return String(value).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;');
}

function header() {
  return `<header class="site-header site-header--light" data-header><div class="container header__inner"><a aria-label="返回首页" class="brand" href="/"><img alt="智界问道 AIRank 来客" height="42" src="/assets/img/logo-brand.png" width="152"/><span>智界问道</span><em>|</em><strong>AIRank 来客</strong></a><nav aria-label="主导航" class="nav" id="siteNav"><a href="/">首页</a><a href="/product/">产品功能</a><a href="/solutions/">解决方案</a><a href="/cases/">客户案例</a><a class="is-active" href="/resources/">资源中心</a><a href="/pricing/">定价</a><a href="/about/">关于我们</a></nav><div class="header__actions"><a class="btn btn--ghost" href="/login/">登录</a><a class="btn btn--primary" href="/diagnosis/">免费测一测 →</a><button aria-controls="siteNav" aria-expanded="false" aria-label="打开菜单" class="menu-button" type="button"><span></span><span></span><span></span></button></div></div></header>`;
}

function footer() {
  return `<footer class="footer"><div class="container footer__grid"><div class="footer__brand"><a class="brand brand--footer" href="/"><img alt="AIRank 来客" height="42" src="/assets/img/logo-brand.png" width="152"/></a><p>企业级 AI 搜索增长平台<br/>让品牌成为 AI 的可信答案。</p></div><div class="footer__col"><h3>研究中心</h3><a href="/resources/#research-library">25 篇深度文章</a><a href="/resources/#downloads">研究报告</a><a href="/resources/#learning">能力地图</a></div><div class="footer__col"><h3>产品与服务</h3><a href="/product/">产品功能</a><a href="/solutions/">解决方案</a><a href="/diagnosis/">申请企业诊断</a></div><div class="footer__col"><h3>联系我们</h3><a href="tel:4001108776">400-110-8776</a><a href="/about/#contact">联系 AIRank</a></div></div><div class="container footer__bottom"><span>© 2026 北京智界问道科技有限公司</span><span><a href="https://beian.miit.gov.cn/" rel="nofollow noopener" target="_blank">京ICP备17041981号-12</a></span><span><a href="/terms/">服务协议</a>　<a href="/privacy/">隐私政策</a></span></div></footer>`;
}

function renderArticle(article, index) {
  const meta = series[article.category];
  const next = articles[(index + 1) % articles.length];
  const toc = ['背景与问题', '分析框架', '方法与实施', 'AIRank 产品落点', '适用边界', '方法来源'];
  const schema = JSON.stringify({ '@context': 'https://schema.org', '@type': 'Article', headline: article.title, description: article.lead, datePublished: date, dateModified: date, author: { '@type': 'Organization', name: 'AIRank 研究中心' }, publisher: { '@type': 'Organization', name: '北京智界问道科技有限公司' }, mainEntityOfPage: `https://airank.net.cn/resources/${article.slug}/` });
  const pillars = article.pillars.map(([title, text], i) => `<article><small>0${i + 1}</small><h3>${esc(title)}</h3><p>${esc(text)}</p></article>`).join('');
  const paragraphs = values => values.map(value => `<p>${esc(value)}</p>`).join('');
  const sources = meta.source.map(url => `<li><a href="${url}" rel="noopener" target="_blank">${url.split('/').at(-1)}</a>：本文仅吸收其公开方法思路，并按 AIRank 的企业证据、任务与复测体系重新产品化。</li>`).join('');
  return `<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8"/><meta content="width=device-width, initial-scale=1" name="viewport"/><title>${esc(article.title)} | AIRank 研究</title><meta content="${esc(article.lead)}" name="description"/><meta content="index,follow" name="robots"/><link href="https://airank.net.cn/resources/${article.slug}/" rel="canonical"/><link href="/assets/img/favicon.png" rel="icon" type="image/png"/><link href="/assets/css/styles.v20260517.css?v=20260809-research-8" rel="stylesheet"/><meta content="article" property="og:type"/><meta content="${esc(article.title)}" property="og:title"/><meta content="${esc(article.lead)}" property="og:description"/><meta content="https://airank.net.cn/assets/img/og-image.webp" property="og:image"/><script type="application/ld+json">${schema}</script></head><body data-page="research-article"><a class="skip-link" href="#main">跳到主要内容</a>${header()}<main id="main"><section class="research-article__hero"><div class="container research-article__head"><div><div class="research-article__crumbs"><a href="/resources/">AIRank 研究中心</a><span>/</span><span>${meta.label}</span></div><h1>${esc(article.title)}</h1><p class="research-article__lead">${esc(article.lead)}</p><div class="research-article__meta"><span>${date}</span><span>约 ${article.read}阅读</span><span>AIRank Research ${meta.no}</span></div></div><div class="research-article__visual" aria-label="${esc(article.title)}方法框架"><div class="research-article__visual-core"><div><b>${meta.label}</b><small>AIRank Research</small></div></div>${article.pillars.map(([title, text], i) => `<div class="research-article__signal research-article__signal--${i + 1}"><b>${esc(title)}</b><span>${esc(text.length > 16 ? `${text.slice(0, 16)}…` : text)}</span></div>`).join('')}</div></div></section><section class="research-article__body"><div class="container research-article__layout"><aside class="research-article__toc"><b>文章目录</b>${toc.map((label, i) => `<a href="#s${i + 1}">${label}</a>`).join('')}</aside><article class="research-prose"><div class="research-summary"><b>核心结论</b><p>${esc(article.core)}</p></div><h2 id="s1">背景与问题</h2>${paragraphs(article.context)}<h2 id="s2">分析框架</h2><div class="research-framework">${pillars}</div><p>这四个维度不是孤立检查项，而是一条连续证据链。任何结论都需要说明输入、处理过程、输出和限制条件，才能进入企业决策。</p><h2 id="s3">方法与实施</h2>${paragraphs(article.method)}<ol>${article.steps.map(step => `<li>${esc(step)}</li>`).join('')}</ol><h2 id="s4">AIRank 产品落点</h2><div class="research-callout"><h3>从研究方法到可交付系统</h3><p>${esc(article.product)}</p></div><p>AIRank 将结论关联到原始回答、引用来源、企业事实、页面任务与复测批次，使研究不是孤立文章，而是可以被团队执行和验收的工作流。</p><h2 id="s5">适用边界</h2><p>${esc(article.boundary)}</p><p>本文提供的是企业实施框架，不构成对任何 AI 平台内部算法、固定排名或业务结果的保证。真实项目应使用当期数据重新验证。</p><section class="research-sources" id="s6"><h2>方法来源与 AIRank 再产品化</h2><ul>${sources}</ul></section></article></div></section><section class="research-article__next"><div class="container research-next-card"><div><small>继续阅读 · ${series[next.category].label}</small><h2>${esc(next.title)}</h2></div><a class="btn btn--primary" href="/resources/${next.slug}/">下一篇 →</a></div></section></main>${footer()}<script src="/assets/js/config.v20260517.js"></script><script defer src="/assets/js/main.v20260517.js?v=20260809-research-8"></script></body></html>`;
}

for (const [index, article] of articles.entries()) {
  const dir = path.join(root, 'resources', article.slug);
  fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(path.join(dir, 'index.html'), renderArticle(article, index));
}

const all = [...featured, ...articles];
const library = all.map((article, index) => {
  const meta = series[article.category];
  return `<a class="research-library-card" data-research-card data-category="${article.category}" data-search="${esc(`${article.title} ${article.lead} ${meta.label}`)}" href="/resources/${article.slug}/"><span class="research-library-card__series">${meta.no} · ${meta.label}</span><span class="research-library-card__index">${String(index + 1).padStart(2, '0')}</span><h3>${esc(article.title)}</h3><p>${esc(article.lead)}</p><small>${article.read}阅读</small><b>阅读全文 →</b></a>`;
}).join('\n');

for (const file of ['resources.html', path.join('resources', 'index.html')]) {
  const target = path.join(root, file);
  const html = fs.readFileSync(target, 'utf8');
  const marker = /<!-- research-library:start -->[\s\S]*?<!-- research-library:end -->/;
  if (!marker.test(html)) throw new Error(`Missing research library markers in ${file}`);
  const next = html.replace(marker, `<!-- research-library:start -->\n${library}\n<!-- research-library:end -->`);
  fs.writeFileSync(target, next);
}

fs.mkdirSync(path.join(root, 'assets', 'data'), { recursive: true });
const manifest = all.map(({ slug, category, title, lead, read }) => ({ slug, category, title, lead, read }));
fs.writeFileSync(path.join(root, 'assets', 'data', 'research-library.json'), `${JSON.stringify(manifest, null, 2)}\n`);

const sitemapPath = path.join(root, 'sitemap.xml');
const sitemap = fs.readFileSync(sitemapPath, 'utf8');
const sitemapEntries = all.map(article => `  <url><loc>https://airank.net.cn/resources/${article.slug}/</loc><lastmod>${date}</lastmod><changefreq>monthly</changefreq><priority>0.7</priority></url>`).join('\n');
const sitemapMarker = /  <!-- research-sitemap:start -->[\s\S]*?  <!-- research-sitemap:end -->/;
if (!sitemapMarker.test(sitemap)) throw new Error('Missing research sitemap markers');
const nextSitemap = sitemap.replace(sitemapMarker, `  <!-- research-sitemap:start -->\n${sitemapEntries}\n  <!-- research-sitemap:end -->`);
fs.writeFileSync(sitemapPath, nextSitemap);

console.log(`Generated ${articles.length} article pages and ${all.length} research-library entries.`);
