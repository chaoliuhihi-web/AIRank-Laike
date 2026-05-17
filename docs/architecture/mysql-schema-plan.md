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
| `airank_answer_snapshots` | AI 回答快照 | 是 |
| `airank_source_citations` | 回答引用和来源归因 | 是 |
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
5. `apps/worker` 从 `airank_async_jobs` 领取任务，写 `scan_runs`、`scan_tasks`、`answer_snapshots`、`source_citations`。
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
