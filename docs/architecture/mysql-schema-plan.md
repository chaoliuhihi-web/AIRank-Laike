# AIRank MySQL 建库方案

## 建库原则

AIRank 来客的长期真相源必须是自有 MySQL 主库。yudao 和 XingheAI2026V2 都是外部能力源，不拥有 AIRank 产品主数据。

推荐：

- MySQL 8.0+
- InnoDB
- `utf8mb4`
- 数据库名：`airank_laike`
- 主键：业务侧生成字符串 ID，例如 `prj_...`、`run_...`、`snap_...`
- 租户字段：所有核心业务表必须有 `tenant_id`
- 软删除：核心业务表保留 `deleted_at`
- 大对象：报告文件、网页快照原文、证据包文件放对象存储，MySQL 只保存 `object_uri` 和摘要

## 为什么不放进 yudao 数据库

yudao 负责账号、租户、权限、模型配置。AIRank 负责产品业务闭环。

把 AIRank 表放进 yudao 的 `ruoyi-vue-pro` 数据库会带来三个问题：

1. yudao 升级和 AIRank 迭代耦合，后续迁移风险高。
2. AIRank 扫描、快照、报告、证据包数据量会污染 yudao 管理库。
3. 独立 SaaS、私有化部署、客户隔离和计费会变复杂。

因此只保存 yudao ID 引用，不建立跨库外键。

## 核心领域表

| 表 | 作用 | MVP 必需 |
| --- | --- | --- |
| `airank_tenant_bindings` | yudao 租户与 AIRank 租户配置绑定 | 是 |
| `airank_user_bindings` | yudao 用户与 AIRank 用户缓存绑定 | 是 |
| `airank_projects` | 企业品牌项目 | 是 |
| `airank_competitors` | 竞品 | 是 |
| `airank_buyer_questions` | AI 来客问题地图 | 是 |
| `airank_scan_runs` | 一次扫描批次 | 是 |
| `airank_scan_tasks` | 单平台、单问题扫描任务 | 是 |
| `airank_scan_task_attempts` | 单采样槽 Worker 尝试、结果未知与证据关联台账 | 是 |
| `airank_answer_snapshots` | AI 回答快照 | 是 |
| `airank_source_citations` | 回答引用和来源归因 | 是 |
| `airank_answer_claims` | 回答内具体断言、精确字符边界和回答 hash | 是 |
| `airank_citation_support_reviews` | 断言—引用支持/矛盾/不足的追加式人工复核 | 是 |
| `airank_citation_source_captures` | 引用来源页不可变抓取、网络元数据与双对象引用 | 是 |
| `airank_citation_source_segments` | 来源正文确定性切片与精确字符边界 | 是 |
| `airank_page_audit_runs` | 官网技术可提取性运行、原始响应摘要、规则版本与独立技术分 | 是 |
| `airank_page_audit_findings` | 页面审计逐规则证据、扣分与整改建议 | 是 |
| `airank_fact_atoms` | 可信事实卡内部 FactAtom，含可信等级、可公开程度、来源片段、风险提示 | 是 |
| `airank_fact_sources` | FactAtom 与来源证据关系 | 是 |
| `airank_content_gaps` | 内容 / 信源缺口 | 是 |
| `airank_content_assets` | FAQ、选型指南、案例页等内容资产 | 是 |
| `airank_publish_packages` | 发布包导出、发布 URL、状态 | 是 |
| `airank_retest_runs` | 复测批次和增长对比 | 是 |
| `airank_reports` | 高管报告和诊断报告 | 是 |
| `airank_object_refs` | 网页快照、报告、证据包等对象引用 | 是 |
| `airank_async_jobs` | worker 任务状态 | 是 |
| `airank_outbox_events` | M2 事件分发 outbox，用于异步链路解耦 | 否 |
| `airank_integration_capabilities` | yudao / Xinghe 能力探测状态 | 是 |
| `airank_audit_events` | 审计事件 | 是 |

## 状态枚举

应用层统一使用以下状态，不依赖 MySQL `ENUM`：

