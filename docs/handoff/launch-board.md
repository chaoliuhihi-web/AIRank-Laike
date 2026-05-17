# AIRank v0.1 Launch Board

目标：快速完成一个可上线 beta，让企业品牌方可以跑通“建项目 -> 竞品/问题 -> 扫描/导入结果 -> 评分 -> 缺口 -> AI 收录包 -> 报告”的闭环。

当前产品基线：

- 前端原型提交：`622b1f7 feat: implement console frontend prototype`
- 最新远端阶段提交：`a4de530 docs: detail low-touch hermes MVP flow`
- 前端：React + Vite 控制台原型已完成，当前为 fixture 数据。
- 后端：`apps/api` 已有 FastAPI baseline 和 `GET /api/v1/console/overview`。
- Worker：`apps/worker` 仍为空骨架。
- 数据库：`ops/deployment/mysql-bootstrap.sql` 已有 bootstrap schema，Alembic 尚未建立。
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

每轮只做一个可验证小闭环，并更新本文件和 `docs/handoff/review-ledger.md`。

自动协作机制见：

- `docs/handoff/agent-control.md`
- `docs/handoff/execution-packets.md`
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
| 建立 SQLAlchemy + Alembic | CodexiMac | todo | `alembic upgrade head` 可从空库建 schema |
| 项目/竞品/问题 CRUD | CodexWin | todo | tenant 过滤，contract test 通过 |
| 错误码和 trace_id 落地 | CodexWin | todo | 所有 API 返回 trace_id，错误码来自 `packages/contracts/error-codes.md` |
| 数据库 schema review | CodexMacPro | todo | tenant、索引、迁移、敏感字段检查通过 |

## Milestone 2：扫描和评分闭环

| Task | Owner | Status | Exit Criteria |
| --- | --- | --- | --- |
| scan run / scan task API | CodexWin | todo | 可创建 scan run 并查询状态 |
| worker job 领取和 heartbeat | CodexiMac | todo | queued/running/succeeded/failed/timeout 状态可复测 |
| mock/manual provider | CodexiMac | todo | 可生成 answer snapshot 和 citation |
| AIRank Score 纯函数 | CodexiMac | todo | 同一输入重复计算一致 |
| scan/score acceptance | CodexMacPro | todo | 从项目到 score 的测试通过 |

## Milestone 3：事实卡、缺口、AI 收录包

| Task | Owner | Status | Exit Criteria |
| --- | --- | --- | --- |
| FactAtom domain model | CodexiMac | todo | 每个 FactAtom 至少有 source/citation |
| fact review API | CodexWin | todo | 支持确认、驳回、需脱敏、不可公开 |
| content gap 生成 | CodexiMac | todo | 缺口可追溯到问题、citation、FactAtom |
| AI 收录包 API | CodexWin | todo | 前端 `AI 收录包` 页面可读取真实资产 |
| 事实链 review | CodexMacPro | todo | 无来源的内容不能进入报告 |

## Milestone 4：报告、前端接入、上线 beta

| Task | Owner | Status | Exit Criteria |
| --- | --- | --- | --- |
| 诊断报告 JSON | CodexiMac | todo | 每个结论可追溯到 snapshot/citation/FactAtom |
| report API + download receipt | CodexWin | todo | 报告中心可查看真实报告 |
| 前端 fixture 切 API | CodexWin | todo | 控制台主页面不再依赖硬编码 demo 数据 |
| GitHub Actions CI | CodexMacPro | done | web build + backend tests + diff check |
| v0.1 beta release gate | CodexMacPro | todo | `docs/handoff/release-gate.md` 全部通过 |

## 当前下一个推荐动作

1. CodexWin：领取 `M1-WIN-001 health-version-envelope`。
2. CodexiMac：领取 `M1-IMAC-001 alembic-initial-schema`。
3. CodexMacPro：领取 `M1-MACPRO-001 stage-review-current-head`。
