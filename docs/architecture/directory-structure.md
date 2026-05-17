# 工程目录设计

## 设计目标

AIRank 需要支持持续开发、多 Agent 协作、独立部署和与 `XingheAI2026V2` 可控整合。目录设计遵循四个原则：

1. 产品体验独立：AIRank 可以不依赖星河主仓独立跑通 MVP。
2. 领域边界清楚：扫描、事实、证据、内容、发布、复测和报告分别落位。
3. 复用不穿透：复用星河能力只能通过 contracts 和 adapter。
4. 开发与审核分离：开发 Agent 和审核 Agent 有各自目录、清单和产物。

## 推荐结构

```text
apps/
  web/
    src/
      marketing/        官网、免费测一测、案例、报价
      console/          后台工作台
      routes/           路由和页面壳
      services/         前端 API client
      state/            前端状态
  api/
    src/
      modules/
        projects/       品牌项目
        competitors/    竞品管理
        questions/      AI 来客问题地图
        scans/          多平台扫描记录
        facts/          可信事实卡内部事实元和企业事实库
        gaps/           竞品压制分析和内容/信源缺口
        assets/         内容资产与发布包
        publishing/     发布状态和渠道管理
        reports/        体检、复测和高管报告
        leads/          AI 来客助手与线索
        integrations/   外部能力接入入口
      platform/         auth、tenant、audit、settings、job client
  worker/
    src/
      jobs/
        scan/           AI 平台采样和回答快照
        attribution/    引用来源归因
        fact-extract/   资料到可信事实卡内部事实元
        content/
          website/      官网资产（事实页、服务页、案例页、FAQ、对比页、价格页、方案页）
          platform/     平台资产（公众号、知乎、小红书、视频号、百家号、行业媒体稿）
          schema/       结构化资产（JSON-LD、sitemap、robots、canonical）
          sales/        销售承接资产（销售 FAQ、异议处理、话术、来客助手回答库）
        publish/        发布包和发布状态追踪
        retest/         复测
      queues/
      providers/
  review-console/
    src/
      review/           人工确认、风险审校、验收

packages/
  contracts/
    schemas/            JSON Schema
    openapi/            OpenAPI 契约
    events/             异步事件契约
  domain/
    src/
      project/
      competitor/
      question/
      scan/
      fact-atom/        可信事实卡的内部最小事实单元（FactAtom）
      fact-store/       企业事实库
      gap/
        suppression/    竞品压制分析
        evidence-gap/   内容/信源缺口（页面可叫推荐证据缺口）
      asset/
      publishing/       发布状态机和渠道管理
      report/
      lead/
      assistant/        AI 来客助手（P2 占位）
  score/
    src/                AIRank 来客指数计算
  evidence/
    src/                快照、证据包、下载回执、source index
  crawler-lite/
    src/                自有轻量抓取和半自动采样
  kb-lite/
    src/                自有最小事实库、分段和检索
  xinghe-adapter/
    src/
      auth/             yudao 用户、租户、权限
      model/            yudao 模型和 key authority
      crawler/          Crawler Gateway client
      kb/               KB / Qdrant / Brand Corpus client
      workflow/         workflow-runner client
      content/          智能出版/内容工厂 client
      hermes/           Hermes 巡检和自动化 client
      status/           capability readiness
  ui/
    src/
      components/
      charts/
      theme/

docs/
  product/
  architecture/
  decisions/            含术语映射表 terminology.md
  handoff/

agents/
  dev/
  review/
  prompts/

tests/
  acceptance/
  contracts/
  fixtures/

ops/
  deployment/
  runbooks/

scripts/                开发和运维辅助脚本
```

## 为什么不把 AIRank 放进 XingheAI2026V2

`XingheAI2026V2` 当前是企业交付 AI 运行系统主仓，已经承载出版主线、营销主线、yudao、KB、crawler、workflow、治理和发布门禁。AIRank 是新 SaaS 产品线，如果直接塞进主仓，会带来三个问题：

- 产品交付节奏被旧主线门禁和历史复杂度拖住。
- AIRank 的企业品牌方模型会被出版/营销场景对象污染。
- 后续部署会形成对主仓运行时和目录路径的强依赖。

正确方式是：AIRank 独立仓承载产品体验和领域内核；`XingheAI2026V2` 保留可复用能力、contract、bridge 和经验沉淀。

## 空目录保留规则

工程初始化阶段，每个顶层目录放一个 `README.md` 或 `.gitkeep`，避免空目录在 Git 中丢失。后续进入编码后，按实际代码替换占位文件。