```text
project.status: active, archived
scan_run.status: queued, running, completed, failed, canceled
scan_task.status: queued, running, completed, failed, skipped
fact_atom.status: draft, confirmed, rejected, stale
fact_atom.trust_level: A, B, C, D
fact_atom.disclosure: public, redacted, internal, forbidden, pending_approval
fact_atom.fact_type: brand_identity, product_service, customer_case, industry_solution, qualification, pricing, faq, competitor_diff, channel
content_gap.gap_type: evidence_gap, suppression, content_gap, source_gap, technical_gap
content_asset.status: draft, reviewed, packaged, published, stale
publish_package.status: draft, packaged, published, crawling, crawled, indexed, pending_retest, retested, failed
publish_package.channel: website, wechat_mp, zhihu, xiaohongshu, video_account, baidu, toutiao, industry_media
buyer_question.question_type: purchase, compare, select, trust, price, risk, scenario, local, alternative
async_job.status: queued, running, completed, failed, canceled
capability.status: ready, partial, blocked, disabled, dev_only
```

不用 MySQL `ENUM` 的原因是后续状态机还会扩展，用 `VARCHAR` 更利于灰度和迁移。

## 最小启动 DDL

当前可直接执行的 bootstrap SQL 已放在：

```text
ops/deployment/mysql-bootstrap.sql
```

执行顺序：

```bash
mysql -uroot -p < ops/deployment/mysql-bootstrap.sql
```

本地开发推荐连接串：

```text
AIRANK_DATABASE_URL=mysql+pymysql://airank:airank_dev_password@127.0.0.1:3306/airank_laike?charset=utf8mb4
```

生产环境必须替换密码，并按客户或环境隔离数据库账号。

`ops/deployment/mysql-bootstrap.sql` 是 M0 本地初始化快照。M0 结束前必须建立 Alembic 初始迁移，并把 Alembic migration 作为生产 schema 真相源；bootstrap SQL 后续只保留为开发环境快速初始化或由 migration 生成的快照。

## 第一轮迁移策略

1. M0 用 `ops/deployment/mysql-bootstrap.sql` 验证核心表。
2. M1 初始化 `apps/api` 后创建 Alembic `0001_initial_airank_schema`，内容必须与 bootstrap SQL 对齐。
3. `apps/api` 只访问 AIRank 主库，不直接访问 yudao 数据库。
4. `apps/api` 认证中间件调用 yudao `/admin-api/system/auth/get-permission-info`，拿到 `tenant_id` 和 user 后写入 binding 表。
5. `apps/worker` 从 `airank_async_jobs` 逐槽领取任务，在单事务中写 `scan_task_attempts`、`scan_tasks`、`answer_snapshots`、`evidence_snapshots`、`source_citations` 和 job 终态；全部槽终态后再聚合 `scan_runs`。
6. M2 开始由业务写入 `airank_outbox_events`，再由 outbox dispatcher 分发 `scan.completed`、`fact_atom.confirmed` 等事件。
7. `packages/xinghe-adapter/status` 定时刷新 `airank_integration_capabilities`。
8. 报告和证据包文件写对象存储，本库只写 `airank_object_refs`。

## 索引策略

第一版重点索引：

- 所有列表页：`tenant_id + project_id + updated_at`
- 扫描查询：`tenant_id + project_id + status + created_at`
- 回答快照：`tenant_id + project_id + run_id + question_id`
- 引用归因：`tenant_id + project_id + host`
- 事实库：`tenant_id + project_id + trust_level + disclosure`
- 事实类型：`tenant_id + project_id + fact_type`
- 发布渠道：`tenant_id + project_id + channel + status`
- worker：`status + scheduled_at`
- worker 心跳回收：`status + heartbeat_at`

暂不做全文索引。MVP 的事实检索先用 `kb-lite` 简单检索；后续接 Xinghe KB Service / Qdrant。

## M1 tenant / project 索引审查

本节是 `M1-IMAC-002` 的 schema/index review 结论。目标是让 CodexWin 后续 CRUD 和 CodexiMac worker 都有一致的查询边界，不通过 API 或 worker 绕过租户隔离。

### 查询字段基线

