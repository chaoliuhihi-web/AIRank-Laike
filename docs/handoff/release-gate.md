# AIRank Release Gate

本文件是 AIRank v0.1 beta 上线前的强制门禁。未全部通过时，不允许声明“可上线”。

## Gate 0：仓库和远端

| Check | Command / Evidence | Required |
| --- | --- | --- |
| 工作区干净 | `git status --short --branch` | 无未提交业务变更 |
| GitHub main 指针 | `git ls-remote origin refs/heads/main` | 与本地 HEAD 一致 |
| Gitee main 指针 | `git ls-remote gitee refs/heads/main` | 与本地 HEAD 一致 |
| GitHub Actions CI | `.github/workflows/ci.yml` | diff check、static checks、API contract tests、web build 全部启用 |
| 无密钥入库 | `git grep -n "AKIA\\|SECRET\\|TOKEN\\|PASSWORD\\|sk-"` | 无真实密钥 |
| 运行产物未入库 | `git ls-files | rg "node_modules|dist|\\.runtime|\\.env|\\.sqlite|tsbuildinfo"` | 无非法文件 |

## Gate 1：前端

| Check | Command / Evidence | Required |
| --- | --- | --- |
| Web 构建 | `cd apps/web && npm run build` | 通过 |
| 控制台桌面渲染 | 浏览器访问 `http://localhost:5173/console`，1491x1055 截图 | 无白屏、无 overlay、无明显布局断裂 |
| 控制台移动渲染 | 390x844 截图 | 无横向溢出、主内容可读 |
| 路由切换 | 点击工作台、推荐缺口、AI 收录包、报告中心 | URL 和页面内容变化 |
| Console health | 浏览器 console | 无 error/warning |

## Gate 2：API

后端初始化后启用。

| Check | Command / Evidence | Required |
| --- | --- | --- |
| API health | `curl /api/v1/health` | 返回 ok 和 trace_id |
| API version | `curl /api/v1/version` | 返回 commit/version |
| response envelope | contract test | 所有 API 统一 envelope |
| error code | contract test | 错误码来自 registry |
| tenant isolation | acceptance test | 不能跨租户读取 |

## Gate 3：数据库和迁移

| Check | Command / Evidence | Required |
| --- | --- | --- |
| 空库迁移 | `alembic upgrade head` | 通过 |
| 回滚策略 | migration review | 破坏性变更有说明 |
| tenant 字段 | schema review | 业务表都有 tenant/project 过滤依据 |
| 索引 | schema review | 高频查询字段有索引 |
| 不跨库外键 | schema review | 不依赖 yudao 外键 |

## Gate 4：扫描、证据和评分

| Check | Command / Evidence | Required |
| --- | --- | --- |
| scan run 创建 | acceptance test | 可创建并查询状态 |
| task 状态机 | worker test | queued/running/succeeded/failed/timeout 可复测 |
| snapshot 保存 | DB/test evidence | 每个回答有 answer snapshot |
| citation 保存 | DB/test evidence | 每个引用来源有 citation |
| score 可复现 | score fixture test | 同一输入重复计算一致 |
| 失败显式化 | worker test | 失败不能长期停在 queued |

## Gate 5：FactAtom / 可信事实卡

| Check | Command / Evidence | Required |
| --- | --- | --- |
| 候选事实提取 | domain test | 可从 snapshot/citation 生成候选 FactAtom |
| 人工确认状态 | API/test | confirmed/rejected/needs_redaction/private |
| 来源追溯 | evidence test | 每个 confirmed FactAtom 至少一个 source |
| 客户侧术语 | UI/API review | 页面叫“可信事实卡”，内部可叫 FactAtom |

## Gate 6：报告和 AI 收录包

| Check | Command / Evidence | Required |
| --- | --- | --- |
| AI 收录包生成 | acceptance test | 可生成企业事实页、FAQ、案例页等资产 |
| 发布包记录 | DB/test | 有 publish package 和 object ref |
| 报告 JSON | report fixture | 包含 score、缺口、建议、证据索引 |
| 证据包 | evidence package | source index、snapshot index、download receipt |
| 报告追溯 | review | 关键结论可回溯到 snapshot/citation/FactAtom |

## Gate 7：Xinghe/yudao adapter

| Check | Command / Evidence | Required |
| --- | --- | --- |
| adapter 边界 | code review | 跨仓调用只在 `packages/xinghe-adapter` |
| capability status | API/test | ready/partial/blocked/disabled/dev_only |
| yudao auth | integration test or documented mock | 不可用时有 fallback |
| crawler/KB/Hermes | capability probe | 不可用不阻塞 MVP 主链 |

## Gate 8：上线结论

CodexMacPro 必须在 `docs/handoff/review-ledger.md` 写最终结论：

```text
Release Gate: PASS / BLOCKED / PASS_WITH_RISK
Commit:
Date:
Reviewer:
Residual risks:
```

只有 `PASS` 或经用户明确接受的 `PASS_WITH_RISK` 可以打 beta tag。

## 2026-05-17 18:08 +08:00 Execution

Release Gate: BLOCKED

Commit: `1a1def6`

Reviewer: CodexMacPro

Passed:

- GitHub and Gitee `main` both match local HEAD.
- CI workflow includes diff check, static checks, contract tests, and web build.
- `git diff --check` and tracked runtime artifact checks pass.
- `python3 -m pytest tests/contracts -q` passed 33 tests.
- `python3 -m pytest tests/acceptance -q` passed 9 tests.
- `cd apps/web && npm run build` passed.
- Worker, score, evidence, and xinghe-adapter package tests passed.
- API health/version passed via FastAPI TestClient with trace_id.
- `cd apps/api && python3 -m alembic upgrade head --sql` generated offline SQL.

Blocked:

- Real `alembic upgrade head` against local MySQL failed with `(1045) Access denied for user 'airank'@'192.168.65.1'`.
- yudao/Xinghe/Hermes capability probe remains `dev_only`; no real external readiness signal is available.
- Git secret grep only matched symbolic names such as `AUTH_TOKEN_*`, `YUDAO_BEARER_TOKEN`, and the release-gate pattern itself; no real secret value was identified in this pass.

Minimum fix before beta PASS:

- Re-run `ops/deployment/mysql-bootstrap.sql` or fix local/prod MySQL grants for the `airank` user, then rerun `cd apps/api && AIRANK_DATABASE_URL=... python3 -m alembic upgrade head`.
- Provide real yudao/Xinghe/Hermes configuration or explicitly accept a dev_only beta scope before tagging.
