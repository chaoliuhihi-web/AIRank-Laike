# AIRank v0.1 Launch Board

目标：快速完成一个可上线 beta，让企业品牌方可以跑通“建项目 -> 竞品/问题 -> 扫描/导入结果 -> 评分 -> 缺口 -> AI 收录包 -> 报告”的闭环。

当前产品基线：

- 前端原型提交：`622b1f7 feat: implement console frontend prototype`
- 最新远端阶段提交：`9ca4fc9 feat: add mysql worker lease store`
- 前端：React + Vite 控制台原型已完成，当前为 fixture 数据。
- 后端：`apps/api` 已有 FastAPI baseline 和 `GET /api/v1/console/overview`。
- Worker：`apps/worker` 已有 in-memory 和 MySQL-backed async job lease/heartbeat、mock provider snapshot/citation、FactAtom、content gap、report evidence JSON 和 capability probe baseline；scan API 已能在 MySQL 路径写入 `airank_async_jobs`，真实 worker DB 消费仍需实库验证。
- 数据库：`ops/deployment/mysql-bootstrap.sql` 已有 bootstrap schema，Alembic 初始迁移已入库；2026-05-17 已在本机 `yudao-mysql` 容器验证 `airank` 应用用户、真实 `alembic upgrade head` 和 MySQL-backed 项目/竞品/问题/scan/assets/reports API。
- Contracts：`packages/contracts/console_overview.schema.json` 已有首个 dashboard slice contract。
- 审核：基础 CI 已覆盖 diff check、静态架构检查、API contract test 和 Web build；Release Gate 尚未执行完整通过。

## 协作规则

每个 AI 每轮必须：

```bash
git fetch origin
git merge --ff-only origin/main
```

完成后如果有提交，必须：

```bash
git push origin main
git push gitee main
```

每轮只做一个可验证小闭环。CodexWin / CodexiMac 更新自己的 `docs/handoff/status/<owner>.md`；CodexMacPro 汇总更新本文件和 `docs/handoff/review-ledger.md`。

自动协作机制见：

- `docs/handoff/agent-control.md`
- `docs/handoff/execution-packets.md`
- `docs/handoff/status/`
- `scripts/agent_control.py`
- `docs/handoff/director-brief.md`（本地生成）
- `docs/handoff/next-prompts/`（本地生成）

## Owner Lanes

| Lane | Owner | 主要目录 | 禁止抢占 |
| --- | --- | --- | --- |
| Product/API/Web | CodexWin | `apps/api`, `apps/web`, `packages/contracts`, `tests/contracts` | 不改 worker 深层调度，不改 score 核心算法 |
| Data/Worker/Evidence | CodexiMac | `apps/worker`, `packages/domain`, `packages/score`, `packages/evidence`, `packages/xinghe-adapter`, `ops/deployment` | 不改前端视觉主结构，不绕过 adapter |
| Review/Release | CodexMacPro | `tests`, `docs/handoff`, `docs/decisions`, `.github/workflows`, `agents/review` | 不抢业务主链，除非 blocker 小修 |

## Milestone 0：协作和门禁冻结

| Task | Owner | Status | Exit Criteria |
| --- | --- | --- | --- |
| 三 AI prompt 固化 | CodexMacPro | done | `agents/prompts/codex-win.md`, `codex-imac.md`, `codex-macpro.md` 可直接复制执行 |
| Launch Board 固化 | CodexMacPro | done | 本文件存在，并包含 owner、任务、exit criteria |
| Release Gate 固化 | CodexMacPro | done | `docs/handoff/release-gate.md` 存在 |
| Review Ledger 固化 | CodexMacPro | done | `docs/handoff/review-ledger.md` 存在 |

## Milestone 1：API + DB 最小主链