| 表 | tenant 字段 | project 字段 | 主要查询路径 | 当前索引结论 |
| --- | --- | --- | --- | --- |
| `airank_tenant_bindings` | `tenant_id` | 无 | 按 `tenant_id` / `yudao_tenant_id` 查绑定，按 `status` 巡检 | `uk_airank_tenant_bindings_tenant`、`uk_airank_tenant_bindings_yudao`、`idx_airank_tenant_bindings_status` 覆盖 |
| `airank_user_bindings` | `tenant_id` | 无 | 按租户和 `yudao_user_id` 查用户缓存，按租户状态列表 | `uk_airank_user_bindings_yudao`、`idx_airank_user_bindings_tenant_status` 覆盖 |
| `airank_projects` | `tenant_id` | `id` 即 project id | 租户项目列表、按品牌名查项目、软删除过滤 | `idx_airank_projects_tenant_status`、`idx_airank_projects_brand` 覆盖；API 必须额外过滤 `deleted_at IS NULL` |
| `airank_project_members` | `tenant_id` | `project_id` | 项目成员列表、按 yudao 用户查项目角色 | `uk_airank_project_members_user`、`idx_airank_project_members_project` 覆盖 |
| `airank_competitors` | `tenant_id` | `project_id` | 项目竞品列表，按 `priority` 排序 | `idx_airank_competitors_project` 覆盖；API 必须过滤 `deleted_at IS NULL` |
| `airank_buyer_questions` | `tenant_id` | `project_id` | 问题列表、按类型/意图筛选、按优先级排序 | `idx_airank_questions_project_priority`、`idx_airank_questions_type`、`idx_airank_questions_intent` 覆盖 |
| `airank_scan_runs` | `tenant_id` | `project_id` | 项目扫描批次列表、按状态筛选、租户级最近扫描 | `idx_airank_scan_runs_project_status`、`idx_airank_scan_runs_created` 覆盖 |
| `airank_scan_tasks` | `tenant_id` | `project_id` | worker 领取任务、项目任务状态列表、单 run 采样槽去重 | `idx_airank_scan_tasks_worker`、`idx_airank_scan_tasks_project`、`uk_airank_scan_tasks_sample` 覆盖 |
| `airank_scan_task_attempts` | `tenant_id` | `project_id` | 按 run/task 下钻 Worker attempt、未知结果、回答/证据关联 | `uk_airank_scan_attempt_number`、`idx_airank_scan_attempt_run`、`idx_airank_scan_attempt_job` 覆盖 |
| `airank_answer_snapshots` | `tenant_id` | `project_id` | 按 run/question 查回答，按品牌出现和排名统计 | `idx_airank_snapshots_run_question`、`idx_airank_snapshots_brand_rank` 覆盖 |
| `airank_source_citations` | `tenant_id` | `project_id` | 按 snapshot 回溯引用，按 host 做来源统计 | `idx_airank_citations_snapshot`、`idx_airank_citations_host` 覆盖 |
| `airank_answer_claims` | `tenant_id` | `project_id` | 按回答下钻断言、按边界/hash 幂等登记 | `uk_airank_answer_claim_boundary`、`idx_airank_answer_claim_project` 覆盖 |
| `airank_citation_support_reviews` | `tenant_id` | `project_id` | 按 claim/citation 读取追加历史，按证据等级统计可交付支持度 | `idx_airank_citation_support_claim`、`idx_airank_citation_support_project` 覆盖 |
| `airank_citation_source_captures` | `tenant_id` | `project_id` | 按 citation 回溯抓取历史，按状态领取/排障 | citation、status、idempotency、job 索引覆盖 |
| `airank_citation_source_segments` | `tenant_id` | `project_id` | 按 capture 和 segment index 重建完整正文、校验精确审核边界 | capture/index 唯一索引覆盖 |
| `airank_page_audit_runs` | `tenant_id` | `project_id` | 项目页面审计历史、按状态领取/回查、幂等创建 | `uk_airank_page_audit_idempotency`、`uk_airank_page_audit_job`、`idx_airank_page_audit_project`、`idx_airank_page_audit_status` 覆盖 |
| `airank_page_audit_findings` | `tenant_id` | `project_id` | 按运行下钻规则、按严重度/状态筛选 | `uk_airank_page_audit_rule`、`idx_airank_page_audit_finding_project` 覆盖 |
| `airank_fact_atoms` | `tenant_id` | `project_id` | 事实库列表、可信等级/公开等级筛选、事实类型筛选 | `idx_airank_fact_atoms_project_status`、`idx_airank_fact_atoms_trust`、`idx_airank_fact_atoms_type` 覆盖 |
| `airank_fact_sources` | `tenant_id` | `project_id` | FactAtom 来源回溯 | `idx_airank_fact_sources_fact` 覆盖 |
| `airank_content_gaps` | `tenant_id` | `project_id` | 项目缺口列表，按状态和严重度筛选 | `idx_airank_content_gaps_project_status` 覆盖 |
| `airank_content_assets` | `tenant_id` | `project_id` | 内容资产列表，按状态/类型筛选 | `idx_airank_content_assets_project_status`、`idx_airank_content_assets_type` 覆盖 |
| `airank_publish_packages` | `tenant_id` | `project_id` | 发布包状态、渠道列表、复测队列 | `idx_airank_publish_packages_status`、`idx_airank_publish_packages_channel`、`idx_airank_publish_packages_retest` 覆盖 |
| `airank_retest_runs` | `tenant_id` | `project_id` | 复测批次列表、按状态查询 | `idx_airank_retest_runs_project_status` 覆盖 |
| `airank_reports` | `tenant_id` | `project_id` | 报告列表、按类型和生成时间查询 | `idx_airank_reports_project_status`、`idx_airank_reports_type` 覆盖 |
| `airank_object_refs` | `tenant_id` | `project_id` 可空 | 对象引用列表、按 `sha256` 去重 | `idx_airank_object_refs_project`、`idx_airank_object_refs_sha` 覆盖 |
| `airank_async_jobs` | `tenant_id` | `project_id` 可空 | worker claim、heartbeat 回收、项目任务列表 | `idx_airank_async_jobs_claim`、`idx_airank_async_jobs_heartbeat`、`idx_airank_async_jobs_project` 覆盖 |
| `airank_provider_capacity_leases` | `tenant_id` | `project_id` | 按 Provider/配置指纹跨 Worker 领取并发槽、幂等拦截、TTL 回收 | idempotency、expiry、project 索引覆盖 |
| `airank_provider_capacity_states` | 无 | 无 | Provider/配置指纹级 token bucket 与在途并发计数 | 复合主键和 updated 索引覆盖；不保存凭证或客户内容 |
| `airank_provider_routes` | 无 | 无 | Provider 上游路由公开 manifest 历史、当前版本和配置指纹 | current、fingerprint 索引覆盖；只保存 host/model/priority，不保存密钥或密钥值 |
| `airank_provider_route_controls` | 无 | 无 | Provider 路由启停、优先级覆盖和乐观锁当前状态 | Provider/route 复合主键；只保存公开控制状态、操作者和理由，不保存凭证 |
| `airank_provider_route_control_events` | 无 | 无 | Provider 路由控制追加式审计历史 | Provider/route/version 唯一；应用禁止覆盖历史事件，回滚需先导出审计证据 |
| `airank_outbox_events` | `tenant_id` | `project_id` 可空 | outbox 发布、aggregate 回溯、trace 排查 | `idx_airank_outbox_events_publish`、`idx_airank_outbox_events_aggregate`、`idx_airank_outbox_events_trace` 覆盖 |
| `airank_integration_capabilities` | 无 | 无 | 能力探测状态，非租户业务数据 | `uk_airank_capabilities`、`idx_airank_capabilities_status` 覆盖 |
| `airank_audit_events` | `tenant_id` | `project_id` 可空 | 审计列表、实体审计、trace 排查 | `idx_airank_audit_events_project`、`idx_airank_audit_events_entity`、`idx_airank_audit_events_trace` 覆盖 |

