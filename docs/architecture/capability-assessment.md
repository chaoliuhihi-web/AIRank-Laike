# AIRank 复用能力评估

评估日期：2026-05-17

评估对象：

- `XingheAI2026V2`：`/Users/bruce/Developer/work/XingheAI2026V2`
- yudao：`XingheAI2026V2/vendor/xingheai-yudao`
- AIRank：`/Users/bruce/Developer/work/AIRank`

## 结论

`yudao + XingheAI2026V2` 的基础能力足够支撑 AIRank 来客进入开发，但不足以直接替代 AIRank 自有产品主库和自有领域模型。

正确做法是：

1. AIRank 建独立 MySQL 主库，保存项目、竞品、问题、扫描、回答快照、引用、FactAtom、内容资产、发布包、复测和报告。
2. yudao 作为账号、租户、权限、模型配置的权威源，AIRank 只保存必要绑定和缓存。
3. XingheAI2026V2 作为能力供应方，通过 `packages/xinghe-adapter` 接入，不直接 import 主仓内部代码。
4. 所有外部能力必须有状态探测和 fallback；状态只能是 `ready`、`partial`、`blocked`、`disabled`、`dev_only` 之一。

## 能力判断

| 能力 | 当前可用性 | 是否足够 AIRank MVP | 证据 | AIRank 使用方式 |
| --- | --- | --- | --- | --- |
| yudao 账号 / 租户 / 权限 | `ready` | 足够 | `shared/bridges/auth.py` 已按 bearer token 调 `/admin-api/system/auth/get-permission-info`，并校验 `tenant-id` | `apps/api` 统一接 yudao token；本库保存 `tenant_id`、`yudao_user_id` 绑定 |
| yudao 模型 / API Key | `partial` | 基本足够 | yudao AI 模块有 `/ai/model/simple-list`、`/ai/model/resolve`，兼容接口返回 provider、model、api_base_url、api_key | AIRank adapter 只读模型路由；AIRank 自己做场景、预算、熔断和审计 |
| yudao AI 知识库 | `partial` | 不作为 MVP 主库 | yudao 有 `/ai/knowledge`、`/ai/knowledge/document`、`/ai/knowledge/segment` 管理接口 | 可作为企业已有知识导入源，不承载 AIRank 事实库主数据 |
| yudao AI workflow | `partial` | 不作为 MVP 编排核心 | yudao 有 `/ai/workflow` CRUD 和 test | 后续可映射 AIRank 固定流程，不阻塞 MVP |
| Xinghe Crawler Gateway | `partial` | 可增强，不可强依赖 | 有 fetch/discover/plan/job/audit/login profile 契约，blocked reason 已细化 | MVP 用 `crawler-lite`；复杂站点再调用 gateway |
| Xinghe KB Service / Qdrant | `partial` | 可增强，不可强依赖 | kb-service 目标是 MySQL 元数据 + Qdrant 索引，但 README 明确仍有过渡层 | MVP 用 AIRank MySQL + 简单检索；向量检索后续替换 |
| Xinghe KB Core MySQL store | `ready` | 可借鉴表设计 | `kb_core_store.py` 已支持 `SCN_KB_CORE_MYSQL_DSN`，有 `kb_documents`、`kb_segments` 等结构 | 只借鉴 document/version/segment 思路，不共用表 |
| Xinghe Trace MySQL store | `ready` | 可借鉴审计结构 | `trace_store.py` 支持 `SCN_TRACE_MYSQL_DSN`，有 session/event/reference | AIRank 自建 `airank_audit_events`、`airank_object_refs` |
| Brand Corpus | `partial` | 可借鉴，不直接复用 | public router 有 sources、review queue、runs、exports、KB ingestion、qdrant snapshot | 借鉴“品牌资料、审校、导出包、知识回流”流程 |
| Creator Marketing report evidence | `ready` | 足够借鉴 | 项目报告已有 evidence/source-index/download receipt 模式 | AIRank 自建证据包和高管报告下载回执 |
| Hermes / shared hermes policy | `partial` | 不阻塞 MVP | shared bridge 有 source policy、allowlist/governance tags；完整自动化仍需接入 | 后续做周期复测、异常巡检、自动报告 |
| workflow-runner | `partial` | 不阻塞 MVP | 主仓已有 workflow-runner 服务和 specs contract | MVP 用 `apps/worker` 自有 job；长任务成熟后迁移 |

## 不足点

### yudao 不足点

- yudao 的知识库和 workflow 是通用 AI 管理能力，不理解 AIRank 的“品牌项目、竞品压制、AI 来客问题、回答快照、引用归因、事实卡、内容缺口”。
- yudao 可以提供模型路由，但不负责 AIRank 的扫描策略、平台配额、失败重试、证据留存和报告审计。
- yudao 租户库不应承载 AIRank 大量业务表，否则后续独立部署、迁移、计费和客户隔离都会变复杂。

### XingheAI2026V2 不足点

- Crawler Gateway 和 KB Service 有价值，但当前属于平台能力，不是 AIRank 产品主库。
- Creator Marketing / Brand Corpus 与 AIRank 场景相近，但领域对象不同，不能整块复制。
- 部分能力仍有 `.runtime`、SQLite、缓存和过渡层，不适合作为 AIRank 第一版上线的硬依赖。

## 架构决策

### 主库

AIRank 使用独立 MySQL 数据库：

```text
airank_laike
```

不把 AIRank 表建到 yudao 的 `ruoyi-vue-pro` 数据库里，也不写入 XingheAI2026V2 的业务表。

### 身份和租户

AIRank 表中的 `tenant_id`、`created_by`、`updated_by` 使用 yudao 返回的 ID 字符串，但不建立跨数据库外键。

### 外部能力

`packages/xinghe-adapter` 输出统一能力状态：

```json
{
  "capability": "crawler_gateway",
  "status": "partial",
  "required_for_mvp": false,
  "fallback": "packages/crawler-lite",
  "checked_at": "2026-05-17T00:00:00+08:00"
}
```

### MVP 红线

只要 AIRank 自有 API、MySQL、worker、crawler-lite、kb-lite 可用，就可以进入 MVP 开发；不要等待 XingheAI2026V2 的所有能力都变成 `ready`。