| Task | Owner | Status | Exit Criteria |
| --- | --- | --- | --- |
| 初始化 FastAPI 工程 | CodexWin | done | `/api/v1/health`, `/api/v1/version` 可用，统一 response envelope |
| Console overview API loop | CodexWin | done | `GET /api/v1/console/overview`、schema、contract test、web fallback 已有 |
| 建立 SQLAlchemy + Alembic | CodexiMac | review | migration SQL/parity 已通过；本机 `yudao-mysql` 容器已验证 `airank` dev credentials 和真实 `alembic upgrade head` |
| 错误码和 trace_id 落地 | CodexWin | review | 所有 API 返回 trace_id，错误码来自 `packages/contracts/error-codes.md` |
| 项目/竞品/问题 contract skeleton | CodexWin | review | request/response JSON Schema 和 contract tests 先冻结，不等 DB |
| 项目/竞品/问题 dev repository | CodexWin | dev_only | repository interface + in-memory/dev-only adapter 已打通 API；不作为生产持久化 |
| 项目/竞品/问题 CRUD | CodexWin | review | MySQL repository code path 已实现；`AIRANK_DATABASE_URL` 下 FastAPI TestClient 已验证项目、竞品、买家问题写入 |
| 数据库 schema review | CodexiMac | review | tenant、索引、迁移、敏感字段检查通过 |

## Milestone 2：扫描和评分闭环

| Task | Owner | Status | Exit Criteria |
| --- | --- | --- | --- |
| scan run / scan task API | CodexWin | review | MySQL 路径已在 fresh release-gate DB 验证：可创建 scan run/task，并写入 `airank_async_jobs` |
| worker job 领取和 heartbeat | CodexiMac | review | queued/running/succeeded/failed/timeout 状态在 in-memory 和 MySQL-backed store 可复测；fresh release-gate DB 已验证 claim/heartbeat/succeed/timeout/retry |
| mock/manual provider | CodexiMac | review | 可生成 answer snapshot 和 citation |
| AIRank Score 纯函数 | CodexiMac | review | 同一输入重复计算一致 |
| scan/score acceptance | CodexMacPro | review | 从项目到 question、scan run/task、snapshot、score 的 acceptance 测试通过 |

## Milestone 3：事实卡、缺口、AI 收录包

| Task | Owner | Status | Exit Criteria |
| --- | --- | --- | --- |
| FactAtom domain model | CodexiMac | review | 每个 FactAtom 至少有 source/citation |
| fact review API | CodexWin | review | 支持 confirmed/rejected/needs_redaction/private；confirmed 必须有 traceable source |
| content gap 生成 | CodexiMac | review | 缺口可追溯到问题、citation、FactAtom |
| AI 收录包 API | CodexWin | review | 配置 MySQL 时从 content assets/gaps/publish packages 派生资产包；fresh release-gate DB 已验证真实读取 |
| 事实链 review | CodexMacPro | review | acceptance 覆盖无来源 FactAtom 和缺 snapshot/citation/FactAtom 的报告结论失败 |

## Milestone 4：报告、前端接入、上线 beta

| Task | Owner | Status | Exit Criteria |
| --- | --- | --- | --- |
| 诊断报告 JSON | CodexiMac | review | 每个结论可追溯到 snapshot/citation/FactAtom |
| Xinghe/yudao capability probe | CodexiMac | dev_only | capability probe 已入库；本地矩阵全为 dev_only fallback，release 前需接真实 yudao/Xinghe/Hermes 环境验证 |
| report API + download receipt | CodexWin | review | 配置 MySQL 时从 `airank_reports` 读取报告，并把下载回执写入 `airank_audit_events`；fresh release-gate DB 已验证 |
| 前端 fixture 切 API | CodexWin | review | 控制台主页面 API-first；API 不可用时显示明确 fallback 状态 |
| GitHub Actions CI | CodexMacPro | done | web build + backend tests + diff check |
| v0.1 beta release gate | CodexMacPro | blocked | 自动化测试、真实 MySQL migration、MySQL-backed CRUD/scan/assets/reports/worker lease 已通过；外部 yudao token 未提供，capability 仍含 dev_only/partial，未获明确 dev_only beta scope 批准前不能声明可上线 |

## 当前下一个推荐动作

1. CodexMacPro：数据库 blocker 已解除；保持 release gate `blocked`，直到外部 yudao token/真实能力验证完成，或产品明确批准 dev_only beta scope。
2. CodexWin：当前 Product/API/Web packet 已推进到 `M4-WIN-002 review/dev_only`；不要重复执行 `M1-WIN-001C` / `M1-WIN-001D`。
3. CodexiMac：当前 Data/Worker/Evidence packet 已推进到 `M4-IMAC-002 dev_only`；等待真实外部环境或 CodexMacPro 拆分新的后续 packet，不要重复执行 capability probe。