### CRUD 和 worker 查询约束

- 所有 Product/API 列表、详情、更新、删除都必须从认证上下文拿 `tenant_id`，不能接受客户端传入的 `tenant_id` 作为授权依据。
- 有 `project_id` 的表，API 查询必须同时带 `tenant_id` 和 `project_id`。只用 `id` 查询时，也必须补充 `tenant_id` 条件。
- 软删除表的用户可见查询必须带 `deleted_at IS NULL`。历史审计、内部巡检或 backfill 可以读取软删除数据，但必须是独立代码路径。
- worker claim 类查询可以按 `status/scheduled_at/heartbeat_at` 走全局队列索引，但领取后写入、完成和回查项目数据时必须带 `tenant_id`。
- `airank_integration_capabilities` 是全局能力探测表，不保存客户业务内容；如果后续要做租户级能力覆盖，必须新增租户维度表或字段并重新评审索引。

### 敏感字段和脱敏要求

| 字段 / 字段组 | 风险 | M1 处理规则 |
| --- | --- | --- |
| `airank_user_bindings.mobile`, `email` | 个人联系方式 | API 默认不返回完整值；日志、错误和 audit payload 中必须脱敏 |
| `model_route_snapshot` | 可能包含模型路由和 key 指纹 | 只允许保存 provider、model、model_id、key_id、脱敏 key 指纹；禁止保存 API Key 明文 |
| `request_json`, `response_meta_json`, `payload_json`, `metadata_json` | 可能包含 prompt、客户字段、外部 trace | 写入前做字段 allowlist 或 redaction；日志只输出摘要 |
| `answer_text`, `cited_text`, `source_excerpt`, `fact_text`, `body_md` | 可能包含客户事实、销售资料、竞品描述 | 报告和发布包必须通过 FactAtom/source/citation gate；不允许无来源结论进入公开资产 |
| `object_uri` | 可能暴露对象存储路径 | 使用按租户隔离的路径前缀；API 返回下载 URL 时必须做授权校验 |
| `audit_events.payload_json` | 可能包含操作上下文 | 默认不在普通页面展示敏感 payload；导出需要管理员权限 |

### 外键边界

- 当前 DDL 只允许 AIRank 自有表之间建立外键，例如 project、run、question、snapshot、FactAtom 关系。
- 禁止对 yudao 数据库、XingheAI2026V2 数据库或其它外部系统建立跨库外键。
- yudao 和 Xinghe 字段只保存字符串引用或 snapshot：`yudao_tenant_id`、`yudao_user_id`、`external_trace_id`、`object_ref_id`、`model_route_snapshot`。
- 外部系统删除、改名或暂时不可用时，AIRank 业务表不能因为外部 FK 失败而无法读取历史报告、证据或审计记录。
- 如果未来需要强一致同步，用 adapter/outbox/reconcile job 处理，不通过跨库 FK 处理。

### M1 结论

- Bootstrap SQL 和 Alembic 初始迁移的核心 tenant/project 查询索引可支撑 M1 CRUD、M2 worker claim、M3/M4 证据回溯的最小闭环。
- M1 不新增 DDL；后续如出现慢查询，优先基于真实 query plan 新增 Alembic migration，不在业务代码里绕过租户过滤。
- 当前真实 `alembic upgrade head` 仍受本机 MySQL 授权影响，状态见 `docs/handoff/status/codex-imac.md` 的 `M1-IMAC-001 review_env_blocked`。

## 与 yudao 的字段映射

| AIRank 字段 | 来源 | 说明 |
| --- | --- | --- |
| `tenant_id` | yudao tenant-id | 必填，字符串保存 |
| `created_by` | yudao user id | 可为空，系统任务用 `system` |
| `updated_by` | yudao user id | 可为空 |
| `yudao_user_id` | yudao user id | 只在 binding 表保存 |
| `yudao_tenant_id` | yudao tenant-id | 只在 binding 表保存 |
| `model_route_snapshot` | yudao `/ai/model/resolve` | 扫描时固化一份 JSON，方便复盘 |

## 与 XingheAI2026V2 的字段映射

| AIRank 字段 | Xinghe 来源 | 说明 |
| --- | --- | --- |
| `external_trace_id` | Trace Store / Crawler / KB | 外部调用 trace，不作为主键 |
| `external_run_id` | workflow-runner / crawler job | 外部 job，不作为主键 |
| `external_kb_id` | KB Service / Brand Corpus | 后续增强检索时保存 |
| `source_capture` | Crawler Gateway | 作为 JSON 摘要保存，原始文件进对象存储 |
| `capability_status` | adapter status | 写 `airank_integration_capabilities` |

## 不建议现在做的事

- 不做分库分表。MVP 数据量用单库足够。
- 不做复杂权限表。权限先交给 yudao，AIRank 只做项目成员和角色缓存。
- 不做跨库外键。yudao 和 XingheAI2026V2 是外部系统。
- 不把网页 HTML、长回答、报告 PDF 全塞进 MySQL。
- 不先接完整 Qdrant。等 MySQL 主链跑通后再替换检索层。
